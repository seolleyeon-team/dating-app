#!/usr/bin/env python3
"""Common helpers for the Seolleyeon 3:3 meeting recommender v1."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from itertools import permutations
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd

try:
    from google.cloud import firestore
    from google.cloud.firestore_v1.base_query import FieldFilter
except Exception:  # pragma: no cover
    firestore = None
    FieldFilter = None

from seolleyeon_clip_embedder import SeolleyeonCLIPEmbedder
from seolleyeon_rec_common_v3 import parse_firestore_like_ts


KST = timezone(timedelta(hours=9))
UTC = timezone.utc

DEFAULT_MEETING_GROUPS_COLLECTION = "meetingGroups"
DEFAULT_MEETING_GROUP_INDEX_COLLECTION = "meetingGroupIndex"
DEFAULT_MEETING_MODEL_RECS_COLLECTION = "meetingModelRecs"
DEFAULT_MEETING_DAILY_RECS_COLLECTION = "meetingDailyRecs"
DEFAULT_PROFILE_INDEX_COLLECTION = "profileIndex"
DEFAULT_USERS_COLLECTION = "users"
DEFAULT_REC_EVENTS_COLLECTION = "recEvents"
DEFAULT_MODEL_RECS_COLLECTION = "modelRecs"

DEFAULT_MEETING_POSITIVE_EVENTS = {
    "like",
    "match_created",
    "chat_first_message",
    "meeting_confirmed",
    "post_meeting_positive",
}
DEFAULT_MEETING_NEGATIVE_EVENTS = {"nope", "block", "report"}
DEFAULT_MEETING_EXPOSURE_EVENTS = {"impression", "open", "detail_open"}


def require_firestore() -> None:
    """Raise a friendly error when Firestore libraries are unavailable."""
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is not installed.")


def log_struct(level: str, event: str, **kwargs: Any) -> None:
    """Emit structured JSON logs for Cloud Run friendly observability."""
    payload = {
        "ts": datetime.now(tz=UTC).isoformat(),
        "level": str(level).lower(),
        "event": event,
    }
    payload.update(_json_safe_mapping(kwargs))
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _json_safe_mapping(data: Mapping[str, Any]) -> Dict[str, Any]:
    return {str(k): _json_safe_value(v) for k, v in data.items()}


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.to_pydatetime().astimezone(UTC).isoformat()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(v) for v in value]
    if isinstance(value, Mapping):
        return _json_safe_mapping(value)
    if hasattr(value, "__dict__"):
        return _json_safe_mapping(value.__dict__)
    return str(value)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def clamp01(value: float) -> float:
    return clamp(float(value), 0.0, 1.0)


def normalize_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def normalize_gender(value: Any) -> Optional[str]:
    s = normalize_optional_str(value)
    if s is None:
        return None
    return s.lower()


def normalize_pref_gender_list(values: Any) -> List[str]:
    out: List[str] = []
    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
        for value in values:
            gender = normalize_gender(value)
            if gender in {"all", "any", "both"}:
                continue
            if gender:
                out.append(gender)
    return _dedupe_preserve_order(out)


def coerce_str_list(values: Any) -> List[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    out: List[str] = []
    for value in values:
        normalized = normalize_optional_str(value)
        if normalized:
            out.append(normalized)
    return _dedupe_preserve_order(out)


def _dedupe_preserve_order(values: Sequence[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def parse_date_key(date_key: str) -> str:
    if len(date_key) != 8 or not str(date_key).isdigit():
        raise ValueError("date_key must be YYYYMMDD")
    return date_key


def date_key_to_date(date_key: str) -> date:
    date_key = parse_date_key(date_key)
    return date(int(date_key[0:4]), int(date_key[4:6]), int(date_key[6:8]))


def make_date_key(value: date) -> str:
    return value.strftime("%Y%m%d")


def list_recent_date_keys(date_key: str, lookback_days: int) -> List[str]:
    if lookback_days <= 0:
        return []
    base = date_key_to_date(date_key)
    return [
        make_date_key(base - timedelta(days=offset))
        for offset in range(int(lookback_days))
    ]


def pd_ts_to_datetime(value: Any) -> Optional[datetime]:
    ts = parse_firestore_like_ts(value)
    if not isinstance(ts, pd.Timestamp) or pd.isna(ts):
        return None
    return ts.to_pydatetime().astimezone(UTC)


def days_since(value: Optional[datetime], *, now: Optional[datetime] = None) -> Optional[float]:
    if value is None:
        return None
    ref = now or datetime.now(tz=UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return max(0.0, (ref - value.astimezone(UTC)).total_seconds() / 86400.0)


def iter_chunks(values: Sequence[str], chunk_size: int) -> Iterator[List[str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    for idx in range(0, len(values), chunk_size):
        yield list(values[idx : idx + chunk_size])


def make_firestore_client(project_id: str, database: Optional[str] = None):
    require_firestore()
    return firestore.Client(project=project_id, database=database)


def stream_collection_documents(db, collection_name: str) -> Dict[str, Dict[str, Any]]:
    docs: Dict[str, Dict[str, Any]] = {}
    for snap in db.collection(collection_name).stream():
        docs[snap.id] = snap.to_dict() or {}
    return docs


def load_documents_by_ids(
    db,
    collection_name: str,
    doc_ids: Sequence[str],
    *,
    batch_size: int = 200,
) -> Dict[str, Dict[str, Any]]:
    docs: Dict[str, Dict[str, Any]] = {}
    unique_ids = _dedupe_preserve_order([doc_id for doc_id in doc_ids if doc_id])
    if not unique_ids:
        return docs
    for batch in iter_chunks(unique_ids, batch_size):
        refs = [db.collection(collection_name).document(doc_id) for doc_id in batch]
        for snap in db.get_all(refs):
            if snap.exists:
                docs[snap.id] = snap.to_dict() or {}
    return docs


def _first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _coerce_birth_year(*values: Any) -> Optional[int]:
    for value in values:
        if value is None:
            continue
        parsed = safe_int(value, default=-1)
        if 1900 <= parsed <= 2100:
            return parsed
    return None


def _coerce_age_bound(value: Any) -> Optional[int]:
    parsed = safe_int(value, default=-1)
    return parsed if parsed > 0 else None


def _extract_photo_urls(user_doc: Mapping[str, Any]) -> List[str]:
    onboarding = user_doc.get("onboarding")
    if isinstance(onboarding, Mapping):
        urls = coerce_str_list(onboarding.get("photoUrls"))
        if urls:
            return urls
    return coerce_str_list(user_doc.get("photoUrls"))


def _extract_tags(
    profile_doc: Mapping[str, Any],
    user_doc: Mapping[str, Any],
    *,
    primary_keys: Sequence[str],
    onboarding_keys: Sequence[str],
    user_keys: Sequence[str],
) -> List[str]:
    for key in primary_keys:
        tags = coerce_str_list(profile_doc.get(key))
        if tags:
            return tags
    onboarding = user_doc.get("onboarding")
    if isinstance(onboarding, Mapping):
        for key in onboarding_keys:
            tags = coerce_str_list(onboarding.get(key))
            if tags:
                return tags
    for key in user_keys:
        tags = coerce_str_list(user_doc.get(key))
        if tags:
            return tags
    return []


@dataclass
class MemberProfileView:
    uid: str
    university_id: Optional[str]
    is_verified: bool
    is_active: bool
    is_profile_complete: bool
    gender: Optional[str]
    birth_year: Optional[int]
    pref_gender: List[str]
    pref_age_min: Optional[int]
    pref_age_max: Optional[int]
    manner_score: float
    last_active_at: Optional[datetime]
    interest_tag_ids: List[str]
    lifestyle_tag_ids: List[str]
    photo_urls: List[str]


def build_member_profile_view(
    uid: str,
    profile_doc: Optional[Mapping[str, Any]],
    user_doc: Optional[Mapping[str, Any]],
) -> MemberProfileView:
    profile_doc = profile_doc or {}
    user_doc = user_doc or {}
    onboarding = user_doc.get("onboarding")
    onboarding = onboarding if isinstance(onboarding, Mapping) else {}

    university_id = normalize_optional_str(
        _first_non_none(
            profile_doc.get("universityId"),
            onboarding.get("universityId"),
            user_doc.get("universityId"),
            onboarding.get("university"),
            user_doc.get("university"),
        )
    )
    is_verified = bool(
        _first_non_none(
            profile_doc.get("isVerified"),
            user_doc.get("isStudentVerified"),
            user_doc.get("isVerified"),
            False,
        )
    )
    is_active = bool(_first_non_none(profile_doc.get("isActive"), user_doc.get("isActive"), True))
    is_profile_complete = bool(
        _first_non_none(
            profile_doc.get("isProfileComplete"),
            user_doc.get("isProfileComplete"),
            True,
        )
    )
    gender = normalize_gender(
        _first_non_none(profile_doc.get("gender"), onboarding.get("gender"), user_doc.get("gender"))
    )
    birth_year = _coerce_birth_year(
        profile_doc.get("birthYear"),
        onboarding.get("birthYear"),
        user_doc.get("birthYear"),
    )
    pref_gender = normalize_pref_gender_list(
        _first_non_none(profile_doc.get("prefGender"), onboarding.get("prefGender"), user_doc.get("prefGender"), [])
    )
    pref_age_min = _coerce_age_bound(
        _first_non_none(profile_doc.get("prefAgeMin"), onboarding.get("prefAgeMin"), user_doc.get("prefAgeMin"))
    )
    pref_age_max = _coerce_age_bound(
        _first_non_none(profile_doc.get("prefAgeMax"), onboarding.get("prefAgeMax"), user_doc.get("prefAgeMax"))
    )
    manner_score = safe_float(
        _first_non_none(profile_doc.get("mannerScore"), user_doc.get("mannerScore"), 36.5),
        36.5,
    )
    last_active_at = pd_ts_to_datetime(
        _first_non_none(
            profile_doc.get("lastActiveAt"),
            user_doc.get("lastActiveAt"),
            user_doc.get("updatedAt"),
        )
    )
    interest_tag_ids = _extract_tags(
        profile_doc,
        user_doc,
        primary_keys=("interestTagIds",),
        onboarding_keys=("interestTagIds", "interests"),
        user_keys=("interestTagIds", "interests"),
    )
    lifestyle_tag_ids = _extract_tags(
        profile_doc,
        user_doc,
        primary_keys=("lifestyleTagIds",),
        onboarding_keys=("lifestyleTagIds", "keywords"),
        user_keys=("lifestyleTagIds", "keywords"),
    )
    photo_urls = _extract_photo_urls(user_doc)

    return MemberProfileView(
        uid=uid,
        university_id=university_id,
        is_verified=is_verified,
        is_active=is_active,
        is_profile_complete=is_profile_complete,
        gender=gender,
        birth_year=birth_year,
        pref_gender=pref_gender,
        pref_age_min=pref_age_min,
        pref_age_max=pref_age_max,
        manner_score=manner_score,
        last_active_at=last_active_at,
        interest_tag_ids=interest_tag_ids,
        lifestyle_tag_ids=lifestyle_tag_ids,
        photo_urls=photo_urls,
    )


@dataclass
class MeetingGroupIndexRecord:
    group_id: str
    captain_uid: Optional[str]
    member_uids: List[str]
    size: int
    status: Optional[str]
    region_id: Optional[str]
    availability_slot_ids: List[str]
    vibe_tag_ids: List[str]
    university_ids: List[str]
    primary_university_id: Optional[str]
    genders: List[str]
    birth_years: List[int]
    min_birth_year: Optional[int]
    max_birth_year: Optional[int]
    min_manner_score: float
    avg_manner_score: float
    all_verified: bool
    all_active: bool
    all_profile_complete: bool
    interest_tag_ids_union: List[str]
    lifestyle_tag_ids_union: List[str]
    last_active_at_min: Optional[datetime]
    last_active_at_max: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    expire_at: Optional[datetime]
    index_status: str
    skip_reason: Optional[str]
    skip_reasons: List[str]
    member_profile_missing_uids: List[str]

    def to_document(self) -> Dict[str, Any]:
        return {
            "captainUid": self.captain_uid,
            "memberUids": self.member_uids,
            "size": self.size,
            "status": self.status,
            "regionId": self.region_id,
            "availabilitySlotIds": self.availability_slot_ids,
            "vibeTagIds": self.vibe_tag_ids,
            "universityIds": self.university_ids,
            "primaryUniversityId": self.primary_university_id,
            "genders": self.genders,
            "birthYears": self.birth_years,
            "minBirthYear": self.min_birth_year,
            "maxBirthYear": self.max_birth_year,
            "minMannerScore": round(self.min_manner_score, 4),
            "avgMannerScore": round(self.avg_manner_score, 4),
            "allVerified": self.all_verified,
            "allActive": self.all_active,
            "allProfileComplete": self.all_profile_complete,
            "interestTagIdsUnion": self.interest_tag_ids_union,
            "lifestyleTagIdsUnion": self.lifestyle_tag_ids_union,
            "lastActiveAtMin": self.last_active_at_min,
            "lastActiveAtMax": self.last_active_at_max,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "expireAt": self.expire_at,
            "indexStatus": self.index_status,
            "skipReason": self.skip_reason,
            "skipReasons": self.skip_reasons,
            "memberProfileMissingUids": self.member_profile_missing_uids,
        }

    @classmethod
    def from_document(cls, group_id: str, data: Mapping[str, Any]) -> "MeetingGroupIndexRecord":
        return cls(
            group_id=group_id,
            captain_uid=normalize_optional_str(data.get("captainUid")),
            member_uids=coerce_str_list(data.get("memberUids")),
            size=safe_int(data.get("size"), 0),
            status=normalize_optional_str(data.get("status")),
            region_id=normalize_optional_str(data.get("regionId")),
            availability_slot_ids=coerce_str_list(data.get("availabilitySlotIds")),
            vibe_tag_ids=coerce_str_list(data.get("vibeTagIds")),
            university_ids=coerce_str_list(data.get("universityIds")),
            primary_university_id=normalize_optional_str(data.get("primaryUniversityId")),
            genders=coerce_str_list(data.get("genders")),
            birth_years=[year for year in [safe_int(v, -1) for v in data.get("birthYears", []) or []] if year > 0],
            min_birth_year=_coerce_birth_year(data.get("minBirthYear")),
            max_birth_year=_coerce_birth_year(data.get("maxBirthYear")),
            min_manner_score=safe_float(data.get("minMannerScore"), 0.0),
            avg_manner_score=safe_float(data.get("avgMannerScore"), 0.0),
            all_verified=bool(data.get("allVerified", False)),
            all_active=bool(data.get("allActive", False)),
            all_profile_complete=bool(data.get("allProfileComplete", False)),
            interest_tag_ids_union=coerce_str_list(data.get("interestTagIdsUnion")),
            lifestyle_tag_ids_union=coerce_str_list(data.get("lifestyleTagIdsUnion")),
            last_active_at_min=pd_ts_to_datetime(data.get("lastActiveAtMin")),
            last_active_at_max=pd_ts_to_datetime(data.get("lastActiveAtMax")),
            created_at=pd_ts_to_datetime(data.get("createdAt")),
            updated_at=pd_ts_to_datetime(data.get("updatedAt")),
            expire_at=pd_ts_to_datetime(data.get("expireAt")),
            index_status=normalize_optional_str(data.get("indexStatus")) or "unknown",
            skip_reason=normalize_optional_str(data.get("skipReason")),
            skip_reasons=coerce_str_list(data.get("skipReasons")),
            member_profile_missing_uids=coerce_str_list(data.get("memberProfileMissingUids")),
        )


def _pick_primary_university(universities: Sequence[str]) -> Optional[str]:
    universities = [value for value in universities if value]
    if not universities:
        return None
    counts = Counter(universities)
    best_count = max(counts.values())
    for value in universities:
        if counts[value] == best_count:
            return value
    return universities[0]


def build_group_index_record(
    group_id: str,
    raw_group: Mapping[str, Any],
    member_profiles: Mapping[str, Optional[MemberProfileView]],
    *,
    manner_min_threshold: float,
) -> MeetingGroupIndexRecord:
    member_uids = _dedupe_preserve_order(coerce_str_list(raw_group.get("memberUids")))
    member_views: List[MemberProfileView] = []
    missing_member_profile_uids: List[str] = []
    for uid in member_uids:
        member_view = member_profiles.get(uid)
        if member_view is None:
            missing_member_profile_uids.append(uid)
            continue
        member_views.append(member_view)

    status = normalize_optional_str(raw_group.get("status"))
    university_ids = _dedupe_preserve_order(
        [view.university_id for view in member_views if view.university_id]
    )
    genders = _dedupe_preserve_order(
        [view.gender for view in member_views if view.gender]
    )
    birth_years = [view.birth_year for view in member_views if view.birth_year is not None]
    manners = [view.manner_score for view in member_views]
    interest_tags = sorted(
        {
            tag
            for view in member_views
            for tag in view.interest_tag_ids
            if normalize_optional_str(tag)
        }
    )
    lifestyle_tags = sorted(
        {
            tag
            for view in member_views
            for tag in view.lifestyle_tag_ids
            if normalize_optional_str(tag)
        }
    )
    last_active_values = [view.last_active_at for view in member_views if view.last_active_at is not None]

    skip_reasons: List[str] = []
    if status != "open":
        skip_reasons.append("not_open")
    if len(member_uids) != 3:
        skip_reasons.append("group_size_not_3")
    if missing_member_profile_uids:
        skip_reasons.append("missing_member_profile")
    if member_views and not all(view.is_verified for view in member_views):
        skip_reasons.append("member_not_verified")
    if member_views and not all(view.is_active for view in member_views):
        skip_reasons.append("member_not_active")
    if member_views and not all(view.is_profile_complete for view in member_views):
        skip_reasons.append("member_profile_incomplete")
    if member_views and min(manners or [0.0]) < float(manner_min_threshold):
        skip_reasons.append("low_manner")

    index_status = "ready" if not skip_reasons else "skipped"
    skip_reason = skip_reasons[0] if skip_reasons else None

    return MeetingGroupIndexRecord(
        group_id=group_id,
        captain_uid=normalize_optional_str(raw_group.get("captainUid")),
        member_uids=member_uids,
        size=len(member_uids),
        status=status,
        region_id=normalize_optional_str(raw_group.get("regionId")),
        availability_slot_ids=coerce_str_list(raw_group.get("availabilitySlotIds")),
        vibe_tag_ids=coerce_str_list(raw_group.get("vibeTagIds")),
        university_ids=university_ids,
        primary_university_id=_pick_primary_university(
            [view.university_id for view in member_views if view.university_id]
        ),
        genders=genders,
        birth_years=sorted(birth_years),
        min_birth_year=min(birth_years) if birth_years else None,
        max_birth_year=max(birth_years) if birth_years else None,
        min_manner_score=min(manners) if manners else 0.0,
        avg_manner_score=(sum(manners) / len(manners)) if manners else 0.0,
        all_verified=bool(member_views) and all(view.is_verified for view in member_views),
        all_active=bool(member_views) and all(view.is_active for view in member_views),
        all_profile_complete=bool(member_views) and all(view.is_profile_complete for view in member_views),
        interest_tag_ids_union=interest_tags,
        lifestyle_tag_ids_union=lifestyle_tags,
        last_active_at_min=min(last_active_values) if last_active_values else None,
        last_active_at_max=max(last_active_values) if last_active_values else None,
        created_at=pd_ts_to_datetime(raw_group.get("createdAt")),
        updated_at=pd_ts_to_datetime(raw_group.get("updatedAt")),
        expire_at=pd_ts_to_datetime(raw_group.get("expireAt")),
        index_status=index_status,
        skip_reason=skip_reason,
        skip_reasons=skip_reasons,
        member_profile_missing_uids=missing_member_profile_uids,
    )


@dataclass
class SourceItemLookup:
    rank: int
    raw_score: float
    rank_score: float
    blended_score: float


@dataclass
class UserSourceLookup:
    eligible: bool
    confidence: float
    items_by_uid: Dict[str, SourceItemLookup]


def rank_to_unit_score(
    rank: int,
    *,
    mode: str = "reciprocal",
    topn_assumption: int = 300,
    reciprocal_offset: float = 60.0,
) -> float:
    if rank <= 0:
        return 0.0
    if mode == "linear":
        if topn_assumption <= 1:
            return 1.0
        return clamp01(1.0 - ((rank - 1.0) / float(topn_assumption - 1)))
    if mode != "reciprocal":
        raise ValueError("rank_to_unit_score mode must be 'reciprocal' or 'linear'")
    return clamp01((reciprocal_offset + 1.0) / (reciprocal_offset + float(rank)))


def _normalize_raw_scores(items: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    raw_pairs: List[Tuple[str, float]] = []
    for item in items:
        uid = normalize_optional_str(item.get("uid"))
        if not uid:
            continue
        raw_pairs.append((uid, safe_float(item.get("score"), 0.0)))
    if not raw_pairs:
        return {}
    values = [score for _, score in raw_pairs]
    lo = min(values)
    hi = max(values)
    if math.isclose(lo, hi):
        return {uid: 1.0 for uid, _ in raw_pairs}
    return {
        uid: clamp01((score - lo) / (hi - lo))
        for uid, score in raw_pairs
    }


def build_user_source_lookup(
    source_name: str,
    doc_data: Optional[Mapping[str, Any]],
    *,
    rank_mode: str = "reciprocal",
    topn_assumption: int = 300,
    reciprocal_offset: float = 60.0,
    raw_score_weight: float = 0.0,
) -> UserSourceLookup:
    if not doc_data or doc_data.get("status") != "ready":
        return UserSourceLookup(eligible=False, confidence=0.0, items_by_uid={})

    signal = doc_data.get("signal")
    signal = signal if isinstance(signal, Mapping) else {}
    eligible_key = {
        "svd": "eligibleForSvd",
        "knn": "eligibleForKnn",
        "clip": "eligibleForClip",
    }.get(source_name)
    eligible = bool(signal.get(eligible_key, True if source_name == "clip" else False))
    confidence_default = 1.0 if source_name == "clip" else 0.0
    confidence = clamp01(safe_float(signal.get("confidence"), confidence_default))
    if not eligible:
        confidence = 0.0

    items = doc_data.get("items")
    items = items if isinstance(items, list) else []
    raw_scores = _normalize_raw_scores(items)
    weight = clamp01(raw_score_weight)

    items_by_uid: Dict[str, SourceItemLookup] = {}
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            continue
        target_uid = normalize_optional_str(item.get("uid"))
        if not target_uid:
            continue
        rank = safe_int(item.get("rank"), idx)
        rank_score = rank_to_unit_score(
            rank,
            mode=rank_mode,
            topn_assumption=topn_assumption,
            reciprocal_offset=reciprocal_offset,
        )
        raw_score = safe_float(item.get("score"), 0.0)
        raw_component = raw_scores.get(target_uid, rank_score)
        blended_score = ((1.0 - weight) * rank_score) + (weight * raw_component)
        items_by_uid[target_uid] = SourceItemLookup(
            rank=rank,
            raw_score=raw_score,
            rank_score=rank_score,
            blended_score=clamp01(blended_score),
        )
    return UserSourceLookup(eligible=eligible, confidence=confidence, items_by_uid=items_by_uid)


def load_user_source_lookups(
    db,
    uids: Sequence[str],
    *,
    date_key: str,
    source_name: str,
    model_recs_collection: str = DEFAULT_MODEL_RECS_COLLECTION,
    rank_mode: str = "reciprocal",
    topn_assumption: int = 300,
    reciprocal_offset: float = 60.0,
    raw_score_weight: float = 0.0,
    batch_size: int = 200,
) -> Dict[str, UserSourceLookup]:
    uids = _dedupe_preserve_order([uid for uid in uids if uid])
    lookups: Dict[str, UserSourceLookup] = {}
    if not uids:
        return lookups
    for batch in iter_chunks(uids, batch_size):
        refs = [
            db.document(f"{model_recs_collection}/{uid}/daily/{date_key}/sources/{source_name}")
            for uid in batch
        ]
        for snap in db.get_all(refs):
            data = snap.to_dict() if snap.exists else None
            uid = snap.reference.parent.parent.parent.parent.id
            lookups[uid] = build_user_source_lookup(
                source_name,
                data,
                rank_mode=rank_mode,
                topn_assumption=topn_assumption,
                reciprocal_offset=reciprocal_offset,
                raw_score_weight=raw_score_weight,
            )
    return lookups


def mutual_source_pair_signal(
    source_lookups: Mapping[str, UserSourceLookup],
    left_uid: str,
    right_uid: str,
) -> Tuple[float, float]:
    left = source_lookups.get(left_uid)
    right = source_lookups.get(right_uid)

    left_item = left.items_by_uid.get(right_uid) if left else None
    right_item = right.items_by_uid.get(left_uid) if right else None

    score_left = left_item.blended_score if left_item is not None else 0.0
    score_right = right_item.blended_score if right_item is not None else 0.0

    conf_left = left.confidence if left and left.eligible and left_item is not None else 0.0
    conf_right = right.confidence if right and right.eligible and right_item is not None else 0.0

    return 0.5 * (score_left + score_right), 0.5 * (conf_left + conf_right)


class MemberEmbeddingCache:
    """Cache member CLIP vectors inside a single batch run."""

    def __init__(
        self,
        embedder: SeolleyeonCLIPEmbedder,
        *,
        max_photos_per_user: int = 3,
    ) -> None:
        self._embedder = embedder
        self._max_photos_per_user = max(1, int(max_photos_per_user))
        self._cache: Dict[str, Optional[np.ndarray]] = {}

    def get_embedding(self, uid: str, photo_urls: Sequence[str]) -> Optional[np.ndarray]:
        if uid in self._cache:
            return self._cache[uid]
        cleaned_urls = [url for url in coerce_str_list(photo_urls) if url]
        if not cleaned_urls:
            self._cache[uid] = None
            return None
        try:
            vec, _ = self._embedder.embed_profile_mean(
                cleaned_urls[: self._max_photos_per_user],
                normalize=True,
            )
            arr = np.asarray(vec, dtype=np.float32)
            norm = float(np.linalg.norm(arr))
            if norm > 0:
                arr = (arr / norm).astype(np.float32, copy=False)
            self._cache[uid] = arr
            return arr
        except Exception as exc:
            log_struct("warning", "member_embedding_failed", uid=uid, error=str(exc))
            self._cache[uid] = None
            return None


@dataclass
class GroupEmbeddingBundle:
    group_id: str
    centroid: Optional[np.ndarray]
    member_vectors: Dict[str, np.ndarray]
    embedded_member_count: int


def build_group_embedding_bundle(
    group_id: str,
    member_uids: Sequence[str],
    member_profiles: Mapping[str, MemberProfileView],
    embedding_cache: MemberEmbeddingCache,
) -> GroupEmbeddingBundle:
    member_vectors: Dict[str, np.ndarray] = {}
    for uid in member_uids:
        profile = member_profiles.get(uid)
        if profile is None:
            continue
        vec = embedding_cache.get_embedding(uid, profile.photo_urls)
        if vec is not None:
            member_vectors[uid] = vec
    if not member_vectors:
        return GroupEmbeddingBundle(
            group_id=group_id,
            centroid=None,
            member_vectors={},
            embedded_member_count=0,
        )
    centroid = np.mean(np.stack(list(member_vectors.values()), axis=0), axis=0).astype(np.float32)
    norm = float(np.linalg.norm(centroid))
    if norm > 0:
        centroid = (centroid / norm).astype(np.float32, copy=False)
    return GroupEmbeddingBundle(
        group_id=group_id,
        centroid=centroid,
        member_vectors=member_vectors,
        embedded_member_count=len(member_vectors),
    )


def clip_similarity_unit(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.float32)
    right = np.asarray(right, dtype=np.float32)
    if left.size == 0 or right.size == 0:
        return 0.0
    sim = float(np.dot(left, right))
    return clamp01((sim + 1.0) * 0.5)


def choose_member_vector(
    uid: str,
    member_vectors: Mapping[str, np.ndarray],
    group_centroid: Optional[np.ndarray],
) -> Optional[np.ndarray]:
    vec = member_vectors.get(uid)
    if vec is not None:
        return vec
    return group_centroid


def kst_age(birth_year: int, *, now_year: Optional[int] = None) -> int:
    ref_year = now_year or datetime.now(tz=KST).year
    return ref_year - int(birth_year) + 1


def member_pref_allows(source: MemberProfileView, target: MemberProfileView) -> bool:
    if source.pref_gender:
        if target.gender is None or target.gender not in source.pref_gender:
            return False
    if source.pref_age_min is not None or source.pref_age_max is not None:
        if target.birth_year is None:
            return False
        target_age = kst_age(target.birth_year)
        if source.pref_age_min is not None and target_age < source.pref_age_min:
            return False
        if source.pref_age_max is not None and target_age > source.pref_age_max:
            return False
    return True


def member_pair_reciprocal_feasible(left: MemberProfileView, right: MemberProfileView) -> bool:
    return member_pref_allows(left, right) and member_pref_allows(right, left)


def shares_member(left_member_uids: Sequence[str], right_member_uids: Sequence[str]) -> bool:
    return bool(set(left_member_uids) & set(right_member_uids))


def availability_overlap_score(left_slots: Sequence[str], right_slots: Sequence[str]) -> Tuple[int, float]:
    left = set(coerce_str_list(left_slots))
    right = set(coerce_str_list(right_slots))
    overlap = len(left & right)
    if overlap <= 0:
        return 0, 0.0
    denom = max(1, min(len(left), len(right)))
    return overlap, clamp01(overlap / float(denom))


def jaccard_score(left: Sequence[str], right: Sequence[str]) -> float:
    left_set = set(coerce_str_list(left))
    right_set = set(coerce_str_list(right))
    if not left_set and not right_set:
        return 0.0
    inter = len(left_set & right_set)
    union = len(left_set | right_set)
    if union <= 0:
        return 0.0
    return clamp01(inter / float(union))


def tag_overlap_score(left: MeetingGroupIndexRecord, right: MeetingGroupIndexRecord) -> float:
    components: List[float] = []
    interest = jaccard_score(left.interest_tag_ids_union, right.interest_tag_ids_union)
    lifestyle = jaccard_score(left.lifestyle_tag_ids_union, right.lifestyle_tag_ids_union)
    vibe = jaccard_score(left.vibe_tag_ids, right.vibe_tag_ids)
    for value, usable in (
        (interest, bool(left.interest_tag_ids_union or right.interest_tag_ids_union)),
        (lifestyle, bool(left.lifestyle_tag_ids_union or right.lifestyle_tag_ids_union)),
        (vibe, bool(left.vibe_tag_ids or right.vibe_tag_ids)),
    ):
        if usable:
            components.append(value)
    if not components:
        return 0.0
    return clamp01(sum(components) / len(components))


def region_compatibility(
    left_region_id: Optional[str],
    right_region_id: Optional[str],
    *,
    allow_missing_region: bool,
) -> Tuple[bool, float]:
    left = normalize_optional_str(left_region_id)
    right = normalize_optional_str(right_region_id)
    if left and right:
        if left == right:
            return True, 1.0
        return False, 0.0
    if allow_missing_region:
        return True, 0.5
    return False, 0.0


def trust_score(
    left: MeetingGroupIndexRecord,
    right: MeetingGroupIndexRecord,
    *,
    now: Optional[datetime] = None,
    manner_floor: float = 30.0,
    manner_ceiling: float = 40.0,
    recency_half_life_days: float = 7.0,
) -> float:
    verified = 1.0 if left.all_verified and right.all_verified else 0.0
    active = 1.0 if left.all_active and right.all_active else 0.0
    profile = 1.0 if left.all_profile_complete and right.all_profile_complete else 0.0
    manner_ref = min(left.min_manner_score, right.min_manner_score)
    manner = clamp01((manner_ref - manner_floor) / max(1e-6, manner_ceiling - manner_floor))
    stale_days = [
        days_since(left.last_active_at_min, now=now),
        days_since(right.last_active_at_min, now=now),
    ]
    stale_days = [value for value in stale_days if value is not None]
    if stale_days:
        worst_days = max(stale_days)
        recency = math.pow(0.5, worst_days / max(1e-6, recency_half_life_days))
    else:
        recency = 0.5
    return clamp01((0.20 * verified) + (0.20 * active) + (0.20 * profile) + (0.20 * manner) + (0.20 * recency))


def balance_score(pair_scores: Sequence[float], *, std_target: float = 0.20) -> float:
    if not pair_scores:
        return 0.0
    std = float(np.std(np.asarray(pair_scores, dtype=np.float32)))
    if std_target <= 0:
        return 1.0 if std <= 0 else 0.0
    return clamp01(1.0 - (std / float(std_target)))


@dataclass
class MatchedPair:
    from_uid: str
    to_uid: str
    score: float

    def to_document(self) -> Dict[str, Any]:
        return {
            "fromUid": self.from_uid,
            "toUid": self.to_uid,
            "score": round(float(self.score), 6),
        }


@dataclass
class AssignmentResult:
    matched_pairs: List[MatchedPair]
    pair_scores: List[float]
    pair_clip_scores: List[float]
    pair_svd_scores: List[float]
    pair_knn_scores: List[float]

    @property
    def assignment_mean(self) -> float:
        return float(np.mean(self.pair_scores)) if self.pair_scores else 0.0

    @property
    def min_pair(self) -> float:
        return min(self.pair_scores) if self.pair_scores else 0.0

    def balance(self, *, std_target: float) -> float:
        return balance_score(self.pair_scores, std_target=std_target)


def best_group_assignment(
    actor_member_uids: Sequence[str],
    candidate_member_uids: Sequence[str],
    member_profiles: Mapping[str, MemberProfileView],
    actor_member_vectors: Mapping[str, np.ndarray],
    candidate_member_vectors: Mapping[str, np.ndarray],
    actor_centroid: Optional[np.ndarray],
    candidate_centroid: Optional[np.ndarray],
    *,
    svd_lookups: Mapping[str, UserSourceLookup],
    knn_lookups: Mapping[str, UserSourceLookup],
    clip_weight: float = 0.80,
    svd_weight: float = 0.15,
    knn_weight: float = 0.05,
    balance_std_target: float = 0.20,
) -> Optional[AssignmentResult]:
    if len(actor_member_uids) != 3 or len(candidate_member_uids) != 3:
        return None

    pair_scores = np.zeros((3, 3), dtype=np.float32)
    pair_clip = np.zeros((3, 3), dtype=np.float32)
    pair_svd = np.zeros((3, 3), dtype=np.float32)
    pair_knn = np.zeros((3, 3), dtype=np.float32)
    reciprocal_ok = np.zeros((3, 3), dtype=bool)

    for left_idx, left_uid in enumerate(actor_member_uids):
        left_profile = member_profiles.get(left_uid)
        left_vec = choose_member_vector(left_uid, actor_member_vectors, actor_centroid)
        for right_idx, right_uid in enumerate(candidate_member_uids):
            right_profile = member_profiles.get(right_uid)
            right_vec = choose_member_vector(right_uid, candidate_member_vectors, candidate_centroid)
            if left_profile is None or right_profile is None:
                reciprocal_ok[left_idx, right_idx] = False
                continue
            reciprocal_ok[left_idx, right_idx] = member_pair_reciprocal_feasible(left_profile, right_profile)
            clip_pair = clip_similarity_unit(left_vec, right_vec) if left_vec is not None and right_vec is not None else 0.0
            svd_pair, svd_conf = mutual_source_pair_signal(svd_lookups, left_uid, right_uid)
            knn_pair, knn_conf = mutual_source_pair_signal(knn_lookups, left_uid, right_uid)
            pair_clip[left_idx, right_idx] = clip_pair
            pair_svd[left_idx, right_idx] = svd_pair * svd_conf
            pair_knn[left_idx, right_idx] = knn_pair * knn_conf
            pair_scores[left_idx, right_idx] = clamp01(
                (clip_weight * clip_pair)
                + (svd_weight * pair_svd[left_idx, right_idx])
                + (knn_weight * pair_knn[left_idx, right_idx])
            )

    best_result: Optional[AssignmentResult] = None
    best_key: Optional[Tuple[float, float, float]] = None
    for perm in permutations(range(3)):
        matched_pairs: List[MatchedPair] = []
        score_list: List[float] = []
        clip_list: List[float] = []
        svd_list: List[float] = []
        knn_list: List[float] = []
        feasible = True
        for left_idx, right_idx in enumerate(perm):
            if not reciprocal_ok[left_idx, right_idx]:
                feasible = False
                break
            score_list.append(float(pair_scores[left_idx, right_idx]))
            clip_list.append(float(pair_clip[left_idx, right_idx]))
            svd_list.append(float(pair_svd[left_idx, right_idx]))
            knn_list.append(float(pair_knn[left_idx, right_idx]))
            matched_pairs.append(
                MatchedPair(
                    from_uid=str(actor_member_uids[left_idx]),
                    to_uid=str(candidate_member_uids[right_idx]),
                    score=float(pair_scores[left_idx, right_idx]),
                )
            )
        if not feasible:
            continue
        key = (
            float(np.mean(score_list)),
            min(score_list),
            balance_score(score_list, std_target=balance_std_target),
        )
        if best_key is None or key > best_key:
            best_key = key
            best_result = AssignmentResult(
                matched_pairs=matched_pairs,
                pair_scores=score_list,
                pair_clip_scores=clip_list,
                pair_svd_scores=svd_list,
                pair_knn_scores=knn_list,
            )
    return best_result


def compute_group_score(
    actor_group: MeetingGroupIndexRecord,
    candidate_group: MeetingGroupIndexRecord,
    assignment: AssignmentResult,
    *,
    weight_assignment_mean: float,
    weight_balance: float,
    weight_min_pair: float,
    weight_availability: float,
    weight_tag_overlap: float,
    weight_trust: float,
    weight_region_compatibility: float = 0.0,
    balance_std_target: float = 0.20,
    allow_missing_region: bool = True,
) -> Tuple[float, Dict[str, float], bool]:
    overlap_count, availability = availability_overlap_score(
        actor_group.availability_slot_ids,
        candidate_group.availability_slot_ids,
    )
    region_ok, region_score = region_compatibility(
        actor_group.region_id,
        candidate_group.region_id,
        allow_missing_region=allow_missing_region,
    )
    if not region_ok:
        return 0.0, {}, False

    components = {
        "assignmentMean": clamp01(assignment.assignment_mean),
        "balance": assignment.balance(std_target=balance_std_target),
        "minPair": clamp01(assignment.min_pair),
        "availability": availability if overlap_count > 0 else 0.0,
        "tagOverlap": tag_overlap_score(actor_group, candidate_group),
        "trust": trust_score(actor_group, candidate_group),
        "regionCompatibility": region_score,
    }
    total = (
        (weight_assignment_mean * components["assignmentMean"])
        + (weight_balance * components["balance"])
        + (weight_min_pair * components["minPair"])
        + (weight_availability * components["availability"])
        + (weight_tag_overlap * components["tagOverlap"])
        + (weight_trust * components["trust"])
        + (weight_region_compatibility * components["regionCompatibility"])
    )
    return round(float(total), 6), {k: round(float(v), 6) for k, v in components.items()}, True


def select_primary_reason(reason_counts: Mapping[str, int], *, fallback: str) -> str:
    if not reason_counts:
        return fallback
    ordered = sorted(reason_counts.items(), key=lambda item: (-item[1], item[0]))
    return ordered[0][0]


def load_rec_event_docs_by_date_keys(
    db,
    *,
    collection_name: str,
    date_keys: Sequence[str],
) -> List[Dict[str, Any]]:
    unique_date_keys = _dedupe_preserve_order([key for key in date_keys if key])
    if not unique_date_keys:
        return []

    require_firestore()
    docs: List[Dict[str, Any]] = []
    for batch in iter_chunks(unique_date_keys, 10):
        try:
            query = db.collection(collection_name).where(filter=FieldFilter("dateKey", "in", batch))
            snaps = list(query.stream())
        except Exception as exc:
            log_struct("warning", "rec_events_datekey_query_fallback", error=str(exc), batch=batch)
            batch_set = set(batch)
            snaps = [
                snap
                for snap in db.collection(collection_name).stream()
                if normalize_optional_str((snap.to_dict() or {}).get("dateKey")) in batch_set
            ]
        for snap in snaps:
            data = snap.to_dict() or {}
            data["_docId"] = snap.id
            docs.append(data)
    return docs


def build_group_recent_action_maps(
    event_docs: Sequence[Mapping[str, Any]],
    *,
    exposure_event_types: Optional[Set[str]] = None,
) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    exposure_types = exposure_event_types or set(DEFAULT_MEETING_EXPOSURE_EVENTS)
    recent_nope: Dict[str, Set[str]] = defaultdict(set)
    recent_exposure: Dict[str, Set[str]] = defaultdict(set)
    for event_doc in event_docs:
        event_type = normalize_optional_str(event_doc.get("type") or event_doc.get("eventType"))
        target_type = normalize_optional_str(event_doc.get("targetType"))
        context = event_doc.get("context")
        context = context if isinstance(context, Mapping) else {}
        actor_group_id = normalize_optional_str(context.get("actorGroupId"))
        target_group_id = normalize_optional_str(_first_non_none(context.get("targetGroupId"), event_doc.get("targetId")))
        if target_type != "meeting_group" or not actor_group_id or not target_group_id or not event_type:
            continue
        if event_type == "nope":
            recent_nope[actor_group_id].add(target_group_id)
        if event_type in exposure_types:
            recent_exposure[actor_group_id].add(target_group_id)
    return recent_nope, recent_exposure


def build_cross_user_block_pairs(
    event_docs: Sequence[Mapping[str, Any]],
    *,
    allowed_user_ids: Optional[Set[str]] = None,
) -> Set[Tuple[str, str]]:
    blocked_pairs: Set[Tuple[str, str]] = set()
    for event_doc in event_docs:
        event_type = normalize_optional_str(event_doc.get("type") or event_doc.get("eventType"))
        if event_type not in {"block", "report"}:
            continue
        target_type = normalize_optional_str(event_doc.get("targetType"))
        if target_type == "meeting_group":
            continue
        actor_uid = normalize_optional_str(event_doc.get("userId") or event_doc.get("fromUserId"))
        target_uid = normalize_optional_str(
            _first_non_none(
                event_doc.get("candidateUserId"),
                event_doc.get("targetUserId"),
                event_doc.get("toUserId"),
                event_doc.get("targetId"),
            )
        )
        if not actor_uid or not target_uid:
            continue
        if allowed_user_ids is not None and (actor_uid not in allowed_user_ids or target_uid not in allowed_user_ids):
            continue
        blocked_pairs.add(tuple(sorted((actor_uid, target_uid))))
    return blocked_pairs


def has_cross_block_pair(
    left_member_uids: Sequence[str],
    right_member_uids: Sequence[str],
    blocked_pairs: Set[Tuple[str, str]],
) -> bool:
    for left_uid in left_member_uids:
        for right_uid in right_member_uids:
            if tuple(sorted((left_uid, right_uid))) in blocked_pairs:
                return True
    return False


def load_meeting_group_index_records(
    db,
    *,
    collection_name: str = DEFAULT_MEETING_GROUP_INDEX_COLLECTION,
    only_ready: bool = False,
    group_ids: Optional[Sequence[str]] = None,
) -> Dict[str, MeetingGroupIndexRecord]:
    if group_ids:
        raw_docs = load_documents_by_ids(db, collection_name, list(group_ids))
    else:
        raw_docs = stream_collection_documents(db, collection_name)
    records: Dict[str, MeetingGroupIndexRecord] = {}
    for group_id, raw in raw_docs.items():
        record = MeetingGroupIndexRecord.from_document(group_id, raw)
        if only_ready and record.index_status != "ready":
            continue
        records[group_id] = record
    return records


def normalize_scores(values: Sequence[float]) -> List[float]:
    if not values:
        return []
    arr = np.asarray(values, dtype=np.float32)
    lo = float(np.min(arr))
    hi = float(np.max(arr))
    if math.isclose(lo, hi):
        return [1.0 for _ in values]
    return [clamp01((float(v) - lo) / (hi - lo)) for v in arr.tolist()]


def group_diversity_similarity(
    left: MeetingGroupIndexRecord,
    right: MeetingGroupIndexRecord,
    *,
    centroids: Optional[Mapping[str, np.ndarray]] = None,
) -> float:
    centroid_score = 0.0
    if centroids is not None:
        left_centroid = centroids.get(left.group_id)
        right_centroid = centroids.get(right.group_id)
        if left_centroid is not None and right_centroid is not None:
            centroid_score = clip_similarity_unit(left_centroid, right_centroid)
    same_university = 1.0 if (
        left.primary_university_id
        and right.primary_university_id
        and left.primary_university_id == right.primary_university_id
    ) else 0.0
    same_region = 1.0 if (
        left.region_id
        and right.region_id
        and left.region_id == right.region_id
    ) else 0.0
    return clamp01((0.60 * centroid_score) + (0.25 * same_university) + (0.15 * same_region))
