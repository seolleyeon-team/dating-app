import io
import json
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.avatar_prompt_contract import AVATAR_GENERAL_PROMPT_V0_TEMP  # noqa: E402
from avatar_generation import calibration_service as calibration_service_module  # noqa: E402
from avatar_generation.calibration_runner import (  # noqa: E402
    CalibrationRunnerConfig,
    CalibrationRunnerError,
)
from avatar_generation.calibration_service import (  # noqa: E402
    CALIBRATION_REQUEST_SCHEMA,
    execute_g004_calibration_request,
)
from avatar_generation.model_adapters.azure_contracts import (  # noqa: E402
    AzureGenerationAudit,
    AzureGenerationResult,
)
from avatar_generation.qa import AvatarQAResult  # noqa: E402


SOURCE_BUCKET = "seolleyeon-final-private-source-photos"
TEMP_BUCKET = "seolleyeon-final-avatar-temp"


def _image_bytes(image_format: str = "JPEG", color=(80, 120, 160)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (512, 512), color).save(output, format=image_format)
    return output.getvalue()


class _FakeBlob:
    def __init__(
        self,
        *,
        data=None,
        content_type="",
        generation="100",
        download_generation=None,
    ):
        self.data = data
        self.content_type = content_type
        self.generation = generation
        self.download_generation = download_generation or generation
        self.download_preconditions = []
        self.reload_count = 0
        self.upload_preconditions = []
        self.delete_preconditions = []

    def exists(self):
        return self.data is not None

    def reload(self):
        self.reload_count += 1
        return None

    def download_as_bytes(self, **kwargs):
        if self.data is None:
            raise FileNotFoundError("missing")
        expected = kwargs.get("if_generation_match")
        self.download_preconditions.append(expected)
        if str(expected) != str(self.download_generation):
            raise RuntimeError("generation precondition failed")
        return self.data

    def upload_from_string(self, data, **kwargs):
        expected = kwargs.get("if_generation_match")
        self.upload_preconditions.append(expected)
        if expected != 0 or self.data is not None:
            raise RuntimeError("create-only precondition failed")
        self.data = bytes(data)
        self.content_type = kwargs.get("content_type", "")
        self.generation = "201"
        self.download_generation = self.generation

    def delete(self, **kwargs):
        expected = kwargs.get("if_generation_match")
        self.delete_preconditions.append(expected)
        if str(expected) != str(self.generation):
            raise RuntimeError("delete generation precondition failed")
        self.data = None


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

    def sleep(self, seconds):
        self.now += float(seconds)


class _FakeProvider:
    def __init__(self):
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(dict(kwargs))
        request_budget = kwargs.get("request_budget")
        if request_budget is None or not request_budget.acquire():
            raise RuntimeError("request budget unavailable")
        return AzureGenerationResult(
            image_bytes=_image_bytes("PNG", color=(90, 130, 170)),
            audit=AzureGenerationAudit(
                attempts=1,
                latency_seconds=0.25,
                provider_status=200,
                outcome="success",
                output_format="png",
                output_bytes=1024,
            ),
        )


@dataclass(frozen=True)
class _FakeArtifact:
    calibration_version: str = "g004-test-v1"
    model_versions: dict = None

    def __post_init__(self):
        object.__setattr__(
            self,
            "model_versions",
            self.model_versions
            or {
                "faceSimilarity": "face-model-test",
                "clipSafety": "clip-model-test",
            },
        )


def _qa_runner(source_ref, candidate_ref, metadata):
    assert source_ref == "process-local://source"
    assert candidate_ref == "process-local://candidate"
    assert metadata["generationBackend"] == "azure_gpt_image_2"
    assert metadata["sourceInputMode"] == "storage_normalized_original_direct"
    assert metadata["_source_image"].size == (512, 512)
    assert metadata["_candidate_image"].size == (512, 512)
    return AvatarQAResult(
        adultQa="pass",
        childlikeRisk="low",
        privacyQa="pass",
        brandQa="pass",
        beautificationRisk="low",
        cropConsistency="pass",
        cropIsolationQuality="pass",
        uniqueMarkCopyRisk="low",
        logoTextWatermarkRisk="low",
        textLogoWatermarkRisk="low",
        backgroundLeakageRisk="low",
        secondaryFaceLeakageRisk="low",
        identifiabilityRisk="low",
        previewAllowed=True,
        requiresHumanReview=False,
        qaVersion="avatar_qa_v2",
        debug={
            "modelAvailability": {
                "faceDetector": "available",
                "visualRisk": "available",
                "localSafetyRisk": "available",
                "faceSimilarity": "available",
            }
        },
    )


