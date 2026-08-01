from __future__ import annotations

from typing import List, Sequence, Tuple

from .types import InternalFaceDetection, NormalizedBox


def merge_detections_nms(
    detections: Sequence[InternalFaceDetection],
    *,
    iou_threshold: float,
) -> List[InternalFaceDetection]:
    """Cross-pass NMS. Prefer higher confidence; optionally average boxes."""
    ordered = sorted(detections, key=lambda item: item.confidence, reverse=True)
    kept: List[InternalFaceDetection] = []
    for candidate in ordered:
        merged = False
        for index, existing in enumerate(kept):
            if candidate.bbox_normalized.iou(existing.bbox_normalized) < iou_threshold:
                continue
            kept[index] = _merge_pair(existing, candidate)
            merged = True
            break
        if not merged:
            kept.append(candidate)
    return kept


def _merge_pair(
    a: InternalFaceDetection,
    b: InternalFaceDetection,
) -> InternalFaceDetection:
    # Keep higher-confidence detection as representative; confidence-weighted box.
    total = max(1e-6, a.confidence + b.confidence)
    wa = a.confidence / total
    wb = b.confidence / total
    box = NormalizedBox(
        x_min=a.bbox_normalized.x_min * wa + b.bbox_normalized.x_min * wb,
        y_min=a.bbox_normalized.y_min * wa + b.bbox_normalized.y_min * wb,
        x_max=a.bbox_normalized.x_max * wa + b.bbox_normalized.x_max * wb,
        y_max=a.bbox_normalized.y_max * wa + b.bbox_normalized.y_max * wb,
    ).clamp()
    primary = a if a.confidence >= b.confidence else b
    return InternalFaceDetection(
        bbox_normalized=box,
        bbox_pixels=primary.bbox_pixels,
        keypoints_normalized=primary.keypoints_normalized,
        confidence=max(a.confidence, b.confidence),
        detector_pass=primary.detector_pass,
        tile_id=primary.tile_id,
        face_short_side_px=primary.face_short_side_px,
        face_area_ratio=box.area,
        center_proximity=primary.center_proximity,
        border_clearance=primary.border_clearance,
        sharpness_score=primary.sharpness_score,
    )


def detections_overlap_ambiguous(
    a: InternalFaceDetection,
    b: InternalFaceDetection,
    *,
    iou_threshold: float,
) -> bool:
    """True when two faces overlap strongly but were not merged (fail-closed)."""
    return a.bbox_normalized.iou(b.bbox_normalized) >= iou_threshold


__all__ = ["merge_detections_nms", "detections_overlap_ambiguous"]
