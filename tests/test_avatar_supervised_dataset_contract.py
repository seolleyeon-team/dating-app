"""CI tests for B3-L17A SUPERVISED_WATERMARK_LOGO_DATASET_V1 (data design only). Pure logic: no model, no user image, no label."""

import hashlib
import inspect
import json
import re
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
AI = REPO / "lib" / "ai_recommend_model"
if str(AI) not in sys.path:
    sys.path.insert(0, str(AI))

import avatar_dinov2_verifier as dv  # noqa: E402
import avatar_supervised_dataset_contract as sc  # noqa: E402
import avatar_supervised_manifest_validate as mv  # noqa: E402
import avatar_supervised_sample_size as ss  # noqa: E402
import avatar_supervised_split_plan as sp  # noqa: E402
import avatar_watermark_label_local as ll  # noqa: E402

DOCS = REPO / "docs" / "avatar-production"
DESIGN = DOCS / "b3-l17a-supervised-data-design.md"
AGGREGATE = DOCS / "b3-l17a-supervised-data-design-aggregate-v1.json"
EXAMPLE = DOCS / "b3-l17a-supervised-manifest-example.json"


def _region(**over):
    base = {"regionId": "r1", "class": "GRAPHICAL_LOGO", "bboxNormalized": [0.1, 0.1, 0.3, 0.3], "visibility": "clear", "sceneRelation": "overlay", "legibility": "not_applicable",
            "raterConfidence": "high", "annotationStatus": "agreed"}
    base.update(over)
    return base


def _image(oid="img-0001", gid="grp-0001", prov="FUTURE_TRAINING_ELIGIBLE", origin="NATURAL_GENERATED_OUTPUT", regions=None, split="TRAIN_DEVELOPMENT", **over):
    rec = {"opaqueImageId": oid, "groupId": gid, "provenanceClass": prov, "originKind": origin, "collectionBatch": "batch-0001", "annotationVersion": sc.ANNOTATION_SCHEMA_VERSION,
           "sha256": hashlib.sha256(oid.encode()).hexdigest(), "perceptualHash": "0" * 16, "width": 1024, "height": 1024, "regions": regions if regions is not None else [], "split": split,
           "hasRelevantRegion": bool(regions), "regionCount": len(regions or []), "classSet": sorted({r["class"] for r in (regions or [])}), "uncertainPresent": any(r["class"] == "UNCERTAIN" for r in (regions or [])),
           "sourceProvenanceClass": prov, "splitGroupId": gid}
    rec.update(over)
    return rec


# ------------------------------------------------------------ 1-3 immutability / stop rule


def test_b3l16a_metadata_correction_detected():
    a = json.loads((DOCS / "b3-l16a-dinov2-verifier-aggregate-v1.json").read_text(encoding="utf-8"))
    assert a["classifier"]["input"] == "L2-normalized DINOv2 pooler_output image embedding" and a["provenanceCorrection"]["marker"] == "PROVENANCE_ONLY_METADATA_CORRECTION"
    assert sc.PRIOR_STATUS["B3_L16A_CORRECTION"] == "PROVENANCE_ONLY_METADATA_CORRECTION"


def test_correction_does_not_change_verdict():
    a = json.loads((DOCS / "b3-l16a-dinov2-verifier-aggregate-v1.json").read_text(encoding="utf-8"))
    assert a["verdict"] == "DINOV2_VERIFIER_FAILED_DEVELOPMENT" and a["contractDigestPrefix"] == dv.contract_digest()[:12] == "b6a22d71eb0e"
    assert sc.PRIOR_STATUS["B3_L16A"] == "DINOV2_VERIFIER_FAILED_DEVELOPMENT" and sc.PRIOR_STATUS["B3_L15A"] == "EDGE_SCAN_VERIFIER_FAILED_DEVELOPMENT"


