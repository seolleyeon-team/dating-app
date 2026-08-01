"""Process-local, versioned blur assessment for conservative shadow evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from PIL import Image

from .diagnostic_metrics import SafeStageMetrics, measure_safe_metrics
from .diagnostic_roi import canonical_downscale, face_quality_roi
from .types import InternalFaceDetection

BlurDecision = Literal[
    "pass",
    "borderline",
    "reject_true_blur",
    "reject_low_resolution",
    "reject_low_light",
    "reject_compression",
    "reject_invalid_roi",
    "needs_review",
]


@dataclass(frozen=True)
class BlurAssessmentConfig:
    """Configurable, uncalibrated candidate policy for shadow comparison only."""

    metric_version: str = "avatar_face_blur_multimetric_v3"
    policy_version: str = "pr85_v3_shadow"
    calibration_status: str = "uncalibrated_candidate"
    canonical_short_side_px: int = 160
    quality_roi_margin_ratio: float = 0.12
    min_native_short_side_px: int = 64
    min_valid_pixel_ratio: float = 0.80

    candidate_blur_laplacian_max: float = 50.0
    candidate_blur_tenengrad_max: float = 400.0
    candidate_blur_edge_density_max: float = 0.03
    candidate_blur_local_contrast_max: float = 3.0
    required_blur_signal_count: int = 2

    candidate_clear_laplacian_min: float = 70.0
    candidate_clear_tenengrad_min: float = 576.0
    candidate_clear_edge_density_min: float = 0.05
    candidate_clear_local_contrast_min: float = 4.0
    required_clear_signal_count: int = 3

    candidate_canonical_blur_laplacian_max: float = 80.0
    candidate_canonical_blur_tenengrad_max: float = 1024.0
    candidate_canonical_blur_edge_density_max: float = 0.08
    candidate_canonical_blur_local_contrast_max: float = 4.0
    required_canonical_blur_signal_count: int = 1
    candidate_canonical_clear_laplacian_min: float = 80.0
    candidate_canonical_clear_tenengrad_min: float = 1024.0
    candidate_canonical_clear_edge_density_min: float = 0.08
    candidate_canonical_clear_local_contrast_min: float = 5.0
    required_canonical_clear_signal_count: int = 2

    candidate_underexposed_luminance_max: float = 30.0
    candidate_overexposed_luminance_min: float = 235.0
    candidate_severe_clipping_ratio: float = 0.60
    candidate_severe_compression_risk: float = 0.60
    candidate_motion_directionality_min: float = 0.80
    required_motion_low_signal_count: int = 1


@dataclass(frozen=True)
class BlurAssessment:
    """Sensitive metric evidence that must remain process-local.

    Only version and decision metadata may be sanitized for persistence by an
    integrating caller. This module does not mutate the active quality gate.
    """

    decision: BlurDecision
    reason_code: Optional[str]
    root_cause: str
    metric_version: str
    policy_version: str
    calibration_status: str

    native_face_short_side_px: int = field(repr=False)
    native_roi_width_px: int = field(repr=False)
    native_roi_height_px: int = field(repr=False)
    canonical_resize_scale: float = field(repr=False)
    valid_pixel_ratio: float = field(repr=False)

    laplacian_variance: Optional[float] = field(repr=False)
    tenengrad_score: Optional[float] = field(repr=False)
    edge_density: Optional[float] = field(repr=False)
    local_contrast: Optional[float] = field(repr=False)
    exposure_score: Optional[float] = field(repr=False)
    clipping_ratio: Optional[float] = field(repr=False)
    compression_risk: Optional[float] = field(repr=False)
    confidence: float = field(repr=False)

    native_metrics: SafeStageMetrics = field(repr=False, compare=False)
    canonical_metrics: SafeStageMetrics = field(repr=False, compare=False)


class BlurAssessor:
    """Build the native quality ROI and evaluate a candidate shadow policy."""

    def __init__(self, config: Optional[BlurAssessmentConfig] = None) -> None:
        self.config = config or BlurAssessmentConfig()

    def assess(
        self,
        image: Image.Image,
        primary: InternalFaceDetection,
    ) -> BlurAssessment:
        cfg = self.config
        quality_roi = face_quality_roi(
            image,
            primary.bbox_pixels,
            margin_ratio=cfg.quality_roi_margin_ratio,
        )
        canonical_roi, canonical_scale = canonical_downscale(
            quality_roi,
            canonical_short_side=cfg.canonical_short_side_px,
        )
        native = measure_safe_metrics(quality_roi)
        canonical = measure_safe_metrics(canonical_roi)
        context = _AssessmentContext(
            config=cfg,
            primary=primary,
            roi_size=quality_roi.image.size,
            canonical_scale=canonical_scale,
            native=native,
            canonical=canonical,
        )

        if primary.face_short_side_px < cfg.min_native_short_side_px:
            return context.result(
                decision="reject_low_resolution",
                reason_code="avatar_source_face_too_small",
                root_cause="LOW_FACE_RESOLUTION",
                confidence=1.0,
            )
        if _touches_image_border(primary, image.size):
            return context.result(
                decision="reject_invalid_roi",
                reason_code="avatar_source_face_out_of_frame",
                root_cause="INVALID_FACE_QUALITY_ROI",
                confidence=1.0,
            )
        if (
            native.status != "measured"
            or canonical.status != "measured"
            or native.valid_pixel_ratio < cfg.min_valid_pixel_ratio
        ):
            return context.result(
                decision="reject_invalid_roi",
                reason_code="avatar_source_face_out_of_frame",
                root_cause="INVALID_FACE_QUALITY_ROI",
                confidence=1.0,
            )
        if _has_severe_exposure(native, cfg):
            return context.result(
                decision="reject_low_light",
                reason_code="avatar_source_low_light",
                root_cause="LOW_LIGHT_OR_EXPOSURE",
                confidence=0.9,
            )
        if _at_least(
            native.compression_risk,
            cfg.candidate_severe_compression_risk,
        ):
            return context.result(
                decision="needs_review",
                reason_code="avatar_source_analysis_uncertain",
                root_cause="COMPRESSION_RISK_UNVALIDATED",
                confidence=0.5,
            )

        blur_votes = _blur_signal_count(native, cfg)
        clear_votes = _clear_signal_count(native, cfg)
        canonical_blur_votes = _canonical_blur_signal_count(canonical, cfg)
        canonical_clear_votes = _canonical_clear_signal_count(canonical, cfg)
        native_blur_agreement = blur_votes >= cfg.required_blur_signal_count
        blur_agreement = native_blur_agreement and (
            canonical_blur_votes >= cfg.required_canonical_blur_signal_count
            or blur_votes >= 3
        )
        clear_agreement = (
            clear_votes >= cfg.required_clear_signal_count
            and canonical_clear_votes >= cfg.required_canonical_clear_signal_count
        )
        if (
            native_blur_agreement
            and canonical_clear_votes >= cfg.required_canonical_clear_signal_count
        ):
            return context.result(
                decision="borderline",
                reason_code="avatar_source_analysis_uncertain",
                root_cause="CONFLICTING_NATIVE_CANONICAL_SIGNALS",
                confidence=0.5,
            )
        if blur_agreement:
            return context.result(
                decision="reject_true_blur",
                reason_code="avatar_source_face_too_blurry",
                root_cause="TRUE_BLUR_UNTYPED",
                confidence=min(1.0, 0.55 + 0.1 * blur_votes),
            )
        if _has_motion_blur_support(
            native,
            canonical,
            native_low_signal_count=blur_votes,
            canonical_low_signal_count=canonical_blur_votes,
            config=cfg,
        ):
            return context.result(
                decision="borderline",
                reason_code="avatar_source_analysis_uncertain",
                root_cause="DIRECTIONAL_BLUR_SUPPORT",
                confidence=0.55,
            )
        if clear_agreement:
            return context.result(
                decision="pass",
                reason_code=None,
                root_cause="NO_BLOCKING_QUALITY_CAUSE",
                confidence=min(1.0, 0.55 + 0.1 * clear_votes),
            )
        if blur_votes > 0 and clear_votes > 0:
            return context.result(
                decision="borderline",
                reason_code="avatar_source_analysis_uncertain",
                root_cause="CONFLICTING_QUALITY_SIGNALS",
                confidence=0.5,
            )
        return context.result(
            decision="needs_review",
            reason_code="avatar_source_analysis_uncertain",
            root_cause="INSUFFICIENT_QUALITY_EVIDENCE",
            confidence=0.35,
        )


@dataclass(frozen=True)
class _AssessmentContext:
    config: BlurAssessmentConfig
    primary: InternalFaceDetection
    roi_size: tuple[int, int]
    canonical_scale: float
    native: SafeStageMetrics
    canonical: SafeStageMetrics

    def result(
        self,
        *,
        decision: BlurDecision,
        reason_code: Optional[str],
        root_cause: str,
        confidence: float,
    ) -> BlurAssessment:
        luminance = self.native.mean_luminance
        exposure_score = None
        if luminance is not None:
            exposure_score = max(
                0.0,
                min(1.0, 1.0 - abs(luminance - 127.5) / 127.5),
            )
        cfg = self.config
        return BlurAssessment(
            decision=decision,
            reason_code=reason_code,
            root_cause=root_cause,
            metric_version=cfg.metric_version,
            policy_version=cfg.policy_version,
            calibration_status=cfg.calibration_status,
            native_face_short_side_px=int(self.primary.face_short_side_px),
            native_roi_width_px=int(self.roi_size[0]),
            native_roi_height_px=int(self.roi_size[1]),
            canonical_resize_scale=float(self.canonical_scale),
            valid_pixel_ratio=float(self.native.valid_pixel_ratio),
            laplacian_variance=self.native.laplacian_variance,
            tenengrad_score=self.native.tenengrad_score,
            edge_density=self.native.edge_density,
            local_contrast=self.native.local_contrast,
            exposure_score=exposure_score,
            clipping_ratio=self.native.clipping_ratio,
            compression_risk=self.native.compression_risk,
            confidence=max(0.0, min(1.0, float(confidence))),
            native_metrics=self.native,
            canonical_metrics=self.canonical,
        )


def assess_primary_face_quality(
    image: Image.Image,
    primary: InternalFaceDetection,
    *,
    config: Optional[BlurAssessmentConfig] = None,
) -> BlurAssessment:
    return BlurAssessor(config).assess(image, primary)


def _touches_image_border(
    primary: InternalFaceDetection,
    image_size: tuple[int, int],
) -> bool:
    width, height = image_size
    box = primary.bbox_pixels
    return (
        box.x_min <= 0
        or box.y_min <= 0
        or box.x_max >= width
        or box.y_max >= height
    )


def _has_severe_exposure(
    metrics: SafeStageMetrics,
    config: BlurAssessmentConfig,
) -> bool:
    luminance = metrics.mean_luminance
    clipping = metrics.clipping_ratio
    if luminance is None or clipping is None:
        return False
    return (
        luminance <= config.candidate_underexposed_luminance_max
        or luminance >= config.candidate_overexposed_luminance_min
        or clipping >= config.candidate_severe_clipping_ratio
    )


def _blur_signal_count(
    metrics: SafeStageMetrics,
    config: BlurAssessmentConfig,
) -> int:
    return sum(
        (
            _below(metrics.laplacian_variance, config.candidate_blur_laplacian_max),
            _below(metrics.tenengrad_score, config.candidate_blur_tenengrad_max),
            _below(metrics.edge_density, config.candidate_blur_edge_density_max),
            _below(metrics.local_contrast, config.candidate_blur_local_contrast_max),
        )
    )


def _clear_signal_count(
    metrics: SafeStageMetrics,
    config: BlurAssessmentConfig,
) -> int:
    return sum(
        (
            _at_least(metrics.laplacian_variance, config.candidate_clear_laplacian_min),
            _at_least(metrics.tenengrad_score, config.candidate_clear_tenengrad_min),
            _at_least(metrics.edge_density, config.candidate_clear_edge_density_min),
            _at_least(metrics.local_contrast, config.candidate_clear_local_contrast_min),
        )
    )


def _canonical_blur_signal_count(
    metrics: SafeStageMetrics,
    config: BlurAssessmentConfig,
) -> int:
    return sum(
        (
            _below(metrics.laplacian_variance, config.candidate_canonical_blur_laplacian_max),
            _below(metrics.tenengrad_score, config.candidate_canonical_blur_tenengrad_max),
            _below(metrics.edge_density, config.candidate_canonical_blur_edge_density_max),
            _below(metrics.local_contrast, config.candidate_canonical_blur_local_contrast_max),
        )
    )


def _canonical_clear_signal_count(
    metrics: SafeStageMetrics,
    config: BlurAssessmentConfig,
) -> int:
    return sum(
        (
            _at_least(metrics.laplacian_variance, config.candidate_canonical_clear_laplacian_min),
            _at_least(metrics.tenengrad_score, config.candidate_canonical_clear_tenengrad_min),
            _at_least(metrics.edge_density, config.candidate_canonical_clear_edge_density_min),
            _at_least(metrics.local_contrast, config.candidate_canonical_clear_local_contrast_min),
        )
    )


def _has_motion_blur_support(
    native: SafeStageMetrics,
    canonical: SafeStageMetrics,
    *,
    native_low_signal_count: int,
    canonical_low_signal_count: int,
    config: BlurAssessmentConfig,
) -> bool:
    low_signal_count = native_low_signal_count + canonical_low_signal_count
    if low_signal_count < config.required_motion_low_signal_count:
        return False
    directionality = max(
        native.gradient_directionality or 0.0,
        canonical.gradient_directionality or 0.0,
    )
    return directionality >= config.candidate_motion_directionality_min


def _below(value: Optional[float], threshold: float) -> bool:
    return value is not None and value < threshold


def _at_least(value: Optional[float], threshold: float) -> bool:
    return value is not None and value >= threshold


__all__ = [
    "BlurAssessment",
    "BlurAssessmentConfig",
    "BlurAssessor",
    "BlurDecision",
    "assess_primary_face_quality",
]
