"""CI tests for B3-L12A GDINO_BOX_GEOMETRY_FILTER_V1. Pure logic: no model, no user image, no label."""

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
import avatar_gdino_geometry_eval as ge  # noqa: E402
import avatar_gdino_geometry_filter as gf  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

PREREG = REPO / "docs" / "avatar-production" / "b3-l12a-preregistration.md"
REPORT = REPO / "docs" / "avatar-production" / "b3-l12a-gdino-geometry-filter-report.md"
AGGREGATE = REPO / "docs" / "avatar-production" / "b3-l12a-gdino-geometry-filter-aggregate-v1.json"
L11_AGGREGATE = REPO / "docs" / "avatar-production" / "b3-l11-visual-mark-detector-aggregate-v1.json"
SIZE = (1000, 1000)
G2 = gf.CANDIDATE_BY_ID["G2"]


def _d(box, score=0.3, label="a logo a watermark"):
    return {"box": list(box), "score": score, "label": label}


# ------------------------------------------------------------ 1-4 immutability / OR / operating point / prompts


def test_b3l11_verdict_immutable():
    a = json.loads(L11_AGGREGATE.read_text(encoding="utf-8"))
    assert a["verdict"] == "VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT" and a["holdoutEvaluated"] == 0
    gd = [t for t in a["development"]["table"] if t["detector"] == "grounding-dino-tiny" and t["operatingPoint"] == "historical_0.25"][0]
    assert gd["clean"]["cleanImageResponse"] == 12 and gd["clean"]["newAllowToReview"] == 10 and gd["overall"]["k"] == 163
    assert gf.PRIOR_STATUS["B3_L11"] == "VISUAL_MARK_DETECTOR_FAILED_DEVELOPMENT" and gf.PRIOR_STATUS["B3_L11_HOLDOUT_EXECUTIONS"] == 0
    assert det.contract_digest().startswith("086a32a65e05") and c3.construct_digest().startswith("38ec105fc597")


def test_or_ensemble_structurally_rejected():
    a = json.loads(L11_AGGREGATE.read_text(encoding="utf-8"))
    fl = [t for t in a["development"]["table"] if t["detector"] == "florence2-phrase-grounding"][0]
    assert gf.or_ensemble_min_clean_response(0, 1, fl["clean"]["newAllowToReview"]) == 4 > 1   # cannot meet A (<= 1/12)
    assert gf.OR_ENSEMBLE_MARKER == "FIXED_OR_ENSEMBLE_REJECTED_BY_DEVELOPMENT_DOMINANCE" and gf.OR_ENSEMBLE_MARKER in PREREG.read_text(encoding="utf-8")


def test_gdino_threshold_exactly_0_25():
    assert gf.OPERATING_POINT == {"threshold": 0.25} and gf.OPERATING_POINT_ID == "historical_0.25"
    assert det.CANDIDATES[gf.DETECTOR]["operatingPoints"]["historical_0.25"] == {"threshold": 0.25}
    assert det.CANDIDATES[gf.DETECTOR]["revision"] == "a2bb814dd30d776dcf7e30523b00659f4f141c71" and det.CANDIDATES[gf.DETECTOR]["license"] == "apache-2.0"
    assert gf.surviving(G2, [_d([10, 10, 60, 60], score=0.24)], SIZE) == []


def test_prompts_unchanged():
    assert det.PROMPTS == ("a logo", "a watermark", "a brand emblem", "a graphic symbol")
    assert det.CANDIDATES[gf.DETECTOR]["prompts"] == list(det.PROMPTS)
    assert gf.surviving(G2, [_d([10, 10, 60, 60], label="a person")], SIZE) == []


# ------------------------------------------------------------ 5-8 forbidden predicate inputs


def test_query_label_forbidden_in_geometry_predicate():
    assert "label" in gf.FORBIDDEN_PREDICATE_INPUTS and gf.ALLOWED_FEATURES == ("normalizedArea", "aspectRatio")
    with pytest.raises(ValueError):
        gf.surviving(G2, [_d([10, 10, 60, 60])], SIZE, label="a logo")
    # the same geometry survives regardless of which query labelled it
    for lab in det.PROMPTS:
        assert len(gf.surviving(G2, [_d([10, 10, 60, 60], label=lab)], SIZE)) == 1


@pytest.mark.parametrize("field", sorted(sel.HUMAN_ONLY_FIELDS))
def test_human_fields_forbidden(field):
    with pytest.raises(ValueError):
        gf.surviving(G2, [_d([10, 10, 60, 60])], SIZE, **{field: "yes"})


@pytest.mark.parametrize("field", ("family", "familyCode", "groupKey", "participantGroup", "baseOpaqueId"))
def test_family_forbidden(field):
    with pytest.raises(ValueError):
        gf.surviving(G2, [_d([10, 10, 60, 60])], SIZE, **{field: "EDGE_MARK"})


