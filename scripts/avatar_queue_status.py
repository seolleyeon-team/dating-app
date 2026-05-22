#!/usr/bin/env python3
"""Report Seolleyeon avatar queue backlog health without exposing source refs."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, NamedTuple, Optional, Sequence


QUEUED_STATUSES = {"queued"}
RUNNING_STATUSES = {"running", "processing"}
RETRYABLE_STATUSES = {"", "failed", "cancelled", "enqueue_failed", "retryable"}
PREVIEW_READY_STATUSES = {"preview_ready"}


class EstimateConfig(NamedTuple):
    batch_size: int = 4
    gpu_seconds_per_candidate: float = 30.0
    gpu_cost_per_second_usd: float = 0.0
    default_candidate_count: int = 4


def _as_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _nested_get(data: Mapping[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, Mapping):
        seconds = value.get("seconds") or value.get("_seconds")
        nanos = value.get("nanos") or value.get("_nanoseconds") or 0
        if seconds is None:
            return None
        return datetime.fromtimestamp(float(seconds) + float(nanos) / 1_000_000_000, tz=timezone.utc)
    if hasattr(value, "timestamp"):
        try:
            return datetime.fromtimestamp(float(value.timestamp()), tz=timezone.utc)
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _first_timestamp(job: Mapping[str, Any], fields: Sequence[str]) -> Optional[datetime]:
    for field in fields:
        value = _nested_get(job, field) if "." in field else job.get(field)
        parsed = parse_timestamp(value)
        if parsed is not None:
            return parsed
    return None


def _positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _positive_float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def estimate_config_from_env(env: Mapping[str, str] = os.environ) -> EstimateConfig:
    return EstimateConfig(
        batch_size=_positive_int(env.get("AVATAR_QUEUE_BATCH_SIZE"), 4),
        gpu_seconds_per_candidate=_positive_float(
            env.get("AVATAR_QUEUE_GPU_SECONDS_PER_CANDIDATE"), 30.0
        ),
        gpu_cost_per_second_usd=_positive_float(
            env.get("AVATAR_QUEUE_GPU_COST_PER_SECOND_USD"), 0.0
        ),
        default_candidate_count=_positive_int(env.get("AVATAR_DEFAULT_CANDIDATE_COUNT"), 4),
    )


def is_stale_job(job: Mapping[str, Any], *, now: datetime) -> bool:
    status = _as_status(job.get("status"))
    if status not in RUNNING_STATUSES:
        return False
    lease_expires_at = parse_timestamp(_nested_get(job, "processing.leaseExpiresAt"))
    return lease_expires_at is not None and lease_expires_at <= now


def is_retryable_job(job: Mapping[str, Any]) -> bool:
    status_raw = job.get("status")
    status = _as_status(job.get("status"))
    queue_status = _as_status(job.get("queueStatus"))
    status_retryable = status in RETRYABLE_STATUSES and (bool(status) or status_raw is not None)
    queue_status_retryable = bool(queue_status) and queue_status in RETRYABLE_STATUSES
    return status_retryable or queue_status_retryable


def _candidate_count(job: Mapping[str, Any], default_candidate_count: int) -> int:
    return _positive_int(job.get("candidateCount"), default_candidate_count)


def _percentile_nearest_rank(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil((percentile / 100.0) * len(ordered)))
    return float(ordered[min(rank - 1, len(ordered) - 1)])


def _round_seconds(value: float) -> float:
    return round(float(value), 3)


def summarize_jobs(
    jobs: Iterable[Mapping[str, Any]],
    *,
    now: Optional[datetime] = None,
    estimate_config: Optional[EstimateConfig] = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    estimate_config = estimate_config or estimate_config_from_env()

    counts = {
        "total": 0,
        "queued": 0,
        "running": 0,
        "stale": 0,
        "retryable": 0,
        "preview_ready": 0,
    }
    queue_ages: list[float] = []
    actionable_jobs = 0
    actionable_candidates = 0

    for job in jobs:
        counts["total"] += 1
        status = _as_status(job.get("status"))
        queued = status in QUEUED_STATUSES
        running = status in RUNNING_STATUSES
        stale = is_stale_job(job, now=now)
        retryable = is_retryable_job(job)
        preview_ready = status in PREVIEW_READY_STATUSES

        if queued:
            counts["queued"] += 1
        if running:
            counts["running"] += 1
        if stale:
            counts["stale"] += 1
        if retryable:
            counts["retryable"] += 1
        if preview_ready:
            counts["preview_ready"] += 1

        if queued or running or retryable:
            queued_at = _first_timestamp(job, ("queuedAt", "createdAt", "updatedAt"))
            if queued_at is not None:
                queue_ages.append(max(0.0, (now - queued_at).total_seconds()))

        if queued or retryable or stale:
            actionable_jobs += 1
            actionable_candidates += _candidate_count(
                job, estimate_config.default_candidate_count
            )

    average = sum(queue_ages) / len(queue_ages) if queue_ages else 0.0
    estimated_batches = (
        math.ceil(actionable_candidates / estimate_config.batch_size)
        if estimate_config.batch_size > 0
        else 0
    )
    estimated_gpu_seconds = actionable_candidates * estimate_config.gpu_seconds_per_candidate

    return {
        "generatedAt": now.isoformat(),
        "counts": counts,
        "queue_age_seconds": {
            "sample_count": len(queue_ages),
            "average": _round_seconds(average),
            "p95": _round_seconds(_percentile_nearest_rank(queue_ages, 95)),
            "max": _round_seconds(max(queue_ages) if queue_ages else 0.0),
        },
        "estimates": {
            "actionable_jobs": actionable_jobs,
            "candidate_count": actionable_candidates,
            "estimated_batches": estimated_batches,
            "estimated_gpu_seconds": _round_seconds(estimated_gpu_seconds),
            "estimated_gpu_cost_usd": round(
                estimated_gpu_seconds * estimate_config.gpu_cost_per_second_usd, 4
            ),
        },
    }


def _optional_int(env: Mapping[str, str], name: str) -> Optional[int]:
    raw = env.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(str(raw).strip())
    except ValueError:
        return None


def _thresholds_from_env(env: Mapping[str, str]) -> dict[str, Optional[int]]:
    return {
        "queued": _optional_int(env, "AVATAR_QUEUE_MAX_QUEUED_JOBS"),
        "stale": _optional_int(env, "AVATAR_QUEUE_MAX_STALE_JOBS"),
        "retryable": _optional_int(env, "AVATAR_QUEUE_MAX_RETRYABLE_JOBS"),
        "p95_age_seconds": _optional_int(env, "AVATAR_QUEUE_MAX_P95_AGE_SECONDS"),
    }


def build_backlog_alerts(
    summary: Mapping[str, Any],
    *,
    thresholds: Mapping[str, Optional[int]],
) -> list[dict[str, Any]]:
    counts = summary.get("counts") if isinstance(summary.get("counts"), Mapping) else {}
    ages = (
        summary.get("queue_age_seconds")
        if isinstance(summary.get("queue_age_seconds"), Mapping)
        else {}
    )
    checks = {
        "queued": counts.get("queued", 0),
        "stale": counts.get("stale", 0),
        "retryable": counts.get("retryable", 0),
        "p95_age_seconds": ages.get("p95", 0),
    }
    alerts: list[dict[str, Any]] = []
    for name, limit in thresholds.items():
        if limit is None:
            continue
        value = float(checks.get(name, 0) or 0)
        if value > limit:
            alerts.append(
                {
                    "severity": "error",
                    "metric": name,
                    "value": value,
                    "limit": limit,
                    "message": f"{name}={value:g} exceeds threshold {limit:g}",
                }
            )
    return alerts


def _doc_to_dict(snapshot: Any) -> dict[str, Any]:
    data = snapshot.to_dict() if hasattr(snapshot, "to_dict") else {}
    if not isinstance(data, Mapping):
        data = {}
    doc = dict(data)
    doc_id = getattr(snapshot, "id", None)
    if doc_id and "jobId" not in doc:
        doc["jobId"] = str(doc_id)
    return doc


def stream_avatar_jobs(firestore_client: Any, *, limit: Optional[int] = None) -> list[dict[str, Any]]:
    query = firestore_client.collection("avatarJobs")
    if limit:
        query = query.limit(limit)
    return [_doc_to_dict(snapshot) for snapshot in query.stream()]


def default_firestore_client(project: Optional[str], database: Optional[str]) -> Any:
    try:
        from google.cloud import firestore
    except Exception as exc:  # pragma: no cover - depends on local install
        raise RuntimeError("google-cloud-firestore is required for live queue status.") from exc
    kwargs: dict[str, Any] = {}
    if project:
        kwargs["project"] = project
    if database:
        kwargs["database"] = database
    return firestore.Client(**kwargs)


def _load_fixture(path: str) -> list[Mapping[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, Mapping):
        jobs = raw.get("jobs", [])
    else:
        jobs = raw
    if not isinstance(jobs, list):
        raise ValueError("fixture must be a JSON array or an object with a jobs array.")
    return [job for job in jobs if isinstance(job, Mapping)]


def _write_report(report: Mapping[str, Any], path: Optional[str]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        Path(path).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Report avatarJobs queue backlog health.")
    parser.add_argument("--firestore_project")
    parser.add_argument("--firestore_database")
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Run without live Firestore credentials when no fixture is provided.",
    )
    parser.add_argument("--fixture_json", help="Read avatarJobs docs from a local JSON fixture.")
    parser.add_argument("--output_report_json")
    parser.add_argument("--fail_queued_over", type=int)
    parser.add_argument("--fail_stale_over", type=int)
    parser.add_argument("--fail_retryable_over", type=int)
    parser.add_argument("--fail_p95_age_seconds_over", type=int)
    args = parser.parse_args(argv)

    if args.fixture_json:
        jobs = _load_fixture(args.fixture_json)
    elif args.dry_run:
        jobs = []
    else:
        client = default_firestore_client(args.firestore_project, args.firestore_database)
        jobs = stream_avatar_jobs(client, limit=args.limit)

    summary = summarize_jobs(jobs, estimate_config=estimate_config_from_env(os.environ))
    thresholds = _thresholds_from_env(os.environ)
    explicit_thresholds = {
        "queued": args.fail_queued_over,
        "stale": args.fail_stale_over,
        "retryable": args.fail_retryable_over,
        "p95_age_seconds": args.fail_p95_age_seconds_over,
    }
    thresholds = {
        key: explicit_thresholds[key] if explicit_thresholds[key] is not None else value
        for key, value in thresholds.items()
    }
    alerts = build_backlog_alerts(summary, thresholds=thresholds)
    report = {
        **summary,
        "dryRun": bool(args.dry_run),
        "thresholds": thresholds,
        "alerts": alerts,
        "ok": not alerts,
    }
    _write_report(report, args.output_report_json)
    return 0 if report["ok"] else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
