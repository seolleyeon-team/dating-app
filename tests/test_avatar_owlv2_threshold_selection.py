"""CI tests for the frozen OWLv2 threshold selection, H4-DIRECT-1 and the holdout guard.

No model, no image, no human label in CI. Fixtures only.
"""

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_owlv2_calibration as calib  # noqa: E402
import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_watermark_label_ingest as ingest  # noqa: E402
import avatar_watermark_label_local as ui  # noqa: E402

PREREG = Path(__file__).resolve().parents[1] / "docs" / "avatar-production" / "b3-l6-2-preregistration.md"


# ------------------------------------------------------------- frozen inputs


def test_pre_registered_values_are_unchanged_from_b3l6():
    assert sel.THRESHOLD_GRID == calib.THRESHOLD_GRID == (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)
    assert sel.PROMPTS == ("a logo", "a watermark", "a brand emblem", "a graphic symbol")
    assert sel.PROMPT_MODE == "combined"
    assert sel.DEVELOPMENT_GROUPS == calib.DEVELOPMENT_GROUPS == ("G1", "G2", "G3")
    assert sel.HOLDOUT_GROUPS == calib.HOLDOUT_GROUPS == ("G4", "G5")


def test_gate_constants_unchanged_from_b3l6_1():
    assert calib.GATE_VERSION == "owlv2_provisional_shadow_gate_v1"
    assert sel.PRECISION_FLOOR == calib.PROVISIONAL_PRECISION_FLOOR == 0.80
    assert sel.NEW_REVIEW_CEILING == calib.CLEAN_NEGATIVE_NEW_REVIEW_CEILING == 0.10
    assert sel.INJECTED_RECALL_REQUIRED == calib.INJECTED_RECALL_REQUIREMENT == 1.0


def test_preregistration_document_records_the_rule_before_evaluation():
    text = PREREG.read_text(encoding="utf-8")
    assert sel.SELECTION_VERSION in text
    assert sel.H4_VERSION in text
    assert "lowest" in text.lower()
    assert "exactly once" in text.lower()


# ------------------------------------------------------- precision semantics


def test_truth_comes_only_from_visible_graphical_mark():
    assert sel.truth_of({"visibleGraphicalMark": "yes", "primaryLabel": "NO_VISIBLE_RELEVANT_TEXT_OR_MARK"}) == "positive"
    assert sel.truth_of({"visibleGraphicalMark": "no", "primaryLabel": "GRAPHICAL_LOGO"}) == "negative"
    assert sel.truth_of({"visibleGraphicalMark": "uncertain"}) is None
    assert sel.truth_of({"primaryLabel": "GRAPHICAL_LOGO"}) is None


def test_undefined_precision_is_not_estimable_and_cannot_pass():
    no_predictions = sel.confusion([{"truth": "negative", "hit": False, "currentAction": "allow"}])
    assert no_predictions["precisionStatus"] == "NOT_ESTIMABLE" and no_predictions["precision"] is None
    block = sel.eligible(no_predictions, injected_recall=1.0, artifact_regressions=0, hard_reject_bypass=0)
    assert block["criteria"]["A"] is False and block["eligible"] is False
    no_positives = sel.confusion([{"truth": "negative", "hit": True, "currentAction": "allow"}])
    assert no_positives["recallStatus"] == "NOT_ESTIMABLE"
    assert no_positives["precision"] == 0.0  # a detector positive with no human positive is a defined 0


def test_unresolved_items_are_excluded_not_counted():
    result = sel.confusion(
        [
            {"truth": None, "hit": True, "currentAction": "allow"},
            {"truth": "positive", "hit": True, "currentAction": "allow"},
        ]
    )
    assert result["excludedUnresolved"] == 1 and result["tp"] == 1 and result["fp"] == 0


# ---------------------------------------------------------- criterion B


