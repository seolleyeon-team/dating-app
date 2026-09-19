"""CI tests for B3-L16A DINOv2_FROZEN_VISUAL_REPRESENTATION_VERIFIER_V1. Pure logic: no model, no user image, no label."""

import inspect
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
AI = REPO / "lib" / "ai_recommend_model"
if str(AI) not in sys.path:
    sys.path.insert(0, str(AI))

import avatar_dinov2_embed as dm  # noqa: E402
import avatar_dinov2_eval as de  # noqa: E402
import avatar_dinov2_verifier as dv  # noqa: E402
import avatar_edge_mark_generalization as eg  # noqa: E402
import avatar_edge_scan_eval as se  # noqa: E402
import avatar_edge_scan_verifier as es  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_proposal_verifier as pv  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

DOCS = REPO / "docs" / "avatar-production"
PREREG = DOCS / "b3-l16a-preregistration.md"
REPORT = DOCS / "b3-l16a-dinov2-verifier-report.md"
AGGREGATE = DOCS / "b3-l16a-dinov2-verifier-aggregate-v1.json"
L15A = DOCS / "b3-l15a-edge-scan-verifier-aggregate-v1.json"
SIZE = (1000, 1000)


def _record(cid, opaque, group, clean, props, truth, meta=None, dataset="l11_dev"):
    return {"conditionId": cid, "opaqueId": opaque, "groupKey": group, "clean": clean, "dataset": dataset, "imageSize": [1000, 1000], "groundTruth": truth,
            "meta": {} if clean else (meta or {"family": "TEXT_WATERMARK_OPAQUE", "alphaName": "OPAQUE", "placementClass": "torso", "sizeBand": "medium", "diagnostic": False}),
            "proposals": [{"proposalId": f"{cid}#{k}", "source": s, "box": b, "label": l, "embedding": e} for k, (s, b, l, e) in enumerate(props)]}


# ------------------------------------------------------------ 1-3 immutability


def test_b3l13_immutable():
    a = json.loads((DOCS / "b3-l13-proposal-verifier-aggregate-v1.json").read_text(encoding="utf-8"))
    assert a["verdict"] == "PROPOSAL_UNION_COVERAGE_INSUFFICIENT" and dv.PRIOR_STATUS["B3_L13"] == "PROPOSAL_UNION_COVERAGE_INSUFFICIENT"


def test_b3l14a_immutable():
    a = json.loads((DOCS / "b3-l14a-edge-proposal-generalization-aggregate-v1.json").read_text(encoding="utf-8"))
    assert a["verdict"] == "EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED" and dv.PRIOR_STATUS["B3_L14A"] == "EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED"


def test_b3l15a_immutable():
    a = json.loads(L15A.read_text(encoding="utf-8"))
    assert a["verdict"] == "EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT" and a["stressEvaluated"] == 0 and a["holdoutEvaluated"] == 0
    assert a["ceiling"]["pass"] and a["ceiling"]["broad"]["overall"] == {"k": 166, "n": 168, "rate": 0.9881} and a["ceiling"]["broad"]["families"]["EDGE_MARK"]["k"] == 12
    assert a["ceiling"]["edge"]["overall"] == {"k": 192, "n": 192, "rate": 1.0} and min(c["k"] for c in a["ceiling"]["edge"]["cells"].values()) == 12
    assert dv.PRIOR_STATUS["B3_L15A"] == "EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT" and dv.PRIOR_STATUS["B3_L15A_CEILING"] == "PASS (B3-L11 dev 166/168, EDGE_MARK 12/12; B3-L14A dev 192/192, all cells 12/12)"
    assert dv.PRIOR_STATUS["B3_L15A_STRESS"] == "NOT_EXECUTED" and dv.PRIOR_STATUS["B3_L15A_HOLDOUT"] == "UNOPENED" and es.contract_digest().startswith("de771758cc30")
    assert dv.interpretation_note()["priorFailuresReopened"] is False


