"""Pure policy filtering and deterministic Top3 selection for dailyRecs.

This module deliberately has no Firestore client.  It receives normalized
metadata and RRF items, which keeps the safety rules unit-testable and makes
the daily writer responsible only for I/O and run coverage.
"""

from __future__ import annotations

import copy
import hashlib
import os
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_AI_MODEL_DIR = os.environ.get(
    "AI_MODEL_DIR", os.path.join(_PROJECT_ROOT, "lib", "ai_recommend_model")
)
if _AI_MODEL_DIR not in sys.path:
    sys.path.insert(0, _AI_MODEL_DIR)

from seolleyeon_rec_common_v3 import (  # noqa: E402
    campus_life_zone_rejection,
    is_ai_profile,
    passes_policy,
)


@dataclass(frozen=True)
class DailySelectionConfig:
    topn: int = 3
    exploit_count: int = 2
    explore_count: int = 1
    manner_min: float = 33.0
    active_within_days: int = 14
    require_same_university: bool = True
    reciprocal: bool = True
    exclude_same_gender: bool = True
    # rollout activation. OFF 면 기존 추천 정책만 적용한다 (생활권 미강제).
    # 최종 정책 자체를 완화하는 것이 아니라 활성화 시점만 제어한다.
    campus_life_zone_enforced: bool = False


