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
DESIGN_V1 = DOCS / "b3-l17a-supervised-data-design.md"                      # historical frozen record (V1; pinned by sha256 in test_a16)
AGGREGATE_V1 = DOCS / "b3-l17a-supervised-data-design-aggregate-v1.json"
EXAMPLE_V1 = DOCS / "b3-l17a-supervised-manifest-example.json"
DESIGN = DOCS / "b3-l17a1-supervised-data-contract-correction.md"           # current V1_1 correction
AGGREGATE = DOCS / "b3-l17a1-supervised-data-contract-correction-aggregate-v1.json"
EXAMPLE = DOCS / "b3-l17a1-supervised-manifest-example.json"


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


def _groups(n, prov="FUTURE_HOLDOUT_ELIGIBLE", stratum="NATURAL_CLEAN_REPRESENTATIVE"):
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
    sc.write_sealed_quota_check(tmp_path, _full_sealed_records())
    lock = sc.sealed_test_guard(tmp_path)
    assert lock.name == sc.SEALED_TEST_LOCK_NAME == "supervised_dataset_v1_1_sealed_test.lock"
    assert sc.SEALED_TEST_PREREQUISITES == ("supervised_dataset_v1_1_manifest_frozen.json", "supervised_model_architecture_frozen.json", "supervised_training_recipe_frozen.json", "supervised_threshold_frozen.json",
                                            "supervised_dataset_v1_1_sealed_quota_check.json")


def _full_sealed_records():
    full = []
    for cls in sc.CRITICAL_POSITIVE_STRATA:
        full += [_image(oid=f"img-{cls}{i}", gid=f"grp-{cls.lower().replace('_', '')}{i:04x}", prov="FUTURE_HOLDOUT_ELIGIBLE", split="SEALED_TEST", regions=[_region(**{"class": cls})]) for i in range(29)]
    return full + [_image(oid=f"img-c{i}", gid=f"grp-c{i:04x}", prov="FUTURE_HOLDOUT_ELIGIBLE", split="SEALED_TEST", cleanCategory="NATURAL_CLEAN_REPRESENTATIVE") for i in range(29)]


def test_second_holdout_evaluation_refused(tmp_path):
    for name in sc.SEALED_TEST_PREREQUISITES[:-1]:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    sc.write_sealed_quota_check(tmp_path, _full_sealed_records())
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
    assert ss.plan()["trainingSize"].items() >= {"status": "TRAINING_SIZE_NOT_YET_JUSTIFIED", "decidedBy": "future supervised phase learning-curve contract", "evaluationNIsNotTrainingN": True}.items()


# ------------------------------------------------------------ 26-30 privacy / artifacts / no training / no production / no paid generation


def test_raw_uid_path_forbidden():
    for key in ("uid", "userId", "email", "sourcePhotoPath", "path", "filename", "userFacingFilename"):
        errs = mv.validate_manifest({"datasetVersion": sc.VERSION, "images": [_image(**{key: "x"})]})["errors"]
        assert any("forbidden" in e and key in e for e in errs), key
    assert set(sc.FORBIDDEN_MANIFEST_KEYS) >= {"uid", "userId", "email", "sourcePhotoPath", "path", "filename", "userFacingFilename"}
    assert sc.validate_group_id("grp-0001") == [] and sc.validate_group_id("P01_C02") and sc.validate_group_id("user_1234@x")
    assert sc.IMAGE_LEVEL_ALLOWED == ("hasRelevantRegion", "regionCount", "classSet", "uncertainPresent", "sourceProvenanceClass", "splitGroupId", "cleanCategory")


def test_aggregate_only_repo_artifact():
    ex = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert ex["fixture"] == "FAKE_OPAQUE_IDS_ONLY" and mv.validate_manifest(ex)["errors"] == []
    for path in (DESIGN, AGGREGATE, EXAMPLE, DESIGN_V1, AGGREGATE_V1, EXAMPLE_V1):
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
    assert agg["verdict"] == sc.CORRECTION_MARKER and agg["naturalPositiveCorpus"] == "NATURAL_POSITIVE_CORPUS_INSUFFICIENT" and agg["cleanNegativeCorpus"] == "CLEAN_NEGATIVE_CORPUS_INSUFFICIENT"
    assert agg["gaps"]["naturalPositive"] == "NATURAL_POSITIVE_EVIDENCE_MISSING" and agg["trainingSize"] == "TRAINING_SIZE_NOT_YET_JUSTIFIED"


