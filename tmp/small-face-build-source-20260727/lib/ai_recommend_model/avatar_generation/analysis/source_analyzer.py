from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, List, Optional, Sequence, Union

from PIL import Image, ImageOps

from .config import SourceSafetyConfig
from .detectors import (
    DeterministicFallbackFaceDetector,
    FaceDetector,
    build_default_face_detector,
)
from .redaction import redacted_source_ref
from .schema import FaceDetection, FaceDetectorResult, SourceAnalysisResult
from .small_face import SmallFacePipelineConfig, SmallFaceSourcePipeline

ImageInput = Union[bytes, bytearray, memoryview, BinaryIO, Image.Image]

REJECT_NO_FACE = "no_face"
REJECT_MULTIPLE_FACES = "multiple_faces"
REJECT_MULTI_FACE_PRIMARY = "multi_face_primary"
REJECT_AMBIGUOUS_PRIMARY_FACE = "ambiguous_primary_face"
REJECT_FACE_TOO_SMALL = "face_too_small"
REJECT_SEVERE_OCCLUSION = "severe_occlusion"
REJECT_CORRUPT_IMAGE = "corrupt_image"

REJECT_REASON_ORDER = (
    REJECT_NO_FACE,
    REJECT_MULTI_FACE_PRIMARY,
    REJECT_AMBIGUOUS_PRIMARY_FACE,
    REJECT_MULTIPLE_FACES,
    REJECT_FACE_TOO_SMALL,
    REJECT_SEVERE_OCCLUSION,
    REJECT_CORRUPT_IMAGE,
)


@dataclass(frozen=True)
class FaceSelection:
    primary_face: Optional[FaceDetection]
    primary_score: Optional[float]
    primary_score_margin: Optional[float]
    secondary_face_count: int
    large_secondary_face_count: int
    background_face_risk: str
    background_neutralization_required: bool


def analyze_avatar_source_image(
    image_data: ImageInput,
    *,
    source_ref: str = "",
    detector: Optional[FaceDetector] = None,
    config: Optional[SourceSafetyConfig] = None,
    small_face_pipeline: Optional[SmallFaceSourcePipeline] = None,
    small_face_config: Optional[SmallFacePipelineConfig] = None,
) -> SourceAnalysisResult:
    source_config = config or SourceSafetyConfig.from_env()
    redacted_ref = redacted_source_ref(source_ref)
    pipeline_config = small_face_config or SmallFacePipelineConfig.from_env()

    if pipeline_config.enabled and detector is None:
        return _analyze_with_small_face_pipeline(
            image_data,
            source_ref=redacted_ref,
            source_config=source_config,
            pipeline_config=pipeline_config,
            pipeline=small_face_pipeline,
        )

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

    face_selection = _select_primary_face(detector_result.faces, source_config)
    reasons = _source_reject_reasons(
        detector_result.faces,
        source_config,
        face_selection=face_selection,
    )
    return _build_result(
        status="rejected" if reasons else "accepted",
        hard_reject=bool(reasons),
        reject_reasons=reasons,
        source_ref=redacted_ref,
        image_width=detector_result.image_width,
        image_height=detector_result.image_height,
        detector_result=detector_result,
        face_selection=face_selection,
        analysis_version=source_config.analysis_version,
    )


def _analyze_with_small_face_pipeline(
    image_data: ImageInput,
    *,
    source_ref: str,
    source_config: SourceSafetyConfig,
    pipeline_config: SmallFacePipelineConfig,
    pipeline: Optional[SmallFaceSourcePipeline],
) -> SourceAnalysisResult:
    if pipeline is None:
        model_path = pipeline_config.face_detect_model_path
        model_ok = bool(model_path and Path(model_path).is_file())
        if not model_ok and (
            pipeline_config.fail_closed_without_model
            or _is_production_like_environment()
        ):
            return _build_result(
                status="rejected",
                hard_reject=True,
                reject_reasons=[REJECT_CORRUPT_IMAGE],
                source_ref=source_ref,
                image_width=None,
                image_height=None,
                detector_result=FaceDetectorResult(
                    provider="small_face_pipeline",
                    image_width=None,
                    image_height=None,
                    faces=[],
                    metadata={"pipeline": "small_face", "modelMissing": True},
                ),
                analysis_version=source_config.analysis_version,
            )
        pipeline = SmallFaceSourcePipeline(
            config=pipeline_config,
            source_config=source_config,
            landmarker_model_path=source_config.mediapipe_face_landmarker_model_path,
        )

    pipeline_result = pipeline.run(image_data)
    detector_result = pipeline_result.detector_result
    face_selection = _select_primary_face(detector_result.faces, source_config)
    reasons = list(pipeline_result.public_reject_reasons)
    if not reasons:
        reasons = _source_reject_reasons(
            detector_result.faces,
            source_config,
            face_selection=face_selection,
        )
    metrics = pipeline_result.analysis.metrics if pipeline_result.analysis else {}
    result = _build_result(
        status="rejected" if reasons else "accepted",
        hard_reject=bool(reasons),
        reject_reasons=reasons,
        source_ref=source_ref,
        image_width=detector_result.image_width,
        image_height=detector_result.image_height,
        detector_result=detector_result,
        face_selection=face_selection,
        analysis_version=source_config.analysis_version,
        used_tile_fallback=bool(metrics.get("usedTileFallback")),
        face_size_bucket=(
            str(metrics["primaryFaceSizeBucket"])
            if metrics.get("primaryFaceSizeBucket") is not None
            else None
        ),
    )
    object.__setattr__(
        result, "analysis_reference_image", pipeline_result.analysis_reference
    )
    object.__setattr__(result, "internal_face_analysis", pipeline_result.analysis)
    return result


