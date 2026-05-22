import json
import sys
from pathlib import Path


AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.model_adapters.florence2 import Florence2TraitExtractionAdapter
from avatar_generation.trait_card import (
    FLORENCE2_TRAIT_EXTRACTION_PROMPT,
    TRAIT_CARD_ALLOWED_ENUMS,
    validate_trait_card_response,
)


def _payload(trait_card=None, **extra):
    body = {
        "schemaVersion": "seolleyeon_avatar_trait_card_v3",
        "privacySafe": True,
        "confidence": 0.82,
        "traitCard": trait_card
        or {
            "visible_crop": "head_and_shoulders",
            "hair_length": "medium",
            "hair_volume": "medium",
            "hair_direction": "side_part",
            "hair_color_range": "dark_brown",
            "eyewear_present": "no",
            "eyewear_style": "none",
            "face_shape_category": "oval",
            "eye_size_category": "medium",
            "eye_tilt_category": "neutral",
            "brow_thickness": "natural",
            "nose_prominence": "medium",
            "cheek_fullness": "moderate",
            "jaw_impression": "soft",
            "mouth_expression": "calm_closed",
            "skin_tone_range": "natural_beige",
            "expression_mood": "calm",
            "clothing_category": "knit",
            "clothing_color": "gray",
        },
    }
    body.update(extra)
    return body


def test_trait_validator_accepts_valid_enum_only_card():
    result = validate_trait_card_response(json.dumps(_payload()))

    assert result.privacy_safe is True
    assert result.confidence == 0.82
    assert result.errors == []
    assert result.trait_card.to_dict()["hair_length"] == "medium"
    assert result.to_dict()["privacySafe"] is True


def test_trait_validator_overwrites_model_gender_with_onboarding_gender():
    payload = _payload({"avatar_presentation_gender": "male"})

    result = validate_trait_card_response(
        json.dumps(payload),
        avatar_presentation_gender="female",
    )

    assert result.privacy_safe is True
    assert result.trait_card.to_dict()["avatar_presentation_gender"] == "female"


def test_trait_validator_invalid_onboarding_gender_becomes_unknown():
    result = validate_trait_card_response(
        json.dumps(_payload({"avatar_presentation_gender": "female"})),
        avatar_presentation_gender="not-a-valid-gender",
    )

    assert result.trait_card.to_dict()["avatar_presentation_gender"] == "unknown"


def test_trait_validator_invalid_enum_becomes_unclear():
    payload = _payload({"hair_length": "extra_long", "clothing_color": "gray"})

    result = validate_trait_card_response(json.dumps(payload))

    assert result.privacy_safe is True
    assert result.trait_card.to_dict()["hair_length"] == "unclear"
    assert result.trait_card.to_dict()["clothing_color"] == "gray"
    assert result.invalid_enum_fields == ["hair_length"]


def test_trait_validator_removes_unknown_keys():
    payload = _payload()
    payload["debug"] = "must be removed"
    payload["traitCard"]["broad_cues"] = "soft smile and exact jaw"

    result = validate_trait_card_response(json.dumps(payload))
    data = result.to_dict()

    assert "debug" not in data
    assert "broad_cues" not in data["traitCard"]
    assert result.removed_keys == ["debug", "traitCard.broad_cues"]


def test_trait_validator_sanitizes_forbidden_details():
    payload = _payload(
        {
            "face_shape_category": "oval with exact jaw contour",
            "jaw_impression": "sharp jaw",
            "mouth_expression": "beautiful smile",
            "skin_tone_range": "natural_beige",
        }
    )

    result = validate_trait_card_response(json.dumps(payload))
    dumped = json.dumps(result.to_dict(), sort_keys=True)

    assert result.trait_card.to_dict()["face_shape_category"] == "unclear"
    assert result.trait_card.to_dict()["jaw_impression"] == "unclear"
    assert result.trait_card.to_dict()["mouth_expression"] == "unclear"
    assert "exact jaw" not in dumped
    assert "sharp jaw" not in dumped
    assert "beautiful" not in dumped


def test_trait_validator_removes_unique_marks_and_sensitive_attrs():
    payload = _payload()
    payload["traitCard"].update(
        {
            "mole": "small mole under the left eye",
            "scar": "thin scar near eyebrow",
            "ethnicity": "Korean",
            "religion": "unknown",
            "face_shape_category": "round",
        }
    )

    result = validate_trait_card_response(json.dumps(payload))
    data = result.to_dict()
    dumped = json.dumps(data, sort_keys=True).lower()

    assert data["traitCard"]["face_shape_category"] == "round"
    assert "mole" not in data["traitCard"]
    assert "scar" not in data["traitCard"]
    assert "ethnicity" not in data["traitCard"]
    assert "religion" not in data["traitCard"]
    assert "under the left eye" not in dumped


def test_trait_validator_handles_malformed_json():
    result = validate_trait_card_response('{"traitCard": {"hair_length": "short"')

    assert result.privacy_safe is False
    assert result.confidence == 0.0
    assert result.trait_card.to_dict()["hair_length"] == "unclear"
    assert result.errors == ["malformed_json"]


