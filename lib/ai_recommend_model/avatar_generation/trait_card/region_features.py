from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass, field
from statistics import median
from typing import Any, Mapping, Sequence

from PIL import Image

from .schema import UNCLEAR

HAIR_COLOR_ENUMS = {"black", "dark_brown", "brown", "light_brown", "dyed_light", "dyed_warm", "not_visible", UNCLEAR}
CLOTHING_COLOR_ENUMS = {"blue", "white", "black", "beige", "gray", "navy", "brown", "green", "not_visible", UNCLEAR}


@dataclass(frozen=True)
class RegionColorHint:
    value: str
    confidence: str
    unclear_reason: str | None = None


@dataclass(frozen=True)
class RegionColorTraits:
    hair_color_range: RegionColorHint
    clothing_color: RegionColorHint

    def to_trait_card_update(self) -> dict[str, str]:
        update: dict[str, str] = {}
        if self.hair_color_range.value in HAIR_COLOR_ENUMS - {UNCLEAR, "not_visible"}:
            update["hair_color_range"] = self.hair_color_range.value
        if self.clothing_color.value in CLOTHING_COLOR_ENUMS - {UNCLEAR, "not_visible"}:
            update["clothing_color"] = self.clothing_color.value
        return update


@dataclass(frozen=True)
class DerivedRegionColorRegion:
    kind: str
    bbox: tuple[int, int, int, int] = field(repr=False, compare=False)
    coarse_reason: str | None = None


def extract_region_color_traits(
    image: Image.Image,
    *,
    regions: Sequence[Any] | Mapping[str, Any] = (),
    primary_face_hint: Any | None = None,
    foreground_mask: Image.Image | None = None,
    neutral_color: str | tuple[int, int, int] = "#F7F2EC",
) -> RegionColorTraits:
    rgb = image.convert("RGB")
    neutral_rgb = _parse_color(neutral_color)
    region_list = _normalize_regions(regions)
    derived_regions: tuple[DerivedRegionColorRegion, ...] = ()
    if primary_face_hint is not None:
        derived_regions = derive_conservative_region_color_regions(
            primary_face_hint,
            rgb.size,
            foreground_mask=foreground_mask,
        )
        normalized_present_kinds = {kind.replace("-", "_").replace(" ", "_") for kind, _bbox in region_list}
        region_list = (
            *region_list,
            *(
                (region.kind, region.bbox)
                for region in derived_regions
                if region.kind not in normalized_present_kinds and region.coarse_reason is None
            ),
        )

    hair_issue = _coarse_issue_for_kind(derived_regions, "hair")
    clothing_issue = _coarse_issue_for_kind(derived_regions, "clothing")
    hair_pixels = () if hair_issue else _pixels_for_kinds(rgb, region_list, {"hair"}, neutral_rgb, foreground_mask)
    clothing_pixels = (
        ()
        if clothing_issue
        else _pixels_for_kinds(
            rgb,
            region_list,
            {"clothing", "shirt", "torso", "upper_body", "top"},
            neutral_rgb,
            foreground_mask,
        )
    )
    return RegionColorTraits(
        hair_color_range=RegionColorHint(value=UNCLEAR, confidence="low", unclear_reason=hair_issue)
        if hair_issue
        else _classify_hair_color(hair_pixels),
        clothing_color=RegionColorHint(
            value="not_visible" if clothing_issue == "clothing_region_not_visible" else UNCLEAR,
            confidence="low",
            unclear_reason=clothing_issue,
        )
        if clothing_issue
        else _classify_clothing_color(clothing_pixels),
    )


