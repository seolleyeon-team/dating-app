"""CI tests for B3-L10B FLORENCE_OCR_TWO_FEATURE_STUDY_V1. Pure logic: no model, no user image, no label."""

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
AI = REPO / "lib" / "ai_recommend_model"
if str(AI) not in sys.path:
    sys.path.insert(0, str(AI))

import avatar_dual_channel_v3 as v3  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_ocr_score_separability as st  # noqa: E402
import avatar_ocr_two_feature as tf  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_text_policy_shadow as tp  # noqa: E402
from avatar_generation.analysis.visual_risk import analyze_florence_visual_risk_outputs  # noqa: E402
from avatar_generation.analysis.watermark import evaluate_watermark_risk  # noqa: E402
from avatar_generation.model_adapters import florence2_visual as fv  # noqa: E402

PREREG = REPO / "docs" / "avatar-production" / "b3-l10b-preregistration.md"
REPORT = REPO / "docs" / "avatar-production" / "b3-l10b-two-feature-report.md"
AGGREGATE = REPO / "docs" / "avatar-production" / "b3-l10b-two-feature-aggregate-v1.json"
L10A_AGGREGATE = REPO / "docs" / "avatar-production" / "b3-l10a-ocr-score-separability-aggregate-v1.json"
OCR = "<OCR_WITH_REGION>"
OD = "<OD>"
SIZE = (1000, 1000)


def _shadow(score=-0.6, tokens=13, regions=1, **over):
    s = {"scoreSource": st.SCORE_SOURCE, "scoreCalibrated": False, "scoreAvailable": True, "generationMode": "beam_search", "numBeams": 3,
         "lengthPenalty": 1.0, "regionCount": regions, "attributionScope": "single_region" if regions == 1 else "whole_sequence",
         "outputTokenCount": tokens, "rawSequenceScore": score}
    s.update(over)
    return s


class _Gen:
    def __init__(self, seqs, scores=None):
        self.sequences = seqs
        if scores is not None:
            self.sequences_scores = scores


C = tf.Candidate(tf.SCORE_THRESHOLDS[3], 16)


# ------------------------------------------------------------ 1-3 semantics


def test_output_token_count_exact_semantics_contract():
    # decoder-side sequence length of beam 0, special tokens included, prompt excluded
    seqs = [[2, 0, 11, 12, 13, 2], [2, 0, 11, 2]]        # two beams; beam 0 has 6 decoder tokens (start, bos, 3 content, eos)
    parsed = fv._attach_shadow_ocr_evidence({OCR: {"quad_boxes": [[0] * 8], "labels": ["a"]}}, OCR, _Gen(seqs, [-0.2, -0.9]), seqs, 1.0)
    sh = parsed[OCR]["shadowOcrEvidence"]
    assert sh["outputTokenCount"] == 6 and sh["rawSequenceScore"] == -0.2
    assert fv._output_token_count(seqs) == len(seqs[0])
    sem = tf.TOKEN_COUNT_SEMANTICS
    assert "decoder" in sem["side"] and "prompt tokens excluded" in sem["side"]
    assert "decoder_start_token_id=2" in sem["includesSpecialTokens"] and "eos_token_id=2" in sem["includesSpecialTokens"]
    assert tf.TOKEN_FEATURE_ROLE == "UNCALIBRATED_AUXILIARY_FEATURE" and "confidence" in sem["notA"]


def test_raw_sequence_score_stays_uncalibrated():
    assert st.SCORE_CALIBRATED is False and tf.SCORE_FEATURE_ROLE == "UNCALIBRATED_DISCRIMINATION_FEATURE"
    with pytest.raises(ValueError):
        tf.features(_shadow(scoreCalibrated=True))
    assert tf.eligible(tf.candidate_metrics(C, [(-2.0, 30)], [(-0.5, 13)], [(-0.5, 13)]), coverage_rate=1.0, calibrated_flags={True}, decision_diff=0)["criteria"]["E"] is False


def test_confidence_band_stays_unknown():
    tasks = {OCR: {OCR: {"quad_boxes": [[300, 450, 700, 450, 700, 560, 300, 560]], "labels": ["x"], "shadowOcrEvidence": _shadow(score=0.0, tokens=5)}},
             OD: {OD: {"bboxes": [], "labels": []}}}
    a = analyze_florence_visual_risk_outputs(tasks, image_size=SIZE)
    d = evaluate_watermark_risk(a.regions, source_regions=(), image_size=SIZE)
    assert [r.confidence for r in a.regions] == [None] and d.evidence["confidenceBands"] == {"unknown": 1}


