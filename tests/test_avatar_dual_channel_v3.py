"""CI tests for B3-L8 AVATAR_WATERMARK_DUAL_CHANNEL_V3. Pure logic: no model, no user image, no label."""

import json
import re
import sys
from pathlib import Path

import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_dual_channel_v3 as v3  # noqa: E402
import avatar_dual_channel_v3_eval as ev  # noqa: E402
import avatar_florence_ceiling as bench  # noqa: E402
import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_challenge_v2 as v2  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_watermark_controls as controls  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PREREG = REPO / "docs" / "avatar-production" / "b3-l8-preregistration.md"
REPORT = REPO / "docs" / "avatar-production" / "b3-l8-dual-channel-v3-report.md"
AGGREGATE = REPO / "docs" / "avatar-production" / "b3-l8-dual-channel-v3-aggregate-v1.json"
SIZE = (1000, 1000)


def _base():
    return controls.build_controls()[8][1]


def _quad(box):
    l, t, r, b = box
    return [l, t, r, t, r, b, l, b]


def _tasks(boxes, labels, od=None):
    return {
        bench.TASK_OCR_WITH_REGION: {bench.TASK_OCR_WITH_REGION: {"quad_boxes": [_quad(b) for b in boxes], "labels": list(labels)}},
        bench.TASK_OD: {bench.TASK_OD: od or {"bboxes": [], "labels": []}},
    }


def _hit(score=0.5, label="a graphic symbol"):
    return [{"box": [10.0, 10.0, 90.0, 90.0], "label": label, "score": score}]


# ------------------------------------------------------------ 1-5 versions / frozen constants


def test_v1_status_untouched():
    assert calib.GATE_VERSION == "owlv2_provisional_shadow_gate_v1"
    assert calib.PROVISIONAL_PRECISION_FLOOR == 0.80 and calib.CLEAN_NEGATIVE_NEW_REVIEW_CEILING == 0.10
    assert v3.GATE_V1_STATUS_FROZEN == "OWLV2_POSITIVE_GROUND_TRUTH_INSUFFICIENT"


def test_v2_status_untouched():
    assert v2.GATE_VERSION == "OWLV2_CONTROLLED_CHALLENGE_GATE_V2"
    assert v2.NEW_REVIEW_CEILING == 0.10 and v2.OVERALL_RECALL_FLOOR == 0.95 and v2.CRITICAL_FAMILY_FLOOR == 0.90
    assert v3.GATE_V2_STATUS_FROZEN == "OWLV2_CONTROLLED_GATE_FAILED_DEVELOPMENT"
    assert len(v2.FAMILIES) == 10


def test_v3_version_distinct():
    assert v3.V3_VERSION == "AVATAR_WATERMARK_DUAL_CHANNEL_V3"
    assert v3.EVIDENCE_LABEL == "G004_DUAL_CHANNEL_CONTROLLED_EVIDENCE_V3"
    assert v3.V3_VERSION not in (calib.GATE_VERSION, v2.GATE_VERSION)
    assert v3.CHANNEL_T == "CANONICAL_FLORENCE_TEXT_POLICY" and v3.CHANNEL_G == "OWLV2_GRAPHICAL_SUPPLEMENT"
    assert v3.OWLV2_THRESHOLD_AUTHORITY == "DEVELOPMENT_SELECTED_GRAPHICAL_SUPPLEMENT_THRESHOLD"


def test_owlv2_threshold_exactly_0_25():
    assert v3.OWLV2_THRESHOLD == 0.25
    with pytest.raises(ValueError):
        v3.channel_g_hit(_hit(0.9), threshold=0.20)
    assert v3.channel_g_hit(_hit(0.25)) is True
    assert v3.channel_g_hit(_hit(0.2499)) is False


def test_prompt_set_unchanged():
    assert v3.PROMPTS == ("a logo", "a watermark", "a brand emblem", "a graphic symbol") == sel.PROMPTS
    assert v3.PROMPT_MODE == "combined"
    assert v3.channel_g_hit(_hit(0.9, label="a face")) is False


# ------------------------------------------------------------ 6-10 channels and composition


