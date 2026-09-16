"""CI tests for B3-L13 VISUAL_MARK_PROPOSAL_VERIFIER_V1. Pure logic: no model, no user image, no label."""

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

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_proposal_verifier as pv  # noqa: E402
import avatar_proposal_verifier_eval as pe  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

PREREG = REPO / "docs" / "avatar-production" / "b3-l13-preregistration.md"
REPORT = REPO / "docs" / "avatar-production" / "b3-l13-proposal-verifier-report.md"
AGGREGATE = REPO / "docs" / "avatar-production" / "b3-l13-proposal-verifier-aggregate-v1.json"
SIZE = (1000, 1000)


def _det(box, score=0.3, label="a logo"):
    return {"box": list(box), "score": score, "label": label}


def _record(cid, opaque, group, clean, props, truth, family="TEXT_WATERMARK_OPAQUE"):
    return {"conditionId": cid, "opaqueId": opaque, "groupKey": group, "clean": clean, "imageSize": [1000, 1000], "groundTruth": truth,
            "meta": {} if clean else {"family": family, "alphaName": "OPAQUE", "placementClass": "torso", "sizeBand": "medium", "diagnostic": False},
            "proposals": [{"proposalId": f"{cid}#{k}", "source": "grounding-dino-tiny", "box": b, "label": l, "bestIou": 0.0, "embedding": e} for k, (b, l, e) in enumerate(props)]}


# ------------------------------------------------------------ 1-3 immutability / closure / face


def test_b3l11_b3l12a_verdicts_immutable():
    a = json.loads((REPO / "docs/avatar-production/b3-l11-visual-mark-detector-aggregate-v1.json").read_text(encoding="utf-8"))
    b = json.loads((REPO / "docs/avatar-production/b3-l12a-gdino-geometry-filter-aggregate-v1.json").read_text(encoding="utf-8"))
    assert a["verdict"] == "VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT" and a["holdoutEvaluated"] == 0
    assert b["verdict"] == "GDINO_GEOMETRY_FILTER_FAILED_DEVELOPMENT" and b["holdoutEvaluated"] == 0
    assert pv.PRIOR_STATUS["B3_L11"] == "VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT" and pv.PRIOR_STATUS["B3_L12A"] == "GDINO_GEOMETRY_FILTER_FAILED_DEVELOPMENT"
    assert det.contract_digest().startswith("086a32a65e05") and c3.construct_digest().startswith("38ec105fc597")


def test_geometry_path_closed_marker():
    assert pv.GEOMETRY_CLOSURE == "GDINO_GEOMETRY_FILTER_PATH_CLOSED_ON_CURRENT_CORPUS"
    text = PREREG.read_text(encoding="utf-8")
    assert pv.GEOMETRY_CLOSURE in text and pv.UNION_MARKER in text


def test_face_suppression_prohibited():
    assert pv.FACE_SUPPRESSION == "FACE_SUPPRESSION_PROHIBITED" and pv.FACE_SUPPRESSION in PREREG.read_text(encoding="utf-8")
    for field in ("primaryFaceBBox", "faceBox", "face"):
        with pytest.raises(ValueError):
            pv.crop_box([10, 10, 60, 60], SIZE, **{field: [0, 0, 500, 500]})


# ------------------------------------------------------------ 4-6 frozen union


def test_detector_union_fixed():
    assert set(pv.PROPOSAL_GENERATORS) == {"owlv2-base-patch16-ensemble", "grounding-dino-tiny", "florence2-phrase-grounding"} == set(det.CANDIDATES)
    props = pv.union_proposals({"owlv2-base-patch16-ensemble": [_det([10, 10, 60, 60], 0.9)], "grounding-dino-tiny": [_det([100, 100, 160, 160], 0.3, "a logo a watermark")],
                                "florence2-phrase-grounding": [_det([0, 0, 999, 999], None), _det([300, 300, 340, 340], None, "a watermark")]}, SIZE)
    assert [p["source"] for p in props] == ["owlv2-base-patch16-ensemble", "grounding-dino-tiny", "florence2-phrase-grounding"]   # full-frame Florence box filtered


def test_detector_thresholds_unchanged():
    assert pv.PROPOSAL_GENERATORS == {"owlv2-base-patch16-ensemble": "legacy_0.25", "grounding-dino-tiny": "historical_0.25", "florence2-phrase-grounding": "presence"}
    assert det.CANDIDATES["owlv2-base-patch16-ensemble"]["operatingPoints"]["legacy_0.25"] == {"threshold": 0.25}
    assert det.CANDIDATES["grounding-dino-tiny"]["operatingPoints"]["historical_0.25"] == {"threshold": 0.25}
    assert pv.proposals("owlv2-base-patch16-ensemble", [_det([10, 10, 60, 60], 0.24)], SIZE) == []


