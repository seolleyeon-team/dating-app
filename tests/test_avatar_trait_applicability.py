import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.preview_policy import is_preview_eligible  # noqa: E402
from avatar_generation.qa import build_avatar_qa_from_signals  # noqa: E402
from avatar_generation.trait_policy import (  # noqa: E402
    TRAIT_QA_ACTION_ALLOW,
    TRAIT_QA_ACTION_REVIEW,
    TRAIT_QA_APPLICABILITY_AVAILABLE,
    TRAIT_QA_APPLICABILITY_NOT_APPLICABLE,
    TRAIT_QA_APPLICABILITY_UNAVAILABLE,
    resolve_trait_qa_state,
)


AZURE_CANONICAL = {
    "provider": "azure",
    "generationBackend": "azure_gpt_image_2",
    "modelFamily": "gpt-image-2",
    "sourceInputMode": "storage_normalized_original_direct",
    "uploadNormalization": "existing_avatar_media_ingestion",
    "preGenerationTransform": "none",
    "pipelineMode": "azure_gpt_image_2",
    "legacyTraitExtraction": False,
    "legacyReferencePreprocessing": False,
    "legacyFlux": False,
    "traitQaMode": "disabled_by_pipeline",
    "traitQaAuthority": "server",
}

TRAIT_ENABLED = {
    "pipelineMode": "flux",
    "traitQaMode": "enabled",
    "traitQaAuthority": "server",
}


def _traits(**overrides):
    values = {
        "hair_color_range": "black",
        "hair_color_range_confidence": 0.96,
        "eyewear_present": False,
        "eyewear_present_confidence": 0.97,
        "facial_hair_present": False,
        "facial_hair_present_confidence": 0.98,
        "clothing_category": "hoodie",
        "clothing_category_confidence": 0.94,
        "clothing_color": "navy",
        "clothing_color_confidence": 0.95,
    }
    values.update(overrides)
    return values


def _safe_signals(**overrides):
    values = {
        "adultLike": True,
        "brandFit": True,
        "cropConsistent": True,
        "cropIsolationQuality": "pass",
        "childlikeScore": 0.05,
        "beautificationScore": 0.05,
        "faceSimilarityReliable": True,
        "faceSimilarityScore": 0.12,
        "faceSimilarityDecision": "low_similarity_risk",
        "faceSimilarityCalibrationState": "calibrated",
        "localSafetyRiskAvailability": "available",
        "backgroundLeakageRisk": "low",
        "secondaryFaceLeakageRisk": "low",
        "uniqueMarkCopied": False,
        "watermarkQaAction": "allow",
        "watermarkDecisionClass": "ambiguous_text_evidence",
        "watermarkEvidenceClasses": ["ambiguous_text_evidence"],
        "traitQaApplicability": "not_applicable",
        "traitQaAction": "allow",
        "traitQaReason": "disabled_by_canonical_azure_pipeline",
        "traitReviewContribution": False,
    }
    values.update(overrides)
    return values


def _qa_document(**overrides):
    document = build_avatar_qa_from_signals(_safe_signals(**overrides)).to_document()
    document["debug"]["modelAvailability"].update(
        {
            "faceDetector": "available",
            "visualRisk": "available",
            "mediapipe": "available",
        }
    )
    return document


def test_canonical_azure_missing_traits_is_not_applicable_and_allow():
    result = resolve_trait_qa_state(AZURE_CANONICAL, {}, {}, {})

    assert result.applicability == TRAIT_QA_APPLICABILITY_NOT_APPLICABLE
    assert result.action == TRAIT_QA_ACTION_ALLOW
    assert result.needs_review is False
    assert result.to_document()["traitQaApplicability"] == "not_applicable"


def test_canonical_azure_does_not_fabricate_trait_pass_fields():
    result = resolve_trait_qa_state(AZURE_CANONICAL, {}, {}, {})
    document = result.to_document()

    assert "sourceTraitCard" not in document
    assert "candidateTraitCard" not in document
    assert "confidence" not in document
    assert "matchingResult" not in document


