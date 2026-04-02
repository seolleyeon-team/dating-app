
#!/usr/bin/env python3
"""
Seolleyeon Item-KNN / Memory-based CF Recommender (improved)

핵심 변경점
- pair-level signal consolidation:
  * open/nope 같이 섞인 pair를 그대로 positive로 학습하지 않음
  * 합산(sum) 대신 "최종 유효 positive" 1개만 남김
  * negative(nope/block/report)가 나오면 이전 positive를 무효화하고,
    이후 더 강한 positive가 다시 생긴 경우에만 pair를 살림
- open 계열은 기본적으로 학습에서 제외(0.0)하여 false positive 억제
- AI 취향 카드(female_*, male_*) 스와이프는 기본적으로 학습 행렬에 반영(선호 신호).
  추천 후보만 실제 유저로 제한(--exclude_ai_profiles_from_training 로 학습에서도 제외 가능)
- Firestore createdAt 문자열/Datetime 모두 robust parse
- warm user gating:
  * strong positive pair 수 / total pair 수 / total weight 기반으로 KNN export 여부 결정
- top-level recEvents / recEvents/{uid}/events 둘 다 지원
- KNN source 문서에 signal meta를 함께 저장하여 RRF에서 confidence down-weight 가능
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import sparse
from tqdm import tqdm

try:
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
except Exception:  # pragma: no cover
    firestore = None
    FieldFilter = None


DEFAULT_EVENT_WEIGHTS: Dict[str, float] = {
    "open": 0.0,
    "detail_open": 0.0,
    "like": 4.0,
    "match_created": 7.0,
    "chat_first_message": 9.0,
}

DEFAULT_NEGATIVE_EVENTS = {"nope", "block", "report"}
DEFAULT_STRONG_POSITIVE_EVENTS = {"like", "match_created", "chat_first_message"}

DEFAULT_KNN_TYPE = "bm25"  # bm25 | cosine | tfidf
DEFAULT_FIRESTORE_LAYOUT = "auto"  # auto | top_level | user_subcollections


def require_firestore() -> None:
    if firestore is None or FieldFilter is None:
        raise RuntimeError(
            "google-cloud-firestore is not installed. "
            "Install it for Firestore load/export, or use --events_csv with --no_export_firestore."
        )


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def compute_source_confidence(total_pairs: int, strong_pairs: int, total_weight: float) -> float:
    """RRF dynamic weighting에 사용할 user-level confidence."""
    c_pairs = min(1.0, total_pairs / 10.0)
    c_strong = min(1.0, strong_pairs / 4.0)
    c_weight = min(1.0, total_weight / 20.0)
    conf = 0.20 + 0.35 * c_pairs + 0.35 * c_strong + 0.10 * c_weight
    return round(clamp01(conf), 4)


def parse_datekey_to_utc_range(date_key: str) -> Tuple[datetime, datetime]:
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


def is_ai_profile(item_id: str) -> bool:
    if not item_id or not isinstance(item_id, str):
        return False
    return item_id.startswith("female_") or item_id.startswith("male_")


def parse_firestore_like_ts(value: Any) -> pd.Timestamp:
    if value is None:
        return pd.NaT
    if isinstance(value, pd.Timestamp):
        if value.tzinfo is None:
            return value.tz_localize("UTC")
        return value.tz_convert("UTC")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return pd.Timestamp(value.replace(tzinfo=timezone.utc))
        return pd.Timestamp(value.astimezone(timezone.utc))
    if isinstance(value, (int, float)):
        try:
            v = float(value)
            if math.isnan(v):
                return pd.NaT
            if v > 1e12:
                return pd.to_datetime(int(v), unit="ms", utc=True)
            return pd.to_datetime(int(v), unit="s", utc=True)
        except Exception:
            return pd.NaT
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return pd.NaT
        try:
            return pd.to_datetime(s, utc=True)
        except Exception:
            return pd.NaT
    return pd.NaT


def _rec_events_created_at_query_bounds(
    start_time_utc: Optional[datetime],
    end_time_utc: Optional[datetime],
) -> Tuple[Optional[str], Optional[str]]:
    def to_iso(dt: datetime) -> str:
        u = dt.astimezone(timezone.utc)
        return u.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return (
        to_iso(start_time_utc) if start_time_utc is not None else None,
        to_iso(end_time_utc) if end_time_utc is not None else None,
    )


def _extract_user_item_event_ts(doc: Dict[str, Any]) -> Optional[Tuple[str, str, str, pd.Timestamp]]:
    user_id = doc.get("userId") or doc.get("fromUserId")
    item_id = (
        doc.get("targetId")
        or doc.get("candidateUserId")
        or doc.get("targetUserId")
        or doc.get("toUserId")
    )
    event = doc.get("type") or doc.get("eventType") or doc.get("action")
    ts_raw = doc.get("eventTime") or doc.get("createdAt") or doc.get("ts")
    ts = parse_firestore_like_ts(ts_raw)
    if user_id is None or item_id is None or event is None:
        return None
    return str(user_id), str(item_id), str(event), ts


def load_events_from_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)

    col_map = {
        "userId": "user_id",
        "fromUserId": "user_id",
        "targetUserId": "item_id",
        "targetId": "item_id",
        "candidateUserId": "item_id",
        "toUserId": "item_id",
        "eventType": "event",
        "type": "event",
        "action": "event",
        "eventTime": "ts",
        "createdAt": "ts",
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    required = {"user_id", "item_id", "event"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")

    if "ts" not in df.columns:
        df["ts"] = pd.NaT

    df["ts"] = df["ts"].apply(parse_firestore_like_ts)
    df["user_id"] = df["user_id"].astype(str)
    df["item_id"] = df["item_id"].astype(str)
    df["event"] = df["event"].astype(str)
    out = df[["user_id", "item_id", "event", "ts"]].copy()
    out["_row_order"] = np.arange(len(out), dtype=np.int64)
    return out


def load_events_from_firestore_top_level(
    project_id: str,
    *,
    collection: str = "recEvents",
    start_time_utc: Optional[datetime] = None,
    end_time_utc: Optional[datetime] = None,
    database: Optional[str] = None,
) -> pd.DataFrame:
    require_firestore()
    db = firestore.Client(project=project_id, database=database)
    q = db.collection(collection)

    start_str, end_str = _rec_events_created_at_query_bounds(start_time_utc, end_time_utc)
    if start_str is not None:
        q = q.where(filter=FieldFilter("createdAt", ">=", start_str))
    if end_str is not None:
        q = q.where(filter=FieldFilter("createdAt", "<", end_str))

    rows: List[Tuple[str, str, str, pd.Timestamp]] = []
    for doc in q.stream():
        ext = _extract_user_item_event_ts(doc.to_dict() or {})
        if ext is None:
            continue
        rows.append(ext)

    df = pd.DataFrame(rows, columns=["user_id", "item_id", "event", "ts"])
    if not df.empty:
        df["_row_order"] = np.arange(len(df), dtype=np.int64)
    return df


def load_events_from_firestore_user_subcollections(
    project_id: str,
    *,
    collection: str = "recEvents",
    start_time_utc: Optional[datetime] = None,
    end_time_utc: Optional[datetime] = None,
    database: Optional[str] = None,
) -> pd.DataFrame:
    require_firestore()
    db = firestore.Client(project=project_id, database=database)
    rows: List[Tuple[str, str, str, pd.Timestamp]] = []

    user_docs = db.collection(collection).list_documents()
    start_str, end_str = _rec_events_created_at_query_bounds(start_time_utc, end_time_utc)

    for user_doc_ref in user_docs:
        q = user_doc_ref.collection("events")
        if start_str is not None:
            q = q.where(filter=FieldFilter("createdAt", ">=", start_str))
        if end_str is not None:
            q = q.where(filter=FieldFilter("createdAt", "<", end_str))
        for doc in q.stream():
            ext = _extract_user_item_event_ts(doc.to_dict() or {})
            if ext is None:
                continue
            rows.append(ext)

    df = pd.DataFrame(rows, columns=["user_id", "item_id", "event", "ts"])
    if not df.empty:
        df["_row_order"] = np.arange(len(df), dtype=np.int64)
    return df


def load_events_from_firestore(
    project_id: str,
    *,
    collection: str = "recEvents",
    start_time_utc: Optional[datetime] = None,
    end_time_utc: Optional[datetime] = None,
    layout: str = DEFAULT_FIRESTORE_LAYOUT,
    database: Optional[str] = None,
) -> pd.DataFrame:
    if layout not in {"auto", "top_level", "user_subcollections"}:
        raise ValueError("layout must be one of: auto, top_level, user_subcollections")

    if layout == "top_level":
        return load_events_from_firestore_top_level(
            project_id,
            collection=collection,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
            database=database,
        )
    if layout == "user_subcollections":
        return load_events_from_firestore_user_subcollections(
            project_id,
            collection=collection,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
            database=database,
        )

    df = load_events_from_firestore_top_level(
        project_id,
        collection=collection,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
        database=database,
    )
    if not df.empty:
        return df
    return load_events_from_firestore_user_subcollections(
        project_id,
        collection=collection,
        start_time_utc=start_time_utc,
        end_time_utc=end_time_utc,
        database=database,
    )


def load_user_genders_from_firestore(
    project_id: str,
    *,
    users_collection: str = "users",
    database: Optional[str] = None,
) -> Dict[str, str]:
    require_firestore()
    db = firestore.Client(project=project_id, database=database)
    out: Dict[str, str] = {}
    for doc in db.collection(users_collection).stream():
        d = doc.to_dict() or {}
        onboarding = d.get("onboarding")
        if isinstance(onboarding, dict):
            gender = onboarding.get("gender")
            if gender is not None:
                out[doc.id] = str(gender).strip().lower()
    return out


def load_profile_index_from_firestore(
    project_id: str,
    *,
    collection: str = "profileIndex",
    database: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    require_firestore()
    db = firestore.Client(project=project_id, database=database)
    meta: Dict[str, Dict[str, Any]] = {}
    for doc in db.collection(collection).stream():
        d = doc.to_dict() or {}
        meta[doc.id] = {
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
            "lastActiveAt": parse_firestore_like_ts(d.get("lastActiveAt")),
        }
    return meta


def now_year_kst() -> int:
    kst = timezone(timedelta(hours=9))
    return datetime.now(tz=kst).year


def kst_age(birth_year: int, now_year: int) -> int:
    return now_year - birth_year + 1


def passes_policy(
    user_id: str,
    cand_id: str,
    meta: Dict[str, Dict[str, Any]],
    *,
    manner_min: float,
    active_within_days: int,
    require_same_university: bool,
    reciprocal: bool,
) -> bool:
    mu = meta.get(user_id)
    mv = meta.get(cand_id)
    if mu is None or mv is None:
        return False

    if not mv.get("isActive", True):
        return False
    if not mv.get("isVerified", False):
        return False
    if not mv.get("isProfileComplete", True):
        return False
    if safe_float(mv.get("mannerScore", 36.5), 36.5) < manner_min:
        return False

    last_active = mv.get("lastActiveAt")
    if isinstance(last_active, pd.Timestamp) and not pd.isna(last_active):
        days = (pd.Timestamp.now(tz="UTC") - last_active).total_seconds() / (24 * 3600)
        if days > active_within_days:
            return False

    if require_same_university:
        if not mu.get("universityId") or not mv.get("universityId"):
            return False
        if mu["universityId"] != mv["universityId"]:
            return False

    user_pref_gender = mu.get("prefGender", []) or []
    cand_gender = mv.get("gender")
    if user_pref_gender and cand_gender is not None and cand_gender not in user_pref_gender:
        return False

    by_u = mu.get("birthYear")
    by_v = mv.get("birthYear")
    now_year = now_year_kst()

    if isinstance(by_v, int):
        age_v = kst_age(by_v, now_year)
        amin = mu.get("prefAgeMin")
        amax = mu.get("prefAgeMax")
        if amin is not None and age_v < int(amin):
            return False
        if amax is not None and age_v > int(amax):
            return False

    if reciprocal:
        cand_pref_gender = mv.get("prefGender", []) or []
        user_gender = mu.get("gender")
        if cand_pref_gender and user_gender is not None and user_gender not in cand_pref_gender:
            return False

        if isinstance(by_u, int):
            age_u = kst_age(by_u, now_year)
            amin2 = mv.get("prefAgeMin")
            amax2 = mv.get("prefAgeMax")
            if amin2 is not None and age_u < int(amin2):
                return False
            if amax2 is not None and age_u > int(amax2):
                return False

    return True


@dataclasses.dataclass
class PairBuildConfig:
    event_weights: Dict[str, float]
    negative_events: set
    strong_positive_events: set
    half_life_days: float
    max_weight_per_pair: float
    allow_open_only_pairs: bool = False
    exclude_ai_items_from_training: bool = False


def normalize_events_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["user_id"] = out["user_id"].astype(str)
    out["item_id"] = out["item_id"].astype(str)
    out["event"] = out["event"].astype(str)
    if "ts" not in out.columns:
        out["ts"] = pd.NaT
    out["ts"] = out["ts"].apply(parse_firestore_like_ts)
    if "_row_order" not in out.columns:
        out["_row_order"] = np.arange(len(out), dtype=np.int64)
    return out[["user_id", "item_id", "event", "ts", "_row_order"]]


def collapse_pair_events(
    df: pd.DataFrame,
    cfg: PairBuildConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = normalize_events_df(df)
    known_events = set(cfg.event_weights.keys()) | set(cfg.negative_events)
    df = df[df["event"].isin(known_events)].copy()

    if cfg.exclude_ai_items_from_training:
        df = df[~df["item_id"].apply(is_ai_profile)].copy()

    if df.empty:
        raise ValueError(
            "No usable events after filtering known events"
            + (" / AI profiles." if cfg.exclude_ai_items_from_training else ".")
        )

    rows: List[Dict[str, Any]] = []
    negative_rows: List[Dict[str, Any]] = []
    now_utc = pd.Timestamp.now(tz="UTC")

    for (user_id, item_id), g in df.groupby(["user_id", "item_id"], sort=False):
        if g["ts"].notna().all():
            g = g.sort_values(["ts", "_row_order"], kind="stable")
        else:
            g = g.sort_values(["_row_order"], kind="stable")

        final_event: Optional[str] = None
        final_weight: float = 0.0
        final_ts: pd.Timestamp = pd.NaT
        has_negative = False
        positive_history: List[str] = []
        negative_history: List[str] = []

        for _, row in g.iterrows():
            ev = str(row["event"])
            ts = row["ts"]

            if ev in cfg.negative_events:
                has_negative = True
                negative_history.append(ev)
                final_event = None
                final_weight = 0.0
                final_ts = pd.NaT
                continue

            if ev not in cfg.event_weights:
                continue

            w = safe_float(cfg.event_weights.get(ev, 0.0), 0.0)
            positive_history.append(ev)

            if w <= 0.0 and not cfg.allow_open_only_pairs:
                continue

            if final_event is None:
                final_event = ev
                final_weight = w
                final_ts = ts
                continue

            replace = False
            if w > final_weight:
                replace = True
            elif math.isclose(w, final_weight):
                old_valid = isinstance(final_ts, pd.Timestamp) and not pd.isna(final_ts)
                new_valid = isinstance(ts, pd.Timestamp) and not pd.isna(ts)
                if new_valid and (not old_valid or ts >= final_ts):
                    replace = True

            if replace:
                final_event = ev
                final_weight = w
                final_ts = ts

        if has_negative:
            negative_rows.append({
                "user_id": user_id,
                "item_id": item_id,
                "events": negative_history,
            })

        if final_event is None:
            continue
        if final_weight <= 0.0 and not cfg.allow_open_only_pairs:
            continue

        ts_for_decay = final_ts
        if not isinstance(ts_for_decay, pd.Timestamp) or pd.isna(ts_for_decay):
            age_days = 0.0
        else:
            age_days = max(0.0, (now_utc - ts_for_decay).total_seconds() / (24 * 3600))

        decayed = final_weight * half_life_decay(age_days, cfg.half_life_days)
        decayed = float(min(decayed, cfg.max_weight_per_pair))

        rows.append({
            "user_id": user_id,
            "item_id": item_id,
            "final_event": final_event,
            "weight": decayed,
            "raw_weight": final_weight,
            "ts": final_ts,
            "age_days": age_days,
            "is_strong": final_event in cfg.strong_positive_events,
            "positive_events": positive_history,
            "had_negative": has_negative,
        })

    pair_df = pd.DataFrame(rows)
    neg_df = pd.DataFrame(negative_rows)

    if pair_df.empty:
        raise ValueError(
            "No positive pairs survived collapse_pair_events. "
            "Check event weights / negative events / open-only handling."
        )
    return pair_df, neg_df


def build_interaction_matrix_from_pairs(
    pair_df: pd.DataFrame,
    neg_df: Optional[pd.DataFrame] = None,
) -> Tuple[sparse.csr_matrix, Dict[str, int], List[str], Dict[int, set], pd.DataFrame]:
    pair_df = pair_df.copy()
    pair_df["user_id"] = pair_df["user_id"].astype(str)
    pair_df["item_id"] = pair_df["item_id"].astype(str)

    users = pd.Index(pair_df["user_id"].unique())
    items = pd.Index(pair_df["item_id"].unique())

    user2idx = {u: i for i, u in enumerate(users.tolist())}
    item2idx = {it: j for j, it in enumerate(items.tolist())}
    idx2item = items.tolist()

    pair_df["user_idx"] = pair_df["user_id"].map(user2idx)
    pair_df["item_idx"] = pair_df["item_id"].map(item2idx)

    rows = pair_df["user_idx"].to_numpy(dtype=np.int64)
    cols = pair_df["item_idx"].to_numpy(dtype=np.int64)
    data = pair_df["weight"].to_numpy(dtype=np.float32)

    coo = sparse.coo_matrix((data, (rows, cols)), shape=(len(users), len(items)), dtype=np.float32)
    coo.sum_duplicates()
    mat = coo.tocsr()

    negative_by_useridx: Dict[int, set] = defaultdict(set)
    if neg_df is not None and not neg_df.empty:
        for _, row in neg_df.iterrows():
            u = str(row["user_id"])
            it = str(row["item_id"])
            if u in user2idx and it in item2idx:
                negative_by_useridx[user2idx[u]].add(item2idx[it])

    return mat, user2idx, idx2item, negative_by_useridx, pair_df


def compute_user_signal_stats(pair_df: pd.DataFrame) -> pd.DataFrame:
    if pair_df.empty:
        return pd.DataFrame(columns=["user_id", "total_pairs", "strong_pairs", "total_weight"])
    agg = (
        pair_df.groupby("user_id", as_index=False)
        .agg(
            total_pairs=("item_id", "count"),
            strong_pairs=("is_strong", "sum"),
            total_weight=("weight", "sum"),
        )
        .copy()
    )
    agg["strong_pairs"] = agg["strong_pairs"].astype(int)
    return agg


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
            print(f"[warn] implicit KNN unavailable/failed ({e}); falling back to scipy cosine KNN")
            return _train_cosine_knn_scipy(user_item)
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
    p = argparse.ArgumentParser(description="Seolleyeon Item-KNN training + Firestore export (improved)")

    # input
    p.add_argument("--events_csv", type=str, default=None)
    p.add_argument("--firestore_events", action="store_true")
    p.add_argument("--firestore_project", type=str, default=None)
    p.add_argument("--firestore_database", type=str, default=None)
    p.add_argument("--events_collection", type=str, default="recEvents")
    p.add_argument("--events_layout", type=str, default=DEFAULT_FIRESTORE_LAYOUT,
                   choices=["auto", "top_level", "user_subcollections"])

    # time range
    p.add_argument("--date_key", type=str, required=True, help="YYYYMMDD (KST)")
    p.add_argument("--lookback_days", type=int, default=120)

    # signal building
    p.add_argument("--event_weights_json", type=str, default=None,
                   help='e.g. {"open":0.0,"like":4.0,"match_created":7.0,"chat_first_message":9.0}')
    p.add_argument("--negative_events_json", type=str, default=None,
                   help='e.g. ["nope","block","report"]')
    p.add_argument("--strong_positive_events_json", type=str, default=None,
                   help='e.g. ["like","match_created","chat_first_message"]')
    p.add_argument("--half_life_days", type=float, default=30.0)
    p.add_argument("--max_weight_per_pair", type=float, default=12.0)
    p.add_argument("--allow_open_only_pairs", action="store_true", help="기본은 False 권장")
    p.add_argument(
        "--exclude_ai_profiles_from_training",
        action="store_true",
        help="AI 취향 카드(female_*, male_*)를 학습 행렬에서 제외(이전 기본 동작)",
    )

    # model params
    p.add_argument("--knn_type", type=str, default=DEFAULT_KNN_TYPE, choices=["bm25", "cosine", "tfidf"])
    p.add_argument("--K", type=int, default=120)
    p.add_argument("--num_threads", type=int, default=0)
    p.add_argument("--bm25_k1", type=float, default=1.2)
    p.add_argument("--bm25_b", type=float, default=0.75)

    # warm user gating
    p.add_argument("--min_total_pairs", type=int, default=5)
    p.add_argument("--min_strong_pairs", type=int, default=3)
    p.add_argument("--min_total_weight", type=float, default=12.0)

    # recommendation
    p.add_argument("--topn", type=int, default=300)
    p.add_argument("--oversample", type=int, default=6)

    # policy filters
    p.add_argument("--apply_policy_filters", action="store_true")
    p.add_argument("--profile_index_collection", type=str, default="profileIndex")
    p.add_argument("--manner_min", type=float, default=33.0)
    p.add_argument("--active_within_days", type=int, default=14)
    p.add_argument("--require_same_university", dest="require_same_university", action="store_true")
    p.add_argument("--no_require_same_university", dest="require_same_university", action="store_false")
    p.set_defaults(require_same_university=True)
    p.add_argument("--no_reciprocal", action="store_true")

    # export
    p.add_argument("--export_firestore", dest="export_firestore", action="store_true")
    p.add_argument("--no_export_firestore", dest="export_firestore", action="store_false")
    p.set_defaults(export_firestore=True)
    p.add_argument("--algorithm_version", type=str, default=None)

    args = p.parse_args()

    event_weights = dict(DEFAULT_EVENT_WEIGHTS)
    if args.event_weights_json:
        event_weights.update(json.loads(args.event_weights_json))

    negative_events = set(DEFAULT_NEGATIVE_EVENTS)
    if args.negative_events_json:
        negative_events = set(json.loads(args.negative_events_json))

    strong_positive_events = set(DEFAULT_STRONG_POSITIVE_EVENTS)
    if args.strong_positive_events_json:
        strong_positive_events = set(json.loads(args.strong_positive_events_json))

    # ---- Load events ----
    if args.events_csv:
        df = load_events_from_csv(args.events_csv)
        if df.empty and args.firestore_project:
            print("[data] CSV empty, fallback to Firestore")
            start_day_utc, end_day_utc = parse_datekey_to_utc_range(args.date_key)
            start_time = start_day_utc - timedelta(days=int(args.lookback_days))
            df = load_events_from_firestore(
                args.firestore_project,
                collection=args.events_collection,
                start_time_utc=start_time,
                end_time_utc=end_day_utc,
                layout=args.events_layout,
                database=args.firestore_database,
            )
    elif args.firestore_events:
        if not args.firestore_project:
            raise ValueError("--firestore_project is required for --firestore_events")
        start_day_utc, end_day_utc = parse_datekey_to_utc_range(args.date_key)
        start_time = start_day_utc - timedelta(days=int(args.lookback_days))
        df = load_events_from_firestore(
            args.firestore_project,
            collection=args.events_collection,
            start_time_utc=start_time,
            end_time_utc=end_day_utc,
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
        exclude_ai_items_from_training=bool(args.exclude_ai_profiles_from_training),
    )
    pair_df, neg_df = collapse_pair_events(df, pair_cfg)

    print(f"[pairs] surviving positive pairs: {len(pair_df):,}")
    print(f"[pairs] negative pairs: {0 if neg_df.empty else len(neg_df):,}")

    user_item, user2idx, idx2item, negative_by_useridx, pair_df = build_interaction_matrix_from_pairs(pair_df, neg_df)
    n_users, n_items = user_item.shape
    print(f"[matrix] users={n_users:,}, items={n_items:,}, nnz={user_item.nnz:,}")

    signal_df = compute_user_signal_stats(pair_df)
    signal_meta_by_uid: Dict[str, Dict[str, Any]] = {}
    eligible_user_ids: List[str] = []

    for _, row in signal_df.iterrows():
        uid = str(row["user_id"])
        total_pairs = int(row["total_pairs"])
        strong_pairs = int(row["strong_pairs"])
        total_weight = float(row["total_weight"])
        eligible = (
            total_pairs >= int(args.min_total_pairs)
            and strong_pairs >= int(args.min_strong_pairs)
            and total_weight >= float(args.min_total_weight)
        )
        confidence = compute_source_confidence(total_pairs, strong_pairs, total_weight)
        signal_meta_by_uid[uid] = {
            "totalPairs": total_pairs,
            "strongPairs": strong_pairs,
            "totalWeight": total_weight,
            "eligibleForKnn": eligible,
            "confidence": confidence,
        }
        if eligible:
            eligible_user_ids.append(uid)

    active_user_indices = [user2idx[u] for u in eligible_user_ids if u in user2idx]
    print(f"[train] eligible users: {len(active_user_indices):,} / {len(user2idx):,}")

    if not active_user_indices:
        print("[train] no eligible users. Nothing to export.")
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

    recs_to_export: Dict[str, List[Dict[str, Any]]] = {}
    topn = int(args.topn)
    oversample = max(1, int(args.oversample))

    for ui in tqdm(active_user_indices, desc="generating"):
        uid = idx2user[ui]
        if uid is None:
            continue

        filter_items = set(negative_by_useridx.get(ui, set()))
        filter_items.update(i for i, item in enumerate(idx2item) if is_ai_profile(item))

        self_item_idx = item2idx.get(uid)
        if self_item_idx is not None:
            filter_items.add(self_item_idx)

        item_idx, scores = model.recommend(
            ui,
            user_item,
            N=topn * oversample,
            filter_already_liked_items=True,
            filter_items=list(filter_items) if filter_items else None,
        )

        # implicit can return python lists or numpy arrays depending on backend
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
            recs_to_export[uid] = items_out

    print(f"[export] prepared recs for users: {len(recs_to_export):,}")

    algorithm_version = args.algorithm_version or (
        f"knn_v2_{cfg.knn_type}_K{cfg.K}_{args.date_key}"
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
            "excludeAiProfilesFromTraining": bool(
                args.exclude_ai_profiles_from_training
            ),
            "gating": {
                "minTotalPairs": int(args.min_total_pairs),
                "minStrongPairs": int(args.min_strong_pairs),
                "minTotalWeight": float(args.min_total_weight),
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
