import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageFilter

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

import avatar_generation.analysis.small_face.blur_assessment as blur_module  # noqa: E402
from avatar_generation.analysis.small_face.blur_assessment import BlurAssessor  # noqa: E402
from avatar_generation.analysis.small_face.diagnostic_metrics import (  # noqa: E402
    SafeStageMetrics,
    measure_safe_metrics,
)
from avatar_generation.analysis.small_face.diagnostic_roi import (  # noqa: E402
    canonical_downscale,
    extract_with_valid_mask,
    face_quality_roi,
)
from avatar_generation.analysis.small_face.types import (  # noqa: E402
    InternalFaceDetection,
    PixelBox,
    pixel_to_normalized,
)


def _noise_image(size: int = 256, *, seed: int = 17) -> Image.Image:
    rng = np.random.default_rng(seed)
    array = rng.integers(35, 221, size=(size, size, 3), dtype=np.uint8)
    return Image.fromarray(array, "RGB")


def _detection(*, short_side: int = 192) -> InternalFaceDetection:
    box = PixelBox(32, 32, 224, 224)
    return InternalFaceDetection(
        bbox_normalized=pixel_to_normalized(box, 256, 256),
        bbox_pixels=box,
        confidence=0.95,
        face_short_side_px=short_side,
        face_area_ratio=0.5625,
        center_proximity=0.9,
        border_clearance=0.8,
        sharpness_score=0.8,
    )


def _metric(
    *,
    laplacian: float = 100.0,
    tenengrad: float = 10.0,
    edge_density: float = 0.10,
    contrast: float = 8.0,
    luminance: float = 127.0,
    clipping: float = 0.0,
    compression: float = 0.0,
    status: str = "measured",
    valid_ratio: float = 1.0,
) -> SafeStageMetrics:
    measured = status == "measured"
    return SafeStageMetrics(
        status=status,
        input_short_side_px=160,
        valid_pixel_ratio=valid_ratio,
        laplacian_variance=laplacian if measured else None,
        tenengrad_score=tenengrad if measured else None,
        edge_density=edge_density if measured else None,
        local_contrast=contrast if measured else None,
        mean_luminance=luminance if measured else None,
        clipping_ratio=clipping if measured else None,
        compression_risk=compression if measured else None,
        gradient_directionality=0.1 if measured else None,
    )


def _assess_with_metrics(monkeypatch, native, canonical, *, short_side=192):
    metrics = iter((native, canonical))
    monkeypatch.setattr(blur_module, "measure_safe_metrics", lambda _roi: next(metrics))
    return BlurAssessor().assess(_noise_image(), _detection(short_side=short_side))


def test_face_quality_roi_keeps_native_pixels_and_tracks_padding():
    image = _noise_image()
    interior = face_quality_roi(image, PixelBox(64, 72, 192, 208), margin_ratio=0.125)
    border = face_quality_roi(image, PixelBox(0, 0, 80, 88), margin_ratio=0.25)

    assert interior.image.size == (160, 170)
    assert interior.valid_pixel_ratio == 1.0
    assert border.valid_pixel_ratio < 1.0
    assert border.source_box.x_min < 0
    assert border.source_box.y_min < 0


def test_padding_is_excluded_from_sharpness_metrics():
    source = _noise_image(64)
    unpadded = extract_with_valid_mask(source, PixelBox(0, 0, 64, 64))
    padded = extract_with_valid_mask(source, PixelBox(-16, -16, 80, 80))

    baseline = measure_safe_metrics(unpadded)
    measured = measure_safe_metrics(padded)

    assert padded.valid_pixel_ratio == pytest.approx(4 / 9)
    assert measured.status == "measured"
    assert measured.laplacian_variance == pytest.approx(
        baseline.laplacian_variance, rel=0.01
    )
    assert measured.tenengrad_score == pytest.approx(
        baseline.tenengrad_score, rel=0.01
    )
    assert measured.local_contrast == pytest.approx(
        baseline.local_contrast, rel=0.01
    )


def test_canonical_resize_downscales_but_never_upscales():
    large = extract_with_valid_mask(_noise_image(320), PixelBox(0, 0, 320, 240))
    small = extract_with_valid_mask(_noise_image(96), PixelBox(0, 0, 96, 80))

    downscaled, downscale = canonical_downscale(large, canonical_short_side=160)
    unchanged, unchanged_scale = canonical_downscale(small, canonical_short_side=160)

    assert min(downscaled.image.size) == 160
    assert downscale == pytest.approx(160 / 240)
    assert unchanged is small
    assert unchanged.image.size == small.image.size
    assert unchanged_scale == 1.0


def test_sharp_synthetic_face_passes():
    result = BlurAssessor().assess(_noise_image(), _detection())

    assert result.decision == "pass"
    assert result.canonical_resize_scale <= 1.0


def test_gaussian_and_directional_motion_blur_do_not_pass():
    sharp = _noise_image()
    gaussian = sharp.filter(ImageFilter.GaussianBlur(radius=7))
    pixels = np.asarray(sharp, dtype=np.float32)
    padded = np.pad(pixels, ((0, 0), (12, 12), (0, 0)), mode="edge")
    cumulative = np.cumsum(padded, axis=1)
    motion = (cumulative[:, 24:] - cumulative[:, :-24]) / 24.0
    motion_image = Image.fromarray(np.clip(motion, 0, 255).astype(np.uint8), "RGB")

    gaussian_result = BlurAssessor().assess(gaussian, _detection())
    motion_result = BlurAssessor().assess(motion_image, _detection())

    assert gaussian_result.decision == "reject_true_blur"
    assert motion_result.decision in {"reject_true_blur", "borderline"}


def test_low_resolution_precedes_low_light_and_blur(monkeypatch):
    severe = _metric(
        laplacian=0,
        tenengrad=0,
        edge_density=0,
        contrast=0,
        luminance=5,
        clipping=1,
    )

    result = _assess_with_metrics(monkeypatch, severe, severe, short_side=40)

    assert result.decision == "reject_low_resolution"
    assert result.reason_code == "avatar_source_face_too_small"


def test_low_light_is_separate_from_blur(monkeypatch):
    low_light = _metric(luminance=10, clipping=0.9)

    result = _assess_with_metrics(monkeypatch, low_light, low_light)

    assert result.decision == "reject_low_light"
    assert result.reason_code == "avatar_source_low_light"


def test_invalid_roi_is_rejected_before_metric_policy(monkeypatch):
    invalid = _metric(status="invalid", valid_ratio=0.0)

    result = _assess_with_metrics(monkeypatch, invalid, invalid)

    assert result.decision == "reject_invalid_roi"
    assert result.reason_code == "avatar_source_face_out_of_frame"


def test_assessment_repr_keeps_process_local_evidence_private():
    result = BlurAssessor().assess(_noise_image(), _detection())
    rendered = repr(result).lower()

    assert "native_metrics=" not in rendered
    assert "canonical_metrics=" not in rendered
    assert "bbox" not in rendered
    assert "landmark" not in rendered
    assert "pixelbox" not in rendered
