"""Verify pipeline results in Firestore.

Checks modelRecs/{uid}/daily/{dateKey}/sources/{algo} for each source
and reports coverage, item counts, and health status.
"""
from __future__ import annotations

import time
from typing import Optional

from google.cloud import firestore


def run_verify(
    *,
    project: str,
    date_key: str,
    database: Optional[str] = None,
    sources: Optional[list[str]] = None,
    logger=None,
) -> dict:
    """Check modelRecs for completeness.

    Returns dict with per-source stats and overall health flag.
    """
    if sources is None:
        sources = ["clip", "svd", "knn", "rrf"]

    t0 = time.time()
    db = firestore.Client(project=project, database=database)

    user_ids = [doc.id for doc in db.collection("modelRecs").list_documents()]
    total_users = len(user_ids)

    if logger:
        logger.info(
            f"Verify: {total_users} users in modelRecs",
            extra={"count": total_users, "date_key": date_key},
        )

    source_stats: dict[str, dict] = {}

    for source in sources:
        ready = 0
        empty = 0
        missing = 0
        total_items = 0
        min_items = float("inf")
        max_items = 0

        for uid in user_ids:
            doc_ref = db.document(
                f"modelRecs/{uid}/daily/{date_key}/sources/{source}"
            )
            try:
                snap = doc_ref.get()
            except Exception:
                missing += 1
                continue

            if not snap.exists:
                missing += 1
                continue

            data = snap.to_dict() or {}
            status = data.get("status")
            items = data.get("items", [])
            n = len(items) if isinstance(items, list) else 0

            if status == "ready" and n > 0:
                ready += 1
                total_items += n
                min_items = min(min_items, n)
                max_items = max(max_items, n)
            else:
                empty += 1

        avg_items = round(total_items / ready, 1) if ready > 0 else 0
        if min_items == float("inf"):
            min_items = 0

        coverage = round(ready / total_users * 100, 1) if total_users > 0 else 0.0

        stats = {
            "ready": ready,
            "empty": empty,
            "missing": missing,
            "total_items": total_items,
            "avg_items": avg_items,
            "min_items": min_items,
            "max_items": max_items,
            "coverage_pct": coverage,
        }
        source_stats[source] = stats

        if logger:
            logger.info(
                f"  {source}: ready={ready}, empty={empty}, missing={missing}, "
                f"coverage={coverage}%, avg_items={avg_items}",
                extra={"detail": {source: stats}, "date_key": date_key},
            )

    elapsed = time.time() - t0

    result: dict = {
        "total_users": total_users,
        "date_key": date_key,
        "sources": source_stats,
        "elapsed_s": round(elapsed, 1),
    }

    rrf = source_stats.get("rrf", {})
    if rrf.get("ready", 0) == 0:
        if logger:
            logger.warning(
                "No RRF results found — pipeline may have failed.",
                extra={"date_key": date_key},
            )
        result["healthy"] = False
    else:
        result["healthy"] = True

    # Diagnostic hints: which source has lowest coverage
    if source_stats:
        weakest = min(source_stats, key=lambda s: source_stats[s]["coverage_pct"])
        weakest_pct = source_stats[weakest]["coverage_pct"]
        if weakest_pct < 50 and logger:
            logger.warning(
                f"Lowest coverage: {weakest}={weakest_pct}%. "
                f"Check if min_pos_interactions filter is too aggressive, "
                f"or profileIndex is incomplete.",
                extra={"date_key": date_key},
            )

    if logger:
        logger.info(
            f"Verify complete in {elapsed:.1f}s. Healthy={result['healthy']}",
            extra={"duration_s": round(elapsed, 1), "date_key": date_key},
        )

    return result