def test_stop_rule_immutable():
    assert sc.STOP_RULE == dv.STOP_RULE == "FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE" and sc.MARKER == "SUPERVISED_WATERMARK_LOGO_DATA_DESIGN"
    assert set(sc.PROHIBITED_IN_THIS_PHASE) >= {"SigLIP", "OpenCLIP", "DINOv2-large", "CLIP variant", "RBF SVM", "MLP", "random forest", "boosting", "new threshold grid", "new crop", "new scan", "new zero-shot detector"}
    src = (inspect.getsource(sc) + inspect.getsource(mv) + inspect.getsource(sp) + inspect.getsource(ss)).lower()
    for banned in ("logisticregression(", ".fit(", "from_pretrained", "torch", "sklearn", "get_image_features", "pooler_output"):
        assert banned not in src, banned
    assert sc.NO_TRAINING == {"modelTraining": 0, "fineTuning": 0, "linearProbe": 0, "classifierFit": 0, "thresholdSelection": 0, "featureExtractionForModelSelection": 0, "productionInference": 0}


# ------------------------------------------------------------ 4-8 sources


def test_source_photos_excluded():
    inv = {e["source"]: e for e in sc.legacy_inventory()}
    assert inv["source photos (8)"]["classification"] == "RESTRICTED_SOURCE_NOT_MODEL_DATA" and inv["source photos (8)"]["count"] == 8
    assert sc.check_source(_image(origin="SOURCE_PHOTO", prov="RESTRICTED_SOURCE_NOT_MODEL_DATA")) == ["RESTRICTED_SOURCE_NOT_MODEL_DATA: source photos are never model data"]
    assert sc.check_source(_image(origin="SOURCE_PHOTO", prov="FUTURE_TRAINING_ELIGIBLE"))   # any attempt to make a source photo training data is an error
    assert sc.SOURCE_POLICY["runtimeTarget"] == "generated avatar output" and sc.SOURCE_POLICY["sourcePhotosCopiedIntoDataset"] is False


def test_prior_b3_artifacts_contaminated():
    inv = {e["source"]: e for e in sc.legacy_inventory()}
    for key in ("generated avatars (20, G1-G5)", "B3-L11 constructs (VISUAL_MARK_CHALLENGE_V3)", "B3-L14A constructs (EDGE_MARK_GENERALIZATION_V1)", "B3-L15A crops/proposals (CLIP)", "B3-L16A crops/embeddings (DINOv2)", "human label artifacts (B3-L5/L6 Rater A/B/C)"):
        assert inv[key]["classification"] == "LEGACY_DEVELOPMENT_CONTAMINATED", key
        assert "SEALED_TEST" not in inv[key]["futureUse"]
    assert sc.allowed_partitions("LEGACY_DEVELOPMENT_CONTAMINATED") == ("TRAIN_DEVELOPMENT", "VALIDATION")
    assert sc.allowed_partitions("FUTURE_HOLDOUT_ELIGIBLE") == ("TRAIN_DEVELOPMENT", "VALIDATION", "SEALED_TEST") and sc.allowed_partitions("RESTRICTED_SOURCE_NOT_MODEL_DATA") == ()


def test_natural_positive_definition_excludes_injected_overlays():
    assert sc.NATURAL_POSITIVE["definition"].startswith("visible text/logo/watermark/mark region that appears in the canonical avatar generation output itself")
    for kind in ("CONTROLLED_SYNTHETIC_AUGMENTATION", "CONTROLLED_CHALLENGE_EVIDENCE"):
        assert not sc.is_natural_positive(_image(origin=kind, regions=[_region()]))
    assert sc.is_natural_positive(_image(origin="NATURAL_GENERATED_OUTPUT", regions=[_region()]))
    assert not sc.is_natural_positive(_image(origin="NATURAL_GENERATED_OUTPUT", regions=[]))
    for excluded in ("B3 injected overlays", "programmatic synthetic marks", "manually pasted logo/text", "challenge derivatives", "synthetic constructs"):
        assert excluded in sc.NATURAL_POSITIVE["notCounted"]
    assert sc.PRIOR_STATUS["NATURAL_POSITIVE"] == "NATURAL_POSITIVE_EVIDENCE_MISSING" and sc.gap_status(natural_positive_groups=0)["naturalPositive"] == "NATURAL_POSITIVE_EVIDENCE_MISSING"
    assert sc.gap_status(natural_positive_groups=100)["naturalPositive"] == "NATURAL_POSITIVE_EVIDENCE_MISSING"   # design alone never closes the gap


