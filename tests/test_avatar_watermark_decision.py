import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.visual_risk import (  # noqa: E402
    VisualRiskAnalysis,
    VisualRiskRegion,
)
from avatar_generation.analysis.watermark import (  # noqa: E402
    evaluate_watermark_risk,
)


def _region(kind, bbox, *, confidence, label):
    return VisualRiskRegion(
        kind=kind,
        bbox_xyxy=bbox,
        confidence=confidence,
        raw_label=label,
    )


def test_source_consistent_central_clothing_text_is_not_a_watermark_reject():
    source = _region("text", (60, 120, 140, 145), confidence=0.96, label="CAMPUS")
    candidate = _region("text", (61, 121, 141, 146), confidence=0.96, label="CAMPUS")

    decision = evaluate_watermark_risk(
        [candidate],
        source_regions=[source],
        image_size=(200, 200),
    )

    assert decision.hard_reject is False
    assert decision.needs_review is False
    assert decision.decision_class == "source_consistent_clothing_text"
    assert decision.evidence["sourceConsistency"] == "consistent"


def test_source_consistency_uses_source_image_dimensions_when_sizes_differ():
    source = _region("text", (120, 240, 280, 290), confidence=0.96, label="CAMPUS")
    candidate = _region("text", (60, 120, 140, 145), confidence=0.96, label="CAMPUS")

    decision = evaluate_watermark_risk(
        [candidate],
        source_regions=[source],
        image_size=(200, 200),
        source_image_size=(400, 400),
    )

    assert decision.decision_class == "source_consistent_clothing_text"
    assert decision.needs_review is False


def test_single_ambiguous_text_detection_is_non_blocking_without_hard_reject():
    candidate = _region("text", (70, 92, 130, 108), confidence=0.58, label="ORDINARY")

    decision = evaluate_watermark_risk(
        [candidate],
        image_size=(200, 200),
    )

    assert decision.hard_reject is False
    assert decision.needs_review is False
    assert decision.decision_class == "ambiguous_text_evidence"
    assert decision.watermark_qa_action == "allow"


def test_repeated_high_confidence_corner_logo_remains_hard_reject():
    candidates = [
        _region("logo", (8, 8, 36, 22), confidence=0.96, label="BRAND"),
        _region("logo", (164, 8, 192, 22), confidence=0.95, label="BRAND"),
    ]

    decision = evaluate_watermark_risk(candidates, image_size=(200, 200))

    assert decision.hard_reject is True
    assert decision.needs_review is False
    assert decision.decision_class == "generated_overlay_logo"
    assert "generated_overlay_logo" in decision.evidence_classes


def test_watermark_evidence_document_never_contains_raw_label_or_geometry():
    candidate = _region(
        "logo",
        (8, 8, 36, 22),
        confidence=0.96,
        label="PRIVATE SCHOOL 010-1234",
    )
    analysis = VisualRiskAnalysis(
        provider="fake-visual",
        provider_available=True,
        regions=(candidate,),
    )
    decision = evaluate_watermark_risk([candidate], image_size=(200, 200))

    serialized = repr(analysis.to_document()) + repr(decision.to_document())
    assert "PRIVATE" not in serialized
    assert "010" not in serialized
    assert "36" not in serialized
    assert "22" not in serialized
    assert decision.to_document()["evidence"]["ocrDetectionCount"] == 1
