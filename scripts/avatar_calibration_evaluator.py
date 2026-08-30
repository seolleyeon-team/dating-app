"""CLI and compatibility surface for the deterministic G004 evaluator."""

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

from avatar_generation.calibration_evaluator import (  # noqa: E402
    evaluate_calibration_rows,
    freeze_threshold_snapshot,
    redact_calibration_report,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a redacted G004 calibration run.")
    parser.add_argument("--rows", type=Path, required=True, help="Redacted calibration rows JSON")
    parser.add_argument("--artifact", type=Path, required=True, help="Pinned calibration artifact JSON")
    parser.add_argument("--rubric", type=Path, help="Redacted run-level rubric/evidence JSON")
    parser.add_argument("--output", type=Path, help="Optional redacted report output path")
    args = parser.parse_args(argv)

    rows_value = json.loads(args.rows.read_text(encoding="utf-8"))
    artifact_value = json.loads(args.artifact.read_text(encoding="utf-8"))
    rubric_value: Mapping[str, Any] | None = None
    if args.rubric:
        loaded_rubric = json.loads(args.rubric.read_text(encoding="utf-8"))
        rubric_value = loaded_rubric if isinstance(loaded_rubric, Mapping) else None
    rows = rows_value if isinstance(rows_value, list) else []
    report = evaluate_calibration_rows(rows, artifact=artifact_value, rubric=rubric_value)
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 0 if report.get("g004Pass") is True else 2


__all__ = [
    "evaluate_calibration_rows",
    "freeze_threshold_snapshot",
    "redact_calibration_report",
    "main",
]


if __name__ == "__main__":  # pragma: no cover - exercised by operator use
    raise SystemExit(main())
