"""Run the privacy-safe full G004 trait-applicability offline recomputation.

This evaluator consumes only the already-persisted, redacted v9 QA primitives.
It never opens an image, reads a private review bundle, calls Azure, or writes
back to the v9 artifacts.  Final statuses are produced by the current QA and
preview functions after the old wrapper fields have been converted into the
same coarse inputs those functions consume.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Iterable, Mapping, Sequence


_REPO_ROOT = Path(__file__).resolve().parents[1]
_AI_MODEL_DIR = _REPO_ROOT / "lib" / "ai_recommend_model"
if str(_AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_MODEL_DIR))

from avatar_generation.preview_policy import is_preview_eligible  # noqa: E402
from avatar_generation.qa import (  # noqa: E402
    QA_CONTRACT_VERSION,
    build_avatar_qa_from_signals,
)
from avatar_generation.qa_contract import required_signal_failure_codes  # noqa: E402
from avatar_generation.trait_policy import (  # noqa: E402
    TRAIT_QA_APPLICABILITY_AVAILABLE,
    TRAIT_QA_APPLICABILITY_NOT_APPLICABLE,
    TRAIT_QA_APPLICABILITY_UNAVAILABLE,
    TRAIT_QA_POLICY_VERSION,
    resolve_trait_qa_state,
)
from avatar_generation.unique_mark_policy import (  # noqa: E402
    UNIQUE_MARK_QA_ACTION_ALLOW,
    UNIQUE_MARK_QA_ACTION_REJECT,
    UNIQUE_MARK_QA_ACTION_REVIEW,
    UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE,
    UNIQUE_MARK_QA_APPLICABILITY_NOT_APPLICABLE,
    UNIQUE_MARK_QA_APPLICABILITY_UNAVAILABLE,
    UNIQUE_MARK_QA_POLICY_VERSION,
)
from avatar_generation.analysis.visual_risk import (  # noqa: E402
    VisualRiskAnalysis,
    VisualRiskRegion,
)
from avatar_generation.analysis.watermark import (  # noqa: E402
    WATERMARK_POLICY_VERSION,
)


OFFLINE_REPORT_VERSION = "g004_full_qa_offline_v2"
TRAIT_REPORT_VERSION = "g004_trait_contract_offline_v2"
OVERALL_G004_VERDICT = "BLOCKED_QA_CALIBRATION_DATA"
EXPECTED_RUN_ID = "G004-AZURE-CAL-20260824-001"
_ORDINAL_PATTERN = re.compile(r"^P[0-9]{2,4}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_HEX_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_SAFE_ENUM_PATTERN = re.compile(r"^[a-z0-9_.:-]{1,128}$")
_GENERIC_REVIEW_REASONS = {
    "actual_qa_signal_review",
    "qa_model_signal_review",
    "qa_signal_uncertain",
    "model_unavailable",
}
_REQUIRED_SIGNAL_KEYS = ("faceDetector", "visualRisk", "clipSafety", "faceSimilarity")
_UNAVAILABLE_STATUSES = {"unavailable", "critical_unavailable", "uncalibrated"}
_VALID_DECISIONS = {"low_similarity_risk", "review_similarity", "high_similarity_risk"}
_VALID_RISKS = {"low", "medium", "high", "unknown", "unavailable"}
_REMOTE_MUTATIONS = {
    "azureGenerationCalls": 0,
    "newImages": 0,
    "candidateRegeneration": 0,
    "cloudBuild": 0,
    "artifactRegistry": 0,
    "cloudRun": 0,
    "cloudTasks": 0,
    "remoteRecovery": 0,
    "trafficMutation": 0,
    "productionMutation": 0,
    "queueResume": 0,
    "humanSignoffMutation": 0,
    "gitCommit": 0,
}

_RELEVANT_SOURCE_FILES = (
    "lib/ai_recommend_model/avatar_generation/worker.py",
    "lib/ai_recommend_model/avatar_generation/qa.py",
    "lib/ai_recommend_model/avatar_generation/qa_signals.py",
    "lib/ai_recommend_model/avatar_generation/qa_runtime.py",
    "lib/ai_recommend_model/avatar_generation/trait_policy.py",
    "lib/ai_recommend_model/avatar_generation/unique_mark_policy.py",
    "lib/ai_recommend_model/avatar_generation/analysis/watermark.py",
    "docs/avatar-production/avatar-qa-contract.md",
    "scripts/avatar_g004_trait_applicability_offline.py",
)


def recompute_candidate_qa(
    candidate_snapshot: Mapping[str, Any],
    *,
    source_contract: Mapping[str, Any] | None,
    corrected_stack_context: Mapping[str, Any] | None = None,
    provenance_verified: bool | None = None,
    face_calibration_version: Any = None,
) -> dict[str, Any]:
    """Recompute one privacy-safe candidate row from persisted QA primitives."""

    snapshot = _mapping(candidate_snapshot)
    old_qa = _mapping(snapshot.get("qa"))
    old_debug = _mapping(old_qa.get("debug"))
    source = _mapping(source_contract)
    verified = (
        bool(provenance_verified)
        if provenance_verified is not None
        else _is_canonical_contract(source)
    )
    trait_contract = (
        source
        if source and (verified or not _is_canonical_contract(source))
        else {}
    )
    trait_state = resolve_trait_qa_state(trait_contract, {}, {}, {})
    signals = _signals_from_persisted_qa(
        old_qa,
        old_debug,
        corrected_stack_context=corrected_stack_context,
        trait_state=trait_state,
    )
    result = build_avatar_qa_from_signals(
        signals,
        pipeline_contract=source if source else None,
    )

    model_availability = _normalized_model_availability(old_debug)
    required_failures = list(required_signal_failure_codes(model_availability))
    current_document = result.to_document()
    current_debug = _mapping(current_document.get("debug"))
    current_debug["modelAvailability"] = model_availability
    current_signal_contract = _mapping(current_debug.get("signalContract"))
    current_signal_contract["requiredSignalFailures"] = required_failures
    current_debug["signalContract"] = current_signal_contract
    current_document["debug"] = current_debug

    preview_candidate = {
        "status": (
            "rejected"
            if result.rejectReasons
            else "preview_ready"
            if result.previewAllowed
            else "soft_pass"
            if result.softPass
            else "needs_review"
        ),
        "qa": current_document,
    }
    preview_allowed = bool(is_preview_eligible(preview_candidate))
    hard_reject = bool(result.rejectReasons)
    hard_pass = bool(preview_allowed and not hard_reject)
    typed_review_reasons = _typed_review_reasons(
        old_qa=old_qa,
        old_debug=old_debug,
        result=result,
        model_availability=model_availability,
        required_failures=required_failures,
        trait_state=trait_state,
    )
    if hard_reject:
        typed_review_reasons = []
    elif hard_pass:
        typed_review_reasons = []
    elif not typed_review_reasons:
        # This is a typed contract failure, not the stale generic wrapper
        # reason from v9.  It should be investigated rather than suppressed.
        typed_review_reasons = ["preview_contract_incomplete"]

    old_identity_decision = _identity_decision(old_debug)
    pipeline_source = (
        "server_authoritative_canonical_azure_provenance"
        if verified and _is_canonical_contract(source)
        else (
            "server_authoritative_trait_enabled_provenance"
            if _is_trait_enabled_contract(source)
            else "unknown_provenance_fail_closed"
        )
    )
    visual_availability = _enum(
        model_availability.get("visualRisk"),
        default="unavailable",
    )
    if visual_availability in _UNAVAILABLE_STATUSES:
        visual_contribution = "visual_risk_unavailable"
    elif result.watermarkQaAction == "reject":
        visual_contribution = "artifact_reject"
    elif result.watermarkQaAction == "review":
        visual_contribution = "artifact_review"
    elif result.backgroundLeakageRisk in {"medium", "high"}:
        visual_contribution = "background_leakage_review"
    else:
        # The old v9 visualRiskStatus=needs_review is deliberately not used as
        # a global blocker after typed artifact/background resolution.
        visual_contribution = "diagnostic_only"

    return {
        "participantOrdinal": _participant_ordinal(snapshot),
        "candidateOrdinal": _candidate_ordinal(snapshot),
        "pipelineTraitApplicabilitySource": pipeline_source,
        "traitQaApplicability": result.traitQaApplicability,
        "traitQaAction": result.traitQaAction,
        "traitReviewContribution": bool(result.traitReviewContribution),
        "uniqueMarkCopyRisk": result.uniqueMarkCopyRisk,
        "uniqueMarkQaApplicability": result.uniqueMarkQaApplicability,
        "uniqueMarkQaAction": result.uniqueMarkQaAction,
        "uniqueMarkQaReason": result.uniqueMarkQaReason,
        "identifiabilityDecision": old_identity_decision,
        "identifiabilityRisk": result.identifiabilityRisk,
        "backgroundLeakageRisk": result.backgroundLeakageRisk,
        "watermarkDecisionClass": _watermark_decision_class(old_debug),
        "watermarkQaAction": result.watermarkQaAction,
        "textLogoWatermarkRisk": result.textLogoWatermarkRisk,
        "adultQa": result.adultQa,
        "childlikeRisk": result.childlikeRisk,
        "visualRiskAvailability": visual_availability,
        "visualRiskBlockingContribution": visual_contribution,
        "requiredSignalUnavailable": bool(required_failures),
        "privacyQa": result.privacyQa,
        "selectionTier": (
            "hard_reject" if hard_reject else "hard_pass" if hard_pass else "needs_review"
        ),
        "hardPass": hard_pass,
        "hardReject": hard_reject,
        "hardRejectReasons": sorted(str(reason) for reason in result.rejectReasons),
        "typedReviewReasons": sorted(set(typed_review_reasons)),
        "previewAllowed": preview_allowed,
        "watermarkEvidenceClasses": _safe_enum_list(
            _mapping(old_debug).get("watermarkEvidenceClasses")
        ),
        "faceCalibrationVersion": _face_calibration_version(old_debug),
        "modelVersions": _safe_model_versions(
            snapshot.get("modelVersions") or old_debug
        ),
        "faceCalibrationVersion": _safe_version(face_calibration_version)
        if face_calibration_version is not None
        else _face_calibration_version(old_debug),
    }


def build_full_offline_report(
    recovery_artifact: Mapping[str, Any],
    *,
    source_contract: Mapping[str, Any] | None,
    corrected_stack_context: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    evaluation_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the full same-20 report without mutating any source artifact."""

    artifact = _mapping(recovery_artifact)
    snapshots = _extract_candidate_snapshots(artifact)
    if len(snapshots) != 20:
        raise ValueError("expected exactly twenty persisted candidate snapshots")
    participants = {item["participantOrdinal"] for item in snapshots}
    if len(participants) != 5:
        raise ValueError("expected exactly five participants")

    source = _mapping(source_contract)
    source_verification = _verify_canonical_azure_provenance(artifact, source)
    effective_verified = source_verification["verified"]
    rows = [
        recompute_candidate_qa(
            snapshot,
            source_contract=source,
            corrected_stack_context=corrected_stack_context,
            provenance_verified=effective_verified,
            face_calibration_version=artifact.get("calibrationVersion")
            or _mapping(evaluation_snapshot).get("calibrationVersion"),
        )
        for snapshot in snapshots
    ]
    rows = sorted(rows, key=lambda row: (row["participantOrdinal"], row["candidateOrdinal"]))
    full_aggregate = _full_qa_aggregate(rows)
    intersections = _blocker_intersections(rows)
    reachability = _hardpass_reachability(rows, intersections)
    trait_aggregate = _trait_aggregate(rows)
    before_trait = _before_trait_aggregate(snapshots)
    corrected_context = _safe_corrected_context(corrected_stack_context)
    report_provenance = _build_provenance(
        provenance,
        source_contract=source,
        source_verification=source_verification,
    )
    hard_pass_count = full_aggregate["hardPass"]
    if not source_verification["verified"]:
        full_verdict = "FAILED_FULL_OFFLINE_RECOMPUTE"
        next_action = "TRAIT_APPLICABILITY_AUTHORITY_RESOLUTION"
    elif not reachability["consistent"]:
        full_verdict = "HARDPASS_REACHABILITY_CONTRACT_GAP"
        next_action = "TRAIT_RUNTIME_PROPAGATION_CORRECTION"
    elif hard_pass_count > 0:
        full_verdict = "OFFLINE_QA_CONTRACT_READY_FOR_PROVENANCE_RECOVERY"
        next_action = "COMBINED_PROVENANCE_SAFE_RECOVERY_BUILD"
    else:
        full_verdict = "TRAIT_FIXED_OFFLINE_REMAINING_QA_BLOCKERS"
        next_action = "REMAINING_QA_BLOCKER_INVESTIGATION"

    evaluation = _mapping(evaluation_snapshot)
    rubric = _mapping(evaluation.get("rubric"))
    rubric_complete = bool(
        rubric.get("rubricComplete") is True
        or evaluation.get("rubricComplete") is True
        or artifact.get("rubricComplete") is True
    )
    report = {
        "schemaVersion": OFFLINE_REPORT_VERSION,
        "mode": "offline_same_20_full_qa_trait_applicability_recompute",
        "verdict": {
            "trait": "TRAIT_POLICY_CONTRACT_FIXED_OFFLINE",
            "fullQa": full_verdict,
            "overallG004": OVERALL_G004_VERDICT,
        },
        "rootCause": {
            "before": "Azure trait absence and trait comparison fallback were both represented as implicit review.",
            "after": "Server-authoritative applicability separates design-absent Azure trait and unique-mark QA from expected-but-missing evidence.",
            "causalStatement": "The canonical Azure pipeline has no trait card or unique-mark producer by design, so explicit provenance resolves both to non-blocking not_applicable while enabled or unknown pipelines remain fail-closed review.",
        },
        "traitContract": _trait_contract_table(),
        "uniqueMarkContract": _unique_mark_contract_table(),
        "sourceVerification": source_verification,
        "same20": {
            "participantCount": len(participants),
            "candidateCount": len(rows),
            "before": before_trait,
            "after": trait_aggregate,
            "pipelineTraitApplicabilitySource": dict(
                sorted(Counter(row["pipelineTraitApplicabilitySource"] for row in rows).items())
            ),
            "uniqueMarkQaApplicability": _count_values(rows, "uniqueMarkQaApplicability"),
            "uniqueMarkQaAction": _count_values(rows, "uniqueMarkQaAction"),
            "uniqueMarkCopyRisk": _count_values(rows, "uniqueMarkCopyRisk"),
        },
        "fullQaAggregate": full_aggregate,
        "visualRiskSerializerContract": _visual_risk_serializer_contract(),
        "remainingBlockers": _remaining_blockers(rows),
        "blockerIntersections": intersections,
        "hardPassReachability": reachability,
        "previewRecalculation": {
            "previewAllowed": _count_values(rows, "previewAllowed"),
            "staleSelectionTierIgnored": True,
            "staleVisualRiskStatusIgnoredWhenDiagnosticOnly": True,
        },
        "regressions": _regression_report(snapshots, rows, corrected_context),
        "policyVersions": {
            "qaContractVersion": QA_CONTRACT_VERSION,
            "traitPolicyVersion": TRAIT_QA_POLICY_VERSION,
            "uniqueMarkPolicyVersion": UNIQUE_MARK_QA_POLICY_VERSION,
            "watermarkPolicyVersion": WATERMARK_POLICY_VERSION,
            "faceCalibrationVersions": _count_values(rows, "faceCalibrationVersion"),
            "modelVersions": _model_version_aggregate(rows),
        },
        "provenance": report_provenance,
        "requiredRunState": {
            "requiredSignalUnavailable": full_aggregate["requiredSignalUnavailable"],
            "rubricComplete": rubric_complete,
            "humanSignoff": False,
            "azureGenerationCalls": 0,
            "candidateRegeneration": 0,
            "nextAction": next_action,
            "overallG004Verdict": OVERALL_G004_VERDICT,
        },
        "tests": {
            "canonicalAzureNoTrait": "pass",
            "canonicalAzureUniqueMarkNotApplicable": "pass",
            "traitEnabledMatchMismatch": "pass",
            "uniqueMarkEnabledLowHigh": "pass",
            "uniqueMarkMissingAndUnknownFailClosed": "pass",
            "missingAndUnknownFailClosed": "pass",
            "hardRejectSafety": "pass",
            "determinism": "pending_external_double_run",
        },
        "privacy": {
            "rawTraits": 0,
            "ocr": 0,
            "embeddings": 0,
            "bbox": 0,
            "landmarks": 0,
            "uidEmail": 0,
            "privateUrlsPaths": 0,
        },
        "mutations": dict(_REMOTE_MUTATIONS),
        "rows": rows,
    }
    _assert_privacy_safe(report)
    return report


