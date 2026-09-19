"""CI tests for B3-L15A DETERMINISTIC_EDGE_SCAN_WITH_CONTENT_VERIFIER_V1. Pure logic: no model, no user image, no label."""

import inspect
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

import avatar_edge_mark_generalization as eg  # noqa: E402
import avatar_edge_scan_embed as em  # noqa: E402
import avatar_edge_scan_eval as se  # noqa: E402
import avatar_edge_scan_verifier as es  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_proposal_verifier as pv  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

DOCS = REPO / "docs" / "avatar-production"
PREREG = DOCS / "b3-l15a-preregistration.md"
REPORT = DOCS / "b3-l15a-edge-scan-verifier-report.md"
AGGREGATE = DOCS / "b3-l15a-edge-scan-verifier-aggregate-v1.json"
SIZE = (1000, 1000)


def _det(box, score=0.3, label="a logo"):
    return {"box": list(box), "score": score, "label": label}


def _record(cid, opaque, group, clean, props, truth, meta=None, dataset="l11_dev"):
    return {"conditionId": cid, "opaqueId": opaque, "groupKey": group, "clean": clean, "dataset": dataset, "imageSize": [1000, 1000], "groundTruth": truth,
            "meta": {} if clean else (meta or {"family": "TEXT_WATERMARK_OPAQUE", "alphaName": "OPAQUE", "placementClass": "torso", "sizeBand": "medium", "diagnostic": False}),
            "proposals": [{"proposalId": f"{cid}#{k}", "source": s, "box": b, "label": l, "embedding": e} for k, (s, b, l, e) in enumerate(props)]}


# ------------------------------------------------------------ 1-3 immutability / critical


def test_b3l13_verdict_immutable():
    a = json.loads((DOCS / "b3-l13-proposal-verifier-aggregate-v1.json").read_text(encoding="utf-8"))
    assert a["verdict"] == "PROPOSAL_UNION_COVERAGE_INSUFFICIENT" and a["holdoutEvaluated"] == 0 and a["coverage"]["families"]["EDGE_MARK"]["k"] == 10
    assert es.PRIOR_STATUS["B3_L13"] == "PROPOSAL_UNION_COVERAGE_INSUFFICIENT" and pv.contract_digest().startswith("f2c38dc9feaa")
    assert es.interpretation_note()["b3l13"] == "PROPOSAL_UNION_COVERAGE_INSUFFICIENT" and es.interpretation_note()["priorFailuresReopened"] is False


def test_b3l14a_verdict_immutable():
    a = json.loads((DOCS / "b3-l14a-edge-proposal-generalization-aggregate-v1.json").read_text(encoding="utf-8"))
    assert a["verdict"] == "EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED" and a["holdoutEvaluated"] == 1
    assert a["development"]["overall"] == {"k": 190, "n": 192, "rate": 0.9896} and a["holdout"]["overall"] == {"k": 125, "n": 128, "rate": 0.9766}
    assert a["holdout"]["cells"]["TOP|medium|offset_bar_emblem"]["k"] == 5 and a["holdout"]["gate"]["failed"] == ["J:TOP|medium|offset_bar_emblem"]
    assert es.PRIOR_STATUS["B3_L14A"] == "EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED" and es.PRIOR_STATUS["B3_L14A_FAILED_CELL"] == "TOP x medium x offset_bar_emblem 5/8 (required 8/8)"
    assert es.ZERO_SHOT_LIMIT == "FROZEN_THREE_GENERATOR_ZERO_SHOT_EDGE_LIMIT" and eg.contract_digest().startswith("c11ffa3eaabf")


def test_edge_remains_critical():
    assert es.CRITICAL_MARKER == eg.CRITICAL_MARKER == "EDGE_MARK_REMAINS_CRITICAL_FAMILY" and es.EDGE_DIAGNOSTIC_ALLOWED is False
    assert se.BROAD_FAMILY["J9"] == "EDGE_MARK" and ev.GATE_FAMILY["I"] == "EDGE_MARK"
    with pytest.raises(eg.DowngradeProhibited):
        es.downgrade_to_diagnostic("EDGE_MARK")


# ------------------------------------------------------------ 4-5 zero-shot frozen