def test_trait_validator_rejects_prose_wrapped_json():
    result = validate_trait_card_response(
        'Here is the JSON: {"traitCard": {"hair_length": "short"}}'
    )

    assert result.privacy_safe is False
    assert result.confidence == 0.0
    assert result.trait_card.to_dict()["hair_length"] == "unclear"
    assert result.errors == ["prose_or_non_json_response"]


def test_trait_extraction_prompt_contains_privacy_constraints():
    prompt = FLORENCE2_TRAIT_EXTRACTION_PROMPT
    lowered = prompt.lower()

    assert "privacy-safe" in lowered
    assert "json object only" in lowered
    assert "no prose" in lowered
    assert "enum" in lowered
    assert "remove unknown keys" in lowered
    assert "invalid enum" in lowered
    assert "biometric" in lowered
    assert "sensitive" in lowered
    assert "beauty" in lowered
    assert "unique marks" in lowered
    assert "privacysafe" in lowered
    assert "confidence" in lowered
    assert "unclear" in TRAIT_CARD_ALLOWED_ENUMS["hair_length"]


def test_florence2_adapter_dry_run_validates_mock_response():
    adapter = Florence2TraitExtractionAdapter(
        dry_run=True,
        dry_run_response=json.dumps(_payload({"hair_length": "long"})),
    )

    result = adapter.extract_traits(image=None)

    assert adapter.model_id == "microsoft/Florence-2-large-ft"
    assert result.privacy_safe is True
    assert result.trait_card.to_dict()["hair_length"] == "long"


def test_florence2_adapter_defaults_to_eager_attention():
    adapter = Florence2TraitExtractionAdapter(dry_run=True)

    assert adapter.attn_implementation == "eager"
    assert adapter.task_prompt == "<MORE_DETAILED_CAPTION>"


def test_florence2_adapter_wraps_task_prompt_token():
    adapter = Florence2TraitExtractionAdapter(
        dry_run=True,
        task_prompt="CAPTION",
    )

    assert adapter.task_prompt == "<CAPTION>"


def test_florence2_adapter_maps_caption_to_enum_trait_card():
    adapter = Florence2TraitExtractionAdapter(dry_run=True)

    result = validate_trait_card_response(
        adapter._caption_to_trait_response(  # pylint: disable=protected-access
            "A head and shoulders portrait of a person with black hair, glasses, "
            "a gray hoodie, and a subtle smile."
        )
    )

    card = result.trait_card.to_dict()
    assert result.privacy_safe is True
    assert card["visible_crop"] == "head_and_shoulders"
    assert card["hair_color_range"] == "black"
    assert card["eyewear_present"] == "yes"
    assert card["clothing_category"] == "hoodie"
    assert card["clothing_color"] == "gray"
    assert card["mouth_expression"] == "subtle_smile"


class _FakeTensor:
    def __init__(self, name):
        self.name = name
        self.to_calls = []

    def to(self, *args, **kwargs):
        self.to_calls.append((args, kwargs))
        return self


class _FakeProcessor:
    def __init__(self):
        self.post_process_calls = []

    def __call__(self, *, text, images, return_tensors):
        assert text == "<MORE_DETAILED_CAPTION>"
        assert images is not None
        assert return_tensors == "pt"
        return {
            "input_ids": _FakeTensor("input_ids"),
            "pixel_values": _FakeTensor("pixel_values"),
            "attention_mask": _FakeTensor("attention_mask"),
        }

    def batch_decode(self, generated_ids, *, skip_special_tokens):
        assert generated_ids == ["generated"]
        assert skip_special_tokens is False
        return ["<MORE_DETAILED_CAPTION>A head and shoulders portrait with black hair.</s>"]

    def post_process_generation(self, text, *, task, image_size):
        self.post_process_calls.append((text, task, image_size))
        return {task: "A head and shoulders portrait with black hair."}


class _FakeModel:
    dtype = "float16"

    def __init__(self):
        self.generate_kwargs = None

    def generate(self, **kwargs):
        self.generate_kwargs = kwargs
        return ["generated"]


class _FakeImage:
    width = 320
    height = 240


def test_florence2_adapter_uses_official_generate_kwargs_only():
    processor = _FakeProcessor()
    model = _FakeModel()
    adapter = Florence2TraitExtractionAdapter(processor=processor, model=model)

    caption = adapter._generate_response(_FakeImage())  # pylint: disable=protected-access

    assert caption == "A head and shoulders portrait with black hair."
    assert set(model.generate_kwargs) == {
        "input_ids",
        "pixel_values",
        "max_new_tokens",
        "num_beams",
        "do_sample",
        "use_cache",
    }
    assert "attention_mask" not in model.generate_kwargs
    assert model.generate_kwargs["use_cache"] is False
    assert processor.post_process_calls[0][1] == "<MORE_DETAILED_CAPTION>"
    assert processor.post_process_calls[0][2] == (320, 240)
