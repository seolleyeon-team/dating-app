"""CI tests for B3-L17B0 — prospective corpus collection feasibility, sealed-test quota planning, natural-positive incidence pilot design, budget / stopping rule.

Pure logic: no image, no model, no generation, no production data. Numbers here are planning arithmetic on fake records.
"""

import hashlib
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
AI = REPO / "lib" / "ai_recommend_model"
if str(AI) not in sys.path:
    sys.path.insert(0, str(AI))

import avatar_supervised_collection_budget as cb  # noqa: E402
import avatar_supervised_dataset_contract as sc  # noqa: E402
import avatar_supervised_incidence_pilot as ip  # noqa: E402
import avatar_supervised_sample_size as ss  # noqa: E402

DOCS = REPO / "docs" / "avatar-production"
PLAN = DOCS / "b3-l17b0-collection-feasibility-plan.md"
AGGREGATE = DOCS / "b3-l17b0-collection-feasibility-aggregate-v1.json"


def _region(**over):
    base = {"regionId": "r1", "class": "GRAPHICAL_LOGO", "bboxNormalized": [0.1, 0.1, 0.3, 0.3], "visibility": "clear", "sceneRelation": "overlay", "legibility": "not_applicable",
            "raterConfidence": "high", "annotationStatus": "agreed"}
    base.update(over)
    return base


def _pilot(oid, lin, regions=None, split="TRAIN_DEVELOPMENT", **over):
    rec = {"opaqueImageId": oid, "groupId": f"grp-{lin[4:]}", "lineageId": lin, "provenanceClass": "FUTURE_TRAINING_ELIGIBLE", "originKind": "NATURAL_GENERATED_OUTPUT", "collectionBatch": "pilot-0001",
           "annotationVersion": sc.ANNOTATION_SCHEMA_VERSION, "sha256": hashlib.sha256(oid.encode()).hexdigest(), "perceptualHash": "0" * 16, "width": 1024, "height": 1024,
           "regions": regions or [], "split": split, "lineageReservation": "DEVELOPMENT_ONLY", "sourceAuthority": "OWNER_AUTHORIZED_FIRST_PARTY"}
    if not regions:
        rec["cleanCategory"] = "NATURAL_CLEAN_REPRESENTATIVE"
    rec.update(over)
    return rec


# ---- 16. natural-positive incidence unknown marker


def test_b16_incidence_unknown_marker():
    assert cb.INCIDENCE_STATUS == ip.INCIDENCE_STATUS == "NATURAL_POSITIVE_INCIDENCE_UNKNOWN"
    e = cb.expected_generation(29, None)
    assert e["incidenceStatus"] == "NATURAL_POSITIVE_INCIDENCE_UNKNOWN" and e["expectedIndependentGroupsToGenerate"] is None and e["expectedGeneratedOutputs"] is None and e["generationPlanConfirmed"] is False
    c = cb.combined_expectation(29, {})
    assert c["incidenceStatus"] == "NATURAL_POSITIVE_INCIDENCE_UNKNOWN" and set(c["unknownClasses"]) == set(sc.CRITICAL_POSITIVE_STRATA) and c["expectedGeneratedOutputs"] is None
    agg = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    assert agg["incidenceStatus"] == "NATURAL_POSITIVE_INCIDENCE_UNKNOWN" and agg["budget"]["generationPlanConfirmed"] is False


def test_b18_no_direct_145_x_n_generation_plan():
    with pytest.raises(RuntimeError, match="NATURAL_POSITIVE_INCIDENCE_UNKNOWN"):
        cb.confirmed_generation_budget()
    with pytest.raises(RuntimeError):
        cb.confirmed_generation_budget({"status": "PILOT_NOT_RUN"})
    agg = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    assert agg["budget"]["withoutIncidence"]["expectedGeneratedOutputs"] is None and agg["budget"]["isExpectationOnly"] is True
    # 142 is split arithmetic for positives already in hand, not a generation count
    assert agg["budget"]["requiredCollectedPositiveGroupsFuturePool"] == ss.minimum_collected_groups(29)["minimumCollectedIndependentGroupsRequired"]
    assert cb.expected_generation(29, 0.01)["expectedIndependentGroupsToGenerate"] > 10 * cb.expected_generation(29, 0.10)["expectedIndependentGroupsToGenerate"] * 0.9


