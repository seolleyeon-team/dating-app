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

import avatar_generation.analysis.source_analyzer as source_analyzer  # noqa: E402
import avatar_generation.worker as worker_module  # noqa: E402
from avatar_generation.analysis.config import SourceSafetyConfig  # noqa: E402
from avatar_generation.analysis.small_face.config import (  # noqa: E402
    SmallFacePipelineConfig,
)
from avatar_generation.analysis.small_face.pipeline import (  # noqa: E402
    SmallFaceSourcePipeline,
    _to_public_reasons,
)
from avatar_generation.analysis.source_analyzer import (  # noqa: E402
    analyze_avatar_source_image,
)


class SingleFaceDetector:
    def __init__(self, *, face_xywh=(0.25, 0.20, 0.45, 0.50)):
        self.face_xywh = face_xywh

    def detect_raw(self, _image):
        x, y, width, height = self.face_xywh
        return [((x, y, width, height), 0.95, ((x + width / 2, y + height / 2),))]


class OkLandmarker:
    def landmark(self, _image):
        point = type("Point", (), {})
        result = []
        for x, y in ((0.4, 0.4), (0.6, 0.4), (0.5, 0.55), (0.45, 0.7), (0.55, 0.7)):
            value = point()
            value.x = x
            value.y = y
            result.append(value)
        return True, result, None


class FailingLandmarker:
    def landmark(self, _image):
        return False, None, "avatar_source_landmarks_unstable"


def _config(**overrides):
    values = dict(
        enabled=True,
        blur_shadow_enabled=True,
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
    values.update(overrides)
    return SmallFacePipelineConfig(**values)


def _sharp_image(size=640):
    y, x = np.indices((size, size))
    base = ((x * 37 + y * 19) % 186 + 35).astype(np.uint8)
    array = np.stack((base, np.roll(base, 3, axis=1), np.roll(base, 5, axis=0)), axis=2)
    return Image.fromarray(array, "RGB")


def _pipeline(*, config=None, detector=None, landmarker=None):
    return SmallFaceSourcePipeline(
        config=config or _config(),
        source_config=SourceSafetyConfig(),
        raw_detector=detector or SingleFaceDetector(),
        landmarker_backend=landmarker or OkLandmarker(),
    )


def test_shadow_metadata_uses_allowlist_without_raw_metric_evidence():
    result = _pipeline().run(_sharp_image())
    metadata = result.detector_result.metadata

    allowed = {
        "pipeline",
        "faceDetectionFullMs",
        "faceDetectionTileMs",
        "tileCount",
        "nmsMs",
        "primarySelectionMs",
        "cropLandmarkerMs",
        "referencePreprocessingMs",
        "usedTileFallback",
        "detectionPassCount",
        "detectedFaceCountBucket",
        "primaryFaceSizeBucket",
        "secondaryFacesDetected",
        "secondaryFacesNeutralized",
        "secondaryFaceNeutralizationCount",
        "neutralizationMethodVersion",
        "sourceRejectedBeforeGpu",
        "blurAssessmentShadowMs",
        "blurMetricVersion",
        "blurPolicyVersion",
        "blurCalibrationStatus",
        "blurShadowDecision",
    }
    forbidden_fragments = {
        "laplacian",
        "tenengrad",
        "edgedensity",
        "localcontrast",
        "validpixel",
        "luminance",
        "clipping",
        "compressionrisk",
        "bbox",
        "landmarks",
        "keypoint",
    }

    assert set(metadata) <= allowed
    rendered = json.dumps(metadata, default=str).lower()
    assert not any(fragment in rendered for fragment in forbidden_fragments)
    assert metadata["sourceRejectedBeforeGpu"] is False
    assert metadata["blurMetricVersion"] == "avatar_face_blur_multimetric_v3"
    assert metadata["blurPolicyVersion"] == "pr85_v3_shadow"


@pytest.mark.parametrize(
    ("image", "config", "landmarker", "expected_reason"),
    [
        (
            Image.new("RGB", (640, 640), (128, 128, 128)),
            _config(),
            OkLandmarker(),
            "avatar_source_face_too_blurry",
        ),
        (
            _sharp_image(),
            _config(min_short_side_trait_px=320),
            OkLandmarker(),
            "avatar_source_face_too_small",
        ),
        (
            _sharp_image(),
            _config(),
            FailingLandmarker(),
            "avatar_source_landmarks_unstable",
        ),
    ],
)
def test_all_source_quality_rejections_set_pre_gpu_flag(
    image,
    config,
    landmarker,
    expected_reason,
):
    result = _pipeline(config=config, landmarker=landmarker).run(image)

    assert result.analysis.reason_code == expected_reason
    assert result.analysis.metrics["sourceRejectedBeforeGpu"] is True
    assert result.analysis.avatar_usable is False


def test_process_local_assessment_is_not_persisted_in_source_analysis_document():
    image = _sharp_image()
    config = _config()
    pipeline = _pipeline(config=config)

    result = analyze_avatar_source_image(
        image,
        source_ref="redacted-local-fixture",
        small_face_pipeline=pipeline,
        small_face_config=config,
    )
    document = result.to_document()
    rendered = json.dumps(document, default=str).lower()

    assert result.internal_face_analysis.quality_assessment is not None
    assert "quality_assessment" not in rendered
    assert "native_metrics" not in rendered
    assert "canonical_metrics" not in rendered
    assert "laplacian" not in rendered
    assert "tenengrad" not in rendered
    assert "validpixel" not in rendered
    assert "bbox" not in rendered
    assert "landmarks" not in rendered


@pytest.mark.parametrize(
    ("internal_reason", "public_reason"),
    [
        ("avatar_source_face_too_blurry", "face_too_blurry"),
        ("avatar_source_face_out_of_frame", "face_out_of_frame"),
        ("avatar_source_landmarks_unstable", "landmarks_unstable"),
        ("avatar_source_low_light", "low_light"),
        ("avatar_source_compression_damage", "compression_damage"),
        ("avatar_source_analysis_uncertain", "analysis_uncertain"),
    ],
)
def test_internal_quality_reasons_have_distinct_safe_public_mappings(
    internal_reason,
    public_reason,
):
    assert _to_public_reasons(internal_reason) == (public_reason,)
    assert source_analyzer._ordered_reasons([public_reason]) == [public_reason]


@pytest.mark.parametrize(
    ("public_reason", "worker_error_code"),
    [
        ("face_too_blurry", "avatar_source_face_too_blurry"),
        ("face_out_of_frame", "avatar_source_face_out_of_frame"),
        ("landmarks_unstable", "avatar_source_landmarks_unstable"),
        ("low_light", "avatar_source_low_light"),
        ("compression_damage", "avatar_source_compression_damage"),
        ("analysis_uncertain", "avatar_source_analysis_uncertain"),
    ],
)
def test_worker_preserves_distinct_source_quality_error_codes(
    public_reason,
    worker_error_code,
):
    analysis = {"status": "rejected", "hardReject": True, "rejectReasons": [public_reason]}

    assert worker_module._source_reject_error_code(analysis) == worker_error_code
