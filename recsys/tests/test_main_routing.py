from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from recsys.jobs.meeting_job import (
    MeetingStepOptions,
    build_meeting_script_args,
)
from recsys.main import STEPS, build_parser, classify_subprocess_result, step_verify
from recsys.jobs.common import KST


def test_all_meeting_steps_are_registered():
    assert {
        "meeting-group-index",
        "meeting-recommend",
        "meeting-daily",
        "meeting-verify",
    }.issubset(STEPS)


def test_meeting_parser_accepts_shared_options():
    args = build_parser().parse_args(
        [
            "--step",
            "meeting-verify",
            "--project",
            "test-project",
            "--date-key",
            "20260802",
            "--meeting-group-ids",
            "g1,g2",
            "--write-meeting-verify-doc",
        ]
    )
    assert args.step == "meeting-verify"
    assert args.date_key == "20260802"
    assert args.meeting_group_ids == "g1,g2"
    assert args.write_meeting_verify_doc is True


def test_parser_defaults_to_seolleyeon_final_project():
    args = build_parser().parse_args(["--step", "verify"])

    assert args.project == "seolleyeon-final"


def test_meeting_script_contracts_keep_existing_v1_defaults():
    options = MeetingStepOptions(
        project="test-project",
        date_key="20260802",
        database="(default)",
        group_ids="g1,g2",
        dry_run=True,
        write_verify_doc=True,
    )

    script, args = build_meeting_script_args("meeting-recommend", options)
    assert script == "seolleyeon_meeting_recommend_export_v1.py"
    assert args == [
        "--firestore_project",
        "test-project",
        "--date_key",
        "20260802",
        "--firestore_database",
        "(default)",
        "--group_ids",
        "g1,g2",
        "--dry_run",
    ]

    script, args = build_meeting_script_args("meeting-verify", options)
    assert script == "seolleyeon_meeting_verify_v1.py"
    assert "--write_verify_doc" in args
    assert "--dry_run" not in args


def test_unknown_meeting_step_is_rejected():
    options = MeetingStepOptions(project="p", date_key="20260802")
    try:
        build_meeting_script_args("meeting-unknown", options)
    except ValueError as exc:
        assert "unknown meeting step" in str(exc)
    else:
        raise AssertionError("unknown meeting step must fail")

def test_kst_date_key_boundary_is_explicit():
    before_midnight = datetime(2026, 8, 1, 14, 59, tzinfo=timezone.utc)
    after_midnight = datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc)
    assert before_midnight.astimezone(KST).strftime("%Y%m%d") == "20260801"
    assert after_midnight.astimezone(KST).strftime("%Y%m%d") == "20260802"


def test_model_signal_shortage_is_classified_as_non_fatal_skip():
    result = classify_subprocess_result(
        "seolleyeon_svd_train_export_v3.py",
        1,
        "ValueError: No usable events after filtering known events / AI profiles.",
    )

    assert result == ("skipped", "insufficient_signal")


def test_unexpected_model_failure_remains_fatal():
    result = classify_subprocess_result(
        "seolleyeon_svd_train_export_v3.py",
        1,
        "PermissionError: Firestore access denied",
    )

    assert result == ("failed", "runtime_error")


def test_verify_step_logs_summary_without_serializing_firestore_values(monkeypatch):
    from recsys.jobs import verify_job

    monkeypatch.setattr(
        verify_job,
        "run_verify",
        lambda **_: {
            "healthy": True,
            "degraded": True,
            "fatal": False,
            "reasons": ["no_compatible_pair"],
            "source_details": {"clip": {"data": {"generatedAt": object()}}},
        },
    )

    class Logger:
        def __init__(self):
            self.messages = []

        def info(self, message, **_kwargs):
            self.messages.append(message)

    logger = Logger()
    args = SimpleNamespace(
        project="test-project",
        date_key="20260824",
        database=None,
    )

    assert step_verify(args, logger) == 0
    assert "Verify result summary" in logger.messages[-1]
