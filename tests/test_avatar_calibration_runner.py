import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from scripts.avatar_calibration_runner import (  # noqa: E402
    CalibrationRunnerConfig,
    CalibrationRunnerError,
    RetryAfterError,
    run_calibration,
    validate_calibration_manifest,
)


def _consent(exact: bool = True) -> dict[str, object]:
    return {
        "exact": exact,
        "calibrationPurpose": exact,
        "sourceImageUse": exact,
        "azureExternalAiProcessing": exact,
        "qaScoring": exact,
        "humanReview": exact,
        "temporaryRetention": "bounded_delete_after_review" if exact else "",
        "calibrationDate": "2026-08-23",
        "calibrationVersion": "g004-test-v1" if exact else "",
    }


def _manifest_payload(count: int = 5, *, consent_exact: bool = True) -> dict[str, object]:
    return {
        "projectId": "seolleyeon-final",
        "purpose": "g004_quality_calibration",
        "calibrationVersion": "g004-test-v1",
        "participants": [
            {
                "uid": f"uid-secret-{index}",
                "sourcePhotoRef": f"gs://private-source/users/uid-secret-{index}/source/photo.png",
                "sourceVersion": "source-v1",
                "sourceGeneration": "100",
                "fresh": True,
                "approvedAvatarLocked": False,
                "authProject": "seolleyeon-final",
                "consent": _consent(consent_exact),
                "cohortSlice": {"background": "simple", "eyewear": "none", "hair": "short"},
            }
            for index in range(1, count + 1)
        ],
    }