# ------------------------------------------------------------ 4-6 neutrality and inputs


def test_two_feature_study_cannot_modify_action():
    for action in ("allow", "review", "reject"):
        assert tf.watermark_action_with_features(action, 0.0, 5, C) == action
        assert tf.watermark_action_with_features(action, -9.0, 500, C) == action
    with pytest.raises(ValueError):
        tf.watermark_action_with_features("escalate", 0.0, 5, C)


def test_only_score_and_token_count_accepted_as_features():
    assert tf.FEATURES == ("rawSequenceScore", "outputTokenCount")
    assert tf.features(_shadow(score=-0.6, tokens=13)) == (-0.6, 13)
    with pytest.raises(ValueError):
        tf.features(_shadow(outputTokenCount=None))
    with pytest.raises(ValueError):
        tf.features(_shadow(regions=2))
    with pytest.raises(ValueError):
        tf.features(_shadow(), lengthPenalty=1.0)


@pytest.mark.parametrize("field", sorted(sel.HUMAN_ONLY_FIELDS) + ["family", "familyCode", "groundTruth", "groundTruthBox", "location", "areaBand", "overlayLike", "textQuality", "confidenceBand", "groupKey"])
def test_geometry_human_family_fields_rejected(field):
    with pytest.raises(ValueError):
        tf.features(_shadow(), **{field: "x"})


# ------------------------------------------------------------ 7-8 frozen grids


def test_old_b3l10a_score_thresholds_reused_exactly():
    table = json.loads(L10A_AGGREGATE.read_text(encoding="utf-8"))["development"]["table"]
    assert tuple(t["threshold"] for t in table) == tf.SCORE_THRESHOLDS
    assert len(tf.SCORE_THRESHOLDS) == 9 and tf.SCORE_DIRECTION == "positive_higher"
    with pytest.raises(ValueError):
        tf.Candidate(-1.0, 16)          # a new score threshold is not a candidate
    assert not any(-1.066554 < s < -0.918332 for s in tf.SCORE_THRESHOLDS)   # nothing inserted between the L10A neighbours


def test_coarse_token_caps_frozen():
    assert tf.TOKEN_CAPS == (16, 24, 32) and len(tf.CANDIDATES) == 27
    with pytest.raises(ValueError):
        tf.Candidate(tf.SCORE_THRESHOLDS[0], 14)
    assert tf.TOKEN_DIRECTION == "positive_shorter"
    assert tf.flagged(-0.5, 16, C) and not tf.flagged(-0.5, 17, C) and not tf.flagged(-0.95, 13, C)
    text = PREREG.read_text(encoding="utf-8")
    assert tf.contract_digest()[:12] in text
    for token in (tf.VERSION, tf.EVIDENCE_LABEL, tf.ROBUSTNESS_VERSION, tf.VALIDATION_SPLIT_NAME, "ocr_two_feature_v1_validation.lock", "16, 24, 32"):
        assert token in text


# ------------------------------------------------------------ 9-12 selection / validation guards


def test_selector_cannot_see_validation():
    sig = tf.select_candidate.__code__.co_varnames[: tf.select_candidate.__code__.co_argcount]
    assert sig == ("development_table",)
    a = dict(tf.candidate_metrics(tf.Candidate(tf.SCORE_THRESHOLDS[3], 16), [(-2.0, 30)] * 12, [(-0.5, 13)] * 12, [(-0.5, 13)] * 12), eligibility={"eligible": True})
    b = dict(tf.candidate_metrics(tf.Candidate(tf.SCORE_THRESHOLDS[3], 32), [(-2.0, 30)] * 12, [(-0.5, 13)] * 12, [(-0.5, 13)] * 12), eligibility={"eligible": True})
    c = dict(tf.candidate_metrics(tf.Candidate(tf.SCORE_THRESHOLDS[2], 32), [(-2.0, 30)] * 12, [(-0.5, 13)] * 12, [(-0.5, 13)] * 12), eligibility={"eligible": True})
    picked = tf.select_candidate([a, b, c])
    assert picked["selectedCandidate"] == c["candidate"]        # tie on metrics -> larger cap -> lower (more permissive) score threshold
    assert tf.select_candidate([dict(a, eligibility={"eligible": False})])["status"] == "NONE"


