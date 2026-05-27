from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Protocol, Sequence

from PIL import Image

from avatar_generation.trait_card.mediapipe_binning import build_broad_trait_hints

from .config import SourceSafetyConfig
from .schema import FaceDetection, FaceDetectorResult

logger = logging.getLogger(__name__)


def _exception_detail(exc: Exception) -> str:
    return str(exc).splitlines()[0][:160]


def _has_solution_face_detection(mp: object) -> bool:
    solutions = getattr(mp, "solutions", None)
    return solutions is not None and hasattr(solutions, "face_detection")


def _has_tasks_face_landmarker(mp: object) -> bool:
    if _load_tasks_face_landmarker_api(mp) is not None:
        return True
    return False


def _load_tasks_face_landmarker_api(mp: object) -> tuple[object, object] | None:
    try:
        from mediapipe.tasks import python as mp_tasks  # type: ignore[import-not-found]
        from mediapipe.tasks.python import vision  # type: ignore[import-not-found]

        if (
            hasattr(mp_tasks, "BaseOptions")
            and hasattr(vision, "FaceLandmarker")
            and hasattr(vision, "FaceLandmarkerOptions")
            and hasattr(vision, "RunningMode")
        ):
            return mp_tasks, vision
    except Exception:
        pass

    tasks = getattr(mp, "tasks", None)
    vision = getattr(tasks, "vision", None)
    if (
        tasks is not None
        and vision is not None
        and hasattr(tasks, "BaseOptions")
        and hasattr(vision, "FaceLandmarker")
        and hasattr(vision, "FaceLandmarkerOptions")
        and hasattr(vision, "RunningMode")
    ):
        return tasks, vision
    return None


def check_mediapipe_available() -> bool:
    try:
        import mediapipe as mp  # type: ignore[import-not-found]
        import numpy  # noqa: F401

        if not _has_solution_face_detection(mp) and not _has_tasks_face_landmarker(mp):
            raise RuntimeError(
                "MediaPipe has neither solutions.face_detection nor "
                "tasks.vision.FaceLandmarker available"
            )
        return True
    except Exception as exc:
        logger.warning(
            "MediaPipe face detector unavailable: %s: %s",
            type(exc).__name__,
            _exception_detail(exc),
        )
        return False


class FaceDetector(Protocol):
    provider_name: str

    def detect(self, image: Image.Image) -> FaceDetectorResult:
        ...


class DeterministicFallbackFaceDetector:
    provider_name = "deterministic_fallback"

    def detect(self, image: Image.Image) -> FaceDetectorResult:
        width, height = image.size
        return FaceDetectorResult(
            provider=self.provider_name,
            image_width=width,
            image_height=height,
            faces=[],
        )


class StaticFaceDetector:
    provider_name = "static"

    def __init__(
        self,
        faces: Sequence[FaceDetection],
        *,
        provider_name: Optional[str] = None,
    ) -> None:
        self._faces = list(faces)
        if provider_name:
            self.provider_name = provider_name

    def detect(self, image: Image.Image) -> FaceDetectorResult:
        width, height = image.size
        return FaceDetectorResult(
            provider=self.provider_name,
            image_width=width,
            image_height=height,
            faces=list(self._faces),
        )


