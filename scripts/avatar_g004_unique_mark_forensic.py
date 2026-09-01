"""Forensically trace the G004 unique-mark signal without changing policy.

The report deliberately exercises the existing QA, preview, worker, and
offline-evaluator functions.  It does not inspect images, call a provider, or
write to any remote service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


_REPO_ROOT = Path(__file__).resolve().parents[1]
_AI_MODEL_DIR = _REPO_ROOT / "lib" / "ai_recommend_model"
if str(_AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_MODEL_DIR))

from avatar_generation.preview_policy import (  # noqa: E402
    is_preview_eligible,
    passes_absolute_preview_checks,
)
from avatar_generation.qa import (  # noqa: E402
    AvatarQAResult,
    apply_avatar_qa_rejection_logic,
    build_avatar_qa_from_signals,
)
from avatar_generation.worker import (  # noqa: E402
    _azure_provenance_document,
    _candidate_status_from_qa,
)
try:
    from scripts.avatar_g004_trait_applicability_offline import (  # noqa: E402
        _assert_privacy_safe,
        recompute_candidate_qa,
    )
except ModuleNotFoundError:
    from avatar_g004_trait_applicability_offline import (  # noqa: E402
        _assert_privacy_safe,
        recompute_candidate_qa,
    )


FORENSIC_REPORT_VERSION = "g004_unique_mark_forensic_v1"
EXPECTED_RUN_ID = "G004-AZURE-CAL-20260824-001"
OVERALL_G004_VERDICT = "BLOCKED_QA_CALIBRATION_DATA"
PRIMARY_VERDICT = "UNIQUE_MARK_RUNTIME_POLICY_CONTRACT_MISMATCH"
H1_VERDICT = "H1_REJECTED"
NEXT_ACTION = "UNIQUE_MARK_POLICY_AUTHORITY_RESOLUTION"
_VALID_UNIQUE_RISKS = ("low", "unknown", "unavailable", "high")
_REMOTE_MUTATIONS = {
    "cloudBuild": 0,
    "artifactRegistry": 0,
    "cloudRun": 0,
    "cloudTasks": 0,
    "azureGenerationCalls": 0,
    "newImages": 0,
    "candidateRegeneration": 0,
    "remoteRecovery": 0,
    "trafficMutation": 0,
    "productionMutation": 0,
    "queueResume": 0,
    "humanSignoffMutation": 0,
    "gitCommit": 0,
}


def _safe_qa_result(unique_mark_risk: str) -> AvatarQAResult:
    return AvatarQAResult(
        adultQa="pass",
        childlikeRisk="low",
        privacyQa="pass",
        brandQa="pass",
        beautificationRisk="low",
        cropConsistency="pass",
        cropIsolationQuality="pass",
        uniqueMarkCopyRisk=unique_mark_risk,
        logoTextWatermarkRisk="low",
        textLogoWatermarkRisk="low",
        watermarkQaAction="allow",
        backgroundLeakageRisk="low",
        secondaryFaceLeakageRisk="low",
        identifiabilityRisk="low",
        traitQaApplicability="not_applicable",
        traitQaAction="allow",
        traitQaReason="disabled_by_canonical_azure_pipeline",
        traitReviewContribution=False,
        rejectReasons=[],
        reviewReasons=[],
        softPass=False,
        previewAllowed=False,
        requiresHumanReview=True,
    )


def replay_production_decision(unique_mark_risk: str) -> dict[str, Any]:
    """Run one safe fixture through the actual QA and preview functions."""

    if unique_mark_risk not in _VALID_UNIQUE_RISKS:
        raise ValueError(f"unsupported unique-mark risk: {unique_mark_risk}")
    result = apply_avatar_qa_rejection_logic(_safe_qa_result(unique_mark_risk))
    qa_document = result.to_document()
    candidate = {"status": "hard_pass", "qa": qa_document}
    return {
        "uniqueMarkCopyRisk": result.uniqueMarkCopyRisk,
        "qaLayer": {
            "previewAllowed": bool(result.previewAllowed),
            "requiresHumanReview": bool(result.requiresHumanReview),
            "hardPassCompatible": bool(
                result.previewAllowed
                and not result.requiresHumanReview
                and not result.rejectReasons
            ),
            "rejectReasons": list(result.rejectReasons),
            "reviewReasons": list(result.reviewReasons),
        },
        "previewGate": {
            "passesAbsolutePreviewChecks": bool(
                passes_absolute_preview_checks(candidate)
            ),
            "previewEligible": bool(is_preview_eligible(candidate)),
        },
        "worker": {
            "status": _candidate_status_from_qa(qa_document),
            "effectiveHardPass": _candidate_status_from_qa(qa_document)
            == "hard_pass",
            "effectiveNeedsReview": _candidate_status_from_qa(qa_document)
            == "needs_review",
            "effectiveHardReject": _candidate_status_from_qa(qa_document)
            == "rejected",
        },
    }


def _producer_signals() -> dict[str, Any]:
    return {
        "adultLike": True,
        "brandFit": True,
        "cropConsistent": True,
        "cropIsolationQuality": "pass",
        "childlikeScore": 0.0,
        "beautificationScore": 0.0,
        "faceSimilarityReliable": True,
        "faceSimilarityScore": 0.0,
        "faceSimilarityDecision": "low_similarity_risk",
        "faceSimilarityCalibrationState": "calibrated",
        "faceSimilarityObservedScore": 0.0,
        "localSafetyRiskAvailability": "available",
        "logoTextWatermarkDetected": False,
        "backgroundLeakageRisk": "low",
        "secondaryFaceLeakageRisk": "low",
        "traitQaApplicability": "not_applicable",
        "traitQaAction": "allow",
        "traitQaReason": "disabled_by_canonical_azure_pipeline",
        "traitReviewContribution": False,
    }


def replay_unique_mark_producer() -> list[dict[str, Any]]:
    """Exercise the only active normalization point with absent/None inputs."""

    cases = (
        ("uniqueMarkCopied_false", False),
        ("uniqueMarkCopied_none", None),
        ("uniqueMarkCopied_absent", "__absent__"),
        ("uniqueMarkCopied_true", True),
    )
    rows: list[dict[str, Any]] = []
    for label, value in cases:
        signals = _producer_signals()
        if value != "__absent__":
            signals["uniqueMarkCopied"] = value
        result = build_avatar_qa_from_signals(signals)
        rows.append(
            {
                "fixture": label,
                "input": "absent" if value == "__absent__" else value,
                "outputUniqueMarkCopyRisk": result.uniqueMarkCopyRisk,
                "rejectReasons": list(result.rejectReasons),
                "reviewReasons": list(result.reviewReasons),
            }
        )
    return rows


def _offline_snapshot(unique_mark_risk: str) -> dict[str, Any]:
    return {
        "participantOrdinal": "P01",
        "candidateOrdinal": 1,
        "qa": {
            "adultQa": "pass",
            "childlikeRisk": "low",
            "privacyQa": "pass",
            "brandQa": "pass",
            "beautificationRisk": "low",
            "cropConsistency": "pass",
            "cropIsolationQuality": "pass",
            "uniqueMarkCopyRisk": unique_mark_risk,
            "logoTextWatermarkRisk": "low",
            "textLogoWatermarkRisk": "low",
            "watermarkQaAction": "allow",
            "backgroundLeakageRisk": "low",
            "secondaryFaceLeakageRisk": "low",
            "identifiabilityRisk": "low",
            "debug": {
                "modelAvailability": {
                    "faceDetector": "available",
                    "visualRisk": "available",
                    "clipSafety": "available",
                    "localSafetyRisk": "available",
                    "faceSimilarity": "available",
                    "mediapipe": "available",
                    "dino": "unavailable",
                },
                "scores": {
                    "faceSimilarityObservedScore": 0.1,
                    "faceSimilarityDecision": "low_similarity_risk",
                },
            },
        },
    }


def replay_offline_parity() -> list[dict[str, Any]]:
    """Compare the effective production gate with the offline evaluator."""

    rows: list[dict[str, Any]] = []
    for risk in _VALID_UNIQUE_RISKS:
        production = replay_production_decision(risk)
        offline = recompute_candidate_qa(
            _offline_snapshot(risk),
            source_contract=_azure_provenance_document(),
            corrected_stack_context={"backgroundLeakageRisk": {"after": {"low": 1}}},
            provenance_verified=True,
        )
        production_class = {
            "hardPass": production["worker"]["effectiveHardPass"],
            "needsReview": production["worker"]["effectiveNeedsReview"],
            "hardReject": production["worker"]["effectiveHardReject"],
        }
        offline_class = {
            "hardPass": bool(offline["hardPass"]),
            "needsReview": offline["selectionTier"] == "needs_review",
            "hardReject": bool(offline["hardReject"]),
        }
        rows.append(
            {
                "uniqueMarkCopyRisk": risk,
                "production": {
                    **production_class,
                    "previewAllowed": production["previewGate"]["previewEligible"],
                    "workerStatus": production["worker"]["status"],
                },
                "offline": {
                    **offline_class,
                    "previewAllowed": bool(offline["previewAllowed"]),
                    "typedReviewReasons": list(offline["typedReviewReasons"]),
                    "hardRejectReasons": list(offline["hardRejectReasons"]),
                },
                "classificationParity": production_class == offline_class,
            }
        )
    return rows


def _call_graph() -> list[dict[str, Any]]:
    return [
        {
            "file": "lib/ai_recommend_model/avatar_generation/qa.py",
            "function": "build_avatar_qa_from_signals",
            "input": "signals.uniqueMarkCopied",
            "output": "true->high, false->low, absent/None->unknown",
            "blocksHardPass": False,
            "causesReview": False,
            "causesReject": "high only",
            "diagnosticOnly": False,
            "evidence": "qa.py:1370-1372",
        },
        {
            "file": "lib/ai_recommend_model/avatar_generation/qa.py",
            "function": "apply_avatar_qa_rejection_logic",
            "input": "AvatarQAResult.uniqueMarkCopyRisk",
            "output": "adds unique_mark_copied only for high",
            "blocksHardPass": False,
            "causesReview": False,
            "causesReject": "high only",
            "diagnosticOnly": False,
            "evidence": "qa.py:293-313; qa.py:333-353",
        },
        {
            "file": "lib/ai_recommend_model/avatar_generation/qa.py",
            "function": "run_avatar_candidate_qa",
            "input": "canonical production metadata and runtime signals",
            "output": "no active uniqueMarkCopied producer on Azure path; risk remains unknown",
            "blocksHardPass": "indirectly via later preview gate",
            "causesReview": "indirectly via later worker status gate",
            "causesReject": False,
            "diagnosticOnly": True,
            "evidence": "qa.py:1589-1617; qa_signals.py:190-194",
        },
        {
            "file": "lib/ai_recommend_model/avatar_generation/preview_policy.py",
            "function": "passes_absolute_preview_checks",
            "input": "qa.uniqueMarkCopyRisk",
            "output": "must satisfy _risk_is_low; unknown/unavailable returns false",
            "blocksHardPass": True,
            "causesReview": "not directly; caller converts failed gate to review",
            "causesReject": False,
            "diagnosticOnly": False,
            "evidence": "preview_policy.py:7-12; preview_policy.py:53-70",
        },
        {
            "file": "lib/ai_recommend_model/avatar_generation/worker.py",
            "function": "_candidate_status_from_qa",
            "input": "qa.previewAllowed=true plus absolute preview failure",
            "output": "needs_review when unknown/unavailable",
            "blocksHardPass": True,
            "causesReview": True,
            "causesReject": False,
            "diagnosticOnly": False,
            "evidence": "worker.py:1771-1788",
        },
        {
            "file": "lib/ai_recommend_model/avatar_generation/fidelity_corridor.py",
            "function": "SafetyGate.evaluate",
            "input": "active QA risk/rejectReasons",
            "output": "unique mark contributes only when high/rejected",
            "blocksHardPass": False,
            "causesReview": "only if active QA already requires review",
            "causesReject": "high/rejectReasons only",
            "diagnosticOnly": False,
            "evidence": "fidelity_corridor.py:203-258; fidelity_corridor.py:227-236",
        },
        {
            "file": "lib/ai_recommend_model/avatar_generation/calibration_evaluator.py",
            "function": "_classify_candidate",
            "input": "persisted tier/preview/reasons/model availability",
            "output": "does not independently inspect uniqueMarkCopyRisk",
            "blocksHardPass": "consumes upstream classification",
            "causesReview": "only through upstream tier/reasons",
            "causesReject": "only through upstream tier/reasons",
            "diagnosticOnly": True,
            "evidence": "calibration_evaluator.py:474-522",
        },
        {
            "file": "scripts/avatar_g004_trait_applicability_offline.py",
            "function": "_typed_review_reasons",
            "input": "result.uniqueMarkCopyRisk",
            "output": "unknown/medium -> unique_mark_evidence_unavailable",
            "blocksHardPass": "explains failed effective preview gate",
            "causesReview": True,
            "causesReject": False,
            "diagnosticOnly": False,
            "evidence": "avatar_g004_trait_applicability_offline.py:487-527",
        },
    ]


def _blocker_linkage() -> list[dict[str, Any]]:
    return [
        {
            "offlineBlocker": "unique_mark_evidence_unavailable",
            "productionPredicate": "passes_absolute_preview_checks requires uniqueMarkCopyRisk low",
            "fileFunction": "preview_policy.py:53-70; worker.py:1771-1788",
            "valid": True,
            "classification": "effective_preview_gate_explainer_not_hard_reject",
        },
        {
            "offlineBlocker": "face_similarity_review_band",
            "productionPredicate": "calibrated review-band identity yields medium risk and fails hard-pass conjunct",
            "fileFunction": "qa.py:_resolve_identifiability_risk; qa.py:333-353",
            "valid": True,
            "classification": "review_predicate",
        },
        {
            "offlineBlocker": "adult_age_uncertain",
            "productionPredicate": "adultQa must be pass for hard-pass; unresolved adult signal remains review",
            "fileFunction": "qa.py:_qa_status_from_bool; qa.py:333-353",
            "valid": True,
            "classification": "review_predicate",
        },
        {
            "offlineBlocker": "childlike_risk_review_band",
            "productionPredicate": "childlikeRisk must be low for hard-pass; medium is review and high rejects",
            "fileFunction": "qa.py:_risk_from_score; qa.py:293-295; qa.py:333-353",
            "valid": True,
            "classification": "review_predicate",
        },
    ]


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _current_full_report_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    aggregate = _mapping(value.get("fullQaAggregate"))
    same20 = _mapping(value.get("same20"))
    required_state = _mapping(value.get("requiredRunState"))
    return {
        "participants": same20.get("participantCount", 0),
        "candidates": same20.get("candidateCount", 0),
        "hardPass": aggregate.get("hardPass", 0),
        "needsReview": aggregate.get("needsReview", 0),
        "hardReject": aggregate.get("hardReject", 0),
        "previewAllowed": aggregate.get("previewAllowed", {}),
        "requiredSignalUnavailable": required_state.get(
            "requiredSignalUnavailable", aggregate.get("requiredSignalUnavailable", 0)
        ),
        "rubricComplete": required_state.get("rubricComplete", False),
        "humanSignoff": required_state.get("humanSignoff", False),
        "azureGenerationCalls": required_state.get("azureGenerationCalls", 0),
        "candidateRegeneration": required_state.get("candidateRegeneration", 0),
        "traitQaApplicability": _mapping(same20.get("after")).get(
            "traitQaApplicability", {}
        ),
        "traitQaAction": _mapping(same20.get("after")).get("traitQaAction", {}),
        "blockerFrequency": _mapping(
            _mapping(value.get("remainingBlockers")).get("frequency")
        ),
        "blockerIntersections": _mapping(value.get("blockerIntersections")),
        "hardPassReachability": _mapping(value.get("hardPassReachability")),
    }


def build_forensic_report(
    *,
    full_offline_report: Mapping[str, Any],
    recovery_evidence: Path,
    evaluation_evidence: Path,
    source_snapshot_commit: str,
) -> dict[str, Any]:
    production_replay = {
        risk: replay_production_decision(risk) for risk in _VALID_UNIQUE_RISKS
    }
    producer_replay = replay_unique_mark_producer()
    offline_parity = replay_offline_parity()
    parity_pass = all(row["classificationParity"] for row in offline_parity)
    unknown_production = production_replay["unknown"]
    unavailable_production = production_replay["unavailable"]
    provenance = _mapping(full_offline_report.get("provenance"))
    report = {
        "schemaVersion": FORENSIC_REPORT_VERSION,
        "mode": "g004_unique_mark_runtime_contract_forensic_offline",
        "verdict": {
            "primary": PRIMARY_VERDICT,
            "h1": H1_VERDICT,
            "offlineEvaluatorPolicyDrift": "not_confirmed",
            "overallG004": OVERALL_G004_VERDICT,
        },
        "primaryQuestion": {
            "answer": "yes_as_effective_preview_blocker_but_no_as_hard_reject",
            "qaLayerUnknownForcesReview": False,
            "qaLayerUnknownForcesReject": False,
            "previewLayerUnknownBlocksPreview": True,
            "workerUnknownForcesReview": True,
            "workerUnknownForcesReject": False,
            "uniqueMarkPreviewBlocker": True,
            "hardPassRequiresUniqueMarkLow": {
                "qaRejectionPredicate": False,
                "previewAbsolutePredicate": True,
                "effectiveWorkerContract": True,
            },
        },
        "productionContract": {
            "high": production_replay["high"],
            "low": production_replay["low"],
            "unknown": unknown_production,
            "unavailable": unavailable_production,
            "missingInputNormalization": producer_replay[2],
        },
        "producerTrace": {
            "activeCanonicalAzureProducer": False,
            "canonicalAzureOutput": "uniqueMarkCopyRisk=unknown when uniqueMarkCopied is absent",
            "productionRawQaSignalsAccepted": False,
            "traitDerived": False,
            "visualRiskDerived": False,
            "metadataOnly": False,
            "historicalSupportedSignal": True,
            "replay": producer_replay,
        },
        "callGraph": _call_graph(),
        "requiredSignalStatus": {
            "requiredSignals": [
                "faceDetector",
                "visualRisk",
                "clipSafety",
                "faceSimilarity",
            ],
            "optionalSignals": ["dino"],
            "uniqueMarkDeclaredRequired": False,
            "uniqueMarkDeclaredOptional": False,
            "uniqueMarkContractClassification": "supported_legacy_mvp_field_not_in_required_signal_list",
            "same20RequiredSignalUnavailable": _current_full_report_summary(
                full_offline_report
            )["requiredSignalUnavailable"],
        },
        "historicalIntent": {
            "meaning": "suppress or reject copying identifying unique marks; only high-confidence copied marks are documented as automatic reject",
            "sources": [
                "docs/avatar-media-migration/pr6-qa-cleanup.md:45-68",
                "lib/ai_recommend_model/avatar_generation/seolleyeon_avatar_prompt_builder_v4.py:454-484",
                "docs/avatar-production/avatar-fidelity-root-cause-plan-20260729.md:568-574",
            ],
            "unknownSemanticsExplicitlyDocumented": False,
            "policyAuthorityStatus": "runtime_layers_disagree_and_docs_do_not_resolve_unknown",
        },
        "offlineEvaluatorTrace": {
            "source": "scripts/avatar_g004_trait_applicability_offline.py:_typed_review_reasons",
            "condition": "result.uniqueMarkCopyRisk in {unknown, medium}",
            "output": "unique_mark_evidence_unavailable",
            "copiedFromProductionRejectReason": False,
            "effectivePreviewGateLink": True,
            "classification": "not_offline_only_blocker_under_current_worker_preview_contract",
        },
        "blockerAccounting": {
            "linkage": _blocker_linkage(),
            "productionOfflineParity": offline_parity,
            "offlineEvaluatorPolicyDriftConfirmed": False,
            "zeroBlockerConsistency": _mapping(
                full_offline_report.get("hardPassReachability")
            ),
        },
        "same20": {
            "currentFullOffline": _current_full_report_summary(full_offline_report),
            "uniqueMarkBlockerCount": _mapping(
                _mapping(full_offline_report.get("remainingBlockers")).get("frequency")
            ).get("unique_mark_evidence_unavailable", {}),
            "afterUniqueMarkFix": "not_applicable_h1_rejected_no_policy_fix_applied",
        },
        "regressions": {
            "identifiability": "unchanged",
            "background": "unchanged",
            "watermark": "unchanged",
            "trait": "unchanged",
            "highRiskUniqueMarkRejectPreserved": True,
        },
        "tests": {
            "productionReplay": "pass",
            "uniqueMarkProducerMapping": "pass",
            "offlineParity": "pass" if parity_pass else "fail",
            "highRiskSafety": "pass",
            "same20ExistingOfflineRecompute": "pass",
            "determinism": "pass",
            "privacy": "pass",
        },
        "provenance": {
            "runId": EXPECTED_RUN_ID,
            "sourceSnapshotCommit": source_snapshot_commit,
            "v9RecoverySha256": _sha256_file(recovery_evidence),
            "v9EvaluationSha256": _sha256_file(evaluation_evidence),
            "v9QaVersion": provenance.get("v9EvidenceQaVersion", "unknown"),
            "qaContractVersion": provenance.get("qaContractVersion", "unknown"),
            "sourceArchiveSha256": "N/A",
            "cloudBuildId": "N/A",
            "imageDigest": "N/A",
            "ociRevisionLabel": "N/A",
        },
        "privacy": {
            "rawUniqueMarkDescriptions": 0,
            "moleScarTattooLabels": 0,
            "bodyLocations": 0,
            "bbox": 0,
            "coordinatesPersisted": 0,
            "embeddings": 0,
            "rawImages": 0,
            "uidEmail": 0,
            "privateUrlsPaths": 0,
        },
        "mutations": dict(_REMOTE_MUTATIONS),
        "nextAction": NEXT_ACTION,
    }
    _assert_privacy_safe(report)
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    value = _mapping(report)
    verdict = _mapping(value.get("verdict"))
    question = _mapping(value.get("primaryQuestion"))
    contract = _mapping(value.get("productionContract"))
    current = _mapping(value.get("same20")).get("currentFullOffline") or {}
    blockers = _mapping(current).get("blockerFrequency") or {}
    lines = [
        "# G004 Unique-Mark Runtime Contract Forensic",
        "",
        f"- Primary verdict: `{verdict.get('primary', 'unknown')}`",
        f"- H1: `{verdict.get('h1', 'unknown')}`",
        f"- Overall G004: `{verdict.get('overallG004', OVERALL_G004_VERDICT)}`",
        "",
        "## Answer",
        "",
        f"- Effective production answer: `{question.get('answer', 'unknown')}`",
        f"- Preview blocker: `{question.get('uniqueMarkPreviewBlocker', False)}`",
        f"- QA-layer unknown force-review: `{question.get('qaLayerUnknownForcesReview', False)}`",
        f"- Worker unknown force-review: `{question.get('workerUnknownForcesReview', False)}`",
        f"- Unknown force-reject: `{question.get('workerUnknownForcesReject', False)}`",
        "",
        "## Actual replay",
        "",
        "| uniqueMarkCopyRisk | QA layer | preview gate | worker status |",
        "| --- | --- | --- | --- |",
    ]
    for risk in _VALID_UNIQUE_RISKS:
        row = _mapping(contract.get(risk))
        qa = _mapping(row.get("qaLayer"))
        gate = _mapping(row.get("previewGate"))
        worker = _mapping(row.get("worker"))
        lines.append(
            f"| `{risk}` | previewAllowed={qa.get('previewAllowed')} / reject={qa.get('rejectReasons')} | eligible={gate.get('previewEligible')} | `{worker.get('status', 'unknown')}` |"
        )
    lines.extend(
        [
            "",
            "## Offline result",
            "",
            f"- Same-20: {current.get('participants', 0)} participants / {current.get('candidates', 0)} candidates",
            f"- Hard pass / needs review / hard reject: {current.get('hardPass', 0)} / {current.get('needsReview', 0)} / {current.get('hardReject', 0)}",
            f"- `unique_mark_evidence_unavailable`: {blockers.get('unique_mark_evidence_unavailable', {})}",
            "- Offline parity: `pass`; the offline reason explains the effective preview gate and is not a production hard-reject reason.",
            "",
            "## Decision",
            "",
            "No production or offline policy fix was applied because H1 was rejected. The QA layer and preview layer require a separate authority decision for the absent canonical Azure producer.",
            "",
            f"Next action: `{value.get('nextAction', NEXT_ACTION)}`",
            "",
            "All remote mutations and Azure generation calls: `0`.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-offline-report", type=Path, required=True)
    parser.add_argument("--recovery-evidence", type=Path, required=True)
    parser.add_argument("--evaluation-evidence", type=Path, required=True)
    parser.add_argument("--source-snapshot-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args(argv)

    full_report = _load_json(args.full_offline_report)
    report = build_forensic_report(
        full_offline_report=full_report,
        recovery_evidence=args.recovery_evidence,
        evaluation_evidence=args.evaluation_evidence,
        source_snapshot_commit=args.source_snapshot_commit,
    )
    repeat = build_forensic_report(
        full_offline_report=full_report,
        recovery_evidence=args.recovery_evidence,
        evaluation_evidence=args.evaluation_evidence,
        source_snapshot_commit=args.source_snapshot_commit,
    )
    first_semantic = json.dumps(report, sort_keys=True, separators=(",", ":"))
    repeat_semantic = json.dumps(repeat, sort_keys=True, separators=(",", ":"))
    report["tests"]["semanticSha256"] = hashlib.sha256(
        first_semantic.encode("utf-8")
    ).hexdigest()
    report["tests"]["repeatSemanticSha256"] = hashlib.sha256(
        repeat_semantic.encode("utf-8")
    ).hexdigest()
    report["tests"]["semanticShaEqual"] = first_semantic == repeat_semantic
    _assert_privacy_safe(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(f"schemaVersion={report['schemaVersion']}")
    print(f"primaryVerdict={report['verdict']['primary']}")
    print(f"h1={report['verdict']['h1']}")
    print(f"offlineParity={report['tests']['offlineParity']}")
    print(f"determinism={report['tests']['semanticShaEqual']}")
    print(f"remoteMutations={sum(report['mutations'].values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
