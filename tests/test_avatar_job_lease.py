import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.batching import bounded_batch_size, claim_avatar_job_batch
import avatar_generation.job_lease as job_lease
from avatar_generation.job_lease import (
    AvatarJobLeaseConfig,
    ClaimDeadline,
    claim_next_avatar_job,
    heartbeat_avatar_job_lease,
    sweep_stale_avatar_job_leases,
    try_claim_avatar_job,
)


NOW = datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc)
PRIVATE_REF = "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg"


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
        "lease_seconds": 120,
        "heartbeat_seconds": 30,
        "max_attempts": 3,
        "batch_size": 2,
        "deadline_safety_seconds": 30,
        "max_scan": 50,
    }
    values.update(overrides)
    return AvatarJobLeaseConfig(**values)


def _job(job_id="job_1", status="queued", **overrides):
    doc = {
        "jobId": job_id,
        "uid": "u1",
        "status": status,
        "sourcePhotoIds": ["src_001"],
        "sourcePhotoRefs": [PRIVATE_REF],
        "candidateCount": 4,
        "jobType": "avatar_generation",
        "schemaVersion": "avatar_job_v1",
        "createdAt": NOW - timedelta(minutes=5),
        "processing": {"attempt": 0},
    }
    doc.update(overrides)
    return doc


