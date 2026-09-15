"""CI tests for B3-L11 VISUAL_MARK_CHALLENGE_V3 + DETECTOR_CANDIDATE_SET_V1. Pure logic: no model, no user image, no label."""

import json
import re
import sys
from pathlib import Path

import pytest
from PIL import Image

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
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_text_policy_shadow as tp  # noqa: E402
import avatar_visual_mark_challenge_v3 as c3  # noqa: E402
import avatar_visual_mark_detectors as det  # noqa: E402
import avatar_visual_mark_eval as ev  # noqa: E402

PREREG = REPO / "docs" / "avatar-production" / "b3-l11-preregistration.md"
REPORT = REPO / "docs" / "avatar-production" / "b3-l11-visual-mark-detector-report.md"
AGGREGATE = REPO / "docs" / "avatar-production" / "b3-l11-visual-mark-detector-aggregate-v1.json"
OWL = "owlv2-base-patch16-ensemble"
GD = "grounding-dino-tiny"
FL = "florence2-phrase-grounding"


def _base(seed=7):
    img = Image.new("RGB", (640, 800), (90 + seed, 110, 130))
    return img


# ------------------------------------------------------------ 1-2 closure / immutability


def test_florence_telemetry_closure_marker_exists():
    assert c3.FLORENCE_TELEMETRY_CLOSURE == "FLORENCE_TELEMETRY_TEXT_PATH_CLOSED_ON_CURRENT_CORPUS"
    assert ev.PRIOR_STATUS["FLORENCE_TELEMETRY"] == c3.FLORENCE_TELEMETRY_CLOSURE
    assert c3.FLORENCE_TELEMETRY_CLOSURE in PREREG.read_text(encoding="utf-8")


def test_b3l10a_b3l10b_results_immutable():
    a = json.loads((REPO / "docs/avatar-production/b3-l10a-ocr-score-separability-aggregate-v1.json").read_text(encoding="utf-8"))
    b = json.loads((REPO / "docs/avatar-production/b3-l10b-two-feature-aggregate-v1.json").read_text(encoding="utf-8"))
    assert a["verdict"] == "FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING" and a["validationEvaluated"] == 0
    assert b["verdict"] == "FLORENCE_TWO_FEATURE_NOT_SEPARATING" and b["validationEvaluated"] == 0
    assert st.contract_digest().startswith("8092c3ea2f34") and tf.contract_digest().startswith("390251927491")
    assert v3.contract_digest().startswith("7e0281db982a") and tp.contract_digest().startswith("89514d712ad8")
    for k, v in (("V1", "OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT"), ("V2", "OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT"), ("V3", "V3_DUAL_CHANNEL_FAILED_DEVELOPMENT"),
                 ("B3_L9", "TEXT_POLICY_SHADOW_HOLDOUT_FAILED"), ("B3_L10A", "FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING"), ("B3_L10B", "FLORENCE_TWO_FEATURE_NOT_SEPARATING")):
        assert ev.PRIOR_STATUS[k] == v


# ------------------------------------------------------------ 3-8 frozen candidate set / constructs


def test_candidate_set_frozen_before_real_image_inference():
    assert det.CANDIDATE_SET_VERSION == "DETECTOR_CANDIDATE_SET_V1" and set(det.CANDIDATES) == {OWL, GD, FL}
    with pytest.raises(RuntimeError):
        det.register_candidate("new-detector", {"license": "mit"})
    text = PREREG.read_text(encoding="utf-8")
    assert det.contract_digest()[:12] in text and c3.construct_digest()[:12] in text
    for name, spec in det.CANDIDATES.items():
        assert spec["repo"] and len(spec["revision"]) == 40 and spec["prompts"] == list(det.PROMPTS)
        assert spec["revision"] in text


def test_real_trademark_construct_rejected():
    for s in c3.all_strings():
        assert c3.no_real_trademark(s), s
    assert not c3.no_real_trademark("Adidas") and not c3.no_real_trademark("yonsei")
    bad = c3.FamilyDef("FX", "X", "text", "OPAQUE", "torso", ("medium",), "Nike", "PROOF")
    with pytest.raises(ValueError):
        _cond_with(bad)


