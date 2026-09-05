"""Independent re-verification of the source-quality selector contract.

Product contract (2026-09-05, section 10):
  hard gates, exact weights, bounded deterministic score, top1/top2 margin,
  versioned confidence, no biometric persistence, normalized original kept.

These tests do NOT tune thresholds. They pin the values the implementation
declares so a silent change fails loudly.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.avatar_source_quality import (  # noqa: E402
    CONFIDENCE_POLICY_VERSION,
    NO_ELIGIBLE_SOURCE_ERROR,
    SELECTOR_VERSION,
    AvatarSourceQualitySelector,
    SecondaryFaceSignal,
    SourceQualitySignals,
    SourceQualityThresholds,
    SourceQualityWeights,
)


def good(photo_id: str, order: int, **overrides: object) -> SourceQualitySignals:
    values: dict[str, object] = {
        "photo_id": photo_id,
        "stable_order": order,
        "image_width": 1200,
        "image_height": 1600,
        "primary_face_confidence": 0.96,
        "primary_bbox": (0.28, 0.18, 0.44, 0.42),
        "face_short_side_px": 520,
        "face_sharpness": 0.90,
        "yaw_degrees": 4.0,
        "pitch_degrees": 2.0,
        "roll_degrees": 1.0,
        "illumination_quality": 0.90,
        "face_luminance": 128.0,
        "dark_clip_ratio": 0.01,
        "highlight_clip_ratio": 0.01,
        "face_visibility": 0.95,
        "occlusion_score": 0.05,
        "landmarks_reliable": True,
        "corrupt": False,
        "secondary_faces": (),
        "glasses_present": False,
    }
    values.update(overrides)
    return SourceQualitySignals(**values)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Declared constants (pinned, not tuned)
# ---------------------------------------------------------------------------

def test_weights_are_exactly_the_declared_contract():
    weights = SourceQualityWeights()
    assert weights.face_sharpness == 0.25
    assert weights.useful_face_resolution == 0.20
    assert weights.pose_frontalness == 0.20
    assert weights.illumination_quality == 0.15
    assert weights.face_visibility == 0.10
    assert weights.framing_quality == 0.05
    assert weights.secondary_person_penalty == 0.05  # applied subtractively


def test_hard_gate_thresholds_are_the_declared_values():
    t = SourceQualityThresholds()
    assert t.min_primary_confidence == 0.45
    assert t.meaningful_secondary_min_confidence == 0.55
    assert t.meaningful_secondary_min_area_ratio == 0.025
    assert t.meaningful_secondary_relative_area == 0.35
    assert t.min_face_short_side_px == 64
    assert t.severe_crop_margin == 0.002
    assert t.min_face_sharpness == 0.12
    assert t.severe_underexposed_luminance == 30.0
    assert t.severe_overexposed_luminance == 235.0
    assert t.severe_clip_ratio == 0.60
    assert t.min_face_visibility == 0.25
    assert t.severe_occlusion == 0.75


def test_versions_are_pinned():
    assert SELECTOR_VERSION == "avatar_source_quality_selector_v1"
    assert CONFIDENCE_POLICY_VERSION == "avatar_source_selection_confidence_v1"
    assert NO_ELIGIBLE_SOURCE_ERROR == "avatar_no_eligible_source_photo"


# ---------------------------------------------------------------------------
# Hard gates: each one rejects on its own
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"corrupt": True}, "avatar_source_corrupt_image"),
        ({"primary_bbox": None, "primary_face_confidence": None}, "avatar_source_no_face"),
        ({"primary_face_confidence": 0.44}, "avatar_source_no_face"),
        (
            {"secondary_faces": (SecondaryFaceSignal(confidence=0.9, area_ratio=0.10),)},
            "avatar_source_multiple_primary_faces",
        ),
        ({"face_short_side_px": 63}, "avatar_source_face_too_small"),
        ({"primary_bbox": (0.0, 0.18, 0.44, 0.42)}, "avatar_source_face_out_of_frame"),
        ({"face_sharpness": 0.11}, "avatar_source_face_too_blurry"),
        ({"face_luminance": 30.0}, "avatar_source_underexposed"),
        ({"dark_clip_ratio": 0.60}, "avatar_source_underexposed"),
        ({"face_luminance": 235.0}, "avatar_source_overexposed"),
        ({"landmarks_reliable": False}, "avatar_source_landmarks_unreliable"),
        ({"face_visibility": 0.24}, "avatar_source_severe_occlusion"),
        ({"occlusion_score": 0.75}, "avatar_source_severe_occlusion"),
    ],
)
def test_each_hard_gate_rejects_independently(overrides, reason):
    evaluation = AvatarSourceQualitySelector().evaluate(good("P", 0, **overrides))
    assert evaluation.eligible is False
    assert reason in evaluation.reason_codes


def test_boundary_values_just_inside_the_gates_remain_eligible():
    inside = good(
        "P",
        0,
        primary_face_confidence=0.45,
        face_short_side_px=64,
        face_sharpness=0.12,
        face_luminance=31.0,
        dark_clip_ratio=0.59,
        highlight_clip_ratio=0.59,
        face_visibility=0.25,
        occlusion_score=0.74,
    )
    assert AvatarSourceQualitySelector().evaluate(inside).eligible is True


# ---------------------------------------------------------------------------
# Scoring: bounded, deterministic, ranked, tie-broken
# ---------------------------------------------------------------------------

def test_score_is_bounded_in_unit_interval_even_with_extreme_inputs():
    selector = AvatarSourceQualitySelector()
    best = selector.evaluate(good("A", 0, face_sharpness=1.0, illumination_quality=1.0, face_visibility=1.0))
    worst = selector.evaluate(
        good("B", 1, face_sharpness=0.12, illumination_quality=0.0, face_visibility=0.25, yaw_degrees=60.0,
             secondary_faces=(SecondaryFaceSignal(confidence=0.9, area_ratio=0.02),))
    )
    for evaluation in (best, worst):
        assert evaluation.eligible is True
        assert 0.0 <= evaluation.quality_score <= 1.0


def test_selection_is_deterministic_and_order_independent():
    sources = [
        good("P1", 0, face_sharpness=0.30),
        good("P2", 1, face_sharpness=0.95),
        good("P3", 2, face_sharpness=0.70, yaw_degrees=25.0),
    ]
    first = AvatarSourceQualitySelector().select(sources)
    reversed_result = AvatarSourceQualitySelector().select(list(reversed(sources)))
    repeated = AvatarSourceQualitySelector().select(sources)
    assert first.selected_photo_id == "P2"
    assert reversed_result.selected_photo_id == first.selected_photo_id
    assert repeated.top1_score == first.top1_score
    assert repeated.score_margin == first.score_margin


def test_exact_tie_is_broken_deterministically_by_stable_order():
    tie_a = good("Z_late", 0)
    tie_b = good("A_early", 1)
    result = AvatarSourceQualitySelector().select([tie_a, tie_b])
    assert result.top1_score == result.top2_score
    assert result.score_margin == 0.0
    # Stable order (upload order) wins before photo id.
    assert result.selected_photo_id == "Z_late"
    assert result.selection_confidence == "low"


def test_top_two_margin_and_confidence_are_recorded_with_versions():
    result = AvatarSourceQualitySelector().select(
        [good("P1", 0, face_sharpness=0.40), good("P2", 1, face_sharpness=0.95)]
    )
    document = result.to_private_document()
    assert document["selectorVersion"] == SELECTOR_VERSION
    assert document["confidencePolicyVersion"] == CONFIDENCE_POLICY_VERSION
    assert document["selectedPhotoId"] == "P2"
    assert document["top1Score"] == result.top1_score
    assert document["top2Score"] == result.top2_score
    assert document["scoreMargin"] == round(result.top1_score - result.top2_score, 6)
    assert document["selectionConfidence"] in {"high", "medium", "low"}
    assert document["evaluatedCount"] == 2
    assert document["eligibleCount"] == 2


# ---------------------------------------------------------------------------
# Privacy: nothing biometric leaves the process
# ---------------------------------------------------------------------------

FORBIDDEN_PERSISTED_KEYS = {
    "evaluations", "primary_bbox", "primaryBbox", "bbox", "landmarks", "embedding",
    "faceEmbedding", "descriptor", "yaw_degrees", "pitch_degrees", "roll_degrees",
}


def test_persisted_selection_document_contains_no_biometric_fields():
    result = AvatarSourceQualitySelector().select(
        [good("P1", 0, face_sharpness=0.40), good("P2", 1)]
    )
    document = result.to_private_document()
    assert FORBIDDEN_PERSISTED_KEYS.isdisjoint(document.keys())
    # Only scalar scores, counts, ids, versions and a reason histogram.
    for value in document.values():
        assert isinstance(value, (str, int, float, dict, type(None)))


def test_bbox_and_evaluations_are_excluded_from_repr():
    signals = good("P1", 0)
    assert "primary_bbox" not in repr(signals)
    result = AvatarSourceQualitySelector().select([signals, good("P2", 1)])
    assert "evaluations" not in repr(result)
    field_names = {f.name for f in dataclasses.fields(result)}
    assert "evaluations" in field_names  # exists in memory ...
    assert "evaluations" not in result.to_private_document()  # ... never persisted


def test_all_ineligible_yields_typed_failure_and_no_selection():
    result = AvatarSourceQualitySelector().select(
        [good("P1", 0, corrupt=True), good("P2", 1, face_short_side_px=10)]
    )
    assert result.selected_photo_id is None
    assert result.failure_code == NO_ELIGIBLE_SOURCE_ERROR
    assert result.eligible_count == 0
    assert result.evaluated_count == 2
