
#!/usr/bin/env python3
"""
Seolleyeon RRF (Reciprocal Rank Fusion) - improved

핵심 변경점
- source base weight 지원 (기본: clip=1.0, svd=0.8, knn=0.7, content=0.5)
- source 문서 signal meta를 읽어 user-level dynamic confidence down-weight 적용
- source 내부 중복 uid dedupe (best rank만 사용)
- item.rank 필드를 우선 사용하고, 없으면 리스트 순서 fallback
- source별 max rank / max items 제한으로 long-tail noise 억제
- scoreComponents / sourceRanks 저장으로 디버깅 가능
- status != ready / items 없음 / low-confidence source는 자동 skip
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover
    firestore = None

from seolleyeon_rec_common_v3 import (
    canonicalize_recommendation_target_id,
    is_ai_profile,
)
from seolleyeon_recommendation_privacy import (
    load_recommendation_privacy_policy,
)
from campus_life_zone_policy import (
    ACTIVATION_ENFORCED,
    ACTIVATION_OFF,
    load_campus_life_zone_activation_with_version,
)


DEFAULT_SOURCE_WEIGHTS: Dict[str, float] = {
    "clip": 1.0,
    "svd": 0.8,
    "knn": 0.7,
    "content": 0.5,
}


def require_firestore() -> None:
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is not installed.")


def parse_datekey(date_key: str) -> str:
    if len(date_key) != 8:
        raise ValueError("dateKey must be YYYYMMDD")
    return date_key


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def parse_source_weights_json(raw: Optional[str]) -> Dict[str, float]:
    out = dict(DEFAULT_SOURCE_WEIGHTS)
    if raw:
        out.update({str(k): float(v) for k, v in json.loads(raw).items()})
    return out


def load_source_doc(doc_ref) -> Optional[Dict[str, Any]]:
    try:
        snap = doc_ref.get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        items = data.get("items")
        if data.get("status") != "ready":
            return None
        if not isinstance(items, list) or len(items) == 0:
            return None
        return data
    except Exception as e:
        print(f"[warn] failed to load {doc_ref.path}: {e}")
        return None


def extract_item_rank(item: Dict[str, Any], fallback_rank: int) -> int:
    rank = safe_int(item.get("rank"), 0)
    if rank > 0:
        return rank
    return fallback_rank


def dedupe_source_items(
    items: Sequence[Dict[str, Any]],
    *,
    max_items: int,
) -> List[Tuple[str, int, Dict[str, Any]]]:
    """
    Returns list of (uid, best_rank, best_item_payload) sorted by best_rank asc.
    source 내부에 uid 중복이 있으면 가장 좋은 rank만 남긴다.
    """
    best: Dict[str, Tuple[int, Dict[str, Any]]] = {}
    for idx, item in enumerate(items, start=1):
        uid = item.get("uid")
        if not uid:
            continue
        uid = canonicalize_recommendation_target_id(str(uid))
        if is_ai_profile(uid):
            continue
        rank = extract_item_rank(item, idx)
        cur = best.get(uid)
        if cur is None or rank < cur[0]:
            best[uid] = (rank, dict(item))

    deduped = sorted(((uid, rank, payload) for uid, (rank, payload) in best.items()), key=lambda x: x[1])
    return deduped[:max_items]


def derive_source_confidence(
    source_name: str,
    data: Dict[str, Any],
    *,
    min_confidence: float,
) -> float:
    """
    source doc에 signal.confidence가 있으면 우선 사용.
    없으면 totalPairs / strongPairs / totalWeight 기반으로 heuristic 산출.
    """
    if source_name == "clip":
        return 1.0

    signal = data.get("signal")
    if isinstance(signal, dict):
        explicit = signal.get("confidence")
        if isinstance(explicit, (int, float)):
            return clamp(float(explicit), min_confidence, 1.0)

        total_pairs = safe_int(signal.get("totalPairs"), 0)
        strong_pairs = safe_int(signal.get("strongPairs"), 0)
        total_weight = safe_float(signal.get("totalWeight"), 0.0)

        # saturation targets
        if source_name == "svd":
            tp_sat, sp_sat, tw_sat = 10.0, 5.0, 20.0
            eligible = bool(signal.get("eligibleForSvd", True))
        elif source_name == "knn":
            tp_sat, sp_sat, tw_sat = 10.0, 4.0, 20.0
            eligible = bool(signal.get("eligibleForKnn", True))
        else:
            tp_sat, sp_sat, tw_sat = 10.0, 4.0, 20.0
            eligible = True

        c_pairs = min(1.0, total_pairs / tp_sat) if tp_sat > 0 else 1.0
        c_strong = min(1.0, strong_pairs / sp_sat) if sp_sat > 0 else 1.0
        c_weight = min(1.0, total_weight / tw_sat) if tw_sat > 0 else 1.0
        conf = 0.20 + 0.35 * c_pairs + 0.35 * c_strong + 0.10 * c_weight
        if not eligible:
            conf *= 0.25
        return clamp(conf, min_confidence, 1.0)

    return 1.0 if source_name == "clip" else min_confidence


def source_policy_state(raw: Dict[str, Any]) -> Optional[str]:
    """소스 문서에 기록된 생활권 정책 상태를 읽는다.

    provenance 가 없는 legacy 문서는 ``None`` 이다. 어떤 정책으로 만들어졌는지
    알 수 없다는 뜻이므로, 활성화된 상태에서는 재사용하지 않는다.
    """
    policy = raw.get("policy")
    if not isinstance(policy, dict):
        return None
    state = policy.get("campusLifeZone")
    return state if isinstance(state, str) and state else None


def passes_source_quality_gate(
    merge_meta: Dict[str, Any], min_sources_per_user: int
) -> bool:
    """단일 소스만으로 만들어진 피드를 내보내지 않기 위한 품질 게이트.

    예: SVD 신호만 있는 사용자는 협업필터 잔재만 보게 되므로
    fused feed 로 내보내지 않는다 (§28 의 min_sources_per_user).
    """
    return len(merge_meta.get("usedSources", [])) >= int(min_sources_per_user)


def rrf_merge(
    source_docs: Dict[str, Dict[str, Any]],
    *,
    source_names: Sequence[str],
    source_weights: Dict[str, float],
    rrf_k: int,
    max_items_per_source: int,
    max_rank_per_source: int,
    use_dynamic_confidence: bool,
    min_source_confidence: float,
    min_effective_weight: float,
    topn: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Returns:
      merged_items
      merge_meta
    """
    scores: Dict[str, float] = {}
    source_ranks: Dict[str, Dict[str, int]] = {}
    score_components: Dict[str, Dict[str, float]] = {}
    effective_weights: Dict[str, float] = {}
    used_sources: List[str] = []

    for source_name in source_names:
        data = source_docs.get(source_name)
        if not data:
            continue

        base_weight = float(source_weights.get(source_name, 1.0))
        confidence = derive_source_confidence(
            source_name,
            data,
            min_confidence=min_source_confidence,
        ) if use_dynamic_confidence else 1.0

        eff_weight = base_weight * confidence
        if eff_weight < min_effective_weight:
            continue

        items = dedupe_source_items(
            data.get("items", []),
            max_items=max_items_per_source,
        )
        if not items:
            continue

        used_sources.append(source_name)
        effective_weights[source_name] = round(eff_weight, 6)

        for uid, rank, _payload in items:
            if is_ai_profile(uid):
                continue
            if rank <= 0 or rank > max_rank_per_source:
                continue
            contrib = eff_weight / (rrf_k + rank)
            scores[uid] = scores.get(uid, 0.0) + contrib
            source_ranks.setdefault(uid, {})[source_name] = rank
            score_components.setdefault(uid, {})[source_name] = round(contrib, 8)

    sorted_items = sorted(
        scores.items(),
        key=lambda kv: (
            -kv[1],
            min(source_ranks.get(kv[0], {}).get("clip", math.inf),
                min(source_ranks.get(kv[0], {}).values()) if source_ranks.get(kv[0]) else math.inf),
        ),
    )

    merged: List[Dict[str, Any]] = []
    for rank, (uid, score) in enumerate(sorted_items[:topn], start=1):
        merged.append({
            "uid": uid,
            "rank": rank,
            "score": round(float(score), 8),
            "sourceRanks": source_ranks.get(uid, {}),
            "scoreComponents": score_components.get(uid, {}),
        })

    merge_meta = {
        "usedSources": used_sources,
        "effectiveWeights": effective_weights,
    }
    return merged, merge_meta