@pytest.mark.parametrize("field", ("groundTruth", "groundTruthBox", "groundTruthBoxes", "isClean", "markPresent"))
def test_gt_box_forbidden_runtime(field):
    with pytest.raises(ValueError):
        gf.surviving(G2, [_d([10, 10, 60, 60])], SIZE, **{field: [[0, 0, 1, 1]]})
    assert set(gf.box_geometry([10, 10, 60, 60], SIZE)) == {"normalizedArea", "aspectRatio"}


# ------------------------------------------------------------ 9-12 blinding / candidate contract


def test_positive_box_geometry_inaccessible_before_candidate_freeze(tmp_path):
    cap = tmp_path / f"capture_{gf.DETECTOR}_development.jsonl"
    rows = [{"conditionId": "b0:CLEAN", "opaqueId": "b0", "imageSize": [1000, 1000], "meta": {"family": None}, "groundTruth": [], "detections": [_d([0, 0, 900, 900])], "seconds": 1.0},
            {"conditionId": "b0:F1:medium:D", "opaqueId": "b0", "imageSize": [1000, 1000], "meta": {"family": "TEXT_WATERMARK_OPAQUE"}, "groundTruth": [{"box": [1, 1, 2, 2]}], "detections": [_d([1, 1, 2, 2])], "seconds": 1.0}]
    cap.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert len(ge._rows(cap, clean_only=True)) == 1
    inv = ge.clean_inventory(ge._rows(cap, clean_only=True))
    assert inv["boxes"] == 1 and inv["fullFrameLike"] == 1
    report = ge.run("clean-inventory", tmp_path, tmp_path, [], {"labels": []})
    assert report["positiveRowsOpened"] is False and "development" not in report


def test_candidate_count_at_most_4():
    assert 1 <= len(gf.CANDIDATES) <= gf.MAX_CANDIDATES == 4
    assert [c.id for c in gf.CANDIDATES] == ["G1", "G2", "G3", "G4"]


def test_candidate_ordering_frozen():
    ranks = [c.rank for c in gf.CANDIDATES]
    assert ranks == [1, 2, 3, 4]
    areas = [c.max_area for c in gf.CANDIDATES]
    assert areas == sorted(areas, reverse=True)      # least -> most aggressive
    text = PREREG.read_text(encoding="utf-8")
    assert gf.contract_digest()[:12] in text and gf.VERSION in text and gf.CANDIDATE_SET_VERSION in text and gf.DESIGNATION in text
    for c in gf.CANDIDATES:
        assert c.predicate in text


def test_fine_midpoint_geometry_search_prohibited():
    with pytest.raises(ValueError):
        gf.Candidate("GX", 9, 0.137, None)
    with pytest.raises(ValueError):
        gf.Candidate("GX", 9, 0.08, 3.5)
    assert gf.ALLOWED_AREA_EDGES == (0.03, 0.08, 0.20, 0.50) and gf.ALLOWED_ASPECT_CAPS == (3.0, 4.0)
    assert gf.ALLOWED_AREA_EDGES[0] == 0.03 and gf.ALLOWED_AREA_EDGES[1] == 0.08   # canonical TINY / SMALL region area constants


# ------------------------------------------------------------ 13-15 shadow semantics


def test_geometry_filter_review_only():
    assert gf.shadow_action("allow", True) == "review" and gf.shadow_action("allow", False) == "allow"
    with pytest.raises(ValueError):
        gf.shadow_action("escalate", True)
    assert G2.keeps({"normalizedArea": 0.01, "aspectRatio": 1.0}) and not G2.keeps({"normalizedArea": 0.25, "aspectRatio": 1.0}) and not G2.keeps({"normalizedArea": 0.01, "aspectRatio": 4.5})


def test_canonical_review_reject_never_downgraded():
    assert gf.shadow_action("review", False) == "review" and gf.shadow_action("reject", False) == "reject" and gf.shadow_action("reject", True) == "reject"
    rows = [{"conditionId": "b0:CLEAN", "opaqueId": "b0", "imageSize": [1000, 1000], "meta": {"family": None}, "groundTruth": [], "detections": [_d([10, 10, 60, 60])], "seconds": 1.0}]
    r = ge.evaluate(G2, rows, {"b0": "reject"}, {"b0": "negative"})
    assert r["clean"]["hardRejectBypass"] == 0 and r["clean"]["downgrades"] == 0 and r["criteria"]["K"] and r["criteria"]["L"]


def test_existing_canonical_review_not_counted_as_new_burden():
    rows = [{"conditionId": f"b{i}:CLEAN", "opaqueId": f"b{i}", "imageSize": [1000, 1000], "meta": {"family": None}, "groundTruth": [], "detections": [_d([10, 10, 60, 60])], "seconds": 1.0} for i in range(2)]
    r = ge.evaluate(G2, rows, {"b0": "review", "b1": "allow"}, {"b0": "negative", "b1": "negative"})
    assert r["clean"]["cleanImageResponse"] == 2 and r["clean"]["newAllowToReview"] == 1 and r["clean"]["existingCanonicalBurdenNotCounted"] == 1


