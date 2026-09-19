"""B3-L17A — statistical sufficiency helper (one-sided exact binomial / Clopper-Pearson).

Evaluation-confidence arithmetic only.  These numbers size the sealed
evaluation corpus; they are NOT a training-size requirement
(TRAINING_SIZE_NOT_YET_JUSTIFIED: decided by the future supervised phase's
learning-curve contract).
"""

from __future__ import annotations

import argparse
import json
from typing import Any

TRAINING_SIZE_STATUS = "TRAINING_SIZE_NOT_YET_JUSTIFIED"
METHOD = "one-sided exact binomial (Clopper-Pearson) via beta quantiles"
CLEAN_GATE_TARGET = 0.10          # current clean gate: new allow->review <= 10 %
CLEAN_ASPIRATIONAL_TARGET = 0.05  # production-strength aspiration (reported separately)
RECALL_TARGET = 0.90              # critical family recall floor
CONFIDENCE = 0.95


def _beta_ppf(q: float, a: float, b: float) -> float:
    from scipy.stats import beta

    return float(beta.ppf(q, a, b))


def scipy_version() -> str:
    import scipy

    return scipy.__version__


def cp_upper_one_sided(successes: int, trials: int, confidence: float = CONFIDENCE) -> float:
    """One-sided upper Clopper-Pearson bound on the event rate after `successes` events in `trials` (e.g. false reviews among clean images)."""

    if trials <= 0 or successes >= trials:
        return 1.0
    if successes < 0:
        raise ValueError("successes must be >= 0")
    return _beta_ppf(confidence, successes + 1, trials - successes)


def cp_lower_one_sided(successes: int, trials: int, confidence: float = CONFIDENCE) -> float:
    """One-sided lower Clopper-Pearson bound on the event rate (e.g. recall after `successes` hits in `trials`)."""

    if trials <= 0 or successes <= 0:
        return 0.0
    if successes > trials:
        raise ValueError("successes must be <= trials")
    return _beta_ppf(1.0 - confidence, successes, trials - successes + 1)


def min_n_for_upper(failures: int, confidence: float = CONFIDENCE, target: float = CLEAN_GATE_TARGET, limit: int = 100000) -> int:
    """Smallest n such that, with exactly `failures` events observed, the one-sided upper bound is below `target`."""

    for n in range(failures + 1, limit):
        if cp_upper_one_sided(failures, n, confidence) < target:
            return n
    raise ValueError("no n below the search limit")


def min_n_for_lower(misses: int, confidence: float = CONFIDENCE, target: float = RECALL_TARGET, limit: int = 100000) -> int:
    """Smallest n such that, with exactly `misses` misses observed, the one-sided lower bound on recall is >= `target`."""

    for n in range(misses + 1, limit):
        if cp_lower_one_sided(n - misses, n, confidence) >= target:
            return n
    raise ValueError("no n below the search limit")


def training_size_from_evaluation_n(n: int) -> None:
    raise RuntimeError(f"{TRAINING_SIZE_STATUS}: evaluation-confidence n is not a training-size requirement")


def plan() -> dict[str, Any]:
    return {"method": METHOD, "confidence": CONFIDENCE, "scipyVersion": scipy_version(),
            "clean": {"gateTarget": CLEAN_GATE_TARGET, "minIndependentCleanFor0FalseReviews": min_n_for_upper(0, CONFIDENCE, CLEAN_GATE_TARGET),
                      "minIndependentCleanFor1FalseReview": min_n_for_upper(1, CONFIDENCE, CLEAN_GATE_TARGET), "aspirationalTarget": CLEAN_ASPIRATIONAL_TARGET,
                      "minIndependentCleanFor0FalseReviewsAt5pct": min_n_for_upper(0, CONFIDENCE, CLEAN_ASPIRATIONAL_TARGET),
                      "upperBoundAt0of29": round(cp_upper_one_sided(0, 29), 4), "upperBoundAt0of59": round(cp_upper_one_sided(0, 59), 4)},
            "recall": {"target": RECALL_TARGET, "minIndependentPositivesFor0Misses": min_n_for_lower(0), "minIndependentPositivesFor1Miss": min_n_for_lower(1),
                       "minIndependentPositivesFor2Misses": min_n_for_lower(2), "lowerBoundAt29of29": round(cp_lower_one_sided(29, 29), 4)},
            "unit": "independent image/group (never crop or region count)", "pointEstimateAloneIsInsufficient": True,
            "trainingSize": {"status": TRAINING_SIZE_STATUS, "decidedBy": "future supervised phase learning-curve contract", "evaluationNIsNotTrainingN": True}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--successes", type=int)
    parser.add_argument("--trials", type=int)
    parser.add_argument("--confidence", type=float, default=CONFIDENCE)
    parser.add_argument("--target", type=float)
    args = parser.parse_args(argv)
    out: dict[str, Any] = {"plan": plan()}
    if args.successes is not None and args.trials is not None:
        out["query"] = {"successes": args.successes, "trials": args.trials, "confidence": args.confidence,
                        "upperOneSided": cp_upper_one_sided(args.successes, args.trials, args.confidence), "lowerOneSided": cp_lower_one_sided(args.successes, args.trials, args.confidence)}
        if args.target is not None:
            out["query"]["minNFor0EventsBelowTarget"] = min_n_for_upper(0, args.confidence, args.target)
            out["query"]["minNFor1EventBelowTarget"] = min_n_for_upper(1, args.confidence, args.target)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
