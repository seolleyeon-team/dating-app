from __future__ import annotations

from .schema import TRAIT_CARD_ALLOWED_ENUMS, TRAIT_CARD_SCHEMA_VERSION


def _enum_lines() -> str:
    lines = []
    for key in sorted(TRAIT_CARD_ALLOWED_ENUMS):
        values = ", ".join(TRAIT_CARD_ALLOWED_ENUMS[key])
        lines.append(f"- {key}: {values}")
    return "\n".join(lines)


FLORENCE2_TRAIT_EXTRACTION_PROMPT = f"""You are extracting a privacy-safe enum trait card for Seolleyeon avatar generation v3.
Return JSON object only. No prose, markdown, explanations, comments, or code fences.
Use schemaVersion "{TRAIT_CARD_SCHEMA_VERSION}".
Top-level keys must be exactly schemaVersion, privacySafe, confidence, traitCard.
traitCard must use only the enum values listed below. If a value is not visible or is uncertain, use "unclear".
Remove unknown keys. Invalid enum values must become "unclear".
Do not output free text descriptors.
Do not output exact biometric geometry, face-recognition likeness, identity details, asymmetry patterns, exact pores, or facial measurements.
Do not output sensitive attributes such as race, ethnicity, nationality, religion, politics, health, disability, sexuality, gender identity, school name, address, or contact information.
Do not output beauty or attractiveness judgments such as beautiful, pretty, handsome, ugly, V-line, sharp jaw, tiny nose, large eyes, model, idol, influencer, or beauty upgrade.
Do not output unique marks such as moles, scars, birthmarks, tattoos, wrinkles, piercings, skin texture, or other identifying marks.
privacySafe must be true only when the returned traitCard contains broad visible enum categories and no forbidden details.
confidence must be a number from 0.0 to 1.0 based only on visible broad categories.

Allowed traitCard enums:
{_enum_lines()}"""
