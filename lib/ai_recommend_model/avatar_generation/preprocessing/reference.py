from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from avatar_generation.analysis.segmentation import (
    FaceRegion,
    ReferenceSegmenter,
    SegmentationResult,
    face_regions_from_source_analysis,
    fallback_segment_reference_regions,
)

REFERENCE_PREPROCESS_METADATA_SCHEMA_VERSION = "avatar_reference_preprocess_metadata_v1"


@dataclass(frozen=True)
class ReferencePreprocessConfig:
    face_downsample_px: int = 32
    style_downsample_px: int = 96
    face_blur_radius: float = 4.0
    style_blur_radius: float = 1.5
    sam_enabled: bool = False
    sam_model_path: str | None = None
    sam_model_type: str = "vit_h"
    sam_device: str | None = None
    primary_crop_enabled: bool = True
    background_neutralization_enabled: bool = True
    background_neutral_color: str = "#F7F2EC"
    secondary_face_blur_radius: float = 12.0
    background_blur_radius: float = 10.0
    background_desaturate: bool = True
    background_text_logo_blur: bool = True
    metadata_extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReferencePreprocessResult:
    image: Image.Image
    metadata: dict[str, Any]
    segmentation: SegmentationResult


def preprocess_reference_image(
    source_image: Image.Image,
    *,
    source_analysis: Any = None,
    config: ReferencePreprocessConfig | None = None,
    segmenter: ReferenceSegmenter | None = None,
    sam_enabled: bool | None = None,
) -> ReferencePreprocessResult:
    cfg = config or ReferencePreprocessConfig()
    source_rgb = source_image.copy().convert("RGB")
    face_hints = face_regions_from_source_analysis(source_analysis, source_rgb.size)
    crop_result = _apply_primary_crop(
        source_rgb,
        face_hints=face_hints,
        enabled=cfg.primary_crop_enabled,
    )
    working_rgb = crop_result.image
    use_sam = cfg.sam_enabled if sam_enabled is None else bool(sam_enabled)

    segmentation = _segment_reference(
        working_rgb,
        source_analysis=source_analysis,
        face_hints=crop_result.face_hints,
        segmenter=segmenter,
        config=cfg,
        sam_enabled=use_sam,
    )

    face_mask = segmentation.face_mask.convert("L").resize(
        working_rgb.size,
        Image.Resampling.NEAREST,
    )
    style_mask = segmentation.style_mask.convert("L").resize(
        working_rgb.size,
        Image.Resampling.NEAREST,
    )
    face_variant = _detail_reduced_image(
        working_rgb,
        downsample_px=cfg.face_downsample_px,
        blur_radius=cfg.face_blur_radius,
    )
    style_variant = _detail_reduced_image(
        working_rgb,
        downsample_px=cfg.style_downsample_px,
        blur_radius=cfg.style_blur_radius,
    )

    privacy_reduced = Image.composite(face_variant, style_variant, face_mask)
    output, neutralization_metadata = _neutralize_background(
        privacy_reduced,
        segmentation=segmentation,
        primary_face_hints=crop_result.face_hints,
        secondary_face_hints=crop_result.secondary_face_hints,
        source_analysis=source_analysis,
        config=cfg,
    )
    metadata = _build_metadata(
        source_size=source_rgb.size,
        output_size=output.size,
        config=cfg,
        segmentation=segmentation,
        face_mask=face_mask,
        style_mask=style_mask,
        sam_enabled=use_sam,
        crop_metadata=crop_result.metadata,
        neutralization_metadata=neutralization_metadata,
    )
    return ReferencePreprocessResult(
        image=output,
        metadata=metadata,
        segmentation=segmentation,
    )


@dataclass(frozen=True)
class _PrimaryCropResult:
    image: Image.Image
    face_hints: tuple[FaceRegion, ...]
    secondary_face_hints: tuple[FaceRegion, ...]
    metadata: dict[str, Any]