# ---- 17. pilot images never SEALED_TEST


def test_b17_pilot_images_never_sealed_test():
    assert ip.PILOT_DATA_STATUS == "PILOT_DISCOVERY_NOT_SEALED_TEST" and "SEALED_TEST" not in ip.PILOT_ALLOWED_PARTITIONS and ip.PILOT_LINEAGE_RESERVATION == "DEVELOPMENT_ONLY"
    good = _pilot("img-p1", "lin-a1")
    assert ip.validate_pilot_record(good) == []
    bad = _pilot("img-p2", "lin-a2", split="SEALED_TEST")
    errs = ip.validate_pilot_record(bad)
    assert any("PILOT_DISCOVERY_NOT_SEALED_TEST" in e for e in errs)
    assert any("SEALED_TEST" in e for e in ip.validate_pilot_record(_pilot("img-p3", "lin-a3", provenanceClass="FUTURE_HOLDOUT_ELIGIBLE", lineageReservation="SEALED_RESERVED", split="SEALED_TEST")))
    with pytest.raises(ValueError):
        ip.incidence_report([good, bad])
    plan = ip.pilot_plan("SMALL")
    assert plan["sealedTestEligible"] is False and plan["dataStatus"] == "PILOT_DISCOVERY_NOT_SEALED_TEST"


# ---- 18 (label). pilot uses no model score


def test_b18_pilot_uses_no_model_score():
    assert ip.PILOT_LABEL_CONTRACT["blindedHumanLabelsOnly"] is True and ip.PILOT_LABEL_CONTRACT["modelScoreFiltering"] is False
    assert set(ip.PILOT_LABEL_CONTRACT["prohibitedInputs"]) >= {"CLIP", "DINOv2", "Grounding DINO", "Florence", "OWLv2", "future supervised model", "model score filtering"}
    for key in ("clipScore", "dinov2Score", "groundingDinoBox", "florenceResult", "owlv2Result", "supervisedModelScore", "detectorScore"):
        rec = _pilot("img-x", "lin-x1", **{key: 0.9})
        assert any(key in e for e in ip.check_pilot_label_input(rec)), key
        with pytest.raises(ValueError, match="blinded human labels only"):
            ip.incidence_report([rec])
    src = inspect.getsource(ip) + inspect.getsource(cb)
    for banned in ("torch", "from_pretrained", ".fit(", "import openai", "AzureOpenAI", "images.generate", "import requests", "google.cloud", "storage.Client"):
        assert banned not in src, banned


# ---- 19-20. production-user source prohibited; source photos remain restricted


def test_b19_production_user_source_prohibited():
    assert ip.SOURCE_CATEGORIES == ("OWNER_VOLUNTEER_REAL_SOURCE", "OWNER_AUTHORIZED_SYNTHETIC_SOURCE", "PRODUCTION_USER_SOURCE")
    assert ip.SOURCE_CATEGORY_POLICY["PRODUCTION_USER_SOURCE"]["allowedInPilot"] is False
    assert any("prohibited" in e for e in ip.check_pilot_source("PRODUCTION_USER_SOURCE"))
    with pytest.raises(ValueError):
        ip.natural_artifact_claim("PRODUCTION_USER_SOURCE")
    assert any("PRODUCTION_USER_SOURCE" in e for e in ip.validate_batch({f: "x" for f in ip.BATCH_PROVENANCE_FIELDS} | {"sourceAuthorityClass": "PRODUCTION_USER_SOURCE"}))
    assert sc.production_mining_allowed() is False and sc.PRODUCTION_ACCESS == {"firestoreScans": 0, "storageBulkList": 0, "userDataMutation": 0, "userCorpusExport": 0}
    agg = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    assert agg["productionAccess"] == sc.PRODUCTION_ACCESS and agg["productionUserDataRequired"] == "NO" and agg["productionWrites"] == 0


