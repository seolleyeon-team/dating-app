import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(module_name: str, file_name: str):
    path = REPO_ROOT / "scripts" / file_name
    if not path.exists():
        pytest.fail(f"{path} is missing")
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_backlog_metrics_counts_stale_retryable_and_cost_estimates():
    status = load_script("avatar_queue_status", "avatar_queue_status.py")
    now = datetime(2026, 5, 14, 0, 0, 0, tzinfo=timezone.utc)
    jobs = [
        {
            "status": "queued",
            "createdAt": now - timedelta(seconds=60),
            "candidateCount": 4,
        },
        {
            "status": "running",
            "createdAt": now - timedelta(seconds=120),
            "candidateCount": 2,
            "processing": {"leaseExpiresAt": now + timedelta(seconds=30)},
        },
        {
            "status": "running",
            "createdAt": now - timedelta(seconds=300),
            "candidateCount": 4,
            "processing": {"leaseExpiresAt": now - timedelta(seconds=1)},
        },
        {
            "status": "failed",
            "createdAt": now - timedelta(seconds=600),
            "candidateCount": 1,
        },
        {
            "status": "preview_ready",
            "createdAt": now - timedelta(seconds=900),
            "candidateCount": 4,
        },
    ]

    summary = status.summarize_jobs(
        jobs,
        now=now,
        estimate_config=status.EstimateConfig(
            batch_size=4,
            gpu_seconds_per_candidate=10.0,
            gpu_cost_per_second_usd=0.01,
            default_candidate_count=4,
        ),
    )

    assert summary["counts"] == {
        "total": 5,
        "queued": 1,
        "running": 2,
        "stale": 1,
        "retryable": 1,
        "preview_ready": 1,
    }
    assert summary["queue_age_seconds"] == {
        "sample_count": 4,
        "average": 270.0,
        "p95": 600.0,
        "max": 600.0,
    }
    assert summary["estimates"] == {
        "actionable_jobs": 3,
        "candidate_count": 9,
        "estimated_batches": 3,
        "estimated_gpu_seconds": 90.0,
        "estimated_gpu_cost_usd": 0.9,
    }


def test_production_cloud_tasks_missing_oidc_config_fails_fast():
    config = load_script("avatar_queue_config_check", "avatar_queue_config_check.py")
    env = {
        "ENVIRONMENT": "production",
        "JOB_QUEUE_MODE": "cloud_tasks",
        "CLOUD_TASKS_PROJECT": "seolleyeon-prod",
        "GCP_LOCATION": "asia-northeast3",
        "AVATAR_GENERATION_QUEUE_NAME": "avatar-generation",
        "CLIP_EMBEDDING_QUEUE_NAME": "clip-embedding",
        "AVATAR_GENERATION_TASK_URL": "https://avatar-worker.example/tasks/avatar-generation",
        "CLIP_EMBEDDING_TASK_URL": "https://clip-worker.example/tasks/clip-embedding",
        "AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES": "1",
        "AVATAR_QUEUE_MAX_DISPATCHES_PER_SECOND": "1",
        "AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS": "900",
        "AVATAR_QUEUE_MAX_ATTEMPTS": "3",
        "AVATAR_QUEUE_MIN_BACKOFF_SECONDS": "30",
        "AVATAR_QUEUE_MAX_BACKOFF_SECONDS": "600",
        "AVATAR_QUEUE_MAX_DOUBLINGS": "4",
        "AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS": "1",
    }

    report = config.validate_queue_config(env)

    assert report["ok"] is False
    assert any(
        issue["severity"] == "error"
        and "TASK_INVOKER_SERVICE_ACCOUNT" in issue["message"]
        for issue in report["issues"]
    )


