from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Mapping


TRAIT_CARD_SCHEMA_VERSION = "seolleyeon_avatar_trait_card_v3"

UNCLEAR = "unclear"

TRAIT_CARD_ALLOWED_ENUMS: dict[str, tuple[str, ...]] = {
    "visible_crop": (
        "face_only",
        "head_and_shoulders",
        "upper_body",
        "full_body_visible",
        UNCLEAR,
    ),
    "hair_length": ("short", "medium", "long", UNCLEAR),
    "hair_volume": ("low", "medium", "high", UNCLEAR),
    "hair_direction": (
        "side_part",
        "center_part",
        "forward_bangs",
        "natural_messy",
        "pulled_back",
        "not_visible",
        UNCLEAR,
    ),
    "hair_color_range": (
        "black",
        "dark_brown",
        "brown",
        "light_brown",
        "dyed_warm",
        "not_visible",
        UNCLEAR,
    ),
    "eyewear_present": ("yes", "no", UNCLEAR),
    "eyewear_style": (
        "none",
        "round_black",
        "thin_metal",
        "rectangular",
        "clear_frame",
        "other_simple",
        "not_visible",
        UNCLEAR,
    ),
    "face_shape_category": ("round", "oval", "long", "soft_square", UNCLEAR),
    "eye_size_category": ("small", "medium", "medium_large", UNCLEAR),
    "eye_tilt_category": (
        "neutral",
        "slightly_upturned",
        "slightly_downturned",
        UNCLEAR,
    ),
    "brow_thickness": ("thin", "natural", "thick", UNCLEAR),
    "nose_prominence": ("soft", "medium", "defined", UNCLEAR),
    "cheek_fullness": ("low", "moderate", "full", UNCLEAR),
    "jaw_impression": ("soft", "moderate_defined", "broad_soft", UNCLEAR),
    "mouth_expression": ("neutral", "subtle_smile", "calm_closed", UNCLEAR),
    "skin_tone_range": (
        "fair_warm",
        "natural_beige",
        "medium_warm",
        "sun_kissed",
        UNCLEAR,
    ),
    "expression_mood": ("calm", "gentle", "neutral", "focused", UNCLEAR),
    "clothing_category": (
        "sweatshirt",
        "shirt",
        "polo",
        "jacket",
        "knit",
        "hoodie",
        "t_shirt",
        "not_visible",
        UNCLEAR,
    ),
    "clothing_color": (
        "blue",
        "white",
        "black",
        "beige",
        "gray",
        "navy",
        "brown",
        "green",
        "not_visible",
        UNCLEAR,
    ),
    "avatar_presentation_gender": (
        "male",
        "female",
        "non_binary",
        "prefer_not_to_say",
        "unknown",
    ),
}