def test_no_model_training():
    assert sc.readiness()["allComplete"] is True and sc.readiness_verdict() == "SUPERVISED_DATA_COLLECTION_CONTRACT_READY_AFTER_QUOTA_CORRECTION"
    assert set(sc.READINESS_CHECKLIST) == {"sourcePolicy", "naturalPositiveDefinition", "labelOntology", "regionSchema", "blindedLabelWorkflow", "leakageGroup", "splitAlgorithm", "sealedHoldoutContract",
                                           "duplicateHandling", "privacyContract", "licenseHandling", "statisticalSufficiencyHelper", "legacyContaminationClassification",
                                           "evaluationVsCollectionQuota", "multiLabelGroupSplit", "cleanCategorySeparation", "sealedQuotaValidator"}
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
    groups = _groups(40, stratum="NATURAL_CLEAN_REPRESENTATIVE") + [dict(g, groupId=f"grp-p{i:03d}", stratum="GRAPHICAL_LOGO") for i, g in enumerate(_groups(10))]
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
    text = DESIGN_V1.read_text(encoding="utf-8")
    for token in (sc.VERSION_V1, sc.MARKER, sc.V1_FROZEN_DIGESTS["contract"][:12], sc.V1_FROZEN_DIGESTS["sourcePolicy"][:12], sc.V1_FROZEN_DIGESTS["ontology"][:12], sc.V1_FROZEN_DIGESTS["schema"][:12],
                  sc.V1_FROZEN_DIGESTS["splitPlan"][:12], sc.V1_FROZEN_DIGESTS["labelPolicy"][:12], "SINGLE_RATER_DATASET_LIMITATION", "TRAINING_SIZE_NOT_YET_JUSTIFIED", "LICENSE_REVIEW_REQUIRED", "29", "59", "46"):
        assert token in text, token
    text = DESIGN.read_text(encoding="utf-8")
    for token in (sc.VERSION, sc.contract_digest()[:12], sc.source_policy_digest()[:12], sc.ontology_digest()[:12], sc.schema_digest()[:12], sc.split_plan_digest()[:12], sc.label_policy_digest()[:12]):
        assert token in text, token
    for cls in ("FIRST_PARTY_GENERATED_OUTPUT", "LEGACY_DEVELOPMENT_CONTAMINATED", "THIRD_PARTY_AUGMENTATION", "SOURCE_PHOTO"):
        r = sc.RETENTION[cls]
        assert {"retentionPeriod", "deletionTrigger", "consentWithdrawal", "derivedAnnotationDeletion", "splitManifestCleanup"} <= set(r)
    assert sc.RETENTION["PRODUCTION_USER_IMAGE"] == {"used": False, "note": "production user images are not used in SUPERVISED_WATERMARK_LOGO_DATASET_V1"}


# ============================================================ B3-L17A.1 — evaluation-quota vs collection-quota consistency correction (V1_1)

CORRECTION = DOCS / "b3-l17a1-supervised-data-contract-correction.md"
CORRECTION_AGGREGATE = DOCS / "b3-l17a1-supervised-data-contract-correction-aggregate-v1.json"
EXAMPLE_V1_1 = DOCS / "b3-l17a1-supervised-manifest-example.json"
V1_FILE_SHA256 = {"b3-l17a-supervised-data-design.md": "cdb82a608bc4fcd7c910f9d9ad5196716a71d2eaa9954f022fac6081845c3de4",
                  "b3-l17a-supervised-data-design-aggregate-v1.json": "2ef377daeb5e652abf7bb3247b24738e2a0928b18463e3f947ffdd0e1ea98285",
                  "b3-l17a-supervised-manifest-example.json": "646cffdb794cd43f635c74e8ecb51a25a43b1afced7b69fd6d6bab76b8d0c704"}


def _mgroup(gid, strata, prov="FUTURE_HOLDOUT_ELIGIBLE", **over):
    g = {"groupId": gid, "provenanceClass": prov, "evaluationStrata": sorted(strata), "imageCount": 1}
    g.update(over)
    return g


def _pool(n, label, prefix="grp-s", prov="FUTURE_HOLDOUT_ELIGIBLE"):
    return [_mgroup(f"{prefix}{label[:3].lower()}{i:04d}", [label], prov=prov) for i in range(n)]


# ---- 1. 29 evaluation groups != 29 total collection groups


