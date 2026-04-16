#!/usr/bin/env python3
"""
Seolleyeon Item-KNN / Memory-based CF Recommender v3

주요 보완점
- pair-level label 정제 공통화
- AI 더미 프로필 기본 학습 제외
- warm-user export gating + training prune 분리
- training 단계에서 min item support / min pair weight / iterative pruning 적용
- source confidence 명시 저장
- policy filter / reciprocal / same-university 필터 지원
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse
from tqdm import tqdm
from seolleyeon_knn_backend import build_weighted_user_item, should_use_implicit_backend

from seolleyeon_rec_common_v3 import (
    DEFAULT_EVENT_WEIGHTS,
    DEFAULT_FIRESTORE_LAYOUT,
    DEFAULT_NEGATIVE_EVENTS,
    DEFAULT_STRONG_POSITIVE_EVENTS,
    PairBuildConfig,
    build_interaction_matrix_from_pairs,
    collapse_pair_events,
    compute_source_confidence,
    compute_user_signal_stats,
    is_ai_profile,
    load_events_from_csv,
    load_events_from_firestore,
    load_profile_index_from_firestore,
    load_user_genders_from_firestore,
    passes_policy,
    prune_training_pairs,
    require_firestore,
)

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover
    firestore = None


DEFAULT_KNN_TYPE = "bm25"  # bm25 | cosine | tfidf


def safe_json_update(base: Dict[str, Any], raw: Optional[str]) -> Dict[str, Any]:
    out = dict(base)
    if raw:
        out.update(json.loads(raw))
    return out


@dataclasses.dataclass
class KNNConfig:
    knn_type: str = DEFAULT_KNN_TYPE
    K: int = 120
    num_threads: int = 0
    bm25_k1: float = 1.2
    bm25_b: float = 0.75


class ScipyCosineKNN:
    def __init__(self, sim: np.ndarray):
        self.similarity = sim

    def recommend(
        self,
        userid: int,
        user_items: sparse.csr_matrix,
        N: int = 10,
        filter_already_liked_items: bool = True,
        filter_items: Optional[Sequence[int]] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        row = user_items[userid]
        row = np.asarray(row.toarray()).flatten()
        scores = (row @ self.similarity).astype(np.float32)

        eligible = np.ones(scores.shape[0], dtype=bool)
        if filter_already_liked_items:
            liked = np.where(row != 0)[0]
            eligible[liked] = False
        if filter_items is not None and len(filter_items) > 0:
            eligible[np.array(list(filter_items), dtype=np.int64)] = False

        valid_idx = np.flatnonzero(eligible)
        if valid_idx.size == 0:
            return np.array([], dtype=np.int64), np.array([], dtype=np.float32)

        sub = scores[valid_idx]
        k = min(int(N), int(valid_idx.size))
        if k >= sub.size:
            order = np.argsort(-sub)
        else:
            part = np.argpartition(sub, -k)[-k:]
            order = part[np.argsort(-sub[part])]
        sel = valid_idx[order[:k]]
        return sel.astype(np.int64, copy=False), scores[sel]


def _train_cosine_knn_scipy(user_item: sparse.csr_matrix):
    item_user = user_item.T.tocsr()
    n_items = item_user.shape[0]

    row_sumsq = np.zeros(n_items, dtype=np.float64)
    for i in range(n_items):
        s = item_user.indptr[i]
        e = item_user.indptr[i + 1]
        if e > s:
            row_sumsq[i] = np.sum(item_user.data[s:e] ** 2)

    norms = np.sqrt(row_sumsq)
    norms = np.where(norms > 0, norms, 1.0)
    nnz_per_row = np.diff(item_user.indptr)
    norm_expanded = np.repeat(norms, nnz_per_row)

    data_norm = np.divide(
        item_user.data,
        norm_expanded,
        out=np.zeros_like(item_user.data, dtype=np.float64),
        where=norm_expanded > 0,
    )
    item_user_norm = sparse.csr_matrix(
        (data_norm, item_user.indices.copy(), item_user.indptr.copy()),
        shape=item_user.shape,
    )

    sim = (item_user_norm @ item_user_norm.T).toarray().astype(np.float32)
    np.fill_diagonal(sim, -1e9)
    sim = np.nan_to_num(sim, nan=0.0, posinf=0.0, neginf=0.0)
    return ScipyCosineKNN(sim)


def train_item_knn(user_item: sparse.csr_matrix, cfg: KNNConfig):
    if not should_use_implicit_backend():
        weighted_user_item = build_weighted_user_item(
            user_item,
            knn_type=cfg.knn_type,
            bm25_k1=cfg.bm25_k1,
            bm25_b=cfg.bm25_b,
        )
        print(f"[train] using scipy backend for knn_type={cfg.knn_type}")
        return _train_cosine_knn_scipy(weighted_user_item)

    try:
        from implicit.nearest_neighbours import BM25Recommender, CosineRecommender, TFIDFRecommender

        if cfg.knn_type == "cosine":
            model = CosineRecommender(K=cfg.K, num_threads=cfg.num_threads)
        elif cfg.knn_type == "tfidf":
            model = TFIDFRecommender(K=cfg.K, num_threads=cfg.num_threads)
        elif cfg.knn_type == "bm25":
            model = BM25Recommender(K=cfg.K, K1=cfg.bm25_k1, B=cfg.bm25_b, num_threads=cfg.num_threads)
        else:
            raise ValueError("knn_type must be one of: bm25, cosine, tfidf")

        item_user = user_item.T.tocsr()
        item_user = sparse.csr_matrix(
            (
                np.ascontiguousarray(item_user.data, dtype=np.float32),
                np.ascontiguousarray(item_user.indices, dtype=np.int32),
                np.ascontiguousarray(item_user.indptr, dtype=np.int32),
            ),
            shape=item_user.shape,
        )
        model.fit(item_user)
        return model
    except Exception as e:
        msg = str(e)
        if (
            isinstance(e, ModuleNotFoundError)
            or "No module named 'implicit'" in msg
            or "Buffer dtype mismatch" in msg
            or "expected 'long'" in msg
            or "int32" in msg
        ):
            weighted_user_item = build_weighted_user_item(
                user_item,
                knn_type=cfg.knn_type,
                bm25_k1=cfg.bm25_k1,
                bm25_b=cfg.bm25_b,
            )
            print(f"[warn] implicit KNN unavailable/failed ({e}); falling back to scipy backend")
            return _train_cosine_knn_scipy(weighted_user_item)
        raise


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
        doc_ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/knn")
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


def main() -> None:
    p = argparse.ArgumentParser(description="Seolleyeon Item-KNN training + Firestore export v3")

    p.add_argument("--events_csv", type=str, default=None)
    p.add_argument("--firestore_events", action="store_true")
    p.add_argument("--firestore_project", type=str, default=None)
    p.add_argument("--firestore_database", type=str, default=None)
    p.add_argument("--events_collection", type=str, default="recEvents")
    p.add_argument(
        "--events_layout",
        type=str,
        default=DEFAULT_FIRESTORE_LAYOUT,
        choices=["auto", "top_level", "user_subcollections"],
    )

    p.add_argument("--date_key", type=str, required=True, help="YYYYMMDD (KST)")
    p.add_argument("--lookback_days", type=int, default=120)

    p.add_argument("--event_weights_json", type=str, default=None)
    p.add_argument("--negative_events_json", type=str, default=None)
    p.add_argument("--strong_positive_events_json", type=str, default=None)
    p.add_argument("--half_life_days", type=float, default=30.0)
    p.add_argument("--max_weight_per_pair", type=float, default=12.0)
    p.add_argument("--allow_open_only_pairs", action="store_true")
    p.add_argument(
        "--include_ai_profiles_in_training",
        action="store_true",
        help="기본은 False. AI 취향 카드를 collaborative 학습에 포함하려면 명시적으로 켜라",
    )

    p.add_argument("--knn_type", type=str, default=DEFAULT_KNN_TYPE, choices=["bm25", "cosine", "tfidf"])
    p.add_argument("--K", type=int, default=120)
    p.add_argument("--num_threads", type=int, default=0)
    p.add_argument("--bm25_k1", type=float, default=1.2)
    p.add_argument("--bm25_b", type=float, default=0.75)

    p.add_argument("--min_total_pairs", type=int, default=5)
    p.add_argument("--min_strong_pairs", type=int, default=3)
    p.add_argument("--min_total_weight", type=float, default=12.0)

    p.add_argument("--min_train_total_pairs", type=int, default=3)
    p.add_argument("--min_train_strong_pairs", type=int, default=2)
    p.add_argument("--min_train_total_weight", type=float, default=8.0)
    p.add_argument("--min_item_support", type=int, default=2)
    p.add_argument("--min_item_strong_users", type=int, default=1)
    p.add_argument("--min_pair_weight", type=float, default=0.5)
    p.add_argument("--no_iterative_pruning", action="store_true")

    p.add_argument("--topn", type=int, default=300)
    p.add_argument("--oversample", type=int, default=6)

    p.add_argument("--apply_policy_filters", action="store_true")
    p.add_argument("--profile_index_collection", type=str, default="profileIndex")
    p.add_argument("--manner_min", type=float, default=33.0)
    p.add_argument("--active_within_days", type=int, default=14)
    p.add_argument("--require_same_university", dest="require_same_university", action="store_true")
    p.add_argument("--no_require_same_university", dest="require_same_university", action="store_false")
    p.set_defaults(require_same_university=True)
    p.add_argument("--no_reciprocal", action="store_true")

    p.add_argument("--export_firestore", dest="export_firestore", action="store_true")
    p.add_argument("--no_export_firestore", dest="export_firestore", action="store_false")
    p.set_defaults(export_firestore=True)
    p.add_argument("--algorithm_version", type=str, default=None)

    args = p.parse_args()

    event_weights = safe_json_update(DEFAULT_EVENT_WEIGHTS, args.event_weights_json)
    negative_events = set(json.loads(args.negative_events_json)) if args.negative_events_json else set(DEFAULT_NEGATIVE_EVENTS)
    strong_positive_events = (
        set(json.loads(args.strong_positive_events_json))
        if args.strong_positive_events_json
        else set(DEFAULT_STRONG_POSITIVE_EVENTS)
    )

    if args.events_csv:
        df = load_events_from_csv(args.events_csv)
    elif args.firestore_events:
        if not args.firestore_project:
            raise ValueError("--firestore_project is required for --firestore_events")
        kst = timezone(timedelta(hours=9))
        yyyy, mm, dd = int(args.date_key[:4]), int(args.date_key[4:6]), int(args.date_key[6:8])
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
    else:
        raise ValueError("Provide --events_csv or --firestore_events")

    if df.empty:
        raise ValueError("No events loaded.")
    print(f"[raw] loaded events: {len(df):,}")

    pair_cfg = PairBuildConfig(
        event_weights=event_weights,
        negative_events=negative_events,
        strong_positive_events=strong_positive_events,
        half_life_days=float(args.half_life_days),
        max_weight_per_pair=float(args.max_weight_per_pair),
        allow_open_only_pairs=bool(args.allow_open_only_pairs),
        exclude_ai_items_from_training=not bool(args.include_ai_profiles_in_training),
    )
    pair_df_all, neg_df_all = collapse_pair_events(df, pair_cfg)
    print(f"[pairs] surviving positive pairs: {len(pair_df_all):,}")
    print(f"[pairs] final negative pairs: {0 if neg_df_all.empty else len(neg_df_all):,}")

    signal_df = compute_user_signal_stats(pair_df_all)
    export_eligible_user_ids = set(
        signal_df.loc[
            (signal_df["total_pairs"] >= int(args.min_total_pairs))
            & (signal_df["strong_pairs"] >= int(args.min_strong_pairs))
            & (signal_df["total_weight"] >= float(args.min_total_weight)),
            "user_id",
        ].astype(str)
    )

    signal_meta_by_uid: Dict[str, Dict[str, Any]] = {}
    for _, row in signal_df.iterrows():
        uid = str(row["user_id"])
        total_pairs = int(row["total_pairs"])
        strong_pairs = int(row["strong_pairs"])
        total_weight = float(row["total_weight"])
        eligible = uid in export_eligible_user_ids
        signal_meta_by_uid[uid] = {
            "totalPairs": total_pairs,
            "strongPairs": strong_pairs,
            "totalWeight": total_weight,
            "eligibleForKnn": eligible,
            "confidence": compute_source_confidence(total_pairs, strong_pairs, total_weight) if eligible else 0.0,
        }

    train_pair_df = prune_training_pairs(
        pair_df_all,
        min_train_total_pairs=int(args.min_train_total_pairs),
        min_train_strong_pairs=int(args.min_train_strong_pairs),
        min_train_total_weight=float(args.min_train_total_weight),
        min_item_support=int(args.min_item_support),
        min_item_strong_users=int(args.min_item_strong_users),
        min_pair_weight=float(args.min_pair_weight),
        iterative=not bool(args.no_iterative_pruning),
    )
    if train_pair_df.empty:
        print("[train] no pairs survived training prune. Nothing to export.")
        return

    train_user_ids = set(train_pair_df["user_id"].astype(str).unique().tolist())
    train_item_ids = set(train_pair_df["item_id"].astype(str).unique().tolist())
    neg_df_train = neg_df_all[
        neg_df_all["user_id"].astype(str).isin(train_user_ids)
        & neg_df_all["item_id"].astype(str).isin(train_item_ids)
    ].copy() if not neg_df_all.empty else neg_df_all

    print(f"[train] pairs after prune: {len(train_pair_df):,}")
    print(f"[train] users after prune: {len(train_user_ids):,}, items after prune: {len(train_item_ids):,}")

    user_item, user2idx, idx2item, negative_by_useridx, train_pair_df = build_interaction_matrix_from_pairs(
        train_pair_df,
        neg_df_train,
    )
    n_users, n_items = user_item.shape
    print(f"[matrix] users={n_users:,}, items={n_items:,}, nnz={user_item.nnz:,}")

    export_user_ids = [u for u in sorted(export_eligible_user_ids) if u in user2idx]
    active_user_indices = [user2idx[u] for u in export_user_ids]
    print(f"[export] eligible users in trained matrix: {len(active_user_indices):,} / {len(export_eligible_user_ids):,}")
    if not active_user_indices:
        print("[export] no eligible users survived training prune. Nothing to export.")
        return

    cfg = KNNConfig(
        knn_type=args.knn_type,
        K=int(args.K),
        num_threads=int(args.num_threads),
        bm25_k1=float(args.bm25_k1),
        bm25_b=float(args.bm25_b),
    )
    model = train_item_knn(user_item, cfg)
    trained_at = datetime.now(tz=timezone.utc).isoformat()

    meta = None
    if args.apply_policy_filters:
        if not args.firestore_project:
            raise ValueError("--firestore_project is required for --apply_policy_filters")
        meta = load_profile_index_from_firestore(
            args.firestore_project,
            collection=args.profile_index_collection,
            database=args.firestore_database,
        )
        print(f"[meta] loaded profileIndex docs: {len(meta):,}")

    gender_by_uid: Dict[str, str] = {}
    if args.firestore_project:
        gender_by_uid = load_user_genders_from_firestore(
            args.firestore_project,
            users_collection="users",
            database=args.firestore_database,
        )
        print(f"[gender] loaded users/onboarding genders: {len(gender_by_uid):,}")

    idx2user = [None] * len(user2idx)
    for uid, i in user2idx.items():
        idx2user[i] = uid

    item2idx = {it: j for j, it in enumerate(idx2item)}
    reciprocal = not args.no_reciprocal
    topn = int(args.topn)
    oversample = max(1, int(args.oversample))

    recs_to_export: Dict[str, List[Dict[str, Any]]] = {}
    for ui in tqdm(active_user_indices, desc="generating"):
        uid = idx2user[ui]
        if uid is None:
            continue

        filter_items = set(negative_by_useridx.get(ui, set()))
        filter_items.update(i for i, item in enumerate(idx2item) if is_ai_profile(item))
        self_item_idx = item2idx.get(uid)
        if self_item_idx is not None:
            filter_items.add(self_item_idx)

        # implicit item-item recommenders expect a single-row CSR matrix for
        # scalar user queries, not the full user-item matrix.
        user_row = user_item[ui]
        item_idx, scores = model.recommend(
            0,
            user_row,
            N=topn * oversample,
            filter_already_liked_items=True,
            filter_items=list(filter_items) if filter_items else None,
        )
        if not isinstance(item_idx, np.ndarray):
            item_idx = np.array(item_idx, dtype=np.int64)
        if not isinstance(scores, np.ndarray):
            scores = np.array(scores, dtype=np.float32)

        items_out: List[Dict[str, Any]] = []
        rank = 1
        for ii, score in zip(item_idx.tolist(), scores.tolist()):
            cand_uid = idx2item[int(ii)]
            if is_ai_profile(cand_uid):
                continue

            u_gender = gender_by_uid.get(uid)
            v_gender = gender_by_uid.get(cand_uid)
            if u_gender and v_gender and u_gender == v_gender:
                continue

            if meta is not None:
                if not passes_policy(
                    uid,
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
                "rank": rank,
                "score": float(score),
            })
            rank += 1
            if rank > topn:
                break

        if items_out:
            meta_row = signal_meta_by_uid.get(uid)
            if meta_row is not None:
                meta_row["trainedForKnn"] = True
            recs_to_export[uid] = items_out

    print(f"[export] prepared recs for users: {len(recs_to_export):,}")

    algorithm_version = args.algorithm_version or (
        f"knn_v3_{cfg.knn_type}_K{cfg.K}_{args.date_key}"
    )

    if args.export_firestore:
        if not args.firestore_project:
            raise ValueError("--firestore_project is required for export")

        model_meta = {
            "type": "item_knn",
            "knnType": cfg.knn_type,
            "K": cfg.K,
            "bm25K1": cfg.bm25_k1 if cfg.knn_type == "bm25" else None,
            "bm25B": cfg.bm25_b if cfg.knn_type == "bm25" else None,
            "trainedAt": trained_at,
            "eventWeights": event_weights,
            "negativeEvents": sorted(list(negative_events)),
            "strongPositiveEvents": sorted(list(strong_positive_events)),
            "halfLifeDays": float(args.half_life_days),
            "allowOpenOnlyPairs": bool(args.allow_open_only_pairs),
            "excludeAiProfilesFromTraining": not bool(args.include_ai_profiles_in_training),
            "trainingPrune": {
                "minTrainTotalPairs": int(args.min_train_total_pairs),
                "minTrainStrongPairs": int(args.min_train_strong_pairs),
                "minTrainTotalWeight": float(args.min_train_total_weight),
                "minItemSupport": int(args.min_item_support),
                "minItemStrongUsers": int(args.min_item_strong_users),
                "minPairWeight": float(args.min_pair_weight),
                "iterative": not bool(args.no_iterative_pruning),
            },
            "gating": {
                "minTotalPairs": int(args.min_total_pairs),
                "minStrongPairs": int(args.min_strong_pairs),
                "minTotalWeight": float(args.min_total_weight),
            },
            "matrix": {
                "users": int(n_users),
                "items": int(n_items),
                "nnz": int(user_item.nnz),
            },
        }

        export_to_firestore(
            args.firestore_project,
            args.date_key,
            recs_to_export,
            algorithm_version=algorithm_version,
            model_meta=model_meta,
            user_signal_meta=signal_meta_by_uid,
            database=args.firestore_database,
        )
        print("[export] done")

    sample_users = list(recs_to_export.keys())[:3]
    for su in sample_users:
        print(f"\n[sample] {su}")
        print(json.dumps(recs_to_export[su][:5], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
