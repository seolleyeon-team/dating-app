#!/usr/bin/env python3
"""Requeue avatar jobs failed by the FLUX negative_prompt worker regression."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence


TARGET_ERROR_CODE = "avatar_generation_worker_error"
TARGET_ERROR_SUBSTRING = "unexpected keyword argument 'negative_prompt'"

PRIVATE_MARKER_RE = re.compile(
    r"(?i)(g(?:s|cs)://[^\s\"']+|seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp)[^\s\"']*)"
)
SIGNED_MARKER_RE = re.compile(
    r"(?i)(X-Goog-[^=&\s]+|GoogleAccessId|Signature|Expires|X-Amz-[^=&\s]+)=([^&\s]+)"
)


def redact_text(value: Any) -> str:
    text = str(value or "")
    text = PRIVATE_MARKER_RE.sub("<private-ref-redacted>", text)
    text = SIGNED_MARKER_RE.sub(r"\1=<redacted>", text)
    return text[:240]


def redact_identifier(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 8:
        return "<redacted>"
    return f"{text[:6]}...{text[-4:]}"


def is_negative_prompt_worker_failure(job: Mapping[str, Any]) -> bool:
    return (
        str(job.get("status") or "") == "failed"
        and str(job.get("errorCode") or "") == TARGET_ERROR_CODE
        and TARGET_ERROR_SUBSTRING in str(job.get("errorMessage") or "")
    )


def retry_update_for_job(
    job: Mapping[str, Any],
    *,
    server_timestamp: Any,
) -> dict[str, Any]:
    processing = dict(job.get("processing") or {})
    retry = dict(job.get("retry") or {})
    reset_count = int(retry.get("negativePromptWorkerErrorResetCount") or 0) + 1
    processing.update(
        {
            "lastErrorCode": str(job.get("errorCode") or ""),
            "lastErrorMessage": redact_text(job.get("errorMessage")),
            "lastResetReason": "flux_negative_prompt_kwarg_regression",
            "lastResetAt": server_timestamp,
        }
    )
    retry.update(
        {
            "negativePromptWorkerErrorResetCount": reset_count,
            "lastNegativePromptWorkerErrorResetAt": server_timestamp,
        }
    )
    return {
        "status": "queued",
        "updatedAt": server_timestamp,
        "queuedAt": server_timestamp,
        "errorCode": "",
        "errorMessage": "",
        "processing": processing,
        "retry": retry,
    }


def build_retry_report(
    jobs: Mapping[str, Mapping[str, Any]],
    *,
    apply: bool,
) -> dict[str, Any]:
    selected = {
        job_id: job
        for job_id, job in jobs.items()
        if is_negative_prompt_worker_failure(job)
    }
    skipped = len(jobs) - len(selected)
    return {
        "ok": True,
        "applied": bool(apply),
        "targetErrorCode": TARGET_ERROR_CODE,
        "targetErrorSubstring": TARGET_ERROR_SUBSTRING,
        "matchedCount": len(selected),
        "skippedCount": skipped,
        "jobIds": [redact_identifier(job_id) for job_id in sorted(selected)],
        "privacy": {
            "sourceRefsEmitted": False,
            "signedUrlsEmitted": False,
        },
    }


def _load_firestore_jobs(project: str, database: str, limit: int) -> tuple[Any, dict[str, Mapping[str, Any]]]:
    try:
        from google.cloud import firestore
        from google.cloud.firestore_v1.base_query import FieldFilter
    except Exception as exc:  # pragma: no cover - live dependency path
        raise RuntimeError("google-cloud-firestore is required for live retry.") from exc

    kwargs: dict[str, Any] = {"project": project}
    if database:
        kwargs["database"] = database
    client = firestore.Client(**kwargs)
    query = (
        client.collection("avatarJobs")
        .where(filter=FieldFilter("status", "==", "failed"))
        .where(filter=FieldFilter("errorCode", "==", TARGET_ERROR_CODE))
        .limit(limit)
    )
    jobs: dict[str, Mapping[str, Any]] = {}
    for snapshot in query.stream():
        data = snapshot.to_dict() or {}
        if isinstance(data, Mapping):
            jobs[str(snapshot.id)] = data
    return client, jobs


def _apply_retry_updates(client: Any, jobs: Mapping[str, Mapping[str, Any]]) -> int:
    from google.cloud.firestore import SERVER_TIMESTAMP

    applied = 0
    for job_id, job in jobs.items():
        if not is_negative_prompt_worker_failure(job):
            continue
        client.collection("avatarJobs").document(job_id).update(
            retry_update_for_job(job, server_timestamp=SERVER_TIMESTAMP)
        )
        applied += 1
    return applied


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Requeue only avatarJobs failed by the FLUX negative_prompt kwarg regression."
    )
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--database", default="(default)")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    client, jobs = _load_firestore_jobs(args.project, args.database, args.limit)
    report = build_retry_report(jobs, apply=args.apply)
    if args.apply:
        matched = {
            job_id: job
            for job_id, job in jobs.items()
            if is_negative_prompt_worker_failure(job)
        }
        report["appliedCount"] = _apply_retry_updates(client, matched)
    else:
        report["appliedCount"] = 0
    report["generatedAt"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
