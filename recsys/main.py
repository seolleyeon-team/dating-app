#!/usr/bin/env python3
"""Seolleyeon Recommendation Pipeline - Cloud Run Job Entrypoint.

Usage (local):
  python -m recsys.main --step export  --project seolleyeon --bucket seolleyeon-recs
  python -m recsys.main --step svd     --project seolleyeon --bucket seolleyeon-recs
  python -m recsys.main --step knn     --project seolleyeon --bucket seolleyeon-recs
  python -m recsys.main --step clip    --project seolleyeon
  python -m recsys.main --step rrf     --project seolleyeon
  python -m recsys.main --step verify  --project seolleyeon

All steps default --date-key to today (KST YYYYMMDD) when omitted.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

# Ensure the project root is on sys.path so `from recsys.jobs...` works
# regardless of how this module is invoked.
_RECSYS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_RECSYS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from recsys.jobs.common import (
    get_default_date_key,
    generate_run_id,
    gcs_download_to_file,
    setup_logging,
)
from recsys.jobs.export_job import run_export
from recsys.jobs.verify_job import run_verify

# Directory containing the original ML scripts.
# Docker:  /app/ai_recommend_model   (set via ENV AI_MODEL_DIR)
# Local:   lib/ai_recommend_model    (relative to project root)
AI_MODEL_DIR = os.environ.get(
    "AI_MODEL_DIR",
    os.path.join(_PROJECT_ROOT, "lib", "ai_recommend_model"),
)
if not os.path.isdir(AI_MODEL_DIR):
    AI_MODEL_DIR = os.path.join(_PROJECT_ROOT, "ai_recommend_model")


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def _run_script(script_name: str, args: list[str], logger) -> int:
    """Run an existing ML script as a subprocess."""
    script_path = os.path.join(AI_MODEL_DIR, script_name)
    if not os.path.isfile(script_path):
        logger.error(f"Script not found: {script_path}")
        return 1

    cmd = [sys.executable, script_path] + args
    logger.info(f"Subprocess: {' '.join(cmd)}")

    result = subprocess.run(cmd)

    if result.returncode != 0:
        logger.error(f"{script_name} failed (exit {result.returncode})")
    else:
        logger.info(f"{script_name} completed successfully")
    return result.returncode


def _download_events_csv(args, logger) -> str | None:
    """Download events.csv from GCS to a temp file."""
    if not args.bucket:
        logger.error("--bucket is required for svd/knn (to download events CSV from GCS)")
        return None

    gcs_blob = f"{args.prefix}events.csv"
    local_path = os.path.join(tempfile.gettempdir(), f"events_{args.date_key}.csv")

    logger.info(f"Downloading gs://{args.bucket}/{gcs_blob} → {local_path}")
    try:
        gcs_download_to_file(args.bucket, gcs_blob, local_path, project=args.project)
    except Exception as e:
        logger.error(f"GCS download failed: {e}")
        return None

    file_size = os.path.getsize(local_path)
    logger.info(f"Downloaded {file_size:,} bytes to {local_path}")
    return local_path


# ---------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------

def step_export(args, logger) -> int:
    if not args.bucket:
        logger.error("--bucket is required for export step")
        return 1

    result = run_export(
        project=args.project,
        bucket=args.bucket,
        prefix=args.prefix,
        date_key=args.date_key,
        database=args.database,
        lookback_days=args.lookback_days,
        limit_users=args.limit_users,
        dry_run=args.dry_run,
        logger=logger,
    )
    logger.info(f"Export result: {json.dumps(result, ensure_ascii=False)}")
    return 0 if result.get("rows", 0) >= 0 else 1


def step_svd(args, logger) -> int:
    csv_path = _download_events_csv(args, logger)
    if csv_path is None:
        return 1

    script_args = [
        "--events_csv", csv_path,
        "--firestore_project", args.project,
        "--date_key", args.date_key,
    ]
    if args.database:
        script_args.extend(["--firestore_database", args.database])

    return _run_script("seolleyeon_svd_train_export.py", script_args, logger)


def step_knn(args, logger) -> int:
    csv_path = _download_events_csv(args, logger)
    if csv_path is None:
        return 1

    script_args = [
        "--events_csv", csv_path,
        "--firestore_project", args.project,
        "--date_key", args.date_key,
    ]
    if args.database:
        script_args.extend(["--firestore_database", args.database])

    return _run_script("seolleyeon_knn_train_export.py", script_args, logger)


def step_clip(args, logger) -> int:
    script_args = [
        "--firestore_project", args.project,
        "--date_key", args.date_key,
    ]
    if args.database:
        script_args.extend(["--firestore_database", args.database])

    return _run_script("seolleyeon_clip_train_export.py", script_args, logger)


def step_rrf(args, logger) -> int:
    script_args = [
        "--firestore_project", args.project,
        "--date_key", args.date_key,
    ]
    if args.database:
        script_args.extend(["--firestore_database", args.database])

    return _run_script("seolleyeon_rrf_export.py", script_args, logger)


def step_verify(args, logger) -> int:
    result = run_verify(
        project=args.project,
        date_key=args.date_key,
        database=args.database,
        logger=logger,
    )
    logger.info(f"Verify result:\n{json.dumps(result, ensure_ascii=False, indent=2)}")
    return 0 if result.get("healthy", False) else 1


# ---------------------------------------------------------------
# CLI
# ---------------------------------------------------------------

STEPS = {
    "export": step_export,
    "svd": step_svd,
    "knn": step_knn,
    "clip": step_clip,
    "rrf": step_rrf,
    "verify": step_verify,
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Seolleyeon recommendation pipeline entrypoint",
    )
    p.add_argument("--step", required=True, choices=list(STEPS.keys()))
    p.add_argument(
        "--date-key", dest="date_key", default=None,
        help="YYYYMMDD (KST). Defaults to today.",
    )
    p.add_argument(
        "--project", default=os.environ.get("GCP_PROJECT", "seolleyeon"),
    )
    p.add_argument("--bucket", default=os.environ.get("GCS_BUCKET"))
    p.add_argument(
        "--prefix", default=None,
        help="GCS prefix (default: recs/{date_key}/)",
    )
    p.add_argument("--database", default=os.environ.get("FIRESTORE_DATABASE"))
    p.add_argument("--lookback-days", dest="lookback_days", type=int, default=120)
    p.add_argument("--limit-users", dest="limit_users", type=int, default=None)
    p.add_argument("--dry-run", dest="dry_run", action="store_true")
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Resolve defaults
    if not args.date_key:
        args.date_key = get_default_date_key()
    if args.prefix is None:
        args.prefix = f"recs/{args.date_key}/"

    run_id = generate_run_id()
    logger = setup_logging(args.step, run_id)

    logger.info(
        f"Pipeline step={args.step} date_key={args.date_key} "
        f"run_id={run_id} project={args.project} bucket={args.bucket}",
        extra={"date_key": args.date_key},
    )

    t0 = time.time()

    try:
        rc = STEPS[args.step](args, logger)
    except Exception:
        logger.error(f"Step {args.step} failed with exception", exc_info=True)
        rc = 1

    elapsed = time.time() - t0
    logger.info(
        f"Step {args.step} finished: rc={rc}, elapsed={elapsed:.1f}s",
        extra={"duration_s": round(elapsed, 1), "date_key": args.date_key},
    )
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
