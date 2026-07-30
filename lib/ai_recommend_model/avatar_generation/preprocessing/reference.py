from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from avatar_generation.environment import is_production_like_environment
from avatar_generation.analysis.segmentation import (
    FaceRegion,
    ReferenceSegmenter,
    SegmentationResult,
    face_regions_from_source_analysis,
    fallback_segment_reference_regions,
)

REFERENCE_PREPROCESS_METADATA_SCHEMA_VERSION = "avatar_reference_preprocess_metadata_v1"


@dataclass(frozen=True)
class ReferencePreprocessProfile:
    name: str
    version: str
    face_equivalent_px: int
    style_equivalent_px: int
    face_blur_radius: float
    style_blur_radius: float
    protected_style_equivalent_px: int
    protected_style_blur_radius: float
    require_later_upper_bound_gate: bool = False


REFERENCE_PREPROCESS_PROFILES: Mapping[str, ReferencePreprocessProfile] = {
    "privacy_strict": ReferencePreprocessProfile(
        name="privacy_strict",
        version="privacy_strict_v1",
        face_equivalent_px=28,
        style_equivalent_px=84,
        face_blur_radius=4.5,
        style_blur_radius=1.8,
        protected_style_equivalent_px=168,
        protected_style_blur_radius=0.35,
        require_later_upper_bound_gate=False,
    ),
    "fidelity_balanced": ReferencePreprocessProfile(
        name="fidelity_balanced",
        version="fidelity_balanced_v1",
        face_equivalent_px=40,
        style_equivalent_px=124,
        face_blur_radius=3.0,
        style_blur_radius=1.0,
        protected_style_equivalent_px=224,
        protected_style_blur_radius=0.2,
        require_later_upper_bound_gate=True,
    ),
    "fidelity_high_bounded": ReferencePreprocessProfile(
        name="fidelity_high_bounded",
        version="fidelity_high_bounded_v1",
        face_equivalent_px=52,
        style_equivalent_px=168,
        face_blur_radius=2.0,
        style_blur_radius=0.6,
        protected_style_equivalent_px=288,
        protected_style_blur_radius=0.1,
        require_later_upper_bound_gate=True,
    ),
}


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
    profile_name: str = "privacy_strict"
    metadata_extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReferencePreprocessResult:
    image: Image.Image
    analysis_image: Image.Image = field(repr=False, compare=False)
    metadata: dict[str, Any]
    segmentation: SegmentationResult
    foreground_mask: Image.Image = field(repr=False, compare=False)
    face_hints: tuple[FaceRegion, ...] = field(default=(), repr=False, compare=False)


