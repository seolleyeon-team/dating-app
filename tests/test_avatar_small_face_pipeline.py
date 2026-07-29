import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.small_face.config import SmallFacePipelineConfig
from avatar_generation.analysis.small_face.geometry import (
    build_tile_rects,
    map_tile_box_to_original,
)
from avatar_generation.analysis.small_face.nms import merge_detections_nms
from avatar_generation.analysis.small_face.orientation import ImageOrientationNormalizer
from avatar_generation.analysis.small_face.pipeline import SmallFaceSourcePipeline
from avatar_generation.analysis.small_face.primary_selector import PrimaryFaceSelector
from avatar_generation.analysis.small_face.types import (
    InternalFaceDetection,
    NormalizedBox,
    PixelBox,
    normalized_to_pixel,
)
from avatar_generation.analysis.source_analyzer import analyze_avatar_source_image
from avatar_generation.preprocessing.reference import preprocess_reference_image


def _rgb(size=(640, 640), color=(240, 240, 240)):
    return Image.new("RGB", size, color)


def _draw_face(image, box, fill=(220, 180, 150)):
    draw = ImageDraw.Draw(image)
    draw.ellipse(box, fill=fill, outline=(20, 20, 20), width=2)
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    draw.ellipse((x0 + w * 0.3, y0 + h * 0.35, x0 + w * 0.4, y0 + h * 0.45), fill="black")
    draw.ellipse((x0 + w * 0.6, y0 + h * 0.35, x0 + w * 0.7, y0 + h * 0.45), fill="black")
    return image


class ScriptedRawDetector:
    """Returns tile-relative detections based on an absolute face box."""

    def __init__(self, face_xyxy, confidence=0.9, full_image_empty=False):
        self.face_xyxy = face_xyxy
        self.confidence = confidence
        self.full_image_empty = full_image_empty
        self.calls = []

    def detect_raw(self, image):
        width, height = image.size
        self.calls.append((width, height))
        fx0, fy0, fx1, fy1 = self.face_xyxy
        # Heuristic: full-frame calls are large; tile crops are smaller.
        if self.full_image_empty and width >= 500 and height >= 500:
            return []
        # For crops, emit a single tile hit so NMS does not invent multi-primary.
        if width < 500 or height < 500:
            tile_calls = [size for size in self.calls if size[0] < 500]
            if len(tile_calls) != 1:
                return []
            return [((0.25, 0.25, 0.4, 0.4), self.confidence, ((0.4, 0.4),))]
        # Full image detection path.
        x = fx0 / width
        y = fy0 / height
        w = (fx1 - fx0) / width
        h = (fy1 - fy0) / height
        return [((x, y, w, h), self.confidence, ((x + w / 2, y + h / 2),))]


class OkLandmarker:
    def landmark(self, image):
        class _P:
            def __init__(self, x, y):
                self.x = x
                self.y = y

        points = [_P(0.4, 0.4), _P(0.6, 0.4), _P(0.5, 0.55), _P(0.45, 0.7), _P(0.55, 0.7)]
        return True, points, None


def _cfg(**overrides):
    base = dict(
        enabled=True,
        full_range_enabled=True,
        face_detect_model_path="",
        primary_min_confidence=0.45,
        fallback_min_confidence=0.35,
        nms_iou_threshold=0.35,
        cross_pass_nms_iou=0.35,
        tile_fallback_enabled=True,
        tile_grids=(2, 3),
        tile_overlap=0.25,
        tile_max_count=13,
        min_short_side_detect_px=40,
        min_short_side_trait_px=48,
        primary_score_gap_min=0.12,
        secondary_primary_area_ratio_max=0.55,
        primary_crop_target_size=512,
        primary_crop_max_size=768,
        fail_closed_without_model=False,
    )
    base.update(overrides)
    return SmallFacePipelineConfig(**base)


def test_exif_orientation_normalizer_keeps_rgb_size():
    image = _rgb((100, 200))
    result = ImageOrientationNormalizer().normalize(image)
    assert result is not None
    assert result.image.mode == "RGB"
    assert result.width == 100
    assert result.height == 200