def _cond_with(fam):
    original = c3.FAMILIES
    try:
        c3.FAMILIES = (fam,)
        return c3.conditions(c3.DEV_VARIANT)
    finally:
        c3.FAMILIES = original


def test_dev_holdout_strings_differ():
    for f in c3.FAMILIES:
        if f.kind in ("text", "text_symbol", "tiled_text"):
            assert f.dev != f.holdout, f.code
            assert f.dev not in ("SAMPLE", "NOVA") and f.holdout not in ("SAMPLE", "NOVA")
    classes = {c3.text_length_class(f.dev) for f in c3.FAMILIES if f.kind == "text"}
    assert {"short_word", "long_word", "two_word", "alphanumeric"} <= classes
    classes_h = {c3.text_length_class(f.holdout) for f in c3.FAMILIES if f.kind == "text"}
    assert {"short_word", "long_word", "two_word", "alphanumeric"} <= classes_h


def test_dev_holdout_graphic_variants_differ():
    for f in c3.FAMILIES:
        if f.kind == "graphic":
            assert f.dev != f.holdout and f.dev in c3.GEOMETRIES and f.holdout in c3.GEOMETRIES, f.code
        if f.kind == "text_symbol":
            assert f.dev_shape != f.holdout_shape
    used = {f.dev for f in c3.FAMILIES if f.kind == "graphic"} | {f.holdout for f in c3.FAMILIES if f.kind == "graphic"}
    assert {"emblem_shield", "emblem_crest", "monogram_squares", "icon_asymmetric", "line_emblem", "badge_ring"} <= used


def test_alpha_set_frozen():
    assert c3.ALPHAS == {"OPAQUE": 1.00, "HIGH": 0.65, "MEDIUM": 0.35, "LOW": 0.20}
    fams = {f.family: f.alpha_name for f in c3.FAMILIES}
    assert fams["TEXT_WATERMARK_OPAQUE"] == "OPAQUE" and fams["TEXT_WATERMARK_TRANSLUCENT_HIGH"] == "HIGH"
    assert fams["TEXT_WATERMARK_TRANSLUCENT_MEDIUM"] == "MEDIUM" and fams["TEXT_WATERMARK_TRANSLUCENT_LOW"] == "LOW"
    assert c3.FAMILY_BY_CODE["F4"].diagnostic and not c3.FAMILY_BY_CODE["F4"].critical


def test_size_and_placement_frozen():
    assert c3.SIZE_BANDS == {"small": 0.035, "medium": 0.07}
    sizes = {s for f in c3.FAMILIES for s in f.sizes}
    assert sizes == {"small", "medium"}
    assert {c3.PLACEMENT_CLASS[f.placement] for f in c3.FAMILIES} >= {"corner", "edge", "center", "torso"}
    assert len(c3.conditions(c3.DEV_VARIANT)) == 15 == len(c3.conditions(c3.HOLDOUT_VARIANT))
    assert [f.family for f in c3.FAMILIES] == ["TEXT_WATERMARK_OPAQUE", "TEXT_WATERMARK_TRANSLUCENT_HIGH", "TEXT_WATERMARK_TRANSLUCENT_MEDIUM", "TEXT_WATERMARK_TRANSLUCENT_LOW",
                                                "GRAPHICAL_WATERMARK_TRANSLUCENT", "LOGO_LIKE_EMBLEM", "BRAND_LIKE_TEXT_AND_SYMBOL", "SMALL_CORNER_MARK", "EDGE_MARK",
                                                "CENTER_OVERLAY_MARK", "REPEATED_TILED_MARK", "GRAPHIC_SYMBOL"]


# ------------------------------------------------------------ 9-11 rendering / originals / split


def test_construct_rendering_deterministic():
    base = _base()
    for cond in c3.conditions(c3.DEV_VARIANT) + c3.conditions(c3.HOLDOUT_VARIANT):
        a, ba = c3.render(base, cond)
        b, bb = c3.render(base, cond)
        assert c3.image_digest(a) == c3.image_digest(b) and ba == bb and len(ba) >= 1
        assert c3.image_digest(a) != c3.image_digest(base)