def test_b20_source_photos_remain_restricted():
    for cat in ("OWNER_VOLUNTEER_REAL_SOURCE", "OWNER_AUTHORIZED_SYNTHETIC_SOURCE"):
        assert ip.SOURCE_CATEGORY_POLICY[cat]["sourcePhotoClass"] == "RESTRICTED_SOURCE_NOT_MODEL_DATA" and ip.SOURCE_CATEGORY_POLICY[cat]["datasetRecord"] == "generated output only"
    assert ip.check_pilot_source("OWNER_VOLUNTEER_REAL_SOURCE") and ip.check_pilot_source("OWNER_VOLUNTEER_REAL_SOURCE", consent_authority="consent-record-ref") == []
    assert ip.check_pilot_source("OWNER_AUTHORIZED_SYNTHETIC_SOURCE") == []
    errs = ip.validate_pilot_record(_pilot("img-s", "lin-s1", originKind="SOURCE_PHOTO", provenanceClass="RESTRICTED_SOURCE_NOT_MODEL_DATA"))
    assert any("RESTRICTED_SOURCE_NOT_MODEL_DATA" in e for e in errs)


# ---- 21. same source lineage outputs = one group


def test_b21_same_lineage_outputs_one_group():
    outs = [_pilot(f"img-{i}", "lin-one") for i in range(20)] + [_pilot("img-z", "lin-two")]
    assert ip.independent_lineage_count(outs) == {"generatedOutputs": 21, "independentGroups": 2}
    assert ip.lineage_groups(outs)["lin-one"] == [f"img-{i}" for i in range(20)]
    assert cb.independent_groups(1, 20) == {"sourceLineages": 1, "outputsPerLineage": 20, "generatedOutputs": 20, "independentGroups": 1, "unit": sc.STATISTICAL_UNIT,
                                            "rule": "same source lineage regeneration = same group; outputs never count as independent evaluation units"}
    assert ip.LINEAGE_DEFINITION["regeneration"] == "same lineage regeneration = same group" and ip.validate_lineage_id("P01") and ip.validate_lineage_id("lin-0a1b") == []
    rep = ip.incidence_report([_pilot(f"img-{i}", "lin-one", regions=[_region()]) for i in range(20)])
    assert rep["totalIndependentGroups"] == 1 and rep["totalGeneratedOutputs"] == 20 and rep["perClass"]["GRAPHICAL_LOGO"]["naturalPositiveGroups"] == 1


# ---- 22. synthetic-source domain limitation


def test_b22_synthetic_source_domain_limitation():
    c = ip.natural_artifact_claim("OWNER_AUTHORIZED_SYNTHETIC_SOURCE")
    assert c == {"artifactKind": "NATURAL_GENERATION_ARTIFACT", "domainMarker": "SYNTHETIC_SOURCE_DOMAIN_LIMITATION", "realUserDomainValidated": False, "forbiddenClaim": "REAL_USER_SOURCE_DOMAIN_VALIDATED"}
    r = ip.natural_artifact_claim("OWNER_VOLUNTEER_REAL_SOURCE")
    assert r["domainMarker"] is None and r["realUserDomainValidated"] is False
    assert ip.SOURCE_CATEGORY_POLICY["OWNER_AUTHORIZED_SYNTHETIC_SOURCE"]["realUserDomainEquivalent"] is False
    for path in (PLAN, AGGREGATE):
        text = path.read_text(encoding="utf-8")
        assert "SYNTHETIC_SOURCE_DOMAIN_LIMITATION" in text
        for line in text.splitlines():
            if "REAL_USER_SOURCE_DOMAIN_VALIDATED" in line:
                assert "never" in line.lower() or "forbidden" in line.lower(), line     # only ever named as the forbidden claim


