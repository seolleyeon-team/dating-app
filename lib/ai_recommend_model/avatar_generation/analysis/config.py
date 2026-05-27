from __future__ import annotations

from dataclasses import dataclass
import os

DEFAULT_SOURCE_ANALYSIS_VERSION = "avatar_source_analysis_v1"
DEFAULT_MIN_FACE_AREA_RATIO = 0.08
DEFAULT_SEVERE_OCCLUSION_THRESHOLD = 0.60
DEFAULT_MEDIAPIPE_MIN_DETECTION_CONFIDENCE = 0.60
DEFAULT_MEDIAPIPE_MIN_PRESENCE_CONFIDENCE = 0.60
DEFAULT_MEDIAPIPE_NUM_FACES = 2
DEFAULT_PRIMARY_FACE_MIN_SCORE_MARGIN = 0.20
DEFAULT_PRIMARY_FACE_MIN_RELATIVE_AREA = 0.04
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


def _env_bool(name: str, fallback: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return fallback


def _env_int(name: str, fallback: int, *, minimum: int = 1, maximum: int = 100) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        return fallback
    return max(minimum, min(maximum, value))


def _env_text(name: str, fallback: str) -> str:
    return os.environ.get(name, "").strip() or fallback


@dataclass(frozen=True)
class SourceSafetyConfig:
    analysis_version: str = DEFAULT_SOURCE_ANALYSIS_VERSION
    min_face_area_ratio: float = DEFAULT_MIN_FACE_AREA_RATIO
    severe_occlusion_threshold: float = DEFAULT_SEVERE_OCCLUSION_THRESHOLD
    face_detector_provider: str = "mediapipe"
    mediapipe_enabled: bool = True
    mediapipe_face_landmarker_model_path: str = ""
    mediapipe_output_blendshapes: bool = True
    mediapipe_num_faces: int = DEFAULT_MEDIAPIPE_NUM_FACES
    mediapipe_min_detection_confidence: float = (
        DEFAULT_MEDIAPIPE_MIN_DETECTION_CONFIDENCE
    )
    mediapipe_min_presence_confidence: float = (
        DEFAULT_MEDIAPIPE_MIN_PRESENCE_CONFIDENCE
    )
    mediapipe_fail_closed_in_production: bool = True
    primary_face_min_score_margin: float = DEFAULT_PRIMARY_FACE_MIN_SCORE_MARGIN
    primary_face_min_relative_area: float = DEFAULT_PRIMARY_FACE_MIN_RELATIVE_AREA
    allow_small_background_faces_if_removed: bool = True
    reject_large_secondary_face: bool = True

    @property
    def mediapipe_landmarker_model_path(self) -> str:
        return self.mediapipe_face_landmarker_model_path

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
            face_detector_provider=_env_text(
                "AVATAR_FACE_DETECTOR_PROVIDER",
                "mediapipe",
            ),
            mediapipe_enabled=_env_bool("AVATAR_MEDIAPIPE_ENABLED", True),
            mediapipe_face_landmarker_model_path=_env_text(
                "AVATAR_MEDIAPIPE_FACE_LANDMARKER_MODEL_PATH",
                "",
            ),
            mediapipe_output_blendshapes=_env_bool(
                "AVATAR_MEDIAPIPE_OUTPUT_BLENDSHAPES",
                True,
            ),
            mediapipe_num_faces=_env_int(
                "AVATAR_MEDIAPIPE_NUM_FACES",
                DEFAULT_MEDIAPIPE_NUM_FACES,
                minimum=1,
                maximum=5,
            ),
            mediapipe_min_detection_confidence=_env_float_any(
                (
                    "AVATAR_MEDIAPIPE_MIN_DETECTION_CONFIDENCE",
                    "AVATAR_FACE_DETECTOR_MIN_CONFIDENCE",
                    "AVATAR_SOURCE_MEDIAPIPE_MIN_DETECTION_CONFIDENCE",
                ),
                DEFAULT_MEDIAPIPE_MIN_DETECTION_CONFIDENCE,
            ),
            mediapipe_min_presence_confidence=_env_float(
                "AVATAR_MEDIAPIPE_MIN_PRESENCE_CONFIDENCE",
                DEFAULT_MEDIAPIPE_MIN_PRESENCE_CONFIDENCE,
            ),
            mediapipe_fail_closed_in_production=_env_bool(
                "AVATAR_MEDIAPIPE_FAIL_CLOSED_IN_PRODUCTION",
                True,
            ),
            primary_face_min_score_margin=_env_float(
                "AVATAR_PRIMARY_FACE_MIN_SCORE_MARGIN",
                DEFAULT_PRIMARY_FACE_MIN_SCORE_MARGIN,
            ),
            primary_face_min_relative_area=_env_float(
                "AVATAR_PRIMARY_FACE_MIN_RELATIVE_AREA",
                DEFAULT_PRIMARY_FACE_MIN_RELATIVE_AREA,
            ),
            allow_small_background_faces_if_removed=_env_bool(
                "AVATAR_ALLOW_SMALL_BACKGROUND_FACES_IF_REMOVED",
                True,
            ),
            reject_large_secondary_face=_env_bool(
                "AVATAR_REJECT_LARGE_SECONDARY_FACE",
                True,
            ),
        )
