"""CI tests for the B3-L7 V2 challenge set, gate V2 and evaluation runner. No model, no user image."""

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_challenge_eval as ev  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_watermark_controls as controls  # noqa: E402

PREREG = Path(__file__).resolve().parents[1] / "docs" / "avatar-production" / "b3-l7-preregistration.md"


def _base():
    return controls.build_controls()[8][1]  # synthetic no-text base


# ------------------------------------------------------------ versions


def test_gate_v2_is_a_distinct_version_and_v1_is_untouched():
    assert v2.GATE_VERSION == "OWLV2_CONTROLLED_CHALLENGE_GATE_V2"
    assert v2.EVIDENCE_LABEL == "G004_CONTROLLED_MARK_CHALLENGE_EVIDENCE"
    assert calib.GATE_VERSION == "owlv2_provisional_shadow_gate_v1"
    assert calib.PROVISIONAL_PRECISION_FLOOR == 0.80 and calib.CLEAN_NEGATIVE_NEW_REVIEW_CEILING == 0.10
    assert v2.THRESHOLD_GRID == sel.THRESHOLD_GRID and v2.PROMPTS == sel.PROMPTS
    assert v2.DEVELOPMENT_GROUPS == ("G1", "G2", "G3") and v2.HOLDOUT_GROUPS == ("G4", "G5")
    assert v2.H4_VERSION == "H4-DIRECT-1"


def test_v2_criteria_are_frozen():
    assert v2.NEW_REVIEW_CEILING == 0.10
    assert v2.OVERALL_RECALL_FLOOR == 0.95
    assert v2.CRITICAL_FAMILIES == ("TEXT_WATERMARK_OPAQUE", "TEXT_WATERMARK_TRANSLUCENT", "GRAPHICAL_WATERMARK", "LOGO_LIKE_EMBLEM")
    assert v2.CRITICAL_FAMILY_FLOOR == 0.90 and v2.CORNER_FLOOR == 0.90 and v2.EDGE_FLOOR == 0.90


def test_preregistration_document_exists_before_results():
    text = PREREG.read_text(encoding="utf-8")
    for token in (v2.GATE_VERSION, v2.EVIDENCE_LABEL, "0.95", "0.90", "NATURAL_POSITIVE_EVIDENCE_MISSING", "exactly once"):
        assert token in text


# ------------------------------------------------------------ families


def test_required_families_present_and_matched():
    names = {f.family for f in v2.FAMILIES}
    for required in ("GRAPHIC_SYMBOL", "LOGO_LIKE_EMBLEM", "TEXT_WATERMARK_OPAQUE", "TEXT_WATERMARK_TRANSLUCENT",
                     "GRAPHICAL_WATERMARK", "BRAND_LIKE_TEXT_AND_SYMBOL", "SMALL_CORNER_MARK", "EDGE_MARK"):
        assert required in names
    opaque = v2.FAMILY_BY_NAME["TEXT_WATERMARK_OPAQUE"]
    translucent = v2.FAMILY_BY_NAME["TEXT_WATERMARK_TRANSLUCENT"]
    assert opaque.text == translucent.text and opaque.rel_size == translucent.rel_size and opaque.anchor == translucent.anchor
    assert opaque.alpha == 1.0 and translucent.alpha < 0.5
    assert v2.FAMILY_BY_NAME["GRAPHICAL_WATERMARK"].text is None and v2.FAMILY_BY_NAME["LOGO_LIKE_EMBLEM"].text is None
    assert v2.FAMILY_BY_NAME["SMALL_CORNER_MARK"].placement == "corner" and v2.FAMILY_BY_NAME["EDGE_MARK"].placement == "edge"


def test_no_real_trademark_in_any_family():
    for f in v2.FAMILIES:
        assert v2.no_real_trademark(f.text), f.family
        assert f.text is None or f.text in v2.SYNTHETIC_WORDS
    assert not v2.no_real_trademark("Nike")
    assert not v2.no_real_trademark("coca-cola")


def test_render_is_deterministic_and_never_mutates_base():
    base = _base()
    before = base.tobytes()
    for f in v2.FAMILIES:
        a, ta = v2.render_family(base, f)
        b, tb = v2.render_family(base, f)
        assert a.tobytes() == b.tobytes() and ta == tb
        assert a is not base and a.size == base.size
        assert ta and all(0 <= x[0] < x[2] <= base.width and 0 <= x[1] < x[3] <= base.height for x in (t["box"] for t in ta))
    assert base.tobytes() == before


