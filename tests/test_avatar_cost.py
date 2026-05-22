import importlib.util
import json
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
    assert scenario["estimatedCost"]["usd"] == 34.884
    assert scenario["estimatedCost"]["pricingVersion"] == "cloud_run_l4_2026_05"


def test_formula_includes_gpu_cpu_memory_and_zonal_redundancy():
    normal = estimate_job_cost(duration_seconds=10, config=_config())
    redundant = estimate_job_cost(
        duration_seconds=10,
        config=_config(gpu_zonal_redundancy=True),
    )

    assert normal.usd == 1.28
    assert normal.breakdown["gpuUsd"] == 1.0
    assert normal.breakdown["cpuUsd"] == 0.2
    assert normal.breakdown["memoryUsd"] == 0.08
    assert redundant.usd == 2.28
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
    assert aggregate.total_usd == 1.92
    assert aggregate.daily_count == 2
    assert aggregate.monthly_count == 2
    assert batch.job_count == 2
    assert batch.candidate_count == 6
    assert batch.total_cost.usd == 1.536


def test_job_and_batch_cost_documents_expose_persistable_worker_fields():
    jobs = [_job(job_id=f"job_{index}", processing={"durationSeconds": 10}) for index in range(2)]

    job_doc = build_job_cost_document(duration_seconds=10, config=_config(), estimated_at=NOW)
    batch_doc = build_batch_cost_document(jobs, duration_seconds=12, config=_config(), estimated_at=NOW)

    assert job_doc["costEstimateUsd"] == 1.28
    assert job_doc["costEstimate"]["durationSeconds"] == 10
    assert job_doc["costEstimate"]["pricingVersion"] == "test-pricing"
    assert job_doc["costEstimate"]["estimatedAt"] == NOW
    assert batch_doc["batchCostEstimateUsd"] == 1.536
    assert batch_doc["batchCostEstimate"]["jobCount"] == 2
    assert batch_doc["batchCostEstimate"]["savingsUsd"] == 1.024
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
    assert report["scenario"]["estimatedCost"]["usd"] == 34.884


def test_batching_savings_calculation_compares_per_job_runtime_to_shared_batch_runtime():
    jobs = [_job(job_id=f"job_{index}", processing={"durationSeconds": 10}) for index in range(4)]

    batch = estimate_batch_cost(jobs, duration_seconds=20, config=_config())

    assert batch.unbatched_cost.usd == 5.12
    assert batch.total_cost.usd == 2.56
    assert batch.savings_usd == 2.56
    assert batch.savings_ratio == 0.5