def test_prompts_unchanged():
    assert det.PROMPTS == ("a logo", "a watermark", "a brand emblem", "a graphic symbol")
    assert pv.proposals("grounding-dino-tiny", [_det([10, 10, 60, 60], 0.5, "a person")], SIZE) == []


# ------------------------------------------------------------ 7-8 coverage gate precedes verifier


def test_union_coverage_gate_precedes_verifier(tmp_path):
    report = pe.run("coverage", tmp_path, tmp_path, [], {"labels": []})
    assert "coverage" in report and "development" not in report
    assert pe.COVERAGE_FAMILY["H"] == "EDGE_MARK" and pe.COVERAGE_FAMILY["E"] == "GRAPHICAL_WATERMARK_TRANSLUCENT"


def test_insufficient_proposal_ceiling_blocks_verifier():
    with pytest.raises(pv.CoverageInsufficient):
        pv.require_coverage({"pass": False})
    assert pv.verdict(False, None, None)["verdict"] == "PROPOSAL_UNION_COVERAGE_INSUFFICIENT"
    assert "PROPOSAL_CEILING_INSUFFICIENT" in pv.diagnosis({"pass": False, "criteria": {"H": False, "E": True}}, [])
    assert "EDGE_PROPOSAL_GAP" in pv.diagnosis({"pass": False, "criteria": {"H": False, "E": True}}, [])


# ------------------------------------------------------------ 9-10 crop / forbidden inputs


def test_crop_contract_deterministic():
    assert pv.CROP["paddingRelative"] == 0.15
    a = pv.crop_box([100, 200, 300, 260], SIZE)
    assert a == pv.crop_box([100, 200, 300, 260], SIZE) == (70, 191, 330, 269)
    assert pv.crop_box([0, 0, 40, 40], SIZE)[0] == 0 and pv.crop_box([990, 990, 1000, 1000], SIZE)[2] == 1000
    assert pv.crop_box([500, 500, 502, 502], SIZE)[2] - pv.crop_box([500, 500, 502, 502], SIZE)[0] >= pv.CROP["minSidePx"]


@pytest.mark.parametrize("field", sorted(sel.HUMAN_ONLY_FIELDS) + ["groundTruth", "groundTruthBox", "family", "alpha", "placement", "variant", "baseOpaqueId", "isClean", "label", "detectorScore"])
def test_gt_human_family_forbidden_runtime(field):
    with pytest.raises(ValueError):
        pv.crop_box([10, 10, 60, 60], SIZE, **{field: "x"})


# ------------------------------------------------------------ 11-14 folds / OOF / recipe


def test_same_base_cannot_cross_folds():
    rows = [{"opaqueId": "b1", "groupKey": "G1"}, {"opaqueId": "b1", "groupKey": "G3"}]
    with pytest.raises(ValueError):
        pv.assert_group_disjoint(("G1", "G2"), "G3", rows)
    with pytest.raises(ValueError):
        pv.assert_group_disjoint(("G1", "G3"), "G3", [{"opaqueId": "b2", "groupKey": "G3"}])
    pv.assert_group_disjoint(("G1", "G2"), "G3", [{"opaqueId": "b1", "groupKey": "G1"}, {"opaqueId": "b9", "groupKey": "G3"}])
    assert pv.FOLDS == (("G1", "G2", "G3"), ("G1", "G3", "G2"), ("G2", "G3", "G1"))


def _synthetic_flat():
    import random

    rnd = random.Random(0)
    flat = []
    for g in ("G1", "G2", "G3"):
        for b in range(4):
            for k in range(6):
                pos = k % 2 == 0
                emb = [1.0 if pos else -1.0] + [rnd.uniform(-0.1, 0.1) for _ in range(7)]
                flat.append({"proposalId": f"{g}b{b}#{k}", "opaqueId": f"{g}b{b}", "groupKey": g, "label": "positive" if pos else "negative", "embedding": emb, "source": "grounding-dino-tiny"})
    return flat


def test_oof_predictions_required_for_development_gate():
    flat = _synthetic_flat()
    oof = pv.oof_scores(flat)
    assert set(oof) == {r["proposalId"] for r in flat}
    sig = pv.select_threshold.__code__.co_varnames[: pv.select_threshold.__code__.co_argcount]
    assert sig == ("table",)


