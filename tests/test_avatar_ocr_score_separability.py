"""CI tests for B3-L10A FLORENCE_OCR_SEQUENCE_SCORE_STUDY_V1. Pure logic: no model, no user image, no label."""

import json
import re
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPO = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
AI = REPO / "lib" / "ai_recommend_model"
if str(AI) not in sys.path:
    sys.path.insert(0, str(AI))

import avatar_dual_channel_v3 as v3  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_ocr_score_separability as st  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_text_policy_shadow as tp  # noqa: E402
from avatar_generation.analysis.visual_risk import analyze_florence_visual_risk_outputs  # noqa: E402
from avatar_generation.analysis.watermark import evaluate_watermark_risk  # noqa: E402
from avatar_generation.model_adapters import florence2_visual as fv  # noqa: E402

PREREG = REPO / "docs" / "avatar-production" / "b3-l10a-preregistration.md"
REPORT = REPO / "docs" / "avatar-production" / "b3-l10a-ocr-score-separability-report.md"
AGGREGATE = REPO / "docs" / "avatar-production" / "b3-l10a-ocr-score-separability-aggregate-v1.json"
OCR = "<OCR_WITH_REGION>"
OD = "<OD>"
SIZE = (1000, 1000)


def _tasks(boxes, labels, shadow=None):
    payload = {"quad_boxes": [[b[0], b[1], b[2], b[1], b[2], b[3], b[0], b[3]] for b in boxes], "labels": list(labels)}
    if shadow is not None:
        payload["shadowOcrEvidence"] = shadow
    return {OCR: {OCR: payload}, OD: {OD: {"bboxes": [], "labels": []}}}


def _shadow(score=-0.4, regions=1, **over):
    s = {"scoreSource": st.SCORE_SOURCE, "scoreCalibrated": False, "scoreAvailable": True, "generationMode": "beam_search", "numBeams": 3,
         "lengthPenalty": 1.0, "regionCount": regions, "attributionScope": "single_region" if regions == 1 else "whole_sequence",
         "outputTokenCount": 12, "rawSequenceScore": score}
    s.update(over)
    return s


class _Gen:
    def __init__(self, seqs, scores=None):
        self.sequences = seqs
        if scores is not None:
            self.sequences_scores = scores


# ------------------------------------------------------------ 1-3 score never becomes confidence


def test_raw_sequence_score_never_feeds_region_confidence():
    parsed = fv._attach_shadow_ocr_evidence({OCR: {"quad_boxes": [[1, 1, 9, 1, 9, 9, 1, 9]], "labels": ["x"]}}, OCR, _Gen([[1, 2, 3]], [-0.3]), [[1, 2, 3]], 1.0)
    assert parsed[OCR]["shadowOcrEvidence"]["rawSequenceScore"] == -0.3
    assert "scores" not in parsed[OCR] and "confidences" not in parsed[OCR]
    analysis = analyze_florence_visual_risk_outputs({OCR: parsed, OD: {OD: {"bboxes": [], "labels": []}}}, image_size=SIZE)
    assert [r.confidence for r in analysis.regions] == [None]
    assert analysis.shadow_ocr_evidence["rawSequenceScore"] == -0.3


def test_confidence_band_remains_unknown():
    tasks = _tasks([[300, 450, 700, 560]], ["x"], _shadow(score=-0.05))
    analysis = analyze_florence_visual_risk_outputs(tasks, image_size=SIZE)
    decision = evaluate_watermark_risk(analysis.regions, source_regions=(), image_size=SIZE)
    assert decision.evidence["confidenceBands"] == {"unknown": 1}
    assert decision.evidence["regionEvidence"][0]["confidenceBand"] == "unknown"


def test_score_calibrated_must_remain_false():
    assert st.SCORE_CALIBRATED is False and fv.SHADOW_OCR_SCORE_SOURCE == st.SCORE_SOURCE
    parsed = fv._attach_shadow_ocr_evidence({OCR: {"quad_boxes": [], "labels": []}}, OCR, _Gen([[1]], [-1.0]), [[1]], None)
    assert parsed[OCR]["shadowOcrEvidence"]["scoreCalibrated"] is False
    assert not st.usable(_shadow(scoreCalibrated=True))
    assert st.eligible(st.threshold_metrics(0.0, "positive_higher", [-1.0], [0.5], [0.5]), coverage_rate=1.0, calibrated_flags={True}, decision_diff=0)["criteria"]["E"] is False


# ------------------------------------------------------------ 4-5 attribution scope


def test_whole_sequence_scope_cannot_masquerade_as_per_region():
    assert not st.usable(_shadow(regions=2))
    assert not st.usable(_shadow(attributionScope="whole_sequence"))
    with pytest.raises(ValueError):
        st.score_of(_shadow(regions=3))
    assert st.inventory([{"shadow": _shadow(regions=2)}])["usableSingleRegion"] == 0


