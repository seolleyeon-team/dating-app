import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import avatar_g004_recover_qa as recovery_script  # noqa: E402
from avatar_generation.calibration_operator import (  # noqa: E402
    CalibrationOperatorError,
    StagedRecoveryBundle,
)
from avatar_generation.calibration_evaluator import redact_calibration_report  # noqa: E402


def _report():
    return {
        "status": "completed",
        "nextState": "HUMAN_REVIEW_REQUIRED",
        "evaluationId": "G004-AZURE-CAL-20260824-001-QA-RECOVERY-2",
        "participantCount": 5,
        "participantOrdinals": [f"P{index:02d}" for index in range(1, 6)],
        "candidateCount": 20,
        "azureCallCount": 20,
        "retryCount": 0,
        "generationCallsPerformedByRecovery": 0,
        "qaEvaluationVersion": "avatar_qa_v3_watermark_evidence_v1",
        "watermarkPolicyVersion": "watermark_policy_v2_source_consistency_v1",
        "calibrationEvaluationVersion": "g004_calibration_evaluation_v2_watermark_evidence",
        "thresholdSnapshot": {
            "calibrationVersion": "g004-live-calibration-v1",
            "modelVersions": {},
            "preprocessingVersions": {},
        },
        "calibrationArtifactIntegrity": "unavailable",
        "gitRevision": "unavailable",
        "previewSideEffects": 0,
        "approvalSideEffects": 0,
        "publicProjectionSideEffects": 0,
        "qaEvaluation": {
            "rows": [
                {
                    "participantOrdinal": f"P{participant:02d}",
                    "candidates": [
                        {
                            "candidateOrdinal": candidate,
                            "previewExposed": False,
                            "approvalPerformed": False,
                            "publicProjection": False,
                            "qa": {"qaVersion": "avatar_qa_v2"},
                        }
                        for candidate in range(1, 5)
                    ],
                }
                for participant in range(1, 6)
            ]
        },
        "recovery": {
            "candidatePreflightCount": 20,
            "qaEvaluationCount": 20,
            "readOnly": True,
        },
        "reviewArtifacts": {"count": 20, "referencesExposed": False},
        "rawImagePersistence": 0,
        "rawBiometricPersistence": 0,
    }


def test_validate_recovery_report_requires_complete_read_only_twenty_candidate_evidence():
    recovery_script._validate_recovery_report(_report())


def test_validate_recovery_report_accepts_actual_server_redaction_contract():
    recovery_script._validate_recovery_report(
        redact_calibration_report(_report())
    )


def test_attach_recovery_audit_metadata_creates_new_parented_evaluation():
    enriched = recovery_script._attach_recovery_audit_metadata(
        _report(),
        run_id="G004-AZURE-CAL-20260824-001",
        parent_recovery_id="G004-AZURE-CAL-20260824-001-QA-RECOVERY-2",
        worker_image_digest="sha256:" + "a" * 64,
    )

    assert enriched["evaluationId"] == (
        "G004-AZURE-CAL-20260824-001-QA-RECOVERY-3"
    )
    assert enriched["evaluationVersion"] == "QA-RECOVERY-3"
    assert enriched["parentRunId"] == "G004-AZURE-CAL-20260824-001"
    assert enriched["parentRecoveryId"].endswith("QA-RECOVERY-2")
    assert enriched["qaVersion"] == enriched["qaEvaluationVersion"]
    assert enriched["workerImage"] == "sha256:" + "a" * 64


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("generationCallsPerformedByRecovery",), 1),
        (("candidateCount",), 19),
        (("previewSideEffects",), 1),
        (("recovery", "qaEvaluationCount"), 19),
    ],
)
def test_validate_recovery_report_fails_closed_for_inconsistent_evidence(path, value):
    report = _report()
    target = report
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(CalibrationOperatorError, match="operator_recovery_report_invalid"):
        recovery_script._validate_recovery_report(report)


def test_recovery_http_client_uses_only_qa_recovery_route(monkeypatch):
    captured = {}

    class _Response:
        status_code = 200

        def json(self):
            return _report()

    def post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _Response()

    monkeypatch.setattr(recovery_script.httpx, "post", post)

    report = recovery_script._post_once(
        service_url="https://worker-example.a.run.app",
        token="opaque-token",
        request_body={"schemaVersion": "g004_calibration_recovery_request_v1"},
        timeout_seconds=60,
    )

    assert report["status"] == "completed"
    assert captured["url"].endswith("/internal/g004-calibration-recovery")
    assert not captured["url"].endswith("/internal/g004-calibration")
    assert captured["kwargs"]["follow_redirects"] is False


class _CleanupGateway:
    def __init__(self):
        self.deleted = []

    def identity_token(self):
        return "opaque-token"

    def delete(self, uri, *, generation):
        self.deleted.append((uri, generation))


def _staged_bundle():
    return StagedRecoveryBundle(
        count=1,
        _objects=(("gs://private-temp/candidate.png", "101"),),
    )


def test_known_recovery_failure_generation_match_cleans_staged_candidates(monkeypatch):
    gateway = _CleanupGateway()
    monkeypatch.setattr(
        recovery_script,
        "_post_once",
        lambda **_kwargs: (_ for _ in ()).throw(
            CalibrationOperatorError("operator_recovery_remote_rejected")
        ),
    )

    with pytest.raises(CalibrationOperatorError, match="operator_recovery_remote_rejected"):
        recovery_script._recover_report_and_cleanup(
            gateway=gateway,
            staged_bundle=_staged_bundle(),
            service_url="https://worker-example.a.run.app",
            request_body={},
            timeout_seconds=60,
            private_values=(),
        )

    assert gateway.deleted == [("gs://private-temp/candidate.png", "101")]


def test_unknown_recovery_http_outcome_preserves_staged_candidates(monkeypatch):
    gateway = _CleanupGateway()
    monkeypatch.setattr(
        recovery_script,
        "_post_once",
        lambda **_kwargs: (_ for _ in ()).throw(
            CalibrationOperatorError("operator_recovery_http_unknown_outcome")
        ),
    )

    with pytest.raises(CalibrationOperatorError, match="operator_recovery_http_unknown_outcome"):
        recovery_script._recover_report_and_cleanup(
            gateway=gateway,
            staged_bundle=_staged_bundle(),
            service_url="https://worker-example.a.run.app",
            request_body={},
            timeout_seconds=60,
            private_values=(),
        )

    assert gateway.deleted == []
