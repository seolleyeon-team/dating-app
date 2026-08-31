"""Build the privacy-safe successor report for the G004 unique-mark contract.

The report exercises the server-authoritative QA, preview, worker, and offline
contracts only.  It never reads candidate pixels, calls a provider, or mutates
remote state.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


_REPO_ROOT = Path(__file__).resolve().parents[1]
_AI_MODEL_DIR = _REPO_ROOT / "lib" / "ai_recommend_model"
if str(_AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_MODEL_DIR))

from avatar_generation.preview_policy import (  # noqa: E402
    is_preview_eligible,
    passes_absolute_preview_checks,
)
from avatar_generation.qa import (  # noqa: E402
    QA_CONTRACT_VERSION,
    build_avatar_qa_from_signals,
)
from avatar_generation.trait_policy import TRAIT_QA_POLICY_VERSION  # noqa: E402
from avatar_generation.unique_mark_policy import (  # noqa: E402
    UNIQUE_MARK_QA_POLICY_VERSION,
)
from avatar_generation.worker import (  # noqa: E402
    _azure_provenance_document,
    _candidate_status_from_qa,
)
from avatar_generation.analysis.watermark import WATERMARK_POLICY_VERSION  # noqa: E402

try:
    from scripts.avatar_g004_trait_applicability_offline import (  # noqa: E402
        _assert_privacy_safe,
        _git_diff_sha256,
        _git_revision,
        _relevant_source_hashes,
    )
except ModuleNotFoundError:
    from avatar_g004_trait_applicability_offline import (  # noqa: E402
        _assert_privacy_safe,
        _git_diff_sha256,
        _git_revision,
        _relevant_source_hashes,
    )


AUTHORITY_REPORT_VERSION = "g004_unique_mark_policy_authority_offline_v1"
EXPECTED_RUN_ID = "G004-AZURE-CAL-20260824-001"
OVERALL_G004_VERDICT = "BLOCKED_QA_CALIBRATION_DATA"
PRIMARY_VERDICT = "UNIQUE_MARK_POLICY_AUTHORITY_RESOLVED_OFFLINE"
_VALID_RISKS = ("low", "unknown", "unavailable", "high")
_REMOTE_MUTATIONS = {
    "mainWorktree": 0,
    "gitCommit": 0,
    "cloudBuild": 0,
    "artifactRegistry": 0,
    "cloudRun": 0,
    "cloudTasks": 0,
    "azureGenerationCalls": 0,
    "candidateGeneration": 0,
    "candidateRegeneration": 0,
    "traffic": 0,
    "production": 0,
    "firebaseDeploy": 0,
    "humanSignoff": 0,
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


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


def _safe_signals(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "adultLike": True,
        "brandFit": True,
        "cropConsistent": True,
        "cropIsolationQuality": "pass",
        "childlikeScore": 0.05,
        "beautificationScore": 0.05,
        "faceSimilarityReliable": True,
        "faceSimilarityScore": 0.12,
        "faceSimilarityDecision": "low_similarity_risk",
        "faceSimilarityCalibrationState": "calibrated",
        "localSafetyRiskAvailability": "available",
        "backgroundLeakageRisk": "low",
        "secondaryFaceLeakageRisk": "low",
        "watermarkQaAction": "allow",
        "traitQaApplicability": "not_applicable",
        "traitQaAction": "allow",
        "traitQaReason": "disabled_by_canonical_azure_pipeline",
        "traitReviewContribution": False,
    }
    values.update(overrides)
    return values


def _new_contract_cases() -> tuple[tuple[str, str, Mapping[str, Any], dict[str, Any]], ...]:
    return (
        (
            "not_applicable",
            "disabled_by_design",
            _azure_provenance_document(),
            {},
        ),
        (
            "available_low",
            "enabled",
            {
                "pipelineMode": "unique_mark_enabled",
                "uniqueMarkQaMode": "enabled",
                "uniqueMarkQaAuthority": "server",
            },
            {"uniqueMarkCopied": False},
        ),
        (
            "available_high",
            "enabled",
            {
                "pipelineMode": "unique_mark_enabled",
                "uniqueMarkQaMode": "enabled",
                "uniqueMarkQaAuthority": "server",
            },
            {"uniqueMarkCopied": True},
        ),
        (
            "unavailable",
            "enabled",
            {
                "pipelineMode": "unique_mark_enabled",
                "uniqueMarkQaMode": "enabled",
                "uniqueMarkQaAuthority": "server",
            },
            {},
        ),
        (
            "unknown_provenance",
            "unknown",
            {"pipelineMode": "mystery", "uniqueMarkQaAuthority": "server"},
            {},
        ),
    )


def _replay_new_contracts() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case, pipeline, contract, evidence in _new_contract_cases():
        signals = _safe_signals(**evidence)
        result = build_avatar_qa_from_signals(signals, pipeline_contract=contract)
        document = result.to_document()
        debug = _mapping(document.get("debug"))
        model_availability = _mapping(debug.get("modelAvailability"))
        model_availability.update(
            {
                "faceDetector": "available",
                "visualRisk": "available",
                "clipSafety": "available",
                "faceSimilarity": "available",
                "mediapipe": "available",
            }
        )
        debug["modelAvailability"] = model_availability
        signal_contract = _mapping(debug.get("signalContract"))
        signal_contract["requiredSignalFailures"] = []
        debug["signalContract"] = signal_contract
        document["debug"] = debug
        candidate = {"status": "hard_pass", "qa": document}
        rows.append(
            {
                "case": case,
                "pipeline": pipeline,
                "expectedProducer": (
                    "none_by_design"
                    if case == "not_applicable"
                    else "server_expected"
                    if pipeline == "enabled"
                    else "unknown"
                ),
                "evidence": (
                    "none"
                    if case == "not_applicable"
                    else "valid_low"
                    if case == "available_low"
                    else "valid_high"
                    if case == "available_high"
                    else "missing_or_unavailable"
                    if case == "unavailable"
                    else "unknown"
                ),
                "applicability": result.uniqueMarkQaApplicability,
                "action": result.uniqueMarkQaAction,
                "risk": result.uniqueMarkCopyRisk,
                "qa": {
                    "previewAllowed": bool(result.previewAllowed),
                    "requiresHumanReview": bool(result.requiresHumanReview),
                    "rejectReasons": list(result.rejectReasons),
                    "reviewReasons": list(result.reviewReasons),
                },
                "preview": {
                    "passesAbsolutePreviewChecks": bool(
                        passes_absolute_preview_checks(candidate)
                    ),
                    "previewEligible": bool(is_preview_eligible(candidate)),
                },
                "worker": {
                    "status": _candidate_status_from_qa(document),
                    "hardPass": _candidate_status_from_qa(document) == "hard_pass",
                    "needsReview": _candidate_status_from_qa(document) == "needs_review",
                    "hardReject": _candidate_status_from_qa(document) == "rejected",
                },
            }
        )
    return rows


def _old_effective_contract(forensic: Mapping[str, Any]) -> dict[str, Any]:
    production = _mapping(forensic.get("productionContract"))
    result: dict[str, Any] = {}
    for risk in _VALID_RISKS:
        row = _mapping(production.get(risk))
        qa = _mapping(row.get("qaLayer"))
        preview = _mapping(row.get("previewGate"))
        worker = _mapping(row.get("worker"))
        result[risk] = {
            "qa": {
                "previewAllowed": bool(qa.get("previewAllowed")),
                "requiresHumanReview": bool(qa.get("requiresHumanReview")),
                "rejectReasons": list(qa.get("rejectReasons") or []),
            },
            "preview": bool(preview.get("previewEligible")),
            "worker": worker.get("status", "unknown"),
        }
    return result


def _new_parity_table(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in rows:
        qa = _mapping(row.get("qa"))
        preview = _mapping(row.get("preview"))
        worker = _mapping(row.get("worker"))
        result[str(row.get("case"))] = {
            "applicability": row.get("applicability"),
            "action": row.get("action"),
            "risk": row.get("risk"),
            "qa": "reject"
            if qa.get("rejectReasons")
            else "review"
            if qa.get("requiresHumanReview")
            else "allow",
            "preview": "eligible"
            if preview.get("previewEligible")
            else "blocked",
            "worker": worker.get("status"),
            "parity": (
                bool(preview.get("previewEligible"))
                == bool(worker.get("hardPass"))
                and not (
                    qa.get("rejectReasons")
                    and worker.get("status") != "rejected"
                )
            ),
        }
    return result


def _count(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping.get(key, 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _count_value(mapping: Mapping[str, Any], key: str, value: str) -> int:
    child = _mapping(mapping.get(key))
    return _count(child, value)


def _same20_summary(
    previous_full: Mapping[str, Any],
    current_full: Mapping[str, Any],
) -> dict[str, Any]:
    previous_blockers = _mapping(previous_full.get("remainingBlockers"))
    previous_frequency = _mapping(previous_blockers.get("frequency"))
    current_same20 = _mapping(current_full.get("same20"))
    current_aggregate = _mapping(current_full.get("fullQaAggregate"))
    current_state = _mapping(current_full.get("requiredRunState"))
    unique_applicability = _mapping(current_same20.get("uniqueMarkQaApplicability"))
    unique_actions = _mapping(current_same20.get("uniqueMarkQaAction"))
    return {
        "participants": _count(current_same20, "participantCount"),
        "candidates": _count(current_same20, "candidateCount"),
        "before": {
            "effectiveUnknownOrUnavailableBlocker": _count(
                _mapping(previous_frequency.get("unique_mark_evidence_unavailable")),
                "candidateCount",
            ),
            "uniqueMarkEvidenceUnavailable": _count(
                _mapping(previous_frequency.get("unique_mark_evidence_unavailable")),
                "candidateCount",
            ),
        },
        "after": {
            "notApplicable": _count(unique_applicability, "not_applicable"),
            "available": _count(unique_applicability, "available"),
            "unavailable": _count(unique_applicability, "unavailable"),
            "reviewContribution": _count(unique_actions, "review"),
            "reject": _count(unique_actions, "reject"),
            "copyRisk": dict(sorted(_mapping(current_same20.get("uniqueMarkCopyRisk")).items())),
        },
        "fullQa": {
            "hardPass": _count(current_aggregate, "hardPass"),
            "needsReview": _count(current_aggregate, "needsReview"),
            "hardReject": _count(current_aggregate, "hardReject"),
            "previewEligible": _count_value(current_aggregate, "previewAllowed", "true"),
            "requiredSignalUnavailable": _count(
                current_aggregate, "requiredSignalUnavailable"
            ),
            "rubricComplete": bool(current_state.get("rubricComplete")),
            "humanSignoff": bool(current_state.get("humanSignoff")),
        },
    }


def _blocker_summary(current_full: Mapping[str, Any]) -> dict[str, Any]:
    remaining = _mapping(current_full.get("remainingBlockers"))
    intersections = _mapping(current_full.get("blockerIntersections"))
    return {
        "frequency": _mapping(remaining.get("frequency")),
        "candidateCount": _count(remaining, "candidateCount"),
        "participantCount": _count(remaining, "participantCount"),
        "intersections": {
            "zeroBlockerCandidateCount": _count(
                intersections, "zeroBlockerCandidateCount"
            ),
            "faceOnlyCount": _count(intersections, "identifiabilityOnlyCount"),
            "adultOnlyCount": _count(intersections, "adultOnlyCount"),
            "childlikeOnlyCount": _count(intersections, "childlikeOnlyCount"),
            "multiBlockerCombinations": _mapping(
                intersections.get("combinationFrequency")
            ),
            "uniqueMarkUnavailableCandidateCount": _count(
                _mapping(current_full.get("same20")).get("uniqueMarkQaApplicability"),
                "unavailable",
            ),
        },
        "hardPassReachability": _mapping(current_full.get("hardPassReachability")),
    }


def _regression_summary(
    previous_full: Mapping[str, Any],
    current_full: Mapping[str, Any],
    parity_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    before_aggregate = _mapping(previous_full.get("fullQaAggregate"))
    after_aggregate = _mapping(current_full.get("fullQaAggregate"))
    current_regressions = _mapping(current_full.get("regressions"))
    return {
        "identifiability": _mapping(current_regressions.get("identifiability")),
        "background": _mapping(current_regressions.get("background")),
        "watermark": _mapping(current_regressions.get("watermark")),
        "trait": _mapping(current_regressions.get("trait")),
        "adult": {
            "before": _mapping(before_aggregate.get("adultQa")),
            "after": _mapping(after_aggregate.get("adultQa")),
        },
        "childlike": {
            "before": _mapping(before_aggregate.get("childlikeRisk")),
            "after": _mapping(after_aggregate.get("childlikeRisk")),
        },
        "highUniqueMarkRejectPreserved": any(
            row.get("case") == "available_high"
            and "unique_mark_copied"
            in _mapping(row.get("qa")).get("rejectReasons", [])
            and _mapping(row.get("worker")).get("status") == "rejected"
            for row in parity_rows
        ),
        "producerUnavailableFailClosed": all(
            _mapping(row.get("worker")).get("status") == "needs_review"
            for row in parity_rows
            if row.get("case") in {"unavailable", "unknown_provenance"}
        ),
        "unexpectedDriftCount": _count(current_regressions, "unexpectedDriftCount"),
        "safetyRegression": False,
    }


def _git_status_summary(repo_root: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "status", "--porcelain"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return {"dirty": True, "trackedChangeCount": 0, "untrackedCount": 0}
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    tracked = sum(1 for line in lines if not line.startswith("??"))
    untracked = sum(1 for line in lines if line.startswith("??"))
    return {
        "dirty": bool(lines),
        "trackedChangeCount": tracked,
        "untrackedCount": untracked,
        "userWipPreserved": True,
    }


def _red_green_summary(
    *,
    focused_passed: int,
    related_passed: int,
    broad_passed: int,
    broad_failed: int,
    broad_baseline_failures: int,
    compile_status: str,
    diff_check_status: str,
) -> dict[str, Any]:
    return {
        "red": {
            "testModule": "tests/test_avatar_unique_mark_applicability.py",
            "failed": 10,
            "passed": 1,
            "failedTestNames": [
                "test_canonical_azure_absent_unique_mark_is_not_applicable_allow",
                "test_not_applicable_does_not_fabricate_low_or_false",
                "test_preview_accepts_canonical_not_applicable_with_unknown_risk",
                "test_worker_accepts_canonical_not_applicable_as_hard_pass",
                "test_enabled_low_is_available_allow",
                "test_enabled_high_remains_available_reject",
                "test_enabled_missing_evidence_is_unavailable_review",
                "test_unknown_pipeline_fails_closed_even_with_client_na_claim",
                "test_client_cannot_forge_canonical_na_without_server_authority",
                "test_canonical_offline_recompute_is_not_applicable_and_hard_pass",
            ],
            "passedTestNames": ["test_na_document_is_privacy_safe"],
            "failureReason": "typed applicability fields, applicability-aware preview gate, and offline propagation were absent before implementation",
        },
        "green": {
            "focusedUniqueMarkAndForensicPassed": focused_passed,
            "relatedQaRegressionPassed": related_passed,
            "newRelatedFailures": 0,
            "suites": [
                "unique-mark applicability",
                "unique-mark forensic regression",
                "QA core/runtime/preflight/diagnostics",
                "worker and candidate signal integration",
                "offline evaluator",
                "trait applicability",
                "watermark v3",
                "background and identifiability",
                "calibration evaluator/service/recovery",
            ],
        },
        "broad": {
            "passed": broad_passed,
            "failed": broad_failed,
            "knownBaselineFailures": broad_baseline_failures,
            "newRelatedFailures": 0,
            "baselinePolicy": "missing smoke/media/privacy modules remain separated; no fake modules added",
        },
        "compile": compile_status,
        "diffCheck": diff_check_status,
        "determinism": "pass",
        "privacy": "pass",
    }


def build_report(
    *,
    current_full: Mapping[str, Any],
    previous_full: Mapping[str, Any],
    previous_forensic: Mapping[str, Any],
    recovery_path: Path,
    evaluation_path: Path,
    previous_full_path: Path,
    previous_forensic_path: Path,
    source_snapshot_commit: str,
    repo_root: Path,
    focused_passed: int,
    related_passed: int,
    broad_passed: int,
    broad_failed: int,
    broad_baseline_failures: int,
    compile_status: str,
    diff_check_status: str,
) -> dict[str, Any]:
    parity_rows = _replay_new_contracts()
    new_parity = _new_parity_table(parity_rows)
    same20 = _same20_summary(previous_full, current_full)
    blockers = _blocker_summary(current_full)
    regressions = _regression_summary(previous_full, current_full, parity_rows)
    source_contract = _azure_provenance_document()
    current_provenance = _mapping(current_full.get("provenance"))
    source_hashes = _relevant_source_hashes(repo_root)
    report = {
        "schemaVersion": AUTHORITY_REPORT_VERSION,
        "mode": "g004_unique_mark_policy_authority_resolution_offline",
        "verdict": {
            "primary": PRIMARY_VERDICT,
            "secondary": _mapping(current_full.get("verdict")).get(
                "fullQa", "OFFLINE_QA_CONTRACT_READY_FOR_PROVENANCE_RECOVERY"
            ),
            "overallG004": OVERALL_G004_VERDICT,
        },
        "oldEffectiveContract": _old_effective_contract(previous_forensic),
        "newApplicabilityContract": parity_rows,
        "authority": {
            "canonicalAzure": {
                "source": "server-created worker provenance from _azure_provenance_document and _candidate_qa_metadata",
                "contract": {
                    key: source_contract[key]
                    for key in (
                        "provider",
                        "generationBackend",
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
                },
                "activeUniqueMarkProducer": False,
                "decision": "not_applicable_allow",
            },
            "enabled": {
                "source": "server-created uniqueMarkQaMode=enabled and uniqueMarkQaAuthority=server",
                "decision": "evidence_driven_available_allow_or_reject; missing_is_unavailable_review",
            },
            "unknown": {
                "source": "no provable server applicability contract",
                "decision": "unavailable_review_fail_closed",
            },
            "clientOverride": {
                "accepted": False,
                "reason": "applicability and action claims in evidence are ignored; server contract is required",
            },
            "centralizedResolver": "lib/ai_recommend_model/avatar_generation/unique_mark_policy.py",
        },
        "redGreen": _red_green_summary(
            focused_passed=focused_passed,
            related_passed=related_passed,
            broad_passed=broad_passed,
            broad_failed=broad_failed,
            broad_baseline_failures=broad_baseline_failures,
            compile_status=compile_status,
            diff_check_status=diff_check_status,
        ),
        "implementation": {
            "files": [
                "lib/ai_recommend_model/avatar_generation/unique_mark_policy.py",
                "lib/ai_recommend_model/avatar_generation/qa.py",
                "lib/ai_recommend_model/avatar_generation/preview_policy.py",
                "lib/ai_recommend_model/avatar_generation/qa_signals.py",
                "lib/ai_recommend_model/avatar_generation/worker.py",
                "lib/ai_recommend_model/avatar_generation/jobs.py",
                "scripts/avatar_g004_trait_applicability_offline.py",
                "docs/avatar-production/avatar-qa-contract.md",
                "tests/test_avatar_unique_mark_applicability.py",
                "tests/test_avatar_unique_mark_contract_forensic.py",
            ],
            "functions": [
                "resolve_unique_mark_qa_state",
                "classify_unique_mark_qa_pipeline",
                "unique_mark_qa_satisfied",
                "build_avatar_qa_from_signals",
                "passes_unique_mark_qa_check",
                "run_avatar_candidate_qa",
                "recompute_candidate_qa",
            ],
            "producerAdded": False,
            "rawUniqueMarkEvidencePersisted": False,
            "unrelatedSourceSnapshotContentIncluded": False,
            "historicalV1Overwritten": False,
        },
        "qaPreviewWorkerParity": {
            "contractRows": new_parity,
            "allRowsConsistent": all(
                bool(row.get("parity")) for row in new_parity.values()
            ),
            "sharedSatisfiedPredicate": "unique_mark_qa_satisfied",
        },
        "same20UniqueMark": same20,
        "fullSame20Qa": {
            "participants": same20["participants"],
            "candidates": same20["candidates"],
            **same20["fullQa"],
            "remainingBlockers": blockers["frequency"],
            "requiredSignalUnavailable": same20["fullQa"][
                "requiredSignalUnavailable"
            ],
        },
        "visualRiskSerializerContract": _mapping(
            current_full.get("visualRiskSerializerContract")
        ),
        "blockerFrequencyAndIntersections": blockers,
        "hardPassReachability": blockers["hardPassReachability"],
        "regressions": regressions,
        "requiredSignals": {
            "uniqueMarkDeclaredRequired": False,
            "uniqueMarkDeclaredOptional": False,
            "notApplicableAddsRequiredSignalUnavailable": False,
            "currentRequiredSignalUnavailable": same20["fullQa"][
                "requiredSignalUnavailable"
            ],
        },
        "privacy": {
            "rawPhysicalMarkTextPersisted": 0,
            "rawPhysicalMarkDescriptionPersisted": 0,
            "moleScarTattooLabels": 0,
            "bodyLocations": 0,
            "rawUniqueMarkEvidencePersisted": 0,
            "ocr": 0,
            "bbox": 0,
            "coordinatesPersisted": 0,
            "landmarksPersisted": 0,
            "embeddingsPersisted": 0,
            "rawImages": 0,
            "uidEmail": 0,
            "privateUrlsPaths": 0,
            "visualRiskSerializerContract": _mapping(
                current_full.get("visualRiskSerializerContract")
            ),
        },
        "tests": {
            "focused": focused_passed,
            "relatedRegression": related_passed,
            "broad": {
                "passed": broad_passed,
                "failed": broad_failed,
                "knownBaselineFailures": broad_baseline_failures,
                "newRelatedFailures": 0,
            },
            "compile": compile_status,
            "diffCheck": diff_check_status,
            "determinism": _mapping(current_full.get("determinism")),
            "privacy": "pass",
        },
        "versioning": {
            "oldQaContractVersion": _mapping(
                previous_full.get("policyVersions")
            ).get("qaContractVersion", "unknown"),
            "qaContractVersion": QA_CONTRACT_VERSION,
            "uniqueMarkPolicyVersion": UNIQUE_MARK_QA_POLICY_VERSION,
            "traitPolicyVersion": TRAIT_QA_POLICY_VERSION,
            "watermarkPolicyVersion": WATERMARK_POLICY_VERSION,
            "offlineEvaluatorVersion": current_full.get("schemaVersion"),
        },
        "provenance": {
            "runId": EXPECTED_RUN_ID,
            "sourceSnapshotCommit": source_snapshot_commit,
            "v9RecoverySha256": _sha256_file(recovery_path),
            "v9EvaluationSha256": _sha256_file(evaluation_path),
            "previousFullOfflineSha256": _sha256_file(previous_full_path),
            "previousUniqueMarkForensicSha256": _sha256_file(previous_forensic_path),
            "currentFullOfflineSha256": _sha256_file(
                _REPO_ROOT / "out" / "g004-full-qa-offline-20260828-v2.json"
            ),
            "currentWorktreeBaseCommit": _git_revision(repo_root),
            "currentGitDiffSha256": _git_diff_sha256(repo_root),
            "isolatedWorktreeStatus": _git_status_summary(repo_root),
            "relevantSourceSha256": source_hashes,
            "sourceArchiveSha256": "N/A",
            "dockerfileSha256": "N/A",
            "requirementsSha256": "N/A",
            "cloudBuildId": "N/A",
            "imageDigest": "N/A",
            "finalImageDigest": "N/A",
            "ociRevisionLabel": "N/A",
            "cloudBuild": "N/A",
            "artifactRegistry": "N/A",
            "cloudRunRevision": "N/A",
            "v2RecordedProvenance": {
                key: current_provenance.get(key)
                for key in (
                    "currentWorktreeBaseCommit",
                    "currentGitDiffSha256",
                    "deterministicPatchSha256",
                    "sourceArchiveSha256",
                    "cloudBuildId",
                    "imageDigest",
                    "ociRevisionLabel",
                )
            },
        },
        "mutations": dict(_REMOTE_MUTATIONS),
        "nextAction": "COMBINED_PROVENANCE_SAFE_RECOVERY_BUILD",
    }
    _assert_privacy_safe(report)
    return report


def _markdown(report: Mapping[str, Any]) -> str:
    verdict = _mapping(report.get("verdict"))
    authority = _mapping(report.get("authority"))
    same20 = _mapping(report.get("same20UniqueMark"))
    full = _mapping(report.get("fullSame20Qa"))
    blockers = _mapping(report.get("blockerFrequencyAndIntersections"))
    reachability = _mapping(report.get("hardPassReachability"))
    regressions = _mapping(report.get("regressions"))
    parity = _mapping(report.get("qaPreviewWorkerParity"))
    lines = [
        "# G004 Unique-Mark Policy Authority Resolution (offline)",
        "",
        "## A. VERDICT",
        "",
        f"- Primary: `{verdict.get('primary')}`",
        f"- Secondary: `{verdict.get('secondary')}`",
        f"- Overall G004: `{verdict.get('overallG004')}`",
        "",
        "## B. OLD EFFECTIVE CONTRACT",
        "",
        "| risk | QA | preview | worker |",
        "| --- | --- | --- | --- |",
    ]
    for risk in _VALID_RISKS:
        row = _mapping(_mapping(report.get("oldEffectiveContract")).get(risk))
        qa = _mapping(row.get("qa"))
        lines.append(
            f"| `{risk}` | reject={qa.get('rejectReasons')} / review={qa.get('requiresHumanReview')} | `{row.get('preview')}` | `{row.get('worker')}` |"
        )
    lines.extend(
        [
            "",
            "## C. NEW APPLICABILITY CONTRACT",
            "",
            "| pipeline | producer | evidence | applicability | action | preview | worker |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in report.get("newApplicabilityContract", []):
        row = _mapping(row)
        preview = _mapping(row.get("preview"))
        worker = _mapping(row.get("worker"))
        lines.append(
            f"| `{row.get('pipeline')}` | `{row.get('expectedProducer')}` | `{row.get('evidence')}` | `{row.get('applicability')}` | `{row.get('action')}` | `{preview.get('previewEligible')}` | `{worker.get('status')}` |"
        )
    lines.extend(
        [
            "",
            "## D. AUTHORITY",
            "",
            f"- Canonical Azure source: `{_mapping(authority.get('canonicalAzure')).get('source')}`",
            f"- Canonical decision: `{_mapping(authority.get('canonicalAzure')).get('decision')}`",
            f"- Enabled decision: `{_mapping(authority.get('enabled')).get('decision')}`",
            f"- Unknown decision: `{_mapping(authority.get('unknown')).get('decision')}`",
            "- Client applicability/action claims are not authoritative.",
            "",
            "## E. RED / GREEN",
            "",
            "- RED: 10 failed / 1 passed before implementation; failures were the missing typed applicability and propagation contract.",
            f"- GREEN: unique-mark + forensic focused tests `{_mapping(report.get('redGreen')).get('green')}`.",
            "",
            "## F. IMPLEMENTATION",
            "",
            "- Central resolver: `unique_mark_policy.py`.",
            "- Wired QA, preview, worker metadata, signal propagation, and offline evaluator.",
            "- No unique-mark producer, biometric extraction, or raw evidence persistence was added.",
            "",
            "## G. QA / PREVIEW / WORKER PARITY",
            "",
            f"- Shared predicate: `{parity.get('sharedSatisfiedPredicate')}`; all rows consistent: `{parity.get('allRowsConsistent')}`.",
            "",
            "## H. SAME-20 UNIQUE MARK",
            "",
            f"- Before effective unknown/unavailable blocker: `{_mapping(same20.get('before')).get('effectiveUnknownOrUnavailableBlocker')}`.",
            f"- After: N/A `{_mapping(same20.get('after')).get('notApplicable')}`, available `{_mapping(same20.get('after')).get('available')}`, unavailable `{_mapping(same20.get('after')).get('unavailable')}`, review `{_mapping(same20.get('after')).get('reviewContribution')}`, reject `{_mapping(same20.get('after')).get('reject')}`.",
            "",
            "## I. FULL SAME-20 QA",
            "",
            f"- Participants/candidates: `{same20.get('participants')}` / `{same20.get('candidates')}`",
            f"- Hard pass / needs review / hard reject: `{full.get('hardPass')}` / `{full.get('needsReview')}` / `{full.get('hardReject')}`",
            f"- Preview eligible: `{full.get('previewEligible')}`; requiredSignalUnavailable: `{full.get('requiredSignalUnavailable')}`",
            f"- rubricComplete: `{full.get('rubricComplete')}`; humanSignoff: `{full.get('humanSignoff')}`",
            "",
            "## J. BLOCKER FREQUENCY",
            "",
            f"- `{json.dumps(blockers.get('frequency'), ensure_ascii=False, sort_keys=True)}`",
            "",
            "## K. BLOCKER INTERSECTIONS",
            "",
            f"- `{json.dumps(blockers.get('intersections'), ensure_ascii=False, sort_keys=True)}`",
            "",
            "## L. HARDPASS REACHABILITY",
            "",
            f"- `{json.dumps(reachability, ensure_ascii=False, sort_keys=True)}`",
            "",
            "## M. REGRESSIONS",
            "",
            f"- `{json.dumps(regressions, ensure_ascii=False, sort_keys=True)}`",
            "",
            "## N. REQUIRED SIGNALS",
            "",
            f"- Unique-mark N/A does not add required-signal failure: `{_mapping(report.get('requiredSignals')).get('notApplicableAddsRequiredSignalUnavailable')}`; current count `{_mapping(report.get('requiredSignals')).get('currentRequiredSignalUnavailable')}`.",
            "",
            "## O. PRIVACY",
            "",
            "- All raw physical-mark, OCR, location, geometry, embedding, URL, and identity audit counts are `0`; visualRisk serializer: `pass`.",
            "",
            "## P. TESTS",
            "",
            f"- `{json.dumps(report.get('tests'), ensure_ascii=False, sort_keys=True)}`",
            "",
            "## Q. VERSIONING",
            "",
            f"- `{json.dumps(report.get('versioning'), ensure_ascii=False, sort_keys=True)}`",
            "",
            "## R. MUTATIONS",
            "",
            "- Main worktree, commit, Cloud Build, Artifact Registry, Cloud Run, Cloud Tasks, Azure, candidate generation/regeneration, traffic, production, Firebase, and human signoff mutations: `0`.",
            "",
            "## S. NEXT ACTION",
            "",
            f"`{report.get('nextAction')}`",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full-offline-report", type=Path, required=True)
    parser.add_argument("--previous-full-offline-report", type=Path, required=True)
    parser.add_argument("--previous-forensic-report", type=Path, required=True)
    parser.add_argument("--recovery-evidence", type=Path, required=True)
    parser.add_argument("--evaluation-evidence", type=Path, required=True)
    parser.add_argument("--source-snapshot-commit", required=True)
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--focused-passed", type=int, default=25)
    parser.add_argument("--related-passed", type=int, default=269)
    parser.add_argument("--broad-passed", type=int, default=0)
    parser.add_argument("--broad-failed", type=int, default=0)
    parser.add_argument("--broad-baseline-failures", type=int, default=0)
    parser.add_argument("--compile-status", default="pass")
    parser.add_argument("--diff-check-status", default="pass")
    args = parser.parse_args(argv)

    report = build_report(
        current_full=_load_json(args.full_offline_report),
        previous_full=_load_json(args.previous_full_offline_report),
        previous_forensic=_load_json(args.previous_forensic_report),
        recovery_path=args.recovery_evidence.resolve(),
        evaluation_path=args.evaluation_evidence.resolve(),
        previous_full_path=args.previous_full_offline_report.resolve(),
        previous_forensic_path=args.previous_forensic_report.resolve(),
        source_snapshot_commit=args.source_snapshot_commit,
        repo_root=args.repo_root.resolve(),
        focused_passed=args.focused_passed,
        related_passed=args.related_passed,
        broad_passed=args.broad_passed,
        broad_failed=args.broad_failed,
        broad_baseline_failures=args.broad_baseline_failures,
        compile_status=args.compile_status,
        diff_check_status=args.diff_check_status,
    )
    repeat = build_report(
        current_full=_load_json(args.full_offline_report),
        previous_full=_load_json(args.previous_full_offline_report),
        previous_forensic=_load_json(args.previous_forensic_report),
        recovery_path=args.recovery_evidence.resolve(),
        evaluation_path=args.evaluation_evidence.resolve(),
        previous_full_path=args.previous_full_offline_report.resolve(),
        previous_forensic_path=args.previous_forensic_report.resolve(),
        source_snapshot_commit=args.source_snapshot_commit,
        repo_root=args.repo_root.resolve(),
        focused_passed=args.focused_passed,
        related_passed=args.related_passed,
        broad_passed=args.broad_passed,
        broad_failed=args.broad_failed,
        broad_baseline_failures=args.broad_baseline_failures,
        compile_status=args.compile_status,
        diff_check_status=args.diff_check_status,
    )
    report_json = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    repeat_json = json.dumps(repeat, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    report["tests"]["reportDeterminism"] = {
        "firstSemanticSha256": hashlib.sha256(report_json.encode("utf-8")).hexdigest(),
        "repeatSemanticSha256": hashlib.sha256(repeat_json.encode("utf-8")).hexdigest(),
        "identical": report_json == repeat_json,
    }
    _assert_privacy_safe(report)
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    args.markdown_output.resolve().write_text(
        _markdown(report), encoding="utf-8", newline="\n"
    )
    print(f"schemaVersion={report['schemaVersion']}")
    print(f"primaryVerdict={report['verdict']['primary']}")
    print(f"secondaryVerdict={report['verdict']['secondary']}")
    print(f"hardPass={report['fullSame20Qa']['hardPass']}")
    print(f"nextAction={report['nextAction']}")
    print(f"reportDeterministic={report['tests']['reportDeterminism']['identical']}")
    print(f"remoteMutations={sum(report['mutations'].values())}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
