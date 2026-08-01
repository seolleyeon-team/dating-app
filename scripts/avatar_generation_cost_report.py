#!/usr/bin/env python3
"""Report avatar generation worker timing percentiles and unit economics."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.cost import (  # noqa: E402
    AvatarCostConfig,
    aggregate_avatar_job_costs,
    build_cost_alerts,
    build_default_scenario_report,
    parse_report_date,
    parse_report_month,
)
from avatar_generation.job_lease import default_firestore_client, utcnow  # noqa: E402


GENERATED_STATUSES = {"preview_ready", "approved", "needs_review", "failed", "no_previewable_candidates"}
STAGE_FIELDS = (
    ("model_load_seconds", "modelLoadSeconds"),
    ("face_detect_seconds", "faceDetectSeconds"),
    ("trait_extract_seconds", "traitExtractSeconds"),
    ("preprocess_seconds", "preprocessSeconds"),
    ("sam_seconds", "samSeconds"),
    ("generation_seconds", "generationSeconds"),
    ("qa_seconds", "qaSeconds"),
    ("rerank_seconds", "rerankSeconds"),
    ("upload_seconds", "uploadSeconds"),
)


def _load_fixture(path: str) -> list[Mapping[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    jobs = raw.get("jobs", []) if isinstance(raw, Mapping) else raw
    if not isinstance(jobs, list):
        raise ValueError("fixture must be a JSON array or an object with a jobs array.")
    return [job for job in jobs if isinstance(job, Mapping)]


def _stream_avatar_jobs(firestore_client: Any, *, limit: Optional[int] = None) -> list[dict[str, Any]]:
    query = firestore_client.collection("avatarJobs")
    if limit and hasattr(query, "limit"):
        query = query.limit(limit)
    docs: list[dict[str, Any]] = []
    for snapshot in query.stream():
        data = snapshot.to_dict() if hasattr(snapshot, "to_dict") else {}
        if isinstance(data, Mapping):
            doc = dict(data)
            doc_id = getattr(snapshot, "id", None)
            if doc_id and "jobId" not in doc:
                doc["jobId"] = str(doc_id)
            docs.append(doc)
    return docs


def _write_report(report: Mapping[str, Any], path: Optional[str]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        Path(path).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def _write_csv(report: Mapping[str, Any], path: Optional[str]) -> None:
    if not path:
        return
    timing = report.get("timing") if isinstance(report.get("timing"), Mapping) else {}
    total = timing.get("totalWorkerSeconds") if isinstance(timing.get("totalWorkerSeconds"), Mapping) else {}
    economics = (
        report.get("unitEconomics")
        if isinstance(report.get("unitEconomics"), Mapping)
        else {}
    )
    actuals = report.get("actuals") if isinstance(report.get("actuals"), Mapping) else {}
    row = {
        "generatedAt": report.get("generatedAt", ""),
        "jobCount": timing.get("jobCount", 0),
        "approvedCount": economics.get("approvedCount", 0),
        "generatedCount": actuals.get("generatedCount", 0),
        "candidateCount": actuals.get("candidateCount", 0),
        "totalWorkerSecondsP50": total.get("p50", 0),
        "totalWorkerSecondsP95": total.get("p95", 0),
        "estimatedUsd": economics.get("estimatedUsd", 0),
        "costPerApprovedAvatarUsd": economics.get("costPerApprovedAvatarUsd", 0),
    }
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def _status(job: Mapping[str, Any]) -> str:
    return str(job.get("status") or "").strip().lower()


def _generated_jobs(jobs: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [job for job in jobs if _status(job) in GENERATED_STATUSES]


def _number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _cost_doc(job: Mapping[str, Any]) -> Mapping[str, Any]:
    cost = job.get("cost")
    return cost if isinstance(cost, Mapping) else {}


def _stage_seconds(job: Mapping[str, Any], snake_key: str, camel_key: str) -> Optional[float]:
    cost = _cost_doc(job)
    seconds_by_stage = cost.get("secondsByStage")
    if isinstance(seconds_by_stage, Mapping):
        for key in (snake_key, camel_key):
            parsed = _number(seconds_by_stage.get(key))
            if parsed is not None:
                return parsed
    for source in (cost, job):
        for key in (camel_key, snake_key):
            parsed = _number(source.get(key))
            if parsed is not None:
                return parsed
    return None


def _total_worker_seconds(job: Mapping[str, Any]) -> Optional[float]:
    cost = _cost_doc(job)
    seconds_by_stage = cost.get("secondsByStage")
    if isinstance(seconds_by_stage, Mapping):
        for key in ("total_worker_seconds", "totalWorkerSeconds", "total_seconds", "total"):
            parsed = _number(seconds_by_stage.get(key))
            if parsed is not None:
                return parsed
    for source in (cost, job):
        for key in ("totalWorkerSeconds", "total_worker_seconds", "durationSeconds", "runtimeSeconds"):
            parsed = _number(source.get(key))
            if parsed is not None:
                return parsed
    processing = job.get("processing")
    if isinstance(processing, Mapping):
        for key in ("totalWorkerSeconds", "total_worker_seconds", "durationSeconds", "runtimeSeconds"):
            parsed = _number(processing.get(key))
            if parsed is not None:
                return parsed
    return None


def _round_seconds(value: float) -> float:
    return round(max(0.0, float(value)), 3)


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(max(0.0, float(value)) for value in values)
    index = max(0, min(len(ordered) - 1, math.ceil((percentile / 100.0) * len(ordered)) - 1))
    return _round_seconds(ordered[index])


def _percentile_doc(values: Sequence[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "p50": _percentile(values, 50),
        "p95": _percentile(values, 95),
    }


def _timing_report(jobs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    generated = _generated_jobs(jobs)
    total_values = [
        value
        for value in (_total_worker_seconds(job) for job in generated)
        if value is not None
    ]
    stages: dict[str, Any] = {}
    for snake_key, camel_key in STAGE_FIELDS:
        values = [
            value
            for value in (_stage_seconds(job, snake_key, camel_key) for job in generated)
            if value is not None
        ]
        stages[camel_key] = _percentile_doc(values)
    return {
        "jobCount": len(generated),
        "totalWorkerSeconds": _percentile_doc(total_values),
        "stages": stages,
    }


def _unit_economics(jobs: Sequence[Mapping[str, Any]], *, total_usd: float) -> dict[str, Any]:
    approved_count = sum(1 for job in jobs if _status(job) == "approved")
    return {
        "approvedCount": approved_count,
        "estimatedUsd": round(max(0.0, float(total_usd)), 6),
        "costPerApprovedAvatarUsd": (
            round(max(0.0, float(total_usd)) / approved_count, 6)
            if approved_count > 0
            else 0.0
        ),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report avatar generation cost, timing percentiles, and cost per approved avatar."
    )
    parser.add_argument("--firestore_project", "--project", dest="firestore_project")
    parser.add_argument("--firestore_database")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--fixture_json", "--fixture-json", dest="fixture_json")
    parser.add_argument("--date", help="UTC date for daily budget/quota accounting, YYYY-MM-DD.")
    parser.add_argument("--month", help="UTC month for monthly budget/quota accounting, YYYY-MM.")
    parser.add_argument("--dry_run", "--dry-run", dest="dry_run", action="store_true")
    parser.add_argument("--output_report_json", "--output-report-json", dest="output_report_json")
    parser.add_argument("--output_csv", "--output-csv", dest="output_csv")
    args = parser.parse_args(argv)

    config = AvatarCostConfig.from_env()
    if args.fixture_json:
        jobs = _load_fixture(args.fixture_json)
    elif args.dry_run and not args.firestore_project and not args.firestore_database:
        jobs = []
    else:
        jobs = _stream_avatar_jobs(
            default_firestore_client(args.firestore_project, args.firestore_database),
            limit=args.limit,
        )

    now = utcnow()
    aggregate = aggregate_avatar_job_costs(
        jobs,
        now=now,
        config=config,
        report_date=parse_report_date(args.date),
        report_month=parse_report_month(args.month),
    )
    report = {
        "generatedAt": now.isoformat() if isinstance(now, datetime) else str(now),
        "dryRun": bool(args.dry_run),
        "actuals": aggregate.to_dict(),
        "alerts": build_cost_alerts(aggregate, config=config),
        "timing": _timing_report(jobs),
        "unitEconomics": _unit_economics(jobs, total_usd=aggregate.total_usd),
        "scenario": build_default_scenario_report(config=config),
        "privacy": {
            "sourceRefsEmitted": False,
            "userIdsEmitted": False,
            "jobIdsEmitted": False,
        },
    }
    _write_csv(report, args.output_csv)
    _write_report(report, args.output_report_json)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
