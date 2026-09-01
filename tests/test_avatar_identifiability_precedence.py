import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.qa import build_avatar_qa_from_signals  # noqa: E402


def _signals(**overrides):
    values = {
        "adultLike": True,
        "brandFit": True,
        "cropConsistent": True,
        "cropIsolationQuality": "pass",
        "logoTextWatermarkDetected": False,
        "textLogoWatermarkRisk": "low",
        "logoTextWatermarkRisk": "low",
        "uniqueMarkCopied": False,
        "backgroundLeakageRisk": "low",
        "secondaryFaceLeakageRisk": "low",
        "childlikeScore": 0.05,
        "beautificationScore": 0.05,
        "localSafetyRiskAvailability": "available",
    }
    values.update(overrides)
    return values


def test_calibrated_low_similarity_maps_to_low_identifiability():
    result = build_avatar_qa_from_signals(
        _signals(
            faceSimilarityReliable=True,
            faceSimilarityScore=0.56,
            faceSimilarityDecision="low_similarity_risk",
            faceSimilarityCalibrationState="calibrated",
        )
    )

    assert result.identifiabilityRisk == "low"
    assert result.privacyQa == "pass"


def test_calibrated_review_similarity_remains_medium_without_score_fail_open():
    result = build_avatar_qa_from_signals(
        _signals(
            faceSimilarityReliable=False,
            faceSimilarityObservedScore=0.69,
            faceSimilarityDecision="review_similarity",
            faceSimilarityCalibrationState="calibrated_review_band",
        )
    )

    assert result.identifiabilityRisk == "medium"
    assert result.privacyQa == "needs_review"
    assert result.debug["scores"]["faceSimilarityObservedScore"] == 0.69
    assert result.debug["scores"]["faceSimilarityDecision"] == "review_similarity"


def test_calibrated_high_similarity_remains_high_and_rejected():
    result = build_avatar_qa_from_signals(
        _signals(
            faceSimilarityReliable=True,
            faceSimilarityScore=0.85,
            faceSimilarityDecision="high_similarity_risk",
            faceSimilarityCalibrationState="calibrated",
        )
    )

    assert result.identifiabilityRisk == "high"
    assert result.privacyQa == "fail"
    assert "too_identifiable" in result.rejectReasons


def test_generic_score_thresholds_remain_fallback_without_calibrated_state():
    result = build_avatar_qa_from_signals(
        _signals(
            faceSimilarityReliable=True,
            faceSimilarityScore=0.60,
        )
    )

    assert result.identifiabilityRisk == "medium"
    assert result.privacyQa == "needs_review"


def test_missing_face_similarity_remains_fail_closed():
    result = build_avatar_qa_from_signals(
        _signals(
            faceSimilarityReliable=False,
        )
    )

    assert result.identifiabilityRisk == "medium"
    assert result.privacyQa == "needs_review"


def test_calibrated_decision_precedes_generic_face_review_threshold():
    result = build_avatar_qa_from_signals(
        _signals(
            faceSimilarityReliable=True,
            faceSimilarityScore=0.60,
            faceSimilarityDecision="low_similarity_risk",
            faceSimilarityCalibrationState="calibrated",
        )
    )

    assert result.identifiabilityRisk == "low"
    assert result.debug["thresholdSnapshot"]["faceSimilarityReview"] == 0.50
    assert result.debug["thresholdSnapshot"]["faceSimilarityReject"] == 0.65
