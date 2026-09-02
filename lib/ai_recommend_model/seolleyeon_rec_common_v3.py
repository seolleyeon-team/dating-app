#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

import numpy as np
import pandas as pd
from scipy import sparse
from avatar_media_privacy import (
   PRIVATE_SOURCE_PHOTO_BUCKET,
    PRIVATE_SOURCE_PHOTO_BUCKETS,
    CHAT_PROFILE_PHOTO_BUCKETS,
   _is_private_or_signed_image_ref,
    extract_display_avatar_url,
    filter_recommendation_items_for_display_ready,
    load_avatar_display_status_from_docs,
    load_users_with_private_source_photos_from_docs,
    sanitize_public_recommendation_item,
    validate_public_recommendation_item,
)
# 생활권 정책은 의존성 없는 순수 모듈에 있다. 1:1 / 3:3 블라인드 /
# 3:3 시즌이 모두 같은 semantics를 공유하도록 여기서 재수출한다.
from campus_life_zone_policy import (  # noqa: F401
    ACTIVATION_ENFORCED,
    ACTIVATION_OFF,
    ACTIVATION_UNKNOWN,
    CAMPUS_LIFE_ZONE_FIELD,
    CANONICAL_CAMPUS_LIFE_ZONES,
    CampusLifeZoneActivationUnknown,
    campus_life_zone_activation_from_config,
    campus_life_zone_rejection,
    campus_zone_compatibility,
    has_compatible_campus_life_zone,
    load_campus_life_zone_activation_with_version,
    normalize_campus_life_zones,
    read_campus_life_zones_from_user_doc,
    read_persisted_campus_life_zones,
    shared_campus_life_zones,
)
from seolleyeon_policy_state import policy_state_from_user_doc

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
# `nope` is a one-directional taste signal. Block/report are safety events and
# are expanded symmetrically before any candidate export.
DEFAULT_HARD_BLOCK_EVENTS = {"block", "report"}
DEFAULT_STRONG_POSITIVE_EVENTS = {"like", "match_created", "chat_first_message"}
DEFAULT_FIRESTORE_LAYOUT = "auto"  # auto | top_level | user_subcollections
DEFAULT_NEGATIVE_PREF_WEIGHTS: Dict[str, float] = {
    "nope": 1.0,
    "block": 1.5,
    "report": 2.0,
}

_AI_PROFILE_ID_RE = re.compile(r"(?P<gender>female|male)_(?P<number>\d+)")
_AI_PROFILE_SHOT_ID_RE = re.compile(
    r"(?P<identity>(?:female|male)_\d+)_(?:face_card|vibe_card|silhouette_card)"
)


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


