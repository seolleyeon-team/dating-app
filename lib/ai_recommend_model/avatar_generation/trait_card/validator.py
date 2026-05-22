from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .schema import (
    TRAIT_CARD_ALLOWED_ENUMS,
    TRAIT_CARD_SCHEMA_VERSION,
    UNCLEAR,
    AvatarTraitCard,
    TraitCardValidationResult,
)


_ENVELOPE_KEYS = {"schemaVersion", "privacySafe", "confidence", "traitCard", "trait_card"}

_FORBIDDEN_PHRASES = (
    "biometric",
    "face-recognition",
    "face recognition",
    "identity",
    "lookalike",
    "exact",
    "asymmetry",
    "eye distance",
    "nose shape",
    "jaw contour",
    "mouth shape",
    "cheekbone",
    "pores",
    "skin texture",
    "mole",
    "moles",
    "scar",
    "scars",
    "birthmark",
    "tattoo",
    "tattoos",
    "wrinkle",
    "wrinkles",
    "piercing",
    "piercings",
    "beautiful",
    "pretty",
    "handsome",
    "ugly",
    "v-line",
    "vline",
    "sharp jaw",
    "tiny nose",
    "large eyes",
    "bigger eyes",
    "beauty",
    "attractive",
    "model",
    "idol",
    "influencer",
)

_SENSITIVE_PHRASES = (
    "race",
    "ethnicity",
    "ethnic",
    "nationality",
    "religion",
    "politic",
    "health",
    "disability",
    "sexuality",
    "gender identity",
    "school name",
    "address",
    "phone",
    "email",
    "contact",
)


def _empty_result(error: str) -> TraitCardValidationResult:
    return TraitCardValidationResult(
        schema_version=TRAIT_CARD_SCHEMA_VERSION,
        trait_card=AvatarTraitCard(),
        privacy_safe=False,
        confidence=0.0,
        errors=[error],
    )


def _loads_json_object(response: str) -> Mapping[str, Any] | TraitCardValidationResult:
    text = response.strip()
    if not text:
        return _empty_result("malformed_json")
    if not text.startswith("{"):
        return _empty_result("prose_or_non_json_response")

    decoder = json.JSONDecoder()
    try:
        parsed, end_index = decoder.raw_decode(text)
    except json.JSONDecodeError:
        return _empty_result("malformed_json")

    if text[end_index:].strip():
        return _empty_result("prose_or_non_json_response")
    if not isinstance(parsed, Mapping):
        return _empty_result("prose_or_non_json_response")
    return parsed


