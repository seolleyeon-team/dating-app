import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

import avatar_generation.worker as worker_module  # noqa: E402
from avatar_generation.analysis.config import SourceSafetyConfig  # noqa: E402
from avatar_generation.analysis.small_face.config import (  # noqa: E402
    SmallFacePipelineConfig,
)
from avatar_generation.analysis.small_face.pipeline import (  # noqa: E402
    SmallFaceSourcePipeline,
)
from avatar_generation.analysis.source_analyzer import (  # noqa: E402
    analyze_avatar_source_image,
)
from avatar_generation.environment import (  # noqa: E402
    is_local_or_dev_environment,
    is_production_like_environment,
    resolve_environment_name,
)


class _SingleFaceDetector:
    def detect_raw(self, _image):
        return [((0.25, 0.20, 0.45, 0.50), 0.95, ((0.4, 0.4),))]


class _OkLandmarker:
    def landmark(self, _image):
        point = type("Point", (), {})
        values = []
        for x, y in (
            (0.4, 0.4),
            (0.6, 0.4),
            (0.5, 0.55),
            (0.45, 0.7),
            (0.55, 0.7),
        ):
            value = point()
            value.x = x
            value.y = y
            values.append(value)
        return True, values, None


def _config(*, blur_shadow_enabled: bool) -> SmallFacePipelineConfig:
    return SmallFacePipelineConfig(
        enabled=True,
        blur_shadow_enabled=blur_shadow_enabled,
        full_range_enabled=True,
        face_detect_model_path="",
        primary_min_confidence=0.45,
        fallback_min_confidence=0.35,
        nms_iou_threshold=0.35,
        cross_pass_nms_iou=0.35,
        tile_fallback_enabled=False,
        tile_grids=(2,),
        tile_overlap=0.25,
        tile_max_count=4,
        min_short_side_detect_px=40,
        min_short_side_trait_px=48,
        primary_score_gap_min=0.12,
        secondary_primary_area_ratio_max=0.55,
        primary_crop_target_size=512,
        primary_crop_max_size=768,
        fail_closed_without_model=False,
    )


def _pipeline(*, blur_shadow_enabled: bool) -> SmallFaceSourcePipeline:
    return SmallFaceSourcePipeline(
        config=_config(blur_shadow_enabled=blur_shadow_enabled),
        source_config=SourceSafetyConfig(),
        raw_detector=_SingleFaceDetector(),
        landmarker_backend=_OkLandmarker(),
    )


def _sharp_image() -> Image.Image:
    rng = np.random.default_rng(71)
    return Image.fromarray(
        rng.integers(35, 221, size=(640, 640, 3), dtype=np.uint8),
        "RGB",
    )


@pytest.mark.parametrize(
    ("image", "expected_usable", "expected_reason"),
    [
        (_sharp_image(), True, None),
        (
            Image.new("RGB", (640, 640), (128, 128, 128)),
            False,
            "avatar_source_face_too_blurry",
        ),
    ],
)
def test_shadow_assessor_exception_cannot_change_active_v1_decision(
    monkeypatch,
    image,
    expected_usable,
    expected_reason,
):
    baseline = _pipeline(blur_shadow_enabled=False).run(image)
    pipeline = _pipeline(blur_shadow_enabled=True)

    class FailingAssessorWithoutConfig:
        def assess(self, _image, _primary):
            raise RuntimeError("sensitive-shadow-failure-detail")

    monkeypatch.setattr(
        pipeline,
        "_blur_assessor",
        FailingAssessorWithoutConfig(),
    )
    result = pipeline.run(image)

    assert result.analysis.avatar_usable is expected_usable
    assert result.analysis.reason_code == expected_reason
    assert result.public_reject_reasons == baseline.public_reject_reasons
    assert result.analysis.classification == baseline.analysis.classification
    assert result.analysis.quality_assessment is None
    assert result.detector_result.metadata["blurShadowDecision"] == "unavailable"
    encoded = json.dumps(result.detector_result.metadata).lower()
    assert "sensitive-shadow-failure-detail" not in encoded
    assert "exception" not in encoded
    assert "bbox" not in encoded
    assert "laplacian" not in encoded


