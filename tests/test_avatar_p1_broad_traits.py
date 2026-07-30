import json
import sys
from pathlib import Path

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.model_adapters.florence2 import Florence2TraitExtractionAdapter
from avatar_generation.trait_card import (
    CRITICAL_BROAD_TRAIT_FIELDS,
    TRAIT_CARD_SCHEMA_VERSION,
    critical_broad_trait_coverage,
    validate_trait_card_response,
)


def test_p1_broad_caption_traits_meet_coverage_without_private_fields():
    adapter = Florence2TraitExtractionAdapter(dry_run=True)

    result = validate_trait_card_response(
        adapter._caption_to_trait_response(  # pylint: disable=protected-access
            "A centered head and shoulders portrait with medium dark brown side-parted hair, "
            "side bangs, medium volume hair, no glasses, clean-shaven face, oval face, "
            "balanced facial features, medium eyes, neutral eyes, calm gaze, natural thick "
            "eyebrows with a soft arch, medium nose, medium nose bridge, moderate cheeks, "
            "soft jaw, calm closed mouth, medium lips, natural beige skin, calm expression, "
            "and a gray hoodie."
        )
    )

    data = result.to_dict()
    card = data["traitCard"]
    rendered = json.dumps(data, sort_keys=True).lower()

    assert result.privacy_safe is True
    assert data["traitExtractionAvailability"] == "available"
    assert data["criticalTraitCoverage"]["meetsMinimum"] is True
    assert data["criticalTraitCoverage"]["completeCount"] >= 20
    assert card["face_shape_category"] == "oval"
    assert card["facial_feature_balance"] == "balanced"
    assert card["eye_size_category"] == "medium"
    assert card["eye_tilt_category"] == "neutral"
    assert card["eye_shape_mood"] == "calm"
    assert card["brow_thickness"] == "thick"
    assert card["brow_shape"] == "soft_arch"
    assert card["nose_prominence"] == "medium"
    assert card["nose_bridge_impression"] == "medium"
    assert card["cheek_fullness"] == "moderate"
    assert card["jaw_impression"] == "soft"
    assert card["mouth_expression"] == "calm_closed"
    assert card["mouth_fullness_category"] == "medium"
    assert card["skin_tone_range"] == "natural_beige"
    assert card["avatar_presentation_gender"] == "unknown"
    assert "embedding" not in rendered
    assert "landmark" not in rendered
    assert "beautiful" not in rendered


def test_p1_critical_coverage_review_when_insufficient():
    result = validate_trait_card_response(
        {
            "schemaVersion": TRAIT_CARD_SCHEMA_VERSION,
            "privacySafe": True,
            "confidence": 0.4,
            "traitCard": {"visible_crop": "head_and_shoulders", "hair_length": "short"},
        }
    )
    data = result.to_dict()

    assert result.privacy_safe is True
    assert data["traitExtractionAvailability"] == "review"
    assert data["traitExtractionAvailabilityReason"] == "insufficient_critical_broad_trait_coverage"
    assert data["criticalTraitCoverage"]["completeCount"] == 2
    assert data["criticalTraitCoverage"]["totalCount"] == len(CRITICAL_BROAD_TRAIT_FIELDS)
    assert "face_shape_category" in data["criticalTraitCoverage"]["missingCriticalFields"]


def test_p1_coverage_helper_has_no_raw_geometry_or_hash_material():
    result = validate_trait_card_response(
        {
            "schemaVersion": TRAIT_CARD_SCHEMA_VERSION,
            "privacySafe": True,
            "confidence": 0.7,
            "traitCard": {
                "visible_crop": "head_and_shoulders",
                "hair_length": "medium",
                "face_shape_category": "round",
                "embedding_hash": "abc123",
                "face_bbox": [0.1, 0.2, 0.3, 0.4],
            },
        }
    )
    coverage = critical_broad_trait_coverage(result.trait_card)
    rendered = json.dumps(result.to_dict(), sort_keys=True).lower()

    assert result.privacy_safe is False
    assert result.to_dict()["traitExtractionAvailability"] == "unavailable"
    assert coverage["completeCount"] == 3
    assert "abc123" not in rendered
    assert "traitCard.embedding_hash" in result.removed_keys
    assert "traitCard.face_bbox" in result.removed_keys


def test_p1_caption_does_not_invent_absent_eyewear_or_facial_hair_loss():
    adapter = Florence2TraitExtractionAdapter(dry_run=True)

    result = validate_trait_card_response(
        adapter._caption_to_trait_response(  # pylint: disable=protected-access
            "A head and shoulders portrait with visible eyes, short black hair, and a navy shirt."
        )
    )
    card = result.trait_card.to_dict()

    assert card["eyewear_present"] == "unclear"
    assert card["eyewear_style"] == "unclear"
    assert card["facial_hair_present"] == "unclear"
    assert card["facial_hair_style"] == "unclear"