def test_a1_evaluation_quota_is_not_collection_quota():
    assert sc.VERSION == "SUPERVISED_WATERMARK_LOGO_DATASET_V1_1" and sc.VERSION_V1 == "SUPERVISED_WATERMARK_LOGO_DATASET_V1"
    assert sc.MISMATCH_MARKER == "EVALUATION_QUOTA_VS_COLLECTION_QUOTA_MISMATCH" and sc.PRIOR_STATUS["B3_L17A_1"] == sc.MISMATCH_MARKER
    assert sc.COUNT_KINDS == ("COLLECTED_GROUPS", "PARTITIONED_GROUPS", "EVALUATION_ELIGIBLE_SEALED_GROUPS") and sc.EVALUATION_TARGET_COUNT_KIND == "EVALUATION_ELIGIBLE_SEALED_GROUPS"
    m = ss.minimum_collected_groups(29)
    assert m["targetCountKind"] == "EVALUATION_ELIGIBLE_SEALED_GROUPS" and m["countKind"] == "COLLECTED_GROUPS" and m["minimumCollectedIndependentGroupsRequired"] > 29
    status = sc.corpus_status({}, 0)
    assert status["requiredSealedPerStratum"] == 29 and status["requiredSealedRepresentativeClean"] == 29 and "collectionGapByClass" not in status
    assert status["sealedEvaluationGapByClass"]["GRAPHICAL_LOGO"] == 29 and status["minimumCollectionByClass"]["GRAPHICAL_LOGO"] == m["minimumCollectedIndependentGroupsRequired"]
    assert sc.MISMATCH_RECORD["oldWording"] == "Collection gap: 29 independent groups per positive stratum and 29 independent clean groups (59 aspirational)"
    assert "EVALUATION_ELIGIBLE_SEALED_GROUPS" in sc.MISMATCH_RECORD["correctedMeaning"]


# ---- 2-5. minimum collection calculator simulates the frozen splitter; sealed 29 / 46 / clean 59 derived


def test_a2_minimum_collection_calculator_simulates_splitter():
    m = ss.minimum_collected_groups(29, sealed_fraction=0.20, stratum="GRAPHICAL_LOGO", provenance_pool="FUTURE")
    n = m["minimumCollectedIndependentGroupsRequired"]
    assert m["sealedFraction"] == 0.20 and m["splitPlanDigestPrefix"] == sc.split_plan_digest()[:12] and m["method"] == "simulate the frozen deterministic splitter on n synthetic opaque groups"
    assert m["sealedGroupsAtMinimum"] >= 29 and m["sealedGroupsOneBelow"] < 29 and m["naiveCeil"] == 145 and abs(n - 145) <= 5
    plan = sp.plan_split(_pool(n, "GRAPHICAL_LOGO"))
    assert sum(1 for p in plan.values() if p == "SEALED_TEST") >= 29
    plan = sp.plan_split(_pool(n - 1, "GRAPHICAL_LOGO"))
    assert sum(1 for p in plan.values() if p == "SEALED_TEST") < 29
    with pytest.raises(ValueError):
        ss.minimum_collected_groups(29, sealed_fraction=0.5, provenance_pool="FUTURE")     # fraction is frozen by the pool, not a free parameter
    with pytest.raises(ValueError):
        ss.minimum_collected_groups(29, provenance_pool="LEGACY")                           # legacy pool can never reach SEALED_TEST
    assert ss.minimum_collected_groups(29, provenance_pool="SEALED_RESERVED")["minimumCollectedIndependentGroupsRequired"] == 29


def test_a3_sealed_29_target_derived_by_planner():
    m = ss.minimum_collected_groups(29)
    assert m["targetSealedGroups"] == 29 == ss.min_n_for_lower(0) == ss.min_n_for_upper(0)
    assert m["minimumCollectedIndependentGroupsRequired"] == ss.plan()["minimumCollection"]["sealed29"]["minimumCollectedIndependentGroupsRequired"]


def test_a4_sealed_46_target_derived():
    m = ss.minimum_collected_groups(46)
    assert m["targetSealedGroups"] == 46 == ss.min_n_for_lower(1) and abs(m["minimumCollectedIndependentGroupsRequired"] - 230) <= 5 and m["naiveCeil"] == 230
    assert m["minimumCollectedIndependentGroupsRequired"] == ss.plan()["minimumCollection"]["sealed46"]["minimumCollectedIndependentGroupsRequired"]