def test_channel_t_uses_canonical_policy_not_raw_ocr_presence():
    # One plausible, non-repeated token in the centre: Florence DID detect text,
    # but the canonical policy does not flag it. Channel T must say allow.
    tasks = _tasks([[300, 450, 700, 560]], ["SAMPLE"])
    assert bench._ocr_regions(tasks, SIZE)  # raw OCR region exists
    assert v3.channel_t_action(tasks, SIZE) == "allow"
    # Tiled repeated overlay-like text reaches the canonical hard reject.
    tiles = [[int((c + 0.5) / 3 * 1000) - 30, int((r + 0.5) / 4 * 1000) - 8, int((c + 0.5) / 3 * 1000) + 30, int((r + 0.5) / 4 * 1000) + 8]
             for r in range(4) for c in range(3)]
    assert v3.channel_t_action(_tasks(tiles, ["SAMPLE"] * 12), SIZE) == "reject"
    assert v3.CHANNEL_T_POLICY_VERSION == "watermark_policy_v4_runtime_evidence_parity_v1"
    assert "evaluate_watermark_risk" in v3.CHANNEL_T_SOURCE and "source_regions=()" in v3.CHANNEL_T_SOURCE


def test_channel_g_is_review_only_supplement():
    assert v3.channel_g_action(True) == "review"
    assert v3.channel_g_action(False) == "allow"
    assert v3.v3_shadow_action("allow", True) == "review"
    assert v3.v3_shadow_action("allow", False) == "allow"


def test_v3_max_severity_composition():
    for text in ("allow", "review", "reject"):
        for hit in (False, True):
            got = v3.v3_shadow_action(text, hit)
            expected = max((text, "review" if hit else "allow"), key=lambda a: v3._SEVERITY[a])
            assert got == expected


def test_canonical_reject_cannot_downgrade():
    assert v3.v3_shadow_action("reject", False) == "reject"
    assert v3.v3_shadow_action("reject", True) == "reject"
    rows = [{"canonicalAction": "reject", "owlv2Hit": h} for h in (False, True)]
    assert v3.safety(rows) == {"artifactRegressions": 0, "hardRejectBypass": 0}


def test_canonical_review_cannot_downgrade():
    assert v3.v3_shadow_action("review", False) == "review"
    assert v3.v3_shadow_action("review", True) == "review"
    with pytest.raises(ValueError):
        v3.v3_shadow_action("unknown", True)


# ------------------------------------------------------------ 11-13 forbidden runtime inputs


@pytest.mark.parametrize("field", sorted(sel.HUMAN_ONLY_FIELDS))
def test_human_fields_forbidden_runtime(field):
    with pytest.raises(ValueError):
        v3.v3_shadow_action("allow", True, **{field: "yes"})
    with pytest.raises(ValueError):
        v3.channel_g_hit(_hit(), **{field: "yes"})
    with pytest.raises(ValueError):
        v3.channel_t_action(_tasks([], []), SIZE, **{field: "yes"})


@pytest.mark.parametrize("field", ("family", "familyCode", "constructFamily"))
def test_construct_family_forbidden_runtime(field):
    with pytest.raises(ValueError):
        v3.v3_shadow_action("allow", False, **{field: "TEXT_WATERMARK_OPAQUE"})


@pytest.mark.parametrize("field", ("groundTruthBox", "groundTruthBoxes", "groundTruth"))
def test_ground_truth_box_forbidden_runtime(field):
    with pytest.raises(ValueError):
        v3.channel_g_hit(_hit(), **{field: [[0, 0, 1, 1]]})
    with pytest.raises(ValueError):
        v3.v3_shadow_action("allow", True, **{field: [[0, 0, 1, 1]]})


# ------------------------------------------------------------ 14-15 clean burden accounting


def test_clean_new_review_counts_only_canonical_allow_to_v3_review():
    items = [
        {"canonicalAction": "allow", "owlv2Hit": True},    # new burden
        {"canonicalAction": "allow", "owlv2Hit": False},   # untouched
        {"canonicalAction": "review", "owlv2Hit": True},   # existing, not new
        {"canonicalAction": "reject", "owlv2Hit": True},   # existing, not new
    ]
    out = v3.clean_burden(items)
    assert out["newAllowToReview"] == 1 and out["newReviewRate"] == 0.25
    assert out["newAllowToReject"] == 0
    assert out["v3"] == {"allow": 1, "review": 2, "reject": 1}