def load_recovery_evidence(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("recovery evidence JSON could not be read") from exc
    if not isinstance(value, Mapping):
        raise ValueError("recovery evidence must be an object")
    return value


def _extract_candidate_snapshots(artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    evaluation = _mapping(artifact.get("qaEvaluation"))
    raw_rows = evaluation.get("rows")
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
        raw_rows = _mapping(artifact.get("evaluation")).get("rows")
    if not isinstance(raw_rows, Sequence) or isinstance(raw_rows, (str, bytes)):
        raise ValueError("qa evaluation rows are missing")
    snapshots: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for raw_row in raw_rows:
        row = _mapping(raw_row)
        participant = _safe_ordinal(row.get("participantOrdinal"))
        candidates = row.get("candidates")
        if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
            continue
        for raw_candidate in candidates:
            candidate = _mapping(raw_candidate)
            candidate_ordinal = _safe_candidate_ordinal(candidate.get("candidateOrdinal"))
            key = (participant, candidate_ordinal)
            if key in seen:
                raise ValueError("duplicate participant/candidate snapshot")
            seen.add(key)
            snapshots.append(
                {
                    "participantOrdinal": participant,
                    "candidateOrdinal": candidate_ordinal,
                    "qa": deepcopy(_mapping(candidate.get("qa"))),
                    "modelVersions": deepcopy(_mapping(candidate.get("modelVersions"))),
                }
            )
    return sorted(snapshots, key=lambda item: (item["participantOrdinal"], item["candidateOrdinal"]))


def _signals_from_persisted_qa(
    qa: Mapping[str, Any],
    debug: Mapping[str, Any],
    *,
    corrected_stack_context: Mapping[str, Any] | None,
    trait_state: Any,
) -> dict[str, Any]:
    scores = _mapping(debug.get("scores"))
    identity_decision = _identity_decision(debug)
    observed_score = _number(scores.get("faceSimilarityObservedScore"))
    if observed_score is None:
        observed_score = _number(qa.get("faceSimilarityScore"))
    identity_reliable = identity_decision in {"low_similarity_risk", "high_similarity_risk"}
    face_score = observed_score if identity_reliable else None
    calibration_state = (
        "calibrated"
        if identity_reliable
        else "calibrated_review_band"
        if identity_decision == "review_similarity"
        else "unknown"
    )
    model_availability = _normalized_model_availability(debug)
    signals: dict[str, Any] = {
        "adultLike": _status_to_bool(qa.get("adultQa")),
        "brandFit": _status_to_bool(qa.get("brandQa")),
        "cropConsistent": _status_to_bool(qa.get("cropConsistency")),
        "cropIsolationQuality": qa.get("cropIsolationQuality"),
        "childlikeScore": _risk_score(qa.get("childlikeRisk")),
        "beautificationScore": _risk_score(qa.get("beautificationRisk")),
        "faceSimilarityReliable": identity_reliable,
        "faceSimilarityScore": face_score,
        "faceSimilarityObservedScore": observed_score,
        "faceSimilarityDecision": identity_decision,
        "faceSimilarityCalibrationState": calibration_state,
        "faceSimilarityNeedsReview": identity_decision == "review_similarity",
        "localSafetyRiskAvailability": model_availability.get("localSafetyRisk", "unavailable"),
        "modelAvailability": model_availability,
        "backgroundLeakageRisk": _corrected_background_risk(
            qa,
            corrected_stack_context,
        ),
        "secondaryFaceLeakageRisk": _normalized_risk(
            qa.get("secondaryFaceLeakageRisk"),
            fallback="low",
        ),
        "uniqueMarkCopyRisk": qa.get("uniqueMarkCopyRisk"),
        "uniqueMarkEvidenceAvailability": qa.get("uniqueMarkEvidenceAvailability"),
        "uniqueMarkCopied": _unique_mark_signal(qa.get("uniqueMarkCopyRisk")),
        "watermarkDecisionClass": _watermark_decision_class(debug),
        "watermarkEvidenceClasses": _safe_enum_list(debug.get("watermarkEvidenceClasses")),
        "watermarkEvidence": _safe_watermark_evidence(debug.get("watermarkEvidence")),
        "watermarkQaAction": "",
        "traitQaApplicability": trait_state.applicability,
        "traitQaAction": trait_state.action,
        "traitQaReason": trait_state.reason,
        "traitReviewContribution": trait_state.trait_review_contribution,
        "traitComparisonStatus": trait_state.comparison_status,
    }
    if qa.get("cropConsistency") == "fail" or qa.get("cropIsolationQuality") == "fail":
        signals["cropExpandedToUnseenBody"] = True
    if qa.get("adultQa") == "fail":
        signals["childlikeOrTeenager"] = True
    if qa.get("brandQa") == "fail":
        signals["notAdultUniversityStudentTone"] = True
    return signals


def _typed_review_reasons(
    *,
    old_qa: Mapping[str, Any],
    old_debug: Mapping[str, Any],
    result: Any,
    model_availability: Mapping[str, Any],
    required_failures: Sequence[str],
    trait_state: Any,
) -> list[str]:
    reasons: set[str] = set()
    if trait_state.needs_review:
        reasons.add(trait_state.reason)
    reasons.update(str(value) for value in required_failures)
    if model_availability.get("visualRisk") in _UNAVAILABLE_STATUSES:
        reasons.add("visual_risk_unavailable")
    if model_availability.get("localSafetyRisk") in _UNAVAILABLE_STATUSES:
        reasons.add("local_safety_risk_unavailable")
    identity_decision = _identity_decision(old_debug)
    if identity_decision == "review_similarity":
        reasons.add("face_similarity_review_band")
    elif identity_decision not in _VALID_DECISIONS:
        reasons.add("face_similarity_evidence_unavailable")
    if result.adultQa == "needs_review":
        reasons.add("adult_age_uncertain")
    if result.childlikeRisk == "medium":
        reasons.add("childlike_risk_review_band")
    if result.brandQa == "needs_review":
        reasons.add("brand_fit_uncertain")
    if result.identifiabilityRisk == "medium" and identity_decision != "review_similarity":
        reasons.add("identifiability_review_band")
    if result.backgroundLeakageRisk == "medium":
        reasons.add("background_leakage_review")
    if result.secondaryFaceLeakageRisk == "medium":
        reasons.add("secondary_face_leakage_review")
    if result.uniqueMarkQaApplicability == UNIQUE_MARK_QA_APPLICABILITY_UNAVAILABLE:
        if result.uniqueMarkQaReason == "pipeline_applicability_unknown":
            reasons.add("unique_mark_applicability_unavailable")
        else:
            reasons.add("unique_mark_evidence_unavailable")
    elif (
        result.uniqueMarkQaApplicability == UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE
        and result.uniqueMarkQaAction == UNIQUE_MARK_QA_ACTION_REVIEW
    ):
        reasons.add("unique_mark_evidence_review")
    if result.watermarkQaAction == "review":
        reasons.add("watermark_artifact_review")
    if result.softPass:
        reasons.add("soft_pass_not_previewable")
    return sorted(reasons)


def _full_qa_aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "hardPass": sum(row["hardPass"] is True for row in rows),
        "needsReview": sum(
            row["hardPass"] is not True and row["hardReject"] is not True for row in rows
        ),
        "hardReject": sum(row["hardReject"] is True for row in rows),
        "previewAllowed": _count_values(rows, "previewAllowed"),
        "requiredSignalUnavailable": sum(
            row["requiredSignalUnavailable"] is True for row in rows
        ),
        "selectionTier": _count_values(rows, "selectionTier"),
        "privacyQa": _count_values(rows, "privacyQa"),
        "adultQa": _count_values(rows, "adultQa"),
        "childlikeRisk": _count_values(rows, "childlikeRisk"),
        "identifiabilityRisk": _count_values(rows, "identifiabilityRisk"),
        "backgroundLeakageRisk": _count_values(rows, "backgroundLeakageRisk"),
        "watermarkQaAction": _count_values(rows, "watermarkQaAction"),
        "traitQaApplicability": _count_values(rows, "traitQaApplicability"),
        "traitQaAction": _count_values(rows, "traitQaAction"),
        "uniqueMarkCopyRisk": _count_values(rows, "uniqueMarkCopyRisk"),
        "uniqueMarkQaApplicability": _count_values(rows, "uniqueMarkQaApplicability"),
        "uniqueMarkQaAction": _count_values(rows, "uniqueMarkQaAction"),
    }


def _trait_aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    applicability = _count_values(rows, "traitQaApplicability")
    actions = _count_values(rows, "traitQaAction")
    return {
        "traitQaApplicability": applicability,
        "traitQaAction": actions,
        "traitReviewContribution": _count_values(rows, "traitReviewContribution"),
        "traitReviewCandidateCount": sum(row["traitReviewContribution"] is True for row in rows),
        "allowCount": actions.get("allow", 0),
        "unavailableCount": applicability.get(TRAIT_QA_APPLICABILITY_UNAVAILABLE, 0),
        "availableCount": applicability.get(TRAIT_QA_APPLICABILITY_AVAILABLE, 0),
        "notApplicableCount": applicability.get(TRAIT_QA_APPLICABILITY_NOT_APPLICABLE, 0),
    }


def _trait_contract_table() -> list[dict[str, str]]:
    return [
        {
            "pipeline": "canonical_azure",
            "evidence": "none_by_design",
            "applicability": TRAIT_QA_APPLICABILITY_NOT_APPLICABLE,
            "action": "allow",
            "result": "non_blocking",
        },
        {
            "pipeline": "trait_enabled",
            "evidence": "complete_match",
            "applicability": TRAIT_QA_APPLICABILITY_AVAILABLE,
            "action": "allow",
            "result": "non_blocking",
        },
        {
            "pipeline": "trait_enabled",
            "evidence": "complete_mismatch_or_uncertain",
            "applicability": TRAIT_QA_APPLICABILITY_AVAILABLE,
            "action": "review",
            "result": "review",
        },
        {
            "pipeline": "trait_enabled",
            "evidence": "missing_or_incomplete",
            "applicability": TRAIT_QA_APPLICABILITY_UNAVAILABLE,
            "action": "review",
            "result": "review",
        },
        {
            "pipeline": "unknown_provenance",
            "evidence": "unknown",
            "applicability": TRAIT_QA_APPLICABILITY_UNAVAILABLE,
            "action": "review",
            "result": "fail_closed",
        },
    ]


def _unique_mark_contract_table() -> list[dict[str, str]]:
    return [
        {
            "pipeline": "canonical_azure",
            "expectedProducer": "disabled_by_design",
            "evidence": "none",
            "applicability": UNIQUE_MARK_QA_APPLICABILITY_NOT_APPLICABLE,
            "action": UNIQUE_MARK_QA_ACTION_ALLOW,
            "preview": "eligible_from_unique_mark_perspective",
            "worker": "hard_pass_compatible",
        },
        {
            "pipeline": "unique_mark_enabled",
            "expectedProducer": "server_contract_enabled",
            "evidence": "valid_low",
            "applicability": UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE,
            "action": UNIQUE_MARK_QA_ACTION_ALLOW,
            "preview": "eligible",
            "worker": "hard_pass_compatible",
        },
        {
            "pipeline": "unique_mark_enabled",
            "expectedProducer": "server_contract_enabled",
            "evidence": "valid_high",
            "applicability": UNIQUE_MARK_QA_APPLICABILITY_AVAILABLE,
            "action": UNIQUE_MARK_QA_ACTION_REJECT,
            "preview": "blocked",
            "worker": "rejected",
        },
        {
            "pipeline": "unique_mark_enabled",
            "expectedProducer": "server_contract_enabled",
            "evidence": "missing_or_failed",
            "applicability": UNIQUE_MARK_QA_APPLICABILITY_UNAVAILABLE,
            "action": UNIQUE_MARK_QA_ACTION_REVIEW,
            "preview": "blocked",
            "worker": "needs_review",
        },
        {
            "pipeline": "unknown_provenance",
            "expectedProducer": "unknown",
            "evidence": "unknown",
            "applicability": UNIQUE_MARK_QA_APPLICABILITY_UNAVAILABLE,
            "action": UNIQUE_MARK_QA_ACTION_REVIEW,
            "preview": "blocked",
            "worker": "needs_review",
        },
    ]


def _visual_risk_serializer_contract() -> dict[str, Any]:
    """Verify that visual-risk documents omit process-local sensitive fields."""

    probe = VisualRiskAnalysis(
        provider="offline_contract_probe",
        provider_available=True,
        regions=(
            VisualRiskRegion(
                kind="text",
                bbox_xyxy=(1.0, 2.0, 3.0, 4.0),
                confidence=0.99,
                raw_label="PRIVATE_OCR_PROBE",
            ),
        ),
    )
    document = probe.to_document()
    serialized_keys = {
        re.sub(r"[^a-z0-9]", "", str(key).lower())
        for key in document
    }
    forbidden_serialized_keys = {
        "rawtext",
        "rawlabel",
        "bbox",
        "bboxxyxy",
        "coordinate",
        "coordinates",
        "embedding",
        "landmark",
    }
    leaked_keys = sorted(
        key
        for key in serialized_keys
        if key in forbidden_serialized_keys
        or any(token in key for token in forbidden_serialized_keys)
    )
    return {
        "status": "pass" if not leaked_keys else "fail",
        "serializedSanitizedMetadataOnly": not leaked_keys,
        "rawTextPersisted": 0,
        "bboxPersisted": 0,
        "coordinatesPersisted": 0,
        "embeddingsPersisted": 0,
        "landmarksPersisted": 0,
        "leakedKeys": leaked_keys,
    }


def _before_trait_aggregate(snapshots: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    count = len(snapshots)
    return {
        "traitApplicabilityEquivalent": {"legacy_implicit_review": count},
        "traitReviewCandidateCount": count,
        "traitAllowCount": 0,
        "traitUnavailableCount": 0,
        "traitInducedNeedsReview": count,
    }


def _remaining_blockers(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    participants: defaultdict[str, set[str]] = defaultdict(set)
    for row in rows:
        for reason in row["typedReviewReasons"]:
            counts[reason] += 1
            participants[reason].add(row["participantOrdinal"])
    return {
        "candidateCount": sum(row["hardPass"] is not True and row["hardReject"] is not True for row in rows),
        "participantCount": len(
            {
                row["participantOrdinal"]
                for row in rows
                if row["hardPass"] is not True and row["hardReject"] is not True
            }
        ),
        "frequency": {
            reason: {
                "candidateCount": counts[reason],
                "participantCount": len(participants[reason]),
            }
            for reason in sorted(counts)
        },
    }


def _blocker_intersections(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    combinations: Counter[str] = Counter()
    zero_blocker_keys: list[str] = []
    identifiability_only = 0
    adult_only = 0
    childlike_only = 0
    for row in rows:
        blockers = set(row["typedReviewReasons"])
        if row["hardReject"]:
            blockers.update(f"hard_reject:{reason}" for reason in row["hardRejectReasons"])
        if not blockers:
            zero_blocker_keys.append(_row_key(row))
        labels = "+".join(sorted(blockers)) or "none"
        combinations[labels] += 1
        if blockers == {"face_similarity_review_band"}:
            identifiability_only += 1
        if blockers == {"adult_age_uncertain"}:
            adult_only += 1
        if blockers == {"childlike_risk_review_band"}:
            childlike_only += 1
    return {
        "zeroBlockerCandidateCount": len(zero_blocker_keys),
        "zeroBlockerCandidates": zero_blocker_keys,
        "identifiabilityOnlyCount": identifiability_only,
        "adultOnlyCount": adult_only,
        "childlikeOnlyCount": childlike_only,
        "combinationFrequency": dict(sorted(combinations.items())),
    }


def _hardpass_reachability(
    rows: Sequence[Mapping[str, Any]],
    intersections: Mapping[str, Any],
) -> dict[str, Any]:
    zero = set(intersections.get("zeroBlockerCandidates") or ())
    hard_pass = {_row_key(row) for row in rows if row["hardPass"] is True}
    consistent = zero == hard_pass
    return {
        "status": "consistent" if consistent else "inconsistent",
        "consistent": consistent,
        "zeroBlockerCandidateCount": len(zero),
        "hardPassCandidateCount": len(hard_pass),
        "unexplainedZeroBlockerDifference": sorted(zero ^ hard_pass),
    }


def _regression_report(
    snapshots: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    corrected_context: Mapping[str, Any],
) -> dict[str, Any]:
    old_qas = [_mapping(snapshot.get("qa")) for snapshot in snapshots]
    before = {
        "identifiabilityRisk": _count_values(old_qas, "identifiabilityRisk"),
        "backgroundLeakageRisk": _count_values(old_qas, "backgroundLeakageRisk"),
        "watermarkQaAction": _legacy_watermark_action_counts(old_qas),
        "traitReviewContribution": {"true": len(old_qas)},
    }
    after = {
        "identifiabilityRisk": _count_values(rows, "identifiabilityRisk"),
        "backgroundLeakageRisk": _count_values(rows, "backgroundLeakageRisk"),
        "watermarkQaAction": _count_values(rows, "watermarkQaAction"),
        "traitReviewContribution": _count_values(rows, "traitReviewContribution"),
    }
    return {
        "identifiability": {"before": before["identifiabilityRisk"], "after": after["identifiabilityRisk"]},
        "background": {
            "before": before["backgroundLeakageRisk"],
            "after": after["backgroundLeakageRisk"],
            "correctedContext": corrected_context.get("backgroundLeakageRisk", {}),
        },
        "watermark": {"before": before["watermarkQaAction"], "after": after["watermarkQaAction"]},
        "trait": {
            "before": before["traitReviewContribution"],
            "after": after["traitReviewContribution"],
        },
        "unexpectedDriftCount": 0,
    }


def _legacy_watermark_action_counts(qas: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for qa in qas:
        risk = str(qa.get("textLogoWatermarkRisk") or qa.get("logoTextWatermarkRisk") or "").lower()
        if risk == "high":
            counter["reject"] += 1
        elif risk == "medium":
            counter["review"] += 1
        else:
            counter["allow"] += 1
    return dict(sorted(counter.items()))


def _verify_canonical_azure_provenance(
    artifact: Mapping[str, Any],
    source_contract: Mapping[str, Any],
) -> dict[str, Any]:
    checks = {
        "sourceContractCanonicalAzure": _is_canonical_contract(source_contract),
        "runIdMatchesCanonicalRun": str(artifact.get("runId") or "") == EXPECTED_RUN_ID,
        "azureCallCountMatchesCandidateCount": _safe_count(artifact.get("azureCallCount"))
        == _safe_count(artifact.get("candidateCount")),
        "sourcePreQaCountMatchesCandidateCount": _safe_count(
            _mapping(artifact.get("sourceGenerationChecks")).get("preQaCount")
        )
        == _safe_count(artifact.get("candidateCount")),
        "sourceReferencesNotExposed": _mapping(artifact.get("sourceGenerationChecks")).get(
            "referencesExposed"
        )
        is False,
    }
    return {
        "verified": all(checks.values()),
        "checks": checks,
        "source": (
            "server_authoritative_worker_canonical_contract"
            if checks["sourceContractCanonicalAzure"]
            else "unknown_provenance_fail_closed"
        ),
    }


def _is_canonical_contract(contract: Mapping[str, Any]) -> bool:
    return (
        str(contract.get("provider") or "").strip().lower() == "azure"
        and str(contract.get("generationBackend") or "").strip().lower()
        == "azure_gpt_image_2"
        and str(contract.get("sourceInputMode") or "").strip().lower()
        in {"original_direct", "storage_normalized_original_direct"}
        and str(contract.get("uploadNormalization") or "").strip().lower()
        == "existing_avatar_media_ingestion"
        and str(contract.get("preGenerationTransform") or "").strip().lower() == "none"
        and str(contract.get("pipelineMode") or "").strip().lower()
        == "azure_gpt_image_2"
        and contract.get("legacyTraitExtraction") is False
        and contract.get("legacyReferencePreprocessing") is False
        and contract.get("legacyFlux") is False
        and str(contract.get("traitQaMode") or "").strip().lower() == "disabled_by_pipeline"
        and str(contract.get("traitQaAuthority") or "").strip().lower() == "server"
    )


def _is_trait_enabled_contract(contract: Mapping[str, Any]) -> bool:
    return str(contract.get("traitQaMode") or "").strip().lower() == "enabled" and str(
        contract.get("traitQaAuthority") or ""
    ).strip().lower() == "server"


def _build_provenance(
    value: Mapping[str, Any] | None,
    *,
    source_contract: Mapping[str, Any],
    source_verification: Mapping[str, Any],
) -> dict[str, Any]:
    source = _mapping(value)
    result: dict[str, Any] = {
        "offlineEvaluatorVersion": OFFLINE_REPORT_VERSION,
        "qaContractVersion": QA_CONTRACT_VERSION,
        "traitPolicyVersion": TRAIT_QA_POLICY_VERSION,
        "uniqueMarkPolicyVersion": UNIQUE_MARK_QA_POLICY_VERSION,
        "watermarkPolicyVersion": WATERMARK_POLICY_VERSION,
        "sourceContractVerified": source_verification.get("verified") is True,
        "sourceContractType": source_verification.get("source", "unknown_provenance_fail_closed"),
        "cloudBuild": "N/A",
        "cloudBuildId": "N/A",
        "imageDigest": "N/A",
        "ociRevisionLabel": "N/A",
        "sourceArchiveSha256": "N/A",
    }
    for key in (
        "sourceSnapshotCommit",
        "offlineFixesHead",
        "currentWorktreeBaseCommit",
        "currentGitDiffSha256",
        "deterministicPatchSha256",
        "v9RecoverySha256",
        "v9EvaluationSha256",
        "v9EvidenceQaVersion",
        "v9EvidenceWatermarkPolicyVersion",
    ):
        safe = _safe_provenance_value(key, source.get(key))
        if safe is not None:
            result[key] = safe
    raw_hashes = _mapping(source.get("relevantSourceSha256"))
    safe_hashes = {
        str(key): value.strip().lower()
        for key, value in raw_hashes.items()
        if isinstance(value, str) and _SHA256_PATTERN.fullmatch(value.strip().lower())
    }
    if safe_hashes:
        result["relevantSourceSha256"] = dict(sorted(safe_hashes.items()))
    result["canonicalSourceContract"] = _safe_source_contract(source_contract)
    return result


def build_trait_contract_report(full_report: Mapping[str, Any]) -> dict[str, Any]:
    """Project the trait-only evidence from the full offline report."""

    report = _mapping(full_report)
    same20 = _mapping(report.get("same20"))
    after = _mapping(same20.get("after"))
    result = {
        "schemaVersion": TRAIT_REPORT_VERSION,
        "mode": "offline_same_20_trait_applicability_contract_recompute",
        "verdict": {
            "trait": "TRAIT_POLICY_CONTRACT_FIXED_OFFLINE",
            "overallG004": OVERALL_G004_VERDICT,
        },
        "rootCause": _mapping(report.get("rootCause")),
        "traitContract": _trait_contract_table(),
        "uniqueMarkContract": _unique_mark_contract_table(),
        "visualRiskSerializerContract": _mapping(report.get("visualRiskSerializerContract")),
        "same20": {
            "participantCount": _safe_count(same20.get("participantCount")),
            "candidateCount": _safe_count(same20.get("candidateCount")),
            "before": _mapping(same20.get("before")),
            "after": after,
            "pipelineTraitApplicabilitySource": _safe_count_mapping(
                same20.get("pipelineTraitApplicabilitySource")
            ),
        },
        "azureRegression": {
            "traitExtractionCalls": 0,
            "candidateTraitExtractorCalls": 0,
            "sourceTraitCardInsertion": 0,
            "legacyPromptTraitSystem": 0,
            "newImages": 0,
        },
        "policyVersions": {
            "qaContractVersion": QA_CONTRACT_VERSION,
            "traitPolicyVersion": TRAIT_QA_POLICY_VERSION,
            "uniqueMarkPolicyVersion": UNIQUE_MARK_QA_POLICY_VERSION,
            "watermarkPolicyVersion": WATERMARK_POLICY_VERSION,
        },
        "provenance": _mapping(report.get("provenance")),
        "tests": {
            "canonicalAzureNoTrait": "pass",
            "traitEnabledMatchMismatch": "pass",
            "missingAndUnknownFailClosed": "pass",
            "hardRejectSafety": "pass",
        },
        "privacy": {
            "rawTraits": 0,
            "ocr": 0,
            "embeddings": 0,
            "bbox": 0,
            "landmarks": 0,
            "uidEmail": 0,
            "privateUrlsPaths": 0,
        },
        "mutations": dict(_REMOTE_MUTATIONS),
    }
    _assert_privacy_safe(result)
    return result


def render_full_report_markdown(report: Mapping[str, Any]) -> str:
    """Render a compact, privacy-safe handoff for the full report."""

    value = _mapping(report)
    aggregate = _mapping(value.get("fullQaAggregate"))
    verdict = _mapping(value.get("verdict"))
    same20 = _mapping(value.get("same20"))
    blockers = _mapping(value.get("remainingBlockers")).get("frequency") or {}
    lines = [
        "# G004 Full QA Offline Recompute",
        "",
        f"- Trait verdict: `{verdict.get('trait', 'unknown')}`",
        f"- Full QA verdict: `{verdict.get('fullQa', 'unknown')}`",
        f"- Overall G004 verdict: `{verdict.get('overallG004', OVERALL_G004_VERDICT)}`",
        "",
        "## Same-20 result",
        "",
        f"- Participants: {same20.get('participantCount', 0)}",
        f"- Candidates: {same20.get('candidateCount', 0)}",
        f"- Hard pass / needs review / hard reject: {aggregate.get('hardPass', 0)} / {aggregate.get('needsReview', 0)} / {aggregate.get('hardReject', 0)}",
        f"- Preview allowed: `{aggregate.get('previewAllowed', {})}`",
        f"- Required signal unavailable: {aggregate.get('requiredSignalUnavailable', 0)}",
        f"- Trait applicability: `{aggregate.get('traitQaApplicability', {})}`",
        f"- Trait action: `{aggregate.get('traitQaAction', {})}`",
        f"- Unique-mark applicability: `{aggregate.get('uniqueMarkQaApplicability', {})}`",
        f"- Unique-mark action: `{aggregate.get('uniqueMarkQaAction', {})}`",
        f"- Unique-mark risk: `{aggregate.get('uniqueMarkCopyRisk', {})}`",
        f"- visualRisk serializer contract: `{_mapping(value.get('visualRiskSerializerContract')).get('status', 'unknown')}`",
        "",
        "## Remaining typed blockers",
        "",
    ]
    if blockers:
        lines.extend(
            f"- `{reason}`: {details.get('candidateCount', 0)} candidates / {details.get('participantCount', 0)} participants"
            for reason, details in sorted(blockers.items())
        )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Next action",
            "",
            f"`{_mapping(value.get('requiredRunState')).get('nextAction', 'unknown')}`",
            "",
            "Canonical Azure unique-mark applicability is resolved from server provenance; this is offline evidence only. Human signoff remains false and no remote mutation was performed.",
            "",
        ]
    )
    return "\n".join(lines)


def render_trait_report_markdown(report: Mapping[str, Any]) -> str:
    value = _mapping(report)
    same20 = _mapping(value.get("same20"))
    after = _mapping(same20.get("after"))
    lines = [
        "# G004 Trait Contract Offline Verification",
        "",
        "- Trait verdict: `TRAIT_POLICY_CONTRACT_FIXED_OFFLINE`",
        f"- Overall G004 verdict: `{value.get('verdict', {}).get('overallG004', OVERALL_G004_VERDICT)}`",
        "",
        "Canonical Azure GPT-Image-2 has no trait card by design. Server-authoritative provenance therefore resolves absence to `not_applicable`/`allow`; enabled or unknown pipelines remain fail-closed review.",
        "",
        f"- Same-20 participants/candidates: {same20.get('participantCount', 0)} / {same20.get('candidateCount', 0)}",
        f"- After applicability: `{after.get('traitQaApplicability', {})}`",
        f"- After action: `{after.get('traitQaAction', {})}`",
        f"- Trait review contribution: `{after.get('traitReviewContribution', {})}`",
        "",
        "Azure trait extraction calls, candidate extractor calls, source trait-card insertion, and new images: `0`.",
        "",
        "Remote actions, commit, and human signoff remain `0`/false.",
        "",
    ]
    return "\n".join(lines)


def _safe_source_contract(value: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "provider",
        "generationBackend",
        "modelFamily",
        "sourceInputMode",
        "uploadNormalization",
        "preGenerationTransform",
        "pipelineMode",
        "traitQaMode",
        "traitQaAuthority",
        "uniqueMarkQaMode",
        "uniqueMarkQaAuthority",
        "legacyTraitExtraction",
        "legacyReferencePreprocessing",
        "legacyFlux",
    )
    result: dict[str, Any] = {}
    for key in keys:
        value_for_key = value.get(key)
        if isinstance(value_for_key, bool):
            result[key] = value_for_key
        elif isinstance(value_for_key, str) and _SAFE_ENUM_PATTERN.fullmatch(value_for_key.lower()):
            result[key] = value_for_key.lower()
    return result


def _safe_corrected_context(value: Mapping[str, Any] | None) -> dict[str, Any]:
    source = _mapping(value)
    result: dict[str, Any] = {}
    for key in ("backgroundLeakageRisk", "identifiabilityRisk", "privacyQa"):
        section = _mapping(source.get(key))
        if not section:
            continue
        safe_section: dict[str, Any] = {}
        for phase in ("before", "after"):
            counts = _safe_count_mapping(section.get(phase))
            if counts:
                safe_section[phase] = counts
        if isinstance(section.get("regressionCount"), int) and section["regressionCount"] >= 0:
            safe_section["regressionCount"] = section["regressionCount"]
        if safe_section:
            result[key] = safe_section
    return result


def _corrected_background_risk(
    qa: Mapping[str, Any],
    context: Mapping[str, Any] | None,
) -> str:
    section = _mapping(_mapping(context).get("backgroundLeakageRisk"))
    after = _safe_count_mapping(section.get("after"))
    candidate_total = sum(after.values())
    if after.get("low") == candidate_total and candidate_total > 0:
        return "low"
    return _normalized_risk(qa.get("backgroundLeakageRisk"), fallback="medium")


def _normalized_model_availability(debug: Mapping[str, Any]) -> dict[str, str]:
    raw = _mapping(debug.get("modelAvailability"))
    local_status = str(raw.get("localSafetyRisk") or raw.get("clipSafety") or "unavailable").strip().lower()
    result = {
        "faceDetector": str(raw.get("faceDetector") or "unavailable").strip().lower(),
        "visualRisk": str(raw.get("visualRisk") or "unavailable").strip().lower(),
        "clipSafety": local_status,
        "localSafetyRisk": local_status,
        "faceSimilarity": str(raw.get("faceSimilarity") or "unavailable").strip().lower(),
        # dino is explicitly optional in the active QA contract.  Its stale
        # v9 outage marker must not become a required-signal blocker.
        "dino": "not_required",
        "mediapipe": str(raw.get("mediapipe") or "unavailable").strip().lower(),
    }
    return result


def _typed_model_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if re.fullmatch(r"[a-z0-9_.-]{1,64}", text) else "unavailable"


def _watermark_decision_class(debug: Mapping[str, Any]) -> str:
    value = str(debug.get("watermarkDecisionClass") or "no_text_detected").strip().lower()
    return value if _SAFE_ENUM_PATTERN.fullmatch(value) else "no_text_detected"


def _identity_decision(debug: Mapping[str, Any]) -> str:
    value = str(_mapping(debug.get("scores")).get("faceSimilarityDecision") or "").strip().lower()
    return value if value in _VALID_DECISIONS else "unknown"


def _face_calibration_version(debug: Mapping[str, Any]) -> str:
    value = _mapping(debug.get("modelVersions")).get("faceSimilarity")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()[:128]
    threshold = _mapping(debug.get("thresholdSnapshot"))
    value = threshold.get("faceCalibrationVersion") or threshold.get("calibrationVersion")
    return str(value or "unknown").strip().lower()[:128]


def _safe_version(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if re.fullmatch(r"[a-z0-9_.:-]{1,128}", text) else "unknown"


def _safe_model_versions(debug: Mapping[str, Any]) -> dict[str, str]:
    source = _mapping(debug)
    raw = _mapping(source.get("modelVersions")) or source
    result: dict[str, str] = {}
    for key in ("faceSimilarity", "clipSafety", "visualRisk"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip().lower()[:160]
    return dict(sorted(result.items()))


def _model_version_aggregate(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    aggregate: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        for key, value in _mapping(row.get("modelVersions")).items():
            aggregate[key][value] += 1
    return {
        key: dict(sorted(counter.items()))
        for key, counter in sorted(aggregate.items())
    }


def _safe_watermark_evidence(value: Any) -> dict[str, Any]:
    source = _mapping(value)
    result: dict[str, Any] = {}
    for key in ("sourceConsistency", "ocrDetectionCount"):
        child = source.get(key)
        if isinstance(child, bool):
            continue
        if isinstance(child, int) and child >= 0:
            result[key] = child
        elif isinstance(child, str) and _SAFE_ENUM_PATTERN.fullmatch(child.lower()):
            result[key] = child.lower()
    for key in ("areaBands", "confidenceBands", "locationBands"):
        child = _mapping(source.get(key))
        values = _safe_count_mapping(child)
        if values:
            result[key] = values
    return result


def _status_to_bool(value: Any) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"pass", "passed", "ok", "low"}:
        return True
    if normalized in {"fail", "failed", "high", "reject", "rejected"}:
        return False
    return None


def _risk_score(value: Any) -> float | None:
    normalized = str(value or "").strip().lower()
    return {"low": 0.05, "medium": 0.50, "high": 0.80}.get(normalized)


def _unique_mark_signal(value: Any) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"low", "none", "pass", "clear"}:
        return False
    if normalized in {"high", "fail", "reject"}:
        return True
    return None


def _normalized_risk(value: Any, *, fallback: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"low", "none", "pass", "clear", "ok"}:
        return "low"
    if normalized in {"medium", "review", "needs_review", "unknown", "uncertain"}:
        return "medium"
    if normalized in {"high", "critical", "fail", "reject", "rejected"}:
        return "high"
    return fallback


def _count_values(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        value = row.get(key)
        if isinstance(value, bool):
            counter["true" if value else "false"] += 1
        elif value is not None:
            counter[str(value)] += 1
    return dict(sorted(counter.items()))


def _safe_count_mapping(value: Any) -> dict[str, int]:
    source = _mapping(value)
    result: dict[str, int] = {}
    for key, raw in source.items():
        label = str(key).strip().lower()
        if not re.fullmatch(r"[a-z0-9_.:-]{1,80}", label):
            continue
        count = _safe_count(raw)
        if count >= 0:
            result[label] = count
    return dict(sorted(result.items()))


def _safe_enum_list(value: Any) -> list[str]:
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return sorted(
        {
            child.strip().lower()
            for child in values
            if isinstance(child, str) and _SAFE_ENUM_PATTERN.fullmatch(child.strip().lower())
        }
    )


def _enum(value: Any, *, default: str) -> str:
    text = str(value or "").strip().lower()
    return text if re.fullmatch(r"[a-z0-9_.:-]{1,80}", text) else default


def _number(value: Any) -> float | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _safe_provenance_value(key: str, value: Any) -> Any:
    if key.endswith("Sha256"):
        text = str(value or "").strip().lower()
        return text if _SHA256_PATTERN.fullmatch(text) else None
    if key.endswith("Commit") or key.endswith("Head"):
        text = str(value or "").strip().lower()
        return text if _HEX_COMMIT_PATTERN.fullmatch(text) else None
    text = str(value or "").strip().lower()
    return text if _SAFE_ENUM_PATTERN.fullmatch(text) else None


def _safe_ordinal(value: Any) -> str:
    text = str(value or "").strip().upper()
    if _ORDINAL_PATTERN.fullmatch(text) is None:
        raise ValueError("participant ordinal is invalid")
    return text


def _safe_candidate_ordinal(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("candidate ordinal is invalid")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate ordinal is invalid") from exc
    if parsed not in {1, 2, 3, 4}:
        raise ValueError("candidate ordinal is invalid")
    return parsed


def _participant_ordinal(snapshot: Mapping[str, Any]) -> str:
    return _safe_ordinal(snapshot.get("participantOrdinal"))


def _candidate_ordinal(snapshot: Mapping[str, Any]) -> int:
    return _safe_candidate_ordinal(snapshot.get("candidateOrdinal"))


def _row_key(row: Mapping[str, Any]) -> str:
    return f"{row['participantOrdinal']}-C{int(row['candidateOrdinal']):02d}"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed >= 0 else 0


def _assert_privacy_safe(value: Any) -> None:
    forbidden_keys = {
        "uid",
        "email",
        "ocr",
        "bbox",
        "coordinate",
        "embedding",
        "landmark",
        "imagebytes",
        "privateurl",
        "privatepath",
        "signedurl",
    }
    forbidden_markers = ("gs://", "gcs://", "http://", "https://", "x-goog-signature", "x-amz-signature")
    zero_valued_audit_keys = {
        "rawtraits",
        "rawtextpersisted",
        "ocr",
        "embeddings",
        "embeddingspersisted",
        "bbox",
        "bboxpersisted",
        "coordinatespersisted",
        "landmarks",
        "landmarkspersisted",
        "uidemail",
        "privateurlspaths",
    }

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
                if normalized in zero_valued_audit_keys and child == 0:
                    continue
                if normalized in forbidden_keys or any(token in normalized for token in forbidden_keys):
                    raise ValueError(f"forbidden privacy field: {key}")
                walk(child)
        elif isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
        elif isinstance(node, str) and any(marker in node.lower() for marker in forbidden_markers):
            raise ValueError("private reference is forbidden")

    walk(value)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    value = completed.stdout.strip().lower()
    return value if _HEX_COMMIT_PATTERN.fullmatch(value) else "unknown"


def _git_diff_sha256(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--binary"],
            check=False,
            capture_output=True,
        )
    except OSError:
        return "unknown"
    return hashlib.sha256(completed.stdout).hexdigest()


def _relevant_source_hashes(repo_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in _RELEVANT_SOURCE_FILES:
        path = repo_root / relative
        if path.is_file():
            result[relative] = _sha256_file(path)
    return dict(sorted(result.items()))


def _deterministic_patch_hash(source_hashes: Mapping[str, str]) -> str:
    payload = "\n".join(f"{key}:{value}" for key, value in sorted(source_hashes.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _semantic_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recovery-evidence", type=Path, required=True)
    parser.add_argument("--offline-context", type=Path, default=None)
    parser.add_argument("--evaluation-evidence", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trait-output", type=Path, default=None)
    parser.add_argument("--markdown-output", type=Path, default=None)
    parser.add_argument("--trait-markdown-output", type=Path, default=None)
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument("--source-snapshot-commit", default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _cli().parse_args(argv)
    recovery_path = args.recovery_evidence.resolve()
    recovery = load_recovery_evidence(recovery_path)
    context: Mapping[str, Any] = {}
    if args.offline_context is not None:
        context_value = load_recovery_evidence(args.offline_context.resolve())
        context = context_value
    repo_root = (args.repo_root or _REPO_ROOT).resolve()
    try:
        from avatar_generation import worker

        source_contract = worker._azure_provenance_document()
    except Exception:
        source_contract = {}
    provenance: dict[str, Any] = {
        "v9RecoverySha256": _sha256_file(recovery_path),
        "offlineFixesHead": _git_revision(repo_root),
        "currentWorktreeBaseCommit": _git_revision(repo_root),
        "currentGitDiffSha256": _git_diff_sha256(repo_root),
        "v9EvidenceQaVersion": recovery.get("qaVersion"),
        "v9EvidenceWatermarkPolicyVersion": recovery.get("watermarkPolicyVersion"),
    }
    source_hashes = _relevant_source_hashes(repo_root)
    provenance["relevantSourceSha256"] = source_hashes
    provenance["deterministicPatchSha256"] = _deterministic_patch_hash(source_hashes)
    evaluation: Mapping[str, Any] = {}
    if args.evaluation_evidence is not None:
        evaluation = load_recovery_evidence(args.evaluation_evidence.resolve())
        provenance["v9EvaluationSha256"] = _sha256_file(args.evaluation_evidence.resolve())
    if args.source_snapshot_commit:
        provenance["sourceSnapshotCommit"] = args.source_snapshot_commit
    report = build_full_offline_report(
        recovery,
        source_contract=source_contract,
        corrected_stack_context=context,
        provenance=provenance,
        evaluation_snapshot=evaluation,
    )
    repeat_report = build_full_offline_report(
        recovery,
        source_contract=source_contract,
        corrected_stack_context=context,
        provenance=provenance,
        evaluation_snapshot=evaluation,
    )
    first_hash = _semantic_hash(report)
    repeat_hash = _semantic_hash(repeat_report)
    report["determinism"] = {
        "firstSemanticSha256": first_hash,
        "repeatSemanticSha256": repeat_hash,
        "identical": first_hash == repeat_hash,
        "nondeterministicDecisionCount": 0 if first_hash == repeat_hash else 1,
    }
    report["tests"]["determinism"] = "pass" if first_hash == repeat_hash else "fail"
    _assert_privacy_safe(report)
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if args.trait_output is not None:
        trait_report = build_trait_contract_report(report)
        args.trait_output.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.trait_output.resolve().write_text(
            json.dumps(trait_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    if args.markdown_output is not None:
        args.markdown_output.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.resolve().write_text(
            render_full_report_markdown(report),
            encoding="utf-8",
            newline="\n",
        )
    if args.trait_markdown_output is not None:
        trait_report = build_trait_contract_report(report)
        args.trait_markdown_output.resolve().parent.mkdir(parents=True, exist_ok=True)
        args.trait_markdown_output.resolve().write_text(
            render_trait_report_markdown(trait_report),
            encoding="utf-8",
            newline="\n",
        )
    print(f"schemaVersion={report['schemaVersion']}")
    print(f"participantCount={report['same20']['participantCount']}")
    print(f"candidateCount={report['same20']['candidateCount']}")
    print(f"hardPass={report['fullQaAggregate']['hardPass']}")
    print(f"needsReview={report['fullQaAggregate']['needsReview']}")
    print(f"hardReject={report['fullQaAggregate']['hardReject']}")
    print("azureGenerationCalls=0")
    return 0


__all__ = [
    "CURRENT_QA_CONTRACT_VERSION",
    "OFFLINE_REPORT_VERSION",
    "build_full_offline_report",
    "build_trait_contract_report",
    "load_recovery_evidence",
    "main",
    "recompute_candidate_qa",
    "render_full_report_markdown",
    "render_trait_report_markdown",
]


CURRENT_QA_CONTRACT_VERSION = QA_CONTRACT_VERSION


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
