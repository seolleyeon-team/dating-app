#!/usr/bin/env python3
"""Export group-level meeting recommendations for Seolleyeon meeting recommender v1."""

from __future__ import annotations

import argparse
from collections import Counter
from typing import Dict, List, Optional, Set

import numpy as np
from tqdm import tqdm

from seolleyeon_clip_embedder import SeolleyeonCLIPEmbedder
from seolleyeon_meeting_common_v1 import (
    DEFAULT_MEETING_GROUP_INDEX_COLLECTION,
    DEFAULT_MEETING_MODEL_RECS_COLLECTION,
    DEFAULT_MODEL_RECS_COLLECTION,
    DEFAULT_PROFILE_INDEX_COLLECTION,
    DEFAULT_REC_EVENTS_COLLECTION,
    DEFAULT_USERS_COLLECTION,
    build_cross_user_block_pairs,
    build_group_embedding_bundle,
    build_group_recent_action_maps,
    build_member_profile_view,
    coerce_str_list,
    compute_group_score,
    firestore,
    has_cross_block_pair,
    list_recent_date_keys,
    load_documents_by_ids,
    load_meeting_group_index_records,
    load_rec_event_docs_by_date_keys,
    load_user_source_lookups,
    log_struct,
    make_firestore_client,
    parse_date_key,
    select_primary_reason,
    shares_member,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export meeting group ranker results for Seolleyeon meeting recommender v1."
    )
    parser.add_argument("--firestore_project", required=True, type=str)
    parser.add_argument("--firestore_database", default=None, type=str)
    parser.add_argument("--date_key", required=True, type=str, help="YYYYMMDD (KST)")
    parser.add_argument("--meeting_group_index_collection", default=DEFAULT_MEETING_GROUP_INDEX_COLLECTION, type=str)
    parser.add_argument("--meeting_model_recs_collection", default=DEFAULT_MEETING_MODEL_RECS_COLLECTION, type=str)
    parser.add_argument("--model_recs_collection", default=DEFAULT_MODEL_RECS_COLLECTION, type=str)
    parser.add_argument("--profile_index_collection", default=DEFAULT_PROFILE_INDEX_COLLECTION, type=str)
    parser.add_argument("--users_collection", default=DEFAULT_USERS_COLLECTION, type=str)
    parser.add_argument("--rec_events_collection", default=DEFAULT_REC_EVENTS_COLLECTION, type=str)
    parser.add_argument("--group_ids", default="", type=str, help="Optional comma-separated actor groupIds")
    parser.add_argument("--candidate_pool_size", default=150, type=int)
    parser.add_argument("--candidate_pool_oversample", default=3, type=int)
    parser.add_argument("--topn", default=150, type=int)
    parser.add_argument("--clip_device", default="auto", type=str)
    parser.add_argument("--clip_dtype", default="auto", type=str)
    parser.add_argument("--clip_model", default=None, type=str)
    parser.add_argument("--max_photos_per_user", default=3, type=int)
    parser.add_argument("--manner_min_threshold", default=33.0, type=float)
    parser.add_argument("--allow_missing_region", dest="allow_missing_region", action="store_true")
    parser.add_argument("--disallow_missing_region", dest="allow_missing_region", action="store_false")
    parser.set_defaults(allow_missing_region=True)
    parser.add_argument("--exclude_recent_nope_days", default=14, type=int)
    parser.add_argument("--exclude_recent_exposure_days", default=3, type=int)
    parser.add_argument("--block_history_days", default=365, type=int)
    parser.add_argument("--source_rank_mode", default="reciprocal", choices=["reciprocal", "linear"])
    parser.add_argument("--source_topn_assumption", default=300, type=int)
    parser.add_argument("--source_rank_offset", default=60.0, type=float)
    parser.add_argument("--source_raw_score_weight", default=0.0, type=float)
    parser.add_argument("--pair_clip_weight", default=0.80, type=float)
    parser.add_argument("--pair_svd_weight", default=0.15, type=float)
    parser.add_argument("--pair_knn_weight", default=0.05, type=float)
    parser.add_argument("--weight_assignment_mean", default=0.45, type=float)
    parser.add_argument("--weight_balance", default=0.15, type=float)
    parser.add_argument("--weight_min_pair", default=0.10, type=float)
    parser.add_argument("--weight_availability", default=0.10, type=float)
    parser.add_argument("--weight_tag_overlap", default=0.10, type=float)
    parser.add_argument("--weight_trust", default=0.10, type=float)
    parser.add_argument("--weight_region_compatibility", default=0.0, type=float)
    parser.add_argument("--balance_std_target", default=0.20, type=float)
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--algorithm_version", default=None, type=str)
    return parser


