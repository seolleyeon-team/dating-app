from __future__ import annotations

import logging
from typing import Optional, Protocol, Sequence

from PIL import Image

from .config import SourceSafetyConfig
from .schema import FaceDetection, FaceDetectorResult

logger = logging.getLogger(__name__)


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

    def __init__(self, *, min_detection_confidence: float) -> None:
        from mediapipe.python.solutions import face_detection  # type: ignore[import-not-found]

        self._mp_face_detection = face_detection
        self._min_detection_confidence = min_detection_confidence

    @classmethod
    def from_config(cls, config: SourceSafetyConfig) -> "MediaPipeFaceDetector":
        return cls(
            min_detection_confidence=config.mediapipe_min_detection_confidence,
        )

    @classmethod
    def is_available(cls) -> bool:
        try:
            from mediapipe.python.solutions import face_detection  # noqa: F401
            import numpy  # noqa: F401

            return True
        except Exception as exc:
            detail = str(exc).splitlines()[0][:160]
            logger.warning(
                "MediaPipe face detector unavailable: %s: %s",
                type(exc).__name__,
                detail,
            )
            return False

    def detect(self, image: Image.Image) -> FaceDetectorResult:
        import numpy as np

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
            provider_version=None,
            image_width=width,
            image_height=height,
            faces=faces,
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
    if MediaPipeFaceDetector.is_available():
        try:
            return MediaPipeFaceDetector.from_config(source_config)
        except Exception as exc:
            detail = str(exc).splitlines()[0][:160]
            logger.warning(
                "MediaPipe face detector init failed: %s: %s",
                type(exc).__name__,
                detail,
            )
    if OpenCvHaarFaceDetector.is_available():
        try:
            return OpenCvHaarFaceDetector()
        except Exception as exc:
            detail = str(exc).splitlines()[0][:160]
            logger.warning(
                "OpenCV Haar face detector init failed: %s: %s",
                type(exc).__name__,
                detail,
            )
    return DeterministicFallbackFaceDetector()


__all__ = [
    "DeterministicFallbackFaceDetector",
    "FaceDetector",
    "MediaPipeFaceDetector",
    "OpenCvHaarFaceDetector",
    "StaticFaceDetector",
    "build_default_face_detector",
]