def test_production_user_mining_prohibited():
    assert sc.production_mining_allowed() is False and sc.SOURCE_POLICY["productionUserImages"] == "prohibited without separate owner/privacy approval"
    errs = sc.check_source(_image(origin="NATURAL_GENERATED_OUTPUT", collectionBatch="prod-export-1", sourceAuthority="PRODUCTION_USER"))
    assert any("production" in e.lower() for e in errs)
    assert sc.check_source(_image(origin="NATURAL_GENERATED_OUTPUT", sourceAuthority="OWNER_AUTHORIZED_FIRST_PARTY")) == []
    src = (inspect.getsource(sc) + inspect.getsource(mv) + inspect.getsource(sp)).lower()
    for banned in ("firestore.client", "google.cloud.firestore", "firestore_v1", "storage.client", "gs://", "firebase_admin", "list_blobs"):
        assert banned not in src, banned
    assert sc.PRODUCTION_ACCESS == {"firestoreScans": 0, "storageBulkList": 0, "userDataMutation": 0, "userCorpusExport": 0}


def test_third_party_unknown_license_rejected():
    ok = {"name": "x", "sourceUrl": "https://example.org/x", "exactVersion": "1.0", "license": "CC-BY-4.0", "commercialProductUseCompatible": True, "redistributionRestrictions": "attribution",
          "imageCopyrightStatus": "cleared", "annotationLicense": "CC-BY-4.0", "downloadTerms": "accepted"}
    a = sc.audit_third_party(ok)
    assert a["status"] == "ELIGIBLE_AUGMENTATION_ONLY" and a["holdoutEligible"] is False and a["replacesNaturalHoldout"] is False
    assert sc.audit_third_party({**ok, "license": "unknown"})["status"] == "LICENSE_REVIEW_REQUIRED"
    assert sc.audit_third_party({k: v for k, v in ok.items() if k != "annotationLicense"})["status"] == "LICENSE_REVIEW_REQUIRED"
    assert sc.audit_third_party({**ok, "commercialProductUseCompatible": None})["status"] == "LICENSE_REVIEW_REQUIRED"
    assert set(sc.THIRD_PARTY_REQUIRED_FIELDS) == set(ok) and sc.SOURCE_POLICY["webScraping"] == "prohibited"


# ------------------------------------------------------------ 9-14 labels


def test_ontology_exact():
    assert sc.ONTOLOGY == ("NO_VISIBLE_RELEVANT_TEXT_OR_MARK", "GARMENT_TEXT", "BACKGROUND_SIGNAGE", "BRAND_TEXT_OR_MARK", "OVERLAY_TEXT", "OVERLAY_WATERMARK", "GRAPHICAL_LOGO", "GENERATIVE_TEXT_ARTIFACT", "UNCERTAIN")
    assert set(sc.ONTOLOGY) == set(ll.PRIMARY_LABELS) and sc.ONTOLOGY_AUTHORITY == ll.LABEL_SCHEMA_VERSION
    with pytest.raises(RuntimeError):
        sc.extend_ontology("NEW_CLASS")
    assert sc.POLICY_COLLAPSE_ALLOWED is False and not hasattr(sc, "POSITIVE_CLASSES")
    assert sc.validate_region(_region(**{"class": "LOGO"})) == ["class not in ontology: LOGO"]


def test_uncertain_excluded_from_primary_train():
    rec = _image(regions=[_region(**{"class": "UNCERTAIN", "annotationStatus": "uncertain"})])
    assert sc.primary_training_eligible(rec) is False and sc.UNCERTAIN_POLICY == "EXCLUDED_FROM_PRIMARY_TRAINING"
    assert sc.primary_training_eligible(_image(regions=[_region()])) is True
    agg = mv.aggregate([rec, _image(oid="img-0002", gid="grp-0002", regions=[_region()])])
    assert agg["uncertaintyRate"] == 0.5 and agg["primaryTrainingEligibleImages"] == 1


