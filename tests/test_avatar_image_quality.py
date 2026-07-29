import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.image_quality import analyze_image_quality  # noqa: E402


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _detail_image() -> Image.Image:
    image = Image.new("RGB", (96, 96), "white")
    draw = ImageDraw.Draw(image)
    for x in range(0, 96, 4):
        color = "black" if (x // 4) % 2 == 0 else "white"
        draw.rectangle((x, 0, x + 2, 95), fill=color)
    for y in range(0, 96, 8):
        draw.line((0, y, 95, y), fill=(80, 120, 180), width=1)
    return image


def test_quality_detects_dark_and_overexposed_lighting_bands():
    dark = analyze_image_quality(_png_bytes(Image.new("RGB", (64, 64), (5, 5, 5))))
    overexposed = analyze_image_quality(
        _png_bytes(Image.new("RGB", (64, 64), (255, 250, 246)))
    )

    assert dark.width == 64
    assert dark.height == 64
    assert dark.lighting_band == "dark"
    assert dark.dark_clipping_ratio > 0.95

    assert overexposed.lighting_band == "overexposed"
    assert overexposed.overexposure_band == "severe"
    assert overexposed.bright_clipping_ratio > 0.95


def test_quality_detects_blur_from_real_decoded_pixels():
    detailed = analyze_image_quality(_png_bytes(_detail_image()))
    blurred = analyze_image_quality(
        _png_bytes(_detail_image().filter(ImageFilter.GaussianBlur(radius=3)))
    )

    assert detailed.sharpness_score > blurred.sharpness_score
    assert detailed.blur_band in {"sharp", "acceptable"}
    assert blurred.blur_band in {"blurred", "soft"}


def test_quality_reports_contrast_border_and_complexity_without_geometry():
    image = Image.new("RGB", (80, 80), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 79, 79), outline="black", width=8)
    for x in range(10, 70, 6):
        for y in range(10, 70, 6):
            draw.rectangle((x, y, x + 2, y + 2), fill=((x * 3) % 255, y * 2, 90))

    result = analyze_image_quality(_png_bytes(image))
    doc = result.to_document()

    assert result.contrast_band == "high"
    assert result.border_occupancy_ratio > 0.20
    assert result.crop_border_band in {"bordered", "heavy_border"}
    assert result.background_complexity_band in {"moderate", "complex"}

    rendered = repr(doc).lower()
    assert "path" not in rendered
    assert "pixel" not in rendered
    assert "bbox" not in rendered
    assert set(doc) == {
        "width",
        "height",
        "luminanceMean",
        "lightingBand",
        "sharpnessScore",
        "blurBand",
        "darkClippingRatio",
        "brightClippingRatio",
        "overexposureBand",
        "contrastScore",
        "contrastBand",
        "borderOccupancyRatio",
        "cropBorderBand",
        "backgroundComplexityScore",
        "backgroundComplexityBand",
    }