def test_existing_canonical_reviews_not_counted_as_new_burden():
    items = [{"canonicalAction": "review", "owlv2Hit": True} for _ in range(5)]
    out = v3.clean_burden(items)
    assert out["newAllowToReview"] == 0 and out["newReviewRate"] == 0.0
    assert out["existingCanonicalBurdenNotCounted"] == 5
    assert out["canonical"]["review"] == 5 and out["v3"]["review"] == 5


# ------------------------------------------------------------ 16-19 actual derivative + reuse audit


def test_actual_derivative_action_required_base_proxy_forbidden():
    challenge = {"rows": [{"opaqueId": "b", "groupKey": "G1", "family": "LOGO_LIKE_EMBLEM", "familyCode": "F2",
                           "detections": _hit(0.3), "groundTruth": [[1.0, 2.0, 3.0, 4.0]]}]}
    audit = {"families": {"LOGO_LIKE_EMBLEM": {"verdict": v3.REUSE_NONE, "variant": None}}}
    # base clean Florence output exists, but that is a proxy and must not be used
    base_clean = {"b:V0": {"tasks": _tasks([], []), "imageSize": SIZE, "groundTruth": []}}
    rows = ev.build_positive_rows(challenge, base_clean, [], audit)
    assert rows[0]["canonicalAction"] is None and rows[0]["florenceSource"] == ev.SOURCE_LOCAL
    with pytest.raises(ev.MissingFlorenceRows):
        ev.split_eval([], rows, "development")
    # With the actual derivative output the row resolves.
    local = [{"conditionId": "b:F2", "tasks": _tasks([], []), "imageSize": SIZE, "groundTruth": [{"box": [1.0, 2.0, 3.0, 4.0], "text": None}]}]
    rows = ev.build_positive_rows(challenge, base_clean, local, audit)
    assert rows[0]["canonicalAction"] == "allow"


def test_exact_reuse_requires_exact_spec_provenance():
    f1 = v2.FAMILY_BY_NAME["GRAPHIC_SYMBOL"]
    assert v3.exact_spec_match(f1, bench.spec_for("V8"))
    tweaked = bench.OverlaySpec("VX", "graphical_logo_like_mark", None, "rt", (0.98, 0.02), 0.08, 0.85, logo=True)
    assert not v3.exact_spec_match(f1, tweaked)  # alpha differs -> not exact
    base = _base()
    assert v3.render_identity(base, f1, "V8")
    verdict = v3.reuse_verdict(f1, [base], ["V0", "V8"])
    assert verdict["verdict"] == v3.REUSE_EXACT and verdict["variant"] == "V8"
    assert verdict["bitwiseIdentityOfHistoricalCapture"] == v3.BITWISE_UNPROVEN
    # provenance check in the evaluator: boxes must match or the row is refused
    challenge = {"rows": [{"opaqueId": "b", "groupKey": "G1", "family": "GRAPHIC_SYMBOL", "familyCode": "F1",
                           "detections": [], "groundTruth": [[5.0, 5.0, 9.0, 9.0]]}]}
    audit = {"families": {"GRAPHIC_SYMBOL": verdict}}
    reused = {"b:V8": {"tasks": _tasks([], []), "imageSize": SIZE, "groundTruth": [{"box": [1.0, 1.0, 2.0, 2.0], "text": None}]}}
    with pytest.raises(ev.MissingFlorenceRows):
        ev.build_positive_rows(challenge, reused, [], audit)


def test_semantic_similarity_alone_cannot_authorize_reuse():
    # Corner opaque text (V1) and the V3 text-watermark family are both "opaque
    # SAMPLE text" but differ in placement/size -> NOT_REUSABLE.
    f3 = v2.FAMILY_BY_NAME["TEXT_WATERMARK_OPAQUE"]
    assert bench.spec_for("V1").text == f3.text == "SAMPLE"
    assert not v3.exact_spec_match(f3, bench.spec_for("V1"))
    assert v3.candidate_variants(f3) == []
    assert v3.reuse_verdict(f3, [_base()], ["V1", "V3", "V5"])["verdict"] == v3.REUSE_NONE
    # Same-spec-name but different pixels is also refused.
    for family in v2.FAMILIES:
        if family.family not in ("GRAPHIC_SYMBOL", "REPEATED_TILED_MARK"):
            assert v3.reuse_verdict(family, [_base()], [s.variant for s in bench.CORE_VARIANTS])["verdict"] == v3.REUSE_NONE


