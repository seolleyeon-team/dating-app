from __future__ import annotations

from typing import List, Sequence, Tuple

from .config import PrimaryScoreWeights, SmallFacePipelineConfig
from .nms import detections_overlap_ambiguous
from .types import InternalFaceDetection, PrimaryFaceSelection


class PrimaryFaceSelector:
    def __init__(self, config: SmallFacePipelineConfig) -> None:
        self._config = config

    def select(self, detections: Sequence[InternalFaceDetection]) -> PrimaryFaceSelection:
        if not detections:
            return PrimaryFaceSelection(
                primary=None,
                secondary_faces=(),
                primary_score=0.0,
                ambiguous_primary=False,
                classification="no_usable_face",
                reason_code="avatar_source_no_face",
            )

        scored: List[Tuple[float, InternalFaceDetection]] = sorted(
            ((self.score(face), face) for face in detections),
            key=lambda item: item[0],
            reverse=True,
        )
        primary_score, primary = scored[0]
        secondary = tuple(face for _score, face in scored[1:])

        if len(scored) >= 2:
            second_score, second = scored[1]
            if detections_overlap_ambiguous(
                primary,
                second,
                iou_threshold=self._config.cross_pass_nms_iou,
            ):
                return PrimaryFaceSelection(
                    primary=primary,
                    secondary_faces=secondary,
                    primary_score=primary_score,
                    ambiguous_primary=True,
                    classification="ambiguous_detection",
                    reason_code="avatar_source_multiple_primary_faces",
                )
            area_ratio = (
                second.face_area_ratio / primary.face_area_ratio
                if primary.face_area_ratio > 0
                else 0.0
            )
            score_gap = primary_score - second_score
            both_usable = (
                primary.face_short_side_px >= self._config.min_short_side_trait_px
                and second.face_short_side_px >= self._config.min_short_side_trait_px
            )
            if (
                both_usable
                and area_ratio >= self._config.secondary_primary_area_ratio_max
            ) or (
                both_usable
                and second.center_proximity >= 0.55
                and primary.center_proximity >= 0.55
                and score_gap < self._config.primary_score_gap_min
            ):
                return PrimaryFaceSelection(
                    primary=primary,
                    secondary_faces=secondary,
                    primary_score=primary_score,
                    ambiguous_primary=True,
                    classification="multi_face_primary",
                    reason_code="avatar_source_multiple_primary_faces",
                )

        if primary.face_short_side_px < self._config.min_short_side_detect_px:
            return PrimaryFaceSelection(
                primary=primary,
                secondary_faces=secondary,
                primary_score=primary_score,
                ambiguous_primary=False,
                classification="no_usable_face",
                reason_code="avatar_source_face_too_small",
            )

        classification = (
            "clear_primary_with_small_secondary_faces"
            if secondary
            else "single_clear_primary"
        )
        return PrimaryFaceSelection(
            primary=primary,
            secondary_faces=secondary,
            primary_score=primary_score,
            ambiguous_primary=False,
            classification=classification,
            reason_code=None,
        )

    def score(self, face: InternalFaceDetection) -> float:
        weights: PrimaryScoreWeights = self._config.score_weights
        confidence = max(0.0, min(1.0, face.confidence))
        # Bound area contribution so huge poster faces do not dominate.
        area = max(0.0, min(1.0, face.face_area_ratio / 0.18))
        center = max(0.0, min(1.0, face.center_proximity))
        border = max(0.0, min(1.0, face.border_clearance))
        if face.sharpness_score is None:
            sharpness = confidence
        else:
            sharpness = max(0.0, min(1.0, face.sharpness_score))
        return round(
            weights.confidence * confidence
            + weights.face_area * area
            + weights.center_proximity * center
            + weights.border_clearance * border
            + weights.sharpness * sharpness,
            6,
        )


__all__ = ["PrimaryFaceSelector"]
