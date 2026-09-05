import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

import avatar_generation.qa_preflight as qa_preflight  # noqa: E402
import avatar_generation.worker as worker  # noqa: E402
import avatar_generation.worker_service as worker_service  # noqa: E402
from avatar_generation.qa_preflight import (  # noqa: E402
    QAComponentReadiness,
    QARuntimeReadiness,
)


class _Snapshot:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _Doc:
    def __init__(self, store, collection, doc_id):
        self.store = store
        self.collection = collection
        self.doc_id = doc_id

    def get(self, **_kwargs):
        return _Snapshot(self.store.get(self.collection, {}).get(self.doc_id))

    def set(self, data, merge=True):
        collection = self.store.setdefault(self.collection, {})
        if merge and self.doc_id in collection:
            collection[self.doc_id].update(data)
        else:
            collection[self.doc_id] = dict(data)


class _Collection:
    def __init__(self, store, name):
        self.store = store
        self.name = name

    def document(self, doc_id):
        return _Doc(self.store, self.name, doc_id)


class _Firestore:
    def __init__(self, store):
        self.store = store

    def collection(self, name):
        return _Collection(self.store, name)


def _not_ready_readiness(*, reason="model_artifact_unavailable"):
    return QARuntimeReadiness(
        components=(
            QAComponentReadiness(
                name="visualRisk",
                status="unavailable",
                critical=True,
                reason=reason,
            ),
            QAComponentReadiness(
                name="localSafetyRisk",
                status="uncalibrated",
                critical=True,
                reason="calibration_missing_or_invalid",
            ),
            QAComponentReadiness(
                name="faceSimilarity",
                status="uncalibrated",
                critical=True,
                reason="calibration_missing_or_invalid",
            ),
            QAComponentReadiness(
                name="dino",
                status="not_required",
                critical=False,
                reason="not_in_active_qa_contract",
            ),
        )
    )


def test_readiness_document_is_sanitized_and_dino_is_explicitly_optional():
    readiness = QARuntimeReadiness(
        components=(
            QAComponentReadiness(
                name="imageDecode",
                status="available",
                critical=True,
                reason="ok",
            ),
            QAComponentReadiness(
                name="dino",
                status="not_required",
                critical=False,
                reason="not_in_active_qa_contract",
            ),
        )
    )

    document = readiness.to_document()

    assert document["ready"] is True
    assert document["components"]["dino"]["status"] == "not_required"
    assert document["components"]["dino"]["critical"] is False
    assert "/" not in json.dumps(document)
    assert "exception" not in json.dumps(document).lower()


def test_runtime_readiness_probes_local_only_components(monkeypatch):
    class _FaceDetector:
        provider_name = "mediapipe"

    class _VisualRisk:
        def _ensure_loaded(self):
            return None

    class _Clip:
        def is_available(self):
            return True

    class _Similarity:
        def is_available(self):
            return True

    monkeypatch.setattr(qa_preflight, "get_default_face_detector", lambda: _FaceDetector())
    monkeypatch.setattr(qa_preflight, "get_default_visual_risk_adapter", lambda: _VisualRisk())
    monkeypatch.setattr(qa_preflight, "get_default_clip_risk_scorer", lambda: _Clip())
    monkeypatch.setattr(qa_preflight, "get_default_similarity_adapter", lambda: _Similarity())
    monkeypatch.setattr(qa_preflight, "_probe_device", lambda: QAComponentReadiness(
        name="device",
        status="available",
        critical=True,
        reason="cuda_available",
    ))
    monkeypatch.setattr(
        qa_preflight,
        "_similarity_policy_from_env",
        lambda: type("Policy", (), {"is_calibrated": True})(),
    )
    monkeypatch.setattr(
        qa_preflight.ClipRiskCalibrationPolicy,
        "from_env",
        classmethod(lambda cls: type("Policy", (), {"is_valid": True})()),
    )

    readiness = qa_preflight.build_qa_runtime_readiness()

    assert qa_preflight.os.environ["HF_HUB_OFFLINE"] == "1"
    assert qa_preflight.os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert readiness.ready is True
    assert readiness.to_document()["components"]["dino"]["status"] == "not_required"
    assert readiness.to_document()["components"]["visualRisk"]["status"] == "available"


def test_runtime_readiness_fails_closed_with_component_reason_codes(monkeypatch):
    monkeypatch.setattr(
        qa_preflight,
        "_probe_face_detector",
        lambda: QAComponentReadiness(
            name="faceDetector",
            status="unavailable",
            critical=True,
            reason="face_detector_fallback",
        ),
    )
    monkeypatch.setattr(
        qa_preflight,
        "_probe_visual_risk",
        lambda: QAComponentReadiness(
            name="visualRisk",
            status="unavailable",
            critical=True,
            reason="model_artifact_unavailable",
        ),
    )
    monkeypatch.setattr(
        qa_preflight,
        "_probe_local_safety",
        lambda: QAComponentReadiness(
            name="localSafetyRisk",
            status="uncalibrated",
            critical=True,
            reason="calibration_missing_or_invalid",
        ),
    )
    monkeypatch.setattr(
        qa_preflight,
        "_probe_face_similarity",
        lambda: QAComponentReadiness(
            name="faceSimilarity",
            status="uncalibrated",
            critical=True,
            reason="calibration_missing_or_invalid",
        ),
    )
    monkeypatch.setattr(
        qa_preflight,
        "_probe_device",
        lambda: QAComponentReadiness(
            name="device",
            status="available",
            critical=True,
            reason="cuda_available",
        ),
    )

    readiness = qa_preflight.build_qa_runtime_readiness()
    document = readiness.to_document()

    assert readiness.ready is False
    assert document["blockingComponents"] == [
        "faceDetector",
        "visualRisk",
        "localSafetyRisk",
        "faceSimilarity",
    ]
    assert readiness.failure_code == "avatar_qa_runtime_unavailable"
    assert all("/" not in json.dumps(component) for component in document["components"].values())