def preprocess_reference_image(
    source_image: Image.Image,
    *,
    source_analysis: Any = None,
    visual_risk_regions: Sequence[Any] = (),
    config: ReferencePreprocessConfig | None = None,
    segmenter: ReferenceSegmenter | None = None,
    sam_enabled: bool | None = None,
) -> ReferencePreprocessResult:
    cfg = config or ReferencePreprocessConfig()
    profile = _reference_preprocess_profile(cfg.profile_name)
    source_rgb = source_image.copy().convert("RGB")
    face_hints = face_regions_from_source_analysis(source_analysis, source_rgb.size)
    crop_result = _apply_primary_crop(
        source_rgb,
        face_hints=face_hints,
        enabled=cfg.primary_crop_enabled,
    )
    working_rgb = crop_result.image
    remapped_visual_risks = _remap_visual_risk_regions(
        visual_risk_regions,
        input_size=source_rgb.size,
        crop_box=crop_result.crop_box,
        output_size=working_rgb.size,
    )
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
    primary_face_scale_px = _primary_face_scale_px(crop_result.face_hints, working_rgb.size)
    protected_style_mask = _protected_style_mask(
        working_rgb.size,
        source_analysis=source_analysis,
        face_hints=crop_result.face_hints,
    )
    face_variant = _scale_aware_detail_reduced_image(
        working_rgb,
        face_scale_px=primary_face_scale_px,
        equivalent_face_px=profile.face_equivalent_px,
        blur_radius=profile.face_blur_radius,
    )
    style_variant = _scale_aware_detail_reduced_image(
        working_rgb,
        face_scale_px=primary_face_scale_px,
        equivalent_face_px=profile.style_equivalent_px,
        blur_radius=profile.style_blur_radius,
    )
    protected_variant = _scale_aware_detail_reduced_image(
        working_rgb,
        face_scale_px=primary_face_scale_px,
        equivalent_face_px=profile.protected_style_equivalent_px,
        blur_radius=profile.protected_style_blur_radius,
    )

    privacy_reduced = Image.composite(face_variant, style_variant, face_mask)
    privacy_reduced = Image.composite(protected_variant, privacy_reduced, protected_style_mask)
    output, neutralization_metadata, _generation_foreground_mask = _neutralize_background(
        privacy_reduced,
        segmentation=segmentation,
        primary_face_hints=crop_result.face_hints,
        secondary_face_hints=crop_result.secondary_face_hints,
        visual_risk_regions=remapped_visual_risks,
        source_analysis=source_analysis,
        config=cfg,
    )
    analysis_image, analysis_neutralization_metadata, analysis_foreground_mask = _neutralize_background(
        working_rgb,
        segmentation=segmentation,
        primary_face_hints=crop_result.face_hints,
        secondary_face_hints=crop_result.secondary_face_hints,
        visual_risk_regions=remapped_visual_risks,
        source_analysis=source_analysis,
        config=cfg,
    )
    metadata = _build_metadata(
        source_size=source_rgb.size,
        output_size=output.size,
        config=cfg,
        profile=profile,
        primary_face_scale_px=primary_face_scale_px,
        segmentation=segmentation,
        face_mask=face_mask,
        style_mask=style_mask,
        sam_enabled=use_sam,
        crop_metadata=crop_result.metadata,
        neutralization_metadata=_merge_neutralization_metadata(
            neutralization_metadata,
            analysis_neutralization_metadata,
        ),
    )
    return ReferencePreprocessResult(
        image=output,
        analysis_image=analysis_image,
        metadata=metadata,
        segmentation=segmentation,
        foreground_mask=analysis_foreground_mask,
        face_hints=crop_result.face_hints,
    )


@dataclass(frozen=True)
class _PrimaryCropResult:
    image: Image.Image
    face_hints: tuple[FaceRegion, ...]
    secondary_face_hints: tuple[FaceRegion, ...]
    metadata: dict[str, Any]
    crop_box: tuple[int, int, int, int]


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
                "cropIsolationQuality": "unclear",
            },
            crop_box=(0, 0, image.size[0], image.size[1]),
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
                "cropIsolationQuality": "low",
            },
            crop_box=(0, 0, image.size[0], image.size[1]),
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
                "cropIsolationQuality": _crop_isolation_quality(crop_risk, False),
            },
            crop_box=full_box,
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
            "cropIsolationQuality": _crop_isolation_quality(crop_risk, True),
        },
        crop_box=crop_box,
    )

@dataclass(frozen=True)
class _VisualRiskRegion:
    kind: str
    bbox: tuple[int, int, int, int]


def _crop_isolation_quality(crop_risk: str, crop_applied: bool) -> str:
    if crop_risk == "ok" and crop_applied:
        return "high"
    if crop_risk == "ok":
        return "medium"
    if crop_risk == "needs_review":
        return "low"
    return "unclear"


def _remap_visual_risk_regions(
    visual_risk_regions: Sequence[Any],
    *,
    input_size: tuple[int, int],
    crop_box: tuple[int, int, int, int],
    output_size: tuple[int, int],
) -> tuple[_VisualRiskRegion, ...]:
    regions: list[_VisualRiskRegion] = []
    for region in visual_risk_regions or ():
        kind = str(_field(region, "kind") or _field(region, "type") or "").strip().lower()
        bbox = _bbox_to_pixels(_field(region, "bbox") or _field(region, "box") or _field(region, "boundingBox"), input_size)
        if not kind or bbox is None:
            continue
        remapped = _remap_bbox(bbox, crop_box, output_size)
        if remapped is not None:
            regions.append(_VisualRiskRegion(kind=kind, bbox=remapped))
    return tuple(regions)


