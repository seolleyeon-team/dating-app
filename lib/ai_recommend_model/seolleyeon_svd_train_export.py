#!/usr/bin/env python3
"""
Seolleyeon SVD(=Matrix Factorization) Recommender - Train & Export

목표:
- 설레연 1:1 추천에서 SVD/CF 소스 하나를 만들기 위해,
  implicit feedback(열람/like/match/chat)을 행렬로 만들고
  잠재요인 분해(ALS or Truncated SVD)로 TopN 후보를 산출한 뒤
  Firestore modelRecs/{uid}/daily/{dateKey}/sources/svd 에 저장.

권장 운영:
- 이 스크립트를 Cloud Run Job / VM / 내부 서버에서 하루 1회 실행
- 결과는 온라인 추천(getOrCreateDailyRecs)에서 RRF로 CLIP/KNN/Content와 통합

입력(둘 중 하나):
1) --events_csv: CSV with columns: user_id,item_id,event,ts(optional)
2) --firestore_events: Firestore recEvents collection에서 기간 조회

Firestore 저장 경로(예시):
- modelRecs/{uid}/daily/{dateKey}/sources/svd

주의:
- 이 코드는 "학습용 로그"가 top-level recEvents에 존재한다는 가정이 제일 깔끔함.
- nope/block/report 같은 강한 음성 피드백은 오프라인에서 제외용으로만 쓰는 걸 기본으로 함.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy import sparse
from tqdm import tqdm

# --- Firestore ---
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter


def _rec_events_created_at_query_bounds(
    start_time_utc: Optional[datetime], end_time_utc: Optional[datetime]
) -> Tuple[Optional[str], Optional[str]]:
    """앱은 createdAt을 UTC ISO 문자열로 저장 — Range 쿼리도 문자열로 맞춤."""
    def to_iso(dt: datetime) -> str:
        u = dt.astimezone(timezone.utc)
        return u.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    return (
        to_iso(start_time_utc) if start_time_utc is not None else None,
        to_iso(end_time_utc) if end_time_utc is not None else None,
    )


# =========================
# Config / Defaults
# =========================

DEFAULT_EVENT_WEIGHTS = {
    "open": 1.0,
    "like": 3.0,
    "match_created": 5.0,
    "chat_first_message": 4.0,
    # "impression": 0.1,  # 필요하면 포함 가능(노이즈라 기본 제외 권장)
    # "nope": 0.0,        # 학습에는 보통 안 넣고 "제외 리스트"로만 씀
}

DEFAULT_NEGATIVE_EVENTS = {"nope"}  # 추천 생성 시 제외할 이벤트 (학습에는 반영 X)

DEFAULT_ALGO = "als"  # als | svds


# =========================
# Utilities
# =========================

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

    # KST = UTC+9
    kst = timezone(timedelta(hours=9))
    start_kst = datetime(yyyy, mm, dd, 0, 0, 0, tzinfo=kst)
    end_kst = start_kst + timedelta(days=1)

    start_utc = start_kst.astimezone(timezone.utc)
    end_utc = end_kst.astimezone(timezone.utc)
    return start_utc, end_utc


def half_life_decay(age_days: float, half_life_days: float) -> float:
    if half_life_days <= 0:
        return 1.0
    # weight * 0.5^(age/half_life)
    return 0.5 ** (age_days / half_life_days)


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


# =========================
# Data loading
# =========================

def load_events_from_csv(path: str) -> pd.DataFrame:
    """
    CSV columns:
      user_id, item_id, event, ts (ts optional)
    ts: ISO8601 or unix seconds or empty
    """
    df = pd.read_csv(path)

    # Auto-map column names from recEvents export format
    col_map = {
        "userId": "user_id",
        "targetUserId": "item_id",
        "eventType": "event",
        "createdAt": "ts",
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)

    required = {"user_id", "item_id", "event"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")

    if "ts" not in df.columns:
        df["ts"] = pd.NaT

    # parse timestamp
    def parse_ts(v):
        if pd.isna(v):
            return pd.NaT
        if isinstance(v, (int, float)) and not math.isnan(float(v)):
            # unix seconds
            return pd.to_datetime(int(v), unit="s", utc=True)
        # string
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
        start_str, end_str = _rec_events_created_at_query_bounds(start_time_utc, end_time_utc)
        if start_str is not None:
            q = q.where(filter=FieldFilter("createdAt", ">=", start_str))
        if end_str is not None:
            q = q.where(filter=FieldFilter("createdAt", "<", end_str))

        for doc in q.stream():
            d = doc.to_dict() or {}
            user_id = d.get("userId")
            item_id = d.get("targetUserId") or d.get("targetId") or d.get("candidateUserId")
            event = d.get("eventType") or d.get("type")
            ts = d.get("createdAt")

            if user_id is None or item_id is None or event is None:
                continue

            # ts could be datetime already
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                else:
                    ts = ts.astimezone(timezone.utc)
            else:
                ts = pd.NaT

            rows.append((str(user_id), str(item_id), str(event), ts))

    df = pd.DataFrame(rows, columns=["user_id", "item_id", "event", "ts"])
    return df


# =========================
# Metadata (optional policy filtering)
# =========================

def load_user_genders_from_firestore(
    project_id: str,
    *,
    users_collection: str = "users",
    database: Optional[str] = None,
) -> Dict[str, str]:
    """users/{uid} onboarding.gender 로드. uid -> gender (female|male 등)"""
    db = firestore.Client(project=project_id, database=database)
    result: Dict[str, str] = {}
    for doc in db.collection(users_collection).stream():
        d = doc.to_dict() or {}
        onboarding = d.get("onboarding")
        if isinstance(onboarding, dict):
            g = onboarding.get("gender")
            if g is not None:
                result[doc.id] = str(g).strip().lower()
    return result


def load_profile_index_from_firestore(
    project_id: str,
    *,
    collection: str = "profileIndex",
    database: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    profileIndex/{uid} (서버 전용 인덱스)에서 추천 필터링에 필요한 최소 필드만 로딩
    """
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