def test_disabled_shadow_has_no_assessor_cost_or_evidence(monkeypatch):
    pipeline = _pipeline(blur_shadow_enabled=False)

    def forbidden_shadow(_image, _primary):
        raise AssertionError("disabled shadow must not execute")

    monkeypatch.setattr(pipeline._blur_assessor, "assess", forbidden_shadow)
    result = pipeline.run(_sharp_image())

    assert result.analysis.avatar_usable is True
    assert result.analysis.quality_assessment is None
    assert result.detector_result.metadata["blurShadowDecision"] == "disabled"
    assert "blurAssessmentShadowMs" not in result.detector_result.metadata
    assert "blurMetricVersion" not in result.detector_result.metadata


def test_blur_shadow_config_is_opt_in(monkeypatch):
    monkeypatch.delenv("AVATAR_BLUR_SHADOW_ENABLED", raising=False)
    assert SmallFacePipelineConfig.from_env().blur_shadow_enabled is False

    monkeypatch.setenv("AVATAR_BLUR_SHADOW_ENABLED", "true")
    assert SmallFacePipelineConfig.from_env().blur_shadow_enabled is True


@pytest.mark.parametrize(
    "alias",
    ("AVATAR_ENVIRONMENT", "ENVIRONMENT", "APP_ENV"),
)
def test_all_environment_aliases_force_production_source_analysis(
    monkeypatch,
    alias,
):
    for name in ("AVATAR_ENVIRONMENT", "ENVIRONMENT", "APP_ENV"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(alias, "production")
    monkeypatch.setenv("AVATAR_FACE_DETECTOR_ENABLED", "false")
    monkeypatch.setenv("AVATAR_SMALL_FACE_PIPELINE_ENABLED", "false")
    monkeypatch.setenv("AVATAR_FACE_DETECT_MODEL_PATH", "missing-model.tflite")

    analysis = analyze_avatar_source_image(Image.new("RGB", (128, 128), "white"))

    assert analysis.hard_reject is True
    assert analysis.reject_reasons == ["corrupt_image"]
    assert resolve_environment_name() == "production"
    assert is_production_like_environment() is True
    assert worker_module.is_production_environment() is True


@pytest.mark.parametrize(
    ("values", "expected_name", "expected_production"),
    [
        (
            {
                "AVATAR_ENVIRONMENT": "local",
                "ENVIRONMENT": "production",
                "APP_ENV": "production",
            },
            "local",
            True,
        ),
        (
            {
                "AVATAR_ENVIRONMENT": " ",
                "ENVIRONMENT": "staging",
                "APP_ENV": "production",
            },
            "staging",
            True,
        ),
        (
            {
                "AVATAR_ENVIRONMENT": "",
                "ENVIRONMENT": "",
                "APP_ENV": "production_bridge",
            },
            "production_bridge",
            True,
        ),
    ],
)
def test_environment_alias_display_precedence_but_conflicts_fail_closed(
    monkeypatch,
    values,
    expected_name,
    expected_production,
):
    for name in ("AVATAR_ENVIRONMENT", "ENVIRONMENT", "APP_ENV"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv(name, values[name])

    assert resolve_environment_name() == expected_name
    assert is_production_like_environment() is expected_production
    assert is_local_or_dev_environment() is False


def test_production_legacy_detector_injection_cannot_bypass_small_face(monkeypatch):
    for name in ("AVATAR_ENVIRONMENT", "ENVIRONMENT", "APP_ENV"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AVATAR_SMALL_FACE_PIPELINE_ENABLED", "false")
    monkeypatch.setenv("AVATAR_FACE_DETECT_MODEL_PATH", "missing-model.tflite")

    class ForbiddenLegacyDetector:
        def detect(self, _image):
            raise AssertionError("legacy detector must not run in production")

    result = analyze_avatar_source_image(
        Image.new("RGB", (128, 128), "white"),
        detector=ForbiddenLegacyDetector(),
    )

    assert result.hard_reject is True
    assert result.reject_reasons == ["corrupt_image"]
    assert result.detector_metadata["modelMissing"] is True
