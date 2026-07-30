import json
import os
import sys
from pathlib import Path

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.seolleyeon_avatar_prompt_builder_v4 import (
    AvatarTraitCard,
    build_avatar_prompt,
)

TOKEN_BUDGET = 512
FORBIDDEN_IDENTITY_PHRASES = (
    "different person",
    "generic person",
    "unrelated identity",
    "avoid resemblance",
    "do not look like the source",
)
CORE_CLAUSES = (
    "Preserve broad resemblance",
    "Suppress exact biometric identity",
    "ordinary adult university student",
    "adult proportions",
    "not beautified",
    "Privacy-preserving adult 3D avatar",
)
TRAIT_PAYLOAD_CLAUSES = (
    '"hair_bangs":"curtain_bangs"',
    '"facial_hair_present":false',
    '"facial_feature_balance":"balanced"',
    '"nose_bridge_impression":"moderate"',
    '"mouth_fullness_category":"medium"',
    '"clothing_color":"navy"',
)


def _dense_trait_card() -> AvatarTraitCard:
    return AvatarTraitCard(
        visible_crop="upper_body",
        hair_length="long",
        hair_volume="high",
        hair_direction="center_part",
        hair_bangs="curtain_bangs",
        hair_color_range="dark_brown",
        eyewear_present=False,
        eyewear_style="none",
        eyewear_confidence="high",
        eyewear_source="merged",
        facial_hair_present=False,
        facial_hair_style="none",
        face_shape_category="oval",
        facial_feature_balance="balanced",
        eye_size_category="medium",
        eye_tilt_category="neutral",
        eye_shape_mood="gentle",
        brow_thickness="natural",
        brow_shape="soft_arch",
        nose_prominence="medium",
        nose_bridge_impression="moderate",
        cheek_fullness="moderate",
        jaw_impression="soft",
        mouth_expression="subtle_smile",
        mouth_fullness_category="medium",
        skin_tone_range="natural_beige",
        expression_mood="calm",
        clothing_category="jacket",
        clothing_color="navy",
        avatar_presentation_gender="female",
    )


def _final_flux_prompt() -> str:
    prompt = build_avatar_prompt(
        trait_card=_dense_trait_card(),
        reference_mode="reference_plus_trait",
        candidate_count=1,
    )
    assert prompt.provider_negative is None
    assert "\nAvoid:\n" in prompt.positive
    return prompt.positive


def _load_deployed_flux_tokenizer():
    from transformers import AutoTokenizer

    explicit_path = os.environ.get("AVATAR_FLUX_TOKENIZER_PATH")
    if explicit_path:
        tokenizer_path = Path(explicit_path)
        assert tokenizer_path.exists(), f"AVATAR_FLUX_TOKENIZER_PATH does not exist: {tokenizer_path}"
        return AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)

    return AutoTokenizer.from_pretrained(
        "black-forest-labs/FLUX.2-klein-4B",
        subfolder="tokenizer",
        revision="e7b7dc27f91deacad38e78976d1f2b499d76a294",
        local_files_only=True,
    )


def test_compact_flux_prompt_orders_invariants_and_sparse_traits_before_avoid_block():
    final_prompt = _final_flux_prompt()
    lowered = final_prompt.lower()

    for clause in CORE_CLAUSES:
        assert clause.lower() in lowered
    for clause in TRAIT_PAYLOAD_CLAUSES:
        assert clause in final_prompt
    for phrase in FORBIDDEN_IDENTITY_PHRASES:
        assert phrase not in lowered

    assert "broad impression categories without copying exact geometry" in final_prompt
    assert final_prompt.index("Core invariants:") < final_prompt.index("Trait card JSON first")
    assert final_prompt.index("Trait card JSON first") < final_prompt.index("Avoid:")
    assert final_prompt.count("Avoid:") == 1


def _nested_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _nested_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nested_keys(child)


def test_prompt_meta_and_generation_kwargs_do_not_persist_raw_prompt_text():
    prompt = build_avatar_prompt(trait_card=_dense_trait_card(), candidate_count=1)
    persisted = {
        "promptMeta": dict(prompt.meta),
        "generationKwargs": dict(prompt.generation_kwargs),
    }
    serialized = json.dumps(persisted, sort_keys=True)
    keys = set(_nested_keys(persisted))

    assert prompt.positive not in serialized
    assert prompt.negative not in serialized
    assert "rawPrompt" not in keys
    assert "raw_prompt" not in keys
    assert "promptText" not in keys
    assert "prompt_text" not in keys
    assert "positive" not in keys
    assert "negative" not in keys
    assert "promptHash" not in keys
    assert "imageHash" not in keys
    assert "sourceImageHash" not in keys
    assert "sourceImageSha256Prefix" not in keys
    assert "privacyReferenceSha256Prefix" not in keys
    assert "traitCardHash" not in keys

def test_generation_kwargs_seed_uses_worker_candidate_specific_seed_without_offset():
    input_seed = 983451

    for candidate_index in (2, 3, 7):
        prompt = build_avatar_prompt(
            trait_card=_dense_trait_card(),
            candidate_index=candidate_index,
            candidate_count=8,
            seed=input_seed,
        )

        assert prompt.generation_kwargs["seed"] == input_seed
        assert prompt.generation_kwargs["seed"] != input_seed + candidate_index


def test_deployed_flux_tokenizer_keeps_core_clauses_and_traits_inside_budget():
    tokenizer = _load_deployed_flux_tokenizer()
    final_prompt = _final_flux_prompt()
    encoded = tokenizer(final_prompt, add_special_tokens=True, truncation=False)
    token_count = len(encoded["input_ids"])
    truncated = tokenizer(
        final_prompt,
        add_special_tokens=True,
        max_length=TOKEN_BUDGET,
        truncation=True,
    )
    decoded = tokenizer.decode(truncated["input_ids"], skip_special_tokens=True)

    assert token_count <= TOKEN_BUDGET
    assert "Preserve broad resemblance" in decoded
    assert "Suppress exact biometric identity" in decoded
    assert "Avoid:" in decoded
    for clause in CORE_CLAUSES:
        assert clause in final_prompt
    for clause in TRAIT_PAYLOAD_CLAUSES:
        assert clause in final_prompt
        assert clause.strip('"').split(":", 1)[0] in decoded