#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import sparse

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
DEFAULT_FIRESTORE_LAYOUT = "auto"  # auto | top_level | user_subcollections
DEFAULT_NEGATIVE_PREF_WEIGHTS: Dict[str, float] = {
    "nope": 1.0,
    "block": 1.5,
    "report": 2.0,
}


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


def safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def clamp01(x: float) -> float:
    return clamp(float(x), 0.0, 1.0)


def compute_source_confidence(total_pairs: int, strong_pairs: int, total_weight: float) -> float:
    c_pairs = min(1.0, total_pairs / 10.0)
    c_strong = min(1.0, strong_pairs / 4.0)
    c_weight = min(1.0, total_weight / 20.0)
    conf = 0.20 + 0.35 * c_pairs + 0.35 * c_strong + 0.10 * c_weight
    return round(clamp01(conf), 4)


def compute_clip_signal_confidence(total_pairs: int, strong_pairs: int, total_weight: float) -> float:
    c_pairs = min(1.0, total_pairs / 6.0)
    c_strong = min(1.0, strong_pairs / 3.0)
    c_weight = min(1.0, total_weight / 15.0)
    conf = 0.10 + 0.40 * c_pairs + 0.35 * c_strong + 0.15 * c_weight
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


def load_users_with_photos_from_firestore(
    project_id: str,
    *,
    users_collection: str = "users",
    database: Optional[str] = None,
) -> Dict[str, List[str]]:
    require_firestore()
    db = firestore.Client(project=project_id, database=database)
    result: Dict[str, List[str]] = {}
    for doc in db.collection(users_collection).stream():
        uid = doc.id
        d = doc.to_dict() or {}
        onboarding = d.get("onboarding")
        if not isinstance(onboarding, dict):
            continue
        photos = onboarding.get("photoUrls")
        if not isinstance(photos, list) or len(photos) == 0:
            continue
        urls = [str(p) for p in photos if p and str(p).startswith("http")]
        if urls:
            result[uid] = urls
    return result


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
    exclude_ai_items_from_training: bool = True


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
        final_state: Optional[str] = None
        final_negative_event: Optional[str] = None
        final_negative_ts: pd.Timestamp = pd.NaT
        had_negative_any = False
        positive_history: List[str] = []
        negative_history: List[str] = []

        for _, row in g.iterrows():
            ev = str(row["event"])
            ts = row["ts"]

            if ev in cfg.negative_events:
                had_negative_any = True
                negative_history.append(ev)
                final_state = "negative"
                final_negative_event = ev
                final_negative_ts = ts
                final_event = None
                final_weight = 0.0
                final_ts = pd.NaT
                continue

            if ev not in cfg.event_weights:
                continue

            positive_history.append(ev)
            w = safe_float(cfg.event_weights.get(ev, 0.0), 0.0)
            if w <= 0.0 and not cfg.allow_open_only_pairs:
                continue

            if final_state != "positive":
                final_state = "positive"
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

        if final_state == "negative":
            negative_rows.append({
                "user_id": user_id,
                "item_id": item_id,
                "final_negative_event": final_negative_event,
                "ts": final_negative_ts,
                "negative_events": negative_history,
            })
            continue

        if final_state != "positive" or final_event is None:
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
            "had_negative_any": had_negative_any,
        })

    pair_df = pd.DataFrame(rows)
    neg_df = pd.DataFrame(negative_rows)

    if pair_df.empty:
        raise ValueError(
            "No positive pairs survived collapse_pair_events. "
            "Check event weights / negative events / open-only handling."
        )
    return pair_df, neg_df


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


def user_ids_by_threshold(
    signal_df: pd.DataFrame,
    *,
    min_total_pairs: int,
    min_strong_pairs: int,
    min_total_weight: float,
) -> List[str]:
    if signal_df.empty:
        return []
    cond = (
        (signal_df["total_pairs"] >= int(min_total_pairs))
        & (signal_df["strong_pairs"] >= int(min_strong_pairs))
        & (signal_df["total_weight"] >= float(min_total_weight))
    )
    return signal_df.loc[cond, "user_id"].astype(str).tolist()


def prune_training_pairs(
    pair_df: pd.DataFrame,
    *,
    min_train_total_pairs: int,
    min_train_strong_pairs: int,
    min_train_total_weight: float,
    min_item_support: int,
    min_item_strong_users: int,
    min_pair_weight: float,
    iterative: bool = True,
) -> pd.DataFrame:
    cur = pair_df.copy()
    if min_pair_weight > 0:
        cur = cur[cur["weight"] >= float(min_pair_weight)].copy()
    if cur.empty:
        return cur

    train_signal = compute_user_signal_stats(cur)
    keep_users = set(
        user_ids_by_threshold(
            train_signal,
            min_total_pairs=min_train_total_pairs,
            min_strong_pairs=min_train_strong_pairs,
            min_total_weight=min_train_total_weight,
        )
    )
    cur = cur[cur["user_id"].isin(keep_users)].copy()
    if cur.empty:
        return cur

    prev_rows = -1
    while True:
        if cur.empty:
            break

        item_total = cur.groupby("item_id")["user_id"].nunique()
        keep_items = set(item_total[item_total >= int(min_item_support)].index.tolist())
        if int(min_item_strong_users) > 0:
            strong_cur = cur[cur["is_strong"] == True]  # noqa: E712
            if strong_cur.empty:
                keep_items = set()
            else:
                item_strong = strong_cur.groupby("item_id")["user_id"].nunique()
                strong_items = set(
                    item_strong[item_strong >= int(min_item_strong_users)].index.tolist()
                )
                keep_items &= strong_items

        cur = cur[cur["item_id"].isin(keep_items)].copy()
        if cur.empty:
            break

        train_signal = compute_user_signal_stats(cur)
        keep_users = set(
            user_ids_by_threshold(
                train_signal,
                min_total_pairs=min_train_total_pairs,
                min_strong_pairs=min_train_strong_pairs,
                min_total_weight=min_train_total_weight,
            )
        )
        cur = cur[cur["user_id"].isin(keep_users)].copy()
        if not iterative:
            break
        if len(cur) == prev_rows:
            break
        prev_rows = len(cur)

    return cur.reset_index(drop=True)


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