def test_a5_clean_sealed_59_aspirational_derived():
    m = ss.minimum_collected_groups(59, stratum="NATURAL_CLEAN_REPRESENTATIVE")
    assert m["targetSealedGroups"] == 59 == ss.min_n_for_upper(0, target=0.05) and abs(m["minimumCollectedIndependentGroupsRequired"] - 295) <= 5 and m["naiveCeil"] == 295
    assert m["minimumCollectedIndependentGroupsRequired"] == ss.plan()["minimumCollection"]["clean59Aspirational"]["minimumCollectedIndependentGroupsRequired"]


# ---- 6. statistical target unchanged


def test_a6_statistical_target_unchanged():
    assert (ss.CONFIDENCE, ss.CLEAN_GATE_TARGET, ss.CLEAN_ASPIRATIONAL_TARGET, ss.RECALL_TARGET) == (0.95, 0.10, 0.05, 0.90)
    assert ss.min_n_for_upper(0) == 29 and ss.min_n_for_upper(1) == 46 and ss.min_n_for_upper(0, target=0.05) == 59 and ss.min_n_for_lower(0) == 29 and ss.min_n_for_lower(1) == 46
    assert sc.SEALED_QUOTA == {"criticalPositivePerClass": 29, "representativeClean": 29, "representativeCleanAspirational": 59, "unit": "independent group", "partition": "SEALED_TEST"}
    assert sc.STATISTICAL_UNIT == "independent image/group, never crop or region count" and sc.PARTITION_FRACTIONS["SEALED_TEST"] == 0.2


# ---- 7. validation cannot count toward sealed evidence


def test_a7_validation_not_sealed_evidence():
    recs = [_image(oid=f"img-{i}", gid=f"grp-{i:04x}", prov="FUTURE_HOLDOUT_ELIGIBLE", split="SEALED_TEST", regions=[_region()]) for i in range(3)]
    recs += [_image(oid=f"img-v{i}", gid=f"grp-v{i:04x}", prov="FUTURE_HOLDOUT_ELIGIBLE", split="VALIDATION", regions=[_region()]) for i in range(5)]
    assert sc.validation_counts_toward_sealed_evidence() is False
    ev = sc.sealed_evidence_groups(recs)
    assert ev["GRAPHICAL_LOGO"] == 3
    with pytest.raises(ValueError):
        sc.sealed_evidence_groups(recs, partition="VALIDATION")
    assert sc.VALIDATION_ROLE == ("model selection", "training recipe selection", "threshold selection") and sc.SEALED_TEST_CONTRACT["evaluations"] == "exactly one behind the lock; second evaluation fails closed"


# ---- 8-9. representative clean vs benign hard-negative stress; stress rate never named production rate


def test_a8_representative_clean_vs_hard_negative_stress_separate():
    assert sc.CLEAN_CATEGORIES == ("NATURAL_CLEAN_REPRESENTATIVE", "BENIGN_HARD_NEGATIVE_STRESS") and sc.BENIGN_CLASSES == ("GARMENT_TEXT", "BACKGROUND_SIGNAGE")
    assert sc.POLICY_POSITIVE_CLASSES == ("BRAND_TEXT_OR_MARK", "OVERLAY_WATERMARK", "GRAPHICAL_LOGO", "GENERATIVE_TEXT_ARTIFACT", "OVERLAY_TEXT") and sc.ONTOLOGY == tuple(ll.PRIMARY_LABELS)
    rep = _image(oid="img-r", gid="grp-r", cleanCategory="NATURAL_CLEAN_REPRESENTATIVE")
    stress = _image(oid="img-s", gid="grp-s", regions=[_region(**{"class": "GARMENT_TEXT", "sceneRelation": "garment", "legibility": "partial"})], cleanCategory="BENIGN_HARD_NEGATIVE_STRESS")
    uncat = _image(oid="img-u", gid="grp-u")
    pos = _image(oid="img-p", gid="grp-p", regions=[_region()])
    assert sc.clean_status(rep) == sc.clean_status(stress) == sc.clean_status(uncat) == "CLEAN" and sc.clean_status(pos) == "POSITIVE"
    assert sc.clean_category(rep) == "NATURAL_CLEAN_REPRESENTATIVE" and sc.clean_category(stress) == "BENIGN_HARD_NEGATIVE_STRESS" and sc.clean_category(uncat) == "UNCATEGORIZED_CLEAN" and sc.clean_category(pos) is None
    assert sc.validate_image_record(rep) == [] and sc.validate_image_record(stress) == []
    assert any("cleanCategory" in e for e in sc.validate_image_record(_image(oid="img-x", gid="grp-x", regions=[_region()], cleanCategory="NATURAL_CLEAN_REPRESENTATIVE")))
    assert any("cleanCategory" in e for e in sc.validate_image_record(_image(oid="img-y", gid="grp-y", origin="CONTROLLED_SYNTHETIC_AUGMENTATION", cleanCategory="NATURAL_CLEAN_REPRESENTATIVE")))
    agg = mv.aggregate([rep, stress, uncat, pos])
    assert agg["cleanRepresentativeIndependentGroups"] == 1 and agg["hardNegativeStressIndependentGroups"] == 1 and agg["uncategorizedCleanIndependentGroups"] == 1
    assert sc.CLEAN_CATEGORY_CONTRACT["NATURAL_CLEAN_REPRESENTATIVE"]["selectedByModelScore"] is False and sc.CLEAN_CATEGORY_CONTRACT["BENIGN_HARD_NEGATIVE_STRESS"]["enrichmentAllowed"] is True
    assert sc.CLEAN_CATEGORY_CONTRACT["BENIGN_HARD_NEGATIVE_STRESS"]["productionPrevalenceClaim"] is False


