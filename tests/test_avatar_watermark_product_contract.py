import sys
from pathlib import Path

import pytest
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.visual_risk import VisualRiskRegion  # noqa: E402
from avatar_generation.analysis.watermark import evaluate_watermark_risk  # noqa: E402
from avatar_generation.qa import build_avatar_qa_from_signals, run_avatar_candidate_qa  # noqa: E402


def _region(kind, bbox, *, confidence, label):
    return VisualRiskRegion(
        kind=kind,
        bbox_xyxy=bbox,
        confidence=confidence,
        raw_label=label,
    )


def _safe_signals(**overrides):
    signals = {
        "adultLike": True,
        "brandFit": True,
        "cropConsistent": True,
        "cropIsolationQuality": "pass",
        "backgroundLeakageRisk": "low",
        "secondaryFaceLeakageRisk": "low",
        "uniqueMarkCopied": False,
        "faceSimilarityReliable": True,
        "faceSimilarityScore": 0.10,
        "childlikeScore": 0.05,
        "beautificationScore": 0.05,
        "localSafetyRiskAvailability": "available",
        "watermarkDecisionClass": "no_text_detected",
        "watermarkEvidenceClasses": ["no_text_detected"],
        "watermarkEvidence": {"ocrDetectionCount": 0},
        "textLogoWatermarkRisk": "low",
        "logoTextWatermarkRisk": "low",
    }
    signals.update(overrides)
    return signals


def _image(color):
    image = Image.new("RGB", (96, 96), color)
    pixels = image.load()
    for x in range(0, 96, 8):
        for y in range(96):
            pixels[x, y] = ((color[0] + x + y) % 255, (color[1] + x) % 255, (color[2] + y) % 255)
    return image


@pytest.mark.parametrize("kind", ["logo", "sign"])
def test_source_consistent_text_like_mark_is_allowed(kind):
    source = _region(kind, (60, 120, 140, 145), confidence=0.96, label="CAMPUS")
    candidate = _region(kind, (61, 121, 141, 146), confidence=0.96, label="CAMPUS")

    decision = evaluate_watermark_risk(
        [candidate],
        source_regions=[source],
        image_size=(200, 200),
    )

    assert decision.watermark_qa_action == "allow"
    assert decision.hard_reject is False
    assert decision.needs_review is False
    assert decision.evidence["sourceConsistency"] == "consistent"


def test_source_consistent_corner_mark_is_allowed_without_generated_repetition():
    source = _region("text", (8, 8, 36, 22), confidence=0.98, label="WATERMARK")
    candidate = _region("text", (8, 8, 36, 22), confidence=0.98, label="WATERMARK")

    decision = evaluate_watermark_risk(
        [candidate],
        source_regions=[source],
        image_size=(200, 200),
    )

    assert decision.watermark_qa_action == "allow"
    assert decision.hard_reject is False
    assert decision.needs_review is False


def test_candidate_only_integrated_logo_is_allowed_without_artifact_corroboration():
    decision = evaluate_watermark_risk(
        [_region("logo", (60, 120, 140, 145), confidence=0.98, label="BRAND")],
        image_size=(200, 200),
    )

    assert decision.watermark_qa_action == "allow"
    assert decision.hard_reject is False
    assert decision.needs_review is False


def test_ambiguous_text_evidence_is_diagnostic_and_non_blocking():
    decision = evaluate_watermark_risk(
        [_region("text", (70, 92, 130, 108), confidence=None, label="ORDINARY")],
        image_size=(200, 200),
    )

    assert decision.decision_class == "ambiguous_text_evidence"
    assert decision.watermark_qa_action == "allow"
    assert decision.hard_reject is False
    assert decision.needs_review is False
    assert decision.to_document()["watermarkQaAction"] == "allow"


def test_short_ordinary_text_is_not_treated_as_a_generated_artifact():
    decision = evaluate_watermark_risk(
        [_region("text", (70, 92, 130, 108), confidence=0.96, label="OK")],
        image_size=(200, 200),
    )

    assert decision.watermark_qa_action == "allow"
    assert decision.hard_reject is False
    assert decision.needs_review is False


def test_generated_broken_text_requires_review_without_clear_overlay():
    decision = evaluate_watermark_risk(
        [_region("text", (60, 120, 140, 145), confidence=0.96, label="A B")],
        image_size=(200, 200),
    )

    assert decision.decision_class == "generated_text_artifact"
    assert decision.watermark_qa_action == "review"
    assert decision.hard_reject is False
    assert decision.needs_review is True


