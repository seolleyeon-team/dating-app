import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.trait_card import extract_region_color_traits
from avatar_generation.trait_card.region_features import derive_conservative_region_color_regions


def test_hair_brown_ordering_uses_region_lighting_statistics():
    image = Image.new("RGB", (90, 30), (247, 242, 236))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 29, 29), fill=(42, 24, 14))
    draw.rectangle((30, 0, 59, 29), fill=(105, 63, 32))
    draw.rectangle((60, 0, 89, 29), fill=(178, 119, 55))

    dark = extract_region_color_traits(image, regions={"hair": (0, 0, 30, 30)})
    medium = extract_region_color_traits(image, regions={"hair": (30, 0, 60, 30)})
    light = extract_region_color_traits(image, regions={"hair": (60, 0, 90, 30)})

    assert dark.hair_color_range.value == "dark_brown"
    assert medium.hair_color_range.value == "brown"
    assert light.hair_color_range.value == "light_brown"
    assert light.hair_color_range.confidence in {"medium", "high"}


def test_clothing_color_comes_from_clothing_region_only():
    image = Image.new("RGB", (120, 120), (247, 242, 236))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 120, 70), fill=(24, 150, 70))
    draw.rectangle((30, 72, 90, 116), fill=(30, 90, 210))

    traits = extract_region_color_traits(
        image,
        regions=[
            {"kind": "background", "bbox": (0, 0, 120, 70)},
            {"kind": "clothing", "bbox": (30, 72, 90, 116)},
        ],
    )

    assert traits.clothing_color.value == "blue"


def test_region_color_excludes_neutral_background_inside_xyxy_boxes():
    image = Image.new("RGB", (100, 100), (247, 242, 236))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 10, 44, 34), fill=(105, 63, 32))
    draw.rectangle((30, 58, 70, 84), fill=(30, 90, 210))

    traits = extract_region_color_traits(
        image,
        regions=[
            {"kind": "hair", "bbox": (10, 0, 60, 48)},
            {"kind": "clothing", "bbox": (18, 48, 82, 96)},
        ],
    )

    assert traits.hair_color_range.value == "brown"
    assert traits.clothing_color.value == "blue"


def test_wall_background_region_cannot_become_clothing_color():
    image = Image.new("RGB", (80, 80), (247, 242, 236))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 80, 80), fill=(30, 120, 55))

    traits = extract_region_color_traits(
        image,
        regions=[{"kind": "background", "bbox": (0, 0, 80, 80)}],
    )

    assert traits.clothing_color.value == "unclear"
    assert traits.clothing_color.unclear_reason == "clothing_region_missing_or_neutral"


def test_foreground_mask_prevents_wall_contamination_inside_region():
    image = Image.new("RGB", (90, 90), (30, 120, 55))
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(image)
    mask_draw = ImageDraw.Draw(mask)
    draw.rectangle((30, 48, 60, 78), fill=(30, 90, 210))
    mask_draw.rectangle((30, 48, 60, 78), fill=255)

    traits = extract_region_color_traits(
        image,
        regions={"clothing": (8, 30, 82, 88)},
        foreground_mask=mask,
    )

    assert traits.clothing_color.value == "blue"


def test_conservative_regions_derive_from_nonzero_origin_normalized_face():
    image = Image.new("RGB", (160, 200), (247, 242, 236))
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(image)
    mask_draw = ImageDraw.Draw(mask)
    draw.rectangle((50, 28, 102, 49), fill=(105, 63, 32))
    draw.rectangle((36, 105, 116, 160), fill=(30, 90, 210))
    mask_draw.rectangle((50, 28, 102, 49), fill=255)
    mask_draw.rectangle((36, 105, 116, 160), fill=255)

    traits = extract_region_color_traits(
        image,
        primary_face_hint={"bbox": (0.35, 0.25, 0.25, 0.25), "confidence": 0.92},
        foreground_mask=mask,
    )

    assert traits.hair_color_range.value == "brown"
    assert traits.clothing_color.value == "blue"


def test_cropped_derived_hair_region_becomes_unclear():
    image = Image.new("RGB", (120, 100), (105, 63, 32))

    traits = extract_region_color_traits(
        image,
        primary_face_hint=(45, 0, 75, 32),
    )

    assert traits.hair_color_range.value == "unclear"
    assert traits.hair_color_range.unclear_reason == "hair_region_cut_off"



def test_derived_low_foreground_coverage_becomes_unclear():
    image = Image.new("RGB", (120, 140), (30, 120, 55))
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rectangle((58, 58, 61, 61), fill=255)

    traits = extract_region_color_traits(
        image,
        primary_face_hint={"bbox_xyxy": (45, 40, 75, 80), "confidence": 0.9},
        foreground_mask=mask,
    )

    assert traits.hair_color_range.value == "unclear"
    assert traits.hair_color_range.unclear_reason == "hair_region_outside_foreground"

def test_derived_region_repr_does_not_expose_exact_geometry():
    regions = derive_conservative_region_color_regions(
        {"bbox_xyxy": (45, 40, 75, 80), "confidence": 0.9},
        (120, 140),
    )

    assert regions[0].bbox != (0, 0, 0, 0)
    assert "bbox" not in repr(regions[0])
    assert "45" not in repr(regions[0])