def test_in_sample_training_result_cannot_select_threshold():
    flat = _synthetic_flat()
    clf = pv.fit_classifier([r["embedding"] for r in flat], [r["label"] for r in flat])
    in_sample = pv.score(clf, [r["embedding"] for r in flat])
    oof = pv.oof_scores(flat)
    # the selector consumes a table built from OOF scores; in-sample scores are not a table and the module exposes no in-sample selection path
    assert not hasattr(pv, "select_threshold_in_sample")
    assert len(in_sample) == len(oof)


def test_classifier_hyperparameters_frozen():
    assert pv.CLASSIFIER == {"estimator": "sklearn.linear_model.LogisticRegression", "penalty": "l2", "C": 1.0, "solver": "lbfgs", "class_weight": "balanced", "max_iter": 1000, "random_state": 0,
                             "input": "L2-normalized CLIP image embedding", "hyperparameterSearch": "none", "sklearnVersionPinned": "1.9.1"}
    clf = pv.fit_classifier([[1, 0], [0.9, 0.1], [0, 1], [0.1, 0.9]], ["positive", "positive", "negative", "negative"])
    assert clf.get_params()["C"] == 1.0 and clf.get_params()["class_weight"] == "balanced" and clf.get_params()["random_state"] == 0


# ------------------------------------------------------------ 15-18 score semantics / grid / labels


def test_verifier_score_explicitly_uncalibrated():
    assert pv.SCORE_ROLE == "UNCALIBRATED_VERIFIER_SCORE" and pv.VERIFIER["scoreRole"] == pv.SCORE_ROLE
    for path in (PREREG, REPORT, AGGREGATE):
        if path.exists():
            t = path.read_text(encoding="utf-8")
            assert "CALIBRATED PROBABILITY" not in t and "confidenceBand" not in t.replace("no confidenceBand", "")


def test_finite_threshold_grid_frozen():
    assert pv.THRESHOLD_GRID == (0.20, 0.35, 0.50, 0.65, 0.80) and pv.NEUTRAL_THRESHOLD == 0.50
    text = PREREG.read_text(encoding="utf-8")
    assert pv.contract_digest()[:12] in text and "0.20" in text and "0.80" in text


def test_no_midpoint_threshold_search():
    good = {"eligible": True, "threshold": 0.5, "clean": {"newReviewRate": 0.0}, "criticalFamilyMinRecall": 1.0, "overall": {"rate": 1.0}}
    assert pv.select_threshold([good])["threshold"] == 0.5
    with pytest.raises(pv.NotFrozen):
        pv.require_selected(Path("C:/definitely/not/here"), pv.contract_digest())
    rec = {"threshold": 0.42}
    assert rec["threshold"] not in pv.THRESHOLD_GRID


def test_ambiguous_proposal_exclusion():
    truth = [{"box": [100, 100, 200, 200]}]
    assert pv.proposal_label([105, 105, 205, 205], truth, clean_image=False)[0] == "positive"
    assert pv.proposal_label([600, 600, 700, 700], truth, clean_image=False)[0] == "negative"
    assert pv.proposal_label([150, 150, 300, 300], truth, clean_image=False)[0] == "ambiguous"        # IoU between 0.05 and 0.30
    assert pv.proposal_label([50, 50, 400, 400], truth, clean_image=False)[0] == "ambiguous"          # contains the mark
    assert pv.proposal_label([140, 140, 160, 160], truth, clean_image=False)[0] == "ambiguous"        # inside the mark
    assert pv.proposal_label([1, 1, 2, 2], [], clean_image=True)[0] == "negative"
    flat = _synthetic_flat() + [{"proposalId": "amb#0", "opaqueId": "G1b0", "groupKey": "G1", "label": "ambiguous", "embedding": [0.0] * 8, "source": "grounding-dino-tiny"}]
    oof = pv.oof_scores(flat)
    assert "amb#0" in oof   # scored, never trained on


# ------------------------------------------------------------ 19-20 shadow semantics


def test_review_only_action():
    assert pv.shadow_action("allow", True) == "review" and pv.shadow_action("allow", False) == "allow"
    with pytest.raises(ValueError):
        pv.shadow_action("escalate", True)
    rec = _record("b0:F1:medium:D", "b0", "G1", False, [([105, 105, 205, 205], "positive", [1.0]), ([600, 600, 700, 700], "negative", [1.0])], [{"box": [100, 100, 200, 200]}])
    out = pv.image_outcome(rec["proposals"], {"b0:F1:medium:D#0": 0.9, "b0:F1:medium:D#1": 0.9}, 0.5, rec["groundTruth"])
    assert out["hit"] and out["survivors"] == 2
    out2 = pv.image_outcome(rec["proposals"], {"b0:F1:medium:D#0": 0.1, "b0:F1:medium:D#1": 0.9}, 0.5, rec["groundTruth"])
    assert not out2["hit"] and out2["response"]      # unmatched survivor is not recall