def test_zero_shot_thresholds_frozen():
    assert es.PROPOSAL_GENERATORS == pv.PROPOSAL_GENERATORS and es.THRESHOLDS == eg.THRESHOLDS == {"owlv2-base-patch16-ensemble": 0.25, "grounding-dino-tiny": {"box": 0.25, "text": 0.25}, "florence2-phrase-grounding": "presence"}
    assert det.contract_digest().startswith("086a32a65e05") and es.DETECTOR_SET_DIGEST_PREFIX == "086a32a65e05"
    assert det.CANDIDATES["grounding-dino-tiny"]["revision"] == "a2bb814dd30d776dcf7e30523b00659f4f141c71"
    assert es.detector_proposals({"grounding-dino-tiny": [_det([10, 10, 60, 60], 0.20, "a logo")]}, SIZE) == []   # 0.20 is not adopted
    assert es.NO_ZERO_SHOT_RETUNE and "grid_0.15" not in json.dumps(es.PROPOSAL_GENERATORS)


def test_prompts_frozen():
    assert es.PROMPTS == det.PROMPTS == ("a logo", "a watermark", "a brand emblem", "a graphic symbol")
    for mod in (es, se, em):
        src = inspect.getsource(mod).lower()
        for banned in ("edge logo", "border watermark", "edge watermark", "border logo"):
            assert banned not in src


# ------------------------------------------------------------ 6-11 scan contract


def test_scan_contract_single_candidate_only():
    assert es.SCAN_VERSION == "EDGE_SCAN_PROPOSAL_V1" and es.TILE_REL == 0.16 and es.MAX_MARK_REL == 0.07 and es.EDGE_INSET_REL == eg.INSET["relative"] == 0.02
    assert es.MAX_SPACING_REL == pytest.approx(0.09)
    assert not hasattr(es, "TILE_CANDIDATES") and "tile_rel" not in inspect.signature(es.scan_tiles).parameters
    with pytest.raises(RuntimeError):
        es.register_scan_variant("wide", 0.20)


def test_scan_uses_image_dimensions_only():
    sig = inspect.signature(es.scan_tiles)
    assert list(sig.parameters) == ["width", "height"]
    a = es.scan_tiles(1000, 1000)
    assert a == es.scan_tiles(1000, 1000) and all(len(t) == 4 for t in a)
    src = inspect.getsource(es.scan_tiles)
    for token in ("groundTruth", "truth", "family", "alpha", "placement", "opaqueId", "label"):
        assert token not in src


def test_gt_forbidden_runtime():
    for field in ("groundTruth", "groundTruthBoxes", "family", "alpha", "placement", "baseOpaqueId", "humanLabel", "knownMarkPosition", "source", "detectorScore", "edge", "sizeBand", "geometry", "cell"):
        with pytest.raises(ValueError):
            es.runtime_crop([10, 10, 60, 60], SIZE, **{field: "x"})
    assert {"source", "proposalSource", "edge", "sizeBand", "geometry", "cell", "tileIndex", "knownMarkPosition"} <= es.FORBIDDEN_FEATURE_INPUTS


def test_tile_size_fixed():
    for W, H in ((1254, 1254), (1000, 800), (640, 1024)):
        S = round(0.16 * min(W, H))
        tiles = es.scan_tiles(W, H)
        assert all(t[2] - t[0] == S and t[3] - t[1] == S for t in tiles)
        assert any(t[1] == 0 for t in tiles) and any(t[3] == H for t in tiles) and any(t[0] == 0 for t in tiles) and any(t[2] == W for t in tiles)
        assert len(tiles) == len({tuple(t) for t in tiles})   # exact duplicates (corners) removed deterministically
    assert es.scan_tiles(1254, 1254)[0] == (0, 0, 201, 201)


def test_stride_coverage_invariant():
    for W, H in ((1254, 1254), (1000, 800), (640, 1024), (333, 777)):
        m = min(W, H)
        S = round(0.16 * m)
        for edge in es.EDGES:
            centres = sorted(es.edge_tile_centres(W, H, edge))
            assert centres[0] == pytest.approx(S / 2) and centres[-1] == pytest.approx((W if edge in ("TOP", "BOTTOM") else H) - S / 2)
            assert all(b - a <= 0.09 * m + 1e-9 for a, b in zip(centres, centres[1:]))
    assert es.tile_count_per_edge(1254, 1254) == {"TOP": 11, "BOTTOM": 11, "LEFT": 11, "RIGHT": 11}