def test_a9_hard_negative_stress_rate_not_named_production_rate():
    assert sc.false_review_metric_name("BENIGN_HARD_NEGATIVE_STRESS") == "HARD_NEGATIVE_STRESS_FALSE_REVIEW_RATE"
    assert sc.false_review_metric_name("NATURAL_CLEAN_REPRESENTATIVE") == "REPRESENTATIVE_CLEAN_FALSE_REVIEW_RATE"
    with pytest.raises(ValueError):
        sc.false_review_metric_name("UNCATEGORIZED_CLEAN")
    assert sc.production_clean_rate_claim_allowed("BENIGN_HARD_NEGATIVE_STRESS", representative_sealed_groups=1000) is False
    assert sc.production_clean_rate_claim_allowed("NATURAL_CLEAN_REPRESENTATIVE", representative_sealed_groups=0) is False
    assert sc.production_clean_rate_claim_allowed("NATURAL_CLEAN_REPRESENTATIVE", representative_sealed_groups=29) is True
    with pytest.raises(ValueError):
        sc.metric_label("BENIGN_HARD_NEGATIVE_STRESS", "production clean false-review rate")
    assert sc.metric_label("BENIGN_HARD_NEGATIVE_STRESS", "HARD_NEGATIVE_STRESS_FALSE_REVIEW_RATE") == "HARD_NEGATIVE_STRESS_FALSE_REVIEW_RATE"


# ---- 10-13. multi-label group split contract


def test_a10_multi_label_group_in_one_partition_only():
    groups = _pool(40, "GRAPHICAL_LOGO") + _pool(40, "OVERLAY_WATERMARK", prefix="grp-w") + [_mgroup("grp-multi01", ["GRAPHICAL_LOGO", "OVERLAY_WATERMARK"]), _mgroup("grp-multi02", ["GRAPHICAL_LOGO", "GENERATIVE_TEXT_ARTIFACT"])]
    plan = sp.plan_split(groups)
    assert len(plan) == len(groups) and set(plan.values()) <= set(sc.PARTITIONS)
    assert plan == sp.plan_split(list(reversed(groups))) == sp.plan_split(sorted(groups, key=lambda g: g["groupId"]))
    v = sp.verify(plan, groups)
    assert v["groupDisjoint"] and v["reproducible"] and v["multiLabelGroups"] == 2
    recs = [_image(oid="img-1", gid="grp-m", prov="FUTURE_HOLDOUT_ELIGIBLE", split=plan["grp-multi01"], regions=[_region(), _region(regionId="r2", **{"class": "OVERLAY_WATERMARK"})])]
    assert mv.validate_manifest({"datasetVersion": sc.VERSION, "images": recs})["errors"] == []


