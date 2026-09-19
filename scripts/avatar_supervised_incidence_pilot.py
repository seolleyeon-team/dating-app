"""B3-L17B0 — FIRST_PARTY_NATURAL_MARK_INCIDENCE_PILOT_V1: plan, validators and aggregate-only report tool (no execution).

The pilot's purpose is to estimate how often each natural-positive class and
representative clean output occur in owner-authorized first-party canonical
generation.  This module only plans and validates: it generates nothing
(Azure 0, OpenAI image 0), trains nothing, scores nothing, and never touches
production user data.  Pilot images are PILOT_DISCOVERY_NOT_SEALED_TEST from
the start; classification is by blinded human labels only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_supervised_collection_budget as cb  # noqa: E402
import avatar_supervised_dataset_contract as sc  # noqa: E402
import avatar_supervised_sample_size as ss  # noqa: E402

PILOT_VERSION = "FIRST_PARTY_NATURAL_MARK_INCIDENCE_PILOT_V1"
PILOT_DATA_STATUS = "PILOT_DISCOVERY_NOT_SEALED_TEST"
PILOT_ALLOWED_PARTITIONS = ("TRAIN_DEVELOPMENT", "VALIDATION")     # eligibility decided separately later; SEALED_TEST never
PILOT_LINEAGE_RESERVATION = "DEVELOPMENT_ONLY"
PILOT_PROVENANCE_CLASS = "FUTURE_TRAINING_ELIGIBLE"
PILOT_BATCH_PREFIX = "pilot-"
INCIDENCE_STATUS = cb.INCIDENCE_STATUS
EXECUTION_STATUS = "PLAN_ONLY_NOT_EXECUTED"
CANONICAL_PROVIDER = {"provider": "azure", "modelId": "azure_gpt_image_2", "note": "canonical generation path; revision recorded per batch at generation time, never assumed"}

# ------------------------------------------------------------------ source lineage authority

SOURCE_CATEGORIES = ("OWNER_VOLUNTEER_REAL_SOURCE", "OWNER_AUTHORIZED_SYNTHETIC_SOURCE", "PRODUCTION_USER_SOURCE")
SOURCE_CATEGORY_POLICY = {
    "OWNER_VOLUNTEER_REAL_SOURCE": {"allowedInPilot": True, "requires": ["explicit volunteer consent", "separate privacy authority"], "sourcePhotoClass": "RESTRICTED_SOURCE_NOT_MODEL_DATA",
                                    "datasetRecord": "generated output only", "domainValidity": "REAL_SOURCE_DOMAIN", "realUserDomainEquivalent": False},
    "OWNER_AUTHORIZED_SYNTHETIC_SOURCE": {"allowedInPilot": True, "requires": ["owner authorization"], "sourcePhotoClass": "RESTRICTED_SOURCE_NOT_MODEL_DATA", "datasetRecord": "generated output only",
                                          "domainValidity": "SYNTHETIC_SOURCE_DOMAIN_LIMITATION", "realUserDomainEquivalent": False, "forbiddenClaim": "REAL_USER_SOURCE_DOMAIN_VALIDATED"},
    "PRODUCTION_USER_SOURCE": {"allowedInPilot": False, "requires": ["not usable in this plan"], "sourcePhotoClass": "RESTRICTED_SOURCE_NOT_MODEL_DATA", "datasetRecord": "none",
                               "domainValidity": "not applicable", "realUserDomainEquivalent": False},
}
SYNTHETIC_DOMAIN_MARKER = "SYNTHETIC_SOURCE_DOMAIN_LIMITATION"
FORBIDDEN_DOMAIN_CLAIM = "REAL_USER_SOURCE_DOMAIN_VALIDATED"
LINEAGE_ID_PATTERN = r"lin-[0-9a-z]+"
LINEAGE_DEFINITION = {"unit": "independent source lineage = one source subject/photo set that no other lineage shares (no regeneration, variant, crop or near duplicate of another lineage)",
                      "regeneration": "same lineage regeneration = same group", "developmentReuse": "a lineage used for train/dev generation is never reused as a sealed lineage",
                      "idFormat": "opaque lin-<alnum>; never a user id, filename or path"}


def check_pilot_source(category: str, consent_authority: Optional[str] = None) -> list[str]:
    if category not in SOURCE_CATEGORIES:
        return [f"unknown source category {category!r}"]
    policy = SOURCE_CATEGORY_POLICY[category]
    errors = []
    if not policy["allowedInPilot"]:
        errors.append(f"{category} is prohibited in {PILOT_VERSION} (no production user data)")
    if category == "OWNER_VOLUNTEER_REAL_SOURCE" and not consent_authority:
        errors.append("OWNER_VOLUNTEER_REAL_SOURCE requires an explicit consent/privacy authority reference")
    return errors


def natural_artifact_claim(category: str) -> dict[str, Any]:
    if category not in SOURCE_CATEGORIES or not SOURCE_CATEGORY_POLICY[category]["allowedInPilot"]:
        raise ValueError(f"{category} yields no pilot artifacts")
    return {"artifactKind": "NATURAL_GENERATION_ARTIFACT", "domainMarker": SYNTHETIC_DOMAIN_MARKER if category == "OWNER_AUTHORIZED_SYNTHETIC_SOURCE" else None,
            "realUserDomainValidated": False, "forbiddenClaim": FORBIDDEN_DOMAIN_CLAIM}


def validate_lineage_id(lineage_id: Any) -> list[str]:
    if not isinstance(lineage_id, str) or not re.fullmatch(LINEAGE_ID_PATTERN, lineage_id):
        return ["lineageId must be opaque (lin-<alnum>); identity-like ids are forbidden"]
    return []


def lineage_groups(outputs: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """All outputs of one source lineage form exactly one group."""

    groups: dict[str, list[str]] = defaultdict(list)
    for o in outputs:
        if validate_lineage_id(o.get("lineageId")):
            raise ValueError(f"invalid lineageId on {o.get('opaqueImageId')}")
        groups[o["lineageId"]].append(o["opaqueImageId"])
    return dict(groups)


def independent_lineage_count(outputs: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    g = lineage_groups(outputs)
    return {"generatedOutputs": len(outputs), "independentGroups": len(g)}


# ------------------------------------------------------------------ pilot data status / human-label-only contract

PILOT_LABEL_CONTRACT = {"blindedHumanLabelsOnly": True, "coverage": "every generated pilot output is labelled by blinded raters; no model-selected subset",
                        "modelScoreFiltering": False, "prohibitedInputs": ("CLIP", "DINOv2", "Grounding DINO", "Florence", "OWLv2", "future supervised model", "model score filtering"),
                        "labelAuthority": "dual independent raters + adjudication as SUPERVISED_WATERMARK_LOGO_DATASET_V1_1", "blindingForbiddenFields": list(sc.BLINDING_FORBIDDEN)}
_SCORE_TOKENS = ("score", "prediction", "threshold", "passfail", "detector", "verifier", "proposal", "logit", "embedding")


def check_pilot_label_input(record: Mapping[str, Any]) -> list[str]:
    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)
    out = []
    for k in keys(record):
        lowered = str(k).lower()
        if k in sc.BLINDING_FORBIDDEN or any(t in lowered for t in _SCORE_TOKENS):
            out.append(f"model output is not a pilot input: {k}")
    return out


def validate_pilot_record(record: Mapping[str, Any]) -> list[str]:
    errors = check_pilot_label_input(record)
    if record.get("split") == "SEALED_TEST":
        errors.append(f"{PILOT_DATA_STATUS}: pilot images are never SEALED_TEST")
    if record.get("lineageReservation") != PILOT_LINEAGE_RESERVATION:
        errors.append(f"pilot records must carry lineageReservation {PILOT_LINEAGE_RESERVATION}")
    if record.get("provenanceClass") != PILOT_PROVENANCE_CLASS:
        errors.append(f"pilot records must be {PILOT_PROVENANCE_CLASS} (never holdout-eligible)")
    if not str(record.get("collectionBatch", "")).startswith(PILOT_BATCH_PREFIX):
        errors.append(f"pilot collectionBatch must start with {PILOT_BATCH_PREFIX!r}")
    if record.get("originKind") != "NATURAL_GENERATED_OUTPUT":
        errors.append("pilot outputs are natural generated outputs only (no synthetic overlay, no challenge derivative)")
    errors += validate_lineage_id(record.get("lineageId"))
    base = {k: v for k, v in record.items() if k != "lineageId"}
    errors += sc.validate_image_record(base)
    return errors


# ------------------------------------------------------------------ size options / cost / stopping rule

ASSUMPTIONS = {"outputsPerLineage": cb.DEFAULT_OUTPUTS_PER_LINEAGE, "storageMbPerOutputUpperBound": 2.0, "raterMinutesPerOutput": 1.5, "raters": 2,
               "note": "storage and labelling numbers are declared planning assumptions, not measurements"}
PILOT_SIZE_OPTIONS = {"SMALL": {"independentSourceLineages": 12}, "MEDIUM": {"independentSourceLineages": 30}, "LARGE": {"independentSourceLineages": 60}}
OBSERVABILITY_INCIDENCES = (0.01, 0.05, 0.10, 0.20)
COST_STATUS = "COST_NOT_VERIFIED"
FEASIBILITY_FLOOR_POSITIVE_LINEAGES_PER_CLASS = 3
STOPPING_RULE = {"fixedGenerationAttemptCap": True, "capUnit": "generation attempts (jobs x candidates)", "modelScoreAdaptiveContinuation": False,
                 "extensionTrigger": f"blinded human-labelled positive lineage count in a critical class below the feasibility floor ({FEASIBILITY_FLOOR_POSITIVE_LINEAGES_PER_CLASS})",
                 "extensionRequires": "explicit owner re-approval of a new cap", "automaticPaidExtension": False, "agentMayIncreaseCap": False, "frozenBeforeStart": True}
PAID_GENERATION = {"executedInThisTask": False, "azureCalls": 0, "openaiImageCalls": 0, "requiresExplicitOwnerApproval": True, "automaticExecution": False, "status": EXECUTION_STATUS}


def _observability(lineages: int) -> dict[str, Any]:
    return {"probabilityAtLeastOnePositiveLineage": {str(p): round(1.0 - (1.0 - p) ** lineages, 4) for p in OBSERVABILITY_INCIDENCES},
            "expectedPositiveLineages": {str(p): round(p * lineages, 2) for p in OBSERVABILITY_INCIDENCES},
            "zeroObservedIncidenceUpperBound95": round(ss.cp_upper_one_sided(0, lineages), 4),
            "note": "rare strata (incidence ~1 %) are unlikely to be observed at all in a small pilot; the pilot then yields only an upper bound"}


def size_option(name: str) -> dict[str, Any]:
    if name not in PILOT_SIZE_OPTIONS:
        raise ValueError(f"unknown option {name!r}; options: {sorted(PILOT_SIZE_OPTIONS)}")
    lineages = PILOT_SIZE_OPTIONS[name]["independentSourceLineages"]
    per = ASSUMPTIONS["outputsPerLineage"]
    counts = cb.independent_groups(lineages, per)
    outputs = counts["generatedOutputs"]
    limitations = ["incidence is per lineage; outputs from one lineage are one group", "PILOT_DISCOVERY_NOT_SEALED_TEST: no pilot image can become sealed evidence",
                   "synthetic-source lineages carry SYNTHETIC_SOURCE_DOMAIN_LIMITATION", "cost is COST_NOT_VERIFIED until a fresh provider price source is recorded"]
    if lineages < 30:
        limitations.append("a class with incidence <= 5 % will most likely not be observed; only an upper bound results")
    return {"option": name, "independentSourceLineages": lineages, "generationAttemptsPerLineage": per, "totalGenerationAttempts": outputs, "generatedOutputs": outputs, "independentGroups": counts["independentGroups"],
            "estimatedLabelingWorkload": {"raterLabels": outputs * ASSUMPTIONS["raters"], "raterMinutesAssumed": round(outputs * ASSUMPTIONS["raters"] * ASSUMPTIONS["raterMinutesPerOutput"], 1), "assumption": "declared, not measured"},
            "estimatedStorageMbUpperBound": round(outputs * ASSUMPTIONS["storageMbPerOutputUpperBound"], 1), "observability": _observability(lineages), "cost": cost_estimate(name),
            "fixedGenerationAttemptCap": outputs, "limitations": limitations, "dataStatus": PILOT_DATA_STATUS}


def cost_estimate(name: str, unit_price_usd: Optional[float] = None, price_source: Optional[str] = None, price_verified_on: Optional[str] = None) -> dict[str, Any]:
    attempts = PILOT_SIZE_OPTIONS[name]["independentSourceLineages"] * ASSUMPTIONS["outputsPerLineage"]
    if unit_price_usd is None or not price_source or not price_verified_on:
        return {"status": COST_STATUS, "generationAttempts": attempts, "why": "no fresh verified provider pricing source was supplied; the repo holds no pricing authority"}
    return {"status": "COST_ESTIMATED_FROM_VERIFIED_SOURCE", "generationAttempts": attempts, "unitPriceUsd": unit_price_usd, "estimatedUsd": round(attempts * unit_price_usd, 2), "priceSource": price_source, "priceVerifiedOn": price_verified_on}


def pilot_plan(option: str, source_category: str = "OWNER_AUTHORIZED_SYNTHETIC_SOURCE") -> dict[str, Any]:
    o = size_option(option)
    src_errors = check_pilot_source(source_category, consent_authority="owner-designated" if source_category == "OWNER_VOLUNTEER_REAL_SOURCE" else None)
    plan = {"pilotVersion": PILOT_VERSION, "option": option, "sourceCategory": source_category, "sourceErrors": src_errors, "dataStatus": PILOT_DATA_STATUS, "allowedPartitionsLater": list(PILOT_ALLOWED_PARTITIONS),
            "sealedTestEligible": False, "lineageReservation": PILOT_LINEAGE_RESERVATION, "labelContract": PILOT_LABEL_CONTRACT, "fixedGenerationAttemptCap": o["fixedGenerationAttemptCap"],
            "stoppingRule": STOPPING_RULE, "feasibilityFloorPositiveLineagesPerClass": FEASIBILITY_FLOOR_POSITIVE_LINEAGES_PER_CLASS, "paidGeneration": PAID_GENERATION, "provider": CANONICAL_PROVIDER,
            "incidenceStatus": INCIDENCE_STATUS, "execution": EXECUTION_STATUS, "sizes": o}
    plan["planDigest"] = hashlib.sha256(json.dumps({k: v for k, v in plan.items() if k != "sourceErrors"}, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return plan


def validate_stopping_rule(plan: Mapping[str, Any]) -> list[str]:
    errors = []
    cap = plan.get("fixedGenerationAttemptCap")
    if not isinstance(cap, int) or cap <= 0:
        errors.append("a fixed positive integer generation-attempt cap is required before the pilot starts")
    rule = plan.get("stoppingRule", {})
    if rule.get("modelScoreAdaptiveContinuation") is not False:
        errors.append("model-score adaptive continuation is prohibited")
    if rule.get("automaticPaidExtension") is not False or rule.get("agentMayIncreaseCap") is not False:
        errors.append("automatic paid extension is prohibited; extension needs owner re-approval")
    return errors


def request_extension(plan: Mapping[str, Any], positive_lineages_by_class: Mapping[str, int]) -> dict[str, Any]:
    """Never extends anything: reports whether the human-labelled floor triggers an owner re-approval request."""

    below = {c: positive_lineages_by_class.get(c, 0) for c in sc.CRITICAL_POSITIVE_STRATA if positive_lineages_by_class.get(c, 0) < plan["feasibilityFloorPositiveLineagesPerClass"]}
    return {"trigger": bool(below), "classesBelowFloor": below, "status": "OWNER_REAPPROVAL_REQUIRED" if below else "NO_EXTENSION_TRIGGER", "executed": False, "automatic": False,
            "currentCap": plan["fixedGenerationAttemptCap"], "newCap": None}


def execute_generation(*_args, **_kwargs) -> None:
    raise RuntimeError(f"{EXECUTION_STATUS}: paid generation requires explicit owner approval and is never executed by this module (Azure 0, OpenAI image 0)")


# ------------------------------------------------------------------ incidence report tool (aggregate only; group unit)


def _cp_two_sided(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    from scipy.stats import beta

    if n <= 0:
        return (0.0, 1.0)
    alpha = 1.0 - confidence
    lower = 0.0 if k == 0 else float(beta.ppf(alpha / 2, k, n - k + 1))
    upper = 1.0 if k == n else float(beta.ppf(1 - alpha / 2, k + 1, n - k))
    return (round(lower, 4), round(upper, 4))


def incidence_report(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate-only incidence per class over independent lineages (groups). Refuses any model-score input."""

    for r in records:
        bad = check_pilot_label_input(r)
        if bad:
            raise ValueError(f"incidence report accepts blinded human labels only: {bad[0]}")
        if r.get("split") == "SEALED_TEST":
            raise ValueError(f"{PILOT_DATA_STATUS}: sealed records cannot enter a pilot incidence report")
    groups = lineage_groups(records)
    n = len(groups)
    by_lineage: dict[str, list] = defaultdict(list)
    for r in records:
        by_lineage[r["lineageId"]].append(r)
    positive: Counter = Counter()
    clean_rep = 0
    uncertain = 0
    for lid, recs in by_lineage.items():
        classes = {g.get("class") for r in recs for g in r.get("regions", []) if g.get("class") in sc.POLICY_POSITIVE_CLASSES}
        for c in classes:
            positive[c] += 1
        statuses = {sc.clean_status(r) for r in recs}
        if statuses == {"CLEAN"} and all(sc.clean_category(r) == "NATURAL_CLEAN_REPRESENTATIVE" for r in recs):
            clean_rep += 1
        if "UNCERTAIN" in statuses:
            uncertain += 1
    per_class = {}
    for c in sc.POLICY_POSITIVE_CLASSES:
        k = positive.get(c, 0)
        per_class[c] = {"totalIndependentGroups": n, "totalGeneratedOutputs": len(records), "naturalPositiveGroups": k, "incidenceEstimate": round(k / n, 4) if n else None,
                        "exactBinomialInterval95": _cp_two_sided(k, n) if n else None, "feasibilityFloorMet": k >= FEASIBILITY_FLOOR_POSITIVE_LINEAGES_PER_CLASS}
    return {"pilotVersion": PILOT_VERSION, "unit": "independent lineage (group)", "totalIndependentGroups": n, "totalGeneratedOutputs": len(records), "perClass": per_class,
            "cleanRepresentativeGroups": clean_rep, "uncertainGroups": uncertain, "dataStatus": PILOT_DATA_STATUS, "humanLabelsOnly": True,
            "status": "PILOT_COMPLETED_HUMAN_LABELLED" if n else "PILOT_NOT_RUN"}


