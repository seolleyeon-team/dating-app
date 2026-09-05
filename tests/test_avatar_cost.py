import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.cost import (
    AvatarCostConfig,
    aggregate_avatar_job_costs,
    build_batch_cost_document,
    build_default_scenario_report,
    build_job_cost_document,
    estimate_batch_cost,
    estimate_job_cost,
    evaluate_cost_guard,
)
from avatar_generation.job_lease import AvatarJobLeaseConfig, claim_next_avatar_job


NOW = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
PRIVATE_REF = "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg"


class FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class FakeDocRef:
    def __init__(self, store, collection, doc_id):
        self.store = store
        self.collection = collection
        self.doc_id = doc_id

    def get(self, **_kwargs):
        return FakeSnapshot(self.doc_id, self.store.get(self.collection, {}).get(self.doc_id))

    def set(self, data, merge=True):
        collection = self.store.setdefault(self.collection, {})
        if merge and self.doc_id in collection:
            collection[self.doc_id].update(data)
        else:
            collection[self.doc_id] = dict(data)

    def update(self, data):
        self.set(data, merge=True)


class FakeCollection:
    def __init__(self, store, name):
        self.store = store
        self.name = name

    def document(self, doc_id):
        return FakeDocRef(self.store, self.name, doc_id)

    def stream(self):
        for doc_id, data in self.store.get(self.name, {}).items():
            yield FakeSnapshot(doc_id, data)


class FakeFirestore:
    def __init__(self, data):
        self.data = data

    def collection(self, name):
        return FakeCollection(self.data, name)


def _config(**overrides):
    values = {
        "gpu_usd_per_second": 0.10,
        "cpu_usd_per_vcpu_second": 0.01,
        "memory_usd_per_gib_second": 0.001,
        "gpu_zonal_redundancy": False,
        "vcpu": 2.0,
        "memory_gib": 8.0,
        "pricing_version": "test-pricing",
        "daily_alert_usd": 10.0,
        "monthly_alert_usd": 100.0,
        "hard_daily_generation_limit": 10,
        "hard_monthly_generation_limit": 100,
        "kill_switch_enabled": False,
        "enforce_budget": True,
    }
    values.update(overrides)
    return AvatarCostConfig(**values)


def _job(job_id="job_1", status="queued", **overrides):
    doc = {
        "jobId": job_id,
        "uid": "u1",
        "status": status,
        "sourcePhotoIds": ["src_001"],
        "sourcePhotoRefs": [PRIVATE_REF],
        "candidateCount": 4,
        "createdAt": NOW,
        "processing": {"attempt": 0},
    }
    doc.update(overrides)
    return doc


def _private_media():
    return {
        "photoConsent": {
            "avatarGeneration": True,
            "profileDisplayOriginalPhoto": False,
        },
        "sourcePhotos": [
            {
                "photoId": "src_001",
                "gcsUri": PRIVATE_REF,
                "status": "active",
                "purpose": {"avatarGeneration": True},
            }
        ],
    }


def _firestore(jobs):
    return FakeFirestore({"avatarJobs": jobs, "userPrivateMedia": {"u1": _private_media()}})


def _clear_cost_env(monkeypatch):
    for name in (
        "CLOUD_RUN_L4_GPU_USD_PER_SECOND",
        "CLOUD_RUN_CPU_USD_PER_VCPU_SECOND",
        "CLOUD_RUN_MEMORY_USD_PER_GIB_SECOND",
        "CLOUD_RUN_GPU_ZONAL_REDUNDANCY",
        "CLOUD_RUN_VCPU",
        "CLOUD_RUN_MEMORY_GIB",
        "CLOUD_RUN_PRICING_VERSION",
        "AVATAR_COST_ALERT_DAILY_USD",
        "AVATAR_COST_ALERT_MONTHLY_USD",
        "AVATAR_COST_HARD_DAILY_GENERATION_LIMIT",
        "AVATAR_COST_HARD_MONTHLY_GENERATION_LIMIT",
        "AVATAR_COST_KILL_SWITCH_ENABLED",
        "AVATAR_COST_ENFORCE_BUDGET",
    ):
        monkeypatch.delenv(name, raising=False)


def test_default_config_matches_pr7_prompt_assumptions(monkeypatch):
    _clear_cost_env(monkeypatch)

    config = AvatarCostConfig.from_env()

    assert config.gpu_usd_per_second == 0.0001867
    assert config.cpu_usd_per_vcpu_second == 0.000018
    assert config.memory_usd_per_gib_second == 0.000002
    assert config.vcpu == 4
    assert config.memory_gib == 16
    assert config.pricing_version == "cloud_run_l4_2026_05"
    assert config.daily_alert_usd == 10
    assert config.monthly_alert_usd == 200
    assert config.hard_daily_generation_limit == 500
    assert config.hard_monthly_generation_limit == 10000


def test_production_cost_config_enforces_budget_by_default(monkeypatch):
    _clear_cost_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")

    config = AvatarCostConfig.from_env()

    assert config.enforce_budget is True


def test_default_1000_user_scenario_has_nonzero_cost(monkeypatch):
    _clear_cost_env(monkeypatch)

    scenario = build_default_scenario_report()

    assert scenario["users"] == 1000
    assert scenario["candidateCount"] == 4000
    assert scenario["estimatedCost"]["usd"] == 12.48
    assert scenario["estimatedCost"]["pricingVersion"] == "cloud_run_l4_2026_05"


def test_azure_formula_charges_cpu_and_memory_but_not_retired_generation_gpu():
    normal = estimate_job_cost(duration_seconds=10, config=_config())
    redundant = estimate_job_cost(
        duration_seconds=10,
        config=_config(gpu_zonal_redundancy=True),
    )

    assert normal.usd == 0.28
    assert normal.breakdown["gpuUsd"] == 0.0
    assert normal.breakdown["cpuUsd"] == 0.2
    assert normal.breakdown["memoryUsd"] == 0.08
    assert redundant.usd == 0.28
    assert redundant.breakdown["gpuZonalRedundancy"] is True
    assert redundant.pricing_version == "test-pricing"


def test_batch_and_job_cost_aggregation_use_runtime_metadata():
    jobs = [
        _job(job_id="a", status="preview_ready", candidateCount=4, processing={"durationSeconds": 10}),
        _job(job_id="b", status="failed", candidateCount=2, processing={"durationSeconds": 5}),
    ]

    aggregate = aggregate_avatar_job_costs(jobs, now=NOW, config=_config())
    batch = estimate_batch_cost(jobs, duration_seconds=12, config=_config())

    assert aggregate.generated_count == 2
    assert aggregate.candidate_count == 6
    assert aggregate.total_usd == 0.42
    assert aggregate.daily_count == 2
    assert aggregate.monthly_count == 2
    assert batch.job_count == 2
    assert batch.candidate_count == 6
    assert batch.total_cost.usd == 0.336


def test_cost_aggregation_reads_nested_worker_cost_document():
    jobs = [
        _job(
            job_id="approved",
            status="approved",
            candidateCount=4,
            cost={
                "estimatedUsd": 7.5,
                "totalWorkerSeconds": 12,
                "secondsByStage": {"total_worker_seconds": 12},
            },
        ),
        _job(
            job_id="no_preview",
            status="no_previewable_candidates",
            candidateCount=2,
            cost={"estimatedUsd": 1.0, "totalWorkerSeconds": 4},
        ),
    ]

    aggregate = aggregate_avatar_job_costs(jobs, now=NOW, config=_config())

    assert aggregate.generated_count == 2
    assert aggregate.candidate_count == 6
    assert aggregate.total_usd == 8.5


def test_job_and_batch_cost_documents_expose_persistable_worker_fields():
    jobs = [_job(job_id=f"job_{index}", processing={"durationSeconds": 10}) for index in range(2)]

    job_doc = build_job_cost_document(duration_seconds=10, config=_config(), estimated_at=NOW)
    batch_doc = build_batch_cost_document(jobs, duration_seconds=12, config=_config(), estimated_at=NOW)

    assert job_doc["costEstimateUsd"] == 0.28
    assert job_doc["costEstimate"]["durationSeconds"] == 10
    assert job_doc["costEstimate"]["pricingVersion"] == "test-pricing"
    assert job_doc["costEstimate"]["estimatedAt"] == NOW
    assert batch_doc["batchCostEstimateUsd"] == 0.336
    assert batch_doc["batchCostEstimate"]["jobCount"] == 2
    assert batch_doc["batchCostEstimate"]["savingsUsd"] == 0.224
    assert batch_doc["batchCostEstimate"]["pricingVersion"] == "test-pricing"


def test_daily_and_monthly_quota_guard_blocks_when_hard_limits_reached():
    fs = _firestore(
        {
            "today": _job(job_id="today", status="preview_ready", createdAt=NOW),
            "month": _job(job_id="month", status="failed", createdAt=NOW - timedelta(days=3)),
            "next": _job(job_id="next", status="queued", createdAt=NOW),
        }
    )

    daily = evaluate_cost_guard(fs, now=NOW, config=_config(hard_daily_generation_limit=1))
    monthly = evaluate_cost_guard(fs, now=NOW, config=_config(hard_monthly_generation_limit=2))

    assert daily.allowed is False
    assert daily.reason == "daily_generation_quota_exceeded"
    assert monthly.allowed is False
    assert monthly.reason == "monthly_generation_quota_exceeded"


def test_budget_guard_blocks_only_when_enforced():
    fs = _firestore(
        {
            "done": _job(
                job_id="done",
                status="preview_ready",
                createdAt=NOW,
                costEstimateUsd=12.5,
            ),
            "next": _job(job_id="next", status="queued", createdAt=NOW),
        }
    )

    enforced = evaluate_cost_guard(fs, now=NOW, config=_config(daily_alert_usd=10.0, enforce_budget=True))
    advisory = evaluate_cost_guard(fs, now=NOW, config=_config(daily_alert_usd=10.0, enforce_budget=False))

    assert enforced.allowed is False
    assert enforced.reason == "daily_budget_exceeded"
    assert advisory.allowed is True
    assert advisory.alerts[0]["metric"] == "dailyCostUsd"


def test_kill_switch_prevents_claim_without_mutating_job(monkeypatch):
    monkeypatch.setenv("AVATAR_COST_KILL_SWITCH_ENABLED", "true")
    fs = _firestore({"job_1": _job()})

    lease = claim_next_avatar_job(
        fs,
        worker_id="worker-a",
        now=NOW,
        config=AvatarJobLeaseConfig(lease_seconds=120, max_scan=10),
    )

    assert lease is None
    assert fs.data["avatarJobs"]["job_1"]["status"] == "queued"
    assert fs.data["avatarJobs"]["job_1"]["processing"]["attempt"] == 0


