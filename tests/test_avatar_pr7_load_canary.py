import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
SCRIPTS_DIR = REPO_ROOT / "scripts"
for path in (AI_MODEL_DIR, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from avatar_generation.job_lease import AvatarJobLeaseConfig


NOW = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
PRIVATE_REF = "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg"


def _load_script(name):
    script_path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


def _job(job_id, uid="u1", status="queued", **overrides):
    doc = {
        "jobId": job_id,
        "uid": uid,
        "status": status,
        "sourcePhotoIds": ["src_001"],
        "sourcePhotoRefs": [PRIVATE_REF.replace("/u1/", f"/{uid}/")],
        "candidateCount": 4,
        "createdAt": NOW,
        "processing": {"attempt": 0},
        "privacyQaMarker": "pr7f_privacy_qa_pass",
    }
    doc.update(overrides)
    return doc


def _private_media(uid="u1"):
    source_ref = PRIVATE_REF.replace("/u1/", f"/{uid}/")
    return {
        "photoConsent": {
            "avatarGeneration": True,
            "profileDisplayOriginalPhoto": False,
        },
        "sourcePhotos": [
            {
                "photoId": "src_001",
                "gcsUri": source_ref,
                "status": "active",
                "purpose": {"avatarGeneration": True},
            }
        ],
    }


def _firestore(job_count):
    jobs = {f"job_{index:03d}": _job(f"job_{index:03d}", uid=f"u{index:03d}") for index in range(job_count)}
    private_media = {f"u{index:03d}": _private_media(f"u{index:03d}") for index in range(job_count)}
    return FakeFirestore({"avatarJobs": jobs, "userPrivateMedia": private_media})


def test_load_test_claims_100_jobs_without_duplicate_claims(monkeypatch):
    module = _load_script("avatar_pipeline_load_test")
    fs = _firestore(100)
    monkeypatch.setattr(module, "utcnow", lambda: NOW)

    report = module.run_load_test(
        firestore_client=fs,
        num_users=1000,
        jobs_per_user=1,
        candidate_count=4,
        ci_jobs=100,
        simulate_worker=True,
        dry_run=True,
        no_real_gcs=True,
        no_real_gpu=True,
        firestore_emulator=True,
        config=AvatarJobLeaseConfig(lease_seconds=120, max_scan=200, max_attempts=3, batch_size=10),
    )

    assert report["mode"]["dryRun"] is True
    assert report["simulation"]["numUsers"] == 1000
    assert report["simulation"]["jobsPerUser"] == 1
    assert report["simulation"]["candidateCount"] == 4
    assert report["simulation"]["ciJobs"] == 100
    assert report["claims"]["claimed"] == 100
    assert report["duplicatePrevention"]["duplicateClaims"] == 0
    assert report["duplicatePrevention"]["uniqueClaimedJobs"] == 100
    assert report["batches"]["batchSize"] == 10
    assert report["batches"]["numberOfBatches"] == 10
    assert report["batches"]["averageBatchSize"] == 10
    assert report["gpu"]["realGpuUsed"] is False
    assert report["gcs"]["realGcsUsed"] is False


def test_load_test_requeues_stale_crash_lease():
    module = _load_script("avatar_pipeline_load_test")
    fs = FakeFirestore(
        {
            "avatarJobs": {
                "stale": _job(
                    "stale",
                    status="running",
                    processing={
                        "attempt": 1,
                        "leaseOwner": "crashed-worker",
                        "leaseToken": "old-token",
                        "leaseExpiresAt": NOW - timedelta(seconds=1),
                    },
                )
            },
            "userPrivateMedia": {"u1": _private_media("u1")},
        }
    )

    report = module.run_stale_lease_drill(
        fs,
        now=NOW,
        config=AvatarJobLeaseConfig(lease_seconds=120, max_scan=10, max_attempts=3),
    )

    assert report["staleLeases"]["found"] == 1
    assert report["staleLeases"]["requeued"] == 1
    assert fs.data["avatarJobs"]["stale"]["status"] == "queued"
    assert fs.data["avatarJobs"]["stale"]["processing"]["leaseToken"] == ""


def test_load_test_cost_report_includes_timing_and_privacy_marker():
    module = _load_script("avatar_pipeline_load_test")
    fs = _firestore(10)

    report = module.run_load_test(
        firestore_client=fs,
        num_users=1000,
        jobs_per_user=1,
        candidate_count=4,
        ci_jobs=10,
        simulate_worker=True,
        dry_run=True,
        no_real_gcs=True,
        no_real_gpu=True,
        firestore_emulator=True,
        now=NOW,
        config=AvatarJobLeaseConfig(lease_seconds=120, max_scan=20, max_attempts=3),
    )

    assert report["cost"]["estimatedGpuSeconds"] > 0
    assert report["cost"]["totalSimulatedWorkerSeconds"] > 0
    assert report["cost"]["estimatedCostPerUser"] > 0
    assert report["cost"]["costPerApprovedAvatar"] > 0
    assert report["cost"]["timing"]["claimLoopSeconds"] >= 0
    assert report["cost"]["estimatedBatches"] == 2
    assert report["staleLeases"]["simulated"] == 0
    assert report["staleLeases"]["recovered"] == 0
    assert report["failures"]["failed"] == 0
    assert report["retries"]["retryable"] == 0
    assert report["privacy"]["status"] == "pass"
    assert report["privacy"]["leakageCheck"] == "pass"
    assert report["privacy"]["qaMarker"] == "pr7f_privacy_qa_pass"
    encoded = json.dumps(report)
    assert "gs://seolleyeon-final-private-source-photos" not in encoded


def test_privacy_status_fails_when_emitted_report_contains_sensitive_markers():
    module = _load_script("avatar_pipeline_load_test")

    report = module._privacy_status(
        {
            "bad": "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg?X-Goog-Signature=abc"
        }
    )

    assert report["status"] == "fail"
    assert report["leakageCheck"] == "fail"
    assert report["sourceRefsEmitted"] is True
    assert report["signedUrlsEmitted"] is True


def test_load_test_prompt_cli_flags_write_report(tmp_path):
    module = _load_script("avatar_pipeline_load_test")
    output = tmp_path / "avatar_load_report.json"

    result = module.main(
        [
            "--dry_run",
            "--num_users",
            "10",
            "--jobs_per_user",
            "1",
            "--candidate_count",
            "4",
            "--simulate_worker",
            "--no_real_gcs",
            "--no_real_gpu",
            "--report_json",
            str(output),
        ]
    )

    assert result == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["simulation"]["numUsers"] == 10
    assert report["simulation"]["jobsPerUser"] == 1
    assert report["simulation"]["candidateCount"] == 4
    assert report["claims"]["attempted"] == 10
    assert report["claims"]["claimed"] == 10
    assert report["cost"]["totalSimulatedWorkerSeconds"] > 0
    assert report["privacy"]["leakageCheck"] == "pass"


def test_canary_dry_run_report_has_all_exact_gates(tmp_path):
    module = _load_script("avatar_staging_canary")
    output = tmp_path / "canary.json"

    result = module.main(["--dry_run", "--output_report_json", str(output)])

    assert result == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["mode"] == "dry_run"
    assert report["ok"] is True
    assert set(report["gates"]) == {
        "gcs",
        "firestore",
        "queue",
        "oidc",
        "gpu",
        "tempDocs",
        "qa",
        "previewApproval",
        "cleanup",
        "privacy",
    }
    assert all(gate["status"] == "pass" for gate in report["gates"].values())
    assert report["featureFlags"]["rollback"]["AVATAR_DISABLE_NEW_GENERATION"] is True
    assert report["privacy"]["sourceRefsEmitted"] is False
