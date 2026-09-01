import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.preview_policy import (  # noqa: E402
    is_preview_eligible,
    passes_absolute_preview_checks,
)
from avatar_generation.qa import (  # noqa: E402
    AvatarQAResult,
    apply_avatar_qa_rejection_logic,
    build_avatar_qa_from_signals,
)
from avatar_generation.worker import (  # noqa: E402
    _azure_provenance_document,
    _candidate_status_from_qa,
)
from scripts.avatar_g004_trait_applicability_offline import (  # noqa: E402
    recompute_candidate_qa,
)


def _safe_qa_result(*, unique_mark_risk: str) -> AvatarQAResult:
    return AvatarQAResult(
        adultQa="pass",
        childlikeRisk="low",
        privacyQa="pass",
        brandQa="pass",
        beautificationRisk="low",
        cropConsistency="pass",
        cropIsolationQuality="pass",
        uniqueMarkCopyRisk=unique_mark_risk,
        logoTextWatermarkRisk="low",
        textLogoWatermarkRisk="low",
        watermarkQaAction="allow",
        backgroundLeakageRisk="low",
        secondaryFaceLeakageRisk="low",
        identifiabilityRisk="low",
        traitQaApplicability="not_applicable",
        traitQaAction="allow",
        traitQaReason="disabled_by_canonical_azure_pipeline",
        traitReviewContribution=False,
        rejectReasons=[],
        reviewReasons=[],
        softPass=False,
        previewAllowed=False,
        requiresHumanReview=True,
    )


@pytest.mark.parametrize(
    ("risk", "expected_preview", "expected_status", "expected_reject"),
    (
        ("low", True, "hard_pass", False),
        ("unknown", False, "needs_review", False),
        ("unavailable", False, "needs_review", False),
        ("high", False, "rejected", True),
    ),
)
def test_effective_production_gate_preserves_qa_preview_split(
    risk,
    expected_preview,
    expected_status,
    expected_reject,
):
    result = apply_avatar_qa_rejection_logic(_safe_qa_result(unique_mark_risk=risk))
    qa_document = result.to_document()
    candidate = {"status": "hard_pass", "qa": qa_document}

    assert result.previewAllowed is (risk == "low")
    assert result.requiresHumanReview is (risk in {"unknown", "unavailable"})
    assert bool(result.rejectReasons) is expected_reject
    if risk == "high":
        assert result.rejectReasons == ["unique_mark_copied"]
    else:
        assert result.rejectReasons == []
    assert passes_absolute_preview_checks(candidate) is expected_preview
    assert is_preview_eligible(candidate) is expected_preview
    assert _candidate_status_from_qa(qa_document) == expected_status


def _safe_signal_values():
    return {
        "adultLike": True,
        "brandFit": True,
        "cropConsistent": True,
        "cropIsolationQuality": "pass",
        "childlikeScore": 0.0,
        "beautificationScore": 0.0,
        "faceSimilarityReliable": True,
        "faceSimilarityScore": 0.0,
        "faceSimilarityDecision": "low_similarity_risk",
        "faceSimilarityCalibrationState": "calibrated",
        "faceSimilarityObservedScore": 0.0,
        "localSafetyRiskAvailability": "available",
        "logoTextWatermarkDetected": False,
        "backgroundLeakageRisk": "low",
        "secondaryFaceLeakageRisk": "low",
        "traitQaApplicability": "not_applicable",
        "traitQaAction": "allow",
        "traitQaReason": "disabled_by_canonical_azure_pipeline",
        "traitReviewContribution": False,
    }


@pytest.mark.parametrize(
    ("label", "value", "expected_risk"),
    (
        ("false", False, "low"),
        ("none", None, "unknown"),
        ("absent", "__absent__", "unknown"),
        ("true", True, "high"),
    ),
)
def test_unique_mark_producer_mapping_is_explicit_and_privacy_safe(
    label,
    value,
    expected_risk,
):
    signals = _safe_signal_values()
    if value != "__absent__":
        signals["uniqueMarkCopied"] = value

    result = build_avatar_qa_from_signals(signals)

    assert result.uniqueMarkCopyRisk == expected_risk, label
    assert ("unique_mark_copied" in result.rejectReasons) is (expected_risk == "high")


def _offline_snapshot(unique_mark_risk):
    return {
        "participantOrdinal": "P01",
        "candidateOrdinal": 1,
        "qa": {
            "adultQa": "pass",
            "childlikeRisk": "low",
            "privacyQa": "pass",
            "brandQa": "pass",
            "beautificationRisk": "low",
            "cropConsistency": "pass",
            "cropIsolationQuality": "pass",
            "uniqueMarkCopyRisk": unique_mark_risk,
            "logoTextWatermarkRisk": "low",
            "textLogoWatermarkRisk": "low",
            "watermarkQaAction": "allow",
            "backgroundLeakageRisk": "low",
            "secondaryFaceLeakageRisk": "low",
            "identifiabilityRisk": "low",
            "debug": {
                "modelAvailability": {
                    "faceDetector": "available",
                    "visualRisk": "available",
                    "clipSafety": "available",
                    "localSafetyRisk": "available",
                    "faceSimilarity": "available",
                    "mediapipe": "available",
                    "dino": "unavailable",
                },
                "scores": {
                    "faceSimilarityObservedScore": 0.1,
                    "faceSimilarityDecision": "low_similarity_risk",
                },
            },
        },
    }


@pytest.mark.parametrize(
    ("risk", "expected_hard_pass", "expected_hard_reject", "expected_reason"),
    (
        ("low", True, False, None),
        ("unknown", True, False, None),
        ("unavailable", True, False, None),
        ("high", False, True, None),
    ),
)
def test_offline_blocker_accounting_matches_effective_production_gate(
    risk,
    expected_hard_pass,
    expected_hard_reject,
    expected_reason,
):
    row = recompute_candidate_qa(
        _offline_snapshot(risk),
        source_contract=_azure_provenance_document(),
        corrected_stack_context={"backgroundLeakageRisk": {"after": {"low": 1}}},
        provenance_verified=True,
    )

    assert row["hardPass"] is expected_hard_pass
    assert row["hardReject"] is expected_hard_reject
    if expected_reason is None:
        assert row["typedReviewReasons"] == []
        if risk == "high":
            assert row["hardRejectReasons"] == ["unique_mark_copied"]
    else:
        assert expected_reason in row["typedReviewReasons"]