def test_queue_config_rejects_unbounded_gpu_fanout():
    config = load_script("avatar_queue_config_check", "avatar_queue_config_check.py")
    env = {
        "ENVIRONMENT": "production",
        "JOB_QUEUE_MODE": "cloud_tasks",
        "CLOUD_TASKS_PROJECT": "seolleyeon-prod",
        "GCP_LOCATION": "asia-northeast3",
        "AVATAR_GENERATION_QUEUE_NAME": "avatar-generation",
        "CLIP_EMBEDDING_QUEUE_NAME": "clip-embedding",
        "AVATAR_GENERATION_TASK_URL": "https://avatar-worker.example/tasks/avatar-generation",
        "CLIP_EMBEDDING_TASK_URL": "https://clip-worker.example/tasks/clip-embedding",
        "TASK_INVOKER_SERVICE_ACCOUNT": "task-invoker@seolleyeon-prod.iam.gserviceaccount.com",
        "AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES": "8",
        "AVATAR_QUEUE_MAX_DISPATCHES_PER_SECOND": "1",
        "AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS": "900",
        "AVATAR_QUEUE_MAX_ATTEMPTS": "3",
        "AVATAR_QUEUE_MIN_BACKOFF_SECONDS": "30",
        "AVATAR_QUEUE_MAX_BACKOFF_SECONDS": "600",
        "AVATAR_QUEUE_MAX_DOUBLINGS": "4",
        "AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS": "1",
    }

    report = config.validate_queue_config(env)

    assert report["ok"] is False
    assert any("unbounded GPU fanout" in issue["message"] for issue in report["issues"])


def test_queue_config_allows_avatar_only_staging_without_clip_worker():
    config = load_script("avatar_queue_config_check", "avatar_queue_config_check.py")
    env = {
        "ENVIRONMENT": "production",
        "JOB_QUEUE_MODE": "cloud_tasks",
        "CLOUD_TASKS_PROJECT": "seolleyeon-final",
        "GCP_LOCATION": "asia-northeast3",
        "AVATAR_GENERATION_QUEUE_NAME": "avatar-generation",
        "AVATAR_GENERATION_TASK_URL": "https://avatar-worker.example/tasks/avatar-generation",
        "TASK_INVOKER_SERVICE_ACCOUNT": "task-invoker@seolleyeon-final.iam.gserviceaccount.com",
        "CLIP_EMBEDDING_QUEUE_ENABLED": "false",
        "AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES": "1",
        "AVATAR_QUEUE_MAX_DISPATCHES_PER_SECOND": "1",
        "AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS": "900",
        "AVATAR_QUEUE_MAX_ATTEMPTS": "3",
        "AVATAR_QUEUE_MIN_BACKOFF_SECONDS": "30",
        "AVATAR_QUEUE_MAX_BACKOFF_SECONDS": "600",
        "AVATAR_QUEUE_MAX_DOUBLINGS": "4",
        "AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS": "1",
    }

    report = config.validate_queue_config(env)

    assert report["ok"] is True
    assert not any(
        issue["field"] in {"CLIP_EMBEDDING_QUEUE_NAME", "CLIP_EMBEDDING_TASK_URL"}
        and issue["severity"] == "error"
        for issue in report["issues"]
    )


def test_queue_config_rejects_placeholder_worker_urls():
    config = load_script("avatar_queue_config_check", "avatar_queue_config_check.py")
    env = {
        "ENVIRONMENT": "production",
        "JOB_QUEUE_MODE": "cloud_tasks",
        "CLOUD_TASKS_PROJECT": "seolleyeon-final",
        "GCP_LOCATION": "asia-northeast3",
        "AVATAR_GENERATION_QUEUE_NAME": "avatar-generation",
        "AVATAR_GENERATION_TASK_URL": "https://AVATAR_WORKER/tasks/avatar-generation",
        "TASK_INVOKER_SERVICE_ACCOUNT": "task-invoker@seolleyeon-final.iam.gserviceaccount.com",
        "CLIP_EMBEDDING_QUEUE_ENABLED": "false",
        "AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES": "1",
        "AVATAR_QUEUE_MAX_DISPATCHES_PER_SECOND": "1",
        "AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS": "900",
        "AVATAR_QUEUE_MAX_ATTEMPTS": "3",
        "AVATAR_QUEUE_MIN_BACKOFF_SECONDS": "30",
        "AVATAR_QUEUE_MAX_BACKOFF_SECONDS": "600",
        "AVATAR_QUEUE_MAX_DOUBLINGS": "4",
        "AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS": "1",
    }

    report = config.validate_queue_config(env)

    assert report["ok"] is False
    assert any(
        issue["field"] == "AVATAR_GENERATION_TASK_URL"
        and "placeholder" in issue["message"]
        for issue in report["issues"]
    )


