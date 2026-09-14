"""B3-L10A — FLORENCE_OCR_SEQUENCE_SCORE_STUDY_V1 (pre-registered, analysis only).

Question: does the Florence beam-search sequence score recorded by the PR #100
shadow telemetry (`shadowOcrEvidence.rawSequenceScore`) usefully separate the
single incidental OCR region on clean human-negative avatars from the single
injected text-watermark region?  It is a separability study of an
UNCALIBRATED DISCRIMINATION FEATURE.  It is not a policy, not a confidence
band, not a probability, and it never touches a watermark action.

Score semantics (fresh audit of florence2_visual._attach_shadow_ocr_evidence):
  scoreSource        = florence_beam_sequence_score
  scoreCalibrated    = False
  rawSequenceScore   = beam-search log-probability of the WHOLE generated string
  attributionScope   = single_region only when regionCount == 1, else whole_sequence
The parser turns a "scores"/"confidences" key into VisualRiskRegion.confidence;
the shadow key is a separate namespace and nothing here writes there.

Prior results are immutable (V1, V2, V3, B3-L9).  Graphical channel out of
scope (GRAPHICAL_DETECTOR_STUDY_REQUIRED).
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_owlv2_threshold_selection as sel  # noqa: E402
import avatar_text_policy_shadow as tp  # noqa: E402

# ------------------------------------------------------------------ versions / semantics

VERSION = "FLORENCE_OCR_SEQUENCE_SCORE_STUDY_V1"
EVIDENCE_LABEL = "G004_UNCALIBRATED_OCR_SCORE_EVIDENCE"
FEATURE_NAME = "UNCALIBRATED_DISCRIMINATION_FEATURE"
SCORE_SOURCE = "florence_beam_sequence_score"
SCORE_CALIBRATED = False
SCOPE_SINGLE = "single_region"
SCOPE_WHOLE = "whole_sequence"
THRESHOLD_ROLE = "SEPARABILITY_CANDIDATE_THRESHOLD"
SELECTED_ROLE = "SEPARABILITY_THRESHOLD_V1"
VALIDATION_SPLIT_NAME = "FEATURE_SPECIFIC_FROZEN_VALIDATION_SPLIT"
VALIDATION_LOCK_NAME = "ocr_score_v1_validation_evaluated.lock"
FROZEN_NAME = "ocr_score_v1_threshold_frozen.json"
NATURAL_POSITIVE_LIMITATION = "NATURAL_POSITIVE_EVIDENCE_MISSING"
GRAPHICAL_STUDY_MARKER = "GRAPHICAL_DETECTOR_STUDY_REQUIRED"
TEXT_POLICY_GAP_STATUS = "TEXT_POLICY_GAP_UNRESOLVED"
PRIOR_STATUS = {**tp.PRIOR_STATUS, "B3_L9": "TEXT_POLICY_SHADOW_HOLDOUT_FAILED", "B3_L9_SUPPORT": "TEXT_POLICY_SHADOW_NOT_SUPPORTED"}
FORBIDDEN_WORDING = ("HIGH_CONFIDENCE", "MEDIUM_CONFIDENCE", "LOW_CONFIDENCE", "CONFIDENCE_CALIBRATED", "CONFIDENCE_BAND_VALIDATED",
                     "TEXT_POLICY_READY", "PRODUCTION_VALIDATED", "LIVE_READY", "probability-bearing")
SHADOW_FIELDS = frozenset({"scoreSource", "scoreCalibrated", "scoreAvailable", "scoreUnavailableReason", "generationMode", "numBeams",
                           "lengthPenalty", "regionCount", "attributionScope", "outputTokenCount", "rawSequenceScore"})
FORBIDDEN_EXTRACTION_INPUTS = tp.FORBIDDEN_RUNTIME_FIELDS
OCR_TASK = "<OCR_WITH_REGION>"

# ------------------------------------------------------------------ study contract (frozen)

DEVELOPMENT_GROUPS = sel.DEVELOPMENT_GROUPS
VALIDATION_GROUPS = sel.HOLDOUT_GROUPS
POSITIVE_FAMILIES = ("TEXT_WATERMARK_OPAQUE", "TEXT_WATERMARK_TRANSLUCENT")
QUANTILE_GRID = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90)   # positions in the pooled development score range
CLEAN_FALSE_ESCALATION_CEILING = 0.10   # A (proxy: clean rows on the positive side of the boundary)
SENSITIVITY_FLOOR = 0.90                # B opaque, C translucent
CRITERIA = ("A", "B", "C", "D", "E", "F")


def contract_digest() -> str:
    payload = {"version": VERSION, "evidence": EVIDENCE_LABEL, "scoreSource": SCORE_SOURCE, "scoreCalibrated": SCORE_CALIBRATED,
               "usableScope": SCOPE_SINGLE, "grid": "pooled development quantiles " + ",".join(str(q) for q in QUANTILE_GRID),
               "direction": "positive_higher if median(positive dev) > median(clean dev) else positive_lower; frozen at selection",
               "criteria": {"A": CLEAN_FALSE_ESCALATION_CEILING, "B": SENSITIVITY_FLOOR, "C": SENSITIVITY_FLOOR, "D": 1.0, "E": False, "F": 0},
               "selection": "min clean false-escalation -> max combined sensitivity -> more conservative boundary",
               "split": {"development": list(DEVELOPMENT_GROUPS), "validation": list(VALIDATION_GROUPS), "validationName": VALIDATION_SPLIT_NAME},
               "forbiddenExtractionInputs": sorted(FORBIDDEN_EXTRACTION_INPUTS)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ extraction (runtime-shaped, no labels)


def extract_shadow(tasks: Mapping[str, Any], **runtime_inputs: Any) -> dict[str, Any]:
    """Allowlisted copy of the shadow telemetry from a raw Florence task payload.

    Refuses human/family/ground-truth inputs.  Never returns OCR text.
    """

    leaked = FORBIDDEN_EXTRACTION_INPUTS & set(runtime_inputs)
    if leaked:
        raise ValueError(f"not an extraction input: {sorted(leaked)}")
    payload = tasks.get(OCR_TASK, {})
    if isinstance(payload, Mapping) and OCR_TASK in payload and isinstance(payload[OCR_TASK], Mapping):
        payload = payload[OCR_TASK]
    if not isinstance(payload, Mapping):
        return {}
    shadow = payload.get("shadowOcrEvidence")
    if not isinstance(shadow, Mapping):
        return {}
    return {str(k): v for k, v in shadow.items() if str(k) in SHADOW_FIELDS and (isinstance(v, (str, int, float, bool)) or v is None)}


def usable(shadow: Mapping[str, Any]) -> bool:
    """Only a single-region, uncalibrated, available beam score may enter the primary analysis."""

    return (bool(shadow.get("scoreAvailable")) and shadow.get("scoreSource") == SCORE_SOURCE and shadow.get("scoreCalibrated") is False
            and shadow.get("attributionScope") == SCOPE_SINGLE and int(shadow.get("regionCount", 0)) == 1
            and isinstance(shadow.get("rawSequenceScore"), (int, float)) and math.isfinite(float(shadow["rawSequenceScore"])))


def score_of(shadow: Mapping[str, Any]) -> float:
    if not usable(shadow):
        raise ValueError("whole-sequence or unavailable score cannot masquerade as a region score")
    return float(shadow["rawSequenceScore"])


# ------------------------------------------------------------------ descriptive statistics (aggregate)


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return float("nan")
    pos = (len(sorted_values) - 1) * q
    lo, hi = int(math.floor(pos)), int(math.ceil(pos))
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def distribution(values: Sequence[float]) -> dict[str, Any]:
    v = sorted(float(x) for x in values)
    if not v:
        return {"n": 0}
    return {"n": len(v), "min": round(v[0], 4), "q1": round(_quantile(v, 0.25), 4), "median": round(_quantile(v, 0.5), 4),
            "q3": round(_quantile(v, 0.75), 4), "max": round(v[-1], 4)}


def inventory(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    shadows = [r["shadow"] for r in rows]
    us = [s for s in shadows if usable(s)]
    return {"n": len(rows), "scoreAvailable": sum(1 for s in shadows if s.get("scoreAvailable")), "usableSingleRegion": len(us),
            "attributionScope": dict(Counter(s.get("attributionScope") for s in shadows)),
            "regionCount": {str(k): v for k, v in sorted(Counter(int(s.get("regionCount", -1)) for s in shadows).items())},
            "outputTokenCount": distribution([s["outputTokenCount"] for s in shadows if isinstance(s.get("outputTokenCount"), int)]),
            "rawSequenceScore": distribution([score_of(s) for s in us])}


# ------------------------------------------------------------------ thresholds and metrics


def direction(clean_scores: Sequence[float], positive_scores: Sequence[float]) -> str:
    """Frozen rule: which side of a boundary counts as 'text-like'.  Decided on development only."""

    mc = _quantile(sorted(clean_scores), 0.5)
    mp = _quantile(sorted(positive_scores), 0.5)
    return "positive_higher" if mp > mc else "positive_lower"


def candidate_thresholds(pooled_dev_scores: Sequence[float]) -> list[float]:
    v = sorted(float(x) for x in pooled_dev_scores)
    return [round(_quantile(v, q), 6) for q in QUANTILE_GRID]


def flagged(score: float, threshold: float, direction_: str) -> bool:
    return score >= threshold if direction_ == "positive_higher" else score <= threshold


def _auc_roc(clean: Sequence[float], positive: Sequence[float], direction_: str) -> Optional[float]:
    if not clean or not positive:
        return None
    sign = 1.0 if direction_ == "positive_higher" else -1.0
    wins = 0.0
    for p in positive:
        for c in clean:
            wins += 1.0 if sign * p > sign * c else 0.5 if p == c else 0.0
    return round(wins / (len(clean) * len(positive)), 4)


def _average_precision(clean: Sequence[float], positive: Sequence[float], direction_: str) -> Optional[float]:
    if not clean or not positive:
        return None
    sign = 1.0 if direction_ == "positive_higher" else -1.0
    ranked = sorted([(sign * s, 1) for s in positive] + [(sign * s, 0) for s in clean], key=lambda x: -x[0])
    tp_ = 0
    ap = 0.0
    for i, (_, y) in enumerate(ranked, 1):
        if y:
            tp_ += 1
            ap += tp_ / i
    return round(ap / len(positive), 4)


def threshold_metrics(threshold: float, direction_: str, clean: Sequence[float], opaque: Sequence[float], translucent: Sequence[float]) -> dict[str, Any]:
    cfp = sum(1 for s in clean if flagged(s, threshold, direction_))
    op = sum(1 for s in opaque if flagged(s, threshold, direction_))
    tr = sum(1 for s in translucent if flagged(s, threshold, direction_))
    n_pos = len(opaque) + len(translucent)
    clean_rate = round(cfp / len(clean), 4) if clean else None
    op_rate = round(op / len(opaque), 4) if opaque else None
    tr_rate = round(tr / len(translucent), 4) if translucent else None
    comb = round((op + tr) / n_pos, 4) if n_pos else None
    bal = round(((1 - clean_rate) + comb) / 2, 4) if clean_rate is not None and comb is not None else None
    return {"threshold": threshold, "role": THRESHOLD_ROLE, "direction": direction_,
            "cleanFalseEscalationProxy": {"k": cfp, "n": len(clean), "rate": clean_rate},
            "opaqueSensitivity": {"k": op, "n": len(opaque), "rate": op_rate},
            "translucentSensitivity": {"k": tr, "n": len(translucent), "rate": tr_rate},
            "combinedSensitivity": {"k": op + tr, "n": n_pos, "rate": comb}, "balancedAccuracy": bal}


def eligible(metrics: Mapping[str, Any], *, coverage_rate: float, calibrated_flags: set, decision_diff: int) -> dict[str, Any]:
    checks = {
        "A": metrics["cleanFalseEscalationProxy"]["rate"] is not None and metrics["cleanFalseEscalationProxy"]["rate"] <= CLEAN_FALSE_ESCALATION_CEILING,
        "B": metrics["opaqueSensitivity"]["rate"] is not None and metrics["opaqueSensitivity"]["rate"] >= SENSITIVITY_FLOOR,
        "C": metrics["translucentSensitivity"]["rate"] is not None and metrics["translucentSensitivity"]["rate"] >= SENSITIVITY_FLOOR,
        "D": coverage_rate == 1.0,
        "E": calibrated_flags == {False},
        "F": decision_diff == 0,
    }
    return {"criteria": checks, "eligible": all(checks[c] for c in CRITERIA), "failed": [c for c in CRITERIA if not checks[c]]}


def select_threshold(development_table: Sequence[Mapping[str, Any]], direction_: str) -> dict[str, Any]:
    """Development table only.  Validation scores are never an input."""

    elig = [t for t in development_table if t["eligibility"]["eligible"]]
    if not elig:
        return {"status": "NONE", "selectedThreshold": None, "reason": "no candidate satisfies A-F on development"}
    conservative = (lambda t: -t["threshold"]) if direction_ == "positive_higher" else (lambda t: t["threshold"])
    best = sorted(elig, key=lambda t: (t["cleanFalseEscalationProxy"]["rate"], -t["combinedSensitivity"]["rate"], conservative(t)))[0]
    return {"status": "SELECTED", "selectedThreshold": best["threshold"], "role": SELECTED_ROLE, "direction": direction_,
            "reason": "lowest clean false-escalation, then highest combined sensitivity, then more conservative boundary"}


# ------------------------------------------------------------------ decision neutrality


def watermark_action_with_score(canonical_action: str, score: float, threshold: float, direction_: str) -> str:
    """The study never changes an action: whatever the score says, the canonical action is returned."""

    del score, threshold, direction_
    if canonical_action not in ("allow", "review", "reject"):
        raise ValueError("unknown canonical action")
    return canonical_action


# ------------------------------------------------------------------ freeze / validation guards


class ThresholdNotFrozen(RuntimeError):
    pass


class ValidationScoresPreviouslySeen(RuntimeError):
    pass


def frozen_path(private_dir: Path) -> Path:
    return Path(private_dir) / FROZEN_NAME


def write_frozen(private_dir: Path, selection: Mapping[str, Any], digest: str, dev_inputs_digest: str) -> Path:
    path = frozen_path(private_dir)
    path.write_text(json.dumps({"version": VERSION, "role": SELECTED_ROLE, "contractDigest": digest, "developmentInputsDigest": dev_inputs_digest,
                                "selectedThreshold": selection["selectedThreshold"], "direction": selection.get("direction"),
                                "notPolicyThreshold": True, "notConfidenceThreshold": True, "frozenAt": datetime.now(timezone.utc).isoformat()}, indent=2),
                    encoding="utf-8")
    return path


def require_frozen(private_dir: Path, digest: str) -> Mapping[str, Any]:
    path = frozen_path(private_dir)
    if not path.exists():
        raise ThresholdNotFrozen("validation requires a frozen separability threshold")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("contractDigest") != digest or record.get("version") != VERSION or record.get("selectedThreshold") is None:
        raise ThresholdNotFrozen("frozen record does not match the study contract")
    return record


def validation_guard(private_dir: Path, digest: str, exposure_audit: Mapping[str, Any]) -> Path:
    require_frozen(private_dir, digest)
    if exposure_audit.get("validationScoreValuesPreviouslySeen") is not False:
        raise ValidationScoresPreviouslySeen("validation score values were previously exposed: NEW_HELDOUT_REQUIRED")
    lock = Path(private_dir) / VALIDATION_LOCK_NAME
    if lock.exists():
        raise sel.HoldoutAlreadyEvaluated(f"score validation already evaluated once: {lock.name}")
    return lock


def mark_validation_evaluated(lock: Path, digest: str) -> None:
    lock.write_text(json.dumps({"version": VERSION, "contractDigest": digest, "evaluatedAt": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")


def verdict(dev_selected: bool, validation_allowed: Optional[bool], validation_pass: Optional[bool]) -> str:
    if not dev_selected:
        return "FLORENCE_SEQUENCE_SCORE_NOT_SEPARATING"
    if validation_allowed is False:
        return "FLORENCE_SEQUENCE_SCORE_DEVELOPMENT_SEPARABLE_NEW_HELDOUT_REQUIRED"
    if validation_pass:
        return "FLORENCE_SEQUENCE_SCORE_SEPARABILITY_SUPPORTED"
    return "FLORENCE_SEQUENCE_SCORE_SEPARABILITY_NOT_SUPPORTED"
