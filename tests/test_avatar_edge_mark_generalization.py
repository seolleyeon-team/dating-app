"""CI tests for B3-L14A EDGE_MARK_GENERALIZATION_V1. Pure logic: no model, no user image, no label, no verifier."""

import inspect
import json
import re
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
AI = REPO / "lib" / "ai_recommend_model"
if str(AI) not in sys.path:
    sys.path.insert(0, str(AI))

import avatar_edge_mark_capture as ec  # noqa: E402
import avatar_edge_mark_eval as ee  # noqa: E402
import avatar_edge_mark_generalization as eg  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_proposal_verifier as pv  # noqa: E402
import avatar_visual_mark_capture as l11cap  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

DOCS = REPO / "docs" / "avatar-production"
PREREG = DOCS / "b3-l14a-preregistration.md"
REPORT = DOCS / "b3-l14a-edge-proposal-generalization-report.md"
AGGREGATE = DOCS / "b3-l14a-edge-proposal-generalization-aggregate-v1.json"
L13_AGGREGATE = DOCS / "b3-l13-proposal-verifier-aggregate-v1.json"
SIZE = (1000, 1000)


def _det(box, score=0.3, label="a logo"):
    return {"box": list(box), "score": score, "label": label}


def _blank():
    return Image.new("RGB", (400, 400), (120, 120, 120))


def _row(cid, base, group, cond, truth_box, dets):
    return {"conditionId": cid, "opaqueId": base, "groupKey": group, "imageSize": [1000, 1000], "meta": eg.manifest_row(cond, base, group, [{"box": truth_box}]),
            "groundTruth": [{"box": truth_box}], "detections": dets}