def _apply_primary_crop(
    image: Image.Image,
    *,
    face_hints: Sequence[FaceRegion],
    enabled: bool,
) -> _PrimaryCropResult:
    if not enabled or not face_hints:
        return _PrimaryCropResult(
            image=image,
            face_hints=tuple(face_hints[:1]),
            secondary_face_hints=tuple(face_hints[1:]),
            metadata={
                "primaryCropApplied": False,
                "cropType": "none",
                "cropRisk": "no_face_hint" if enabled else "disabled",
            },
        )

    primary_face = face_hints[0].clamped(image.size)
    if primary_face is None:
        return _PrimaryCropResult(
            image=image,
            face_hints=(),
            secondary_face_hints=(),
            metadata={
                "primaryCropApplied": False,
                "cropType": "none",
                "cropRisk": "invalid_face_hint",
            },
        )

    crop_box, crop_type, crop_risk = _primary_head_shoulders_crop_box(
        primary_face,
        image.size,
    )
    full_box = (0, 0, image.size[0], image.size[1])
    if crop_box == full_box:
        return _PrimaryCropResult(
            image=image,
            face_hints=(primary_face,),
            secondary_face_hints=tuple(
                face for face in (hint.clamped(image.size) for hint in face_hints[1:]) if face
            ),
            metadata={
                "primaryCropApplied": False,
                "cropType": crop_type,
                "cropRisk": crop_risk,
            },
        )

    cropped = image.crop(crop_box).resize(image.size, Image.Resampling.LANCZOS)
    remapped_face = _remap_face_region(primary_face, crop_box, image.size)
    face_tuple = (remapped_face,) if remapped_face is not None else ()
    secondary_faces = tuple(
        face
        for face in (
            _remap_face_region(hint, crop_box, image.size)
            for hint in face_hints[1:]
        )
        if face is not None
    )
    return _PrimaryCropResult(
        image=cropped,
        face_hints=face_tuple,
        secondary_face_hints=secondary_faces,
        metadata={
            "primaryCropApplied": True,
            "cropType": crop_type,
            "cropRisk": crop_risk,
        },
    )


def _primary_head_shoulders_crop_box(
    face: FaceRegion,
    image_size: tuple[int, int],
) -> tuple[tuple[int, int, int, int], str, str]:
    image_width, image_height = image_size
    left, top, right, bottom = face.bbox
    face_width = max(1, right - left)
    face_height = max(1, bottom - top)
    center_x = (left + right) / 2.0

    desired_left = center_x - (face_width * 1.55)
    desired_right = center_x + (face_width * 1.55)
    desired_top = top - (face_height * 0.85)
    desired_bottom = bottom + (face_height * 1.70)
    crop_width = desired_right - desired_left
    crop_height = desired_bottom - desired_top
    side = max(crop_width, crop_height)
    center_y = (desired_top + desired_bottom) / 2.0

    crop_left = center_x - (side / 2.0)
    crop_right = center_x + (side / 2.0)
    crop_top = center_y - (side / 2.0)
    crop_bottom = center_y + (side / 2.0)

    crop_left, crop_right = _shift_into_bounds(crop_left, crop_right, image_width)
    crop_top, crop_bottom = _shift_into_bounds(crop_top, crop_bottom, image_height)
    crop_left = max(0.0, crop_left)
    crop_top = max(0.0, crop_top)
    crop_right = min(float(image_width), crop_right)
    crop_bottom = min(float(image_height), crop_bottom)

    crop_box = (
        int(round(crop_left)),
        int(round(crop_top)),
        int(round(crop_right)),
        int(round(crop_bottom)),
    )
    crop_risk = "ok"
    if crop_box[0] > left or crop_box[1] > top or crop_box[2] < right or crop_box[3] < bottom:
        crop_risk = "needs_review"
    elif top - crop_box[1] < face_height * 0.20:
        crop_risk = "needs_review"
    return crop_box, "head_and_shoulders", crop_risk


def _shift_into_bounds(
    start: float,
    end: float,
    maximum: int,
) -> tuple[float, float]:
    span = end - start
    if span >= maximum:
        return 0.0, float(maximum)
    if start < 0:
        end -= start
        start = 0.0
    if end > maximum:
        start -= end - maximum
        end = float(maximum)
    return start, end


def _remap_face_region(
    face: FaceRegion,
    crop_box: tuple[int, int, int, int],
    output_size: tuple[int, int],
) -> FaceRegion | None:
    crop_left, crop_top, crop_right, crop_bottom = crop_box
    crop_width = max(1, crop_right - crop_left)
    crop_height = max(1, crop_bottom - crop_top)
    output_width, output_height = output_size
    left, top, right, bottom = face.bbox
    remapped = FaceRegion(
        bbox=(
            int(round((left - crop_left) * output_width / crop_width)),
            int(round((top - crop_top) * output_height / crop_height)),
            int(round((right - crop_left) * output_width / crop_width)),
            int(round((bottom - crop_top) * output_height / crop_height)),
        ),
        confidence=face.confidence,
        source=face.source,
    )
    return remapped.clamped(output_size)