def test_region_bbox_validation():
    assert sc.validate_region(_region()) == []
    assert "bbox" in sc.validate_region(_region(bboxNormalized=[0.5, 0.1, 0.3, 0.3]))[0]
    assert "bbox" in sc.validate_region(_region(bboxNormalized=[0.0, 0.0, 1.2, 0.5]))[0]
    assert "bbox" in sc.validate_region(_region(bboxNormalized=[0.1, 0.1, 0.3]))[0]
    assert any("visibility" in e for e in sc.validate_region(_region(visibility="blurry")))
    assert any("sceneRelation" in e for e in sc.validate_region(_region(sceneRelation="floating")))
    assert any("annotationStatus" in e for e in sc.validate_region(_region(annotationStatus="guessed")))
    assert set(sc.REGION_SCHEMA) == {"regionId", "class", "bboxNormalized", "visibility", "sceneRelation", "legibility", "raterConfidence", "annotationStatus"}


def test_transcription_optional_not_default():
    assert sc.TRANSCRIPTION_POLICY["default"] == "not stored" and sc.TRANSCRIPTION_POLICY["requiresNewHypothesis"] is True
    assert any("transcription" in e for e in sc.validate_region(_region(transcription="ACME")))
    assert sc.validate_region(_region(transcription="ACME"), allow_transcription=True) == []


def test_rater_blind_to_model_outputs():
    tmpl = sc.label_template("img-0001")
    flat = json.dumps(tmpl).lower()
    for banned in ("clip", "dinov2", "grounding", "florence", "owlv2", "prediction", "threshold", "score", "b3pass", "passfail"):
        assert banned not in flat, banned
    assert sc.check_template_blind(tmpl) == []
    assert sc.check_template_blind({**tmpl, "clipScore": 0.9}) == ["forbidden rater-visible field: clipScore"]
    assert set(sc.BLINDING_FORBIDDEN) >= {"clipScore", "dinov2Score", "groundingDinoBox", "florenceResult", "owlv2Result", "modelPrediction", "thresholdResult", "priorB3PassFail"}


def test_disagreement_workflow_fixed():
    assert sc.LABEL_AUTHORITY["raters"] == ["RATER_A", "RATER_B"] and sc.LABEL_AUTHORITY["independent"] is True and sc.LABEL_AUTHORITY["inheritsB3PilotTruth"] is False
    assert sc.resolve_disagreement("GRAPHICAL_LOGO", "GRAPHICAL_LOGO", None) == ("GRAPHICAL_LOGO", "agreed")
    assert sc.resolve_disagreement("GRAPHICAL_LOGO", "OVERLAY_WATERMARK", "OVERLAY_WATERMARK") == ("OVERLAY_WATERMARK", "adjudicated")
    assert sc.resolve_disagreement("GRAPHICAL_LOGO", "OVERLAY_WATERMARK", None) == ("UNCERTAIN", "uncertain")
    assert sc.authority_status(2) == "DUAL_RATER_INDEPENDENT" and sc.authority_status(1) == "SINGLE_RATER_DATASET_LIMITATION"
    assert sc.production_validation_allowed(sc.authority_status(1)) is False
    assert sc.AGREEMENT_METRICS == ("image_level_agreement", "region_class_agreement", "region_localization_agreement") and sc.LOCALIZATION_AGREEMENT_IOU == 0.5
    assert sc.cohen_kappa(["a", "b", "a", "b"], ["a", "b", "a", "b"]) == 1.0 and sc.KAPPA_ROLE == "descriptive only; never proof of label correctness"


# ------------------------------------------------------------ 15-20 leakage / duplicates / split / sealed test


def _groups(n, prov="FUTURE_HOLDOUT_ELIGIBLE", stratum="CLEAN"):
    return [{"groupId": f"grp-{i:04d}", "provenanceClass": prov, "stratum": stratum, "imageCount": 1} for i in range(n)]


def test_group_cannot_cross_split():
    recs = [_image(oid="img-1", gid="grp-1", split="TRAIN_DEVELOPMENT"), _image(oid="img-2", gid="grp-1", split="SEALED_TEST", prov="FUTURE_HOLDOUT_ELIGIBLE")]
    errs = mv.validate_manifest({"datasetVersion": sc.VERSION, "images": recs})["errors"]
    assert any("group grp-1 spans partitions" in e for e in errs)
    plan = sp.plan_split(_groups(30))
    assert sp.verify(plan, _groups(30))["groupDisjoint"] is True
    with pytest.raises(TypeError):
        sp.plan_split(_groups(30), overrides={"grp-0001": "SEALED_TEST"})
    assert sc.LEAKAGE_UNIT == "group (same underlying identity / source lineage: regenerations, variants, near duplicates)"