class MediaPipeFaceDetector:
    provider_name = "mediapipe"

    def __init__(
        self,
        *,
        min_detection_confidence: float,
        face_landmarker_model_path: str = "",
        output_blendshapes: bool = False,
        num_faces: int = 2,
        min_presence_confidence: float = 0.5,
    ) -> None:
        import mediapipe as mp  # type: ignore[import-not-found]

        self._mp = mp
        self._mp_face_detection = None
        self._provider_version = getattr(mp, "__version__", None)
        self._min_detection_confidence = min_detection_confidence
        self._face_landmarker_model_path = face_landmarker_model_path
        self._face_landmarker_model_available = bool(
            face_landmarker_model_path and Path(face_landmarker_model_path).is_file()
        )
        self._output_blendshapes = output_blendshapes
        self._num_faces = max(1, int(num_faces))
        self._min_presence_confidence = min_presence_confidence
        self._runtime = "solutions_face_detection"

        if face_landmarker_model_path:
            if self._face_landmarker_model_available and _load_tasks_face_landmarker_api(mp) is not None:
                self._runtime = "tasks_face"
                return
            logger.warning(
                "MediaPipe Face Landmarker Tasks API unavailable; falling back to "
                "solutions.face_detection when possible."
            )

        if not _has_solution_face_detection(mp):
            raise RuntimeError("mediapipe.solutions.face_detection is unavailable")
        self._mp_face_detection = mp.solutions.face_detection

    @classmethod
    def from_config(cls, config: SourceSafetyConfig) -> "MediaPipeFaceDetector":
        return cls(
            min_detection_confidence=config.mediapipe_min_detection_confidence,
            face_landmarker_model_path=(
                config.mediapipe_face_landmarker_model_path
            ),
            output_blendshapes=config.mediapipe_output_blendshapes,
            num_faces=config.mediapipe_num_faces,
            min_presence_confidence=config.mediapipe_min_presence_confidence,
        )

    @classmethod
    def is_available(cls) -> bool:
        return check_mediapipe_available()

    def detect(self, image: Image.Image) -> FaceDetectorResult:
        if self._runtime == "tasks_face":
            return self._detect_with_face_landmarker(image)
        return self._detect_with_solution(image)

    def _detect_with_solution(self, image: Image.Image) -> FaceDetectorResult:
        import numpy as np

        if self._mp_face_detection is None:
            raise RuntimeError("MediaPipe solution face detector is not initialized")

        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        with self._mp_face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=self._min_detection_confidence,
        ) as detector:
            result = detector.process(np.asarray(rgb_image))

        faces = []
        for detection in result.detections or []:
            relative_box = detection.location_data.relative_bounding_box
            score = None
            if detection.score:
                score = float(detection.score[0])
            faces.append(
                FaceDetection(
                    bbox=(
                        float(relative_box.xmin),
                        float(relative_box.ymin),
                        float(relative_box.width),
                        float(relative_box.height),
                    ),
                    confidence=score,
                )
            )
        return FaceDetectorResult(
            provider=self.provider_name,
            provider_version=self._provider_version,
            image_width=width,
            image_height=height,
            faces=faces,
            model_availability={
                "mediapipe": "available",
                "faceDetector": "available",
                "faceTaskModel": (
                    "available"
                    if self._face_landmarker_model_available
                    else "not_configured"
                ),
            },
            metadata={"runtime": "solutions_face_detection"},
        )

    def _detect_with_face_landmarker(self, image: Image.Image) -> FaceDetectorResult:
        import numpy as np

        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        tasks_api = _load_tasks_face_landmarker_api(self._mp)
        if tasks_api is None:
            raise RuntimeError("MediaPipe Face Landmarker Tasks API is unavailable")
        mp_tasks, vision = tasks_api
        options = vision.FaceLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(
                model_asset_path=self._face_landmarker_model_path,
            ),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=self._num_faces,
            min_face_detection_confidence=self._min_detection_confidence,
            min_face_presence_confidence=self._min_presence_confidence,
            output_face_blendshapes=self._output_blendshapes,
        )
        mp_image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=np.asarray(rgb_image),
        )
        with vision.FaceLandmarker.create_from_options(options) as landmarker:
            result = landmarker.detect(mp_image)

        blendshape_faces = getattr(result, "face_blendshapes", []) or []
        faces = []
        for index, landmarks in enumerate(getattr(result, "face_landmarks", []) or []):
            if not landmarks:
                continue
            bbox = _bbox_from_landmarks(landmarks)
            blendshape_scores = _blendshape_scores(
                blendshape_faces[index] if index < len(blendshape_faces) else []
            )
            faces.append(
                FaceDetection(
                    bbox=bbox,
                    confidence=None,
                    broad_traits=build_broad_trait_hints(
                        face_bbox=bbox,
                        landmarks=landmarks,
                        blendshapes=blendshape_scores,
                    ),
                    blendshape_categories={
                        "blendshapes": "available"
                        if blendshape_scores
                        else "unavailable",
                    },
                )
            )
        return FaceDetectorResult(
            provider=self.provider_name,
            provider_version=self._provider_version,
            image_width=width,
            image_height=height,
            faces=faces,
            model_availability={
                "mediapipe": "available",
                "faceDetector": "available",
                "faceTaskModel": "available",
            },
            metadata={
                "runtime": "tasks_face",
                "modelConfigured": True,
                "modelAvailable": self._face_landmarker_model_available,
                "maxFaces": self._num_faces,
                "blendshapesRequested": self._output_blendshapes,
                "blendshapeFaceCount": len(blendshape_faces),
            },
        )