def test_hard_reject_cannot_downgrade():
    assert pv.shadow_action("reject", False) == "reject" and pv.shadow_action("review", False) == "review"
    rec = _record("b0:CLEAN", "b0", "G1", True, [([10, 10, 60, 60], "negative", [1.0])], [])
    r = pe.evaluate([rec], {"b0:CLEAN#0": 0.9}, 0.5, {"b0": "reject"}, {"b0": "negative"})
    assert r["clean"]["hardRejectBypass"] == 0 and r["clean"]["downgrades"] == 0 and r["criteria"]["J11"] and r["criteria"]["J12"]


# ------------------------------------------------------------ 21-24 holdout guards


def test_holdout_inaccessible_before_candidate_freeze(tmp_path):
    with pytest.raises(pv.NotFrozen):
        pv.holdout_guard(tmp_path, pv.contract_digest())
    pv.write_selected(tmp_path, 0.5, "0" * 64, "1" * 64)
    with pytest.raises(pv.NotFrozen):
        pv.holdout_guard(tmp_path, pv.contract_digest())
    assert pv.holdout_unopened_audit(tmp_path)["unopened"]


def test_holdout_one_shot(tmp_path):
    digest = pv.contract_digest()
    pv.write_selected(tmp_path, 0.5, digest, "1" * 64)
    lock = pv.holdout_guard(tmp_path, digest)
    assert lock.name == det.HOLDOUT_LOCK_NAME == "visual_mark_detector_v1_holdout.lock"
    ev.mark_holdout(lock, digest)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        pv.holdout_guard(tmp_path, digest)
    union = json.loads((tmp_path / det.SELECTED_MARKER_NAME).read_text(encoding="utf-8"))
    assert union["detector"] == "union" and set(union["detectors"]) == set(pv.PROPOSAL_GENERATORS)


def test_one_of_eight_clean_fails_holdout_j1():
    recs = [_record(f"b{i}:CLEAN", f"b{i}", "G4", True, [([10, 10, 60, 60], "negative", [1.0])], []) for i in range(8)]
    scores = {"b0:CLEAN#0": 0.9, **{f"b{i}:CLEAN#0": 0.1 for i in range(1, 8)}}
    r = pe.evaluate(recs, scores, 0.5, {f"b{i}": "allow" for i in range(8)}, {f"b{i}": "negative" for i in range(8)})
    assert r["clean"]["newReviewRate"] == 0.125 and r["criteria"]["J1"] is False
    assert ev.required_hits(8, 0.90) == 8 and ev.required_hits(112, 0.95) == 107


def test_no_post_holdout_retuning(tmp_path):
    digest = pv.contract_digest()
    pv.write_selected(tmp_path, 0.5, digest, "1" * 64)
    marker = json.loads((tmp_path / pv.SELECTED_MARKER_NAME).read_text(encoding="utf-8"))
    for mutate in ({"threshold": 0.42}, {"classifier": {**pv.CLASSIFIER, "C": 2.0}}, {"crop": {**pv.CROP, "paddingRelative": 0.2}}):
        bad = {**marker, **mutate}
        (tmp_path / pv.SELECTED_MARKER_NAME).write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(pv.NotFrozen):
            pv.require_selected(tmp_path, digest)


# ------------------------------------------------------------ 25-26 privacy / gate


def test_aggregate_only_repo_artifacts():
    forbidden = ("PRODUCTION_VALIDATED", "PRODUCTION_PRECISION_PROVEN", "LIVE_READY", "WATERMARK_POLICY_READY", "three-rater", "adjudicated human ground truth", "production-ready")
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
        assert not ({"embedding", "proposals", "detections", "groundTruth", "box"} & set(keys(report)))
        assert report["watermarkPolicyChanged"] is False and report["decisionDiff"] == 0 and report["holdoutEvaluated"] in (0, 1)
        assert report["gaps"]["naturalPositive"] == "NATURAL_POSITIVE_EVIDENCE_MISSING"


def test_ui_needs_review_policy_cannot_weaken_qa_gate():
    assert ev.NEW_REVIEW_CEILING == 0.10 and ev.OVERALL_RECALL_FLOOR == 0.95 and ev.FAMILY_RECALL_FLOOR == 0.90
    assert "UI" in PREREG.read_text(encoding="utf-8")