def test_exact_duplicate_cannot_cross_split():
    a = _image(oid="img-1", gid="grp-1", split="TRAIN_DEVELOPMENT")
    b = _image(oid="img-2", gid="grp-2", split="SEALED_TEST", prov="FUTURE_HOLDOUT_ELIGIBLE", sha256=a["sha256"])
    errs = mv.validate_manifest({"datasetVersion": sc.VERSION, "images": [a, b]})["errors"]
    assert any("exact duplicate" in e and "partitions" in e for e in errs)
    merged = sc.collapse_duplicates([a, b])
    assert merged["img-1"] == merged["img-2"]


def test_near_duplicate_cannot_cross_split():
    a = _image(oid="img-1", gid="grp-1", split="TRAIN_DEVELOPMENT", perceptualHash="ffffffff00000000")
    b = _image(oid="img-2", gid="grp-2", split="SEALED_TEST", prov="FUTURE_HOLDOUT_ELIGIBLE", perceptualHash="ffffffff00000001")   # Hamming 1
    c = _image(oid="img-3", gid="grp-3", split="SEALED_TEST", prov="FUTURE_HOLDOUT_ELIGIBLE", perceptualHash="00000000ffffffff")   # Hamming 64
    errs = mv.validate_manifest({"datasetVersion": sc.VERSION, "images": [a, b, c]})["errors"]
    assert any("near duplicate" in e for e in errs) and not any("img-3" in e for e in errs)
    assert sc.DUPLICATE_POLICY["perceptualHash"] == "64-bit DCT pHash (32x32 grayscale, top-left 8x8 DCT, median)" and sc.DUPLICATE_POLICY["hammingThreshold"] == 10
    assert sc.hamming("ffffffff00000000", "ffffffff00000001") == 1
    img = Image.new("RGB", (64, 64), (100, 120, 140))
    assert re.fullmatch(r"[0-9a-f]{16}", sc.phash(img)) and sc.phash(img) == sc.phash(img.copy())
    with pytest.raises(TypeError):
        sc.collapse_duplicates([a, b], scores={"img-1": 0.9})    # model scores never enter dedup


def test_legacy_20_cannot_enter_sealed_test():
    rec = _image(oid="img-legacy", gid="grp-legacy", prov="LEGACY_DEVELOPMENT_CONTAMINATED", split="SEALED_TEST")
    errs = mv.validate_manifest({"datasetVersion": sc.VERSION, "images": [rec]})["errors"]
    assert any("LEGACY_DEVELOPMENT_CONTAMINATED" in e and "SEALED_TEST" in e for e in errs)
    legacy = [dict(g, groupId=f"grp-l{i:03d}") for i, g in enumerate(_groups(5, prov="LEGACY_DEVELOPMENT_CONTAMINATED"))]
    plan = sp.plan_split(legacy + _groups(30))
    assert all(plan[g["groupId"]] != "SEALED_TEST" for g in legacy) and any(plan[g["groupId"]] == "SEALED_TEST" for g in _groups(30))
    assert sc.LEGACY_SPLIT_STATUS == {"legacy20GeneratedAvatars": "LEGACY_DEVELOPMENT_CONTAMINATED", "allB3Constructs": "LEGACY_DEVELOPMENT_CONTAMINATED", "sealedEvaluationHoldout": "never"}


def test_sealed_test_cannot_be_evaluated_before_lock_prerequisites(tmp_path):
    with pytest.raises(sc.NotFrozen):
        sc.sealed_test_guard(tmp_path)
    for name in sc.SEALED_TEST_PREREQUISITES[:-1]:
        (tmp_path / name).write_text("{}", encoding="utf-8")
        with pytest.raises(sc.NotFrozen):
            sc.sealed_test_guard(tmp_path)
    (tmp_path / sc.SEALED_TEST_PREREQUISITES[-1]).write_text("{}", encoding="utf-8")
    lock = sc.sealed_test_guard(tmp_path)
    assert lock.name == sc.SEALED_TEST_LOCK_NAME == "supervised_dataset_v1_sealed_test.lock"
    assert sc.SEALED_TEST_PREREQUISITES == ("supervised_dataset_v1_manifest_frozen.json", "supervised_model_architecture_frozen.json", "supervised_training_recipe_frozen.json", "supervised_threshold_frozen.json")


