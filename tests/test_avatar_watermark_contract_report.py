import sys
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
SCRIPTS_DIR = REPO_ROOT / "scripts"
for path in (AI_MODEL_DIR, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from avatar_watermark_contract_offline import build_offline_contract_report  # noqa: E402


def _machine_rows():
    return [
        {
            "participantOrdinal": f"P{participant:02d}",
            "candidateOrdinal": candidate,
            "watermarkDecisionClass": "ambiguous_text_evidence",
            "watermarkEvidenceClasses": ["ambiguous_text_evidence"],
            "sourceConsistency": "inconsistent",
            "textLogoWatermarkRisk": "medium",
            "logoTextWatermarkRisk": "medium",
            "visualRiskStatus": "needs_review",
            "hardReject": False,
            "needsReview": True,
            "selectionTier": "needs_review",
        }
        for participant in range(1, 6)
        for candidate in range(1, 5)
    ]


def _context():
    return {
        "backgroundLeakageRisk": {
            "before": {"medium": 20},
            "after": {"low": 20},
            "regressionCount": 0,
        },
        "identifiabilityRisk": {
            "before": {"low": 8, "medium": 12},
            "after": {"low": 8, "medium": 12},
            "regressionCount": 0,
        },
        "privacyQa": {
            "before": {"pass": 8, "needs_review": 12},
            "after": {"pass": 8, "needs_review": 12},
        },
        "remainingBlockers": [
            "BLOCKED_TRAIT_POLICY_CONTRACT",
            "identifiability_review_band",
        ],
        "humanSignoff": False,
    }


def test_offline_report_separates_watermark_action_from_v9_selection_outcome():
    report = build_offline_contract_report(
        _machine_rows(),
        evaluation_snapshot={
            "verdict": "BLOCKED_QA_CALIBRATION_DATA",
            "counts": {
                "hardPass": 0,
                "softPass": 0,
                "needsReview": 20,
                "hardReject": 0,
            },
            "requiredSignalUnavailable": 0,
            "rubricComplete": True,
            "humanSignoff": False,
        },
        corrected_stack_context=_context(),
    )

    assert report["schemaVersion"] == "g004_watermark_artifact_only_offline_v1"
    assert report["candidateCount"] == 20
    assert report["before"]["watermarkQaActions"] == {"review": 20}
    assert report["after"]["watermarkQaActions"] == {"allow": 20}
    assert report["before"]["textLogoWatermarkRisk"] == {"medium": 20}
    assert report["after"]["textLogoWatermarkRisk"] == {"low": 20}
    assert report["after"]["visualRiskStatusContribution"] == {"diagnostic_only": 20}
    assert report["after"]["candidateQASignalNeedsReviewFromWatermark"] == {"false": 20}
    assert report["after"]["qaOutcome"] == {
        "hardPass": 0,
        "softPass": 0,
        "needsReview": 20,
        "hardReject": 0,
        "basis": "existing_v9_selection_tier_non_watermark_gates_not_rerun",
    }
    assert report["causalReviewAfter"]["watermarkArtifactReview"] == 0
    assert report["requiredRunState"]["requiredSignalUnavailable"] == 0
    assert report["requiredRunState"]["rubricComplete"] is True
    assert report["requiredRunState"]["humanSignoff"] is False
    assert report["regressionChecks"]["backgroundLeakageRisk"]["regressionCount"] == 0
    assert report["regressionChecks"]["identifiabilityRisk"]["regressionCount"] == 0
    assert report["rows"][0]["watermarkQaAction"] == "allow"
    assert report["rows"][0]["runtimeNeedsReviewFromWatermark"] is False
    assert all(value == 0 for value in report["mutations"].values())
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in ("raw", "bbox", "coordinate", "uid", "email", "http://", "gs://"):
        assert forbidden not in serialized