def _stable_tie(actor_uid: str, date_key: str, candidate_uid: str) -> str:
    payload = f"{actor_uid}|{date_key}|{candidate_uid}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _safe_score(item: Mapping[str, Any]) -> float:
    try:
        return float(item.get("score", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _feature_tokens(doc: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(doc, Mapping):
        return set()
    fields = (
        "features",
        "interests",
        "interestTags",
        "interestTagIds",
        "lifestyle",
        "lifestyleTags",
        "lifestyleTagIds",
        "keywords",
        "campusLifeZones",
    )
    tokens: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            for child in value.values():
                collect(child)
        elif isinstance(value, (list, tuple, set)):
            for child in value:
                collect(child)
        elif value is not None:
            text = str(value).strip().lower()
            if text:
                tokens.add(text)

    for field in fields:
        collect(doc.get(field))
    return tokens


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _dedupe_rrf_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue
        uid = str(item.get("uid") or "").strip()
        if not uid:
            continue
        candidate = copy.deepcopy(dict(item))
        candidate["uid"] = uid
        current = best.get(uid)
        if current is None:
            best[uid] = candidate
            continue
        current_key = (-_safe_score(current), str(current.get("rank", "")))
        candidate_key = (-_safe_score(candidate), str(candidate.get("rank", "")))
        if candidate_key < current_key:
            best[uid] = candidate
    return list(best.values())


def select_daily_items(
    actor_uid: str,
    rrf_items: Sequence[Mapping[str, Any]],
    policy_meta: Mapping[str, Mapping[str, Any]],
    *,
    date_key: str,
    candidate_docs: Mapping[str, Mapping[str, Any]] | None = None,
    blocked_by_actor: set[str] | None = None,
    nope_by_actor: set[str] | None = None,
    recent_exposure_by_actor: set[str] | None = None,
    config: DailySelectionConfig | None = None,
) -> dict[str, Any]:
    """Filter one actor's RRF feed and deterministically select up to Top3."""
    cfg = config or DailySelectionConfig()
    actor_uid = str(actor_uid)
    candidate_docs = candidate_docs or {}
    blocked = {str(uid) for uid in (blocked_by_actor or set())}
    noped = {str(uid) for uid in (nope_by_actor or set())}
    recently_seen = {str(uid) for uid in (recent_exposure_by_actor or set())}
    rejected: Counter[str] = Counter()
    # OFF 상태에서도 얼마나 걸릴지 관측한다 (coverage gate 판단 근거).
    observed: Counter[str] = Counter()

    eligible: list[dict[str, Any]] = []
    for item in _dedupe_rrf_items(rrf_items):
        uid = str(item["uid"])
        if uid == actor_uid:
            rejected["self"] += 1
            continue
        if is_ai_profile(uid):
            rejected["synthetic"] += 1
            continue
        if uid in blocked:
            rejected["blocked_or_reported"] += 1
            continue
        if uid in noped:
            rejected["nope"] += 1
            continue
        if uid in recently_seen:
            rejected["recent_exposure"] += 1
            continue

        actor_meta = policy_meta.get(actor_uid)
        candidate_meta = policy_meta.get(uid)

        # 생활권은 hard eligibility다. passes_policy 도 같은 조건을 강제하지만
        # 여기서 먼저 확인해 skip 사유를 구분 가능한 카운터로 남긴다.
        # rollout activation 이 OFF 면 관측만 하고 제외하지는 않는다.
        zone_rejection = campus_life_zone_rejection(actor_meta, candidate_meta)
        if zone_rejection is not None:
            if cfg.campus_life_zone_enforced:
                rejected[zone_rejection] += 1
                continue
            observed[zone_rejection] += 1

        if cfg.exclude_same_gender and actor_meta and candidate_meta:
            actor_gender = actor_meta.get("gender")
            candidate_gender = candidate_meta.get("gender")
            if actor_gender and candidate_gender and actor_gender == candidate_gender:
                rejected["gender"] += 1
                continue

        if not passes_policy(
            actor_uid,
            uid,
            dict(policy_meta),
            manner_min=float(cfg.manner_min),
            active_within_days=int(cfg.active_within_days),
            require_same_university=bool(cfg.require_same_university),
            reciprocal=bool(cfg.reciprocal),
            require_same_campus_life_zone=bool(cfg.campus_life_zone_enforced),
        ):
            rejected["policy"] += 1
            continue
        eligible.append(item)

    eligible.sort(
        key=lambda item: (
            -_safe_score(item),
            _stable_tie(actor_uid, date_key, str(item["uid"])),
            str(item["uid"]),
        )
    )

    limit = max(0, int(cfg.topn))
    selected: list[tuple[dict[str, Any], bool]] = []
    exploit_limit = min(limit, max(0, int(cfg.exploit_count)), len(eligible))
    for item in eligible[:exploit_limit]:
        selected.append((item, False))

    remaining = eligible[exploit_limit:]
    explore_limit = min(
        max(0, int(cfg.explore_count)),
        max(0, limit - len(selected)),
        len(remaining),
    )
    selected_features = [
        _feature_tokens(candidate_docs.get(str(item["uid"])))
        for item, _is_explore in selected
    ]

    for _ in range(explore_limit):
        if not remaining:
            break
        scores = [_safe_score(item) for item in remaining]
        lo, hi = min(scores), max(scores)
        span = hi - lo
        ranked: list[tuple[float, str, dict[str, Any], set[str]]] = []
        for item in remaining:
            features = _feature_tokens(candidate_docs.get(str(item["uid"])))
            max_similarity = max(
                (_jaccard(features, chosen) for chosen in selected_features),
                default=0.0,
            )
            novelty = 1.0 - max_similarity
            relevance = ((_safe_score(item) - lo) / span) if span > 0 else 0.0
            explore_score = 0.55 * relevance + 0.45 * novelty
            ranked.append(
                (
                    explore_score,
                    _stable_tie(actor_uid, date_key, str(item["uid"])),
                    item,
                    features,
                )
            )
        ranked.sort(key=lambda row: (-row[0], row[1], str(row[2]["uid"])))
        _score, _tie, chosen, features = ranked[0]
        selected.append((chosen, True))
        selected_features.append(features)
        remaining = [item for item in remaining if item is not chosen]

    if len(selected) < limit:
        for item in remaining:
            if len(selected) >= limit:
                break
            selected.append((item, False))

    output_items: list[dict[str, Any]] = []
    for rank, (item, is_explore) in enumerate(selected, start=1):
        output = copy.deepcopy(item)
        output["uid"] = str(output["uid"])
        output["rank"] = rank
        output["isExplore"] = bool(is_explore)
        output["selectionMode"] = "explore" if is_explore else "exploit"
        output_items.append(output)

    status = "ready" if output_items else "empty"
    return {
        "status": status,
        "items": output_items,
        "topN": len(output_items),
        "algorithmVersion": f"daily_v1_{date_key}",
        "selection": {
            "inputCount": len(rrf_items),
            "dedupedCount": len(_dedupe_rrf_items(rrf_items)),
            "eligibleCount": len(eligible),
            "rejected": dict(rejected),
            "campusLifeZoneEnforced": bool(cfg.campus_life_zone_enforced),
            "campusLifeZoneObserved": dict(observed),
            "exploitCount": sum(1 for _item, explore in selected if not explore),
            "exploreCount": sum(1 for _item, explore in selected if explore),
        },
    }


__all__ = ["DailySelectionConfig", "select_daily_items"]
