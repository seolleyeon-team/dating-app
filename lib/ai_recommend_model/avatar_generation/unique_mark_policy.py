"""Server-authoritative unique-mark QA applicability and action contract.

The canonical Azure GPT-Image-2 pipeline intentionally has no unique-mark
producer.  This module resolves that pipeline fact before interpreting the
diagnostic ``uniqueMarkCopyRisk`` value, so absence-by-design is not confused
with a failed producer and unknown values are never rewritten to ``low``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


UNIQUE_MARK_QA_POLICY_VERSION = "unique_mark_policy_v2_applicability_v1"

UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE = "available"
UNIQUE_MARK_QA_APPLICABILITY_NOT_APPLICABLE = "not_applicable"
UNIQUE_MARK_QA_APPLICABILITY_UNAVAILABLE = "unavailable"
UNIQUE_MARK_QA_APPLICABILITIES = frozenset(
    {
        UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE,
        UNIQUE_MARK_QA_APPLICABILITY_NOT_APPLICABLE,
        UNIQUE_MARK_QA_APPLICABILITY_UNAVAILABLE,
    }
)

UNIQUE_MARK_QA_ACTION_ALLOW = "allow"
UNIQUE_MARK_QA_ACTION_REVIEW = "review"
UNIQUE_MARK_QA_ACTION_REJECT = "reject"
UNIQUE_MARK_QA_ACTIONS = frozenset(
    {
        UNIQUE_MARK_QA_ACTION_ALLOW,
        UNIQUE_MARK_QA_ACTION_REVIEW,
        UNIQUE_MARK_QA_ACTION_REJECT,
    }
)

UNIQUE_MARK_QA_MODE_DISABLED = "disabled_by_pipeline"
UNIQUE_MARK_QA_MODE_ENABLED = "enabled"
UNIQUE_MARK_QA_MODE_UNKNOWN = "unknown"

_CANONICAL_AZURE_MODE = "azure_gpt_image_2"
_DIRECT_SOURCE_INPUT_MODES = frozenset(
    {"original_direct", "storage_normalized_original_direct"}
)
_SERVER_AUTHORITY = "server"
_LOW_RISK_VALUES = frozenset({"low", "none", "pass", "clear", "ok"})
_MEDIUM_RISK_VALUES = frozenset(
    {"medium", "review", "needs_review", "uncertain", "unclear"}
)
_HIGH_RISK_VALUES = frozenset({"high", "fail", "reject", "rejected"})
_UNAVAILABLE_VALUES = frozenset(
    {"", "missing", "unavailable", "critical_unavailable", "failed", "unknown"}
)


@dataclass(frozen=True)
class UniqueMarkQAResult:
    """Privacy-safe normalized unique-mark decision."""

    applicability: str
    action: str
    reason: str
    evidence_present: bool = False

    @property
    def needs_review(self) -> bool:
        return self.action == UNIQUE_MARK_QA_ACTION_REVIEW

    @property
    def hard_reject(self) -> bool:
        return self.action == UNIQUE_MARK_QA_ACTION_REJECT

    @property
    def satisfied(self) -> bool:
        return unique_mark_qa_satisfied(self.applicability, self.action)

    def to_document(self) -> dict[str, Any]:
        return {
            "uniqueMarkQaApplicability": self.applicability,
            "uniqueMarkQaAction": self.action,
            "uniqueMarkQaReason": self.reason,
            "uniqueMarkPolicyVersion": UNIQUE_MARK_QA_POLICY_VERSION,
        }


def resolve_unique_mark_qa_state(
    pipeline_contract: Mapping[str, Any] | None,
    evidence: Mapping[str, Any] | None,
) -> UniqueMarkQAResult:
    """Resolve applicability from server-side provenance before evidence.

    ``pipeline_contract`` is expected to be server-generated.  Client-provided
    applicability/action claims inside ``evidence`` are deliberately ignored.
    """

    contract = pipeline_contract if isinstance(pipeline_contract, Mapping) else {}
    mode = classify_unique_mark_qa_pipeline(contract)
    if mode == UNIQUE_MARK_QA_MODE_DISABLED:
        reason = (
            "disabled_by_canonical_azure_pipeline"
            if _is_canonical_azure_contract(contract)
            else "disabled_by_server_pipeline_contract"
        )
        return UniqueMarkQAResult(
            applicability=UNIQUE_MARK_QA_APPLICABILITY_NOT_APPLICABLE,
            action=UNIQUE_MARK_QA_ACTION_ALLOW,
            reason=reason,
            evidence_present=False,
        )
    if mode == UNIQUE_MARK_QA_MODE_ENABLED:
        return _resolve_enabled_evidence(evidence)
    return UniqueMarkQAResult(
        applicability=UNIQUE_MARK_QA_APPLICABILITY_UNAVAILABLE,
        action=UNIQUE_MARK_QA_ACTION_REVIEW,
        reason="pipeline_applicability_unknown",
        evidence_present=False,
    )


def normalize_unique_mark_copy_risk(evidence: Mapping[str, Any] | None) -> str:
    """Normalize only the coarse risk label; never infer low from absence."""

    values = evidence if isinstance(evidence, Mapping) else {}
    if "uniqueMarkCopied" in values:
        copied = values.get("uniqueMarkCopied")
        if copied is True:
            return "high"
        if copied is False:
            return "low"
    raw = _text(values.get("uniqueMarkCopyRisk"))
    if raw in _LOW_RISK_VALUES:
        return "low"
    if raw in _MEDIUM_RISK_VALUES:
        return "medium"
    if raw in _HIGH_RISK_VALUES:
        return "high"
    if raw in {"unavailable", "missing", "critical_unavailable", "failed"}:
        return "unavailable"
    return "unknown"


def classify_unique_mark_qa_pipeline(
    pipeline_contract: Mapping[str, Any] | None,
) -> str:
    """Classify unique-mark QA mode from server-authoritative provenance."""

    contract = pipeline_contract if isinstance(pipeline_contract, Mapping) else {}
    if _is_canonical_azure_contract(contract):
        return UNIQUE_MARK_QA_MODE_DISABLED

    mode = _text(
        contract.get("uniqueMarkQaMode")
        or contract.get("unique_mark_qa_mode")
    )
    authority = _text(
        contract.get("uniqueMarkQaAuthority")
        or contract.get("unique_mark_qa_authority")
    )
    if authority != _SERVER_AUTHORITY:
        return UNIQUE_MARK_QA_MODE_UNKNOWN
    if mode == UNIQUE_MARK_QA_MODE_ENABLED:
        return UNIQUE_MARK_QA_MODE_ENABLED
    if mode == UNIQUE_MARK_QA_MODE_DISABLED:
        return UNIQUE_MARK_QA_MODE_DISABLED
    return UNIQUE_MARK_QA_MODE_UNKNOWN


def normalize_unique_mark_qa_state(
    value: Mapping[str, Any] | None,
) -> UniqueMarkQAResult | None:
    """Normalize an already-resolved typed state carried through QA signals."""

    if not isinstance(value, Mapping):
        return None
    raw_applicability = _text(value.get("uniqueMarkQaApplicability"))
    raw_action = _text(value.get("uniqueMarkQaAction"))
    if not raw_applicability and not raw_action:
        return None

    applicability = (
        raw_applicability
        if raw_applicability in UNIQUE_MARK_QA_APPLICABILITIES
        else UNIQUE_MARK_QA_APPLICABILITY_UNAVAILABLE
    )
    if applicability == UNIQUE_MARK_QA_APPLICABILITY_NOT_APPLICABLE:
        action = UNIQUE_MARK_QA_ACTION_ALLOW
        default_reason = "disabled_by_server_pipeline_contract"
    elif applicability == UNIQUE_MARK_QA_APPLICABILITY_UNAVAILABLE:
        action = UNIQUE_MARK_QA_ACTION_REVIEW
        default_reason = "unique_mark_evidence_unavailable"
    else:
        action = (
            raw_action
            if raw_action in UNIQUE_MARK_QA_ACTIONS
            else UNIQUE_MARK_QA_ACTION_REVIEW
        )
        default_reason = (
            "unique_mark_action_invalid"
            if raw_action not in UNIQUE_MARK_QA_ACTIONS
            else "unique_mark_action_resolved"
        )
    return UniqueMarkQAResult(
        applicability=applicability,
        action=action,
        reason=_text(value.get("uniqueMarkQaReason")) or default_reason,
        evidence_present=applicability == UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE,
    )


def unique_mark_qa_satisfied(applicability: str, action: str) -> bool:
    """Return whether the unique-mark contract permits preview/hard pass."""

    normalized_applicability = _text(applicability)
    normalized_action = _text(action)
    return normalized_applicability == UNIQUE_MARK_QA_APPLICABILITY_NOT_APPLICABLE or (
        normalized_applicability == UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE
        and normalized_action == UNIQUE_MARK_QA_ACTION_ALLOW
    )


def _resolve_enabled_evidence(
    evidence: Mapping[str, Any] | None,
) -> UniqueMarkQAResult:
    values = evidence if isinstance(evidence, Mapping) else {}
    availability = _text(values.get("uniqueMarkEvidenceAvailability"))
    if availability in _UNAVAILABLE_VALUES - {""}:
        return _unavailable_result("unique_mark_evidence_unavailable")
    risk = normalize_unique_mark_copy_risk(values)

    if risk in _LOW_RISK_VALUES:
        return UniqueMarkQAResult(
            applicability=UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE,
            action=UNIQUE_MARK_QA_ACTION_ALLOW,
            reason="unique_mark_evidence_available_low",
            evidence_present=True,
        )
    if risk in _HIGH_RISK_VALUES:
        return UniqueMarkQAResult(
            applicability=UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE,
            action=UNIQUE_MARK_QA_ACTION_REJECT,
            reason="unique_mark_evidence_available_high",
            evidence_present=True,
        )
    if risk in _MEDIUM_RISK_VALUES:
        return UniqueMarkQAResult(
            applicability=UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE,
            action=UNIQUE_MARK_QA_ACTION_REVIEW,
            reason="unique_mark_evidence_uncertain",
            evidence_present=True,
        )
    return _unavailable_result("unique_mark_evidence_unavailable")


def _unavailable_result(reason: str) -> UniqueMarkQAResult:
    return UniqueMarkQAResult(
        applicability=UNIQUE_MARK_QA_APPLICABILITY_UNAVAILABLE,
        action=UNIQUE_MARK_QA_ACTION_REVIEW,
        reason=reason,
        evidence_present=False,
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
        and _text(contract.get("traitQaMode")) == "disabled_by_pipeline"
        and _text(contract.get("traitQaAuthority")) == _SERVER_AUTHORITY
    )


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


__all__ = [
    "UNIQUE_MARK_QA_ACTION_ALLOW",
    "UNIQUE_MARK_QA_ACTION_REJECT",
    "UNIQUE_MARK_QA_ACTION_REVIEW",
    "UNIQUE_MARK_QA_ACTIONS",
    "UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE",
    "UNIQUE_MARK_QA_APPLICABILITY_NOT_APPLICABLE",
    "UNIQUE_MARK_QA_APPLICABILITY_UNAVAILABLE",
    "UNIQUE_MARK_QA_APPLICABILITIES",
    "UNIQUE_MARK_QA_MODE_DISABLED",
    "UNIQUE_MARK_QA_MODE_ENABLED",
    "UNIQUE_MARK_QA_MODE_UNKNOWN",
    "UNIQUE_MARK_QA_POLICY_VERSION",
    "UniqueMarkQAResult",
    "classify_unique_mark_qa_pipeline",
    "normalize_unique_mark_qa_state",
    "normalize_unique_mark_copy_risk",
    "resolve_unique_mark_qa_state",
    "unique_mark_qa_satisfied",
]
