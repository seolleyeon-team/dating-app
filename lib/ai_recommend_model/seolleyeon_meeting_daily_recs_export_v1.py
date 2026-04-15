#!/usr/bin/env python3
"""Export final meetingDailyRecs documents from group ranker outputs."""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Dict, List

from tqdm import tqdm

from seolleyeon_clip_embedder import SeolleyeonCLIPEmbedder
from seolleyeon_meeting_common_v1 import (
    DEFAULT_MEETING_DAILY_RECS_COLLECTION,
    DEFAULT_MEETING_GROUP_INDEX_COLLECTION,
    DEFAULT_MEETING_MODEL_RECS_COLLECTION,
    DEFAULT_PROFILE_INDEX_COLLECTION,
    DEFAULT_REC_EVENTS_COLLECTION,
    DEFAULT_USERS_COLLECTION,
    build_group_embedding_bundle,
    build_group_recent_action_maps,
    build_member_profile_view,
    coerce_str_list,
    firestore,
    group_diversity_similarity,
    list_recent_date_keys,
    load_documents_by_ids,
    load_meeting_group_index_records,
    load_rec_event_docs_by_date_keys,
    log_struct,
    make_firestore_client,
    normalize_scores,
    parse_date_key,
    select_primary_reason,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export final meeting daily recs from meeting group ranker outputs."
    )
    parser.add_argument("--firestore_project", required=True, type=str)
    parser.add_argument("--firestore_database", default=None, type=str)
    parser.add_argument("--date_key", required=True, type=str, help="YYYYMMDD (KST)")
    parser.add_argument("--meeting_group_index_collection", default=DEFAULT_MEETING_GROUP_INDEX_COLLECTION, type=str)
    parser.add_argument("--meeting_model_recs_collection", default=DEFAULT_MEETING_MODEL_RECS_COLLECTION, type=str)
    parser.add_argument("--meeting_daily_recs_collection", default=DEFAULT_MEETING_DAILY_RECS_COLLECTION, type=str)
    parser.add_argument("--profile_index_collection", default=DEFAULT_PROFILE_INDEX_COLLECTION, type=str)
    parser.add_argument("--users_collection", default=DEFAULT_USERS_COLLECTION, type=str)
    parser.add_argument("--rec_events_collection", default=DEFAULT_REC_EVENTS_COLLECTION, type=str)
    parser.add_argument("--group_ids", default="", type=str, help="Optional comma-separated actor groupIds")
    parser.add_argument("--topn", default=30, type=int)
    parser.add_argument("--clip_device", default="auto", type=str)
    parser.add_argument("--clip_dtype", default="auto", type=str)
    parser.add_argument("--clip_model", default=None, type=str)
    parser.add_argument("--max_photos_per_user", default=3, type=int)
    parser.add_argument("--exclude_recent_nope_days", default=14, type=int)
    parser.add_argument("--exclude_recent_exposure_days", default=3, type=int)
    parser.add_argument("--mmr_lambda", default=0.75, type=float)
    parser.add_argument("--exploit_lambda", default=0.90, type=float)
    parser.add_argument("--explore_pool_size", default=20, type=int)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--algorithm_version", default=None, type=str)
    return parser


def _parse_group_ids(raw: str) -> List[str]:
    return [value for value in coerce_str_list(raw.split(",")) if value]


def _load_ranker_docs(db, actor_group_ids: List[str], *, collection_name: str, date_key: str) -> Dict[str, dict]:
    refs = [
        db.document(f"{collection_name}/{group_id}/daily/{date_key}/sources/group_ranker")
        for group_id in actor_group_ids
    ]
    docs: Dict[str, dict] = {}
    for snap in db.get_all(refs):
        group_id = snap.reference.parent.parent.parent.parent.id
        docs[group_id] = snap.to_dict() or {}
    return docs


def _mmr_pick(remaining_ids, selected_ids, relevance_by_id, records, centroids, weight):
    best_id = None
    best_score = None
    for candidate_id in remaining_ids:
        relevance = relevance_by_id.get(candidate_id, 0.0)
        penalty = 0.0
        if selected_ids:
            penalty = max(
                group_diversity_similarity(records[candidate_id], records[selected_id], centroids=centroids)
                for selected_id in selected_ids
            )
        score = (weight * relevance) - ((1.0 - weight) * penalty)
        if best_score is None or score > best_score:
            best_score = score
            best_id = candidate_id
    return best_id


