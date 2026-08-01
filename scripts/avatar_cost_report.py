#!/usr/bin/env python3
"""Report Seolleyeon avatar generation cost and budget guard status."""

from __future__ import annotations

import argparse
import json
import sys
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


def _load_fixture(path: str) -> list[Mapping[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, Mapping):
        jobs = raw.get("jobs", [])
    else:
        jobs = raw
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Report avatar generation costs and hard guard status.")
    parser.add_argument("--firestore_project")
    parser.add_argument("--firestore_database")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--fixture_json", help="Read avatarJobs docs from a local JSON fixture.")
    parser.add_argument("--date", help="UTC date for daily budget/quota accounting, YYYY-MM-DD.")
    parser.add_argument("--month", help="UTC month for monthly budget/quota accounting, YYYY-MM.")
    parser.add_argument("--dry_run", action="store_true", help="Do not enforce or mutate; this report never mutates.")
    parser.add_argument("--output_report_json")
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
    alerts = build_cost_alerts(aggregate, config=config)
    report = {
        "generatedAt": now.isoformat(),
        "dryRun": bool(args.dry_run),
        "pricing": {
            "version": config.pricing_version,
            "gpuUsdPerSecond": config.gpu_usd_per_second,
            "cpuUsdPerVcpuSecond": config.cpu_usd_per_vcpu_second,
            "memoryUsdPerGibSecond": config.memory_usd_per_gib_second,
            "gpuZonalRedundancy": config.gpu_zonal_redundancy,
            "vcpu": config.vcpu,
            "memoryGib": config.memory_gib,
            "defaultsAreConfigurableAssumptions": True,
            "excludedCosts": ["storage", "network_egress", "artifact_registry"],
        },
        "limits": {
            "dailyAlertUsd": config.daily_alert_usd,
            "monthlyAlertUsd": config.monthly_alert_usd,
            "hardDailyGenerationLimit": config.hard_daily_generation_limit,
            "hardMonthlyGenerationLimit": config.hard_monthly_generation_limit,
            "enforceBudget": config.enforce_budget,
            "killSwitchEnabled": config.kill_switch_enabled,
        },
        "actuals": aggregate.to_dict(),
        "alerts": alerts,
        "scenario": build_default_scenario_report(config=config),
        "privacy": {
            "sourceRefsEmitted": False,
            "userIdsEmitted": False,
            "jobIdsEmitted": False,
        },
    }
    _write_report(report, args.output_report_json)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
