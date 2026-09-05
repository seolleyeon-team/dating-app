from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence


SELECTOR_VERSION = "avatar_source_quality_selector_v1"
CONFIDENCE_POLICY_VERSION = "avatar_source_selection_confidence_v1"
NO_ELIGIBLE_SOURCE_ERROR = "avatar_no_eligible_source_photo"


@dataclass(frozen=True)
class SourceQualityWeights:
    face_sharpness: float = 0.25
    useful_face_resolution: float = 0.20
    pose_frontalness: float = 0.20
    illumination_quality: float = 0.15
    face_visibility: float = 0.10
    framing_quality: float = 0.05
    secondary_person_penalty: float = 0.05


@dataclass(frozen=True)
class SourceQualityThresholds:
    min_primary_confidence: float = 0.45
    meaningful_secondary_min_confidence: float = 0.55
    meaningful_secondary_min_area_ratio: float = 0.025
    meaningful_secondary_relative_area: float = 0.35
    min_face_short_side_px: int = 64
    severe_crop_margin: float = 0.002
    min_face_sharpness: float = 0.12
    severe_underexposed_luminance: float = 30.0
    severe_overexposed_luminance: float = 235.0
    severe_clip_ratio: float = 0.60
    min_face_visibility: float = 0.25
    severe_occlusion: float = 0.75
    high_confidence_min_score: float = 0.72
    high_confidence_min_margin: float = 0.12
    medium_confidence_min_score: float = 0.62
    medium_confidence_min_margin: float = 0.04


@dataclass(frozen=True)
class SecondaryFaceSignal:
    confidence: float
    area_ratio: float


@dataclass(frozen=True)
class SourceQualitySignals:
    photo_id: str
    stable_order: int
    image_width: int
    image_height: int
    primary_face_confidence: Optional[float]
    primary_bbox: Optional[tuple[float, float, float, float]] = field(repr=False)
    face_short_side_px: int = 0
    face_sharpness: Optional[float] = None
    yaw_degrees: Optional[float] = None
    pitch_degrees: Optional[float] = None
    roll_degrees: Optional[float] = None
    illumination_quality: Optional[float] = None
    face_luminance: Optional[float] = None
    dark_clip_ratio: Optional[float] = None
    highlight_clip_ratio: Optional[float] = None
    face_visibility: Optional[float] = None
    occlusion_score: Optional[float] = None
    landmarks_reliable: bool = False
    corrupt: bool = False
    secondary_faces: tuple[SecondaryFaceSignal, ...] = ()
    glasses_present: bool = False


@dataclass(frozen=True)
class SourceQualityComponents:
    face_sharpness: float
    useful_face_resolution: float
    pose_frontalness: float
    illumination_quality: float
    face_visibility: float
    framing_quality: float
    secondary_person_penalty: float


@dataclass(frozen=True)
class SourceQualityEvaluation:
    photo_id: str
    stable_order: int
    eligible: bool
    reason_codes: tuple[str, ...]
    quality_score: float
    components: SourceQualityComponents


@dataclass(frozen=True)
class AvatarSourceSelectionResult:
    selector_version: str
    confidence_policy_version: str
    selected_photo_id: Optional[str]
    runner_up_photo_id: Optional[str]
    top1_score: Optional[float]
    top2_score: Optional[float]
    score_margin: Optional[float]
    selection_confidence: Optional[str]
    evaluated_count: int
    eligible_count: int
    reason_histogram: Mapping[str, int]
    evaluations: tuple[SourceQualityEvaluation, ...] = field(repr=False)
    failure_code: Optional[str] = None

    @property
    def selected_source_ids(self) -> tuple[str, ...]:
        return (self.selected_photo_id,) if self.selected_photo_id else ()

    def to_private_document(self) -> dict[str, Any]:
        return {
            "selectorVersion": self.selector_version,
            "confidencePolicyVersion": self.confidence_policy_version,
            "selectedPhotoId": self.selected_photo_id,
            "top1Score": self.top1_score,
            "top2Score": self.top2_score,
            "scoreMargin": self.score_margin,
            "selectionConfidence": self.selection_confidence,
            "evaluatedCount": self.evaluated_count,
            "eligibleCount": self.eligible_count,
            "reasonHistogram": dict(self.reason_histogram),
            "failureCode": self.failure_code,
        }