# ------------------------------------------------------------ 4-6 proposal freeze / scan-only reject / one candidate


def test_proposal_contract_frozen():
    assert dv.PROPOSAL_FREEZE_MARKER == "EDGE_SCAN_PROPOSAL_CONTRACT_FROZEN_AFTER_B3_L15A"
    assert dv.PROPOSAL_CONTRACT_DIGEST_PREFIX == "de771758cc30" == es.contract_digest()[:12] and dv.SCAN_DIGEST_PREFIX == "1b45958a524d" == es.scan_digest()[:12]
    assert dv.runtime_proposals is es.runtime_proposals and dv.proposal_matches is es.proposal_matches and dv.proposal_label is es.proposal_label
    assert es.TILE_REL == 0.16 and es.SCAN_COVERAGE_FLOOR == 0.95 and es.IOU_MATCH == 0.30 and es.THRESHOLDS["grounding-dino-tiny"] == {"box": 0.25, "text": 0.25}
    src = inspect.getsource(dv).lower()
    for token in ("nms(", "suppress(", "face_box", "facebbox", "primaryface"):
        assert token not in src, token
    assert dv.PROPOSAL_FREEZE_MARKER in PREREG.read_text(encoding="utf-8")


def test_scan_only_rejected_by_existing_evidence():
    assert dv.SCAN_ONLY_REJECT == "SCAN_ONLY_CURRENT_REPRESENTATION_DOMINATED_BY_EXISTING_EVIDENCE"
    ev_ = dv.scan_only_dominance(json.loads(L15A.read_text(encoding="utf-8")))
    assert ev_["rejected"] is True and ev_["scanCleanSurvivorImages"]["0.5"] == 2 and ev_["scanCleanSurvivorImages"]["0.65"] == 2 and ev_["cleanCeiling"] == "<= 1/12"
    assert ev_["combinedEdgeMarkAt0.8"] == "9/12" and "cannot exceed" in ev_["reason"]
    assert not hasattr(dm, "SCAN_ONLY") and "scan_only" not in json.dumps(dm.DATASETS)


def test_only_one_representation_candidate():
    assert dv.REPRESENTATION_CANDIDATES == ("facebook/dinov2-base",) and dv.VERIFIER["repo"] == "facebook/dinov2-base"
    with pytest.raises(RuntimeError):
        dv.register_representation("google/siglip-base-patch16-224", "0" * 40)
    src = inspect.getsource(dm).lower() + inspect.getsource(de).lower()
    for banned in ("siglip", "openclip", "dinov2-small", "dinov2-large", "dinov2-giant", "ensemble("):
        assert banned not in src, banned
    dv_src = inspect.getsource(dv).lower()
    esc = inspect.getsource(dv.failure_escalation).lower()
    for banned in ("siglip", "openclip", "dinov2-large"):
        assert dv_src.count(banned) == esc.count(banned), banned      # named only in the not-tried list of the stop rule
    assert dv.STOP_RULE == "FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE" and dv.NEXT_ON_FAILURE == "SUPERVISED_WATERMARK_LOGO_DATA_DESIGN"


# ------------------------------------------------------------ 7-11 model authority / preprocessing / semantics / no search


def test_dino_exact_revision_required():
    assert re.fullmatch(r"[0-9a-f]{40}", dv.VERIFIER["revision"]) and dv.VERIFIER["revision"] == "f9e44c814b77203eaa57a6bdbbd535f21ede1415"
    assert dv.VERIFIER["revision"] in PREREG.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        dv.require_pinned_revision("main")
    assert dv.require_pinned_revision(dv.VERIFIER["revision"]) == dv.VERIFIER["revision"]


def test_license_verified():
    assert dv.VERIFIER["license"] == "apache-2.0" and dv.VERIFIER["licenseAuthority"].startswith("official model card")
    assert "apache-2.0" in PREREG.read_text(encoding="utf-8")


