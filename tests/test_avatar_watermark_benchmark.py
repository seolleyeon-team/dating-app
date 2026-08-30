import copy
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from avatar_watermark_benchmark import (  # noqa: E402
    LabelValidationError,
    assert_privacy_safe,
    build_human_label_worksheet,
    compute_metrics,
    extract_machine_evidence,
    validate_label_rows,
    wilson_interval,
)


def _qa(*, source_consistency="inconsistent", decision="ambiguous_text_evidence", risk="medium", hard_reject=False, needs_review=True):
    return {
        "requiresHumanReview": needs_review,
        "rejectReasons": ["logo_text_watermark"] if hard_reject else [],
        "textLogoWatermarkRisk": risk,
        "debug": {
            "visualRiskStatus": "needs_review" if needs_review else "available",
            "watermarkDecisionClass": decision,
            "watermarkEvidenceClasses": [decision],
            "watermarkEvidence": {
                "ocrDetectionCount": 1,
                "confidenceBands": {"unknown": 1},
                "areaBands": {"small": 1},
                "locationBands": {"corner": 1},
                "sourceConsistency": source_consistency,
                "rawLabel": "must never be copied",
            },
        },
        "selectionTier": "needs_review" if needs_review else "hard_reject" if hard_reject else "hard_pass",
    }


def _recovery(candidate_factory=_qa):
    rows = []
    for participant_index in range(1, 6):
        candidates = []
        for candidate_index in range(1, 5):
            candidates.append(
                {
                    "candidateOrdinal": candidate_index,
                    "qa": candidate_factory(),
                    "selectionTier": "needs_review",
                    "privatePath": "must never be copied",
                }
            )
        rows.append(
            {
                "participantOrdinal": f"P{participant_index:02d}",
                "candidates": candidates,
                "uid": "must never be copied",
            }
        )
    return {
        "runId": "G004-AZURE-CAL-20260824-001",
        "participantCount": 5,
        "candidateCount": 20,
        "queueStatus": "PAUSED",
        "generationCallsPerformedByRecovery": 0,
        "watermarkPolicyVersion": "watermark_policy_v2_source_consistency_v1",
        "qaVersion": "avatar_qa_v3_watermark_evidence_v1",
        "qaEvaluation": {"rows": rows},
    }


def _labels(rows, *, candidate_class="no_visible_text_or_logo", source_mark="no", overlay="no", confidence="high"):
    result = []
    for row in rows:
        item = dict(row)
        item.update(
            {
                "candidateVisualClass": candidate_class,
                "sameVisibleMarkInSource": source_mark,
                "overlayAppearance": overlay,
                "humanLabelConfidence": confidence,
            }
        )
        result.append(item)
    return result


def test_worksheet_contains_only_ordinal_rows_and_pending_human_fields():
    worksheet = build_human_label_worksheet(_recovery())

    assert worksheet["candidateCount"] == 20
    assert worksheet["humanLabelStatus"] == "PENDING"
    assert len(worksheet["rows"]) == 20
    assert set(worksheet["rows"][0]) == {
        "participantOrdinal",
        "candidateOrdinal",
        "candidateVisualClass",
        "sameVisibleMarkInSource",
        "overlayAppearance",
        "humanLabelConfidence",
        "location",
    }
    assert all(value is None for value in worksheet["rows"][0].values() if isinstance(value, type(None)))
    assert all(row["candidateVisualClass"] is None for row in worksheet["rows"])


def test_machine_join_extracts_redacted_fields_only():
    machine_rows = extract_machine_evidence(_recovery())

    assert len(machine_rows) == 20
    assert machine_rows[0]["participantOrdinal"] == "P01"
    assert machine_rows[0]["candidateOrdinal"] == 1
    assert machine_rows[0]["watermarkDecisionClass"] == "ambiguous_text_evidence"
    assert machine_rows[0]["selectionTier"] == "needs_review"
    assert "rawLabel" not in machine_rows[0]
    assert "privatePath" not in machine_rows[0]
    assert "uid" not in machine_rows[0]


def test_machine_join_preserves_new_watermark_action_contract_fields():
    recovery = _recovery()
    qa = recovery["qaEvaluation"]["rows"][0]["candidates"][0]["qa"]
    qa["watermarkQaAction"] = "allow"
    qa["logoTextWatermarkRisk"] = "low"
    qa["debug"]["watermarkQaAction"] = "allow"
    qa["debug"]["watermarkPolicyVersion"] = "watermark_policy_v3_generated_artifact_only_v1"

    row = extract_machine_evidence(recovery)[0]

    assert row["watermarkQaAction"] == "allow"
    assert row["logoTextWatermarkRisk"] == "low"
    assert row["watermarkPolicyVersion"] == "watermark_policy_v3_generated_artifact_only_v1"