def _parse_group_ids(raw: str) -> List[str]:
    if not raw:
        return []
    return [value for value in coerce_str_list(raw.split(",")) if value]


def _prepare_group_bundles(args: argparse.Namespace, ready_groups, member_profiles):
    embedder = SeolleyeonCLIPEmbedder(
        model_id=args.clip_model,
        device=args.clip_device,
        dtype=args.clip_dtype,
    ) if args.clip_model else SeolleyeonCLIPEmbedder(device=args.clip_device, dtype=args.clip_dtype)
    from seolleyeon_meeting_common_v1 import MemberEmbeddingCache

    cache = MemberEmbeddingCache(embedder, max_photos_per_user=int(args.max_photos_per_user))
    bundles = {}
    for group_id, record in tqdm(ready_groups.items(), desc="group_embeddings"):
        bundles[group_id] = build_group_embedding_bundle(
            group_id,
            record.member_uids,
            member_profiles,
            cache,
        )
    return bundles


def main() -> int:
    args = build_parser().parse_args()
    date_key = parse_date_key(args.date_key)
    algorithm_version = args.algorithm_version or f"meeting_group_ranker_v1_{date_key}"

    db = make_firestore_client(args.firestore_project, database=args.firestore_database)
    requested_actor_group_ids = _parse_group_ids(args.group_ids)

    ready_groups = load_meeting_group_index_records(
        db,
        collection_name=args.meeting_group_index_collection,
        only_ready=True,
    )
    if not ready_groups:
        log_struct("warning", "meeting_ranker_no_ready_groups")
        return 0

    actor_group_ids = requested_actor_group_ids or sorted(ready_groups.keys())
    actor_group_ids = [group_id for group_id in actor_group_ids if group_id in ready_groups]
    if not actor_group_ids:
        log_struct("warning", "meeting_ranker_no_actor_groups", requested=requested_actor_group_ids)
        return 0

    all_member_uids: List[str] = []
    for record in ready_groups.values():
        all_member_uids.extend(record.member_uids)
    all_member_uids = list(dict.fromkeys(all_member_uids))

    profile_docs = load_documents_by_ids(db, args.profile_index_collection, all_member_uids)
    user_docs = load_documents_by_ids(db, args.users_collection, all_member_uids)
    member_profiles = {
        uid: build_member_profile_view(uid, profile_docs.get(uid), user_docs.get(uid))
        for uid in all_member_uids
        if uid in profile_docs or uid in user_docs
    }
    group_bundles = _prepare_group_bundles(args, ready_groups, member_profiles)
    centroid_group_ids = [group_id for group_id, bundle in group_bundles.items() if bundle.centroid is not None]
    centroid_matrix = np.stack([group_bundles[group_id].centroid for group_id in centroid_group_ids], axis=0) if centroid_group_ids else np.zeros((0, 0), dtype=np.float32)
    similarity_matrix = centroid_matrix @ centroid_matrix.T if centroid_group_ids else np.zeros((0, 0), dtype=np.float32)
    centroid_index = {group_id: idx for idx, group_id in enumerate(centroid_group_ids)}

    svd_lookups = load_user_source_lookups(
        db,
        all_member_uids,
        date_key=date_key,
        source_name="svd",
        model_recs_collection=args.model_recs_collection,
        rank_mode=args.source_rank_mode,
        topn_assumption=args.source_topn_assumption,
        reciprocal_offset=args.source_rank_offset,
        raw_score_weight=args.source_raw_score_weight,
    )
    knn_lookups = load_user_source_lookups(
        db,
        all_member_uids,
        date_key=date_key,
        source_name="knn",
        model_recs_collection=args.model_recs_collection,
        rank_mode=args.source_rank_mode,
        topn_assumption=args.source_topn_assumption,
        reciprocal_offset=args.source_rank_offset,
        raw_score_weight=args.source_raw_score_weight,
    )

    recent_window = max(int(args.exclude_recent_nope_days), int(args.exclude_recent_exposure_days), 0)
    recent_event_docs = load_rec_event_docs_by_date_keys(
        db,
        collection_name=args.rec_events_collection,
        date_keys=list_recent_date_keys(date_key, recent_window),
    )
    recent_nope_map, recent_exposure_map = build_group_recent_action_maps(recent_event_docs)
    blocked_pairs = build_cross_user_block_pairs(
        load_rec_event_docs_by_date_keys(
            db,
            collection_name=args.rec_events_collection,
            date_keys=list_recent_date_keys(date_key, int(args.block_history_days)),
        ),
        allowed_user_ids=set(all_member_uids),
    )

    bw = None if args.dry_run else db.bulk_writer()
    status_counter: Counter[str] = Counter()
    skip_reason_counter: Counter[str] = Counter()

    for actor_group_id in tqdm(actor_group_ids, desc="meeting_ranker"):
        actor_record = ready_groups[actor_group_id]
        actor_bundle = group_bundles.get(actor_group_id)
        doc_ref = db.document(
            f"{args.meeting_model_recs_collection}/{actor_group_id}/daily/{date_key}/sources/group_ranker"
        )

        if actor_bundle is None or actor_bundle.centroid is None:
            payload = {
                "status": "skipped",
                "algorithmVersion": algorithm_version,
                "generatedAt": firestore.SERVER_TIMESTAMP if firestore is not None else None,
                "topN": 0,
                "items": [],
                "model": {"type": "meeting_group_ranker", "version": algorithm_version},
                "skipReason": "missing_embeddings",
            }
            status_counter["skipped"] += 1
            skip_reason_counter["missing_embeddings"] += 1
            if bw is not None:
                bw.set(doc_ref, payload, merge=True)
            continue

        actor_idx = centroid_index.get(actor_group_id)
        reason_counts: Counter[str] = Counter()
        if actor_idx is None:
            reason_counts["missing_embeddings"] += 1
            candidate_group_ids: List[str] = []
        else:
            order = np.argsort(-similarity_matrix[actor_idx]).tolist()
            candidate_group_ids = []
            pool_limit = max(1, int(args.candidate_pool_size) * max(1, int(args.candidate_pool_oversample)))
            for idx in order:
                candidate_group_id = centroid_group_ids[idx]
                if candidate_group_id == actor_group_id:
                    continue
                candidate_record = ready_groups[candidate_group_id]
                if shares_member(actor_record.member_uids, candidate_record.member_uids):
                    continue
                candidate_group_ids.append(candidate_group_id)
                if len(candidate_group_ids) >= pool_limit:
                    break

        scored_items = []
        for candidate_group_id in candidate_group_ids:
            candidate_record = ready_groups[candidate_group_id]
            candidate_bundle = group_bundles.get(candidate_group_id)
            if candidate_bundle is None or candidate_bundle.centroid is None:
                reason_counts["missing_embeddings"] += 1
                continue
            if int(args.exclude_recent_nope_days) > 0 and candidate_group_id in recent_nope_map.get(actor_group_id, set()):
                reason_counts["recent_nope_exclusion"] += 1
                continue
            if int(args.exclude_recent_exposure_days) > 0 and candidate_group_id in recent_exposure_map.get(actor_group_id, set()):
                reason_counts["recent_exposure_exclusion"] += 1
                continue
            from seolleyeon_meeting_common_v1 import availability_overlap_score, best_group_assignment

            overlap_count, _availability = availability_overlap_score(
                actor_record.availability_slot_ids,
                candidate_record.availability_slot_ids,
            )
            if overlap_count <= 0:
                reason_counts["no_availability_overlap"] += 1
                continue
            if has_cross_block_pair(actor_record.member_uids, candidate_record.member_uids, blocked_pairs):
                reason_counts["cross_block_or_report"] += 1
                continue

            assignment = best_group_assignment(
                actor_record.member_uids,
                candidate_record.member_uids,
                member_profiles,
                actor_bundle.member_vectors,
                candidate_bundle.member_vectors,
                actor_bundle.centroid,
                candidate_bundle.centroid,
                svd_lookups=svd_lookups,
                knn_lookups=knn_lookups,
                clip_weight=float(args.pair_clip_weight),
                svd_weight=float(args.pair_svd_weight),
                knn_weight=float(args.pair_knn_weight),
                balance_std_target=float(args.balance_std_target),
            )
            if assignment is None:
                reason_counts["no_reciprocal_assignment"] += 1
                continue

            score_total, score_components, region_ok = compute_group_score(
                actor_record,
                candidate_record,
                assignment,
                weight_assignment_mean=float(args.weight_assignment_mean),
                weight_balance=float(args.weight_balance),
                weight_min_pair=float(args.weight_min_pair),
                weight_availability=float(args.weight_availability),
                weight_tag_overlap=float(args.weight_tag_overlap),
                weight_trust=float(args.weight_trust),
                weight_region_compatibility=float(args.weight_region_compatibility),
                balance_std_target=float(args.balance_std_target),
                allow_missing_region=bool(args.allow_missing_region),
            )
            if not region_ok:
                reason_counts["region_incompatible"] += 1
                continue
            scored_items.append(
                {
                    "groupId": candidate_group_id,
                    "score": score_total,
                    "matchedPairs": [pair.to_document() for pair in assignment.matched_pairs],
                    "scoreComponents": score_components,
                    "candidateMeta": {
                        "memberUids": candidate_record.member_uids,
                        "regionId": candidate_record.region_id,
                        "primaryUniversityId": candidate_record.primary_university_id,
                    },
                }
            )

        scored_items.sort(
            key=lambda item: (
                -float(item["score"]),
                -float(item["scoreComponents"]["minPair"]),
                -float(item["scoreComponents"]["balance"]),
            )
        )
        items = []
        for rank, item in enumerate(scored_items[: int(args.topn)], start=1):
            item["rank"] = rank
            items.append(item)

        if items:
            status = "ready"
            skip_reason = None
        else:
            status = "empty"
            skip_reason = select_primary_reason(reason_counts, fallback="no_candidate_after_filters")
            skip_reason_counter[skip_reason] += 1

        status_counter[status] += 1
        payload = {
            "status": status,
            "algorithmVersion": algorithm_version,
            "topN": len(items),
            "items": items,
            "generatedAt": firestore.SERVER_TIMESTAMP if firestore is not None else None,
            "model": {
                "type": "meeting_group_ranker",
                "version": algorithm_version,
                "candidatePoolSize": int(args.candidate_pool_size),
                "candidatePoolOversample": int(args.candidate_pool_oversample),
                "pairWeights": {
                    "clip": float(args.pair_clip_weight),
                    "svd": float(args.pair_svd_weight),
                    "knn": float(args.pair_knn_weight),
                },
                "groupWeights": {
                    "assignmentMean": float(args.weight_assignment_mean),
                    "balance": float(args.weight_balance),
                    "minPair": float(args.weight_min_pair),
                    "availability": float(args.weight_availability),
                    "tagOverlap": float(args.weight_tag_overlap),
                    "trust": float(args.weight_trust),
                    "regionCompatibility": float(args.weight_region_compatibility),
                },
                "sourceRankMode": args.source_rank_mode,
            },
            "skipReason": skip_reason,
            "candidateStats": {
                "candidatePool": len(candidate_group_ids),
                "survived": len(items),
                "reasonCounts": dict(reason_counts),
            },
        }
        if bw is not None:
            bw.set(doc_ref, payload, merge=True)

    if bw is not None:
        bw.close()

    log_struct(
        "info",
        "meeting_ranker_export_done",
        algorithmVersion=algorithm_version,
        dryRun=bool(args.dry_run),
        actorGroups=len(actor_group_ids),
        ready=status_counter.get("ready", 0),
        empty=status_counter.get("empty", 0),
        skipped=status_counter.get("skipped", 0),
        emptyReasonCounts=dict(skip_reason_counter),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