# ------------------------------------------------------------ 16-21 provenance / holdout guards


def test_development_raw_capture_exact_provenance_required(tmp_path):
    p = ge.provenance(tmp_path, "development")
    assert not p["exact"]
    (tmp_path / f"run_meta_{gf.DETECTOR}_development.json").write_text(json.dumps({"repo": "IDEA-Research/grounding-dino-tiny", "revision": "0" * 40, "license": "apache-2.0",
        "contractDigestPrefix": det.contract_digest()[:12], "constructDigestPrefix": c3.construct_digest()[:12], "variant": c3.DEV_VARIANT, "originalsUnchanged": True}), encoding="utf-8")
    assert not ge.provenance(tmp_path, "development")["exact"]   # wrong revision
    with pytest.raises(SystemExit):
        ge.run("development", tmp_path, tmp_path, [], {"labels": []})


def test_holdout_impossible_without_selected_filter(tmp_path):
    with pytest.raises(gf.NotFrozen):
        gf.holdout_guard(tmp_path, gf.contract_digest())
    gf.write_selected(tmp_path, G2, "0" * 64, "1" * 64)
    with pytest.raises(gf.NotFrozen):
        gf.holdout_guard(tmp_path, gf.contract_digest())


def test_holdout_variants_unchanged_from_b3l11():
    assert c3.construct_digest().startswith("38ec105fc597")
    hold = c3.conditions(c3.HOLDOUT_VARIANT)
    assert len(hold) == 15 and len(c3.HOLDOUT_GROUPS) == 2 and 15 * 8 == 120
    assert {c.text for c in hold if c.text} == {"PROOF", "UNCONFIRMED", "FOR REVIEW", "QZ4K9", "KOLT"}
    assert gf.holdout_unopened_audit(Path("C:/definitely/not/here"))["unopened"]


def test_holdout_one_shot(tmp_path):
    digest = gf.contract_digest()
    gf.write_selected(tmp_path, G2, digest, "1" * 64)
    lock = gf.holdout_guard(tmp_path, digest)
    assert lock.name == det.HOLDOUT_LOCK_NAME == "visual_mark_detector_v1_holdout.lock"
    ev.mark_holdout(lock, digest)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        gf.holdout_guard(tmp_path, digest)


def test_one_of_eight_clean_fails_a():
    rows = [{"conditionId": f"b{i}:CLEAN", "opaqueId": f"b{i}", "imageSize": [1000, 1000], "meta": {"family": None}, "groundTruth": [], "detections": [_d([10, 10, 60, 60])] if i == 0 else [], "seconds": 1.0} for i in range(8)]
    r = ge.evaluate(G2, rows, {f"b{i}": "allow" for i in range(8)}, {f"b{i}": "negative" for i in range(8)})
    assert r["clean"]["newReviewRate"] == 0.125 and r["criteria"]["A"] is False
    assert ev.required_hits(8, 0.90) == 8 and ev.required_hits(16, 0.90) == 15 and ev.required_hits(112, 0.95) == 107


def test_post_holdout_retuning_prohibited(tmp_path):
    digest = gf.contract_digest()
    gf.write_selected(tmp_path, G2, digest, "1" * 64)
    marker = json.loads((tmp_path / det.SELECTED_MARKER_NAME).read_text(encoding="utf-8"))
    marker["params"] = {"threshold": 0.30}
    (tmp_path / det.SELECTED_MARKER_NAME).write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(gf.NotFrozen):
        gf.require_selected(tmp_path, digest)
    marker["params"] = {"threshold": 0.25}; marker["geometryCandidate"] = "G9"
    (tmp_path / det.SELECTED_MARKER_NAME).write_text(json.dumps(marker), encoding="utf-8")
    with pytest.raises(gf.NotFrozen):
        gf.require_selected(tmp_path, digest)


# ------------------------------------------------------------ 22-23 gate / privacy


def test_soft_needs_review_ui_policy_does_not_weaken_qa_gate():
    assert ev.NEW_REVIEW_CEILING == 0.10 and ev.OVERALL_RECALL_FLOOR == 0.95 and ev.FAMILY_RECALL_FLOOR == 0.90
    text = PREREG.read_text(encoding="utf-8")
    assert "0.10" in text and "UI" in text


def test_aggregate_only_artifact():
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
        assert not ({"detections", "groundTruth", "box", "rows_raw"} & set(keys(report)))
        assert report["watermarkPolicyChanged"] is False and report["decisionDiff"] == 0 and report["holdoutEvaluated"] in (0, 1)
        assert report["gaps"]["naturalPositive"] == "NATURAL_POSITIVE_EVIDENCE_MISSING"
