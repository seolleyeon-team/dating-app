import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.calibration_artifact import (  # noqa: E402
    CalibrationArtifact,
    CalibrationArtifactError,
    canonical_artifact_sha256,
)
from scripts.avatar_calibration_evaluator import (  # noqa: E402
    evaluate_calibration_rows,
    freeze_threshold_snapshot,
    redact_calibration_report,
)


def _artifact() -> CalibrationArtifact:
    value = {
        "schemaVersion": "avatar_qa_calibration_v1",
        "calibrationVersion": "g004-test-v1",
        "createdAt": "2026-08-23T00:00:00Z",
        "gitRevision": "test-revision",
        "qaContractVersion": "avatar-qa-v1",
        "cohortPolicyVersion": "g004-5plus-v1",
        "modelVersions": {
            "faceSimilarity": "openai/clip-vit-base-patch32",
            "clipSafety": "openai/clip-vit-large-patch14",
        },
        "preprocessingVersions": {
            "reference": "avatar-reference-v1",
            "qa": "avatar-qa-preprocess-v1",
        },
        "faceSimilarity": {
            "model": "openai/clip-vit-base-patch32",
            "metric": "cosine",
            "semanticRole": "identity_privacy_upper_bound",
            "threshold": 0.86,
            "thresholdDirection": "gte_review",
            "reviewMargin": 0.04,
            "evidenceSummary": "deterministic non-user evidence",
        },
        "clipSafety": {
            "model": "openai/clip-vit-large-patch14",
            "thresholds": {
                "childlike": 0.35,
                "sexualized": 0.35,
                "beautification": 0.55,
                "brand_mismatch": 0.45,
                "severe_artifact": 0.35,
            },
            "minimumScores": {"adult_like": 0.55, "brand_fit": 0.55},
            "evidenceSummary": "deterministic non-user evidence",
        },
        "humanReviewPolicy": {"rubricVersion": "g004-v1"},
    }
    value["integrity"] = {"sha256": canonical_artifact_sha256(value)}
    return CalibrationArtifact.from_mapping(value)


def _consent() -> dict[str, object]:
    return {
        "exact": True,
        "calibrationPurpose": True,
        "sourceImageUse": True,
        "azureExternalAiProcessing": True,
        "qaScoring": True,
        "humanReview": True,
        "temporaryRetention": "bounded_delete_after_review",
        "calibrationVersion": "g004-test-v1",
    }


def _rubric(*, safety: str = "approve") -> dict[str, object]:
    return {
        "reviewerPresent": True,
        "overallQuality": 4,
        "resemblance": 4,
        "ageDistortionRisk": 4,
        "consistency": 4,
        "backgroundNaturalness": 4,
        "safety": safety,
        "usableCandidate": True,
        "regenerationNeeded": False,
        "note": "sanitized observation",
    }


def _candidate(ordinal: int, tier: str = "hard_pass", *, missing_signal: bool = False) -> dict[str, object]:
    availability = {
        "faceDetector": "available",
        "faceSimilarity": "available",
        "clipSafety": "available",
        "visualRisk": "available",
    }
    if missing_signal:
        availability.pop("clipSafety")
    preview = tier == "hard_pass"
    return {
        "candidateOrdinal": ordinal,
        "qa": {
            "decision": {
                "selectionTier": tier,
                "previewAllowed": preview,
                "requiresHumanReview": tier == "needs_review",
                "hardRejectReasons": ["severe_artifact"] if tier == "hard_reject" else [],
                "needsReviewReasons": ["model_unavailable"] if tier == "needs_review" else [],
            },
            "modelAvailability": availability,
            "faceSimilarityScore": 0.20,
            "traitCoverage": 0.8,
        },
        "metrics": {"latencyMs": 1000 + ordinal, "costUsd": 0.01 + ordinal / 10000},
    }


def _row(ordinal: int, *, missing_signal: bool = False, incomplete_rubric: bool = False) -> dict[str, object]:
    rubric = _rubric()
    if incomplete_rubric:
        rubric.pop("backgroundNaturalness")
    return {
        "participantOrdinal": f"P{ordinal:02d}",
        "consent": _consent(),
        "cohortSlice": {"background": "simple", "eyewear": "none", "hair": "short"},
        "candidates": [
            _candidate(1, "hard_pass"),
            _candidate(2, "soft_pass"),
            _candidate(3, "needs_review", missing_signal=missing_signal),
            _candidate(4, "hard_reject"),
        ],
        "humanReview": rubric,
    }


def _run_rows(count: int = 5) -> list[dict[str, object]]:
    return [_row(index) for index in range(1, count + 1)]


def _snapshot(artifact: CalibrationArtifact) -> dict[str, object]:
    return {
        "calibrationVersion": artifact.calibration_version,
        "artifactSha256": artifact.payload["integrity"]["sha256"],
        "modelVersions": dict(artifact.model_versions),
        "preprocessingVersions": dict(artifact.preprocessing_versions),
    }