class OpenCvHaarFaceDetector:
    provider_name = "opencv_haar"

    def __init__(self) -> None:
        import cv2  # type: ignore[import-not-found]

        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        classifier = cv2.CascadeClassifier(cascade_path)
        if classifier.empty():
            raise RuntimeError("OpenCV face cascade was not found.")
        self._cv2 = cv2
        self._classifier = classifier

    @classmethod
    def is_available(cls) -> bool:
        try:
            import cv2  # type: ignore[import-not-found]  # noqa: F401

            return True
        except Exception as exc:
            detail = str(exc).splitlines()[0][:160]
            logger.warning(
                "OpenCV Haar face detector unavailable: %s: %s",
                type(exc).__name__,
                detail,
            )
            return False

    def detect(self, image: Image.Image) -> FaceDetectorResult:
        import numpy as np

        rgb_image = image.convert("RGB")
        width, height = rgb_image.size
        gray = self._cv2.cvtColor(np.asarray(rgb_image), self._cv2.COLOR_RGB2GRAY)
        min_side = max(24, int(min(width, height) * 0.08))
        boxes = self._classifier.detectMultiScale(
            gray,
            scaleFactor=1.05,
            minNeighbors=3,
            minSize=(min_side, min_side),
        )
        faces = [
            FaceDetection(
                bbox=(
                    float(x) / float(width),
                    float(y) / float(height),
                    float(w) / float(width),
                    float(h) / float(height),
                ),
                confidence=None,
            )
            for (x, y, w, h) in boxes
        ]
        faces.sort(key=lambda face: face.bbox[2] * face.bbox[3], reverse=True)
        return FaceDetectorResult(
            provider=self.provider_name,
            provider_version=None,
            image_width=width,
            image_height=height,
            faces=faces,
        )


def build_default_face_detector(
    config: Optional[SourceSafetyConfig] = None,
) -> FaceDetector:
    source_config = config or SourceSafetyConfig.from_env()
    if not source_config.mediapipe_enabled:
        if source_config.mediapipe_fail_closed_in_production:
            return DeterministicFallbackFaceDetector()
    elif MediaPipeFaceDetector.is_available():
        try:
            return MediaPipeFaceDetector.from_config(source_config)
        except Exception as exc:
            logger.warning(
                "MediaPipe face detector init failed: %s: %s",
                type(exc).__name__,
                _exception_detail(exc),
            )
            if source_config.mediapipe_fail_closed_in_production:
                return DeterministicFallbackFaceDetector()
    elif source_config.mediapipe_fail_closed_in_production:
        return DeterministicFallbackFaceDetector()

    if OpenCvHaarFaceDetector.is_available():
        try:
            return OpenCvHaarFaceDetector()
        except Exception as exc:
            logger.warning(
                "OpenCV Haar face detector init failed: %s: %s",
                type(exc).__name__,
                _exception_detail(exc),
            )
    return DeterministicFallbackFaceDetector()


def _bbox_from_landmarks(landmarks: Sequence[object]) -> tuple[float, float, float, float]:
    xs = [_clamp_relative(float(getattr(point, "x"))) for point in landmarks]
    ys = [_clamp_relative(float(getattr(point, "y"))) for point in landmarks]
    min_x = min(xs)
    min_y = min(ys)
    max_x = max(xs)
    max_y = max(ys)
    return (
        round(min_x, 6),
        round(min_y, 6),
        round(max(0.0, max_x - min_x), 6),
        round(max(0.0, max_y - min_y), 6),
    )


def _clamp_relative(value: float) -> float:
    return max(0.0, min(1.0, value))


def _blendshape_scores(categories: object) -> dict[str, float]:
    scores: dict[str, float] = {}
    for category in categories or []:
        name = getattr(category, "category_name", None)
        if not name:
            continue
        try:
            scores[str(name)] = float(getattr(category, "score", 0.0))
        except (TypeError, ValueError):
            continue
    return scores


__all__ = [
    "check_mediapipe_available",
    "DeterministicFallbackFaceDetector",
    "FaceDetector",
    "MediaPipeFaceDetector",
    "OpenCvHaarFaceDetector",
    "StaticFaceDetector",
    "build_default_face_detector",
]
