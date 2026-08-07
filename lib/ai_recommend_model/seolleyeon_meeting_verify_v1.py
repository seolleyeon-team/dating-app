#!/usr/bin/env python3
"""Verify exported meeting recommender artifacts with a strict production policy."""

from __future__ import annotations

import argparse
import os
import sys
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

try:
    from recsys.jobs.meeting_verify_policy import build_meeting_verification_summary
except ModuleNotFoundError:
    # Keep the existing direct local invocation working when the repository
    # root is not already on PYTHONPATH.
    _PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _PROJECT_ROOT not in sys.path:
        sys.path.insert(0, _PROJECT_ROOT)
    from recsys.jobs.meeting_verify_policy import build_meeting_verification_summary


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
    refs = [
        db.document(f"{prefix_collection}/{group_id}/{suffix.format(date_key=date_key)}")
        for group_id in group_ids
    ]
    docs: Dict[str, dict] = {}
    for snap in db.get_all(refs):
        if not snap.exists:
            continue
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
    model_docs = (
        _load_nested_docs(
            db,
            group_ids,
            prefix_collection=args.meeting_model_recs_collection,
            date_key=date_key,
            suffix="daily/{date_key}/sources/group_ranker",
            source_kind="model",
        )
        if group_ids
        else {}
    )
    daily_docs = (
        _load_nested_docs(
            db,
            group_ids,
            prefix_collection=args.meeting_daily_recs_collection,
            date_key=date_key,
            suffix="days/{date_key}",
            source_kind="daily",
        )
        if group_ids
        else {}
    )

    summary = build_meeting_verification_summary(
        date_key,
        group_records,
        model_docs,
        daily_docs,
    )
    log_struct("info", "meeting_verify_summary", **summary)

    if args.write_verify_doc:
        payload = dict(summary)
        payload["createdAt"] = firestore.SERVER_TIMESTAMP if firestore is not None else None
        doc_ref = db.collection(args.verify_collection).document(date_key)
        doc_ref.set(payload, merge=True)

    return 0 if summary.get("healthy", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
