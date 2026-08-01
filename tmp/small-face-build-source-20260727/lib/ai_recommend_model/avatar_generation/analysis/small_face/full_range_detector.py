from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import List, Optional, Protocol, Sequence

from PIL import Image

from .config import SmallFacePipelineConfig
from .geometry import enrich_detection
from .types import InternalFaceDetection, NormalizedBox

logger = logging.getLogger(__name__)

_PROCESS_DETECTOR_LOCK = threading.Lock()
_PROCESS_DETECTOR = None
_PROCESS_DETECTOR_PATH: Optional[str] = None


class RawFaceDetector(Protocol):
    """Returns detections as (xywh_normalized, confidence, keypoints)."""

    def detect_raw(
        self, image: Image.Image
    ) -> Sequence[tuple[tuple[float, float, float, float], float, tuple]]:
        ...


class FullRangeFaceDetector:
    """MediaPipe Tasks BlazeFace full-range adapter with process-level reuse."""

    provider_name = "mediapipe_tasks_face_detector"

    def __init__(
        self,
        config: SmallFacePipelineConfig,
        *,
        raw_detector: Optional[RawFaceDetector] = None,
    ) -> None:
        self._config = config
        self._raw_detector = raw_detector
        self._local_landmarker = None

    def detect(
        self,
        image: Image.Image,
        *,
        min_confidence: Optional[float] = None,
        detector_pass: str = "full_image",
        tile_id: Optional[str] = None,
    ) -> List[InternalFaceDetection]:
        threshold = (
            self._config.primary_min_confidence
            if min_confidence is None
            else float(min_confidence)
        )
        width, height = image.size
        raw_items = self._detect_raw(image)
        faces: List[InternalFaceDetection] = []
        for xywh, confidence, keypoints in raw_items:
            if confidence < threshold:
                continue
            x, y, w, h = xywh
            box = NormalizedBox(x, y, x + w, y + h).clamp()
            faces.append(
                enrich_detection(
                    bbox_normalized=box,
                    confidence=confidence,
                    image_width=width,
                    image_height=height,
                    detector_pass=detector_pass,
                    tile_id=tile_id,
                    keypoints_normalized=tuple(
                        (float(px), float(py)) for px, py in keypoints
                    ),
                    image=image,
                )
            )
        return faces

    def _detect_raw(
        self, image: Image.Image
    ) -> Sequence[tuple[tuple[float, float, float, float], float, tuple]]:
        if self._raw_detector is not None:
            return self._raw_detector.detect_raw(image)
        detector = self._get_or_create_tasks_detector()
        return detector(image)

    def _get_or_create_tasks_detector(self):
        global _PROCESS_DETECTOR, _PROCESS_DETECTOR_PATH
        model_path = self._config.face_detect_model_path
        if not model_path or not Path(model_path).is_file():
            raise RuntimeError(
                "AVATAR_FACE_DETECT_MODEL_PATH missing or not a file; "
                "full-range FaceDetector cannot start"
            )
        with _PROCESS_DETECTOR_LOCK:
            if _PROCESS_DETECTOR is not None and _PROCESS_DETECTOR_PATH == model_path:
                return _PROCESS_DETECTOR
            _PROCESS_DETECTOR = _build_tasks_face_detector_callable(model_path)
            _PROCESS_DETECTOR_PATH = model_path
            return _PROCESS_DETECTOR


def _build_tasks_face_detector_callable(model_path: str):
    import mediapipe as mp  # type: ignore[import-not-found]
    import numpy as np

    try:
        from mediapipe.tasks import python as mp_tasks  # type: ignore[import-not-found]
        from mediapipe.tasks.python import vision  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - environment specific
        raise RuntimeError("MediaPipe Tasks FaceDetector API unavailable") from exc

    if not hasattr(vision, "FaceDetector"):
        raise RuntimeError("mediapipe.tasks.python.vision.FaceDetector is unavailable")

    options = vision.FaceDetectorOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.IMAGE,
        min_detection_confidence=0.01,
    )
    # Keep one long-lived detector instance for the process.
    detector = vision.FaceDetector.create_from_options(options)

    def _detect(image: Image.Image):
        rgb = image.convert("RGB")
        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=np.asarray(rgb),
        )
        result = detector.detect(mp_image)
        items = []
        for detection in getattr(result, "detections", None) or []:
            bbox = detection.bounding_box
            width = max(1, rgb.size[0])
            height = max(1, rgb.size[1])
            x = float(bbox.origin_x) / width
            y = float(bbox.origin_y) / height
            w = float(bbox.width) / width
            h = float(bbox.height) / height
            score = 0.0
            if detection.categories:
                score = float(detection.categories[0].score or 0.0)
            keypoints = []
            for kp in getattr(detection, "keypoints", None) or []:
                keypoints.append((float(getattr(kp, "x", 0.0)), float(getattr(kp, "y", 0.0))))
            items.append(((x, y, w, h), score, tuple(keypoints)))
        return items

    return _detect


def reset_process_face_detector_for_tests() -> None:
    global _PROCESS_DETECTOR, _PROCESS_DETECTOR_PATH
    with _PROCESS_DETECTOR_LOCK:
        _PROCESS_DETECTOR = None
        _PROCESS_DETECTOR_PATH = None


__all__ = [
    "FullRangeFaceDetector",
    "RawFaceDetector",
    "reset_process_face_detector_for_tests",
]