def _captures(tmp_path, split, hit_fn, groups=("G1", "G2", "G3"), per_group=4):
    """Synthetic per-detector capture files; hit_fn(cond, base_index) -> True gives GDINO a matching box."""

    variant = eg.DEV_VARIANT if split == "development" else eg.HOLDOUT_VARIANT
    conds = eg.conditions(variant)
    for name in eg.PROPOSAL_GENERATORS:
        rows = []
        for g in groups:
            for b in range(per_group):
                base = f"{g}b{b}"
                for cond in conds:
                    truth = [100.0, 100.0, 160.0, 160.0]
                    dets = []
                    if name == "grounding-dino-tiny" and hit_fn(cond, b):
                        dets.append(_det([102, 102, 162, 162], 0.4, "a logo"))
                    rows.append(_row(f"{base}:{cond.code}", base, g, cond, truth, dets))
        (tmp_path / f"edge_capture_{name}_{split}.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        spec = det.CANDIDATES[name]
        (tmp_path / f"edge_run_meta_{name}_{split}.json").write_text(json.dumps({"repo": spec["repo"], "revision": spec["revision"], "license": spec["license"], "variant": variant,
                                                                              "originalsUnchanged": True, "contractDigestPrefix": eg.contract_digest()[:12], "constructDigestPrefix": eg.construct_digest()[:12],
                                                                              "detectorSetDigestPrefix": det.contract_digest()[:12]}), encoding="utf-8")


# ------------------------------------------------------------ 1-4 immutability / critical / no diagnostic / no verifier


def test_b3l13_verdict_immutable():
    a = json.loads(L13_AGGREGATE.read_text(encoding="utf-8"))
    assert a["verdict"] == "PROPOSAL_UNION_COVERAGE_INSUFFICIENT" and a["holdoutEvaluated"] == 0 and "development" not in a
    assert a["coverage"]["overall"] == {"k": 164, "n": 168, "rate": 0.9762} and a["coverage"]["families"]["EDGE_MARK"] == {"k": 10, "n": 12, "rate": 0.8333}
    assert eg.PRIOR_STATUS["B3_L13"] == "PROPOSAL_UNION_COVERAGE_INSUFFICIENT" and eg.PRIOR_STATUS["B3_L13_EDGE_MARK"] == "10/12" and eg.PRIOR_STATUS["B3_L13_VERIFIER"] == "NOT_STARTED"
    assert eg.PRIOR_STATUS["B3_L11"] == "VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT" and eg.PRIOR_STATUS["B3_L12A"] == "GDINO_GEOMETRY_FILTER_FAILED_DEVELOPMENT"
    assert pv.contract_digest().startswith("f2c38dc9feaa") and det.contract_digest().startswith("086a32a65e05") and c3.construct_digest().startswith("38ec105fc597")
    # a pass on new constructs never reopens B3-L13
    assert eg.interpretation(True, True)["b3l13"] == "PROPOSAL_UNION_COVERAGE_INSUFFICIENT" and eg.interpretation(True, True)["b3l13Reopened"] is False


def test_edge_critical_marker_immutable():
    assert eg.CRITICAL_MARKER == "EDGE_MARK_REMAINS_CRITICAL_FAMILY" and eg.EDGE_DIAGNOSTIC_ALLOWED is False
    assert c3.FAMILY_BY_CODE["F9"].family == "EDGE_MARK" and c3.FAMILY_BY_CODE["F9"].critical and not c3.FAMILY_BY_CODE["F9"].diagnostic
    assert ev.GATE_FAMILY["I"] == "EDGE_MARK"
    assert eg.CRITICAL_MARKER in PREREG.read_text(encoding="utf-8")


def test_diagnostic_downgrade_prohibited():
    with pytest.raises(eg.DowngradeProhibited):
        eg.downgrade_to_diagnostic("EDGE_MARK")
    assert "diagnostic" not in inspect.signature(eg.gate).parameters
    # 10/12 on any cell is a failure, never "sufficient"
    cells = {c: [True] * 10 + [False] * 2 for c in eg.cell_ids(eg.DEV_VARIANT)}
    g = eg.gate(eg.tables_from_hits(cells, eg.DEV_VARIANT), eg.DEV_VARIANT)
    assert not g["pass"] and any(k.startswith("J") for k in g["failed"])


def test_verifier_execution_prohibited():
    assert eg.VERIFIER_PROHIBITED == "VERIFIER_STAGE_PROHIBITED_IN_B3_L14A"
    with pytest.raises(eg.VerifierProhibited):
        eg.verifier_prohibited()
    for mod in (eg, ee, ec):
        src = inspect.getsource(mod)
        for token in ("fit_classifier", "oof_scores", "sklearn", "get_image_features", "CLIPModel", "proposal_embeddings", "select_threshold"):
            assert token not in src, (mod.__name__, token)
    assert eg.EXPECTED_VERIFIER_EMBEDDINGS == 0 and eg.EXPECTED_CLASSIFIER_FITS == 0


# ------------------------------------------------------------ 5 construct frozen before the old-miss audit


def test_construct_frozen_before_old_miss_audit(tmp_path):
    with pytest.raises(eg.NotFrozen):
        eg.require_construct_frozen(tmp_path, eg.contract_digest())
    with pytest.raises(eg.NotFrozen):
        ee.run("decompose", tmp_path, tmp_path, tmp_path)
    eg.write_construct_frozen(tmp_path, eg.contract_digest(), "0" * 40)
    assert eg.require_construct_frozen(tmp_path, eg.contract_digest())["freezeCommit"] == "0" * 40
    with pytest.raises(eg.NotFrozen):
        eg.require_construct_frozen(tmp_path, "f" * 64)
    assert ee.decompose.__doc__ and "cannot" in ee.decompose.__doc__.lower()


# ------------------------------------------------------------ 6-7 synthetic geometries


def test_real_trademarks_rejected():
    for bad in ("nike_swoosh", "apple_logo", "kakao_ring", "seolleyeon_mark", "coca_bar"):
        assert not eg.no_real_trademark_geometry(bad)
    for good in eg.DEV_GEOMETRIES + eg.HOLDOUT_GEOMETRIES:
        assert eg.no_real_trademark_geometry(good)
    with pytest.raises(ValueError):
        eg.render(_blank(), eg.EdgeCondition("TOP", "small", "nike_swoosh", eg.DEV_VARIANT))
    with pytest.raises(RuntimeError):
        eg.register_geometry("new_shape", lambda *a: None)


def test_dev_holdout_geometries_distinct():
    assert len(eg.DEV_GEOMETRIES) == 2 and len(eg.HOLDOUT_GEOMETRIES) == 2
    assert not set(eg.DEV_GEOMETRIES) & set(eg.HOLDOUT_GEOMETRIES)
    assert not (set(eg.DEV_GEOMETRIES) | set(eg.HOLDOUT_GEOMETRIES)) & set(c3.GEOMETRIES)   # B3-L11 geometries are not replicated
    digests = {}
    for name in eg.DEV_GEOMETRIES + eg.HOLDOUT_GEOMETRIES:
        img, boxes = eg.render(_blank(), eg.EdgeCondition("TOP", "medium", name, eg.DEV_VARIANT if name in eg.DEV_GEOMETRIES else eg.HOLDOUT_VARIANT))
        digests[name] = eg.image_digest(img)
        assert len(boxes) == 1
    assert len(set(digests.values())) == 4
    # structurally different from the B3-L11 EDGE_MARK geometries rendered in the same box
    for old in ("line_emblem", "icon_asymmetric"):
        layer = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        c3._draw_geometry(old, ImageDraw.Draw(layer), eg.edge_box(400, 400, "TOP", 28), 255)
        out = Image.alpha_composite(_blank().convert("RGBA"), layer).convert("RGB")
        assert eg.image_digest(out) not in digests.values()
    assert {"edge", "size_band", "geometry", "variant"} <= set(eg.EdgeCondition.__dataclass_fields__)


# ------------------------------------------------------------ 8-10 edges / sizes / alpha


def test_four_edge_sides_fixed():
    assert eg.EDGES == ("TOP", "BOTTOM", "LEFT", "RIGHT") and "corner" not in " ".join(eg.EDGES).lower()
    W, H, size = 1000, 800, 40
    inset = round(eg.INSET["relative"] * min(W, H))
    assert inset == 16 and eg.INSET["relative"] == 0.02
    assert eg.edge_box(W, H, "TOP", size) == (480, inset, 520, inset + size)
    assert eg.edge_box(W, H, "BOTTOM", size) == (480, H - inset - size, 520, H - inset)
    assert eg.edge_box(W, H, "LEFT", size) == (inset, 380, inset + size, 420)
    assert eg.edge_box(W, H, "RIGHT", size) == (W - inset - size, 380, W - inset, 420)
    with pytest.raises(ValueError):
        eg.edge_box(W, H, "CORNER_TL", size)
    assert {c.edge for c in eg.conditions(eg.DEV_VARIANT)} == set(eg.EDGES)


def test_sizes_fixed_from_prior_contract():
    assert eg.SIZE_BANDS == c3.SIZE_BANDS == {"small": 0.035, "medium": 0.07}
    assert {c.size_band for c in eg.conditions(eg.DEV_VARIANT)} == {"small", "medium"}
    img, boxes = eg.render(_blank(), eg.EdgeCondition("LEFT", "small", eg.DEV_GEOMETRIES[0], eg.DEV_VARIANT))
    b = boxes[0]["box"]
    assert b[2] - b[0] == b[3] - b[1] == round(0.035 * 400)


def test_opaque_alpha_fixed():
    assert eg.ALPHA_NAME == "OPAQUE" and eg.ALPHA == c3.ALPHAS["OPAQUE"] == 1.0
    assert all(c.alpha == 1.0 for c in eg.conditions(eg.DEV_VARIANT) + eg.conditions(eg.HOLDOUT_VARIANT))
    base = _blank()
    before = eg.image_digest(base)
    eg.render(base, eg.conditions(eg.DEV_VARIANT)[0])
    assert eg.image_digest(base) == before    # never mutates the base


# ------------------------------------------------------------ 11-14 detector set / thresholds / prompts / IoU


def test_detector_set_unchanged():
    assert eg.PROPOSAL_GENERATORS == pv.PROPOSAL_GENERATORS == {"owlv2-base-patch16-ensemble": "legacy_0.25", "grounding-dino-tiny": "historical_0.25", "florence2-phrase-grounding": "presence"}
    assert set(eg.PROPOSAL_GENERATORS) == set(det.CANDIDATES)
    assert det.CANDIDATES["grounding-dino-tiny"]["revision"] == "a2bb814dd30d776dcf7e30523b00659f4f141c71"
    assert det.CANDIDATES["owlv2-base-patch16-ensemble"]["revision"] == "cfd3195ba4ea9592eec887ded089f4c08eff231d"
    assert det.CANDIDATES["florence2-phrase-grounding"]["revision"] == "26b734a54fdfbf9c398351eedfabb7f27fc470b7"
    assert eg.DETECTOR_SET_DIGEST_PREFIX == "086a32a65e05" == det.contract_digest()[:12]
    with pytest.raises(RuntimeError):
        det.register_candidate("x", {})


def test_thresholds_unchanged():
    assert det.CANDIDATES["owlv2-base-patch16-ensemble"]["operatingPoints"]["legacy_0.25"] == {"threshold": 0.25}
    assert det.CANDIDATES["grounding-dino-tiny"]["operatingPoints"]["historical_0.25"] == {"threshold": 0.25}
    assert det.CANDIDATES["florence2-phrase-grounding"]["operatingPoints"]["presence"] == {"threshold": None}
    assert det.CANDIDATES["florence2-phrase-grounding"]["boxFilter"]["dropFullFrameAreaRatio"] == 0.50
    assert eg.union_proposals({"owlv2-base-patch16-ensemble": [_det([10, 10, 60, 60], 0.24)]}, SIZE) == []
    assert eg.union_proposals({"grounding-dino-tiny": [_det([10, 10, 60, 60], 0.25, "a logo")]}, SIZE) != []
    assert eg.THRESHOLDS == {"owlv2-base-patch16-ensemble": 0.25, "grounding-dino-tiny": {"box": 0.25, "text": 0.25}, "florence2-phrase-grounding": "presence"}


def test_prompts_unchanged():
    assert det.PROMPTS == ("a logo", "a watermark", "a brand emblem", "a graphic symbol") and eg.PROMPTS == det.PROMPTS
    for mod in (eg, ee, ec):
        src = inspect.getsource(mod).lower()
        for banned in ("edge logo", "border watermark", "edge watermark", "border logo"):
            assert banned not in src, (mod.__name__, banned)
    assert eg.union_proposals({"grounding-dino-tiny": [_det([10, 10, 60, 60], 0.5, "a person")]}, SIZE) == []


def test_iou_exactly_prior_contract():
    assert eg.IOU_MATCH == pv.IOU_MATCH == det.IOU_MATCH == bench.IOU_MATCH == 0.30 and eg.CONTAINMENT_CLAUSE is False
    truth = [{"box": [100, 100, 200, 200]}]
    assert eg.union_hit([{"box": [100, 100, 200, 170]}], truth)          # IoU 0.70
    assert not eg.union_hit([{"box": [100, 100, 200, 128]}], truth)      # IoU 0.28 -> not a hit; the rule is never lowered from a diagnostic
    assert not eg.union_hit([{"box": [50, 50, 400, 400]}], truth)        # containment is not a match
    assert eg.union_hit([{"box": [100, 100, 200, 130]}], truth)          # IoU 0.30 exactly


# ------------------------------------------------------------ 15-16 arithmetic


def test_development_matrix_arithmetic():
    assert len(eg.conditions(eg.DEV_VARIANT)) == len(eg.conditions(eg.HOLDOUT_VARIANT)) == 16 == 4 * 2 * 2
    assert eg.expected_counts(12, 8) == {"conditionsPerBase": 16, "developmentPositives": 192, "holdoutPositives": 128, "cellN": {"development": 12, "holdout": 8},
                                          "edgeN": {"development": 48, "holdout": 32}, "sizeN": {"development": 96, "holdout": 64}, "geometryN": {"development": 96, "holdout": 64}}
    assert len(eg.cell_ids(eg.DEV_VARIANT)) == 16 and len(set(eg.cell_ids(eg.DEV_VARIANT)) & set(eg.cell_ids(eg.HOLDOUT_VARIANT))) == 0
    assert eg.EXPECTED_BASES == {"development": 12, "holdout": 8}
    assert {c.geometry for c in eg.conditions(eg.HOLDOUT_VARIANT)} == set(eg.HOLDOUT_GEOMETRIES)


def test_per_cell_gate_arithmetic():
    assert eg.required(12) == 11 and eg.required(8) == 8 and eg.required(48) == 44 and eg.required(96) == 87 and eg.required(32) == 29 and eg.required(64) == 58
    assert eg.required(192, eg.OVERALL_FLOOR) == 183 and eg.required(128, eg.OVERALL_FLOOR) == 122
    assert eg.OVERALL_FLOOR == ev.OVERALL_RECALL_FLOOR == 0.95 and eg.AXIS_FLOOR == ev.FAMILY_RECALL_FLOOR == 0.90
    cells = {c: [True] * 12 for c in eg.cell_ids(eg.DEV_VARIANT)}
    ok = eg.gate(eg.tables_from_hits(cells, eg.DEV_VARIANT), eg.DEV_VARIANT)
    assert ok["pass"] and set(ok["criteria"]) == {"A", "B", "C", "D", "E", "F", "G", "H", "I"} | {f"J:{c}" for c in eg.cell_ids(eg.DEV_VARIANT)}
    cells[eg.cell_ids(eg.DEV_VARIANT)[0]] = [True] * 11 + [False]
    assert eg.gate(eg.tables_from_hits(cells, eg.DEV_VARIANT), eg.DEV_VARIANT)["pass"]          # 11/12 is the floor
    hold = {c: [True] * 7 + [False] for c in eg.cell_ids(eg.HOLDOUT_VARIANT)}
    assert not eg.gate(eg.tables_from_hits(hold, eg.HOLDOUT_VARIANT), eg.HOLDOUT_VARIANT)["pass"]  # holdout cell n=8 -> 8/8
    text = PREREG.read_text(encoding="utf-8")
    assert "11/12" in text and "8/8" in text and "183" in text and "122" in text


# ------------------------------------------------------------ 17-21 holdout access / one shot / designation / L11 untouched / no retune


def test_holdout_inaccessible_before_dev_pass(tmp_path):
    with pytest.raises(eg.NotFrozen):
        eg.holdout_guard(tmp_path, eg.contract_digest())
    with pytest.raises(eg.NotFrozen):
        ec.holdout_conditions(tmp_path)
    eg.write_dev_passed(tmp_path, "0" * 64, "1" * 64)
    with pytest.raises(eg.NotFrozen):
        eg.holdout_guard(tmp_path, eg.contract_digest())
    eg.write_dev_passed(tmp_path, eg.contract_digest(), "1" * 64)
    assert [c.variant for c in ec.holdout_conditions(tmp_path)] == [eg.HOLDOUT_VARIANT] * 16


def test_holdout_one_shot(tmp_path):
    digest = eg.contract_digest()
    eg.write_dev_passed(tmp_path, digest, "1" * 64)
    lock = eg.holdout_guard(tmp_path, digest)
    assert lock.name == eg.HOLDOUT_LOCK_NAME == "edge_proposal_generalization_v1_holdout.lock" != det.HOLDOUT_LOCK_NAME
    eg.mark_holdout(lock, digest)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        eg.holdout_guard(tmp_path, digest)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        ec.holdout_conditions(tmp_path)   # no further holdout inference after the single evaluation


def test_g4_g5_designation_not_globally_unseen():
    assert eg.HOLDOUT_NAME == "EDGE_CONSTRUCT_SPECIFIC_FROZEN_HOLDOUT" and eg.HOLDOUT_GROUPS == ("G4", "G5") and eg.DEVELOPMENT_GROUPS == ("G1", "G2", "G3")
    text = PREREG.read_text(encoding="utf-8")
    assert eg.HOLDOUT_NAME in text and "not globally unseen" in text and "virgin" not in text.lower()
    assert eg.definitions()["holdout"]["globallyUnseen"] is False


def test_b3l11_original_holdout_untouched(tmp_path):
    for mod in (ec, ee, eg):
        src = inspect.getsource(mod)
        assert "c3.HOLDOUT_VARIANT" not in src and "c3.conditions(" not in src and "c3.render(" not in src, mod.__name__
    audit = eg.l11_holdout_untouched_audit(tmp_path)
    assert audit["untouched"] and audit["captures"] == {n: False for n in eg.PROPOSAL_GENERATORS}
    (tmp_path / det.HOLDOUT_LOCK_NAME).write_text("{}", encoding="utf-8")
    assert not eg.l11_holdout_untouched_audit(tmp_path)["untouched"]
    assert ec.CAPTURE_FILE_PREFIX == "edge_capture_" and not l11cap.CAPTURE_VERSION.startswith("edge")
    assert eg.DEV_PASS_MARKER_NAME != det.SELECTED_MARKER_NAME and eg.DEV_PASS_MARKER_NAME != pv.SELECTED_MARKER_NAME


def test_no_post_holdout_retune(tmp_path):
    digest = eg.contract_digest()
    eg.write_dev_passed(tmp_path, digest, "1" * 64)
    marker = json.loads((tmp_path / eg.DEV_PASS_MARKER_NAME).read_text(encoding="utf-8"))
    assert marker["thresholds"] == eg.THRESHOLDS
    for mutate in ({"thresholds": {**marker["thresholds"], "owlv2-base-patch16-ensemble": 0.2}}, {"iouMatch": 0.25}, {"inset": {**marker["inset"], "relative": 0.01}},
                   {"holdoutGeometries": list(eg.DEV_GEOMETRIES)}, {"sizeBands": {"small": 0.05, "medium": 0.07}}, {"prompts": ["a logo"]}, {"contractDigest": "f" * 64}):
        (tmp_path / eg.DEV_PASS_MARKER_NAME).write_text(json.dumps({**marker, **mutate}), encoding="utf-8")
        with pytest.raises(eg.NotFrozen):
            eg.require_dev_passed(tmp_path, digest)
    assert eg.NO_RETUNE == ("threshold", "prompt", "geometry", "size", "inset", "matching", "detector set")


# ------------------------------------------------------------ 22 aggregate-only artifacts + wording


def test_aggregate_only_artifacts():
    forbidden = ("PRODUCTION_VALIDATED", "PRODUCTION_PRECISION_PROVEN", "LIVE_READY", "WATERMARK_POLICY_READY", "TEXT_POLICY_READY", "LIVE_POLICY_READY",
                 "three-rater", "adjudicated human ground truth", "production-ready", "globally unseen images", "virgin subject")
    for path in (REPORT, AGGREGATE, PREREG):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in forbidden:
            assert phrase not in text.replace("not globally unseen", ""), (path.name, phrase)
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
        assert not ({"embedding", "proposals", "detections", "groundTruth", "box", "boxes", "score", "path", "opaqueId"} & set(keys(report)))
        assert report["verifierEmbeddings"] == 0 and report["classifierFits"] == 0 and report["watermarkPolicyChanged"] is False and report["decisionDiff"] == 0
        assert report["priorStatus"]["B3_L13"] == "PROPOSAL_UNION_COVERAGE_INSUFFICIENT" and report["gaps"]["naturalPositive"] == "NATURAL_POSITIVE_EVIDENCE_MISSING"
        assert report["l11HoldoutAudit"]["untouched"] is True


# ------------------------------------------------------------ extra: evaluator end to end on synthetic captures, sensitivity markers, prereg digest


def test_development_stage_end_to_end_and_no_retune_on_fail(tmp_path):
    cap = tmp_path / "cap"; priv = tmp_path / "priv"; cap.mkdir(); priv.mkdir()
    _captures(cap, "development", lambda cond, b: True)
    rep = ee.run("development", cap, priv, tmp_path)
    assert rep["development"]["overall"] == {"k": 192, "n": 192, "rate": 1.0} and rep["development"]["gate"]["pass"]
    assert rep["verdict"] == "EDGE_PROPOSAL_GENERALIZATION_DEVELOPMENT_PASSED" and rep["holdoutEvaluated"] == 0
    assert (priv / eg.DEV_PASS_MARKER_NAME).exists()
    assert set(rep["development"]["cells"]) == set(eg.cell_ids(eg.DEV_VARIANT)) and rep["development"]["perDetector"]["grounding-dino-tiny"]["overall"]["k"] == 192
    assert rep["development"]["perDetector"]["owlv2-base-patch16-ensemble"]["overall"]["k"] == 0
    # failure: LEFT edge misses on two bases per cell -> gate fails, verdict STOP, no marker, sensitivity = placement
    cap2 = tmp_path / "cap2"; priv2 = tmp_path / "priv2"; cap2.mkdir(); priv2.mkdir()
    _captures(cap2, "development", lambda cond, b: not (cond.edge == "LEFT" and b < 2))
    rep2 = ee.run("development", cap2, priv2, tmp_path)
    assert rep2["verdict"] == "EDGE_PROPOSAL_GENERALIZATION_FAILED_DEVELOPMENT" and not (priv2 / eg.DEV_PASS_MARKER_NAME).exists()
    assert rep2["development"]["edges"]["LEFT"] == {"k": 24, "n": 48, "rate": 0.5}
    assert rep2["interpretation"]["status"] == "EDGE_PROPOSAL_GAP_REPLICATED" and "EDGE_PLACEMENT_SENSITIVE" in rep2["interpretation"]["markers"]
    assert rep2["nextStepIsNotRetuning"] is True
    with pytest.raises(eg.NotFrozen):
        ee.run("holdout", cap2, priv2, tmp_path)


def test_holdout_stage_end_to_end(tmp_path):
    cap = tmp_path / "cap"; priv = tmp_path / "priv"; cap.mkdir(); priv.mkdir()
    _captures(cap, "development", lambda cond, b: True)
    ee.run("development", cap, priv, tmp_path)
    _captures(cap, "holdout", lambda cond, b: not (cond.size_band == "small" and b == 0), groups=("G4", "G5"))
    rep = ee.run("holdout", cap, priv, tmp_path)
    assert rep["holdoutEvaluated"] == 1 and rep["holdout"]["overall"] == {"k": 112, "n": 128, "rate": 0.875}
    assert rep["verdict"] == "EDGE_PROPOSAL_GENERALIZATION_HOLDOUT_FAILED" and "EDGE_SIZE_SENSITIVE" in rep["interpretation"]["markers"]
    assert (priv / eg.HOLDOUT_LOCK_NAME).exists()
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        ee.run("holdout", cap, priv, tmp_path)


def test_sensitivity_markers_pre_registered():
    def res(edges, sizes, geoms, overall=True):
        crit = {"A": overall, **{k: edges[i] for i, k in enumerate("BCDE")}, "F": sizes[0], "G": sizes[1], "H": geoms[0], "I": geoms[1]}
        return {"criteria": crit, "pass": all(crit.values())}
    assert eg.sensitivity_markers(res([True, True, False, True], [True, True], [True, True])) == ["EDGE_PLACEMENT_SENSITIVE"]
    assert eg.sensitivity_markers(res([True] * 4, [False, True], [True, True])) == ["EDGE_SIZE_SENSITIVE"]
    assert eg.sensitivity_markers(res([True] * 4, [True, True], [False, True])) == ["EDGE_GEOMETRY_SENSITIVE"]
    assert eg.sensitivity_markers(res([False] * 4, [False, False], [False, False], overall=False)) == ["EDGE_ZERO_SHOT_GENERALIZATION_LIMIT"]
    m = eg.sensitivity_markers(res([True, False, True, True], [False, True], [True, True]))
    assert "MIXED" in m and "EDGE_PLACEMENT_SENSITIVE" in m and "EDGE_SIZE_SENSITIVE" in m
    assert eg.sensitivity_markers(res([True] * 4, [True, True], [True, True])) == []
    assert eg.interpretation(True, True)["status"] == "EDGE_PROPOSAL_GAP_NOT_REPLICATED_ON_NEW_CONSTRUCTS"
    assert eg.interpretation(False, None)["status"] == "EDGE_PROPOSAL_GAP_REPLICATED" and eg.interpretation(True, False)["status"] == "EDGE_PROPOSAL_GAP_REPLICATED"
    assert eg.interpretation(True, None)["status"] == "HOLDOUT_PENDING"
    assert eg.interpretation(True, True)["b3l13VerifierContinuationAllowed"] is False


def test_decomposition_categories_fixed():
    assert eg.DECOMPOSITION_CATEGORIES == ("NO_RELEVANT_PROPOSAL", "PROPOSAL_WRONG_LABEL_ONLY", "LOCALIZATION_MISS_IOU_BELOW_030", "FULL_FRAME_FILTER_EFFECT", "OTHER")
    truth = [{"box": [100, 100, 160, 160]}]
    assert eg.classify_miss("grounding-dino-tiny", [], truth, SIZE) == "NO_RELEVANT_PROPOSAL"
    assert eg.classify_miss("grounding-dino-tiny", [_det([102, 102, 162, 162], 0.4, "a person")], truth, SIZE) == "PROPOSAL_WRONG_LABEL_ONLY"
    assert eg.classify_miss("grounding-dino-tiny", [_det([130, 130, 200, 200], 0.4, "a logo")], truth, SIZE) == "LOCALIZATION_MISS_IOU_BELOW_030"
    assert eg.classify_miss("grounding-dino-tiny", [_det([102, 102, 162, 162], 0.10, "a logo")], truth, SIZE) == "OTHER"
    assert eg.classify_miss("florence2-phrase-grounding", [_det([0, 0, 999, 999], None, "a watermark")], truth, SIZE) == "FULL_FRAME_FILTER_EFFECT"
    assert eg.classify_miss("florence2-phrase-grounding", [_det([500, 500, 600, 600], None, "a watermark")], truth, SIZE) == "NO_RELEVANT_PROPOSAL"
    with pytest.raises(ValueError):
        eg.classify_miss("grounding-dino-tiny", [_det([102, 102, 162, 162], 0.4, "a logo")], truth, SIZE)   # not a miss


def test_prereg_digests_and_contract_frozen_in_doc():
    text = PREREG.read_text(encoding="utf-8")
    assert eg.contract_digest()[:12] in text and eg.construct_digest()[:12] in text and det.contract_digest()[:12] in text
    assert all(g in text for g in eg.DEV_GEOMETRIES + eg.HOLDOUT_GEOMETRIES) and "0.02" in text
    assert eg.VERSION == "EDGE_MARK_GENERALIZATION_V1" and eg.VERSION in text
    assert "UI" in text and ev.NEW_REVIEW_CEILING == 0.10


def test_capture_guards_not_lowered():
    assert ec.MIN_AVAILABLE_GB_TO_START == l11cap.MIN_AVAILABLE_GB_TO_START == {"owl": 4.0, "gdino": 3.0, "florence": 4.0}
    assert ec.MIN_AVAILABLE_GB_DURING == l11cap.MIN_AVAILABLE_GB_DURING == 0.6
    assert ec.MAX_LONG_SIDE == det.MAX_LONG_SIDE == 2048
