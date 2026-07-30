import importlib.util
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "avatar_observability_reconcile.py"
CONFIG_PATH = REPO_ROOT / "config" / "avatar-ops" / "avatar-observability.json"


def load_reconciler():
    if not SCRIPT_PATH.exists():
        pytest.fail(f"{SCRIPT_PATH} is missing")
    spec = importlib.util.spec_from_file_location("avatar_observability_reconcile", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeRunner:
    def __init__(self, existing=(), remote_resources=None):
        self.commands = []
        self.existing = set(existing)
        self.remote_resources = dict(remote_resources or {})
        self.policy_bodies = []

    def __call__(self, command):
        self.commands.append(list(command))
        if "--policy-from-file" in command:
            path = Path(command[command.index("--policy-from-file") + 1])
            self.policy_bodies.append(json.loads(path.read_text(encoding="utf-8")))
        if "describe" in command:
            name = command[command.index("describe") + 1]
            if name in self.remote_resources:
                return SimpleNamespace(
                    returncode=0,
                    stdout=json.dumps(self.remote_resources[name]),
                    stderr="",
                )
            if name in self.existing:
                return SimpleNamespace(returncode=0, stdout="{}", stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr="resource not found")
        if "list" in command:
            matches = [
                body
                for body in self.remote_resources.values()
                if body.get("displayName")
            ]
            for name in self.existing:
                if "-" not in name:
                    continue
                display_name = f"Avatar {name.removeprefix('avatar-').replace('-', ' ')}"
                resource_kind = "dashboards" if "dashboards" in command else "alertPolicies"
                matches.append(
                    {
                        "name": f"projects/test-project/{resource_kind}/{name}-remote",
                        "displayName": display_name,
                    }
                )
            return SimpleNamespace(returncode=0, stdout=json.dumps(matches), stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def test_run_command_resolves_windows_gcloud_cmd_without_shell_and_captures_output(monkeypatch):
    mod = load_reconciler()
    resolved = r"C:\Program Files\Google\Cloud SDK\bin\gcloud.cmd"
    captured = {}

    def fake_which(candidate):
        return resolved if candidate == "gcloud.cmd" else None

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout='{"name":"remote"}', stderr="")

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(mod, "WINDOWS", True, raising=False)
    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    result = mod.run_command(["gcloud", "version"])

    assert captured["command"] == [resolved, "version"]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["capture_output"] is True
    assert captured["kwargs"]["text"] is True
    assert result.returncode == 0
    assert result.stdout == '{"name":"remote"}'


def test_config_is_versioned_and_covers_required_observability_signals():
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert data["schemaVersion"] == "avatar_observability_reconcile_v1"

    names = {item["name"] for item in data["logMetrics"]}
    policies = {item["name"] for item in data["alertPolicies"]}
    widgets = {item["title"] for item in data["dashboard"]["widgets"]}

    for required in (
        "avatar_worker_unhealthy",
        "avatar_job_failed",
        "avatar_queue_depth",
        "avatar_deadline_stop",
        "avatar_retry_scheduled",
        "avatar_cost_guard_daily",
        "avatar_cost_guard_monthly",
        "avatar_qa_no_preview",
        "avatar_qa_reject",
        "avatar_qa_review_required",
        "avatar_iam_failure",
        "avatar_app_check_failure",
        "avatar_bridge_auth_failure",
        "avatar_bridge_isolation_violation",
    ):
        assert required in names
        assert required.removeprefix("avatar_") in policies
    assert {"Avatar worker", "Queue health", "Cost guard", "QA", "Security and bridge"} <= widgets


def test_generated_bodies_match_gcloud_logging_and_monitoring_contracts():
    mod = load_reconciler()
    plan = mod.reconcile(
        config_path=CONFIG_PATH,
        project="seolleyeon-final",
        mode="plan",
    )
    operations = plan["plannedOperations"]

    metrics = [item["body"] for item in operations if item["kind"] == "logMetric"]
    assert metrics
    assert all(
        extractor.startswith("EXTRACT(") and extractor.endswith(")")
        for metric in metrics
        for extractor in metric["labelExtractors"].values()
    )

    policies = [item["body"] for item in operations if item["kind"] == "alertPolicy"]
    assert policies
    assert all(
        policy["conditions"][0]["conditionThreshold"]["comparison"] == "COMPARISON_GT"
        for policy in policies
    )
    assert min(
        policy["conditions"][0]["conditionThreshold"]["thresholdValue"]
        for policy in policies
    ) == 0.0

    dashboard = next(item["body"] for item in operations if item["kind"] == "dashboard")
    tiles = dashboard["mosaicLayout"]["tiles"]
    assert len({(tile["xPos"], tile["yPos"]) for tile in tiles}) == len(tiles)


def test_remote_projection_normalizes_api_order_and_omitted_zero_only():
    mod = load_reconciler()

    desired = {
        "thresholdValue": 0.0,
        "mosaicLayout": {"xPos": 0, "yPos": 0},
        "labels": [{"key": "a", "valueType": "STRING"}, {"key": "b", "valueType": "STRING"}],
    }
    remote = {
        "mosaicLayout": {},
        "labels": [{"key": "b"}, {"key": "a"}],
    }

    assert mod._project_remote_body(remote, desired) == desired
    assert mod._project_remote_body({"xPos": 1}, {"xPos": 0}) == {"xPos": 1}


def test_default_plan_causes_zero_mutations_and_runs_no_gcloud():
    mod = load_reconciler()
    runner = FakeRunner()

    report = mod.reconcile(
        config_path=CONFIG_PATH,
        project="seolleyeon-final",
        mode="plan",
        notification_channels=[],
        runner=runner,
    )

    assert report["mode"] == "plan"
    assert report["mutations"] == []
    assert runner.commands == []
    assert all(op["action"] in {"create", "update"} for op in report["plannedOperations"])


@pytest.mark.parametrize("project", ["", "default", "seolleyeon", "my-staging"])
def test_forbidden_or_unapproved_project_is_hard_rejected(project):
    mod = load_reconciler()

    with pytest.raises(ValueError, match="refusing project"):
        mod.reconcile(
            config_path=CONFIG_PATH,
            project=project,
            mode="plan",
            notification_channels=[],
            runner=FakeRunner(),
        )


def test_verify_returns_sanitized_resource_existence_and_drift_without_mutating():
    mod = load_reconciler()
    plan = mod.reconcile(
        config_path=CONFIG_PATH,
        project="seolleyeon-festival",
        mode="plan",
    )
    operations = {operation["name"]: operation for operation in plan["plannedOperations"]}
    worker_remote = json.loads(json.dumps(operations["avatar_worker_unhealthy"]["body"]))
    worker_remote["name"] = (
        "projects/seolleyeon-festival/metrics/avatar_worker_unhealthy"
    )
    failed_job_remote = json.loads(json.dumps(operations["avatar_job_failed"]["body"]))
    failed_job_remote["filter"] = "REMOTE_FILTER_SHOULD_NOT_LEAK"
    runner = FakeRunner(
        remote_resources={
            "avatar_worker_unhealthy": worker_remote,
            "avatar_job_failed": failed_job_remote,
        }
    )

    report = mod.reconcile(
        config_path=CONFIG_PATH,
        project="seolleyeon-festival",
        mode="verify",
        notification_channels=[],
        runner=runner,
    )

    verification = {item["name"]: item for item in report["verification"]}
    assert verification["avatar_worker_unhealthy"]["exists"] is True
    assert verification["avatar_worker_unhealthy"]["drift"] is False
    assert verification["avatar_worker_unhealthy"]["status"] == "in_sync"
    assert verification["avatar_job_failed"]["exists"] is True
    assert verification["avatar_job_failed"]["drift"] is True
    assert verification["avatar_job_failed"]["status"] == "drifted"
    assert verification["avatar_queue_depth"]["exists"] is False
    assert verification["avatar_queue_depth"]["drift"] is True
    assert verification["avatar_queue_depth"]["status"] == "missing"
    assert report["mode"] == "verify"
    assert report["mutations"] == []
    assert runner.commands
    assert all("describe" in command or "list" in command for command in runner.commands)
    assert all("--format=json" in command for command in runner.commands)
    assert all("body" not in operation for operation in report["plannedOperations"])

    serialized = json.dumps(report, sort_keys=True)
    assert "REMOTE_FILTER_SHOULD_NOT_LEAK" not in serialized
    assert '"stdout"' not in serialized
    assert '"stderr"' not in serialized
    assert '"command"' not in serialized


def test_apply_is_opt_in_and_generates_idempotent_create_update_gcloud_operations():
    mod = load_reconciler()
    runner = FakeRunner(existing={"avatar_worker_unhealthy", "avatar-cost-guard-daily"})

    report = mod.reconcile(
        config_path=CONFIG_PATH,
        project="seolleyeon-final",
        mode="apply",
        notification_channels=["projects/seolleyeon-final/notificationChannels/123"],
        runner=runner,
    )

    assert report["mode"] == "apply"
    assert report["mutations"]
    joined = "\n".join(" ".join(command) for command in runner.commands)
    assert "metrics describe avatar_worker_unhealthy" in joined
    assert "metrics update avatar_worker_unhealthy" in joined
    assert "policies update projects/test-project/alertPolicies/avatar-cost-guard-daily-remote" in joined
    assert "metrics create avatar_job_failed" in joined
    assert "policies create avatar-job-failed" not in joined
    assert "dashboards create avatar-observability" not in joined
    assert "notificationChannels/123" not in joined
    assert any(
        "projects/seolleyeon-final/notificationChannels/123"
        in body.get("notificationChannels", [])
        for body in runner.policy_bodies
    )
    assert "gs://" not in joined
    assert "token" not in joined.lower()
    assert "secret" not in joined.lower()


def test_notification_channels_are_never_fabricated():
    mod = load_reconciler()
    report = mod.reconcile(
        config_path=CONFIG_PATH,
        project="seolleyeon-final",
        mode="plan",
        notification_channels=[],
        runner=FakeRunner(),
    )

    policies = [op["body"] for op in report["plannedOperations"] if op["kind"] == "alertPolicy"]
    assert policies
    assert all("notificationChannels" not in policy for policy in policies)


def test_apply_preserves_existing_notification_channels_when_none_are_supplied():
    mod = load_reconciler()
    plan = mod.reconcile(
        config_path=CONFIG_PATH,
        project="seolleyeon-final",
        mode="plan",
    )
    policy_operation = next(
        operation
        for operation in plan["plannedOperations"]
        if operation["kind"] == "alertPolicy"
    )
    remote = json.loads(json.dumps(policy_operation["body"]))
    remote["name"] = "projects/seolleyeon-final/alertPolicies/policy-123"
    remote["notificationChannels"] = [
        "projects/seolleyeon-final/notificationChannels/channel-123"
    ]
    runner = FakeRunner(remote_resources={"existing-policy": remote})

    report = mod.reconcile(
        config_path=CONFIG_PATH,
        project="seolleyeon-final",
        mode="apply",
        notification_channels=[],
        runner=runner,
    )

    matching_bodies = [
        body
        for body in runner.policy_bodies
        if body.get("displayName") == remote["displayName"]
    ]
    assert matching_bodies
    assert matching_bodies[0]["notificationChannels"] == remote["notificationChannels"]
    assert report["ok"] is True


def test_apply_fails_closed_when_temp_file_cleanup_fails(monkeypatch):
    mod = load_reconciler()
    runner = FakeRunner()

    def fail_unlink(_self, *, missing_ok=False):
        raise OSError("cleanup failed")

    monkeypatch.setattr(mod.Path, "unlink", fail_unlink)
    report = mod.reconcile(
        config_path=CONFIG_PATH,
        project="seolleyeon-final",
        mode="apply",
        runner=runner,
    )
    monkeypatch.undo()
    for command in runner.commands:
        for flag in ("--policy-from-file", "--config-from-file"):
            if flag in command:
                Path(command[command.index(flag) + 1]).unlink(missing_ok=True)

    assert report["ok"] is False
    assert report["mutations"]
    assert all(item["tempFileCleanup"] is False for item in report["mutations"])

def test_filters_use_low_cardinality_labels_and_canonical_events_only():
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    encoded = json.dumps(data, sort_keys=True)
    assert "uid" not in encoded
    assert "jobId" not in encoded
    assert "sourceRef" not in encoded
    assert "signedUrl" not in encoded
    assert "resource.labels" not in encoded
    for metric in data["logMetrics"]:
        labels = metric.get("labels", {})
        assert set(labels) <= {"service", "event_name", "status", "severity", "component", "signal"}






