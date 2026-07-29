import io
import sys
from types import SimpleNamespace
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
    DeterministicFallbackFaceDetector,
    MediaPipeFaceDetector,
    redact_source_ref,
)
import avatar_generation.analysis.detectors as detectors  # noqa: E402
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


def test_two_primary_sized_faces_are_hard_rejected():
    face = FaceDetection(bbox=(0.2, 0.2, 0.35, 0.35), confidence=0.95)
    result = _analyze([face, face])
    doc = result.to_document()

    assert doc["status"] == "rejected"
    assert doc["rejectReasons"] == ["multi_face_primary"]
    assert doc["face"]["count"] == 2
    assert doc["largeSecondaryFaceCount"] == 1
    assert doc["backgroundFaceRisk"] in {
        "large_secondary_face",
        "ambiguous_primary_face",
    }


def test_clear_primary_face_with_small_background_face_is_accepted():
    primary = FaceDetection(
        bbox=(0.24, 0.14, 0.48, 0.52),
        confidence=0.96,
        broad_traits={"face_shape": "oval"},
    )
    background = FaceDetection(bbox=(0.82, 0.16, 0.07, 0.07), confidence=0.78)

    result = _analyze([background, primary])
    doc = result.to_document()

    assert doc["status"] == "accepted"
    assert doc["hardReject"] is False
    assert doc["rejectReasons"] == []
    assert doc["face"]["count"] == 2
    assert doc["face"]["areaRatio"] == primary.area_ratio
    assert "primaryFaceBbox" not in doc
    assert doc["primaryFaceConfidence"] == 0.96
    assert doc["secondaryFaceCount"] == 1
    assert doc["largeSecondaryFaceCount"] == 0
    assert doc["backgroundFaceRisk"] == "secondary_background_face"
    assert doc["backgroundNeutralizationRequired"] is True
    assert result.broad_trait_hints == {"face_shape": "oval"}


def test_ambiguous_primary_face_is_hard_rejected_when_score_margin_is_small():
    config = SourceSafetyConfig(
        min_face_area_ratio=0.04,
        primary_face_min_score_margin=0.20,
        reject_large_secondary_face=False,
    )
    left = FaceDetection(bbox=(0.18, 0.2, 0.28, 0.32), confidence=0.92)
    right = FaceDetection(bbox=(0.54, 0.2, 0.28, 0.32), confidence=0.91)

    doc = _analyze([left, right], config=config).to_document()

    assert doc["status"] == "rejected"
    assert doc["rejectReasons"] == ["ambiguous_primary_face"]
    assert doc["backgroundFaceRisk"] == "ambiguous_primary_face"


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


def test_source_safety_config_reads_mediapipe_runtime_envs(monkeypatch):
    monkeypatch.setenv("AVATAR_MEDIAPIPE_FACE_LANDMARKER_MODEL_PATH", "/models/face.task")
    monkeypatch.setenv("AVATAR_MEDIAPIPE_ENABLED", "false")
    monkeypatch.setenv("AVATAR_MEDIAPIPE_OUTPUT_BLENDSHAPES", "true")
    monkeypatch.setenv("AVATAR_MEDIAPIPE_NUM_FACES", "3")
    monkeypatch.setenv("AVATAR_MEDIAPIPE_MIN_DETECTION_CONFIDENCE", "0.72")
    monkeypatch.setenv("AVATAR_MEDIAPIPE_MIN_PRESENCE_CONFIDENCE", "0.64")
    monkeypatch.setenv("AVATAR_MEDIAPIPE_FAIL_CLOSED_IN_PRODUCTION", "true")
    monkeypatch.setenv("AVATAR_PRIMARY_FACE_MIN_SCORE_MARGIN", "0.31")
    monkeypatch.setenv("AVATAR_PRIMARY_FACE_MIN_RELATIVE_AREA", "0.06")
    monkeypatch.setenv("AVATAR_ALLOW_SMALL_BACKGROUND_FACES_IF_REMOVED", "false")
    monkeypatch.setenv("AVATAR_REJECT_LARGE_SECONDARY_FACE", "false")

    config = SourceSafetyConfig.from_env()

    assert config.mediapipe_face_landmarker_model_path == "/models/face.task"
    assert config.mediapipe_enabled is False
    assert config.mediapipe_output_blendshapes is True
    assert config.mediapipe_num_faces == 3
    assert config.mediapipe_min_detection_confidence == 0.72
    assert config.mediapipe_min_presence_confidence == 0.64
    assert config.mediapipe_fail_closed_in_production is True
    assert config.primary_face_min_score_margin == 0.31
    assert config.primary_face_min_relative_area == 0.06
    assert config.allow_small_background_faces_if_removed is False
    assert config.reject_large_secondary_face is False


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


def test_mediapipe_detector_uses_public_solution_import(monkeypatch):
    fake_face_detection = SimpleNamespace(FaceDetection=object)
    fake_mediapipe = SimpleNamespace(
        solutions=SimpleNamespace(face_detection=fake_face_detection)
    )
    monkeypatch.setitem(sys.modules, "mediapipe", fake_mediapipe)

    assert MediaPipeFaceDetector.is_available() is True
    detector = MediaPipeFaceDetector(min_detection_confidence=0.6)

    assert detector._mp_face_detection is fake_face_detection


