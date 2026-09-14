"""CI tests for B3-L9 TEXT_POLICY_SHADOW_V1. Pure logic: no model, no user image, no label."""

import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_dual_channel_v3 as v3  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_text_policy_shadow as tp  # noqa: E402
import avatar_text_policy_shadow_eval as ev  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PREREG = REPO / "docs" / "avatar-production" / "b3-l9-preregistration.md"
REPORT = REPO / "docs" / "avatar-production" / "b3-l9-text-policy-shadow-report.md"
AGGREGATE = REPO / "docs" / "avatar-production" / "b3-l9-text-policy-shadow-aggregate-v1.json"


def _region(**over):
    base = {"kind": "text", "confidenceBand": "unknown", "areaBand": "small", "location": "clothing_zone",
            "overlayLike": False, "textQuality": "plausible", "sourceConsistent": None, "repeated": False, "artifactHint": False}
    base.update(over)
    return base


def _evidence(regions):
    return {"ocrDetectionCount": len(regions), "regionEvidence": list(regions)}


T3 = tp.CANDIDATE_BY_ID["T3"]


# ------------------------------------------------------------ 1-3 escalate-only


def test_candidate_only_escalates_allow_to_review():
    ev_doc = _evidence([_region()])
    assert tp.proposed_review(T3, ev_doc) is True
    assert tp.shadow_action("allow", True) == "review"
    assert tp.shadow_action("allow", False) == "allow"
    assert tp.shadow_action("allow", True) != "reject"


def test_review_never_downgrades():
    assert tp.shadow_action("review", False) == "review"
    assert tp.shadow_action("review", True) == "review"


def test_reject_never_downgrades():
    assert tp.shadow_action("reject", False) == "reject"
    assert tp.shadow_action("reject", True) == "reject"
    with pytest.raises(ValueError):
        tp.shadow_action("unknown", True)


# ------------------------------------------------------------ 4-9 evidence discipline


def test_raw_ocr_presence_alone_cannot_trigger():
    # A text region exists but with the clean-avatar profile (large / corner overlay etc.).
    for cand in tp.CANDIDATES:
        assert tp.proposed_review(cand, _evidence([_region(areaBand="large", location="central")])) is False
    assert tp.proposed_review(T3, _evidence([_region(location="corner", overlayLike=True)])) is False
    assert tp.proposed_review(T3, _evidence([])) is False
    # every candidate requires more than kind == text
    for cand in tp.CANDIDATES:
        assert cand.locations != tp.ALL_LOCATIONS or cand.single_region or cand.overlay_like is not None or cand.area_bands != tp.ALL_AREA_BANDS


def test_raw_transcription_cannot_enter_predicate():
    for key in ("token_key", "labels", "quad_boxes", "text", "ocr_text", "rawLabel"):
        with pytest.raises(ValueError):
            tp.proposed_review(T3, _evidence([_region(**{key: "SAMPLE"})]))
        with pytest.raises(ValueError):
            tp.proposed_review(T3, {**_evidence([_region()]), key: "SAMPLE"})
    assert not any(w in json.dumps(tp.candidate_definitions()) for w in ("SAMPLE", "NOVA"))


@pytest.mark.parametrize("field", sorted(sel.HUMAN_ONLY_FIELDS))
def test_human_fields_forbidden(field):
    with pytest.raises(ValueError):
        tp.candidate_action(T3, "allow", _evidence([_region()]), **{field: "yes"})
    with pytest.raises(ValueError):
        tp.proposed_review(T3, _evidence([_region(**{field: "yes"})]))


@pytest.mark.parametrize("field", ("family", "familyCode", "constructFamily"))
def test_family_field_forbidden(field):
    with pytest.raises(ValueError):
        tp.candidate_action(T3, "allow", _evidence([_region()]), **{field: "TEXT_WATERMARK_OPAQUE"})


