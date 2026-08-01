import importlib.util
import json
import os
import subprocess
import time
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "avatar_release_inventory.py"
MANIFEST_PATH = REPO_ROOT / "config" / "avatar-ops" / "avatar-release-manifest.json"


def load_inventory():
    if not SCRIPT_PATH.exists():
        pytest.fail(f"{SCRIPT_PATH} is missing")
    spec = importlib.util.spec_from_file_location("avatar_release_inventory", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeProcess:
    def __init__(self, *, stdout="{}", returncode=0, communicate_error=None):
        self.stdout_value = stdout
        self.returncode = returncode
        self.communicate_error = communicate_error
        self.communicate_timeouts = []
        self.pid = 12345

    def communicate(self, timeout):
        self.communicate_timeouts.append(timeout)
        if self.communicate_error is not None:
            raise self.communicate_error
        return self.stdout_value, None

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -1

    def wait(self, timeout):
        return self.returncode


class FakeRunner:
    def __init__(self):
        self.commands = []

    def __call__(self, command):
        self.commands.append(list(command))
        if command[:4] == ["gcloud", "functions", "list", "--project"]:
            return json.dumps(
                [
                    {
                        "name": "projects/seolleyeon-final/locations/asia-northeast3/functions/generateAvatarCandidate",
                        "state": "ACTIVE",
                        "serviceConfig": {
                            "availableMemory": "512Mi",
                            "timeoutSeconds": 540,
                            "environmentVariables": {"SECRET_KEY": "must-not-leak"},
                            "uri": "https://private.example/call?X-Goog-Signature=abc",
                        },
                    }
                ]
            )
        if command[:4] == ["gcloud", "run", "services", "list"]:
            return json.dumps(
                [
                    {
                        "metadata": {"name": "seolleyeon-avatar-worker"},
                        "spec": {
                            "template": {
                                "metadata": {
                                    "annotations": {
                                        "autoscaling.knative.dev/minScale": "0",
                                        "autoscaling.knative.dev/maxScale": "1",
                                    }
                                },
                                "spec": {
                                    "containerConcurrency": 1,
                                    "timeoutSeconds": 1800,
                                    "serviceAccountName": "avatar-worker@seolleyeon-final.iam.gserviceaccount.com",
                                    "containers": [
                                        {
                                            "image": (
                                                "asia-northeast3-docker.pkg.dev/seolleyeon-final/"
                                                "repo/worker@sha256:abc123"
                                            )
                                        }
                                    ],
                                },
                            }
                        },
                        "status": {
                            "latestReadyRevisionName": "seolleyeon-avatar-worker-00001-abc",
                            "url": "https://service.run.app",
                        },
                    }
                ]
            )
        if command[:4] == ["gcloud", "tasks", "queues", "describe"]:
            return json.dumps(
                {
                    "name": "projects/seolleyeon-final/locations/asia-northeast3/queues/avatar-generation",
                    "rateLimits": {"maxConcurrentDispatches": 1, "maxDispatchesPerSecond": 1.0},
                    "retryConfig": {"maxAttempts": 3, "minBackoff": "30s", "maxBackoff": "600s"},
                    "state": "RUNNING",
                }
            )
        if command[:4] == ["gcloud", "storage", "buckets", "describe"]:
            return json.dumps(
                {
                    "name": "seolleyeon-final-private-source-photos",
                    "uniform_bucket_level_access": True,
                    "public_access_prevention": "enforced",
                }
            )
        return "{}"


def test_manifest_versions_release_expectations_for_both_allowed_projects():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    assert data["schemaVersion"] == "avatar_release_manifest_v1"
    assert set(data["projects"]) == {"seolleyeon-final", "seolleyeon-festival"}
    assert "seolleyeon" not in data["projects"]

    for project in data["projects"].values():
        assert project["selectedFunctions"]
        assert project["cloudRunServices"]["seolleyeon-avatar-worker"]["privateInvocation"] is True
        assert project["cloudRunServices"]["seolleyeon-avatar-worker"]["minInstances"] == 0
        assert project["cloudRunServices"]["seolleyeon-avatar-worker"]["maxInstances"] == 1
        assert project["cloudRunServices"]["seolleyeon-avatar-worker"]["concurrency"] == 1
        assert project["queues"]["avatar-generation"]["rateLimits"]["maxConcurrentDispatches"] == 1
        assert project["queues"]["avatar-generation"]["rateLimits"]["maxDispatchesPerSecond"] == 1
        assert project["mediaBuckets"]["private-source-photos"]["uniformBucketLevelAccess"] is True
        assert project["evidencePlaceholders"]["appCheck"]
        assert project["evidencePlaceholders"]["rules"]
        assert project["evidencePlaceholders"]["hosting"]
        assert project["temporaryBridge"]["status"] == "temporary"


@pytest.mark.parametrize("project", ["", "default", "seolleyeon", "other-project"])
def test_refuses_empty_default_source_and_unapproved_projects(project):
    mod = load_inventory()

    with pytest.raises(ValueError, match="refusing project"):
        mod.build_release_report(project=project, manifest_path=MANIFEST_PATH, fixture_path=None)


def test_fixture_reports_known_festival_drift_without_sensitive_values(tmp_path):
    mod = load_inventory()
    fixture = {
        "functions": [],
        "cloudRunServices": [],
        "queues": {
            "avatar-generation": {
                "rateLimits": {"maxConcurrentDispatches": 1, "maxDispatchesPerSecond": 1},
                "retryConfig": {"maxAttempts": 3, "minBackoff": "30s", "maxBackoff": "600s"},
                "state": "RUNNING",
            }
        },
        "buckets": {
            "private-source-photos": {
                "uniformBucketLevelAccess": True,
                "publicAccessPrevention": "enforced",
                "retentionPolicy": "absent",
                "privateObjectPath": "gs://seolleyeon-festival-private-source-photos/user/source.jpg",
            }
        },
        "extra": {
            "signedUrl": "https://storage.googleapis.com/bucket/object?X-Goog-Signature=abc",
            "token": "ya29.secret",
            "identity": "person@example.com",
        },
    }
    fixture_path = tmp_path / "festival.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    report = mod.build_release_report(
        project="seolleyeon-festival",
        manifest_path=MANIFEST_PATH,
        fixture_path=fixture_path,
    )
    encoded = json.dumps(report, sort_keys=True)

    assert report["ok"] is False
    assert report["summary"]["expectedSelectedFunctions"] > 0
    assert report["summary"]["actualSelectedFunctions"] == 0
    assert {"field": "selectedFunctions.count", "severity": "error"}.items() <= report["drift"][0].items()
    assert any(item["field"] == "cloudRunServices.seolleyeon-avatar-worker.present" for item in report["drift"])
    assert any(item["field"] == "temporaryBridge.status" and item["severity"] == "warning" for item in report["drift"])
    assert "X-Goog-Signature" not in encoded
    assert "ya29" not in encoded
    assert "person@example.com" not in encoded
    assert "gs://seolleyeon-festival-private-source-photos/user/source.jpg" not in encoded