def test_queue_config_can_load_dotenv_file(tmp_path):
    config = load_script("avatar_queue_config_check", "avatar_queue_config_check.py")
    env_file = tmp_path / "functions.env"
    env_file.write_text(
        "\n".join(
            [
                "ENVIRONMENT=production",
                "JOB_QUEUE_MODE=cloud_tasks",
                "CLOUD_TASKS_PROJECT=seolleyeon-final",
                "GCP_LOCATION=asia-northeast3",
                "AVATAR_GENERATION_QUEUE_NAME=avatar-generation",
                "AVATAR_GENERATION_TASK_URL=https://avatar-worker.example/tasks/avatar-generation",
                "TASK_INVOKER_SERVICE_ACCOUNT=task-invoker@seolleyeon-final.iam.gserviceaccount.com",
                "CLIP_EMBEDDING_QUEUE_ENABLED=false",
                "AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES=1",
                "AVATAR_QUEUE_MAX_DISPATCHES_PER_SECOND=1",
                "AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS=900",
                "AVATAR_QUEUE_MAX_ATTEMPTS=3",
                "AVATAR_QUEUE_MIN_BACKOFF_SECONDS=30",
                "AVATAR_QUEUE_MAX_BACKOFF_SECONDS=600",
                "AVATAR_QUEUE_MAX_DOUBLINGS=4",
                "AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS=1",
            ]
        ),
        encoding="utf-8",
    )

    report = config.validate_queue_config(config._load_env_file(str(env_file)))

    assert report["ok"] is True


def test_live_iam_check_reports_unauthenticated_rejected_and_authenticated_healthz():
    live = load_script("avatar_live_iam_check", "avatar_live_iam_check.py")
    calls = []

    def fake_http_get(url, *, token=None, timeout_seconds=10):
        calls.append({"url": url, "token": token, "timeout_seconds": timeout_seconds})
        if token:
            return live.HttpResult(status_code=200, body='{"status":"ok"}')
        return live.HttpResult(status_code=403, body="forbidden")

    report = live.run_live_iam_check(
        worker_url="https://avatar-worker.example",
        token="provided-id-token",
        http_get=fake_http_get,
    )

    assert report["ok"] is True
    assert [call["token"] for call in calls] == [None, "provided-id-token"]
    assert report["checks"][0]["name"] == "unauthenticated_healthz_rejected"
    assert report["checks"][0]["ok"] is True
    assert report["checks"][1]["name"] == "authenticated_healthz"
    assert report["checks"][1]["ok"] is True


def test_live_iam_check_fails_when_unauthenticated_healthz_is_public():
    live = load_script("avatar_live_iam_check", "avatar_live_iam_check.py")

    def fake_http_get(_url, *, token=None, timeout_seconds=10):
        return live.HttpResult(status_code=200, body='{"status":"ok"}')

    report = live.run_live_iam_check(
        worker_url="https://avatar-worker.example",
        token="provided-id-token",
        http_get=fake_http_get,
    )

    assert report["ok"] is False
    assert report["checks"][0]["name"] == "unauthenticated_healthz_rejected"
    assert report["checks"][0]["ok"] is False