def test_quota_guard_prevents_claim_without_mutating_job(monkeypatch):
    monkeypatch.setenv("AVATAR_COST_ENFORCE_BUDGET", "true")
    monkeypatch.setenv("AVATAR_COST_HARD_DAILY_GENERATION_LIMIT", "1")
    fs = _firestore(
        {
            "done": _job(job_id="done", status="preview_ready", createdAt=NOW),
            "job_1": _job(job_id="job_1", status="queued", createdAt=NOW),
        }
    )

    lease = claim_next_avatar_job(
        fs,
        worker_id="worker-a",
        now=NOW,
        config=AvatarJobLeaseConfig(lease_seconds=120, max_scan=10),
    )

    assert lease is None
    assert fs.data["avatarJobs"]["job_1"]["status"] == "queued"
    assert fs.data["avatarJobs"]["job_1"]["processing"]["attempt"] == 0


def test_cost_report_fixture_and_dry_run(tmp_path, monkeypatch):
    script_path = REPO_ROOT / "scripts" / "avatar_cost_report.py"
    spec = importlib.util.spec_from_file_location("avatar_cost_report", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    fixture = tmp_path / "jobs.json"
    output = tmp_path / "report.json"
    fixture.write_text(
        json.dumps(
            {
                "jobs": [
                    _job(job_id="done", status="preview_ready", processing={"durationSeconds": 10}),
                    _job(job_id="queued", status="queued"),
                ]
            },
            default=str,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLOUD_RUN_L4_GPU_USD_PER_SECOND", "0.10")
    monkeypatch.setenv("CLOUD_RUN_CPU_USD_PER_VCPU_SECOND", "0.01")
    monkeypatch.setenv("CLOUD_RUN_MEMORY_USD_PER_GIB_SECOND", "0.001")
    monkeypatch.setenv("CLOUD_RUN_VCPU", "2")
    monkeypatch.setenv("CLOUD_RUN_MEMORY_GIB", "8")

    result = module.main(
        [
            "--fixture_json",
            str(fixture),
            "--date",
            "2026-05-14",
            "--month",
            "2026-05",
            "--dry_run",
            "--output_report_json",
            str(output),
        ]
    )

    assert result == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["dryRun"] is True
    assert report["actuals"]["generatedCount"] == 1
    assert report["scenario"]["users"] == 1000
    assert report["scenario"]["candidatesPerUser"] == 4
    assert report["scenario"]["candidateCount"] == 4000


def test_cost_report_dry_run_without_fixture_uses_default_assumptions(tmp_path, monkeypatch):
    _clear_cost_env(monkeypatch)
    script_path = REPO_ROOT / "scripts" / "avatar_cost_report.py"
    spec = importlib.util.spec_from_file_location("avatar_cost_report", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    output = tmp_path / "report.json"

    result = module.main(["--dry_run", "--output_report_json", str(output)])

    assert result == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["actuals"]["generatedCount"] == 0
    assert report["pricing"]["version"] == "cloud_run_l4_2026_05"
    assert report["scenario"]["estimatedCost"]["usd"] == 12.48


def test_generation_cost_report_fixture_includes_timing_percentiles_and_unit_cost(tmp_path, monkeypatch):
    _clear_cost_env(monkeypatch)
    script_path = REPO_ROOT / "scripts" / "avatar_generation_cost_report.py"
    spec = importlib.util.spec_from_file_location("avatar_generation_cost_report", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    fixture = tmp_path / "jobs.json"
    output = tmp_path / "generation_report.json"
    fixture.write_text(
        json.dumps(
            {
                "jobs": [
                    _job(
                        job_id="approved",
                        status="approved",
                        cost={
                            "estimatedUsd": 2.5,
                            "totalWorkerSeconds": 10,
                            "secondsByStage": {
                                "generation_seconds": 6,
                                "upload_seconds": 1,
                                "total_worker_seconds": 10,
                            },
                        },
                    ),
                    _job(
                        job_id="preview",
                        status="preview_ready",
                        cost={
                            "estimatedUsd": 2.5,
                            "totalWorkerSeconds": 20,
                            "secondsByStage": {
                                "generation_seconds": 12,
                                "upload_seconds": 1.5,
                                "total_worker_seconds": 20,
                            },
                        },
                    ),
                    _job(
                        job_id="failed",
                        status="failed",
                        cost={
                            "estimatedUsd": 5.0,
                            "totalWorkerSeconds": 30,
                            "secondsByStage": {
                                "generation_seconds": 20,
                                "upload_seconds": 2,
                                "total_worker_seconds": 30,
                            },
                        },
                    ),
                ]
            },
            default=str,
        ),
        encoding="utf-8",
    )

    result = module.main(
        [
            "--fixture_json",
            str(fixture),
            "--dry_run",
            "--output_report_json",
            str(output),
        ]
    )

    assert result == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["dryRun"] is True
    assert report["actuals"]["generatedCount"] == 3
    assert report["timing"]["totalWorkerSeconds"]["p50"] == 20
    assert report["timing"]["totalWorkerSeconds"]["p95"] == 30
    assert report["timing"]["stages"]["generationSeconds"]["p95"] == 20
    assert report["unitEconomics"]["approvedCount"] == 1
    assert report["unitEconomics"]["estimatedUsd"] == 10.0
    assert report["unitEconomics"]["costPerApprovedAvatarUsd"] == 10.0


def test_internal_canary_report_redacts_private_refs_and_summarizes_payload(tmp_path):
    script_path = REPO_ROOT / "scripts" / "avatar_internal_canary_report.py"
    spec = importlib.util.spec_from_file_location("avatar_internal_canary_report", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    fixture = tmp_path / "canary.json"
    output = tmp_path / "canary_report.json"
    fixture.write_text(
        json.dumps(
            {
                "users": {
                    "uid-a": {
                        "avatar": {
                            "status": "approved",
                            "approvedAvatarUrl": "https://cdn.example/avatar.png",
                            "approvedCandidateId": "candidate-a",
                        }
                    }
                },
                "userPrivateMedia": {
                    "uid-a": {
                        "sourcePhotos": [
                            {
                                "photoId": "photo-a",
                                "sha256": "abcdef1234567890",
                                "gcsUri": PRIVATE_REF
                                + "?X-Goog-Signature=secret",
                            }
                        ]
                    }
                },
                "avatarJobs": {
                    "job-a": {
                        "uid": "uid-a",
                        "jobId": "job-a",
                        "status": "preview_ready",
                        "createdAt": NOW.isoformat(),
                        "sourcePhotoIds": ["photo-a"],
                        "sourcePhotoRefs": [PRIVATE_REF],
                        "sourceAnalysis": {
                            "modelAvailability": {"mediapipe": "available"},
                            "faceVisible": True,
                            "singlePerson": True,
                            "broadTraitHints": {"mouthExpression": "subtle_smile"},
                        },
                        "traitCard": {
                            "hair": {"bangs": "light"},
                            "facialHair": {"present": False, "broadStyle": "none"},
                            "faceImpression": {
                                "facialFeatureBalance": "balanced",
                                "eyeShapeMood": "gentle",
                                "browShape": "soft_arch",
                                "noseBridgeImpression": "moderate",
                                "mouthFullnessCategory": "medium",
                            },
                        },
                        "cost": {
                            "estimatedUsd": 0.08,
                            "totalWorkerSeconds": 120,
                            "secondsByStage": {
                                "generation_seconds": 80,
                                "qa_seconds": 10,
                            },
                        },
                    }
                },
                "avatarCandidates": {
                    "candidate-a": {
                        "jobId": "job-a",
                        "candidateId": "candidate-a",
                        "status": "preview_ready",
                        "previewPayloadBytes": 9 * 1024 * 1024,
                        "qa": {"previewAllowed": True},
                        "rerank": {
                            "selectionTier": "soft_pass",
                            "selectedForPreview": True,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = module.main(
        [
            "--fixture_json",
            str(fixture),
            "--project",
            "seolleyeon-final",
            "--uids",
            "uid-a",
            "--since",
            "2026-05-14T00:00:00Z",
            "--output_json",
            str(output),
        ]
    )

    assert result == 0
    report_text = output.read_text(encoding="utf-8")
    assert PRIVATE_REF not in report_text
    assert "X-Goog-Signature" not in report_text
    report = json.loads(report_text)
    assert report["summary"]["previewReadyRate"] == 1.0
    assert report["summary"]["approvalRate"] == 1.0
    assert report["summary"]["candidateStats"]["softPassCount"] == 1
    assert report["summary"]["previewPayloadWarnings"]["warning"] == 1
    job = report["jobs"][0]
    assert job["approvedAvatarUrlPresent"] is True
    assert job["sourceAnalysis"]["modelAvailability"]["mediapipe"] == "available"
    assert job["traitCardCompleteness"]["completeCount"] == 8
    assert job["timing"]["generationSeconds"] == 80


def test_internal_canary_report_counts_flat_trait_card_fields():
    script_path = REPO_ROOT / "scripts" / "avatar_internal_canary_report.py"
    spec = importlib.util.spec_from_file_location("avatar_internal_canary_report", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    summary = module._trait_card_summary(
        {
            "traitCard": {
                "traitCard": {
                    "hair_bangs": "light",
                    "facial_hair_present": "no",
                    "facial_hair_style": "none",
                    "facial_feature_balance": "balanced",
                    "eye_shape_mood": "gentle",
                    "brow_shape": "soft_arch",
                    "nose_bridge_impression": "moderate",
                    "mouth_fullness_category": "medium",
                }
            }
        }
    )

    assert summary["completeCount"] == 8
    assert summary["unclearFields"] == []


def test_trait_coverage_report_redacts_and_counts_flat_fields(tmp_path):
    script_path = REPO_ROOT / "scripts" / "avatar_trait_coverage_report.py"
    spec = importlib.util.spec_from_file_location("avatar_trait_coverage_report", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    fixture = tmp_path / "trait_fixture.json"
    output = tmp_path / "trait_report.json"
    fixture.write_text(
        json.dumps(
            {
                "avatarJobs": {
                    "job-a": {
                        "uid": "uid-a",
                        "status": "preview_ready",
                        "createdAt": NOW.isoformat(),
                        "sourceAnalysis": {
                            "modelAvailability": {"mediapipe": "available"},
                            "broadTraitHints": {
                                "facial_feature_balance": "balanced",
                                "brow_shape": "soft_arch",
                            },
                        },
                        "traitCard": {
                            "traitCard": {
                                "hair_bangs": "light",
                                "facial_hair_present": "no",
                                "facial_hair_style": "none",
                                "facial_feature_balance": "balanced",
                                "eye_shape_mood": "gentle",
                                "brow_shape": "soft_arch",
                                "nose_bridge_impression": "moderate",
                                "mouth_fullness_category": "medium",
                            }
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = module.main(
        [
            "--fixture_json",
            str(fixture),
            "--project",
            "seolleyeon-final",
            "--uids",
            "uid-a",
            "--since",
            "2026-05-14T00:00:00Z",
            "--output_json",
            str(output),
            "--redact",
        ]
    )

    assert result == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["summary"]["averageCoveragePercentage"] == 100.0
    job = report["jobs"][0]
    assert job["coverage"]["nonUnclearCount"] == 8
    assert job["expandedFields"]["brow_shape"]["source"] == "mediapipe_hint"


def test_canary_map_validator_reports_concrete_blockers():
    script_path = REPO_ROOT / "scripts" / "validate_canary_uid_photo_map.py"
    spec = importlib.util.spec_from_file_location("validate_canary_uid_photo_map", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    blockers = module._blockers(
        {"recommendation": "BLOCK_FACE_TOO_SMALL"},
        {
            "exists": True,
            "approvedLock": False,
            "isStudentVerified": True,
            "studentEmailDomainOk": False,
        },
        Path("missing.jpg"),
        False,
        {"valid": True},
    )

    assert "photo_missing" in blockers
    assert "block_face_too_small" in blockers
    assert "auth_uid_mismatch_or_missing_secret" in blockers
    assert "student_email_not_yonsei" in blockers


def test_mediapipe_task_preflight_recommendation_policy():
    script_path = REPO_ROOT / "scripts" / "preflight_canary_images_mediapipe_task.py"
    spec = importlib.util.spec_from_file_location("preflight_canary_images_mediapipe_task", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module._recommendation(0, 0.0, 0.08) == "BLOCK_NO_FACE"
    assert module._recommendation(2, 0.2, 0.08) == "BLOCK_MULTI_FACE"
    assert module._recommendation(1, 0.02, 0.08) == "BLOCK_FACE_TOO_SMALL"
    assert module._recommendation(1, 0.12, 0.08) == "PASS"


def test_canary_runner_dry_run_blocks_when_minimum_eligible_missing(tmp_path):
    script_path = REPO_ROOT / "scripts" / "run_canary_from_validated_map.py"
    spec = importlib.util.spec_from_file_location("run_canary_from_validated_map", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_dry_run_report(
        eligible=[
            {
                "rowLineage": "calibration_dedc0384e77a83a3f31f1e07",
                "photoFile": "a.jpg",
            }
        ],
        blocked=[
            {
                "rowLineage": "calibration_c6f9041e417f12eec2a209cc",
                "photoFile": "b.jpg",
                "blockers": ["block_face_too_small"],
            }
        ],
        min_users=3,
    )

    assert report["status"] == "BLOCKED_MIN_ELIGIBLE"
    assert report["eligibleCount"] == 1
    assert report["blocked"][0]["blockers"] == ["block_face_too_small"]
    rendered = json.dumps(report, sort_keys=True)
    assert "a.jpg" not in rendered
    assert "b.jpg" not in rendered


def test_canary_runner_payload_level_thresholds():
    script_path = REPO_ROOT / "scripts" / "run_canary_from_validated_map.py"
    spec = importlib.util.spec_from_file_location("run_canary_from_validated_map", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module._payload_level(1024) == "ok"
    assert module._payload_level(9 * 1024 * 1024) == "warning"
    assert module._payload_level(21 * 1024 * 1024) == "critical"
    request_id = module._safe_client_request_id("uid-a", "a.jpg")
    assert request_id == "calibration_dedc0384e77a83a3f31f1e07"
    assert "uid-a" not in request_id
    assert "a.jpg" not in request_id


def test_canary_runner_apply_reports_missing_auth_token_as_error(monkeypatch, tmp_path):
    script_path = REPO_ROOT / "scripts" / "run_canary_from_validated_map.py"
    spec = importlib.util.spec_from_file_location("run_canary_from_validated_map", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    photo = tmp_path / "uid_2_photo_plain.jpg"
    photo.write_bytes(b"jpeg")
    mapping = tmp_path / "map.txt"
    mapping.write_text(f"uid-a={photo}\n", encoding="utf-8")
    validation = tmp_path / "validation.json"
    validation.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "photoFile": photo.name,
                        "eligibleForUpload": True,
                        "blockers": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "runner.json"
    app_check_token = tmp_path / "app_check_token.txt"
    app_check_token.write_text("test-app-check-token", encoding="utf-8")

    monkeypatch.setattr(module, "_auth_tokens_by_uid", lambda api_key, secret_paths: {})
    monkeypatch.setattr(module, "_firestore_client", lambda project: object())

    result = module.main(
        [
            "--project",
            "seolleyeon-final",
            "--mapping_file",
            str(mapping),
            "--validation_json",
            str(validation),
            "--output_json",
            str(output),
            "--api_key",
            "test-api-key",
            "--app_check_token_file",
            str(app_check_token),
            "--min_users",
            "1",
            "--apply",
        ]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert result == 1
    assert report["status"] == "COMPLETE_WITH_ERRORS"
    assert report["jobErrorCount"] == 1
    assert report["jobs"][0]["error"] == "missing_auth_token"
    assert photo.name not in json.dumps(report, sort_keys=True)


def test_canary_runner_apply_reports_unsafe_callable_response_as_error(monkeypatch, tmp_path):
    script_path = REPO_ROOT / "scripts" / "run_canary_from_validated_map.py"
    spec = importlib.util.spec_from_file_location("run_canary_from_validated_map", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    photo = tmp_path / "uid_2_photo_plain.jpg"
    photo.write_bytes(b"jpeg")
    mapping = tmp_path / "map.txt"
    mapping.write_text(f"uid-a={photo}\n", encoding="utf-8")
    validation = tmp_path / "validation.json"
    validation.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "photoFile": photo.name,
                        "eligibleForUpload": True,
                        "blockers": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "runner.json"
    app_check_token = tmp_path / "app_check_token.txt"
    app_check_token.write_text("test-app-check-token", encoding="utf-8")

    monkeypatch.setattr(module, "_auth_tokens_by_uid", lambda api_key, secret_paths: {"uid-a": "token"})
    monkeypatch.setattr(module, "_firestore_client", lambda project: object())
    monkeypatch.setattr(
        module,
        "_run_one",
        lambda **kwargs: {
            "rowLineage": "calibration_d17aabd4b57b7f7b2737e1fa",
            "photoFile": photo.name,
            "upload": {"httpStatus": 200, "safeResponse": False},
        },
    )

    result = module.main(
        [
            "--project",
            "seolleyeon-final",
            "--mapping_file",
            str(mapping),
            "--validation_json",
            str(validation),
            "--output_json",
            str(output),
            "--api_key",
            "test-api-key",
            "--app_check_token_file",
            str(app_check_token),
            "--min_users",
            "1",
            "--apply",
        ]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert result == 1
    assert report["status"] == "COMPLETE_WITH_ERRORS"
    assert report["responseSafetyViolationCount"] == 1
    assert photo.name not in json.dumps(report, sort_keys=True)
    assert report["jobs"][0]["error"] == "unsafe_callable_response"


def test_canary_tools_read_api_key_from_google_services(tmp_path):
    payload = {
        "client": [
            {
                "api_key": [
                    {
                        "current_key": "test-api-key",
                    }
                ]
            }
        ]
    }
    google_services = tmp_path / "google-services.json"
    google_services.write_text(json.dumps(payload), encoding="utf-8")

    for script_name in (
        "validate_canary_uid_photo_map.py",
        "run_canary_from_validated_map.py",
    ):
        script_path = REPO_ROOT / "scripts" / script_name
        spec = importlib.util.spec_from_file_location(script_name, script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        assert module._api_key_from_google_services(google_services) == "test-api-key"


def test_normalize_canary_images_uses_deterministic_output_path():
    script_path = REPO_ROOT / "scripts" / "normalize_canary_images.py"
    spec = importlib.util.spec_from_file_location("normalize_canary_images", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module._output_path(Path("out"), "uid_1_photo") == Path(
        "out/uid_1_photo_plain.jpg"
    )


def test_pr84_gate_redacts_secret_arguments():
    script_path = REPO_ROOT / "scripts" / "pr84_canary_gate.py"
    spec = importlib.util.spec_from_file_location("pr84_canary_gate", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    redacted = module._redact_command(
        [
            "python",
            "script.py",
            "--api_key",
            "secret-api-key",
            "--auth_secret_json",
            ".local_secrets/users.json",
        ]
    )

    assert "secret-api-key" not in redacted
    assert ".local_secrets/users.json" not in redacted
    assert redacted.count("<redacted>") == 2


def test_pr84_default_auth_secret_paths_include_pr84_canary_secret():
    for script_name in (
        "pr84_canary_gate.py",
        "pr84_eligibility_inventory.py",
        "run_canary_from_validated_map.py",
        "validate_canary_uid_photo_map.py",
    ):
        script_path = REPO_ROOT / "scripts" / script_name
        spec = importlib.util.spec_from_file_location(script_name, script_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        paths = [str(path).replace("\\", "/") for path in module.DEFAULT_AUTH_SECRET_PATHS]
        assert any(path.endswith(".local_secrets/staging_pr84_canary_users.json") for path in paths)


def test_pr84_gate_summary_reports_needed_eligible_rows(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_canary_gate.py"
    spec = importlib.util.spec_from_file_location("pr84_canary_gate", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    preflight = tmp_path / "preflight.json"
    validation = tmp_path / "validation.json"
    runner = tmp_path / "runner.json"
    preflight.write_text(
        json.dumps(
            {
                "provider": "mediapipe_face_landmarker_tasks",
                "recommendationCounts": {"PASS": 1},
                "images": [
                    {
                        "normalizedFile": "a.jpg",
                        "recommendation": "PASS",
                    },
                    {
                        "normalizedFile": "unused.jpg",
                        "recommendation": "PASS",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    validation.write_text(
        json.dumps(
            {
                "rowCount": 2,
                "eligibleUploadRows": 1,
                "rows": [
                    {
                        "rowLineage": "calibration_dedc0384e77a83a3f31f1e07",
                        "photoFile": "a.jpg",
                        "eligibleForUpload": True,
                        "blockers": [],
                    },
                    {
                        "rowLineage": "calibration_c6f9041e417f12eec2a209cc",
                        "photoFile": "b.jpg",
                        "eligibleForUpload": False,
                        "blockers": ["approved_avatar_lock"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    runner.write_text(
        json.dumps({"status": "BLOCKED_MIN_ELIGIBLE", "eligibleCount": 1, "jobs": []}),
        encoding="utf-8",
    )

    summary = module._summary(
        preflight_json=preflight,
        validation_json=validation,
        runner_json=runner,
        apply=False,
        min_users=3,
    )

    assert summary["safeToApply"] is False
    assert summary["neededEligibleRows"] == 2
    assert summary["nextAction"] == "provide_2_more_eligible_uid_photo_rows"
    assert summary["validation"]["blockerCounts"] == {"approved_avatar_lock": 1}
    assert summary["preflight"]["unmappedPassFixtureCount"] == 1
    assert summary["preflight"]["unmappedPassFixtures"] == ["unused.jpg"]


def test_pr84_gate_summary_reports_activation_blocker(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_canary_gate.py"
    spec = importlib.util.spec_from_file_location("pr84_canary_gate", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    preflight = tmp_path / "preflight.json"
    validation = tmp_path / "validation.json"
    runner = tmp_path / "runner.json"
    activation = tmp_path / "activation.json"
    preflight.write_text(json.dumps({"provider": "mediapipe"}), encoding="utf-8")
    validation.write_text(json.dumps({"eligibleUploadRows": 0}), encoding="utf-8")
    runner.write_text(json.dumps({"status": "BLOCKED_MIN_ELIGIBLE"}), encoding="utf-8")
    activation.write_text(
        json.dumps(
            {
                "status": "BLOCKED_CONSENT",
                "activeRowCount": 0,
                "blockedRowCount": 3,
                "blockerCounts": {"uid_photo_pair_consent_missing": 3},
            }
        ),
        encoding="utf-8",
    )

    summary = module._summary(
        preflight_json=preflight,
        validation_json=validation,
        runner_json=runner,
        activation_json=activation,
        apply=False,
        min_users=3,
    )

    assert summary["nextAction"] == "activate_3_uid_photo_consent_rows"
    assert summary["safeToApply"] is False
    assert summary["activation"]["status"] == "BLOCKED_CONSENT"
    assert summary["activation"]["blockerCounts"] == {"uid_photo_pair_consent_missing": 3}


def test_pr84_gate_summary_blocks_safe_to_apply_when_activation_is_blocked(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_canary_gate.py"
    spec = importlib.util.spec_from_file_location("pr84_canary_gate", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    preflight = tmp_path / "preflight.json"
    validation = tmp_path / "validation.json"
    runner = tmp_path / "runner.json"
    activation = tmp_path / "activation.json"
    preflight.write_text(json.dumps({"provider": "mediapipe"}), encoding="utf-8")
    validation.write_text(json.dumps({"eligibleUploadRows": 3}), encoding="utf-8")
    runner.write_text(json.dumps({"status": "READY_DRY_RUN"}), encoding="utf-8")
    activation.write_text(
        json.dumps({"status": "BLOCKED_CONSENT", "activeRowCount": 0, "blockedRowCount": 3}),
        encoding="utf-8",
    )

    summary = module._summary(
        preflight_json=preflight,
        validation_json=validation,
        runner_json=runner,
        activation_json=activation,
        apply=False,
        min_users=3,
    )

    assert summary["safeToApply"] is False
    assert summary["nextAction"] == "activate_3_uid_photo_consent_rows"


def test_pr84_gate_summary_requests_rerun_with_activated_mapping(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_canary_gate.py"
    spec = importlib.util.spec_from_file_location("pr84_canary_gate", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    preflight = tmp_path / "preflight.json"
    validation = tmp_path / "validation.json"
    runner = tmp_path / "runner.json"
    activation = tmp_path / "activation.json"
    preflight.write_text(json.dumps({"provider": "mediapipe"}), encoding="utf-8")
    validation.write_text(json.dumps({"eligibleUploadRows": 0}), encoding="utf-8")
    runner.write_text(json.dumps({"status": "BLOCKED_MIN_ELIGIBLE"}), encoding="utf-8")
    activation.write_text(
        json.dumps({"status": "READY", "activeRowCount": 3, "blockedRowCount": 0}),
        encoding="utf-8",
    )

    summary = module._summary(
        preflight_json=preflight,
        validation_json=validation,
        runner_json=runner,
        activation_json=activation,
        apply=False,
        min_users=3,
    )

    assert summary["nextAction"] == "rerun_pr84_gate_with_activated_mapping"


def test_pr84_gate_summary_reports_apply_runner_no_upload_status(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_canary_gate.py"
    spec = importlib.util.spec_from_file_location("pr84_canary_gate", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    preflight = tmp_path / "preflight.json"
    validation = tmp_path / "validation.json"
    runner = tmp_path / "runner.json"
    activation = tmp_path / "activation.json"
    preflight.write_text(json.dumps({"provider": "mediapipe"}), encoding="utf-8")
    validation.write_text(json.dumps({"eligibleUploadRows": 3}), encoding="utf-8")
    runner.write_text(
        json.dumps({"status": "BLOCKED_MIN_ELIGIBLE_NO_UPLOAD", "jobs": []}),
        encoding="utf-8",
    )
    activation.write_text(
        json.dumps({"status": "READY", "activeRowCount": 3, "blockedRowCount": 0}),
        encoding="utf-8",
    )

    summary = module._summary(
        preflight_json=preflight,
        validation_json=validation,
        runner_json=runner,
        activation_json=activation,
        apply=True,
        min_users=3,
    )

    assert summary["safeToApply"] is False
    assert summary["nextAction"] == "apply_requested_but_runner_did_not_upload"


def test_pr84_gate_summary_reports_runner_errors_before_completion(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_canary_gate.py"
    spec = importlib.util.spec_from_file_location("pr84_canary_gate", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    preflight = tmp_path / "preflight.json"
    validation = tmp_path / "validation.json"
    runner = tmp_path / "runner.json"
    activation = tmp_path / "activation.json"
    preflight.write_text(json.dumps({"provider": "mediapipe"}), encoding="utf-8")
    validation.write_text(json.dumps({"eligibleUploadRows": 3}), encoding="utf-8")
    runner.write_text(
        json.dumps({"status": "COMPLETE_WITH_ERRORS", "jobs": [{"error": "missing_auth_token"}]}),
        encoding="utf-8",
    )
    activation.write_text(
        json.dumps({"status": "READY", "activeRowCount": 3, "blockedRowCount": 0}),
        encoding="utf-8",
    )

    summary = module._summary(
        preflight_json=preflight,
        validation_json=validation,
        runner_json=runner,
        activation_json=activation,
        apply=True,
        min_users=3,
    )

    assert summary["safeToApply"] is False
    assert summary["nextAction"] == "fix_runner_errors_before_completion"


def test_pr84_completion_audit_blocks_when_three_user_evidence_missing():
    script_path = REPO_ROOT / "scripts" / "pr84_completion_audit.py"
    spec = importlib.util.spec_from_file_location("pr84_completion_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    audit = module.build_audit(
        gate={
            "generatedAt": "2026-05-24T00:00:00+00:00",
            "preflight": {"provider": "mediapipe_face_landmarker_tasks"},
            "validation": {"eligibleUploadRows": 0},
            "neededEligibleRows": 3,
            "nextAction": "provide_3_more_eligible_uid_photo_rows",
            "safeToApply": False,
        },
        canary={"jobCount": 2, "jobs": []},
        trait={"jobCount": 2, "summary": {"allExpandedFieldsUnclearCount": 0}},
        privacy={"status": "pass"},
        inventory={
            "passFixtureCount": 3,
            "eligibleAuthUserCount": 0,
            "eligiblePairUpperBound": 0,
            "neededForThreeUserRerun": 3,
        },
    )

    assert audit["status"] == "BLOCKED_BY_INPUTS"
    assert audit["complete"] is False
    assert audit["inputBlockers"] == ["fixture_or_staging_auth_insufficient"]
    assert "provide_3_unlocked_staging_auth_users" in audit["remaining"]
    assert "provide_3_more_eligible_uid_photo_rows" in audit["remaining"]


def test_pr84_completion_audit_distinguishes_missing_uid_photo_activation():
    script_path = REPO_ROOT / "scripts" / "pr84_completion_audit.py"
    spec = importlib.util.spec_from_file_location("pr84_completion_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    audit = module.build_audit(
        gate={
            "generatedAt": "2026-05-24T00:00:00+00:00",
            "preflight": {"provider": "mediapipe_face_landmarker_tasks"},
            "validation": {"eligibleUploadRows": 0},
            "neededEligibleRows": 3,
            "nextAction": "provide_3_more_eligible_uid_photo_rows",
            "safeToApply": False,
        },
        canary={"jobCount": 2, "jobs": []},
        trait={"jobCount": 2, "summary": {"allExpandedFieldsUnclearCount": 0}},
        privacy={"status": "pass"},
        inventory={
            "passFixtureCount": 3,
            "eligibleAuthUserCount": 3,
            "eligiblePairUpperBound": 3,
            "neededForThreeUserRerun": 0,
        },
        activation={
            "activeRowCount": 0,
            "blockedRowCount": 3,
            "rows": [
                {"active": False, "blockers": ["uid_photo_pair_consent_missing"]},
                {"active": False, "blockers": ["uid_photo_pair_consent_missing"]},
                {"active": False, "blockers": ["uid_photo_pair_consent_missing"]},
            ],
        },
    )

    assert audit["status"] == "BLOCKED_BY_INPUTS"
    assert audit["complete"] is False
    assert audit["activation"]["activeRowCount"] == 0
    assert audit["activation"]["blockerCounts"] == {"uid_photo_pair_consent_missing": 3}
    assert audit["inputBlockers"] == ["uid_photo_pair_consent_missing"]
    assert audit["requirements"]["blockedByInputs"] is True
    assert "activate_3_uid_photo_consent_rows" in audit["remaining"]
    assert "provide_3_more_eligible_uid_photo_rows" not in audit["remaining"]
    assert "provide_3_unlocked_staging_auth_users" not in audit["remaining"]


def test_pr84_completion_audit_blocks_uid_photo_consent_mismatch():
    script_path = REPO_ROOT / "scripts" / "pr84_completion_audit.py"
    spec = importlib.util.spec_from_file_location("pr84_completion_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    audit = module.build_audit(
        gate={
            "generatedAt": "2026-05-24T00:00:00+00:00",
            "preflight": {"provider": "mediapipe_face_landmarker_tasks"},
            "validation": {"eligibleUploadRows": 0},
            "safeToApply": False,
        },
        canary={"jobCount": 0, "jobs": []},
        trait={"jobCount": 1, "summary": {"allExpandedFieldsUnclearCount": 0}},
        privacy={"status": "pass"},
        inventory={
            "passFixtureCount": 3,
            "eligibleAuthUserCount": 3,
            "eligiblePairUpperBound": 3,
            "neededForThreeUserRerun": 0,
        },
        activation={
            "status": "BLOCKED_CONSENT_MISMATCH",
            "activeRowCount": 3,
            "blockedRowCount": 0,
            "unexpectedConsentPairCount": 1,
            "uidPhotoConsentMap": {"unexpectedPairCount": 1},
            "rows": [
                {"active": True, "blockers": []},
                {"active": True, "blockers": []},
                {"active": True, "blockers": []},
            ],
        },
    )

    assert audit["status"] == "BLOCKED_BY_INPUTS"
    assert audit["complete"] is False
    assert audit["requirements"]["uidPhotoActivationReadyOrCanaryAlreadyRan"] is False
    assert audit["inputBlockers"] == ["uid_photo_consent_map_mismatch"]
    assert "fix_uid_photo_consent_map_mismatch" in audit["remaining"]
    assert "rerun_pr84_gate_with_activated_mapping" not in audit["remaining"]


def test_pr84_completion_audit_includes_general_consent_exact_row_summary():
    script_path = REPO_ROOT / "scripts" / "pr84_completion_audit.py"
    spec = importlib.util.spec_from_file_location("pr84_completion_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    audit = module.build_audit(
        gate={
            "generatedAt": "2026-05-24T00:00:00+00:00",
            "preflight": {"provider": "mediapipe_face_landmarker_tasks"},
            "validation": {"eligibleUploadRows": 0},
            "safeToApply": False,
        },
        canary={"jobCount": 0, "jobs": []},
        trait={"jobCount": 1, "summary": {"allExpandedFieldsUnclearCount": 0}},
        privacy={"status": "pass"},
        inventory={
            "passFixtureCount": 3,
            "eligibleAuthUserCount": 3,
            "eligiblePairUpperBound": 3,
            "neededForThreeUserRerun": 0,
        },
        activation={
            "activeRowCount": 0,
            "blockedRowCount": 3,
            "rows": [
                {"active": False, "blockers": ["uid_photo_pair_consent_missing"]},
                {"active": False, "blockers": ["uid_photo_pair_consent_missing"]},
                {"active": False, "blockers": ["uid_photo_pair_consent_missing"]},
            ],
        },
        post_consent={
            "generalConsentEvidence": {
                "present": True,
                "valid": True,
                "scope": "general_canary_consent_evidence",
                "consentFile": "canary_consent.txt",
                "consentFileSelection": "explicit",
                "exactUidPhotoConsent": {
                    "satisfiedByThisFile": False,
                    "parsedRowCount": 4,
                    "requiredRowCount": 3,
                    "matchedRowCount": 0,
                    "missingRowCount": 3,
                    "unexpectedRowCount": 4,
                },
                "blockers": [],
            }
        },
    )

    general = audit["generalConsentEvidence"]
    assert general["valid"] is True
    assert general["consentFile"] == "canary_consent.txt"
    assert general["exactUidPhotoConsent"]["satisfiedByThisFile"] is False
    assert general["exactUidPhotoConsent"]["parsedRowCount"] == 4
    assert general["exactUidPhotoConsent"]["missingRowCount"] == 3
    assert general["exactUidPhotoConsent"]["unexpectedRowCount"] == 4
    assert "general_consent_exact_uid_photo_mismatch" in audit["inputBlockers"]
    assert "uid_photo_pair_consent_missing" in audit["inputBlockers"]
    assert "fix_general_consent_exact_uid_photo_mismatch" in audit["remaining"]


def test_pr84_completion_audit_ignores_stale_gate_when_post_consent_gate_not_executed():
    script_path = REPO_ROOT / "scripts" / "pr84_completion_audit.py"
    spec = importlib.util.spec_from_file_location("pr84_completion_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    audit = module.build_audit(
        gate={
            "generatedAt": "2026-05-24T00:00:00+00:00",
            "preflight": {"provider": "mediapipe_face_landmarker_tasks"},
            "validation": {"eligibleUploadRows": 3},
            "safeToApply": True,
        },
        canary={"jobCount": 0, "jobs": []},
        trait={"jobCount": 1, "summary": {"allExpandedFieldsUnclearCount": 0}},
        privacy={"status": "pass"},
        inventory={
            "passFixtureCount": 3,
            "eligibleAuthUserCount": 3,
            "eligiblePairUpperBound": 3,
            "neededForThreeUserRerun": 0,
        },
        activation={
            "activeRowCount": 0,
            "blockedRowCount": 3,
            "rows": [
                {"active": False, "blockers": ["uid_photo_pair_consent_missing"]},
                {"active": False, "blockers": ["uid_photo_pair_consent_missing"]},
                {"active": False, "blockers": ["uid_photo_pair_consent_missing"]},
            ],
        },
        post_consent={
            "gate": {
                "executed": False,
                "safeToApply": False,
                "eligibleUploadRows": None,
            }
        },
    )

    assert audit["gate"]["freshForPostConsent"] is False
    assert audit["gate"]["eligibleUploadRows"] == 0
    assert audit["gate"]["safeToApply"] is False
    assert audit["requirements"]["uidPhotoActivationReadyOrCanaryAlreadyRan"] is False
    assert audit["requirements"]["mappingHasThreeEligibleRows"] is False
    assert audit["requirements"]["gateSafeToApplyOrAlreadyRan"] is False
    assert "uid_photo_pair_consent_missing" in audit["inputBlockers"]


def test_pr84_completion_audit_requests_gate_rerun_after_activation():
    script_path = REPO_ROOT / "scripts" / "pr84_completion_audit.py"
    spec = importlib.util.spec_from_file_location("pr84_completion_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    audit = module.build_audit(
        gate={
            "generatedAt": "2026-05-24T00:00:00+00:00",
            "preflight": {"provider": "mediapipe_face_landmarker_tasks"},
            "validation": {"eligibleUploadRows": 0},
            "safeToApply": False,
        },
        canary={"jobCount": 0, "jobs": []},
        trait={"jobCount": 1, "summary": {"allExpandedFieldsUnclearCount": 0}},
        privacy={"status": "pass"},
        inventory={
            "passFixtureCount": 3,
            "eligibleAuthUserCount": 3,
            "eligiblePairUpperBound": 3,
            "neededForThreeUserRerun": 0,
        },
        activation={
            "activeRowCount": 3,
            "blockedRowCount": 0,
            "rows": [
                {"active": True, "blockers": []},
                {"active": True, "blockers": []},
                {"active": True, "blockers": []},
            ],
        },
    )

    assert "rerun_pr84_gate_with_activated_mapping" in audit["remaining"]
    assert "provide_3_more_eligible_uid_photo_rows" not in audit["remaining"]


def test_pr84_completion_audit_passes_with_three_approved_locked_users():
    script_path = REPO_ROOT / "scripts" / "pr84_completion_audit.py"
    spec = importlib.util.spec_from_file_location("pr84_completion_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    jobs = [
        {
            "status": "approved",
            "approvedAvatarUrlPresent": True,
            "lockRetestStatus": "passed",
            "candidateStats": {"previewCount": 4},
        }
        for _ in range(3)
    ]
    audit = module.build_audit(
        gate={
            "generatedAt": "2026-05-24T00:00:00+00:00",
            "preflight": {"provider": "mediapipe_face_landmarker_tasks"},
            "validation": {"eligibleUploadRows": 3},
            "safeToApply": False,
        },
        canary={"jobCount": 3, "jobs": jobs},
        trait={"jobCount": 3, "summary": {"allExpandedFieldsUnclearCount": 0}},
        privacy={"status": "pass"},
        inventory={
            "passFixtureCount": 0,
            "eligibleAuthUserCount": 0,
            "eligiblePairUpperBound": 0,
            "neededForThreeUserRerun": 3,
        },
    )

    assert audit["status"] == "PASS_INTERNAL_CANARY_3USER"
    assert audit["complete"] is True
    assert audit["remaining"] == []


def test_pr84_completion_audit_accepts_apply_runner_schema_for_lock_evidence():
    script_path = REPO_ROOT / "scripts" / "pr84_completion_audit.py"
    spec = importlib.util.spec_from_file_location("pr84_completion_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    jobs = [
        {
            "job": {"status": "preview_ready"},
            "approval": {
                "avatarStatus": "approved",
                "approvedAvatarUrlPresent": True,
            },
            "lockRetest": {
                "httpStatus": 400,
                "safeResponse": True,
                "rejected": True,
                "errorMessage": "avatar_already_approved",
            },
            "candidateStats": {"previewCount": 4},
        }
        for _ in range(3)
    ]

    audit = module.build_audit(
        gate={
            "generatedAt": "2026-05-24T00:00:00+00:00",
            "preflight": {"provider": "mediapipe_face_landmarker_tasks"},
            "validation": {"eligibleUploadRows": 3},
            "safeToApply": False,
        },
        canary={"status": "COMPLETE", "jobs": jobs},
        trait={"jobCount": 3, "summary": {"allExpandedFieldsUnclearCount": 0}},
        privacy={"status": "pass"},
    )

    assert audit["canary"] == {
        "jobCount": 3,
        "previewReadyCount": 3,
        "approvedCount": 3,
        "lockRetestPassedCount": 3,
    }
    assert audit["status"] == "PASS_INTERNAL_CANARY_3USER"
    assert audit["complete"] is True
    assert audit["remaining"] == []


def test_pr84_completion_audit_reads_utf8_bom_json(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_completion_audit.py"
    spec = importlib.util.spec_from_file_location("pr84_completion_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    path = tmp_path / "privacy.json"
    path.write_text('{"status":"pass"}', encoding="utf-8-sig")

    assert module._load_json(path) == {"status": "pass"}


def test_pr84_eligibility_inventory_redacts_auth_users_and_counts_pairs(monkeypatch):
    script_path = REPO_ROOT / "scripts" / "pr84_eligibility_inventory.py"
    spec = importlib.util.spec_from_file_location("pr84_eligibility_inventory", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    def fake_auth_uid_records(api_key, secrets):
        return [
            {
                "labelHash": "label:a",
                "localAuthUid": "uid-a",
                "localAuthUidHash": "uid:hash-a",
                "authOk": True,
                "authError": "",
            },
            {
                "labelHash": "label:b",
                "localAuthUid": "uid-b",
                "localAuthUidHash": "uid:hash-b",
                "authOk": True,
                "authError": "",
            },
        ]

    states = {
        "uid-a": {
            "exists": True,
            "approvedLock": False,
            "isStudentVerified": True,
            "studentEmailDomainOk": True,
        },
        "uid-b": {
            "exists": True,
            "approvedLock": True,
            "isStudentVerified": True,
            "studentEmailDomainOk": True,
        },
    }

    monkeypatch.setattr(module, "_auth_uid_records", fake_auth_uid_records)
    monkeypatch.setattr(module, "_user_state", lambda client, uid: states[uid])

    report = module.build_inventory(
        project="seolleyeon-final",
        preflight={
            "images": [
                {"normalizedFile": "a.jpg", "recommendation": "PASS"},
                {"normalizedFile": "b.jpg", "recommendation": "PASS"},
                {"normalizedFile": "c.jpg", "recommendation": "BLOCK_FACE_TOO_SMALL"},
            ]
        },
        validation={"rows": [{"photoFile": "a.jpg"}]},
        api_key="test-api-key",
        auth_secrets=[{"email": "secret@example.com", "password": "secret"}],
        firestore_client=object(),
    )

    serialized = json.dumps(report)
    assert "secret@example.com" not in serialized
    assert "uid-a" not in serialized
    assert report["passFixtureCount"] == 2
    assert report["unmappedPassFixtures"] == ["b.jpg"]
    assert report["eligibleAuthUserCount"] == 1
    assert report["eligiblePairUpperBound"] == 1
    assert report["authUsers"][1]["blockers"] == ["approved_avatar_lock"]


def test_pr84_prepare_canary_auth_users_dry_run_does_not_store_passwords(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_prepare_canary_auth_users.py"
    spec = importlib.util.spec_from_file_location("pr84_prepare_canary_auth_users", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    users = {
        "PR84_A": {"email": "staging-pr84-a@yonsei.ac.kr", "password": "secret-password"},
    }

    report = module.build_dry_run_report(
        users=users,
        secret_file=tmp_path / "staging_pr84_canary_users.json",
    )
    serialized = json.dumps(report)

    assert report["mode"] == "dry_run"
    assert report["willMutateStaging"] is False
    assert "secret-password" not in serialized
    assert report["users"]["PR84_A"]["passwordStoredLocally"] is False


def test_pr84_mapping_template_comments_rows_that_need_consent(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_canary_mapping_template.py"
    spec = importlib.util.spec_from_file_location("pr84_canary_mapping_template", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_template(
        prepared_report={
            "users": {
                "PR84_A": {
                    "uid": "new-uid",
                    "email": "staging-pr84-a@yonsei.ac.kr",
                }
            }
        },
        preflight_report={
            "images": [
                {
                    "normalizedFile": "uid_2_photo_plain.jpg",
                    "recommendation": "PASS",
                }
            ]
        },
        existing_mapping={"uid_2_photo_plain.jpg": "old-uid"},
        normalized_dir=tmp_path,
    )
    rendered = module._render_template(report)

    assert report["candidatePairCount"] == 1
    assert report["activeRowCount"] == 0
    assert report["consentRequiredCount"] == 1
    assert rendered.splitlines()[4].startswith("# new-uid=")
    assert "CONSENT_REQUIRED" in rendered


def test_pr84_mapping_template_defaults_rows_inactive_without_activation(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_canary_mapping_template.py"
    spec = importlib.util.spec_from_file_location("pr84_canary_mapping_template", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_template(
        prepared_report={
            "users": {
                "PR84_A": {
                    "uid": "new-uid",
                    "email": "staging-pr84-a@yonsei.ac.kr",
                }
            }
        },
        preflight_report={
            "images": [
                {
                    "normalizedFile": "fresh_photo_plain.jpg",
                    "recommendation": "PASS",
                }
            ]
        },
        existing_mapping={},
        normalized_dir=tmp_path,
    )
    rendered = module._render_template(report)

    assert report["activeRowCount"] == 0
    assert report["rows"][0]["reason"] == "explicit_activation_required"
    assert rendered.splitlines()[4].startswith("# new-uid=")
    assert "INACTIVE" in rendered


def test_pr84_consent_evidence_rejects_mojibake_text():
    script_path = REPO_ROOT / "scripts" / "pr84_consent_evidence.py"
    spec = importlib.util.spec_from_file_location("pr84_consent_evidence", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.evaluate_consent_text(
        "??UID seolleyeon-final staging avatar canary?? production rollout???",
    )

    assert report["valid"] is False
    assert "consent_file_mojibake_or_unreadable" in report["blockers"]
    assert "consent_missing_explicit_consent" in report["blockers"]


def test_pr84_activate_canary_mapping_requires_exact_uid_photo_consent(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_activate_canary_mapping.py"
    spec = importlib.util.spec_from_file_location("pr84_activate_canary_mapping", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    template = {
        "rows": [
            {
                "label": "PR84_A",
                "uid": "uid-a",
                "photoFile": "photo_a_plain.jpg",
                "photoPath": str(tmp_path / "photo_a_plain.jpg"),
            },
            {
                "label": "PR84_B",
                "uid": "uid-b",
                "photoFile": "photo_b_plain.jpg",
                "photoPath": str(tmp_path / "photo_b_plain.jpg"),
            },
        ]
    }

    report = module.build_activation(
        template=template,
        consent_pairs={("uid-a", "photo_a_plain.jpg")},
        confirm_uid_photo_consent=True,
    )
    rendered = module._render_mapping(report)
    consent_template = module._render_required_consent_template(report)

    assert report["activeRowCount"] == 1
    assert report["blockedRowCount"] == 1
    assert report["consentPairCount"] == 1
    assert report["matchedConsentPairCount"] == 1
    assert report["unexpectedConsentPairCount"] == 0
    assert report["blockerCounts"] == {"uid_photo_pair_consent_missing": 1}
    assert report["candidateConsentMapRows"] == [
        "uid-a=photo_a_plain.jpg",
        "uid-b=photo_b_plain.jpg",
    ]
    assert report["requiredConsentMapRows"] == ["uid-b=photo_b_plain.jpg"]
    assert "uid-a=" in rendered
    assert "uid-b=" not in rendered
    assert "# uid-a=photo_a_plain.jpg" in consent_template
    assert "# uid-b=photo_b_plain.jpg" in consent_template
    assert report["rows"][1]["blockers"] == ["uid_photo_pair_consent_missing"]


def test_pr84_activate_canary_mapping_counts_unexpected_consent_pairs(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_activate_canary_mapping.py"
    spec = importlib.util.spec_from_file_location("pr84_activate_canary_mapping", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_activation(
        template={
            "rows": [
                {
                    "uid": "pr84-uid-a",
                    "photoFile": "uid_2_photo_plain.jpg",
                    "photoPath": str(tmp_path / "uid_2_photo_plain.jpg"),
                },
                {
                    "uid": "pr84-uid-b",
                    "photoFile": "uid_4_photo_plain.jpg",
                    "photoPath": str(tmp_path / "uid_4_photo_plain.jpg"),
                },
            ]
        },
        consent_pairs={
            ("legacy-uid-a", "uid_2_photo_plain.jpg"),
            ("legacy-uid-b", "uid_5_photo_plain.jpg"),
        },
        confirm_uid_photo_consent=True,
    )

    assert report["activeRowCount"] == 0
    assert report["consentPairCount"] == 2
    assert report["matchedConsentPairCount"] == 0
    assert report["unexpectedConsentPairCount"] == 2
    assert report["requiredConsentMapRows"] == [
        "pr84-uid-a=uid_2_photo_plain.jpg",
        "pr84-uid-b=uid_4_photo_plain.jpg",
    ]
    assert module._activation_status(report, min_users=2) == "BLOCKED_CONSENT_MISMATCH"


def test_pr84_activate_canary_mapping_blocks_ready_when_extra_consent_pair_present(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_activate_canary_mapping.py"
    spec = importlib.util.spec_from_file_location("pr84_activate_canary_mapping", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_activation(
        template={
            "rows": [
                {
                    "uid": "pr84-uid-a",
                    "photoFile": "uid_2_photo_plain.jpg",
                    "photoPath": str(tmp_path / "uid_2_photo_plain.jpg"),
                }
            ]
        },
        consent_pairs={
            ("pr84-uid-a", "uid_2_photo_plain.jpg"),
            ("legacy-uid-a", "uid_2_photo_plain.jpg"),
        },
        confirm_uid_photo_consent=True,
    )

    assert report["activeRowCount"] == 1
    assert report["matchedConsentPairCount"] == 1
    assert report["unexpectedConsentPairCount"] == 1
    assert module._activation_status(report, min_users=1) == "BLOCKED_CONSENT_MISMATCH"


def test_pr84_activate_canary_mapping_keeps_canonical_consent_template_after_ready(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_activate_canary_mapping.py"
    spec = importlib.util.spec_from_file_location("pr84_activate_canary_mapping", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_activation(
        template={
            "rows": [
                {
                    "uid": "uid-a",
                    "photoFile": "photo_a_plain.jpg",
                    "photoPath": str(tmp_path / "photo_a_plain.jpg"),
                },
                {
                    "uid": "uid-b",
                    "photoFile": "photo_b_plain.jpg",
                    "photoPath": str(tmp_path / "photo_b_plain.jpg"),
                },
            ]
        },
        consent_pairs={
            ("uid-a", "photo_a_plain.jpg"),
            ("uid-b", "photo_b_plain.jpg"),
        },
        confirm_uid_photo_consent=True,
    )

    rendered = module._render_required_consent_template(report)

    assert report["activeRowCount"] == 2
    assert report["requiredConsentMapRows"] == []
    assert report["candidateConsentMapRows"] == [
        "uid-a=photo_a_plain.jpg",
        "uid-b=photo_b_plain.jpg",
    ]
    assert "# uid-a=photo_a_plain.jpg" in rendered
    assert "# uid-b=photo_b_plain.jpg" in rendered


def test_pr84_activate_canary_mapping_blocks_without_confirmation(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_activate_canary_mapping.py"
    spec = importlib.util.spec_from_file_location("pr84_activate_canary_mapping", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_activation(
        template={
            "rows": [
                {
                    "uid": "uid-a",
                    "photoFile": "photo_a_plain.jpg",
                    "photoPath": str(tmp_path / "photo_a_plain.jpg"),
                }
            ]
        },
        consent_pairs={("uid-a", "photo_a_plain.jpg")},
        confirm_uid_photo_consent=False,
    )

    assert report["activeRowCount"] == 0
    assert report["requiredConsentMapRows"] == ["uid-a=photo_a_plain.jpg"]
    assert report["rows"][0]["blockers"] == ["confirm_uid_photo_consent_required"]


def test_pr84_activate_canary_mapping_require_ready_exits_nonzero(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_activate_canary_mapping.py"
    template = tmp_path / "template.json"
    output_mapping = tmp_path / "activated.txt"
    output_json = tmp_path / "activation.json"
    required_template = tmp_path / "required.txt"
    template.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "uid": "uid-a",
                        "photoFile": "photo_a_plain.jpg",
                        "photoPath": str(tmp_path / "photo_a_plain.jpg"),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--template_json",
            str(template),
            "--uid_photo_consent_map",
            str(tmp_path / "missing.txt"),
            "--output_mapping",
            str(output_mapping),
            "--output_json",
            str(output_json),
            "--required_consent_template",
            str(required_template),
            "--require_ready",
            "--min_users",
            "1",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["status"] == "BLOCKED_CONSENT"
    assert report["uidPhotoConsentMap"]["present"] is False
    assert report["uidPhotoConsentMap"]["pairCount"] == 0
    assert "# uid-a=photo_a_plain.jpg" in required_template.read_text(encoding="utf-8")


def test_pr84_post_consent_canary_requires_apply_confirmation():
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--apply",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--apply requires --confirm_staging_mutation" in result.stderr


def test_pr84_post_consent_gate_reuses_explicit_general_consent_when_unset():
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    spec = importlib.util.spec_from_file_location("pr84_post_consent_canary", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    args = type(
        "Args",
        (),
        {
            "python": "python",
            "project": "seolleyeon-final",
            "region": "asia-northeast3",
            "input_dir": "canary_inputs",
            "output_dir": "canary_inputs/normalized",
            "activated_mapping": "out/pr84_canary_uid_photo_map_activated.txt",
            "consent_file": None,
            "general_consent_file": "canary_consent.txt",
            "google_services_json": "android/app/google-services.json",
            "activation_json": "out/pr84_canary_uid_photo_map_activation.json",
            "gate_summary_json": "out/pr84_canary_gate_summary.json",
            "runner_json": "out/pr84_canary_runner_dry_run.json",
            "min_users": 3,
            "auth_secret_json": [],
            "apply": False,
        },
    )()

    command = module.build_gate_command(args)

    assert command[command.index("--consent_file") + 1] == "canary_consent.txt"


def test_pr84_post_consent_report_summarizes_blocked_activation(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    spec = importlib.util.spec_from_file_location("pr84_post_consent_canary", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_report(
        steps=[
            {
                "name": "activate_uid_photo_mapping",
                "command": ["python", "scripts/pr84_activate_canary_mapping.py"],
                "returnCode": 2,
                "stdout": "",
                "stderr": "",
            }
        ],
        project_guard={
            "checks": {
                "account": True,
                "gcloudProject": True,
                "firebaseProject": True,
            }
        },
        activation={
            "status": "BLOCKED_CONSENT",
            "activeRowCount": 0,
            "blockedRowCount": 3,
            "blockerCounts": {"uid_photo_pair_consent_missing": 3},
            "requiredConsentMapRows": ["uid-a=photo_a_plain.jpg"],
            "uidPhotoConsentMap": {
                "path": str(tmp_path / "missing.txt"),
                "present": False,
                "pairCount": 0,
            },
        },
        gate={},
        apply=False,
        min_users=3,
        general_consent={
            "present": True,
            "valid": True,
            "scope": "general_canary_consent_evidence",
            "consentFile": "canary_uid_photo_consent.txt",
            "consentFileSelection": "default",
            "exactUidPhotoConsent": {
                "requiredForPr84Activation": True,
                "satisfiedByThisFile": False,
                "requiredMapFile": "pr84_uid_photo_consent_map.txt",
            },
            "blockers": [],
        },
    )

    assert report["status"] == "BLOCKED"
    assert report["inputBlockers"] == ["uid_photo_pair_consent_missing"]
    assert report["missingConsentRowCount"] == 1
    assert report["generalConsentEvidence"]["valid"] is True
    assert report["generalConsentEvidence"]["exactUidPhotoConsent"]["satisfiedByThisFile"] is False
    assert report["consentMap"]["present"] is False
    assert report["consentMap"]["pairCount"] == 0
    assert report["consentMap"]["matchedPairCount"] == 0
    assert report["consentMap"]["unexpectedPairCount"] == 0
    assert report["activationReady"] is False
    assert report["activation"]["matchedConsentPairCount"] == 0
    assert report["activation"]["unexpectedConsentPairCount"] == 0
    assert report["activation"]["requiredConsentMapRows"] == ["uid-a=photo_a_plain.jpg"]
    assert report["activation"]["uidPhotoConsentMap"]["present"] is False
    assert report["activation"]["uidPhotoConsentMap"]["pairCount"] == 0


def test_pr84_post_consent_report_blocks_consent_mismatch():
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    spec = importlib.util.spec_from_file_location("pr84_post_consent_canary", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_report(
        steps=[],
        project_guard={
            "checks": {
                "account": True,
                "gcloudProject": True,
                "firebaseProject": True,
            }
        },
        activation={
            "status": "BLOCKED_CONSENT_MISMATCH",
            "activeRowCount": 3,
            "blockedRowCount": 0,
            "blockerCounts": {},
            "unexpectedConsentPairCount": 1,
            "uidPhotoConsentMap": {"unexpectedPairCount": 1},
        },
        gate={"safeToApply": True},
        apply=False,
        min_users=3,
    )

    assert report["status"] == "BLOCKED"
    assert report["activationReady"] is False
    assert report["inputBlockers"] == ["uid_photo_consent_map_mismatch"]
    assert report["consentMap"]["unexpectedPairCount"] == 1
    assert report["activation"]["unexpectedConsentPairCount"] == 1


def test_pr84_post_consent_report_ignores_stale_gate_when_activation_blocked():
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    spec = importlib.util.spec_from_file_location("pr84_post_consent_canary", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_report(
        steps=[
            {
                "name": "activate_uid_photo_mapping",
                "returnCode": 2,
                "stdout": "",
                "stderr": "",
            }
        ],
        project_guard={
            "checks": {
                "account": True,
                "gcloudProject": True,
                "firebaseProject": True,
            }
        },
        activation={
            "status": "BLOCKED_CONSENT",
            "activeRowCount": 0,
            "blockedRowCount": 3,
            "blockerCounts": {"uid_photo_pair_consent_missing": 3},
        },
        gate={
            "safeToApply": True,
            "validation": {"eligibleUploadRows": 3},
            "runner": {"status": "READY_DRY_RUN", "jobCount": 3},
        },
        apply=False,
        min_users=3,
    )

    assert report["status"] == "BLOCKED"
    assert report["gateReady"] is False
    assert report["gate"]["executed"] is False
    assert report["gate"]["safeToApply"] is False
    assert report["gate"]["eligibleUploadRows"] is None


def test_pr84_post_consent_report_blocks_apply_when_gate_failed_after_activation_ready():
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    spec = importlib.util.spec_from_file_location("pr84_post_consent_canary", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_report(
        steps=[
            {"name": "activate_uid_photo_mapping", "returnCode": 0},
            {"name": "activated_mapping_gate", "returnCode": 1},
        ],
        project_guard={
            "checks": {
                "account": True,
                "gcloudProject": True,
                "firebaseProject": True,
            }
        },
        activation={
            "status": "READY",
            "activeRowCount": 3,
            "blockedRowCount": 0,
            "blockerCounts": {},
        },
        gate={
            "failed": True,
            "safeToApply": False,
            "nextAction": "fix_failed_gate_step_before_upload",
            "validation": {"eligibleUploadRows": 0},
            "runner": {"status": None, "jobCount": 0},
        },
        apply=True,
        min_users=3,
    )

    assert report["status"] == "BLOCKED_GATE"
    assert report["gateReady"] is False
    assert report["gate"]["executed"] is True
    assert report["gate"]["failed"] is True
    assert "gate_execution_failed" in report["inputBlockers"]


def test_pr84_post_consent_report_blocks_apply_when_runner_did_not_upload():
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    spec = importlib.util.spec_from_file_location("pr84_post_consent_canary", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_report(
        steps=[
            {"name": "activate_uid_photo_mapping", "returnCode": 0},
            {"name": "activated_mapping_gate", "returnCode": 0},
        ],
        project_guard={
            "checks": {
                "account": True,
                "gcloudProject": True,
                "firebaseProject": True,
            }
        },
        activation={
            "status": "READY",
            "activeRowCount": 3,
            "blockedRowCount": 0,
            "blockerCounts": {},
        },
        gate={
            "safeToApply": False,
            "nextAction": "apply_requested_but_runner_did_not_upload",
            "validation": {"eligibleUploadRows": 0},
            "runner": {"status": "BLOCKED_MIN_ELIGIBLE_NO_UPLOAD", "jobCount": 0},
        },
        apply=True,
        min_users=3,
    )

    assert report["status"] == "BLOCKED_RUNNER_NO_UPLOAD"
    assert report["gateReady"] is False
    assert report["gate"]["runnerStatus"] == "BLOCKED_MIN_ELIGIBLE_NO_UPLOAD"
    assert "apply_runner_did_not_upload" in report["inputBlockers"]


def test_pr84_post_consent_report_blocks_apply_when_runner_completed_with_errors():
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    spec = importlib.util.spec_from_file_location("pr84_post_consent_canary", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_report(
        steps=[
            {"name": "activate_uid_photo_mapping", "returnCode": 0},
            {"name": "activated_mapping_gate", "returnCode": 0},
        ],
        project_guard={
            "checks": {
                "account": True,
                "gcloudProject": True,
                "firebaseProject": True,
            }
        },
        activation={
            "status": "READY",
            "activeRowCount": 3,
            "blockedRowCount": 0,
            "blockerCounts": {},
        },
        gate={
            "safeToApply": False,
            "nextAction": "review_canary_runner_output",
            "validation": {"eligibleUploadRows": 3},
            "runner": {"status": "COMPLETE_WITH_ERRORS", "jobCount": 3},
        },
        apply=True,
        min_users=3,
    )

    assert report["status"] == "BLOCKED_RUNNER_ERRORS"
    assert report["gate"]["runnerStatus"] == "COMPLETE_WITH_ERRORS"
    assert "apply_runner_completed_with_errors" in report["inputBlockers"]


def test_pr84_post_consent_report_surfaces_general_consent_exact_row_mismatch():
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    spec = importlib.util.spec_from_file_location("pr84_post_consent_canary", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.build_report(
        steps=[],
        project_guard={
            "checks": {
                "account": True,
                "gcloudProject": True,
                "firebaseProject": True,
            }
        },
        activation={
            "status": "BLOCKED_CONSENT",
            "activeRowCount": 0,
            "blockedRowCount": 3,
            "blockerCounts": {"uid_photo_pair_consent_missing": 3},
            "requiredConsentMapRows": [
                "pmmHkAR9jpUuMBMnWcqm4tIKLW53=uid_2_photo_plain.jpg",
                "47VcfOmL2nTkzN8LHSbBhY8CEJl2=uid_4_photo_plain.jpg",
                "UzqFhD0o3fg7tZKpWU4ws3wLrCJ2=uid_5_photo_plain.jpg",
            ],
        },
        gate={},
        apply=False,
        min_users=3,
        general_consent={
            "present": True,
            "valid": True,
            "scope": "general_canary_consent_evidence",
            "consentFile": "canary_consent.txt",
            "consentFileSelection": "explicit",
            "exactUidPhotoConsent": {
                "satisfiedByThisFile": False,
                "parsedRowCount": 4,
                "requiredRowCount": 3,
                "matchedRowCount": 0,
                "missingRowCount": 3,
                "unexpectedRowCount": 4,
            },
            "blockers": [],
        },
    )

    assert report["inputBlockers"] == [
        "general_consent_exact_uid_photo_mismatch",
        "uid_photo_pair_consent_missing",
    ]
    assert report["activationReady"] is False


def test_pr84_post_consent_console_summary_reports_missing_consent_rows(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    spec = importlib.util.spec_from_file_location("pr84_post_consent_canary", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    summary = module.build_console_summary(
        {
            "status": "BLOCKED",
            "inputBlockers": ["uid_photo_pair_consent_missing"],
            "generalConsentEvidence": {
                "present": True,
                "valid": True,
                "scope": "general_canary_consent_evidence",
                "exactUidPhotoConsent": {"satisfiedByThisFile": False},
            },
            "consentMap": {
                "present": False,
                "pairCount": 0,
                "matchedPairCount": 0,
                "unexpectedPairCount": 0,
            },
            "missingConsentRowCount": 1,
            "activationReady": False,
            "gateReady": False,
            "activation": {"requiredConsentMapRows": ["uid-a=photo_a_plain.jpg"]},
            "gate": {"nextAction": "activate_3_uid_photo_consent_rows"},
        },
        output_path=tmp_path / "post_consent.json",
        required_consent_template=tmp_path / "required.txt",
    )

    assert summary["status"] == "BLOCKED"
    assert summary["inputBlockers"] == ["uid_photo_pair_consent_missing"]
    assert summary["generalConsentEvidence"]["valid"] is True
    assert summary["consentMap"]["present"] is False
    assert summary["consentMap"]["matchedPairCount"] == 0
    assert summary["missingConsentRowCount"] == 1
    assert summary["requiredConsentRows"] == ["uid-a=photo_a_plain.jpg"]
    assert summary["requiredConsentTemplate"].endswith("required.txt")


def test_pr84_post_consent_report_blocks_project_guard_mismatch():
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    spec = importlib.util.spec_from_file_location("pr84_post_consent_canary", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    ok, guard = module.build_project_guard_steps(
        account_result={"returnCode": 0, "stdout": "wrong@example.com"},
        project_result={"returnCode": 0, "stdout": "seolleyeon"},
        firebase_result={"returnCode": 0, "stdout": "seolleyeon"},
        expected_account="seolleyeon.official@gmail.com",
        expected_project="seolleyeon-final",
    )
    report = module.build_report(
        steps=[],
        project_guard=guard,
        activation={"status": "READY", "activeRowCount": 3, "blockedRowCount": 0},
        gate={"safeToApply": True},
        apply=False,
        min_users=3,
    )

    assert ok is False
    assert report["status"] == "BLOCKED_PROJECT_GUARD"
    assert report["projectGuard"]["checks"] == {
        "account": False,
        "gcloudProject": False,
        "firebaseProject": False,
    }


def test_pr84_post_consent_run_reports_missing_executable(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_post_consent_canary.py"
    spec = importlib.util.spec_from_file_location("pr84_post_consent_canary", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    result = module._run(["definitely-missing-pr84-command"], cwd=tmp_path)

    assert result["returnCode"] == 127
    assert result["command"] == ["definitely-missing-pr84-command"]
    assert result["stderr"]


def test_pr84_consent_evidence_accepts_explicit_staging_text():
    script_path = REPO_ROOT / "scripts" / "pr84_consent_evidence.py"
    spec = importlib.util.spec_from_file_location("pr84_consent_evidence", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.evaluate_consent_text(
        "Participants gave explicit consent for seolleyeon-final staging avatar "
        "canary QA and privacy monitoring. This is not production rollout.",
    )

    assert report["valid"] is True
    assert report["scope"] == "general_canary_consent_evidence"
    assert report["exactUidPhotoConsent"]["requiredForPr84Activation"] is True
    assert report["exactUidPhotoConsent"]["satisfiedByThisFile"] is False
    assert report["exactUidPhotoConsent"]["requiredMapFile"] == "pr84_uid_photo_consent_map.txt"
    assert report["exactUidPhotoConsent"]["parsedRowCount"] == 0
    assert report["blockers"] == []


def test_pr84_consent_evidence_falls_back_to_canary_consent_file(tmp_path):
    script_path = REPO_ROOT / "scripts" / "pr84_consent_evidence.py"
    spec = importlib.util.spec_from_file_location("pr84_consent_evidence", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    fallback = tmp_path / "canary_consent.txt"
    fallback.write_text(
        "Participants gave explicit consent for seolleyeon-final staging avatar "
        "canary QA and privacy monitoring. This is not production rollout.",
        encoding="utf-8",
    )

    consent_path, selection = module.resolve_consent_path(None, cwd=tmp_path)
    report = module.evaluate_consent_file(consent_path)

    assert consent_path == fallback
    assert selection == "fallback"
    assert report["valid"] is True
    assert report["exactUidPhotoConsent"]["satisfiedByThisFile"] is False


def test_pr84_consent_evidence_reports_exact_uid_photo_mismatch():
    script_path = REPO_ROOT / "scripts" / "pr84_consent_evidence.py"
    spec = importlib.util.spec_from_file_location("pr84_consent_evidence", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.evaluate_consent_text(
        "Participants gave explicit consent for seolleyeon-final staging avatar "
        "canary QA and privacy monitoring. This is not production rollout.\n"
        "legacy-uid=C:\\tmp\\uid_2_photo_plain.jpg\n"
        "another-uid=C:\\tmp\\uid_5_photo_plain.jpg\n",
        required_uid_photo_rows=[
            "pr84-uid-a=uid_2_photo_plain.jpg",
            "pr84-uid-b=uid_4_photo_plain.jpg",
            "pr84-uid-c=uid_5_photo_plain.jpg",
        ],
    )

    exact = report["exactUidPhotoConsent"]
    assert report["valid"] is True
    assert exact["satisfiedByThisFile"] is False
    assert exact["parsedRowCount"] == 2
    assert exact["requiredRowCount"] == 3
    assert exact["matchedRowCount"] == 0
    assert exact["missingRowCount"] == 3
    assert exact["unexpectedRowCount"] == 2
    assert exact["unexpectedRows"] == [
        "legacy-uid=uid_2_photo_plain.jpg",
        "another-uid=uid_5_photo_plain.jpg",
    ]


def test_canary_mapping_validator_blocks_invalid_consent(monkeypatch, tmp_path):
    script_path = REPO_ROOT / "scripts" / "validate_canary_uid_photo_map.py"
    spec = importlib.util.spec_from_file_location("validate_canary_uid_photo_map", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    photo = tmp_path / "normalized" / "photo_plain.jpg"
    photo.parent.mkdir()
    photo.write_bytes(b"jpeg")
    mapping = tmp_path / "map.txt"
    mapping.write_text(f"uid-1={photo}\n", encoding="utf-8")
    consent = tmp_path / "consent.txt"
    consent.write_text("?? seolleyeon-final staging avatar canary ??", encoding="utf-8")
    preflight = tmp_path / "preflight.json"
    preflight.write_text(
        json.dumps(
            {
                "images": [
                    {
                        "normalizedFile": "photo_plain.jpg",
                        "recommendation": "PASS",
                        "faceCount": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "_auth_uid_lookup", lambda api_key, secrets: {"uid-1": "A"})
    monkeypatch.setattr(
        module,
        "_user_state",
        lambda project, uid: {
            "exists": True,
            "approvedLock": False,
            "isStudentVerified": True,
            "studentEmailDomainOk": True,
        },
    )

    report = module.build_report(
        project="seolleyeon-final",
        mapping_path=mapping,
        consent_file=consent,
        preflight_json=preflight,
        api_key="test",
        auth_secret_paths=[],
    )

    assert report["eligibleUploadRows"] == 0
    assert report["consentEvidence"]["valid"] is False
    assert report["rows"][0]["blockers"] == ["consent_evidence_invalid"]


def test_batching_savings_calculation_compares_per_job_runtime_to_shared_batch_runtime():
    jobs = [_job(job_id=f"job_{index}", processing={"durationSeconds": 10}) for index in range(4)]

    batch = estimate_batch_cost(jobs, duration_seconds=20, config=_config())

    assert batch.unbatched_cost.usd == 1.12
    assert batch.total_cost.usd == 0.56
    assert batch.savings_usd == 0.56
    assert batch.savings_ratio == 0.5
