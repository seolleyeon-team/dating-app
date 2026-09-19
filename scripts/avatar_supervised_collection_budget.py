"""B3-L17B0 — full-collection budget calculator (planning only; expectation, never a guarantee).

Given a sealed evaluation target (EVALUATION_ELIGIBLE_SEALED_GROUPS), the
frozen split contract and an incidence p of natural positives per independent
source lineage, derive the EXPECTED number of independent lineages (groups) and
generated outputs to collect.  Independent groups and generated outputs are
always separate numbers: k outputs regenerated from one source lineage are one
group, never k evaluation units.

Until FIRST_PARTY_NATURAL_MARK_INCIDENCE_PILOT_V1 has been run and labelled by
blinded humans, the incidence is NATURAL_POSITIVE_INCIDENCE_UNKNOWN and no
generation budget is confirmed: `confirmed_generation_budget()` raises.  No
generation, no model, no production data in this module.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_supervised_dataset_contract as sc  # noqa: E402
import avatar_supervised_sample_size as ss  # noqa: E402

PLAN_VERSION = "B3_L17B0_COLLECTION_FEASIBILITY_V1"
INCIDENCE_STATUS = "NATURAL_POSITIVE_INCIDENCE_UNKNOWN"
EXPECTATION_ONLY = True
DEFAULT_OUTPUTS_PER_LINEAGE = 4          # one canonical generation job yields up to 4 candidates (max4 job cap); still ONE group
DEFAULT_RISK_INCIDENCES = (0.01, 0.02, 0.05, 0.10, 0.20, 0.50)
SUFFICIENCY_CONFIDENCE = 0.95
COLLECTION_POOLS = ("FUTURE", "SEALED_RESERVED")


def _binom_sf(k_minus_1: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), passed as sf(k-1)."""

    from scipy.stats import binom

    return float(binom.sf(k_minus_1, n, p))


def independent_groups(source_lineages: int, outputs_per_lineage: int = DEFAULT_OUTPUTS_PER_LINEAGE) -> dict[str, Any]:
    """Generated outputs and independent groups are different numbers: outputs from one lineage form one group."""

    if source_lineages < 0 or outputs_per_lineage <= 0:
        raise ValueError("source_lineages must be >= 0 and outputs_per_lineage >= 1")
    return {"sourceLineages": source_lineages, "outputsPerLineage": outputs_per_lineage, "generatedOutputs": source_lineages * outputs_per_lineage, "independentGroups": source_lineages,
            "unit": sc.STATISTICAL_UNIT, "rule": "same source lineage regeneration = same group; outputs never count as independent evaluation units"}


def required_collected_positive_groups(target_sealed: int, pool: str = "FUTURE", stratum: str = "GRAPHICAL_LOGO") -> dict[str, Any]:
    if pool not in COLLECTION_POOLS:
        raise ValueError(f"pool must be one of {COLLECTION_POOLS}")
    m = ss.minimum_collected_groups(target_sealed, stratum=stratum, provenance_pool=pool)
    return {"targetSealedGroups": target_sealed, "targetCountKind": m["targetCountKind"], "pool": pool, "sealedFraction": m["sealedFraction"],
            "minimumCollectedPositiveGroups": m["minimumCollectedIndependentGroupsRequired"], "countKind": "COLLECTED_GROUPS", "splitPlanDigestPrefix": m["splitPlanDigestPrefix"]}