def _pick_explore(remaining_ids, selected_ids, relevance_by_id, records, centroids):
    best_id = None
    best_score = None
    for candidate_id in remaining_ids:
        relevance = relevance_by_id.get(candidate_id, 0.0)
        novelty = 1.0
        if selected_ids:
            novelty = 1.0 - max(
                group_diversity_similarity(records[candidate_id], records[selected_id], centroids=centroids)
                for selected_id in selected_ids
            )
        score = (0.45 * relevance) + (0.55 * novelty)
        if best_score is None or score > best_score:
            best_score = score
            best_id = candidate_id
    return best_id


def main() -> int:
    args = build_parser().parse_args()
    date_key = parse_date_key(args.date_key)
    algorithm_version = args.algorithm_version or f"meeting_daily_v1_{date_key}"

    db = make_firestore_client(args.firestore_project, database=args.firestore_database)
    ready_groups = load_meeting_group_index_records(
        db,
        collection_name=args.meeting_group_index_collection,
        only_ready=True,
    )
    actor_group_ids = _parse_group_ids(args.group_ids) or sorted(ready_groups.keys())
    actor_group_ids = [group_id for group_id in actor_group_ids if group_id in ready_groups]
    if not actor_group_ids:
        log_struct("warning", "meeting_daily_no_actor_groups")
        return 0

    ranker_docs = _load_ranker_docs(
        db,
        actor_group_ids,
        collection_name=args.meeting_model_recs_collection,
        date_key=date_key,
    )

    related_group_ids = set(actor_group_ids)
    for doc in ranker_docs.values():
        for item in doc.get("items", []) or []:
            if isinstance(item, dict) and item.get("groupId"):
                related_group_ids.add(str(item["groupId"]))
    records = load_meeting_group_index_records(
        db,
        collection_name=args.meeting_group_index_collection,
        group_ids=sorted(related_group_ids),
    )

    member_uids: List[str] = []
    for record in records.values():
        member_uids.extend(record.member_uids)
    member_uids = list(dict.fromkeys(member_uids))
    profile_docs = load_documents_by_ids(db, args.profile_index_collection, member_uids)
    user_docs = load_documents_by_ids(db, args.users_collection, member_uids)
    member_profiles = {
        uid: build_member_profile_view(uid, profile_docs.get(uid), user_docs.get(uid))
        for uid in member_uids
        if uid in profile_docs or uid in user_docs
    }

    from seolleyeon_meeting_common_v1 import MemberEmbeddingCache

    embedder = SeolleyeonCLIPEmbedder(
        model_id=args.clip_model,
        device=args.clip_device,
        dtype=args.clip_dtype,
    ) if args.clip_model else SeolleyeonCLIPEmbedder(device=args.clip_device, dtype=args.clip_dtype)
    cache = MemberEmbeddingCache(embedder, max_photos_per_user=int(args.max_photos_per_user))
    centroids = {}
    for group_id, record in tqdm(records.items(), desc="daily_group_embeddings"):
        bundle = build_group_embedding_bundle(group_id, record.member_uids, member_profiles, cache)
        if bundle.centroid is not None:
            centroids[group_id] = bundle.centroid

    recent_window = max(int(args.exclude_recent_nope_days), int(args.exclude_recent_exposure_days), 0)
    recent_event_docs = load_rec_event_docs_by_date_keys(
        db,
        collection_name=args.rec_events_collection,
        date_keys=list_recent_date_keys(date_key, recent_window),
    )
    recent_nope_map, recent_exposure_map = build_group_recent_action_maps(recent_event_docs)

    bw = None if args.dry_run else db.bulk_writer()
    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()

    for actor_group_id in tqdm(actor_group_ids, desc="meeting_daily"):
        doc_ref = db.document(
            f"{args.meeting_daily_recs_collection}/{actor_group_id}/days/{date_key}"
        )
        ranker_doc = ranker_docs.get(actor_group_id, {})
        if ranker_doc.get("status") != "ready":
            status = ranker_doc.get("status") or "skipped"
            skip_reason = ranker_doc.get("skipReason") or "missing_group_ranker_doc"
            payload = {
                "status": status,
                "algorithmVersion": algorithm_version,
                "candidateGroupIds": [],
                "candidates": [],
                "createdAt": firestore.SERVER_TIMESTAMP if firestore is not None else None,
                "skipReason": skip_reason,
            }
            status_counts[status] += 1
            reason_counts[skip_reason] += 1
            if bw is not None:
                bw.set(doc_ref, payload, merge=True)
            continue

        raw_items = [item for item in ranker_doc.get("items", []) or [] if isinstance(item, dict)]
        filtered_items = []
        filter_reasons: Counter[str] = Counter()
        for item in raw_items:
            group_id = str(item.get("groupId", ""))
            if not group_id:
                continue
            if int(args.exclude_recent_nope_days) > 0 and group_id in recent_nope_map.get(actor_group_id, set()):
                filter_reasons["recent_nope_exclusion"] += 1
                continue
            if int(args.exclude_recent_exposure_days) > 0 and group_id in recent_exposure_map.get(actor_group_id, set()):
                filter_reasons["recent_exposure_exclusion"] += 1
                continue
            filtered_items.append(item)

        if not filtered_items:
            skip_reason = select_primary_reason(filter_reasons, fallback="no_candidate_after_filters")
            payload = {
                "status": "empty",
                "algorithmVersion": algorithm_version,
                "candidateGroupIds": [],
                "candidates": [],
                "createdAt": firestore.SERVER_TIMESTAMP if firestore is not None else None,
                "skipReason": skip_reason,
            }
            status_counts["empty"] += 1
            reason_counts[skip_reason] += 1
            if bw is not None:
                bw.set(doc_ref, payload, merge=True)
            continue

        usable_items = [
            item
            for item in filtered_items
            if str(item.get("groupId", "")) in records
        ]
        candidate_ids = [str(item["groupId"]) for item in usable_items]
        relevance_values = normalize_scores([float(item.get("score", 0.0)) for item in usable_items])
        relevance_by_id = {
            candidate_id: relevance
            for candidate_id, relevance in zip(candidate_ids, relevance_values)
        }
        item_by_group_id = {
            str(item["groupId"]): item
            for item in usable_items
            if str(item.get("groupId", "")) in records
        }
        if not candidate_ids:
            skip_reason = "no_candidate_after_filters"
            payload = {
                "status": "empty",
                "algorithmVersion": algorithm_version,
                "candidateGroupIds": [],
                "candidates": [],
                "createdAt": firestore.SERVER_TIMESTAMP if firestore is not None else None,
                "skipReason": skip_reason,
            }
            status_counts["empty"] += 1
            reason_counts[skip_reason] += 1
            if bw is not None:
                bw.set(doc_ref, payload, merge=True)
            continue

        selected_ids: List[str] = []
        explore_ids = set()
        while len(selected_ids) < min(2, len(candidate_ids)):
            next_id = _mmr_pick(
                [candidate_id for candidate_id in candidate_ids if candidate_id not in selected_ids],
                selected_ids,
                relevance_by_id,
                records,
                centroids,
                float(args.exploit_lambda),
            )
            if next_id is None:
                break
            selected_ids.append(next_id)

        remaining_for_explore = [
            candidate_id
            for candidate_id in candidate_ids
            if candidate_id not in selected_ids
        ][: max(1, int(args.explore_pool_size))]
        if len(selected_ids) < int(args.topn) and remaining_for_explore:
            explore_id = _pick_explore(
                remaining_for_explore,
                selected_ids,
                relevance_by_id,
                records,
                centroids,
            )
            if explore_id is not None and explore_id not in selected_ids:
                selected_ids.append(explore_id)
                explore_ids.add(explore_id)

        while len(selected_ids) < int(args.topn):
            remaining = [candidate_id for candidate_id in candidate_ids if candidate_id not in selected_ids]
            if not remaining:
                break
            next_id = _mmr_pick(
                remaining,
                selected_ids,
                relevance_by_id,
                records,
                centroids,
                float(args.mmr_lambda),
            )
            if next_id is None:
                break
            selected_ids.append(next_id)

        candidates = []
        for position, group_id in enumerate(selected_ids, start=1):
            source_item = item_by_group_id[group_id]
            candidates.append(
                {
                    "groupId": group_id,
                    "position": position,
                    "isExplore": group_id in explore_ids,
                    "scoreTotal": float(source_item.get("score", 0.0)),
                    "scoreComponents": source_item.get("scoreComponents", {}),
                    "matchedPairs": source_item.get("matchedPairs", []),
                }
            )

        status_counts["ready"] += 1
        payload = {
            "status": "ready",
            "algorithmVersion": algorithm_version,
            "candidateGroupIds": [candidate["groupId"] for candidate in candidates],
            "candidates": candidates,
            "createdAt": firestore.SERVER_TIMESTAMP if firestore is not None else None,
        }
        if bw is not None:
            bw.set(doc_ref, payload, merge=True)

    if bw is not None:
        bw.close()

    log_struct(
        "info",
        "meeting_daily_export_done",
        algorithmVersion=algorithm_version,
        dryRun=bool(args.dry_run),
        ready=status_counts.get("ready", 0),
        empty=status_counts.get("empty", 0),
        skipped=status_counts.get("skipped", 0),
        reasonCounts=dict(reason_counts),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
