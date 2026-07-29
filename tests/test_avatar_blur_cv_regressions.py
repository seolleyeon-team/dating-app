import inspect
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

import avatar_generation.analysis.small_face.blur_assessment as blur_module  # noqa: E402
from avatar_generation.analysis.small_face.blur_assessment import BlurAssessor  # noqa: E402
from avatar_generation.analysis.small_face.diagnostic_metrics import (  # noqa: E402
    SafeStageMetrics,
    _compression_risk,
    measure_safe_metrics,
)
from avatar_generation.analysis.small_face.diagnostic_roi import (  # noqa: E402
    DiagnosticRoi,
    canonical_downscale,
    extract_with_valid_mask,
    full_image_roi,
)
from avatar_generation.analysis.small_face.types import (  # noqa: E402
    InternalFaceDetection,
    PixelBox,
    pixel_to_normalized,
)
import scripts.avatar_blur_diagnostics as diagnostic_script  # noqa: E402


def _detection(box: PixelBox = PixelBox(32, 32, 224, 224)) -> InternalFaceDetection:
    return InternalFaceDetection(
        bbox_normalized=pixel_to_normalized(box, 256, 256),
        bbox_pixels=box,
        confidence=0.95,
        face_short_side_px=min(box.width, box.height),
        face_area_ratio=0.5,
        center_proximity=0.9,
        border_clearance=0.8,
        sharpness_score=0.8,
    )


def _metric(
    *,
    laplacian: float,
    tenengrad: float,
    edge_density: float,
    contrast: float,
    compression: float = 0.0,
    directionality: float = 0.1,
) -> SafeStageMetrics:
    return SafeStageMetrics(
        status="measured",
        input_short_side_px=160,
        valid_pixel_ratio=1.0,
        laplacian_variance=laplacian,
        tenengrad_score=tenengrad,
        edge_density=edge_density,
        local_contrast=contrast,
        mean_luminance=127.0,
        clipping_ratio=0.0,
        compression_risk=compression,
        gradient_directionality=directionality,
    )


def _assess_with_metrics(monkeypatch, native: SafeStageMetrics, canonical: SafeStageMetrics):
    metrics = iter((native, canonical))
    monkeypatch.setattr(blur_module, "measure_safe_metrics", lambda _roi: next(metrics))
    image = Image.new("RGB", (256, 256), (127, 127, 127))
    return BlurAssessor().assess(image, _detection())


def test_native_blur_canonical_clear_conflict_precedes_true_blur(monkeypatch):
    native_blur = _metric(
        laplacian=10.0,
        tenengrad=100.0,
        edge_density=0.01,
        contrast=1.0,
    )
    canonical_clear = _metric(
        laplacian=1000.0,
        tenengrad=10000.0,
        edge_density=0.5,
        contrast=20.0,
    )

    result = _assess_with_metrics(monkeypatch, native_blur, canonical_clear)

    assert result.decision == "borderline"
    assert result.reason_code == "avatar_source_analysis_uncertain"
    assert result.root_cause == "CONFLICTING_NATIVE_CANONICAL_SIGNALS"