def kst_age(birth_year: int, now_year_kst: int) -> int:
    # 한국식 나이(원하면 만 나이로 바꿔도 됨)
    return now_year_kst - birth_year + 1


def now_year_kst() -> int:
    kst = timezone(timedelta(hours=9))
    return datetime.now(tz=kst).year


def is_ai_profile(item_id: str) -> bool:
    """ai_preference 스와이프 타겟: female_123, male_456 형식 — 추천 출력에서 제외"""
    if not item_id or not isinstance(item_id, str):
        return False
    return item_id.startswith("female_") or item_id.startswith("male_")


def ai_profile_item_indices(idx2item: Sequence[str]) -> set:
    """행렬 item 컬럼 중 AI 더미 ID — 학습에는 남기되 추천 후보에서는 제외(순위 눌림 방지)."""
    return {i for i, uid in enumerate(idx2item) if is_ai_profile(uid)}


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
    """
    설레연 정책 필터(옵션): 대학/인증/활동/매너/선호/상호선호 등
    """
    mu = meta.get(u)
    mv = meta.get(v)
    if mu is None or mv is None:
        return False

    # base gating
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
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)
        else:
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

    # preference filter (u's preference on v)
    u_pref_gender = mu.get("prefGender", []) or []
    v_gender = mv.get("gender")
    if u_pref_gender and v_gender is not None and v_gender not in u_pref_gender:
        return False

    # age filter
    by_u = mu.get("birthYear")
    by_v = mv.get("birthYear")
    if isinstance(by_u, int) and isinstance(by_v, int):
        age_v = kst_age(by_v, now_year_kst())
        amin = mu.get("prefAgeMin")
        amax = mu.get("prefAgeMax")
        if amin is not None and age_v < int(amin):
            return False
        if amax is not None and age_v > int(amax):
            return False

    # reciprocal preference: v's preference on u
    if reciprocal:
        v_pref_gender = mv.get("prefGender", []) or []
        u_gender = mu.get("gender")
        if v_pref_gender and u_gender is not None and u_gender not in v_pref_gender:
            return False

        if isinstance(by_u, int) and isinstance(by_v, int):
            age_u = kst_age(by_u, now_year_kst())
            amin2 = mv.get("prefAgeMin")
            amax2 = mv.get("prefAgeMax")
            if amin2 is not None and age_u < int(amin2):
                return False
            if amax2 is not None and age_u > int(amax2):
                return False

    return True