def test_live_iam_output_redacts_tokens_and_source_refs():
    live = load_script("avatar_live_iam_check", "avatar_live_iam_check.py")

    def fake_http_get(_url, *, token=None, timeout_seconds=10):
        if token:
            return live.HttpResult(status_code=200, body="ok")
        return live.HttpResult(status_code=403, body="forbidden")

    report = live.run_live_iam_check(
        worker_url="https://avatar-worker.example",
        token="secret-token-value",
        http_get=fake_http_get,
        task_dry_run={
            "queue_name": "projects/seolleyeon/locations/asia-northeast3/queues/avatar-generation",
            "task_url": "https://avatar-worker.example/tasks/avatar-generation",
            "service_account_email": "task-invoker@seolleyeon.iam.gserviceaccount.com",
            "audience": "https://avatar-worker.example",
            "payload": {
                "jobType": "avatar_generation",
                "schemaVersion": "avatar_job_v1",
                "idempotencyKey": "u1:src_secret:avatar_generation_v1",
                "sourcePhotoRefs": [
                    "gs://seolleyeon-private-source-photos/users/u1/source/src_secret.jpg"
                ],
            },
        },
    )

    rendered = live.format_report(report)
    parsed = json.loads(rendered)

    assert parsed["ok"] is True
    assert "secret-token-value" not in rendered
    assert "src_secret" not in rendered
    assert "seolleyeon-private-source-photos" not in rendered
    assert "sourcePhotoRefs" not in rendered