def derive_conservative_region_color_regions(
    primary_face_hint: Any,
    image_size: tuple[int, int],
    *,
    foreground_mask: Image.Image | None = None,
) -> tuple[DerivedRegionColorRegion, ...]:
    """Derive process-local hair/clothing sample boxes from one primary face hint."""
    face = _face_hint_to_xyxy(primary_face_hint, image_size)
    confidence = _face_confidence(primary_face_hint)
    if face is None:
        return (
            DerivedRegionColorRegion("hair", (0, 0, 0, 0), "hair_region_face_missing"),
            DerivedRegionColorRegion("clothing", (0, 0, 0, 0), "clothing_region_face_missing"),
        )
    if confidence is not None and confidence < 0.50:
        return (
            DerivedRegionColorRegion("hair", (0, 0, 0, 0), "hair_region_face_low_confidence"),
            DerivedRegionColorRegion("clothing", (0, 0, 0, 0), "clothing_region_face_low_confidence"),
        )

    width, height = image_size
    left, top, right, bottom = face
    face_width = max(1, right - left)
    face_height = max(1, bottom - top)
    hair_raw = (
        int(round(left - face_width * 0.18)),
        int(round(top - face_height * 0.45)),
        int(round(right + face_width * 0.18)),
        int(round(top + face_height * 0.35)),
    )
    clothing_raw = (
        int(round(left - face_width * 0.55)),
        int(round(bottom + face_height * 0.05)),
        int(round(right + face_width * 0.55)),
        int(round(bottom + face_height * 1.25)),
    )
    return (
        _derived_region("hair", hair_raw, width, height, foreground_mask),
        _derived_region("clothing", clothing_raw, width, height, foreground_mask),
    )


def _normalize_regions(regions: Sequence[Any] | Mapping[str, Any]) -> tuple[tuple[str, tuple[int, int, int, int]], ...]:
    if isinstance(regions, Mapping):
        items = []
        for kind, value in regions.items():
            bbox = _field(value, "bbox") or _field(value, "box") or value
            items.append({"kind": kind, "bbox": bbox})
    else:
        items = list(regions or ())

    normalized: list[tuple[str, tuple[int, int, int, int]]] = []
    for item in items:
        kind = str(_field(item, "kind") or _field(item, "type") or "").strip().lower()
        bbox = _bbox_to_xyxy(_field(item, "bbox") or _field(item, "box") or _field(item, "boundingBox"))
        if kind and bbox is not None:
            normalized.append((kind, bbox))
    return tuple(normalized)


def _pixels_for_kinds(
    image: Image.Image,
    regions: Sequence[tuple[str, tuple[int, int, int, int]]],
    accepted_kinds: set[str],
    neutral_rgb: tuple[int, int, int],
    foreground_mask: Image.Image | None = None,
) -> tuple[tuple[int, int, int], ...]:
    pixels: list[tuple[int, int, int]] = []
    width, height = image.size
    mask = _prepare_mask(foreground_mask, image.size)
    for kind, bbox in regions:
        normalized_kind = kind.replace("-", "_").replace(" ", "_")
        if not any(accepted in normalized_kind for accepted in accepted_kinds):
            continue
        left, top, right, bottom = _clamp_bbox(bbox, width, height)
        if right <= left or bottom <= top:
            continue
        for x, y, red, green, blue in _iter_region_pixels(image, (left, top, right, bottom)):
            if mask is not None and mask.getpixel((x, y)) <= 127:
                continue
            if _is_neutral_background((red, green, blue), neutral_rgb):
                continue
            pixels.append((red, green, blue))
    return tuple(pixels)


def _iter_region_pixels(image: Image.Image, bbox: tuple[int, int, int, int]):
    left, top, right, bottom = bbox
    for y in range(top, bottom):
        for x in range(left, right):
            red, green, blue = image.getpixel((x, y))
            yield x, y, red, green, blue


def _coarse_issue_for_kind(regions: Sequence[DerivedRegionColorRegion], kind: str) -> str | None:
    for region in regions:
        if region.kind == kind:
            return region.coarse_reason
    return None