def test_evaluator_counts_four_candidates_and_requires_safe_preview_contract():
    artifact = _artifact()
    report = evaluate_calibration_rows(
        _run_rows(),
        artifact=artifact,
        rubric={"thresholdSnapshot": _snapshot(artifact)},
    )

    assert report["participantCount"] == 5
    assert report["schemaVersion"] == "g004_calibration_evaluation_v3_watermark_artifact_only"
    assert report["consentCount"] == 5
    assert report["candidateCount"] == 20
    assert report["counts"] == {
        "hardPass": 5,
        "softPass": 5,
        "needsReview": 5,
        "hardReject": 5,
    }
    assert report["previewViolations"] == 0
    assert report["g004Pass"] is False


def test_evaluator_aggregates_redacted_watermark_decision_classes():
    artifact = _artifact()
    rows = _run_rows()
    rows[0]["candidates"][0]["qa"]["debug"] = {
        "watermarkDecisionClass": "source_consistent_clothing_text",
        "watermarkEvidenceClasses": ["source_consistent_clothing_text"],
        "watermarkQaAction": "allow",
        "watermarkPolicyVersion": "watermark_policy_v3_generated_artifact_only_v1",
    }
    rows[0]["candidates"][1]["qa"]["debug"] = {
        "watermarkDecisionClass": "overlay_watermark",
        "watermarkEvidenceClasses": ["overlay_watermark"],
        "watermarkQaAction": "reject",
        "watermarkPolicyVersion": "watermark_policy_v3_generated_artifact_only_v1",
    }

    report = evaluate_calibration_rows(
        rows,
        artifact=artifact,
        rubric={"thresholdSnapshot": _snapshot(artifact)},
    )

    assert report["watermarkDecisionClasses"] == {
        "overlay_watermark": 1,
        "source_consistent_clothing_text": 1,
    }
    assert report["watermarkEvidenceClassCounts"] == {
        "overlay_watermark": 1,
        "source_consistent_clothing_text": 1,
    }
    assert report["watermarkQaActions"] == {"allow": 1, "reject": 1}
    assert report["watermarkPolicyVersions"] == [
        "watermark_policy_v3_generated_artifact_only_v1"
    ]


def test_missing_required_signal_is_never_a_hard_pass():
    artifact = _artifact()
    rows = _run_rows()
    rows[0]["candidates"][0] = _candidate(1, "hard_pass", missing_signal=True)

    report = evaluate_calibration_rows(
        rows,
        artifact=artifact,
        rubric={"thresholdSnapshot": _snapshot(artifact)},
    )

    assert report["counts"]["hardPass"] == 4
    assert report["counts"]["needsReview"] == 6
    assert "required_signal_unavailable" in report["failureReasons"]


def test_required_signal_failures_are_reported_with_typed_reasons():
    artifact = _artifact()
    rows = _run_rows()
    candidate = _candidate(1, "needs_review")
    candidate["qa"]["modelAvailability"]["clipSafety"] = "unavailable"
    candidate["qa"]["modelAvailability"]["faceSimilarity"] = "uncalibrated"
    rows[0]["candidates"][0] = candidate

    report = evaluate_calibration_rows(
        rows,
        artifact=artifact,
        rubric={"thresholdSnapshot": _snapshot(artifact)},
    )

    assert report["requiredSignalFailureCounts"] == {
        "clip_safety_unavailable": 1,
        "face_similarity_uncalibrated": 1,
    }
    assert report["verdict"] == "BLOCKED_QA_SIGNAL"


def test_hard_reject_preview_is_counted_as_a_violation():
    artifact = _artifact()
    rows = _run_rows()
    rows[0]["candidates"][3]["qa"]["decision"]["previewAllowed"] = True

    report = evaluate_calibration_rows(
        rows,
        artifact=artifact,
        rubric={"thresholdSnapshot": _snapshot(artifact)},
    )

    assert report["previewViolations"] == 1
    assert report["g004Pass"] is False


def test_missing_rubric_is_human_review_required_and_four_participants_fail_closed():
    artifact = _artifact()
    rows = _run_rows(4)
    rows[0]["humanReview"] = _rubric()
    rows[1]["humanReview"] = {}
    report = evaluate_calibration_rows(
        rows,
        artifact=artifact,
        rubric={"thresholdSnapshot": _snapshot(artifact)},
    )

    assert report["participantCount"] == 4
    assert report["rubricComplete"] is False
    assert report["verdict"] == "BLOCKED_QA_CALIBRATION_DATA"
    assert "G004_CALIBRATION_INSUFFICIENT_COHORT" in report["failureReasons"]


def test_metrics_are_deterministic_and_threshold_snapshot_must_match():
    artifact = _artifact()
    rows = _run_rows()
    report = evaluate_calibration_rows(
        rows,
        artifact=artifact,
        rubric={"thresholdSnapshot": _snapshot(artifact)},
    )

    assert report["metrics"]["latencyMs"]["p50"] == 1002.5
    assert report["metrics"]["latencyMs"]["p95"] == 1004.0
    assert report["thresholdSnapshotMatch"] is True
    assert report["modelVersionMatch"] is True

    bad_snapshot = _snapshot(artifact)
    bad_snapshot["calibrationVersion"] = "wrong"
    mismatch = evaluate_calibration_rows(
        rows,
        artifact=artifact,
        rubric={"thresholdSnapshot": bad_snapshot},
    )
    assert mismatch["thresholdSnapshotMatch"] is False
    assert "threshold_snapshot_mismatch" in mismatch["failureReasons"]