def test_worker_drain_once_dry_run_does_not_post_or_need_token():
    drain = load_script("avatar_worker_drain_once", "avatar_worker_drain_once.py")
    calls = []

    def fake_http_post(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return drain.HttpResult(status_code=200, body='{"status":"ok"}')

    report = drain.build_drain_report(
        worker_url="https://avatar-worker.example",
        apply=False,
        http_post=fake_http_post,
    )

    assert report["ok"] is True
    assert report["applied"] is False
    assert report["wouldPost"] is True
    assert report["endpointPath"] == "/tasks/avatar-generation/drain"
    assert calls == []


def test_worker_drain_once_apply_posts_with_token_and_redacts_response():
    drain = load_script("avatar_worker_drain_once", "avatar_worker_drain_once.py")
    calls = []

    def fake_http_post(url, *, token, timeout_seconds=60):
        calls.append({"url": url, "token": token, "timeout_seconds": timeout_seconds})
        return drain.HttpResult(
            status_code=200,
            body=json.dumps(
                {
                    "status": "ok",
                    "processed": 1,
                    "sourcePhotoRefs": [
                        "gs://seolleyeon-final-private-source-photos/users/u/source/src.jpg"
                    ],
                    "previewUrl": "https://storage.googleapis.com/x?X-Goog-Signature=secret",
                }
            ),
        )

    report = drain.build_drain_report(
        worker_url="https://avatar-worker.example",
        apply=True,
        token="secret-token-value",
        http_post=fake_http_post,
        timeout_seconds=12,
    )
    rendered = json.dumps(report, ensure_ascii=False)

    assert report["ok"] is True
    assert report["applied"] is True
    assert report["statusCode"] == 200
    assert report["body"]["status"] == "ok"
    assert report["body"]["processed"] == 1
    assert calls == [
        {
            "url": "https://avatar-worker.example/tasks/avatar-generation/drain",
            "token": "secret-token-value",
            "timeout_seconds": 12,
        }
    ]
    assert "secret-token-value" not in rendered
    assert "sourcePhotoRefs" not in rendered
    assert "seolleyeon-final-private-source-photos" not in rendered
    assert "X-Goog-Signature" not in rendered


def test_worker_staging_smoke_live_real_gpu_uses_warmup(tmp_path, monkeypatch):
    scripts_dir = str(REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    smoke = load_script("avatar_worker_staging_smoke", "avatar_worker_staging_smoke.py")
    report_path = tmp_path / "worker_smoke.json"
    calls = []

    monkeypatch.setattr(smoke, "_gcloud_id_token", lambda audience: "id-token")

    def fake_get_json(url, headers):
        calls.append(("GET", url, dict(headers)))
        return {"status": "ok", "authMode": "cloud_run_iam"}

    def fake_post_json(url, payload, headers, *, timeout_seconds=120):
        calls.append(("POST", url, dict(payload), dict(headers), timeout_seconds))
        return {"status": "ok", "modelCacheMisses": 1}

    monkeypatch.setattr(smoke, "_get_json", fake_get_json)
    monkeypatch.setattr(smoke, "_post_json", fake_post_json)

    exit_code = smoke.main(
        [
            "--real_gpu",
            "--worker_url",
            "https://avatar-worker.example",
            "--id_token_from_gcloud",
            "--audience",
            "https://avatar-worker.example",
            "--output_report_json",
            str(report_path),
        ]
    )

    assert exit_code == 0
    assert calls[0][0:2] == ("GET", "https://avatar-worker.example/readyz")
    assert calls[1][0:3] == ("POST", "https://avatar-worker.example/warmup", {})
    assert not any("/tasks/avatar-generation" in call[1] for call in calls)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["result"] == {
        "status": "warmup_completed",
        "taskPayloadPosted": False,
    }


def test_live_verify_redacts_uid_and_checks_preview_ready_evidence():
    verify = load_script("staging_avatar_live_verify", "staging_avatar_live_verify.py")

    command = verify._safe_command(
        [
            "python",
            "scripts/debug_avatar_job_status.py",
            "--uid",
            "4705828086",
            "--job_id=avatar_job_secret",
        ]
    )
    rendered_command = json.dumps(command)
    assert "4705828086" not in rendered_command
    assert "avatar_job_secret" not in rendered_command

    assert (
        verify._avatar_job_preview_ready_ok(
            {
                "jobs": [
                    {
                        "status": "preview_ready",
                        "candidateQa": {"previewAllowedCount": 4},
                        "candidatesByStatus": {"preview_ready": 4},
                    }
                ]
            }
        )
        is True
    )
    assert (
        verify._avatar_job_preview_ready_ok(
            {
                "jobs": [
                    {
                        "status": "queued",
                        "candidateQa": {"previewAllowedCount": 0},
                        "candidatesByStatus": {},
                    }
                ]
            }
        )
        is False
    )
    assert (
        verify._avatar_job_approved_ok(
            {
                "userDocument": {
                    "avatarStatus": "approved",
                    "approvedAvatarUrlPresent": True,
                    "onboardingAvatarUrlsCount": 1,
                },
                "jobs": [],
            }
        )
        is True
    )
    assert (
        verify._avatar_job_approved_ok(
            {
                "userDocument": {
                    "avatarStatus": "approval_copying",
                    "approvedAvatarUrlPresent": False,
                    "onboardingAvatarUrlsCount": 0,
                },
                "jobs": [],
            }
        )
        is False
    )


def _install_preflight_fakes(
    monkeypatch,
    preflight,
    *,
    secrets=(),
    run_services=(),
    env_keys=(),
    deployed_env_keys=(),
    worker_env_keys=(),
):
    def fake_run(command):
        if command[-2:] == ["get-value", "account"]:
            return 0, "seolleyeon.official@gmail.com", ""
        if command[-2:] == ["get-value", "project"]:
            return 0, "seolleyeon-final", ""
        return 0, "", ""

    def fake_gcloud_values(args):
        joined = " ".join(args)
        if "run services list" in joined:
            return list(run_services)
        if "services list" in joined:
            return sorted(preflight.REQUIRED_SERVICES)
        if "secrets list" in joined:
            return list(secrets)
        if "service-accounts list" in joined:
            return [
                "avatar-worker@seolleyeon-final.iam.gserviceaccount.com",
                "task-invoker@seolleyeon-final.iam.gserviceaccount.com",
            ]
        if "tasks queues list" in joined:
            return ["avatar-generation"]
        if "artifacts repositories list" in joined:
            return ["seolleyeon-repo"]
        if "storage buckets list" in joined:
            return sorted(preflight.REQUIRED_BUCKETS)
        if "artifacts docker images list" in joined:
            return [
                "asia-northeast3-docker.pkg.dev/seolleyeon-final/seolleyeon-repo/seolleyeon-avatar-worker"
            ]
        return []

    monkeypatch.setattr(preflight, "_run", fake_run)
    monkeypatch.setattr(preflight, "_gcloud_values", fake_gcloud_values)
    monkeypatch.setattr(preflight, "_read_env_keys", lambda _path: set(env_keys))
    monkeypatch.setattr(
        preflight,
        "_deployed_function_env_keys",
        lambda **_kwargs: set(deployed_env_keys),
    )
    monkeypatch.setattr(
        preflight,
        "_deployed_run_service_env_keys",
        lambda **_kwargs: set(worker_env_keys),
    )


def _preflight_report(preflight, *, stage):
    return preflight.build_report(
        project="seolleyeon-final",
        location="asia-northeast3",
        worker_location="asia-southeast1",
        repository="seolleyeon-repo",
        env_file=Path("unused.env"),
        avatar_only=True,
        expected_account="seolleyeon.official@gmail.com",
        hf_token_env_var="AVATAR_WORKER_HF_TOKEN",
        upload_function_name="beginAvatarGenerationFromOnboardingPhotos",
        stage=stage,
    )


def test_staging_preflight_prepare_allows_secret_worker_and_env_as_warnings(monkeypatch):
    preflight = load_script("staging_avatar_live_preflight", "staging_avatar_live_preflight.py")
    _install_preflight_fakes(monkeypatch, preflight)

    report = _preflight_report(preflight, stage="prepare")

    assert report["ok"] is True
    issue_map = {(issue["kind"], issue["value"]): issue["severity"] for issue in report["issues"]}
    assert issue_map[("run_service_missing", "seolleyeon-avatar-worker")] == "warning"
    assert issue_map[("env_key_missing", "JOB_QUEUE_MODE")] == "warning"
    assert issue_map[("function_env_key_missing", "JOB_QUEUE_MODE")] == "warning"


def test_staging_preflight_deploy_requires_hf_secret_but_not_worker_env(monkeypatch):
    preflight = load_script("staging_avatar_live_preflight", "staging_avatar_live_preflight.py")
    _install_preflight_fakes(
        monkeypatch,
        preflight,
        secrets=("seolleyeon-avatar-azure-openai-api-key",),
    )

    report = _preflight_report(preflight, stage="deploy")

    assert report["ok"] is True
    issue_map = {(issue["kind"], issue["value"]): issue["severity"] for issue in report["issues"]}
    assert issue_map[("run_service_missing", "seolleyeon-avatar-worker")] == "warning"
    assert issue_map[("env_key_missing", "JOB_QUEUE_MODE")] == "warning"
    assert issue_map[("function_env_key_missing", "JOB_QUEUE_MODE")] == "warning"


def test_staging_preflight_live_requires_worker_and_functions_env(monkeypatch):
    preflight = load_script("staging_avatar_live_preflight", "staging_avatar_live_preflight.py")
    _install_preflight_fakes(
        monkeypatch,
        preflight,
        secrets=("avatar-worker-hf-token", "seolleyeon-avatar-azure-openai-api-key"),
        env_keys=(
            "JOB_QUEUE_MODE",
            "CLOUD_TASKS_PROJECT",
            "GCP_LOCATION",
            "AVATAR_GENERATION_QUEUE_NAME",
            "AVATAR_GENERATION_TASK_URL",
            "TASK_INVOKER_SERVICE_ACCOUNT",
            "CLIP_EMBEDDING_QUEUE_ENABLED",
        ),
    )

    report = _preflight_report(preflight, stage="live")

    assert report["ok"] is False
    issue_map = {(issue["kind"], issue["value"]): issue["severity"] for issue in report["issues"]}
    assert issue_map[("run_service_missing", "seolleyeon-avatar-worker")] == "blocker"
    assert ("env_key_missing", "JOB_QUEUE_MODE") not in issue_map
    assert issue_map[("function_env_key_missing", "JOB_QUEUE_MODE")] == "blocker"


def test_staging_preflight_live_passes_with_avatar_only_infra_ready(monkeypatch):
    preflight = load_script("staging_avatar_live_preflight", "staging_avatar_live_preflight.py")
    assert "AVATAR_REFERENCE_FACE_EQUIVALENT_SIZE" in preflight.REQUIRED_AVATAR_WORKER_ENV_KEYS
    assert "AVATAR_REFERENCE_DOWNSAMPLE_SIZE" not in preflight.REQUIRED_AVATAR_WORKER_ENV_KEYS
    assert "AVATAR_RERANK_PROVIDER" in preflight.REQUIRED_AVATAR_WORKER_ENV_KEYS
    _install_preflight_fakes(
        monkeypatch,
        preflight,
        secrets=("avatar-worker-hf-token", "seolleyeon-avatar-azure-openai-api-key"),
        run_services=("seolleyeon-avatar-worker",),
        env_keys=(
            "JOB_QUEUE_MODE",
            "CLOUD_TASKS_PROJECT",
            "GCP_LOCATION",
            "AVATAR_GENERATION_QUEUE_NAME",
            "AVATAR_GENERATION_TASK_URL",
            "TASK_INVOKER_SERVICE_ACCOUNT",
            "CLIP_EMBEDDING_QUEUE_ENABLED",
        ),
        deployed_env_keys=(
            "JOB_QUEUE_MODE",
            "CLOUD_TASKS_PROJECT",
            "GCP_LOCATION",
            "AVATAR_GENERATION_QUEUE_NAME",
            "AVATAR_GENERATION_TASK_URL",
            "TASK_INVOKER_SERVICE_ACCOUNT",
            "CLIP_EMBEDDING_QUEUE_ENABLED",
        ),
        worker_env_keys=preflight.REQUIRED_AVATAR_WORKER_ENV_KEYS,
    )

    report = _preflight_report(preflight, stage="live")

    assert report["ok"] is True
    assert all(issue["severity"] == "warning" for issue in report["issues"])


def test_staging_preflight_live_requires_worker_env_keys(monkeypatch):
    preflight = load_script("staging_avatar_live_preflight", "staging_avatar_live_preflight.py")
    _install_preflight_fakes(
        monkeypatch,
        preflight,
        secrets=("avatar-worker-hf-token", "seolleyeon-avatar-azure-openai-api-key"),
        run_services=("seolleyeon-avatar-worker",),
        env_keys=(
            "JOB_QUEUE_MODE",
            "CLOUD_TASKS_PROJECT",
            "GCP_LOCATION",
            "AVATAR_GENERATION_QUEUE_NAME",
            "AVATAR_GENERATION_TASK_URL",
            "TASK_INVOKER_SERVICE_ACCOUNT",
            "CLIP_EMBEDDING_QUEUE_ENABLED",
        ),
        deployed_env_keys=(
            "JOB_QUEUE_MODE",
            "CLOUD_TASKS_PROJECT",
            "GCP_LOCATION",
            "AVATAR_GENERATION_QUEUE_NAME",
            "AVATAR_GENERATION_TASK_URL",
            "TASK_INVOKER_SERVICE_ACCOUNT",
            "CLIP_EMBEDDING_QUEUE_ENABLED",
        ),
        worker_env_keys=("ENVIRONMENT", "AVATAR_WORKER_MODE"),
    )

    report = _preflight_report(preflight, stage="live")

    assert report["ok"] is False
    issue_map = {(issue["kind"], issue["value"]): issue["severity"] for issue in report["issues"]}
    assert issue_map[("worker_env_key_missing", "AVATAR_COST_ENFORCE_BUDGET")] == "blocker"


def test_debug_avatar_job_status_redacts_private_refs_and_summarizes_state():
    debug = load_script("debug_avatar_job_status", "debug_avatar_job_status.py")
    fixture = {
        "avatarJobs": {
            "job_1": {
                "uid": "u1",
                "status": "queued",
                "queueMode": "dry_run",
                "queueStatus": "dry_run",
                "candidateCount": 4,
                "sourcePhotoIds": ["src_001"],
                "sourcePhotoRefs": [
                    "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg"
                ],
                "processing": {
                    "attempt": 1,
                    "leaseOwner": "worker-a",
                    "lastErrorCode": "worker_unavailable",
                    "lastErrorMessage": "failed for gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg",
                },
            }
        },
        "avatarCandidates": {
            "cand_1": {
                "jobId": "job_1",
                "uid": "u1",
                "status": "qa_pending",
                "imageRef": "gs://seolleyeon-final-avatar-temp/users/u1/candidates/cand_1.png?X-Goog-Signature=secret",
                "qa": {"previewAllowed": False, "rejectReasons": ["model_unavailable"]},
            }
        },
        "userPrivateMedia": {
            "u1": {
                "sourcePhotos": [
                    {
                        "photoId": "src_001",
                        "gcsUri": "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg",
                    }
                ],
                "clip": {"embeddingStatus": "queued"},
            }
        },
        "users": {
            "u1": {
                "avatar": {
                    "status": "approved",
                    "avatarId": "avatar_1",
                    "approvedAvatarUrl": "https://cdn.example/avatar.png?Signature=secret",
                    "selectedCandidateId": "cand_1",
                    "sourceJobId": "job_1",
                },
                "onboarding": {
                    "avatarUrls": ["https://cdn.example/avatar.png?Signature=secret"],
                    "photoUrls": [],
                },
            }
        },
    }

    report = debug.build_diagnostic_report(fixture, uid="u1", job_id="job_1")
    rendered = json.dumps(report, ensure_ascii=False)

    assert report["uid"] == "<redacted>"
    assert report["jobs"][0]["jobId"] == "job_1"
    assert report["jobs"][0]["uid"] == "<redacted>"
    assert report["jobs"][0]["status"] == "queued"
    assert report["jobs"][0]["sourcePhotoIdsCount"] == 1
    assert report["jobs"][0]["sourcePhotoRefsCount"] == 1
    assert report["jobs"][0]["candidatesByStatus"] == {"qa_pending": 1}
    assert report["userPrivateMedia"]["sourcePhotosCount"] == 1
    assert report["userPrivateMedia"]["clipEmbeddingStatus"] == "queued"
    assert report["userDocument"]["avatarStatus"] == "approved"
    assert report["userDocument"]["approvedAvatarUrlPresent"] is True
    assert report["userDocument"]["onboardingAvatarUrlsCount"] == 1
    assert "gs://" not in rendered
    assert "src_001.jpg" not in rendered
    assert "seolleyeon-final-private-source-photos" not in rendered
    assert "X-Goog-Signature" not in rendered
    assert "Signature=secret" not in rendered


def test_staging_preflight_blocks_when_azure_secret_binding_is_absent(monkeypatch):
    # Azure 키는 Secret Manager 참조로만 주입된다. 시크릿이 없으면 워커는
    # 첫 생성에서 실패하므로 배포/라이브 단계에서 blocker 여야 한다.
    preflight = load_script("staging_avatar_live_preflight", "staging_avatar_live_preflight.py")
    _install_preflight_fakes(monkeypatch, preflight, secrets=("avatar-worker-hf-token",))

    report = _preflight_report(preflight, stage="deploy")

    assert report["ok"] is False
    issue_map = {
        (issue["kind"], issue["value"]): issue["severity"] for issue in report["issues"]
    }
    assert (
        issue_map[("secret_missing", "seolleyeon-avatar-azure-openai-api-key")]
        == "blocker"
    )