# ------------------------------------------------------------------ batch provenance / provider drift / sealed lineage reservation

BATCH_PROVENANCE_FIELDS = ("batchId", "sourceAuthorityClass", "generationProvider", "generationModelRevision", "promptContractDigest", "generationDate", "consentAuthority", "retentionRule")
PROVIDER_DRIFT_POLICY = {"recordRevisionPerBatch": True, "hideRevisionChange": False, "sealedAcrossRevisions": "report the revision distribution of SEALED_TEST; never silently pool",
                         "repoArtifacts": "aggregate counts per revision only"}
RESERVATION_RULES = {"name": "SEALED_TEST_ELIGIBLE_SOURCE_LINEAGES", "when": "before full corpus generation; recorded in the private manifest before any output exists",
                     "rule": "reserved lineages are FUTURE_HOLDOUT_ELIGIBLE + lineageReservation SEALED_RESERVED; development lineages are DEVELOPMENT_ONLY; no lineage is both",
                     "regeneration": "same lineage regeneration = same group", "selection": "deterministic by sha256(SEED + ':reserve:' + lineageId); no manual override; no model score"}


def validate_batch(batch: Mapping[str, Any]) -> list[str]:
    errors = [f"missing batch provenance field: {f}" for f in BATCH_PROVENANCE_FIELDS if not batch.get(f)]
    if batch.get("sourceAuthorityClass") == "PRODUCTION_USER_SOURCE":
        errors.append("PRODUCTION_USER_SOURCE batches are prohibited")
    if batch.get("sourceAuthorityClass") not in (None, *SOURCE_CATEGORIES):
        errors.append(f"unknown sourceAuthorityClass {batch.get('sourceAuthorityClass')!r}")
    return errors


