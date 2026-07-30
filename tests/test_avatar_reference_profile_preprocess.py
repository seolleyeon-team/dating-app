import sys
import types
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.quality_context import AvatarQualityContext
from avatar_generation.preprocessing.reference import (
    REFERENCE_PREPROCESS_PROFILES,
    ReferencePreprocessConfig,
    preprocess_reference_image,
)

NEUTRAL = (247, 242, 236)


def _analysis(face_box, regions=()):
    return types.SimpleNamespace(
        faces=[types.SimpleNamespace(bbox=face_box, confidence=0.99)],
        regions=tuple(regions),
    )


def _region(kind, bbox):
    return types.SimpleNamespace(kind=kind, bbox=bbox)


def _mean_abs_diff(before, after, box):
    diff = ImageChops.difference(before.crop(box), after.crop(box))
    return sum(ImageStat.Stat(diff).mean) / 3.0


def _portrait(size=(180, 180), face_box=(60, 42, 60, 64)):
    image = Image.new("RGB", size, (52, 88, 126))
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], 4):
        draw.line((x, 0, x, size[1]), fill=(42 + x % 80, 108, 150))
    left, top, width, height = face_box
    right = left + width
    bottom = top + height
    draw.rectangle((left - 12, top - 20, right + 12, top + 18), fill=(45, 28, 24))
    draw.rectangle((left, top, right, bottom), fill=(230, 177, 142))
    for y in range(top, bottom, 3):
        draw.line((left, y, right, y), fill=(190, 118 + y % 60, 105))
    draw.rectangle((left + 8, top + 22, left + 23, top + 28), fill=(8, 8, 8))
    draw.rectangle((right - 23, top + 22, right - 8, top + 28), fill=(8, 8, 8))
    mouth_left = left + max(3, width // 4)
    mouth_right = right - max(3, width // 4)
    if mouth_right >= mouth_left:
        draw.rectangle((mouth_left, bottom - 14, mouth_right, bottom - 6), fill=(73, 43, 35))
    draw.rectangle((54, 120, 126, 164), fill=(74, 88, 110))
    return image


def _normalized_xywh(box, size):
    left, top, width, height = box
    return (left / size[0], top / size[1], width / size[0], height / size[1])



@pytest.mark.parametrize(
    ("label", "face_box"),
    (
        ("close", (40, 24, 104, 116)),
        ("small", (82, 58, 24, 28)),
        ("upper", (60, 42, 60, 64)),
        ("full", (72, 36, 42, 48)),
    ),
)
def test_close_small_upper_and_full_frames_keep_primary_pixels(label, face_box):
    source = _portrait(face_box=face_box)
    result = preprocess_reference_image(
        source,
        source_analysis=_analysis(_normalized_xywh(face_box, source.size)),
        config=ReferencePreprocessConfig(primary_crop_enabled=False),
    )

    left, top, width, height = face_box
    assert result.image.size == source.size
    assert result.metadata["profile"]["name"] == "privacy_strict"
    assert result.metadata["profile"]["primaryFaceScalePx"] == max(width, height)
    assert result.image.getpixel((left + width // 2, top + height // 2)) != NEUTRAL
    assert label in {"close", "small", "upper", "full"}

def test_versioned_reference_profiles_are_declared_with_upper_bound_gate_flags():
    assert set(REFERENCE_PREPROCESS_PROFILES) == {
        "privacy_strict",
        "fidelity_balanced",
        "fidelity_high_bounded",
    }
    assert REFERENCE_PREPROCESS_PROFILES["privacy_strict"].version == "privacy_strict_v1"
    assert REFERENCE_PREPROCESS_PROFILES["privacy_strict"].require_later_upper_bound_gate is False
    assert REFERENCE_PREPROCESS_PROFILES["fidelity_balanced"].require_later_upper_bound_gate is True
    assert REFERENCE_PREPROCESS_PROFILES["fidelity_high_bounded"].require_later_upper_bound_gate is True


def test_profile_metadata_and_retention_strength_are_profile_specific():
    source = _portrait()
    analysis = _analysis(_normalized_xywh((60, 42, 60, 64), source.size))

    strict = preprocess_reference_image(
        source,
        source_analysis=analysis,
        config=ReferencePreprocessConfig(primary_crop_enabled=False, background_neutralization_enabled=False),
    )
    high = preprocess_reference_image(
        source,
        source_analysis=analysis,
        config=ReferencePreprocessConfig(
            primary_crop_enabled=False,
            background_neutralization_enabled=False,
            profile_name="fidelity_high_bounded",
        ),
    )

    persisted = AvatarQualityContext(metadata=high.metadata).persisted_metadata()
    assert persisted["profile"] == high.metadata["profile"]
    assert persisted["profile"]["version"] == "fidelity_high_bounded_v1"
    assert persisted["profile"]["requiresLaterUpperBoundGate"] is True

    face_box = (64, 50, 116, 98)
    assert strict.metadata["profile"]["name"] == "privacy_strict"
    assert high.metadata["profile"]["requiresLaterUpperBoundGate"] is True
    assert _mean_abs_diff(source, strict.image, face_box) > _mean_abs_diff(source, high.image, face_box)


def test_face_scale_aware_abstraction_is_stronger_for_large_primary_faces():
    small = _portrait(face_box=(78, 54, 28, 30))
    large = _portrait(face_box=(42, 24, 96, 104))

    small_result = preprocess_reference_image(
        small,
        source_analysis=_analysis(_normalized_xywh((78, 54, 28, 30), small.size)),
        config=ReferencePreprocessConfig(primary_crop_enabled=False, background_neutralization_enabled=False),
    )
    large_result = preprocess_reference_image(
        large,
        source_analysis=_analysis(_normalized_xywh((42, 24, 96, 104), large.size)),
        config=ReferencePreprocessConfig(primary_crop_enabled=False, background_neutralization_enabled=False),
    )

    assert small_result.metadata["profile"]["primaryFaceScalePx"] == 30
    assert large_result.metadata["profile"]["primaryFaceScalePx"] == 104
    small_texture = sum(ImageStat.Stat(small_result.image.crop((80, 58, 104, 82))).stddev) / 3.0
    large_texture = sum(ImageStat.Stat(large_result.image.crop((48, 34, 132, 118))).stddev) / 3.0
    assert large_texture < small_texture


def test_hair_hat_glasses_and_facial_hair_regions_are_retained_more_than_skin_detail():
    source = _portrait()
    regions = (
        _region("hair", (45, 18, 135, 62)),
        _region("glasses", (68, 62, 112, 72)),
        _region("facial_hair", (76, 88, 104, 104)),
        _region("hood-hat", (36, 12, 144, 54)),
    )
    result = preprocess_reference_image(
        source,
        source_analysis=_analysis(_normalized_xywh((60, 42, 60, 64), source.size), regions),
        config=ReferencePreprocessConfig(primary_crop_enabled=False, background_neutralization_enabled=False),
    )

    skin_diff = _mean_abs_diff(source, result.image, (74, 74, 104, 86))
    retained_diff = _mean_abs_diff(source, result.image, (68, 24, 112, 70))
    assert retained_diff < skin_diff


def test_text_logo_school_region_changes_pixels_and_sets_neutralized_flag():
    source = _portrait()
    draw = ImageDraw.Draw(source)
    draw.rectangle((70, 132, 112, 144), fill=(255, 255, 255))
    draw.text((73, 132), "SNU", fill=(0, 0, 0))

    result = preprocess_reference_image(
        source,
        source_analysis=_analysis(_normalized_xywh((60, 42, 60, 64), source.size)),
        visual_risk_regions=(_region("school-logo-text", (70, 132, 112, 144)),),
        config=ReferencePreprocessConfig(primary_crop_enabled=False),
    )

    assert result.metadata["textLogoDetected"] is True
    assert result.metadata["textLogoNeutralized"] is True
    assert result.metadata["backgroundNeutralization"]["textLogoNeutralizedRegionCount"] == 1
    assert _mean_abs_diff(source, result.image, (70, 132, 112, 144)) > 10


def test_unique_marks_tattoos_change_pixels_without_erasing_primary_face():
    source = _portrait()
    draw = ImageDraw.Draw(source)
    draw.rectangle((88, 72, 94, 78), fill=(0, 0, 0))

    result = preprocess_reference_image(
        source,
        source_analysis=_analysis(_normalized_xywh((60, 42, 60, 64), source.size)),
        visual_risk_regions=(_region("unique-mark-tattoo", (86, 70, 96, 80)),),
        config=ReferencePreprocessConfig(primary_crop_enabled=False),
    )

    assert result.metadata["uniqueDetailsNeutralized"] is True
    assert result.metadata["backgroundNeutralization"]["uniqueDetailNeutralizedRegionCount"] == 1
    assert result.image.getpixel((90, 74)) != NEUTRAL
    assert _mean_abs_diff(source, result.image, (86, 70, 96, 80)) > 1


def test_background_person_mask_cannot_erase_primary_face_pixels():
    source = _portrait()
    result = preprocess_reference_image(
        source,
        source_analysis=_analysis(_normalized_xywh((60, 42, 60, 64), source.size)),
        visual_risk_regions=(_region("background-person", (40, 20, 140, 130)),),
        config=ReferencePreprocessConfig(primary_crop_enabled=False),
    )

    assert result.metadata["secondaryFacesNeutralized"] is True
    assert result.metadata["backgroundNeutralization"]["backgroundPersonRegionCount"] == 1
    assert result.image.getpixel((90, 74)) != NEUTRAL


def test_complex_multiple_secondary_background_regions_are_pixel_neutralized():
    source = _portrait(size=(220, 180), face_box=(76, 38, 58, 64))
    draw = ImageDraw.Draw(source)
    draw.rectangle((170, 40, 194, 68), fill=(226, 170, 140))
    draw.rectangle((8, 8, 42, 34), fill=(255, 255, 255))
    analysis = types.SimpleNamespace(
        faces=[
            types.SimpleNamespace(bbox=_normalized_xywh((76, 38, 58, 64), source.size), confidence=0.99),
            types.SimpleNamespace(bbox=_normalized_xywh((170, 40, 24, 28), source.size), confidence=0.77),
        ]
    )

    result = preprocess_reference_image(
        source,
        source_analysis=analysis,
        visual_risk_regions=(
            _region("background", (0, 0, 54, 44)),
            _region("text", (8, 8, 42, 34)),
        ),
        config=ReferencePreprocessConfig(primary_crop_enabled=False),
    )

    assert result.metadata["backgroundNeutralized"] is True
    assert result.metadata["secondaryFacesNeutralized"] is True
    assert result.metadata["textLogoNeutralized"] is True
    assert result.image.getpixel((182, 52)) == NEUTRAL
    assert result.image.getpixel((18, 18)) == NEUTRAL
    assert result.image.getpixel((104, 70)) != NEUTRAL