def main() -> int:
    p = argparse.ArgumentParser(description="Seolleyeon RRF merge + Firestore export (improved)")
    p.add_argument("--firestore_project", type=str, required=True)
    p.add_argument("--firestore_database", type=str, default=None)
    p.add_argument("--date_key", type=str, required=True, help="YYYYMMDD (KST)")
    p.add_argument("--sources", type=str, default="clip,svd,knn",
                   help="Comma-separated source names")
    p.add_argument("--source_weights_json", type=str, default=None,
                   help='e.g. {"clip":1.0,"svd":0.4,"knn":0.7,"content":0.5}')
    p.add_argument("--rrf_k", type=int, default=60)
    p.add_argument("--topn", type=int, default=400)

    # source truncation / quality guardrails
    p.add_argument("--max_items_per_source", type=int, default=300)
    p.add_argument("--max_rank_per_source", type=int, default=300)
    # canonical default 는 2 다 (recsys/main.py 와 동일).
    # SVD 신호만 있는 사용자를 융합 피드로 내보내지 않기 위한 품질 게이트.
    p.add_argument("--min_sources_per_user", type=int, default=2)

    # dynamic confidence
    p.add_argument("--use_dynamic_confidence", dest="use_dynamic_confidence", action="store_true")
    p.add_argument("--no_dynamic_confidence", dest="use_dynamic_confidence", action="store_false")
    p.set_defaults(use_dynamic_confidence=True)
    p.add_argument("--min_source_confidence", type=float, default=0.20)
    p.add_argument("--min_effective_weight", type=float, default=0.05)

    # optional requirement
    # 생활권 rollout activation. 지정하지 않으면 config 문서를 따른다.
    p.add_argument(
        "--enforce_campus_life_zone",
        dest="enforce_campus_life_zone",
        action="store_true",
        default=None,
    )
    p.add_argument(
        "--no_enforce_campus_life_zone",
        dest="enforce_campus_life_zone",
        action="store_false",
    )

    p.add_argument("--required_sources", type=str, default="",
                   help="Comma-separated sources that must exist to export a user, e.g. clip")

    args = p.parse_args()
    require_firestore()

    date_key = parse_datekey(args.date_key)
    source_names = [s.strip() for s in args.sources.split(",") if s.strip()]
    required_sources = {s.strip() for s in args.required_sources.split(",") if s.strip()}
    source_weights = parse_source_weights_json(args.source_weights_json)

    db = firestore.Client(project=args.firestore_project, database=args.firestore_database)
    privacy_policy = load_recommendation_privacy_policy(db)

    # 생활권 정책 상태. 조회 실패(UNKNOWN)면 여기서 예외가 올라와 배치가 멈춘다.
    # 활성화 여부를 모른 채 융합 피드를 새로 쓰지 않기 위해서다.
    if args.enforce_campus_life_zone is None:
        campus_zone_state, campus_zone_policy_version = (
            load_campus_life_zone_activation_with_version(db)
        )
    else:
        campus_zone_state = (
            ACTIVATION_ENFORCED if args.enforce_campus_life_zone else ACTIVATION_OFF
        )
        campus_zone_policy_version = 0
    print(
        f"[RRF] campusLifeZone policy: {campus_zone_state} "
        f"(version {campus_zone_policy_version})"
    )
    policy_provenance = {
        "campusLifeZone": campus_zone_state,
        "campusLifeZonePolicyVersion": int(campus_zone_policy_version),
    }
    stale_policy_sources = 0

    user_ids = [doc.id for doc in db.collection("modelRecs").list_documents()]
    print(f"[RRF] scanning users in modelRecs: {len(user_ids):,}")

    recs_to_export: Dict[str, List[Dict[str, Any]]] = {}
    merge_meta_by_uid: Dict[str, Dict[str, Any]] = {}
    empty_status_by_uid: Dict[str, str] = {}
    privacy_ineligible_user_ids: Set[str] = set()

    for uid in user_ids:
        if uid not in privacy_policy.ready_user_ids:
            empty_status_by_uid[uid] = "viewer_privacy_not_ready"
            privacy_ineligible_user_ids.add(uid)
            continue

        source_docs: Dict[str, Dict[str, Any]] = {}
        source_statuses: Dict[str, str] = {}
        for source_name in source_names:
            doc_ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/{source_name}")
            try:
                snap = doc_ref.get()
            except Exception as exc:
                print(f"[warn] failed to read {doc_ref.path}: {exc}")
                continue
            if snap.exists:
                raw = snap.to_dict() or {}
                source_statuses[source_name] = str(raw.get("status") or "unknown")
                if campus_zone_state == ACTIVATION_ENFORCED:
                    # 정책이 켜진 뒤에는 "생활권을 적용하지 않고 만든" 소스를
                    # 융합하지 않는다. provenance 가 없는 legacy 문서도 같다.
                    if source_policy_state(raw) != ACTIVATION_ENFORCED:
                        stale_policy_sources += 1
                        continue
            data = load_source_doc(doc_ref)
            if data is not None:
                source_docs[source_name] = data

        if not source_docs and source_statuses:
            empty_status_by_uid.setdefault(uid, "stale_campus_life_zone_policy")
        if not source_docs:
            if source_statuses:
                empty_status_by_uid[uid] = "no_ready_model_source"
            continue
        if required_sources and not required_sources.issubset(set(source_docs.keys())):
            if required_sources.intersection(source_statuses):
                empty_status_by_uid[uid] = "required_source_empty_or_skipped"
            continue

        # Merge every candidate that can survive the per-source caps before
        # applying privacy. Truncating to topN first could leave fewer cards
        # even though a safe rank N+1 candidate exists.
        privacy_prefilter_limit = max(
            int(args.topn),
            int(args.max_items_per_source) * max(1, len(source_names)),
        )
        merged, merge_meta = rrf_merge(
            source_docs,
            source_names=source_names,
            source_weights=source_weights,
            rrf_k=int(args.rrf_k),
            max_items_per_source=int(args.max_items_per_source),
            max_rank_per_source=int(args.max_rank_per_source),
            use_dynamic_confidence=bool(args.use_dynamic_confidence),
            min_source_confidence=float(args.min_source_confidence),
            min_effective_weight=float(args.min_effective_weight),
            topn=privacy_prefilter_limit,
        )
        merged = privacy_policy.filter_items(uid, merged)
        merged = merged[: int(args.topn)]
        for rank, item in enumerate(merged, start=1):
            item["rank"] = rank

        if not merged:
            empty_status_by_uid[uid] = "no_privacy_eligible_candidates"
            continue
        if not passes_source_quality_gate(
            merge_meta, int(args.min_sources_per_user)
        ):
            empty_status_by_uid[uid] = "insufficient_sources"
            continue

        recs_to_export[uid] = merged
        merge_meta_by_uid[uid] = merge_meta

    print(f"[export] prepared RRF docs: {len(recs_to_export):,}")

    bw = db.bulk_writer()
    gen_at = firestore.SERVER_TIMESTAMP
    algo_version = f"rrf_v2_k{args.rrf_k}_{date_key}"
    model_meta = {
        "type": "rrf",
        "k": int(args.rrf_k),
        "sources": source_names,
        "sourceWeights": source_weights,
        "useDynamicConfidence": bool(args.use_dynamic_confidence),
        "minSourceConfidence": float(args.min_source_confidence),
        "minEffectiveWeight": float(args.min_effective_weight),
        "maxItemsPerSource": int(args.max_items_per_source),
        "maxRankPerSource": int(args.max_rank_per_source),
        "generatedAt": datetime.now(tz=timezone.utc).isoformat(),
    }

    for uid, items in recs_to_export.items():
        doc_ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/rrf")
        payload = {
            "status": "ready",
            "algorithmVersion": algo_version,
            "model": model_meta,
            "generatedAt": gen_at,
            "topN": len(items),
            "items": items,
            "merge": merge_meta_by_uid.get(uid, {}),
            "policy": policy_provenance,
        }
        bw.set(doc_ref, payload, merge=True)

    # A rerun for the same date must not leave an older ready RRF document
    # behind when the viewer or every candidate became privacy-ineligible.
    for uid, reason in empty_status_by_uid.items():
        if uid in recs_to_export:
            continue
        doc_ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/rrf")
        bw.set(
            doc_ref,
            {
                "status": "ineligible"
                if uid in privacy_ineligible_user_ids
                else "empty",
                "algorithmVersion": algo_version,
                "model": model_meta,
                "generatedAt": gen_at,
                "topN": 0,
                "items": [],
                "reason": reason,
                "policy": policy_provenance,
            },
            # Clear every stale ready-only field from a previous run.
            merge=False,
        )

    bw.close()
    if stale_policy_sources:
        print(
            "[RRF] skipped stale-policy source docs: "
            f"{stale_policy_sources:,} (campusLifeZone enforced)"
        )
    print("[export] RRF done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
