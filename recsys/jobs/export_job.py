"""Export Firestore recEvents to GCS as CSV.

Reads recEvents/{userId}/events subcollection and writes a CSV to GCS
that SVD/KNN can consume via --events_csv.

포함: 프로필 카드(profile_card) + AI 취향(ai_preference) 스와이프 기록
CSV columns: user_id, item_id, event, ts, source
  - source: profile_card | ai_preference (surface 필드)
"""
from __future__ import annotations

import csv
import io
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from .common import KST, gcs_upload_string


def run_export(
    *,
    project: str,
    bucket: str,
    prefix: str,
    date_key: str,
    database: Optional[str] = None,
    lookback_days: int = 120,
    limit_users: Optional[int] = None,
    dry_run: bool = False,
    logger=None,
) -> dict:
    """Export Firestore recEvents → GCS CSV.

    Returns dict with export stats.
    """
    t0 = time.time()

    yyyy, mm, dd = int(date_key[:4]), int(date_key[4:6]), int(date_key[6:8])
    end_kst = datetime(yyyy, mm, dd, 23, 59, 59, tzinfo=KST)
    start_utc = (end_kst - timedelta(days=lookback_days)).astimezone(timezone.utc)
    end_utc = end_kst.astimezone(timezone.utc)

    # Flutter rec_event_service는 createdAt을 ISO8601 문자열로 저장함.
    # Firestore 쿼리는 저장 타입과 일치해야 하므로 문자열로 변환.
    def _to_iso8601_str(dt: datetime) -> str:
        utc = dt.astimezone(timezone.utc)
        return utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    start_str = _to_iso8601_str(start_utc)
    end_str = _to_iso8601_str(end_utc)

    if logger:
        logger.info(
            f"Export start: lookback={lookback_days}d, "
            f"range=[{start_str}, {end_str})",
            extra={"date_key": date_key},
        )

    db = firestore.Client(project=project, database=database)

    user_doc_refs = list(db.collection("recEvents").list_documents())
    if limit_users:
        user_doc_refs = user_doc_refs[:limit_users]

    rows: list[list[str]] = []
    users_scanned = 0
    skipped = 0

    # Per-event-type counters for diagnostics
    event_counts: dict[str, int] = {}

    for user_doc_ref in user_doc_refs:
        users_scanned += 1
        q = user_doc_ref.collection("events")
        q = q.where(filter=FieldFilter("createdAt", ">=", start_str))
        q = q.where(filter=FieldFilter("createdAt", "<", end_str))

        for doc in q.stream():
            d = doc.to_dict() or {}
            user_id = d.get("userId")
            item_id = (
                d.get("targetUserId")
                or d.get("targetId")
                or d.get("candidateUserId")
            )
            event = d.get("eventType") or d.get("type")
            ts = d.get("createdAt")

            if not user_id or not item_id or not event:
                skipped += 1
                continue

            event_str = str(event)
            event_counts[event_str] = event_counts.get(event_str, 0) + 1

            if isinstance(ts, datetime):
                ts_str = ts.astimezone(timezone.utc).isoformat()
            elif isinstance(ts, str) and ts.strip():
                ts_str = ts.strip()  # Flutter가 저장한 ISO8601 문자열 그대로
            else:
                ts_str = ""

            # source: profile_card | ai_preference (surface)
            source = d.get("surface") or d.get("source") or d.get("targetType") or "profile_card"
            source_str = str(source).lower()
            if source_str not in ("profile_card", "ai_preference"):
                source_str = "profile_card"

            rows.append([str(user_id), str(item_id), event_str, ts_str, source_str])

    if logger:
        logger.info(
            f"Loaded {len(rows)} events from {users_scanned} users "
            f"(skipped={skipped}), event breakdown: {event_counts}",
            extra={"count": len(rows), "date_key": date_key},
        )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["user_id", "item_id", "event", "ts", "source"])
    writer.writerows(rows)
    csv_data = buf.getvalue()

    gcs_blob = f"{prefix}events.csv"

    if dry_run:
        if logger:
            logger.info(
                f"DRY RUN: would upload {len(rows)} rows to gs://{bucket}/{gcs_blob}"
            )
        return {
            "rows": len(rows),
            "users_scanned": users_scanned,
            "gcs_uri": f"gs://{bucket}/{gcs_blob}",
            "dry_run": True,
        }

    gcs_uri = gcs_upload_string(bucket, gcs_blob, csv_data, project=project)
    elapsed = time.time() - t0

    if logger:
        logger.info(
            f"Export complete: {len(rows)} rows → {gcs_uri}",
            extra={
                "count": len(rows),
                "duration_s": round(elapsed, 1),
                "date_key": date_key,
            },
        )

    return {
        "rows": len(rows),
        "users_scanned": users_scanned,
        "skipped": skipped,
        "event_counts": event_counts,
        "gcs_uri": gcs_uri,
        "elapsed_s": round(elapsed, 1),
    }
