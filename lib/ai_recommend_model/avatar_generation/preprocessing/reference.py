from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from PIL import Image, ImageFilter

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
    use_sam = cfg.sam_enabled if sam_enabled is None else bool(sam_enabled)

    segmentation = _segment_reference(
        source_rgb,
        source_analysis=source_analysis,
        face_hints=face_hints,
        segmenter=segmenter,
        config=cfg,
        sam_enabled=use_sam,
    )

    face_mask = segmentation.face_mask.convert("L").resize(
        source_rgb.size,
        Image.Resampling.NEAREST,
    )
    style_mask = segmentation.style_mask.convert("L").resize(
        source_rgb.size,
        Image.Resampling.NEAREST,
    )
    face_variant = _detail_reduced_image(
        source_rgb,
        downsample_px=cfg.face_downsample_px,
        blur_radius=cfg.face_blur_radius,
    )
    style_variant = _detail_reduced_image(
        source_rgb,
        downsample_px=cfg.style_downsample_px,
        blur_radius=cfg.style_blur_radius,
    )

    output = Image.composite(face_variant, style_variant, face_mask)
    metadata = _build_metadata(
        source_size=source_rgb.size,
        output_size=output.size,
        config=cfg,
        segmentation=segmentation,
        face_mask=face_mask,
        style_mask=style_mask,
        sam_enabled=use_sam,
    )
    return ReferencePreprocessResult(
        image=output,
        metadata=metadata,
        segmentation=segmentation,
    )


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
