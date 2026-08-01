#!/usr/bin/env python3
"""Offline evaluation for Seolleyeon meeting recommender v1."""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from datetime import timedelta
from typing import Dict, List, Mapping, Sequence, Set

from seolleyeon_meeting_common_v1 import (
    DEFAULT_MEETING_DAILY_RECS_COLLECTION,
    DEFAULT_MEETING_MODEL_RECS_COLLECTION,
    DEFAULT_MEETING_POSITIVE_EVENTS,
    DEFAULT_MEETING_NEGATIVE_EVENTS,
    DEFAULT_REC_EVENTS_COLLECTION,
    coerce_str_list,
    date_key_to_date,
    firestore,
    load_rec_event_docs_by_date_keys,
    log_struct,
    make_date_key,
    make_firestore_client,
    parse_date_key,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate meeting recommender outputs offline.")
    parser.add_argument("--firestore_project", required=True, type=str)
    parser.add_argument("--firestore_database", default=None, type=str)
    parser.add_argument("--date_key", required=True, type=str, help="YYYYMMDD (KST)")
    parser.add_argument("--source_kind", default="daily", choices=["daily", "model"])
    parser.add_argument("--meeting_model_recs_collection", default=DEFAULT_MEETING_MODEL_RECS_COLLECTION, type=str)
    parser.add_argument("--meeting_daily_recs_collection", default=DEFAULT_MEETING_DAILY_RECS_COLLECTION, type=str)
    parser.add_argument("--rec_events_collection", default=DEFAULT_REC_EVENTS_COLLECTION, type=str)
    parser.add_argument("--group_ids", default="", type=str)
    parser.add_argument("--lookahead_days", default=14, type=int)
    parser.add_argument("--ks", default="5,10,20", type=str)
    parser.add_argument("--write_eval_doc", action="store_true")
    parser.add_argument("--eval_collection", default="meetingEvalRuns", type=str)
    return parser


def _parse_group_ids(raw: str) -> List[str]:
    return [value for value in coerce_str_list(raw.split(",")) if value]


def _parse_ks(raw: str) -> List[int]:
    return sorted({int(value) for value in coerce_str_list(raw.split(",")) if int(value) > 0})


def _load_eval_docs(db, actor_group_ids: List[str], *, date_key: str, collection_name: str, source_kind: str) -> Dict[str, dict]:
    if source_kind == "daily":
        refs = [db.document(f"{collection_name}/{group_id}/days/{date_key}") for group_id in actor_group_ids]
    else:
        refs = [db.document(f"{collection_name}/{group_id}/daily/{date_key}/sources/group_ranker") for group_id in actor_group_ids]
    docs: Dict[str, dict] = {}
    for snap in db.get_all(refs):
        if source_kind == "daily":
            group_id = snap.reference.parent.parent.id
        else:
            group_id = snap.reference.parent.parent.parent.parent.id
        docs[group_id] = snap.to_dict() or {}
    return docs


def _extract_ranked_group_ids(source_kind: str, doc: Mapping[str, object]) -> List[str]:
    if source_kind == "daily":
        candidates = doc.get("candidates", []) or []
        return [
            str(item["groupId"])
            for item in candidates
            if isinstance(item, dict) and item.get("groupId")
        ]
    items = doc.get("items", []) or []
    return [
        str(item["groupId"])
        for item in items
        if isinstance(item, dict) and item.get("groupId")
    ]


def _future_date_keys(date_key: str, lookahead_days: int) -> List[str]:
    base = date_key_to_date(date_key)
    return [make_date_key(base + timedelta(days=offset)) for offset in range(max(1, int(lookahead_days) + 1))]


def _build_group_labels(event_docs: Sequence[Mapping[str, object]]):
    positive_by_actor: Dict[str, Set[str]] = defaultdict(set)
    negative_by_actor: Dict[str, Set[str]] = defaultdict(set)
    skipped_missing_actor_group = 0
    for event_doc in event_docs:
        if str(event_doc.get("targetType") or "") != "meeting_group":
            continue
        context = event_doc.get("context")
        context = context if isinstance(context, Mapping) else {}
        actor_group_id = str(context.get("actorGroupId") or "")
        if not actor_group_id:
            skipped_missing_actor_group += 1
            continue
        target_group_id = str(context.get("targetGroupId") or event_doc.get("targetId") or "")
        if not target_group_id:
            continue
        event_type = str(event_doc.get("type") or event_doc.get("eventType") or "")
        if event_type in DEFAULT_MEETING_POSITIVE_EVENTS:
            positive_by_actor[actor_group_id].add(target_group_id)
        if event_type in DEFAULT_MEETING_NEGATIVE_EVENTS:
            negative_by_actor[actor_group_id].add(target_group_id)
    return positive_by_actor, negative_by_actor, skipped_missing_actor_group


def _ndcg_at_k(ranked: Sequence[str], positives: Set[str], k: int) -> float:
    dcg = 0.0
    for idx, group_id in enumerate(ranked[:k], start=1):
        if group_id in positives:
            dcg += 1.0 / math.log2(idx + 1.0)
    ideal_hits = min(len(positives), k)
    if ideal_hits <= 0:
        return 0.0
    idcg = sum(1.0 / math.log2(idx + 1.0) for idx in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def main() -> int:
    args = build_parser().parse_args()
    date_key = parse_date_key(args.date_key)
    ks = _parse_ks(args.ks)
    if not ks:
        raise ValueError("--ks must contain at least one positive integer")

    db = make_firestore_client(args.firestore_project, database=args.firestore_database)
    actor_group_ids = _parse_group_ids(args.group_ids)
    if not actor_group_ids:
        # Evaluate only groups that have a document for the requested source kind on the given date.
        actor_group_ids = []

    docs = _load_eval_docs(
        db,
        actor_group_ids,
        date_key=date_key,
        collection_name=args.meeting_daily_recs_collection if args.source_kind == "daily" else args.meeting_model_recs_collection,
        source_kind=args.source_kind,
    ) if actor_group_ids else {}

    if not actor_group_ids:
        if args.source_kind == "daily":
            for snap in db.collection(args.meeting_daily_recs_collection).list_documents():
                actor_group_ids.append(snap.id)
        else:
            for snap in db.collection(args.meeting_model_recs_collection).list_documents():
                actor_group_ids.append(snap.id)
        docs = _load_eval_docs(
            db,
            actor_group_ids,
            date_key=date_key,
            collection_name=args.meeting_daily_recs_collection if args.source_kind == "daily" else args.meeting_model_recs_collection,
            source_kind=args.source_kind,
        )

    ranked_by_actor = {
        group_id: _extract_ranked_group_ids(args.source_kind, doc)
        for group_id, doc in docs.items()
        if doc.get("status") == "ready"
    }
    event_docs = load_rec_event_docs_by_date_keys(
        db,
        collection_name=args.rec_events_collection,
        date_keys=_future_date_keys(date_key, int(args.lookahead_days)),
    )
    positive_by_actor, negative_by_actor, skipped_missing_actor_group = _build_group_labels(event_docs)

    metrics = {}
    actors_with_recs = len(ranked_by_actor)
    for k in ks:
        hit_sum = 0.0
        recall_sum = 0.0
        mrr_sum = 0.0
        ndcg_sum = 0.0
        negative_rate_sum = 0.0
        negative_denominator = 0

        for actor_group_id, ranked in ranked_by_actor.items():
            topk = ranked[:k]
            positives = positive_by_actor.get(actor_group_id, set())
            negatives = negative_by_actor.get(actor_group_id, set())
            if topk:
                negative_rate_sum += len([group_id for group_id in topk if group_id in negatives]) / float(len(topk))
                negative_denominator += 1
            if not positives:
                continue
            hits = [idx for idx, group_id in enumerate(topk, start=1) if group_id in positives]
            hit_sum += 1.0 if hits else 0.0
            recall_sum += len(hits) / float(len(positives))
            mrr_sum += (1.0 / hits[0]) if hits else 0.0
            ndcg_sum += _ndcg_at_k(topk, positives, k)

        positive_denominator = max(1, len([actor for actor, positives in positive_by_actor.items() if positives and actor in ranked_by_actor]))
        metrics[f"HitRate@{k}"] = round(hit_sum / positive_denominator, 6)
        metrics[f"Recall@{k}"] = round(recall_sum / positive_denominator, 6)
        metrics[f"MRR@{k}"] = round(mrr_sum / positive_denominator, 6)
        metrics[f"NDCG@{k}"] = round(ndcg_sum / positive_denominator, 6)
        metrics[f"NegativeRate@{k}"] = round(
            negative_rate_sum / max(1, negative_denominator),
            6,
        )

    summary = {
        "dateKey": date_key,
        "sourceKind": args.source_kind,
        "lookaheadDays": int(args.lookahead_days),
        "actorsWithRecs": actors_with_recs,
        "actorsWithPositiveLabels": len([actor for actor, positives in positive_by_actor.items() if positives and actor in ranked_by_actor]),
        "skippedMissingActorGroupIdEvents": skipped_missing_actor_group,
        "metrics": metrics,
    }
    log_struct("info", "meeting_eval_summary", **summary)

    if args.write_eval_doc:
        doc_ref = db.collection(args.eval_collection).document(f"{args.source_kind}_{date_key}")
        payload = dict(summary)
        payload["createdAt"] = firestore.SERVER_TIMESTAMP if firestore is not None else None
        doc_ref.set(payload, merge=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
