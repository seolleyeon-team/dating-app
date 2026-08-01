import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

import avatar_generation.worker as worker_module
from avatar_generation.analysis.config import SourceSafetyConfig
from avatar_generation.analysis.small_face.blur_assessment import BlurAssessor
from avatar_generation.analysis.small_face.config import SmallFacePipelineConfig
from avatar_generation.analysis.small_face.pipeline import SmallFaceSourcePipeline
from avatar_generation.analysis.small_face.types import (
    CropTransform,
    InternalFaceAnalysis,
    InternalFaceDetection,
    NormalizedBox,
    PixelBox,
)
from avatar_generation.analysis.source_analyzer import analyze_avatar_source_image
from avatar_generation.quality_context import AvatarQualityContext
from tests.test_avatar_generation_worker import _fake_firestore, _fake_storage, _payload, _passing_qa


class _SingleFaceDetector:
    def detect_raw(self, _image):
        return [((0.25, 0.20, 0.45, 0.50), 0.95, ((0.4, 0.4),))]


class _OkLandmarker:
    def landmark(self, _image):
        point = type("Point", (), {})
        values = []
        for x, y in ((0.4, 0.4), (0.6, 0.4), (0.5, 0.55), (0.45, 0.7), (0.55, 0.7)):
            value = point()
            value.x = x
            value.y = y
            values.append(value)
        return True, values, None


def _pipeline_config(**overrides):
    values = dict(
        enabled=True,
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


def test_production_flux_cannot_disable_source_analysis_or_reach_generation(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production_bridge")
    monkeypatch.setenv("AVATAR_DATA_PROJECT", "seolleyeon-festival")
    monkeypatch.setenv("AVATAR_FACE_DETECTOR_ENABLED", "false")
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "false")
    calls = {"analysis": 0, "generation": 0}

    class RejectedAnalysis:
        hard_reject = True
        broad_trait_hints = {}

        def to_document(self):
            return {
                "status": "rejected",
                "hardReject": True,
                "rejectReasons": ["corrupt_image"],
            }

    def rejected_analysis(*_args, **_kwargs):
        calls["analysis"] += 1
        return RejectedAnalysis()

    def forbidden_generation(*_args, **_kwargs):
        calls["generation"] += 1
        raise AssertionError("generation must not run after source rejection")

    monkeypatch.setattr(worker_module, "analyze_avatar_source_image", rejected_analysis)
    monkeypatch.setattr(worker_module, "_analyze_source_visual_risk", lambda *_a, **_k: None)
    monkeypatch.setattr(worker_module, "generate_candidate_artifacts", forbidden_generation)
    payload = _payload(job_id="avatar_g006_source_analysis_required")
    fs = _fake_firestore(payload)

    result = worker_module.process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="flux",
        firestore_project="seolleyeon-festival",
    )

    assert result.status == "failed"
    assert calls == {"analysis": 1, "generation": 0}
    assert fs.data["avatarCandidates"] == {}


def test_production_source_analyzer_forces_small_face_fail_closed(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AVATAR_SMALL_FACE_PIPELINE_ENABLED", "false")
    monkeypatch.setenv("AVATAR_FACE_DETECT_MODEL_PATH", "missing-model.tflite")

    result = analyze_avatar_source_image(Image.new("RGB", (128, 128), "white"))

    assert result.status == "rejected"
    assert result.hard_reject is True
    assert result.reject_reasons == ["corrupt_image"]
    assert result.detector_metadata["modelMissing"] is True


def test_process_local_geometry_and_metric_repr_is_sanitized():
    normalized = NormalizedBox(0.1234, 0.2345, 0.6789, 0.7891)
    pixels = PixelBox(31, 47, 211, 229)
    detection = InternalFaceDetection(
        bbox_normalized=normalized,
        bbox_pixels=pixels,
        keypoints_normalized=((0.3333, 0.4444),),
        confidence=0.91,
        face_short_side_px=180,
    )
    transform = CropTransform(
        original_box=pixels,
        padded_box=PixelBox(3, 5, 251, 253),
        target_width=512,
        target_height=512,
        scale_x=2.1,
        scale_y=2.1,
        offset_x=0.0,
        offset_y=0.0,
    )
    analysis = InternalFaceAnalysis(
        primary_detection=detection,
        secondary_detections=(detection,),
        crop_transform=transform,
        metrics={"poisonToken": "secret"},
    )
    rng = np.random.default_rng(11)
    image = Image.fromarray(rng.integers(35, 221, (256, 256, 3), dtype=np.uint8), "RGB")
    assessment = BlurAssessor().assess(image, detection)
    rendered = " ".join(map(repr, (normalized, pixels, detection, transform, analysis, assessment))).lower()

    for forbidden in (
        "x_min",
        "x_max",
        "bbox",
        "keypoint",
        "original_box",
        "padded_box",
        "crop_transform",
        "poison",
        "native_roi",
        "laplacian",
        "tenengrad",
        "edge_density",
        "local_contrast",
        "clipping_ratio",
        "compression_risk",
    ):
        assert forbidden not in rendered


def test_active_legacy_blur_branch_preserves_distinct_public_reason():
    config = _pipeline_config()
    pipeline = SmallFaceSourcePipeline(
        config=config,
        source_config=SourceSafetyConfig(),
        raw_detector=_SingleFaceDetector(),
        landmarker_backend=_OkLandmarker(),
    )
    image = Image.new("RGB", (640, 640), (128, 128, 128))

    pipeline_result = pipeline.run(image)
    analysis_result = analyze_avatar_source_image(
        image,
        small_face_pipeline=pipeline,
        small_face_config=config,
    )

    assert pipeline_result.analysis.reason_code == "avatar_source_face_too_blurry"
    assert pipeline_result.public_reject_reasons == ("face_too_blurry",)
    assert analysis_result.reject_reasons == ["face_too_blurry"]


def test_quality_context_persistence_uses_recursive_allowlist():
    context = AvatarQualityContext(
        metadata={
            "schemaVersion": "avatar_reference_preprocess_metadata_v1",
            "enabled": True,
            "regions": {
                "face": {"downsamplePx": 32, "maskCoverage": 0.2, "sourcePath": "private"},
                "style": {"downsamplePx": 96, "blurRadius": 1.5},
                "token": "private",
            },
            "segmentation": {
                "provider": "source_analysis",
                "faceCount": 1,
                "bbox": [1, 2, 3, 4],
                "landmarkData": "private",
            },
            "backgroundNeutralization": {
                "enabled": True,
                "mode": "neutral_color",
                "foregroundMaskCoverage": 0.4,
                "signedToken": "private",
            },
            "sourcePhotoRefs": ["private"],
            "localPath": "private",
            "refreshToken": "private",
            "unexpectedSafeLookingKey": "must still be dropped",
        }
    )

    persisted = context.persisted_metadata()
    encoded = json.dumps(persisted).lower()

    assert persisted["schemaVersion"] == "avatar_reference_preprocess_metadata_v1"
    assert persisted["regions"]["face"]["downsamplePx"] == 32
    assert persisted["segmentation"] == {"provider": "source_analysis", "faceCount": 1}
    assert persisted["backgroundNeutralization"]["mode"] == "neutral_color"
    for forbidden in (
        "sourcepath",
        "token",
        "bbox",
        "landmark",
        "sourcephotorefs",
        "localpath",
        "unexpected",
    ):
        assert forbidden not in encoded
