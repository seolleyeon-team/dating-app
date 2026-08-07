"""Cloud Run adapters for the 3:3 season meeting recommendation steps.

The actual recommendation algorithms remain in ``lib/ai_recommend_model``.
This module only translates the unified ``recsys.main`` arguments into the
existing script contracts so that the local runner and Cloud Run use exactly
the same invocation shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


MEETING_SCRIPT_NAMES = {
    "meeting-group-index": "seolleyeon_meeting_group_index_export_v1.py",
    "meeting-recommend": "seolleyeon_meeting_recommend_export_v1.py",
    "meeting-daily": "seolleyeon_meeting_daily_recs_export_v1.py",
    "meeting-verify": "seolleyeon_meeting_verify_v1.py",
}

MEETING_VERIFY_COLLECTION = "meetingVerifyRuns"


@dataclass(frozen=True)
class MeetingStepOptions:
    """Inputs shared by all season meeting script invocations."""

    project: str
    date_key: str
    database: Optional[str] = None
    group_ids: str = ""
    dry_run: bool = False
    write_verify_doc: bool = False
    verify_collection: str = MEETING_VERIFY_COLLECTION


def _base_args(options: MeetingStepOptions) -> list[str]:
    script_args = [
        "--firestore_project",
        options.project,
        "--date_key",
        options.date_key,
    ]
    if options.database:
        script_args.extend(["--firestore_database", options.database])
    if options.group_ids:
        script_args.extend(["--group_ids", options.group_ids])
    return script_args


def build_meeting_script_args(
    step: str,
    options: MeetingStepOptions,
) -> tuple[str, list[str]]:
    """Return the existing script name and CLI arguments for ``step``.

    No model/scoring flags are supplied here. The v1 scripts' checked-in
    defaults therefore remain the source of truth for production execution.
    """

    if step not in MEETING_SCRIPT_NAMES:
        raise ValueError(f"unknown meeting step: {step}")

    script_args = _base_args(options)
    if step == "meeting-verify":
        if options.write_verify_doc:
            script_args.append("--write_verify_doc")
        if options.verify_collection != MEETING_VERIFY_COLLECTION:
            script_args.extend(["--verify_collection", options.verify_collection])
    elif options.dry_run:
        # All three export scripts expose the same dry-run flag. The verify
        # script is read-only and intentionally has no dry-run argument.
        script_args.append("--dry_run")

    return MEETING_SCRIPT_NAMES[step], script_args


def run_meeting_step(
    step: str,
    options: MeetingStepOptions,
    logger: Any,
    *,
    run_script: Callable[[str, list[str], Any], int],
) -> int:
    """Execute one meeting script through the shared subprocess runner."""

    script_name, script_args = build_meeting_script_args(step, options)
    if logger:
        logger.info(
            "Meeting step %s: script=%s args=%s",
            step,
            script_name,
            script_args,
        )
    return run_script(script_name, script_args, logger)