def coerce_str_list(value: Any) -> List[str]:
    """Return a stable, de-duplicated list for optional string-list fields."""
    if not isinstance(value, list):
        return []
    out: List[str] = []
    seen: Set[str] = set()
    for item in value:
        text = str(item).strip() if item is not None else ""
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def redact_private_image_ref(value: Any) -> Any:
    """Compatibility redaction for worker logs and non-public job metadata."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not _is_private_or_signed_image_ref(text):
        return value
    if text.startswith(("gs://", "gcs://")):
        return "gs://[redacted-private-image]"
    return "[redacted-private-image-url]"


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


def parse_ai_profile_identity(item_id: str) -> Tuple[str, str]:
    """Parse one canonical AI identity ID while preserving numeric padding.

    AI identities are deliberately stricter than a ``female_``/``male_``
    prefix check.  A shot-level target is historical input that must be
    canonicalized before pair construction, never treated as a new identity.
    """
    if not isinstance(item_id, str):
        raise ValueError(f"Invalid AI profile identity: {item_id!r}")
    match = _AI_PROFILE_ID_RE.fullmatch(item_id.strip())
    if match is None:
        raise ValueError(f"Invalid AI profile identity: {item_id!r}")
    return match.group("gender"), match.group("number")


def canonicalize_ai_profile_id(item_id: str) -> str:
    """Return the canonical identity ID without changing zero padding."""
    gender, number = parse_ai_profile_identity(item_id)
    return f"{gender}_{number}"


def canonicalize_recommendation_target_id(item_id: str) -> str:
    """Collapse legacy evidence-shot targets onto their identity target.

    New recEvents use the identity ID directly.  This compatibility boundary
    keeps old ``*_face_card``/``*_vibe_card``/``*_silhouette_card`` events from
    becoming three independent interactions during model training.
    """
    if not isinstance(item_id, str):
        return str(item_id)
    value = item_id.strip()
    shot_match = _AI_PROFILE_SHOT_ID_RE.fullmatch(value)
    if shot_match is not None:
        return shot_match.group("identity")
    return value


def is_ai_profile(item_id: str) -> bool:
    """Whether ``item_id`` is one canonical AI identity (not a shot ID)."""
    if not isinstance(item_id, str):
        return False
    try:
        parse_ai_profile_identity(item_id)
    except ValueError:
        return False
    return True


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


def load_user_documents_from_firestore(
    project_id: str,
    *,
    users_collection: str = "users",
    database: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Load raw user documents for the shared policy/media adapter."""
    require_firestore()
    db = firestore.Client(project=project_id, database=database)
    return {
        doc.id: (doc.to_dict() or {})
        for doc in db.collection(users_collection).stream()
    }


def approved_avatar_urls_from_user_docs(
    users: Dict[str, Dict[str, Any]],
) -> Dict[str, List[str]]:
    """Return only approved HTTPS avatars from an in-memory users snapshot."""
    result: Dict[str, List[str]] = {}
    for uid, doc in users.items():
        if not isinstance(doc, dict):
            continue
        approved = extract_display_avatar_url(doc)
        if approved:
            result[str(uid)] = [approved]
    return result


def load_users_with_approved_avatars_from_firestore(
    project_id: str,
    *,
    users_collection: str = "users",
    database: Optional[str] = None,
) -> Dict[str, List[str]]:
    """Load only canonical, approved public avatar URLs for candidates.

    `onboarding.photoUrls` and `onboarding.avatarUrls` are historical/source
    fields. They are intentionally not treated as display-ready recommendation
    media. AI profile URLs are added by CLIP only to its private preference
    embedding map, never to this candidate map.
    """
    docs = load_user_documents_from_firestore(
        project_id,
        users_collection=users_collection,
        database=database,
    )
    return approved_avatar_urls_from_user_docs(docs)