# ---- 23-24. fixed paid-generation cap required; automatic paid extension prohibited


def test_b23_fixed_paid_generation_cap_required():
    plan = ip.pilot_plan("MEDIUM")
    assert ip.validate_stopping_rule(plan) == [] and plan["fixedGenerationAttemptCap"] == plan["sizes"]["totalGenerationAttempts"] > 0
    assert ip.STOPPING_RULE["fixedGenerationAttemptCap"] is True and ip.STOPPING_RULE["modelScoreAdaptiveContinuation"] is False and ip.STOPPING_RULE["frozenBeforeStart"] is True
    assert ip.validate_stopping_rule({"stoppingRule": ip.STOPPING_RULE})                       # no cap -> error
    assert ip.validate_stopping_rule({"fixedGenerationAttemptCap": 40, "stoppingRule": dict(ip.STOPPING_RULE, modelScoreAdaptiveContinuation=True)})
    assert re.fullmatch(r"[0-9a-f]{64}", plan["planDigest"]) and plan["planDigest"] == ip.pilot_plan("MEDIUM")["planDigest"]


def test_b24_automatic_paid_extension_prohibited():
    plan = ip.pilot_plan("SMALL")
    assert ip.STOPPING_RULE["automaticPaidExtension"] is False and ip.STOPPING_RULE["agentMayIncreaseCap"] is False and ip.STOPPING_RULE["extensionRequires"] == "explicit owner re-approval of a new cap"
    req = ip.request_extension(plan, {"GRAPHICAL_LOGO": 0, "OVERLAY_WATERMARK": 5, "BRAND_TEXT_OR_MARK": 3, "GENERATIVE_TEXT_ARTIFACT": 2})
    assert req["trigger"] is True and req["status"] == "OWNER_REAPPROVAL_REQUIRED" and req["executed"] is False and req["newCap"] is None and set(req["classesBelowFloor"]) == {"GRAPHICAL_LOGO", "GENERATIVE_TEXT_ARTIFACT"}
    assert ip.request_extension(plan, {c: 3 for c in sc.CRITICAL_POSITIVE_STRATA})["status"] == "NO_EXTENSION_TRIGGER"
    assert ip.validate_stopping_rule({"fixedGenerationAttemptCap": 40, "stoppingRule": dict(ip.STOPPING_RULE, automaticPaidExtension=True)})
    with pytest.raises(RuntimeError, match="never executed"):
        ip.execute_generation("SMALL")


# ---- 25-26. incidence helper uses group unit; budget helper separates groups vs outputs


def test_b25_incidence_helper_uses_group_unit():
    recs = []
    for i in range(10):
        recs += [_pilot(f"img-{i}-{j}", f"lin-{i:02d}", regions=[_region()] if (i < 3 and j == 0) else None) for j in range(4)]
    rep = ip.incidence_report(recs)
    assert rep["unit"] == "independent lineage (group)" and rep["totalIndependentGroups"] == 10 and rep["totalGeneratedOutputs"] == 40
    g = rep["perClass"]["GRAPHICAL_LOGO"]
    assert g["naturalPositiveGroups"] == 3 and g["incidenceEstimate"] == 0.3 and g["exactBinomialInterval95"] == (pytest.approx(0.0667, abs=1e-3), pytest.approx(0.6525, abs=1e-3)) and g["feasibilityFloorMet"] is True
    assert rep["perClass"]["OVERLAY_WATERMARK"]["naturalPositiveGroups"] == 0 and rep["perClass"]["OVERLAY_WATERMARK"]["exactBinomialInterval95"] == (0.0, pytest.approx(0.3085, abs=1e-3))
    assert rep["cleanRepresentativeGroups"] == 7 and rep["uncertainGroups"] == 0 and rep["humanLabelsOnly"] is True and rep["status"] == "PILOT_COMPLETED_HUMAN_LABELLED"
    assert ip.incidence_report([])["status"] == "PILOT_NOT_RUN"