def test_completed_labels_require_all_fields_but_allow_uncertain():
    rows = _labels(build_human_label_worksheet(_recovery())["rows"])
    rows[0]["candidateVisualClass"] = "uncertain"
    rows[0]["sameVisibleMarkInSource"] = "uncertain"
    rows[0]["overlayAppearance"] = "uncertain"
    rows[0]["humanLabelConfidence"] = "low"
    validate_label_rows(rows, expected_count=20)

    incomplete = copy.deepcopy(rows)
    incomplete[1]["overlayAppearance"] = None
    with pytest.raises(LabelValidationError):
        validate_label_rows(incomplete, expected_count=20)


def test_metrics_exclude_uncertain_human_class_and_use_correct_denominators():
    machine = extract_machine_evidence(_recovery())[:4]
    machine[0]["watermarkDecisionClass"] = "ambiguous_text_evidence"
    machine[0]["textLogoWatermarkRisk"] = "medium"
    machine[0]["hardReject"] = False
    machine[0]["needsReview"] = True
    machine[1]["watermarkDecisionClass"] = "source_consistent_clothing_text"
    machine[1]["sourceConsistency"] = "consistent"
    machine[1]["textLogoWatermarkRisk"] = "low"
    machine[1]["hardReject"] = False
    machine[1]["needsReview"] = False
    machine[2]["watermarkDecisionClass"] = "overlay_watermark"
    machine[2]["textLogoWatermarkRisk"] = "high"
    machine[2]["hardReject"] = True
    machine[2]["needsReview"] = False
    labels = [
        {
            **machine[0],
            "candidateVisualClass": "no_visible_text_or_logo",
            "sameVisibleMarkInSource": "no",
            "overlayAppearance": "no",
            "humanLabelConfidence": "high",
        },
        {
            **machine[1],
            "candidateVisualClass": "benign_text_or_logo",
            "sameVisibleMarkInSource": "yes",
            "overlayAppearance": "no",
            "humanLabelConfidence": "high",
        },
        {
            **machine[2],
            "candidateVisualClass": "clear_watermark_or_brand_overlay",
            "sameVisibleMarkInSource": "not_applicable",
            "overlayAppearance": "yes",
            "humanLabelConfidence": "high",
        },
        {
            **machine[3],
            "candidateVisualClass": "uncertain",
            "sameVisibleMarkInSource": "uncertain",
            "overlayAppearance": "uncertain",
            "humanLabelConfidence": "low",
        },
    ]

    report = compute_metrics(labels, machine, expected_count=4)

    assert report["uncertainHumanCount"] == 1
    assert report["textRegionFalsePositiveRate"]["numerator"] == 1
    assert report["textRegionFalsePositiveRate"]["denominator"] == 1
    assert report["ambiguousReviewFalsePositiveRate"]["numerator"] == 1
    assert report["hardRejectFalsePositiveRate"]["denominator"] == 2
    assert report["watermarkSafetyCaptureRate"]["numerator"] == 1
    assert report["watermarkSafetyCaptureRate"]["denominator"] == 1
    assert report["sourceConsistencyAgreement"]["availableDenominator"] == 2
    assert report["sourceConsistencyAgreement"]["agreementNumerator"] == 2


def test_wilson_interval_handles_empty_single_and_extreme_samples():
    assert wilson_interval(0, 0) == {"low": None, "high": None}
    single = wilson_interval(1, 1)
    assert 0.0 <= single["low"] <= single["high"] <= 1.0
    assert wilson_interval(0, 5)["high"] < 1.0
    assert wilson_interval(5, 5)["low"] > 0.0


def test_privacy_validator_rejects_private_keys_and_urls():
    assert_privacy_safe({"candidateOrdinal": 1, "humanLabelConfidence": "high"})

    with pytest.raises(ValueError):
        assert_privacy_safe({"uid": "private"})
    with pytest.raises(ValueError):
        assert_privacy_safe({"rawOCRText": "private"})
    with pytest.raises(ValueError):
        assert_privacy_safe({"reviewUrl": "https://private.example"})