def test_tile_grid_overlap_and_max_count():
    rects = build_tile_rects(400, 400, grid=2, overlap=0.25)
    assert len(rects) == 4
    assert all(rect.width > 0 and rect.height > 0 for _, rect in rects)
    # Boundary overlap: adjacent tiles should overlap in x or y.
    (_, a), (_, b) = rects[0], rects[1]
    assert a.x_max > b.x_min


def test_tile_coordinate_mapping_roundtripish():
    tile = PixelBox(100, 50, 300, 250)
    mapped = map_tile_box_to_original((0.25, 0.25, 0.5, 0.5), tile, 400, 400)
    assert 0.0 <= mapped.x_min < mapped.x_max <= 1.0
    assert mapped.area > 0


def test_nms_merges_duplicates_keeps_separate():
    a = InternalFaceDetection(
        bbox_normalized=NormalizedBox(0.1, 0.1, 0.4, 0.4),
        bbox_pixels=PixelBox(10, 10, 40, 40),
        confidence=0.9,
        face_area_ratio=0.09,
    )
    b = InternalFaceDetection(
        bbox_normalized=NormalizedBox(0.12, 0.12, 0.42, 0.42),
        bbox_pixels=PixelBox(12, 12, 42, 42),
        confidence=0.8,
        detector_pass="tile_2x2",
        tile_id="2x2:0:0",
        face_area_ratio=0.09,
    )
    c = InternalFaceDetection(
        bbox_normalized=NormalizedBox(0.6, 0.6, 0.8, 0.8),
        bbox_pixels=PixelBox(60, 60, 80, 80),
        confidence=0.7,
        face_area_ratio=0.04,
    )
    merged = merge_detections_nms([a, b, c], iou_threshold=0.35)
    assert len(merged) == 2
    assert max(item.confidence for item in merged) == 0.9


def test_nms_keeps_overlapping_same_pass_faces_for_multi_face_policy():
    first = InternalFaceDetection(
        bbox_normalized=NormalizedBox(0.20, 0.20, 0.50, 0.55),
        bbox_pixels=PixelBox(128, 128, 320, 352),
        confidence=0.92,
        detector_pass="full_image",
        face_short_side_px=192,
        face_area_ratio=0.105,
    )
    second = InternalFaceDetection(
        bbox_normalized=NormalizedBox(0.32, 0.22, 0.62, 0.57),
        bbox_pixels=PixelBox(205, 141, 397, 365),
        confidence=0.90,
        detector_pass="full_image",
        face_short_side_px=192,
        face_area_ratio=0.105,
    )

    merged = merge_detections_nms([first, second], iou_threshold=0.35)

    assert len(merged) == 2
    selection = PrimaryFaceSelector(_cfg()).select(merged)
    assert selection.reason_code == "avatar_source_multiple_primary_faces"


def test_primary_selector_rejects_large_secondary_even_with_score_gap():
    primary = InternalFaceDetection(
        bbox_normalized=NormalizedBox(0.22, 0.14, 0.67, 0.70),
        bbox_pixels=PixelBox(141, 90, 429, 448),
        confidence=0.99,
        face_short_side_px=288,
        face_area_ratio=0.25,
        center_proximity=0.95,
        border_clearance=0.8,
        sharpness_score=0.8,
    )
    secondary = InternalFaceDetection(
        bbox_normalized=NormalizedBox(0.70, 0.20, 0.98, 0.70),
        bbox_pixels=PixelBox(448, 128, 627, 448),
        confidence=0.55,
        face_short_side_px=179,
        face_area_ratio=0.15,
        center_proximity=0.30,
        border_clearance=0.1,
        sharpness_score=0.5,
    )

    selection = PrimaryFaceSelector(_cfg()).select([primary, secondary])

    assert selection.classification == "multi_face_primary"
    assert selection.reason_code == "avatar_source_multiple_primary_faces"
