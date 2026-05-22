#!/usr/bin/env python3
"""Seolleyeon privacy-preserving avatar prompt builder v4.

Designed for black-forest-labs/FLUX.2-klein-4B, while keeping a provider
capability layer so the same policy can be reused with other image providers.

Core design goals:
- Replace free-text broad_cues with a validated, allowlisted AvatarTraitCard.
- Put all critical safety/privacy/anti-beautification instructions inside the
  positive prompt because FLUX.2 Klein Diffusers does not expose a simple
  negative_prompt text field in the normal call path.
- Still return a negative prompt string for providers/workflows that support it.
- Return generation kwargs, QA checks, reject reasons, and audit-friendly meta.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping, Sequence


# ---------------------------------------------------------------------------
# Public type aliases
# ---------------------------------------------------------------------------

Provider = Literal[
    "flux2_klein_4b_diffusers",
    "flux2_klein_4b_bfl_api",
    "sdxl_local_ip_adapter",
]

StyleMode = Literal[
    "privacy_3d_avatar",
    "subtle_minime",
    "soft_3d_avatar",
    "clay_animation",
]

PrivacyLevel = Literal[
    "balanced",
    "more_private",
    "more_resemblance",
    "anti_beauty_guard",
]

ReferenceMode = Literal[
    "reference_plus_trait",
    "direct_reference",
    "trait_card_only",
]

VisibleCrop = Literal[
    "face_only",
    "head_and_shoulders",
    "upper_body",
    "full_body_visible",
]

CropPolicy = Literal[
    "match_source_no_expansion",
    "app_card_cap_upper_body",
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderCapability:
    """Provider/model capabilities used by the builder.

    supports_negative_prompt_text=False means provider_negative should not be
    sent as a string field. Critical negative constraints are already embedded
    inside the positive prompt.
    """

    provider: Provider
    model_id: str
    supports_reference_image: bool
    supports_multi_reference: bool
    supports_negative_prompt_text: bool
    supports_negative_prompt_embeds: bool
    uses_empty_negative_by_default: bool
    recommended_width: int
    recommended_height: int
    recommended_num_inference_steps: int
    recommended_guidance_scale: float | None
    recommended_max_sequence_length: int | None
    notes: str


@dataclass(frozen=True)
class AvatarTraitCard:
    """Privacy-safe, broad visual trait card.

    Do not add fields for exact biometric geometry, unique marks, exact
    asymmetry, exact nose/lip/jaw contours, moles, scars, tattoos, or other
    identifying details. This schema intentionally allows only broad categories.
    """

    visible_crop: VisibleCrop = "head_and_shoulders"

    hair_length: Literal["short", "medium", "long"] | None = None
    hair_volume: Literal["low", "medium", "high"] | None = None
    hair_direction: Literal[
        "side_part",
        "center_part",
        "forward_bangs",
        "natural_messy",
        "pulled_back",
        "not_visible",
    ] | None = None
    hair_color_range: Literal["black", "dark_brown", "brown", "light_brown", "dyed_warm", "not_visible"] | None = None

    eyewear_present: bool | None = None
    eyewear_style: Literal["none", "round_black", "thin_metal", "rectangular", "clear_frame", "other_simple"] | None = None

    face_shape_category: Literal["round", "oval", "long", "soft_square"] | None = None
    eye_size_category: Literal["small", "medium", "medium_large"] | None = None
    eye_tilt_category: Literal["neutral", "slightly_upturned", "slightly_downturned"] | None = None
    brow_thickness: Literal["thin", "natural", "thick"] | None = None
    nose_prominence: Literal["soft", "medium", "defined"] | None = None
    cheek_fullness: Literal["low", "moderate", "full"] | None = None
    jaw_impression: Literal["soft", "moderate_defined", "broad_soft"] | None = None
    mouth_expression: Literal["neutral", "subtle_smile", "calm_closed"] | None = None

    skin_tone_range: Literal["fair_warm", "natural_beige", "medium_warm", "sun_kissed"] | None = None
    expression_mood: Literal["calm", "gentle", "neutral", "focused"] | None = None

    clothing_category: Literal["sweatshirt", "shirt", "polo", "jacket", "knit", "hoodie", "t_shirt", "not_visible"] | None = None
    clothing_color: Literal["blue", "white", "black", "beige", "gray", "navy", "brown", "green", "not_visible"] | None = None
    avatar_presentation_gender: Literal["male", "female", "non_binary", "prefer_not_to_say", "unknown"] | None = None

    def to_prompt_dict(self) -> dict[str, Any]:
        """Return non-null fields only, safe for prompt/meta serialization."""
        raw = asdict(self)
        return {k: v for k, v in raw.items() if v is not None}


@dataclass(frozen=True)
class AvatarPrompt:
    """Full builder output.

    positive:
        Main prompt. For FLUX.2 Klein, this is the primary policy vehicle.
    negative:
        Negative terms for compatible workflows. Do not rely on this alone.
    provider_negative:
        Negative string only when provider supports a negative_prompt text field.
        For FLUX.2 Klein Diffusers this is None by default.
    generation_kwargs:
        Suggested kwargs for the provider call, excluding the actual reference
        image object.
    qa_checks / reject_reasons:
        Machine-readable QA policy names for downstream review logic.
    meta:
        Audit-friendly prompt/model/policy metadata.
    """

    positive: str
    negative: str
    provider_negative: str | None
    generation_kwargs: Mapping[str, Any]
    qa_checks: tuple[str, ...]
    reject_reasons: tuple[str, ...]
    meta: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "positive": self.positive,
            "negative": self.negative,
            "provider_negative": self.provider_negative,
            "generation_kwargs": dict(self.generation_kwargs),
            "qa_checks": list(self.qa_checks),
            "reject_reasons": list(self.reject_reasons),
            "meta": dict(self.meta),
        }


@dataclass(frozen=True)
class CandidateVariant:
    key: str
    privacy_level: PrivacyLevel
    prompt_note: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Provider capability layer
# ---------------------------------------------------------------------------

PROVIDER_CAPABILITIES: dict[Provider, ProviderCapability] = {
    "flux2_klein_4b_diffusers": ProviderCapability(
        provider="flux2_klein_4b_diffusers",
        model_id="black-forest-labs/FLUX.2-klein-4B",
        supports_reference_image=True,
        supports_multi_reference=True,
        supports_negative_prompt_text=False,
        supports_negative_prompt_embeds=True,
        uses_empty_negative_by_default=True,
        recommended_width=1024,
        recommended_height=1024,
        recommended_num_inference_steps=4,
        recommended_guidance_scale=1.0,
        recommended_max_sequence_length=512,
        notes=(
            "Diffusers Flux2KleinPipeline accepts reference image input and "
            "negative_prompt_embeds, but not a simple negative_prompt string in "
            "the normal text prompt path. Keep core prohibitions in positive."
        ),
    ),
    "flux2_klein_4b_bfl_api": ProviderCapability(
        provider="flux2_klein_4b_bfl_api",
        model_id="black-forest-labs/FLUX.2-klein-4B",
        supports_reference_image=True,
        supports_multi_reference=True,
        supports_negative_prompt_text=False,
        supports_negative_prompt_embeds=False,
        uses_empty_negative_by_default=True,
        recommended_width=1024,
        recommended_height=1024,
        recommended_num_inference_steps=4,
        recommended_guidance_scale=1.0,
        recommended_max_sequence_length=None,
        notes="BFL/API wrapper behavior may vary; keep core prohibitions in positive.",
    ),
    "sdxl_local_ip_adapter": ProviderCapability(
        provider="sdxl_local_ip_adapter",
        model_id="local-sdxl-ip-adapter-faceid",
        supports_reference_image=True,
        supports_multi_reference=False,
        supports_negative_prompt_text=True,
        supports_negative_prompt_embeds=False,
        uses_empty_negative_by_default=False,
        recommended_width=1024,
        recommended_height=1024,
        recommended_num_inference_steps=28,
        recommended_guidance_scale=5.5,
        recommended_max_sequence_length=None,
        notes="Use negative prompt plus low identity/control weights; never use Beauty LoRA.",
    ),
}


# ---------------------------------------------------------------------------
# Allowlist validation
# ---------------------------------------------------------------------------

_ALLOWED_VALUES: dict[str, set[Any]] = {
    "visible_crop": {"face_only", "head_and_shoulders", "upper_body", "full_body_visible"},
    "hair_length": {"short", "medium", "long"},
    "hair_volume": {"low", "medium", "high"},
    "hair_direction": {"side_part", "center_part", "forward_bangs", "natural_messy", "pulled_back", "not_visible"},
    "hair_color_range": {"black", "dark_brown", "brown", "light_brown", "dyed_warm", "not_visible"},
    "eyewear_style": {"none", "round_black", "thin_metal", "rectangular", "clear_frame", "other_simple"},
    "face_shape_category": {"round", "oval", "long", "soft_square"},
    "eye_size_category": {"small", "medium", "medium_large"},
    "eye_tilt_category": {"neutral", "slightly_upturned", "slightly_downturned"},
    "brow_thickness": {"thin", "natural", "thick"},
    "nose_prominence": {"soft", "medium", "defined"},
    "cheek_fullness": {"low", "moderate", "full"},
    "jaw_impression": {"soft", "moderate_defined", "broad_soft"},
    "mouth_expression": {"neutral", "subtle_smile", "calm_closed"},
    "skin_tone_range": {"fair_warm", "natural_beige", "medium_warm", "sun_kissed"},
    "expression_mood": {"calm", "gentle", "neutral", "focused"},
    "clothing_category": {"sweatshirt", "shirt", "polo", "jacket", "knit", "hoodie", "t_shirt", "not_visible"},
    "clothing_color": {"blue", "white", "black", "beige", "gray", "navy", "brown", "green", "not_visible"},
    "avatar_presentation_gender": {"male", "female", "non_binary", "prefer_not_to_say", "unknown"},
}

_FORBIDDEN_CUE_SUBSTRINGS = (
    "mole",
    "scar",
    "birthmark",
    "tattoo",
    "exact",
    "identity",
    "lookalike",
    "celebrity",
    "idol",
    "beautiful",
    "handsome",
    "pretty",
    "v-line",
    "vline",
    "sharp jaw",
    "tiny nose",
    "large eyes",
    "bigger eyes",
)


def validate_trait_card(trait_card: AvatarTraitCard) -> None:
    """Validate allowlisted categorical fields.

    Type hints are not runtime validation. This function catches accidental or
    unsafe values before they enter the prompt.
    """
    data = trait_card.to_prompt_dict()
    for key, allowed in _ALLOWED_VALUES.items():
        value = data.get(key)
        if value is None:
            continue
        if value not in allowed:
            raise ValueError(f"Invalid trait_card.{key}={value!r}. Allowed: {sorted(allowed)!r}")

    # Defensive check in case values were created through type: ignore or raw dict conversion.
    for key, value in data.items():
        if isinstance(value, str):
            lowered = value.lower()
            for bad in _FORBIDDEN_CUE_SUBSTRINGS:
                if bad in lowered:
                    raise ValueError(
                        f"Unsafe trait_card.{key} contains forbidden descriptor {bad!r}: {value!r}"
                    )

    if trait_card.eyewear_present is False and trait_card.eyewear_style not in (None, "none"):
        raise ValueError("eyewear_style must be None or 'none' when eyewear_present is False")


def avatar_trait_card_from_dict(raw: Mapping[str, Any]) -> AvatarTraitCard:
    """Create and validate AvatarTraitCard from a JSON-like dict.

    Unknown keys are rejected instead of ignored. This prevents accidental
    reintroduction of free-text broad_cues or exact identifying descriptors.
    """
    if not isinstance(raw, Mapping):
        raise TypeError("raw must be a mapping/dict")

    allowed_keys = set(AvatarTraitCard.__dataclass_fields__.keys())
    unknown = sorted(set(str(k) for k in raw.keys()) - allowed_keys)
    if unknown:
        raise ValueError(f"Unknown AvatarTraitCard keys: {unknown!r}")

    card = AvatarTraitCard(**dict(raw))
    validate_trait_card(card)
    return card


# ---------------------------------------------------------------------------
# Prompt fragments
# ---------------------------------------------------------------------------

_STYLE_TEXT: dict[StyleMode, str] = {
    "privacy_3d_avatar": "Subtly stylized realistic adult 3D profile avatar style; ordinary university-student proportions; not chibi, baby-faced, doll-like, toy-like, mascot-like, or game-like.",
    "subtle_minime": "Subtly stylized realistic adult 3D profile avatar style; ordinary university-student proportions; not chibi, baby-faced, doll-like, toy-like, mascot-like, or game-like.",
    "soft_3d_avatar": "Soft realistic 3D app-profile avatar style; well-rendered but ordinary; not glossy character showcase or portfolio render.",
    "clay_animation": "Soft clay-inspired 3D animation feel; refined app-profile rendering; mature adult proportions; not toy product, mascot, or collectible figurine.",
}

_PRIVACY_TEXT: dict[PrivacyLevel, str] = {
    "balanced": "Medium broad resemblance only; keep mood, hairstyle, eyewear, expression, clothing category, and broad facial impression, not exact identity.",
    "more_private": "Prioritize lower re-identification risk; preserve mainly hairstyle, eyewear, clothing color, and expression mood; generalize facial structure more strongly.",
    "more_resemblance": "Slightly stronger broad overall impression, but still no exact biometric geometry, unique marks, or face-recognition likeness.",
    "anti_beauty_guard": "Prioritize anti-beautification; preserve ordinary broad impression even if soft, asymmetric, rounder, less sharp, or less model-like; do not upgrade attractiveness.",
}

_CROP_TEXT: dict[CropPolicy, str] = {
    "match_source_no_expansion": "Match the reference crop: face-only, head-and-shoulders, upper-body, or full-body only if actually visible. Never invent unseen lower body, legs, hands, accessories, outfit details, or body proportions.",
    "app_card_cap_upper_body": "Match the reference crop but cap at face, head-and-shoulders, or upper-body for app cards. Never expand beyond the source or invent unseen body/outfit details.",
}

_CANDIDATE_VARIANTS: tuple[CandidateVariant, ...] = (
    CandidateVariant(
        key="balanced",
        privacy_level="balanced",
        prompt_note="candidate 0: balanced medium broad resemblance with clear privacy-preserving generalization.",
        metadata={"identity_strength_target": 0.30, "biometric_abstraction_target": 0.62},
    ),
    CandidateVariant(
        key="hair_clothing_fidelity",
        privacy_level="more_private",
        prompt_note="candidate 1: slightly stronger hairstyle, eyewear, crop, and clothing fidelity, with the same privacy limits.",
        metadata={"identity_strength_target": 0.22, "biometric_abstraction_target": 0.75},
    ),
    CandidateVariant(
        key="softer_facial_abstraction",
        privacy_level="more_private",
        prompt_note="candidate 2: slightly softer facial abstraction, not more attractive or more idealized.",
        metadata={"identity_strength_target": 0.24, "biometric_abstraction_target": 0.78},
    ),
    CandidateVariant(
        key="strongest_privacy_generalization",
        privacy_level="anti_beauty_guard",
        prompt_note="candidate 3: strongest privacy generalization while keeping an ordinary adult student tone.",
        metadata={"identity_strength_target": 0.30, "biometric_abstraction_target": 0.65, "beautification": 0.0},
    ),
    CandidateVariant(
        key="regenerate_balanced",
        privacy_level="balanced",
        prompt_note="extra candidate 4: regenerate variation, balanced broad resemblance, not beautified.",
        metadata={"identity_strength_target": 0.30, "biometric_abstraction_target": 0.64},
    ),
    CandidateVariant(
        key="regenerate_style_fidelity",
        privacy_level="more_private",
        prompt_note="extra candidate 5: regenerate variation with hairstyle and clothing consistency, not beautified.",
        metadata={"identity_strength_target": 0.23, "biometric_abstraction_target": 0.76},
    ),
    CandidateVariant(
        key="regenerate_soft_abstraction",
        privacy_level="more_private",
        prompt_note="extra candidate 6: regenerate variation with softer facial abstraction, not beautified.",
        metadata={"identity_strength_target": 0.22, "biometric_abstraction_target": 0.80},
    ),
    CandidateVariant(
        key="regenerate_privacy_guard",
        privacy_level="anti_beauty_guard",
        prompt_note="extra candidate 7: regenerate variation with strongest privacy guard, not beautified.",
        metadata={"identity_strength_target": 0.20, "biometric_abstraction_target": 0.82, "beautification": 0.0},
    ),
)

_NEGATIVE_TERMS = (
    "photorealistic clone, exact biometric face copy, face-recognition likeness, identity-preserving replica, "
    "over-resemblance, exact facial geometry, exact eye distance, exact nose shape, exact jaw contour, "
    "exact mouth shape, exact cheekbone geometry, exact facial asymmetry, exact moles, exact scars, "
    "unique skin marks, unique wrinkles, copied skin texture, celebrity lookalike, idol styling, K-pop idol style, "
    "influencer photoshoot, model portfolio, fashion photoshoot, professional studio portrait, handsome upgrade, "
    "beauty upgrade, attractiveness enhancement, idealized face, perfect symmetry, sharper jawline, slimmer face, "
    "smaller face, V-line jaw, higher nose bridge, oversized eyes, larger eyes, tiny nose, childlike appearance, "
    "teenager look, babyface, chibi, doll face, toy figurine, collectible figurine, plastic toy, mascot, bobblehead, "
    "game character, glossy character showcase, glossy perfect skin, plastic doll skin, over-smoothed skin, "
    "hyper-realistic pores, school uniform, sexualized styling, nightclub, neon, nightlife, swimsuit, lingerie, "
    "luxury fashion styling, logo, readable text, watermark, school name, brand name, campus sign, detailed campus building, "
    "invented full body, invented lower body, invented legs, invented hands, body extension beyond source crop"
)

_QA_CHECKS: tuple[str, ...] = (
    "adult_20s_appearance",
    "not_childlike_or_teenage",
    "not_chibi_or_doll_like",
    "not_toy_or_mascot_like",
    "not_beautified_or_idol_like",
    "not_face_recognition_likeness",
    "no_exact_biometric_geometry",
    "no_unique_marks_copied",
    "visible_crop_respected",
    "visible_clothing_only",
    "neutral_background_no_text_logo",
    "ordinary_university_student_impression",
    "seolleyeon_quiet_romance_clear_trust_tone",
    "recommendation_style_consistency",
)

_REJECT_REASONS: tuple[str, ...] = (
    "too_identifiable",
    "too_generic",
    "too_beautified",
    "childlike_or_teenage",
    "chibi_or_babyface",
    "idol_or_influencer_style",
    "model_portfolio_style",
    "toy_or_mascot_like",
    "photorealistic_clone",
    "unique_marks_copied",
    "skin_texture_or_moles_copied",
    "exact_face_geometry_preserved",
    "crop_expanded_or_body_invented",
    "hands_or_lower_body_invented",
    "text_logo_watermark_or_school_name",
    "campus_sign_or_specific_background_cue",
    "sexualized_or_nightlife_style",
    "school_uniform_or_minor_coded_style",
    "style_inconsistent_for_clip_recommendation",
)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_trait_card(trait_card: AvatarTraitCard | None) -> str:
    if trait_card is None:
        return "No validated trait card provided; use only broad, visible, non-identifying categories from the privacy-processed reference."

    validate_trait_card(trait_card)
    data = trait_card.to_prompt_dict()
    return (
        "Trait card JSON, validated broad non-identifying categories only:\n"
        f"{json.dumps(data, ensure_ascii=False, sort_keys=True)}"
    )


def _presentation_gender_text(trait_card: AvatarTraitCard | None) -> str:
    gender = trait_card.avatar_presentation_gender if trait_card else None
    if gender == "male":
        return "Use the user-provided onboarding gender only as broad presentation guidance: ordinary adult male university student avatar. Do not infer gender from the face, stereotype, sexualize, or alter age/body."
    if gender == "female":
        return "Use the user-provided onboarding gender only as broad presentation guidance: ordinary adult female university student avatar. Do not infer gender from the face, stereotype, sexualize, or alter age/body."
    if gender == "non_binary":
        return "Use the user-provided onboarding gender only as broad presentation guidance: neutral ordinary adult university student avatar. Do not infer gender from the face, stereotype, sexualize, or alter age/body."
    return "No explicit onboarding gender guidance is available; keep a neutral ordinary adult university student presentation and do not infer gender from the face."


def _reference_mode_text(reference_mode: ReferenceMode) -> str:
    if reference_mode == "reference_plus_trait":
        return "Use the reference image plus the trait card; reference guides crop/style/mood, trait card limits preservation."
    if reference_mode == "direct_reference":
        return "Use the reference image directly, but only for broad non-identifying categories; stricter privacy QA is required."
    if reference_mode == "trait_card_only":
        return "Use the trait card only; no original reference image at generation time; lower re-identification risk but more generic."
    raise ValueError(f"Unsupported reference_mode: {reference_mode!r}")


def _build_positive_prompt(
    *,
    trait_card: AvatarTraitCard | None,
    style_mode: StyleMode,
    privacy_level: PrivacyLevel,
    reference_mode: ReferenceMode,
    crop_policy: CropPolicy,
    candidate_note: str | None,
) -> str:
    trait_text = _format_trait_card(trait_card)
    style_text = _STYLE_TEXT[style_mode]
    privacy_text = _PRIVACY_TEXT[privacy_level]
    crop_text = _CROP_TEXT[crop_policy]
    ref_text = _reference_mode_text(reference_mode)
    gender_text = _presentation_gender_text(trait_card)
    variant_text = f" Candidate calibration: {candidate_note}" if candidate_note else ""

    # Compact by design: Flux2KleinPipeline commonly uses max_sequence_length=512.
    return f"""