class AvatarSourceQualitySelector:
    def __init__(
        self,
        *,
        weights: Optional[SourceQualityWeights] = None,
        thresholds: Optional[SourceQualityThresholds] = None,
    ) -> None:
        self.weights = weights or SourceQualityWeights()
        self.thresholds = thresholds or SourceQualityThresholds()

    def evaluate(self, signals: SourceQualitySignals) -> SourceQualityEvaluation:
        reasons = self._hard_gate_reasons(signals)
        components = self._components(signals)
        weights = self.weights
        score = (
            weights.face_sharpness * components.face_sharpness
            + weights.useful_face_resolution * components.useful_face_resolution
            + weights.pose_frontalness * components.pose_frontalness
            + weights.illumination_quality * components.illumination_quality
            + weights.face_visibility * components.face_visibility
            + weights.framing_quality * components.framing_quality
            - weights.secondary_person_penalty * components.secondary_person_penalty
        )
        return SourceQualityEvaluation(
            photo_id=signals.photo_id,
            stable_order=int(signals.stable_order),
            eligible=not reasons,
            reason_codes=tuple(reasons),
            quality_score=round(_clamp01(score), 6),
            components=components,
        )

    def select(
        self, sources: Sequence[SourceQualitySignals]
    ) -> AvatarSourceSelectionResult:
        if len(sources) < 2 or len(sources) > 6:
            raise ValueError("avatar source selection requires 2 to 6 photos")
        evaluations = tuple(self.evaluate(source) for source in sources)
        reason_histogram: dict[str, int] = {}
        for evaluation in evaluations:
            for reason in evaluation.reason_codes:
                reason_histogram[reason] = reason_histogram.get(reason, 0) + 1
        eligible = sorted(
            (item for item in evaluations if item.eligible),
            key=lambda item: (
                -item.quality_score,
                -item.components.face_sharpness,
                -item.components.useful_face_resolution,
                -item.components.pose_frontalness,
                item.stable_order,
                item.photo_id,
            ),
        )
        if not eligible:
            return AvatarSourceSelectionResult(
                selector_version=SELECTOR_VERSION,
                confidence_policy_version=CONFIDENCE_POLICY_VERSION,
                selected_photo_id=None,
                runner_up_photo_id=None,
                top1_score=None,
                top2_score=None,
                score_margin=None,
                selection_confidence=None,
                evaluated_count=len(evaluations),
                eligible_count=0,
                reason_histogram=reason_histogram,
                evaluations=evaluations,
                failure_code=NO_ELIGIBLE_SOURCE_ERROR,
            )

        top = eligible[0]
        runner_up = eligible[1] if len(eligible) > 1 else None
        margin = (
            round(top.quality_score - runner_up.quality_score, 6)
            if runner_up is not None
            else None
        )
        return AvatarSourceSelectionResult(
            selector_version=SELECTOR_VERSION,
            confidence_policy_version=CONFIDENCE_POLICY_VERSION,
            selected_photo_id=top.photo_id,
            runner_up_photo_id=runner_up.photo_id if runner_up else None,
            top1_score=top.quality_score,
            top2_score=runner_up.quality_score if runner_up else None,
            score_margin=margin,
            selection_confidence=self._confidence(top.quality_score, margin),
            evaluated_count=len(evaluations),
            eligible_count=len(eligible),
            reason_histogram=reason_histogram,
            evaluations=evaluations,
        )

    def _hard_gate_reasons(self, source: SourceQualitySignals) -> list[str]:
        threshold = self.thresholds
        if source.corrupt:
            return ["avatar_source_corrupt_image"]
        if (
            source.primary_bbox is None
            or source.primary_face_confidence is None
            or source.primary_face_confidence < threshold.min_primary_confidence
        ):
            return ["avatar_source_no_face"]

        x, y, width, height = source.primary_bbox
        primary_area = max(0.0, width) * max(0.0, height)
        if any(
            secondary.confidence >= threshold.meaningful_secondary_min_confidence
            and (
                secondary.area_ratio >= threshold.meaningful_secondary_min_area_ratio
                or secondary.area_ratio
                >= primary_area * threshold.meaningful_secondary_relative_area
            )
            for secondary in source.secondary_faces
        ):
            return ["avatar_source_multiple_primary_faces"]

        reasons: list[str] = []
        if source.face_short_side_px < threshold.min_face_short_side_px:
            reasons.append("avatar_source_face_too_small")
        margin = threshold.severe_crop_margin
        if x <= margin or y <= margin or x + width >= 1.0 - margin or y + height >= 1.0 - margin:
            reasons.append("avatar_source_face_out_of_frame")
        if source.face_sharpness is not None and source.face_sharpness < threshold.min_face_sharpness:
            reasons.append("avatar_source_face_too_blurry")
        if (
            source.face_luminance is not None
            and source.face_luminance <= threshold.severe_underexposed_luminance
        ) or (source.dark_clip_ratio or 0.0) >= threshold.severe_clip_ratio:
            reasons.append("avatar_source_underexposed")
        if (
            source.face_luminance is not None
            and source.face_luminance >= threshold.severe_overexposed_luminance
        ) or (source.highlight_clip_ratio or 0.0) >= threshold.severe_clip_ratio:
            reasons.append("avatar_source_overexposed")
        if not source.landmarks_reliable:
            reasons.append("avatar_source_landmarks_unreliable")
        if (
            (source.face_visibility is not None and source.face_visibility < threshold.min_face_visibility)
            or (source.occlusion_score or 0.0) >= threshold.severe_occlusion
        ):
            reasons.append("avatar_source_severe_occlusion")
        return reasons

    def _components(self, source: SourceQualitySignals) -> SourceQualityComponents:
        return SourceQualityComponents(
            face_sharpness=_clamp01(source.face_sharpness if source.face_sharpness is not None else 0.0),
            useful_face_resolution=_useful_face_resolution(source),
            pose_frontalness=_pose_frontalness(source),
            illumination_quality=_illumination_quality(source),
            face_visibility=_clamp01(
                source.face_visibility
                if source.face_visibility is not None
                else 1.0 - (source.occlusion_score or 0.0)
            ),
            framing_quality=_framing_quality(source.primary_bbox),
            secondary_person_penalty=_secondary_person_penalty(source.secondary_faces),
        )

    def _confidence(self, top_score: float, margin: Optional[float]) -> str:
        threshold = self.thresholds
        if (
            margin is not None
            and top_score >= threshold.high_confidence_min_score
            and margin >= threshold.high_confidence_min_margin
        ):
            return "high"
        if top_score >= threshold.medium_confidence_min_score and (
            margin is None or margin >= threshold.medium_confidence_min_margin
        ):
            return "medium"
        return "low"