@pytest.mark.parametrize("field", ("groundTruthBox", "groundTruthBoxes", "groundTruth", "baseOpaqueId", "groupKey", "split"))
def test_ground_truth_and_split_fields_forbidden(field):
    with pytest.raises(ValueError):
        tp.candidate_action(T3, "allow", _evidence([_region()]), **{field: 1})


def test_confidence_unknown_is_not_treated_as_probability():
    assert "confidenceBand" not in tp.ALLOWED_RUNTIME_FIELDS
    assert "sourceConsistent" not in tp.ALLOWED_RUNTIME_FIELDS
    for cand in tp.CANDIDATES:
        a = tp.proposed_review(cand, _evidence([_region(confidenceBand="unknown")]))
        b = tp.proposed_review(cand, _evidence([_region(confidenceBand="high")]))
        c = tp.proposed_review(cand, _evidence([_region(sourceConsistent=True)]))
        assert a == b == c
    with pytest.raises(ValueError):
        tp.Candidate("TX", 9, frozenset({"corner"}), None, True, frozenset({"small"}), confidence_bands=frozenset({"unknown"}))


# ------------------------------------------------------------ 10-11 accounting


def test_repeated_canonical_reject_preserved():
    rows = [{"canonicalAction": "reject", "proposed": p} for p in (True, False)] * 6
    out = tp.repeated_preservation(rows)
    assert out == {"n": 12, "rejectPreserved": 12, "rate": 1.0}
    assert tp.safety(rows) == {"hardRejectBypass": 0, "artifactRegressions": 0}


def test_clean_existing_review_not_counted_as_new_burden():
    items = [
        {"canonicalAction": "allow", "proposed": True},
        {"canonicalAction": "allow", "proposed": False},
        {"canonicalAction": "review", "proposed": True},
        {"canonicalAction": "reject", "proposed": True},
    ]
    out = tp.clean_burden(items)
    assert out["newAllowToReview"] == 1 and out["newReviewRate"] == 0.25
    assert out["existingCanonicalBurdenNotCounted"] == 2
    assert out["v3"]["review"] == 2 and out["v3"]["reject"] == 1


# ------------------------------------------------------------ 12-16 candidate contract


def test_candidate_ordering_frozen():
    assert tp.VERSION == "TEXT_POLICY_SHADOW_V1" and tp.CANDIDATE_SET_VERSION == "TEXT_POLICY_CANDIDATES_V1"
    assert [c.id for c in tp.CANDIDATES] == ["T1", "T2", "T3", "T4"]
    assert [c.rank for c in tp.CANDIDATES] == [1, 2, 3, 4]
    assert tp.CANDIDATES[0].locations == frozenset({"corner", "edge"}) and tp.CANDIDATES[0].overlay_like is True
    assert tp.CANDIDATES[1].locations == frozenset({"central"}) and tp.CANDIDATES[1].single_region
    assert tp.CANDIDATES[2].locations == frozenset({"central", "clothing_zone"}) and tp.CANDIDATES[2].overlay_like is False
    assert tp.CANDIDATES[3].locations == tp.ALL_LOCATIONS and tp.CANDIDATES[3].area_bands == frozenset({"small", "medium"})
    digest = tp.contract_digest()
    assert tp.contract_digest() == digest
    text = PREREG.read_text(encoding="utf-8")
    assert digest[:12] in text
    for token in (tp.VERSION, tp.CANDIDATE_SET_VERSION, "DEVELOPMENT_DESIGNED", "text_policy_v1_holdout_evaluated.lock",
                  "NATURAL_POSITIVE_EVIDENCE_MISSING", "GRAPHICAL_DETECTOR_STUDY_REQUIRED", "0.10", "0.90"):
        assert token in text