def _text_contains_unsafe_phrase(value: Any) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(phrase in lowered for phrase in _FORBIDDEN_PHRASES + _SENSITIVE_PHRASES)
    if isinstance(value, Mapping):
        return any(
            _text_contains_unsafe_phrase(key) or _text_contains_unsafe_phrase(child)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(_text_contains_unsafe_phrase(child) for child in value)
    return False


def _safe_unknown_path(path: str) -> str | None:
    if _text_contains_unsafe_phrase(path):
        return None
    return path


def _coerce_confidence(value: Any, fallback: float) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = fallback
    return round(max(0.0, min(1.0, confidence)), 4)


def _coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return fallback


def normalize_avatar_presentation_gender(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"male", "m", "man", "남성", "남자"}:
        return "male"
    if raw in {"female", "f", "woman", "여성", "여자"}:
        return "female"
    if raw in {"other", "non_binary", "non-binary", "nonbinary"}:
        return "non_binary"
    if raw in {"prefer_not_to_say", "prefer-not-to-say"}:
        return "prefer_not_to_say"
    return "unknown"


def _is_wrapped_payload(payload: Mapping[str, Any]) -> bool:
    return any(key in payload for key in _ENVELOPE_KEYS)


def _trait_payload(payload: Mapping[str, Any], wrapped: bool) -> Mapping[str, Any]:
    if wrapped:
        nested = payload.get("traitCard", payload.get("trait_card", {}))
        return nested if isinstance(nested, Mapping) else {}
    return payload


def validate_trait_card_response(
    response: str | Mapping[str, Any],
    *,
    avatar_presentation_gender: Any = None,
) -> TraitCardValidationResult:
    """Parse and deterministically sanitize a Florence-2 trait-card response.

    The validator never preserves free text. Every trait card field is one of
    the allowlisted enum values or "unclear". Unknown keys are removed.
    """
    if isinstance(response, str):
        parsed = _loads_json_object(response)
        if isinstance(parsed, TraitCardValidationResult):
            return parsed
        payload: Mapping[str, Any] = parsed
    elif isinstance(response, Mapping):
        payload = response
    else:
        return _empty_result("malformed_json")

    wrapped = _is_wrapped_payload(payload)
    errors: list[str] = []
    removed_keys: list[str] = []
    invalid_enum_fields: list[str] = []
    sanitized_fields: list[str] = []
    unsafe_content_found = False

    if wrapped:
        schema_version = payload.get("schemaVersion")
        if schema_version not in (None, TRAIT_CARD_SCHEMA_VERSION):
            errors.append("unsupported_schema_version")

        for raw_key, value in sorted(payload.items(), key=lambda item: str(item[0])):
            key = str(raw_key)
            if key in _ENVELOPE_KEYS:
                continue
            if _text_contains_unsafe_phrase(value):
                unsafe_content_found = True
            safe_path = _safe_unknown_path(key)
            if safe_path is None:
                unsafe_content_found = True
            else:
                removed_keys.append(safe_path)

    if wrapped and ("traitCard" in payload or "trait_card" in payload):
        nested = payload.get("traitCard", payload.get("trait_card"))
        if not isinstance(nested, Mapping):
            errors.append("invalid_trait_card_object")

    raw_trait_card = _trait_payload(payload, wrapped)
    normalized: dict[str, str] = {}

    for raw_key, value in sorted(raw_trait_card.items(), key=lambda item: str(item[0])):
        key = str(raw_key)
        if key in TRAIT_CARD_ALLOWED_ENUMS:
            continue
        if _text_contains_unsafe_phrase(value):
            unsafe_content_found = True
        safe_path = _safe_unknown_path(f"traitCard.{key}")
        if safe_path is None:
            unsafe_content_found = True
        else:
            removed_keys.append(safe_path)

    backend_gender = normalize_avatar_presentation_gender(avatar_presentation_gender)

    for key, allowed_values in TRAIT_CARD_ALLOWED_ENUMS.items():
        if key == "avatar_presentation_gender":
            normalized[key] = backend_gender
            continue
        raw_value = raw_trait_card.get(key, UNCLEAR)
        if _text_contains_unsafe_phrase(raw_value):
            normalized[key] = UNCLEAR
            sanitized_fields.append(key)
            unsafe_content_found = True
            continue
        if raw_value in allowed_values:
            normalized[key] = str(raw_value)
        else:
            normalized[key] = UNCLEAR
            invalid_enum_fields.append(key)

    model_privacy_safe = _coerce_bool(
        payload.get("privacySafe"),
        True if not wrapped else False,
    )
    privacy_safe = model_privacy_safe and not errors and not unsafe_content_found
    confidence = _coerce_confidence(payload.get("confidence"), 1.0 if not wrapped else 0.0)
    if errors or unsafe_content_found or not privacy_safe:
        confidence = 0.0
    elif invalid_enum_fields:
        confidence = min(confidence, 0.5)

    return TraitCardValidationResult(
        schema_version=TRAIT_CARD_SCHEMA_VERSION,
        trait_card=AvatarTraitCard(**normalized),
        privacy_safe=privacy_safe,
        confidence=confidence,
        errors=errors,
        removed_keys=removed_keys,
        invalid_enum_fields=invalid_enum_fields,
        sanitized_fields=sanitized_fields,
    )
