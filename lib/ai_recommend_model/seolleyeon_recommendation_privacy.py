"""Fail-closed recommendation privacy policy for the 1:1 recommender.
Two independent gates compose here:

* Account-state eligibility: only verified, fully onboarded, visible, active
  accounts may appear as a viewer or a candidate.
* Per-pair Kakao friend exclusion: active ``recommendationExclusions`` docs
  (materialized bilaterally from ``kakaoFriendPairs``) remove specific
  viewer/candidate pairs.

The model pipeline runs with Admin SDK privileges, so Firestore Security Rules
cannot protect model output from an accidental policy omission.  Every source
export and the final RRF merge must apply this snapshot before writing
``modelRecs``. It includes Kakao-friend and same-department pair exclusions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Set, Tuple


_INACTIVE_ACCOUNT_STATUSES = {
    "banned",
    "blocked",
    "deleted",
    "restricted_rejoin",
    "suspended",
    "withdrawn",
}

_RECOMMENDATION_EXCLUSION_COLLECTIONS = {
    "recommendationExclusions",
    "departmentRecommendationExclusions",
}


def _is_recommendation_ready_user(data: Mapping[str, Any]) -> bool:
    """Whether the user may receive recommendations as a viewer.

    Profile visibility deliberately does not belong here.  Hiding a profile
    controls whether *other people* can be shown that profile; it must never
    remove the owner's own daily feed.
    """
    status = str(data.get("status") or data.get("accountStatus") or "active").strip().lower()
    if status in _INACTIVE_ACCOUNT_STATUSES:
        return False
    if data.get("isStudentVerified") is not True:
        return False
    if data.get("initialSetupComplete") is not True:
        return False
    if data.get("isActive") is False:
        return False
    if data.get("isDeleted") is True:
        return False
    if data.get("isSuspended") is True:
        return False
    if data.get("isWithdrawn") is True:
        return False
    return True


def _valid_date_key(value: Any) -> str | None:
    text = str(value or "").strip()
    if len(text) != 8 or not text.isdigit():
        return None
    return text


def is_profile_visible_for_recommendations(
    data: Mapping[str, Any],
    *,
    date_key: str | None = None,
) -> bool:
    """Resolve candidate visibility for one KST recommendation date.

    The app stores a requested value plus its next-day effective date.  This
    keeps a generated day's feed stable even if the owner changes the setting
    later that day.  Legacy records without transition metadata retain their
    existing ``profileVisible`` behavior.
    """
    requested_visible = data.get("profileVisible") is not False
    effective_date_key = _valid_date_key(
        data.get("profileVisibleEffectiveDateKey")
    )
    requested_date_key = _valid_date_key(date_key)
    if effective_date_key and requested_date_key:
        previous_visible = data.get("profileVisibleBeforeEffectiveDate") is not False
        if requested_date_key < effective_date_key:
            return previous_visible
    return requested_visible


def _is_active_exclusion(data: Mapping[str, Any]) -> bool:
    # New-style docs (source == "kakao_friend_pair") carry ``active: True``.
    # Legacy docs use enabledBy only, so keep the strict bool-only
    # compatibility path for the any-member-enabled shape.
    if data.get("active") is True:
        return True
    enabled_by = data.get("enabledBy")
    return isinstance(enabled_by, Mapping) and any(
        value is True for value in enabled_by.values()
    )


@dataclass(frozen=True)
class RecommendationPrivacyPolicy:
    # ``ready_user_ids`` is intentionally retained as the viewer set for
    # compatibility with existing batch consumers.  Candidate eligibility is
    # separately represented below.
    ready_user_ids: frozenset[str]
    excluded_by_viewer: Mapping[str, frozenset[str]]
    candidate_ready_user_ids: frozenset[str] | None = None

    @property
    def candidate_user_ids(self) -> frozenset[str]:
        return (
            self.ready_user_ids
            if self.candidate_ready_user_ids is None
            else self.candidate_ready_user_ids
        )

    def allows(self, viewer_uid: str, candidate_uid: str) -> bool:
        if not viewer_uid or not candidate_uid or viewer_uid == candidate_uid:
            return False
        if viewer_uid not in self.ready_user_ids:
            return False
        if candidate_uid not in self.candidate_user_ids:
            return False
        return candidate_uid not in self.excluded_by_viewer.get(
            viewer_uid, frozenset()
        )

    def filter_items(
        self,
        viewer_uid: str,
        items: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for item in items:
            raw_uid = item.get("uid")
            candidate_uid = str(raw_uid).strip() if raw_uid is not None else ""
            if not candidate_uid or candidate_uid in seen:
                continue
            if not self.allows(viewer_uid, candidate_uid):
                continue
            payload = dict(item)
            payload["uid"] = candidate_uid
            payload["rank"] = len(filtered) + 1
            filtered.append(payload)
            seen.add(candidate_uid)
        return filtered


def build_recommendation_privacy_policy(
    user_records: Iterable[Tuple[str, Mapping[str, Any]]],
    exclusion_records: Iterable[Tuple[str, str, Mapping[str, Any]]],
    *,
    date_key: str | None = None,
) -> RecommendationPrivacyPolicy:
    normalized_users = [
        (str(uid), data)
        for uid, data in user_records
        if uid and isinstance(data, Mapping)
    ]
    ready_user_ids = {
        uid for uid, data in normalized_users if _is_recommendation_ready_user(data)
    }
    candidate_ready_user_ids = {
        uid
        for uid, data in normalized_users
        if uid in ready_user_ids
        and is_profile_visible_for_recommendations(data, date_key=date_key)
    }
    excluded: MutableMapping[str, Set[str]] = {}
    for viewer_uid, candidate_uid, data in exclusion_records:
        viewer = str(viewer_uid).strip()
        candidate = str(candidate_uid).strip()
        if not viewer or not candidate or viewer == candidate:
            continue
        if not _is_active_exclusion(data):
            continue
        # Materialization is supposed to be bidirectional.  Mirroring here is
        # defensive: one damaged/missing direction must never become a leak.
        excluded.setdefault(viewer, set()).add(candidate)
        excluded.setdefault(candidate, set()).add(viewer)

    return RecommendationPrivacyPolicy(
        ready_user_ids=frozenset(ready_user_ids),
        candidate_ready_user_ids=frozenset(candidate_ready_user_ids),
        excluded_by_viewer={
            uid: frozenset(targets) for uid, targets in excluded.items()
        },
    )


def load_recommendation_privacy_policy(
    db: Any,
    *,
    users_collection: str = "users",
    date_key: str | None = None,
) -> RecommendationPrivacyPolicy:
    """Load one authoritative snapshot or raise; never return an empty fallback."""

    user_records = [
        (doc.id, doc.to_dict() or {})
        for doc in db.collection(users_collection).stream()
    ]

    exclusion_records: List[Tuple[str, str, Mapping[str, Any]]] = []
    for doc in db.collection_group("targets").stream():
        parts = doc.reference.path.split("/")
        if (
            len(parts) == 4
            and parts[0] in _RECOMMENDATION_EXCLUSION_COLLECTIONS
            and parts[2] == "targets"
        ):
            exclusion_records.append((parts[1], parts[3], doc.to_dict() or {}))

    return build_recommendation_privacy_policy(
        user_records,
        exclusion_records,
        date_key=date_key,
    )


def filter_recommendations(
    recommendations: Mapping[str, Sequence[Mapping[str, Any]]],
    policy: RecommendationPrivacyPolicy,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, int]]:
    filtered: Dict[str, List[Dict[str, Any]]] = {}
    dropped_viewers = 0
    dropped_candidates = 0
    for viewer_uid, items in recommendations.items():
        viewer = str(viewer_uid).strip()
        if viewer not in policy.ready_user_ids:
            dropped_viewers += 1
            dropped_candidates += len(items)
            continue
        kept = policy.filter_items(viewer, items)
        dropped_candidates += max(0, len(items) - len(kept))
        if kept:
            filtered[viewer] = kept
    return filtered, {
        "inputViewers": len(recommendations),
        "outputViewers": len(filtered),
        "droppedViewers": dropped_viewers,
        "droppedCandidates": dropped_candidates,
    }