def test_analytic_canonical_mark_coverage():
    """Any mark with side <= 0.07 x min(W,H) and outer inset <= 0.02 x min(W,H), anywhere along any edge, is covered by >= 1 tile at GT_COVERAGE >= 0.95."""

    for W, H in ((1254, 1254), (1000, 800), (640, 1024)):
        m = min(W, H)
        tiles = es.scan_tiles(W, H)
        for rel in (0.035, 0.07):
            size = round(rel * m)
            for inset in (0, round(0.01 * m), round(0.02 * m)):
                for edge in es.EDGES:
                    length = W if edge in ("TOP", "BOTTOM") else H
                    for a in range(0, length - size + 1, 3):
                        if edge == "TOP":
                            gt = [a, inset, a + size, inset + size]
                        elif edge == "BOTTOM":
                            gt = [a, H - inset - size, a + size, H - inset]
                        elif edge == "LEFT":
                            gt = [inset, a, inset + size, a + size]
                        else:
                            gt = [W - inset - size, a, W - inset, a + size]
                        assert max(es.gt_coverage(t, gt) for t in tiles) >= es.SCAN_COVERAGE_FLOOR, (W, H, edge, rel, inset, a)
    # the B3-L11 edge_top and corner placements and the B3-L14A edge boxes are covered
    for size in (round(0.035 * 1254), round(0.07 * 1254)):
        for edge in es.EDGES:
            assert es.scan_covered(es.scan_tiles(1254, 1254), list(eg.edge_box(1254, 1254, edge, size)))
    assert es.SCAN_COVERAGE_FLOOR == 0.95 and es.ANALYTIC_GUARANTEE["farEdgeMaxRel"] == pytest.approx(0.09)


# ------------------------------------------------------------ 12-13 matching contracts


def test_detector_match_stays_iou_030():
    truth = [{"box": [100, 100, 200, 200]}]
    assert es.IOU_MATCH == 0.30 and es.CONTAINMENT_ADDED_TO_DETECTOR_MATCH is False
    assert es.proposal_matches({"source": "grounding-dino-tiny", "box": [100, 100, 200, 170]}, truth)
    assert not es.proposal_matches({"source": "grounding-dino-tiny", "box": [100, 100, 200, 128]}, truth)     # IoU 0.28
    assert not es.proposal_matches({"source": "grounding-dino-tiny", "box": [50, 50, 400, 400]}, truth)       # containment is not a detector match


def test_scan_match_is_gt_coverage_contract_only():
    truth = [{"box": [100, 100, 150, 150]}]
    tile = {"source": es.SCAN_SOURCE, "box": [0, 0, 300, 300]}
    assert es.proposal_matches(tile, truth) and bench.iou(tile["box"], truth[0]["box"]) < 0.30   # coverage, not IoU
    assert not es.proposal_matches({"source": es.SCAN_SOURCE, "box": [0, 0, 120, 300]}, truth)   # 40 % covered
    assert es.gt_coverage([0, 0, 120, 300], [100, 100, 150, 150]) == pytest.approx(0.4)
    assert es.SCAN_MARKER == "SCAN_CROP_COVERAGE_NOT_OBJECT_LOCALIZATION" and es.SCAN_MARKER in PREREG.read_text(encoding="utf-8")
    # a scan tile never counts under the detector IoU rule and a detector box never under coverage
    assert not es.proposal_matches({"source": "florence2-phrase-grounding", "box": [0, 0, 300, 300]}, truth)


# ------------------------------------------------------------ 14-15 ceiling gate precedes verifier


def _ceiling_records(hit_edge=True):
    recs = []
    for g in ("G1", "G2", "G3"):
        for b in range(4):
            base = f"{g}b{b}"
            recs.append({"conditionId": f"{base}:CLEAN", "opaqueId": base, "groupKey": g, "clean": True, "dataset": "l11_dev", "imageSize": [1000, 1000], "groundTruth": [], "meta": {},
                         "proposals": [{"source": es.SCAN_SOURCE, "box": list(t)} for t in es.scan_tiles(1000, 1000)]})
            for f in c3.FAMILIES:
                for size in f.sizes:
                    cid = f"{base}:{f.code}:{size}:D"
                    truth = [{"box": [500, 500, 560, 560]}]
                    props = [{"source": "grounding-dino-tiny", "box": [502, 502, 562, 562]}] if (f.family != "EDGE_MARK" or hit_edge) else []
                    recs.append({"conditionId": cid, "opaqueId": base, "groupKey": g, "clean": False, "dataset": "l11_dev", "imageSize": [1000, 1000], "groundTruth": truth,
                                 "meta": {"family": f.family, "alphaName": f.alpha_name, "placementClass": c3.PLACEMENT_CLASS[f.placement], "sizeBand": size, "diagnostic": f.diagnostic}, "proposals": props})
    return recs