def source_quality_signals_from_analysis(
    *,
    photo_id: str,
    stable_order: int,
    analysis: Any,
) -> SourceQualitySignals:
    internal = getattr(analysis, "internal_face_analysis", None)
    primary = getattr(internal, "primary_detection", None)
    secondary = getattr(internal, "secondary_detections", ()) or ()
    assessment = getattr(internal, "quality_assessment", None)
    native_metrics = getattr(assessment, "native_metrics", None)
    landmarks = getattr(internal, "crop_landmarks", None)
    yaw, pitch, roll = _pose_from_landmarks(landmarks)
    bbox = getattr(analysis, "primary_face_bbox", None)
    rejection_reasons = set(getattr(analysis, "reject_reasons", ()) or ())
    luminance = getattr(native_metrics, "mean_luminance", None)
    clipping = getattr(native_metrics, "clipping_ratio", None)
    return SourceQualitySignals(
        photo_id=photo_id,
        stable_order=stable_order,
        image_width=int(getattr(analysis, "image_width", 0) or 0),
        image_height=int(getattr(analysis, "image_height", 0) or 0),
        primary_face_confidence=getattr(analysis, "primary_face_confidence", None),
        primary_bbox=tuple(bbox) if bbox is not None else None,
        face_short_side_px=int(getattr(primary, "face_short_side_px", 0) or 0),
        face_sharpness=getattr(primary, "sharpness_score", None),
        yaw_degrees=yaw,
        pitch_degrees=pitch,
        roll_degrees=roll,
        illumination_quality=getattr(assessment, "exposure_score", None),
        face_luminance=luminance,
        dark_clip_ratio=clipping if luminance is not None and luminance < 127.5 else 0.0,
        highlight_clip_ratio=clipping if luminance is not None and luminance >= 127.5 else 0.0,
        face_visibility=(
            0.0 if "severe_occlusion" in rejection_reasons else 1.0
        ),
        occlusion_score=getattr(getattr(analysis, "primary_face", None), "occlusion_score", None),
        landmarks_reliable=landmarks is not None,
        corrupt="corrupt_image" in rejection_reasons,
        secondary_faces=tuple(
            SecondaryFaceSignal(
                confidence=float(getattr(face, "confidence", 0.0) or 0.0),
                area_ratio=float(getattr(face, "face_area_ratio", 0.0) or 0.0),
            )
            for face in secondary
        ),
    )


def _useful_face_resolution(source: SourceQualitySignals) -> float:
    pixel_score = _smoothstep(64.0, 256.0, float(source.face_short_side_px))
    if source.primary_bbox is None:
        return 0.0
    area = max(0.0, source.primary_bbox[2]) * max(0.0, source.primary_bbox[3])
    if area <= 0.08:
        portrait_score = _smoothstep(0.01, 0.08, area)
    elif area <= 0.32:
        portrait_score = 1.0
    else:
        portrait_score = 1.0 - _smoothstep(0.32, 0.75, area)
    return round(_clamp01(0.60 * pixel_score + 0.40 * portrait_score), 6)


