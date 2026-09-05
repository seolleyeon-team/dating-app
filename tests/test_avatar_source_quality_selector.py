import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.avatar_source_quality import (  # noqa: E402
    NO_ELIGIBLE_SOURCE_ERROR,
    SELECTOR_VERSION,
    AvatarSourceQualitySelector,
    SecondaryFaceSignal,
    SourceQualitySignals,
)


def _source(photo_id: str, order: int = 0, **overrides) -> SourceQualitySignals:
    values = dict(
        photo_id=photo_id,
        stable_order=order,
        image_width=1200,
        image_height=1600,
        primary_face_confidence=0.96,
        primary_bbox=(0.28, 0.18, 0.44, 0.42),
        face_short_side_px=520,
        face_sharpness=0.90,
        yaw_degrees=4.0,
        pitch_degrees=2.0,
        roll_degrees=1.0,
        illumination_quality=0.90,
        face_luminance=128.0,
        dark_clip_ratio=0.01,
        highlight_clip_ratio=0.01,
        face_visibility=0.95,
        occlusion_score=0.05,
        landmarks_reliable=True,
        corrupt=False,
        secondary_faces=(),
        glasses_present=False,
    )
    values.update(overrides)
    return SourceQualitySignals(**values)


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"primary_face_confidence": None, "primary_bbox": None}, "avatar_source_no_face"),
        ({"face_short_side_px": 40}, "avatar_source_face_too_small"),
        ({"primary_bbox": (0.0, 0.0, 0.5, 0.55)}, "avatar_source_face_out_of_frame"),
        ({"face_sharpness": 0.08}, "avatar_source_face_too_blurry"),
        ({"face_luminance": 20.0, "dark_clip_ratio": 0.70}, "avatar_source_underexposed"),
        ({"face_luminance": 242.0, "highlight_clip_ratio": 0.70}, "avatar_source_overexposed"),
        ({"landmarks_reliable": False}, "avatar_source_landmarks_unreliable"),
        ({"face_visibility": 0.18, "occlusion_score": 0.82}, "avatar_source_severe_occlusion"),
        ({"corrupt": True}, "avatar_source_corrupt_image"),
    ],
)
def test_hard_gate_rejects_unusable_sources(overrides, reason):
    evaluation = AvatarSourceQualitySelector().evaluate(_source("p1", **overrides))
    assert evaluation.eligible is False
    assert reason in evaluation.reason_codes


def test_good_face_glasses_and_moderate_three_quarter_pose_remain_eligible():
    selector = AvatarSourceQualitySelector()
    plain = selector.evaluate(_source("plain"))
    glasses = selector.evaluate(_source("glasses", glasses_present=True))
    three_quarter = selector.evaluate(_source("three_quarter", yaw_degrees=34.0))

    assert plain.eligible is True
    assert glasses.eligible is True
    assert three_quarter.eligible is True


def test_meaningful_secondary_rejects_but_tiny_background_face_only_penalizes():
    selector = AvatarSourceQualitySelector()
    meaningful = SecondaryFaceSignal(confidence=0.90, area_ratio=0.09)
    tiny = SecondaryFaceSignal(confidence=0.62, area_ratio=0.004)

    rejected = selector.evaluate(_source("two_people", secondary_faces=(meaningful,)))
    accepted = selector.evaluate(_source("background", secondary_faces=(tiny,)))

    assert rejected.eligible is False
    assert rejected.reason_codes == ("avatar_source_multiple_primary_faces",)
    assert accepted.eligible is True
    assert accepted.components.secondary_person_penalty > 0