def _is_production_like_environment() -> bool:
    raw = (
        os.environ.get("AVATAR_ENVIRONMENT")
        or os.environ.get("ENVIRONMENT")
        or os.environ.get("APP_ENV")
        or ""
    ).strip().lower()
    return raw in {"production", "production_bridge", "prod"}


def _load_image(image_data: ImageInput) -> Optional[Image.Image]:
    try:
        if isinstance(image_data, Image.Image):
            image = image_data.copy()
            image.load()
            transposed = ImageOps.exif_transpose(image) or image
            return transposed.convert("RGB")
        if isinstance(image_data, memoryview):
            raw = image_data.tobytes()
        elif isinstance(image_data, (bytes, bytearray)):
            raw = bytes(image_data)
        else:
            raw = image_data.read()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            transposed = ImageOps.exif_transpose(image) or image
            return transposed.convert("RGB")
    except Exception:
        return None


def _source_reject_reasons(
    faces: Sequence[FaceDetection],
    config: SourceSafetyConfig,
    *,
    face_selection: FaceSelection,
) -> List[str]:
    if not faces:
        return [REJECT_NO_FACE]

    face = face_selection.primary_face
    if face is None:
        return [REJECT_AMBIGUOUS_PRIMARY_FACE]

    reasons = []
    if (
        face_selection.large_secondary_face_count > 0
        and config.reject_large_secondary_face
    ):
        reasons.append(REJECT_MULTI_FACE_PRIMARY)
    elif (
        face_selection.secondary_face_count > 0
        and not config.allow_small_background_faces_if_removed
    ):
        reasons.append(REJECT_MULTI_FACE_PRIMARY)
    elif (
        face_selection.secondary_face_count > 0
        and (face_selection.primary_score_margin or 0.0)
        < config.primary_face_min_score_margin
    ):
        reasons.append(REJECT_AMBIGUOUS_PRIMARY_FACE)
    if face.area_ratio < config.min_face_area_ratio:
        reasons.append(REJECT_FACE_TOO_SMALL)
    if (
        face.occlusion_score is not None
        and face.occlusion_score >= config.severe_occlusion_threshold
    ):
        reasons.append(REJECT_SEVERE_OCCLUSION)
    return _ordered_reasons(reasons)


def _select_primary_face(
    faces: Sequence[FaceDetection],
    config: SourceSafetyConfig,
) -> FaceSelection:
    if not faces:
        return FaceSelection(
            primary_face=None,
            primary_score=None,
            primary_score_margin=None,
            secondary_face_count=0,
            large_secondary_face_count=0,
            background_face_risk="none",
            background_neutralization_required=False,
        )

    scored = sorted(
        ((_primary_face_score(face), face) for face in faces),
        key=lambda item: item[0],
        reverse=True,
    )
    primary_score, primary_face = scored[0]
    secondary = scored[1:]
    secondary_face_count = len(secondary)
    large_secondary_face_count = sum(
        1
        for _score, face in secondary
        if _is_large_secondary_face(face, primary_face, config)
    )
    margin = primary_score - secondary[0][0] if secondary else 1.0
    background_face_risk = "none"
    if large_secondary_face_count:
        background_face_risk = "large_secondary_face"
    elif secondary_face_count:
        background_face_risk = "secondary_background_face"
    if secondary_face_count and margin < config.primary_face_min_score_margin:
        background_face_risk = "ambiguous_primary_face"

    return FaceSelection(
        primary_face=primary_face,
        primary_score=primary_score,
        primary_score_margin=margin,
        secondary_face_count=secondary_face_count,
        large_secondary_face_count=large_secondary_face_count,
        background_face_risk=background_face_risk,
        background_neutralization_required=secondary_face_count > 0,
    )