def load_avatar_display_status_from_firestore(
    project_id: str,
    *,
    users_collection: str = "users",
    database: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Load display-readiness metadata using the canonical avatar helper."""
    docs = load_user_documents_from_firestore(
        project_id,
        users_collection=users_collection,
        database=database,
    )
    return load_avatar_display_status_from_docs(docs)


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
        # 완성 여부는 users 경로와 같은 규칙으로 읽는다.
        # 여기서만 `isProfileComplete` 를 직접 보면, 앱이 실제로 쓰는
        # `initialSetupComplete` 만 가진 사용자가 index 경로에서는 미완성으로
        # 판정된다 (같은 사용자가 경로에 따라 다르게 취급된다).
        completion = profile_completion_provenance(d)
        meta[doc.id] = {
            "universityId": d.get("universityId"),
            # 학과 회피 여부는 private users 문서에서 다시 보강한다.
            "department": normalize_department(d.get("department")),
            "avoidSameDepartment": False,
            "isVerified": bool(d.get("isVerified", False)),
            "isActive": bool(d.get("isActive", False)),
            "isProfileComplete": completion["value"] is True,
            "profileCompleteSource": completion["source"],
            "profileCompleteReason": completion["reason"],
            "gender": d.get("gender"),
            "birthYear": d.get("birthYear"),
            "prefGender": d.get("prefGender", []) or [],
            "prefAgeMin": d.get("prefAgeMin"),
            "prefAgeMax": d.get("prefAgeMax"),
            "mannerScore": safe_float(d.get("mannerScore", 36.5), 36.5),
            "lastActiveAt": parse_firestore_like_ts(d.get("lastActiveAt")),
            # 생활권은 users 원본에서 파생된 값이다. index가 아직 이 필드를
            # 전파하지 않으면 빈 값이 되고, 그 사용자는 fail-closed로 제외된다.
            "campusLifeZones": sorted(
                normalize_campus_life_zones(d.get(CAMPUS_LIFE_ZONE_FIELD))
            ),
        }
    return meta


def normalize_department(value: Any) -> Optional[str]:
    """Read a non-empty department without guessing missing values."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if text else None


def department_from_user_doc(doc: Mapping[str, Any]) -> Optional[str]:
    onboarding = doc.get("onboarding")
    onboarding_map = onboarding if isinstance(onboarding, Mapping) else {}
    return normalize_department(onboarding_map.get("department")) or normalize_department(
        doc.get("department")
    )


def avoid_same_department_from_user_doc(doc: Mapping[str, Any]) -> bool:
    privacy_settings = doc.get("privacySettings")
    if not isinstance(privacy_settings, Mapping):
        return False
    return privacy_settings.get("avoidSameDepartment") is True


def same_department_avoidance_rejection(
    viewer_meta: Mapping[str, Any] | None,
    candidate_meta: Mapping[str, Any] | None,
) -> bool:
    """Return true when either side opted out of same-department matches."""
    if not isinstance(viewer_meta, Mapping) or not isinstance(candidate_meta, Mapping):
        return False
    viewer_department = normalize_department(viewer_meta.get("department"))
    candidate_department = normalize_department(candidate_meta.get("department"))
    if not viewer_department or viewer_department != candidate_department:
        return False
    return bool(
        viewer_meta.get("avoidSameDepartment") is True
        or candidate_meta.get("avoidSameDepartment") is True
    )


def filter_same_department_items(
    viewer_uid: str,
    items: Sequence[Mapping[str, Any]],
    policy_meta: Mapping[str, Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Remove opted-out same-department candidates and compact their ranks."""
    viewer_meta = policy_meta.get(viewer_uid)
    filtered: List[Dict[str, Any]] = []
    for item in items:
        candidate_uid = str(item.get("uid") or "").strip()
        if not candidate_uid:
            continue
        candidate_meta = policy_meta.get(candidate_uid)
        if same_department_avoidance_rejection(viewer_meta, candidate_meta):
            continue
        payload = dict(item)
        payload["uid"] = candidate_uid
        payload["rank"] = len(filtered) + 1
        filtered.append(payload)
    return filtered


def university_id_from_student_email(email: Any) -> Optional[str]:
    """Derive a university key without inventing one for malformed mail."""
    text = str(email or "").strip().lower()
    if "@" not in text:
        return None
    labels = [label for label in text.rsplit("@", 1)[1].split(".") if label]
    if len(labels) < 2:
        return None
    if labels[-2:] == ["ac", "kr"]:
        return labels[-3] if len(labels) >= 3 else None
    return labels[-2]


def build_policy_meta_from_user_docs(
    users: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Derive the shared policy shape from raw ``users`` documents.

    Verified is false when its source field is absent. Completion follows the
    app's explicit ``isProfileComplete`` -> ``initialSetupComplete`` contract;
    an absent completion field remains conservative. Account availability is
    separate from recency, and login activity fields are normalized before the
    active-within-days policy is applied.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for uid, doc in users.items():
        if not isinstance(doc, dict):
            continue
        onboarding = doc.get("onboarding") if isinstance(doc.get("onboarding"), dict) else {}
        ideal_type = doc.get("idealType") if isinstance(doc.get("idealType"), dict) else {}
        ideal_age = (
            ideal_type.get("idealAge")
            if isinstance(ideal_type.get("idealAge"), dict)
            else {}
        )
        policy_state = policy_state_from_user_doc(doc)

        birth_year = onboarding.get("birthYear", doc.get("birthYear"))
        birth_year_int = safe_int(birth_year, 0) or None
        gender = onboarding.get("gender", doc.get("gender"))
        gender_text = str(gender).strip().lower() if gender is not None else None

        university_id = None
        for candidate in (
            onboarding.get("universityId"),
            doc.get("universityId"),
            university_id_from_student_email(doc.get("studentEmail")),
        ):
            text = str(candidate).strip() if candidate is not None else ""
            if text:
                university_id = text
                break

        out[str(uid)] = {
            "universityId": university_id,
            "department": department_from_user_doc(doc),
            "avoidSameDepartment": avoid_same_department_from_user_doc(doc),
            "isVerified": bool(doc.get("isStudentVerified", doc.get("isVerified", False))),
            "isActive": policy_state["isActive"],
            "isProfileComplete": policy_state["isProfileComplete"],
            "activeSource": policy_state["activeSource"],
            "activeReason": policy_state["activeReason"],
            "profileCompleteSource": policy_state["profileCompleteSource"],
            "profileCompleteReason": policy_state["profileCompleteReason"],
            "gender": gender_text,
            "birthYear": birth_year_int,
            "prefGender": coerce_str_list(ideal_type.get("preferredGenders")),
            "prefAgeMin": safe_int(
                ideal_age.get("min", ideal_type.get("minAge")), 0
            ) or None,
            "prefAgeMax": safe_int(
                ideal_age.get("max", ideal_type.get("maxAge")), 0
            ) or None,
            "mannerScore": safe_float(doc.get("mannerScore", 36.5), 36.5),
            "lastActiveAt": parse_firestore_like_ts(policy_state["lastActiveAt"]),
            "activitySource": policy_state["activitySource"],
            "activityReason": policy_state["activityReason"],
            # users/{uid}.onboarding.campusLifeZones 가 canonical 위치다.
            "campusLifeZones": sorted(read_campus_life_zones_from_user_doc(doc)),
        }
    return out


def load_policy_meta_from_firestore(
    project_id: str,
    *,
    profile_index_collection: str = "profileIndex",
    users_collection: str = "users",
    database: Optional[str] = None,
) -> Tuple[Dict[str, Dict[str, Any]], str]:
    """Load profileIndex first, enriching private preference fields from users."""
    meta = load_profile_index_from_firestore(
        project_id,
        collection=profile_index_collection,
        database=database,
    )
    if meta:
        # profileIndex is optimized for ranking and intentionally does not
        # carry private privacySettings. The raw users snapshot is authoritative
        # for the department and the opt-in flag used by this hard filter.
        user_docs = load_user_documents_from_firestore(
            project_id,
            users_collection=users_collection,
            database=database,
        )
        user_meta = build_policy_meta_from_user_docs(user_docs)
        for uid, indexed_meta in meta.items():
            private_meta = user_meta.get(uid)
            indexed_meta["department"] = (
                private_meta.get("department") if private_meta else None
            )
            indexed_meta["avoidSameDepartment"] = bool(
                private_meta and private_meta.get("avoidSameDepartment") is True
            )
        return meta, profile_index_collection

    docs = load_user_documents_from_firestore(
        project_id,
        users_collection=users_collection,
        database=database,
    )
    return build_policy_meta_from_user_docs(docs), users_collection


def load_campus_life_zone_activation_for_project(
    project_id: str,
    *,
    database: Optional[str] = None,
) -> Tuple[str, int]:
    """모델 export 스크립트용 activation 조회.

    조회에 실패하면 [CampusLifeZoneActivationUnknown] 이 올라온다. 배치는
    상태를 모른 채 추천을 새로 쓰지 않는다 — 한 번 실패하는 편이,
    활성화된 정책을 모른 채 cross-zone 후보를 저장하는 것보다 안전하다.
    """
    require_firestore()
    db = firestore.Client(project=project_id, database=database)
    return load_campus_life_zone_activation_with_version(db)


def resolve_campus_life_zone_activation(
    override: Optional[bool],
    project_id: str,
    *,
    database: Optional[str] = None,
) -> Tuple[str, int]:
    """CLI 오버라이드가 있으면 그것을, 없으면 config 문서를 따른다.

    오버라이드는 운영자가 명시적으로 지정한 상태이므로 조회하지 않는다.
    조회가 필요한데 실패하면 예외가 그대로 올라가 배치가 중단된다.
    """
    if override is not None:
        return (ACTIVATION_ENFORCED if override else ACTIVATION_OFF), 0
    return load_campus_life_zone_activation_for_project(
        project_id, database=database
    )


def campus_life_zone_policy_provenance(state: str, version: int) -> Dict[str, Any]:
    """추천 문서에 남길 정책 provenance.

    이 문서가 어떤 정책 상태에서 만들어졌는지 소비자(클라이언트/검증)가
    알 수 있어야 한다. config 를 읽지 못하는 순간에도 문서 자체가 근거가 된다.
    """
    return {
        "campusLifeZone": state,
        "campusLifeZonePolicyVersion": int(version),
    }


def assert_policy_meta_coverage(
    meta: Dict[str, Dict[str, Any]],
    required_uids: Sequence[str],
    *,
    min_coverage: float,
    source: str,
) -> float:
    """Fail loudly when policy metadata is too sparse to filter safely."""
    unique_uids = {str(uid) for uid in required_uids}
    if not unique_uids:
        return 1.0
    covered = sum(1 for uid in unique_uids if uid in meta)
    coverage = covered / len(unique_uids)
    if coverage < min_coverage:
        raise ValueError(
            f"Policy metadata from '{source}' covers only {covered}/{len(unique_uids)} "
            f"users ({coverage:.1%} < {min_coverage:.1%}). Refusing to export a "
            "silently empty or unfiltered feed."
        )
    return coverage


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
    require_same_campus_life_zone: bool = True,
) -> bool:
    mu = meta.get(user_id)
    mv = meta.get(cand_id)
    if mu is None or mv is None:
        return False

    # Department avoidance is a bilateral hard exclusion: a preference on
    # either side removes the pair in both recommendation directions.
    if same_department_avoidance_rejection(mu, mv):
        return False

    # 생활권은 점수가 아니라 eligibility다. 값이 없으면 fail-closed.
    if require_same_campus_life_zone and campus_life_zone_rejection(mu, mv):
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
    out["item_id"] = out["item_id"].astype(str).map(
        canonicalize_recommendation_target_id
    )
    out["event"] = out["event"].astype(str)
    if "ts" not in out.columns:
        out["ts"] = pd.NaT
    out["ts"] = out["ts"].apply(parse_firestore_like_ts)
    if "_row_order" not in out.columns:
        out["_row_order"] = np.arange(len(out), dtype=np.int64)
    return out[["user_id", "item_id", "event", "ts", "_row_order"]]


def block_edges_from_owner_targets(
    owner_targets: Dict[str, Sequence[str]],
) -> List[Tuple[str, str]]:
    """Normalize ``blocks/{owner}/targets/{target}`` data into directed edges."""
    edges: List[Tuple[str, str]] = []
    for owner, targets in (owner_targets or {}).items():
        owner_uid = str(owner or "").strip()
        if not owner_uid or not isinstance(targets, Sequence) or isinstance(targets, (str, bytes)):
            continue
        for target in targets:
            target_uid = str(target or "").strip()
            if target_uid and target_uid != owner_uid:
                edges.append((owner_uid, target_uid))
    return edges


def extend_mutual_block_index(
    base: Dict[str, Set[str]],
    firestore_block_edges: Sequence[Tuple[str, str]],
) -> Dict[str, Set[str]]:
    """Merge directed Firestore block edges into a symmetric index."""
    result: Dict[str, Set[str]] = {
        str(owner): set(targets)
        for owner, targets in (base or {}).items()
    }
    for owner, target in firestore_block_edges or []:
        owner_uid = str(owner or "").strip()
        target_uid = str(target or "").strip()
        if not owner_uid or not target_uid or owner_uid == target_uid:
            continue
        result.setdefault(owner_uid, set()).add(target_uid)
        result.setdefault(target_uid, set()).add(owner_uid)
    return result


def resolve_mutual_block_index(
    df: pd.DataFrame,
    *,
    firestore_block_edges: Optional[Sequence[Tuple[str, str]]] = None,
    block_events: Optional[Sequence[str]] = None,
) -> Dict[str, Set[str]]:
    """Combine recEvents block/report signals with active Firestore blocks."""
    return extend_mutual_block_index(
        build_mutual_block_index(df, block_events=block_events),
        firestore_block_edges or [],
    )


def load_firestore_block_edges_from_firestore(
    project_id: str,
    *,
    blocks_collection: str = "blocks",
    database: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """Read active ``blocks/{owner}/targets`` edges from Firestore."""
    require_firestore()
    db = firestore.Client(project=project_id, database=database)
    owner_targets: Dict[str, List[str]] = {}
    for owner_ref in db.collection(blocks_collection).list_documents():
        owner_targets[owner_ref.id] = [
            target_ref.id
            for target_ref in owner_ref.collection("targets").list_documents()
        ]
    return block_edges_from_owner_targets(owner_targets)


def build_mutual_block_index(
    df: pd.DataFrame,
    *,
    block_events: Optional[Sequence[str]] = None,
) -> Dict[str, Set[str]]:
    """Map each uid to users hidden by block/report safety events."""
    events = set(block_events) if block_events is not None else set(DEFAULT_HARD_BLOCK_EVENTS)
    index: Dict[str, Set[str]] = defaultdict(set)
    if df is None or len(df) == 0 or not events:
        return {}

    normalized = normalize_events_df(df)
    hard = normalized[normalized["event"].isin(events)]
    for actor, target in zip(hard["user_id"], hard["item_id"]):
        actor_uid = str(actor).strip()
        target_uid = str(target).strip()
        if not actor_uid or not target_uid or actor_uid == target_uid:
            continue
        index[actor_uid].add(target_uid)
        index[target_uid].add(actor_uid)
    return dict(index)


class NoUsableTrainingEvents(ValueError):
    """협업필터 학습에 쓸 상호작용이 남지 않았다.

    어느 필터에서 비었는지 알 수 있게 단계별 건수를 함께 들고 다닌다.
    "이벤트가 아예 없다" 와 "전부 AI 취향 카드였다" 는 운영상 완전히 다른
    상황인데, 메시지만으로는 구분되지 않아 매번 원본 데이터를 다시 뒤져야 했다.

    개인 식별 정보는 담지 않는다 (건수와 이벤트 종류만).
    """

    def __init__(self, stages: Dict[str, int], event_counts: Dict[str, int]):
        self.stages = dict(stages)
        self.event_counts = dict(event_counts)
        detail = ", ".join(f"{k}={v}" for k, v in stages.items())
        seen = ", ".join(f"{k}={v}" for k, v in sorted(event_counts.items()))
        super().__init__(
            "No usable events after filtering known events / AI profiles. "
            f"stages: {detail}. events seen: {seen or '(none)'}"
        )


def collapse_pair_events(
    df: pd.DataFrame,
    cfg: PairBuildConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = normalize_events_df(df)
    stages = {"normalized": int(len(df))}
    event_counts = {
        str(name): int(count) for name, count in df["event"].value_counts().items()
    } if len(df) else {}

    known_events = set(cfg.event_weights.keys()) | set(cfg.negative_events)
    df = df[df["event"].isin(known_events)].copy()
    stages["known_event"] = int(len(df))

    if cfg.exclude_ai_items_from_training:
        df = df[~df["item_id"].apply(is_ai_profile)].copy()
        stages["non_ai_item"] = int(len(df))

    if df.empty:
        raise NoUsableTrainingEvents(stages, event_counts)

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
