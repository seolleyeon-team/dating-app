from __future__ import annotations

from typing import List, Sequence

from .types import InternalFaceDetection


def merge_detections_nms(
    detections: Sequence[InternalFaceDetection],
    *,
    iou_threshold: float,
) -> List[InternalFaceDetection]:
    """Merge duplicate detections produced by different detector passes."""
    ordered = sorted(detections, key=lambda item: item.confidence, reverse=True)
    kept: List[InternalFaceDetection] = []
    for candidate in ordered:
        merged = False
        for index, existing in enumerate(kept):
            if not _can_merge_cross_pass(existing, candidate):
                continue
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
    # Keep one internally consistent detection. Averaging only the normalized
    # box would desynchronize it from pixel geometry and sharpness metrics.
    return a if a.confidence >= b.confidence else b


def _can_merge_cross_pass(
    a: InternalFaceDetection,
    b: InternalFaceDetection,
) -> bool:
    if a.detector_pass != b.detector_pass:
        return True
    if a.tile_id is not None and b.tile_id is not None:
        return a.tile_id != b.tile_id
    return False


def detections_overlap_ambiguous(
    a: InternalFaceDetection,
    b: InternalFaceDetection,
    *,
    iou_threshold: float,
) -> bool:
    """True when two faces overlap strongly but were not merged (fail-closed)."""
    return a.bbox_normalized.iou(b.bbox_normalized) >= iou_threshold


__all__ = ["merge_detections_nms", "detections_overlap_ambiguous"]
