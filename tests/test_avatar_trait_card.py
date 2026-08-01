import json
import sys
from pathlib import Path


AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.model_adapters.florence2 import Florence2TraitExtractionAdapter
from avatar_generation.seolleyeon_avatar_prompt_builder_v4 import (
    AvatarTraitCard as PromptAvatarTraitCard,
    avatar_trait_card_from_dict as prompt_builder_trait_card_from_dict,
    build_avatar_prompt,
)
from avatar_generation.trait_card import (
    FLORENCE2_TRAIT_EXTRACTION_PROMPT,
    TRAIT_CARD_ALLOWED_ENUMS,
    build_broad_trait_hints,
    merge_trait_card_with_broad_hints,
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
            "hair_bangs": "side_bangs",
            "hair_color_range": "dark_brown",
            "eyewear_present": "no",
            "eyewear_style": "none",
            "facial_hair_present": "no",
            "facial_hair_style": "none",
            "face_shape_category": "oval",
            "facial_feature_balance": "balanced",
            "eye_size_category": "medium",
            "eye_tilt_category": "neutral",
            "eye_shape_mood": "calm",
            "brow_thickness": "natural",
            "brow_shape": "natural",
            "nose_prominence": "medium",
            "nose_bridge_impression": "medium",
            "cheek_fullness": "moderate",
            "jaw_impression": "soft",
            "mouth_expression": "calm_closed",
            "mouth_fullness_category": "medium",
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


def test_trait_validator_accepts_expanded_privacy_safe_fields():
    result = validate_trait_card_response(json.dumps(_payload()))
    card = result.trait_card.to_dict()
    prompt_builder_card = result.trait_card.to_prompt_builder_dict()

    assert result.privacy_safe is True
    assert card["hair_bangs"] == "side_bangs"
    assert card["facial_hair_present"] == "no"
    assert card["facial_hair_style"] == "none"
    assert card["facial_feature_balance"] == "balanced"
    assert card["eye_shape_mood"] == "calm"
    assert card["brow_shape"] == "natural"
    assert card["nose_bridge_impression"] == "medium"
    assert card["mouth_fullness_category"] == "medium"
    assert prompt_builder_card["facial_hair_present"] is False
    assert prompt_builder_card["eyewear_present"] is False
    assert prompt_builder_card["eyewear_style"] == "none"


def test_trait_validator_accepts_nested_eyewear_contract():
    payload = _payload()
    payload["traitCard"] = {
        "eyewear": {
            "present": False,
            "confidence": "high",
            "generalStyle": "none",
            "source": "merged",
        }
    }

    result = validate_trait_card_response(json.dumps(payload))
    card = result.trait_card.to_dict()
    serialized = result.to_dict()

    assert result.privacy_safe is True
    assert card["eyewear_present"] == "no"
    assert card["eyewear_confidence"] == "high"
    assert card["eyewear_source"] == "merged"
    assert serialized["traitCard"]["eyewear"]["present"] is False


def test_trait_validator_overwrites_model_gender_with_onboarding_gender():
    payload = _payload({"avatar_presentation_gender": "male"})

    result = validate_trait_card_response(
        json.dumps(payload),
        avatar_presentation_gender="female",
    )

    assert result.privacy_safe is True
    assert result.trait_card.to_dict()["avatar_presentation_gender"] == "female"


def test_trait_validator_accepts_korean_onboarding_gender_aliases():
    male = validate_trait_card_response(
        json.dumps(_payload({"avatar_presentation_gender": "female"})),
        avatar_presentation_gender="남성",
    )
    female = validate_trait_card_response(
        json.dumps(_payload({"avatar_presentation_gender": "male"})),
        avatar_presentation_gender="여자",
    )

    assert male.trait_card.to_dict()["avatar_presentation_gender"] == "male"
    assert female.trait_card.to_dict()["avatar_presentation_gender"] == "female"


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


def test_trait_validator_rejects_raw_numeric_landmarks():
    payload = _payload()
    payload["traitCard"]["face_landmarks"] = {
        "left_eye": [0.122, 0.334],
        "nose_tip": [0.51, 0.49],
    }

    result = validate_trait_card_response(json.dumps(payload))
    dumped = json.dumps(result.to_dict(), sort_keys=True)

    assert result.privacy_safe is False
    assert result.confidence == 0.0
    assert result.errors == ["raw_numeric_landmarks"]
    assert result.removed_keys == ["traitCard.face_landmarks"]
    assert "0.122" not in dumped
    assert "nose_tip" not in dumped


def test_mediapipe_binning_outputs_enum_hints_without_raw_coordinates():
    landmarks = [type("Point", (), {"x": 0.45, "y": 0.5})() for _ in range(478)]
    landmarks[33] = type("Point", (), {"x": 0.30, "y": 0.38})()
    landmarks[133] = type("Point", (), {"x": 0.38, "y": 0.38})()
    landmarks[362] = type("Point", (), {"x": 0.62, "y": 0.38})()
    landmarks[263] = type("Point", (), {"x": 0.70, "y": 0.38})()
    landmarks[234] = type("Point", (), {"x": 0.18, "y": 0.50})()
    landmarks[454] = type("Point", (), {"x": 0.82, "y": 0.50})()
    landmarks[61] = type("Point", (), {"x": 0.40, "y": 0.65})()
    landmarks[291] = type("Point", (), {"x": 0.60, "y": 0.65})()
    landmarks[13] = type("Point", (), {"x": 0.50, "y": 0.63})()
    landmarks[14] = type("Point", (), {"x": 0.50, "y": 0.67})()

    hints = build_broad_trait_hints(
        face_bbox=(0.2, 0.2, 0.5, 0.55),
        landmarks=landmarks,
        blendshapes={"mouthSmileLeft": 0.8, "mouthSmileRight": 0.7},
    )
    rendered = json.dumps(hints, sort_keys=True)

    assert hints["mouth_expression"] == "subtle_smile"
    assert hints["face_shape_category"] in {"oval", "round", "long"}
    assert "0.30" not in rendered
    assert "landmark" not in rendered.lower()


def test_mediapipe_binning_merges_only_unclear_fields():
    result = validate_trait_card_response(
        json.dumps(_payload({"mouth_expression": "unclear", "facial_hair_style": "mustache"}))
    )

    merged = merge_trait_card_with_broad_hints(
        result,
        {"mouth_expression": "subtle_smile", "facial_hair_style": "goatee"},
    )
    card = merged.trait_card.to_dict()

    assert card["mouth_expression"] == "subtle_smile"
    assert card["facial_hair_style"] == "mustache"


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
    assert "numeric landmarks" in lowered
    assert "sensitive" in lowered
    assert "beauty" in lowered
    assert "unique marks" in lowered
    assert "privacy-processed reference" in lowered
    assert "ignore background objects" in lowered
    assert "text, logos, brands, and locations" in lowered
    assert "privacysafe" in lowered
    assert "confidence" in lowered
    assert "unclear" in TRAIT_CARD_ALLOWED_ENUMS["hair_length"]
    assert "hair_bangs" in lowered
    assert "facial_hair_present" in lowered
    assert "mouth_fullness_category" in lowered


def test_prompt_builder_includes_expanded_fields_as_broad_guidance():
    result = validate_trait_card_response(json.dumps(_payload()))
    prompt_trait_card = prompt_builder_trait_card_from_dict(
        result.trait_card.to_prompt_builder_dict()
    )

    prompt = build_avatar_prompt(
        trait_card=prompt_trait_card,
        reference_mode="trait_card_only",
        candidate_count=1,
    )
    positive = prompt.positive.lower()

    assert "hair_bangs" in positive
    assert "facial_hair_present" in positive
    assert "facial_feature_balance" in positive
    assert "nose_bridge_impression" in positive
    assert "mouth_fullness_category" in positive
    assert "broad impression categories" in positive
    assert "without copying exact geometry" in positive
    assert "bare visible eyes" in positive
    assert "no eye accessory detail" in positive
    assert "do not add any accessory around the eyes" in positive
    assert "do not add glasses or eyewear" not in positive
    assert "eyeglasses" not in positive
    assert "lens reflections" not in positive
    assert '"eyewear_present"' not in positive
    assert positive.startswith("critical eye-area constraint: draw clear bare eyes")


def test_prompt_builder_hard_instructs_confirmed_eyewear_present():
    prompt = build_avatar_prompt(
        trait_card=PromptAvatarTraitCard(
            eyewear_present=True,
            eyewear_style="rectangular",
            eyewear_confidence="high",
        ),
        reference_mode="trait_card_only",
        candidate_count=1,
    )

    positive = prompt.positive.lower()
    assert "eyewear: present" in positive
    assert "must wear eyewear" in positive
    assert "do not omit glasses" in positive
    assert "eyeglass rims" not in positive
    assert positive.startswith("critical eyewear constraint: the source shows eyewear")


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


def test_florence2_adapter_maps_visible_no_glasses_to_false():
    adapter = Florence2TraitExtractionAdapter(dry_run=True)

    result = validate_trait_card_response(
        adapter._caption_to_trait_response(  # pylint: disable=protected-access
            "A head and shoulders portrait of a person with visible eyes, "
            "black hair, no glasses, and a gray hoodie."
        )
    )

    card = result.trait_card.to_dict()
    assert result.privacy_safe is True
    assert card["eyewear_present"] == "no"
    assert card["eyewear_style"] == "none"
    assert card["eyewear_confidence"] == "high"


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