def test_live_mode_uses_only_read_only_gcloud_commands_and_sanitizes_revision_digest():
    mod = load_inventory()
    runner = FakeRunner()

    report = mod.build_release_report(
        project="seolleyeon-final",
        manifest_path=MANIFEST_PATH,
        fixture_path=None,
        runner=runner,
    )

    assert runner.commands
    assert all(
        any(read in command for read in ("list", "describe", "get-iam-policy"))
        for command in runner.commands
    )
    assert not any(any(write in command for write in ("deploy", "create", "update", "delete", "set-iam-policy")) for command in runner.commands)
    worker = report["inventory"]["cloudRunServices"]["seolleyeon-avatar-worker"]
    assert worker["latestReadyRevisionName"] == "seolleyeon-avatar-worker-00001-abc"
    assert worker["imageDigest"] == "sha256:abc123"
    encoded = json.dumps(report, sort_keys=True)
    assert "SECRET_KEY" not in encoded
    assert "private.example" not in encoded
    assert "service.run.app" not in encoded
    assert "avatar-worker@seolleyeon-final.iam.gserviceaccount.com" not in encoded



def test_live_inventory_detects_public_service_and_bucket_iam_without_emitting_members():
    mod = load_inventory()

    class PublicIamRunner(FakeRunner):
        def __call__(self, command):
            if "get-iam-policy" in command:
                return json.dumps(
                    {
                        "bindings": [
                            {"role": "roles/viewer", "members": ["allUsers"]}
                        ]
                    }
                )
            return super().__call__(command)

    report = mod.build_release_report(
        project="seolleyeon-final",
        manifest_path=MANIFEST_PATH,
        runner=PublicIamRunner(),
    )
    encoded = json.dumps(report, sort_keys=True)
    drift_fields = {item["field"] for item in report["drift"]}

    assert report["ok"] is False
    assert "cloudRunServices.seolleyeon-avatar-worker.privateInvocation" in drift_fields
    assert "mediaBuckets.private-source-photos.noPublicIamPrincipals" in drift_fields
    assert "allUsers" not in encoded


def test_storage_cli_snake_case_bucket_fields_are_normalized():
    mod = load_inventory()

    sanitized = mod._sanitize_bucket(
        {
            "uniform_bucket_level_access": True,
            "public_access_prevention": "enforced",
            "soft_delete_policy": {"retentionDurationSeconds": "604800"},
        }
    )

    assert sanitized == {
        "present": True,
        "uniformBucketLevelAccess": True,
        "publicAccessPrevention": "enforced",
        "noPublicIamPrincipals": True,
        "retentionPolicy": "absent",
    }