def revision_distribution(records: Sequence[Mapping[str, Any]], batches: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_batch = {b["batchId"]: b for b in batches}
    overall: Counter = Counter()
    sealed: Counter = Counter()
    unknown = 0
    for r in records:
        b = by_batch.get(r.get("collectionBatch"))
        if b is None:
            unknown += 1
            continue
        key = f"{b.get('generationProvider')}@{b.get('generationModelRevision')}"
        overall[key] += 1
        if r.get("split") == "SEALED_TEST":
            sealed[key] += 1
    return {"overall": dict(overall), "sealedTest": dict(sealed), "recordsWithoutBatch": unknown, "sealedSpansMultipleRevisions": len(sealed) > 1, "policy": PROVIDER_DRIFT_POLICY}


def reserve_sealed_lineages(lineage_ids: Sequence[str], reserved_count: int) -> dict[str, Any]:
    ids = list(lineage_ids)
    for lid in ids:
        if validate_lineage_id(lid):
            raise ValueError(f"invalid lineageId {lid!r}")
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate lineageId")
    if reserved_count < 0 or reserved_count > len(ids):
        raise ValueError("reserved_count must be between 0 and the number of lineages")
    ordered = sorted(ids, key=lambda lid: hashlib.sha256(f"{sc.SEED}:reserve:{lid}".encode("utf-8")).hexdigest())
    reserved = sorted(ordered[:reserved_count])
    development = sorted(ordered[reserved_count:])
    return {"SEALED_TEST_ELIGIBLE_SOURCE_LINEAGES": reserved, "DEVELOPMENT_LINEAGES": development, "reservedLineageReservation": "SEALED_RESERVED", "developmentLineageReservation": "DEVELOPMENT_ONLY",
            "reservedProvenanceClass": "FUTURE_HOLDOUT_ELIGIBLE", "rules": RESERVATION_RULES}


def check_lineage_reuse(lineage_id: str, development_lineages: Sequence[str], reserved_lineages: Sequence[str]) -> list[str]:
    if lineage_id in set(development_lineages) and lineage_id in set(reserved_lineages):
        return [f"lineage {lineage_id} was used for train/dev generation and cannot be a sealed lineage"]
    return []


# ------------------------------------------------------------------ aggregate-only repo artifact


def build_aggregate() -> dict[str, Any]:
    options = {name: size_option(name) for name in PILOT_SIZE_OPTIONS}
    target = ss.min_n_for_lower(0)
    return {"planVersion": cb.PLAN_VERSION, "pilotVersion": PILOT_VERSION, "datasetVersion": sc.VERSION, "contractDigestPrefix": sc.contract_digest()[:12], "splitPlanDigestPrefix": sc.split_plan_digest()[:12],
            "incidenceStatus": INCIDENCE_STATUS, "execution": EXECUTION_STATUS, "paidGeneration": PAID_GENERATION, "imageGeneration": {"azure": 0, "openaiImage": 0}, "modelTraining": 0, "inference": 0,
            "noTraining": sc.NO_TRAINING, "productionAccess": sc.PRODUCTION_ACCESS, "productionUserDataRequired": "NO", "buildsDeploys": 0, "productionWrites": 0, "externalRawImageTransmission": 0,
            "priorStatus": {k: sc.PRIOR_STATUS[k] for k in ("B3_L16A", "STOP_RULE", "NATURAL_POSITIVE", "TEXT_POLICY_GAP", "B3_L17A", "B3_L17A_CORPUS", "B3_L17A_1")},
            "contractVerdict": sc.readiness_verdict(), "trainingSize": ss.TRAINING_SIZE_STATUS,
            "pilot": {"dataStatus": PILOT_DATA_STATUS, "allowedPartitionsLater": list(PILOT_ALLOWED_PARTITIONS), "sealedTestEligible": False, "lineageReservation": PILOT_LINEAGE_RESERVATION,
                      "labelContract": PILOT_LABEL_CONTRACT, "stoppingRule": STOPPING_RULE, "feasibilityFloorPositiveLineagesPerClass": FEASIBILITY_FLOOR_POSITIVE_LINEAGES_PER_CLASS, "assumptions": ASSUMPTIONS,
                      "provider": CANONICAL_PROVIDER, "options": options, "costStatus": COST_STATUS},
            "sourceCategories": SOURCE_CATEGORY_POLICY, "syntheticDomainMarker": SYNTHETIC_DOMAIN_MARKER, "forbiddenDomainClaim": FORBIDDEN_DOMAIN_CLAIM, "lineageDefinition": LINEAGE_DEFINITION,
            "budget": {"targetSealedPositivesPerClass": target, "targetCountKind": sc.EVALUATION_TARGET_COUNT_KIND, "requiredCollectedPositiveGroupsFuturePool": cb.required_collected_positive_groups(target)["minimumCollectedPositiveGroups"],
                       "requiredCollectedPositiveGroupsReservedPool": cb.required_collected_positive_groups(target, "SEALED_RESERVED")["minimumCollectedPositiveGroups"],
                       "withoutIncidence": cb.expected_generation(target, None), "riskTableFuturePool": cb.risk_table(target), "riskTableReservedPool": cb.risk_table(target, pool="SEALED_RESERVED"),
                       "combinedWithoutIncidence": {k: v for k, v in cb.combined_expectation(target, {}).items() if k != "perClass"}, "isExpectationOnly": True, "generationPlanConfirmed": False},
            "sealedQuota": sc.SEALED_QUOTA, "representativeCleanSealedQuota": {"required": sc.SEALED_QUOTA["representativeClean"], "aspirational": sc.SEALED_QUOTA["representativeCleanAspirational"],
                                                                                 "minimumCollection": ss.plan()["minimumCollection"]["clean29"]["minimumCollectedIndependentGroupsRequired"]},
            "hardNegativeStress": {"quota": "none fixed; reported separately as HARD_NEGATIVE_STRESS_FALSE_REVIEW_RATE", "countsTowardRepresentativeClean": False, "status": "STRESS_SET_DEFINED_NOT_COLLECTED"},
            "batchProvenanceFields": list(BATCH_PROVENANCE_FIELDS), "providerDriftPolicy": PROVIDER_DRIFT_POLICY, "reservationRules": RESERVATION_RULES}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="aggregate-only artifact")
    parser.add_argument("--option", choices=sorted(PILOT_SIZE_OPTIONS))
    args = parser.parse_args(argv)
    if args.out:
        args.out.write_text(json.dumps(build_aggregate(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    if args.option:
        print(json.dumps(pilot_plan(args.option), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
