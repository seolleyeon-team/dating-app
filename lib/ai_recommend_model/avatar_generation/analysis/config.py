from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_SOURCE_ANALYSIS_VERSION = "avatar_source_analysis_v1"
DEFAULT_MIN_FACE_AREA_RATIO = 0.08
DEFAULT_SEVERE_OCCLUSION_THRESHOLD = 0.60
DEFAULT_MEDIAPIPE_MIN_DETECTION_CONFIDENCE = 0.60
DEFAULT_REDACTED_GCS_SOURCE_REF = "gs://[redacted-avatar-source]"
DEFAULT_REDACTED_URL_SOURCE_REF = "[redacted-avatar-source-url]"


def _env_float(name: str, fallback: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        return float(raw)
    except ValueError:
        return fallback


def _env_float_any(names: tuple[str, ...], fallback: float) -> float:
    for name in names:
        if os.environ.get(name) is not None:
            return _env_float(name, fallback)
    return fallback


def _env_text(name: str, fallback: str) -> str:
    return os.environ.get(name, "").strip() or fallback


@dataclass(frozen=True)
class SourceSafetyConfig:
    analysis_version: str = DEFAULT_SOURCE_ANALYSIS_VERSION
    min_face_area_ratio: float = DEFAULT_MIN_FACE_AREA_RATIO
    severe_occlusion_threshold: float = DEFAULT_SEVERE_OCCLUSION_THRESHOLD
    mediapipe_min_detection_confidence: float = (
        DEFAULT_MEDIAPIPE_MIN_DETECTION_CONFIDENCE
    )

    @classmethod
    def from_env(cls) -> "SourceSafetyConfig":
        return cls(
            analysis_version=_env_text(
                "AVATAR_SOURCE_ANALYSIS_VERSION",
                DEFAULT_SOURCE_ANALYSIS_VERSION,
            ),
            min_face_area_ratio=_env_float_any(
                (
                    "AVATAR_FACE_MIN_RELATIVE_SIZE",
                    "AVATAR_SOURCE_MIN_FACE_AREA_RATIO",
                ),
                DEFAULT_MIN_FACE_AREA_RATIO,
            ),
            severe_occlusion_threshold=_env_float(
                "AVATAR_SOURCE_SEVERE_OCCLUSION_THRESHOLD",
                DEFAULT_SEVERE_OCCLUSION_THRESHOLD,
            ),
            mediapipe_min_detection_confidence=_env_float_any(
                (
                    "AVATAR_FACE_DETECTOR_MIN_CONFIDENCE",
                    "AVATAR_SOURCE_MEDIAPIPE_MIN_DETECTION_CONFIDENCE",
                ),
                DEFAULT_MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
            ),
        )