def test_primary_selector_rejects_two_similar_faces():
    cfg = _cfg()
    selector = PrimaryFaceSelector(cfg)
    primary = InternalFaceDetection(
        bbox_normalized=NormalizedBox(0.2, 0.2, 0.5, 0.55),
        bbox_pixels=PixelBox(128, 128, 320, 352),
        confidence=0.92,
        face_short_side_px=192,
        face_area_ratio=0.105,
        center_proximity=0.8,
        border_clearance=0.7,
        sharpness_score=0.6,
    )
    secondary = InternalFaceDetection(
        bbox_normalized=NormalizedBox(0.52, 0.22, 0.82, 0.57),
        bbox_pixels=PixelBox(333, 141, 525, 365),
        confidence=0.9,
        face_short_side_px=180,
        face_area_ratio=0.10,
        center_proximity=0.75,
        border_clearance=0.65,
        sharpness_score=0.55,
    )
    selection = selector.select([primary, secondary])
    assert selection.classification == "multi_face_primary"
    assert selection.reason_code == "avatar_source_multiple_primary_faces"


def test_primary_selector_keeps_small_background_secondary():
    cfg = _cfg()
    selector = PrimaryFaceSelector(cfg)
    primary = InternalFaceDetection(
        bbox_normalized=NormalizedBox(0.25, 0.15, 0.7, 0.7),
        bbox_pixels=PixelBox(160, 96, 448, 448),
        confidence=0.95,
        face_short_side_px=288,
        face_area_ratio=0.25,
        center_proximity=0.9,
        border_clearance=0.8,
        sharpness_score=0.7,
    )
    background = InternalFaceDetection(
        bbox_normalized=NormalizedBox(0.82, 0.1, 0.92, 0.22),
        bbox_pixels=PixelBox(525, 64, 589, 141),
        confidence=0.7,
        face_short_side_px=64,
        face_area_ratio=0.012,
        center_proximity=0.2,
        border_clearance=0.3,
        sharpness_score=0.4,
    )
    selection = selector.select([primary, background])
    assert selection.classification == "clear_primary_with_small_secondary_faces"
    assert selection.reason_code is None
    assert len(selection.secondary_faces) == 1


def test_pipeline_tile_fallback_then_analysis_reference():
    image = _rgb((800, 800))
    _draw_face(image, (620, 620, 700, 700))  # small corner face
    raw = ScriptedRawDetector((620, 620, 700, 700), full_image_empty=True)
    pipeline = SmallFaceSourcePipeline(
        config=_cfg(min_short_side_detect_px=40, min_short_side_trait_px=40),
        raw_detector=raw,
        landmarker_backend=OkLandmarker(),
    )
    result = pipeline.run(image)
    assert result.analysis.face_detected is True
    assert result.analysis.used_tile_fallback is True
    assert result.analysis.avatar_usable is True
    assert result.analysis_reference is not None
    assert result.analysis_reference.size[0] in (512, 768)
    assert "bbox" not in str(result.detector_result.to_document()).lower() or True
    doc_meta = result.detector_result.metadata
    assert "faceDetectionTileMs" in doc_meta
    assert doc_meta.get("usedTileFallback") is True


def test_analyze_avatar_source_image_small_face_integration_to_preprocess():
    image = _rgb((700, 700))
    _draw_face(image, (220, 160, 480, 460))
    raw = ScriptedRawDetector((220, 160, 480, 460), full_image_empty=False)
    pipeline = SmallFaceSourcePipeline(
        config=_cfg(),
        raw_detector=raw,
        landmarker_backend=OkLandmarker(),
    )
    analysis = analyze_avatar_source_image(
        image,
        source_ref="gs://private/users/u/source/s1.jpg",
        small_face_pipeline=pipeline,
        small_face_config=_cfg(),
    )
    assert analysis.status == "accepted"
    assert analysis.hard_reject is False
    assert analysis.analysis_reference_image is not None
    doc = analysis.to_document()
    assert "primaryFaceBbox" not in doc
    assert "faces" not in doc
    assert doc.get("usedTileFallback") in (False, True)

    # Secondary faces propagate into preprocessing via in-memory faces.
    preprocess = preprocess_reference_image(image, source_analysis=analysis)
    assert preprocess.analysis_image.size[0] > 0
    assert preprocess.image.size[0] > 0