def test_check_mediapipe_available_accepts_tasks_face_runtime(monkeypatch):
    fake_mediapipe = SimpleNamespace(
        tasks=SimpleNamespace(
            BaseOptions=object,
            vision=SimpleNamespace(
                FaceLandmarker=object,
                FaceLandmarkerOptions=object,
                RunningMode=SimpleNamespace(IMAGE="image"),
            ),
        )
    )
    monkeypatch.setitem(sys.modules, "mediapipe", fake_mediapipe)

    assert detectors.check_mediapipe_available() is True


def test_mediapipe_detector_uses_face_landmarker_tasks_api(monkeypatch, tmp_path):
    class FakeBaseOptions:
        def __init__(self, *, model_asset_path):
            self.model_asset_path = model_asset_path

    class FakeFaceLandmarkerOptions:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeFaceLandmarker:
        options = None

        @classmethod
        def create_from_options(cls, options):
            cls.options = options
            return cls()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def detect(self, image):
            return SimpleNamespace(
                face_landmarks=[
                    [SimpleNamespace(x=0.20, y=0.25) for _ in range(478)]
                ],
                face_blendshapes=[
                    [
                        SimpleNamespace(category_name="mouthSmileLeft", score=0.9),
                        SimpleNamespace(category_name="mouthSmileRight", score=0.9),
                    ]
                ],
            )

    class FakeImage:
        def __init__(self, *, image_format, data):
            self.image_format = image_format
            self.data = data

    fake_mediapipe = SimpleNamespace(
        __version__="0.10.fake",
        Image=FakeImage,
        ImageFormat=SimpleNamespace(SRGB="srgb"),
        tasks=SimpleNamespace(
            BaseOptions=FakeBaseOptions,
            vision=SimpleNamespace(
                FaceLandmarker=FakeFaceLandmarker,
                FaceLandmarkerOptions=FakeFaceLandmarkerOptions,
                RunningMode=SimpleNamespace(IMAGE="image"),
            ),
        ),
    )
    monkeypatch.setitem(sys.modules, "mediapipe", fake_mediapipe)
    model_path = tmp_path / "face.task"
    model_path.write_bytes(b"fake task model")

    config = SourceSafetyConfig(
        mediapipe_face_landmarker_model_path=str(model_path),
        mediapipe_output_blendshapes=True,
        mediapipe_num_faces=2,
        mediapipe_min_detection_confidence=0.72,
        mediapipe_min_presence_confidence=0.64,
    )
    detector = MediaPipeFaceDetector.from_config(config)
    fake_landmarks = [
        SimpleNamespace(x=0.20, y=0.25),
        SimpleNamespace(x=0.70, y=0.25),
        SimpleNamespace(x=0.70, y=0.80),
        SimpleNamespace(x=0.20, y=0.80),
    ]
    fake_landmarks.extend(SimpleNamespace(x=0.45, y=0.50) for _ in range(474))
    monkeypatch.setattr(
        FakeFaceLandmarker,
        "detect",
        lambda self, image: SimpleNamespace(
            face_landmarks=[fake_landmarks],
            face_blendshapes=[
                [
                    SimpleNamespace(category_name="mouthSmileLeft", score=0.9),
                    SimpleNamespace(category_name="mouthSmileRight", score=0.9),
                ]
            ],
        ),
    )
    result = detector.detect(Image.open(io.BytesIO(_image_bytes())))

    assert result.provider == "mediapipe"
    assert result.provider_version == "0.10.fake"
    assert result.faces[0].bbox == (0.2, 0.25, 0.5, 0.55)
    assert result.faces[0].landmarks is None
    assert result.faces[0].broad_traits["mouth_expression"] == "subtle_smile"
    assert result.faces[0].blendshape_categories == {"blendshapes": "available"}
    assert result.metadata == {
        "runtime": "tasks_face",
        "modelConfigured": True,
        "modelAvailable": True,
        "maxFaces": 2,
        "blendshapesRequested": True,
        "blendshapeFaceCount": 1,
    }
    assert FakeFaceLandmarker.options.kwargs["num_faces"] == 2
    assert FakeFaceLandmarker.options.kwargs["min_face_detection_confidence"] == 0.72
    assert FakeFaceLandmarker.options.kwargs["min_face_presence_confidence"] == 0.64
    assert FakeFaceLandmarker.options.kwargs["output_face_blendshapes"] is True


def test_build_default_face_detector_honors_mediapipe_disable(monkeypatch):
    def fail_if_called(cls):
        raise AssertionError("mediapipe availability should not be checked")

    monkeypatch.setattr(MediaPipeFaceDetector, "is_available", classmethod(fail_if_called))
    monkeypatch.setattr(
        detectors.OpenCvHaarFaceDetector,
        "is_available",
        classmethod(lambda cls: False),
    )

    detector = detectors.build_default_face_detector(
        SourceSafetyConfig(mediapipe_enabled=False)
    )

    assert isinstance(detector, DeterministicFallbackFaceDetector)


def test_build_default_face_detector_fail_closed_skips_opencv(monkeypatch):
    monkeypatch.setattr(
        MediaPipeFaceDetector,
        "is_available",
        classmethod(lambda cls: False),
    )

    def fail_if_called(cls):
        raise AssertionError("fail-closed mode should skip OpenCV fallback")

    monkeypatch.setattr(
        detectors.OpenCvHaarFaceDetector,
        "is_available",
        classmethod(fail_if_called),
    )

    detector = detectors.build_default_face_detector(
        SourceSafetyConfig(mediapipe_fail_closed_in_production=True)
    )

    assert isinstance(detector, DeterministicFallbackFaceDetector)


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
