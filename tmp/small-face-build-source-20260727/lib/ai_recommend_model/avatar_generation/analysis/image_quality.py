from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError


@dataclass(frozen=True)
class ImageQualitySignals:
    width: int | None
    height: int | None
    luminance_mean: float | None
    lighting_band: str
    sharpness_score: float | None
    blur_band: str
    dark_clipping_ratio: float | None
    bright_clipping_ratio: float | None
    overexposure_band: str
    contrast_score: float | None
    contrast_band: str
    border_occupancy_ratio: float | None
    crop_border_band: str
    background_complexity_score: float | None
    background_complexity_band: str

    def to_document(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "luminanceMean": _round_optional(self.luminance_mean),
            "lightingBand": self.lighting_band,
            "sharpnessScore": _round_optional(self.sharpness_score),
            "blurBand": self.blur_band,
            "darkClippingRatio": _round_optional(self.dark_clipping_ratio),
            "brightClippingRatio": _round_optional(self.bright_clipping_ratio),
            "overexposureBand": self.overexposure_band,
            "contrastScore": _round_optional(self.contrast_score),
            "contrastBand": self.contrast_band,
            "borderOccupancyRatio": _round_optional(self.border_occupancy_ratio),
            "cropBorderBand": self.crop_border_band,
            "backgroundComplexityScore": _round_optional(
                self.background_complexity_score
            ),
            "backgroundComplexityBand": self.background_complexity_band,
        }


def analyze_image_quality(image: bytes | Image.Image) -> ImageQualitySignals:
    try:
        decoded = _decode_image(image)
    except (UnidentifiedImageError, OSError, ValueError):
        return ImageQualitySignals(
            width=None,
            height=None,
            luminance_mean=None,
            lighting_band="invalid",
            sharpness_score=None,
            blur_band="unknown",
            dark_clipping_ratio=None,
            bright_clipping_ratio=None,
            overexposure_band="unknown",
            contrast_score=None,
            contrast_band="unknown",
            border_occupancy_ratio=None,
            crop_border_band="unknown",
            background_complexity_score=None,
            background_complexity_band="unknown",
        )

    gray = ImageOps.grayscale(decoded)
    pixels = _image_values(gray)
    width, height = gray.size
    count = max(1, len(pixels))

    luminance_mean = sum(pixels) / count
    dark_clipping_ratio = sum(1 for value in pixels if value <= 8) / count
    bright_clipping_ratio = sum(1 for value in pixels if value >= 247) / count
    contrast_score = _standard_deviation(pixels, luminance_mean)
    sharpness_score = _sharpness_score(gray)
    border_occupancy_ratio = _border_occupancy_ratio(gray)
    complexity_score = _background_complexity_score(gray)

    return ImageQualitySignals(
        width=width,
        height=height,
        luminance_mean=luminance_mean,
        lighting_band=_lighting_band(luminance_mean, bright_clipping_ratio),
        sharpness_score=sharpness_score,
        blur_band=_blur_band(sharpness_score),
        dark_clipping_ratio=dark_clipping_ratio,
        bright_clipping_ratio=bright_clipping_ratio,
        overexposure_band=_overexposure_band(bright_clipping_ratio, luminance_mean),
        contrast_score=contrast_score,
        contrast_band=_contrast_band(contrast_score),
        border_occupancy_ratio=border_occupancy_ratio,
        crop_border_band=_crop_border_band(border_occupancy_ratio),
        background_complexity_score=complexity_score,
        background_complexity_band=_complexity_band(complexity_score),
    )