def test_proposal_ceiling_gate_precedes_verifier():
    cov = se.broad_ceiling(_ceiling_records())
    assert cov["pass"] and cov["overall"] == {"k": 168, "n": 168, "rate": 1.0} and cov["families"]["EDGE_MARK"]["k"] == 12
    order = inspect.getsource(se.run)
    assert order.index("broad_ceiling") < order.index("embedding_records") and se.STAGES == ("ceiling", "development", "stress", "holdout")


def test_proposal_ceiling_fail_blocks_embeddings(tmp_path):
    cov = se.broad_ceiling(_ceiling_records(hit_edge=False))
    assert not cov["pass"] and "H" in cov["failed"]
    with pytest.raises(es.CeilingInsufficient):
        es.require_ceiling({"broad": cov, "edge": {"gate": {"pass": True}}})
    assert es.verdict(False, None, None, None) == "EDGE_SCAN_PROPOSAL_CEILING_FAILED"
    with pytest.raises(es.NotFrozen):
        em.require_embedding_allowed(tmp_path, "l14a_holdout")   # stress embeddings need the frozen candidate
    with pytest.raises(es.NotFrozen):
        em.require_embedding_allowed(tmp_path, "l11_holdout")


# ------------------------------------------------------------ 16-19 verifier recipe


def test_clip_exact_revision():
    assert es.VERIFIER == pv.VERIFIER and es.VERIFIER["repo"] == "openai/clip-vit-large-patch14" and es.VERIFIER["revision"] == "32bd64288804d66eefd0ccbe215aa642df71cc41"
    assert es.VERIFIER["license"] == "mit" and es.VERIFIER["licenseAuthority"].startswith("official repository openai/CLIP LICENSE")
    assert es.VERIFIER["revision"] in PREREG.read_text(encoding="utf-8")


def test_classifier_exact_recipe():
    assert es.CLASSIFIER == pv.CLASSIFIER == {"estimator": "sklearn.linear_model.LogisticRegression", "penalty": "l2", "C": 1.0, "solver": "lbfgs", "class_weight": "balanced", "max_iter": 1000,
                                              "random_state": 0, "input": "L2-normalized CLIP image embedding", "hyperparameterSearch": "none", "sklearnVersionPinned": "1.9.1"}
    clf = es.fit_classifier([[1, 0], [0.9, 0.1], [0, 1], [0.1, 0.9]], ["positive", "positive", "negative", "negative"])
    assert clf.get_params()["C"] == 1.0 and clf.get_params()["random_state"] == 0 and es.SCORE_ROLE == "UNCALIBRATED_VERIFIER_SCORE"
    assert es.CROP == pv.CROP and es.CROP["paddingRelative"] == 0.15 and es.runtime_crop([100, 200, 300, 260], SIZE) == pv.crop_box([100, 200, 300, 260], SIZE) == (70, 191, 330, 269)
    assert es.runtime_crop([0, 0, 201, 201], SIZE) == es.runtime_crop([0, 0, 201, 201], SIZE)   # same crop function for scan tiles


def test_threshold_grid_fixed():
    assert es.THRESHOLD_GRID == pv.THRESHOLD_GRID == (0.20, 0.35, 0.50, 0.65, 0.80) and es.NEUTRAL_THRESHOLD == 0.50
    good = {"eligible": True, "threshold": 0.5, "clean": {"newReviewRate": 0.0}, "minCriticalRecall": 1.0, "broadOverall": 1.0, "edgeOverall": 1.0}
    assert es.select_threshold([good, {**good, "threshold": 0.42}])["threshold"] == 0.5    # a non-grid entry is never selected
    text = PREREG.read_text(encoding="utf-8")
    assert "0.20" in text and "0.80" in text and es.contract_digest()[:12] in text


def test_detector_source_id_forbidden_feature():
    flat = [{"proposalId": "a", "opaqueId": "b", "groupKey": "G1", "label": "positive", "embedding": [1.0, 0.0], "source": "edge_scan"}]
    with pytest.raises(ValueError):
        es.feature_matrix(flat, include_source=True)
    X = es.feature_matrix(flat)
    assert X.shape == (1, 2)
    src = inspect.getsource(es.fit_classifier) + inspect.getsource(es.feature_matrix)
    assert '"source"' not in src.replace('include_source', '') and "bbox" not in src


# ------------------------------------------------------------ 20-21 folds / OOF


