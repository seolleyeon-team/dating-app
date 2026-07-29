"""Internal-only face analysis types. Never serialize to Firestore/client/logs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, Tuple


@dataclass(frozen=True)
class NormalizedBox:
    """Axis-aligned box in normalized image coordinates (x_min/y_min/x_max/y_max)."""

    x_min: float = field(repr=False)
    y_min: float = field(repr=False)
    x_max: float = field(repr=False)
    y_max: float = field(repr=False)

    def clamp(self) -> "NormalizedBox":
        x0 = max(0.0, min(1.0, float(self.x_min)))
        y0 = max(0.0, min(1.0, float(self.y_min)))
        x1 = max(0.0, min(1.0, float(self.x_max)))
        y1 = max(0.0, min(1.0, float(self.y_max)))
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        return NormalizedBox(x0, y0, x1, y1)

    @property
    def width(self) -> float:
        return max(0.0, self.x_max - self.x_min)

    @property
    def height(self) -> float:
        return max(0.0, self.y_max - self.y_min)

    @property
    def area(self) -> float:
        return self.width * self.height

    def as_xywh(self) -> Tuple[float, float, float, float]:
        box = self.clamp()
        return (box.x_min, box.y_min, box.width, box.height)

    def iou(self, other: "NormalizedBox") -> float:
        a = self.clamp()
        b = other.clamp()
        ix0 = max(a.x_min, b.x_min)
        iy0 = max(a.y_min, b.y_min)
        ix1 = min(a.x_max, b.x_max)
        iy1 = min(a.y_max, b.y_max)
        iw = max(0.0, ix1 - ix0)
        ih = max(0.0, iy1 - iy0)
        inter = iw * ih
        if inter <= 0.0:
            return 0.0
        union = a.area + b.area - inter
        return inter / union if union > 0 else 0.0


@dataclass(frozen=True)
class PixelBox:
    x_min: int = field(repr=False)
    y_min: int = field(repr=False)
    x_max: int = field(repr=False)
    y_max: int = field(repr=False)

    def clamp(self, width: int, height: int) -> "PixelBox":
        x0 = max(0, min(int(width), int(self.x_min)))
        y0 = max(0, min(int(height), int(self.y_min)))
        x1 = max(0, min(int(width), int(self.x_max)))
        y1 = max(0, min(int(height), int(self.y_max)))
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        return PixelBox(x0, y0, x1, y1)

    @property
    def width(self) -> int:
        return max(0, self.x_max - self.x_min)

    @property
    def height(self) -> int:
        return max(0, self.y_max - self.y_min)

    @property
    def short_side(self) -> int:
        return min(self.width, self.height)

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.x_min, self.y_min, self.x_max, self.y_max)


def normalized_to_pixel(box: NormalizedBox, width: int, height: int) -> PixelBox:
    b = box.clamp()
    return PixelBox(
        x_min=int(round(b.x_min * width)),
        y_min=int(round(b.y_min * height)),
        x_max=int(round(b.x_max * width)),
        y_max=int(round(b.y_max * height)),
    ).clamp(width, height)


def pixel_to_normalized(box: PixelBox, width: int, height: int) -> NormalizedBox:
    if width <= 0 or height <= 0:
        return NormalizedBox(0.0, 0.0, 0.0, 0.0)
    return NormalizedBox(
        x_min=box.x_min / float(width),
        y_min=box.y_min / float(height),
        x_max=box.x_max / float(width),
        y_max=box.y_max / float(height),
    ).clamp()


@dataclass(frozen=True)
class InternalFaceDetection:
    bbox_normalized: NormalizedBox = field(repr=False)
    bbox_pixels: PixelBox = field(repr=False)
    keypoints_normalized: Tuple[Tuple[float, float], ...] = field(
        default=(), repr=False
    )
    confidence: float = field(default=0.0, repr=False)
    detector_pass: str = field(default="full_image", repr=False)
    tile_id: Optional[str] = field(default=None, repr=False)
    face_short_side_px: int = field(default=0, repr=False)
    face_area_ratio: float = field(default=0.0, repr=False)
    center_proximity: float = field(default=0.0, repr=False)
    border_clearance: float = field(default=0.0, repr=False)
    sharpness_score: Optional[float] = field(default=None, repr=False)


@dataclass(frozen=True)
class PrimaryFaceSelection:
    primary: Optional[InternalFaceDetection] = field(repr=False)
    secondary_faces: Tuple[InternalFaceDetection, ...] = field(repr=False)
    primary_score: float = field(repr=False)
    ambiguous_primary: bool = field(repr=False)
    classification: str = "no_usable_face"
    reason_code: Optional[str] = None


@dataclass(frozen=True)
class CropTransform:
    original_box: PixelBox = field(repr=False)
    padded_box: PixelBox = field(repr=False)
    target_width: int = field(repr=False)
    target_height: int = field(repr=False)
    scale_x: float = field(repr=False)
    scale_y: float = field(repr=False)
    offset_x: float = field(repr=False)
    offset_y: float = field(repr=False)

    def original_to_crop_normalized(
        self,
        box: NormalizedBox,
        original_width: int,
        original_height: int,
    ) -> NormalizedBox:
        px = normalized_to_pixel(box, original_width, original_height)
        x0 = (px.x_min - self.padded_box.x_min) * self.scale_x + self.offset_x
        y0 = (px.y_min - self.padded_box.y_min) * self.scale_y + self.offset_y
        x1 = (px.x_max - self.padded_box.x_min) * self.scale_x + self.offset_x
        y1 = (px.y_max - self.padded_box.y_min) * self.scale_y + self.offset_y
        if self.target_width <= 0 or self.target_height <= 0:
            return NormalizedBox(0.0, 0.0, 0.0, 0.0)
        return NormalizedBox(
            x0 / self.target_width,
            y0 / self.target_height,
            x1 / self.target_width,
            y1 / self.target_height,
        ).clamp()


@dataclass
class InternalFaceAnalysis:
    """Worker-memory only. Do not persist or log coordinates."""

    primary_detection: Optional[InternalFaceDetection] = field(repr=False)
    secondary_detections: Tuple[InternalFaceDetection, ...] = field(repr=False)
    crop_transform: Optional[CropTransform] = field(repr=False)
    crop_image: Any = field(default=None, repr=False)
    crop_landmarks: Any = field(default=None, repr=False)
    original_space_landmarks: Any = field(default=None, repr=False)
    used_tile_fallback: bool = False
    detection_pass_count: int = 0
    classification: str = "no_usable_face"
    reason_code: Optional[str] = None
    metrics: dict = field(default_factory=dict, repr=False)
    quality_assessment: Any = field(default=None, repr=False, compare=False)
    avatar_usable: bool = False
    face_detected: bool = False


__all__ = [
    "NormalizedBox",
    "PixelBox",
    "InternalFaceDetection",
    "PrimaryFaceSelection",
    "CropTransform",
    "InternalFaceAnalysis",
    "normalized_to_pixel",
    "pixel_to_normalized",
]
