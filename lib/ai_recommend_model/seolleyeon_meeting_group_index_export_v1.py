#!/usr/bin/env python3
"""Build meetingGroupIndex documents for Seolleyeon meeting recommender v1."""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Dict, List, Optional

from seolleyeon_meeting_common_v1 import (
    DEFAULT_MEETING_GROUP_INDEX_COLLECTION,
    DEFAULT_MEETING_GROUPS_COLLECTION,
    DEFAULT_PROFILE_INDEX_COLLECTION,
    DEFAULT_USERS_COLLECTION,
    build_group_index_record,
    build_member_profile_view,
    coerce_str_list,
    firestore,
    load_documents_by_ids,
    log_struct,
    make_firestore_client,
    parse_date_key,
    stream_collection_documents,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export meeting group index documents for meeting recommender v1."
    )
    parser.add_argument("--firestore_project", required=True, type=str)
    parser.add_argument("--firestore_database", default=None, type=str)
    parser.add_argument("--date_key", required=True, type=str, help="YYYYMMDD (KST)")
    parser.add_argument("--meeting_groups_collection", default=DEFAULT_MEETING_GROUPS_COLLECTION, type=str)
    parser.add_argument("--meeting_group_index_collection", default=DEFAULT_MEETING_GROUP_INDEX_COLLECTION, type=str)
    parser.add_argument("--profile_index_collection", default=DEFAULT_PROFILE_INDEX_COLLECTION, type=str)
    parser.add_argument("--users_collection", default=DEFAULT_USERS_COLLECTION, type=str)
    parser.add_argument("--manner_min_threshold", default=33.0, type=float)
    parser.add_argument("--group_ids", default="", type=str, help="Comma-separated groupIds to process")
    parser.add_argument("--limit", default=0, type=int, help="Optional limit for local smoke runs")
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--algorithm_version", default=None, type=str)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    date_key = parse_date_key(args.date_key)
    algorithm_version = args.algorithm_version or f"meeting_group_index_v1_{date_key}"

    db = make_firestore_client(args.firestore_project, database=args.firestore_database)
    requested_group_ids = [group_id for group_id in coerce_str_list(args.group_ids.split(",")) if group_id]
    if requested_group_ids:
        raw_groups = load_documents_by_ids(db, args.meeting_groups_collection, requested_group_ids)
    else:
        raw_groups = stream_collection_documents(db, args.meeting_groups_collection)

    group_items = list(raw_groups.items())
    if args.limit > 0:
        group_items = group_items[: int(args.limit)]
    if not group_items:
        log_struct("warning", "meeting_group_index_no_groups", collection=args.meeting_groups_collection)
        return 0

    member_uids: List[str] = []
    for _group_id, raw_group in group_items:
        member_uids.extend(coerce_str_list((raw_group or {}).get("memberUids")))
    member_uids = list(dict.fromkeys(member_uids))

    profile_docs = load_documents_by_ids(db, args.profile_index_collection, member_uids)
    user_docs = load_documents_by_ids(db, args.users_collection, member_uids)
    member_views: Dict[str, Optional[object]] = {}
    for uid in member_uids:
        if uid not in profile_docs and uid not in user_docs:
            member_views[uid] = None
            continue
        member_views[uid] = build_member_profile_view(
            uid,
            profile_docs.get(uid),
            user_docs.get(uid),
        )

    counters: Counter[str] = Counter()
    bw = None if args.dry_run else db.bulk_writer()
    for group_id, raw_group in group_items:
        record = build_group_index_record(
            group_id,
            raw_group or {},
            member_views,
            manner_min_threshold=float(args.manner_min_threshold),
        )
        payload = record.to_document()
        payload["algorithmVersion"] = algorithm_version
        payload["indexedAt"] = firestore.SERVER_TIMESTAMP if firestore is not None else None

        counters[record.index_status] += 1
        if record.skip_reason:
            counters[f"skip:{record.skip_reason}"] += 1

        if bw is not None:
            doc_ref = db.collection(args.meeting_group_index_collection).document(group_id)
            bw.set(doc_ref, payload, merge=True)

    if bw is not None:
        bw.close()

    log_struct(
        "info",
        "meeting_group_index_export_done",
        algorithmVersion=algorithm_version,
        dryRun=bool(args.dry_run),
        groups=len(group_items),
        ready=counters.get("ready", 0),
        skipped=counters.get("skipped", 0),
        skipReasonCounts={key[5:]: value for key, value in counters.items() if key.startswith("skip:")},
        memberUidCount=len(member_uids),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
