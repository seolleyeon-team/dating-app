"""Persist explicit model source status for verification and diagnostics."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover
    firestore = None


def write_source_status(
    *,
    project: str,
    date_key: str,
    source: str,
    status: str,
    reason: str,
    user_ids: Iterable[str] | None = None,
    database: str | None = None,
) -> int:
    """Write a current-date status document for every real actor."""
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is not installed")
    db = firestore.Client(project=project, database=database)
    if user_ids is None:
        user_ids = [doc.id for doc in db.collection("users").list_documents()]
    batch = db.batch()
    count = 0
    for uid in sorted({str(value) for value in user_ids if str(value).strip()}):
        ref = db.document(f"modelRecs/{uid}/daily/{date_key}/sources/{source}")
        batch.set(
            ref,
            {
                "status": status,
                "reason": reason,
                "algorithmVersion": f"{source}_status_{date_key}",
                "generatedAt": firestore.SERVER_TIMESTAMP,
                "topN": 0,
                "items": [],
                "modelStatus": {
                    "source": source,
                    "status": status,
                    "reason": reason,
                    "recordedAt": datetime.now(tz=timezone.utc).isoformat(),
                },
            },
            merge=True,
        )
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()
    if count % 400:
        batch.commit()
    return count


__all__ = ["write_source_status"]