Create one standalone privacy-preserving adult 3D avatar for a Seolleyeon profile, a trusted university relationship platform.

Goal:
Represent only the user's broad visible impression, not exact identity or biometric identity.
The avatar should feel similar in mood and style to the reference, but should not be identifiable as the real person.

Use:
- the privacy-processed reference image for crop, general color, mood, hairstyle silhouette, eyewear presence, and clothing color/category
- the trait card for broad non-identifying visual categories only

Reference policy:
{ref_text}

Resemblance:
{privacy_text}

Do not preserve:
exact face geometry, eye distance, nose shape, jaw contour, mouth shape, cheekbones, facial asymmetry, pores, moles, scars, wrinkles, skin marks, or face-recognition likeness.

Style:
{style_text}
ordinary adult university student in their 20s.
Subtly stylized realistic 3D profile avatar with adult proportions.
Well-rendered but not beautified.
Do not make the avatar more handsome or prettier than the reference.
Do not enlarge eyes, shrink nose, slim face, sharpen jawline, improve symmetry, or create a V-line.

Avatar presentation:
{gender_text}

Crop:
{crop_text}
Do not invent unseen body parts, lower body, hands, accessories, logos, school names, brands, or background details.

Expression/background:
calm closed-mouth expression or very subtle natural smile.
simple warm off-white or quiet neutral background.