def test_missing_florence_rows_may_be_locally_inferred_and_reused_rows_are_separated():
    rows = [
        {"family": "EDGE_MARK", "florenceOcrHit": False, "canonicalAction": "allow", "owlv2Hit": True, "florenceSource": ev.SOURCE_LOCAL},
        {"family": "GRAPHIC_SYMBOL", "florenceOcrHit": False, "canonicalAction": "allow", "owlv2Hit": True, "florenceSource": ev.SOURCE_REUSED},
    ]
    fam = v3.family_attribution(rows)
    assert fam["EDGE_MARK"]["actionSources"] == {"reused": 0, "locallyInferred": 1}
    assert fam["GRAPHIC_SYMBOL"]["actionSources"] == {"reused": 1, "locallyInferred": 0}


# ------------------------------------------------------------ 20-23 holdout contract


def test_holdout_inference_impossible_before_dev_pass(tmp_path):
    with pytest.raises(v3.DevelopmentNotPassed):
        v3.require_development_pass(tmp_path, v3.contract_digest())


def test_holdout_metrics_impossible_before_freeze(tmp_path):
    with pytest.raises(v3.DevelopmentNotPassed):
        v3.holdout_guard_v3(tmp_path, v3.contract_digest())
    # a marker written under a different contract digest is refused
    v3.write_dev_pass_marker(tmp_path, "0" * 64, {})
    with pytest.raises(v3.DevelopmentNotPassed):
        v3.holdout_guard_v3(tmp_path, v3.contract_digest())


def test_one_shot_v3_holdout_guard(tmp_path):
    digest = v3.contract_digest()
    v3.write_dev_pass_marker(tmp_path, digest, {})
    lock = v3.holdout_guard_v3(tmp_path, digest)
    assert lock.name == "v3_holdout_evaluated.lock" != sel.HOLDOUT_LOCK_NAME
    v3.mark_holdout_evaluated_v3(lock, digest)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        v3.holdout_guard_v3(tmp_path, digest)


def test_no_holdout_influence_on_v3_contract():
    digest = v3.contract_digest()
    assert v3.contract_digest() == digest
    assert v3.CRITERIA == tuple("ABCDEFGHIJKL")
    assert v3.NEW_REVIEW_CEILING == 0.10 and v3.OVERALL_RECALL_FLOOR == 0.95 and v3.FAMILY_RECALL_FLOOR == 0.90
    assert v3.GATED_FAMILIES == ("TEXT_WATERMARK_OPAQUE", "TEXT_WATERMARK_TRANSLUCENT", "GRAPHICAL_WATERMARK", "LOGO_LIKE_EMBLEM",
                                 "SMALL_CORNER_MARK", "EDGE_MARK", "CENTER_OVERLAY_MARK", "REPEATED_TILED_MARK")
    assert v3.DIAGNOSTIC_ONLY_FAMILIES == ("BRAND_LIKE_TEXT_AND_SYMBOL", "GRAPHIC_SYMBOL")
    assert v3.DEVELOPMENT_GROUPS == ("G1", "G2", "G3") and v3.HOLDOUT_GROUPS == ("G4", "G5")
    text = PREREG.read_text(encoding="utf-8")
    assert digest[:12] in text
    for token in (v3.V3_VERSION, v3.EVIDENCE_LABEL, "0.25", "0.95", "0.90", "NATURAL_POSITIVE_EVIDENCE_MISSING",
                  "v3_holdout_evaluated.lock", v3.OWLV2_THRESHOLD_AUTHORITY):
        assert token in text


# ------------------------------------------------------------ 24-25 metrics