def _primary_face_score(face: FaceDetection) -> float:
    confidence = _clamp01(face.confidence if face.confidence is not None else 0.5)
    area = _clamp01(face.area_ratio / 0.18)
    centrality = _face_centrality(face.bbox)
    border = _border_clearance(face.bbox)
    quality = (
        1.0 - _clamp01(face.occlusion_score)
        if face.occlusion_score is not None
        else confidence
    )
    return round(
        (0.30 * confidence)
        + (0.30 * area)
        + (0.25 * centrality)
        + (0.10 * border)
        + (0.05 * quality),
        6,
    )


def _is_large_secondary_face(
    face: FaceDetection,
    primary_face: FaceDetection,
    config: SourceSafetyConfig,
) -> bool:
    if face.area_ratio >= config.primary_face_min_relative_area:
        return True
    return face.area_ratio >= max(0.0, primary_face.area_ratio * 0.35)


def _face_centrality(bbox: tuple[float, float, float, float]) -> float:
    x, y, width, height = bbox
    center_x = float(x) + (float(width) / 2.0)
    center_y = float(y) + (float(height) / 2.0)
    distance = ((abs(center_x - 0.5) / 0.5) + (abs(center_y - 0.5) / 0.5)) / 2.0
    return _clamp01(1.0 - distance)


def _border_clearance(bbox: tuple[float, float, float, float]) -> float:
    x, y, width, height = bbox
    right_margin = 1.0 - (float(x) + float(width))
    bottom_margin = 1.0 - (float(y) + float(height))
    margin = min(float(x), float(y), right_margin, bottom_margin)
    return _clamp01(margin / 0.15)


def _clamp01(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _primary_first_faces(
    faces: Sequence[FaceDetection],
    primary_face: Optional[FaceDetection],
) -> tuple[FaceDetection, ...]:
    if primary_face is None:
        return tuple(faces)

    remaining: list[FaceDetection] = []
    primary_inserted = False
    for face in faces:
        if not primary_inserted and face is primary_face:
            primary_inserted = True
            continue
        remaining.append(face)
    if not primary_inserted:
        for index, face in enumerate(remaining):
            if face == primary_face:
                del remaining[index]
                primary_inserted = True
                break
    return (primary_face, *remaining)


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
    face_selection: Optional[FaceSelection] = None,
    used_tile_fallback: bool = False,
    face_size_bucket: Optional[str] = None,
) -> SourceAnalysisResult:
    faces = tuple(detector_result.faces) if detector_result else ()
    primary_face = (
        face_selection.primary_face
        if face_selection is not None
        else (faces[0] if len(faces) == 1 else None)
    )
    ordered_faces = _primary_first_faces(faces, primary_face)
    return SourceAnalysisResult(
        status=status,
        hard_reject=hard_reject,
        reject_reasons=_ordered_reasons(reject_reasons),
        source_ref=source_ref,
        image_width=image_width,
        image_height=image_height,
        detector_provider=detector_result.provider if detector_result else "not_run",
        detector_version=detector_result.provider_version if detector_result else None,
        model_availability=dict(detector_result.model_availability)
        if detector_result
        else {},
        detector_metadata=dict(detector_result.metadata) if detector_result else {},
        broad_trait_hints=dict(primary_face.broad_traits) if primary_face else {},
        face_count=len(faces),
        faces=ordered_faces,
        primary_face=primary_face,
        primary_face_bbox=primary_face.bbox if primary_face else None,
        primary_face_confidence=primary_face.confidence if primary_face else None,
        primary_face_score=face_selection.primary_score if face_selection else None,
        primary_face_score_margin=(
            face_selection.primary_score_margin if face_selection else None
        ),
        secondary_face_count=(
            face_selection.secondary_face_count if face_selection else 0
        ),
        large_secondary_face_count=(
            face_selection.large_secondary_face_count if face_selection else 0
        ),
        background_face_risk=(
            face_selection.background_face_risk if face_selection else "none"
        ),
        background_neutralization_required=(
            face_selection.background_neutralization_required
            if face_selection
            else False
        ),
        analysis_version=analysis_version,
        used_tile_fallback=used_tile_fallback,
        face_size_bucket=face_size_bucket,
    )


__all__ = [
    "REJECT_CORRUPT_IMAGE",
    "REJECT_AMBIGUOUS_PRIMARY_FACE",
    "REJECT_FACE_TOO_SMALL",
    "REJECT_MULTI_FACE_PRIMARY",
    "REJECT_MULTIPLE_FACES",
    "REJECT_NO_FACE",
    "REJECT_SEVERE_OCCLUSION",
    "analyze_avatar_source_image",
]
