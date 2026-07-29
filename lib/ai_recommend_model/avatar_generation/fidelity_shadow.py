from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .fidelity_corridor import (
    CorridorCandidate,
    CorridorMode,
    CorridorPolicy,
    IdentityPrivacySignal,
    SafeCandidateRanking,
    UNCALIBRATED_VERSION,
    attach_shadow_corridor_document,
    evaluate_fidelity_corridor,
)
from .fidelity_signals import FIDELITY_COMPONENT_KEYS, FidelitySignalBundle


@dataclass(frozen=True)
class ShadowCorridorEvidence:
    qa_document: dict[str, Any]
    candidate: CorridorCandidate


def build_shadow_corridor_evidence(
    *,
    active_qa: Mapping[str, Any],
    candidate_id: str,
    source_trait_validation: Mapping[str, Any] | None = None,
) -> ShadowCorridorEvidence:
    """Attach non-enforcing, uncalibrated corridor evidence to active QA.

    Broad fidelity remains unavailable until a separately approved adapter and
    calibration exist. Identity similarity contributes only a coarse upper
    privacy-bound signal and is never a positive ranking feature.
    """

    started_at = time.perf_counter()
    identity_signal = _identity_privacy_signal(active_qa)
    fidelity_signals = _unavailable_fidelity_signals(source_trait_validation)
    elapsed_ms = round(max(0.0, (time.perf_counter() - started_at) * 1000.0), 3)
    fidelity_signals = FidelitySignalBundle(
        bands=fidelity_signals.bands,
        model_availability=fidelity_signals.model_availability,
        model_versions=fidelity_signals.model_versions,
        timing_ms={"total": elapsed_ms},
        trait_coverage_status=fidelity_signals.trait_coverage_status,
        lower_bound_decision=fidelity_signals.lower_bound_decision,
        reason_codes=fidelity_signals.reason_codes,
        conflicting=fidelity_signals.conflicting,
    )
    decision = evaluate_fidelity_corridor(
        active_qa=active_qa,
        identity_signal=identity_signal,
        fidelity_signals=fidelity_signals,
        policy=CorridorPolicy(
            mode=CorridorMode.SHADOW,
            calibration_version=UNCALIBRATED_VERSION,
        ),
    )
    return ShadowCorridorEvidence(
        qa_document=attach_shadow_corridor_document(active_qa, decision),
        candidate=CorridorCandidate(
            candidate_id=str(candidate_id),
            decision=decision,
            fidelity_signals=fidelity_signals,
        ),
    )


def build_shadow_ranking_document(
    candidates: Sequence[CorridorCandidate],
) -> dict[str, object]:
    """Build broad-only shadow ranking evidence without changing active order."""

    document = SafeCandidateRanking().rank(candidates).to_document()
    document["mode"] = CorridorMode.SHADOW.value
    document["calibrationVersion"] = UNCALIBRATED_VERSION
    return document


def _identity_privacy_signal(active_qa: Mapping[str, Any]) -> IdentityPrivacySignal:
    debug = active_qa.get("debug")
    availability = debug.get("modelAvailability") if isinstance(debug, Mapping) else None
    face_availability = (
        str(availability.get("faceSimilarity") or "").strip().lower()
        if isinstance(availability, Mapping)
        else ""
    )
    risk_band = str(active_qa.get("identifiabilityRisk") or "").strip().lower()
    reliable = face_availability == "available" and risk_band in {"low", "medium", "high"}
    reject_reasons = {
        str(value)
        for value in active_qa.get("rejectReasons", ())
        if isinstance(value, str)
    }
    too_identifiable = bool(
        reject_reasons
        & {
            "too_identifiable",
            "source_candidate_identical",
            "source_candidate_near_duplicate",
        }
    )
    if not reliable:
        decision = "review"
    elif too_identifiable or risk_band == "high":
        decision = "reject"
    elif risk_band == "low":
        decision = "pass"
    else:
        decision = "review"
    return IdentityPrivacySignal(
        available=reliable,
        calibrated=reliable,
        upper_bound_decision=decision,
        risk_band=risk_band if reliable else "unavailable",
        model_version=str(active_qa.get("qaVersion") or "unknown"),
    )


def _unavailable_fidelity_signals(
    source_trait_validation: Mapping[str, Any] | None,
) -> FidelitySignalBundle:
    coverage = (
        source_trait_validation.get("criticalTraitCoverage")
        if isinstance(source_trait_validation, Mapping)
        else None
    )
    if isinstance(coverage, Mapping) and coverage.get("meetsMinimum") is False:
        trait_status = "mismatch"
        reasons = ("candidate_trait_mismatch", "fidelity_signal_unavailable")
    elif isinstance(coverage, Mapping) and coverage.get("meetsMinimum") is True:
        trait_status = "sufficient"
        reasons = ("fidelity_signal_unavailable",)
    else:
        trait_status = "unavailable"
        reasons = ("fidelity_signal_unavailable",)
    return FidelitySignalBundle(
        bands={
            "fidelity": "unavailable",
            "traitConsistency": "unavailable",
            "composition": "unavailable",
        },
        model_availability={
            key: "unavailable" for key in FIDELITY_COMPONENT_KEYS
        },
        trait_coverage_status=trait_status,
        lower_bound_decision="review",
        reason_codes=reasons,
    )


__all__ = [
    "ShadowCorridorEvidence",
    "build_shadow_corridor_evidence",
    "build_shadow_ranking_document",
]