def test_validation_impossible_without_freeze(tmp_path):
    audit = {"validationScoreValuesPreviouslySeen": False, "validationTokenCountValuesPreviouslySeen": False}
    with pytest.raises(tf.RuleNotFrozen):
        tf.validation_guard(tmp_path, tf.contract_digest(), audit)
    tf.write_frozen(tmp_path, {"selectedCandidate": C.id, "scoreThreshold": C.score_threshold, "tokenCap": C.token_cap}, "0" * 64, "1" * 64)
    with pytest.raises(tf.RuleNotFrozen):
        tf.validation_guard(tmp_path, tf.contract_digest(), audit)


def test_dual_feature_exposure_audit_required(tmp_path):
    digest = tf.contract_digest()
    tf.write_frozen(tmp_path, {"selectedCandidate": C.id, "scoreThreshold": C.score_threshold, "tokenCap": C.token_cap}, digest, "1" * 64)
    for audit in ({"validationScoreValuesPreviouslySeen": False}, {"validationTokenCountValuesPreviouslySeen": False},
                  {"validationScoreValuesPreviouslySeen": False, "validationTokenCountValuesPreviouslySeen": True},
                  {"validationScoreValuesPreviouslySeen": True, "validationTokenCountValuesPreviouslySeen": False}):
        with pytest.raises(st.ValidationScoresPreviouslySeen):
            tf.validation_guard(tmp_path, digest, audit)
    assert tf.verdict(True, False, None, None) == "BLOCKED_NEW_HELDOUT_REQUIRED"


def test_one_shot_validation_lock(tmp_path):
    digest = tf.contract_digest()
    audit = {"validationScoreValuesPreviouslySeen": False, "validationTokenCountValuesPreviouslySeen": False}
    tf.write_frozen(tmp_path, {"selectedCandidate": C.id, "scoreThreshold": C.score_threshold, "tokenCap": C.token_cap}, digest, "1" * 64)
    lock = tf.validation_guard(tmp_path, digest, audit)
    assert lock.name == "ocr_two_feature_v1_validation.lock"
    assert lock.name not in (sel.HOLDOUT_LOCK_NAME, v3.V3_HOLDOUT_LOCK_NAME, tp.HOLDOUT_LOCK_NAME, st.VALIDATION_LOCK_NAME)
    tf.mark_validation_evaluated(lock, digest)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        tf.validation_guard(tmp_path, digest, audit)


# ------------------------------------------------------------ 13-16 arithmetic / retuning


def test_one_of_eight_clean_fails_criterion_a():
    m = tf.candidate_metrics(C, [(-0.5, 13)] + [(-2.0, 30)] * 7, [(-0.5, 13)] * 8, [(-0.5, 13)] * 8)
    assert m["cleanFalseEscalationProxy"]["rate"] == 0.125
    e = tf.eligible(m, coverage_rate=1.0, calibrated_flags={False}, decision_diff=0)
    assert e["criteria"]["A"] is False and not e["eligible"]


def test_eight_of_eight_positive_required():
    m = tf.candidate_metrics(C, [(-2.0, 30)] * 8, [(-0.5, 13)] * 7 + [(-2.0, 13)], [(-0.5, 13)] * 8)
    assert m["opaqueSensitivity"]["rate"] == 0.875
    assert tf.eligible(m, coverage_rate=1.0, calibrated_flags={False}, decision_diff=0)["criteria"]["B"] is False
    m2 = tf.candidate_metrics(C, [(-2.0, 30)] * 8, [(-0.5, 13)] * 8, [(-0.5, 13)] * 8)
    assert tf.eligible(m2, coverage_rate=1.0, calibrated_flags={False}, decision_diff=0)["eligible"]


def test_post_validation_retuning_refused():
    frozen = {"selectedCandidate": C.id, "scoreThreshold": C.score_threshold, "tokenCap": C.token_cap}
    assert tf.frozen_candidate(frozen) == C
    with pytest.raises(tf.RetuningRefused):
        tf.frozen_candidate(dict(frozen, tokenCap=24))
    with pytest.raises(tf.RetuningRefused):
        tf.frozen_candidate(dict(frozen, scoreThreshold=tf.SCORE_THRESHOLDS[2]))
    with pytest.raises(tf.RetuningRefused):
        tf.robustness_metrics(tf.Candidate(C.score_threshold, 24), [], frozen=frozen, calibrated_flags={False}, decision_diff=0)


