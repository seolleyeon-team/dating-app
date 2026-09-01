import json
import hashlib
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.trait_policy import TRAIT_QA_POLICY_VERSION  # noqa: E402
from scripts.avatar_g004_trait_applicability_offline import (  # noqa: E402
    CURRENT_QA_CONTRACT_VERSION,
    OFFLINE_REPORT_VERSION,
    build_full_offline_report,
    recompute_candidate_qa,
)


CANONICAL_AZURE = {
    "provider": "azure",
    "generationBackend": "azure_gpt_image_2",
    "modelFamily": "gpt-image-2",
    "sourceInputMode": "storage_normalized_original_direct",
    "uploadNormalization": "existing_avatar_media_ingestion",
    "preGenerationTransform": "none",
    "pipelineMode": "azure_gpt_image_2",
    "legacyTraitExtraction": False,
    "legacyReferencePreprocessing": False,
    "legacyFlux": False,
    "traitQaMode": "disabled_by_pipeline",
    "traitQaAuthority": "server",
}


def _debug(*, identity_decision="low_similarity_risk", identity_reliable=True):
    return {
        "modelAvailability": {
            "faceDetector": "available",
            "visualRisk": "available",
            "clipSafety": "available",
            "localSafetyRisk": "available",
            "faceSimilarity": "available",
            "dino": "unavailable",
            "mediapipe": "available",
        },
        "scores": {
            "faceSimilarityObservedScore": 0.12,
            "faceSimilarityDecision": identity_decision,
            "perceptualSimilarityScore": 0.20,
        },
        "visualRiskStatus": "needs_review",
        "watermarkDecisionClass": "ambiguous_text_evidence",
        "watermarkEvidenceClasses": ["ambiguous_text_evidence"],
        "watermarkEvidence": {
            "sourceConsistency": "inconsistent",
            "ocrDetectionCount": 1,
        },
    }


def _old_qa(**overrides):
    value = {
        "adultQa": "pass",
        "childlikeRisk": "low",
        "beautificationRisk": "low",
        "brandQa": "pass",
        "cropConsistency": "pass",
        "cropIsolationQuality": "pass",
        "privacyQa": "pass",
        "identifiabilityRisk": "low",
        "backgroundLeakageRisk": "medium",
        "secondaryFaceLeakageRisk": "low",
        "uniqueMarkCopyRisk": "low",
        "logoTextWatermarkRisk": "medium",
        "textLogoWatermarkRisk": "medium",
        "previewAllowed": False,
        "requiresHumanReview": True,
        "selectionTier": "needs_review",
        "reviewReasons": ["actual_qa_signal_review"],
        "rejectReasons": [],
        "debug": _debug(),
    }
    value.update(overrides)
    return value


def _candidate(*, participant="P01", ordinal=1, qa=None):
    return {
        "participantOrdinal": participant,
        "candidateOrdinal": ordinal,
        "qa": qa or _old_qa(),
        "selectionTier": "needs_review",
        "previewExposed": False,
    }


def test_offline_recompute_known_safe_row_is_hard_pass_with_trait_na():
    row = recompute_candidate_qa(
        _candidate(),
        source_contract=CANONICAL_AZURE,
        corrected_stack_context={"backgroundLeakageRisk": {"after": {"low": 1}}},
    )

    assert row["traitQaApplicability"] == "not_applicable"
    assert row["traitQaAction"] == "allow"
    assert row["hardPass"] is True
    assert row["hardReject"] is False
    assert row["previewAllowed"] is True
    assert row["typedReviewReasons"] == []


def test_offline_recompute_known_review_row_does_not_copy_stale_final_status():
    row = recompute_candidate_qa(
        _candidate(
            qa=_old_qa(
                identifiabilityRisk="medium",
                privacyQa="needs_review",
                debug=_debug(
                    identity_decision="review_similarity",
                    identity_reliable=False,
                ),
            )
        ),
        source_contract=CANONICAL_AZURE,
        corrected_stack_context={"backgroundLeakageRisk": {"after": {"low": 1}}},
    )

    assert row["identifiabilityRisk"] == "medium"
    assert row["hardPass"] is False
    assert row["hardReject"] is False
    assert row["selectionTier"] == "needs_review"
    assert "face_similarity_review_band" in row["typedReviewReasons"]
    assert "actual_qa_signal_review" not in row["typedReviewReasons"]


def test_offline_recompute_trait_unavailable_fails_closed():
    row = recompute_candidate_qa(
        _candidate(),
        source_contract={
            "pipelineMode": "flux",
            "traitQaMode": "enabled",
            "traitQaAuthority": "server",
        },
        corrected_stack_context={"backgroundLeakageRisk": {"after": {"low": 1}}},
    )

    assert row["traitQaApplicability"] == "unavailable"
    assert row["traitQaAction"] == "review"
    assert row["hardPass"] is False
    assert row["hardReject"] is False
    assert "source_and_candidate_trait_evidence_missing" in row["typedReviewReasons"]


def test_offline_recompute_known_watermark_reject_is_hard_reject():
    row = recompute_candidate_qa(
        _candidate(
            qa=_old_qa(
                logoTextWatermarkRisk="high",
                textLogoWatermarkRisk="high",
                debug={
                    **_debug(),
                    "watermarkDecisionClass": "overlay_watermark",
                    "watermarkEvidenceClasses": ["overlay_watermark"],
                },
            )
        ),
        source_contract=CANONICAL_AZURE,
        corrected_stack_context={"backgroundLeakageRisk": {"after": {"low": 1}}},
    )

    assert row["hardReject"] is True
    assert row["hardPass"] is False
    assert "logo_text_watermark" in row["hardRejectReasons"]


