import json
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
from avatar_generation.qa import build_avatar_qa_from_signals  # noqa: E402
from avatar_generation.worker import (  # noqa: E402
    _azure_provenance_document,
    _candidate_status_from_qa,
)
from scripts.avatar_g004_trait_applicability_offline import (  # noqa: E402
    recompute_candidate_qa,
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

UNIQUE_MARK_ENABLED = {
    "pipelineMode": "unique_mark_enabled",
    "uniqueMarkQaMode": "enabled",
    "uniqueMarkQaAuthority": "server",
}


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
        "watermarkQaAction": "allow",
        "traitQaApplicability": "not_applicable",
        "traitQaAction": "allow",
        "traitQaReason": "disabled_by_canonical_azure_pipeline",
        "traitReviewContribution": False,
    }
    values.update(overrides)
    return values


def _safe_qa_doc(**overrides):
    values = _safe_signals(**overrides)
    result = build_avatar_qa_from_signals(values)
    document = result.to_document()
    document["debug"]["modelAvailability"].update(
        {
            "faceDetector": "available",
            "visualRisk": "available",
            "clipSafety": "available",
            "faceSimilarity": "available",
            "mediapipe": "available",
        }
    )
    return document


def _canonical_snapshot():
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
            "uniqueMarkCopyRisk": "unknown",
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
                    "faceSimilarity": "available",
                    "localSafetyRisk": "available",
                    "dino": "unavailable",
                    "mediapipe": "available",
                },
                "scores": {
                    "faceSimilarityObservedScore": 0.1,
                    "faceSimilarityDecision": "low_similarity_risk",
                },
            },
        },
    }


def test_canonical_azure_absent_unique_mark_is_not_applicable_allow():
    result = build_avatar_qa_from_signals(
        _safe_signals(**AZURE_CANONICAL),
    )

    assert result.uniqueMarkQaApplicability == "not_applicable"
    assert result.uniqueMarkQaAction == "allow"
    assert result.uniqueMarkCopyRisk == "unknown"
    assert result.previewAllowed is True
    assert result.requiresHumanReview is False


def test_not_applicable_does_not_fabricate_low_or_false():
    result = build_avatar_qa_from_signals(_safe_signals(**AZURE_CANONICAL))
    document = result.to_document()

    assert result.uniqueMarkCopyRisk == "unknown"
    assert "uniqueMarkCopied" not in document
    assert document["uniqueMarkQaApplicability"] == "not_applicable"


def test_preview_accepts_canonical_not_applicable_with_unknown_risk():
    qa = _safe_qa_doc(**AZURE_CANONICAL)
    qa["uniqueMarkCopyRisk"] = "unknown"
    qa["uniqueMarkQaApplicability"] = "not_applicable"
    qa["uniqueMarkQaAction"] = "allow"
    qa["previewAllowed"] = True
    qa["requiresHumanReview"] = False
    candidate = {"status": "preview_ready", "qa": qa}

    assert passes_absolute_preview_checks(candidate) is True
    assert is_preview_eligible(candidate) is True


def test_not_applicable_does_not_bypass_high_risk_preview_guard():
    qa = _safe_qa_doc(**AZURE_CANONICAL)
    qa["uniqueMarkCopyRisk"] = "high"
    qa["uniqueMarkQaApplicability"] = "not_applicable"
    qa["uniqueMarkQaAction"] = "allow"
    qa["previewAllowed"] = True
    qa["requiresHumanReview"] = False
    candidate = {"status": "preview_ready", "qa": qa}

    assert passes_absolute_preview_checks(candidate) is False
    assert is_preview_eligible(candidate) is False


def test_worker_accepts_canonical_not_applicable_as_hard_pass():
    qa = _safe_qa_doc(**AZURE_CANONICAL)
    qa["uniqueMarkCopyRisk"] = "unknown"
    qa["uniqueMarkQaApplicability"] = "not_applicable"
    qa["uniqueMarkQaAction"] = "allow"
    qa["previewAllowed"] = True
    qa["requiresHumanReview"] = False

    assert _candidate_status_from_qa(qa) == "hard_pass"