def lineages_for_sufficiency(required_positive_groups: int, incidence_p: float, confidence: float = SUFFICIENCY_CONFIDENCE, limit: int = 2_000_000) -> int:
    """Smallest N such that P(Binomial(N, p) >= required) >= confidence (planning bound for the upper budget risk)."""

    n = max(required_positive_groups, 1)
    step = max(1, n // 10)
    while n < limit and _binom_sf(required_positive_groups - 1, n, incidence_p) < confidence:
        n += step
    lo, hi = max(required_positive_groups, n - step), n
    while lo < hi:
        mid = (lo + hi) // 2
        if _binom_sf(required_positive_groups - 1, mid, incidence_p) >= confidence:
            hi = mid
        else:
            lo = mid + 1
    if _binom_sf(required_positive_groups - 1, lo, incidence_p) < confidence:
        raise ValueError("no lineage count below the search limit reaches the sufficiency confidence")
    return lo


def expected_generation(target_sealed_positives: int, incidence_p: Optional[float], outputs_per_lineage: int = DEFAULT_OUTPUTS_PER_LINEAGE, pool: str = "FUTURE", stratum: str = "GRAPHICAL_LOGO") -> dict[str, Any]:
    """Expected lineages / outputs to generate for one stratum at incidence p. Expectation only; the 95 % sufficiency count is the upper budget risk."""

    req = required_collected_positive_groups(target_sealed_positives, pool, stratum)
    base = {"planVersion": PLAN_VERSION, "stratum": stratum, "targetSealedPositives": target_sealed_positives, "targetCountKind": req["targetCountKind"], "pool": pool,
            "requiredCollectedPositiveGroups": req["minimumCollectedPositiveGroups"], "outputsPerLineage": outputs_per_lineage, "isExpectationOnly": EXPECTATION_ONLY, "guaranteed": False,
            "trainingSize": ss.TRAINING_SIZE_STATUS}
    if incidence_p is None:
        return base | {"incidenceStatus": INCIDENCE_STATUS, "incidence": None, "expectedIndependentGroupsToGenerate": None, "expectedGeneratedOutputs": None, "generationPlanConfirmed": False,
                       "note": "no generation count is fixed until FIRST_PARTY_NATURAL_MARK_INCIDENCE_PILOT_V1 has estimated the incidence with blinded human labels"}
    if not (0.0 < incidence_p <= 1.0):
        raise ValueError("incidence_p must be in (0, 1]")
    m = req["minimumCollectedPositiveGroups"]
    expected_lineages = math.ceil(m / incidence_p)
    n95 = lineages_for_sufficiency(m, incidence_p)
    shortfall = 1.0 - _binom_sf(m - 1, expected_lineages, incidence_p)
    return base | {"incidenceStatus": "INCIDENCE_ASSUMED_FOR_PLANNING", "incidence": incidence_p, "expectedIndependentGroupsToGenerate": expected_lineages,
                   "expectedGeneratedOutputs": expected_lineages * outputs_per_lineage, "generationPlanConfirmed": False,
                   "upperBudgetRisk": {"lineagesFor95pctSufficiency": n95, "outputsFor95pctSufficiency": n95 * outputs_per_lineage, "shortfallProbabilityAtExpected": round(shortfall, 4),
                                       "why": "at the expected count the realised positive lineages fall below the requirement with the stated probability; low prevalence multiplies the budget"}}


def risk_table(target_sealed_positives: int, incidences: Sequence[float] = DEFAULT_RISK_INCIDENCES, outputs_per_lineage: int = DEFAULT_OUTPUTS_PER_LINEAGE, pool: str = "FUTURE", stratum: str = "GRAPHICAL_LOGO") -> list[dict[str, Any]]:
    rows = []
    for p in incidences:
        e = expected_generation(target_sealed_positives, p, outputs_per_lineage, pool, stratum)
        rows.append({"incidence": p, "requiredCollectedPositiveGroups": e["requiredCollectedPositiveGroups"], "expectedLineages": e["expectedIndependentGroupsToGenerate"], "expectedOutputs": e["expectedGeneratedOutputs"],
                     "lineagesFor95pctSufficiency": e["upperBudgetRisk"]["lineagesFor95pctSufficiency"], "outputsFor95pctSufficiency": e["upperBudgetRisk"]["outputsFor95pctSufficiency"]})
    return rows


def combined_expectation(target_sealed_positives: int, incidence_by_class: Mapping[str, Optional[float]], outputs_per_lineage: int = DEFAULT_OUTPUTS_PER_LINEAGE, pool: str = "FUTURE") -> dict[str, Any]:
    """Lineages are shared across strata: the rarest stratum dominates. Any unknown class incidence keeps the whole budget unconfirmed."""

    per_class = {cls: expected_generation(target_sealed_positives, incidence_by_class.get(cls), outputs_per_lineage, pool, cls) for cls in sc.CRITICAL_POSITIVE_STRATA}
    unknown = [cls for cls, e in per_class.items() if e["expectedIndependentGroupsToGenerate"] is None]
    if unknown:
        return {"planVersion": PLAN_VERSION, "incidenceStatus": INCIDENCE_STATUS, "unknownClasses": unknown, "dominantStratum": None, "expectedIndependentGroupsToGenerate": None, "expectedGeneratedOutputs": None,
                "generationPlanConfirmed": False, "perClass": per_class}
    dominant = max(per_class, key=lambda c: per_class[c]["expectedIndependentGroupsToGenerate"])
    e = per_class[dominant]
    return {"planVersion": PLAN_VERSION, "incidenceStatus": "INCIDENCE_ASSUMED_FOR_PLANNING", "unknownClasses": [], "dominantStratum": dominant, "expectedIndependentGroupsToGenerate": e["expectedIndependentGroupsToGenerate"],
            "expectedGeneratedOutputs": e["expectedGeneratedOutputs"], "upperBudgetRisk": e["upperBudgetRisk"], "generationPlanConfirmed": False, "isExpectationOnly": True, "perClass": per_class,
            "note": "lineages generated for one stratum serve all strata; the rarest stratum sets the budget; representative clean lineages come from the same generation and are usually the majority"}


def confirmed_generation_budget(pilot_result: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """A confirmed budget needs a completed, blinded, human-labelled pilot result with an incidence estimate per critical class. Never available in this task."""

    if not pilot_result or pilot_result.get("status") != "PILOT_COMPLETED_HUMAN_LABELLED" or not pilot_result.get("incidenceByClass"):
        raise RuntimeError(f"{INCIDENCE_STATUS}: no blinded human-labelled incidence pilot result; a fixed generation count (e.g. 142 x strata) is not confirmed")
    return combined_expectation(pilot_result.get("targetSealedPositives", ss.min_n_for_lower(0)), pilot_result["incidenceByClass"]) | {"ownerApprovalRequired": True, "executed": False}


def training_size_from_budget(*_a, **_k) -> None:
    raise RuntimeError(f"{ss.TRAINING_SIZE_STATUS}: a collection budget is not a training-size justification")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=int, default=ss.min_n_for_lower(0))
    parser.add_argument("--incidence", type=float, default=None, help="assumed incidence per lineage for planning only; omit to report NATURAL_POSITIVE_INCIDENCE_UNKNOWN")
    parser.add_argument("--pool", default="FUTURE", choices=COLLECTION_POOLS)
    args = parser.parse_args(argv)
    print(json.dumps({"expected": expected_generation(args.target, args.incidence, pool=args.pool), "riskTable": risk_table(args.target, pool=args.pool)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
