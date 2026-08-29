"""Fail-closed Kakao-friend privacy policy for the 1:1 recommender.

The model pipeline runs with Admin SDK privileges, so Firestore Security Rules
cannot protect model output from an accidental policy omission.  Every source
export and the final RRF merge must apply this snapshot before writing
``modelRecs``.
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


def _is_recommendation_ready_user(data: Mapping[str, Any]) -> bool:
    status = str(data.get("status") or data.get("accountStatus") or "active").strip().lower()
    if status in _INACTIVE_ACCOUNT_STATUSES:
        return False
    if data.get("recommendationPrivacyReady") is not True:
        return False
    if data.get("isStudentVerified") is not True:
        return False
    if data.get("initialSetupComplete") is not True:
        return False
    if data.get("profileVisible") is False:
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


def _is_active_exclusion(data: Mapping[str, Any]) -> bool:
    # ``active`` is the forward-compatible compact representation.  Existing
    # documents use enabledBy, so keep the strict bool-only compatibility path.
    if data.get("active") is True:
        return True
    enabled_by = data.get("enabledBy")
    return isinstance(enabled_by, Mapping) and any(
        value is True for value in enabled_by.values()
    )


@dataclass(frozen=True)
class RecommendationPrivacyPolicy:
    ready_user_ids: frozenset[str]
    excluded_by_viewer: Mapping[str, frozenset[str]]

    def allows(self, viewer_uid: str, candidate_uid: str) -> bool:
        if not viewer_uid or not candidate_uid or viewer_uid == candidate_uid:
            return False
        if viewer_uid not in self.ready_user_ids:
            return False
        if candidate_uid not in self.ready_user_ids:
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
) -> RecommendationPrivacyPolicy:
    ready_user_ids = {
        str(uid)
        for uid, data in user_records
        if uid and _is_recommendation_ready_user(data)
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
        excluded_by_viewer={
            uid: frozenset(targets) for uid, targets in excluded.items()
        },
    )


def load_recommendation_privacy_policy(
    db: Any,
    *,
    users_collection: str = "users",
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
            and parts[0] == "recommendationExclusions"
            and parts[2] == "targets"
        ):
            exclusion_records.append((parts[1], parts[3], doc.to_dict() or {}))

    return build_recommendation_privacy_policy(user_records, exclusion_records)


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
