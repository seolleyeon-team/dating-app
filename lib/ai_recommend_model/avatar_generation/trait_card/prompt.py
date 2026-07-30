from __future__ import annotations

from .schema import TRAIT_CARD_ALLOWED_ENUMS, TRAIT_CARD_SCHEMA_VERSION


def _enum_lines() -> str:
    lines = []
    for key in sorted(TRAIT_CARD_ALLOWED_ENUMS):
        values = ", ".join(TRAIT_CARD_ALLOWED_ENUMS[key])
        lines.append(f"- {key}: {values}")
    return "\n".join(lines)


FLORENCE2_TRAIT_EXTRACTION_PROMPT = f"""Extract a privacy-safe enum trait card for Seolleyeon avatar generation v3.
Return JSON object only: no prose, markdown, explanations, comments, or code fences.
Required top-level keys exactly: schemaVersion, privacySafe, confidence, traitCard.
schemaVersion must be "{TRAIT_CARD_SCHEMA_VERSION}".
traitCard values must be allowed enums only; use "unclear" for hidden, uncertain, or invalid enum input. Remove unknown keys.
Eyewear contract:
- visible glasses/sunglasses: eyewear_present="yes";
- face and eyes visible with no eyewear: eyewear_present="no", eyewear_style="none", eyewear_confidence="medium" or "high";
- eyes hidden or weak evidence: eyewear_present="unclear".
Extract only broad visible face, hair, eyewear, facial hair, clothing, and crop categories from the primary privacy-processed reference person.
Ignore background objects, rooms, streets, campus scenery, signs, posters, text, logos, brands, and locations.
Do not output free text descriptors, exact biometric geometry, face-recognition likeness, identity details, asymmetry patterns, exact pores, facial measurements, numeric landmarks, keypoints, boxes, embeddings, coordinates, or face-mesh data.
Do not output sensitive attributes: race, ethnicity, nationality, religion, politics, health, disability, sexuality, gender identity, school name, address, or contact information.
Do not output beauty judgments or upgrades: beautiful, pretty, handsome, ugly, V-line, sharp jaw, tiny nose, large eyes, model, idol, influencer, or beauty upgrade.
Do not output unique marks: moles, scars, birthmarks, tattoos, wrinkles, piercings, skin texture, or identifying marks.
privacySafe is true only when traitCard contains broad visible enum categories and no forbidden details.
confidence is 0.0 to 1.0 based only on visible broad categories.

Allowed traitCard enums:
{_enum_lines()}"""