def _remap_bbox(
    bbox: tuple[int, int, int, int],
    crop_box: tuple[int, int, int, int],
    output_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    crop_left, crop_top, crop_right, crop_bottom = crop_box
    crop_width = max(1, crop_right - crop_left)
    crop_height = max(1, crop_bottom - crop_top)
    output_width, output_height = output_size
    left, top, right, bottom = bbox
    remapped = (
        int(round((left - crop_left) * output_width / crop_width)),
        int(round((top - crop_top) * output_height / crop_height)),
        int(round((right - crop_left) * output_width / crop_width)),
        int(round((bottom - crop_top) * output_height / crop_height)),
    )
    return _clamp_bbox(remapped, output_size)


def _remove_visual_risk_regions(
    foreground_mask: Image.Image,
    *,
    visual_risk_regions: Sequence[_VisualRiskRegion],
    primary_face_hints: Sequence[FaceRegion],
) -> tuple[Image.Image, dict[str, int]]:
    counts = {"text_logo": 0, "background_person": 0, "background": 0, "unique_detail": 0}
    if not visual_risk_regions:
        return foreground_mask, counts
    output = foreground_mask.copy().convert("L")
    draw = ImageDraw.Draw(output)
    for region in visual_risk_regions:
        category = _risk_category(region.kind)
        if category is None:
            continue
        clamped = _clamp_bbox(region.bbox, output.size)
        if clamped is None:
            continue
        counts[category] += 1
        if category in {"text_logo", "unique_detail"}:
            continue
        draw.rectangle(clamped, fill=0)
    for face in primary_face_hints:
        clamped_face = face.clamped(output.size)
        if clamped_face is not None:
            draw.rectangle(clamped_face.bbox, fill=255)
    return output, counts

def _risk_category(kind: str) -> str | None:
    normalized = kind.replace("-", "_").replace(" ", "_").lower()
    if "text" in normalized or "logo" in normalized or "sign" in normalized:
        return "text_logo"
    if any(token in normalized for token in ("unique", "mark", "mole", "scar", "tattoo")):
        return "unique_detail"
    if "background_person" in normalized or "secondary_person" in normalized:
        return "background_person"
    if normalized in {"background", "wall", "room"}:
        return "background"
    return None


def _changed_visual_region_counts(
    before: Image.Image,
    after: Image.Image,
    *,
    visual_risk_regions: Sequence[_VisualRiskRegion],
) -> dict[str, int]:
    counts = {"text_logo": 0, "unique_detail": 0}
    if not visual_risk_regions:
        return counts
    before_rgb = before.convert("RGB")
    after_rgb = after.convert("RGB")
    for region in visual_risk_regions:
        category = _risk_category(region.kind)
        if category not in counts:
            continue
        clamped = _clamp_bbox(region.bbox, after_rgb.size)
        if clamped is None:
            continue
        if ImageChops.difference(before_rgb.crop(clamped), after_rgb.crop(clamped)).getbbox() is not None:
            counts[category] += 1
    return counts

def _neutralize_sensitive_visual_regions(
    image: Image.Image,
    *,
    visual_risk_regions: Sequence[_VisualRiskRegion],
    neutral_color: tuple[int, int, int],
) -> tuple[Image.Image, dict[str, int]]:
    counts = {"text_logo": 0, "unique_detail": 0}
    if not visual_risk_regions:
        return image, counts
    output = image.copy().convert("RGB")
    for region in visual_risk_regions:
        category = _risk_category(region.kind)
        if category not in counts:
            continue
        clamped = _clamp_bbox(region.bbox, output.size)
        if clamped is None:
            continue
        before = output.crop(clamped)
        if category == "text_logo":
            replacement = Image.new("RGB", before.size, neutral_color)
        else:
            replacement = _detail_reduced_image(
                before,
                downsample_px=max(1, min(before.size) // 3),
                blur_radius=max(2.0, min(before.size) / 5.0),
            )
        if ImageChops.difference(before, replacement).getbbox() is None:
            continue
        output.paste(replacement, clamped)
        counts[category] += 1
    return output, counts

def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _bbox_to_pixels(value: Any, image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if value is None or isinstance(value, (str, bytes)):
        return None
    if isinstance(value, Mapping):
        if {"left", "top", "right", "bottom"}.issubset(value.keys()):
            coords = (value["left"], value["top"], value["right"], value["bottom"])
            return _xyxy_bbox_to_pixels(coords, image_size)
        if {"x", "y", "width", "height"}.issubset(value.keys()):
            coords = (value["x"], value["y"], value["width"], value["height"])
            return _xywh_bbox_to_pixels(coords, image_size)
        return _bbox_to_pixels(value.get("bbox") or value.get("box") or value.get("boundingBox"), image_size)
    if not isinstance(value, Sequence) or len(value) < 4:
        return None
    coords = tuple(float(value[index]) for index in range(4))
    return _xyxy_bbox_to_pixels(coords, image_size)


def _xywh_bbox_to_pixels(coords: Sequence[float], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    x, y, box_width, box_height = coords
    if all(0.0 <= coordinate <= 1.0 for coordinate in coords):
        x *= width
        box_width *= width
        y *= height
        box_height *= height
    return (int(round(x)), int(round(y)), int(round(x + box_width)), int(round(y + box_height)))


def _xyxy_bbox_to_pixels(coords: Sequence[float], image_size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = image_size
    left, top, right, bottom = coords
    if all(0.0 <= coordinate <= 1.0 for coordinate in coords):
        left *= width
        right *= width
        top *= height
        bottom *= height
    return (int(round(left)), int(round(top)), int(round(right)), int(round(bottom)))


def _clamp_bbox(
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    width, height = image_size
    left, top, right, bottom = bbox
    left = max(0, min(width, int(round(left))))
    top = max(0, min(height, int(round(top))))
    right = max(0, min(width, int(round(right))))
    bottom = max(0, min(height, int(round(bottom))))
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _merge_neutralization_metadata(
    generation_metadata: Mapping[str, Any],
    analysis_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(generation_metadata)
    for key in ("textLogoDetected", "textLogoNeutralized", "secondaryFacesNeutralized", "uniqueDetailsNeutralized"):
        merged[key] = bool(generation_metadata.get(key) or analysis_metadata.get(key))
    return merged

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
    visual_risk_regions: Sequence["_VisualRiskRegion"],
    source_analysis: Any,
    config: ReferencePreprocessConfig,
) -> tuple[Image.Image, dict[str, Any], Image.Image]:
    neutral_color = _parse_hex_color(config.background_neutral_color)
    foreground_mask = _foreground_mask(
        image.size,
        segmentation=segmentation,
        primary_face_hints=primary_face_hints,
    )
    foreground_mask, secondary_face_count = _remove_secondary_face_regions(
        foreground_mask,
        secondary_face_hints=secondary_face_hints,
        blur_radius=config.secondary_face_blur_radius,
    )
    foreground_mask, visual_counts = _remove_visual_risk_regions(
        foreground_mask,
        visual_risk_regions=visual_risk_regions,
        primary_face_hints=primary_face_hints,
    )

    text_logo_detected = bool(visual_counts["text_logo"]) or _source_analysis_flag(
        source_analysis,
        {
            "textLogoRisk",
            "backgroundTextLogoRisk",
            "textLogoDetected",
            "schoolSignRisk",
            "dominantTextLogoRisk",
        },
    )
    text_logo_neutralized = False
    unique_details_neutralized = False
    secondary_faces_neutralized = secondary_face_count > 0 or visual_counts["background_person"] > 0

    if not config.background_neutralization_enabled:
        metadata = {
            "backgroundNeutralized": False,
            "textLogoDetected": bool(text_logo_detected),
            "textLogoNeutralized": False,
            "secondaryFacesNeutralized": False,
            "uniqueDetailsNeutralized": False,
            "backgroundNeutralization": {"enabled": False},
        }
        return image, metadata, foreground_mask

    foreground_mask = foreground_mask.filter(ImageFilter.GaussianBlur(radius=3.0))
    background = Image.new("RGB", image.size, neutral_color)
    neutralized = Image.composite(image, background, foreground_mask)
    background_sensitive_counts = _changed_visual_region_counts(
        image,
        neutralized,
        visual_risk_regions=visual_risk_regions,
    )
    neutralized, sensitive_counts = _neutralize_sensitive_visual_regions(
        neutralized,
        visual_risk_regions=visual_risk_regions,
        neutral_color=neutral_color,
    )
    text_logo_neutralized = (sensitive_counts["text_logo"] + background_sensitive_counts["text_logo"]) > 0
    unique_details_neutralized = (sensitive_counts["unique_detail"] + background_sensitive_counts["unique_detail"]) > 0

    metadata = {
        "backgroundNeutralized": True,
        "textLogoDetected": bool(text_logo_detected),
        "textLogoNeutralized": bool(text_logo_neutralized),
        "secondaryFacesNeutralized": bool(secondary_faces_neutralized),
        "uniqueDetailsNeutralized": bool(unique_details_neutralized),
        "backgroundNeutralization": {
            "enabled": True,
            "mode": "neutral_color",
            "neutralColor": config.background_neutral_color,
            "backgroundBlurRadius": float(config.background_blur_radius),
            "backgroundDesaturate": bool(config.background_desaturate),
            "secondaryFaceBlurRadius": float(config.secondary_face_blur_radius),
            "secondaryFaceCount": int(secondary_face_count),
            "secondaryFaceAction": (
                "removed_with_background" if secondary_face_count else "none"
            ),
            "textLogoBlurEnabled": bool(config.background_text_logo_blur),
            "textLogoRiskDetected": bool(text_logo_detected),
            "textLogoRegionCount": int(visual_counts["text_logo"]),
            "textLogoNeutralizedRegionCount": int(sensitive_counts["text_logo"] + background_sensitive_counts["text_logo"]),
            "uniqueDetailRegionCount": int(visual_counts["unique_detail"]),
            "uniqueDetailNeutralizedRegionCount": int(sensitive_counts["unique_detail"] + background_sensitive_counts["unique_detail"]),
            "uniqueDetailAction": (
                "neutralized_local_detail" if unique_details_neutralized else "none"
            ),
            "textLogoAction": (
                "neutralized_background" if text_logo_neutralized else "none"
            ),
            "backgroundPersonRegionCount": int(visual_counts["background_person"]),
            "backgroundRegionCount": int(visual_counts["background"]),
            "foregroundMaskCoverage": _mask_coverage(foreground_mask),
        },
    }
    return neutralized, metadata, foreground_mask

def _remove_secondary_face_regions(
    foreground_mask: Image.Image,
    *,
    secondary_face_hints: Sequence[FaceRegion],
    blur_radius: float,
) -> tuple[Image.Image, int]:
    if not secondary_face_hints:
        return foreground_mask, 0
    output = foreground_mask.copy().convert("L")
    draw = ImageDraw.Draw(output)
    width, height = output.size
    padding = max(2, int(round(float(blur_radius))))
    removed_count = 0
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
        removed_count += 1
    return output, removed_count


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
    production_like = (
        is_production_like_environment({"ENVIRONMENT": environment})
        if environment is not None
        else is_production_like_environment()
    )
    if preprocess_enabled is None:
        preprocess_enabled = _bool_env("AVATAR_REFERENCE_PRIVACY_PREPROCESS", default=True)
    if production_like and preprocess_enabled is False:
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


def _reference_preprocess_profile(profile_name: str) -> ReferencePreprocessProfile:
    normalized = str(profile_name or "privacy_strict").strip().lower()
    return REFERENCE_PREPROCESS_PROFILES.get(
        normalized,
        REFERENCE_PREPROCESS_PROFILES["privacy_strict"],
    )


def _primary_face_scale_px(
    face_hints: Sequence[FaceRegion],
    image_size: tuple[int, int],
) -> int:
    for face in face_hints:
        clamped = face.clamped(image_size)
        if clamped is None:
            continue
        left, top, right, bottom = clamped.bbox
        return max(1, right - left, bottom - top)
    return max(1, min(image_size))


def _scale_aware_detail_reduced_image(
    image: Image.Image,
    *,
    face_scale_px: int,
    equivalent_face_px: int,
    blur_radius: float,
) -> Image.Image:
    width, height = image.size
    longest = max(width, height)
    scale = max(1, int(equivalent_face_px)) / float(max(1, int(face_scale_px)))
    target_longest = max(1, min(longest, int(round(longest * scale))))
    return _detail_reduced_image(
        image,
        downsample_px=target_longest,
        blur_radius=blur_radius,
    )


def _protected_style_mask(
    image_size: tuple[int, int],
    *,
    source_analysis: Any,
    face_hints: Sequence[FaceRegion],
) -> Image.Image:
    mask = Image.new("L", image_size, 0)
    draw = ImageDraw.Draw(mask)
    for face in face_hints:
        clamped = face.clamped(image_size)
        if clamped is None:
            continue
        left, top, right, bottom = clamped.bbox
        face_width = max(1, right - left)
        face_height = max(1, bottom - top)
        center_x = (left + right) / 2.0
        draw.ellipse(
            (
                max(0, int(round(center_x - face_width * 1.15))),
                max(0, int(round(top - face_height * 0.75))),
                min(image_size[0], int(round(center_x + face_width * 1.15))),
                min(image_size[1], int(round(bottom + face_height * 0.35))),
            ),
            fill=255,
        )
    for face in face_hints:
        clamped = face.clamped(image_size)
        if clamped is not None:
            draw.rectangle(clamped.bbox, fill=0)
    for region in _semantic_regions_from_source_analysis(source_analysis, image_size):
        if _protected_region_category(region.kind) is None:
            continue
        clamped = _clamp_bbox(region.bbox, image_size)
        if clamped is not None:
            draw.rectangle(clamped, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(radius=1.0))


def _semantic_regions_from_source_analysis(
    source_analysis: Any,
    image_size: tuple[int, int],
) -> tuple[_VisualRiskRegion, ...]:
    if source_analysis is None:
        return ()
    candidates: list[Any] = [source_analysis]
    to_document = getattr(source_analysis, "to_document", None)
    if callable(to_document):
        try:
            candidates.append(to_document())
        except Exception:
            pass
    regions: list[_VisualRiskRegion] = []
    for candidate in candidates:
        regions.extend(_extract_semantic_regions(candidate, image_size))
    deduped: list[_VisualRiskRegion] = []
    seen: set[tuple[str, tuple[int, int, int, int]]] = set()
    for region in regions:
        key = (region.kind, region.bbox)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(region)
    return tuple(deduped)


def _extract_semantic_regions(value: Any, image_size: tuple[int, int]) -> list[_VisualRiskRegion]:
    if value is None or isinstance(value, (str, bytes)):
        return []
    if isinstance(value, Mapping):
        items: list[Any] = []
        for key in ("regions", "visualRegions", "semanticRegions", "items"):
            child = value.get(key)
            if isinstance(child, Sequence) and not isinstance(child, (str, bytes)):
                items.extend(child)
        if items:
            regions: list[_VisualRiskRegion] = []
            for item in items:
                regions.extend(_extract_semantic_regions(item, image_size))
            return regions
    else:
        child = getattr(value, "regions", None) or getattr(value, "visualRegions", None)
        if isinstance(child, Sequence) and not isinstance(child, (str, bytes)):
            regions = []
            for item in child:
                regions.extend(_extract_semantic_regions(item, image_size))
            return regions
    kind = str(_field(value, "kind") or _field(value, "type") or _field(value, "label") or "").strip().lower()
    bbox = _bbox_to_pixels(_field(value, "bbox") or _field(value, "box") or _field(value, "boundingBox"), image_size)
    if not kind or bbox is None:
        return []
    clamped = _clamp_bbox(bbox, image_size)
    if clamped is None:
        return []
    return [_VisualRiskRegion(kind=kind, bbox=clamped)]


def _protected_region_category(kind: str) -> str | None:
    normalized = kind.replace("-", "_").replace(" ", "_").lower()
    protected_tokens = (
        "hair",
        "eyewear",
        "glasses",
        "facial_hair",
        "beard",
        "mustache",
        "moustache",
        "silhouette",
        "hood",
        "hat",
    )
    return "protected_style" if any(token in normalized for token in protected_tokens) else None

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
    profile: ReferencePreprocessProfile,
    primary_face_scale_px: int,
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
        "profile": {
            "name": profile.name,
            "version": profile.version,
            "primaryFaceScalePx": int(primary_face_scale_px),
            "faceEquivalentPx": int(profile.face_equivalent_px),
            "styleEquivalentPx": int(profile.style_equivalent_px),
            "protectedStyleEquivalentPx": int(profile.protected_style_equivalent_px),
            "requiresLaterUpperBoundGate": bool(profile.require_later_upper_bound_gate),
        },
        "regions": {
            "face": {
                "downsamplePx": int(config.face_downsample_px),
                "blurRadius": float(config.face_blur_radius),
                "profileEquivalentPx": int(profile.face_equivalent_px),
                "profileBlurRadius": float(profile.face_blur_radius),
                "maskCoverage": face_coverage,
            },
            "style": {
                "downsamplePx": int(config.style_downsample_px),
                "blurRadius": float(config.style_blur_radius),
                "profileEquivalentPx": int(profile.style_equivalent_px),
                "profileBlurRadius": float(profile.style_blur_radius),
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