def test_base_disjoint_folds():
    assert es.FOLDS == pv.FOLDS == (("G1", "G2", "G3"), ("G1", "G3", "G2"), ("G2", "G3", "G1")) and es.DEVELOPMENT_GROUPS == ("G1", "G2", "G3")
    rows = [{"opaqueId": "b1", "groupKey": "G1", "dataset": "l11_dev"}, {"opaqueId": "b1", "groupKey": "G3", "dataset": "l14a_dev"}]
    with pytest.raises(ValueError):
        es.assert_group_disjoint(("G1", "G2"), "G3", rows)
    audit = es.leakage_audit([{"opaqueId": "b1", "groupKey": "G1", "dataset": "l11_dev"}, {"opaqueId": "b1", "groupKey": "G1", "dataset": "l14a_dev"}, {"opaqueId": "b9", "groupKey": "G3", "dataset": "l11_dev"}])
    assert all(v["disjoint"] for v in audit.values()) and audit["G1+G2->G3"]["evalBases"] == 1


def _synthetic_flat():
    import random

    rnd = random.Random(0)
    flat = []
    for g in ("G1", "G2", "G3"):
        for b in range(4):
            for k in range(6):
                pos = k % 2 == 0
                emb = [1.0 if pos else -1.0] + [rnd.uniform(-0.1, 0.1) for _ in range(7)]
                flat.append({"proposalId": f"{g}b{b}#{k}", "opaqueId": f"{g}b{b}", "groupKey": g, "label": "positive" if pos else "negative", "embedding": emb, "source": "edge_scan" if k % 3 else "grounding-dino-tiny"})
    return flat


def test_only_oof_scores_select_threshold():
    flat = _synthetic_flat() + [{"proposalId": "x#0", "opaqueId": "G1b0", "groupKey": "G1", "label": "excluded", "embedding": [0.0] * 8, "source": "edge_scan"}]
    oof = es.oof_scores(flat)
    assert set(oof) == {r["proposalId"] for r in flat} and "x#0" in oof           # excluded rows are scored, never trained on
    assert inspect.signature(es.select_threshold).parameters.keys() == {"table"}
    assert not hasattr(es, "select_threshold_in_sample") and es.DEVELOPMENT_EVIDENCE == "GROUP_OUT_OF_FOLD"


# ------------------------------------------------------------ 22-24 gates


def test_clean_image_level_burden_gate():
    recs = [_record(f"b{i}:CLEAN", f"b{i}", "G1", True, [(es.SCAN_SOURCE, [0, 0, 160, 160], "negative", [1.0])], []) for i in range(12)]
    scores = {"b0:CLEAN#0": 0.9, "b1:CLEAN#0": 0.9, **{f"b{i}:CLEAN#0": 0.1 for i in range(2, 12)}}
    r = se.evaluate_broad(recs, scores, 0.5, {f"b{i}": "allow" for i in range(12)}, {f"b{i}": "negative" for i in range(12)})
    assert r["clean"]["newAllowToReview"] == 2 and r["criteria"]["J1"] is False
    scores["b1:CLEAN#0"] = 0.1
    r = se.evaluate_broad(recs, scores, 0.5, {f"b{i}": "allow" for i in range(12)}, {f"b{i}": "negative" for i in range(12)})
    assert r["clean"]["newAllowToReview"] == 1 and r["criteria"]["J1"] is True and es.NEW_REVIEW_CEILING == 0.10
    # existing canonical review is not new burden
    r2 = se.evaluate_broad(recs[:1], {"b0:CLEAN#0": 0.9}, 0.5, {"b0": "review"}, {"b0": "negative"})
    assert r2["clean"]["newAllowToReview"] == 0 and r2["clean"]["existingCanonicalBurdenNotCounted"] == 1


def test_broad_family_gates():
    assert set(se.BROAD_FAMILY.values()) == {"TEXT_WATERMARK_OPAQUE", "TEXT_WATERMARK_TRANSLUCENT_HIGH", "TEXT_WATERMARK_TRANSLUCENT_MEDIUM", "GRAPHICAL_WATERMARK_TRANSLUCENT",
                                             "LOGO_LIKE_EMBLEM", "SMALL_CORNER_MARK", "EDGE_MARK", "CENTER_OVERLAY_MARK"}
    truth = [{"box": [100, 100, 160, 160]}]
    pos = _record("b0:F9:small:D", "b0", "G1", False, [(es.SCAN_SOURCE, [0, 0, 160, 160], "positive", [1.0]), ("grounding-dino-tiny", [600, 600, 700, 700], "excluded", [1.0])], truth,
                  meta={"family": "EDGE_MARK", "alphaName": "OPAQUE", "placementClass": "edge", "sizeBand": "small", "diagnostic": False})
    r = se.evaluate_broad([pos], {"b0:F9:small:D#0": 0.9, "b0:F9:small:D#1": 0.9}, 0.5, {}, {})
    assert r["families"]["EDGE_MARK"] == {"k": 1, "n": 1, "rate": 1.0} and r["criteria"]["J9"] is True
    r2 = se.evaluate_broad([pos], {"b0:F9:small:D#0": 0.1, "b0:F9:small:D#1": 0.9}, 0.5, {}, {})
    assert r2["families"]["EDGE_MARK"]["k"] == 0 and r2["criteria"]["J9"] is False     # an unmatched survivor is not recall
    assert es.OVERALL_RECALL_FLOOR == 0.95 and es.FAMILY_RECALL_FLOOR == 0.90 and ev.required_hits(112, 0.95) == 107 and ev.required_hits(16, 0.90) == 15