def test_machine_verifiable_g004_pass_requires_human_signoff_after_all_gates():
    artifact = _artifact()
    report = evaluate_calibration_rows(
        _run_rows(),
        artifact=artifact,
        rubric={
            "thresholdSnapshot": _snapshot(artifact),
            "currentQAWiring": True,
            "singleRun": True,
            "outageProbe": {
                "tested": True,
                "decision": "needs_review",
                "previewAllowed": False,
            },
            "privacyScan": {
                "passed": True,
                "leakCounters": {
                    "secretLeaks": 0,
                    "privateUrlLeaks": 0,
                    "rawBiometricPersistence": 0,
                },
            },
            "humanSignoff": {"approved": True},
        },
    )

    assert report["machinePass"] is True
    assert report["humanSignoff"] is True
    assert report["verdict"] == "PASS_G004_CALIBRATION"
    assert report["g004Pass"] is True


def test_freeze_threshold_snapshot_uses_only_pre_live_evidence_and_is_immutable():
    evidence = [
        {
            "phase": "pre_live",
            "faceSimilarity": {"score": 0.20, "label": "safe"},
            "clipSafety": {
                "childlike": {"score": 0.10, "label": "safe"},
                "sexualized": {"score": 0.10, "label": "safe"},
                "beautification": {"score": 0.10, "label": "safe"},
                "brand_mismatch": {"score": 0.10, "label": "safe"},
                "severe_artifact": {"score": 0.10, "label": "safe"},
                "adult_like": {"score": 0.90, "label": "safe"},
                "brand_fit": {"score": 0.90, "label": "safe"},
            },
        },
        {
            "phase": "pre_live",
            "faceSimilarity": {"score": 0.80, "label": "risk"},
            "clipSafety": {
                "childlike": {"score": 0.80, "label": "risk"},
                "sexualized": {"score": 0.80, "label": "risk"},
                "beautification": {"score": 0.80, "label": "risk"},
                "brand_mismatch": {"score": 0.80, "label": "risk"},
                "severe_artifact": {"score": 0.80, "label": "risk"},
                "adult_like": {"score": 0.30, "label": "unsafe"},
                "brand_fit": {"score": 0.30, "label": "unsafe"},
            },
        },
    ]
    artifact = freeze_threshold_snapshot(
        evidence,
        versions={
            "calibrationVersion": "g004-evidence-v1",
            "createdAt": "2026-08-23T00:00:00Z",
            "gitRevision": "revision",
            "qaContractVersion": "avatar-qa-v1",
            "modelVersions": {
                "faceSimilarity": "openai/clip-vit-base-patch32",
                "clipSafety": "openai/clip-vit-large-patch14",
            },
            "preprocessingVersions": {
                "reference": "avatar-reference-v1",
                "qa": "avatar-qa-preprocess-v1",
            },
        },
        cohort_policy_version="g004-5plus-v1",
    )

    assert artifact.face_similarity["semanticRole"] == "identity_privacy_upper_bound"
    assert artifact.face_similarity["threshold"] == 0.5
    assert len(artifact.payload["integrity"]["sha256"]) == 64

    with pytest.raises(CalibrationArtifactError, match="live"):
        freeze_threshold_snapshot(
            [{"phase": "live", "faceSimilarity": {"score": 0.2, "label": "safe"}}],
            versions={"calibrationVersion": "g004-live"},
            cohort_policy_version="g004-5plus-v1",
        )


def test_report_redaction_removes_identifiers_urls_paths_and_embeddings():
    report = {
        "participantOrdinal": "P01",
        "rawUid": "uid-secret",
        "sourcePath": "gs://private-bucket/users/uid-secret/source/photo.png",
        "signedUrl": "https://storage.example/private?X-Goog-Signature=secret",
        "embedding": [0.1, 0.2],
        "candidateHash": "a" * 64,
        "sha256": "b" * 64,
        "perceptualHash": "c" * 32,
        "imageDigest": "d" * 64,
        "humanReview": {"note": "see C:/private/source/photo.png uid-secret"},
        "safe": 1,
    }

    redacted = redact_calibration_report(report)
    serialized = json.dumps(redacted, ensure_ascii=False)

    assert "uid-secret" not in serialized
    assert "gs://" not in serialized
    assert "https://" not in serialized
    assert "embedding" not in serialized.lower()
    assert "hash" not in serialized.lower()
    assert "sha256" not in serialized.lower()
    assert "digest" not in serialized.lower()
    assert "safe" in redacted


def test_report_redaction_preserves_safe_source_image_use_consent_boolean():
    report = {
        "consent": {
            "exact": True,
            "sourceImageUse": True,
        },
        "sourceImagePath": "gs://private-bucket/users/private/source/photo.png",
    }

    redacted = redact_calibration_report(report)

    assert redacted["consent"]["sourceImageUse"] is True
    assert "sourceImagePath" not in redacted