@pytest.mark.parametrize(
    ("worse", "better"),
    [
        ({"face_sharpness": 0.35}, {"face_sharpness": 0.95}),
        ({"face_short_side_px": 80, "primary_bbox": (0.43, 0.35, 0.10, 0.10)}, {}),
        ({"primary_bbox": (0.10, 0.02, 0.80, 0.92)}, {}),
        ({"yaw_degrees": 62.0}, {"yaw_degrees": 8.0}),
        ({"illumination_quality": 0.35, "face_luminance": 48.0}, {"illumination_quality": 0.90}),
        ({"face_visibility": 0.45, "occlusion_score": 0.45}, {"face_visibility": 0.95}),
        ({"primary_bbox": (0.05, 0.08, 0.42, 0.42)}, {}),
        ({"secondary_faces": (SecondaryFaceSignal(0.50, 0.01),)}, {}),
    ],
)
def test_quality_components_rank_better_equivalent_above_worse(worse, better):
    selector = AvatarSourceQualitySelector()
    worse_eval = selector.evaluate(_source("worse", **worse))
    better_eval = selector.evaluate(_source("better", **better))

    assert worse_eval.eligible is True
    assert better_eval.eligible is True
    assert better_eval.quality_score > worse_eval.quality_score


def test_score_is_bounded_and_tie_breaking_is_stable():
    selector = AvatarSourceQualitySelector()
    evaluations = [selector.evaluate(_source("z", 0)), selector.evaluate(_source("a", 0))]

    assert all(0.0 <= item.quality_score <= 1.0 for item in evaluations)
    first = selector.select([_source("z", 0), _source("a", 0)])
    second = selector.select([_source("a", 0), _source("z", 0)])
    assert first.selected_photo_id == "a"
    assert second.selected_photo_id == "a"


def test_top_two_margin_and_confidence_are_versioned():
    selector = AvatarSourceQualitySelector()
    result = selector.select(
        [
            _source("top", 0),
            _source("runner_up", 1, face_sharpness=0.20, yaw_degrees=55.0),
        ]
    )

    assert result.selector_version == SELECTOR_VERSION
    assert result.top1_score is not None
    assert result.top2_score is not None
    assert result.score_margin == pytest.approx(result.top1_score - result.top2_score)
    assert result.selection_confidence == "high"


def test_one_eligible_has_no_fake_top_two_margin():
    result = AvatarSourceQualitySelector().select(
        [_source("only"), _source("bad", corrupt=True)]
    )
    assert result.selected_photo_id == "only"
    assert result.top2_score is None
    assert result.score_margin is None


def test_near_tie_is_low_confidence_but_still_selects_exactly_one():
    result = AvatarSourceQualitySelector().select([_source("b", 1), _source("a", 0)])
    assert result.selection_confidence == "low"
    assert result.selected_photo_id == "a"
    assert len(result.selected_source_ids) == 1


def test_two_three_and_six_photo_sets_select_best_not_first():
    selector = AvatarSourceQualitySelector()
    poor = dict(face_sharpness=0.25, yaw_degrees=50.0, illumination_quality=0.45)
    side = dict(face_sharpness=0.88, yaw_degrees=34.0, illumination_quality=0.85)

    assert selector.select([_source("p1", 0, **poor), _source("p2", 1)]).selected_photo_id == "p2"
    assert selector.select([_source("p1", 0, **poor), _source("p2", 1), _source("p3", 2, **side)]).selected_photo_id == "p2"
    result = selector.select(
        [
            _source("p1", 0, **poor),
            _source("p2", 1, **side),
            _source("p3", 2),
            _source("p4", 3, secondary_faces=(SecondaryFaceSignal(0.9, 0.1),)),
            _source("p5", 4, face_luminance=20.0, dark_clip_ratio=0.8),
            _source("p6", 5, face_short_side_px=40),
        ]
    )
    assert result.selected_photo_id == "p3"
    assert result.runner_up_photo_id == "p2"


def test_all_ineligible_returns_typed_failure_without_fallback():
    result = AvatarSourceQualitySelector().select(
        [_source("first", corrupt=True), _source("second", primary_bbox=None)]
    )
    assert result.selected_photo_id is None
    assert result.failure_code == NO_ELIGIBLE_SOURCE_ERROR
    assert result.selected_source_ids == ()
