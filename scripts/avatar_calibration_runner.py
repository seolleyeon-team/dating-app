"""Operator-facing wrapper for the staging-only calibration runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[1]
_AI_MODEL_DIR = _REPO_ROOT / "lib" / "ai_recommend_model"
if str(_AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_MODEL_DIR))

from avatar_generation.calibration_runner import (  # noqa: E402
    CALIBRATION_PURPOSE,
    CalibrationRunnerConfig,
    CalibrationRunnerError,
    CalibrationRunResult,
    EXPECTED_STAGING_PROJECT,
    ManifestParticipant,
    MAX_CANDIDATES_PER_PARTICIPANT,
    ProviderRateLimiter,
    RedactedCalibrationRun,
    RedactedManifestSummary,
    RetryAfterError,
    run_calibration,
    validate_calibration_manifest,
    validate_calibration_manifest_value,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a controlled staging G004 calibration acquisition.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-project", default=EXPECTED_STAGING_PROJECT)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args(argv)

    try:
        summary = validate_calibration_manifest(args.manifest, expected_project=args.expected_project)
    except CalibrationRunnerError as exc:
        print(json.dumps({"status": "blocked", "code": exc.code}, ensure_ascii=False))
        return 2
    report = summary.to_report()
    if args.summary_output:
        args.summary_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if summary.eligible_count >= 5 else 2


__all__ = [
    "CALIBRATION_PURPOSE",
    "CalibrationRunnerConfig",
    "CalibrationRunnerError",
    "CalibrationRunResult",
    "EXPECTED_STAGING_PROJECT",
    "ManifestParticipant",
    "MAX_CANDIDATES_PER_PARTICIPANT",
    "ProviderRateLimiter",
    "RedactedCalibrationRun",
    "RedactedManifestSummary",
    "RetryAfterError",
    "run_calibration",
    "validate_calibration_manifest",
    "validate_calibration_manifest_value",
    "main",
]


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
