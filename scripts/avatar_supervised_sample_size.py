"""B3-L17A / B3-L17A.1 — statistical sufficiency helper (one-sided exact binomial / Clopper-Pearson) + minimum-collection calculator.

Evaluation-confidence arithmetic only.  The 29 / 46 / 59 numbers are targets
for EVALUATION_ELIGIBLE_SEALED_GROUPS (independent groups that actually land
in SEALED_TEST).  They are NOT total collection targets and NOT a
training-size requirement (TRAINING_SIZE_NOT_YET_JUSTIFIED).

B3-L17A.1 adds `minimum_collected_groups`, which derives the minimum number of
COLLECTED_GROUPS needed so that the frozen deterministic splitter places at
least the target number of groups into SEALED_TEST.  The number is obtained by
simulating the actual splitter on synthetic opaque groups; ceil(target /
fraction) is reported only as a naive reference, never as the authority.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Optional

TRAINING_SIZE_STATUS = "TRAINING_SIZE_NOT_YET_JUSTIFIED"
METHOD = "one-sided exact binomial (Clopper-Pearson) via beta quantiles"
CLEAN_GATE_TARGET = 0.10          # current clean gate: new allow->review <= 10 %
CLEAN_ASPIRATIONAL_TARGET = 0.05  # production-strength aspiration (reported separately)
RECALL_TARGET = 0.90              # critical family recall floor
CONFIDENCE = 0.95
COLLECTION_METHOD = "simulate the frozen deterministic splitter on n synthetic opaque groups"
COLLECTION_POOLS = {"FUTURE": {"provenanceClass": "FUTURE_HOLDOUT_ELIGIBLE", "lineageReservation": None},
                    "LEGACY": {"provenanceClass": "LEGACY_DEVELOPMENT_CONTAMINATED", "lineageReservation": None},
                    "SEALED_RESERVED": {"provenanceClass": "FUTURE_HOLDOUT_ELIGIBLE", "lineageReservation": "SEALED_RESERVED"}}


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


def training_size_from_collection_n(n: int) -> None:
    raise RuntimeError(f"{TRAINING_SIZE_STATUS}: minimum collection n is split/evaluation-quota arithmetic, not a training-size requirement")


# ------------------------------------------------------------------ B3-L17A.1 minimum collection (splitter simulation)


def _sealed_count(n: int, stratum: str, pool: dict) -> int:
    import avatar_supervised_split_plan as sp   # lazy: the contract module imports this helper

    tag = "".join(ch for ch in stratum.lower() if ch.isalnum())
    groups = []
    for i in range(n):
        g = {"groupId": f"grp-sim{tag}{i:05d}", "provenanceClass": pool["provenanceClass"], "evaluationStrata": [stratum], "imageCount": 1}
        if pool["lineageReservation"]:
            g["lineageReservation"] = pool["lineageReservation"]
        groups.append(g)
    plan = sp.plan_split(groups) if groups else {}
    return sum(1 for p in plan.values() if p == "SEALED_TEST")


def minimum_collected_groups(target_sealed_groups: int, sealed_fraction: Optional[float] = None, stratum: str = "GRAPHICAL_LOGO", provenance_pool: str = "FUTURE") -> dict[str, Any]:
    """Minimum COLLECTED_GROUPS (one stratum, one provenance pool) so that the frozen splitter yields >= target EVALUATION_ELIGIBLE_SEALED_GROUPS."""

    import avatar_supervised_dataset_contract as sc   # lazy (circular)

    if target_sealed_groups <= 0:
        raise ValueError("target_sealed_groups must be >= 1")
    if provenance_pool not in COLLECTION_POOLS:
        raise ValueError(f"provenance_pool must be one of {sorted(COLLECTION_POOLS)}")
    if stratum not in sc.SPLIT_LABELS:
        raise ValueError(f"stratum must be one of {sc.SPLIT_LABELS}")
    pool = COLLECTION_POOLS[provenance_pool]
    allowed = sc.group_allowed_partitions({"provenanceClass": pool["provenanceClass"], "lineageReservation": pool["lineageReservation"]})
    if "SEALED_TEST" not in allowed:
        raise ValueError(f"pool {provenance_pool} can never reach SEALED_TEST (allowed partitions: {allowed}); no collection size makes it sealed evidence")
    frozen_fraction = sc.PARTITION_FRACTIONS["SEALED_TEST"] / sum(sc.PARTITION_FRACTIONS[p] for p in allowed)
    if sealed_fraction is not None and abs(sealed_fraction - frozen_fraction) > 1e-9:
        raise ValueError(f"sealed_fraction {sealed_fraction} is not the frozen contract fraction {frozen_fraction} for pool {provenance_pool}; the fraction is not a free parameter")
    naive = -(-target_sealed_groups // 1) if frozen_fraction >= 1.0 else int(-(-target_sealed_groups // frozen_fraction))
    limit = max(int(target_sealed_groups / frozen_fraction) + 50, target_sealed_groups + 5)
    minimum = None
    for n in range(target_sealed_groups, limit + 1):
        if _sealed_count(n, stratum, pool) >= target_sealed_groups:
            minimum = n
            break
    if minimum is None:
        raise ValueError("no collection size below the search limit reaches the sealed target")
    return {"targetSealedGroups": target_sealed_groups, "targetCountKind": "EVALUATION_ELIGIBLE_SEALED_GROUPS", "countKind": "COLLECTED_GROUPS", "stratum": stratum, "provenancePool": provenance_pool,
            "sealedFraction": round(frozen_fraction, 6), "method": COLLECTION_METHOD, "splitPlanDigestPrefix": sc.split_plan_digest()[:12],
            "minimumCollectedIndependentGroupsRequired": minimum, "sealedGroupsAtMinimum": _sealed_count(minimum, stratum, pool), "sealedGroupsOneBelow": _sealed_count(minimum - 1, stratum, pool) if minimum > 1 else 0,
            "naiveCeil": int(naive), "naiveCeilIsAuthority": False, "unit": "independent group (never image, crop or region)",
            "assumption": "single-label groups in one provenance pool; multi-label corpora are checked by the sealed quota validator at manifest freeze",
            "isTrainingSizeRequirement": False, "trainingSize": TRAINING_SIZE_STATUS}


def plan() -> dict[str, Any]:
    return {"method": METHOD, "confidence": CONFIDENCE, "scipyVersion": scipy_version(),
            "clean": {"gateTarget": CLEAN_GATE_TARGET, "minIndependentCleanFor0FalseReviews": min_n_for_upper(0, CONFIDENCE, CLEAN_GATE_TARGET),
                      "minIndependentCleanFor1FalseReview": min_n_for_upper(1, CONFIDENCE, CLEAN_GATE_TARGET), "aspirationalTarget": CLEAN_ASPIRATIONAL_TARGET,
                      "minIndependentCleanFor0FalseReviewsAt5pct": min_n_for_upper(0, CONFIDENCE, CLEAN_ASPIRATIONAL_TARGET),
                      "upperBoundAt0of29": round(cp_upper_one_sided(0, 29), 4), "upperBoundAt0of59": round(cp_upper_one_sided(0, 59), 4)},
            "recall": {"target": RECALL_TARGET, "minIndependentPositivesFor0Misses": min_n_for_lower(0), "minIndependentPositivesFor1Miss": min_n_for_lower(1),
                       "minIndependentPositivesFor2Misses": min_n_for_lower(2), "lowerBoundAt29of29": round(cp_lower_one_sided(29, 29), 4)},
            "unit": "independent image/group (never crop or region count)", "pointEstimateAloneIsInsufficient": True,
            "countKindOfTheseTargets": "EVALUATION_ELIGIBLE_SEALED_GROUPS",
            "minimumCollection": {"countKind": "COLLECTED_GROUPS", "method": COLLECTION_METHOD, "isTrainingSizeRequirement": False,
                                  "sealed29": minimum_collected_groups(min_n_for_lower(0)), "sealed46": minimum_collected_groups(min_n_for_lower(1)),
                                  "clean29": minimum_collected_groups(min_n_for_upper(0), stratum="NATURAL_CLEAN_REPRESENTATIVE"),
                                  "clean59Aspirational": minimum_collected_groups(min_n_for_upper(0, CONFIDENCE, CLEAN_ASPIRATIONAL_TARGET), stratum="NATURAL_CLEAN_REPRESENTATIVE")},
            "trainingSize": {"status": TRAINING_SIZE_STATUS, "decidedBy": "future supervised phase learning-curve contract", "evaluationNIsNotTrainingN": True, "collectionNIsNotTrainingN": True}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--successes", type=int)
    parser.add_argument("--trials", type=int)
    parser.add_argument("--confidence", type=float, default=CONFIDENCE)
    parser.add_argument("--target", type=float)
    parser.add_argument("--sealed-target", type=int, help="derive the minimum COLLECTED_GROUPS for this many EVALUATION_ELIGIBLE_SEALED_GROUPS")
    parser.add_argument("--stratum", default="GRAPHICAL_LOGO")
    parser.add_argument("--pool", default="FUTURE", choices=sorted(COLLECTION_POOLS))
    args = parser.parse_args(argv)
    out: dict[str, Any] = {"plan": plan()}
    if args.successes is not None and args.trials is not None:
        out["query"] = {"successes": args.successes, "trials": args.trials, "confidence": args.confidence,
                        "upperOneSided": cp_upper_one_sided(args.successes, args.trials, args.confidence), "lowerOneSided": cp_lower_one_sided(args.successes, args.trials, args.confidence)}
        if args.target is not None:
            out["query"]["minNFor0EventsBelowTarget"] = min_n_for_upper(0, args.confidence, args.target)
            out["query"]["minNFor1EventBelowTarget"] = min_n_for_upper(1, args.confidence, args.target)
    if args.sealed_target is not None:
        out["minimumCollection"] = minimum_collected_groups(args.sealed_target, stratum=args.stratum, provenance_pool=args.pool)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