def test_a11_multi_label_group_counts_toward_all_class_quotas_once_each():
    groups = _pool(30, "GRAPHICAL_LOGO") + [_mgroup("grp-multi01", ["GRAPHICAL_LOGO", "OVERLAY_WATERMARK"])]
    plan = sp.plan_split(groups)
    v = sp.verify(plan, groups)
    per = v["perLabelPartitionCounts"]
    p = plan["grp-multi01"]
    assert per["OVERLAY_WATERMARK"] == {p: 1} and sum(per["GRAPHICAL_LOGO"].values()) == 31
    assert v["independentGroups"] == 31                                             # the multi-label group is one statistical unit
    recs = [_image(oid="img-1", gid="grp-m", prov="FUTURE_HOLDOUT_ELIGIBLE", split="SEALED_TEST", regions=[_region(), _region(regionId="r2", **{"class": "OVERLAY_WATERMARK"})])]
    ev = sc.sealed_evidence_groups(recs)
    assert ev["GRAPHICAL_LOGO"] == 1 and ev["OVERLAY_WATERMARK"] == 1 and ev["independentGroups"] == 1
    assert mv.groups_from_manifest(recs) == [{"groupId": "grp-m", "provenanceClass": "FUTURE_HOLDOUT_ELIGIBLE", "evaluationStrata": ["GRAPHICAL_LOGO", "OVERLAY_WATERMARK"], "imageCount": 1}]


def test_a12_group_duplicated_across_strata_rejected():
    with pytest.raises(ValueError, match="duplicate groupId"):
        sp.plan_split([_mgroup("grp-dup", ["GRAPHICAL_LOGO"]), _mgroup("grp-dup", ["OVERLAY_WATERMARK"])])
    with pytest.raises(ValueError):
        sp.plan_split([_mgroup("grp-x", ["NOT_A_STRATUM"])])
    with pytest.raises(TypeError):
        sp.plan_split(_pool(5, "GRAPHICAL_LOGO"), overrides={"grp-sgra0000": "SEALED_TEST"})
    with pytest.raises(TypeError):
        sp.plan_split(_pool(5, "GRAPHICAL_LOGO"), scores={"grp-sgra0000": 0.9})


def test_a13_multi_label_allocation_rule_frozen():
    assert sc.SPLIT_ALGORITHM.startswith("group-level multi-label: order groups by sha256(SEED + groupId); integer quotas per (label, provenance pool, partition) by largest remainder")
    assert "deficit" in sc.SPLIT_ALGORITHM and "no manual override" in sc.SPLIT_ALGORITHM and "no model score" in sc.SPLIT_ALGORITHM
    assert sp.integer_quotas(143, {"TRAIN_DEVELOPMENT": 0.6, "VALIDATION": 0.2, "SEALED_TEST": 0.2}) == {"TRAIN_DEVELOPMENT": 86, "VALIDATION": 28, "SEALED_TEST": 29}   # 85.8/28.6/28.6: remainders .8 > .6 = .6, tie -> SEALED_TEST
    assert sp.integer_quotas(142, {"TRAIN_DEVELOPMENT": 0.6, "VALIDATION": 0.2, "SEALED_TEST": 0.2}) == {"TRAIN_DEVELOPMENT": 85, "VALIDATION": 28, "SEALED_TEST": 29}   # 85.2/28.4/28.4: one seat, tie -> SEALED_TEST
    assert sp.integer_quotas(141, {"TRAIN_DEVELOPMENT": 0.6, "VALIDATION": 0.2, "SEALED_TEST": 0.2}) == {"TRAIN_DEVELOPMENT": 85, "VALIDATION": 28, "SEALED_TEST": 28}   # 84.6/28.2/28.2: seat -> TRAIN
    assert sp.integer_quotas(5, {"TRAIN_DEVELOPMENT": 0.6, "VALIDATION": 0.2, "SEALED_TEST": 0.2}) == {"TRAIN_DEVELOPMENT": 3, "VALIDATION": 1, "SEALED_TEST": 1}
    assert sp.integer_quotas(4, {"TRAIN_DEVELOPMENT": 0.75, "VALIDATION": 0.25}) == {"TRAIN_DEVELOPMENT": 3, "VALIDATION": 1}
    assert sp.REMAINDER_TIE_BREAK == ("SEALED_TEST", "VALIDATION", "TRAIN_DEVELOPMENT")
    assert sc.group_allowed_partitions({"provenanceClass": "FUTURE_HOLDOUT_ELIGIBLE", "lineageReservation": "SEALED_RESERVED"}) == ("SEALED_TEST",)
    assert sc.group_allowed_partitions({"provenanceClass": "FUTURE_TRAINING_ELIGIBLE", "lineageReservation": "DEVELOPMENT_ONLY"}) == ("TRAIN_DEVELOPMENT", "VALIDATION")
    with pytest.raises(ValueError):
        sc.group_allowed_partitions({"provenanceClass": "LEGACY_DEVELOPMENT_CONTAMINATED", "lineageReservation": "SEALED_RESERVED"})
    reserved = [_mgroup(f"grp-res{i:03d}", ["GRAPHICAL_LOGO"], lineageReservation="SEALED_RESERVED") for i in range(7)]
    assert set(sp.plan_split(reserved).values()) == {"SEALED_TEST"}