def _write_manifest(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "g004-manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _config(**overrides) -> CalibrationRunnerConfig:
    values = {
        "enabled": True,
        "environment": "staging",
        "project": "seolleyeon-final",
        "data_project": "seolleyeon-final",
        "purpose": "g004_quality_calibration",
        "queue_status": "PAUSED",
        "candidate_count": 1,
        "quota_rpm": 2.0,
        "run_id": "G004-AZURE-CAL-TEST-001",
        "calibration_version": "g004-test-v1",
        "max_retries": 1,
    }
    values.update(overrides)
    return CalibrationRunnerConfig(**values)


class _FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(float(seconds))
        self.now += float(seconds)


def _generator(participant, candidate_ordinal, context=None):
    return {
        "candidateOrdinal": candidate_ordinal,
        "qa": {
            "qaVersion": "avatar_qa_v2",
            "modelAvailability": {
                "faceDetector": "available",
                "visualRisk": "available",
                "localSafetyRisk": "available",
                "faceSimilarity": "available",
            },
            "decision": {
                "selectionTier": "needs_review",
                "previewAllowed": False,
                "requiresHumanReview": True,
            },
        },
        "metrics": {"latencyMs": 10.0, "costUsd": 0.01},
    }


def test_calibration_mode_defaults_off(monkeypatch):
    for key in (
        "AVATAR_CALIBRATION_RUN_ENABLED",
        "AVATAR_CALIBRATION_PURPOSE",
        "AVATAR_CALIBRATION_PROJECT",
        "AVATAR_CALIBRATION_RUN_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    config = CalibrationRunnerConfig.from_env()
    assert config.enabled is False


def test_manifest_summary_is_redacted_and_counts_only_exact_consent(tmp_path):
    path = _write_manifest(tmp_path, _manifest_payload(5, consent_exact=False))
    summary = validate_calibration_manifest(path, expected_project="seolleyeon-final")

    assert summary.eligible_count == 0
    assert summary.total_count == 5
    serialized = json.dumps(summary.to_report())
    assert "uid-secret" not in serialized
    assert "gs://" not in serialized
    assert "private-source" not in serialized


def test_manifest_mapping_validation_avoids_plaintext_temp_files():
    from avatar_generation import calibration_runner as runner_module

    summary = runner_module.validate_calibration_manifest_value(
        _manifest_payload(),
        expected_project="seolleyeon-final",
    )

    assert summary.eligible_count == 5
    assert summary.blocked_reason_counts == {}


def test_manifest_requires_an_exact_source_object_generation():
    from avatar_generation import calibration_runner as runner_module

    payload = _manifest_payload()
    del payload["participants"][0]["sourceGeneration"]
    summary = runner_module.validate_calibration_manifest_value(
        payload,
        expected_project="seolleyeon-final",
    )

    assert summary.eligible_count == 4
    assert summary.blocked_reason_counts == {"source_generation_missing": 1}


def test_production_project_is_rejected_before_generation(tmp_path):
    path = _write_manifest(tmp_path, _manifest_payload())
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")
    config = _config(environment="production", project="seolleyeon")

    with pytest.raises(CalibrationRunnerError, match="staging") as error:
        run_calibration(config, manifest, generator=_generator, qa_evaluator=lambda rows: {}, clock=_FakeClock())
    assert error.value.code == "calibration_staging_only"


def test_non_staging_data_project_is_rejected_before_generation(tmp_path):
    path = _write_manifest(tmp_path, _manifest_payload())
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")
    calls = []

    with pytest.raises(CalibrationRunnerError) as error:
        run_calibration(
            _config(data_project=""),
            manifest,
            generator=lambda *args, **kwargs: calls.append(True) or _generator(*args, **kwargs),
            qa_evaluator=lambda rows: {},
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_data_project_invalid"
    assert calls == []


def test_missing_consent_fails_before_provider_calls(tmp_path):
    path = _write_manifest(tmp_path, _manifest_payload(5, consent_exact=False))
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")
    calls = []

    def generator(*args, **kwargs):
        calls.append(True)
        return _generator(*args, **kwargs)

    with pytest.raises(CalibrationRunnerError) as error:
        run_calibration(_config(), manifest, generator=generator, qa_evaluator=lambda rows: {}, clock=_FakeClock())
    assert error.value.code == "G004_CALIBRATION_COHORT_SIZE_INVALID"
    assert calls == []


def test_more_than_five_eligible_participants_are_rejected_before_provider_calls(tmp_path):
    path = _write_manifest(tmp_path, _manifest_payload(6))
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")
    calls = []

    with pytest.raises(CalibrationRunnerError) as error:
        run_calibration(
            _config(),
            manifest,
            generator=lambda *args, **kwargs: calls.append(True) or _generator(*args, **kwargs),
            qa_evaluator=lambda rows: {},
            clock=_FakeClock(),
        )

    assert error.value.code == "G004_CALIBRATION_COHORT_SIZE_INVALID"
    assert calls == []


def test_calibration_quota_cannot_exceed_verified_two_rpm():
    with pytest.raises(ValueError, match="2 RPM"):
        _config(quota_rpm=2.01)


def test_calibration_env_quota_cannot_exceed_verified_two_rpm(monkeypatch):
    monkeypatch.setenv("AVATAR_AZURE_QUOTA_RPM", "3")

    with pytest.raises(ValueError, match="2 RPM"):
        CalibrationRunnerConfig.from_env()


def test_general_queue_must_remain_paused(tmp_path):
    path = _write_manifest(tmp_path, _manifest_payload())
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")

    with pytest.raises(CalibrationRunnerError) as error:
        run_calibration(
            _config(queue_status="RUNNING"),
            manifest,
            generator=_generator,
            qa_evaluator=lambda rows: {},
            clock=_FakeClock(),
        )
    assert error.value.code == "calibration_queue_must_be_paused"


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "preview_ready"},
        {"approved": True},
        {"publicProfile": True},
        {"previewExposed": True},
    ],
)
def test_calibration_side_effects_are_rejected(tmp_path, payload):
    path = _write_manifest(tmp_path, _manifest_payload())
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")

    def generator(*args, **kwargs):
        value = _generator(*args, **kwargs)
        value.update(payload)
        return value

    with pytest.raises(CalibrationRunnerError) as error:
        run_calibration(_config(), manifest, generator=generator, qa_evaluator=lambda rows: {}, clock=_FakeClock())
    assert error.value.code == "calibration_side_effect_forbidden"


