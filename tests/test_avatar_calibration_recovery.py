import io
import inspect
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation import calibration_recovery as recovery_module  # noqa: E402
from avatar_generation.calibration_recovery import (  # noqa: E402
    CALIBRATION_RECOVERY_REQUEST_SCHEMA,
    execute_g004_calibration_recovery_request,
)
from avatar_generation.calibration_runner import (  # noqa: E402
    CalibrationRunnerConfig,
    CalibrationRunnerError,
)


SOURCE_BUCKET = "seolleyeon-final-private-source-photos"
TEMP_BUCKET = "seolleyeon-final-avatar-temp"
RUN_ID = "G004-AZURE-CAL-20260824-001"


def _image_bytes(image_format="JPEG", color=(80, 120, 160)):
    output = io.BytesIO()
    Image.new("RGB", (512, 512), color).save(output, format=image_format)
    return output.getvalue()


class _FakeBlob:
    def __init__(self, *, data=None, content_type="", generation="100"):
        self.data = data
        self.content_type = content_type
        self.generation = str(generation)
        self.reload_count = 0
        self.download_preconditions = []

    def exists(self):
        return self.data is not None

    def reload(self):
        self.reload_count += 1

    def download_as_bytes(self, **kwargs):
        if self.data is None:
            raise FileNotFoundError("missing")
        expected = kwargs.get("if_generation_match")
        self.download_preconditions.append(expected)
        if str(expected) != self.generation:
            raise RuntimeError("generation mismatch")
        return bytes(self.data)


class _FakeBucket:
    def __init__(self, blobs=None):
        self.blobs = dict(blobs or {})

    def blob(self, path):
        return self.blobs.setdefault(path, _FakeBlob())


class _FakeStorage:
    def __init__(self, buckets):
        self.buckets = buckets

    def bucket(self, name):
        return self.buckets[name]


class _FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


@dataclass(frozen=True)
class _FakeArtifact:
    calibration_version: str = "g004-live-calibration-v1"
    model_versions: dict = None

    def __post_init__(self):
        object.__setattr__(
            self,
            "model_versions",
            self.model_versions
            or {
                "faceSimilarity": "face-model-pinned",
                "clipSafety": "clip-model-pinned",
            },
        )


class _FakeArtifactWithMetadata(_FakeArtifact):
    @property
    def payload(self):
        return {
            "gitRevision": "revision-watermark-v2",
            "preprocessingVersions": {
                "qa": "qa-preprocess-v2",
                "reference": "reference-preprocess-v1",
            },
            "integrity": {"sha256": "a" * 64},
        }


def _manifest():
    return {
        "projectId": "seolleyeon-final",
        "purpose": "g004_quality_calibration",
        "calibrationVersion": "g004-live-calibration-v1",
        "participants": [
            {
                "uid": f"uid-secret-{index}",
                "sourcePhotoRef": (
                    f"gs://{SOURCE_BUCKET}/users/uid-secret-{index}/source/photo.jpg"
                ),
                "sourceVersion": "100",
                "sourceGeneration": "100",
                "fresh": True,
                "approvedAvatarLocked": False,
                "authProject": "seolleyeon-final",
                "consent": {
                    "exact": True,
                    "calibrationPurpose": True,
                    "sourceImageUse": True,
                    "azureExternalAiProcessing": True,
                    "qaScoring": True,
                    "humanReview": True,
                    "temporaryRetention": "bounded_delete_after_review",
                    "calibrationDate": "2026-08-24",
                    "calibrationVersion": "g004-live-calibration-v1",
                },
                "cohortSlice": {
                    "background": "simple",
                    "eyewear": "none",
                    "hair": "short",
                },
            }
            for index in range(1, 6)
        ],
    }


def _request():
    return {
        "schemaVersion": CALIBRATION_RECOVERY_REQUEST_SCHEMA,
        "runId": RUN_ID,
        "manifest": _manifest(),
        "originalRunEvidence": {
            "serverRequestCount": 1,
            "serverHttpStatus": 200,
            "serverDurationSeconds": 1179.642522033,
            "candidateCount": 20,
            "retryCount": 0,
            "providerRequestBudget": {
                "limit": 20,
                "consumed": 20,
                "remaining": 0,
            },
        },
    }


def _config(**overrides):
    values = {
        "enabled": True,
        "environment": "staging",
        "project": "seolleyeon-final",
        "data_project": "seolleyeon-final",
        "purpose": "g004_quality_calibration",
        "queue_status": "PAUSED",
        "candidate_count": 4,
        "quota_rpm": 2.0,
        "run_id": RUN_ID,
        "calibration_version": "g004-live-calibration-v1",
        "max_retries": 0,
        "operator_timeout_seconds": 1500,
        "job_lease_seconds": 1500,
    }
    values.update(overrides)
    return CalibrationRunnerConfig(**values)