def test_single_region_only_when_region_count_is_one():
    for n in (0, 1, 2, 5):
        parsed = fv._attach_shadow_ocr_evidence({OCR: {"quad_boxes": [[0] * 8] * n, "labels": ["a"] * n}}, OCR, _Gen([[1]], [-0.2]), [[1]], 1.0)
        sh = parsed[OCR]["shadowOcrEvidence"]
        assert sh["regionCount"] == n and sh["attributionScope"] == ("single_region" if n == 1 else "whole_sequence")
        assert st.usable(sh) == (n == 1)


# ------------------------------------------------------------ 6-7 decision neutrality


def test_unsupported_scoring_kwargs_fallback_remains_decision_neutral():
    parsed = fv._attach_shadow_ocr_evidence({OCR: {"quad_boxes": [[0] * 8], "labels": ["a"]}}, OCR, None, [[1, 2]], 1.0)
    sh = parsed[OCR]["shadowOcrEvidence"]
    assert sh["scoreAvailable"] is False and sh["scoreUnavailableReason"] == "scores_not_supported_by_runtime"
    assert "rawSequenceScore" not in sh and sh["scoreCalibrated"] is False
    assert not st.usable(sh)
    tasks = {OCR: parsed, OD: {OD: {"bboxes": [], "labels": []}}}
    a = analyze_florence_visual_risk_outputs(tasks, image_size=SIZE)
    assert evaluate_watermark_risk(a.regions, source_regions=(), image_size=SIZE).watermark_qa_action == "allow"


def test_score_threshold_cannot_change_watermark_action():
    for action in ("allow", "review", "reject"):
        for score in (-9.0, -0.5, 0.0):
            assert st.watermark_action_with_score(action, score, -0.5, "positive_higher") == action
            assert st.watermark_action_with_score(action, score, -0.5, "positive_lower") == action
    with pytest.raises(ValueError):
        st.watermark_action_with_score("escalate", 0.0, 0.0, "positive_higher")
    # the canonical action is computed without the score in the evaluator's row builder
    tasks = _tasks([[300, 450, 700, 560]], ["x"], _shadow(score=0.0))
    a = analyze_florence_visual_risk_outputs(tasks, image_size=SIZE)
    assert evaluate_watermark_risk(a.regions, source_regions=(), image_size=SIZE).watermark_qa_action == "allow"


# ------------------------------------------------------------ 8-9 extraction inputs


@pytest.mark.parametrize("field", sorted(sel.HUMAN_ONLY_FIELDS))
def test_human_labels_cannot_enter_score_extraction(field):
    with pytest.raises(ValueError):
        st.extract_shadow(_tasks([], [], _shadow()), **{field: "yes"})


@pytest.mark.parametrize("field", ("family", "familyCode", "constructFamily", "groundTruth", "groupKey"))
def test_construct_family_cannot_enter_score_extraction(field):
    with pytest.raises(ValueError):
        st.extract_shadow(_tasks([], [], _shadow()), **{field: "TEXT_WATERMARK_OPAQUE"})
    out = st.extract_shadow(_tasks([[0, 0, 1, 1]], ["SECRET"], _shadow()))
    assert set(out) <= st.SHADOW_FIELDS and "SECRET" not in json.dumps(out)


# ------------------------------------------------------------ 10-13 selection / validation guards


def test_holdout_score_unavailable_to_selector():
    sig = st.select_threshold.__code__.co_varnames[: st.select_threshold.__code__.co_argcount]
    assert sig == ("development_table", "direction_")
    table = [dict(st.threshold_metrics(t, "positive_higher", [-1.0, -0.9], [-0.2, -0.1], [-0.3, -0.1]), eligibility={"eligible": True}) for t in (-0.5, -0.4)]
    picked = st.select_threshold(table, "positive_higher")
    assert picked["status"] == "SELECTED" and picked["selectedThreshold"] == -0.4  # tie on metrics -> more conservative (higher) boundary
    assert st.candidate_thresholds([-1.0, -0.5, 0.0]) == [round(-1.0 + q, 6) for q in st.QUANTILE_GRID]
    assert st.direction([-1.0, -0.8], [-0.2, -0.1]) == "positive_higher" and st.direction([-0.1], [-0.9]) == "positive_lower"


def test_validation_impossible_before_threshold_freeze(tmp_path):
    with pytest.raises(st.ThresholdNotFrozen):
        st.validation_guard(tmp_path, st.contract_digest(), {"validationScoreValuesPreviouslySeen": False})
    st.write_frozen(tmp_path, {"selectedThreshold": -0.3, "direction": "positive_higher"}, "0" * 64, "1" * 64)
    with pytest.raises(st.ThresholdNotFrozen):
        st.validation_guard(tmp_path, st.contract_digest(), {"validationScoreValuesPreviouslySeen": False})


