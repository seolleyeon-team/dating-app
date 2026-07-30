from __future__ import annotations

from .prompt import FLORENCE2_TRAIT_EXTRACTION_PROMPT
from .schema import (
    CRITICAL_BROAD_TRAIT_FIELDS,
    CRITICAL_BROAD_TRAIT_MIN_COVERAGE,
    TRAIT_CARD_ALLOWED_ENUMS,
    TRAIT_CARD_SCHEMA_VERSION,
    UNCLEAR,
    AvatarTraitCard,
    TraitCardValidationResult,
    avatar_trait_card_from_dict,
    critical_broad_trait_coverage,
    trait_card_schema_dict,
)
from .mediapipe_binning import build_broad_trait_hints, merge_trait_card_with_broad_hints
from .region_features import RegionColorHint, RegionColorTraits, extract_region_color_traits
from .validator import normalize_avatar_presentation_gender, validate_trait_card_response

__all__ = [
    "FLORENCE2_TRAIT_EXTRACTION_PROMPT",
    "CRITICAL_BROAD_TRAIT_FIELDS",
    "CRITICAL_BROAD_TRAIT_MIN_COVERAGE",
    "TRAIT_CARD_ALLOWED_ENUMS",
    "TRAIT_CARD_SCHEMA_VERSION",
    "UNCLEAR",
    "AvatarTraitCard",
    "TraitCardValidationResult",
    "avatar_trait_card_from_dict",
    "critical_broad_trait_coverage",
    "build_broad_trait_hints",
    "merge_trait_card_with_broad_hints",
    "RegionColorHint",
    "RegionColorTraits",
    "extract_region_color_traits",
    "trait_card_schema_dict",
    "normalize_avatar_presentation_gender",
    "validate_trait_card_response",
]
