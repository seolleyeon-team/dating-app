#!/usr/bin/env python3
"""
Seolleyeon KNN / Memory-based CF (Item-KNN) - Train & Export

목표:
- 설레연의 implicit feedback(열람/좋아요/매칭/채팅)을 user-item 상호작용 행렬로 만들고
- implicit 라이브러리의 item-item KNN(Cosine/TFIDF/BM25)로 TopN 후보를 생성한 뒤
- Firestore modelRecs/{uid}/daily/{dateKey}/sources/knn 에 저장.

왜 이게 "memory-based CF"인가?
- 잠재요인(embedding)을 학습하는 MF(SVD/ALS)와 달리,
  상호작용 행렬에서 아이템-아이템 유사도를 직접 계산해서 추천하기 때문(=메모리 기반).

입력:
1) --events_csv: CSV columns: user_id,item_id,event,ts(optional)
2) --firestore_events: Firestore recEvents 컬렉션에서 기간 조회

Firestore 저장:
- modelRecs/{uid}/daily/{dateKey}/sources/knn

권장 운영:
- 하루 1회 Cloud Run Job/VM/내부 서버에서 실행
- 온라인 최종 추천은 RRF로 CLIP/SVD/KNN/Content를 통합
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import sparse
from tqdm import tqdm

from google.cloud import firestore


# -------------------------
# Defaults
# -------------------------

DEFAULT_EVENT_WEIGHTS = {
    # KNN에서는 open이 너무 크면 노이즈가 커질 수 있어 낮게 두는 걸 추천
    "open": 0.3,
    "like": 3.0,
    "match_created": 6.0,
    "chat_first_message": 5.0,
}

DEFAULT_NEGATIVE_EVENTS = {"nope"}  # 학습에는 안 넣고 제외용으로만 사용


# -------------------------
# Time helpers
# -------------------------

def parse_datekey_to_utc_range(date_key: str) -> Tuple[datetime, datetime]:
    """
    date_key: 'YYYYMMDD' (KST 기준)
    반환: 해당 KST 날짜의 [start,end) 를 UTC datetime으로 변환
    """
    if len(date_key) != 8:
        raise ValueError("dateKey must be YYYYMMDD")
    yyyy = int(date_key[0:4])
    mm = int(date_key[4:6])
    dd = int(date_key[6:8])

    kst = timezone(timedelta(hours=9))
    start_kst = datetime(yyyy, mm, dd, 0, 0, 0, tzinfo=kst)
    end_kst = start_kst + timedelta(days=1)

    return start_kst.astimezone(timezone.utc), end_kst.astimezone(timezone.utc)


def half_life_decay(age_days: float, half_life_days: float) -> float:
    if half_life_days <= 0:
        return 1.0
    return 0.5 ** (age_days / half_life_days)


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


# -------------------------
# Data loading
# -------------------------

def load_events_from_csv(path: str) -> pd.DataFrame:
    """
    CSV columns:
      user_id, item_id, event, ts(optional)
    ts: ISO8601 or unix seconds or empty
    """
    df = pd.read_csv(path)
    required = {"user_id", "item_id", "event"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")

    if "ts" not in df.columns:
        df["ts"] = pd.NaT

    def parse_ts(v):
        if pd.isna(v):
            return pd.NaT
        if isinstance(v, (int, float)) and not math.isnan(float(v)):
            return pd.to_datetime(int(v), unit="s", utc=True)
        try:
            return pd.to_datetime(v, utc=True)
        except Exception:
            return pd.NaT

    df["ts"] = df["ts"].apply(parse_ts)
    return df[["user_id", "item_id", "event", "ts"]]


def load_events_from_firestore(
    project_id: str,
    *,
    collection: str = "recEvents",
    start_time_utc: Optional[datetime] = None,
    end_time_utc: Optional[datetime] = None,
    database: Optional[str] = None,
) -> pd.DataFrame:
    """
    Firestore recEvents/{userId}/events 서브컬렉션에서 이벤트 로딩
    문서 필드: userId, targetUserId, eventType, source, createdAt
    """
    db = firestore.Client(project=project_id, database=database)

    rows = []

    # recEvents/{userId} 문서 목록 조회
    user_docs = db.collection(collection).list_documents()
    for user_doc_ref in user_docs:
        # 각 유저의 events 서브컬렉션 조회
        q = user_doc_ref.collection("events")
        if start_time_utc is not None:
            q = q.where("createdAt", ">=", start_time_utc)
        if end_time_utc is not None:
            q = q.where("createdAt", "<", end_time_utc)

        for doc in q.stream():
            d = doc.to_dict() or {}
            user_id = d.get("userId")
            item_id = d.get("targetUserId") or d.get("targetId") or d.get("candidateUserId")
            event = d.get("eventType") or d.get("type")
            ts = d.get("createdAt")

            if user_id is None or item_id is None or event is None:
                continue

            if isinstance(ts, datetime):
                ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
                ts = ts.astimezone(timezone.utc)
            else:
                ts = pd.NaT

            rows.append((str(user_id), str(item_id), str(event), ts))

    return pd.DataFrame(rows, columns=["user_id", "item_id", "event", "ts"])


# -------------------------
# Build interaction matrix
# -------------------------

def build_interaction_matrix(
    df: pd.DataFrame,
    *,
    event_weights: Dict[str, float],
    negative_events: set,
    time_decay_half_life_days: float,
    max_weight_per_pair: float,
) -> Tuple[sparse.csr_matrix, Dict[str, int], List[str], Dict[int, set]]:
    """
    Returns:
      user_item_csr: (n_users, n_items)
      user2idx: {user_id -> row index}
      idx2item: list mapping col index -> item_id
      neg_by_useridx: {user_idx -> set(item_idx)}  (nope 등 제외용)
    """
    df = df.copy()
    df["user_id"] = df["user_id"].astype(str)
    df["item_id"] = df["item_id"].astype(str)
    df["event"] = df["event"].astype(str)

    known = set(event_weights.keys()) | set(negative_events)
    df = df[df["event"].isin(known)]
    if df.empty:
        raise ValueError("No known events after filtering.")

    df["base_w"] = df["event"].map(lambda e: float(event_weights.get(e, 0.0))).astype(float)

    # time decay
    if time_decay_half_life_days > 0:
        now = datetime.now(tz=timezone.utc)
        ages = []
        for ts in df["ts"].tolist():
            if isinstance(ts, pd.Timestamp):
                ts = ts.to_pydatetime()
            if isinstance(ts, datetime):
                ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
                age_days = max(0.0, (now - ts.astimezone(timezone.utc)).total_seconds() / (24 * 3600))
                ages.append(age_days)
            else:
                ages.append(0.0)
        df["decay"] = [half_life_decay(a, time_decay_half_life_days) for a in ages]
    else:
        df["decay"] = 1.0

    df["w"] = df["base_w"] * df["decay"]

    users = pd.Index(df["user_id"].unique())
    items = pd.Index(df["item_id"].unique())
    user2idx = {u: i for i, u in enumerate(users.tolist())}
    item2idx = {it: j for j, it in enumerate(items.tolist())}
    idx2item = items.tolist()

    # negatives (nope) -> exclusion set
    neg_by_useridx: Dict[int, set] = {}
    neg_df = df[df["event"].isin(negative_events)]
    for _, row in neg_df.iterrows():
        ui = user2idx[row["user_id"]]
        ii = item2idx[row["item_id"]]
        neg_by_useridx.setdefault(ui, set()).add(ii)

    # positives only for matrix
    pos_df = df[df["base_w"] > 0].copy()
    if pos_df.empty:
        raise ValueError("No positive interactions found (open/like/match/chat).")

    # aggregate weight per (user,item)
    grp = pos_df.groupby(["user_id", "item_id"], as_index=False)["w"].sum()
    grp["w"] = grp["w"].clip(upper=max_weight_per_pair)

    rows = grp["user_id"].map(user2idx).to_numpy()
    cols = grp["item_id"].map(item2idx).to_numpy()
    data = grp["w"].to_numpy(dtype=np.float32)

    coo = sparse.coo_matrix((data, (rows, cols)), shape=(len(users), len(items)), dtype=np.float32)
    coo.sum_duplicates()
    mat = coo.tocsr()
    return mat, user2idx, idx2item, neg_by_useridx


# -------------------------
# Optional policy filtering via profileIndex
# -------------------------

def load_profile_index_from_firestore(
    project_id: str,
    *,
    collection: str = "profileIndex",
    database: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    db = firestore.Client(project=project_id, database=database)
    meta: Dict[str, Dict[str, Any]] = {}
    for doc in db.collection(collection).stream():
        uid = doc.id
        d = doc.to_dict() or {}
        meta[uid] = {
            "universityId": d.get("universityId"),
            "isVerified": bool(d.get("isVerified", False)),
            "isActive": bool(d.get("isActive", True)),
            "isProfileComplete": bool(d.get("isProfileComplete", True)),
            "gender": d.get("gender"),
            "birthYear": d.get("birthYear"),
            "prefGender": d.get("prefGender", []) or [],
            "prefAgeMin": d.get("prefAgeMin"),
            "prefAgeMax": d.get("prefAgeMax"),
            "mannerScore": safe_float(d.get("mannerScore", 36.5), 36.5),
            "lastActiveAt": d.get("lastActiveAt"),
        }
    return meta


def now_year_kst() -> int:
    kst = timezone(timedelta(hours=9))
    return datetime.now(tz=kst).year


def kst_age(birth_year: int, now_year: int) -> int:
    return now_year - birth_year + 1


def passes_policy(
    u: str,
    v: str,
    meta: Dict[str, Dict[str, Any]],
    *,
    manner_min: float,
    active_within_days: int,
    require_same_university: bool,
    reciprocal: bool,
) -> bool:
    mu = meta.get(u)
    mv = meta.get(v)
    if mu is None or mv is None:
        return False

    # candidate gating
    if not mv.get("isActive", True):
        return False
    if not mv.get("isVerified", False):
        return False
    if not mv.get("isProfileComplete", True):
        return False
    if mv.get("mannerScore", 36.5) < manner_min:
        return False

    # activity
    last_active = mv.get("lastActiveAt")
    if isinstance(last_active, datetime):
        last_active = last_active if last_active.tzinfo else last_active.replace(tzinfo=timezone.utc)
        last_active = last_active.astimezone(timezone.utc)
        days = (datetime.now(tz=timezone.utc) - last_active).total_seconds() / (24 * 3600)
        if days > active_within_days:
            return False

    # same university
    if require_same_university:
        if mu.get("universityId") is None or mv.get("universityId") is None:
            return False
        if mu["universityId"] != mv["universityId"]:
            return False

    # u's preference on v
    u_pref_gender = mu.get("prefGender", []) or []
    v_gender = mv.get("gender")
    if u_pref_gender and v_gender is not None and v_gender not in u_pref_gender:
        return False

    by_u = mu.get("birthYear")
    by_v = mv.get("birthYear")
    now_y = now_year_kst()
    if isinstance(by_v, int):
        age_v = kst_age(by_v, now_y)
        amin = mu.get("prefAgeMin")
        amax = mu.get("prefAgeMax")
        if amin is not None and age_v < int(amin):
            return False
        if amax is not None and age_v > int(amax):
            return False

    # reciprocal: v's preference on u
    if reciprocal:
        v_pref_gender = mv.get("prefGender", []) or []
        u_gender = mu.get("gender")
        if v_pref_gender and u_gender is not None and u_gender not in v_pref_gender:
            return False

        if isinstance(by_u, int):
            age_u = kst_age(by_u, now_y)
            amin2 = mv.get("prefAgeMin")
            amax2 = mv.get("prefAgeMax")
            if amin2 is not None and age_u < int(amin2):
                return False
            if amax2 is not None and age_u > int(amax2):
                return False

    return True


# -------------------------
# KNN model training (item-item)
# -------------------------

@dataclass
class KNNConfig:
    knn_type: str = "bm25"      # bm25 | cosine | tfidf
    K: int = 200
    num_threads: int = 0
    bm25_k1: float = 1.2
    bm25_b: float = 0.75


def train_item_knn(user_item: sparse.csr_matrix, cfg: KNNConfig):
    from implicit.nearest_neighbours import BM25Recommender, CosineRecommender, TFIDFRecommender

    if cfg.knn_type == "cosine":
        model = CosineRecommender(K=cfg.K, num_threads=cfg.num_threads)
    elif cfg.knn_type == "tfidf":
        model = TFIDFRecommender(K=cfg.K, num_threads=cfg.num_threads)
    elif cfg.knn_type == "bm25":
        model = BM25Recommender(K=cfg.K, K1=cfg.bm25_k1, B=cfg.bm25_b, num_threads=cfg.num_threads)
    else:
        raise ValueError("knn_type must be one of: bm25, cosine, tfidf")

    # implicit의 KNN 모델은 item-user 전치 행렬을 기대
    item_user = user_item.T.tocsr()
    model.fit(item_user)
    return model


# -------------------------
# Export to Firestore
# -------------------------

def export_to_firestore(
    project_id: str,
    date_key: str,
    recommendations: Dict[str, List[Dict[str, Any]]],
    *,
    algorithm_version: str,
    model_meta: Dict[str, Any],
    database: Optional[str] = None,
):
    db = firestore.Client(project=project_id, database=database)
    bw = db.bulk_writer()

    gen_at = firestore.SERVER_TIMESTAMP
    for uid, items in recommendations.items():
        doc_ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/knn")
        payload = {
            "status": "ready",
            "algorithmVersion": algorithm_version,
            "model": model_meta,
            "generatedAt": gen_at,
            "topN": len(items),
            "items": items,
        }
        bw.set(doc_ref, payload, merge=True)

    bw.close()


# -------------------------
# Main
# -------------------------

def main():
    p = argparse.ArgumentParser(description="Seolleyeon Item-KNN (memory-based CF) train & export")
    # input
    p.add_argument("--events_csv", type=str, default=None, help="CSV path with user_id,item_id,event,ts")
    p.add_argument("--firestore_events", action="store_true", help="Load events from Firestore recEvents")
    p.add_argument("--firestore_project", type=str, default=None, help="GCP project id (Firestore)")
    p.add_argument("--firestore_database", type=str, default=None, help="Firestore database id (usually omit)")
    p.add_argument("--events_collection", type=str, default="recEvents", help="Firestore collection name for events")

    # time range
    p.add_argument("--date_key", type=str, required=True, help="YYYYMMDD (KST)")
    p.add_argument("--lookback_days", type=int, default=120, help="Training data lookback (days)")

    # weights
    p.add_argument("--event_weights_json", type=str, default=None,
                   help='JSON mapping like {"open":0.3,"like":3.0,"match_created":6.0,"chat_first_message":5.0}')
    p.add_argument("--half_life_days", type=float, default=30.0, help="Time decay half-life (0=disable)")
    p.add_argument("--max_weight_per_pair", type=float, default=10.0, help="Cap summed weight per (user,item)")

    # knn model
    p.add_argument("--knn_type", type=str, default="bm25", choices=["bm25", "cosine", "tfidf"])
    p.add_argument("--K", type=int, default=200, help="Number of neighbours for item-item similarity")
    p.add_argument("--num_threads", type=int, default=0)

    p.add_argument("--bm25_k1", type=float, default=1.2)
    p.add_argument("--bm25_b", type=float, default=0.75)

    # recommendation
    p.add_argument("--topn", type=int, default=400)
    p.add_argument("--oversample", type=int, default=5, help="Recommend N*oversample then post-filter down to N")
    p.add_argument("--min_pos_interactions", type=int, default=2, help="Skip users with too few positive pairs")

    # optional policy filters
    p.add_argument("--apply_policy_filters", action="store_true")
    p.add_argument("--profile_index_collection", type=str, default="profileIndex")
    p.add_argument("--manner_min", type=float, default=33.0)
    p.add_argument("--active_within_days", type=int, default=14)
    p.add_argument("--require_same_university", action="store_true", default=True)
    p.add_argument("--no_reciprocal", action="store_true", help="Disable reciprocal preference filter")

    # export
    p.add_argument("--export_firestore", action="store_true", default=True)
    p.add_argument("--algorithm_version", type=str, default=None)

    args = p.parse_args()

    if args.event_weights_json:
        event_weights = json.loads(args.event_weights_json)
    else:
        event_weights = dict(DEFAULT_EVENT_WEIGHTS)

    negative_events = set(DEFAULT_NEGATIVE_EVENTS)

    # ---- Load events ----
    if args.events_csv:
        df = load_events_from_csv(args.events_csv)
    elif args.firestore_events:
        if not args.firestore_project:
            raise ValueError("--firestore_project is required for --firestore_events")

        start_day_utc, end_day_utc = parse_datekey_to_utc_range(args.date_key)
        start_time = start_day_utc - timedelta(days=int(args.lookback_days))
        end_time = end_day_utc

        df = load_events_from_firestore(
            args.firestore_project,
            collection=args.events_collection,
            start_time_utc=start_time,
            end_time_utc=end_time,
            database=args.firestore_database,
        )
    else:
        raise ValueError("Provide --events_csv or --firestore_events")

    if df.empty:
        raise ValueError("No events loaded.")

    # ---- Build matrix ----
    user_item, user2idx, idx2item, neg_by_useridx = build_interaction_matrix(
        df,
        event_weights=event_weights,
        negative_events=negative_events,
        time_decay_half_life_days=float(args.half_life_days),
        max_weight_per_pair=float(args.max_weight_per_pair),
    )

    n_users, n_items = user_item.shape
    print(f"[data] users={n_users}, items={n_items}, nnz={user_item.nnz}")

    # ---- Optional metadata for policy filters ----
    meta = None
    if args.apply_policy_filters:
        if not args.firestore_project:
            raise ValueError("--firestore_project is required for --apply_policy_filters")
        meta = load_profile_index_from_firestore(
            args.firestore_project,
            collection=args.profile_index_collection,
            database=args.firestore_database,
        )
        print(f"[meta] loaded profileIndex docs: {len(meta)}")

    # ---- Train KNN ----
    knn_cfg = KNNConfig(
        knn_type=args.knn_type,
        K=int(args.K),
        num_threads=int(args.num_threads),
        bm25_k1=float(args.bm25_k1),
        bm25_b=float(args.bm25_b),
    )
    model = train_item_knn(user_item, knn_cfg)

    trained_at = datetime.now(tz=timezone.utc).isoformat()

    # eligible users: by positive pairs count
    pos_counts = np.diff(user_item.indptr)
    eligible = np.where(pos_counts >= int(args.min_pos_interactions))[0].tolist()
    print(f"[train] eligible users (>= {args.min_pos_interactions} pos pairs): {len(eligible)}")

    idx2user = [None] * len(user2idx)
    for uid, i in user2idx.items():
        idx2user[i] = uid

    # item_id -> item_idx 사전 (O(1) 룩업용, list.index() 대체)
    item2idx_map = {it: j for j, it in enumerate(idx2item)}

    algorithm_version = args.algorithm_version or f"knn_item_{knn_cfg.knn_type}_K{knn_cfg.K}_{args.date_key}"

    # ---- Generate recs ----
    recs_to_export: Dict[str, List[Dict[str, Any]]] = {}
    topn = int(args.topn)
    oversample = max(1, int(args.oversample))
    reciprocal = not args.no_reciprocal

    for ui in tqdm(eligible, desc="generating"):
        u = idx2user[ui]
        if u is None:
            continue

        # exclude set: nope + self (if in items)
        filter_items = set(neg_by_useridx.get(ui, set()))
        self_item_idx = item2idx_map.get(u)
        if self_item_idx is not None:
            filter_items.add(self_item_idx)

        # implicit recommend: 전체 user-item 행렬을 넘김
        item_idx, scores = model.recommend(
            ui,
            user_item,
            N=topn * oversample,
            filter_already_liked_items=True,
            filter_items=list(filter_items) if filter_items else None,
        )

        items_out: List[Dict[str, Any]] = []
        rank = 1
        for ii, sc in zip(item_idx.tolist(), scores.tolist()):
            cand_uid = idx2item[ii]

            if meta is not None:
                if not passes_policy(
                    u, cand_uid, meta,
                    manner_min=float(args.manner_min),
                    active_within_days=int(args.active_within_days),
                    require_same_university=bool(args.require_same_university),
                    reciprocal=reciprocal,
                ):
                    continue

            items_out.append({"uid": cand_uid, "rank": rank, "score": float(sc)})
            rank += 1
            if rank > topn:
                break

        if items_out:
            recs_to_export[u] = items_out

    print(f"[export] prepared recs for users: {len(recs_to_export)}")

    # ---- Export ----
    if args.export_firestore:
        if not args.firestore_project:
            raise ValueError("--firestore_project is required for export")

        model_meta = {
            "type": "item_knn",
            "knnType": knn_cfg.knn_type,
            "K": knn_cfg.K,
            "bm25K1": knn_cfg.bm25_k1 if knn_cfg.knn_type == "bm25" else None,
            "bm25B": knn_cfg.bm25_b if knn_cfg.knn_type == "bm25" else None,
            "trainedAt": trained_at,
            "eventWeights": event_weights,
            "halfLifeDays": float(args.half_life_days),
            "lookbackDays": int(args.lookback_days),
        }

        export_to_firestore(
            args.firestore_project,
            args.date_key,
            recs_to_export,
            algorithm_version=algorithm_version,
            model_meta=model_meta,
            database=args.firestore_database,
        )
        print("[export] done")

    # print sample
    sample_users = list(recs_to_export.keys())[:3]
    for su in sample_users:
        print(f"\n[sample] {su}")
        print(json.dumps(recs_to_export[su][:5], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()