def test_b26_budget_helper_separates_groups_vs_outputs():
    e = cb.expected_generation(29, 0.10, outputs_per_lineage=4)
    assert e["expectedIndependentGroupsToGenerate"] * 4 == e["expectedGeneratedOutputs"] and e["isExpectationOnly"] is True and e["guaranteed"] is False and e["generationPlanConfirmed"] is False
    assert e["requiredCollectedPositiveGroups"] == ss.minimum_collected_groups(29)["minimumCollectedIndependentGroupsRequired"] and e["expectedIndependentGroupsToGenerate"] == -(-e["requiredCollectedPositiveGroups"] // 0.10)
    risk = e["upperBudgetRisk"]
    assert risk["lineagesFor95pctSufficiency"] > e["expectedIndependentGroupsToGenerate"] and 0.0 < risk["shortfallProbabilityAtExpected"] < 1.0
    assert cb.expected_generation(29, 0.10, pool="SEALED_RESERVED")["requiredCollectedPositiveGroups"] == 29
    rows = cb.risk_table(29, incidences=(0.01, 0.10))
    assert rows[0]["expectedLineages"] > rows[1]["expectedLineages"] and all(r["expectedOutputs"] == r["expectedLineages"] * 4 for r in rows)
    c = cb.combined_expectation(29, {cls: 0.10 for cls in sc.CRITICAL_POSITIVE_STRATA} | {"GRAPHICAL_LOGO": 0.02})
    assert c["dominantStratum"] == "GRAPHICAL_LOGO" and c["generationPlanConfirmed"] is False
    with pytest.raises(ValueError):
        cb.expected_generation(29, 0.0)
    with pytest.raises(RuntimeError):
        cb.training_size_from_budget(1000)


# ---- 27. provider revision recorded


def test_b27_provider_revision_recorded():
    assert ip.BATCH_PROVENANCE_FIELDS == ("batchId", "sourceAuthorityClass", "generationProvider", "generationModelRevision", "promptContractDigest", "generationDate", "consentAuthority", "retentionRule")
    b1 = {"batchId": "pilot-0001", "sourceAuthorityClass": "OWNER_AUTHORIZED_SYNTHETIC_SOURCE", "generationProvider": "azure", "generationModelRevision": "rev-a", "promptContractDigest": "0" * 12, "generationDate": "2026-10-01", "consentAuthority": "owner", "retentionRule": "programme"}
    assert ip.validate_batch(b1) == [] and any("generationModelRevision" in e for e in ip.validate_batch({k: v for k, v in b1.items() if k != "generationModelRevision"}))
    b2 = dict(b1, batchId="batch-0002", generationModelRevision="rev-b")
    recs = [_pilot("img-1", "lin-01"), _pilot("img-2", "lin-02", collectionBatch="batch-0002", split="SEALED_TEST", provenanceClass="FUTURE_HOLDOUT_ELIGIBLE", lineageReservation="SEALED_RESERVED"),
            _pilot("img-3", "lin-03", split="SEALED_TEST", provenanceClass="FUTURE_HOLDOUT_ELIGIBLE", lineageReservation="SEALED_RESERVED")]
    d = ip.revision_distribution(recs, [b1, b2])
    assert d["overall"] == {"azure@rev-a": 2, "azure@rev-b": 1} and d["sealedTest"] == {"azure@rev-a": 1, "azure@rev-b": 1} and d["sealedSpansMultipleRevisions"] is True and d["policy"]["hideRevisionChange"] is False
    assert ip.CANONICAL_PROVIDER["modelId"] == "azure_gpt_image_2"


# ---- 28-30. no generation in this task; no training / inference; aggregate-only repo artifacts


def test_b28_no_generation_in_this_task():
    assert ip.PAID_GENERATION == {"executedInThisTask": False, "azureCalls": 0, "openaiImageCalls": 0, "requiresExplicitOwnerApproval": True, "automaticExecution": False, "status": "PLAN_ONLY_NOT_EXECUTED"}
    agg = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    assert agg["imageGeneration"] == {"azure": 0, "openaiImage": 0} and agg["paidGeneration"]["executedInThisTask"] is False and agg["execution"] == "PLAN_ONLY_NOT_EXECUTED"
    for name in ("SMALL", "MEDIUM", "LARGE"):
        assert agg["pilot"]["options"][name]["cost"]["status"] == "COST_NOT_VERIFIED"
    assert ip.cost_estimate("SMALL")["status"] == "COST_NOT_VERIFIED" and ip.cost_estimate("SMALL", 0.1)["status"] == "COST_NOT_VERIFIED"
    assert ip.cost_estimate("SMALL", 0.1, "example-source", "2026-09-19")["estimatedUsd"] == pytest.approx(4.8)


def test_b29_no_training_or_inference():
    agg = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    assert agg["modelTraining"] == 0 and agg["inference"] == 0 and agg["noTraining"] == sc.NO_TRAINING and agg["trainingSize"] == "TRAINING_SIZE_NOT_YET_JUSTIFIED"
    assert agg["contractVerdict"] == "SUPERVISED_DATA_COLLECTION_CONTRACT_READY_AFTER_QUOTA_CORRECTION" and agg["priorStatus"]["B3_L16A"] == "DINOV2_VERIFIER_FAILED_DEVELOPMENT"
    assert agg["priorStatus"]["STOP_RULE"] == "FROZEN_VERIFIER_REPRESENTATION_SEARCH_STOP_RULE" and agg["priorStatus"]["TEXT_POLICY_GAP"] == "unresolved"


def test_b30_aggregate_only_repo_artifacts():
    agg = json.loads(AGGREGATE.read_text(encoding="utf-8"))

    def keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield k
                yield from keys(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from keys(v)
    assert not ({"sha256", "perceptualHash", "regions", "bboxNormalized", "path", "opaqueImageId", "lineageId", "uid", "email"} & set(keys(agg)))
    assert agg["pilotVersion"] == "FIRST_PARTY_NATURAL_MARK_INCIDENCE_PILOT_V1" and agg["planVersion"] == "B3_L17B0_COLLECTION_FEASIBILITY_V1" and agg["contractDigestPrefix"] == sc.contract_digest()[:12]
    text = PLAN.read_text(encoding="utf-8")
    for token in ("FIRST_PARTY_NATURAL_MARK_INCIDENCE_PILOT_V1", "NATURAL_POSITIVE_INCIDENCE_UNKNOWN", "PILOT_DISCOVERY_NOT_SEALED_TEST", "OWNER_VOLUNTEER_REAL_SOURCE", "OWNER_AUTHORIZED_SYNTHETIC_SOURCE",
                  "PRODUCTION_USER_SOURCE", "SYNTHETIC_SOURCE_DOMAIN_LIMITATION", "COST_NOT_VERIFIED", "SEALED_TEST_ELIGIBLE_SOURCE_LINEAGES", "HARD_NEGATIVE_STRESS_FALSE_REVIEW_RATE", "TRAINING_SIZE_NOT_YET_JUSTIFIED",
                  "SMALL", "MEDIUM", "LARGE", sc.contract_digest()[:12], "azure_gpt_image_2"):
        assert token in text, token
    for path in (PLAN, AGGREGATE):
        t = path.read_text(encoding="utf-8")
        assert not re.search(r"P\d{2}_C\d{2}", t) and "AppData" not in t and not re.search(r"[A-Za-z]:\\Users\\", t) and "@gmail" not in t
        for phrase in ("PRODUCTION_VALIDATED", "LIVE_READY", "NATURAL_POSITIVE_VALIDATED", "production-ready", "CONFIDENCE_CALIBRATED", "REAL_USER_SOURCE_DOMAIN_VALIDATED: yes"):
            assert phrase not in t


# ---- extra: size options, sealed lineage reservation, sealed per-class quota linkage


def test_bx_three_size_options_for_owner_decision():
    opts = {n: ip.size_option(n) for n in ("SMALL", "MEDIUM", "LARGE")}
    assert opts["SMALL"]["independentSourceLineages"] < opts["MEDIUM"]["independentSourceLineages"] < opts["LARGE"]["independentSourceLineages"]
    for o in opts.values():
        assert o["totalGenerationAttempts"] == o["independentSourceLineages"] * o["generationAttemptsPerLineage"] == o["generatedOutputs"] and o["independentGroups"] == o["independentSourceLineages"]
        assert {"estimatedLabelingWorkload", "estimatedStorageMbUpperBound", "observability", "limitations", "cost", "fixedGenerationAttemptCap"} <= set(o) and o["cost"]["status"] == "COST_NOT_VERIFIED"
        assert 0 < o["observability"]["zeroObservedIncidenceUpperBound95"] < 1 and o["observability"]["probabilityAtLeastOnePositiveLineage"]["0.01"] < o["observability"]["probabilityAtLeastOnePositiveLineage"]["0.2"]
    assert opts["LARGE"]["observability"]["zeroObservedIncidenceUpperBound95"] < opts["SMALL"]["observability"]["zeroObservedIncidenceUpperBound95"]
    with pytest.raises(ValueError):
        ip.size_option("HUGE")


def test_bx_sealed_lineage_reservation_prospective():
    ids = [f"lin-{i:03x}" for i in range(50)]
    r = ip.reserve_sealed_lineages(ids, 12)
    assert len(r["SEALED_TEST_ELIGIBLE_SOURCE_LINEAGES"]) == 12 and not set(r["SEALED_TEST_ELIGIBLE_SOURCE_LINEAGES"]) & set(r["DEVELOPMENT_LINEAGES"]) and r == ip.reserve_sealed_lineages(list(reversed(ids)), 12)
    assert r["reservedLineageReservation"] == "SEALED_RESERVED" and r["developmentLineageReservation"] == "DEVELOPMENT_ONLY" and r["reservedProvenanceClass"] == "FUTURE_HOLDOUT_ELIGIBLE"
    lid = r["SEALED_TEST_ELIGIBLE_SOURCE_LINEAGES"][0]
    assert ip.check_lineage_reuse(lid, development_lineages=[lid], reserved_lineages=[lid]) and ip.check_lineage_reuse(lid, development_lineages=[], reserved_lineages=[lid]) == []
    with pytest.raises(TypeError):
        ip.reserve_sealed_lineages(ids, 12, overrides={"lin-000": True})
    with pytest.raises(ValueError):
        ip.reserve_sealed_lineages(ids + ["lin-000"], 5)


def test_bx_sealed_quota_and_representative_clean_linked_to_contract():
    agg = json.loads(AGGREGATE.read_text(encoding="utf-8"))
    assert agg["sealedQuota"] == sc.SEALED_QUOTA and agg["representativeCleanSealedQuota"] == {"required": 29, "aspirational": 59, "minimumCollection": ss.minimum_collected_groups(29, stratum="NATURAL_CLEAN_REPRESENTATIVE")["minimumCollectedIndependentGroupsRequired"]}
    assert agg["hardNegativeStress"]["countsTowardRepresentativeClean"] is False and agg["hardNegativeStress"]["status"] == "STRESS_SET_DEFINED_NOT_COLLECTED"
    assert agg["budget"]["requiredCollectedPositiveGroupsReservedPool"] == 29 and agg["budget"]["targetCountKind"] == "EVALUATION_ELIGIBLE_SEALED_GROUPS"
    assert agg["reservationRules"]["name"] == "SEALED_TEST_ELIGIBLE_SOURCE_LINEAGES"