Trait card:
{trait_text}

Avoid:
{_NEGATIVE_TERMS}

Requirements:
calm, trustworthy, ordinary adult 3D Seolleyeon avatar; similar in broad mood/style but not identifiable as a biometric copy.{variant_text}
""".strip()

def _provider_generation_kwargs(
    *,
    caps: ProviderCapability,
    reference_mode: ReferenceMode,
    candidate_count: int,
    seed: int | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model_id": caps.model_id,
        "height": caps.recommended_height,
        "width": caps.recommended_width,
        "num_inference_steps": caps.recommended_num_inference_steps,
        "num_images_per_prompt": 1,
        "output_type": "pil",
        "reference_mode": reference_mode,
        "requires_reference_image": reference_mode in {"reference_plus_trait", "direct_reference"},
        "candidate_count": int(candidate_count),
    }
    if caps.recommended_guidance_scale is not None:
        kwargs["guidance_scale"] = caps.recommended_guidance_scale
    if caps.recommended_max_sequence_length is not None:
        kwargs["max_sequence_length"] = caps.recommended_max_sequence_length
    if seed is not None:
        kwargs["seed"] = int(seed)

    if caps.provider == "flux2_klein_4b_diffusers":
        kwargs.update({
            "pipeline_class": "diffusers.Flux2KleinPipeline",
            "image_argument_name": "image",
            "torch_dtype": "bfloat16",
            "negative_prompt_strategy": "positive_constraints_only",
            "negative_prompt_embeds": None,
        })
    elif caps.provider == "sdxl_local_ip_adapter":
        kwargs.update({
            "ip_adapter_faceid_weight": 0.25,
            "controlnet_face_structure_weight": 0.15,
            "denoise_strength": 0.68,
            "cfg_scale": caps.recommended_guidance_scale,
            "beauty_lora": False,
            "negative_prompt_strategy": "text_negative_prompt_supported",
        })
    else:
        kwargs.update({
            "negative_prompt_strategy": "positive_constraints_only",
        })
    return kwargs


# ---------------------------------------------------------------------------
# Public builder functions
# ---------------------------------------------------------------------------

def build_avatar_prompt(
    *,
    trait_card: AvatarTraitCard | None = None,
    provider: Provider = "flux2_klein_4b_diffusers",
    style_mode: StyleMode = "privacy_3d_avatar",
    privacy_level: PrivacyLevel = "balanced",
    reference_mode: ReferenceMode = "reference_plus_trait",
    crop_policy: CropPolicy = "match_source_no_expansion",
    candidate_index: int = 0,
    candidate_count: int = 4,
    seed: int | None = None,
) -> AvatarPrompt:
    """Build a Seolleyeon avatar prompt package.

    Recommended default for FLUX.2 Klein 4B:
        provider="flux2_klein_4b_diffusers"
        reference_mode="reference_plus_trait"
        style_mode="privacy_3d_avatar"
        candidate_count=4

    The actual reference image should be passed by the caller to the model
    pipeline, not embedded in this prompt object.
    """
    if provider not in PROVIDER_CAPABILITIES:
        raise ValueError(f"Unsupported provider: {provider!r}")
    if style_mode not in _STYLE_TEXT:
        raise ValueError(f"Unsupported style_mode: {style_mode!r}")
    if privacy_level not in _PRIVACY_TEXT:
        raise ValueError(f"Unsupported privacy_level: {privacy_level!r}")
    if crop_policy not in _CROP_TEXT:
        raise ValueError(f"Unsupported crop_policy: {crop_policy!r}")
    if candidate_count <= 0:
        raise ValueError("candidate_count must be > 0")

    caps = PROVIDER_CAPABILITIES[provider]
    if reference_mode in {"reference_plus_trait", "direct_reference"} and not caps.supports_reference_image:
        raise ValueError(f"Provider {provider!r} does not support reference images")

    variant = _CANDIDATE_VARIANTS[int(candidate_index) % len(_CANDIDATE_VARIANTS)]
    effective_privacy_level = variant.privacy_level if privacy_level == "balanced" and candidate_count > 1 else privacy_level

    positive = _build_positive_prompt(
        trait_card=trait_card,
        style_mode=style_mode,
        privacy_level=effective_privacy_level,
        reference_mode=reference_mode,
        crop_policy=crop_policy,
        candidate_note=variant.prompt_note,
    )

    generation_kwargs = _provider_generation_kwargs(
        caps=caps,
        reference_mode=reference_mode,
        candidate_count=candidate_count,
        seed=seed + int(candidate_index) if seed is not None else None,
    )

    provider_negative = _NEGATIVE_TERMS if caps.supports_negative_prompt_text else None

    meta = {
        "prompt_version": "seolleyeon_avatar_v3_flux2_klein",
        "brand_positioning": "Quiet Romance / Clear Trust",
        "provider": caps.provider,
        "model_id": caps.model_id,
        "provider_capability": asdict(caps),
        "style_mode": style_mode,
        "privacy_level_requested": privacy_level,
        "privacy_level_effective": effective_privacy_level,
        "reference_mode": reference_mode,
        "crop_policy": crop_policy,
        "candidate_index": int(candidate_index),
        "candidate_variant": variant.key,
        "candidate_variant_meta": dict(variant.metadata),
        "trait_card": trait_card.to_prompt_dict() if trait_card else None,
        "prompt_char_count": len(positive),
        "prompt_word_count_approx": len(positive.split()),
        "privacy_claim": "re_identification_risk_reduction_not_full_anonymization",
        "input_policy": {
            "use_visible_information_only": True,
            "free_text_broad_cues_allowed": False,
            "trait_card_allowlist_enforced": True,
            "exact_biometric_fields_allowed": False,
            "unique_marks_fields_allowed": False,
        },
        "storage_policy_recommendation": {
            "store_source_photo": False,
            "source_photo_ttl_hours": 24,
            "store_face_embedding_long_term": False,
            "store_approved_avatar_only": True,
            "requires_user_approval": True,
        },
        "recommendation_consistency": {
            "background_family": "warm_neutral_matte",
            "lighting": "soft_app_profile_lighting",
            "render_material": "soft_3d_avatar_not_toy",
            "beautification": 0.0,
            "reason": "Avatar images may feed CLIP/profile similarity, so style variance should not dominate recommendation signals.",
        },
    }

    return AvatarPrompt(
        positive=positive,
        negative=_NEGATIVE_TERMS,
        provider_negative=provider_negative,
        generation_kwargs=generation_kwargs,
        qa_checks=_QA_CHECKS,
        reject_reasons=_REJECT_REASONS,
        meta=meta,
    )


def build_candidate_avatar_prompts(
    *,
    trait_card: AvatarTraitCard | None = None,
    provider: Provider = "flux2_klein_4b_diffusers",
    style_mode: StyleMode = "privacy_3d_avatar",
    reference_mode: ReferenceMode = "reference_plus_trait",
    crop_policy: CropPolicy = "match_source_no_expansion",
    candidate_count: int = 4,
    seed: int | None = None,
) -> list[AvatarPrompt]:
    """Build a stable 4-candidate package.

    Only privacy/resemblance calibration changes between candidates. Style,
    background, lighting, and crop policy remain fixed for recommendation
    consistency.
    """
    return [
        build_avatar_prompt(
            trait_card=trait_card,
            provider=provider,
            style_mode=style_mode,
            privacy_level="balanced",
            reference_mode=reference_mode,
            crop_policy=crop_policy,
            candidate_index=i,
            candidate_count=candidate_count,
            seed=seed,
        )
        for i in range(candidate_count)
    ]


# ---------------------------------------------------------------------------
# Example use
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    example_trait_card = AvatarTraitCard(
        visible_crop="head_and_shoulders",
        hair_length="medium",
        hair_volume="medium",
        hair_direction="side_part",
        hair_color_range="dark_brown",
        eyewear_present=True,
        eyewear_style="thin_metal",
        face_shape_category="oval",
        eye_size_category="medium",
        eye_tilt_category="neutral",
        brow_thickness="natural",
        nose_prominence="medium",
        cheek_fullness="moderate",
        jaw_impression="soft",
        mouth_expression="calm_closed",
        skin_tone_range="natural_beige",
        expression_mood="calm",
        clothing_category="knit",
        clothing_color="gray",
    )
    prompt = build_avatar_prompt(trait_card=example_trait_card, seed=42)
    print(json.dumps(prompt.to_dict(), ensure_ascii=False, indent=2))