def test_second_holdout_evaluation_refused(tmp_path):
    for name in sc.SEALED_TEST_PREREQUISITES:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    lock = sc.sealed_test_guard(tmp_path)
    sc.mark_sealed_evaluated(lock, "0" * 64)
    with pytest.raises(sc.SealedAlreadyEvaluated):
        sc.sealed_test_guard(tmp_path)


# ------------------------------------------------------------ 21-25 statistics


def test_image_group_is_statistical_unit():
    recs = [_image(oid="img-1", gid="grp-1", regions=[_region(regionId=f"r{k}") for k in range(20)]), _image(oid="img-2", gid="grp-1", regions=[_region()]), _image(oid="img-3", gid="grp-2", regions=[_region()])]
    assert sc.STATISTICAL_UNIT == "independent image/group, never crop or region count"
    units = sc.count_units(recs)
    assert units == {"images": 3, "groups": 2, "regions": 22}
    assert sc.family_recall_denominator(recs, "GRAPHICAL_LOGO") == 2    # independent groups, not 22 regions


def test_synthetic_does_not_count_as_natural_positive():
    recs = [_image(oid="img-1", gid="grp-1", origin="CONTROLLED_SYNTHETIC_AUGMENTATION", regions=[_region()]), _image(oid="img-2", gid="grp-2", origin="NATURAL_GENERATED_OUTPUT", regions=[_region()])]
    agg = mv.aggregate(recs)
    assert agg["naturalPositiveIndependentGroups"]["GRAPHICAL_LOGO"] == 1 and agg["syntheticPositiveImages"] == 1
    assert sc.SYNTHETIC_ROLE == {"allowed": ["training augmentation", "challenge set", "regression set"], "excludedFrom": ["natural-domain validation statistics", "sealed natural holdout statistics", "natural positive counts"]}


def test_cp_clean_upper_bound_calculation():
    assert ss.cp_upper_one_sided(0, 29, 0.95) == pytest.approx(1 - 0.05 ** (1 / 29), abs=1e-9) and ss.cp_upper_one_sided(0, 29, 0.95) < 0.10
    assert ss.cp_upper_one_sided(0, 28, 0.95) >= 0.10
    assert ss.cp_upper_one_sided(0, 59, 0.95) < 0.05 and ss.cp_upper_one_sided(0, 58, 0.95) >= 0.05
    assert ss.min_n_for_upper(failures=0, confidence=0.95, target=0.10) == 29 and ss.min_n_for_upper(failures=0, confidence=0.95, target=0.05) == 59
    assert ss.min_n_for_upper(failures=1, confidence=0.95, target=0.10) == 46
    assert ss.cp_upper_one_sided(1, 46, 0.95) < 0.10 and ss.cp_upper_one_sided(1, 45, 0.95) >= 0.10
    assert ss.cp_upper_one_sided(0, 0, 0.95) == 1.0
    plan = ss.plan()
    assert plan["clean"]["gateTarget"] == 0.10 and plan["clean"]["minIndependentCleanFor0FalseReviews"] == 29 and plan["clean"]["aspirationalTarget"] == 0.05 and plan["clean"]["minIndependentCleanFor0FalseReviewsAt5pct"] == 59