def test_sharp_directional_pattern_never_claims_motion_blur_subtype():
    columns = np.where((np.arange(256) // 2) % 2 == 0, 40, 215).astype(np.uint8)
    gray = np.broadcast_to(columns, (256, 256))
    image = Image.fromarray(np.stack((gray, gray, gray), axis=2), "RGB")

    result = BlurAssessor().assess(image, _detection())

    assert result.decision != "reject_true_blur"
    assert "MOTION" not in result.root_cause
    assert "DEFOCUS" not in result.root_cause


def test_directionality_only_supports_borderline(monkeypatch):
    directional = _metric(
        laplacian=60.0,
        tenengrad=2000.0,
        edge_density=0.10,
        contrast=10.0,
        directionality=0.99,
    )
    canonical_ambiguous = _metric(
        laplacian=90.0,
        tenengrad=1100.0,
        edge_density=0.07,
        contrast=4.5,
        directionality=0.99,
    )

    result = _assess_with_metrics(monkeypatch, directional, canonical_ambiguous)

    assert result.decision == "borderline"
    assert result.root_cause == "DIRECTIONAL_BLUR_SUPPORT"


def test_unvalidated_compression_risk_goes_to_review(monkeypatch):
    compressed = _metric(
        laplacian=1000.0,
        tenengrad=10000.0,
        edge_density=0.5,
        contrast=20.0,
        compression=0.9,
    )

    result = _assess_with_metrics(monkeypatch, compressed, compressed)

    assert result.decision == "needs_review"
    assert result.reason_code == "avatar_source_analysis_uncertain"
    assert result.root_cause == "COMPRESSION_RISK_UNVALIDATED"


def test_compression_risk_is_invariant_to_eight_pixel_grid_phase():
    row, column = np.indices((96, 96))
    risks = []
    valid = np.ones((96, 96), dtype=bool)
    for phase in range(8):
        blocks = (((column + phase) // 8) + ((row + phase) // 8)) % 2
        gray = (70 + blocks * 100).astype(np.float32)
        risks.append(_compression_risk(gray, valid))

    assert all(risk is not None for risk in risks)
    assert max(risks) - min(risks) < 0.05


def test_canonical_padding_is_excluded_from_lanczos_metrics():
    rng = np.random.default_rng(27)
    source_array = rng.integers(35, 221, size=(256, 256, 3), dtype=np.uint8)
    source = Image.fromarray(source_array, "RGB")
    padded = extract_with_valid_mask(source, PixelBox(-32, -32, 288, 288))
    padded_canonical, _ = canonical_downscale(padded, canonical_short_side=160)

    baseline_image = source.resize((128, 128), Image.Resampling.LANCZOS).crop(
        (3, 3, 125, 125)
    )
    baseline = DiagnosticRoi(
        image=baseline_image,
        valid_mask=Image.new("L", baseline_image.size, 255),
        source_box=PixelBox(0, 0, *baseline_image.size),
    )
    padded_metrics = measure_safe_metrics(padded_canonical)
    baseline_metrics = measure_safe_metrics(baseline)

    assert padded_metrics.status == "measured"
    assert padded_metrics.laplacian_variance == pytest.approx(
        baseline_metrics.laplacian_variance, rel=0.08
    )
    assert padded_metrics.tenengrad_score == pytest.approx(
        baseline_metrics.tenengrad_score, rel=0.08
    )


def test_border_contacting_primary_face_is_invalid_shadow_roi():
    rng = np.random.default_rng(31)
    image = Image.fromarray(
        rng.integers(35, 221, size=(256, 256, 3), dtype=np.uint8),
        "RGB",
    )
    border_box = PixelBox(0, 40, 160, 220)

    result = BlurAssessor().assess(image, _detection(border_box))

    assert result.decision == "reject_invalid_roi"
    assert result.reason_code == "avatar_source_face_out_of_frame"


def test_tenengrad_is_mean_squared_sobel_gradient_energy():
    gray = np.array(
        [
            [0, 10, 20, 30, 40],
            [5, 15, 25, 35, 45],
            [10, 20, 30, 40, 50],
            [15, 25, 35, 45, 55],
            [20, 30, 40, 50, 60],
        ],
        dtype=np.uint8,
    )
    metrics = measure_safe_metrics(full_image_roi(Image.fromarray(gray, "L")))
    values = gray.astype(np.float32)
    gx = (
        -values[:-2, :-2]
        - 2.0 * values[1:-1, :-2]
        - values[2:, :-2]
        + values[:-2, 2:]
        + 2.0 * values[1:-1, 2:]
        + values[2:, 2:]
    )
    gy = (
        -values[:-2, :-2]
        - 2.0 * values[:-2, 1:-1]
        - values[:-2, 2:]
        + values[2:, :-2]
        + 2.0 * values[2:, 1:-1]
        + values[2:, 2:]
    )

    assert metrics.tenengrad_score == pytest.approx(float(np.mean(gx * gx + gy * gy)))


def test_diagnostic_script_has_no_row_index_decision_bypass():
    source = inspect.getsource(diagnostic_script)

    assert "def _root_cause(" not in source
    assert "row_index ==" not in source
    assert "blur_assessor.assess(image, primary)" in source