def test_matched_spec_yields_same_normalized_box_on_any_same_size_base():
    a = Image.new("RGB", (400, 400), (10, 20, 30))
    b = Image.new("RGB", (400, 400), (200, 210, 220))
    for f in v2.FAMILIES:
        _, ta = v2.render_family(a, f)
        _, tb = v2.render_family(b, f)
        assert [t["box"] for t in ta] == [t["box"] for t in tb], f.family


def test_manifest_row_is_pii_free_and_typed():
    _, truth = v2.render_family(_base(), v2.FAMILY_BY_CODE["F3"])
    row = v2.manifest_row(v2.FAMILY_BY_CODE["F3"], "g004-avatar-001", "G1", truth)
    assert row["textPresent"] is True and row["graphicalMarkPresent"] is False and row["overlayPresent"] is True
    assert row["safetyCritical"] is True and row["placement"] == "center"
    assert not bench.privacy_violations(row)


def test_capture_script_never_persists_images_and_is_offline():
    src = (SCRIPTS / "avatar_owlv2_challenge_capture.py").read_text(encoding="utf-8")
    assert ".save(" not in src and "write_bytes" not in src
    assert 'os.environ.setdefault("HF_HUB_OFFLINE", "1")' in src and "ORIGINALS_CHANGED" in src
    assert "EXISTING_CAPTURE_REVISION_MISMATCH" in src


# ------------------------------------------------------------ gate V2 logic


def _conf(new_reviews, negatives):
    return {"newReviewRate": new_reviews / negatives if negatives else None, "newDetectorInducedReviews": new_reviews, "humanNegatives": negatives}


def _fam(rate):
    return {"rate": rate}


def _all_families(rate=1.0):
    return {f.family: _fam(rate) for f in v2.FAMILIES}


def test_eligible_v2_passes_only_when_all_criteria_hold():
    ok = v2.eligible_v2(_conf(1, 12), _all_families(1.0), 1.0, artifact_regressions=0, hard_reject_bypass=0)
    assert ok["eligible"] is True and ok["gateVersion"] == v2.GATE_VERSION
    assert v2.eligible_v2(_conf(2, 12), _all_families(1.0), 1.0, artifact_regressions=0, hard_reject_bypass=0)["eligible"] is False  # A
    assert v2.eligible_v2(_conf(0, 12), _all_families(1.0), 0.94, artifact_regressions=0, hard_reject_bypass=0)["eligible"] is False  # B
    fams = _all_families(1.0); fams["GRAPHICAL_WATERMARK"] = _fam(0.85)
    assert v2.eligible_v2(_conf(0, 12), fams, 0.99, artifact_regressions=0, hard_reject_bypass=0)["criteria"]["C_safety_critical_family_recall"]["pass"] is False
    fams = _all_families(1.0); fams["SMALL_CORNER_MARK"] = _fam(0.8)
    assert v2.eligible_v2(_conf(0, 12), fams, 0.99, artifact_regressions=0, hard_reject_bypass=0)["criteria"]["D_small_corner_recall"]["pass"] is False
    fams = _all_families(1.0); fams["EDGE_MARK"] = _fam(0.8)
    assert v2.eligible_v2(_conf(0, 12), fams, 0.99, artifact_regressions=0, hard_reject_bypass=0)["criteria"]["E_edge_recall"]["pass"] is False
    assert v2.eligible_v2(_conf(0, 12), _all_families(1.0), 1.0, artifact_regressions=1, hard_reject_bypass=0)["eligible"] is False  # F
    assert v2.eligible_v2(_conf(0, 12), _all_families(1.0), 1.0, artifact_regressions=0, hard_reject_bypass=1)["eligible"] is False  # G


def test_clean_specificity_and_positive_sensitivity_are_separate_blocks():
    clean = [{"detections": [{"score": 0.5, "label": "a logo", "box": [0, 0, 5, 5]}], "truth": "negative", "currentAction": "allow"},
             {"detections": [], "truth": "negative", "currentAction": "review"}]
    pos = [{"family": "EDGE_MARK", "detections": [{"score": 0.5, "label": "a watermark", "box": [100, 100, 140, 140]}],
            "groundTruth": [[100, 100, 140, 140]], "currentAction": "allow"},
           {"family": "EDGE_MARK", "detections": [], "groundTruth": [[100, 100, 140, 140]], "currentAction": "allow"}]
    out = ev.split_eval(clean, pos, 0.25)
    assert out["cleanNegative"]["newDetectorInducedReviews"] == 1 and out["cleanNegative"]["humanNegatives"] == 2
    assert out["cleanNegative"]["currentReviewBurden"] == 1 and out["cleanNegative"]["h4ReviewBurden"] == 2
    fam = out["controlledPositive"]["families"]["EDGE_MARK"]
    assert fam["imageHits"] == 1 and fam["modelMisses"] == 1 and fam["policyMisses"] == 0 and fam["h4Flagged"] == 1
    assert fam["promptsThatHit"] == {"a watermark": 1}
    assert "precision" not in json.dumps(out["controlledPositive"]).lower()