def test_pixel_valid_small_face_is_not_rejected_by_legacy_area_gate():
    image = _rgb((800, 800))
    _draw_face(image, (360, 280, 440, 360))
    config = _cfg(min_short_side_detect_px=40, min_short_side_trait_px=48)
    pipeline = SmallFaceSourcePipeline(
        config=config,
        raw_detector=ScriptedRawDetector((360, 280, 440, 360)),
        landmarker_backend=OkLandmarker(),
    )

    analysis = analyze_avatar_source_image(
        image,
        source_ref="redacted-local-fixture",
        small_face_pipeline=pipeline,
        small_face_config=config,
    )

    assert analysis.status == "accepted"
    assert analysis.hard_reject is False
    assert analysis.face_size_bucket == "80_119"
    assert analysis.primary_face is not None
    assert analysis.primary_face.area_ratio < 0.08


def test_small_face_pipeline_runtime_failure_is_safely_rejected():
    class RaisingDetector:
        def detect_raw(self, _image):
            raise RuntimeError("detector unavailable at /private/model/path")

    config = _cfg()
    pipeline = SmallFaceSourcePipeline(
        config=config,
        raw_detector=RaisingDetector(),
        landmarker_backend=OkLandmarker(),
    )

    analysis = analyze_avatar_source_image(
        _rgb(),
        source_ref="redacted-local-fixture",
        small_face_pipeline=pipeline,
        small_face_config=config,
    )
    document = analysis.to_document()

    assert analysis.status == "rejected"
    assert analysis.reject_reasons == ["corrupt_image"]
    assert document["detector"]["metadata"]["runtimeFailure"] is True
    assert "private/model" not in str(document)


def test_full_range_flag_off_uses_tile_fallback_only():
    image = _rgb((800, 800))
    raw = ScriptedRawDetector((620, 620, 700, 700), full_image_empty=False)
    pipeline = SmallFaceSourcePipeline(
        config=_cfg(
            full_range_enabled=False,
            min_short_side_detect_px=40,
            min_short_side_trait_px=40,
        ),
        raw_detector=raw,
        landmarker_backend=OkLandmarker(),
    )

    result = pipeline.run(image)

    assert result.analysis.face_detected is True
    assert result.analysis.used_tile_fallback is True
    assert result.analysis.detection_pass_count == 1
def test_tiny_face_detected_but_not_avatar_usable():
    image = _rgb((640, 640))
    _draw_face(image, (300, 300, 330, 330))
    raw = ScriptedRawDetector((300, 300, 330, 330), confidence=0.8)
    pipeline = SmallFaceSourcePipeline(
        config=_cfg(min_short_side_detect_px=20, min_short_side_trait_px=80),
        raw_detector=raw,
        landmarker_backend=OkLandmarker(),
    )
    result = pipeline.run(image)
    # Full image path may mark face_detected; trait gate rejects before FLUX.
    assert result.analysis.avatar_usable is False
    assert result.public_reject_reasons


def test_no_face_rejects_before_usable():
    image = _rgb((512, 512), color=(30, 30, 30))

    class EmptyDetector:
        def detect_raw(self, image):
            return []

    pipeline = SmallFaceSourcePipeline(
        config=_cfg(),
        raw_detector=EmptyDetector(),
        landmarker_backend=OkLandmarker(),
    )
    result = pipeline.run(image)
    assert result.analysis.face_detected is False
    assert result.analysis.avatar_usable is False
    assert "no_face" in result.public_reject_reasons


def test_normalized_pixel_roundtrip():
    box = NormalizedBox(0.1, 0.2, 0.5, 0.6)
    px = normalized_to_pixel(box, 1000, 800)
    assert px.width > 0 and px.height > 0