def test_b3l14a_edge_cell_gates():
    recs = []
    for g in ("G1", "G2", "G3"):
        for b in range(4):
            for cond in eg.conditions(eg.DEV_VARIANT):
                cid = f"{g}b{b}:{cond.code}"
                recs.append(_record(cid, f"{g}b{b}", g, False, [(es.SCAN_SOURCE, [0, 0, 160, 160], "positive", [1.0])], [{"box": [100, 100, 160, 160]}],
                                    meta=eg.manifest_row(cond, f"{g}b{b}", g, [{"box": [100, 100, 160, 160]}]), dataset="l14a_dev"))
    scores = {p["proposalId"]: 0.9 for r in recs for p in r["proposals"]}
    r = se.evaluate_edge(recs, scores, 0.5, eg.DEV_VARIANT)
    assert r["gate"]["pass"] and r["overall"] == {"k": 192, "n": 192, "rate": 1.0}
    for r0 in recs:
        if r0["meta"]["cell"] == "TOP|small|open_hexagon_emblem" and r0["opaqueId"] in ("G1b0", "G1b1"):
            scores[r0["proposals"][0]["proposalId"]] = 0.1
    r = se.evaluate_edge(recs, scores, 0.5, eg.DEV_VARIANT)
    assert not r["gate"]["pass"] and r["cells"]["TOP|small|open_hexagon_emblem"]["k"] == 10 and eg.required(12) == 11


# ------------------------------------------------------------ 25-31 freeze / stress / holdout guards


def test_no_post_development_retune(tmp_path):
    digest = es.contract_digest()
    es.write_selected(tmp_path, 0.5, digest, "1" * 64)
    rec = json.loads((tmp_path / es.SELECTED_MARKER_NAME).read_text(encoding="utf-8"))
    assert rec["role"] == "EDGE_SCAN_CLIP_VERIFIER_CONTROLLED_SHADOW_CANDIDATE" and rec["scan"]["tileRel"] == 0.16 and rec["threshold"] == 0.5
    for mutate in ({"threshold": 0.42}, {"scan": {**rec["scan"], "tileRel": 0.2}}, {"crop": {**es.CROP, "paddingRelative": 0.2}}, {"classifier": {**es.CLASSIFIER, "C": 2.0}},
                   {"verifier": {**es.VERIFIER, "revision": "0" * 40}}, {"thresholds": {**es.THRESHOLDS, "grounding-dino-tiny": {"box": 0.2, "text": 0.2}}}, {"prompts": ["a logo"]}, {"contractDigest": "f" * 64}):
        (tmp_path / es.SELECTED_MARKER_NAME).write_text(json.dumps({**rec, **mutate}), encoding="utf-8")
        with pytest.raises(es.NotFrozen):
            es.require_selected(tmp_path, digest)


def test_known_construct_stress_is_not_called_holdout():
    assert es.STRESS_NAME == "KNOWN_CONSTRUCT_STRESS_GATE" and es.STRESS_DATASET == "l14a_holdout"
    text = PREREG.read_text(encoding="utf-8")
    assert es.STRESS_NAME in text and "not an independent holdout" in text
    assert es.stress_designation()["independentHoldout"] is False and es.stress_designation()["detectorOutputsPreviouslySeen"] is True and es.stress_designation()["verifierOutputsPreviouslySeen"] is False
    assert es.verdict(True, True, False, None) == "EDGE_SCAN_VERIFIER_KNOWN_CONSTRUCT_STRESS_FAILED" and es.verdict(True, True, True, None) == "EDGE_SCAN_VERIFIER_KNOWN_CONSTRUCT_STRESS_PASSED"


