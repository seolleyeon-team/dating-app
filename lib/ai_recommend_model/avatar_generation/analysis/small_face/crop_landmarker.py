from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

_PROCESS_LANDMARKER_LOCK = threading.Lock()
_PROCESS_LANDMARKER = None
_PROCESS_LANDMARKER_PATH: Optional[str] = None


class CropLandmarkerBackend(Protocol):
    def landmark(self, image: Image.Image) -> Tuple[bool, Any, Optional[str]]:
        """Return (ok, landmarks_or_none, reason_code)."""
        ...


class CropFaceLandmarker:
    """Run FaceLandmarker on the primary head-and-shoulders crop only."""

    def __init__(
        self,
        *,
        model_path: str = "",
        min_detection_confidence: float = 0.45,
        min_presence_confidence: float = 0.50,
        backend: Optional[CropLandmarkerBackend] = None,
    ) -> None:
        self._model_path = model_path
        self._min_detection_confidence = min_detection_confidence
        self._min_presence_confidence = min_presence_confidence
        self._backend = backend

    def run(self, crop_image: Image.Image) -> Tuple[bool, Any, Optional[str]]:
        if self._backend is not None:
            return self._backend.landmark(crop_image)
        try:
            landmarker = self._get_or_create()
            return landmarker(crop_image)
        except Exception as exc:
            logger.warning(
                "crop FaceLandmarker failed: %s",
                type(exc).__name__,
            )
            return False, None, "avatar_source_analysis_failed"

    def _get_or_create(self):
        global _PROCESS_LANDMARKER, _PROCESS_LANDMARKER_PATH
        if not self._model_path or not Path(self._model_path).is_file():
            raise RuntimeError("FaceLandmarker model path missing for crop analysis")
        with _PROCESS_LANDMARKER_LOCK:
            if (
                _PROCESS_LANDMARKER is not None
                and _PROCESS_LANDMARKER_PATH == self._model_path
            ):
                return _PROCESS_LANDMARKER
            _PROCESS_LANDMARKER = _build_crop_landmarker(
                self._model_path,
                min_detection_confidence=self._min_detection_confidence,
                min_presence_confidence=self._min_presence_confidence,
            )
            _PROCESS_LANDMARKER_PATH = self._model_path
            return _PROCESS_LANDMARKER


def _build_crop_landmarker(
    model_path: str,
    *,
    min_detection_confidence: float,
    min_presence_confidence: float,
):
    import mediapipe as mp  # type: ignore[import-not-found]
    import numpy as np

    from mediapipe.tasks import python as mp_tasks  # type: ignore[import-not-found]
    from mediapipe.tasks.python import vision  # type: ignore[import-not-found]

    options = vision.FaceLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=model_path),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=min_detection_confidence,
        min_face_presence_confidence=min_presence_confidence,
        output_face_blendshapes=False,
    )
    landmarker = vision.FaceLandmarker.create_from_options(options)

    def _run(image: Image.Image):
        rgb = image.convert("RGB")
        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=np.asarray(rgb),
        )
        result = landmarker.detect(mp_image)
        landmarks = getattr(result, "face_landmarks", None) or []
        if not landmarks or not landmarks[0]:
            return False, None, "avatar_source_landmarks_unstable"
        points = landmarks[0]
        xs = [float(getattr(p, "x", 0.0)) for p in points]
        ys = [float(getattr(p, "y", 0.0)) for p in points]
        if not xs or not ys:
            return False, None, "avatar_source_landmarks_unstable"
        # Landmarks should mostly stay inside the crop.
        outside = sum(1 for x, y in zip(xs, ys) if x < -0.05 or x > 1.05 or y < -0.05 or y > 1.05)
        if outside > max(5, int(0.2 * len(xs))):
            return False, None, "avatar_source_face_out_of_frame"
        return True, points, None

    return _run


def reset_process_crop_landmarker_for_tests() -> None:
    global _PROCESS_LANDMARKER, _PROCESS_LANDMARKER_PATH
    with _PROCESS_LANDMARKER_LOCK:
        _PROCESS_LANDMARKER = None
        _PROCESS_LANDMARKER_PATH = None


__all__ = [
    "CropFaceLandmarker",
    "CropLandmarkerBackend",
    "reset_process_crop_landmarker_for_tests",
]