def test_broken_text_with_overlay_corroboration_is_rejected():
    decision = evaluate_watermark_risk(
        [_region("text", (8, 8, 36, 22), confidence=0.96, label="A B")],
        image_size=(200, 200),
    )

    assert decision.watermark_qa_action == "reject"
    assert decision.hard_reject is True
    assert decision.needs_review is False


def test_clear_watermark_token_in_overlay_is_rejected():
    decision = evaluate_watermark_risk(
        [_region("text", (8, 8, 36, 22), confidence=0.98, label="WATERMARK")],
        image_size=(200, 200),
    )

    assert decision.decision_class == "overlay_watermark"
    assert decision.watermark_qa_action == "reject"
    assert decision.hard_reject is True


def test_repeated_overlay_mark_is_rejected():
    decision = evaluate_watermark_risk(
        [
            _region("logo", (8, 8, 36, 22), confidence=0.96, label="BRAND"),
            _region("logo", (164, 8, 192, 22), confidence=0.95, label="BRAND"),
        ],
        image_size=(200, 200),
    )

    assert decision.decision_class == "generated_overlay_logo"
    assert decision.watermark_qa_action == "reject"
    assert decision.hard_reject is True


def test_corner_or_edge_logo_alone_is_not_a_watermark_reject():
    decision = evaluate_watermark_risk(
        [_region("logo", (8, 8, 36, 22), confidence=0.98, label="BRAND")],
        image_size=(200, 200),
    )

    assert decision.watermark_qa_action == "allow"
    assert decision.hard_reject is False
    assert decision.needs_review is False


def test_explicit_watermark_action_is_single_source_for_risk_and_hard_pass():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            watermarkDecisionClass="ambiguous_text_evidence",
            watermarkEvidenceClasses=["ambiguous_text_evidence"],
            watermarkQaAction="allow",
            textLogoWatermarkRisk="medium",
            logoTextWatermarkRisk="high",
            visualRiskStatus="needs_review",
        )
    )

    assert result.watermarkQaAction == "allow"
    assert result.logoTextWatermarkRisk == "low"
    assert result.textLogoWatermarkRisk == "low"
    assert result.debug["watermarkDecisionClass"] == "ambiguous_text_evidence"
    assert result.debug["watermarkQaAction"] == "allow"
    assert result.debug["watermarkPolicyVersion"] == "watermark_policy_v4_runtime_evidence_parity_v1"
    assert result.previewAllowed is True
    assert result.requiresHumanReview is False


def test_generated_text_review_action_blocks_preview_without_hard_reject():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            watermarkDecisionClass="generated_text_artifact",
            watermarkEvidenceClasses=["generated_text_artifact"],
            watermarkQaAction="review",
            textLogoWatermarkRisk="low",
            logoTextWatermarkRisk="low",
        )
    )

    assert result.watermarkQaAction == "review"
    assert result.logoTextWatermarkRisk == "medium"
    assert result.textLogoWatermarkRisk == "medium"
    assert result.rejectReasons == []
    assert result.previewAllowed is False
    assert result.requiresHumanReview is True


def test_raw_logo_presence_boolean_does_not_create_watermark_reject():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            logoTextWatermarkDetected=True,
            textLogoWatermarkDetected=True,
        )
    )

    assert result.watermarkQaAction == "allow"
    assert "logo_text_watermark" not in result.rejectReasons
    assert result.previewAllowed is True


def test_visual_model_outage_is_fail_closed_review():
    result = build_avatar_qa_from_signals(
        _safe_signals(
            watermarkQaAction=None,
            visualRiskStatus="unavailable",
            visualRiskProviderAvailable=False,
            textLogoWatermarkRisk="low",
            logoTextWatermarkRisk="low",
        )
    )

    assert result.watermarkQaAction == "review"
    assert result.logoTextWatermarkRisk == "medium"
    assert result.previewAllowed is False
    assert result.requiresHumanReview is True


def test_legacy_text_marker_is_not_a_standalone_reject():
    result = run_avatar_candidate_qa(
        "",
        "",
        {
            "_source_image": _image((10, 90, 120)),
            "_candidate_image": _image((140, 130, 100)),
            "qaSignals": _safe_signals(),
            "brandLogoDetected": True,
        },
    )

    assert result.watermarkQaAction == "allow"
    assert "logo_text_watermark" not in result.rejectReasons