def test_h4_has_no_florence_prerequisite_and_is_escalate_only():
    assert sel.h4_direct_action("allow", True) == "review"
    assert sel.h4_direct_action("reject", True) == "reject"
    assert sel.h4_direct_action("review", False) == "review"
    with pytest.raises(ValueError):
        sel.h4_direct_action("allow", True, visibleGraphicalMark="yes")


# ------------------------------------------------------------ runner


def _capture(groups, clean_hit, pos_hit_families):
    clean_rows, pos_rows = [], []
    for g in groups:
        oid = f"g004-avatar-{g[1:].zfill(3)}"
        clean_rows.append({"conditionId": f"{oid}:V0", "opaqueId": oid, "groupKey": g, "variant": "V0",
                           "detections": [{"score": 0.5, "label": "a logo", "box": [0, 0, 5, 5]}] if oid in clean_hit else []})
        for f in v2.FAMILIES:
            hit = f.family in pos_hit_families
            pos_rows.append({"conditionId": f"{oid}:{f.code}", "opaqueId": oid, "groupKey": g, "family": f.family, "familyCode": f.code,
                             "groundTruth": [[100.0, 100.0, 140.0, 140.0]],
                             "detections": [{"score": 0.9, "label": "a graphic symbol", "box": [101.0, 101.0, 139.0, 139.0]}] if hit else []})
    return {"rows": clean_rows, "revision": "r"}, {"rows": pos_rows, "revision": "r"}


def _labels(groups):
    return {"complete": True, "unresolvedCount": 0, "truthResolutionVersion": "TEST",
            "labels": [{"evaluationId": f"g004-avatar-{g[1:].zfill(3)}", "visibleGraphicalMark": "no"} for g in groups]}


def test_runner_selects_lowest_eligible_and_evaluates_holdout_once(tmp_path):
    groups = ("G1", "G2", "G3", "G4", "G5")
    clean, pos = _capture(groups, clean_hit=set(), pos_hit_families={f.family for f in v2.FAMILIES})
    report = ev.run(clean, pos, [], _labels(groups), tmp_path)
    assert report["selection"]["status"] == "SELECTED" and report["selection"]["selectedThreshold"] == 0.05
    assert report["holdoutEvaluated"] == 1 and (tmp_path / sel.HOLDOUT_LOCK_NAME).exists()
    assert report["v2Verdict"] == "OWLV2_CONTROLLED_CHALLENGE_GATE_PASSED"
    assert report["naturalPositiveLimitation"] == "NATURAL_POSITIVE_EVIDENCE_MISSING"
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        ev.run(clean, pos, [], _labels(groups), tmp_path)


def test_runner_fails_development_without_touching_holdout(tmp_path):
    groups = ("G1", "G2", "G3", "G4", "G5")
    families = {f.family for f in v2.FAMILIES} - {"GRAPHICAL_WATERMARK"}  # a critical family misses everywhere
    clean, pos = _capture(groups, clean_hit=set(), pos_hit_families=families)
    report = ev.run(clean, pos, [], _labels(groups), tmp_path)
    assert report["selection"]["status"] == "NO_THRESHOLD_SELECTED"
    assert report["v2Verdict"] == "OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT"
    assert report["holdoutEvaluated"] == 0 and not (tmp_path / sel.HOLDOUT_LOCK_NAME).exists()
    assert "holdout" not in report


def test_runner_rejects_group_leak(tmp_path):
    groups = ("G1", "G4")
    clean, pos = _capture(groups, clean_hit=set(), pos_hit_families=set())
    for r in pos["rows"]:
        r["groupKey"] = "G1"  # the same base ends up in dev via challenge rows and in holdout via its own id
    pos["rows"][-1]["groupKey"] = "G4"
    pos["rows"][-1]["opaqueId"] = pos["rows"][0]["opaqueId"]
    with pytest.raises(AssertionError, match="GROUP_LEAK"):
        ev.run(clean, pos, [], _labels(groups), tmp_path)


def test_runner_report_is_aggregate_only():
    groups = ("G1", "G2", "G3", "G4", "G5")
    clean, pos = _capture(groups, clean_hit=set(), pos_hit_families={f.family for f in v2.FAMILIES})
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        report = ev.run(clean, pos, [], _labels(groups), Path(d))
    text = json.dumps(report)
    assert "g004-avatar-0" not in text and "detections" not in text
    assert not bench.privacy_violations(report)
