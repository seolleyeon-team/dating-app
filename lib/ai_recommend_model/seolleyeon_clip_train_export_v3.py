#!/usr/bin/env python3
"""
Seolleyeon CLIP-based Recommender v3

주요 보완점
- recEvents top-level / subcollection 모두 지원
- like/nope만이 아니라 pair-level 정제된 strong positive / final negative 사용
- final negative가 있는 pair는 positive preference에서 제거하고 negative vector로만 반영
- AI 취향 카드(female_*, male_*)는 preference 학습에는 선택적으로 사용하되 추천 후보에서는 제외
- few-shot signal일 때 self-profile similarity와 preference vector를 confidence 기반으로 블렌딩
- profileIndex 정책 필터 / reciprocal / same-university 지원
- signal meta 저장으로 RRF 및 디버깅에 활용 가능
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import quote

import numpy as np
from tqdm import tqdm

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover
    firestore = None

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

from seolleyeon_clip_embedder import SeolleyeonCLIPEmbedder
from seolleyeon_rec_common_v3 import (
    DEFAULT_EVENT_WEIGHTS,
    DEFAULT_FIRESTORE_LAYOUT,
    DEFAULT_NEGATIVE_EVENTS,
    DEFAULT_NEGATIVE_PREF_WEIGHTS,
    DEFAULT_STRONG_POSITIVE_EVENTS,
    PairBuildConfig,
    clamp01,
    collapse_pair_events,
    compute_clip_signal_confidence,
    compute_user_signal_stats,
    is_ai_profile,
    load_events_from_csv,
    load_events_from_firestore,
    load_profile_index_from_firestore,
    load_user_genders_from_firestore,
    load_users_with_photos_from_firestore,
    passes_policy,
    require_firestore,
)


def parse_datekey(date_key: str) -> str:
    if len(date_key) != 8:
        raise ValueError("dateKey must be YYYYMMDD")
    return date_key


def safe_json_update(base: Dict[str, Any], raw: Optional[str]) -> Dict[str, Any]:
    out = dict(base)
    if raw:
        out.update(json.loads(raw))
    return out


def ai_profile_to_storage_url(
    ai_profile_id: str,
    *,
    bucket: str = "seolleyeon.firebasestorage.app",
) -> str:
    m = re.match(r"^(female|male)_(\d+)$", str(ai_profile_id))
    if not m:
        raise ValueError(f"Invalid ai_profile_id: {ai_profile_id}")
    folder, pid = m.group(1), m.group(2)
    path = f"ai_profiles/{folder}/{pid}.png"
    encoded = quote(path, safe="")
    return f"https://firebasestorage.googleapis.com/v0/b/{bucket}/o/{encoded}?alt=media"


def add_ai_profiles_to_uid_urls(
    uid_to_urls: Dict[str, List[str]],
    target_ids: Sequence[str],
    *,
    bucket: str = "seolleyeon.firebasestorage.app",
) -> None:
    seen: set[str] = set()
    for t in target_ids:
        if not is_ai_profile(t):
            continue
        if t in uid_to_urls or t in seen:
            continue
        seen.add(t)
        try:
            url = ai_profile_to_storage_url(t, bucket=bucket)
            uid_to_urls[t] = [url]
        except Exception:
            pass


def l2_normalize_np(x: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    norm = float(np.linalg.norm(x))
    if norm <= eps:
        return x.astype(np.float32, copy=False)
    return (x / norm).astype(np.float32, copy=False)


def weighted_mean_from_targets(
    targets: Sequence[Tuple[str, float]],
    uid_to_vec: Dict[str, Sequence[float]],
    *,
    exclude_uid: Optional[str] = None,
) -> Tuple[Optional[np.ndarray], int]:
    vecs: List[np.ndarray] = []
    weights: List[float] = []
    for target_uid, weight in targets:
        if exclude_uid is not None and target_uid == exclude_uid:
            continue
        if target_uid not in uid_to_vec:
            continue
        w = float(weight)
        if w <= 0:
            continue
        vecs.append(np.asarray(uid_to_vec[target_uid], dtype=np.float32))
        weights.append(w)
    if not vecs:
        return None, 0
    mat = np.stack(vecs, axis=0)
    ws = np.asarray(weights, dtype=np.float32)
    if float(ws.sum()) <= 0:
        return None, 0
    mean = np.average(mat, axis=0, weights=ws)
    return l2_normalize_np(mean.astype(np.float32, copy=False)), len(vecs)


def export_to_firestore(
    project_id: str,
    date_key: str,
    recommendations: Dict[str, List[Dict[str, Any]]],
    *,
    algorithm_version: str,
    model_meta: Dict[str, Any],
    user_signal_meta: Optional[Dict[str, Dict[str, Any]]] = None,
    database: Optional[str] = None,
) -> None:
    require_firestore()
    db = firestore.Client(project=project_id, database=database)
    bw = db.bulk_writer()
    gen_at = firestore.SERVER_TIMESTAMP

    for uid, items in recommendations.items():
        doc_ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/clip")
        payload: Dict[str, Any] = {
            "status": "ready",
            "algorithmVersion": algorithm_version,
            "model": model_meta,
            "generatedAt": gen_at,
            "topN": len(items),
            "items": items,
        }
        if user_signal_meta and uid in user_signal_meta:
            payload["signal"] = user_signal_meta[uid]
        bw.set(doc_ref, payload, merge=True)

    bw.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Seolleyeon CLIP-based recommendation + Firestore export v3")
    p.add_argument("--firestore_project", type=str, required=True, help="GCP project id")
    p.add_argument("--firestore_database", type=str, default=None)
    p.add_argument("--date_key", type=str, required=True, help="YYYYMMDD (KST)")
    p.add_argument("--lookback_days", type=int, default=120)
    p.add_argument("--topn", type=int, default=400)
    p.add_argument("--oversample", type=int, default=6)
    p.add_argument("--device", type=str, default="auto")
    p.add_argument("--export_firestore", action="store_true", default=True)
    p.add_argument("--users_collection", type=str, default="users")
    p.add_argument("--events_collection", type=str, default="recEvents")
    p.add_argument(
        "--events_layout",
        type=str,
        default=DEFAULT_FIRESTORE_LAYOUT,
        choices=["auto", "top_level", "user_subcollections"],
    )
    p.add_argument("--events_csv", type=str, default=None)
    p.add_argument("--firestore_events", action="store_true", help="호환성용 플래그. events_csv가 없으면 Firestore 사용")
    p.add_argument("--skip_clip_if_no_torch", action="store_true", help="torch 미설치 시 CLIP 스킵")

    p.add_argument("--event_weights_json", type=str, default=None)
    p.add_argument("--negative_events_json", type=str, default=None)
    p.add_argument("--strong_positive_events_json", type=str, default=None)
    p.add_argument("--negative_pref_weights_json", type=str, default=None)
    p.add_argument("--half_life_days", type=float, default=30.0)
    p.add_argument("--max_weight_per_pair", type=float, default=12.0)
    p.add_argument("--allow_open_only_pairs", action="store_true")
    p.add_argument("--exclude_ai_profiles_from_preference", action="store_true")
    p.add_argument("--negative_pref_scale", type=float, default=0.7)
    p.add_argument("--no_blend_self_profile", action="store_true")

    p.add_argument("--apply_policy_filters", action="store_true")
    p.add_argument("--profile_index_collection", type=str, default="profileIndex")
    p.add_argument("--manner_min", type=float, default=33.0)
    p.add_argument("--active_within_days", type=int, default=14)
    p.add_argument("--require_same_university", dest="require_same_university", action="store_true")
    p.add_argument("--no_require_same_university", dest="require_same_university", action="store_false")
    p.set_defaults(require_same_university=True)
    p.add_argument("--no_reciprocal", action="store_true")

    p.add_argument("--algorithm_version", type=str, default=None)
    args = p.parse_args()
    date_key = parse_datekey(args.date_key)

    event_weights = safe_json_update(DEFAULT_EVENT_WEIGHTS, args.event_weights_json)
    negative_events = set(json.loads(args.negative_events_json)) if args.negative_events_json else set(DEFAULT_NEGATIVE_EVENTS)
    strong_positive_events = (
        set(json.loads(args.strong_positive_events_json))
        if args.strong_positive_events_json
        else set(DEFAULT_STRONG_POSITIVE_EVENTS)
    )
    negative_pref_weights = safe_json_update(DEFAULT_NEGATIVE_PREF_WEIGHTS, args.negative_pref_weights_json)

    print("[1] Loading users with photos...")
    uid_to_urls = load_users_with_photos_from_firestore(
        args.firestore_project,
        users_collection=args.users_collection,
        database=args.firestore_database,
    )
    print(f"    Loaded {len(uid_to_urls)} users with photos")
    if len(uid_to_urls) < 2:
        print("[!] Not enough users with photos. Skipping CLIP export.")
        return 0

    if args.events_csv:
        df = load_events_from_csv(args.events_csv)
    else:
        kst = timezone(timedelta(hours=9))
        yyyy, mm, dd = int(date_key[:4]), int(date_key[4:6]), int(date_key[6:8])
        end_kst = datetime(yyyy, mm, dd, 23, 59, 59, tzinfo=kst)
        start_utc = (end_kst - timedelta(days=int(args.lookback_days))).astimezone(timezone.utc)
        end_utc = end_kst.astimezone(timezone.utc)
        df = load_events_from_firestore(
            args.firestore_project,
            collection=args.events_collection,
            start_time_utc=start_utc,
            end_time_utc=end_utc,
            layout=args.events_layout,
            database=args.firestore_database,
        )
    print(f"[events] loaded events: {len(df):,}")

    pair_df_all = None
    neg_df_all = None
    signal_meta_by_uid: Dict[str, Dict[str, Any]] = {}
    pos_by_user: Dict[str, Any] = {}
    neg_by_user: Dict[str, Any] = {}

    if df is not None and not df.empty:
        pair_cfg = PairBuildConfig(
            event_weights=event_weights,
            negative_events=negative_events,
            strong_positive_events=strong_positive_events,
            half_life_days=float(args.half_life_days),
            max_weight_per_pair=float(args.max_weight_per_pair),
            allow_open_only_pairs=bool(args.allow_open_only_pairs),
            exclude_ai_items_from_training=bool(args.exclude_ai_profiles_from_preference),
        )
        pair_df_all, neg_df_all = collapse_pair_events(df, pair_cfg)
        print(f"[pairs] surviving positive pairs: {len(pair_df_all):,}")
        print(f"[pairs] final negative pairs: {0 if neg_df_all.empty else len(neg_df_all):,}")

        signal_df = compute_user_signal_stats(pair_df_all)
        for _, row in signal_df.iterrows():
            uid = str(row["user_id"])
            total_pairs = int(row["total_pairs"])
            strong_pairs = int(row["strong_pairs"])
            total_weight = float(row["total_weight"])
            signal_meta_by_uid[uid] = {
                "totalPairs": total_pairs,
                "strongPairs": strong_pairs,
                "totalWeight": total_weight,
                "eligibleForClip": True,
                "confidence": compute_clip_signal_confidence(total_pairs, strong_pairs, total_weight),
            }

        pos_by_user = {str(uid): g.copy() for uid, g in pair_df_all.groupby("user_id", sort=False)}
        if neg_df_all is not None and not neg_df_all.empty:
            neg_by_user = {str(uid): g.copy() for uid, g in neg_df_all.groupby("user_id", sort=False)}

        all_signal_targets: List[str] = []
        all_signal_targets.extend(pair_df_all["item_id"].astype(str).tolist())
        if neg_df_all is not None and not neg_df_all.empty:
            all_signal_targets.extend(neg_df_all["item_id"].astype(str).tolist())
        bucket = os.environ.get("FIREBASE_STORAGE_BUCKET", "seolleyeon.firebasestorage.app")
        add_ai_profiles_to_uid_urls(uid_to_urls, all_signal_targets, bucket=bucket)
    else:
        print("[events] no usable events; CLIP will run in pure cold-start/self-profile mode")

    try:
        embedder = SeolleyeonCLIPEmbedder(device=args.device)
    except Exception as e:
        if args.skip_clip_if_no_torch:
            print(f"[!] CLIP init failed ({e}). Skipping.")
            return 0
        raise

    print("[2] Computing profile embeddings...")
    uid_to_vec: Dict[str, List[float]] = {}
    for uid, urls in tqdm(uid_to_urls.items(), desc="embed"):
        try:
            vec, _ = embedder.embed_profile_mean(urls[:3], normalize=True)
            uid_to_vec[uid] = vec
        except Exception as ex:
            print(f"    Skip {uid}: {ex}")

    if len(uid_to_vec) < 2:
        print("[!] Not enough embeddings. Skipping.")
        return 0

    gender_by_uid = load_user_genders_from_firestore(
        args.firestore_project,
        users_collection=args.users_collection,
        database=args.firestore_database,
    )
    print(f"[gender] loaded from users/onboarding: {len(gender_by_uid)} users")

    meta = None
    if args.apply_policy_filters:
        meta = load_profile_index_from_firestore(
            args.firestore_project,
            collection=args.profile_index_collection,
            database=args.firestore_database,
        )
        print(f"[meta] loaded profileIndex docs: {len(meta):,}")

    uids = list(uid_to_vec.keys())
    emb_matrix = np.array([uid_to_vec[u] for u in uids], dtype=np.float32)
    uid_to_idx = {u: i for i, u in enumerate(uids)}
    reciprocal = not args.no_reciprocal
    topn = int(args.topn)
    oversample = max(1, int(args.oversample))

    print("[3] Generating recommendations...")
    recs_to_export: Dict[str, List[Dict[str, Any]]] = {}

    for user_id in tqdm(list(uid_to_vec.keys()), desc="recs"):
        if is_ai_profile(user_id):
            continue
        if user_id not in uid_to_idx:
            continue

        user_idx = uid_to_idx[user_id]
        self_vec = emb_matrix[user_idx]
        user_signal = signal_meta_by_uid.get(
            user_id,
            {
                "totalPairs": 0,
                "strongPairs": 0,
                "totalWeight": 0.0,
                "eligibleForClip": True,
                "confidence": 0.0,
            },
        )

        pos_targets: List[Tuple[str, float]] = []
        neg_targets: List[Tuple[str, float]] = []
        pos_group = pos_by_user.get(user_id)
        if pos_group is not None:
            for _, row in pos_group.iterrows():
                pos_targets.append((str(row["item_id"]), float(row["weight"])))
        neg_group = neg_by_user.get(user_id)
        if neg_group is not None:
            for _, row in neg_group.iterrows():
                ev = str(row.get("final_negative_event") or "nope")
                neg_targets.append((str(row["item_id"]), float(negative_pref_weights.get(ev, 1.0))))

        pos_mean, n_pos_used = weighted_mean_from_targets(pos_targets, uid_to_vec, exclude_uid=user_id)
        neg_mean, n_neg_used = weighted_mean_from_targets(neg_targets, uid_to_vec, exclude_uid=user_id)

        signal_pref: Optional[np.ndarray] = None
        if pos_mean is not None and neg_mean is not None:
            signal_pref = l2_normalize_np(pos_mean - float(args.negative_pref_scale) * neg_mean)
        elif pos_mean is not None:
            signal_pref = pos_mean
        elif neg_mean is not None:
            signal_pref = l2_normalize_np(self_vec - float(args.negative_pref_scale) * neg_mean)

        cold_start_fallback = signal_pref is None
        clip_conf = float(user_signal.get("confidence", 0.0))
        clip_conf = clamp01(clip_conf)

        if signal_pref is None:
            pref = self_vec
        elif args.no_blend_self_profile:
            pref = signal_pref
        else:
            pref = l2_normalize_np((clip_conf * signal_pref) + ((1.0 - clip_conf) * self_vec))

        scores = emb_matrix @ pref

        exclude = {user_idx}
        for target_uid, _w in pos_targets + neg_targets:
            if target_uid in uid_to_idx:
                exclude.add(uid_to_idx[target_uid])
        for idx, candidate_uid in enumerate(uids):
            if is_ai_profile(candidate_uid):
                exclude.add(idx)
        if exclude:
            scores[list(exclude)] = -np.inf

        top_indices = np.argsort(-scores)[: topn * oversample]
        items_out: List[Dict[str, Any]] = []
        for ii in top_indices.tolist():
            if not np.isfinite(scores[ii]):
                continue
            cand_uid = uids[ii]
            if is_ai_profile(cand_uid):
                continue

            u_g = gender_by_uid.get(user_id)
            v_g = gender_by_uid.get(cand_uid)
            if u_g and v_g and u_g == v_g:
                continue

            if meta is not None:
                if not passes_policy(
                    user_id,
                    cand_uid,
                    meta,
                    manner_min=float(args.manner_min),
                    active_within_days=int(args.active_within_days),
                    require_same_university=bool(args.require_same_university),
                    reciprocal=reciprocal,
                ):
                    continue

            items_out.append({
                "uid": cand_uid,
                "rank": len(items_out) + 1,
                "score": float(scores[ii]),
            })
            if len(items_out) >= topn:
                break

        if user_id not in signal_meta_by_uid:
            signal_meta_by_uid[user_id] = {
                "totalPairs": 0,
                "strongPairs": 0,
                "totalWeight": 0.0,
                "eligibleForClip": True,
                "confidence": 0.0,
            }
        signal_meta_by_uid[user_id]["coldStartFallback"] = bool(cold_start_fallback)
        signal_meta_by_uid[user_id]["positiveTargetsUsed"] = int(n_pos_used)
        signal_meta_by_uid[user_id]["negativeTargetsUsed"] = int(n_neg_used)

        if items_out:
            recs_to_export[user_id] = items_out

    print(f"[export] prepared recs for {len(recs_to_export)} users")

    if args.export_firestore and recs_to_export:
        db = firestore.Client(project=args.firestore_project, database=args.firestore_database)
        trained_at = datetime.now(tz=timezone.utc).isoformat()
        algo_version = args.algorithm_version or f"clip_v3_{date_key}"
        model_meta = {
            "type": "clip",
            "trainedAt": trained_at,
            "eventWeights": event_weights,
            "negativeEvents": sorted(list(negative_events)),
            "strongPositiveEvents": sorted(list(strong_positive_events)),
            "negativePrefWeights": negative_pref_weights,
            "negativePrefScale": float(args.negative_pref_scale),
            "blendSelfProfile": not bool(args.no_blend_self_profile),
            "halfLifeDays": float(args.half_life_days),
            "excludeAiProfilesFromPreference": bool(args.exclude_ai_profiles_from_preference),
        }
        export_to_firestore(
            args.firestore_project,
            date_key,
            recs_to_export,
            algorithm_version=algo_version,
            model_meta=model_meta,
            user_signal_meta=signal_meta_by_uid,
            database=args.firestore_database,
        )
        print("[export] CLIP done")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