def test_strictest_eligible_selected():
    table = {
        "T1": {"eligible": False},
        "T2": {"eligible": True},
        "T3": {"eligible": True},
        "T4": {"eligible": True},
    }
    assert tp.select_candidate(table)["selectedCandidate"] == "T2"
    table["T2"]["eligible"] = False
    assert tp.select_candidate(table)["selectedCandidate"] == "T3"
    assert tp.select_candidate({k: {"eligible": False} for k in table})["status"] == "NONE"


def test_holdout_cannot_influence_candidate_selection():
    # selection takes only the development table; holdout metrics are not an input
    sig = tp.select_candidate.__code__.co_varnames[: tp.select_candidate.__code__.co_argcount]
    assert sig == ("development_table",)
    assert tp.contract_digest() == tp.contract_digest()


def test_holdout_impossible_without_selected_freeze(tmp_path):
    with pytest.raises(tp.CandidateNotFrozen):
        tp.holdout_guard(tmp_path, tp.contract_digest())
    tp.write_selected_marker(tmp_path, "T3", "0" * 64, "1" * 64)
    with pytest.raises(tp.CandidateNotFrozen):
        tp.holdout_guard(tmp_path, tp.contract_digest())


def test_one_shot_holdout_lock(tmp_path):
    digest = tp.contract_digest()
    tp.write_selected_marker(tmp_path, "T3", digest, "1" * 64)
    lock = tp.holdout_guard(tmp_path, digest)
    assert lock.name == "text_policy_v1_holdout_evaluated.lock"
    assert lock.name not in (sel.HOLDOUT_LOCK_NAME, v3.V3_HOLDOUT_LOCK_NAME)
    tp.mark_holdout_evaluated(lock, digest)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        tp.holdout_guard(tmp_path, digest)


# ------------------------------------------------------------ 17-18 holdout arithmetic


def test_one_of_eight_clean_new_review_fails_holdout_criterion():
    clean = tp.clean_burden([{"canonicalAction": "allow", "proposed": i == 0} for i in range(8)])
    assert clean["newReviewRate"] == 0.125
    elig = tp.eligible(clean, {"TEXT_WATERMARK_OPAQUE": 1.0, "TEXT_WATERMARK_TRANSLUCENT": 1.0}, 1.0, hard_reject_bypass=0, artifact_regressions=0)
    assert elig["criteria"]["A"] is False and not elig["eligible"]
    clean0 = tp.clean_burden([{"canonicalAction": "allow", "proposed": False} for _ in range(8)])
    assert tp.eligible(clean0, {"TEXT_WATERMARK_OPAQUE": 1.0, "TEXT_WATERMARK_TRANSLUCENT": 1.0}, 1.0, hard_reject_bypass=0, artifact_regressions=0)["eligible"]


def test_eight_of_eight_positive_required_at_n8():
    clean0 = tp.clean_burden([{"canonicalAction": "allow", "proposed": False} for _ in range(8)])
    seven = tp.family_recall([{"canonicalAction": "allow", "proposed": i < 7} for i in range(8)])
    assert seven["rate"] == 0.875
    elig = tp.eligible(clean0, {"TEXT_WATERMARK_OPAQUE": seven["rate"], "TEXT_WATERMARK_TRANSLUCENT": 1.0}, 1.0, hard_reject_bypass=0, artifact_regressions=0)
    assert elig["criteria"]["B"] is False
    assert tp.family_recall([{"canonicalAction": "allow", "proposed": True} for _ in range(8)])["rate"] == 1.0
    # development N=12: 11/12 = 0.917 passes, 10/12 fails
    assert tp.family_recall([{"canonicalAction": "allow", "proposed": i < 11} for i in range(12)])["rate"] >= 0.90
    assert tp.family_recall([{"canonicalAction": "allow", "proposed": i < 10} for i in range(12)])["rate"] < 0.90


# ------------------------------------------------------------ 19-23 frozen prior versions / graphical channel