def _pose_frontalness(source: SourceQualitySignals) -> float:
    if source.yaw_degrees is None or source.pitch_degrees is None or source.roll_degrees is None:
        return 0.45
    yaw_score = 1.0 - _smoothstep(12.0, 68.0, abs(source.yaw_degrees))
    pitch_score = 1.0 - _smoothstep(10.0, 45.0, abs(source.pitch_degrees))
    roll_score = 1.0 - _smoothstep(8.0, 40.0, abs(source.roll_degrees))
    return round(_clamp01(0.60 * yaw_score + 0.25 * pitch_score + 0.15 * roll_score), 6)


def _illumination_quality(source: SourceQualitySignals) -> float:
    if source.illumination_quality is not None:
        base = _clamp01(source.illumination_quality)
    elif source.face_luminance is not None:
        base = 1.0 - abs(float(source.face_luminance) - 127.5) / 127.5
    else:
        base = 0.45
    clipping = max(source.dark_clip_ratio or 0.0, source.highlight_clip_ratio or 0.0)
    return round(_clamp01(base * (1.0 - 0.75 * _clamp01(clipping))), 6)


def _framing_quality(bbox: Optional[tuple[float, float, float, float]]) -> float:
    if bbox is None:
        return 0.0
    x, y, width, height = bbox
    center_x = x + width / 2.0
    center_y = y + height / 2.0
    center_distance = math.sqrt(((center_x - 0.5) / 0.5) ** 2 + ((center_y - 0.45) / 0.55) ** 2)
    centrality = 1.0 - _clamp01(center_distance)
    edge_margin = min(x, y, 1.0 - x - width, 1.0 - y - height)
    clearance = _smoothstep(0.0, 0.12, edge_margin)
    area = max(0.0, width) * max(0.0, height)
    closeup_penalty = _smoothstep(0.38, 0.75, area)
    return round(_clamp01(0.55 * centrality + 0.45 * clearance - 0.55 * closeup_penalty), 6)


def _secondary_person_penalty(faces: Sequence[SecondaryFaceSignal]) -> float:
    if not faces:
        return 0.0
    evidence = sum(
        _clamp01(face.confidence) * _clamp01(face.area_ratio / 0.025)
        for face in faces
    )
    return round(_clamp01(evidence), 6)


def _pose_from_landmarks(landmarks: Any) -> tuple[Optional[float], Optional[float], Optional[float]]:
    if not landmarks:
        return None, None, None
    try:
        if len(landmarks) >= 292:
            left_eye, right_eye = landmarks[33], landmarks[263]
            nose = landmarks[1]
            left_mouth, right_mouth = landmarks[61], landmarks[291]
        elif len(landmarks) >= 5:
            left_eye, right_eye, nose, left_mouth, right_mouth = landmarks[:5]
        else:
            return None, None, None
        lx, ly = float(left_eye.x), float(left_eye.y)
        rx, ry = float(right_eye.x), float(right_eye.y)
        nx, ny = float(nose.x), float(nose.y)
        mx = (float(left_mouth.x) + float(right_mouth.x)) / 2.0
        my = (float(left_mouth.y) + float(right_mouth.y)) / 2.0
        eye_distance = max(0.01, math.hypot(rx - lx, ry - ly))
        eye_mid_x, eye_mid_y = (lx + rx) / 2.0, (ly + ry) / 2.0
        yaw = max(-75.0, min(75.0, ((nx - eye_mid_x) / eye_distance) * 90.0))
        expected_nose_y = eye_mid_y + 0.45 * (my - eye_mid_y)
        pitch = max(-55.0, min(55.0, ((ny - expected_nose_y) / eye_distance) * 70.0))
        roll = math.degrees(math.atan2(ry - ly, rx - lx))
        return yaw, pitch, roll
    except (AttributeError, IndexError, TypeError, ValueError):
        return None, None, None


def _smoothstep(low: float, high: float, value: float) -> float:
    if high <= low:
        return float(value >= high)
    t = _clamp01((float(value) - low) / (high - low))
    return t * t * (3.0 - 2.0 * t)


def _clamp01(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


__all__ = [
    "CONFIDENCE_POLICY_VERSION",
    "NO_ELIGIBLE_SOURCE_ERROR",
    "SELECTOR_VERSION",
    "AvatarSourceQualitySelector",
    "AvatarSourceSelectionResult",
    "SecondaryFaceSignal",
    "SourceQualityComponents",
    "SourceQualityEvaluation",
    "SourceQualitySignals",
    "SourceQualityThresholds",
    "SourceQualityWeights",
    "source_quality_signals_from_analysis",
]