def _manifest():
    return {
        "projectId": "seolleyeon-final",
        "purpose": "g004_quality_calibration",
        "calibrationVersion": "g004-test-v1",
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
                    "calibrationVersion": "g004-test-v1",
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


@pytest.fixture(autouse=True)
def _stub_live_current_source_contract_factory(monkeypatch):
    monkeypatch.setattr(
        calibration_service_module,
        "_build_current_source_contract_checker",
        lambda **_kwargs: (lambda _participant: True),
        raising=False,
    )


def _request():
    return {
        "schemaVersion": CALIBRATION_REQUEST_SCHEMA,
        "runId": "G004-AZURE-CAL-TEST-001",
        "manifest": _manifest(),
    }


def _config(**overrides):
    values = {
        "enabled": True,
        "environment": "staging",
        "project": "seolleyeon-final",
        "data_project": "seolleyeon-final",
        "purpose": "g004_quality_calibration",
        "queue_status": "PAUSED",
        "candidate_count": 1,
        "quota_rpm": 2.0,
        "run_id": "",
        "calibration_version": "g004-test-v1",
        "max_retries": 0,
        "operator_timeout_seconds": 180,
        "job_lease_seconds": 180,
    }
    values.update(overrides)
    return CalibrationRunnerConfig(**values)


def _storage():
    source_blobs = {
        f"users/uid-secret-{index}/source/photo.jpg": _FakeBlob(
            data=_image_bytes("JPEG", color=(50 + index, 90, 120)),
            content_type="image/jpeg",
            generation="100",
        )
        for index in range(1, 6)
    }
    return _FakeStorage(
        {
            SOURCE_BUCKET: _FakeBucket(source_blobs),
            TEMP_BUCKET: _FakeBucket(),
        }
    )


def test_service_runs_five_participants_without_exposing_private_identifiers():
    storage = _storage()
    provider = _FakeProvider()
    contract_checks = []

    def current_source_checker(participant):
        contract_checks.append(participant.ordinal)
        return True

    report = execute_g004_calibration_request(
        _request(),
        config=_config(),
        storage_client=storage,
        provider=provider,
        qa_runner=_qa_runner,
        artifact=_FakeArtifact(),
        qa_readiness_checker=lambda: True,
        participant_contract_checker=current_source_checker,
        clock=_FakeClock(),
    )

    assert report["status"] == "completed"
    assert report["participantCount"] == 5
    assert report["candidateCount"] == 5
    assert report["providerRequestBudget"] == {
        "limit": 5,
        "consumed": 5,
        "remaining": 0,
    }
    assert report["currentSourceContractChecks"] == {
        "preflightCount": 5,
        "preProviderCount": 5,
        "referencesExposed": False,
    }
    assert report["sourceGenerationChecks"] == {
        "preflightCount": 5,
        "preProviderCount": 5,
        "referencesExposed": False,
    }
    assert contract_checks == [
        "P01",
        "P02",
        "P03",
        "P04",
        "P05",
        "P01",
        "P02",
        "P03",
        "P04",
        "P05",
    ]
    assert report["reviewArtifacts"] == {
        "count": 5,
        "private": True,
        "referencesExposed": False,
        "retention": "delete_after_bounded_human_review",
    }
    assert len(provider.calls) == 5
    assert all(call["prompt"] == AVATAR_GENERAL_PROMPT_V0_TEMP for call in provider.calls)
    assert all(call["source_content_type"] == "image/jpeg" for call in provider.calls)
    assert all(call["deadline_monotonic"] == 180.0 for call in provider.calls)
    assert all(
        blob.download_preconditions == [100]
        for blob in storage.buckets[SOURCE_BUCKET].blobs.values()
    )

    serialized = json.dumps(report)
    assert "uid-secret" not in serialized
    assert "gs://" not in serialized
    assert SOURCE_BUCKET not in serialized
    assert TEMP_BUCKET not in serialized

    review_paths = [
        path
        for path, blob in storage.buckets[TEMP_BUCKET].blobs.items()
        if blob.exists()
    ]
    assert review_paths == [
        f"calibration/g004/G004-AZURE-CAL-TEST-001/P{participant:02d}/C01.png"
        for participant in range(1, 6)
    ]
    assert all("uid-secret" not in path for path in review_paths)
    assert all(
        blob.upload_preconditions == [0]
        for blob in storage.buckets[TEMP_BUCKET].blobs.values()
    )


def test_service_rejects_non_staging_data_project_before_paid_calls():
    provider = _FakeProvider()

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_request(
            _request(),
            config=_config(data_project=""),
            storage_client=_storage(),
            provider=provider,
            qa_runner=_qa_runner,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_data_project_invalid"
    assert provider.calls == []


def test_service_rejects_any_current_source_mismatch_before_all_paid_calls():
    storage = _storage()
    provider = _FakeProvider()

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_request(
            _request(),
            config=_config(),
            storage_client=storage,
            provider=provider,
            qa_runner=_qa_runner,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            participant_contract_checker=lambda participant: participant.ordinal != "P05",
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_current_source_contract_invalid"
    assert provider.calls == []
    assert all(
        blob.download_preconditions == []
        for blob in storage.buckets[SOURCE_BUCKET].blobs.values()
    )


def test_service_rechecks_pinned_source_generation_before_provider_send():
    storage = _storage()
    provider = _FakeProvider()
    checks = 0

    def checker(_participant):
        nonlocal checks
        checks += 1
        if checks == 6:
            first_blob = storage.buckets[SOURCE_BUCKET].blobs[
                "users/uid-secret-1/source/photo.jpg"
            ]
            first_blob.generation = "101"
        return True

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_request(
            _request(),
            config=_config(),
            storage_client=storage,
            provider=provider,
            qa_runner=_qa_runner,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            participant_contract_checker=checker,
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_source_generation_mismatch"
    assert provider.calls == []


def test_fixture_current_source_contract_requires_exact_source_and_consent():
    summary = calibration_service_module.validate_calibration_manifest_value(
        _manifest(),
        expected_project="seolleyeon-final",
    )
    participant = summary.participants[0]
    private_doc = {
        "sourcePhotos": [
            {
                "gcsUri": participant.source_ref,
                "status": "active",
                "contentType": "image/jpeg",
                "encrypted": True,
                "exifStripped": True,
                "purpose": {"avatarGeneration": True},
            }
        ],
        "photoConsent": {
            "version": "photo_consent_v4",
            "avatarGeneration": True,
            "profileDisplayOriginalPhoto": False,
            "calibrationPurpose": True,
            "azureExternalAiProcessing": True,
            "sourceImageUse": True,
            "qaScoring": True,
            "humanReview": True,
            "temporaryRetention": "bounded_delete_after_review",
            "calibrationDate": "2026-08-24",
            "calibrationVersion": "g004-test-v1",
        },
        "stagingCalibration": {
            "scope": "g004_quality_calibration",
            "calibrationVersion": "g004-test-v1",
            "fresh": True,
            "approvedAvatarLocked": False,
        },
    }

    assert calibration_service_module._current_source_contract_matches(
        private_doc,
        participant,
        calibration_version="g004-test-v1",
    )

    private_doc["photoConsent"]["azureExternalAiProcessing"] = False
    assert not calibration_service_module._current_source_contract_matches(
        private_doc,
        participant,
        calibration_version="g004-test-v1",
    )

    for field in (
        "calibrationPurpose",
        "azureExternalAiProcessing",
        "sourceImageUse",
        "qaScoring",
        "humanReview",
    ):
        candidate = deepcopy(private_doc)
        candidate["photoConsent"]["azureExternalAiProcessing"] = True
        candidate["photoConsent"].pop(field, None)
        assert not calibration_service_module._current_source_contract_matches(
            candidate,
            participant,
            calibration_version="g004-test-v1",
        )


def test_service_rejects_calibration_version_mismatch_before_paid_calls():
    provider = _FakeProvider()
    request = _request()
    request["manifest"]["calibrationVersion"] = "wrong-version"

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_request(
            request,
            config=_config(),
            storage_client=_storage(),
            provider=provider,
            qa_runner=_qa_runner,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_version_mismatch"
    assert provider.calls == []


def test_service_rejects_changed_source_generation_before_paid_calls():
    provider = _FakeProvider()
    request = _request()
    request["manifest"]["participants"][4]["sourceGeneration"] = "101"

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_request(
            request,
            config=_config(),
            storage_client=_storage(),
            provider=provider,
            qa_runner=_qa_runner,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_source_generation_mismatch"
    assert provider.calls == []


def test_service_source_download_is_generation_pinned_against_reload_download_race():
    provider = _FakeProvider()
    storage = _storage()
    racing_blob = storage.buckets[SOURCE_BUCKET].blobs[
        "users/uid-secret-5/source/photo.jpg"
    ]
    racing_blob.download_generation = "101"

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_request(
            _request(),
            config=_config(),
            storage_client=storage,
            provider=provider,
            qa_runner=_qa_runner,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_source_unavailable"
    assert provider.calls == []


def test_service_requires_exactly_five_manifest_rows_before_paid_calls():
    provider = _FakeProvider()
    request = _request()
    request["manifest"]["participants"].append(
        deepcopy(request["manifest"]["participants"][0])
    )
    request["manifest"]["participants"][-1]["uid"] = "uid-secret-6"
    request["manifest"]["participants"][-1]["sourcePhotoRef"] = (
        f"gs://{SOURCE_BUCKET}/users/uid-secret-6/source/photo.jpg"
    )

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_request(
            request,
            config=_config(),
            storage_client=_storage(),
            provider=provider,
            qa_runner=_qa_runner,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            clock=_FakeClock(),
        )

    assert error.value.code == "G004_CALIBRATION_COHORT_SIZE_INVALID"
    assert provider.calls == []


def test_service_rolls_back_partial_review_artifacts_on_failure():
    storage = _storage()
    provider = _FakeProvider()
    qa_calls = 0

    def failing_qa(*args, **kwargs):
        nonlocal qa_calls
        qa_calls += 1
        if qa_calls == 2:
            raise RuntimeError("private source should never escape")
        return _qa_runner(*args, **kwargs)

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_request(
            _request(),
            config=_config(),
            storage_client=storage,
            provider=provider,
            qa_runner=failing_qa,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_provider_failed"
    assert not any(blob.exists() for blob in storage.buckets[TEMP_BUCKET].blobs.values())
    touched = [
        blob
        for blob in storage.buckets[TEMP_BUCKET].blobs.values()
        if blob.delete_preconditions
    ]
    assert len(touched) == 1
    assert touched[0].delete_preconditions == [201]


def test_service_create_only_upload_never_overwrites_or_deletes_racing_object():
    storage = _storage()
    provider = _FakeProvider()
    target = storage.buckets[TEMP_BUCKET].blob(
        "calibration/g004/G004-AZURE-CAL-TEST-001/P01/C01.png"
    )
    original_generate = provider.generate

    def generate_with_race(**kwargs):
        target.data = b"racing-object"
        target.generation = "999"
        target.download_generation = "999"
        return original_generate(**kwargs)

    provider.generate = generate_with_race

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_request(
            _request(),
            config=_config(),
            storage_client=storage,
            provider=provider,
            qa_runner=_qa_runner,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: True,
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_provider_failed"
    assert target.data == b"racing-object"
    assert target.upload_preconditions == [0]
    assert target.delete_preconditions == []


def test_service_rejects_unready_qa_before_paid_calls():
    provider = _FakeProvider()

    with pytest.raises(CalibrationRunnerError) as error:
        execute_g004_calibration_request(
            _request(),
            config=_config(),
            storage_client=_storage(),
            provider=provider,
            qa_runner=_qa_runner,
            artifact=_FakeArtifact(),
            qa_readiness_checker=lambda: False,
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_qa_not_ready"
    assert provider.calls == []


def _enable_staging_cloud_run_auth(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("AVATAR_WORKER_AUTH_MODE", "cloud_run_iam")
    monkeypatch.setenv("AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED", "true")
    monkeypatch.setenv("K_SERVICE", "seolleyeon-avatar-worker")


def test_worker_service_exposes_authenticated_internal_calibration_route(monkeypatch):
    import avatar_generation.worker_service as worker_service

    _enable_staging_cloud_run_auth(monkeypatch)
    monkeypatch.setenv("AVATAR_CALIBRATION_PAID_ENDPOINT_ENABLED", "true")
    captured = []
    monkeypatch.setattr(
        worker_service,
        "execute_g004_calibration_request",
        lambda payload: captured.append(payload) or {"status": "completed", "redacted": True},
    )

    response = worker_service.app.test_client().post(
        "/internal/g004-calibration",
        json=_request(),
    )

    assert response.status_code == 200
    assert response.get_json() == {"status": "completed", "redacted": True}
    assert len(captured) == 1


def test_worker_service_returns_only_stable_calibration_error(monkeypatch):
    import avatar_generation.worker_service as worker_service

    _enable_staging_cloud_run_auth(monkeypatch)
    monkeypatch.setenv("AVATAR_CALIBRATION_PAID_ENDPOINT_ENABLED", "true")

    def fail(_payload):
        raise CalibrationRunnerError(
            "calibration_source_missing",
            "Calibration source photo is unavailable.",
        )

    monkeypatch.setattr(worker_service, "execute_g004_calibration_request", fail)
    response = worker_service.app.test_client().post(
        "/internal/g004-calibration",
        json=_request(),
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "status": "error",
        "error": "Calibration source photo is unavailable.",
        "errorCode": "calibration_source_missing",
    }
    assert "uid-secret" not in response.get_data(as_text=True)