def test_preprocessing_frozen():
    assert dv.PREPROCESSING == {"processor": "BitImageProcessor (AutoImageProcessor from the pinned snapshot)", "do_convert_rgb": True, "do_resize": True, "size": {"shortest_edge": 256}, "resample": "bicubic (3)",
                                "do_center_crop": True, "crop_size": {"height": 224, "width": 224}, "do_rescale": True, "rescale_factor": 1 / 255, "do_normalize": True,
                                "image_mean": [0.485, 0.456, 0.406], "image_std": [0.229, 0.224, 0.225], "source": "preprocessor_config.json at the pinned revision; official defaults, no custom search"}
    assert "custom" not in json.dumps(dv.VERIFIER).lower().replace("no custom", "")
    assert dm.processor_kwargs() == {}     # official defaults only; nothing overridden


def test_embedding_semantic_frozen():
    assert dv.VERIFIER["embeddingSemantics"] == "pooler_output: the [CLS] token of the final LayerNorm output (== last_hidden_state[:, 0]); no mean pooling"
    assert dv.VERIFIER["embeddingDim"] == 768 and dv.VERIFIER["architecture"].startswith("ViT-B/14")
    fake = SimpleNamespace(pooler_output="CLS", last_hidden_state="ALL", hidden_states=("a", "b"))
    assert dv.image_embedding(fake) == "CLS"


def test_no_layer_or_pooling_search():
    src = inspect.getsource(dv.image_embedding) + inspect.getsource(dm)
    for banned in ("hidden_states", ".mean(", "patch_tokens", "output_hidden_states=True", "layer_index", "concat("):
        assert banned not in src, banned
    assert dv.NO_SEARCH == ("layer", "pooling", "patch pooling", "multi-layer concat", "CLS vs mean-pool", "preprocessing", "padding", "crop")


# ------------------------------------------------------------ 12-14 crop / forbidden features


def test_crop_unchanged():
    assert dv.CROP == es.CROP == pv.CROP and dv.runtime_crop is es.runtime_crop
    assert dv.runtime_crop([100, 200, 300, 260], SIZE) == (70, 191, 330, 269)


def test_proposal_source_forbidden_feature():
    flat = [{"proposalId": "a", "opaqueId": "b", "groupKey": "G1", "label": "positive", "embedding": [1.0, 0.0], "source": "edge_scan"}]
    with pytest.raises(ValueError):
        dv.feature_matrix(flat, include_source=True)
    assert dv.feature_matrix(flat).shape == (1, 2)
    assert {"source", "proposalSource", "detectorScore", "bbox", "edge", "family", "sizeBand", "geometry", "alpha", "groundTruth", "isClean", "baseOpaqueId", "humanLabel"} <= dv.FORBIDDEN_FEATURE_INPUTS


def test_gt_forbidden_runtime():
    for field in ("groundTruth", "family", "alpha", "placement", "baseOpaqueId", "humanLabel", "isClean", "source", "detectorScore", "edge", "geometry"):
        with pytest.raises(ValueError):
            dv.runtime_crop([10, 10, 60, 60], SIZE, **{field: "x"})


# ------------------------------------------------------------ 15-18 folds / classifier / grid / OOF


def test_folds_base_disjoint():
    assert dv.FOLDS == es.FOLDS == (("G1", "G2", "G3"), ("G1", "G3", "G2"), ("G2", "G3", "G1"))
    with pytest.raises(ValueError):
        dv.assert_group_disjoint(("G1", "G2"), "G3", [{"opaqueId": "b1", "groupKey": "G1"}, {"opaqueId": "b1", "groupKey": "G3"}])
    audit = dv.leakage_audit([{"opaqueId": "b1", "groupKey": "G1", "dataset": "l11_dev"}, {"opaqueId": "b1", "groupKey": "G1", "dataset": "l14a_dev"}, {"opaqueId": "b9", "groupKey": "G3", "dataset": "l11_dev"}])
    assert all(v["disjoint"] for v in audit.values())