def _neutralize_background(
    image: Image.Image,
    *,
    segmentation: SegmentationResult,
    primary_face_hints: Sequence[FaceRegion],
    secondary_face_hints: Sequence[FaceRegion],
    source_analysis: Any,
    config: ReferencePreprocessConfig,
) -> tuple[Image.Image, dict[str, Any]]:
    if not config.background_neutralization_enabled:
        return image, {
            "backgroundNeutralized": False,
            "backgroundNeutralization": {"enabled": False},
        }

    neutral_color = _parse_hex_color(config.background_neutral_color)
    background = Image.new("RGB", image.size, neutral_color)
    foreground_mask = _foreground_mask(
        image.size,
        segmentation=segmentation,
        primary_face_hints=primary_face_hints,
    )
    foreground_mask = _remove_secondary_face_regions(
        foreground_mask,
        secondary_face_hints=secondary_face_hints,
        blur_radius=config.secondary_face_blur_radius,
    )
    foreground_mask = foreground_mask.filter(ImageFilter.GaussianBlur(radius=3.0))
    neutralized = Image.composite(image, background, foreground_mask)

    text_logo_risk = _source_analysis_flag(
        source_analysis,
        {
            "textLogoRisk",
            "backgroundTextLogoRisk",
            "textLogoDetected",
            "schoolSignRisk",
            "dominantTextLogoRisk",
        },
    )
    metadata = {
        "backgroundNeutralized": True,
        "backgroundNeutralization": {
            "enabled": True,
            "mode": "neutral_color",
            "neutralColor": config.background_neutral_color,
            "backgroundBlurRadius": float(config.background_blur_radius),
            "backgroundDesaturate": bool(config.background_desaturate),
            "secondaryFaceBlurRadius": float(config.secondary_face_blur_radius),
            "secondaryFaceCount": len(tuple(secondary_face_hints)),
            "secondaryFaceAction": (
                "removed_with_background" if secondary_face_hints else "none"
            ),
            "textLogoBlurEnabled": bool(config.background_text_logo_blur),
            "textLogoRiskDetected": bool(text_logo_risk),
            "textLogoAction": (
                "neutralized_background"
                if text_logo_risk and config.background_text_logo_blur
                else "none"
            ),
            "foregroundMaskCoverage": _mask_coverage(foreground_mask),
        },
    }
    return neutralized, metadata


def _remove_secondary_face_regions(
    foreground_mask: Image.Image,
    *,
    secondary_face_hints: Sequence[FaceRegion],
    blur_radius: float,
) -> Image.Image:
    if not secondary_face_hints:
        return foreground_mask
    output = foreground_mask.copy().convert("L")
    draw = ImageDraw.Draw(output)
    width, height = output.size
    padding = max(2, int(round(float(blur_radius))))
    for face in secondary_face_hints:
        clamped = face.clamped(output.size)
        if clamped is None:
            continue
        left, top, right, bottom = clamped.bbox
        draw.rectangle(
            (
                max(0, left - padding),
                max(0, top - padding),
                min(width, right + padding),
                min(height, bottom + padding),
            ),
            fill=0,
        )
    return output


def _foreground_mask(
    image_size: tuple[int, int],
    *,
    segmentation: SegmentationResult,
    primary_face_hints: Sequence[FaceRegion],
) -> Image.Image:
    if segmentation.provider.startswith("sam"):
        return ImageOps.invert(segmentation.style_mask.convert("L")).resize(
            image_size,
            Image.Resampling.NEAREST,
        )

    mask = Image.new("L", image_size, 0)
    draw = ImageDraw.Draw(mask)
    for face in primary_face_hints:
        clamped = face.clamped(image_size)
        if clamped is None:
            continue
        left, top, right, bottom = clamped.bbox
        face_width = max(1, right - left)
        face_height = max(1, bottom - top)
        center_x = (left + right) / 2.0
        ellipse_left = int(round(center_x - face_width * 1.65))
        ellipse_right = int(round(center_x + face_width * 1.65))
        ellipse_top = int(round(top - face_height * 0.85))
        ellipse_bottom = int(round(bottom + face_height * 2.25))
        draw.ellipse(
            (
                max(0, ellipse_left),
                max(0, ellipse_top),
                min(image_size[0], ellipse_right),
                min(image_size[1], ellipse_bottom),
            ),
            fill=255,
        )
    if mask.getbbox() is None:
        return ImageOps.invert(segmentation.style_mask.convert("L")).resize(
            image_size,
            Image.Resampling.NEAREST,
        )
    return mask


def _parse_hex_color(value: str) -> tuple[int, int, int]:
    normalized = str(value or "").strip().lstrip("#")
    if len(normalized) != 6:
        return (247, 242, 236)
    try:
        return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (247, 242, 236)


