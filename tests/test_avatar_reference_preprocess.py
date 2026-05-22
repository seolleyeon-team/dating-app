import sys
import types
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.segmentation import FaceRegion
from avatar_generation.model_adapters.sam import SamSegmentationAdapter
from avatar_generation.preprocessing import (
    ReferencePreprocessConfig,
    preprocess_reference_image,
    validate_reference_preprocess_enabled_for_environment,
)


def _source_image() -> Image.Image:
    image = Image.new("RGB", (128, 128), (188, 191, 196))
    draw = ImageDraw.Draw(image)

    for x in range(0, 128, 2):
        color = (65, 120, 170) if x % 4 == 0 else (205, 220, 230)
        draw.line((x, 0, x, 127), fill=color)

    for y in range(0, 128, 2):
        color = (230, 177, 142) if y % 4 == 0 else (65, 40, 35)
        draw.line((32, y, 95, y), fill=color)
    draw.rectangle((32, 32, 95, 95), outline=(5, 5, 5), width=1)
    return image


def _source_analysis():
    face = types.SimpleNamespace(bbox=(0.25, 0.25, 0.5, 0.5), confidence=0.98)
    return types.SimpleNamespace(faces=[face])


def _mean_abs_diff(before: Image.Image, after: Image.Image, box: tuple[int, int, int, int]) -> float:
    diff = ImageChops.difference(before.crop(box), after.crop(box))
    return sum(ImageStat.Stat(diff).mean) / 3.0


def test_region_preprocess_modifies_face_more_than_style_and_preserves_source():
    source = _source_image()
    original_bytes = source.tobytes()

    result = preprocess_reference_image(
        source,
        source_analysis=_source_analysis(),
        config=ReferencePreprocessConfig(face_downsample_px=32, style_downsample_px=96),
    )

    assert result.image.size == source.size
    assert source.tobytes() == original_bytes

    face_diff = _mean_abs_diff(source, result.image, (36, 36, 92, 92))
    style_diff = _mean_abs_diff(source, result.image, (0, 0, 24, 128))
    assert face_diff > style_diff * 1.35

    metadata = result.metadata
    assert metadata["schemaVersion"] == "avatar_reference_preprocess_metadata_v1"
    assert metadata["sourceSize"] == {"width": 128, "height": 128}
    assert metadata["outputSize"] == {"width": 128, "height": 128}
    assert metadata["regions"]["face"]["downsamplePx"] == 32
    assert metadata["regions"]["style"]["downsamplePx"] == 96
    assert metadata["segmentation"]["provider"] == "source_analysis"


def test_production_rejects_disabled_reference_preprocess(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AVATAR_REFERENCE_PRIVACY_PREPROCESS", "false")

    with pytest.raises(ValueError, match="production"):
        validate_reference_preprocess_enabled_for_environment()


def test_sam_disabled_uses_source_analysis_fallback():
    source = _source_image()

    result = preprocess_reference_image(
        source,
        source_analysis=_source_analysis(),
        sam_enabled=False,
    )

    assert result.image.size == source.size
    assert result.metadata["segmentation"]["provider"] == "source_analysis"
    assert result.metadata["sam"] == {"enabled": False, "provider": None}


def test_sam_mock_path_loads_lazily():
    source = _source_image()
    adapter = SamSegmentationAdapter(model_path="mock://unit-test")

    assert adapter.loaded is False

    result = adapter.segment(
        source,
        face_hints=[FaceRegion(bbox=(32, 32, 96, 96), confidence=0.98)],
    )

    assert adapter.loaded is True
    assert result.provider == "sam_mock"
    assert result.face_mask.getbbox() == (32, 32, 96, 96)
    assert result.metadata["modelPath"] == "mock://unit-test"