def test_trait_enabled_complete_matching_evidence_allows():
    comparison = {
        "hair_color_range": "match",
        "eyewear_present": "match",
        "eyewear_style": "match",
        "facial_hair_present": "match",
        "facial_hair_style": "match",
        "clothing_category": "match",
        "clothing_color": "match",
    }
    result = resolve_trait_qa_state(TRAIT_ENABLED, _traits(), _traits(), comparison)

    assert result.applicability == TRAIT_QA_APPLICABILITY_AVAILABLE
    assert result.action == TRAIT_QA_ACTION_ALLOW
    assert result.needs_review is False


def test_nested_trait_card_with_false_boolean_is_still_evidence():
    nested = {
        "traitExtractionAvailability": "available",
        "traitCard": {
            "eyewear": {"present": False, "confidence": "high"},
            "hair_color_range": "black",
        },
    }
    result = resolve_trait_qa_state(
        TRAIT_ENABLED,
        nested,
        nested,
        {"eyewear_present": "match", "hair_color_range": "match"},
    )

    assert result.applicability == TRAIT_QA_APPLICABILITY_AVAILABLE
    assert result.action == TRAIT_QA_ACTION_ALLOW


def test_trait_enabled_meaningful_mismatch_reviews_without_hard_reject():
    comparison = {"hair_color_range": "mismatch", "clothing_color": "match"}
    result = resolve_trait_qa_state(TRAIT_ENABLED, _traits(), _traits(), comparison)

    assert result.applicability == TRAIT_QA_APPLICABILITY_AVAILABLE
    assert result.action == TRAIT_QA_ACTION_REVIEW
    assert result.needs_review is True
    assert result.hard_reject is False


@pytest.mark.parametrize(
    "source,candidate,reason",
    [
        ({}, _traits(), "source_trait_evidence_missing"),
        (_traits(), {}, "candidate_trait_evidence_missing"),
        ({}, {}, "source_and_candidate_trait_evidence_missing"),
    ],
)
def test_trait_enabled_missing_evidence_is_unavailable_review(source, candidate, reason):
    result = resolve_trait_qa_state(TRAIT_ENABLED, source, candidate, {})

    assert result.applicability == TRAIT_QA_APPLICABILITY_UNAVAILABLE
    assert result.action == TRAIT_QA_ACTION_REVIEW
    assert result.reason == reason
    assert result.needs_review is True
    assert result.hard_reject is False


def test_unknown_pipeline_provenance_fails_closed():
    result = resolve_trait_qa_state({}, {}, {}, {})

    assert result.applicability == TRAIT_QA_APPLICABILITY_UNAVAILABLE
    assert result.action == TRAIT_QA_ACTION_REVIEW
    assert result.needs_review is True


def test_client_cannot_declare_not_applicable_on_trait_enabled_pipeline():
    client_claim = {
        **TRAIT_ENABLED,
        "traitQaApplicability": "not_applicable",
        "traitQaAction": "allow",
    }
    result = resolve_trait_qa_state(client_claim, {}, {}, {})

    assert result.applicability == TRAIT_QA_APPLICABILITY_UNAVAILABLE
    assert result.action == TRAIT_QA_ACTION_REVIEW


def test_client_cannot_forge_canonical_azure_na_without_server_authority():
    forged = {
        key: value
        for key, value in AZURE_CANONICAL.items()
        if key not in {"traitQaAuthority", "traitQaMode"}
    }
    forged["traitQaApplicability"] = "not_applicable"
    forged["traitQaAction"] = "allow"

    result = resolve_trait_qa_state(forged, {}, {}, {})

    assert result.applicability == TRAIT_QA_APPLICABILITY_UNAVAILABLE
    assert result.action == TRAIT_QA_ACTION_REVIEW


def test_n_a_trait_state_is_hard_pass_compatible_without_fake_pass_fields():
    result = build_avatar_qa_from_signals(_safe_signals())

    assert result.traitQaApplicability == "not_applicable"
    assert result.traitQaAction == "allow"
    assert result.previewAllowed is True
    assert result.requiresHumanReview is False
    assert "trait" not in json.dumps(result.reviewReasons).lower()