def test_classifier_unchanged():
    assert dv.CLASSIFIER == es.CLASSIFIER == pv.CLASSIFIER and dv.fit_classifier is es.fit_classifier and dv.SCORE_ROLE == "UNCALIBRATED_VERIFIER_SCORE"
    clf = dv.fit_classifier([[1, 0], [0.9, 0.1], [0, 1], [0.1, 0.9]], ["positive", "positive", "negative", "negative"])
    assert clf.get_params()["C"] == 1.0 and clf.get_params()["class_weight"] == "balanced"
    assert dv.NON_LINEAR_HEADS_PROHIBITED == ("RBF SVM", "kernel search", "random forest", "boosting", "MLP", "neural classifier", "polynomial features")
    src = inspect.getsource(dv).lower() + inspect.getsource(de).lower()
    for banned in ("svc(", "randomforest", "gradientboosting", "mlpclassifier", "polynomialfeatures", "kernel="):
        assert banned not in src


def test_threshold_grid_unchanged():
    assert dv.THRESHOLD_GRID == es.THRESHOLD_GRID == (0.20, 0.35, 0.50, 0.65, 0.80) and dv.NEUTRAL_THRESHOLD == 0.50
    good = {"eligible": True, "threshold": 0.5, "clean": {"newReviewRate": 0.0}, "minCriticalRecall": 1.0, "broadOverall": 1.0, "edgeOverall": 1.0}
    assert dv.select_threshold([good, {**good, "threshold": 0.42}])["threshold"] == 0.5


def _synthetic_flat():
    import random

    rnd = random.Random(0)
    flat = []
    for g in ("G1", "G2", "G3"):
        for b in range(4):
            for k in range(6):
                pos = k % 2 == 0
                flat.append({"proposalId": f"{g}b{b}#{k}", "opaqueId": f"{g}b{b}", "groupKey": g, "label": "positive" if pos else "negative",
                             "embedding": [1.0 if pos else -1.0] + [rnd.uniform(-0.1, 0.1) for _ in range(7)], "source": "edge_scan"})
    return flat


def test_oof_required():
    flat = _synthetic_flat() + [{"proposalId": "x#0", "opaqueId": "G1b0", "groupKey": "G1", "label": "excluded", "embedding": [0.0] * 8, "source": "edge_scan"}]
    oof = dv.oof_scores(flat)
    assert set(oof) == {r["proposalId"] for r in flat} and dv.DEVELOPMENT_EVIDENCE == "GROUP_OUT_OF_FOLD"
    assert inspect.signature(dv.select_threshold).parameters.keys() == {"table"} and not hasattr(dv, "select_threshold_in_sample")


# ------------------------------------------------------------ 19-21 gates (reused evaluator)


def test_clean_le_1_of_12():
    recs = [_record(f"b{i}:CLEAN", f"b{i}", "G1", True, [(es.SCAN_SOURCE, [0, 0, 160, 160], "negative", [1.0])], []) for i in range(12)]
    scores = {"b0:CLEAN#0": 0.9, "b1:CLEAN#0": 0.9, **{f"b{i}:CLEAN#0": 0.1 for i in range(2, 12)}}
    r = de.evaluate_broad(recs, scores, 0.5, {f"b{i}": "allow" for i in range(12)}, {f"b{i}": "negative" for i in range(12)})
    assert r["clean"]["newAllowToReview"] == 2 and r["criteria"]["J1"] is False
    scores["b1:CLEAN#0"] = 0.1
    assert de.evaluate_broad(recs, scores, 0.5, {f"b{i}": "allow" for i in range(12)}, {f"b{i}": "negative" for i in range(12)})["criteria"]["J1"] is True
    assert de.evaluate_broad is se.evaluate_broad and dv.NEW_REVIEW_CEILING == 0.10