def _storage(*, missing_candidate=None):
    source_blobs = {
        f"users/uid-secret-{index}/source/photo.jpg": _FakeBlob(
            data=_image_bytes("JPEG", color=(50 + index, 90, 120)),
            content_type="image/jpeg",
            generation="100",
        )
        for index in range(1, 6)
    }
    candidate_blobs = {}
    for participant in range(1, 6):
        for candidate in range(1, 5):
            key = (participant, candidate)
            if key == missing_candidate:
                continue
            candidate_blobs[
                f"calibration/g004/{RUN_ID}/P{participant:02d}/C{candidate:02d}.png"
            ] = _FakeBlob(
                data=_image_bytes("PNG", color=(70 + participant, 100 + candidate, 150)),
                content_type="image/png",
                generation=str(300 + participant * 10 + candidate),
            )
    return _FakeStorage(
        {
            SOURCE_BUCKET: _FakeBucket(source_blobs),
            TEMP_BUCKET: _FakeBucket(candidate_blobs),
        }
    )


def _qa_runner(source_ref, candidate_ref, metadata):
    assert source_ref == "process-local://source"
    assert candidate_ref == "process-local://candidate"
    assert metadata["generationBackend"] == "azure_gpt_image_2"
    assert metadata["qaContract"] == "azure_post_generation_direct_source_v2_watermark_evidence"
    assert metadata["compareSourceVisualRisk"] is True
    assert metadata["_source_image"].size == (512, 512)
    assert metadata["_candidate_image"].size == (512, 512)
    return {
        "previewAllowed": True,
        "requiresHumanReview": False,
        "qaVersion": "avatar_qa_v2",
        "rejectReasons": [],
        "candidateHash": "a" * 64,
        "sha256": "b" * 64,
        "imageDigest": "c" * 64,
        "debug": {
            "modelAvailability": {
                "faceDetector": "available",
                "visualRisk": "available",
                "localSafetyRisk": "available",
                "faceSimilarity": "available",
            }
        },
    }


def test_recovery_recomputes_twenty_candidates_without_generation_or_private_output():
    storage = _storage()
    contract_checks = []
    qa_calls = []

    def check_contract(participant):
        contract_checks.append(participant.ordinal)
        return True

    def qa_runner(*args):
        qa_calls.append(args)
        return _qa_runner(*args)

    report = execute_g004_calibration_recovery_request(
        _request(),
        config=_config(),
        storage_client=storage,
        qa_runner=qa_runner,
        artifact=_FakeArtifact(),
        qa_readiness_checker=lambda: True,
        participant_contract_checker=check_contract,
        clock=_FakeClock(),
    )

    assert report["status"] == "completed"
    assert report["nextState"] == "HUMAN_REVIEW_REQUIRED"
    assert report["evaluationId"] == f"{RUN_ID}-QA-RECOVERY-2"
    assert report["participantCount"] == 5
    assert report["candidateCount"] == 20
    assert report["azureCallCount"] == 20
    assert report["retryCount"] == 0
    assert report["generationCallsPerformedByRecovery"] == 0
    assert report["qaEvaluationVersion"] == "avatar_qa_v7_watermark_evidence_parity_v1"
    assert report["watermarkPolicyVersion"] == "watermark_policy_v4_runtime_evidence_parity_v1"
    assert report["calibrationEvaluationVersion"] == "g004_calibration_evaluation_v3_watermark_artifact_only"
    assert report["thresholdSnapshot"] == {
        "calibrationVersion": "g004-live-calibration-v1",
        "modelVersions": {
            "faceSimilarity": "face-model-pinned",
            "clipSafety": "clip-model-pinned",
        },
        "preprocessingVersions": {},
    }
    assert report["calibrationArtifactIntegrity"] == "unavailable"
    assert report["gitRevision"] == "unavailable"
    assert report["rawBiometricPersistence"] == 0
    assert "rawEmbeddingPersistence" not in report
    assert report["providerRequestBudget"] == {
        "limit": 20,
        "consumed": 20,
        "remaining": 0,
    }
    assert report["recovery"]["candidatePreflightCount"] == 20
    assert report["recovery"]["qaEvaluationCount"] == 20
    assert report["recovery"]["readOnly"] is True
    assert report["currentSourceContractChecks"] == {
        "preflightCount": 5,
        "preQaCount": 20,
        "referencesExposed": False,
    }
    assert report["sourceGenerationChecks"] == {
        "preflightCount": 5,
        "preQaCount": 20,
        "referencesExposed": False,
    }
    assert len(report["qaEvaluation"]["rows"]) == 5
    assert sum(len(row["candidates"]) for row in report["qaEvaluation"]["rows"]) == 20
    assert len(qa_calls) == 20
    assert contract_checks == [f"P{index:02d}" for index in range(1, 6)] + [
        f"P{participant:02d}"
        for participant in range(1, 6)
        for _candidate in range(1, 5)
    ]

    serialized = json.dumps(report).lower()
    assert "uid-secret" not in serialized
    assert "gs://" not in serialized
    assert SOURCE_BUCKET not in serialized
    assert TEMP_BUCKET not in serialized
    assert "sourcephotoref" not in serialized
    assert "candidatepath" not in serialized
    assert "embedding" not in serialized
    assert "landmark" not in serialized
    assert "bbox" not in serialized
    assert "hash" not in serialized
    assert "sha256" not in serialized
    assert "digest" not in serialized

    for participant in range(1, 6):
        source = storage.buckets[SOURCE_BUCKET].blobs[
            f"users/uid-secret-{participant}/source/photo.jpg"
        ]
        assert source.download_preconditions == [100]
        for candidate in range(1, 5):
            generated = storage.buckets[TEMP_BUCKET].blobs[
                f"calibration/g004/{RUN_ID}/P{participant:02d}/C{candidate:02d}.png"
            ]
            assert generated.download_preconditions == [int(generated.generation)]


