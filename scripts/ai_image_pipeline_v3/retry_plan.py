from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping


RETRYABLE_STATUSES = {
    "prepared",
    "failed",
    "missing",
    "waiting_reference",
    "qa_rejected",
    "vision_rejected",
    "dry_run",
}
APPROVED_STATUSES = {"completed", "qa_approved", "vision_approved", "file_qa_passed"}


def attempt_count(row: Mapping[str, Any]) -> int:
    try:
        return int(row.get("attemptCount") or 0)
    except (TypeError, ValueError):
        return 0


def final_output_exists(row: Mapping[str, Any]) -> bool:
    final_path = str(row.get("finalPath") or "")
    return bool(final_path) and Path(final_path).exists()


def face_card_exhaustion(profile_rows: Iterable[Mapping[str, Any]], *, max_attempts: int) -> dict[str, Any] | None:
    for row in profile_rows:
        if str(row.get("shotType") or "") != "face_card":
            continue
        attempts = attempt_count(row)
        if attempts < max_attempts or (str(row.get("status") or "") in APPROVED_STATUSES and final_output_exists(row)):
            return None
        return {
            "profileId": str(row.get("profileId") or ""),
            "assetId": str(row.get("assetId") or ""),
            "shotType": "face_card",
            "status": str(row.get("status") or ""),
            "attempt": attempts,
            "maxAttempts": int(max_attempts),
            "reason": "face_card_max_attempts_exhausted",
        }
    return None


def is_retryable(row: Mapping[str, Any], *, max_attempts: int, force: bool) -> bool:
    status = str(row.get("status") or "")
    if force:
        return True
    if status in APPROVED_STATUSES and final_output_exists(row):
        return False
    if status not in RETRYABLE_STATUSES:
        return False
    return attempt_count(row) < max_attempts


def select_retryable_assets(
    rows: Iterable[Mapping[str, Any]],
    *,
    max_attempts: int = 3,
    force: bool = False,
) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if is_retryable(row, max_attempts=max_attempts, force=force)]