def test_original_never_overwritten():
    base = _base()
    before = c3.image_digest(base)
    for cond in c3.conditions(c3.DEV_VARIANT):
        c3.render(base, cond)
    assert c3.image_digest(base) == before


def test_participant_split_preserved():
    assert c3.DEVELOPMENT_GROUPS == sel.DEVELOPMENT_GROUPS == ("G1", "G2", "G3")
    assert c3.HOLDOUT_GROUPS == sel.HOLDOUT_GROUPS == ("G4", "G5")
    assert c3.HOLDOUT_NAME == "DETECTOR_SPECIFIC_FROZEN_HOLDOUT"


# ------------------------------------------------------------ 12-18 detector contract


def test_holdout_variant_inaccessible_to_selector():
    sig = ev.select.__code__.co_varnames[: ev.select.__code__.co_argcount]
    assert sig == ("table", "resources")
    dev = {c.code for c in c3.conditions(c3.DEV_VARIANT)}
    hold = {c.code for c in c3.conditions(c3.HOLDOUT_VARIANT)}
    assert dev.isdisjoint(hold)


def test_owlv2_threshold_remains_0_25():
    assert det.CANDIDATES[OWL]["operatingPoints"] == {"legacy_0.25": {"threshold": 0.25}} and det.CANDIDATES[OWL]["gridOperatingPoints"] == {}
    assert det.CANDIDATES[OWL]["revision"] == "cfd3195ba4ea9592eec887ded089f4c08eff231d" == v3.OWLV2_REVISION
    assert det.CANDIDATES[OWL]["floor"] == 0.01


def test_owlv2_prompts_unchanged():
    assert det.PROMPTS == ("a logo", "a watermark", "a brand emblem", "a graphic symbol") == sel.PROMPTS
    assert det.CANDIDATES[FL]["caption"] == "a logo. a watermark. a brand emblem. a graphic symbol."


def test_yolo_world_excluded_pending_license_decision():
    assert det.EXCLUDED["ultralytics-yolo-world"]["status"] == "EXCLUDED_PENDING_PRODUCT_LICENSE_DECISION"
    assert not any("yolo" in k.lower() for k in det.CANDIDATES)


def test_unverified_license_detector_rejected():
    with pytest.raises(ValueError):
        det._verify_candidate("x", {"license": "unknown", "licenseAuthority": "official model card"})
    with pytest.raises(ValueError):
        det._verify_candidate("x", {"license": "apache-2.0", "licenseAuthority": "blog post"})
    assert all(spec["license"] in det.PERMISSIVE_LICENSES for spec in det.CANDIDATES.values())


def test_model_score_not_treated_as_cross_model_probability():
    assert "never compared across models" in det.SCORE_SEMANTICS_NOTE
    assert det.CANDIDATES[FL]["floor"] is None and det.CANDIDATES[FL]["operatingPoints"]["presence"]["threshold"] is None
    size = (640, 800)
    d = [{"box": [10, 10, 60, 60], "score": None, "label": "a logo"}]
    assert det.filter_detections(FL, d, {"threshold": None}, size) == d
    assert det.filter_detections(GD, [{"box": [10, 10, 60, 60], "score": 0.2, "label": "a logo"}], {"threshold": 0.25}, size) == []
    # the pre-registered full-frame filter applies to the Florence candidate only
    full = [{"box": [0, 0, 639, 799], "score": None, "label": "a watermark"}]
    assert det.filter_detections(FL, full, {"threshold": None}, size) == []
    assert det.filter_detections(OWL, [dict(full[0], score=0.9)], {"threshold": 0.25}, size) != []


def test_query_label_membership_per_detector():
    size = (640, 800)
    concat = [{"box": [10, 10, 60, 60], "score": 0.9, "label": "a logo a watermark a brand emblem a graphic symbol"}]
    assert det.filter_detections(GD, concat, {"threshold": 0.25}, size) == concat
    assert det.filter_detections(OWL, concat, {"threshold": 0.25}, size) == []      # OWLv2 labels are exact query strings
    assert det.filter_detections(GD, [{"box": [10, 10, 60, 60], "score": 0.9, "label": "a person"}], {"threshold": 0.25}, size) == []
    assert det.filter_detections(GD, [{"box": [10, 10, 60, 60], "score": 0.9, "label": ""}], {"threshold": 0.25}, size) == []