def test_cp_recall_lower_bound_calculation():
    assert ss.cp_lower_one_sided(29, 29, 0.95) == pytest.approx(0.05 ** (1 / 29), abs=1e-9) and ss.cp_lower_one_sided(29, 29, 0.95) >= 0.90
    assert ss.cp_lower_one_sided(28, 28, 0.95) < 0.90
    assert ss.min_n_for_lower(misses=0, confidence=0.95, target=0.90) == 29 and ss.min_n_for_lower(misses=1, confidence=0.95, target=0.90) == 46
    assert ss.cp_lower_one_sided(45, 46, 0.95) >= 0.90 and ss.cp_lower_one_sided(44, 45, 0.95) < 0.90
    assert ss.cp_lower_one_sided(0, 10, 0.95) == 0.0
    plan = ss.plan()
    assert plan["recall"]["target"] == 0.90 and plan["recall"]["minIndependentPositivesFor0Misses"] == 29 and plan["recall"]["minIndependentPositivesFor1Miss"] == 46
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?", plan["scipyVersion"]) and plan["method"] == "one-sided exact binomial (Clopper-Pearson) via beta quantiles"


def test_training_size_not_inferred_from_evaluation_n():
    assert ss.TRAINING_SIZE_STATUS == sc.TRAINING_SIZE_STATUS == "TRAINING_SIZE_NOT_YET_JUSTIFIED"
    with pytest.raises(RuntimeError):
        ss.training_size_from_evaluation_n(29)
    assert ss.plan()["trainingSize"] == {"status": "TRAINING_SIZE_NOT_YET_JUSTIFIED", "decidedBy": "future supervised phase learning-curve contract", "evaluationNIsNotTrainingN": True}


# ------------------------------------------------------------ 26-30 privacy / artifacts / no training / no production / no paid generation


def test_raw_uid_path_forbidden():
    for key in ("uid", "userId", "email", "sourcePhotoPath", "path", "filename", "userFacingFilename"):
        errs = mv.validate_manifest({"datasetVersion": sc.VERSION, "images": [_image(**{key: "x"})]})["errors"]
        assert any("forbidden" in e and key in e for e in errs), key
    assert set(sc.FORBIDDEN_MANIFEST_KEYS) >= {"uid", "userId", "email", "sourcePhotoPath", "path", "filename", "userFacingFilename"}
    assert sc.validate_group_id("grp-0001") == [] and sc.validate_group_id("P01_C02") and sc.validate_group_id("user_1234@x")
    assert sc.IMAGE_LEVEL_ALLOWED == ("hasRelevantRegion", "regionCount", "classSet", "uncertainPresent", "sourceProvenanceClass", "splitGroupId")


def test_aggregate_only_repo_artifact():
    ex = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert ex["fixture"] == "FAKE_OPAQUE_IDS_ONLY" and mv.validate_manifest(ex)["errors"] == []
    for path in (DESIGN, AGGREGATE, EXAMPLE):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"P\d{2}_C\d{2}", text) and "AppData" not in text and not re.search(r"[A-Za-z]:\\Users\\", text) and "@gmail" not in text, path.name
        for phrase in ("PRODUCTION_VALIDATED", "LIVE_READY", "NATURAL_POSITIVE_VALIDATED", "production-ready"):
            assert phrase not in text
    agg = json.loads(AGGREGATE.read_text(encoding="utf-8"))

    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)
    assert not ({"sha256", "perceptualHash", "regions", "bboxNormalized", "path", "opaqueImageId"} & set(keys(agg)))
    assert agg["datasetVersion"] == sc.VERSION and agg["contractDigestPrefix"] == sc.contract_digest()[:12]
    assert agg["verdict"] == "SUPERVISED_DATA_COLLECTION_CONTRACT_READY" and agg["naturalPositiveCorpus"] == "NATURAL_POSITIVE_CORPUS_INSUFFICIENT" and agg["cleanNegativeCorpus"] == "CLEAN_NEGATIVE_CORPUS_INSUFFICIENT"
    assert agg["gaps"]["naturalPositive"] == "NATURAL_POSITIVE_EVIDENCE_MISSING" and agg["trainingSize"] == "TRAINING_SIZE_NOT_YET_JUSTIFIED"


def test_no_model_training():
    assert sc.readiness()["allComplete"] is True and sc.readiness_verdict() == "SUPERVISED_DATA_COLLECTION_CONTRACT_READY"
    assert set(sc.READINESS_CHECKLIST) == {"sourcePolicy", "naturalPositiveDefinition", "labelOntology", "regionSchema", "blindedLabelWorkflow", "leakageGroup", "splitAlgorithm", "sealedHoldoutContract",
                                           "duplicateHandling", "privacyContract", "licenseHandling", "statisticalSufficiencyHelper", "legacyContaminationClassification"}
    agg = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    assert agg["noTraining"] == sc.NO_TRAINING and agg["modelTraining"] == 0 and agg["classifierFits"] == 0