@dataclass(frozen=True)
class AvatarTraitCard:
    """Enum-only, privacy-safe visual trait card for avatar generation."""

    visible_crop: str = UNCLEAR
    hair_length: str = UNCLEAR
    hair_volume: str = UNCLEAR
    hair_direction: str = UNCLEAR
    hair_color_range: str = UNCLEAR
    eyewear_present: str = UNCLEAR
    eyewear_style: str = UNCLEAR
    face_shape_category: str = UNCLEAR
    eye_size_category: str = UNCLEAR
    eye_tilt_category: str = UNCLEAR
    brow_thickness: str = UNCLEAR
    nose_prominence: str = UNCLEAR
    cheek_fullness: str = UNCLEAR
    jaw_impression: str = UNCLEAR
    mouth_expression: str = UNCLEAR
    skin_tone_range: str = UNCLEAR
    expression_mood: str = UNCLEAR
    clothing_category: str = UNCLEAR
    clothing_color: str = UNCLEAR
    avatar_presentation_gender: str = "unknown"

    def to_dict(self, *, include_unclear: bool = True) -> dict[str, str]:
        data = {field.name: getattr(self, field.name) for field in fields(self)}
        if include_unclear:
            return data
        return {key: value for key, value in data.items() if value != UNCLEAR}

    def to_prompt_builder_dict(self) -> dict[str, Any]:
        """Return non-unclear values compatible with the v4 prompt builder."""
        data: dict[str, Any] = self.to_dict(include_unclear=False)
        data = {
            key: value
            for key, value in data.items()
            if value not in {UNCLEAR, "not_visible", "unknown", "prefer_not_to_say"}
        }
        if data.get("eyewear_present") == "yes":
            data["eyewear_present"] = True
        elif data.get("eyewear_present") == "no":
            data["eyewear_present"] = False
        _map_value(data, "hair_direction", {"swept_back": "pulled_back"})
        _map_value(data, "hair_color_range", {"dyed_light": "dyed_warm"})
        _map_value(
            data,
            "eyewear_style",
            {
                "round_dark": "round_black",
                "round_metal": "thin_metal",
                "rectangular_dark": "rectangular",
                "rectangular_metal": "rectangular",
            },
        )
        _map_value(
            data,
            "clothing_category",
            {
                "tshirt": "t_shirt",
                "blouse": "shirt",
                "coat": "jacket",
            },
        )
        _drop_unsupported(
            data,
            "eyewear_style",
            {"none", "round_black", "thin_metal", "rectangular", "clear_frame", "other_simple"},
        )
        _drop_unsupported(
            data,
            "clothing_category",
            {"sweatshirt", "shirt", "polo", "jacket", "knit", "hoodie", "t_shirt"},
        )
        _drop_unsupported(
            data,
            "clothing_color",
            {"blue", "white", "black", "beige", "gray", "navy", "brown", "green"},
        )
        return data


@dataclass(frozen=True)
class TraitCardValidationResult:
    schema_version: str
    trait_card: AvatarTraitCard
    privacy_safe: bool
    confidence: float
    errors: list[str] = field(default_factory=list)
    removed_keys: list[str] = field(default_factory=list)
    invalid_enum_fields: list[str] = field(default_factory=list)
    sanitized_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "privacySafe": bool(self.privacy_safe),
            "confidence": float(self.confidence),
            "traitCard": self.trait_card.to_dict(),
            "errors": list(self.errors),
            "removedKeys": list(self.removed_keys),
            "invalidEnumFields": list(self.invalid_enum_fields),
            "sanitizedFields": list(self.sanitized_fields),
        }


def trait_card_schema_dict() -> dict[str, Any]:
    return {
        "schemaVersion": TRAIT_CARD_SCHEMA_VERSION,
        "type": "object",
        "required": ["schemaVersion", "privacySafe", "confidence", "traitCard"],
        "properties": {
            "schemaVersion": {"const": TRAIT_CARD_SCHEMA_VERSION},
            "privacySafe": {"type": "boolean"},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "traitCard": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    key: {"enum": list(values)}
                    for key, values in TRAIT_CARD_ALLOWED_ENUMS.items()
                },
            },
        },
        "additionalProperties": False,
    }


def avatar_trait_card_from_dict(values: Mapping[str, Any]) -> AvatarTraitCard:
    normalized = {
        key: str(values.get(key, UNCLEAR))
        if values.get(key, UNCLEAR) in TRAIT_CARD_ALLOWED_ENUMS[key]
        else UNCLEAR
        for key in TRAIT_CARD_ALLOWED_ENUMS
    }
    return AvatarTraitCard(**normalized)


def _map_value(data: dict[str, Any], key: str, mapping: Mapping[str, str]) -> None:
    value = data.get(key)
    if isinstance(value, str) and value in mapping:
        data[key] = mapping[value]


def _drop_unsupported(data: dict[str, Any], key: str, allowed: set[str]) -> None:
    value = data.get(key)
    if isinstance(value, str) and value not in allowed:
        data.pop(key, None)