# ---- 14. sealed per-class quota validator blocks the lock


def test_a14_sealed_quota_validator_blocks_lock(tmp_path):
    short = [_image(oid=f"img-{i}", gid=f"grp-{i:04x}", prov="FUTURE_HOLDOUT_ELIGIBLE", split="SEALED_TEST", regions=[_region()]) for i in range(5)]
    q = sc.sealed_quota_check(short)
    assert q["status"] == "SEALED_TEST_STATISTICAL_QUOTA_NOT_MET" and q["perClass"]["GRAPHICAL_LOGO"] == {"sealedIndependentGroups": 5, "required": 29, "met": False}
    assert q["representativeClean"] == {"sealedIndependentGroups": 0, "required": 29, "met": False, "aspirational": 59, "aspirationalMet": False}
    for name in sc.SEALED_TEST_PREREQUISITES:
        (tmp_path / name).write_text("{}", encoding="utf-8")
    sc.write_sealed_quota_check(tmp_path, short)
    with pytest.raises(sc.SealedQuotaNotMet):
        sc.sealed_test_guard(tmp_path)
    assert not (tmp_path / sc.SEALED_TEST_LOCK_NAME).exists()
    full = _full_sealed_records() + [_image(oid=f"img-h{i}", gid=f"grp-h{i:04x}", prov="FUTURE_HOLDOUT_ELIGIBLE", split="SEALED_TEST", cleanCategory="BENIGN_HARD_NEGATIVE_STRESS") for i in range(100)]
    q = sc.sealed_quota_check(full)
    assert q["status"] == "SEALED_TEST_STATISTICAL_QUOTA_MET" and q["representativeClean"]["met"] is True and q["representativeClean"]["aspirationalMet"] is False
    assert q["hardNegativeStress"] == {"sealedIndependentGroups": 100, "countsTowardRepresentativeClean": False, "metric": "HARD_NEGATIVE_STRESS_FALSE_REVIEW_RATE"}
    sc.write_sealed_quota_check(tmp_path, full)
    assert sc.sealed_test_guard(tmp_path).name == sc.SEALED_TEST_LOCK_NAME
    assert sc.SEALED_TEST_PREREQUISITES[-1] == sc.SEALED_QUOTA_FILE == "supervised_dataset_v1_1_sealed_quota_check.json"


# ---- 15. collection n is not training n


def test_a15_collection_n_not_training_n():
    m = ss.minimum_collected_groups(29)
    assert m["isTrainingSizeRequirement"] is False and m["trainingSize"] == "TRAINING_SIZE_NOT_YET_JUSTIFIED"
    with pytest.raises(RuntimeError):
        ss.training_size_from_collection_n(m["minimumCollectedIndependentGroupsRequired"])
    assert sc.corpus_status({}, 0)["trainingSize"] == "TRAINING_SIZE_NOT_YET_JUSTIFIED" and ss.plan()["minimumCollection"]["isTrainingSizeRequirement"] is False


# ---- versioning: historical V1 preserved, V1_1 correction marker, digests, aggregate-only


def test_a16_historical_v1_preserved_not_stealth_edited():
    for name, digest in V1_FILE_SHA256.items():
        assert hashlib.sha256((DOCS / name).read_bytes()).hexdigest() == digest, name
    assert sc.V1_FROZEN_DIGESTS["contract"] == "5d10e2b0924840079c494067109e232183f0cf649a2388c77688773af0e899c2" and sc.V1_FROZEN_DIGESTS["splitPlan"].startswith("75522cd03b4f")
    assert sc.contract_digest() != sc.V1_FROZEN_DIGESTS["contract"] and sc.split_plan_digest() != sc.V1_FROZEN_DIGESTS["splitPlan"]
    assert sc.ontology_digest() == sc.V1_FROZEN_DIGESTS["ontology"] and sc.label_policy_digest() == sc.V1_FROZEN_DIGESTS["labelPolicy"]     # ontology and label policy untouched
    v1 = json.loads(AGGREGATE_V1.read_text(encoding="utf-8"))
    assert v1["datasetVersion"] == sc.VERSION_V1 and v1["contractDigestPrefix"] == sc.V1_FROZEN_DIGESTS["contract"][:12]
    errs = mv.validate_manifest(json.loads(EXAMPLE_V1.read_text(encoding="utf-8")))["errors"]
    assert errs == [f"datasetVersion must be {sc.VERSION} (historical {sc.VERSION_V1} manifest requires migration)"]


