from __future__ import annotations

from typing import Optional, Sequence, Tuple

from PIL import Image, ImageFilter, ImageStat

from .types import InternalFaceDetection, NormalizedBox, PixelBox, normalized_to_pixel


def enrich_detection(
    *,
    bbox_normalized: NormalizedBox,
    confidence: float,
    image_width: int,
    image_height: int,
    detector_pass: str,
    tile_id: Optional[str] = None,
    keypoints_normalized: Tuple[Tuple[float, float], ...] = (),
    image: Optional[Image.Image] = None,
) -> InternalFaceDetection:
    box = bbox_normalized.clamp()
    pixels = normalized_to_pixel(box, image_width, image_height)
    short_side = pixels.short_side
    area_ratio = box.area
    center_proximity = _center_proximity(box)
    border_clearance = _border_clearance(box)
    sharpness = None
    if image is not None and pixels.width > 2 and pixels.height > 2:
        sharpness = estimate_sharpness(image, pixels)
    return InternalFaceDetection(
        bbox_normalized=box,
        bbox_pixels=pixels,
        keypoints_normalized=keypoints_normalized,
        confidence=float(confidence),
        detector_pass=detector_pass,
        tile_id=tile_id,
        face_short_side_px=short_side,
        face_area_ratio=round(area_ratio, 6),
        center_proximity=center_proximity,
        border_clearance=border_clearance,
        sharpness_score=sharpness,
    )


def estimate_sharpness(image: Image.Image, box: PixelBox) -> Optional[float]:
    try:
        crop = image.convert("L").crop(box.as_tuple())
        if crop.size[0] < 3 or crop.size[1] < 3:
            return None
        edges = crop.filter(ImageFilter.FIND_EDGES)
        stat = ImageStat.Stat(edges)
        # Normalize Laplacian-ish edge energy into ~[0, 1].
        mean = float(stat.mean[0]) if stat.mean else 0.0
        return max(0.0, min(1.0, mean / 40.0))
    except Exception:
        return None


def _center_proximity(box: NormalizedBox) -> float:
    cx = box.x_min + box.width / 2.0
    cy = box.y_min + box.height / 2.0
    distance = ((abs(cx - 0.5) / 0.5) + (abs(cy - 0.5) / 0.5)) / 2.0
    return max(0.0, min(1.0, 1.0 - distance))


def _border_clearance(box: NormalizedBox) -> float:
    right = 1.0 - box.x_max
    bottom = 1.0 - box.y_max
    margin = min(box.x_min, box.y_min, right, bottom)
    return max(0.0, min(1.0, margin / 0.15))


def build_tile_rects(
    width: int,
    height: int,
    *,
    grid: int,
    overlap: float,
) -> list[tuple[str, PixelBox]]:
    if grid < 2 or width <= 0 or height <= 0:
        return []
    stride_x = width / float(grid)
    stride_y = height / float(grid)
    tile_w = int(round(stride_x * (1.0 + overlap)))
    tile_h = int(round(stride_y * (1.0 + overlap)))
    tile_w = max(1, min(width, tile_w))
    tile_h = max(1, min(height, tile_h))
    rects: list[tuple[str, PixelBox]] = []
    for row in range(grid):
        for col in range(grid):
            x0 = int(round(col * stride_x * (1.0 - overlap)))
            y0 = int(round(row * stride_y * (1.0 - overlap)))
            x0 = max(0, min(width - 1, x0))
            y0 = max(0, min(height - 1, y0))
            x1 = min(width, x0 + tile_w)
            y1 = min(height, y0 + tile_h)
            if col == grid - 1:
                x1 = width
            if row == grid - 1:
                y1 = height
            rects.append((f"{grid}x{grid}:{row}:{col}", PixelBox(x0, y0, x1, y1)))
    return rects


def map_tile_box_to_original(
    tile_box_xywh: Tuple[float, float, float, float],
    tile_rect: PixelBox,
    image_width: int,
    image_height: int,
) -> NormalizedBox:
    tx, ty, tw, th = tile_box_xywh
    tile_w = max(1, tile_rect.width)
    tile_h = max(1, tile_rect.height)
    abs_x0 = tile_rect.x_min + tx * tile_w
    abs_y0 = tile_rect.y_min + ty * tile_h
    abs_x1 = abs_x0 + tw * tile_w
    abs_y1 = abs_y0 + th * tile_h
    return NormalizedBox(
        abs_x0 / float(image_width),
        abs_y0 / float(image_height),
        abs_x1 / float(image_width),
        abs_y1 / float(image_height),
    ).clamp()


__all__ = [
    "enrich_detection",
    "estimate_sharpness",
    "build_tile_rects",
    "map_tile_box_to_original",
]