def test_broad_gates_unchanged():
    assert de.BROAD_FAMILY == se.BROAD_FAMILY and de.BROAD_FAMILY["J9"] == "EDGE_MARK" and dv.OVERALL_RECALL_FLOOR == 0.95 and dv.FAMILY_RECALL_FLOOR == 0.90
    assert ev.required_hits(168, 0.95) == 160 and ev.required_hits(12, 0.90) == 11 and ev.required_hits(24, 0.90) == 22


def test_edge_cell_gates_unchanged():
    assert de.evaluate_edge is se.evaluate_edge and eg.required(12) == 11 and eg.required(8) == 8
    recs = []
    for g in ("G1", "G2", "G3"):
        for b in range(4):
            for cond in eg.conditions(eg.DEV_VARIANT):
                cid = f"{g}b{b}:{cond.code}"
                recs.append(_record(cid, f"{g}b{b}", g, False, [(es.SCAN_SOURCE, [0, 0, 160, 160], "positive", [1.0])], [{"box": [100, 100, 160, 160]}], meta=eg.manifest_row(cond, f"{g}b{b}", g, [{"box": [100, 100, 160, 160]}]), dataset="l14a_dev"))
    scores = {p["proposalId"]: 0.9 for r in recs for p in r["proposals"]}
    assert de.evaluate_edge(recs, scores, 0.5, eg.DEV_VARIANT)["gate"]["pass"]


# ------------------------------------------------------------ 22-28 stage guards


def test_dev_fail_blocks_stress(tmp_path):
    assert dv.verdict(False, None, None) == "DINOV2_VERIFIER_FAILED_DEVELOPMENT"
    with pytest.raises(dv.NotFrozen):
        dm.require_embedding_allowed(tmp_path, "l14a_holdout")
    with pytest.raises(dv.NotFrozen):
        dv.write_stress_result(tmp_path, dv.contract_digest(), passed=True)


def test_dev_fail_blocks_original_holdout(tmp_path):
    with pytest.raises(dv.NotFrozen):
        dv.holdout_guard(tmp_path, tmp_path, dv.contract_digest())
    with pytest.raises(dv.NotFrozen):
        dm.require_embedding_allowed(tmp_path, "l11_holdout")
    assert dv.l11_holdout_unopened_audit(tmp_path, tmp_path)["unopened"]


def test_stress_is_not_independent_holdout():
    assert dv.STRESS_NAME == "KNOWN_CONSTRUCT_STRESS_GATE" and dv.STRESS_DATASET == "l14a_holdout"
    d = dv.stress_designation()
    assert d["independentHoldout"] is False and d["detectorOutputsPreviouslySeen"] is True and d["verifierOutputsPreviouslySeen"] is False
    assert dv.verdict(True, False, None) == "DINOV2_VERIFIER_KNOWN_CONSTRUCT_STRESS_FAILED" and dv.verdict(True, True, None) == "DINOV2_VERIFIER_KNOWN_CONSTRUCT_STRESS_PASSED"
    assert "not an independent holdout" in PREREG.read_text(encoding="utf-8")


def test_stress_fail_preserves_b3l11_holdout(tmp_path):
    digest = dv.contract_digest()
    dv.write_selected(tmp_path, 0.5, digest, "1" * 64)
    dv.write_stress_result(tmp_path, digest, passed=False)
    with pytest.raises(dv.NotFrozen):
        dv.require_stress_passed(tmp_path, digest)
    with pytest.raises(dv.NotFrozen):
        dv.holdout_guard(tmp_path, tmp_path, digest)
    with pytest.raises(dv.NotFrozen):
        dv.write_l11_union_marker(tmp_path, tmp_path, digest)
    assert not (tmp_path / det.SELECTED_MARKER_NAME).exists() and not (tmp_path / det.HOLDOUT_LOCK_NAME).exists()