def test_no_production_access():
    agg = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    assert agg["productionAccess"] == {"firestoreScans": 0, "storageBulkList": 0, "userDataMutation": 0, "userCorpusExport": 0} and agg["productionUserDataRequired"] == "NO (unless separately approved by owner/privacy)"
    assert agg["buildsDeploys"] == 0 and agg["productionWrites"] == 0


def test_no_paid_image_generation():
    agg = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    assert agg["imageGeneration"] == {"azure": 0, "openaiImage": 0} and agg["paidGenerationRequiredForCollection"] == "YES (not executed; plan only)"
    assert sc.COLLECTION_EXECUTION == "NOT_EXECUTED_PLAN_ONLY" and sc.collection_plan()["executed"] is False
    plan = sc.collection_plan()
    assert set(plan["naturalPositiveStrata"]) == {"BRAND_TEXT_OR_MARK", "OVERLAY_WATERMARK", "GRAPHICAL_LOGO", "GENERATIVE_TEXT_ARTIFACT"} and plan["overlayTextSeparate"] == "OVERLAY_TEXT held separately (TEXT_POLICY_GAP unresolved)"
    assert plan["perStratumIndependentGroupsForEvaluation"]["zeroMiss"] == 29 and plan["cleanIndependentGroupsForEvaluation"]["zeroFalseReview"] == 29


# ------------------------------------------------------------ extra: split determinism / stratification / digests / retention


def test_split_planner_deterministic_and_class_aware():
    groups = _groups(40, stratum="CLEAN") + [dict(g, groupId=f"grp-p{i:03d}", stratum="GRAPHICAL_LOGO") for i, g in enumerate(_groups(10))]
    plan1 = sp.plan_split(groups)
    plan2 = sp.plan_split(list(reversed(groups)))
    assert plan1 == plan2
    v = sp.verify(plan1, groups)
    assert v["groupDisjoint"] and v["reproducible"] and set(plan1.values()) <= set(sc.PARTITIONS)
    per = v["perStratumPartitionCounts"]
    assert per["GRAPHICAL_LOGO"]["SEALED_TEST"] >= 1 and per["GRAPHICAL_LOGO"]["TRAIN_DEVELOPMENT"] >= 1
    assert sp.PARTITION_FRACTIONS == {"TRAIN_DEVELOPMENT": 0.6, "VALIDATION": 0.2, "SEALED_TEST": 0.2} and sp.SEED == sc.VERSION
    assert sp.split_plan_digest() == sc.split_plan_digest()


def test_digests_and_retention_contract():
    for name in ("source_policy_digest", "ontology_digest", "schema_digest", "split_plan_digest", "label_policy_digest", "contract_digest"):
        assert re.fullmatch(r"[0-9a-f]{64}", getattr(sc, name)())
    text = DESIGN.read_text(encoding="utf-8")
    for token in (sc.VERSION, sc.MARKER, sc.contract_digest()[:12], sc.source_policy_digest()[:12], sc.ontology_digest()[:12], sc.schema_digest()[:12], sc.split_plan_digest()[:12], sc.label_policy_digest()[:12],
                  "SINGLE_RATER_DATASET_LIMITATION", "TRAINING_SIZE_NOT_YET_JUSTIFIED", "LICENSE_REVIEW_REQUIRED", "29", "59", "46"):
        assert token in text, token
    for cls in ("FIRST_PARTY_GENERATED_OUTPUT", "LEGACY_DEVELOPMENT_CONTAMINATED", "THIRD_PARTY_AUGMENTATION", "SOURCE_PHOTO"):
        r = sc.RETENTION[cls]
        assert {"retentionPeriod", "deletionTrigger", "consentWithdrawal", "derivedAnnotationDeletion", "splitManifestCleanup"} <= set(r)
    assert sc.RETENTION["PRODUCTION_USER_IMAGE"] == {"used": False, "note": "production user images are not used in SUPERVISED_WATERMARK_LOGO_DATASET_V1"}