def test_construct_robustness_cannot_tune_rule(tmp_path):
    frozen = {"selectedCandidate": C.id, "scoreThreshold": C.score_threshold, "tokenCap": C.token_cap}
    rows = [{"category": "A_SHORT_ONE_WORD", "alphaName": "opaque", "score": -0.5, "tokens": 13}, {"category": "B_LONG_ONE_WORD", "alphaName": "translucent", "score": -0.5, "tokens": 30}]
    out = tf.robustness_metrics(C, rows, frozen=frozen, calibrated_flags={False}, decision_diff=0)
    assert out["overall"] == {"k": 1, "n": 2, "rate": 0.5} and out["passed"] is False and out["rule"] == C.predicate
    assert "B" in out["failed"]  # long word missed under the frozen cap; the cap is not widened
    with pytest.raises(tf.RuleNotFrozen):
        tf.require_validation_pass(tmp_path, tf.contract_digest())


# ------------------------------------------------------------ 17-18 constructs


def test_long_text_construct_included():
    lengths = {k: len(t) for _, k, t in tf.ROBUSTNESS_CONSTRUCTS}
    assert 4 <= lengths["A_SHORT_ONE_WORD"] <= 6 and 9 <= lengths["B_LONG_ONE_WORD"] <= 12
    assert len([t for _, k, t in tf.ROBUSTNESS_CONSTRUCTS if k == "C_TWO_WORD_PHRASE"][0].split()) == 2
    assert any(ch.isdigit() for _, k, t in tf.ROBUSTNESS_CONSTRUCTS if k == "D_SHORT_ALPHANUMERIC" for ch in t)
    assert {"E_WIDE_CHARACTERS", "E_NARROW_CHARACTERS"} <= {k for _, k, _ in tf.ROBUSTNESS_CONSTRUCTS}
    assert not any(t in ("SAMPLE", "NOVA") for _, _, t in tf.ROBUSTNESS_CONSTRUCTS)
    specs = tf.robustness_specs()
    assert len(specs) == 12 and {s.alpha for s in specs} == {1.0, 0.35} and all(s.kind == "text" for s in specs)


def test_real_trademark_strings_prohibited():
    for _, _, t in tf.ROBUSTNESS_CONSTRUCTS:
        assert v2.no_real_trademark(t)
    assert not v2.no_real_trademark("Nike")


# ------------------------------------------------------------ 19-20 privacy / prior results


def test_raw_values_cannot_enter_repo_report():
    forbidden = tf.FORBIDDEN_WORDING + ("three-rater", "adjudicated human ground truth", "production-ready")
    for path in (REPORT, AGGREGATE, PREREG):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text, (path.name, phrase)
        assert not re.search(r"P\d{2}_C\d{2}", text) and "AppData" not in text and not re.search(r"[A-Za-z]:\\Users\\", text), path.name
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
        assert not ({"rows", "tasks", "labels", "quad_boxes", "shadow", "score", "tokens"} & set(keys(report)))
        assert report["confidenceBandChanged"] is False and report["watermarkPolicyChanged"] is False and report["calibrationPerformed"] is False and report["decisionDiff"] == 0
        assert report["validationEvaluated"] in (0, 1)


def test_prior_results_unchanged():
    assert calib.GATE_VERSION == "owlv2_provisional_shadow_gate_v1" and v2.GATE_VERSION == "OWLV2_CONTROLLED_CHALLENGE_GATE_V2"
    assert v3.contract_digest().startswith("7e0281db982a") and tp.contract_digest().startswith("89514d712ad8") and st.contract_digest().startswith("8092c3ea2f34")
    l10a = json.loads(L10A_AGGREGATE.read_text(encoding="utf-8"))
    assert l10a["verdict"] == "FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING" and l10a["validationEvaluated"] == 0
    assert tf.PRIOR_STATUS["B3_L10A"] == "FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING" and tf.PRIOR_STATUS["B3_L9"] == "TEXT_POLICY_SHADOW_HOLDOUT_FAILED"
    assert tf.PRIOR_STATUS["V1"] == "OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT" and tf.PRIOR_STATUS["V2"] == "OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT" and tf.PRIOR_STATUS["V3"] == "V3_DUAL_CHANNEL_FAILED_DEVELOPMENT"