def test_matching_rule_frozen():
    assert det.IOU_MATCH == 0.30 == bench.IOU_MATCH and det.MAX_LONG_SIDE == 2048
    truth = [{"box": [100, 100, 200, 200]}]
    good = [{"box": [105, 105, 205, 205], "score": 0.9, "label": "a logo"}]
    off = [{"box": [400, 400, 500, 500], "score": 0.9, "label": "a logo"}]
    assert det.image_hit(OWL, good, truth, {"threshold": 0.25}, (640, 800))["hit"]
    assert not det.image_hit(OWL, off, truth, {"threshold": 0.25}, (640, 800))["hit"]   # unmatched detection is not recall
    assert not det.image_hit(OWL, good, truth, {"threshold": 0.95}, (640, 800))["hit"]


# ------------------------------------------------------------ 19-21 shadow semantics


def test_review_only_supplement():
    assert det.shadow_action("allow", True) == "review" and det.shadow_action("allow", False) == "allow"
    assert det.shadow_action("review", True) == "review" and det.shadow_action("reject", True) == "reject"
    with pytest.raises(ValueError):
        det.shadow_action("escalate", True)


def _rows(clean_hits, positives):
    rows = []
    for i, hit in enumerate(clean_hits):
        rows.append({"conditionId": f"b{i}:CLEAN", "opaqueId": f"b{i}", "groupKey": "G1", "imageSize": [640, 800], "meta": {"family": None}, "groundTruth": [],
                     "detections": [{"box": [10, 10, 60, 60], "score": 0.9, "label": "a logo"}] if hit else [], "seconds": 1.0})
    for i, (family, hit) in enumerate(positives):
        f = next(x for x in c3.FAMILIES if x.family == family)
        rows.append({"conditionId": f"b0:{f.code}:medium:D", "opaqueId": "b0", "groupKey": "G1", "imageSize": [640, 800],
                     "meta": {"family": family, "alphaName": f.alpha_name, "placementClass": c3.PLACEMENT_CLASS[f.placement], "sizeBand": "medium", "textLengthClass": None, "diagnostic": f.diagnostic},
                     "groundTruth": [{"box": [100, 100, 200, 200]}], "detections": [{"box": [100, 100, 200, 200], "score": 0.9, "label": "a logo"}] if hit else [], "seconds": 1.0})
    return rows


def test_canonical_reject_never_downgraded():
    rows = _rows([True, True], [])
    actions = {"b0": "reject", "b1": "review"}
    truth = {"b0": "negative", "b1": "negative"}
    r = ev.evaluate(OWL, "legacy_0.25", {"threshold": 0.25}, rows, actions, truth)
    assert r["clean"]["hardRejectBypass"] == 0 and r["clean"]["downgrades"] == 0 and r["criteria"]["K"] and r["criteria"]["L"]


def test_existing_review_not_counted_as_new_clean_burden():
    rows = _rows([True, True, False], [])
    r = ev.evaluate(OWL, "legacy_0.25", {"threshold": 0.25}, rows, {"b0": "review", "b1": "allow", "b2": "allow"}, {"b0": "negative", "b1": "negative", "b2": "negative"})
    assert r["clean"]["newAllowToReview"] == 1 and r["clean"]["existingCanonicalBurdenNotCounted"] == 1 and r["clean"]["cleanImageResponse"] == 2


# ------------------------------------------------------------ 22-26 selection / holdout guards