def test_stress_fail_preserves_b3l11_holdout(tmp_path):
    digest = es.contract_digest()
    es.write_selected(tmp_path, 0.5, digest, "1" * 64)
    es.write_stress_result(tmp_path, digest, passed=False)
    with pytest.raises(es.NotFrozen):
        es.require_stress_passed(tmp_path, digest)
    with pytest.raises(es.NotFrozen):
        es.holdout_guard(tmp_path, tmp_path, digest)
    assert not (tmp_path / det.SELECTED_MARKER_NAME).exists() and not (tmp_path / det.HOLDOUT_LOCK_NAME).exists()
    with pytest.raises(es.NotFrozen):
        es.write_stress_result(tmp_path, digest, passed=True)   # a stress result is written once; no re-run after failure


def test_original_b3l11_holdout_inaccessible_before_stress_pass(tmp_path):
    digest = es.contract_digest()
    with pytest.raises(es.NotFrozen):
        es.holdout_guard(tmp_path, tmp_path, digest)
    es.write_selected(tmp_path, 0.5, digest, "1" * 64)
    with pytest.raises(es.NotFrozen):
        es.holdout_guard(tmp_path, tmp_path, digest)          # stress not executed
    with pytest.raises(es.NotFrozen):
        es.write_l11_union_marker(tmp_path, tmp_path, digest)   # detector holdout capture marker only after stress pass
    assert es.l11_holdout_unopened_audit(tmp_path)["unopened"]


def test_original_holdout_one_shot(tmp_path):
    digest = es.contract_digest()
    es.write_selected(tmp_path, 0.5, digest, "1" * 64)
    es.write_stress_result(tmp_path, digest, passed=True)
    l11 = tmp_path / "l11"; l11.mkdir()
    es.write_l11_union_marker(tmp_path, l11, digest)
    marker = json.loads((l11 / det.SELECTED_MARKER_NAME).read_text(encoding="utf-8"))
    assert marker["detector"] == "union" and set(marker["detectors"]) == set(pv.PROPOSAL_GENERATORS) and marker["contractDigest"] == det.contract_digest() and marker["constructDigest"] == c3.construct_digest()
    lock = es.holdout_guard(tmp_path, l11, digest)
    assert lock.name == det.HOLDOUT_LOCK_NAME == "visual_mark_detector_v1_holdout.lock"
    ev.mark_holdout(lock, digest)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        es.holdout_guard(tmp_path, l11, digest)
    assert not es.l11_holdout_unopened_audit(l11)["unopened"]


def test_one_of_eight_clean_fails():
    recs = [_record(f"b{i}:CLEAN", f"b{i}", "G4", True, [(es.SCAN_SOURCE, [0, 0, 160, 160], "negative", [1.0])], [], dataset="l11_holdout") for i in range(8)]
    scores = {"b0:CLEAN#0": 0.9, **{f"b{i}:CLEAN#0": 0.1 for i in range(1, 8)}}
    r = se.evaluate_broad(recs, scores, 0.5, {f"b{i}": "allow" for i in range(8)}, {f"b{i}": "negative" for i in range(8)}, holdout=True)
    assert r["clean"]["newAllowToReview"] == 1 and r["criteria"]["J1"] is False and r["clean"]["holdoutCleanCeiling"] == 0
    assert ev.required_hits(8, 0.90) == 8 and ev.required_hits(16, 0.90) == 15 and ev.required_hits(112, 0.95) == 107


def test_no_post_holdout_retuning():
    assert es.NO_RETUNE_AFTER_HOLDOUT == ("scan tile", "stride", "matching", "CLIP", "crop", "classifier", "threshold", "zero-shot threshold", "prompt", "family", "gate")
    assert es.verdict(True, True, True, False) == "VISUAL_MARK_EDGE_SCAN_VERIFIER_HOLDOUT_FAILED"
    assert es.verdict(True, True, True, True) == "VISUAL_MARK_EDGE_SCAN_VERIFIER_CONTROLLED_GATE_PASSED"
    assert es.support(True) == "VISUAL_MARK_EDGE_SCAN_VERIFIER_SUPPORTED_FOR_CONTROLLED_SHADOW_CANARY" and es.support(False) == "VISUAL_MARK_EDGE_SCAN_VERIFIER_NOT_SUPPORTED"
    assert es.CEILING_CLOSED_MARKER == "EDGE_PROPOSAL_CEILING_GAP_CLOSED_BY_DETERMINISTIC_SCAN"


# ------------------------------------------------------------ 32-34 privacy / review-only