def test_qa_preview_eligibility_is_not_treated_as_preview_exposure(tmp_path):
    """A hard-pass QA signal is evidence, not a public preview side effect."""

    path = _write_manifest(tmp_path, _manifest_payload())
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")

    def generator(participant, candidate_ordinal, context=None):
        value = _generator(participant, candidate_ordinal, context)
        value["qa"] = {
            "selectionTier": "hardPass",
            "previewAllowed": True,
            "modelAvailability": {
                "faceDetector": "available",
                "visualRisk": "available",
                "clipSafety": "available",
                "faceSimilarity": "available",
            },
        }
        value["previewExposed"] = False
        return value

    result = run_calibration(
        _config(),
        manifest,
        generator=generator,
        qa_evaluator=lambda rows: {"candidateCount": sum(len(row["candidates"]) for row in rows)},
        clock=_FakeClock(),
    )

    assert result.candidate_count == 5
    assert result.preview_side_effects == 0


def test_retry_after_and_retry_are_rate_limited(tmp_path):
    path = _write_manifest(tmp_path, _manifest_payload())
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")
    clock = _FakeClock()
    starts: list[float] = []
    attempts = 0

    def generator(participant, candidate_ordinal, context=None):
        nonlocal attempts
        starts.append(clock.monotonic())
        attempts += 1
        if attempts == 1:
            raise RetryAfterError(3.0)
        return _generator(participant, candidate_ordinal, context)

    result = run_calibration(
        _config(),
        manifest,
        generator=generator,
        qa_evaluator=lambda rows: {"participantCount": len(rows)},
        clock=clock,
    )

    assert result.retry_count == 1
    assert result.azure_call_count == 6
    assert all(right - left >= 1.0 for left, right in zip(starts, starts[1:]))
    assert starts[1] - starts[0] >= 3.0
    assert result.to_report()["previewSideEffects"] == 0


def test_provider_internal_attempts_are_counted_as_calls_and_retries(tmp_path):
    path = _write_manifest(tmp_path, _manifest_payload())
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")

    def generator(participant, candidate_ordinal, context=None):
        value = _generator(participant, candidate_ordinal, context)
        value["metrics"]["providerAttempts"] = 3 if participant.ordinal == "P01" else 1
        return value

    result = run_calibration(
        _config(),
        manifest,
        generator=generator,
        qa_evaluator=lambda rows: {},
        clock=_FakeClock(),
    )

    assert result.azure_call_count == 7
    assert result.retry_count == 2


def test_calibration_rejects_timeout_shorter_than_minimum_two_rpm_start_span(tmp_path):
    path = _write_manifest(tmp_path, _manifest_payload())
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")
    calls = []

    with pytest.raises(CalibrationRunnerError) as error:
        run_calibration(
            _config(
                candidate_count=4,
                quota_rpm=2.0,
                operator_timeout_seconds=500,
                job_lease_seconds=500,
            ),
            manifest,
            generator=lambda *args, **kwargs: calls.append(True) or _generator(*args, **kwargs),
            qa_evaluator=lambda rows: {},
            clock=_FakeClock(),
        )

    assert error.value.code == "calibration_time_budget_insufficient"
    assert calls == []


def test_calibration_passes_one_absolute_deadline_to_every_provider_call(tmp_path):
    path = _write_manifest(tmp_path, _manifest_payload())
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")
    clock = _FakeClock()
    deadlines: list[float] = []

    def generator(participant, candidate_ordinal, context=None):
        deadlines.append(float(context["deadlineMonotonic"]))
        assert context["remainingSeconds"] > 0
        return _generator(participant, candidate_ordinal, context)

    result = run_calibration(
        _config(
            quota_rpm=2.0,
            operator_timeout_seconds=200,
            job_lease_seconds=150,
        ),
        manifest,
        generator=generator,
        qa_evaluator=lambda rows: {},
        clock=clock,
    )

    assert result.azure_call_count == 5
    assert deadlines == [150.0] * 5


def test_result_report_never_persists_raw_manifest_data(tmp_path):
    path = _write_manifest(tmp_path, _manifest_payload())
    manifest = validate_calibration_manifest(path, expected_project="seolleyeon-final")
    result = run_calibration(
        _config(),
        manifest,
        generator=_generator,
        qa_evaluator=lambda rows: {"participantCount": len(rows)},
        clock=_FakeClock(),
    )
    serialized = json.dumps(result.to_report())

    assert "uid-secret" not in serialized
    assert "gs://" not in serialized
    assert "private-source" not in serialized
    assert "sourcePhotoRef" not in serialized