def test_selector_cannot_see_holdout():
    fam = [(f.family, True) for f in c3.FAMILIES for _ in range(2)]
    good = ev.evaluate(OWL, "legacy_0.25", {"threshold": 0.25}, _rows([False] * 12, fam), {f"b{i}": "allow" for i in range(12)}, {f"b{i}": "negative" for i in range(12)})
    assert good["eligible"]
    worse = dict(good, detector=GD, operatingPoint="historical_0.25", clean=dict(good["clean"], newReviewRate=0.0833))
    picked = ev.select([worse, good], {OWL: 5.0, GD: 3.0})
    assert picked["detector"] == OWL   # lower clean burden wins before resource cost
    tie = dict(good, detector=GD, operatingPoint="historical_0.25")
    assert ev.select([good, tie], {OWL: 5.0, GD: 3.0})["detector"] == GD   # then lower peak RSS
    assert ev.select([dict(good, eligible=False)], {})["status"] == "NONE"


def test_holdout_requires_selected_freeze(tmp_path):
    with pytest.raises(ev.NotFrozen):
        ev.holdout_guard(tmp_path, det.contract_digest(), c3.construct_digest())
    ev.write_selected(tmp_path, {"detector": OWL, "operatingPoint": "legacy_0.25", "params": {"threshold": 0.25}}, "0" * 64, c3.construct_digest(), "1" * 64)
    with pytest.raises(ev.NotFrozen):
        ev.holdout_guard(tmp_path, det.contract_digest(), c3.construct_digest())


def test_holdout_one_shot(tmp_path):
    d, c = det.contract_digest(), c3.construct_digest()
    ev.write_selected(tmp_path, {"detector": OWL, "operatingPoint": "legacy_0.25", "params": {"threshold": 0.25}}, d, c, "1" * 64)
    lock = ev.holdout_guard(tmp_path, d, c)
    assert lock.name == "visual_mark_detector_v1_holdout.lock" not in (sel.HOLDOUT_LOCK_NAME, v3.V3_HOLDOUT_LOCK_NAME, tp.HOLDOUT_LOCK_NAME, st.VALIDATION_LOCK_NAME, tf.VALIDATION_LOCK_NAME)
    ev.mark_holdout(lock, d)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        ev.holdout_guard(tmp_path, d, c)


def test_one_of_eight_clean_response_fails_holdout_a():
    r = ev.evaluate(OWL, "legacy_0.25", {"threshold": 0.25}, _rows([True] + [False] * 7, []), {f"b{i}": "allow" for i in range(8)}, {f"b{i}": "negative" for i in range(8)})
    assert r["clean"]["newReviewRate"] == 0.125 and r["criteria"]["A"] is False
    assert ev.required_hits(8, 0.90) == 8 and ev.required_hits(16, 0.90) == 15 and ev.required_hits(112, 0.95) == 107 and ev.required_hits(168, 0.95) == 160


def test_post_holdout_retuning_refused(tmp_path):
    d, c = det.contract_digest(), c3.construct_digest()
    ev.write_selected(tmp_path, {"detector": OWL, "operatingPoint": "legacy_0.30", "params": {"threshold": 0.30}}, d, c, "1" * 64)
    with pytest.raises(ev.NotFrozen):
        ev.require_selected(tmp_path, d, c)


# ------------------------------------------------------------ 27-28 LOW alpha / privacy


def test_low_alpha_reported_separately():
    fam = [(f.family, f.family != c3.LOW_VISIBILITY_FAMILY) for f in c3.FAMILIES for _ in range(2)]
    r = ev.evaluate(OWL, "legacy_0.25", {"threshold": 0.25}, _rows([False] * 12, fam), {f"b{i}": "allow" for i in range(12)}, {f"b{i}": "negative" for i in range(12)})
    assert r["lowVisibility"]["rate"] == 0.0 and r["lowVisibility"]["marker"] == "LOW_VISIBILITY_STRESS_CONDITION"
    assert r["overall"]["rate"] == 1.0 and r["overall"]["excludes"] == c3.LOW_VISIBILITY_FAMILY and r["eligible"]


def test_aggregate_only_repository_artifact():
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
        assert not ({"detections", "groundTruth", "box", "rows"} & set(keys(report)))
        assert report["watermarkPolicyChanged"] is False and report["decisionDiff"] == 0 and report["holdoutEvaluated"] in (0, 1)
        assert report["gaps"]["naturalPositive"] == "NATURAL_POSITIVE_EVIDENCE_MISSING"
