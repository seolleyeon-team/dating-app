import sys
import types
from pathlib import Path

import pytest

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

import clip_job_service


@pytest.mark.skipif(clip_job_service.Flask is None, reason="flask is not installed")
def test_clip_job_service_accepts_cloud_task_payload(monkeypatch):
    seen = {}

    def fake_process(payload, **kwargs):
        seen["payload"] = payload
        seen["kwargs"] = kwargs
        return {"status": "ready", "uid": payload["uid"]}

    monkeypatch.setattr(clip_job_service, "process_clip_job_payload", fake_process)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("ALLOW_INSECURE_WORKER_LOCAL", "true")
    monkeypatch.setenv("GCP_PROJECT", "seolleyeon-test")
    app = clip_job_service.create_app()
    client = app.test_client()

    response = client.post(
        "/tasks/clip-embedding",
        json={
            "uid": "u1",
            "sourcePhotoIds": ["src_001"],
            "sourcePhotoRefs": [
                "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg"
            ],
            "embeddingVersion": "clip-vit-large-patch14_v1",
            "jobType": "clip_embedding",
            "schemaVersion": "clip_job_v1",
            "idempotencyKey": "u1:src_001:clip_embedding_v1",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "ready"
    assert seen["payload"]["uid"] == "u1"
    assert seen["kwargs"]["firestore_project"] == "seolleyeon-test"


def _set_request_headers(monkeypatch, headers=None):
    monkeypatch.setattr(
        clip_job_service,
        "request",
        types.SimpleNamespace(headers=headers or {}),
    )


def test_clip_job_auth_rejects_production_without_auth_posture(monkeypatch):
    _set_request_headers(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("CLIP_WORKER_AUTH_MODE", raising=False)
    monkeypatch.delenv("CLIP_WORKER_REQUIRE_SHARED_SECRET", raising=False)
    monkeypatch.delenv("CLIP_TASK_SHARED_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_INSECURE_WORKER_LOCAL", raising=False)

    with pytest.raises(clip_job_service.ClipWorkerAuthError, match="production auth mode"):
        clip_job_service._require_worker_auth()


@pytest.mark.skipif(clip_job_service.Flask is None, reason="flask is not installed")
def test_clip_job_service_rejects_production_without_auth_posture(monkeypatch):
    called = False

    def fake_process(_payload, **_kwargs):
        nonlocal called
        called = True
        return {"status": "ready"}

    monkeypatch.setattr(clip_job_service, "process_clip_job_payload", fake_process)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GCP_PROJECT", "seolleyeon-test")
    monkeypatch.delenv("CLIP_WORKER_AUTH_MODE", raising=False)
    monkeypatch.delenv("CLIP_WORKER_REQUIRE_SHARED_SECRET", raising=False)
    monkeypatch.delenv("CLIP_TASK_SHARED_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_INSECURE_WORKER_LOCAL", raising=False)
    app = clip_job_service.create_app()
    client = app.test_client()

    response = client.post("/tasks/clip-embedding", json={"uid": "u1"})

    assert response.status_code == 401
    assert response.get_json()["status"] == "unauthorized"
    assert called is False


def test_clip_job_auth_accepts_production_cloud_run_iam_posture(monkeypatch):
    _set_request_headers(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CLIP_WORKER_AUTH_MODE", "cloud_run_iam")
    monkeypatch.setenv("CLIP_WORKER_CLOUD_RUN_IAM_ENFORCED", "true")
    monkeypatch.setenv("K_SERVICE", "clip-worker")

    clip_job_service._require_worker_auth()


@pytest.mark.skipif(clip_job_service.Flask is None, reason="flask is not installed")
def test_clip_job_service_accepts_production_cloud_run_iam_posture(monkeypatch):
    monkeypatch.setattr(
        clip_job_service,
        "process_clip_job_payload",
        lambda payload, **_kwargs: {"status": "ready", "uid": payload["uid"]},
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GCP_PROJECT", "seolleyeon-test")
    monkeypatch.setenv("CLIP_WORKER_AUTH_MODE", "cloud_run_iam")
    monkeypatch.setenv("CLIP_WORKER_CLOUD_RUN_IAM_ENFORCED", "true")
    monkeypatch.setenv("K_SERVICE", "clip-worker")
    app = clip_job_service.create_app()
    client = app.test_client()

    response = client.post("/tasks/clip-embedding", json={"uid": "u1"})

    assert response.status_code == 200
    assert response.get_json()["status"] == "ready"


def test_clip_job_auth_shared_secret_success_and_failure(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CLIP_WORKER_AUTH_MODE", "shared_secret")
    monkeypatch.setenv("CLIP_TASK_SHARED_SECRET", "expected")

    _set_request_headers(monkeypatch)
    with pytest.raises(clip_job_service.ClipWorkerAuthError, match="authorized"):
        clip_job_service._require_worker_auth()

    _set_request_headers(monkeypatch, {"X-Seolleyeon-Task-Secret": "wrong"})
    with pytest.raises(clip_job_service.ClipWorkerAuthError, match="authorized"):
        clip_job_service._require_worker_auth()

    _set_request_headers(monkeypatch, {"X-Seolleyeon-Task-Secret": "expected"})
    clip_job_service._require_worker_auth()


@pytest.mark.skipif(clip_job_service.Flask is None, reason="flask is not installed")
def test_clip_job_service_shared_secret_success_and_failure(monkeypatch):
    monkeypatch.setattr(
        clip_job_service,
        "process_clip_job_payload",
        lambda payload, **_kwargs: {"status": "ready", "uid": payload["uid"]},
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GCP_PROJECT", "seolleyeon-test")
    monkeypatch.setenv("CLIP_WORKER_AUTH_MODE", "shared_secret")
    monkeypatch.setenv("CLIP_TASK_SHARED_SECRET", "expected")
    app = clip_job_service.create_app()
    client = app.test_client()

    missing = client.post("/tasks/clip-embedding", json={"uid": "u1"})
    wrong = client.post(
        "/tasks/clip-embedding",
        json={"uid": "u1"},
        headers={"X-Seolleyeon-Task-Secret": "wrong"},
    )
    ok = client.post(
        "/tasks/clip-embedding",
        json={"uid": "u1"},
        headers={"X-Seolleyeon-Task-Secret": "expected"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert ok.status_code == 200
    assert ok.get_json()["status"] == "ready"


def test_clip_job_auth_rejects_shared_secret_mode_without_secret(monkeypatch):
    _set_request_headers(monkeypatch, {"X-Seolleyeon-Task-Secret": "expected"})
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CLIP_WORKER_AUTH_MODE", "shared_secret")
    monkeypatch.delenv("CLIP_TASK_SHARED_SECRET", raising=False)

    with pytest.raises(clip_job_service.ClipWorkerAuthError, match="authorized"):
        clip_job_service._require_worker_auth()


@pytest.mark.skipif(clip_job_service.Flask is None, reason="flask is not installed")
def test_clip_job_service_rejects_shared_secret_mode_without_secret(monkeypatch):
    monkeypatch.setattr(
        clip_job_service,
        "process_clip_job_payload",
        lambda _payload, **_kwargs: {"status": "ready"},
    )
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("GCP_PROJECT", "seolleyeon-test")
    monkeypatch.setenv("CLIP_WORKER_AUTH_MODE", "shared_secret")
    monkeypatch.delenv("CLIP_TASK_SHARED_SECRET", raising=False)
    app = clip_job_service.create_app()
    client = app.test_client()

    response = client.post("/tasks/clip-embedding", json={"uid": "u1"})

    assert response.status_code == 401


def test_clip_job_auth_requires_explicit_local_insecure_bypass(monkeypatch):
    _set_request_headers(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("CLIP_WORKER_AUTH_MODE", raising=False)
    monkeypatch.delenv("CLIP_WORKER_REQUIRE_SHARED_SECRET", raising=False)
    monkeypatch.delenv("CLIP_TASK_SHARED_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_INSECURE_WORKER_LOCAL", raising=False)
    monkeypatch.delenv("CLIP_WORKER_ALLOW_INSECURE_LOCAL", raising=False)

    with pytest.raises(clip_job_service.ClipWorkerAuthError, match="ALLOW_INSECURE_WORKER_LOCAL"):
        clip_job_service._require_worker_auth()

    monkeypatch.setenv("CLIP_WORKER_ALLOW_INSECURE_LOCAL", "true")
    clip_job_service._require_worker_auth()


@pytest.mark.skipif(clip_job_service.Flask is None, reason="flask is not installed")
def test_clip_job_service_requires_explicit_local_insecure_bypass(monkeypatch):
    monkeypatch.setattr(
        clip_job_service,
        "process_clip_job_payload",
        lambda payload, **_kwargs: {"status": "ready", "uid": payload["uid"]},
    )
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("GCP_PROJECT", "seolleyeon-test")
    monkeypatch.delenv("CLIP_WORKER_AUTH_MODE", raising=False)
    monkeypatch.delenv("CLIP_WORKER_REQUIRE_SHARED_SECRET", raising=False)
    monkeypatch.delenv("CLIP_TASK_SHARED_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_INSECURE_WORKER_LOCAL", raising=False)
    monkeypatch.delenv("CLIP_WORKER_ALLOW_INSECURE_LOCAL", raising=False)
    app = clip_job_service.create_app()
    client = app.test_client()

    rejected = client.post("/tasks/clip-embedding", json={"uid": "u1"})
    monkeypatch.setenv("CLIP_WORKER_ALLOW_INSECURE_LOCAL", "true")
    allowed = client.post("/tasks/clip-embedding", json={"uid": "u1"})

    assert rejected.status_code == 401
    assert allowed.status_code == 200