def _private_media(**overrides):
    doc = {
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
    doc.update(overrides)
    return doc


def _firestore(jobs=None, private_media=None):
    return FakeFirestore(
        {
            "avatarJobs": jobs if jobs is not None else {"job_1": _job()},
            "userPrivateMedia": private_media if private_media is not None else {"u1": _private_media()},
        }
    )


def test_claims_queued_job_and_writes_lease_metadata(monkeypatch):
    monkeypatch.delenv("AVATAR_GPU_WORKER_ENABLED", raising=False)
    fs = _firestore()

    lease = claim_next_avatar_job(fs, worker_id="worker-a", now=NOW, config=_config())

    assert lease is not None
    assert lease.job_id == "job_1"
    assert lease.attempt == 1
    assert lease.lease_owner == "worker-a"
    assert lease.lease_expires_at == NOW + timedelta(seconds=120)
    job = fs.data["avatarJobs"]["job_1"]
    processing = job["processing"]
    assert job["status"] == "running"
    assert processing["attempt"] == 1
    assert processing["leaseOwner"] == "worker-a"
    assert processing["leaseToken"] == lease.lease_token
    assert processing["leaseExpiresAt"] == NOW + timedelta(seconds=120)
    assert processing["leaseHeartbeatAt"] == NOW
    assert processing["startedAt"] == NOW
    assert processing["batchId"] == ""
    assert processing["lastErrorCode"] == ""
    assert processing["lastErrorMessage"] == ""
    assert "leaseOwner" not in job
    assert "leaseToken" not in job
    assert "leaseExpiresAt" not in job
    assert "attempt" not in job
    assert lease.payload["jobId"] == "job_1"
    assert lease.payload["uid"] == "u1"
    assert lease.payload["sourcePhotoRefCount"] == 1
    assert "sourcePhotoRefs" not in lease.payload


def test_duplicate_claim_is_prevented():
    fs = _firestore()
    first = try_claim_avatar_job(fs, "job_1", worker_id="worker-a", now=NOW, config=_config())
    second = try_claim_avatar_job(fs, "job_1", worker_id="worker-b", now=NOW, config=_config())

    assert first is not None
    assert second is None
    assert fs.data["avatarJobs"]["job_1"]["processing"]["leaseOwner"] == "worker-a"
    assert fs.data["avatarJobs"]["job_1"]["processing"]["attempt"] == 1


@pytest.mark.parametrize("status", ["preview_ready", "approved", "cancelled"])
def test_terminal_jobs_are_not_claimed(status):
    fs = _firestore(jobs={"job_1": _job(status=status)})

    lease = claim_next_avatar_job(fs, worker_id="worker-a", now=NOW, config=_config())

    assert lease is None
    assert fs.data["avatarJobs"]["job_1"]["status"] == status


def test_stale_running_job_is_reclaimed_with_next_attempt():
    fs = _firestore(
        jobs={
            "job_1": _job(
                status="running",
                processing={
                    "attempt": 1,
                    "leaseOwner": "worker-old",
                    "leaseToken": "old-token",
                    "leaseExpiresAt": NOW - timedelta(seconds=1),
                },
            )
        }
    )

    lease = claim_next_avatar_job(fs, worker_id="worker-new", now=NOW, config=_config())

    assert lease is not None
    assert lease.attempt == 2
    job = fs.data["avatarJobs"]["job_1"]
    assert job["processing"]["leaseOwner"] == "worker-new"
    assert job["processing"]["leaseToken"] == lease.lease_token
    assert job["processing"]["attempt"] == 2


def test_legacy_flat_processing_fields_are_read_but_rewritten_nested():
    fs = _firestore(
        jobs={
            "job_1": {
                **_job(status="running"),
                "attempt": 1,
                "leaseOwner": "worker-old",
                "leaseToken": "old-token",
                "leaseExpiresAt": NOW - timedelta(seconds=1),
                "processing": {},
            }
        }
    )

    lease = claim_next_avatar_job(fs, worker_id="worker-new", now=NOW, config=_config())

    assert lease is not None
    job = fs.data["avatarJobs"]["job_1"]
    assert job["processing"]["attempt"] == 2
    assert job["processing"]["leaseOwner"] == "worker-new"
    assert job["processing"]["leaseExpiresAt"] == NOW + timedelta(seconds=120)


def test_retryable_failed_job_at_max_attempts_is_not_claimed():
    fs = _firestore(jobs={"job_1": _job(status="failed", processing={"attempt": 3}, retryable=True)})

    lease = claim_next_avatar_job(fs, worker_id="worker-a", now=NOW, config=_config())

    assert lease is None
    assert fs.data["avatarJobs"]["job_1"]["processing"]["attempt"] == 3
    assert fs.data["avatarJobs"]["job_1"]["status"] == "failed"


def test_consent_revoked_job_is_not_claimed_and_is_terminal():
    fs = _firestore(
        private_media={
            "u1": _private_media(
                photoConsent={
                    "avatarGeneration": False,
                    "profileDisplayOriginalPhoto": False,
                }
            )
        }
    )

    lease = claim_next_avatar_job(fs, worker_id="worker-a", now=NOW, config=_config())

    assert lease is None
    job = fs.data["avatarJobs"]["job_1"]
    assert job["status"] == "failed"
    assert job["retryable"] is False
    assert job["processing"]["lastErrorCode"] == "avatar_consent_not_granted"


@pytest.mark.parametrize(
    "source_refs",
    [
        [],
        ["gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg"],
        ["gs://wrong-bucket/users/u1/source/src_001.jpg"],
        ["https://storage.googleapis.com/seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg"],
    ],
)
def test_missing_or_non_private_source_refs_are_rejected_without_leaking_ref(source_refs):
    fs = _firestore(jobs={"job_1": _job(sourcePhotoRefs=source_refs)})

    lease = claim_next_avatar_job(fs, worker_id="worker-a", now=NOW, config=_config())

    assert lease is None
    job = fs.data["avatarJobs"]["job_1"]
    assert job["status"] == "failed"
    assert job["retryable"] is False
    assert job["processing"]["lastErrorCode"] == "invalid_source_refs"
    encoded = json.dumps(
        {
            "lastErrorCode": job["processing"].get("lastErrorCode"),
            "lastErrorMessage": job["processing"].get("lastErrorMessage", ""),
        }
    )
    assert "users/u1/source/src_001.jpg" not in encoded
    assert "https://storage.googleapis.com" not in encoded


@pytest.mark.parametrize(
    ("env_name", "env_value"),
    [
        ("AVATAR_GPU_WORKER_ENABLED", "false"),
        ("AVATAR_DISABLE_NEW_GENERATION", "true"),
        ("AVATAR_COST_KILL_SWITCH_ENABLED", "true"),
    ],
)
def test_worker_or_cost_gate_prevents_claim_without_mutating_job(monkeypatch, env_name, env_value):
    monkeypatch.setenv(env_name, env_value)
    fs = _firestore()

    lease = claim_next_avatar_job(fs, worker_id="worker-a", now=NOW, config=_config())

    assert lease is None
    assert fs.data["avatarJobs"]["job_1"]["status"] == "queued"
    assert fs.data["avatarJobs"]["job_1"]["processing"]["attempt"] == 0


def test_production_claims_fail_closed_when_cost_guard_is_unavailable(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(job_lease, "AvatarCostConfig", None)
    monkeypatch.setattr(job_lease, "evaluate_cost_guard", None)
    fs = _firestore()

    lease = claim_next_avatar_job(fs, worker_id="worker-a", now=NOW, config=_config())

    assert lease is None
    assert fs.data["avatarJobs"]["job_1"]["status"] == "queued"


def test_deadline_stops_claims_near_safety_window():
    fs = _firestore()
    deadline = ClaimDeadline(deadline_at=NOW + timedelta(seconds=20), safety_seconds=30)

    lease = claim_next_avatar_job(
        fs,
        worker_id="worker-a",
        now=NOW,
        config=_config(),
        deadline=deadline,
    )

    assert lease is None
    assert fs.data["avatarJobs"]["job_1"]["status"] == "queued"


def test_heartbeat_extends_matching_lease_and_rejects_wrong_token():
    fs = _firestore()
    lease = claim_next_avatar_job(fs, worker_id="worker-a", now=NOW, config=_config())
    assert lease is not None

    assert heartbeat_avatar_job_lease(
        fs,
        "job_1",
        lease_token="wrong-token",
        worker_id="worker-a",
        now=NOW + timedelta(seconds=20),
        config=_config(),
    ) is False
    assert heartbeat_avatar_job_lease(
        fs,
        "job_1",
        lease_token=lease.lease_token,
        worker_id="worker-a",
        now=NOW + timedelta(seconds=20),
        config=_config(),
    ) is True
    job = fs.data["avatarJobs"]["job_1"]
    assert job["processing"]["leaseHeartbeatAt"] == NOW + timedelta(seconds=20)
    assert job["processing"]["leaseExpiresAt"] == NOW + timedelta(seconds=140)


def test_sweeper_requeues_stale_running_until_max_attempts_then_fails():
    fs = _firestore(
        jobs={
            "stale_retry": _job(
                job_id="stale_retry",
                status="running",
                processing={
                    "attempt": 1,
                    "leaseExpiresAt": NOW - timedelta(minutes=1),
                    "leaseOwner": "old",
                    "leaseToken": "old-token",
                },
            ),
            "stale_max": _job(
                job_id="stale_max",
                status="running",
                processing={
                    "attempt": 3,
                    "leaseExpiresAt": NOW - timedelta(minutes=1),
                    "leaseOwner": "old",
                    "leaseToken": "old-token",
                },
            ),
            "fresh": _job(
                job_id="fresh",
                status="running",
                processing={
                    "attempt": 1,
                    "leaseExpiresAt": NOW + timedelta(minutes=1),
                    "leaseOwner": "old",
                    "leaseToken": "fresh-token",
                },
            ),
        }
    )

    summary = sweep_stale_avatar_job_leases(fs, now=NOW, config=_config(), dry_run=False)

    assert summary.scanned == 3
    assert summary.stale == 2
    assert summary.requeued == 1
    assert summary.failed == 1
    assert fs.data["avatarJobs"]["stale_retry"]["status"] == "queued"
    assert fs.data["avatarJobs"]["stale_retry"]["processing"]["leaseToken"] == ""
    assert fs.data["avatarJobs"]["stale_retry"]["processing"]["lastErrorCode"] == "lease_expired"
    assert fs.data["avatarJobs"]["stale_max"]["status"] == "failed"
    assert fs.data["avatarJobs"]["stale_max"]["processing"]["lastErrorCode"] == "lease_expired_max_attempts"
    assert fs.data["avatarJobs"]["fresh"]["status"] == "running"


def test_batch_claims_up_to_batch_size_and_honors_deadline():
    fs = _firestore(
        jobs={
            "job_1": _job(job_id="job_1"),
            "job_2": _job(job_id="job_2", sourcePhotoRefs=[PRIVATE_REF.replace("src_001", "src_002")]),
            "job_3": _job(job_id="job_3", sourcePhotoRefs=[PRIVATE_REF.replace("src_001", "src_003")]),
        },
        private_media={
            "u1": _private_media(
                sourcePhotos=[
                    {
                        "photoId": "src_001",
                        "gcsUri": PRIVATE_REF,
                        "status": "active",
                        "purpose": {"avatarGeneration": True},
                    },
                    {
                        "photoId": "src_002",
                        "gcsUri": PRIVATE_REF.replace("src_001", "src_002"),
                        "status": "active",
                        "purpose": {"avatarGeneration": True},
                    },
                    {
                        "photoId": "src_003",
                        "gcsUri": PRIVATE_REF.replace("src_001", "src_003"),
                        "status": "active",
                        "purpose": {"avatarGeneration": True},
                    },
                ]
            )
        },
    )

    leases = claim_avatar_job_batch(fs, worker_id="worker-a", now=NOW, config=_config(), batch_size=2)
    stopped = claim_avatar_job_batch(
        fs,
        worker_id="worker-a",
        now=NOW,
        config=_config(),
        batch_size=2,
        deadline=ClaimDeadline(deadline_at=NOW + timedelta(seconds=1), safety_seconds=30),
    )

    assert [lease.job_id for lease in leases] == ["job_1", "job_2"]
    assert len({lease.batch_id for lease in leases}) == 1
    assert fs.data["avatarJobs"]["job_1"]["processing"]["batchId"]
    assert fs.data["avatarJobs"]["job_2"]["processing"]["batchId"] == fs.data["avatarJobs"]["job_1"]["processing"]["batchId"]
    assert stopped == []
    assert fs.data["avatarJobs"]["job_3"]["status"] == "queued"


def test_pr7_batch_env_names_are_supported(monkeypatch):
    monkeypatch.setenv("AVATAR_BATCHING_ENABLED", "true")
    monkeypatch.setenv("AVATAR_BATCH_MODE", "gpu_batch")
    monkeypatch.setenv("AVATAR_BATCH_MAX_JOBS", "7")
    monkeypatch.setenv("AVATAR_BATCH_MAX_SECONDS", "600")
    monkeypatch.setenv("AVATAR_BATCH_MAX_IDLE_WAIT_SECONDS", "11")
    monkeypatch.setenv("AVATAR_BATCH_POLL_INTERVAL_SECONDS", "3")
    monkeypatch.setenv("AVATAR_BATCH_LEASE_SECONDS", "321")
    monkeypatch.setenv("AVATAR_BATCH_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("AVATAR_BATCH_REQUIRE_APPROVED_SOURCE_CONSENT", "true")
    monkeypatch.setenv("AVATAR_BATCH_CONCURRENCY_PER_GPU", "2")
    monkeypatch.setenv("AVATAR_BATCH_CANDIDATES_PER_USER", "4")
    monkeypatch.setenv("AVATAR_BATCH_SOFT_STOP_BEFORE_DEADLINE_SECONDS", "45")
    monkeypatch.setenv("AVATAR_ALLOW_STALE_LEASE_RECOVERY", "false")
    monkeypatch.setenv("AVATAR_FORCE_SINGLE_JOB_MODE", "true")

    config = AvatarJobLeaseConfig.from_env()

    assert config.batching_enabled is True
    assert config.batch_mode == "gpu_batch"
    assert config.batch_size == 7
    assert config.max_batch_seconds == 600
    assert config.max_idle_wait_seconds == 11
    assert config.poll_interval_seconds == 3
    assert config.lease_seconds == 321
    assert config.max_attempts == 5
    assert config.require_approved_source_consent is True
    assert config.concurrency_per_gpu == 2
    assert config.candidates_per_user == 4
    assert config.deadline_safety_seconds == 45
    assert config.allow_stale_lease_recovery is False
    assert config.force_single_job_mode is True
    assert bounded_batch_size(None, config) == 1


def test_job_lease_sweeper_script_defaults_to_dry_run_and_writes_report(tmp_path, monkeypatch):
    script_path = REPO_ROOT / "scripts" / "avatar_job_lease_sweeper.py"
    spec = importlib.util.spec_from_file_location("avatar_job_lease_sweeper", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    fs = _firestore(
        jobs={
            "job_1": _job(
                status="running",
                processing={
                    "attempt": 1,
                    "leaseExpiresAt": NOW - timedelta(seconds=1),
                    "leaseOwner": "old",
                    "leaseToken": "old-token",
                },
            )
        }
    )
    report_path = tmp_path / "lease_sweep_report.json"
    monkeypatch.setattr(module, "default_firestore_client", lambda project=None, database=None: fs)
    monkeypatch.setattr(module, "utcnow", lambda: NOW)

    result = module.main(
        [
            "--firestore_project",
            "test-project",
            "--firestore_database",
            "(default)",
            "--output_report_json",
            str(report_path),
        ]
    )

    assert result == 0
    assert fs.data["avatarJobs"]["job_1"]["status"] == "running"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["dryRun"] is True
    assert report["stale"] == 1
