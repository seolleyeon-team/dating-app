import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis import (  # noqa: E402
    FaceDetection,
    FaceDetectorResult,
    SourceSafetyConfig,
    analyze_avatar_source_image,
    redact_source_ref,
)
import avatar_generation.analysis.source_analyzer as source_analyzer  # noqa: E402


def _image_bytes() -> bytes:
    image = Image.new("RGB", (200, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((55, 40, 145, 130), fill=(238, 196, 170), outline="black", width=2)
    draw.ellipse((78, 75, 87, 84), fill="black")
    draw.ellipse((113, 75, 122, 84), fill="black")
    draw.arc((78, 82, 122, 114), start=15, end=165, fill="black", width=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class MockDetector:
    provider_name = "mock"

    def __init__(self, faces):
        self._faces = faces

    def detect(self, image):
        width, height = image.size
        return FaceDetectorResult(
            provider=self.provider_name,
            image_width=width,
            image_height=height,
            faces=list(self._faces),
        )


def _analyze(faces, *, data=None, config=None):
    return analyze_avatar_source_image(
        data if data is not None else _image_bytes(),
        source_ref="gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg",
        detector=MockDetector(faces),
        config=config,
    )


def test_no_face_is_hard_rejected():
    result = _analyze([])
    doc = result.to_document()

    assert doc["status"] == "rejected"
    assert doc["hardReject"] is True
    assert doc["rejectReasons"] == ["no_face"]
    assert doc["face"]["count"] == 0


def test_multiple_faces_are_hard_rejected():
    face = FaceDetection(bbox=(0.2, 0.2, 0.35, 0.35), confidence=0.95)
    result = _analyze([face, face])
    doc = result.to_document()

    assert doc["status"] == "rejected"
    assert doc["rejectReasons"] == ["multiple_faces"]
    assert doc["face"]["count"] == 2


def test_single_large_visible_face_is_accepted():
    result = _analyze([FaceDetection(bbox=(0.2, 0.15, 0.5, 0.5), confidence=0.97)])
    doc = result.to_document()

    assert doc["status"] == "accepted"
    assert doc["hardReject"] is False
    assert doc["rejectReasons"] == []
    assert doc["face"]["areaRatio"] == 0.25
    assert doc["face"]["occlusionScore"] is None


def test_too_small_face_and_severe_occlusion_are_hard_rejected():
    config = SourceSafetyConfig(min_face_area_ratio=0.05, severe_occlusion_threshold=0.6)
    face = FaceDetection(
        bbox=(0.4, 0.4, 0.1, 0.1),
        confidence=0.8,
        occlusion_score=0.85,
    )
    result = _analyze([face], config=config)

    assert result.to_document()["rejectReasons"] == ["face_too_small", "severe_occlusion"]


def test_source_safety_default_min_face_ratio_matches_v3_policy():
    assert SourceSafetyConfig.from_env().min_face_area_ratio == 0.08


def test_corrupt_image_is_hard_rejected_without_detector_call():
    class ExplodingDetector:
        provider_name = "exploding"

        def detect(self, image):
            raise AssertionError("detector should not be called for corrupt images")

    result = analyze_avatar_source_image(
        b"not an image",
        source_ref="gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg",
        detector=ExplodingDetector(),
    )
    doc = result.to_document()

    assert doc["status"] == "rejected"
    assert doc["rejectReasons"] == ["corrupt_image"]
    assert doc["image"] == {"width": None, "height": None}


def test_detector_failure_uses_deterministic_fallback(monkeypatch):
    class RaisingDetector:
        provider_name = "raising"

        def detect(self, image):
            raise RuntimeError("detector failed")

    def explode_if_default_builder_is_reused(config):
        raise AssertionError("fallback should not retry provider discovery")

    monkeypatch.setattr(
        source_analyzer,
        "build_default_face_detector",
        explode_if_default_builder_is_reused,
    )

    result = source_analyzer.analyze_avatar_source_image(
        _image_bytes(),
        source_ref="gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg",
        detector=RaisingDetector(),
    )
    doc = result.to_document()

    assert doc["status"] == "rejected"
    assert doc["rejectReasons"] == ["no_face"]
    assert doc["detector"]["provider"] == "deterministic_fallback"


def test_schema_redacts_source_ref_and_does_not_persist_landmarks():
    face = FaceDetection(
        bbox=(0.2, 0.2, 0.5, 0.5),
        confidence=0.9,
        landmarks={"left_eye": (0.3, 0.4), "right_eye": (0.6, 0.4)},
    )
    doc = _analyze([face]).to_document()
    rendered = repr(doc).lower()

    assert doc["analysisVersion"] == "avatar_source_analysis_v1"
    assert doc["sourceRef"] == "gs://[redacted-avatar-source]"
    assert doc["detector"]["provider"] == "mock"
    assert "landmark" not in rendered
    assert "left_eye" not in rendered
    assert "seolleyeon-private-source-photos" not in rendered


def test_redact_source_ref_handles_urls_and_nested_values():
    value = {
        "sourcePhotoRefs": [
            "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg",
            "https://storage.googleapis.com/seolleyeon-private-source-photos/users/u1/source/src_002.jpg",
        ],
        "safe": "gs://seolleyeon-avatar-temp/users/u1/avatar/candidate.png",
    }

    assert redact_source_ref(value) == {
        "sourcePhotoRefs": [
            "gs://[redacted-avatar-source]",
            "[redacted-avatar-source-url]",
        ],
        "safe": "gs://seolleyeon-avatar-temp/users/u1/avatar/candidate.png",
    }