def test_per_family_action_recall_and_eligibility():
    rows = []
    for family in v3.GATED_FAMILIES + v3.DIAGNOSTIC_ONLY_FAMILIES:
        for i in range(10):
            rows.append({"family": family, "florenceOcrHit": True, "canonicalAction": "review" if i < 9 else "allow",
                         "owlv2Hit": False, "florenceSource": ev.SOURCE_LOCAL})
    fam = v3.family_attribution(rows)
    assert all(fam[f]["v3ActionRecall"] == 0.9 for f in v3.GATED_FAMILIES)
    clean = v3.clean_burden([{"canonicalAction": "allow", "owlv2Hit": False}] * 10)
    elig = v3.eligible_v3(clean, fam, 0.9, artifact_regressions=0, hard_reject_bypass=0)
    assert elig["failed"] == ["B"] and not elig["eligible"]
    elig = v3.eligible_v3(clean, fam, 0.95, artifact_regressions=0, hard_reject_bypass=0)
    assert elig["eligible"]
    assert not v3.eligible_v3(clean, fam, 0.95, artifact_regressions=1, hard_reject_bypass=0)["eligible"]
    assert not v3.eligible_v3({**clean, "newReviewRate": 0.11}, fam, 0.95, artifact_regressions=0, hard_reject_bypass=0)["eligible"]


def test_model_hit_vs_policy_flag_separate_and_diagnosis():
    rows = [{"family": "TEXT_WATERMARK_OPAQUE", "florenceOcrHit": True, "canonicalAction": "allow", "owlv2Hit": False, "florenceSource": ev.SOURCE_LOCAL}] * 12
    rows += [{"family": "TEXT_WATERMARK_TRANSLUCENT", "florenceOcrHit": False, "canonicalAction": "allow", "owlv2Hit": False, "florenceSource": ev.SOURCE_LOCAL}] * 12
    rows += [{"family": "GRAPHICAL_WATERMARK", "florenceOcrHit": False, "canonicalAction": "allow", "owlv2Hit": False, "florenceSource": ev.SOURCE_LOCAL}] * 12
    fam = v3.family_attribution(rows)
    opaque = fam["TEXT_WATERMARK_OPAQUE"]
    assert opaque["florenceOcrHit"] == 12 and opaque["canonicalPolicyFlagged"] == 0 and opaque["v3Flagged"] == 0
    assert opaque["florenceModelDetectedPolicyDidNotFlag"] == 12
    clean = v3.clean_burden([{"canonicalAction": "allow", "owlv2Hit": False}] * 12)
    elig = v3.eligible_v3(clean, fam, 0.0, artifact_regressions=0, hard_reject_bypass=0)
    gaps = v3.diagnose(clean, fam, elig)
    assert v3.GAP_TEXT_POLICY in gaps and v3.GAP_TEXT_MODEL in gaps and v3.GAP_GRAPHICAL in gaps and "MIXED" in gaps
    assert v3.GAP_CLEAN not in gaps
    assert v3.verdicts(False, None, True) == {"v3": "V3_DUAL_CHANNEL_FAILED_DEVELOPMENT", "h4": "H4_DUAL_CHANNEL_SHADOW_NOT_SUPPORTED"}
    assert v3.verdicts(True, False, True)["v3"] == "V3_DUAL_CHANNEL_HOLDOUT_FAILED"
    assert v3.verdicts(True, True, True)["h4"] == "H4_DUAL_CHANNEL_SHADOW_SUPPORTED_FOR_CONTROLLED_CANARY"


# ------------------------------------------------------------ 26-27 privacy and originals


def test_aggregate_only_repo_report():
    forbidden = ("PRODUCTION_VALIDATED", "LIVE_POLICY_READY", "PRODUCTION_PRECISION_PROVEN", "LIVE_READY",
                 "production recall proven", "production policy validated", "three-rater", "adjudicated human ground truth")
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
        assert "rows" not in report and "detections" not in json.dumps(report)
        assert report["naturalPositiveLimitation"] == "NATURAL_POSITIVE_EVIDENCE_MISSING"
        assert report["channelG"]["threshold"] == 0.25
        assert report["proxyBaseActionsUsed"] is False


def test_original_images_never_modified():
    base = _base()
    before = base.tobytes()
    for family in v2.FAMILIES:
        image, boxes = v2.render_family(base, family)
        assert image is not base and boxes
    assert base.tobytes() == before
    # The pinned Florence revision is read from the Dockerfile, never hardcoded.
    assert re.fullmatch(r"[0-9a-f]{40}", v3.pinned_florence_revision())