def _source_analysis_flag(source_analysis: Any, keys: set[str]) -> bool:
    if source_analysis is None:
        return False
    candidates: list[Any] = [source_analysis]
    to_document = getattr(source_analysis, "to_document", None)
    if callable(to_document):
        try:
            candidates.append(to_document())
        except Exception:
            pass
    return any(_nested_flag(candidate, keys) for candidate in candidates)


def _nested_flag(value: Any, keys: set[str]) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in keys and bool(child):
                return True
            if _nested_flag(child, keys):
                return True
    elif isinstance(value, list):
        return any(_nested_flag(child, keys) for child in value)
    return False


def validate_reference_preprocess_enabled_for_environment(
    *,
    environment: str | None = None,
    preprocess_enabled: bool | None = None,
) -> None:
    env = (
        environment if environment is not None else os.environ.get("ENVIRONMENT", "")
    ).strip().lower()
    if preprocess_enabled is None:
        preprocess_enabled = _bool_env("AVATAR_REFERENCE_PRIVACY_PREPROCESS", default=True)
    if env in {"prod", "production"} and preprocess_enabled is False:
        raise ValueError("Reference privacy preprocess cannot be disabled in production.")


def _segment_reference(
    image: Image.Image,
    *,
    source_analysis: Any,
    face_hints: Sequence[FaceRegion],
    segmenter: ReferenceSegmenter | None,
    config: ReferencePreprocessConfig,
    sam_enabled: bool,
) -> SegmentationResult:
    if segmenter is not None:
        return segmenter.segment(image, face_hints=face_hints)

    if sam_enabled and config.sam_model_path:
        try:
            from avatar_generation.model_adapters.sam import SamSegmentationAdapter

            return SamSegmentationAdapter(
                model_path=config.sam_model_path,
                model_type=config.sam_model_type,
                device=config.sam_device,
            ).segment(image, face_hints=face_hints)
        except Exception as exc:
            return fallback_segment_reference_regions(
                image,
                source_analysis=source_analysis,
                face_regions=face_hints,
                provider="source_analysis",
                extra_metadata={"samError": type(exc).__name__},
            )

    return fallback_segment_reference_regions(
        image,
        source_analysis=source_analysis,
        face_regions=face_hints,
    )


def _detail_reduced_image(
    image: Image.Image,
    *,
    downsample_px: int,
    blur_radius: float,
) -> Image.Image:
    target = max(1, int(downsample_px))
    width, height = image.size
    longest = max(width, height)
    if longest > target:
        scale = target / float(longest)
        reduced_size = (
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )
        reduced = image.resize(reduced_size, Image.Resampling.BICUBIC)
        reduced = reduced.resize(image.size, Image.Resampling.BICUBIC)
    else:
        reduced = image.copy()

    if blur_radius > 0:
        reduced = reduced.filter(ImageFilter.GaussianBlur(radius=float(blur_radius)))
    return reduced


def _build_metadata(
    *,
    source_size: tuple[int, int],
    output_size: tuple[int, int],
    config: ReferencePreprocessConfig,
    segmentation: SegmentationResult,
    face_mask: Image.Image,
    style_mask: Image.Image,
    sam_enabled: bool,
    crop_metadata: Mapping[str, Any],
    neutralization_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    face_coverage = _mask_coverage(face_mask)
    style_coverage = _mask_coverage(style_mask)
    metadata: dict[str, Any] = {
        "schemaVersion": REFERENCE_PREPROCESS_METADATA_SCHEMA_VERSION,
        "sourceSize": _size_document(source_size),
        "outputSize": _size_document(output_size),
        "regions": {
            "face": {
                "downsamplePx": int(config.face_downsample_px),
                "blurRadius": float(config.face_blur_radius),
                "maskCoverage": face_coverage,
            },
            "style": {
                "downsamplePx": int(config.style_downsample_px),
                "blurRadius": float(config.style_blur_radius),
                "maskCoverage": style_coverage,
            },
        },
        "segmentation": segmentation.to_metadata(),
        "sam": {
            "enabled": bool(sam_enabled),
            "provider": segmentation.provider if sam_enabled and segmentation.provider.startswith("sam") else None,
        },
        **dict(crop_metadata),
        **dict(neutralization_metadata),
    }
    metadata.update(dict(config.metadata_extra))
    return metadata


def _size_document(size: tuple[int, int]) -> dict[str, int]:
    return {"width": int(size[0]), "height": int(size[1])}


def _mask_coverage(mask: Image.Image) -> float:
    histogram = mask.convert("L").histogram()
    pixel_count = max(1, mask.size[0] * mask.size[1])
    coverage = sum(value * count for value, count in enumerate(histogram)) / (255.0 * pixel_count)
    return round(coverage, 6)


def _bool_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"0", "false", "no", "off"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True
    return default