def test_one_shot_validation_guard(tmp_path):
    digest = st.contract_digest()
    st.write_frozen(tmp_path, {"selectedThreshold": -0.3, "direction": "positive_higher"}, digest, "1" * 64)
    lock = st.validation_guard(tmp_path, digest, {"validationScoreValuesPreviouslySeen": False})
    assert lock.name == "ocr_score_v1_validation_evaluated.lock" not in (sel.HOLDOUT_LOCK_NAME, v3.V3_HOLDOUT_LOCK_NAME, tp.HOLDOUT_LOCK_NAME)
    st.mark_validation_evaluated(lock, digest)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        st.validation_guard(tmp_path, digest, {"validationScoreValuesPreviouslySeen": False})


def test_already_seen_validation_scores_require_new_heldout(tmp_path):
    digest = st.contract_digest()
    st.write_frozen(tmp_path, {"selectedThreshold": -0.3, "direction": "positive_higher"}, digest, "1" * 64)
    for audit in ({"validationScoreValuesPreviouslySeen": True}, {}, {"validationScoreValuesPreviouslySeen": "no"}):
        with pytest.raises(st.ValidationScoresPreviouslySeen):
            st.validation_guard(tmp_path, digest, audit)
    assert st.verdict(True, False, None) == "FLORENCE_SEQUENCE_SCORE_DEVELOPMENT_SEPARABLE_NEW_HELDOUT_REQUIRED"
    assert st.verdict(False, None, None) == "FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING"
    assert st.verdict(True, True, True) == "FLORENCE_SEQUENCE_SCORE_SEPARABILITY_SUPPORTED"
    assert st.verdict(True, True, False) == "FLORENCE_SEQUENCE_SCORE_SEPARABILITY_NOT_SUPPORTED"


# ------------------------------------------------------------ 14-15 privacy / prior versions


def test_aggregate_only_report():
    for path in (REPORT, AGGREGATE, PREREG):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in st.FORBIDDEN_WORDING + ("three-rater", "adjudicated human ground truth", "production-ready"):
            assert phrase not in text, (path.name, phrase)
        assert not re.search(r"P\d{2}_C\d{2}", text) and "AppData" not in text and not re.search(r"[A-Za-z]:\\Users\\", text), path.name
    text = PREREG.read_text(encoding="utf-8")
    assert st.contract_digest()[:12] in text
    for token in (st.VERSION, st.EVIDENCE_LABEL, st.FEATURE_NAME, st.VALIDATION_SPLIT_NAME, "ocr_score_v1_validation_evaluated.lock", "0.10", "0.90"):
        assert token in text
    if AGGREGATE.exists():
        report = json.loads(AGGREGATE.read_text(encoding="utf-8"))
        assert bench.privacy_violations(report) == []
        def keys(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    yield k
                    yield from keys(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from keys(v)
        present = set(keys(report))
        assert not ({"rows", "tasks", "labels", "quad_boxes", "shadow", "scores"} & present)
        assert report["confidenceBandChanged"] is False and report["watermarkPolicyChanged"] is False and report["decisionDiff"] == 0
        assert report["scoreSemantics"]["scoreCalibrated"] is False
        assert report["naturalPositiveLimitation"] == "NATURAL_POSITIVE_EVIDENCE_MISSING"
        assert report["graphicalDetectorStudyRequired"] == "GRAPHICAL_DETECTOR_STUDY_REQUIRED"
        assert report["validationEvaluated"] in (0, 1)


def test_prior_results_unchanged():
    assert calib.GATE_VERSION == "owlv2_provisional_shadow_gate_v1" and calib.PROVISIONAL_PRECISION_FLOOR == 0.80
    assert v2.GATE_VERSION == "OWLV2_CONTROLLED_CHALLENGE_GATE_V2" and v2.OVERALL_RECALL_FLOOR == 0.95
    assert v3.V3_VERSION == "AVATAR_WATERMARK_DUAL_CHANNEL_V3" and v3.OWLV2_THRESHOLD == 0.25 and v3.contract_digest().startswith("7e0281db982a")
    assert tp.VERSION == "TEXT_POLICY_SHADOW_V1" and tp.contract_digest().startswith("89514d712ad8")
    assert st.PRIOR_STATUS["V1"] == "OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT"
    assert st.PRIOR_STATUS["V2"] == "OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT"
    assert st.PRIOR_STATUS["V3"] == "V3_DUAL_CHANNEL_FAILED_DEVELOPMENT"
    assert st.PRIOR_STATUS["B3_L9"] == "TEXT_POLICY_SHADOW_HOLDOUT_FAILED"
    assert st.TEXT_POLICY_GAP_STATUS == "TEXT_POLICY_GAP_UNRESOLVED"