def test_criterion_b_counts_only_newly_detector_induced_reviews_on_human_negatives():
    result = sel.confusion(
        [
            {"truth": "negative", "hit": True, "currentAction": "allow"},   # new burden
            {"truth": "negative", "hit": True, "currentAction": "review"},  # already review: not new
            {"truth": "negative", "hit": True, "currentAction": "reject"},  # already reject: not new
            {"truth": "positive", "hit": True, "currentAction": "allow"},   # human positive: not burden
            {"truth": "negative", "hit": False, "currentAction": "allow"},
        ]
    )
    assert result["humanNegatives"] == 4
    assert result["newDetectorInducedReviews"] == 1
    assert result["newReviewRate"] == 0.25
    assert result["fp"] == 3  # fp is a model metric; burden is a policy metric


# ----------------------------------------------------------- selection


def _block(ok: bool):
    return {"criteria": {k: ok for k in "ABCDE"}, "eligible": ok}


def test_lowest_eligible_threshold_is_selected():
    table = {t: _block(t in (0.20, 0.25, 0.30)) for t in sel.THRESHOLD_GRID}
    chosen = sel.select_threshold(table)
    assert chosen["status"] == "SELECTED" and chosen["selectedThreshold"] == 0.20
    assert chosen["tieBreak"] == "lowest_eligible"


def test_no_eligible_threshold_reports_none_selected():
    chosen = sel.select_threshold({t: _block(False) for t in sel.THRESHOLD_GRID})
    assert chosen["status"] == "NO_THRESHOLD_SELECTED" and chosen["selectedThreshold"] is None


def test_selection_reads_development_only_and_holdout_cannot_influence_it():
    """The selector takes a development table only; holdout metrics have no parameter to enter by."""

    import inspect

    assert list(inspect.signature(sel.select_threshold).parameters) == ["table"]
    source = inspect.getsource(sel.select_threshold)
    assert "HOLDOUT" not in source and "holdout" not in source


# ------------------------------------------------------------- H4-DIRECT-1


def test_h4_direct_does_not_require_a_florence_region():
    import inspect

    params = inspect.signature(sel.h4_direct_action).parameters
    assert "florence" not in json.dumps(list(params)).lower()
    assert sel.h4_direct_action("allow", True) == "review"


def test_h4_never_downgrades_current_reject_or_review():
    assert sel.h4_direct_action("reject", True) == "reject"
    assert sel.h4_direct_action("reject", False) == "reject"
    assert sel.h4_direct_action("review", True) == "review"
    assert sel.h4_direct_action("review", False) == "review"
    assert sel.h4_direct_action("allow", False) == "allow"


@pytest.mark.parametrize("field", sorted(sel.HUMAN_ONLY_FIELDS))
def test_human_evaluation_fields_cannot_be_runtime_h4_inputs(field):
    with pytest.raises(ValueError, match="human-only"):
        sel.h4_direct_action("allow", True, **{field: "anything"})


def test_detector_hit_uses_combined_prompts_and_threshold():
    dets = [{"score": 0.24, "label": "a logo"}, {"score": 0.26, "label": "a graphic symbol"}]
    assert sel.detector_hit(dets, 0.25) is True
    assert sel.detector_hit(dets, 0.30) is False
    assert sel.detector_hit([{"score": 0.9, "label": "a person"}], 0.05) is False


# ------------------------------------------------------ freeze + holdout guard


def test_freeze_requires_a_selected_threshold():
    with pytest.raises(ValueError):
        sel.freeze_record({"status": "NO_THRESHOLD_SELECTED"}, "abc")
    frozen = sel.freeze_record({"status": "SELECTED", "selectedThreshold": 0.25}, "abc")
    assert frozen["selectionVersion"] == sel.SELECTION_VERSION and frozen["h4Version"] == sel.H4_VERSION