def _classify_hair_color(pixels: Sequence[tuple[int, int, int]]) -> RegionColorHint:
    stats = _color_stats(pixels)
    if stats is None:
        return RegionColorHint(value=UNCLEAR, confidence="low", unclear_reason="hair_region_missing_or_neutral")
    hue, saturation, value, lab_l, lab_a, lab_b, spread = stats
    if saturation < 0.10 and value < 0.24:
        return RegionColorHint(value="black", confidence=_confidence(spread, saturation, min_count=len(pixels)))
    if value > 0.72 and saturation > 0.18:
        return RegionColorHint(value="dyed_light", confidence=_lighting_confidence(spread, value, saturation, len(pixels)))
    if 15 <= hue <= 70 and saturation > 0.16:
        if lab_l < 28 or value < 0.30:
            color = "dark_brown"
        elif lab_l > 58 or value > 0.58:
            color = "light_brown"
        else:
            color = "brown"
        return RegionColorHint(value=color, confidence=_lighting_confidence(spread, value, saturation, len(pixels)))
    if hue < 15 or 340 <= hue <= 360:
        return RegionColorHint(value="dyed_warm", confidence=_confidence(spread, saturation, min_count=len(pixels)))
    return RegionColorHint(value=UNCLEAR, confidence="low", unclear_reason="hair_color_outside_supported_enums")


def _classify_clothing_color(pixels: Sequence[tuple[int, int, int]]) -> RegionColorHint:
    stats = _color_stats(pixels)
    if stats is None:
        return RegionColorHint(value=UNCLEAR, confidence="low", unclear_reason="clothing_region_missing_or_neutral")
    hue, saturation, value, lab_l, _lab_a, lab_b, spread = stats
    confidence = _confidence(spread, saturation, min_count=len(pixels))
    if saturation < 0.12:
        if value > 0.78 and lab_l > 76:
            return RegionColorHint(value="white", confidence=confidence)
        if value < 0.22 and lab_l < 28:
            return RegionColorHint(value="black", confidence=confidence)
        return RegionColorHint(value="gray", confidence=confidence)
    if 195 <= hue <= 255:
        return RegionColorHint(value="navy" if value < 0.34 else "blue", confidence=confidence)
    if 75 <= hue <= 165:
        return RegionColorHint(value="green", confidence=confidence)
    if 18 <= hue <= 55:
        return RegionColorHint(value="beige" if value > 0.58 and saturation < 0.35 and lab_b > 5 else "brown", confidence=confidence)
    return RegionColorHint(value=UNCLEAR, confidence="low", unclear_reason="clothing_color_outside_supported_enums")


def _color_stats(pixels: Sequence[tuple[int, int, int]]) -> tuple[float, float, float, float, float, float, float] | None:
    if len(pixels) < 8:
        return None
    hsv_values = []
    lab_values = []
    for red, green, blue in pixels:
        hue, saturation, value = colorsys.rgb_to_hsv(red / 255.0, green / 255.0, blue / 255.0)
        hsv_values.append((hue * 360.0, saturation, value))
        lab_values.append(_rgb_to_lab(red, green, blue))
    hue = _circular_median([item[0] for item in hsv_values])
    saturation = float(median(item[1] for item in hsv_values))
    value = float(median(item[2] for item in hsv_values))
    lab_l = float(median(item[0] for item in lab_values))
    lab_a = float(median(item[1] for item in lab_values))
    lab_b = float(median(item[2] for item in lab_values))
    spread = float(median(abs(item[2] - value) for item in hsv_values))
    return hue, saturation, value, lab_l, lab_a, lab_b, spread


def _confidence(spread: float, saturation: float, *, min_count: int) -> str:
    if min_count < 20 or spread > 0.22:
        return "low"
    if min_count < 80 or spread > 0.12 or saturation < 0.14:
        return "medium"
    return "high"


def _lighting_confidence(spread: float, value: float, saturation: float, count: int) -> str:
    if value < 0.12 or value > 0.88 or spread > 0.18:
        return "low"
    return _confidence(spread, saturation, min_count=count)