@pytest.mark.parametrize("executable", ["gcloud", "firebase"])
def test_default_runner_resolves_windows_cmd_launcher_without_shell(monkeypatch, executable):
    mod = load_inventory()
    launcher = rf"C:	ools{executable}.cmd"
    which_calls = []
    popen_calls = []
    process = FakeProcess()

    def fake_which(candidate):
        which_calls.append(candidate)
        return launcher if candidate == f"{executable}.cmd" else None

    def fake_popen(command, **kwargs):
        popen_calls.append((list(command), kwargs))
        return process

    monkeypatch.setattr(mod.shutil, "which", fake_which)
    monkeypatch.setattr(mod, "_create_windows_kill_job", lambda: 99)
    monkeypatch.setattr(mod, "_assign_and_resume_windows_process", lambda process, job: None)
    monkeypatch.setattr(mod, "_close_windows_handle", lambda handle: None)
    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)

    assert mod._run_json_command([executable, "example", "list"], timeout_seconds=9) == "{}"
    assert which_calls == [executable, f"{executable}.cmd"]
    assert popen_calls[0][0] == [launcher, "example", "list"]
    assert popen_calls[0][1]["shell"] is False
    assert process.communicate_timeouts == [9]

@pytest.mark.parametrize(
    ("failure_kind", "expected_error"),
    [
        ("timeout", "timeout"),
        ("nonzero", "command-failed"),
        ("missing", "missing-executable"),
    ],
)
def test_live_failures_emit_partial_report_and_continue(monkeypatch, failure_kind, expected_error):
    mod = load_inventory()
    successful = FakeRunner()
    run_commands = []

    def fake_start_process(command):
        run_commands.append(list(command))
        if len(run_commands) == 1:
            if failure_kind == "timeout":
                return (
                    FakeProcess(
                        communicate_error=subprocess.TimeoutExpired(
                            command,
                            7,
                            output="sensitive timeout stdout",
                            stderr="sensitive timeout stderr",
                        )
                    ),
                    99,
                )
            if failure_kind == "missing":
                raise FileNotFoundError("private-missing-executable-path")
            return FakeProcess(stdout="sensitive failed stdout", returncode=1), 99
        return FakeProcess(stdout=successful(command)), 99

    monkeypatch.setattr(mod, "_resolve_executable", lambda executable: executable)
    monkeypatch.setattr(mod, "_start_process", fake_start_process)
    monkeypatch.setattr(mod, "_terminate_process_tree", lambda process, job: None)
    monkeypatch.setattr(mod, "_drain_terminated_process", lambda process: None)
    monkeypatch.setattr(mod, "_close_windows_handle", lambda handle: None)

    report = mod.build_release_report(
        project="seolleyeon-final",
        manifest_path=MANIFEST_PATH,
        command_timeout_seconds=7,
    )
    selected = report["inventory"]["selectedFunctions"]
    encoded = json.dumps(report, sort_keys=True)

    assert len(run_commands) == 10
    assert report["complete"] is False
    assert report["ok"] is False
    assert report["summary"]["incompleteResources"] == 1
    assert selected["status"] == "unavailable"
    assert selected["error"] == expected_error
    assert report["inventory"]["cloudRunServices"]["seolleyeon-avatar-worker"]["present"] is True
    assert report["summary"]["actualQueues"] == 1
    assert report["summary"]["actualMediaBuckets"] == 3
    assert any(item["field"] == "selectedFunctions.inventory" for item in report["drift"])
    assert "sensitive" not in encoded
    assert "private-missing-executable-path" not in encoded


def test_cli_forwards_bounded_command_timeout(monkeypatch):
    mod = load_inventory()
    captured = {}

    def fake_build_release_report(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(mod, "build_release_report", fake_build_release_report)

    assert 1 <= mod.DEFAULT_COMMAND_TIMEOUT_SECONDS <= mod.MAX_COMMAND_TIMEOUT_SECONDS <= 120
    assert mod.main(["--project", "seolleyeon-final", "--command-timeout-seconds", "7"]) == 0
    assert captured["command_timeout_seconds"] == 7

@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree timeout regression")
def test_windows_timeout_kills_descendant_tree_with_bounded_wall_time():
    mod = load_inventory()
    command = [
        os.environ.get("COMSPEC", "cmd.exe"),
        "/d",
        "/c",
        "ping -n 7 127.0.0.1",
    ]

    started = time.monotonic()
    with pytest.raises(mod.InventoryCommandError) as caught:
        mod._run_json_command(command, timeout_seconds=1)
    elapsed = time.monotonic() - started

    assert caught.value.error == "timeout"
    assert elapsed < 4