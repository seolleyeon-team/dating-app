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
    "hair_length": ("very_short", "short", "medium", "long", UNCLEAR),
    "hair_volume": ("low", "medium", "high", UNCLEAR),
    "hair_direction": (
        "side_part",
        "center_part",
        "forward_bangs",
        "swept_back",
        "natural_messy",
        "pulled_back",
        "not_visible",
        UNCLEAR,
    ),
    "hair_bangs": (
        "none",
        "light",
        "full",
        "soft_bangs",
        "side_bangs",
        "full_bangs",
        "curtain_bangs",
        "not_visible",
        UNCLEAR,
    ),
    "hair_color_range": (
        "black",
        "dark_brown",
        "brown",
        "light_brown",
        "dyed_light",
        "dyed_warm",
        "not_visible",
        UNCLEAR,
    ),
    "eyewear_present": ("yes", "no", UNCLEAR),
    "eyewear_style": (
        "none",
        "round_dark",
        "round_metal",
        "rectangular_dark",
        "rectangular_metal",
        "round_black",
        "thin_metal",
        "rectangular",
        "clear_frame",
        "sunglasses",
        "other_simple",
        "not_visible",
        UNCLEAR,
    ),
    "eyewear_confidence": ("low", "medium", "high", UNCLEAR),
    "eyewear_source": ("florence", "clip", "grounding_dino", "merged", UNCLEAR),
    "facial_hair_present": ("yes", "no", UNCLEAR),
    "facial_hair_style": (
        "none",
        "light_mustache",
        "stubble",
        "light_stubble",
        "mustache",
        "short_beard",
        "goatee",
        "not_visible",
        UNCLEAR,
    ),
    "face_shape_category": ("round", "oval", "long", "soft_square", UNCLEAR),
    "facial_feature_balance": ("soft", "balanced", "defined", UNCLEAR),
    "eye_size_category": ("small", "medium", "medium_large", UNCLEAR),
    "eye_tilt_category": (
        "neutral",
        "slightly_upturned",
        "slightly_downturned",
        UNCLEAR,
    ),
    "eye_shape_mood": (
        "neutral",
        "gentle",
        "slightly_upturned",
        "slightly_downturned",
        "soft",
        "calm",
        "focused",
        UNCLEAR,
    ),
    "brow_thickness": ("thin", "natural", "thick", UNCLEAR),
    "brow_shape": ("straight", "soft_arch", "arched", "natural", "not_visible", UNCLEAR),
    "nose_prominence": ("soft", "medium", "defined", UNCLEAR),
    "nose_bridge_impression": ("soft", "moderate", "medium", "defined", UNCLEAR),
    "cheek_fullness": ("low", "moderate", "full", UNCLEAR),
    "jaw_impression": ("soft", "moderate_defined", "broad_soft", UNCLEAR),
    "mouth_expression": ("neutral", "subtle_smile", "calm_closed", UNCLEAR),
    "mouth_fullness_category": ("thin", "subtle", "medium", "full", UNCLEAR),
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
    hair_bangs: str = UNCLEAR
    hair_color_range: str = UNCLEAR
    eyewear_present: str = UNCLEAR
    eyewear_style: str = UNCLEAR
    eyewear_confidence: str = UNCLEAR
    eyewear_source: str = UNCLEAR
    facial_hair_present: str = UNCLEAR
    facial_hair_style: str = UNCLEAR
    face_shape_category: str = UNCLEAR
    facial_feature_balance: str = UNCLEAR
    eye_size_category: str = UNCLEAR
    eye_tilt_category: str = UNCLEAR
    eye_shape_mood: str = UNCLEAR
    brow_thickness: str = UNCLEAR
    brow_shape: str = UNCLEAR
    nose_prominence: str = UNCLEAR
    nose_bridge_impression: str = UNCLEAR
    cheek_fullness: str = UNCLEAR
    jaw_impression: str = UNCLEAR
    mouth_expression: str = UNCLEAR
    mouth_fullness_category: str = UNCLEAR
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

    def to_eyewear_contract(self) -> dict[str, Any]:
        present: bool | None
        if self.eyewear_present == "yes":
            present = True
        elif self.eyewear_present == "no":
            present = False
        else:
            present = None
        general_style = self.eyewear_style
        if present is False:
            general_style = "none"
        elif general_style in {"not_visible", UNCLEAR, ""}:
            general_style = UNCLEAR
        return {
            "present": present,
            "confidence": self.eyewear_confidence,
            "generalStyle": general_style,
            "source": self.eyewear_source,
        }

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
        if data.get("facial_hair_present") == "yes":
            data["facial_hair_present"] = True
        elif data.get("facial_hair_present") == "no":
            data["facial_hair_present"] = False
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
        _map_value(data, "brow_shape", {"softly_arched": "soft_arch"})
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
            {"none", "round_black", "thin_metal", "rectangular", "clear_frame", "sunglasses", "other_simple"},
        )
        _drop_unsupported(
            data,
            "clothing_category",
            {"sweatshirt", "shirt", "polo", "jacket", "knit", "hoodie", "t_shirt"},
        )
        _drop_unsupported(
            data,
            "hair_bangs",
            {"none", "light", "full", "soft_bangs", "side_bangs", "full_bangs", "curtain_bangs"},
        )
        _drop_unsupported(
            data,
            "facial_hair_style",
            {"none", "light_mustache", "mustache", "short_beard", "goatee", "stubble", "light_stubble"},
        )
        _drop_unsupported(
            data,
            "facial_feature_balance",
            {"soft", "balanced", "defined"},
        )
        _drop_unsupported(
            data,
            "eye_shape_mood",
            {"neutral", "gentle", "slightly_upturned", "slightly_downturned", "soft", "calm", "focused"},
        )
        _drop_unsupported(
            data,
            "brow_shape",
            {"straight", "soft_arch", "arched", "natural"},
        )
        _drop_unsupported(
            data,
            "nose_bridge_impression",
            {"soft", "moderate", "medium", "defined"},
        )
        _drop_unsupported(
            data,
            "mouth_fullness_category",
            {"thin", "subtle", "medium", "full"},
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
        trait_card = self.trait_card.to_dict()
        trait_card["eyewear"] = self.trait_card.to_eyewear_contract()
        return {
            "schemaVersion": self.schema_version,
            "privacySafe": bool(self.privacy_safe),
            "confidence": float(self.confidence),
            "traitCard": trait_card,
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