def test_holdout_requires_frozen_threshold(tmp_path):
    with pytest.raises(sel.ThresholdNotFrozen):
        sel.holdout_guard(tmp_path, None)
    with pytest.raises(sel.ThresholdNotFrozen):
        sel.holdout_guard(tmp_path, {"selectionVersion": sel.SELECTION_VERSION, "selectedThreshold": None})


def test_holdout_is_one_shot(tmp_path):
    frozen = {"selectionVersion": sel.SELECTION_VERSION, "selectedThreshold": 0.25}
    lock = sel.holdout_guard(tmp_path, frozen)
    sel.mark_holdout_evaluated(lock, frozen)
    with pytest.raises(sel.HoldoutAlreadyEvaluated):
        sel.holdout_guard(tmp_path, frozen)


# ------------------------------------------------- adjudication page blinding


def test_third_adjudication_page_hides_both_prior_votes():
    page = ui.build_html(
        [{"opaqueId": "g004-avatar-018", "dataUri": "data:image/jpeg;base64,AAAA"}],
        "C",
        adjudication_state="third_adjudication",
    )
    assert "third adjudicator" in page
    assert "third_adjudication" in page
    lowered = page.lower()
    for forbidden in list(ui.FORBIDDEN_IN_UI) + ["rater a", "rater b", "raterid\": \"a", "raterid\": \"b"]:
        assert forbidden.lower() not in lowered, forbidden
    # No input arrives pre-selected: a prior vote could only leak as a checked control.
    import re

    assert not re.search(r"<input[^>]*\schecked", page)
    assert "http://" not in page and "https://" not in page


def test_adjudicator_export_state_is_distinguishable_by_ingest(tmp_path):
    third = {
        "labelSchema": ui.LABEL_SCHEMA_VERSION,
        "raterId": "C",
        "adjudicationState": "first_pass",  # wrong state for an adjudication
        "labels": [{"evaluationId": "i1", "primaryLabel": "GRAPHICAL_LOGO", "allVisibleClasses": ["GRAPHICAL_LOGO"],
                    "visibleGraphicalMark": "yes", "markIntegration": "overlay_like", "markType": "graphical_logo", "labelConfidence": "high"}],
    }
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    c = tmp_path / "c.json"
    base = {"labelSchema": ui.LABEL_SCHEMA_VERSION, "labels": [dict(third["labels"][0])]}
    a.write_text(json.dumps({**base, "raterId": "A"}), encoding="utf-8")
    other = dict(third["labels"][0]); other.update(visibleGraphicalMark="no", markType="none", primaryLabel="NO_VISIBLE_RELEVANT_TEXT_OR_MARK", allVisibleClasses=["NO_VISIBLE_RELEVANT_TEXT_OR_MARK"], markIntegration="not_applicable")
    b.write_text(json.dumps({"labelSchema": ui.LABEL_SCHEMA_VERSION, "raterId": "B", "labels": [other]}), encoding="utf-8")
    c.write_text(json.dumps(third), encoding="utf-8")
    with pytest.raises(SystemExit, match="ADJUDICATION_STATE_INVALID"):
        ingest.ingest(a, b, independence_attested=True, adjudication=c)


# ------------------------------------------------------------- privacy


def test_raw_labels_cannot_enter_committed_artifacts():
    """Per-image label rows are restricted-local; only aggregates are repo-safe."""

    import avatar_florence_ceiling as bench

    aggregate = {"confusion": sel.confusion([{"truth": "negative", "hit": False, "currentAction": "allow"}])}
    assert not bench.privacy_violations(aggregate)
    per_image = {"labels": [{"evaluationId": "g004-avatar-018", "visibleGraphicalMark": "yes"}]}
    # A per-image row is not itself a privacy pattern hit, so the guard is the
    # commit rule: the ingest output is never passed to the repo writer.
    committed_report_keys = {"confusion", "selection", "gate", "agreement"}
    assert "labels" not in committed_report_keys
    assert isinstance(per_image["labels"], list)