def test_unavailable_trait_state_blocks_hard_pass():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            traitQaApplicability="unavailable",
            traitQaAction="review",
            traitQaReason="candidate_trait_evidence_missing",
            traitReviewContribution=True,
        )
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert result.traitQaAction == "review"
    assert "trait" in " ".join(result.reviewReasons).lower()


def test_available_trait_mismatch_blocks_hard_pass_without_hard_reject():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            traitQaApplicability="available",
            traitQaAction="review",
            traitQaReason="trait_comparison_mismatch",
            traitReviewContribution=True,
        )
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert result.rejectReasons == []


def test_legacy_hard_trait_diagnostic_cannot_create_hard_reject():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            traitQaApplicability="available",
            traitQaAction="review",
            traitQaReason="trait_comparison_mismatch",
            traitReviewContribution=True,
            hardTraitContradiction=True,
        )
    )

    assert result.rejectReasons == []
    assert result.requiresHumanReview is True


def test_preview_policy_accepts_n_a_and_denies_unavailable():
    allowed = {"status": "preview_ready", "qa": _qa_document()}
    denied = {
        "status": "needs_review",
        "qa": _qa_document(
            traitQaApplicability="unavailable",
            traitQaAction="review",
            traitQaReason="pipeline_applicability_unknown",
            traitReviewContribution=True,
        ),
    }

    assert is_preview_eligible(allowed) is True
    assert is_preview_eligible(denied) is False


def test_n_a_does_not_reintroduce_generic_trait_review():
    result = build_avatar_qa_from_signals(_safe_signals())

    assert result.reviewReasons == []
    assert result.traitReviewContribution is False


def test_other_review_reason_is_preserved_with_n_a_trait_state():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            faceSimilarityReliable=False,
            faceSimilarityScore=0.58,
            faceSimilarityDecision="review_similarity",
            faceSimilarityCalibrationState="calibrated_review_band",
            faceSimilarityNeedsReview=True,
        )
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert result.traitReviewContribution is False
    assert "trait" not in " ".join(result.reviewReasons).lower()


def test_watermark_background_and_identifiability_corrections_remain_active():
    allow = build_avatar_qa_from_signals(_safe_signals())
    review_identity = build_avatar_qa_from_signals(
        _safe_signals(
            faceSimilarityReliable=False,
            faceSimilarityScore=0.58,
            faceSimilarityDecision="review_similarity",
            faceSimilarityCalibrationState="calibrated_review_band",
            faceSimilarityNeedsReview=True,
        )
    )

    assert allow.textLogoWatermarkRisk == "low"
    assert allow.backgroundLeakageRisk == "low"
    assert allow.identifiabilityRisk == "low"
    assert review_identity.identifiabilityRisk == "medium"


def test_canonical_azure_worker_provenance_declares_trait_policy_without_extraction():
    import avatar_generation.worker as worker

    assert worker._trait_extraction_enabled(worker.CANONICAL_AZURE_WORKER_MODE) is False
    assert worker._candidate_trait_qa_enabled(worker.CANONICAL_AZURE_WORKER_MODE) is False
    provenance = worker._azure_provenance_document()

    assert provenance["traitQaMode"] == "disabled_by_pipeline"
    assert provenance["traitQaAuthority"] == "server"
    assert provenance["pipelineMode"] == worker.CANONICAL_AZURE_WORKER_MODE


def test_trait_policy_version_is_persisted_and_privacy_safe():
    document = _qa_document()

    assert document["traitPolicyVersion"] == "trait_policy_v2_applicability_v1"
    serialized = json.dumps(document, sort_keys=True).lower()
    for forbidden in ("uid", "email", "bbox", "coordinate", "embedding", "ocr"):
        assert forbidden not in serialized


def test_trait_enabled_unknown_value_remains_review():
    result = resolve_trait_qa_state(
        TRAIT_ENABLED,
        _traits(hair_color_range="unknown"),
        _traits(hair_color_range="black"),
        {"hair_color_range": "review"},
    )

    assert result.applicability == "available"
    assert result.action == "review"
    assert result.needs_review is True