def test_v1_unchanged():
    assert calib.GATE_VERSION == "owlv2_provisional_shadow_gate_v1"
    assert calib.PROVISIONAL_PRECISION_FLOOR == 0.80 and calib.CLEAN_NEGATIVE_NEW_REVIEW_CEILING == 0.10
    assert tp.PRIOR_STATUS["V1"] == "OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT"


def test_v2_unchanged():
    assert v2.GATE_VERSION == "OWLV2_CONTROLLED_CHALLENGE_GATE_V2" and v2.OVERALL_RECALL_FLOOR == 0.95
    assert tp.PRIOR_STATUS["V2"] == "OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT"


def test_v3_unchanged():
    assert v3.V3_VERSION == "AVATAR_WATERMARK_DUAL_CHANNEL_V3" and v3.OWLV2_THRESHOLD == 0.25
    assert v3.contract_digest().startswith("7e0281db982a")
    assert tp.PRIOR_STATUS["V3"] == "V3_DUAL_CHANNEL_FAILED_DEVELOPMENT"
    assert tp.PRIOR_STATUS["H4_DUAL_CHANNEL"] == "H4_DUAL_CHANNEL_SHADOW_NOT_SUPPORTED"


def test_graphical_threshold_remains_0_25_if_v4_recomposed():
    assert tp.V4_OWLV2_THRESHOLD == 0.25 == v3.OWLV2_THRESHOLD
    assert tp.v4_action("allow", proposed_text_review=False, graphical_hit=True) == "review"
    assert tp.v4_action("allow", proposed_text_review=True, graphical_hit=False) == "review"
    assert tp.v4_action("reject", proposed_text_review=False, graphical_hit=False) == "reject"
    assert tp.v4_action("allow", proposed_text_review=False, graphical_hit=False) == "allow"
    with pytest.raises(tp.HoldoutNotPassed):
        tp.require_holdout_pass({"holdoutVerdict": "TEXT_POLICY_SHADOW_HOLDOUT_FAILED"})


def test_no_graphical_threshold_or_prompt_tuning():
    assert tp.V4_PROMPTS == sel.PROMPTS == v3.PROMPTS
    with pytest.raises(ValueError):
        tp.v4_graphical_hit([{"box": [0, 0, 1, 1], "label": "a logo", "score": 0.9}], threshold=0.20)
    assert tp.v4_graphical_hit([{"box": [0, 0, 1, 1], "label": "a logo", "score": 0.25}]) is True
    assert tp.v4_graphical_hit([{"box": [0, 0, 1, 1], "label": "a face", "score": 0.9}]) is False


# ------------------------------------------------------------ 24 privacy


def test_aggregate_only_report():
    forbidden = ("PRODUCTION_VALIDATED", "LIVE_POLICY_READY", "PRODUCTION_PRECISION_PROVEN", "LIVE_READY",
                 "production recall proven", "production policy validated", "three-rater", "adjudicated human ground truth",
                 "production-ready")
    for path in (REPORT, AGGREGATE, PREREG):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, (path.name, phrase)
        assert not re.search(r"P\d{2}_C\d{2}", text), path.name
        assert not re.search(r"[A-Za-z]:\\Users\\", text), path.name
        assert "AppData" not in text and "quad_boxes" not in text
    if AGGREGATE.exists():
        report = json.loads(AGGREGATE.read_text(encoding="utf-8"))
        assert bench.privacy_violations(report) == []
        assert "regionEvidence" not in json.dumps(report) and "detections" not in json.dumps(report)
        assert report["naturalPositiveLimitation"] == "NATURAL_POSITIVE_EVIDENCE_MISSING"
        assert report["graphicalDetectorStudyRequired"] == "GRAPHICAL_DETECTOR_STUDY_REQUIRED"
        assert report["designation"] == "DEVELOPMENT_DESIGNED"
        assert report["contractDigestPrefix"] == tp.contract_digest()[:12]
        assert report["holdoutEvaluated"] in (0, 1)
        if report.get("v4"):
            assert report["v4"]["owlv2Threshold"] == 0.25