def test_a17_correction_marker_and_artifact():
    assert sc.CORRECTION_MARKER == "SUPERVISED_DATA_COLLECTION_CONTRACT_READY_AFTER_QUOTA_CORRECTION" and sc.readiness_verdict() == sc.CORRECTION_MARKER
    assert set(sc.READINESS_CHECKLIST) >= {"evaluationVsCollectionQuota", "multiLabelGroupSplit", "cleanCategorySeparation", "sealedQuotaValidator"}
    agg = json.loads(CORRECTION_AGGREGATE.read_text(encoding="utf-8"))
    assert agg["datasetVersion"] == sc.VERSION and agg["historicalVersion"] == sc.VERSION_V1 and agg["contractDigestPrefix"] == sc.contract_digest()[:12]
    assert agg["verdict"] == sc.CORRECTION_MARKER and agg["mismatch"]["marker"] == sc.MISMATCH_MARKER and agg["priorVerdictV1"] == "SUPERVISED_DATA_COLLECTION_CONTRACT_READY"
    assert agg["naturalPositiveCorpus"] == "NATURAL_POSITIVE_CORPUS_INSUFFICIENT" and agg["cleanNegativeCorpus"] == "CLEAN_NEGATIVE_CORPUS_INSUFFICIENT" and agg["trainingSize"] == "TRAINING_SIZE_NOT_YET_JUSTIFIED"
    mc = agg["minimumCollection"]
    assert mc["sealed29"]["minimumCollectedIndependentGroupsRequired"] == ss.minimum_collected_groups(29)["minimumCollectedIndependentGroupsRequired"]
    assert mc["sealed46"]["minimumCollectedIndependentGroupsRequired"] == ss.minimum_collected_groups(46)["minimumCollectedIndependentGroupsRequired"]
    assert mc["clean59Aspirational"]["minimumCollectedIndependentGroupsRequired"] == ss.minimum_collected_groups(59)["minimumCollectedIndependentGroupsRequired"]
    assert agg["imageGeneration"] == {"azure": 0, "openaiImage": 0} and agg["modelTraining"] == 0 and agg["inference"] == 0 and agg["productionAccess"] == sc.PRODUCTION_ACCESS
    text = CORRECTION.read_text(encoding="utf-8")
    for token in (sc.VERSION, sc.CORRECTION_MARKER, sc.MISMATCH_MARKER, sc.contract_digest()[:12], sc.split_plan_digest()[:12], sc.schema_digest()[:12], "EVALUATION_ELIGIBLE_SEALED_GROUPS", "COLLECTED_GROUPS",
                  "PARTITIONED_GROUPS", "NATURAL_CLEAN_REPRESENTATIVE", "BENIGN_HARD_NEGATIVE_STRESS", "HARD_NEGATIVE_STRESS_FALSE_REVIEW_RATE", "SEALED_TEST_STATISTICAL_QUOTA_NOT_MET", "TRAINING_SIZE_NOT_YET_JUSTIFIED",
                  str(mc["sealed29"]["minimumCollectedIndependentGroupsRequired"]), str(mc["sealed46"]["minimumCollectedIndependentGroupsRequired"]), str(mc["clean59Aspirational"]["minimumCollectedIndependentGroupsRequired"])):
        assert token in text, token
    ex = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    assert ex["fixture"] == "FAKE_OPAQUE_IDS_ONLY" and ex["datasetVersion"] == sc.VERSION and mv.validate_manifest(ex)["errors"] == []
    assert any(r.get("cleanCategory") == "NATURAL_CLEAN_REPRESENTATIVE" for r in ex["images"]) and any(len(r["classSet"]) >= 2 for r in ex["images"])
    for path in (CORRECTION, CORRECTION_AGGREGATE, EXAMPLE):
        t = path.read_text(encoding="utf-8")
        assert not re.search(r"P\d{2}_C\d{2}", t) and "AppData" not in t and not re.search(r"[A-Za-z]:\\Users\\", t) and "@gmail" not in t
        for phrase in ("PRODUCTION_VALIDATED", "LIVE_READY", "NATURAL_POSITIVE_VALIDATED", "production-ready", "CONFIDENCE_CALIBRATED"):
            assert phrase not in t