def image_quality_from_mapping(value: Mapping[str, Any]) -> ImageQualitySignals:
    return ImageQualitySignals(
        width=_optional_int(value.get("width")),
        height=_optional_int(value.get("height")),
        luminance_mean=_optional_float(value.get("luminanceMean")),
        lighting_band=str(value.get("lightingBand", "unknown")),
        sharpness_score=_optional_float(value.get("sharpnessScore")),
        blur_band=str(value.get("blurBand", "unknown")),
        dark_clipping_ratio=_optional_float(value.get("darkClippingRatio")),
        bright_clipping_ratio=_optional_float(value.get("brightClippingRatio")),
        overexposure_band=str(value.get("overexposureBand", "unknown")),
        contrast_score=_optional_float(value.get("contrastScore")),
        contrast_band=str(value.get("contrastBand", "unknown")),
        border_occupancy_ratio=_optional_float(value.get("borderOccupancyRatio")),
        crop_border_band=str(value.get("cropBorderBand", "unknown")),
        background_complexity_score=_optional_float(
            value.get("backgroundComplexityScore")
        ),
        background_complexity_band=str(
            value.get("backgroundComplexityBand", "unknown")
        ),
    )


def _decode_image(image: bytes | Image.Image) -> Image.Image:
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    with Image.open(io.BytesIO(image)) as opened:
        return opened.convert("RGB")


def _image_values(image: Image.Image) -> list[int]:
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())


def _sharpness_score(gray: Image.Image) -> float:
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_pixels = _image_values(edges)
    return _standard_deviation(edge_pixels, sum(edge_pixels) / max(1, len(edge_pixels)))


def _border_occupancy_ratio(gray: Image.Image) -> float:
    width, height = gray.size
    if width <= 0 or height <= 0:
        return 0.0
    inset = max(1, min(width, height) // 10)
    pixels = gray.load()
    occupied = 0
    total = 0
    for y in range(height):
        for x in range(width):
            if x >= inset and x < width - inset and y >= inset and y < height - inset:
                continue
            total += 1
            center = int(pixels[x, y])
            right = int(pixels[min(width - 1, x + 1), y])
            down = int(pixels[x, min(height - 1, y + 1)])
            if center < 245 or abs(center - right) > 25 or abs(center - down) > 25:
                occupied += 1
    return occupied / max(1, total)


def _background_complexity_score(gray: Image.Image) -> float:
    width, height = gray.size
    if width <= 2 or height <= 2:
        return 0.0
    sample = gray.resize((min(64, width), min(64, height)))
    pixels = sample.load()
    edge_count = 0
    total = 0
    for y in range(sample.height - 1):
        for x in range(sample.width - 1):
            total += 1
            current = int(pixels[x, y])
            if (
                abs(current - int(pixels[x + 1, y])) > 18
                or abs(current - int(pixels[x, y + 1])) > 18
            ):
                edge_count += 1
    return edge_count / max(1, total)


def _lighting_band(mean: float, bright_clip: float) -> str:
    if bright_clip >= 0.35 and mean >= 225:
        return "overexposed"
    if mean < 35:
        return "dark"
    if mean < 85:
        return "dim"
    if mean > 215:
        return "bright"
    return "balanced"


def _blur_band(score: float) -> str:
    if score < 7.0:
        return "blurred"
    if score < 36.0:
        return "soft"
    if score < 80.0:
        return "acceptable"
    return "sharp"


def _overexposure_band(bright_clip: float, mean: float) -> str:
    if bright_clip >= 0.35 and mean >= 225:
        return "severe"
    if bright_clip >= 0.15 or mean >= 235:
        return "moderate"
    if bright_clip >= 0.04 or mean >= 220:
        return "mild"
    return "none"


def _contrast_band(score: float) -> str:
    if score < 12:
        return "low"
    if score < 35:
        return "moderate"
    return "high"


def _crop_border_band(ratio: float) -> str:
    if ratio >= 0.35:
        return "heavy_border"
    if ratio >= 0.08:
        return "bordered"
    return "none"


def _complexity_band(score: float) -> str:
    if score < 0.04:
        return "plain"
    if score < 0.16:
        return "moderate"
    return "complex"


def _standard_deviation(values: Sequence[int], mean: float) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum((float(value) - mean) ** 2 for value in values) / len(values))


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


__all__ = [
    "ImageQualitySignals",
    "analyze_image_quality",
    "image_quality_from_mapping",
]
