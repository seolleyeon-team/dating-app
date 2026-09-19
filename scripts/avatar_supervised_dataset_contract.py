"""B3-L17A — SUPERVISED_WATERMARK_LOGO_DATASET_V1 (data-design contract; no model, no training, no inference).

Fixes, before any supervised model is chosen or trained: source policy,
natural-positive definition, label ontology (B3 authority reused), region
annotation schema, blinded dual-rater workflow, leakage group unit, duplicate
policy, deterministic group-disjoint split, sealed-test contract, privacy
schema, third-party license handling, retention/deletion, statistical
sufficiency helper and the legacy contamination classification.

Immutable: B3-L15A EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT, B3-L16A
DINOV2_VERIFIER_FAILED_DEVELOPMENT (provenance-only metadata correction
merged), FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE.  This phase trains
nothing, selects nothing and reads no production data.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import avatar_dinov2_verifier as dv  # noqa: E402
import avatar_supervised_sample_size as ss  # noqa: E402
import avatar_watermark_label_local as ll  # noqa: E402

VERSION = "SUPERVISED_WATERMARK_LOGO_DATASET_V1"
MARKER = "SUPERVISED_WATERMARK_LOGO_DATA_DESIGN"
ANNOTATION_SCHEMA_VERSION = "supervised_watermark_logo_region_schema_v1"
STOP_RULE = dv.STOP_RULE
PRIOR_STATUS = {**dv.PRIOR_STATUS, "B3_L15A": "EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT", "B3_L16A": "DINOV2_VERIFIER_FAILED_DEVELOPMENT",
                "B3_L16A_CORRECTION": "PROVENANCE_ONLY_METADATA_CORRECTION", "STOP_RULE": STOP_RULE, "NATURAL_POSITIVE": "NATURAL_POSITIVE_EVIDENCE_MISSING", "TEXT_POLICY_GAP": "unresolved"}
PROHIBITED_IN_THIS_PHASE = ("SigLIP", "OpenCLIP", "DINOv2-large", "CLIP variant", "RBF SVM", "MLP", "random forest", "boosting", "new threshold grid", "new crop", "new scan", "new zero-shot detector",
                            "model training", "fine-tuning", "linear probe", "classifier fit", "threshold selection", "feature extraction for model selection", "production inference")
NO_TRAINING = {"modelTraining": 0, "fineTuning": 0, "linearProbe": 0, "classifierFit": 0, "thresholdSelection": 0, "featureExtractionForModelSelection": 0, "productionInference": 0}
PRODUCTION_ACCESS = {"firestoreScans": 0, "storageBulkList": 0, "userDataMutation": 0, "userCorpusExport": 0}
TRAINING_SIZE_STATUS = ss.TRAINING_SIZE_STATUS
COLLECTION_EXECUTION = "NOT_EXECUTED_PLAN_ONLY"


class NotFrozen(RuntimeError):
    pass


class SealedAlreadyEvaluated(RuntimeError):
    pass


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ ontology (B3 authority; frozen; no policy collapse)

ONTOLOGY = tuple(ll.PRIMARY_LABELS)
ONTOLOGY_AUTHORITY = ll.LABEL_SCHEMA_VERSION
RELEVANT_CLASSES = tuple(c for c in ONTOLOGY if c not in ("NO_VISIBLE_RELEVANT_TEXT_OR_MARK", "UNCERTAIN"))
POLICY_COLLAPSE_ALLOWED = False          # detector target != product reject policy while TEXT_POLICY_GAP is unresolved
UNCERTAIN_POLICY = "EXCLUDED_FROM_PRIMARY_TRAINING"


def extend_ontology(name: str) -> None:
    raise RuntimeError("ontology is frozen for SUPERVISED_WATERMARK_LOGO_DATASET_V1; a versioned extension must be frozen before labeling starts, never after performance")


# ------------------------------------------------------------------ provenance / natural positive

PROVENANCE_CLASSES = ("LEGACY_DEVELOPMENT_CONTAMINATED", "FUTURE_TRAINING_ELIGIBLE", "FUTURE_HOLDOUT_ELIGIBLE", "RESTRICTED_SOURCE_NOT_MODEL_DATA")
ORIGIN_KINDS = ("NATURAL_GENERATED_OUTPUT", "CONTROLLED_SYNTHETIC_AUGMENTATION", "CONTROLLED_CHALLENGE_EVIDENCE", "SOURCE_PHOTO")
NATURAL_POSITIVE = {
    "definition": "visible text/logo/watermark/mark region that appears in the canonical avatar generation output itself, without any post-hoc synthetic overlay",
    "notCounted": ["B3 injected overlays", "programmatic synthetic marks", "manually pasted logo/text", "challenge derivatives", "synthetic constructs"],
    "notCountedRole": ["CONTROLLED_SYNTHETIC_AUGMENTATION", "CONTROLLED_CHALLENGE_EVIDENCE"],
    "gap": "NATURAL_POSITIVE_EVIDENCE_MISSING until a prospective natural-positive corpus is collected and labelled under this contract",
}
NATURAL_POSITIVE_STRATA = ("BRAND_TEXT_OR_MARK", "OVERLAY_WATERMARK", "GRAPHICAL_LOGO", "GENERATIVE_TEXT_ARTIFACT")
OVERLAY_TEXT_STATUS = "OVERLAY_TEXT held separately (TEXT_POLICY_GAP unresolved)"
BENIGN_HARD_NEGATIVE_KINDS = ("GARMENT_TEXT", "BACKGROUND_SIGNAGE", "benign decorative graphics", "face/skin/hair texture", "jewelry/accessory detail", "clothing seams/patterns")
SYNTHETIC_ROLE = {"allowed": ["training augmentation", "challenge set", "regression set"], "excludedFrom": ["natural-domain validation statistics", "sealed natural holdout statistics", "natural positive counts"]}
LEGACY_SPLIT_STATUS = {"legacy20GeneratedAvatars": "LEGACY_DEVELOPMENT_CONTAMINATED", "allB3Constructs": "LEGACY_DEVELOPMENT_CONTAMINATED", "sealedEvaluationHoldout": "never"}


def is_natural_positive(record: Mapping[str, Any]) -> bool:
    return record.get("originKind") == "NATURAL_GENERATED_OUTPUT" and any(r.get("class") in RELEVANT_CLASSES for r in record.get("regions", []))


def gap_status(natural_positive_groups: int = 0) -> dict[str, Any]:
    return {"naturalPositive": "NATURAL_POSITIVE_EVIDENCE_MISSING", "naturalPositiveIndependentGroupsNow": natural_positive_groups,
            "note": "data design alone never closes the gap; closure requires a labelled prospective natural corpus and a separate evaluation contract"}


def legacy_inventory() -> list[dict[str, Any]]:
    legacy_use = ["TRAIN_DEVELOPMENT augmentation (explicit flag)", "VALIDATION augmentation (explicit flag)", "regression set"]
    return [
        {"source": "generated avatars (20, G1-G5)", "kind": "NATURAL_GENERATED_OUTPUT", "count": 20, "independentGroups": 5, "classification": "LEGACY_DEVELOPMENT_CONTAMINATED",
         "why": "every base was scored by OWLv2/Grounding DINO/Florence/CLIP/DINOv2 across B3-L4..L16A (G4-G5 in B3-L9/B3-L14A holdouts)", "futureUse": legacy_use, "naturalPositives": 0,
         "note": "owner Rater A reference truth: 20/20 no visible graphical mark (18 NO_VISIBLE_RELEVANT_TEXT_OR_MARK, 2 GARMENT_TEXT)"},
        {"source": "source photos (8)", "kind": "SOURCE_PHOTO", "count": 8, "independentGroups": 8, "classification": "RESTRICTED_SOURCE_NOT_MODEL_DATA", "why": "user-uploaded originals; runtime target is generated output; no added identity exposure", "futureUse": []},
        {"source": "B3-L11 constructs (VISUAL_MARK_CHALLENGE_V3)", "kind": "CONTROLLED_CHALLENGE_EVIDENCE", "count": 180, "classification": "LEGACY_DEVELOPMENT_CONTAMINATED", "why": "development derivatives scored by three detectors; HOLDOUT_VARIANT never generated", "futureUse": legacy_use},
        {"source": "B3-L14A constructs (EDGE_MARK_GENERALIZATION_V1)", "kind": "CONTROLLED_CHALLENGE_EVIDENCE", "count": 320, "classification": "LEGACY_DEVELOPMENT_CONTAMINATED", "why": "192 development + 128 consumed holdout derivatives scored by three detectors", "futureUse": legacy_use},
        {"source": "B3-L15A crops/proposals (CLIP)", "kind": "CONTROLLED_CHALLENGE_EVIDENCE", "count": 19607, "classification": "LEGACY_DEVELOPMENT_CONTAMINATED", "why": "proposal crops embedded and OOF-scored", "futureUse": legacy_use},
        {"source": "B3-L16A crops/embeddings (DINOv2)", "kind": "CONTROLLED_CHALLENGE_EVIDENCE", "count": 19607, "classification": "LEGACY_DEVELOPMENT_CONTAMINATED", "why": "same proposal crops embedded and OOF-scored", "futureUse": legacy_use},
        {"source": "B3-L7/L8/L9/L10 OWLv2 + Florence captures", "kind": "CONTROLLED_CHALLENGE_EVIDENCE", "count": 96 + 16, "classification": "LEGACY_DEVELOPMENT_CONTAMINATED", "why": "earlier challenge/holdout captures on the same 20 bases", "futureUse": legacy_use},
        {"source": "human label artifacts (B3-L5/L6 Rater A/B/C)", "kind": "LABEL_ARTIFACT", "count": 20, "classification": "LEGACY_DEVELOPMENT_CONTAMINATED", "why": "pilot truth over the contaminated 20; not inherited by the new label authority", "futureUse": ["reference for ontology continuity only"]},
    ]


def classify_legacy(kind: str) -> str:
    return "RESTRICTED_SOURCE_NOT_MODEL_DATA" if kind == "SOURCE_PHOTO" else "LEGACY_DEVELOPMENT_CONTAMINATED"


# ------------------------------------------------------------------ source policy / third party

SOURCE_POLICY = {
    "runtimeTarget": "generated avatar output",
    "preferredSource": "owner-authorized first-party generated avatar outputs",
    "conditions": ["explicit QA/data-use authority", "generated output only", "source photo never copied into the dataset", "private local storage", "stable opaque dataset id", "retention policy", "deletion policy", "provenance record"],
    "sourcePhotosCopiedIntoDataset": False,
    "productionUserImages": "prohibited without separate owner/privacy approval",
    "productionMining": "prohibited: no Firestore bulk export, no production bucket crawl, no UID-based corpus, no consent-less production image use",
    "webScraping": "prohibited",
    "thirdParty": "optional training augmentation only, per-dataset license audit, never a substitute for the first-party natural holdout",
}
SOURCE_AUTHORITIES = ("OWNER_AUTHORIZED_FIRST_PARTY", "THIRD_PARTY_AUDITED", "PRODUCTION_USER")
THIRD_PARTY_REQUIRED_FIELDS = ("name", "sourceUrl", "exactVersion", "license", "commercialProductUseCompatible", "redistributionRestrictions", "imageCopyrightStatus", "annotationLicense", "downloadTerms")
AMBIGUOUS_LICENSE = frozenset({"", "unknown", "ambiguous", "none", "n/a", "tbd"})


def production_mining_allowed() -> bool:
    return False


def check_source(record: Mapping[str, Any]) -> list[str]:
    errors = []
    if record.get("originKind") == "SOURCE_PHOTO":
        errors.append("RESTRICTED_SOURCE_NOT_MODEL_DATA: source photos are never model data")
        if record.get("provenanceClass") != "RESTRICTED_SOURCE_NOT_MODEL_DATA":
            errors.append("source photo cannot carry a training/holdout provenance class")
        return errors
    authority = record.get("sourceAuthority")
    if authority == "PRODUCTION_USER" or str(record.get("collectionBatch", "")).lower().startswith("prod"):
        if record.get("ownerPrivacyApproval") is not True:
            errors.append("production user images prohibited without separate owner/privacy approval")
    if authority is not None and authority not in SOURCE_AUTHORITIES:
        errors.append(f"unknown sourceAuthority: {authority}")
    return errors


def audit_third_party(meta: Mapping[str, Any]) -> dict[str, Any]:
    missing = [f for f in THIRD_PARTY_REQUIRED_FIELDS if f not in meta or meta[f] in (None, "")]
    license_ok = str(meta.get("license", "")).strip().lower() not in AMBIGUOUS_LICENSE
    commercial_ok = meta.get("commercialProductUseCompatible") is True
    status = "ELIGIBLE_AUGMENTATION_ONLY" if not missing and license_ok and commercial_ok else "LICENSE_REVIEW_REQUIRED"
    return {"status": status, "missingFields": missing, "licenseAmbiguous": not license_ok, "commercialUseUnconfirmed": not commercial_ok, "holdoutEligible": False, "replacesNaturalHoldout": False,
            "role": "optional training augmentation only"}


# ------------------------------------------------------------------ region / image schema

REGION_SCHEMA = {
    "regionId": "opaque string", "class": list(ONTOLOGY), "bboxNormalized": "[xmin, ymin, xmax, ymax] in [0, 1], xmin < xmax, ymin < ymax",
    "visibility": ["clear", "faint"], "sceneRelation": ["overlay", "garment", "background", "integrated", "unknown"], "legibility": ["legible", "partial", "illegible", "not_applicable"],
    "raterConfidence": ["high", "medium", "low"], "annotationStatus": ["agreed", "adjudicated", "uncertain"],
}
TRANSCRIPTION_POLICY = {"default": "not stored", "requiresNewHypothesis": True, "why": "minimise collection of personal / trademark strings; OCR text is not a training target under this contract"}
IMAGE_LEVEL_ALLOWED = ("hasRelevantRegion", "regionCount", "classSet", "uncertainPresent", "sourceProvenanceClass", "splitGroupId")
PRIVATE_MANIFEST_FIELDS = ("opaqueImageId", "groupId", "provenanceClass", "originKind", "collectionBatch", "annotationVersion", "sha256", "perceptualHash", "width", "height", "regions", "split")
OPTIONAL_MANIFEST_FIELDS = ("sourceAuthority", "ownerPrivacyApproval", "thirdPartyDataset") + IMAGE_LEVEL_ALLOWED
FORBIDDEN_MANIFEST_KEYS = ("uid", "userId", "email", "sourcePhotoPath", "path", "filename", "fileName", "userFacingFilename", "displayName", "phone", "identity", "sourcePhotoId")
PARTITIONS = ("TRAIN_DEVELOPMENT", "VALIDATION", "SEALED_TEST")
PARTITION_FRACTIONS = {"TRAIN_DEVELOPMENT": 0.6, "VALIDATION": 0.2, "SEALED_TEST": 0.2}
SEED = VERSION
SPLIT_ALGORITHM = "per (stratum, provenance pool): order groups by sha256(SEED + groupId); assign the i-th of n to the partition whose cumulative fraction covers (i + 0.5) / n; legacy pool excludes SEALED_TEST with renormalised fractions; no manual override"


def allowed_partitions(provenance_class: str) -> tuple:
    if provenance_class == "LEGACY_DEVELOPMENT_CONTAMINATED":
        return ("TRAIN_DEVELOPMENT", "VALIDATION")
    if provenance_class in ("FUTURE_TRAINING_ELIGIBLE", "FUTURE_HOLDOUT_ELIGIBLE"):
        return PARTITIONS
    return ()


def validate_group_id(group_id: Any) -> list[str]:
    if not isinstance(group_id, str) or not re.fullmatch(r"grp-[0-9a-z]+", group_id):
        return ["groupId must be opaque (grp-<hex/alnum>); identity-like ids are forbidden"]
    return []


def validate_region(region: Mapping[str, Any], allow_transcription: bool = False) -> list[str]:
    errors = []
    cls = region.get("class")
    if cls not in ONTOLOGY:
        errors.append(f"class not in ontology: {cls}")
    box = region.get("bboxNormalized")
    if not (isinstance(box, (list, tuple)) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)):
        errors.append("bbox must be [xmin, ymin, xmax, ymax]")
    else:
        x0, y0, x1, y1 = box
        if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
            errors.append("bbox must be normalized to [0, 1] with xmin < xmax and ymin < ymax")
    for field in ("visibility", "sceneRelation", "legibility", "raterConfidence", "annotationStatus"):
        if region.get(field) not in REGION_SCHEMA[field]:
            errors.append(f"{field} not in {REGION_SCHEMA[field]}")
    if not isinstance(region.get("regionId"), str) or not region.get("regionId"):
        errors.append("regionId required")
    if "transcription" in region and not allow_transcription:
        errors.append("transcription stored by default is not allowed (TRANSCRIPTION_POLICY: requires a new pre-registered hypothesis)")
    unknown = set(region) - set(REGION_SCHEMA) - {"transcription"}
    if unknown:
        errors.append(f"unknown region fields: {sorted(unknown)}")
    return errors


def validate_image_record(record: Mapping[str, Any], allow_transcription: bool = False) -> list[str]:
    errors = [f"forbidden key: {k}" for k in record if k in FORBIDDEN_MANIFEST_KEYS]
    for k in PRIVATE_MANIFEST_FIELDS:
        if k not in record:
            errors.append(f"missing field: {k}")
    unknown = set(record) - set(PRIVATE_MANIFEST_FIELDS) - set(OPTIONAL_MANIFEST_FIELDS) - set(FORBIDDEN_MANIFEST_KEYS)
    if unknown:
        errors.append(f"unknown fields: {sorted(unknown)}")
    if errors:
        return errors
    errors += validate_group_id(record["groupId"])
    if record["provenanceClass"] not in PROVENANCE_CLASSES:
        errors.append(f"provenanceClass not in {PROVENANCE_CLASSES}")
    if record["originKind"] not in ORIGIN_KINDS:
        errors.append(f"originKind not in {ORIGIN_KINDS}")
    if record["annotationVersion"] != ANNOTATION_SCHEMA_VERSION:
        errors.append("annotationVersion mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", str(record["sha256"])):
        errors.append("sha256 must be 64 hex chars")
    if not re.fullmatch(r"[0-9a-f]{16}", str(record["perceptualHash"])):
        errors.append("perceptualHash must be 16 hex chars (64-bit pHash)")
    if not (isinstance(record["width"], int) and isinstance(record["height"], int) and record["width"] > 0 and record["height"] > 0):
        errors.append("width/height must be positive integers")
    split = record["split"]
    if split not in PARTITIONS:
        errors.append(f"split not in {PARTITIONS}")
    elif split not in allowed_partitions(record["provenanceClass"]):
        errors.append(f"{record['provenanceClass']} cannot be assigned to {split}")
    regions = record["regions"]
    if not isinstance(regions, list):
        errors.append("regions must be a list")
        regions = []
    for r in regions:
        errors += [f"region {r.get('regionId')}: {e}" for e in validate_region(r, allow_transcription)]
    if len({r.get("regionId") for r in regions}) != len(regions):
        errors.append("duplicate regionId")
    derived = {"hasRelevantRegion": any(r.get("class") in RELEVANT_CLASSES for r in regions), "regionCount": len(regions), "classSet": sorted({r.get("class") for r in regions}),
               "uncertainPresent": any(r.get("class") == "UNCERTAIN" or r.get("annotationStatus") == "uncertain" for r in regions), "sourceProvenanceClass": record["provenanceClass"], "splitGroupId": record["groupId"]}
    for k, v in derived.items():
        if k in record and record[k] != v:
            errors.append(f"image-level field {k} inconsistent with regions")
    errors += check_source(record)
    return errors


def primary_training_eligible(record: Mapping[str, Any]) -> bool:
    if record.get("provenanceClass") not in ("LEGACY_DEVELOPMENT_CONTAMINATED", "FUTURE_TRAINING_ELIGIBLE", "FUTURE_HOLDOUT_ELIGIBLE"):
        return False
    return not any(r.get("class") == "UNCERTAIN" or r.get("annotationStatus") == "uncertain" for r in record.get("regions", []))


# ------------------------------------------------------------------ label authority / blinding / agreement

LABEL_AUTHORITY = {"raters": ["RATER_A", "RATER_B"], "independent": True, "inheritsB3PilotTruth": False, "adjudicator": "owner-designated adjudicator or a pre-registered third rater",
                   "noAdjudicatorOutcome": "UNCERTAIN", "singleRaterMarker": "SINGLE_RATER_DATASET_LIMITATION", "singleRaterProductionValidation": False}
BLINDING_FORBIDDEN = ("clipScore", "dinov2Score", "groundingDinoBox", "florenceResult", "owlv2Result", "modelPrediction", "thresholdResult", "priorB3PassFail", "detectorScore", "verifierScore", "proposalBox")
AGREEMENT_METRICS = ("image_level_agreement", "region_class_agreement", "region_localization_agreement")
LOCALIZATION_AGREEMENT_IOU = 0.5
KAPPA_ROLE = "descriptive only; never proof of label correctness"


def resolve_disagreement(label_a: str, label_b: str, adjudication: Optional[str]) -> tuple[str, str]:
    if label_a == label_b:
        return label_a, "agreed"
    if adjudication:
        return adjudication, "adjudicated"
    return "UNCERTAIN", "uncertain"


def authority_status(rater_count: int) -> str:
    return "DUAL_RATER_INDEPENDENT" if rater_count >= 2 else "SINGLE_RATER_DATASET_LIMITATION"


def production_validation_allowed(status: str) -> bool:
    return status == "DUAL_RATER_INDEPENDENT" and False   # never from this design phase; production validation is a separate contract


def label_template(opaque_image_id: str) -> dict[str, Any]:
    return {"labelSchema": ANNOTATION_SCHEMA_VERSION, "datasetVersion": VERSION, "opaqueImageId": opaque_image_id, "raterId": None, "blinded": True,
            "imageLevel": {"hasRelevantRegion": None, "uncertainPresent": None},
            "regions": [{"regionId": "", "class": None, "bboxNormalized": [None, None, None, None], "visibility": None, "sceneRelation": None, "legibility": None, "raterConfidence": None, "annotationStatus": None}],
            "instructions": "label only what is visible in the generated image; classes: " + ", ".join(ONTOLOGY)}


def check_template_blind(template: Mapping[str, Any]) -> list[str]:
    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)
    out = []
    for k in keys(template):
        lowered = str(k).lower()
        if k in BLINDING_FORBIDDEN or any(t in lowered for t in ("score", "prediction", "threshold", "passfail")):
            out.append(f"forbidden rater-visible field: {k}")
    return out


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    if len(a) != len(b) or not a:
        raise ValueError("equal-length non-empty sequences required")
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    cats = set(a) | set(b)
    pe = sum((sum(1 for x in a if x == c) / n) * (sum(1 for y in b if y == c) / n) for c in cats)
    return 1.0 if pe == 1.0 else round((po - pe) / (1 - pe), 6)


def image_level_agreement(a: Sequence[bool], b: Sequence[bool]) -> float:
    return sum(1 for x, y in zip(a, b) if x == y) / len(a)


def _iou(p, q) -> float:
    left, top, right, bottom = max(p[0], q[0]), max(p[1], q[1]), min(p[2], q[2]), min(p[3], q[3])
    inter = max(0.0, right - left) * max(0.0, bottom - top)
    union = (p[2] - p[0]) * (p[3] - p[1]) + (q[2] - q[0]) * (q[3] - q[1]) - inter
    return inter / union if union > 0 else 0.0


def region_localization_agreement(regions_a: Sequence[Mapping[str, Any]], regions_b: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    matched = sum(1 for r in regions_a if any(_iou(r["bboxNormalized"], s["bboxNormalized"]) >= LOCALIZATION_AGREEMENT_IOU for s in regions_b))
    class_matched = sum(1 for r in regions_a if any(_iou(r["bboxNormalized"], s["bboxNormalized"]) >= LOCALIZATION_AGREEMENT_IOU and r["class"] == s["class"] for s in regions_b))
    return {"regionsA": len(regions_a), "regionsB": len(regions_b), "localized": matched, "localizedSameClass": class_matched, "iouThreshold": LOCALIZATION_AGREEMENT_IOU}


# ------------------------------------------------------------------ leakage unit / duplicates

LEAKAGE_UNIT = "group (same underlying identity / source lineage: regenerations, variants, near duplicates)"
DUPLICATE_POLICY = {"exact": "SHA-256 of the image bytes", "perceptualHash": "64-bit DCT pHash (32x32 grayscale, top-left 8x8 DCT, median)", "hammingThreshold": 10,
                    "action": "collapse into one group before the split", "modelScoresUsed": False, "thresholdFrozenBeforeData": True}


def phash(image) -> str:
    import numpy as np

    g = np.asarray(image.convert("L").resize((32, 32), 3), dtype=float)   # 3 = bicubic
    n = 32
    k = np.arange(n)
    c = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n)) * math.sqrt(2 / n)
    c[0, :] = c[0, :] / math.sqrt(2)
    d = c @ g @ c.T
    low = d[:8, :8].flatten()
    med = float(np.median(low))
    bits = 0
    for v in low:
        bits = (bits << 1) | (1 if v > med else 0)
    return f"{bits:016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def collapse_duplicates(records: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """opaqueImageId -> canonical groupId after merging exact and near duplicates (union-find). No score input exists."""

    parent: dict[str, str] = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for r in records:
        find(r["groupId"])
    for i, a in enumerate(records):
        for b in records[i + 1:]:
            if a["sha256"] == b["sha256"] or hamming(a["perceptualHash"], b["perceptualHash"]) <= DUPLICATE_POLICY["hammingThreshold"]:
                union(a["groupId"], b["groupId"])
    return {r["opaqueImageId"]: find(r["groupId"]) for r in records}


# ------------------------------------------------------------------ sealed test contract

SEALED_TEST_PREREQUISITES = ("supervised_dataset_v1_manifest_frozen.json", "supervised_model_architecture_frozen.json", "supervised_training_recipe_frozen.json", "supervised_threshold_frozen.json")
SEALED_TEST_LOCK_NAME = "supervised_dataset_v1_sealed_test.lock"
SEALED_TEST_CONTRACT = {"partition": "SEALED_TEST", "browsing": "minimised; no performance evaluation before the prerequisites", "prerequisites": list(SEALED_TEST_PREREQUISITES),
                        "evaluations": "exactly one behind the lock; second evaluation fails closed", "legacyData": "never"}


def sealed_test_guard(private_dir: Path) -> Path:
    p = Path(private_dir)
    missing = [name for name in SEALED_TEST_PREREQUISITES if not (p / name).exists()]
    if missing:
        raise NotFrozen(f"sealed test evaluation requires frozen prerequisites: {missing}")
    lock = p / SEALED_TEST_LOCK_NAME
    if lock.exists():
        raise SealedAlreadyEvaluated("sealed test already evaluated once")
    return lock


def mark_sealed_evaluated(lock: Path, digest: str) -> None:
    lock.write_text(json.dumps({"datasetVersion": VERSION, "digest": digest, "evaluatedAt": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")


# ------------------------------------------------------------------ statistical unit / collection plan / retention / readiness

STATISTICAL_UNIT = "independent image/group, never crop or region count"


def count_units(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return {"images": len(records), "groups": len({r["groupId"] for r in records}), "regions": sum(len(r.get("regions", [])) for r in records)}


def family_recall_denominator(records: Sequence[Mapping[str, Any]], cls: str) -> int:
    return len({r["groupId"] for r in records if any(g.get("class") == cls for g in r.get("regions", []))})


def collection_plan() -> dict[str, Any]:
    p = ss.plan()
    return {"executed": False, "execution": COLLECTION_EXECUTION, "naturalPositiveStrata": list(NATURAL_POSITIVE_STRATA), "overlayTextSeparate": OVERLAY_TEXT_STATUS,
            "perStratumIndependentGroupsForEvaluation": {"zeroMiss": p["recall"]["minIndependentPositivesFor0Misses"], "oneMiss": p["recall"]["minIndependentPositivesFor1Miss"]},
            "cleanIndependentGroupsForEvaluation": {"zeroFalseReview": p["clean"]["minIndependentCleanFor0FalseReviews"], "zeroFalseReviewAt5pct": p["clean"]["minIndependentCleanFor0FalseReviewsAt5pct"]},
            "benignHardNegativeKinds": list(BENIGN_HARD_NEGATIVE_KINDS), "hardNegativeMining": "separate phase after training; never in this contract",
            "source": SOURCE_POLICY["preferredSource"], "paidGenerationRequired": "YES (new first-party generated outputs; not executed; count/cost/privacy plan only)",
            "productionUserDataRequired": "NO (unless separately approved by owner/privacy)", "syntheticCountedAsNatural": False}


RETENTION = {
    "FIRST_PARTY_GENERATED_OUTPUT": {"retentionPeriod": "duration of the supervised research programme, reviewed every 90 days", "deletionTrigger": "owner instruction or programme end",
                                     "consentWithdrawal": "delete the image, its regions and split entry; regenerate manifest digest", "derivedAnnotationDeletion": "with the image", "splitManifestCleanup": "entry removed; split re-verified group-disjoint"},
    "LEGACY_DEVELOPMENT_CONTAMINATED": {"retentionPeriod": "as the G004 authorization (28 originals: never deleted by the agent)", "deletionTrigger": "owner instruction only",
                                        "consentWithdrawal": "as G004", "derivedAnnotationDeletion": "derivatives/embeddings deletable on owner instruction", "splitManifestCleanup": "legacy entries removable without affecting SEALED_TEST"},
    "THIRD_PARTY_AUGMENTATION": {"retentionPeriod": "per dataset license", "deletionTrigger": "license change or LICENSE_REVIEW_REQUIRED", "consentWithdrawal": "not applicable (license governs)",
                                 "derivedAnnotationDeletion": "with the dataset", "splitManifestCleanup": "training/validation entries only (never sealed)"},
    "SOURCE_PHOTO": {"retentionPeriod": "not in dataset", "deletionTrigger": "not applicable", "consentWithdrawal": "governed by the product's account/consent flows", "derivedAnnotationDeletion": "none exist", "splitManifestCleanup": "none exist"},
    "PRODUCTION_USER_IMAGE": {"used": False, "note": "production user images are not used in SUPERVISED_WATERMARK_LOGO_DATASET_V1"},
}
READINESS_CHECKLIST = ("sourcePolicy", "naturalPositiveDefinition", "labelOntology", "regionSchema", "blindedLabelWorkflow", "leakageGroup", "splitAlgorithm", "sealedHoldoutContract",
                       "duplicateHandling", "privacyContract", "licenseHandling", "statisticalSufficiencyHelper", "legacyContaminationClassification")


def readiness() -> dict[str, Any]:
    out = {k: True for k in READINESS_CHECKLIST}
    out["allComplete"] = all(out.values())
    return out


def readiness_verdict() -> str:
    return "SUPERVISED_DATA_COLLECTION_CONTRACT_READY" if readiness()["allComplete"] else "SUPERVISED_DATA_COLLECTION_CONTRACT_INCOMPLETE"


def corpus_status(natural_groups_by_stratum: Mapping[str, int], clean_uncontaminated_groups: int) -> dict[str, Any]:
    p = ss.plan()
    need_pos = p["recall"]["minIndependentPositivesFor0Misses"]
    need_clean = p["clean"]["minIndependentCleanFor0FalseReviews"]
    pos_ok = all(natural_groups_by_stratum.get(s, 0) >= need_pos for s in NATURAL_POSITIVE_STRATA)
    return {"naturalPositiveCorpus": "NATURAL_POSITIVE_CORPUS_SUFFICIENT" if pos_ok else "NATURAL_POSITIVE_CORPUS_INSUFFICIENT",
            "cleanNegativeCorpus": "CLEAN_NEGATIVE_CORPUS_SUFFICIENT" if clean_uncontaminated_groups >= need_clean else "CLEAN_NEGATIVE_CORPUS_INSUFFICIENT",
            "requiredPerStratum": need_pos, "requiredClean": need_clean, "naturalGroupsByStratum": {s: natural_groups_by_stratum.get(s, 0) for s in NATURAL_POSITIVE_STRATA},
            "cleanUncontaminatedGroups": clean_uncontaminated_groups,
            "collectionGapByClass": {s: max(0, need_pos - natural_groups_by_stratum.get(s, 0)) for s in NATURAL_POSITIVE_STRATA} | {"CLEAN": max(0, need_clean - clean_uncontaminated_groups)}}


# ------------------------------------------------------------------ digests


def source_policy_digest() -> str:
    return _digest({"sourcePolicy": SOURCE_POLICY, "thirdPartyRequiredFields": list(THIRD_PARTY_REQUIRED_FIELDS), "retention": RETENTION, "authorities": list(SOURCE_AUTHORITIES), "productionAccess": PRODUCTION_ACCESS})


def ontology_digest() -> str:
    return _digest({"ontology": list(ONTOLOGY), "authority": ONTOLOGY_AUTHORITY, "policyCollapseAllowed": POLICY_COLLAPSE_ALLOWED, "uncertainPolicy": UNCERTAIN_POLICY, "naturalPositive": NATURAL_POSITIVE})


def schema_digest() -> str:
    return _digest({"annotationSchemaVersion": ANNOTATION_SCHEMA_VERSION, "region": REGION_SCHEMA, "imageLevelAllowed": list(IMAGE_LEVEL_ALLOWED), "privateFields": list(PRIVATE_MANIFEST_FIELDS),
                    "optionalFields": list(OPTIONAL_MANIFEST_FIELDS), "forbidden": list(FORBIDDEN_MANIFEST_KEYS), "transcription": TRANSCRIPTION_POLICY})


def split_plan_digest() -> str:
    return _digest({"partitions": list(PARTITIONS), "fractions": PARTITION_FRACTIONS, "seed": SEED, "algorithm": SPLIT_ALGORITHM, "leakageUnit": LEAKAGE_UNIT, "duplicatePolicy": DUPLICATE_POLICY,
                    "legacy": LEGACY_SPLIT_STATUS, "sealedTest": SEALED_TEST_CONTRACT})


def label_policy_digest() -> str:
    return _digest({"authority": LABEL_AUTHORITY, "blindingForbidden": list(BLINDING_FORBIDDEN), "agreementMetrics": list(AGREEMENT_METRICS), "localizationIou": LOCALIZATION_AGREEMENT_IOU,
                    "kappaRole": KAPPA_ROLE, "statisticalUnit": STATISTICAL_UNIT, "syntheticRole": SYNTHETIC_ROLE})


def contract_digest() -> str:
    return _digest({"version": VERSION, "marker": MARKER, "sourcePolicy": source_policy_digest(), "ontology": ontology_digest(), "schema": schema_digest(), "splitPlan": split_plan_digest(),
                    "labelPolicy": label_policy_digest(), "statistics": {"method": ss.METHOD, "confidence": ss.CONFIDENCE, "cleanTarget": ss.CLEAN_GATE_TARGET, "aspirational": ss.CLEAN_ASPIRATIONAL_TARGET, "recallTarget": ss.RECALL_TARGET},
                    "noTraining": NO_TRAINING, "prohibited": list(PROHIBITED_IN_THIS_PHASE), "readiness": list(READINESS_CHECKLIST), "priorStatus": {k: PRIOR_STATUS[k] for k in ("B3_L15A", "B3_L16A", "STOP_RULE")}})