def test_holdout_one_shot(tmp_path):
    digest = dv.contract_digest()
    dv.write_selected(tmp_path, 0.5, digest, "1" * 64)
    dv.write_stress_result(tmp_path, digest, passed=True)
    l11 = tmp_path / "l11"; l11.mkdir()
    dv.write_l11_union_marker(tmp_path, l11, digest)
    marker = json.loads((l11 / det.SELECTED_MARKER_NAME).read_text(encoding="utf-8"))
    assert marker["detector"] == "union" and marker["contractDigest"] == det.contract_digest() and marker["constructDigest"] == c3.construct_digest()
    lock = dv.holdout_guard(tmp_path, l11, digest)
    assert lock.name == det.HOLDOUT_LOCK_NAME
    ev.mark_holdout(lock, digest)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        dv.holdout_guard(tmp_path, l11, digest)


def test_one_of_eight_clean_fails():
    recs = [_record(f"b{i}:CLEAN", f"b{i}", "G4", True, [(es.SCAN_SOURCE, [0, 0, 160, 160], "negative", [1.0])], [], dataset="l11_holdout") for i in range(8)]
    scores = {"b0:CLEAN#0": 0.9, **{f"b{i}:CLEAN#0": 0.1 for i in range(1, 8)}}
    r = de.evaluate_broad(recs, scores, 0.5, {f"b{i}": "allow" for i in range(8)}, {f"b{i}": "negative" for i in range(8)}, holdout=True)
    assert r["clean"]["newAllowToReview"] == 1 and r["criteria"]["J1"] is False and ev.required_hits(8, 0.90) == 8 and ev.required_hits(112, 0.95) == 107


def test_no_post_holdout_retune(tmp_path):
    digest = dv.contract_digest()
    dv.write_selected(tmp_path, 0.5, digest, "1" * 64)
    rec = json.loads((tmp_path / dv.SELECTED_MARKER_NAME).read_text(encoding="utf-8"))
    for mutate in ({"threshold": 0.42}, {"verifier": {**dv.VERIFIER, "revision": "0" * 40}}, {"preprocessing": {**dv.PREPROCESSING, "size": {"shortest_edge": 224}}},
                   {"crop": {**dv.CROP, "paddingRelative": 0.2}}, {"classifier": {**dv.CLASSIFIER, "C": 2.0}}, {"scanDigest": "0" * 64}, {"proposalContractDigest": "0" * 64}, {"contractDigest": "f" * 64}):
        (tmp_path / dv.SELECTED_MARKER_NAME).write_text(json.dumps({**rec, **mutate}), encoding="utf-8")
        with pytest.raises(dv.NotFrozen):
            dv.require_selected(tmp_path, digest)
    assert dv.NO_CHANGE_AFTER_HOLDOUT == ("DINO revision", "preprocessing", "embedding semantics", "crop", "classifier", "threshold", "scan", "detectors", "prompts", "matching", "family floors")


def test_representation_search_stop_rule():
    assert dv.STOP_RULE == "FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE"
    rule = dv.failure_escalation()
    assert rule["next"] == "SUPERVISED_WATERMARK_LOGO_DATA_DESIGN" and set(rule["notTried"]) >= {"SigLIP", "OpenCLIP", "DINOv2-large", "new classifier head", "new threshold", "new crop"}
    assert dv.STOP_RULE in PREREG.read_text(encoding="utf-8")
    assert dv.verdict(True, True, False) == "DINOV2_VISUAL_MARK_VERIFIER_HOLDOUT_FAILED" and dv.verdict(True, True, True) == "DINOv2_VISUAL_MARK_VERIFIER_CONTROLLED_GATE_PASSED"


# ------------------------------------------------------------ 30-32 privacy / review-only / hard reject


