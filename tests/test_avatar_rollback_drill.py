import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "avatar_rollback_drill.py"
CONFIG_PATH = REPO_ROOT / "config" / "avatar-ops" / "avatar-rollback.json"


def load_drill():
    if not SCRIPT_PATH.exists():
        pytest.fail(f"{SCRIPT_PATH} is missing")
    spec = importlib.util.spec_from_file_location("avatar_rollback_drill", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeRunner:
    def __init__(self, source_before=None, source_after=None):
        self.commands = []
        self.source_before = source_before or {"objectCount": 17, "totalBytes": 4096}
        self.source_after = source_after or dict(self.source_before)
        self.source_reads = 0

    def __call__(self, command):
        self.commands.append(list(command))
        joined = " ".join(command)
        if command[:3] == ["gcloud", "storage", "du"]:
            self.source_reads += 1
            return json.dumps(self.source_before if self.source_reads == 1 else self.source_after)
        if command[:4] == ["gcloud", "tasks", "queues", "describe"]:
            return json.dumps({"backlogCount": 3, "claimRatePerMinute": 0})
        if "avatar_job_lease_sweeper.py" in joined:
            return json.dumps({"staleLeaseCount": 2, "wouldRecover": 2})
        if "avatar_media_cleanup.py" in joined:
            return json.dumps({"deletedCount": 0, "wouldDeleteCount": 5})
        return json.dumps({"ok": True})


def test_config_is_versioned_and_limited_to_explicit_staging_projects():
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    assert data["schemaVersion"] == "avatar_rollback_drill_v1"
    assert set(data["allowedProjects"]) == {"seolleyeon-final", "seolleyeon-festival"}
    assert "seolleyeon" not in data["projects"]
    assert "source object delete" in data["forbiddenOperations"]


@pytest.mark.parametrize("project", ["", "default", "seolleyeon", "other-project"])
def test_project_guards_reject_empty_source_and_unapproved_projects(project):
    drill = load_drill()

    with pytest.raises(ValueError, match="refusing project"):
        drill.build_rollback_report(project=project, config_path=CONFIG_PATH)


def test_default_plan_is_ordered_sanitized_and_performs_zero_mutations():
    drill = load_drill()
    runner = FakeRunner()

    report = drill.build_rollback_report(
        project="seolleyeon-final",
        config_path=CONFIG_PATH,
        runner=runner,
    )
    rendered = drill.format_report(report)

    assert runner.commands == []
    assert report["mode"] == "plan"
    assert report["applied"] is False
    assert report["mutationsPerformed"] == 0
    assert [step["name"] for step in report["plan"]] == [
        "disable_generation_cost_kill_switch",
        "pause_queue",
        "verify_claim_rate_backlog",
        "dry_run_stale_lease_recovery",
        "dry_run_temp_rejected_cleanup",
        "verify_private_source_aggregate_unchanged",
        "optional_route_prior_worker_revision",
        "resume_requires_separate_confirmation",
    ]
    assert "gs://" not in rendered
    assert "X-Goog-" not in rendered
    assert "sourcePhotoRefs" not in rendered


def test_verify_runs_only_read_and_dry_run_steps_and_preserves_source_aggregate():
    drill = load_drill()
    runner = FakeRunner()

    report = drill.build_rollback_report(
        project="seolleyeon-festival",
        config_path=CONFIG_PATH,
        mode="verify",
        runner=runner,
    )

    assert report["applied"] is False
    assert report["mutationsPerformed"] == 0
    assert report["sourcePreservation"] == {
        "verified": True,
        "unchanged": True,
        "before": {"objectCount": 17, "totalBytes": 4096},
        "after": {"objectCount": 17, "totalBytes": 4096},
    }
    assert [item["name"] for item in report["executed"]] == [
        "disable_generation_cost_kill_switch",
        "pause_queue",
        "verify_claim_rate_backlog",
        "dry_run_stale_lease_recovery",
        "dry_run_temp_rejected_cleanup",
        "verify_private_source_aggregate_unchanged",
        "optional_route_prior_worker_revision",
        "resume_requires_separate_confirmation",
    ]
    assert all(
        "pause" not in command and "update" not in command and "deploy" not in command
        for command in runner.commands
    )
    assert any("avatar_media_cleanup.py" in command for command in runner.commands for command in command)
    cleanup_commands = [command for command in runner.commands if "scripts/avatar_media_cleanup.py" in command]
    assert cleanup_commands == [
        [
            drill.sys.executable,
            "scripts/avatar_media_cleanup.py",
            "--mode",
            "expired_candidates",
            "--dry_run",
            "--firestore_project",
            "seolleyeon-festival",
        ]
    ]


def test_source_invariant_requires_a_real_aggregate_signal():
    drill = load_drill()

    assert drill._source_invariant(
        {"objectCount": None, "totalBytes": None},
        {"objectCount": None, "totalBytes": None},
    ) == {"verified": False, "unchanged": None}


def test_source_aggregate_parses_gcloud_du_text_without_exposing_path():
    drill = load_drill()

    aggregate = drill._source_aggregate(
        lambda _command: "4096  gs://private-source-bucket",
        "seolleyeon-final",
        {"privateSourceBucketSuffix": "private-source-photos"},
    )

    assert aggregate == {"objectCount": None, "totalBytes": 4096}


def test_apply_requires_opt_in_and_confirmation_token_before_mutation():
    drill = load_drill()
    runner = FakeRunner()

    with pytest.raises(drill.RollbackDrillError, match="apply requires"):
        drill.build_rollback_report(
            project="seolleyeon-final",
            config_path=CONFIG_PATH,
            mode="apply",
            runner=runner,
        )

    assert runner.commands == []


def test_apply_runs_bounded_mutations_in_order_after_confirmation():
    drill = load_drill()
    runner = FakeRunner()

    report = drill.build_rollback_report(
        project="seolleyeon-final",
        config_path=CONFIG_PATH,
        mode="apply",
        apply=True,
        confirmation_token="APPLY_AVATAR_ROLLBACK:seolleyeon-final:avatar_rollback_drill_v1",
        prior_worker_revision="seolleyeon-avatar-worker-00012-prev",
        runner=runner,
    )

    step_commands = [
        command
        for command in runner.commands
        if not (command[:3] == ["gcloud", "storage", "du"])
    ]
    assert [item["name"] for item in report["executed"]] == [
        "disable_generation_cost_kill_switch",
        "pause_queue",
        "verify_claim_rate_backlog",
        "dry_run_stale_lease_recovery",
        "dry_run_temp_rejected_cleanup",
        "verify_private_source_aggregate_unchanged",
        "optional_route_prior_worker_revision",
        "resume_requires_separate_confirmation",
    ]
    assert step_commands[0][:4] == ["gcloud", "run", "services", "update"]
    assert "--update-env-vars" in step_commands[0]
    assert "--set-env-vars" not in step_commands[0]
    assert step_commands[1][:4] == ["gcloud", "tasks", "queues", "pause"]
    assert "scripts/avatar_media_cleanup.py" in step_commands[4]
    assert "--mode" in step_commands[4]
    assert "--dry_run" in step_commands[4]
    assert step_commands[5][:4] == ["gcloud", "run", "services", "update-traffic"]
    assert report["mutationsPerformed"] == 3
    assert report["sourcePreservation"]["unchanged"] is True


def test_resume_is_not_performed_without_separate_confirmation():
    drill = load_drill()
    runner = FakeRunner()

    report = drill.build_rollback_report(
        project="seolleyeon-final",
        config_path=CONFIG_PATH,
        mode="apply",
        apply=True,
        confirmation_token="APPLY_AVATAR_ROLLBACK:seolleyeon-final:avatar_rollback_drill_v1",
        runner=runner,
    )

    assert not any("resume" in command for command in runner.commands)
    assert report["plan"][-1]["requiresSeparateConfirmation"] is True


def test_forbidden_cleanup_source_delete_and_sensitive_output_are_blocked():
    drill = load_drill()

    with pytest.raises(drill.RollbackDrillError, match="forbidden cleanup"):
        drill._assert_safe_command(["python", "scripts/source-retention-cleanup.py", "--apply"])
    with pytest.raises(drill.RollbackDrillError, match="source delete"):
        drill._assert_safe_command(["gcloud", "storage", "rm", "gs://bucket/source/object", "--delete"])
    with pytest.raises(drill.RollbackDrillError, match="sensitive"):
        drill.format_report({"path": "gs://private-source/users/u/source.jpg?X-Goog-Signature=secret"})





def test_run_command_resolves_windows_cmd_shim_without_shell(monkeypatch):
    drill = load_drill()
    calls = []

    def fake_which(name):
        return {
            "gcloud": None,
            "gcloud.cmd": r"C:\tools\google-cloud-sdk\bin\gcloud.cmd",
        }.get(name)

    class Completed:
        returncode = 0
        stdout = '{"backlogCount": 0}'
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(drill.shutil, "which", fake_which)
    monkeypatch.setattr(drill.subprocess, "run", fake_run)

    output = drill._run_command(["gcloud", "tasks", "queues", "describe", "avatar-generation"])

    assert json.loads(output) == {"backlogCount": 0}
    assert calls == [
        (
            [
                r"C:\tools\google-cloud-sdk\bin\gcloud.cmd",
                "tasks",
                "queues",
                "describe",
                "avatar-generation",
            ],
            {
                "check": False,
                "capture_output": True,
                "text": True,
                "shell": False,
            },
        )
    ]


def test_verify_missing_cli_returns_sanitized_failed_report():
    drill = load_drill()

    def missing_runner(_command):
        raise FileNotFoundError(r"C:\private\users\uid-123\gcloud.cmd token=secret")

    report = drill.build_rollback_report(
        project="seolleyeon-final",
        config_path=CONFIG_PATH,
        mode="verify",
        runner=missing_runner,
    )
    rendered = drill.format_report(report)

    assert report["verification"] == {"passed": False, "failureCount": 6}
    assert report["sourcePreservation"] == {"verified": False, "unchanged": None}
    assert [item["status"] for item in report["executed"]] == [
        "skipped_mutation_in_verify",
        "skipped_mutation_in_verify",
        "failed_command_unavailable",
        "failed_command_unavailable",
        "failed_command_unavailable",
        "failed_command_unavailable",
        "executed",
        "executed",
    ]
    assert "uid-123" not in rendered
    assert "token=secret" not in rendered
    assert "Traceback" not in rendered

def test_verify_keeps_only_numeric_aggregates_from_command_output():
    drill = load_drill()

    class SensitiveOutputRunner(FakeRunner):
        def __call__(self, command):
            if command[:4] == ["gcloud", "tasks", "queues", "describe"]:
                self.commands.append(list(command))
                return json.dumps(
                    {
                        "backlogCount": "uid-123 token=secret",
                        "claimRatePerMinute": 0,
                        "privatePath": r"C:\private\source\object.jpg",
                    }
                )
            return super().__call__(command)

    report = drill.build_rollback_report(
        project="seolleyeon-final",
        config_path=CONFIG_PATH,
        mode="verify",
        runner=SensitiveOutputRunner(),
    )
    rendered = drill.format_report(report)

    claim_record = next(
        item for item in report["executed"] if item["name"] == "verify_claim_rate_backlog"
    )
    assert claim_record["aggregate"] == {"claimRatePerMinute": 0}
    assert "uid-123" not in rendered
    assert "token=secret" not in rendered
    assert "privatePath" not in rendered