def _is_neutral_background(pixel: tuple[int, int, int], neutral_rgb: tuple[int, int, int]) -> bool:
    red, green, blue = pixel
    hue, saturation, value = colorsys.rgb_to_hsv(red / 255.0, green / 255.0, blue / 255.0)
    distance = math.sqrt(sum((channel - neutral) ** 2 for channel, neutral in zip(pixel, neutral_rgb)))
    return distance <= 18 or (saturation < 0.08 and value > 0.82)


def _parse_color(value: str | tuple[int, int, int]) -> tuple[int, int, int]:
    if isinstance(value, tuple) and len(value) == 3:
        return tuple(int(channel) for channel in value)
    normalized = str(value or "").strip().lstrip("#")
    if len(normalized) != 6:
        return (247, 242, 236)
    try:
        return tuple(int(normalized[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (247, 242, 236)


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _face_hint_to_xyxy(value: Any, image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    if value is None or isinstance(value, (str, bytes)):
        return None
    if isinstance(value, Mapping):
        if {"left", "top", "right", "bottom"}.issubset(value.keys()):
            return _clamped_face_bbox((value["left"], value["top"], value["right"], value["bottom"]), image_size)
        if {"x", "y", "width", "height"}.issubset(value.keys()):
            return _xywh_to_xyxy(value["x"], value["y"], value["width"], value["height"], image_size)
        if "bbox_xyxy" in value:
            return _face_hint_to_xyxy(value["bbox_xyxy"], image_size)
        if "bbox_xywh" in value:
            x, y, box_width, box_height = value["bbox_xywh"]
            return _xywh_to_xyxy(x, y, box_width, box_height, image_size)
        nested = value.get("bbox") or value.get("box") or value.get("boundingBox")
        if nested is not None:
            bbox_format = str(value.get("format") or value.get("bbox_format") or "").lower()
            if bbox_format in {"xywh", "normalized_xywh"} or _looks_normalized_xywh(nested):
                x, y, box_width, box_height = nested
                return _xywh_to_xyxy(x, y, box_width, box_height, image_size)
            return _face_hint_to_xyxy(nested, image_size)
        return None

    bbox = _field(value, "bbox") or _field(value, "box") or _field(value, "boundingBox")
    if bbox is not None:
        class_name = type(value).__name__.lower()
        if "facedetection" in class_name or _looks_normalized_xywh(bbox):
            x, y, box_width, box_height = bbox
            return _xywh_to_xyxy(x, y, box_width, box_height, image_size)
        return _face_hint_to_xyxy(bbox, image_size)

    if isinstance(value, Sequence) and len(value) >= 4:
        return _clamped_face_bbox(value[:4], image_size)
    return None


def _face_confidence(value: Any) -> float | None:
    confidence = _field(value, "confidence")
    if confidence is None and isinstance(value, Mapping):
        confidence = value.get("score")
    if confidence is None:
        return None
    try:
        return float(confidence)
    except (TypeError, ValueError):
        return None


def _xywh_to_xyxy(
    x: Any,
    y: Any,
    box_width: Any,
    box_height: Any,
    image_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    width, height = image_size
    left = float(x)
    top = float(y)
    face_width = float(box_width)
    face_height = float(box_height)
    if max(abs(left), abs(top), abs(face_width), abs(face_height)) <= 1.0:
        left *= width
        face_width *= width
        top *= height
        face_height *= height
    return _clamped_face_bbox((left, top, left + face_width, top + face_height), image_size)


def _looks_normalized_xywh(value: Any) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 4:
        return False
    try:
        numbers = [float(value[index]) for index in range(4)]
    except (TypeError, ValueError):
        return False
    return all(0.0 <= number <= 1.0 for number in numbers) and numbers[2] > 0 and numbers[3] > 0


def _clamped_face_bbox(value: Sequence[Any], image_size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    try:
        bbox = tuple(int(round(float(value[index]))) for index in range(4))
    except (TypeError, ValueError):
        return None
    left, top, right, bottom = _clamp_bbox(bbox, image_size[0], image_size[1])
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _bbox_to_xyxy(value: Any) -> tuple[int, int, int, int] | None:
    if value is None or isinstance(value, (str, bytes)):
        return None
    if isinstance(value, Mapping):
        if {"left", "top", "right", "bottom"}.issubset(value.keys()):
            return (int(value["left"]), int(value["top"]), int(value["right"]), int(value["bottom"]))
        if {"x", "y", "width", "height"}.issubset(value.keys()):
            x = int(value["x"])
            y = int(value["y"])
            return (x, y, x + int(value["width"]), y + int(value["height"]))
        return _bbox_to_xyxy(value.get("bbox") or value.get("box") or value.get("boundingBox"))
    if not isinstance(value, Sequence) or len(value) < 4:
        return None
    left, top, right, bottom = (int(round(float(value[index]))) for index in range(4))
    return (left, top, right, bottom)


def _derived_region(
    kind: str,
    raw_bbox: tuple[int, int, int, int],
    image_width: int,
    image_height: int,
    foreground_mask: Image.Image | None,
) -> DerivedRegionColorRegion:
    left, top, right, bottom = raw_bbox
    clamped = _clamp_bbox(raw_bbox, image_width, image_height)
    clamped_area = max(0, clamped[2] - clamped[0]) * max(0, clamped[3] - clamped[1])
    raw_area = max(1, right - left) * max(1, bottom - top)
    if clamped_area < 24 or clamped[2] - clamped[0] < 4 or clamped[3] - clamped[1] < 4:
        reason = "clothing_region_not_visible" if kind == "clothing" else f"{kind}_region_too_small"
        return DerivedRegionColorRegion(kind, clamped, reason)
    if clamped_area / raw_area < 0.45:
        return DerivedRegionColorRegion(kind, clamped, f"{kind}_region_cut_off")

    mask = _prepare_mask(foreground_mask, (image_width, image_height))
    if mask is not None and _foreground_coverage(mask, clamped) < 0.35:
        return DerivedRegionColorRegion(kind, clamped, f"{kind}_region_outside_foreground")
    return DerivedRegionColorRegion(kind, clamped)


def _prepare_mask(mask: Image.Image | None, image_size: tuple[int, int]) -> Image.Image | None:
    if mask is None:
        return None
    prepared = mask.convert("L")
    if prepared.size != image_size:
        prepared = prepared.resize(image_size)
    return prepared


def _foreground_coverage(mask: Image.Image, bbox: tuple[int, int, int, int]) -> float:
    left, top, right, bottom = bbox
    total = max(1, (right - left) * (bottom - top))
    foreground = 0
    for y in range(top, bottom):
        for x in range(left, right):
            if mask.getpixel((x, y)) > 127:
                foreground += 1
    return foreground / total


def _clamp_bbox(bbox: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    return (
        max(0, min(width, left)),
        max(0, min(height, top)),
        max(0, min(width, right)),
        max(0, min(height, bottom)),
    )


def _circular_median(hues: Sequence[float]) -> float:
    if not hues:
        return 0.0
    sin_sum = sum(math.sin(math.radians(hue)) for hue in hues)
    cos_sum = sum(math.cos(math.radians(hue)) for hue in hues)
    angle = math.degrees(math.atan2(sin_sum, cos_sum))
    return angle + 360.0 if angle < 0 else angle


def _rgb_to_lab(red: int, green: int, blue: int) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(channel / 255.0) for channel in (red, green, blue))
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    x /= 0.95047
    z /= 1.08883
    fx, fy, fz = (_lab_f(component) for component in (x, y, z))
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def _srgb_to_linear(value: float) -> float:
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _lab_f(value: float) -> float:
    if value > 0.008856:
        return value ** (1.0 / 3.0)
    return 7.787 * value + (16.0 / 116.0)