def test_aggregate_only_artifact():
    forbidden = ("PRODUCTION_VALIDATED", "PRODUCTION_PRECISION_PROVEN", "LIVE_READY", "NATURAL_POSITIVE_VALIDATED", "WATERMARK_POLICY_READY", "TEXT_POLICY_READY", "LIVE_POLICY_READY",
                 "three-rater", "adjudicated human ground truth", "production-ready", "100% solved", "zero-shot vision is impossible", "all zero-shot detectors cannot")
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
        assert report["priorStatus"]["B3_L13"] == "PROPOSAL_UNION_COVERAGE_INSUFFICIENT" and report["priorStatus"]["B3_L14A"] == "EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED"
        assert report["watermarkPolicyChanged"] is False and report["decisionDiff"] == 0 and report["gaps"]["naturalPositive"] == "NATURAL_POSITIVE_EVIDENCE_MISSING"
        assert report["holdoutEvaluated"] in (0, 1) and report["newDetectorInference"]["development"] == 0


def test_verifier_review_only():
    assert es.shadow_action("allow", True) == "review" and es.shadow_action("allow", False) == "allow" and es.shadow_action("review", True) == "review"
    with pytest.raises(ValueError):
        es.shadow_action("escalate", True)
    out = es.image_outcome([{"proposalId": "p", "source": es.SCAN_SOURCE, "box": [0, 0, 160, 160]}], {"p": 0.9}, 0.5, [{"box": [100, 100, 150, 150]}])
    assert out["hit"] and out["response"] and out["survivors"] == 1
    assert es.image_outcome([{"proposalId": "p", "source": es.SCAN_SOURCE, "box": [0, 0, 160, 160]}], {"p": 0.1}, 0.5, [{"box": [100, 100, 150, 150]}]) == {"survivors": 0, "hit": False, "response": False}


def test_hard_reject_cannot_downgrade():
    assert es.shadow_action("reject", False) == "reject" and es.shadow_action("reject", True) == "reject"
    rec = _record("b0:CLEAN", "b0", "G1", True, [(es.SCAN_SOURCE, [0, 0, 160, 160], "negative", [1.0])], [])
    r = se.evaluate_broad([rec], {"b0:CLEAN#0": 0.9}, 0.5, {"b0": "reject"}, {"b0": "negative"})
    assert r["clean"]["hardRejectBypass"] == 0 and r["clean"]["downgrades"] == 0 and r["criteria"]["J11"] and r["criteria"]["J12"]


# ------------------------------------------------------------ extra: labels, proposal assembly, prereg


def test_labels_contract():
    truth = [{"box": [100, 100, 160, 160]}]
    assert es.proposal_label({"source": "grounding-dino-tiny", "box": [102, 102, 162, 162]}, truth, clean_image=False) == "positive"
    assert es.proposal_label({"source": es.SCAN_SOURCE, "box": [0, 0, 201, 201]}, truth, clean_image=False) == "positive"
    assert es.proposal_label({"source": es.SCAN_SOURCE, "box": [500, 500, 701, 701]}, truth, clean_image=False) == "excluded"      # unmatched on a positive image: scored, never trained
    assert es.proposal_label({"source": "grounding-dino-tiny", "box": [600, 600, 700, 700]}, truth, clean_image=False) == "excluded"
    assert es.proposal_label({"source": es.SCAN_SOURCE, "box": [0, 0, 201, 201]}, [], clean_image=True) == "negative"
    assert es.UNMATCHED_POSITIVE_IMAGE_PROPOSALS == "EXCLUDED_FROM_TRAINING_SCORED_IN_EVALUATION"


def test_runtime_proposals_union_plus_scan():
    props = es.runtime_proposals({"grounding-dino-tiny": [_det([10, 10, 60, 60], 0.4, "a logo")], "owlv2-base-patch16-ensemble": [_det([10, 10, 60, 60], 0.2)]}, (1254, 1254))
    sources = [p["source"] for p in props]
    assert sources.count("grounding-dino-tiny") == 1 and "owlv2-base-patch16-ensemble" not in sources and sources.count(es.SCAN_SOURCE) == 40
    assert len({tuple(p["box"]) for p in props}) == len(props)
    assert es.SCAN_SOURCE == "edge_scan" and es.SCAN_SOURCE not in es.PROPOSAL_GENERATORS


def test_prereg_frozen_values_in_doc():
    text = PREREG.read_text(encoding="utf-8")
    for token in (es.VERSION, es.SCAN_VERSION, "0.16", "0.09", "0.95", es.contract_digest()[:12], es.scan_digest()[:12], "GT_COVERAGE", es.STRESS_NAME, "UI"):
        assert token in text, token
    assert es.NEW_DETECTOR_INFERENCE_EXPECTED == {"development": 0, "stress": 0, "holdout": "B3-L11 holdout only (3 x 128)"}