def test_recovery_missing_candidate_hard_stops_before_source_download_or_qa():
    storage = _storage(missing_candidate=(5, 4))
    qa_calls = []

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_recovery_request(
            _request(),
            config=_config(),
            storage_client=storage,
            qa_runner=lambda *args: qa_calls.append(args),
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            participant_contract_checker=lambda _participant: True,
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_recovery_candidate_missing"
    assert qa_calls == []
    assert all(
        blob.download_preconditions == []
        for blob in storage.buckets[SOURCE_BUCKET].blobs.values()
    )


def test_recovery_report_preserves_artifact_integrity_and_revision_as_redacted_scalars():
    report = execute_g004_calibration_recovery_request(
        _request(),
        config=_config(),
        storage_client=_storage(),
        qa_runner=_qa_runner,
        artifact=_FakeArtifactWithMetadata(),
        qa_readiness_checker=lambda: True,
        participant_contract_checker=lambda _participant: True,
        clock=_FakeClock(),
    )

    assert report["calibrationArtifactIntegrity"] == "a" * 64
    assert report["gitRevision"] == "revision-watermark-v2"
    assert report["thresholdSnapshot"]["preprocessingVersions"] == {
        "qa": "qa-preprocess-v2",
        "reference": "reference-preprocess-v1",
    }
    serialized = json.dumps(report).lower()
    assert "sha256" not in serialized
    assert "gs://" not in serialized


def test_recovery_rechecks_exact_current_consent_before_any_source_download():
    storage = _storage()
    checks = []

    def reject_fifth(participant):
        checks.append(participant.ordinal)
        return participant.ordinal != "P05"

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_recovery_request(
            _request(),
            config=_config(),
            storage_client=storage,
            qa_runner=_qa_runner,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            participant_contract_checker=reject_fifth,
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_current_source_contract_invalid"
    assert checks == ["P01", "P02", "P03", "P04", "P05"]
    assert all(
        blob.download_preconditions == []
        for blob in storage.buckets[SOURCE_BUCKET].blobs.values()
    )


def test_recovery_rejects_unproven_original_twenty_call_audit():
    request = _request()
    request["originalRunEvidence"]["providerRequestBudget"]["consumed"] = 19

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_recovery_request(
            request,
            config=_config(),
            storage_client=_storage(),
            qa_runner=_qa_runner,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            participant_contract_checker=lambda _participant: True,
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_recovery_original_audit_invalid"


def test_recovery_module_has_no_azure_generation_entrypoint():
    source = inspect.getsource(recovery_module)
    assert "get_azure_gpt_image2_provider" not in source
    assert ".generate(" not in source


def _enable_staging_cloud_run_auth(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("AVATAR_WORKER_AUTH_MODE", "cloud_run_iam")
    monkeypatch.setenv("AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED", "true")
    monkeypatch.setenv("K_SERVICE", "seolleyeon-avatar-worker")


def test_worker_service_exposes_authenticated_recovery_route(monkeypatch):
    import avatar_generation.worker_service as worker_service

    _enable_staging_cloud_run_auth(monkeypatch)
    monkeypatch.setenv("AVATAR_CALIBRATION_RECOVERY_ENDPOINT_ENABLED", "true")
    captured = []
    monkeypatch.setattr(
        worker_service,
        "execute_g004_calibration_recovery_request",
        lambda payload: captured.append(payload) or {
            "status": "completed",
            "nextState": "HUMAN_REVIEW_REQUIRED",
        },
    )

    response = worker_service.app.test_client().post(
        "/internal/g004-calibration-recovery",
        json=_request(),
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "status": "completed",
        "nextState": "HUMAN_REVIEW_REQUIRED",
    }
    assert len(captured) == 1


def test_worker_service_paid_calibration_endpoint_is_disabled_by_default(monkeypatch):
    import avatar_generation.worker_service as worker_service

    _enable_staging_cloud_run_auth(monkeypatch)
    monkeypatch.delenv("AVATAR_CALIBRATION_PAID_ENDPOINT_ENABLED", raising=False)
    called = []
    monkeypatch.setattr(
        worker_service,
        "execute_g004_calibration_request",
        lambda _payload: called.append(True) or {"status": "completed"},
    )

    response = worker_service.app.test_client().post(
        "/internal/g004-calibration",
        json=_request(),
    )

    assert response.status_code == 403
    assert response.get_json()["errorCode"] == "calibration_paid_endpoint_disabled"
    assert called == []