def test_aggregate_only_artifacts():
    forbidden = ("PRODUCTION_VALIDATED", "LIVE_READY", "NATURAL_POSITIVE_VALIDATED", "PRODUCTION_PRECISION_PROVEN", "WATERMARK_POLICY_READY", "TEXT_POLICY_READY", "three-rater",
                 "adjudicated human ground truth", "production-ready", "synthetic style is the cause", "all embeddings fail", "visual verification impossible")
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
        assert not ({"embedding", "proposals", "detections", "groundTruth", "boxes", "score", "path", "opaqueId", "coef"} & set(keys(report)))
        assert report["priorStatus"]["B3_L15A"] == "EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT" and report["watermarkPolicyChanged"] is False and report["decisionDiff"] == 0
        assert report["newDetectorInference"]["development"] == 0 and report["gaps"]["naturalPositive"] == "NATURAL_POSITIVE_EVIDENCE_MISSING" and report["verifier"]["embeddingDim"] == 768


def test_review_only():
    assert dv.shadow_action("allow", True) == "review" and dv.shadow_action("allow", False) == "allow"
    with pytest.raises(ValueError):
        dv.shadow_action("escalate", True)
    out = dv.image_outcome([{"proposalId": "p", "source": es.SCAN_SOURCE, "box": [0, 0, 160, 160]}], {"p": 0.9}, 0.5, [{"box": [100, 100, 150, 150]}])
    assert out["hit"] and out["response"]


def test_hard_reject_cannot_downgrade():
    assert dv.shadow_action("reject", False) == "reject" and dv.shadow_action("reject", True) == "reject"
    rec = _record("b0:CLEAN", "b0", "G1", True, [(es.SCAN_SOURCE, [0, 0, 160, 160], "negative", [1.0])], [])
    r = de.evaluate_broad([rec], {"b0:CLEAN#0": 0.9}, 0.5, {"b0": "reject"}, {"b0": "negative"})
    assert r["clean"]["hardRejectBypass"] == 0 and r["clean"]["downgrades"] == 0


# ------------------------------------------------------------ extra: provenance reuse, freeze gate, prereg digest


def test_proposal_provenance_reuse_exact():
    l15 = [{"conditionId": "b0:X", "proposals": [{"proposalId": "l11_dev:b0:X#0", "source": "edge_scan", "box": [0.0, 0.0, 201.0, 201.0], "label": "negative"}]}]
    props = [{"proposalId": "l11_dev:b0:X#0", "source": "edge_scan", "box": [0.0, 0.0, 201.0, 201.0]}]
    assert dm.provenance_exact(l15[0], props, ["negative"])
    assert not dm.provenance_exact(l15[0], [{**props[0], "box": [0.0, 0.0, 200.0, 201.0]}], ["negative"])
    assert not dm.provenance_exact(l15[0], props, ["positive"])
    assert dv.NEW_DETECTOR_INFERENCE_EXPECTED == {"development": 0, "stress": 0, "holdout": "B3-L11 holdout only (3 x 128)"}


def test_embedding_requires_freeze_commit(tmp_path):
    with pytest.raises(dv.NotFrozen):
        dm.require_embedding_allowed(tmp_path, "l11_dev")
    dv.write_frozen(tmp_path, dv.contract_digest(), "0" * 40)
    dm.require_embedding_allowed(tmp_path, "l11_dev")
    with pytest.raises(dv.NotFrozen):
        dv.require_frozen(tmp_path, "f" * 64)


def test_prereg_frozen_values_in_doc():
    text = PREREG.read_text(encoding="utf-8")
    for token in (dv.VERSION, dv.contract_digest()[:12], "pooler_output", "256", "224", "0.485", "768", dv.STRESS_NAME, dv.SCAN_ONLY_REJECT, dv.PROPOSAL_FREEZE_MARKER, "UI"):
        assert token in text, token
    assert dm.MIN_AVAILABLE_GB_TO_START == 3.0 and dm.MIN_AVAILABLE_GB_DURING == 0.6
