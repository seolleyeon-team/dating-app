"""Server-authoritative trait-QA applicability and action contract.

Trait evidence is intentionally absent from the canonical Azure GPT-Image-2
generation path.  This module keeps that design decision separate from the
legacy trait comparison implementation so an empty evidence mapping can never
silently become a passing result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


TRAIT_QA_POLICY_VERSION = "trait_policy_v2_applicability_v1"

TRAIT_QA_APPLICABILITY_AVAILABLE = "available"
TRAIT_QA_APPLICABILITY_NOT_APPLICABLE = "not_applicable"
TRAIT_QA_APPLICABILITY_UNAVAILABLE = "unavailable"
TRAIT_QA_APPLICABILITIES = frozenset(
    {
        TRAIT_QA_APPLICABILITY_AVAILABLE,
        TRAIT_QA_APPLICABILITY_NOT_APPLICABLE,
        TRAIT_QA_APPLICABILITY_UNAVAILABLE,
    }
)

TRAIT_QA_ACTION_ALLOW = "allow"
TRAIT_QA_ACTION_REVIEW = "review"
TRAIT_QA_ACTIONS = frozenset({TRAIT_QA_ACTION_ALLOW, TRAIT_QA_ACTION_REVIEW})

TRAIT_QA_MODE_CANONICAL_DISABLED = "disabled_by_pipeline"
TRAIT_QA_MODE_ENABLED = "enabled"
TRAIT_QA_MODE_UNKNOWN = "unknown"

_CANONICAL_AZURE_MODE = "azure_gpt_image_2"
_DIRECT_SOURCE_INPUT_MODES = frozenset(
    {"original_direct", "storage_normalized_original_direct"}
)
_TRAIT_ENABLED_PIPELINE_MODES = frozenset({"dry_run", "trait_enabled"})
_MISSING_EVIDENCE_STATUSES = frozenset(
    {"", "missing", "unavailable", "critical_unavailable", "failed", "review", "unknown"}
)
_UNCLEAR_VALUES = frozenset(
    {"", "unknown", "unclear", "uncertain", "unsure", "n/a", "not_visible", "prefer_not_to_say"}
)
_TRAIT_KEYS = frozenset(
    {
        "visible_crop",
        "hair_length",
        "hair_volume",
        "hair_direction",
        "hair_bangs",
        "hair_color_range",
        "eyewear_present",
        "eyewear_style",
        "facial_hair_present",
        "facial_hair_style",
        "face_shape_category",
        "facial_feature_balance",
        "eye_size_category",
        "eye_tilt_category",
        "eye_shape_mood",
        "brow_thickness",
        "brow_shape",
        "nose_prominence",
        "nose_bridge_impression",
        "cheek_fullness",
        "jaw_impression",
        "mouth_expression",
        "mouth_fullness_category",
        "skin_tone_range",
        "expression_mood",
        "clothing_category",
        "clothing_color",
        "avatar_presentation_gender",
        "eyewear",
    }
)
_COMPARISON_STATUSES = frozenset({"match", "mismatch", "review"})


@dataclass(frozen=True)
class TraitQAResult:
    """Privacy-safe normalized trait decision."""

    applicability: str
    action: str
    reason: str
    comparison_status: str = "not_evaluated"
    source_evidence_present: bool = False
    candidate_evidence_present: bool = False

    @property
    def needs_review(self) -> bool:
        return self.action == TRAIT_QA_ACTION_REVIEW

    @property
    def hard_reject(self) -> bool:
        # Trait mismatch/unavailability is a review decision, never a hard reject.
        return False

    @property
    def trait_review_contribution(self) -> bool:
        return self.needs_review

    @property
    def satisfied(self) -> bool:
        return trait_qa_satisfied(self.applicability, self.action)

    def to_document(self) -> dict[str, Any]:
        return {
            "traitQaApplicability": self.applicability,
            "traitQaAction": self.action,
            "traitQaReason": self.reason,
            "traitReviewContribution": self.trait_review_contribution,
            "traitPolicyVersion": TRAIT_QA_POLICY_VERSION,
        }


def resolve_trait_qa_state(
    pipeline_contract: Mapping[str, Any] | None,
    source_trait_evidence: Mapping[str, Any] | None,
    candidate_trait_evidence: Mapping[str, Any] | None,
    comparison_result: Mapping[str, Any] | None,
) -> TraitQAResult:
    """Resolve applicability before interpreting trait comparison values.

    The pipeline contract is expected to be server-generated.  Client-provided
    ``traitQaApplicability`` and ``traitQaAction`` fields are deliberately not
    read as authority.
    """

    mode = classify_trait_qa_pipeline(pipeline_contract)
    if mode == TRAIT_QA_MODE_CANONICAL_DISABLED:
        return TraitQAResult(
            applicability=TRAIT_QA_APPLICABILITY_NOT_APPLICABLE,
            action=TRAIT_QA_ACTION_ALLOW,
            reason="disabled_by_canonical_azure_pipeline",
            comparison_status="not_evaluated",
        )
    if mode != TRAIT_QA_MODE_ENABLED:
        return TraitQAResult(
            applicability=TRAIT_QA_APPLICABILITY_UNAVAILABLE,
            action=TRAIT_QA_ACTION_REVIEW,
            reason="pipeline_applicability_unknown",
            comparison_status="not_evaluated",
        )

    source_present = _trait_evidence_present(source_trait_evidence)
    candidate_present = _trait_evidence_present(candidate_trait_evidence)
    if not source_present and not candidate_present:
        return _unavailable_result(
            "source_and_candidate_trait_evidence_missing",
            source_present=source_present,
            candidate_present=candidate_present,
        )
    if not source_present:
        return _unavailable_result(
            "source_trait_evidence_missing",
            source_present=source_present,
            candidate_present=candidate_present,
        )
    if not candidate_present:
        return _unavailable_result(
            "candidate_trait_evidence_missing",
            source_present=source_present,
            candidate_present=candidate_present,
        )

    statuses = {
        str(value or "").strip().lower()
        for value in (comparison_result or {}).values()
        if str(value or "").strip().lower() in _COMPARISON_STATUSES
    }
    if not statuses:
        return _unavailable_result(
            "trait_comparison_evidence_missing",
            source_present=source_present,
            candidate_present=candidate_present,
        )
    if "mismatch" in statuses:
        return TraitQAResult(
            applicability=TRAIT_QA_APPLICABILITY_AVAILABLE,
            action=TRAIT_QA_ACTION_REVIEW,
            reason="trait_comparison_mismatch",
            comparison_status="mismatch",
            source_evidence_present=source_present,
            candidate_evidence_present=candidate_present,
        )
    if "review" in statuses:
        return TraitQAResult(
            applicability=TRAIT_QA_APPLICABILITY_AVAILABLE,
            action=TRAIT_QA_ACTION_REVIEW,
            reason="trait_comparison_uncertain",
            comparison_status="review",
            source_evidence_present=source_present,
            candidate_evidence_present=candidate_present,
        )
    return TraitQAResult(
        applicability=TRAIT_QA_APPLICABILITY_AVAILABLE,
        action=TRAIT_QA_ACTION_ALLOW,
        reason="trait_comparison_match",
        comparison_status="match",
        source_evidence_present=source_present,
        candidate_evidence_present=candidate_present,
    )


def classify_trait_qa_pipeline(pipeline_contract: Mapping[str, Any] | None) -> str:
    """Return the server-side trait-QA mode from authoritative provenance."""

    contract = pipeline_contract if isinstance(pipeline_contract, Mapping) else {}
    if _is_canonical_azure_contract(contract):
        return TRAIT_QA_MODE_CANONICAL_DISABLED

    pipeline_mode = _text(contract.get("pipelineMode") or contract.get("workerMode"))
    trait_mode = _text(contract.get("traitQaMode"))
    authority = _text(contract.get("traitQaAuthority"))
    if pipeline_mode in _TRAIT_ENABLED_PIPELINE_MODES and authority == "server":
        # A disabled-by-pipeline claim cannot override a server-known legacy
        # mode.  The worker mode remains the authority.
        return TRAIT_QA_MODE_ENABLED
    if trait_mode == TRAIT_QA_MODE_ENABLED and authority == "server":
        return TRAIT_QA_MODE_ENABLED
    return TRAIT_QA_MODE_UNKNOWN


def normalize_trait_qa_state(value: Mapping[str, Any] | None) -> TraitQAResult | None:
    """Normalize an already-resolved state carried through QA signals."""

    if not isinstance(value, Mapping):
        return None
    raw_applicability = _text(value.get("traitQaApplicability"))
    raw_action = _text(value.get("traitQaAction"))
    if not raw_applicability and not raw_action:
        return None
    applicability = (
        raw_applicability
        if raw_applicability in TRAIT_QA_APPLICABILITIES
        else TRAIT_QA_APPLICABILITY_UNAVAILABLE
    )
    if applicability == TRAIT_QA_APPLICABILITY_NOT_APPLICABLE:
        action = TRAIT_QA_ACTION_ALLOW
        default_reason = "disabled_by_canonical_azure_pipeline"
    elif applicability == TRAIT_QA_APPLICABILITY_UNAVAILABLE:
        action = TRAIT_QA_ACTION_REVIEW
        default_reason = "trait_evidence_unavailable"
    else:
        action = raw_action if raw_action in TRAIT_QA_ACTIONS else TRAIT_QA_ACTION_REVIEW
        default_reason = "trait_action_invalid" if raw_action not in TRAIT_QA_ACTIONS else "trait_action_resolved"
    reason = _text(value.get("traitQaReason")) or default_reason
    return TraitQAResult(
        applicability=applicability,
        action=action,
        reason=reason,
        comparison_status=_text(value.get("traitComparisonStatus")) or "not_evaluated",
    )


def trait_qa_satisfied(applicability: str, action: str) -> bool:
    normalized_applicability = _text(applicability)
    normalized_action = _text(action)
    return normalized_applicability == TRAIT_QA_APPLICABILITY_NOT_APPLICABLE or (
        normalized_applicability == TRAIT_QA_APPLICABILITY_AVAILABLE
        and normalized_action == TRAIT_QA_ACTION_ALLOW
    )


def _unavailable_result(
    reason: str,
    *,
    source_present: bool,
    candidate_present: bool,
) -> TraitQAResult:
    return TraitQAResult(
        applicability=TRAIT_QA_APPLICABILITY_UNAVAILABLE,
        action=TRAIT_QA_ACTION_REVIEW,
        reason=reason,
        comparison_status="not_available",
        source_evidence_present=source_present,
        candidate_evidence_present=candidate_present,
    )


def _is_canonical_azure_contract(contract: Mapping[str, Any]) -> bool:
    backend = _text(contract.get("generationBackend") or contract.get("generation_backend"))
    source_input = _text(contract.get("sourceInputMode") or contract.get("source_input_mode"))
    pipeline_mode = _text(contract.get("pipelineMode") or contract.get("workerMode"))
    if backend != _CANONICAL_AZURE_MODE or source_input not in _DIRECT_SOURCE_INPUT_MODES:
        return False
    if pipeline_mode and pipeline_mode != _CANONICAL_AZURE_MODE:
        return False
    return (
        _text(contract.get("provider")) == "azure"
        and _text(contract.get("uploadNormalization")) == "existing_avatar_media_ingestion"
        and _text(contract.get("preGenerationTransform")) == "none"
        and _text(contract.get("pipelineMode")) == _CANONICAL_AZURE_MODE
        and contract.get("legacyTraitExtraction") is False
        and contract.get("legacyReferencePreprocessing") is False
        and contract.get("legacyFlux") is False
        and _text(contract.get("traitQaMode")) == TRAIT_QA_MODE_CANONICAL_DISABLED
        and _text(contract.get("traitQaAuthority")) == "server"
    )


def _trait_evidence_present(value: Mapping[str, Any] | None) -> bool:
    if not isinstance(value, Mapping) or not value:
        return False
    availability_keys = (
        "traitExtractionAvailability",
        "trait_qa_availability",
        "availability",
    )
    for key in availability_keys:
        if key not in value:
            continue
        availability = _text(value.get(key))
        if availability in _MISSING_EVIDENCE_STATUSES:
            return False
        break
    card = value.get("traitCard")
    candidate = card if isinstance(card, Mapping) else value
    for key, raw in candidate.items():
        normalized_key = str(key).strip()
        if normalized_key not in _TRAIT_KEYS:
            continue
        if _concrete_value(raw):
            return True
    return False


def _concrete_value(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key in ("value", "label", "present"):
            if key in value:
                value = value[key]
                break
    if value is None or isinstance(value, bool):
        return value is not None
    if isinstance(value, (int, float)):
        return True
    return _text(value) not in _UNCLEAR_VALUES


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


__all__ = [
    "TRAIT_QA_ACTION_ALLOW",
    "TRAIT_QA_ACTION_REVIEW",
    "TRAIT_QA_ACTIONS",
    "TRAIT_QA_APPLICABILITY_AVAILABLE",
    "TRAIT_QA_APPLICABILITY_NOT_APPLICABLE",
    "TRAIT_QA_APPLICABILITY_UNAVAILABLE",
    "TRAIT_QA_APPLICABILITIES",
    "TRAIT_QA_MODE_CANONICAL_DISABLED",
    "TRAIT_QA_MODE_ENABLED",
    "TRAIT_QA_MODE_UNKNOWN",
    "TRAIT_QA_POLICY_VERSION",
    "TraitQAResult",
    "classify_trait_qa_pipeline",
    "normalize_trait_qa_state",
    "resolve_trait_qa_state",
    "trait_qa_satisfied",
]
