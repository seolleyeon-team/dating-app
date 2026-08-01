from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.job_lease import (  # noqa: E402
    AvatarJobLeaseConfig,
    LeaseSweepSummary,
    default_firestore_client,
    sweep_stale_avatar_job_leases,
)


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scheduled stale lease recovery for Seolleyeon avatar generation jobs."
    )
    parser.add_argument("--firestore_project")
    parser.add_argument("--firestore_database")
    parser.add_argument("--max_jobs", type=int, default=None)
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Preview stale lease recovery. With no Firestore target, returns an empty local report.",
    )
    parser.add_argument("--apply", action="store_true", help="Mutate Firestore. Default is dry-run.")
    parser.add_argument("--output_report_json", help="Optional path for a JSON summary report.")
    args = parser.parse_args(argv)

    dry_run = args.dry_run or not args.apply
    if dry_run and not args.firestore_project and not args.firestore_database:
        summary = LeaseSweepSummary(dry_run=True)
    else:
        firestore_client = default_firestore_client(args.firestore_project, args.firestore_database)
        summary = sweep_stale_avatar_job_leases(
            firestore_client,
            now=utcnow(),
            config=AvatarJobLeaseConfig.from_env(),
            dry_run=dry_run,
            max_jobs=args.max_jobs,
        )
    report = summary.to_dict()
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_report_json:
        Path(args.output_report_json).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