# =========================
# Build interaction matrix
# =========================

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
      user_item_csr: shape (n_users, n_items)
      user2idx: {user_id -> row index}
      idx2item: list mapping col index -> item_id
      nope_by_useridx: dict {user_idx -> set(item_idx)} (추천 생성 시 제외용)
    """
    # clean
    df = df.copy()
    df["user_id"] = df["user_id"].astype(str)
    df["item_id"] = df["item_id"].astype(str)
    df["event"] = df["event"].astype(str)

    # keep only events we know (weights or negative)
    known = set(event_weights.keys()) | set(negative_events)
    df = df[df["event"].isin(known)]

    # compute base weight (positive only)
    def base_weight(ev: str) -> float:
        return float(event_weights.get(ev, 0.0))

    df["base_w"] = df["event"].map(base_weight).astype(float)

    # time decay
    if time_decay_half_life_days > 0:
        now = datetime.now(tz=timezone.utc)
        ages = []
        for ts in df["ts"].tolist():
            if pd.isna(ts):
                ages.append(0.0)
                continue
            if isinstance(ts, pd.Timestamp):
                ts = ts.to_pydatetime()
            if isinstance(ts, datetime):
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_days = max(0.0, (now - ts.astimezone(timezone.utc)).total_seconds() / (24 * 3600))
                ages.append(age_days)
            else:
                ages.append(0.0)
        df["decay"] = [half_life_decay(a, time_decay_half_life_days) for a in ages]
    else:
        df["decay"] = 1.0

    df["w"] = df["base_w"] * df["decay"]

    # prepare id mappings
    users = pd.Index(df["user_id"].unique())
    items = pd.Index(df["item_id"].unique())

    user2idx = {u: i for i, u in enumerate(users.tolist())}
    item2idx = {it: j for j, it in enumerate(items.tolist())}
    idx2item = items.tolist()

    # build nope_by_useridx
    nope_by_useridx: Dict[int, set] = {}
    neg_df = df[df["event"].isin(negative_events)]
    for _, row in neg_df.iterrows():
        ui = user2idx[row["user_id"]]
        ii = item2idx[row["item_id"]]
        nope_by_useridx.setdefault(ui, set()).add(ii)

    # build positive interactions matrix
    pos_df = df[df["base_w"] > 0].copy()

    if pos_df.empty:
        raise ValueError("No positive interactions found. Need at least 'open/like/match/chat' events.")

    # aggregate by (user,item): sum weights but cap
    grp = pos_df.groupby(["user_id", "item_id"], as_index=False)["w"].sum()
    grp["w"] = grp["w"].clip(upper=max_weight_per_pair)

    rows = grp["user_id"].map(user2idx).to_numpy()
    cols = grp["item_id"].map(item2idx).to_numpy()
    data = grp["w"].to_numpy(dtype=np.float32)

    coo = sparse.coo_matrix((data, (rows, cols)), shape=(len(users), len(items)), dtype=np.float32)
    coo.sum_duplicates()
    mat = coo.tocsr()
    return mat, user2idx, idx2item, nope_by_useridx


# =========================
# Models
# =========================

@dataclasses.dataclass
class TrainConfig:
    algo: str = DEFAULT_ALGO  # "als" or "svds"
    factors: int = 64
    iterations: int = 20
    regularization: float = 0.01
    alpha: float = 1.0          # implicit ALS confidence scaling
    random_state: int = 42


class SVDRecommender:
    """
    Unified interface for:
    - implicit ALS MF (recommended for implicit feedback)
    - truncated SVD via scipy.svds (fallback)
    """

    def __init__(self, cfg: TrainConfig):
        self.cfg = cfg
        self.user_factors: Optional[np.ndarray] = None
        self.item_factors: Optional[np.ndarray] = None
        self._als_model = None

    def fit(self, user_item: sparse.csr_matrix):
        if self.cfg.algo == "als":
            self._fit_als(user_item)
        elif self.cfg.algo == "svds":
            self._fit_svds(user_item)
        else:
            raise ValueError(f"Unknown algo: {self.cfg.algo}")

    def _fit_als(self, user_item: sparse.csr_matrix):
        try:
            import implicit  # noqa: F401
            from implicit.als import AlternatingLeastSquares
        except Exception as e:
            raise RuntimeError(
                "Failed to import 'implicit'. Install it or use --algo svds.\n"
                f"Error: {e}"
            )

        # implicit ALS fit() expects (users x items); scale by alpha for confidence
        conf = (user_item * float(self.cfg.alpha)).tocsr()

        model = AlternatingLeastSquares(
            factors=self.cfg.factors,
            regularization=self.cfg.regularization,
            iterations=self.cfg.iterations,
            random_state=self.cfg.random_state,
        )
        model.fit(conf)

        # store factors
        # model.user_factors: (n_users, k), model.item_factors: (n_items, k)
        self._als_model = model
        uf = model.user_factors
        itf = model.item_factors
        # implicit >= 0.6 may return GPU arrays; convert to numpy first
        if hasattr(uf, "to_numpy"):
            uf = uf.to_numpy()
        if hasattr(itf, "to_numpy"):
            itf = itf.to_numpy()
        self.user_factors = np.array(uf, dtype=np.float32, copy=True)
        self.item_factors = np.array(itf, dtype=np.float32, copy=True)

    def _fit_svds(self, user_item: sparse.csr_matrix):
        from scipy.sparse.linalg import svds

        k = int(self.cfg.factors)
        if k <= 0:
            raise ValueError("factors must be > 0")

        # svds returns smallest singular values; we sort descending
        U, s, Vt = svds(user_item, k=k)
        idx = np.argsort(-s)  # descending
        s = s[idx]
        U = U[:, idx]
        Vt = Vt[idx, :]

        # user_factors = U * diag(s)
        self.user_factors = (U * s).astype(np.float32, copy=False)
        self.item_factors = (Vt.T).astype(np.float32, copy=False)

    def recommend_for_user(
        self,
        user_idx: int,
        user_items: sparse.csr_matrix,
        *,
        topn: int,
        filter_items: Optional[Sequence[int]] = None,
        oversample: int = 5,
        filter_already_interacted: bool = True,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns:
          item_indices: shape (topn,)
          scores: shape (topn,)
        """
        if self.user_factors is None or self.item_factors is None:
            raise RuntimeError("Model not trained.")

        # Use our own scoring for both ALS and svds (avoids implicit recommend
        # matrix-orientation issues with single-user slices)
        uvec = self.user_factors[user_idx]  # (k,)
        scores = self.item_factors @ uvec   # (n_items,)
        scores = scores.astype(np.float32)

        n_items = int(scores.shape[0])
        if n_items == 0 or int(topn) <= 0:
            return np.array([], dtype=np.int64), np.array([], dtype=np.float32)

        # 제외: 이미 상호작용 / nope / 본인 — 점수는 유지하고 eligible 만으로 상위 k 선택.
        # 구버전은 scores=-np.inf + argsort(-scores) 조합으로 -(-inf)=+inf 정렬 왜곡 및
        # topn > 추천 가능 아이템 수 일 때 -inf 행이 결과에 섞이는 문제가 있었음.
        eligible = np.ones(n_items, dtype=bool)
        if filter_already_interacted:
            start, end = user_items.indptr[user_idx], user_items.indptr[user_idx + 1]
            eligible[user_items.indices[start:end]] = False
        if filter_items is not None and len(filter_items) > 0:
            eligible[np.array(list(filter_items), dtype=np.int64)] = False

        valid_idx = np.flatnonzero(eligible)
        if valid_idx.size == 0:
            return np.array([], dtype=np.int64), np.array([], dtype=np.float32)

        sub = scores[valid_idx]
        k = int(min(int(topn), int(valid_idx.size)))

        # 점수 **큰** 순 (내적값은 음수일 수 있음 — 정상)
        if k >= sub.size:
            order = np.argsort(-sub)
        else:
            part = np.argpartition(sub, -k)[-k:]
            order = part[np.argsort(-sub[part])]
        sel = valid_idx[order[:k]]
        return sel.astype(np.int64, copy=False), scores[sel]


