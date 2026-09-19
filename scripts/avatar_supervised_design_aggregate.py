"""B3-L17A — build the aggregate-only repository artifact for SUPERVISED_WATERMARK_LOGO_DATASET_V1 (no raw manifest, no image, no model)."""

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


def build(example_manifest: Path, natural_groups_by_stratum=None, clean_uncontaminated_groups: int = 0, clean_contaminated_groups: int = 5) -> dict:
    status = sc.corpus_status(natural_groups_by_stratum or {}, clean_uncontaminated_groups)
    ex = json.loads(example_manifest.read_text(encoding="utf-8"))
    exval = mv.validate_manifest(ex)
    schema = sc.REGION_SCHEMA
    return {
        "datasetVersion": sc.VERSION, "marker": sc.MARKER, "annotationSchemaVersion": sc.ANNOTATION_SCHEMA_VERSION, "contractDigestPrefix": sc.contract_digest()[:12],
        "digests": {"sourcePolicy": sc.source_policy_digest()[:12], "ontology": sc.ontology_digest()[:12], "annotationSchema": sc.schema_digest()[:12], "splitPlan": sc.split_plan_digest()[:12], "labelPolicy": sc.label_policy_digest()[:12]},
        "priorStatus": {k: sc.PRIOR_STATUS[k] for k in ("B3_L13", "B3_L14A", "B3_L15A", "B3_L16A", "B3_L16A_CORRECTION", "STOP_RULE", "NATURAL_POSITIVE", "TEXT_POLICY_GAP")},
        "prohibitedInThisPhase": list(sc.PROHIBITED_IN_THIS_PHASE), "noTraining": sc.NO_TRAINING, "modelTraining": 0, "classifierFits": 0, "inference": 0,
        "productionAccess": sc.PRODUCTION_ACCESS, "productionUserDataRequired": "NO (unless separately approved by owner/privacy)", "imageGeneration": {"azure": 0, "openaiImage": 0},
        "paidGenerationRequiredForCollection": "YES (not executed; plan only)", "buildsDeploys": 0, "productionWrites": 0, "externalRawImageTransmission": 0,
        "ontology": list(sc.ONTOLOGY), "ontologyAuthority": sc.ONTOLOGY_AUTHORITY, "policyCollapseAllowed": sc.POLICY_COLLAPSE_ALLOWED, "uncertainPolicy": sc.UNCERTAIN_POLICY,
        "naturalPositive": sc.NATURAL_POSITIVE, "naturalPositiveStrata": list(sc.NATURAL_POSITIVE_STRATA), "overlayText": sc.OVERLAY_TEXT_STATUS,
        "sourcePolicy": sc.SOURCE_POLICY, "thirdPartyRequiredFields": list(sc.THIRD_PARTY_REQUIRED_FIELDS), "thirdPartyAmbiguousLicenseStatus": "LICENSE_REVIEW_REQUIRED",
        "legacyInventory": sc.legacy_inventory(),
        "futureTrainingEligibleSources": ["owner-authorized first-party generated outputs (prospective)", "legacy 20 avatars + B3 constructs as explicitly flagged augmentation only", "third-party datasets passing the license audit (augmentation only)"],
        "futureHoldoutEligibleSources": ["prospective owner-authorized first-party generated outputs never scored by any B3 model"],
        "sourcePhotos": "RESTRICTED_SOURCE_NOT_MODEL_DATA (8)", "legacySplitStatus": sc.LEGACY_SPLIT_STATUS,
        "regionSchema": {"fields": list(schema), "bboxRule": schema["bboxNormalized"], "enums": {k: schema[k] for k in ("visibility", "sceneRelation", "legibility", "raterConfidence", "annotationStatus")}, "classEnum": "ontology"},
        "imageLevelAllowed": list(sc.IMAGE_LEVEL_ALLOWED), "forbiddenManifestKeys": list(sc.FORBIDDEN_MANIFEST_KEYS), "privateManifestFields": list(sc.PRIVATE_MANIFEST_FIELDS), "transcriptionPolicy": sc.TRANSCRIPTION_POLICY,
        "labelAuthority": sc.LABEL_AUTHORITY, "blindingForbidden": list(sc.BLINDING_FORBIDDEN), "agreementMetrics": list(sc.AGREEMENT_METRICS), "localizationAgreementIou": sc.LOCALIZATION_AGREEMENT_IOU, "kappaRole": sc.KAPPA_ROLE,
        "leakageUnit": sc.LEAKAGE_UNIT,
        "duplicatePolicy": {"exactMethod": sc.DUPLICATE_POLICY["exact"], "perceptualHashMethod": sc.DUPLICATE_POLICY["perceptualHash"], "hammingThreshold": sc.DUPLICATE_POLICY["hammingThreshold"],
                            "action": sc.DUPLICATE_POLICY["action"], "modelScoresUsed": sc.DUPLICATE_POLICY["modelScoresUsed"], "thresholdFrozenBeforeData": sc.DUPLICATE_POLICY["thresholdFrozenBeforeData"]},
        "partitions": list(sc.PARTITIONS), "partitionFractions": sc.PARTITION_FRACTIONS, "splitAlgorithm": sc.SPLIT_ALGORITHM, "sealedTest": sc.SEALED_TEST_CONTRACT,
        "statisticalUnit": sc.STATISTICAL_UNIT, "statistics": ss.plan(), "trainingSize": sc.TRAINING_SIZE_STATUS, "syntheticRole": sc.SYNTHETIC_ROLE, "retention": sc.RETENTION,
        "readiness": sc.readiness(), "verdict": sc.readiness_verdict(), "naturalPositiveCorpus": status["naturalPositiveCorpus"], "cleanNegativeCorpus": status["cleanNegativeCorpus"],
        "currentNaturalPositiveIndependentGroups": status["naturalGroupsByStratum"], "currentCleanUncontaminatedIndependentGroups": clean_uncontaminated_groups,
        "currentCleanContaminatedIndependentGroups": clean_contaminated_groups, "collectionGapByClass": status["collectionGapByClass"], "collectionPlan": sc.collection_plan(),
        "gaps": {"naturalPositive": "NATURAL_POSITIVE_EVIDENCE_MISSING", "textPolicy": "TEXT_POLICY_GAP unresolved", "graphicalDetector": "GRAPHICAL_DETECTOR_STUDY_REQUIRED"},
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
