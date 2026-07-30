#!/usr/bin/env python3
"""Verify exported meeting recommender artifacts and summarize skip reasons."""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Dict, List

from seolleyeon_meeting_common_v1 import (
    DEFAULT_MEETING_DAILY_RECS_COLLECTION,
    DEFAULT_MEETING_GROUP_INDEX_COLLECTION,
    DEFAULT_MEETING_MODEL_RECS_COLLECTION,
    coerce_str_list,
    firestore,
    load_meeting_group_index_records,
    log_struct,
    make_firestore_client,
    parse_date_key,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify meeting recommender outputs.")
    parser.add_argument("--firestore_project", required=True, type=str)
    parser.add_argument("--firestore_database", default=None, type=str)
    parser.add_argument("--date_key", required=True, type=str, help="YYYYMMDD (KST)")
    parser.add_argument("--meeting_group_index_collection", default=DEFAULT_MEETING_GROUP_INDEX_COLLECTION, type=str)
    parser.add_argument("--meeting_model_recs_collection", default=DEFAULT_MEETING_MODEL_RECS_COLLECTION, type=str)
    parser.add_argument("--meeting_daily_recs_collection", default=DEFAULT_MEETING_DAILY_RECS_COLLECTION, type=str)
    parser.add_argument("--group_ids", default="", type=str)
    parser.add_argument("--write_verify_doc", action="store_true")
    parser.add_argument("--verify_collection", default="meetingVerifyRuns", type=str)
    return parser


def _load_nested_docs(
    db,
    group_ids: List[str],
    *,
    prefix_collection: str,
    date_key: str,
    suffix: str,
    source_kind: str,
) -> Dict[str, dict]:
    refs = [db.document(f"{prefix_collection}/{group_id}/{suffix.format(date_key=date_key)}") for group_id in group_ids]
    docs: Dict[str, dict] = {}
    for snap in db.get_all(refs):
        if source_kind == "daily":
            group_id = snap.reference.parent.parent.id
        else:
            group_id = snap.reference.parent.parent.parent.parent.id
        docs[group_id] = snap.to_dict() or {}
    return docs


def main() -> int:
    args = build_parser().parse_args()
    date_key = parse_date_key(args.date_key)
    requested_group_ids = [value for value in coerce_str_list(args.group_ids.split(",")) if value]

    db = make_firestore_client(args.firestore_project, database=args.firestore_database)
    group_records = load_meeting_group_index_records(
        db,
        collection_name=args.meeting_group_index_collection,
        group_ids=requested_group_ids or None,
    )
    group_ids = sorted(group_records.keys())
    model_docs = _load_nested_docs(
        db,
        group_ids,
        prefix_collection=args.meeting_model_recs_collection,
        date_key=date_key,
        suffix="daily/{date_key}/sources/group_ranker",
        source_kind="model",
    ) if group_ids else {}
    daily_docs = _load_nested_docs(
        db,
        group_ids,
        prefix_collection=args.meeting_daily_recs_collection,
        date_key=date_key,
        suffix="days/{date_key}",
        source_kind="daily",
    ) if group_ids else {}

    group_status_counts: Counter[str] = Counter()
    model_status_counts: Counter[str] = Counter()
    daily_status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    for record in group_records.values():
        group_status_counts[record.index_status] += 1
        if record.skip_reason:
            reason_counts[record.skip_reason] += 1

    for group_id, doc in model_docs.items():
        status = str(doc.get("status") or "missing")
        model_status_counts[status] += 1
        reason = doc.get("skipReason")
        if isinstance(reason, str) and reason:
            reason_counts[reason] += 1
    missing_model_docs = len([group_id for group_id in group_ids if group_id not in model_docs])

    for group_id, doc in daily_docs.items():
        status = str(doc.get("status") or "missing")
        daily_status_counts[status] += 1
        reason = doc.get("skipReason")
        if isinstance(reason, str) and reason:
            reason_counts[reason] += 1
    missing_daily_docs = len([group_id for group_id in group_ids if group_id not in daily_docs])

    summary = {
        "dateKey": date_key,
        "meetingGroupIndex": {
            "ready": group_status_counts.get("ready", 0),
            "skipped": group_status_counts.get("skipped", 0),
            "total": len(group_records),
        },
        "meetingModelRecs": {
            "ready": model_status_counts.get("ready", 0),
            "empty": model_status_counts.get("empty", 0),
            "skipped": model_status_counts.get("skipped", 0),
            "missing": missing_model_docs,
        },
        "meetingDailyRecs": {
            "ready": daily_status_counts.get("ready", 0),
            "empty": daily_status_counts.get("empty", 0),
            "skipped": daily_status_counts.get("skipped", 0),
            "missing": missing_daily_docs,
        },
        "skipReasonHistogram": dict(reason_counts),
    }
    log_struct("info", "meeting_verify_summary", **summary)

    if args.write_verify_doc:
        doc_ref = db.collection(args.verify_collection).document(date_key)
        payload = dict(summary)
        payload["createdAt"] = firestore.SERVER_TIMESTAMP if firestore is not None else None
        doc_ref.set(payload, merge=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