def test_enabled_low_is_available_allow():
    result = build_avatar_qa_from_signals(
        _safe_signals(**UNIQUE_MARK_ENABLED, uniqueMarkCopied=False),
    )

    assert result.uniqueMarkQaApplicability == "available"
    assert result.uniqueMarkQaAction == "allow"
    assert result.uniqueMarkCopyRisk == "low"
    assert result.rejectReasons == []


def test_enabled_high_remains_available_reject():
    result = build_avatar_qa_from_signals(
        _safe_signals(**UNIQUE_MARK_ENABLED, uniqueMarkCopied=True),
    )

    assert result.uniqueMarkQaApplicability == "available"
    assert result.uniqueMarkQaAction == "reject"
    assert result.uniqueMarkCopyRisk == "high"
    assert result.rejectReasons == ["unique_mark_copied"]


def test_enabled_missing_evidence_is_unavailable_review():
    result = build_avatar_qa_from_signals(_safe_signals(**UNIQUE_MARK_ENABLED))

    assert result.uniqueMarkQaApplicability == "unavailable"
    assert result.uniqueMarkQaAction == "review"
    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert result.rejectReasons == []


def test_enabled_producer_failure_is_unavailable_review():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            **UNIQUE_MARK_ENABLED,
            uniqueMarkEvidenceAvailability="unavailable",
        ),
    )

    assert result.uniqueMarkQaApplicability == "unavailable"
    assert result.uniqueMarkQaAction == "review"
    assert result.previewAllowed is False
    assert result.requiresHumanReview is True


def test_enabled_uncertain_evidence_preserves_review_action():
    result = build_avatar_qa_from_signals(
        _safe_signals(**UNIQUE_MARK_ENABLED, uniqueMarkCopyRisk="medium"),
    )

    assert result.uniqueMarkQaApplicability == "available"
    assert result.uniqueMarkQaAction == "review"
    assert result.uniqueMarkCopyRisk == "medium"
    assert result.previewAllowed is False
    assert result.requiresHumanReview is True


def test_unknown_pipeline_fails_closed_even_with_client_na_claim():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            pipelineMode="mystery",
            uniqueMarkQaApplicability="not_applicable",
            uniqueMarkQaAction="allow",
        ),
    )

    assert result.uniqueMarkQaApplicability == "unavailable"
    assert result.uniqueMarkQaAction == "review"
    assert result.previewAllowed is False


def test_client_cannot_forge_canonical_na_without_server_authority():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            **{
                key: value
                for key, value in AZURE_CANONICAL.items()
                if key not in {"traitQaMode", "traitQaAuthority"}
            },
            uniqueMarkQaApplicability="not_applicable",
            uniqueMarkQaAction="allow",
        ),
    )

    assert result.uniqueMarkQaApplicability == "unavailable"
    assert result.uniqueMarkQaAction == "review"


def test_enabled_pipeline_ignores_client_not_applicable_claim():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            **UNIQUE_MARK_ENABLED,
            uniqueMarkQaApplicability="not_applicable",
            uniqueMarkQaAction="allow",
        ),
    )

    assert result.uniqueMarkQaApplicability == "unavailable"
    assert result.uniqueMarkQaAction == "review"
    assert result.previewAllowed is False


def test_canonical_offline_recompute_is_not_applicable_and_hard_pass():
    row = recompute_candidate_qa(
        _canonical_snapshot(),
        source_contract=_azure_provenance_document(),
        corrected_stack_context={"backgroundLeakageRisk": {"after": {"low": 1}}},
        provenance_verified=True,
    )

    assert row["uniqueMarkQaApplicability"] == "not_applicable"
    assert row["uniqueMarkQaAction"] == "allow"
    assert row["hardPass"] is True
    assert "unique_mark_evidence_unavailable" not in row["typedReviewReasons"]


def test_na_document_is_privacy_safe():
    qa = _safe_qa_doc(**AZURE_CANONICAL)
    serialized = json.dumps(qa, sort_keys=True).lower()
    for forbidden in (
        "mole",
        "scar",
        "tattoo",
        "bbox",
        "coordinate",
        "embedding",
        "landmark",
        "ocr",
        "uid",
        "email",
    ):
        assert forbidden not in serialized