# =========================
# Export to Firestore
# =========================

def export_to_firestore(
    project_id: str,
    date_key: str,
    recommendations: Dict[str, List[Dict[str, Any]]],
    *,
    algorithm_version: str,
    model_meta: Dict[str, Any],
    database: Optional[str] = None,
):
    """
    recommendations: { user_id -> [ {uid, rank, score}, ... ] }
    Writes to:
      modelRecs/{user_id}/daily/{date_key}/sources/svd
    """
    db = firestore.Client(project=project_id, database=database)

    # BulkWriter (fast for many docs)
    bw = db.bulk_writer()

    gen_at = firestore.SERVER_TIMESTAMP
    for uid, items in recommendations.items():
        doc_ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/svd")
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


# =========================
# Debug: 필터 전 SVD 순위 덤프
# =========================

def dump_raw_user_svd_preview(
    args: argparse.Namespace,
    *,
    user_item: sparse.csr_matrix,
    model: SVDRecommender,
    user2idx: Dict[str, int],
    idx2item: List[str],
    nope_by_useridx: Dict[int, set],
    item2idx_map: Dict[str, int],
    gender_by_uid: Dict[str, str],
    meta: Optional[Dict[str, Dict[str, Any]]],
    pos_counts: np.ndarray,
) -> None:
    """
    recommend_for_user 직후 순위(동성/AI/정책 필터 적용 전)를 stdout 및 선택적 JSON 파일로 출력.
    eligible이 아니어도 행렬에 유저가 있으면 덤프 시도.
    """
    uid = (args.dump_raw_user or "").strip()
    if not uid:
        return

    dump_topk = max(1, int(args.dump_raw_topk))

    print(f"\n[dump_raw] ========== SVD raw ranking (before gender/ai/policy) user={uid} ==========")

    if uid not in user2idx:
        print(f"[dump_raw] user not in training matrix (no rows as user_id in events): {uid}")
        print("[dump_raw] ======================================================================\n")
        return

    ui = user2idx[uid]
    pos_c = int(pos_counts[ui])
    eligible = pos_c >= int(args.min_pos_interactions)
    print(
        f"[dump_raw] user_idx={ui} pos_item_count={pos_c} "
        f"min_pos_interactions={args.min_pos_interactions} eligible={eligible}",
    )

    filter_items: set = set(nope_by_useridx.get(ui, set())) | ai_profile_item_indices(idx2item)
    self_item_idx = item2idx_map.get(uid)
    if self_item_idx is not None:
        filter_items.add(self_item_idx)

    internal_topn = max(dump_topk * 5, int(args.topn) * 5, 200)
    internal_topn = min(internal_topn, len(idx2item))

    item_idx, scores = model.recommend_for_user(
        ui,
        user_item,
        topn=internal_topn,
        filter_items=list(filter_items),
        oversample=1,
        filter_already_interacted=True,
    )

    reciprocal = not args.no_reciprocal
    rows: List[Dict[str, Any]] = []
    for k in range(min(len(item_idx), dump_topk)):
        ii = int(item_idx[k])
        sc = float(scores[k])
        cand_uid = idx2item[ii]
        skip_reasons: List[str] = []
        if is_ai_profile(cand_uid):
            skip_reasons.append("ai_profile")
        u_g = gender_by_uid.get(uid)
        v_g = gender_by_uid.get(cand_uid)
        if u_g and v_g and u_g == v_g:
            skip_reasons.append("same_gender")
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
                skip_reasons.append("policy")

        rows.append(
            {
                "model_rank": k + 1,
                "uid": cand_uid,
                "score": sc,
                "would_be_skipped": len(skip_reasons) > 0,
                "skip_reasons": skip_reasons,
            }
        )

    payload = {
        "userId": uid,
        "user_idx": ui,
        "pos_item_count": pos_c,
        "eligible_for_export_loop": eligible,
        "note": "recommend_for_user: nope/self/seen + AI male_*/female_* columns excluded; then gender/policy in skip_reasons",
        "top": rows,
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    out_path = getattr(args, "dump_raw_out", None) or ""
    if isinstance(out_path, str) and out_path.strip():
        p = out_path.strip()
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[dump_raw] also wrote: {p}")

    print("[dump_raw] ======================================================================\n")


# =========================
# Main pipeline
# =========================

def main():
    p = argparse.ArgumentParser(description="Seolleyeon SVD(MF) training + Firestore export")
    # input
    p.add_argument("--events_csv", type=str, default=None, help="CSV path with user_id,item_id,event,ts")
    p.add_argument("--firestore_events", action="store_true", help="Load events from Firestore recEvents")
    p.add_argument("--firestore_project", type=str, default=None, help="GCP project id (Firestore)")
    p.add_argument("--firestore_database", type=str, default=None, help="Firestore database id (usually omit)")
    p.add_argument("--events_collection", type=str, default="recEvents", help="Firestore collection name for events")

    # time range
    p.add_argument("--date_key", type=str, required=True, help="YYYYMMDD (KST) - used for export path and event range")
    p.add_argument("--lookback_days", type=int, default=120, help="Training data lookback (days)")

    # model
    p.add_argument("--algo", type=str, default=DEFAULT_ALGO, choices=["als", "svds"])
    p.add_argument("--factors", type=int, default=64)
    p.add_argument("--iterations", type=int, default=20)
    p.add_argument("--regularization", type=float, default=0.01)
    p.add_argument("--alpha", type=float, default=1.0)
    p.add_argument("--random_state", type=int, default=42)

    # weights
    p.add_argument("--event_weights_json", type=str, default=None,
                   help='JSON mapping like {"open":1.0,"like":3.0,"match_created":5.0,"chat_first_message":4.0}')
    p.add_argument("--half_life_days", type=float, default=30.0, help="Time decay half-life in days (0=disable)")
    p.add_argument("--max_weight_per_pair", type=float, default=10.0, help="Cap summed weight per (user,item)")

    # recommendation
    p.add_argument("--topn", type=int, default=400, help="TopN to export per user")
    p.add_argument("--min_pos_interactions", type=int, default=3,
                   help="Users with fewer positive interactions won't get SVD recs (skip)")

    # optional policy filters
    p.add_argument("--apply_policy_filters", action="store_true", help="Apply seolleyeon gating filters offline")
    p.add_argument("--profile_index_collection", type=str, default="profileIndex")
    p.add_argument("--manner_min", type=float, default=33.0)
    p.add_argument("--active_within_days", type=int, default=14)
    p.add_argument("--require_same_university", action="store_true", default=True)
    p.add_argument("--no_reciprocal", action="store_true", help="Disable reciprocal preference filter")

    # export
    p.add_argument("--export_firestore", action="store_true", default=True)
    p.add_argument("--algorithm_version", type=str, default=None, help="Override algorithm version string")

    # debug: 특정 유저의 필터 전 SVD 순위 (stdout + 선택적 JSON 파일)
    p.add_argument(
        "--dump_raw_user",
        type=str,
        default=None,
        metavar="USER_ID",
        help="해당 userId에 대해 recommend_for_user 직후 순위를 출력 (동성/AI/정책 필터 전)",
    )
    p.add_argument("--dump_raw_topk", type=int, default=40, help="--dump_raw_user 시 상위 몇 줄까지 출력")
    p.add_argument(
        "--dump_raw_out",
        type=str,
        default=None,
        metavar="PATH",
        help="--dump_raw_user 결과를 이 경로에 JSON으로도 저장",
    )

    args = p.parse_args()

    if args.event_weights_json:
        event_weights = json.loads(args.event_weights_json)
    else:
        event_weights = dict(DEFAULT_EVENT_WEIGHTS)

    negative_events = set(DEFAULT_NEGATIVE_EVENTS)

    # ---- Load events ----
    if args.events_csv:
        df = load_events_from_csv(args.events_csv)
        # CSV 비어있으면 Firestore fallback (export 미실행/빈 파일 대비)
        if df.empty and args.firestore_project:
            print("[data] CSV empty, falling back to Firestore recEvents...")
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
    elif args.firestore_events:
        if not args.firestore_project:
            raise ValueError("--firestore_project is required for --firestore_events")

        # use lookback window ending at date_key end
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
        raise ValueError(
            "No events loaded. Run export first: python -m recsys.main --step export "
            "--project seolleyeon --bucket seolleyeon-recs"
        )

    # ---- Build matrix ----
    user_item, user2idx, idx2item, nope_by_useridx = build_interaction_matrix(
        df,
        event_weights=event_weights,
        negative_events=negative_events,
        time_decay_half_life_days=float(args.half_life_days),
        max_weight_per_pair=float(args.max_weight_per_pair),
    )

    n_users, n_items = user_item.shape
    print(f"[data] users={n_users}, items={n_items}, nnz={user_item.nnz}")

    # ---- Train model ----
    cfg = TrainConfig(
        algo=args.algo,
        factors=args.factors,
        iterations=args.iterations,
        regularization=args.regularization,
        alpha=args.alpha,
        random_state=args.random_state,
    )
    model = SVDRecommender(cfg)
    model.fit(user_item)
    trained_at = datetime.now(tz=timezone.utc).isoformat()

    # ---- Optional metadata for policy filters ----
    meta = None
    if args.apply_policy_filters:
        if not args.firestore_project:
            raise ValueError("--firestore_project is required for --apply_policy_filters (to load profileIndex)")
        meta = load_profile_index_from_firestore(
            args.firestore_project,
            collection=args.profile_index_collection,
            database=args.firestore_database,
        )
        print(f"[meta] loaded profileIndex docs: {len(meta)}")

    # ---- users/onboarding gender (동성 제외용) ----
    gender_by_uid: Dict[str, str] = {}
    if args.firestore_project:
        gender_by_uid = load_user_genders_from_firestore(
            args.firestore_project,
            users_collection="users",
            database=args.firestore_database,
        )
        print(f"[gender] loaded from users/onboarding: {len(gender_by_uid)} users")

    # ---- Count positive interactions per user ----
    pos_counts = np.diff(user_item.indptr)  # nnz per user row (positive only after aggregation)
    active_user_indices = np.where(pos_counts >= int(args.min_pos_interactions))[0].tolist()
    print(f"[train] eligible users (>= {args.min_pos_interactions} pos pairs): {len(active_user_indices)}")

    # Reverse map: idx -> user_id
    idx2user = [None] * len(user2idx)
    for uid, i in user2idx.items():
        idx2user[i] = uid

    # item_id -> item_idx 사전 (O(1) 룩업용, list.index() 대체)
    item2idx_map = {it: j for j, it in enumerate(idx2item)}
    ai_item_idx_set = ai_profile_item_indices(idx2item)

    dump_raw_user_svd_preview(
        args,
        user_item=user_item,
        model=model,
        user2idx=user2idx,
        idx2item=idx2item,
        nope_by_useridx=nope_by_useridx,
        item2idx_map=item2idx_map,
        gender_by_uid=gender_by_uid,
        meta=meta,
        pos_counts=pos_counts,
    )

    # ---- Generate recs ----
    algorithm_version = args.algorithm_version or f"svd_{cfg.algo}_f{cfg.factors}_i{cfg.iterations}_{args.date_key}"

    recs_to_export: Dict[str, List[Dict[str, Any]]] = {}
    topn = int(args.topn)

    reciprocal = not args.no_reciprocal

    for ui in tqdm(active_user_indices, desc="generating"):
        u = idx2user[ui]
        if u is None:
            continue

        # base filter: nope + 본인 + AI 더미 컬럼(학습엔 쓰이나 추천 순위에서는 제외 — 0점으로 상단 독점 방지)
        filter_items = set(nope_by_useridx.get(ui, set())) | ai_item_idx_set
        self_item_idx = item2idx_map.get(u)
        if self_item_idx is not None:
            filter_items.add(self_item_idx)

        # Recommend oversampled, then policy-filter down to topn
        item_idx, scores = model.recommend_for_user(
            ui,
            user_item,
            topn=topn * 5,               # oversample for post-filtering
            filter_items=list(filter_items),
            oversample=1,                # already oversampling via topn*5
            filter_already_interacted=True,
        )

        items_out: List[Dict[str, Any]] = []
        rank = 1

        for ii, sc in zip(item_idx.tolist(), scores.tolist()):
            cand_uid = idx2item[ii]

            # ai_preference 타겟(female_123, male_456)은 추천 제외 — 학습에는 포함됨
            if is_ai_profile(cand_uid):
                continue

            # 동성 제외: users/onboarding.gender 기준
            u_g = gender_by_uid.get(u)
            v_g = gender_by_uid.get(cand_uid)
            if u_g and v_g and u_g == v_g:
                continue

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

        if len(items_out) == 0:
            continue

        recs_to_export[u] = items_out

    print(f"[export] prepared recs for users: {len(recs_to_export)}")

    # ---- Export ----
    if args.export_firestore:
        if not args.firestore_project:
            raise ValueError("--firestore_project is required for export")
        model_meta = {
            "algo": cfg.algo,
            "factors": cfg.factors,
            "iterations": cfg.iterations,
            "regularization": cfg.regularization,
            "alpha": cfg.alpha,
            "trainedAt": trained_at,
            "eventWeights": event_weights,
            "halfLifeDays": args.half_life_days,
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

    # Also print a tiny sample
    sample_users = list(recs_to_export.keys())[:3]
    for su in sample_users:
        print(f"\n[sample] {su}")
        print(json.dumps(recs_to_export[su][:5], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()