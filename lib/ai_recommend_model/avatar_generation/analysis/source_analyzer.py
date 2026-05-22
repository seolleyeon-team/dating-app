from __future__ import annotations

import io
from typing import BinaryIO, List, Optional, Sequence, Union

from PIL import Image

from .config import SourceSafetyConfig
from .detectors import (
    DeterministicFallbackFaceDetector,
    FaceDetector,
    build_default_face_detector,
)
from .redaction import redacted_source_ref
from .schema import FaceDetection, FaceDetectorResult, SourceAnalysisResult

ImageInput = Union[bytes, bytearray, memoryview, BinaryIO, Image.Image]

REJECT_NO_FACE = "no_face"
REJECT_MULTIPLE_FACES = "multiple_faces"
REJECT_FACE_TOO_SMALL = "face_too_small"
REJECT_SEVERE_OCCLUSION = "severe_occlusion"
REJECT_CORRUPT_IMAGE = "corrupt_image"

REJECT_REASON_ORDER = (
    REJECT_NO_FACE,
    REJECT_MULTIPLE_FACES,
    REJECT_FACE_TOO_SMALL,
    REJECT_SEVERE_OCCLUSION,
    REJECT_CORRUPT_IMAGE,
)


def analyze_avatar_source_image(
    image_data: ImageInput,
    *,
    source_ref: str = "",
    detector: Optional[FaceDetector] = None,
    config: Optional[SourceSafetyConfig] = None,
) -> SourceAnalysisResult:
    source_config = config or SourceSafetyConfig.from_env()
    redacted_ref = redacted_source_ref(source_ref)
    image = _load_image(image_data)
    if image is None:
        return _build_result(
            status="rejected",
            hard_reject=True,
            reject_reasons=[REJECT_CORRUPT_IMAGE],
            source_ref=redacted_ref,
            image_width=None,
            image_height=None,
            detector_result=None,
            analysis_version=source_config.analysis_version,
        )

    active_detector = detector or build_default_face_detector(source_config)
    try:
        detector_result = active_detector.detect(image)
    except Exception:
        detector_result = DeterministicFallbackFaceDetector().detect(image)

    reasons = _source_reject_reasons(detector_result.faces, source_config)
    return _build_result(
        status="rejected" if reasons else "accepted",
        hard_reject=bool(reasons),
        reject_reasons=reasons,
        source_ref=redacted_ref,
        image_width=detector_result.image_width,
        image_height=detector_result.image_height,
        detector_result=detector_result,
        analysis_version=source_config.analysis_version,
    )


def _load_image(image_data: ImageInput) -> Optional[Image.Image]:
    try:
        if isinstance(image_data, Image.Image):
            image = image_data.copy()
            image.load()
            return image.convert("RGB")
        if isinstance(image_data, memoryview):
            raw = image_data.tobytes()
        elif isinstance(image_data, (bytes, bytearray)):
            raw = bytes(image_data)
        else:
            raw = image_data.read()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            return image.convert("RGB")
    except Exception:
        return None


def _source_reject_reasons(
    faces: Sequence[FaceDetection],
    config: SourceSafetyConfig,
) -> List[str]:
    if not faces:
        return [REJECT_NO_FACE]
    if len(faces) > 1:
        return [REJECT_MULTIPLE_FACES]

    face = faces[0]
    reasons = []
    if face.area_ratio < config.min_face_area_ratio:
        reasons.append(REJECT_FACE_TOO_SMALL)
    if (
        face.occlusion_score is not None
        and face.occlusion_score >= config.severe_occlusion_threshold
    ):
        reasons.append(REJECT_SEVERE_OCCLUSION)
    return _ordered_reasons(reasons)


def _ordered_reasons(reasons: Sequence[str]) -> List[str]:
    reason_set = set(reasons)
    return [reason for reason in REJECT_REASON_ORDER if reason in reason_set]


def _build_result(
    *,
    status: str,
    hard_reject: bool,
    reject_reasons: Sequence[str],
    source_ref: str,
    image_width: Optional[int],
    image_height: Optional[int],
    detector_result: Optional[FaceDetectorResult],
    analysis_version: str,
) -> SourceAnalysisResult:
    faces = list(detector_result.faces) if detector_result else []
    primary_face = faces[0] if len(faces) == 1 else None
    return SourceAnalysisResult(
        status=status,
        hard_reject=hard_reject,
        reject_reasons=_ordered_reasons(reject_reasons),
        source_ref=source_ref,
        image_width=image_width,
        image_height=image_height,
        detector_provider=detector_result.provider if detector_result else "not_run",
        detector_version=detector_result.provider_version if detector_result else None,
        face_count=len(faces),
        primary_face=primary_face,
        analysis_version=analysis_version,
    )


__all__ = [
    "REJECT_CORRUPT_IMAGE",
    "REJECT_FACE_TOO_SMALL",
    "REJECT_MULTIPLE_FACES",
    "REJECT_NO_FACE",
    "REJECT_SEVERE_OCCLUSION",
    "analyze_avatar_source_image",
]
