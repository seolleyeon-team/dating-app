#!/usr/bin/env python3
"""Backfill meetingGroups from eventTeamSetups for event team matchmaking."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional

from seolleyeon_meeting_common_v1 import (
    DEFAULT_PROFILE_INDEX_COLLECTION,
    DEFAULT_USERS_COLLECTION,
    coerce_str_list,
    firestore,
    load_documents_by_ids,
    log_struct,
    make_firestore_client,
    normalize_optional_str,
    stream_collection_documents,
)

DEFAULT_EVENT_TEAM_SETUPS_COLLECTION = "eventTeamSetups"
DEFAULT_MEETING_GROUPS_COLLECTION = "meetingGroups"
DEFAULT_AVAILABILITY_SLOT_IDS = [
    "weekday_evening",
    "weekend_afternoon",
    "weekend_evening",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill meetingGroups documents from eventTeamSetups."
    )
    parser.add_argument("--firestore_project", required=True, type=str)
    parser.add_argument("--firestore_database", default=None, type=str)
    parser.add_argument(
        "--event_team_setups_collection",
        default=DEFAULT_EVENT_TEAM_SETUPS_COLLECTION,
        type=str,
    )
    parser.add_argument(
        "--meeting_groups_collection",
        default=DEFAULT_MEETING_GROUPS_COLLECTION,
        type=str,
    )
    parser.add_argument(
        "--profile_index_collection",
        default=DEFAULT_PROFILE_INDEX_COLLECTION,
        type=str,
    )
    parser.add_argument(
        "--users_collection",
        default=DEFAULT_USERS_COLLECTION,
        type=str,
    )
    parser.add_argument("--team_setup_ids", default="", type=str)
    parser.add_argument("--limit", default=0, type=int)
    parser.add_argument("--dry_run", action="store_true")
    return parser


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _first_non_empty(*values: Any) -> Optional[str]:
    for value in values:
        normalized = normalize_optional_str(value)
        if normalized:
            return normalized
    return None


def _first_number(*values: Any) -> Optional[float]:
    for value in values:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _first_int(*values: Any) -> Optional[int]:
    parsed = _first_number(*values)
    return None if parsed is None else int(parsed)


def _read_onboarding(user_doc: Mapping[str, Any]) -> Mapping[str, Any]:
    onboarding = user_doc.get("onboarding")
    return onboarding if isinstance(onboarding, Mapping) else {}


def _build_member_snapshot(
    uid: str,
    user_doc: Mapping[str, Any],
    profile_doc: Mapping[str, Any],
) -> Dict[str, Any]:
    onboarding = _read_onboarding(user_doc)
    photo_urls = coerce_str_list(onboarding.get("photoUrls"))
    return {
        "uid": uid,
        "displayName": _first_non_empty(onboarding.get("nickname"), user_doc.get("nickname"), uid) or uid,
        "photoUrl": _first_non_empty(
            photo_urls[0] if photo_urls else None,
            onboarding.get("profileImageUrl"),
            onboarding.get("representativeImageUrl"),
            user_doc.get("profileImageUrl"),
        ),
        "universityId": _first_non_empty(
            onboarding.get("universityId"),
            user_doc.get("universityId"),
            profile_doc.get("universityId"),
            onboarding.get("university"),
            user_doc.get("universityName"),
            user_doc.get("university"),
        ),
        "universityName": _first_non_empty(
            onboarding.get("university"),
            user_doc.get("universityName"),
            user_doc.get("university"),
        ),
        "mannerScore": _first_number(
            profile_doc.get("mannerScore"),
            user_doc.get("mannerScore"),
            36.5,
        ),
        "isVerified": bool(
            profile_doc.get("isVerified")
            or user_doc.get("isStudentVerified")
            or user_doc.get("isVerified")
        ),
        "shortIntro": _first_non_empty(
            onboarding.get("selfIntroduction"),
            onboarding.get("shortIntro"),
            user_doc.get("shortIntro"),
        ),
        "birthYear": _first_int(
            profile_doc.get("birthYear"),
            onboarding.get("birthYear"),
            user_doc.get("birthYear"),
        ),
        "major": _first_non_empty(onboarding.get("major"), user_doc.get("major")),
    }


def _deterministic_member_uids(team_doc: Mapping[str, Any]) -> List[str]:
    leader_uid = normalize_optional_str(team_doc.get("leaderUserId")) or ""
    accepted_user_ids = coerce_str_list(team_doc.get("acceptedUserIds"))
    if not leader_uid:
        return _dedupe_preserve_order(accepted_user_ids)
    return _dedupe_preserve_order(
        [leader_uid, *[uid for uid in accepted_user_ids if uid != leader_uid]]
    )


def _pick_primary(values: List[Optional[str]]) -> Optional[str]:
    counts: Dict[str, int] = {}
    ordered: List[str] = []
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
        if value not in ordered:
            ordered.append(value)
    if not ordered:
        return None
    ordered.sort(key=lambda value: (-counts.get(value, 0), ordered.index(value)))
    return ordered[0]


def _derive_availability_slot_ids(
    team_doc: Mapping[str, Any],
    user_docs: Mapping[str, Mapping[str, Any]],
) -> List[str]:
    direct = coerce_str_list(team_doc.get("availabilitySlotIds"))
    if direct:
        return direct
    collected: List[str] = []
    for user_doc in user_docs.values():
        collected.extend(coerce_str_list(_read_onboarding(user_doc).get("availabilitySlotIds")))
    return _dedupe_preserve_order(collected) or list(DEFAULT_AVAILABILITY_SLOT_IDS)


def _derive_vibe_tag_ids(
    team_doc: Mapping[str, Any],
    user_docs: Mapping[str, Mapping[str, Any]],
) -> List[str]:
    direct = coerce_str_list(team_doc.get("vibeTagIds"))
    if direct:
        return direct[:8]
    collected: List[str] = []
    for user_doc in user_docs.values():
        onboarding = _read_onboarding(user_doc)
        collected.extend(coerce_str_list(onboarding.get("interests")))
        collected.extend(coerce_str_list(onboarding.get("keywords")))
        collected.extend(coerce_str_list(onboarding.get("vibeTagIds")))
    return _dedupe_preserve_order(collected)[:8]


def _build_meeting_group_payload(
    team_setup_id: str,
    team_doc: Mapping[str, Any],
    user_docs: Mapping[str, Mapping[str, Any]],
    profile_docs: Mapping[str, Mapping[str, Any]],
) -> Dict[str, Any]:
    member_uids = _deterministic_member_uids(team_doc)
    members_snapshot = [
        _build_member_snapshot(uid, user_docs.get(uid, {}), profile_docs.get(uid, {}))
        for uid in member_uids
    ]
    member_count = len(member_uids)
    is_eligible = member_count == 3
    university_ids = _dedupe_preserve_order(
        [member.get("universityId") for member in members_snapshot if member.get("universityId")]
    )
    primary_university_id = _pick_primary(
        [member.get("universityId") for member in members_snapshot]
    )
    now_kst = datetime.now(timezone.utc) + timedelta(hours=9)
    expire_at = now_kst + timedelta(days=7)
    return {
        "groupId": team_setup_id,
        "sourceCollection": DEFAULT_EVENT_TEAM_SETUPS_COLLECTION,
        "sourceSetupId": team_setup_id,
        "captainUid": _first_non_empty(team_doc.get("captainUid"), team_doc.get("leaderUserId")),
        "leaderUid": _first_non_empty(team_doc.get("leaderUserId")),
        "memberUids": member_uids,
        "membersSnapshot": members_snapshot,
        "memberCount": member_count,
        "size": member_count,
        "status": "open" if is_eligible else ("draft" if member_count > 0 else "closed"),
        "pendingInviteeIds": coerce_str_list(team_doc.get("pendingInviteeIds")),
        "eventType": "season_meeting",
        "seasonKey": now_kst.strftime("%Y%m"),
        "regionId": _first_non_empty(team_doc.get("regionId"), primary_university_id),
        "availabilitySlotIds": _derive_availability_slot_ids(team_doc, user_docs) if is_eligible else [],
        "vibeTagIds": _derive_vibe_tag_ids(team_doc, user_docs),
        "universityIds": university_ids,
        "primaryUniversityId": primary_university_id,
        "expireAt": expire_at,
        "active": is_eligible,
        "isEligibleForMeetingRec": is_eligible,
        "eligibilityReason": "ready" if is_eligible else "accepted_member_count_not_3",
        "syncSource": "event_team_setup_backfill_v1",
        "lastSyncedAt": firestore.SERVER_TIMESTAMP if firestore is not None else None,
    }


def main() -> int:
    args = build_parser().parse_args()
    db = make_firestore_client(args.firestore_project, database=args.firestore_database)
    requested_ids = [value for value in coerce_str_list(args.team_setup_ids.split(",")) if value]
    if requested_ids:
        raw_team_docs = load_documents_by_ids(
            db,
            args.event_team_setups_collection,
            requested_ids,
        )
    else:
        raw_team_docs = stream_collection_documents(db, args.event_team_setups_collection)

    team_items = list(raw_team_docs.items())
    if args.limit > 0:
        team_items = team_items[: int(args.limit)]
    if not team_items:
        log_struct("warning", "event_team_meeting_groups_backfill_no_source_docs")
        return 0

    all_member_uids: List[str] = []
    for _team_setup_id, team_doc in team_items:
        all_member_uids.extend(_deterministic_member_uids(team_doc or {}))
    unique_member_uids = _dedupe_preserve_order(all_member_uids)
    user_docs = load_documents_by_ids(db, args.users_collection, unique_member_uids)
    profile_docs = load_documents_by_ids(db, args.profile_index_collection, unique_member_uids)

    counters: Counter[str] = Counter()
    bulk_writer = None if args.dry_run else db.bulk_writer()
    for team_setup_id, team_doc in team_items:
        payload = _build_meeting_group_payload(
            team_setup_id,
            team_doc or {},
            user_docs,
            profile_docs,
        )
        payload["updatedAt"] = firestore.SERVER_TIMESTAMP if firestore is not None else None
        payload["createdAt"] = team_doc.get("createdAt")
        payload["sourceUpdatedAt"] = team_doc.get("updatedAt")
        counters[payload["eligibilityReason"]] += 1

        if bulk_writer is not None:
            doc_ref = db.collection(args.meeting_groups_collection).document(team_setup_id)
            bulk_writer.set(doc_ref, payload, merge=True)

    if bulk_writer is not None:
        bulk_writer.close()

    log_struct(
        "info",
        "event_team_meeting_groups_backfill_done",
        dryRun=bool(args.dry_run),
        teamCount=len(team_items),
        uniqueMemberCount=len(unique_member_uids),
        eligibilityCounts=dict(counters),
        targetCollection=args.meeting_groups_collection,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