def test_full_offline_report_uses_exact_same_twenty_and_current_versions():
    rows = []
    for participant_number in range(1, 6):
        for candidate_number in range(1, 5):
            rows.append(
                _candidate(
                    participant=f"P{participant_number:02d}",
                    ordinal=candidate_number,
                )
            )
    artifact = {
        "runId": "G004-AZURE-CAL-20260824-001",
        "azureCallCount": 20,
        "participantCount": 5,
        "candidateCount": 20,
        "sourceGenerationChecks": {
            "preQaCount": 20,
            "preflightCount": 5,
            "referencesExposed": False,
        },
        "qaEvaluation": {
            "rows": [
                {
                    "participantOrdinal": row["participantOrdinal"],
                    "candidates": [row],
                }
                for row in rows
            ]
        },
    }
    report = build_full_offline_report(
        artifact,
        source_contract=CANONICAL_AZURE,
        corrected_stack_context={"backgroundLeakageRisk": {"after": {"low": 20}}},
        provenance={"sourceSnapshotCommit": "62196951e86af7576540c8e2d1eb547d77ce48a0"},
    )

    assert report["schemaVersion"] == OFFLINE_REPORT_VERSION
    assert report["provenance"]["qaContractVersion"] == CURRENT_QA_CONTRACT_VERSION
    assert report["provenance"]["traitPolicyVersion"] == TRAIT_QA_POLICY_VERSION
    assert report["same20"]["participantCount"] == 5
    assert report["same20"]["candidateCount"] == 20
    assert report["same20"]["after"]["traitQaApplicability"] == {
        "not_applicable": 20
    }
    assert report["fullQaAggregate"]["hardPass"] == 20
    assert report["blockerIntersections"]["zeroBlockerCandidateCount"] == 20
    assert report["hardPassReachability"]["status"] == "consistent"
    assert report["visualRiskSerializerContract"]["status"] == "pass"
    assert report["visualRiskSerializerContract"]["leakedKeys"] == []
    assert report["provenance"]["cloudBuildId"] == "N/A"
    assert report["provenance"]["ociRevisionLabel"] == "N/A"
    assert report["mutations"]["azureGenerationCalls"] == 0
    assert len(report["rows"]) == 20
    assert report["privacy"]["ocr"] == 0
    assert report["privacy"]["uidEmail"] == 0
    serialized_rows = json.dumps(report["rows"], sort_keys=True).lower()
    for forbidden in ("uid", "email", "coordinate", "gs://"):
        assert forbidden not in serialized_rows


def test_unknown_source_contract_never_becomes_trait_na():
    row = recompute_candidate_qa(
        _candidate(),
        source_contract={},
        corrected_stack_context={"backgroundLeakageRisk": {"after": {"low": 1}}},
    )

    assert row["pipelineTraitApplicabilitySource"] == "unknown_provenance_fail_closed"
    assert row["traitQaApplicability"] == "unavailable"
    assert row["traitQaAction"] == "review"


def test_canonical_contract_without_matching_run_provenance_fails_closed():
    artifact = {
        "runId": "G004-AZURE-CAL-20260824-OTHER",
        "azureCallCount": 1,
        "candidateCount": 1,
        "sourceGenerationChecks": {"preQaCount": 1, "referencesExposed": False},
    }
    row = recompute_candidate_qa(
        _candidate(),
        source_contract=CANONICAL_AZURE,
        corrected_stack_context={"backgroundLeakageRisk": {"after": {"low": 1}}},
        provenance_verified=False,
    )

    assert row["traitQaApplicability"] == "unavailable"
    assert row["traitQaAction"] == "review"


def test_full_offline_report_is_deterministic_for_same_input():
    snapshots = [
        _candidate(participant=f"P{participant:02d}", ordinal=candidate)
        for participant in range(1, 6)
        for candidate in range(1, 5)
    ]
    artifact = {
        "runId": "G004-AZURE-CAL-20260824-001",
        "azureCallCount": 20,
        "candidateCount": 20,
        "sourceGenerationChecks": {
            "preQaCount": 20,
            "preflightCount": 5,
            "referencesExposed": False,
        },
        "qaEvaluation": {
            "rows": [
                {"participantOrdinal": row["participantOrdinal"], "candidates": [row]}
                for row in snapshots
            ]
        },
    }
    kwargs = {
        "source_contract": CANONICAL_AZURE,
        "corrected_stack_context": {"backgroundLeakageRisk": {"after": {"low": 20}}},
        "provenance": {"sourceSnapshotCommit": "62196951e86af7576540c8e2d1eb547d77ce48a0"},
    }
    first = build_full_offline_report(artifact, **kwargs)
    second = build_full_offline_report(artifact, **kwargs)
    encode = lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    assert hashlib.sha256(encode(first)).hexdigest() == hashlib.sha256(encode(second)).hexdigest()


@pytest.mark.parametrize("source_contract", [CANONICAL_AZURE, {}])
def test_report_contains_no_stale_final_status_copy(source_contract):
    candidate = _candidate()
    candidate["selectionTier"] = "needs_review"
    candidate["qa"]["selectionTier"] = "needs_review"
    row = recompute_candidate_qa(
        candidate,
        source_contract=source_contract,
        corrected_stack_context={"backgroundLeakageRisk": {"after": {"low": 1}}},
    )

    if source_contract is CANONICAL_AZURE:
        assert row["selectionTier"] == "hard_pass"
    else:
        assert row["selectionTier"] == "needs_review"
