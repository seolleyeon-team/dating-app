"""B3-L6.2 - frozen threshold selection, H4-DIRECT-1 shadow, and the one-shot holdout guard.

PRE-REGISTERED BEFORE ANY ADJUDICATED LABEL VALUE WAS EVALUATED. Nothing here
reads a label to decide its own shape; labels are inputs to the functions only.

Selection algorithm (OWLV2_THRESHOLD_SELECTION_V1)
--------------------------------------------------
Uses DEVELOPMENT groups G1-G3 only. A threshold on the frozen grid is eligible
when, on development:
  A. adjudicated clean-avatar image-level precision >= 0.80
  B. new detector-induced review rate among human-negative clean avatars <= 0.10
  C. known injected graphical-mark recall == 1.00
  D. generative-artifact safety regression == 0
  E. hard-reject bypass == 0
Tie-break: the LOWEST eligible threshold, to keep mark sensitivity as high as the
specificity conditions allow. No eligible threshold -> NO_THRESHOLD_SELECTED.

Precision semantics (B3-L6.1 section 13): the truth field is visibleGraphicalMark
(yes = positive, no = negative, uncertain = unresolved, excluded). primaryLabel
is never converted into detector truth. A precision with no detector positives
or no human positives is NOT_ESTIMABLE and can never pass criterion A.

H4-DIRECT-1 (runtime-capable shadow)
------------------------------------
IF an OWLv2 combined-prompt detection has score >= SELECTED_THRESHOLD THEN the
shadow action is max(currentAction, review). No Florence region is required.
A live reject or review is never downgraded. Human-only fields (primaryLabel,
visibleGraphicalMark, markIntegration, markType, confidence) are evaluation
truth and are rejected as runtime inputs.

Criterion B semantics (B3-L6.2 section 22): a "new detector-induced review" is a
human-NEGATIVE clean avatar whose current live action is allow and whose H4
action is review. Existing reviews/rejects are not detector burden. Denominator
= adjudicated human-negative clean avatars.

Holdout (G4-G5) can be evaluated only after the threshold is frozen, and exactly
once: a lock file in the restricted directory refuses a second evaluation.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SELECTION_VERSION = "OWLV2_THRESHOLD_SELECTION_V1"
H4_VERSION = "H4-DIRECT-1"
HOLDOUT_LOCK_NAME = "holdout_evaluated.lock"

THRESHOLD_GRID = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50)
PROMPTS = ("a logo", "a watermark", "a brand emblem", "a graphic symbol")
PROMPT_MODE = "combined"
DEVELOPMENT_GROUPS = ("G1", "G2", "G3")
HOLDOUT_GROUPS = ("G4", "G5")

PRECISION_FLOOR = 0.80
NEW_REVIEW_CEILING = 0.10
INJECTED_RECALL_REQUIRED = 1.0

HUMAN_ONLY_FIELDS = frozenset(
    {"primaryLabel", "visibleGraphicalMark", "markIntegration", "markType", "labelConfidence", "allVisibleClasses"}
)
_SEVERITY = {"allow": 0, "review": 1, "reject": 2}


# ------------------------------------------------------------------ H4-DIRECT-1


def h4_direct_action(current_action: str, detector_hit: bool, **runtime_inputs: Any) -> str:
    """Escalate-only. Refuses any human-only field passed as a runtime input."""

    leaked = HUMAN_ONLY_FIELDS & set(runtime_inputs)
    if leaked:
        raise ValueError(f"human-only fields are not runtime inputs: {sorted(leaked)}")
    if current_action not in _SEVERITY:
        raise ValueError("unknown current action")
    if not detector_hit:
        return current_action
    return current_action if _SEVERITY[current_action] >= _SEVERITY["review"] else "review"


def detector_hit(detections: Sequence[Mapping[str, Any]], threshold: float, prompts: Sequence[str] = PROMPTS) -> bool:
    allowed = set(prompts)
    return any(d.get("score", 0.0) >= threshold and d.get("label") in allowed for d in detections)


# ------------------------------------------------------------ metrics per split


def truth_of(label: Mapping[str, Any]) -> str | None:
    """yes -> positive, no -> negative, anything else -> excluded (unresolved)."""

    value = label.get("visibleGraphicalMark")
    if value == "yes":
        return "positive"
    if value == "no":
        return "negative"
    return None


def confusion(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """items: {truth: positive|negative|None, hit: bool, currentAction: str}."""

    tp = fp = fn = tn = 0
    excluded = 0
    new_reviews = 0
    negatives = 0
    for item in items:
        truth = item["truth"]
        if truth is None:
            excluded += 1
            continue
        hit = bool(item["hit"])
        if truth == "positive":
            tp += int(hit)
            fn += int(not hit)
        else:
            negatives += 1
            fp += int(hit)
            tn += int(not hit)
            if hit and item.get("currentAction") == "allow":
                new_reviews += 1  # criterion B: newly detector-induced only
    predicted_positive = tp + fp
    precision = (tp / predicted_positive) if predicted_positive else None
    positives = tp + fn
    recall = (tp / positives) if positives else None
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "excludedUnresolved": excluded,
        "precision": None if precision is None else round(precision, 4),
        "precisionStatus": "estimable" if precision is not None else "NOT_ESTIMABLE",
        "recall": None if recall is None else round(recall, 4),
        "recallStatus": "estimable" if recall is not None else "NOT_ESTIMABLE",
        "humanPositives": positives,
        "humanNegatives": negatives,
        "newDetectorInducedReviews": new_reviews,
        "newReviewRate": round(new_reviews / negatives, 4) if negatives else None,
    }


def eligible(metrics: Mapping[str, Any], *, injected_recall: float, artifact_regressions: int, hard_reject_bypass: int) -> dict[str, Any]:
    precision = metrics.get("precision")
    rate = metrics.get("newReviewRate")
    criteria = {
        "A": precision is not None and precision >= PRECISION_FLOOR,
        "B": rate is not None and rate <= NEW_REVIEW_CEILING,
        "C": injected_recall >= INJECTED_RECALL_REQUIRED,
        "D": artifact_regressions == 0,
        "E": hard_reject_bypass == 0,
    }
    return {"criteria": criteria, "eligible": all(criteria.values())}


def select_threshold(table: Mapping[float, Mapping[str, Any]]) -> dict[str, Any]:
    """table: threshold -> eligibility block from eligible(). Lowest eligible wins."""

    for threshold in THRESHOLD_GRID:  # ascending: first eligible is the lowest
        block = table.get(threshold)
        if block and block.get("eligible"):
            return {
                "selectionVersion": SELECTION_VERSION,
                "status": "SELECTED",
                "selectedThreshold": threshold,
                "reason": "lowest threshold satisfying A-E on development groups",
                "tieBreak": "lowest_eligible",
            }
    return {
        "selectionVersion": SELECTION_VERSION,
        "status": "NO_THRESHOLD_SELECTED",
        "selectedThreshold": None,
        "reason": "no threshold on the frozen grid satisfies A-E on development groups",
    }


# ------------------------------------------------------------- freeze + holdout


def freeze_record(selection: Mapping[str, Any], inputs_digest: str) -> dict[str, Any]:
    if selection.get("status") != "SELECTED":
        raise ValueError("cannot freeze without a selected threshold")
    return {
        "selectionVersion": SELECTION_VERSION,
        "selectedThreshold": selection["selectedThreshold"],
        "developmentGroups": list(DEVELOPMENT_GROUPS),
        "holdoutGroups": list(HOLDOUT_GROUPS),
        "promptMode": PROMPT_MODE,
        "prompts": list(PROMPTS),
        "h4Version": H4_VERSION,
        "inputsDigest": inputs_digest,
        "frozenAt": datetime.now(timezone.utc).isoformat(),
    }


class HoldoutAlreadyEvaluated(RuntimeError):
    pass


class ThresholdNotFrozen(RuntimeError):
    pass


def holdout_guard(private_dir: Path, frozen: Mapping[str, Any] | None) -> Path:
    """Returns the lock path after checking both preconditions; caller writes it."""

    if not frozen or frozen.get("selectedThreshold") is None or frozen.get("selectionVersion") != SELECTION_VERSION:
        raise ThresholdNotFrozen("holdout requires a frozen threshold record")
    lock = Path(private_dir) / HOLDOUT_LOCK_NAME
    if lock.exists():
        raise HoldoutAlreadyEvaluated(f"holdout already evaluated once: {lock.name}")
    return lock


def mark_holdout_evaluated(lock: Path, frozen: Mapping[str, Any]) -> None:
    lock.write_text(
        json.dumps({"evaluatedAt": datetime.now(timezone.utc).isoformat(), "selectedThreshold": frozen["selectedThreshold"]}),
        encoding="utf-8",
    )


__all__ = [
    "DEVELOPMENT_GROUPS",
    "H4_VERSION",
    "HOLDOUT_GROUPS",
    "HUMAN_ONLY_FIELDS",
    "HoldoutAlreadyEvaluated",
    "PROMPTS",
    "SELECTION_VERSION",
    "THRESHOLD_GRID",
    "ThresholdNotFrozen",
    "confusion",
    "detector_hit",
    "eligible",
    "freeze_record",
    "h4_direct_action",
    "holdout_guard",
    "mark_holdout_evaluated",
    "select_threshold",
    "truth_of",
]
