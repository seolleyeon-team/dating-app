"""B3-L17A.1 — build the aggregate-only repository artifact for SUPERVISED_WATERMARK_LOGO_DATASET_V1_1 (no raw manifest, no image, no model).

The V1 artifact (b3-l17a-supervised-data-design-aggregate-v1.json) is a
historical frozen record and is never rebuilt or edited by this script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_supervised_dataset_contract as sc  # noqa: E402
import avatar_supervised_manifest_validate as mv  # noqa: E402
import avatar_supervised_sample_size as ss  # noqa: E402
import avatar_supervised_split_plan as sp  # noqa: E402


def build(example_manifest: Path, natural_groups_by_stratum=None, clean_uncontaminated_groups: int = 0, clean_contaminated_groups: int = 5) -> dict:
    status = sc.corpus_status(natural_groups_by_stratum or {}, clean_uncontaminated_groups)
    ex = json.loads(example_manifest.read_text(encoding="utf-8"))
    exval = mv.validate_manifest(ex)
    plan = ss.plan()
    schema = sc.REGION_SCHEMA
    return {
        "datasetVersion": sc.VERSION, "historicalVersion": sc.VERSION_V1, "marker": sc.MARKER, "correctionMarker": sc.CORRECTION_MARKER, "annotationSchemaVersion": sc.ANNOTATION_SCHEMA_VERSION,
        "contractDigestPrefix": sc.contract_digest()[:12],
        "digests": {"sourcePolicy": sc.source_policy_digest()[:12], "ontology": sc.ontology_digest()[:12], "annotationSchema": sc.schema_digest()[:12], "splitPlan": sc.split_plan_digest()[:12], "labelPolicy": sc.label_policy_digest()[:12]},
        "v1FrozenDigestPrefixes": {k: v[:12] for k, v in sc.V1_FROZEN_DIGESTS.items()}, "v1ArtifactsPreserved": ["b3-l17a-supervised-data-design.md", "b3-l17a-supervised-data-design-aggregate-v1.json", "b3-l17a-supervised-manifest-example.json"],
        "priorVerdictV1": "SUPERVISED_DATA_COLLECTION_CONTRACT_READY", "priorStatus": {k: sc.PRIOR_STATUS[k] for k in ("B3_L15A", "B3_L16A", "B3_L16A_CORRECTION", "STOP_RULE", "NATURAL_POSITIVE", "TEXT_POLICY_GAP", "B3_L17A", "B3_L17A_CORPUS", "B3_L17A_1")},
        "mismatch": sc.MISMATCH_RECORD, "countKinds": list(sc.COUNT_KINDS), "evaluationTargetCountKind": sc.EVALUATION_TARGET_COUNT_KIND,
        "prohibitedInThisPhase": list(sc.PROHIBITED_IN_THIS_PHASE), "noTraining": sc.NO_TRAINING, "modelTraining": 0, "classifierFits": 0, "inference": 0,
        "productionAccess": sc.PRODUCTION_ACCESS, "productionUserDataRequired": "NO (unless separately approved by owner/privacy)", "imageGeneration": {"azure": 0, "openaiImage": 0},
        "paidGenerationRequiredForCollection": "YES (not executed; plan only)", "buildsDeploys": 0, "productionWrites": 0, "externalRawImageTransmission": 0,
        "ontology": list(sc.ONTOLOGY), "ontologyAuthority": sc.ONTOLOGY_AUTHORITY, "policyCollapseAllowed": sc.POLICY_COLLAPSE_ALLOWED, "uncertainPolicy": sc.UNCERTAIN_POLICY,
        "criticalPositiveStrata": list(sc.CRITICAL_POSITIVE_STRATA), "policyPositiveClasses": list(sc.POLICY_POSITIVE_CLASSES), "benignClasses": list(sc.BENIGN_CLASSES), "overlayText": sc.OVERLAY_TEXT_STATUS,
        "cleanCategories": sc.CLEAN_CATEGORY_CONTRACT, "falseReviewMetricNames": sc.FALSE_REVIEW_METRIC_NAMES,
        "statistics": {k: plan[k] for k in ("method", "confidence", "scipyVersion", "clean", "recall", "unit", "pointEstimateAloneIsInsufficient", "countKindOfTheseTargets", "trainingSize")},
        "sealedQuota": sc.SEALED_QUOTA, "minimumCollection": plan["minimumCollection"], "trainingSize": sc.TRAINING_SIZE_STATUS,
        "partitions": list(sc.PARTITIONS), "partitionFractions": sc.PARTITION_FRACTIONS, "splitAlgorithm": sc.SPLIT_ALGORITHM, "v1SplitAlgorithm": sc.V1_SPLIT_ALGORITHM, "remainderTieBreak": list(sp.REMAINDER_TIE_BREAK),
        "splitLabels": list(sc.SPLIT_LABELS), "lineageReservations": list(sc.LINEAGE_RESERVATIONS), "sealedTest": sc.SEALED_TEST_CONTRACT, "validationRole": list(sc.VALIDATION_ROLE),
        "imageLevelAllowed": list(sc.IMAGE_LEVEL_ALLOWED), "optionalManifestFields": list(sc.OPTIONAL_MANIFEST_FIELDS), "forbiddenManifestKeys": list(sc.FORBIDDEN_MANIFEST_KEYS),
        "regionSchema": {"fields": list(schema), "bboxRule": schema["bboxNormalized"], "classEnum": "ontology (unchanged from V1)"},
        "statisticalUnit": sc.STATISTICAL_UNIT, "leakageUnit": sc.LEAKAGE_UNIT,
        "readiness": sc.readiness(), "verdict": sc.readiness_verdict(), "naturalPositiveCorpus": status["naturalPositiveCorpus"], "cleanNegativeCorpus": status["cleanNegativeCorpus"],
        "currentNaturalPositiveIndependentGroups": status["naturalGroupsByStratum"], "currentCleanUncontaminatedIndependentGroups": clean_uncontaminated_groups,
        "currentCleanContaminatedIndependentGroups": clean_contaminated_groups, "sealedEvaluationGapByClass": status["sealedEvaluationGapByClass"], "minimumCollectionByClass": status["minimumCollectionByClass"],
        "collectionGapByClassMinimum": status["collectionGapByClassMinimum"], "sufficiencyBasis": status["sufficiencyBasis"], "collectionPlan": sc.collection_plan(),
        "gaps": {"naturalPositive": "NATURAL_POSITIVE_EVIDENCE_MISSING", "textPolicy": "TEXT_POLICY_GAP unresolved", "graphicalDetector": "GRAPHICAL_DETECTOR_STUDY_REQUIRED", "naturalPositiveIncidence": "unknown (not estimated in this phase)"},
        "exampleManifest": {"file": example_manifest.name, "fixture": ex.get("fixture"), "validatorErrors": len(exval["errors"]), "aggregate": exval["aggregate"]},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.write_text(json.dumps(build(args.example), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