def test_azure_worker_blocks_before_provider_when_qa_preflight_is_not_ready(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.delenv("AVATAR_WORKER_MODE", raising=False)
    monkeypatch.setattr(worker, "get_qa_runtime_readiness", lambda: _not_ready_readiness())

    job_id = "qa_preflight_blocked_job"
    store = {
        "avatarJobs": {
            job_id: {
                "uid": "u1",
                "status": "queued",
                "sourceSelection": {"status": "selected"},
                "selectedSource": {
                    "photoId": "src_001",
                    "gcsUri": (
                        f"gs://{worker.DEFAULT_SOURCE_PHOTO_BUCKET}"
                        "/users/u1/source/src_001.jpg"
                    ),
                    "objectGeneration": "101",
                },
            }
        },
        "userPrivateMedia": {
            "u1": {
                "photoConsent": {
                    "avatarGeneration": True,
                    "profileDisplayOriginalPhoto": False,
                },
                "sourcePhotos": [
                    {
                        "photoId": "src_001",
                        "gcsUri": (
                            f"gs://{worker.DEFAULT_SOURCE_PHOTO_BUCKET}"
                            "/users/u1/source/src_001.jpg"
                        ),
                        "status": "active",
                        "purpose": {"avatarGeneration": True},
                    }
                ],
            }
        },
    }
    payload = {
        "schemaVersion": "avatar_job_v1",
        "jobType": "avatar_generation",
        "jobId": job_id,
        "uid": "u1",
        "sourcePhotoIds": ["src_001"],
        "sourcePhotoRefs": [
            f"gs://{worker.DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_001.jpg"
        ],
        "sourcePhotoObjectGenerations": ["101"],
        "sourceSelectionMode": "quality_selector_v1",
        "candidateCount": 1,
        "modelId": worker.AZURE_GPT_IMAGE_2_MODEL_ID,
    }

    with pytest.raises(worker.AvatarQAReadinessError):
        worker.process_avatar_generation_payload(
            payload,
            firestore_client=_Firestore(store),
            storage_client=object(),
            mode=worker.CANONICAL_AZURE_WORKER_MODE,
        )

    job = store["avatarJobs"][job_id]
    assert job["status"] == "failed"
    assert job["retryable"] is True
    assert job["errorCode"] == "avatar_qa_runtime_unavailable"
    assert job["providerUsage"]["requestCount"] == 0
    assert job["qaPreflight"]["ready"] is False


def test_readyz_returns_non_ready_for_unavailable_qa_runtime(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setattr(worker_service, "get_qa_runtime_readiness", lambda: _not_ready_readiness())

    posture = worker_service.readyz_status()

    assert posture["status"] == "degraded"
    assert posture["qaReadiness"]["ready"] is False

    if worker_service.app is not None:
        response = worker_service.app.test_client().get("/readyz")
        assert response.status_code == 503
        assert response.get_json()["status"] == "degraded"


def test_authenticated_qa_diagnostics_route_is_flag_gated(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("AVATAR_QA_DIAGNOSTICS_ENABLED", "true")
    monkeypatch.setenv("AVATAR_WORKER_AUTH_MODE", "cloud_run_iam")
    monkeypatch.setenv("AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED", "true")
    monkeypatch.setenv("K_SERVICE", "qa-diagnostic-test")
    monkeypatch.setattr(
        worker_service,
        "collect_qa_runtime_diagnostics",
        lambda: {"schemaVersion": "avatar_qa_runtime_diagnostic_v1", "sanitizedFailureCode": ""},
    )

    response = worker_service.app.test_client().get("/internal/g004-qa-diagnostics")

    assert response.status_code == 200
    assert response.get_json()["schemaVersion"] == "avatar_qa_runtime_diagnostic_v1"


def test_worker_image_declares_pinned_offline_qa_artifacts():
    dockerfile = (
        REPO_ROOT / "lib" / "ai_recommend_model" / "avatar_generation" / "Dockerfile"
    ).read_text(encoding="utf-8")

    for revision in (
        "26b734a54fdfbf9c398351eedfabb7f27fc470b7",
        "32bd64288804d66eefd0ccbe215aa642df71cc41",
        "3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268",
    ):
        assert revision in dockerfile
    assert "repo_id='florence-community/Florence-2-large-ft'" in dockerfile
    assert "HF_HUB_OFFLINE=1" in dockerfile
    assert "TRANSFORMERS_OFFLINE=1" in dockerfile
    assert "AVATAR_QA_VISUAL_RISK_MODEL_ID=/app/models/qa/florence2" in dockerfile
    assert "AVATAR_CLIP_RISK_MODEL_ID=/app/models/qa/clip-large" in dockerfile
    assert "AVATAR_QA_SIMILARITY_MODEL_ID=/app/models/qa/clip-base" in dockerfile
    assert "AVATAR_QA_ALLOW_STAGING_HEURISTIC_PREVIEW=true" not in dockerfile
