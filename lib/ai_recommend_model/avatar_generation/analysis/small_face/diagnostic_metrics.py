"""Pure, CPU-only safe metrics used by the local blur diagnostic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from PIL import Image, ImageFilter

from .diagnostic_roi import DiagnosticRoi


@dataclass(frozen=True)
class SafeStageMetrics:
    status: str
    input_short_side_px: int
    valid_pixel_ratio: float
    laplacian_variance: Optional[float]
    tenengrad_score: Optional[float]
    edge_density: Optional[float]
    local_contrast: Optional[float]
    mean_luminance: Optional[float]
    clipping_ratio: Optional[float]
    compression_risk: Optional[float]
    gradient_directionality: Optional[float]

    def to_safe_document(self) -> dict[str, object]:
        return {
            "status": self.status,
            "inputShortSidePx": self.input_short_side_px,
            "validPixelRatio": _rounded(self.valid_pixel_ratio, 4),
            "laplacianVariance": _rounded(self.laplacian_variance, 3),
            "tenengradScore": _rounded(self.tenengrad_score, 3),
            "edgeDensity": _rounded(self.edge_density, 4),
            "localContrast": _rounded(self.local_contrast, 3),
            "meanLuminance": _rounded(self.mean_luminance, 2),
            "clippingRatio": _rounded(self.clipping_ratio, 4),
            "compressionRisk": _rounded(self.compression_risk, 4),
            "gradientDirectionality": _rounded(self.gradient_directionality, 4),
        }


def measure_safe_metrics(roi: DiagnosticRoi) -> SafeStageMetrics:
    """Measure masked sharpness, exposure, and compression signals.

    All derivative measurements exclude the outer filter boundary and pixels
    whose 3x3 neighborhood contains non-source padding. Tenengrad is the
    conventional mean squared Sobel-gradient energy, ``mean(gx**2 + gy**2)``.
    """

    gray_image = roi.image.convert("L")
    gray = np.asarray(gray_image, dtype=np.float32)
    valid = np.asarray(roi.valid_mask.convert("L"), dtype=np.uint8) >= 128
    short_side = min(gray.shape) if gray.ndim == 2 else 0
    valid_ratio = float(valid.mean()) if valid.size else 0.0
    if (
        gray.ndim != 2
        or gray.shape[0] < 3
        or gray.shape[1] < 3
        or int(valid.sum()) < 9
    ):
        return SafeStageMetrics(
            status="invalid",
            input_short_side_px=int(short_side),
            valid_pixel_ratio=valid_ratio,
            laplacian_variance=None,
            tenengrad_score=None,
            edge_density=None,
            local_contrast=None,
            mean_luminance=None,
            clipping_ratio=None,
            compression_risk=None,
            gradient_directionality=None,
        )

    core_valid = _valid_3x3(valid)
    if int(core_valid.sum()) < 9:
        return SafeStageMetrics(
            status="invalid",
            input_short_side_px=int(short_side),
            valid_pixel_ratio=valid_ratio,
            laplacian_variance=None,
            tenengrad_score=None,
            edge_density=None,
            local_contrast=None,
            mean_luminance=None,
            clipping_ratio=None,
            compression_risk=None,
            gradient_directionality=None,
        )

    center = gray[1:-1, 1:-1]
    laplacian = (
        gray[:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, :-2]
        + gray[1:-1, 2:]
        - 4.0 * center
    )
    gx = (
        -gray[:-2, :-2]
        - 2.0 * gray[1:-1, :-2]
        - gray[2:, :-2]
        + gray[:-2, 2:]
        + 2.0 * gray[1:-1, 2:]
        + gray[2:, 2:]
    )
    gy = (
        -gray[:-2, :-2]
        - 2.0 * gray[:-2, 1:-1]
        - gray[:-2, 2:]
        + gray[2:, :-2]
        + 2.0 * gray[2:, 1:-1]
        + gray[2:, 2:]
    )
    gradient = np.sqrt(gx * gx + gy * gy) / 4.0
    valid_values = gray[valid]
    local_mean = np.asarray(
        gray_image.filter(ImageFilter.BoxBlur(radius=2)),
        dtype=np.float32,
    )
    local_residual = np.abs(gray - local_mean)
    local_valid = _erode_valid(valid, radius=2)
    if int(local_valid.sum()) < 9:
        local_valid = valid

    gx_values = gx[core_valid]
    gy_values = gy[core_valid]
    gradient_energy = gx_values * gx_values + gy_values * gy_values
    directionality = _gradient_directionality(
        gx_values,
        gy_values,
        gradient_energy,
    )

    return SafeStageMetrics(
        status="measured",
        input_short_side_px=int(short_side),
        valid_pixel_ratio=valid_ratio,
        laplacian_variance=float(np.var(laplacian[core_valid])),
        tenengrad_score=float(np.mean(gradient_energy)),
        edge_density=float(np.mean(gradient[core_valid] >= 20.0)),
        local_contrast=float(np.sqrt(np.mean(local_residual[local_valid] ** 2))),
        mean_luminance=float(np.mean(valid_values)),
        clipping_ratio=float(
            np.mean((valid_values <= 5.0) | (valid_values >= 250.0))
        ),
        compression_risk=_compression_risk(gray, valid),
        gradient_directionality=directionality,
    )


def exposure_bucket(metrics: SafeStageMetrics) -> str:
    if metrics.status != "measured" or metrics.mean_luminance is None:
        return "unavailable"
    if metrics.mean_luminance < 45.0:
        return "underexposed"
    if metrics.mean_luminance > 220.0:
        return "overexposed"
    if (metrics.clipping_ratio or 0.0) > 0.20:
        return "high_clipping"
    return "normal"


def contrast_bucket(metrics: SafeStageMetrics) -> str:
    value = metrics.local_contrast
    if value is None:
        return "unavailable"
    if value < 3.0:
        return "very_low"
    if value < 7.0:
        return "low"
    if value < 14.0:
        return "moderate"
    return "high"


def compression_bucket(metrics: SafeStageMetrics) -> str:
    value = metrics.compression_risk
    if value is None:
        return "unavailable"
    if value < 0.15:
        return "low"
    if value < 0.40:
        return "moderate"
    return "high"


def _valid_3x3(valid: np.ndarray) -> np.ndarray:
    return _erode_valid(valid, radius=1)[1:-1, 1:-1]


def _erode_valid(valid: np.ndarray, *, radius: int) -> np.ndarray:
    if radius <= 0:
        return valid.copy()
    height, width = valid.shape
    if height <= 2 * radius or width <= 2 * radius:
        return np.zeros_like(valid, dtype=bool)
    core_height = height - 2 * radius
    core_width = width - 2 * radius
    core = valid[radius : height - radius, radius : width - radius].copy()
    diameter = radius * 2 + 1
    for row_offset in range(diameter):
        for column_offset in range(diameter):
            core &= valid[
                row_offset : row_offset + core_height,
                column_offset : column_offset + core_width,
            ]
    output = np.zeros_like(valid, dtype=bool)
    output[radius : height - radius, radius : width - radius] = core
    return output


def _gradient_directionality(
    gx: np.ndarray,
    gy: np.ndarray,
    energy: np.ndarray,
) -> Optional[float]:
    strong = energy > (20.0 * 4.0) ** 2
    if int(strong.sum()) < 16:
        return None
    angles = np.arctan2(gy[strong], gx[strong])
    weights = np.sqrt(energy[strong])
    vector = np.sum(weights * np.exp(2j * angles))
    weight_sum = float(np.sum(weights))
    return float(abs(vector) / weight_sum) if weight_sum > 0.0 else None


def _compression_risk(gray: np.ndarray, valid: np.ndarray) -> Optional[float]:
    """Estimate 8-pixel block-boundary excess without assuming grid phase zero."""

    vertical_differences = np.abs(gray[:, 1:] - gray[:, :-1])
    vertical_valid = valid[:, 1:] & valid[:, :-1]
    horizontal_differences = np.abs(gray[1:, :] - gray[:-1, :])
    horizontal_valid = valid[1:, :] & valid[:-1, :]
    vertical_indices = np.arange(1, gray.shape[1])
    horizontal_indices = np.arange(1, gray.shape[0])
    phase_risks: list[float] = []

    for phase in range(8):
        vertical_boundary = (vertical_indices - phase) % 8 == 0
        horizontal_boundary = (horizontal_indices - phase) % 8 == 0
        boundary_values = [
            vertical_differences[:, vertical_boundary][
                vertical_valid[:, vertical_boundary]
            ],
            horizontal_differences[horizontal_boundary, :][
                horizontal_valid[horizontal_boundary, :]
            ],
        ]
        interior_values = [
            vertical_differences[:, ~vertical_boundary][
                vertical_valid[:, ~vertical_boundary]
            ],
            horizontal_differences[~horizontal_boundary, :][
                horizontal_valid[~horizontal_boundary, :]
            ],
        ]
        boundary_values = [values for values in boundary_values if values.size]
        interior_values = [values for values in interior_values if values.size]
        if not boundary_values or not interior_values:
            continue
        boundary_mean = float(np.mean(np.concatenate(boundary_values)))
        interior_mean = float(np.mean(np.concatenate(interior_values)))
        phase_risks.append(max(0.0, boundary_mean - interior_mean) / 20.0)

    if not phase_risks:
        return None
    return max(0.0, min(1.0, max(phase_risks)))


def _rounded(value: Optional[float], digits: int) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


__all__ = [
    "SafeStageMetrics",
    "compression_bucket",
    "contrast_bucket",
    "exposure_bucket",
    "measure_safe_metrics",
]
