#!/usr/bin/env python3
"""Seolleyeon Recommendation Pipeline - Cloud Run Job Entrypoint.

Usage (local):
  python -m recsys.main --step export  --project seolleyeon-final --bucket seolleyeon-final-recs
  python -m recsys.main --step svd     --project seolleyeon-final --bucket seolleyeon-final-recs
  python -m recsys.main --step knn     --project seolleyeon-final --bucket seolleyeon-final-recs
  python -m recsys.main --step clip    --project seolleyeon-final
  python -m recsys.main --step rrf     --project seolleyeon-final
  python -m recsys.main --step daily   --project seolleyeon-final
  python -m recsys.main --step verify  --project seolleyeon-final
  python -m recsys.main --step meeting-group-index --project seolleyeon-final
  python -m recsys.main --step meeting-recommend   --project seolleyeon-final
  python -m recsys.main --step meeting-daily       --project seolleyeon-final
  python -m recsys.main --step meeting-verify      --project seolleyeon-final

All steps default --date-key to today (KST YYYYMMDD) when omitted.
Model steps (`clip`, `svd`, `knn`) dispatch to the v3 training/export scripts.
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
from recsys.jobs.meeting_job import MeetingStepOptions, run_meeting_step

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
DEFAULT_RRF_SOURCES = "clip,svd,knn"
DEFAULT_RRF_REQUIRED_SOURCES = "clip"
# 원래 도입값(33209527, 2026-07-27)은 2였다. 정책 블록이 172bcda5 에서
# 통째로 사라졌다가 재작성되며 1이 됐다. 별도 제품 요구가 없으므로
# "SVD 신호만 있는 사용자를 융합 피드로 내보내지 않는다"는 원래 의도로 되돌린다.
DEFAULT_RRF_MIN_SOURCES_PER_USER = 2
DEFAULT_RRF_TOPN = 400
DEFAULT_RRF_MAX_ITEMS_PER_SOURCE = 400
DEFAULT_RRF_SOURCE_WEIGHTS = '{"clip":1.0,"svd":0.35,"knn":0.25}'

_SIGNAL_SHORTAGE_MARKER = (
    "No usable events after filtering known events / AI profiles."
)
_SIGNAL_SHORTAGE_SCRIPTS = frozenset({
    MODEL_SCRIPT_NAMES["svd"],
    MODEL_SCRIPT_NAMES["knn"],
})


def classify_subprocess_result(
    script_name: str,
    returncode: int,
    output: str,
) -> tuple[str, str]:
    """Classify a model subprocess result without hiding unexpected failures."""
    if returncode == 0:
        return "ready", ""

    if (
        script_name in _SIGNAL_SHORTAGE_SCRIPTS
        and _SIGNAL_SHORTAGE_MARKER in output
    ):
        return "skipped", "insufficient_signal"

    return "failed", "runtime_error"


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------


def build_model_script_args(args, *, events_csv: str | None = None) -> list[str]:
    """Build model arguments with production policy defaults enabled."""
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
            "--profile_index_collection", args.profile_index_collection,
            "--policy_min_meta_coverage", str(args.policy_min_meta_coverage),
            "--manner_min", str(args.manner_min),
            "--active_within_days", str(args.active_within_days),
        ])
    if not args.require_same_university:
        script_args.append("--no_require_same_university")
    if not args.firestore_blocks:
        script_args.append("--no_firestore_blocks")
    return script_args


def build_rrf_script_args(args) -> list[str]:
    """Build RRF arguments; CLIP alone is a valid cold-start source."""
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

def _run_script(
    script_name: str,
    args: list[str],
    logger,
    *,
    on_expected_skip=None,
) -> int:
    """Run an existing ML script as a subprocess."""
    script_path = os.path.join(AI_MODEL_DIR, script_name)
    if not os.path.isfile(script_path):
        logger.error(f"Script not found: {script_path}")
        return 1

    cmd = [sys.executable, script_path] + args
    logger.info(f"Subprocess: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    status, reason = classify_subprocess_result(
        script_name,
        result.returncode,
        (result.stdout or "") + (result.stderr or ""),
    )

    if status == "skipped":
        if on_expected_skip is not None:
            try:
                on_expected_skip(reason)
            except Exception:
                logger.error(
                    f"{script_name} skip status could not be persisted",
                    exc_info=True,
                )
                return 1
        logger.warning(
            f"{script_name} skipped: status={status} reason={reason}"
        )
        return 0

    if result.returncode != 0:
        logger.error(f"{script_name} failed (exit {result.returncode})")
    else:
        logger.info(f"{script_name} completed successfully")
    return result.returncode


def _persist_expected_skip(args, source: str, reason: str) -> None:
    from recsys.jobs.model_status import write_source_status

    write_source_status(
        project=args.project,
        date_key=args.date_key,
        source=source,
        status="skipped",
        reason=reason,
        database=args.database,
    )


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
    from recsys.jobs.export_job import run_export

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
        on_expected_skip=lambda reason: _persist_expected_skip(args, "svd", reason),
    )


def step_knn(args, logger) -> int:
    csv_path = _download_events_csv(args, logger)
    if csv_path is None:
        return 1

    return _run_script(
        MODEL_SCRIPT_NAMES["knn"],
        build_model_script_args(args, events_csv=csv_path),
        logger,
        on_expected_skip=lambda reason: _persist_expected_skip(args, "knn", reason),
    )


def step_clip(args, logger) -> int:
    return _run_script(
        MODEL_SCRIPT_NAMES["clip"],
        build_model_script_args(args),
        logger,
    )


def step_rrf(args, logger) -> int:
    return _run_script(RRF_SCRIPT_NAME, build_rrf_script_args(args), logger)


def step_daily(args, logger) -> int:
    from recsys.jobs.daily_job import run_daily

    result = run_daily(
        project=args.project,
        date_key=args.date_key,
        database=args.database,
        logger=logger,
    )
    logger.info(f"Daily result:\n{json.dumps(result, ensure_ascii=False, indent=2)}")
    return 0


def step_verify(args, logger) -> int:
    from recsys.jobs.verify_job import run_verify

    result = run_verify(
        project=args.project,
        date_key=args.date_key,
        database=args.database,
        logger=logger,
    )
    logger.info(
        "Verify result summary: "
        f"healthy={result.get('healthy', False)} "
        f"degraded={result.get('degraded', False)} "
        f"fatal={result.get('fatal', False)} "
        f"reasons={result.get('reasons', [])}"
    )
    return 0 if result.get("healthy", False) else 1


def _step_meeting(step: str, args, logger) -> int:
    """Run one of the existing v1 season meeting scripts."""

    options = MeetingStepOptions(
        project=args.project,
        date_key=args.date_key,
        database=args.database,
        group_ids=args.meeting_group_ids,
        dry_run=args.dry_run,
        write_verify_doc=args.write_meeting_verify_doc,
        verify_collection=args.meeting_verify_collection,
    )
    return run_meeting_step(
        step,
        options,
        logger,
        run_script=_run_script,
    )


def step_meeting_group_index(args, logger) -> int:
    return _step_meeting("meeting-group-index", args, logger)


def step_meeting_recommend(args, logger) -> int:
    return _step_meeting("meeting-recommend", args, logger)


def step_meeting_daily(args, logger) -> int:
    return _step_meeting("meeting-daily", args, logger)


def step_meeting_verify(args, logger) -> int:
    return _step_meeting("meeting-verify", args, logger)


# ---------------------------------------------------------------
# CLI
# ---------------------------------------------------------------

STEPS = {
    "export": step_export,
    "svd": step_svd,
    "knn": step_knn,
    "clip": step_clip,
    "rrf": step_rrf,
    "daily": step_daily,
    "verify": step_verify,
    "meeting-group-index": step_meeting_group_index,
    "meeting-recommend": step_meeting_recommend,
    "meeting-daily": step_meeting_daily,
    "meeting-verify": step_meeting_verify,
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
        "--project", default=os.environ.get("GCP_PROJECT", "seolleyeon-final"),
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
        help="Filter candidates by the shared verification/activity/profile policy.",
    )
    policy.add_argument(
        "--no-apply-policy-filters", dest="apply_policy_filters",
        action="store_false",
        help="Disable candidate policy filters for debugging only.",
    )
    policy.add_argument(
        "--policy-min-meta-coverage", dest="policy_min_meta_coverage",
        type=float, default=0.9,
    )
    policy.add_argument(
        "--profile-index-collection", dest="profile_index_collection",
        default="profileIndex",
    )
    policy.add_argument("--manner-min", dest="manner_min", type=float, default=33.0)
    policy.add_argument(
        "--active-within-days", dest="active_within_days", type=int, default=14,
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
    )
    policy.add_argument(
        "--no-firestore-blocks", dest="firestore_blocks",
        action="store_false",
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
    p.add_argument(
        "--meeting-group-ids",
        dest="meeting_group_ids",
        default="",
        help="Optional comma-separated actor groupIds for meeting steps.",
    )
    p.add_argument(
        "--write-meeting-verify-doc",
        dest="write_meeting_verify_doc",
        action="store_true",
        help="Persist meeting verification summary under meetingVerifyRuns.",
    )
    p.add_argument(
        "--meeting-verify-collection",
        dest="meeting_verify_collection",
        default="meetingVerifyRuns",
        help="Firestore collection for meeting verification summaries.",
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
