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
Model steps (`clip`, `svd`, `knn`) dispatch to the v3 training/export scripts.

Candidate policy filters and the RRF quality gates are on by default, so a
caller that only passes --step/--date-key/--project/--bucket still gets a
filtered feed. Pass --no-apply-policy-filters to opt out while debugging.
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

# Directory containing the ML scripts.
# Docker:  /app/ai_recommend_model   (set via ENV AI_MODEL_DIR)
# Local:   lib/ai_recommend_model    (relative to project root)
AI_MODEL_DIR = os.environ.get(
    "AI_MODEL_DIR",
    os.path.join(_PROJECT_ROOT, "lib", "ai_recommend_model"),
)
if not os.path.isdir(AI_MODEL_DIR):
    AI_MODEL_DIR = os.path.join(_PROJECT_ROOT, "ai_recommend_model")


MODEL_SCRIPT_NAMES = {
    "clip": "seolleyeon_clip_train_export_v3.py",
    "svd": "seolleyeon_svd_train_export_v3.py",
    "knn": "seolleyeon_knn_train_export_v3.py",
}

RRF_SCRIPT_NAME = "seolleyeon_rrf_export.py"

# Quality gates that `seolleyeon_run_all_v3.py` applies. The Cloud Workflow only
# forwards --step/--date-key/--project/--bucket, so these have to be defaults
# here or production silently runs the pipeline with none of them.
DEFAULT_RRF_SOURCES = "clip,svd,knn"
DEFAULT_RRF_REQUIRED_SOURCES = "clip"
DEFAULT_RRF_MIN_SOURCES_PER_USER = 2
DEFAULT_RRF_TOPN = 400
DEFAULT_RRF_MAX_ITEMS_PER_SOURCE = 400
DEFAULT_RRF_SOURCE_WEIGHTS = '{"clip":1.0,"svd":0.35,"knn":0.25}'


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


def build_model_script_args(args, *, events_csv: str | None = None) -> list[str]:
    """Build the CLI arguments for a clip/svd/knn training script."""
    script_args: list[str] = []
    if events_csv is not None:
        script_args.extend(["--events_csv", events_csv])
    script_args.extend([
        "--firestore_project", args.project,
        "--date_key", args.date_key,
    ])
    if args.database:
        script_args.extend(["--firestore_database", args.database])
    if args.apply_policy_filters:
        script_args.append("--apply_policy_filters")
        script_args.extend([
            "--policy_min_meta_coverage", str(args.policy_min_meta_coverage),
        ])
    if not args.require_same_university:
        script_args.append("--no_require_same_university")
    # Scripts default firestore_blocks=True; only forward the opt-out.
    if not args.firestore_blocks:
        script_args.append("--no_firestore_blocks")
    return script_args


def build_rrf_script_args(args) -> list[str]:
    """Build the CLI arguments for the RRF merge script."""
    script_args = [
        "--firestore_project", args.project,
        "--date_key", args.date_key,
        "--sources", args.rrf_sources,
        "--topn", str(args.rrf_topn),
        "--max_items_per_source", str(args.rrf_max_items_per_source),
        "--min_sources_per_user", str(args.rrf_min_sources_per_user),
        "--source_weights_json", args.rrf_source_weights_json,
    ]
    if args.database:
        script_args.extend(["--firestore_database", args.database])
    if args.rrf_required_sources:
        script_args.extend(["--required_sources", args.rrf_required_sources])
    return script_args


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

    return _run_script(
        MODEL_SCRIPT_NAMES["svd"],
        build_model_script_args(args, events_csv=csv_path),
        logger,
    )


def step_knn(args, logger) -> int:
    csv_path = _download_events_csv(args, logger)
    if csv_path is None:
        return 1

    return _run_script(
        MODEL_SCRIPT_NAMES["knn"],
        build_model_script_args(args, events_csv=csv_path),
        logger,
    )


def step_clip(args, logger) -> int:
    return _run_script(
        MODEL_SCRIPT_NAMES["clip"],
        build_model_script_args(args),
        logger,
    )


def step_rrf(args, logger) -> int:
    return _run_script(RRF_SCRIPT_NAME, build_rrf_script_args(args), logger)


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

    policy = p.add_argument_group("candidate policy")
    policy.add_argument(
        "--apply-policy-filters", dest="apply_policy_filters",
        action="store_true",
        help="Filter candidates by verification, activity, manner score and preferences.",
    )
    policy.add_argument(
        "--no-apply-policy-filters", dest="apply_policy_filters",
        action="store_false",
        help="Export unfiltered candidates. Only for debugging.",
    )
    policy.add_argument(
        "--policy-min-meta-coverage", dest="policy_min_meta_coverage",
        type=float, default=0.9,
        help="Fail the job when policy metadata covers fewer than this share of users.",
    )
    policy.add_argument(
        "--require-same-university", dest="require_same_university",
        action="store_true",
    )
    policy.add_argument(
        "--no-require-same-university", dest="require_same_university",
        action="store_false",
    )
    policy.add_argument(
        "--firestore-blocks", dest="firestore_blocks",
        action="store_true",
        help="Load Firestore blocks/{uid}/targets into mutual exclusions (default).",
    )
    policy.add_argument(
        "--no-firestore-blocks", dest="firestore_blocks",
        action="store_false",
        help="Skip Firestore blocks; use recEvents block/report only.",
    )
    p.set_defaults(
        apply_policy_filters=True,
        require_same_university=True,
        firestore_blocks=True,
    )

    rrf = p.add_argument_group("rrf merge")
    rrf.add_argument("--rrf-sources", dest="rrf_sources", default=DEFAULT_RRF_SOURCES)
    rrf.add_argument(
        "--rrf-required-sources", dest="rrf_required_sources",
        default=DEFAULT_RRF_REQUIRED_SOURCES,
        help="Sources a user must have before any merged feed is exported.",
    )
    rrf.add_argument(
        "--rrf-min-sources-per-user", dest="rrf_min_sources_per_user",
        type=int, default=DEFAULT_RRF_MIN_SOURCES_PER_USER,
    )
    rrf.add_argument("--rrf-topn", dest="rrf_topn", type=int, default=DEFAULT_RRF_TOPN)
    rrf.add_argument(
        "--rrf-max-items-per-source", dest="rrf_max_items_per_source",
        type=int, default=DEFAULT_RRF_MAX_ITEMS_PER_SOURCE,
    )
    rrf.add_argument(
        "--rrf-source-weights-json", dest="rrf_source_weights_json",
        default=DEFAULT_RRF_SOURCE_WEIGHTS,
    )
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
    logger.info(
        f"Policy: apply_policy_filters={args.apply_policy_filters} "
        f"require_same_university={args.require_same_university} "
        f"min_meta_coverage={args.policy_min_meta_coverage} | "
        f"RRF: required_sources={args.rrf_required_sources or '(none)'} "
        f"min_sources_per_user={args.rrf_min_sources_per_user}",
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
