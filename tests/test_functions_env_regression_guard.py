"""Deployment env regression guard.

Reconstructs the 2026-09-08 deploy: an incomplete env file silently removed 19
variables from five production functions, including the one that keeps queue
dispatch fail-closed. The guard exists so that comparison is never again made
against the same file the deploy came from.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from functions_env_regression_guard import (  # noqa: E402
    PLATFORM_MANAGED_KEYS,
    is_secret_key,
    parse_env_file,
    plan_functions_env_check,
    redact,
    required_env_keys_from_source,
)

LIVE = {
    "ENVIRONMENT": "staging",
    "JOB_QUEUE_MODE": "cloud_tasks",
    "TASK_INVOKER_SERVICE_ACCOUNT": "task-invoker@example.iam.gserviceaccount.com",
    "AVATAR_GENERATION_TASK_URL": "https://worker.example/tasks/avatar-generation",
    "AVATAR_DISABLE_NEW_GENERATION": "false",
    "FUNCTION_REGION": "asia-northeast3",
    # platform-injected; an env file never carries these
    "K_SERVICE": "retrycurrentavatargeneration",
    "FUNCTION_TARGET": "retryCurrentAvatarGeneration",
}


def test_the_incident_deploy_is_rejected():
    """실제로 배포됐던 불완전한 env 파일이 그대로 통과하면 안 된다."""
    incomplete = {"ENVIRONMENT": "staging"}

    result = plan_functions_env_check(
        deployed={"retryCurrentAvatarGeneration": LIVE},
        candidate=incomplete,
    )

    assert not result.ok
    removed = {f.key for f in result.findings if f.kind == "removed"}
    assert "JOB_QUEUE_MODE" in removed
    assert "TASK_INVOKER_SERVICE_ACCOUNT" in removed
    assert "AVATAR_GENERATION_TASK_URL" in removed
    assert "AVATAR_DISABLE_NEW_GENERATION" in removed


def test_platform_injected_variables_are_not_treated_as_regressions():
    result = plan_functions_env_check(
        deployed={"retryCurrentAvatarGeneration": LIVE},
        candidate={k: v for k, v in LIVE.items() if k not in PLATFORM_MANAGED_KEYS},
    )

    assert result.ok, [f.render() for f in result.findings]


def test_function_region_is_platform_injected_not_a_user_env_removal():
    result = plan_functions_env_check(
        deployed={"retryCurrentAvatarGeneration": LIVE},
        candidate={k: v for k, v in LIVE.items() if k not in PLATFORM_MANAGED_KEYS},
    )

    assert result.ok, [f.render() for f in result.findings]


def test_a_changed_value_is_reported():
    candidate = {k: v for k, v in LIVE.items() if k not in PLATFORM_MANAGED_KEYS}
    candidate["JOB_QUEUE_MODE"] = "dry_run"

    result = plan_functions_env_check(
        deployed={"retryCurrentAvatarGeneration": LIVE},
        candidate=candidate,
    )

    changed = [f for f in result.findings if f.kind == "changed"]
    assert len(changed) == 1
    assert changed[0].key == "JOB_QUEUE_MODE"
    assert "cloud_tasks" in changed[0].detail and "dry_run" in changed[0].detail


def test_a_deliberate_removal_can_be_declared():
    candidate = {
        k: v for k, v in LIVE.items()
        if k not in PLATFORM_MANAGED_KEYS and k != "AVATAR_DISABLE_NEW_GENERATION"
    }

    blocked = plan_functions_env_check(
        deployed={"retryCurrentAvatarGeneration": LIVE}, candidate=candidate
    )
    allowed = plan_functions_env_check(
        deployed={"retryCurrentAvatarGeneration": LIVE},
        candidate=candidate,
        allowed_removals=["AVATAR_DISABLE_NEW_GENERATION"],
    )

    assert not blocked.ok
    assert allowed.ok


def test_every_function_is_checked_not_just_the_first():
    other = dict(LIVE)
    other.pop("JOB_QUEUE_MODE")
    candidate = {k: v for k, v in LIVE.items() if k not in PLATFORM_MANAGED_KEYS}
    candidate.pop("AVATAR_GENERATION_TASK_URL")

    result = plan_functions_env_check(
        deployed={"first": LIVE, "second": other},
        candidate=candidate,
    )

    assert result.checked_functions == ["first", "second"]
    assert {f.function for f in result.findings} == {"first", "second"}


def test_secret_values_are_never_printed():
    live = {"RESEND_API_KEY": "super-secret-value"}
    candidate = {"RESEND_API_KEY": "other-secret-value"}

    result = plan_functions_env_check(deployed={"fn": live}, candidate=candidate)

    assert is_secret_key("RESEND_API_KEY")
    rendered = " ".join(f.render() for f in result.findings)
    assert "super-secret-value" not in rendered
    assert "other-secret-value" not in rendered
    assert "sha256:" in rendered
    # A non-secret operational value is still compared by value.
    assert redact("JOB_QUEUE_MODE", "cloud_tasks") == "'cloud_tasks'"


def test_env_files_parse_quotes_and_comments():
    env = parse_env_file(
        '# comment\n'
        'JOB_QUEUE_MODE=cloud_tasks\n'
        'RESEND_FROM_EMAIL="설레연 <noreply@example.com>"\n'
        '\n'
        'EMPTY=\n'
    )

    assert env["JOB_QUEUE_MODE"] == "cloud_tasks"
    assert env["RESEND_FROM_EMAIL"] == "설레연 <noreply@example.com>"
    assert env["EMPTY"] == ""


def test_required_keys_are_derived_from_the_real_source():
    keys = required_env_keys_from_source(REPO_ROOT / "functions" / "src")

    assert "JOB_QUEUE_MODE" in keys
    assert "TASK_INVOKER_SERVICE_ACCOUNT" in keys
    # platform-injected names are excluded even though the code reads them
    assert not (keys & PLATFORM_MANAGED_KEYS)


def test_a_variable_the_code_reads_cannot_quietly_disappear():
    result = plan_functions_env_check(
        deployed={"fn": LIVE},
        candidate={"ENVIRONMENT": "staging"},
        required_from_source=["JOB_QUEUE_MODE"],
    )

    kinds = {(f.key, f.kind) for f in result.findings}
    assert ("JOB_QUEUE_MODE", "missing_required") in kinds


def test_an_added_variable_is_reported():
    """실제로 이 케이스가 심사 중인 앱의 온보딩 진입점에 beta allowlist 를 되살렸다."""
    candidate = {k: v for k, v in LIVE.items() if k not in PLATFORM_MANAGED_KEYS}
    candidate["AVATAR_UPLOAD_ALLOWED_UIDS"] = "uid_a,uid_b"

    blocked = plan_functions_env_check(
        deployed={"beginAvatarGenerationFromOnboardingPhotos": LIVE},
        candidate=candidate,
    )
    declared = plan_functions_env_check(
        deployed={"beginAvatarGenerationFromOnboardingPhotos": LIVE},
        candidate=candidate,
        allowed_additions=["AVATAR_UPLOAD_ALLOWED_UIDS"],
    )

    added = [f for f in blocked.findings if f.kind == "added"]
    assert [f.key for f in added] == ["AVATAR_UPLOAD_ALLOWED_UIDS"]
    assert declared.ok
