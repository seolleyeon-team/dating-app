#!/usr/bin/env python3
"""CI-safe PR7-F avatar pipeline load, lease, cost, and privacy drill."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.cost import AvatarCostConfig, estimate_batch_cost  # noqa: E402
from avatar_generation.job_lease import (  # noqa: E402
    AvatarJobLeaseConfig,
    claim_next_avatar_job,
    default_firestore_client,
    sweep_stale_avatar_job_leases,
    try_claim_avatar_job,
    utcnow,
)


PRIVACY_QA_MARKER = "pr7f_privacy_qa_pass"
PRIVATE_BUCKET = "seolleyeon-private-source-photos"
TEMP_BUCKET = "seolleyeon-avatar-temp"
SIGNED_URL_MARKERS = (
    "X-Goog-",
    "GoogleAccessId",
    "Signature=",
    "Expires=",
    "X-Amz-",
    "AWSAccessKeyId",
)


class FakeSnapshot:
    def __init__(self, doc_id: str, data: Optional[Mapping[str, Any]]):
        self.id = doc_id
        self._data = dict(data or {}) if data is not None else None
        self.exists = data is not None

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data or {})


class FakeDocRef:
    def __init__(self, store: dict[str, dict[str, dict[str, Any]]], collection: str, doc_id: str):
        self.store = store
        self.collection = collection
        self.doc_id = doc_id

    def get(self, **_kwargs: Any) -> FakeSnapshot:
        return FakeSnapshot(self.doc_id, self.store.get(self.collection, {}).get(self.doc_id))

    def set(self, data: Mapping[str, Any], merge: bool = True) -> None:
        collection = self.store.setdefault(self.collection, {})
        if merge and self.doc_id in collection:
            collection[self.doc_id].update(dict(data))
        else:
            collection[self.doc_id] = dict(data)

    def update(self, data: Mapping[str, Any]) -> None:
        self.set(data, merge=True)


class FakeCollection:
    def __init__(self, store: dict[str, dict[str, dict[str, Any]]], name: str):
        self.store = store
        self.name = name

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(self.store, self.name, doc_id)

    def stream(self) -> list[FakeSnapshot]:
        return [
            FakeSnapshot(doc_id, data)
            for doc_id, data in self.store.get(self.name, {}).items()
        ]


class FakeFirestore:
    def __init__(self, data: dict[str, dict[str, dict[str, Any]]]):
        self.data = data

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self.data, name)


def _source_ref(uid: str, source_id: str = "src_001") -> str:
    return f"gs://{PRIVATE_BUCKET}/users/{uid}/source/{source_id}.jpg"


def _job_doc(job_id: str, uid: str, *, now: datetime, candidate_count: int = 4) -> dict[str, Any]:
    return {
        "jobId": job_id,
        "uid": uid,
        "status": "queued",
        "sourcePhotoIds": ["src_001"],
        "sourcePhotoRefs": [_source_ref(uid)],
        "candidateCount": int(candidate_count),
        "createdAt": now,
        "processing": {"attempt": 0},
        "privacyQaMarker": PRIVACY_QA_MARKER,
    }


def _private_media_doc(uid: str) -> dict[str, Any]:
    return {
        "photoConsent": {
            "avatarGeneration": True,
            "profileDisplayOriginalPhoto": False,
        },
        "sourcePhotos": [
            {
                "photoId": "src_001",
                "gcsUri": _source_ref(uid),
                "status": "active",
                "purpose": {"avatarGeneration": True},
            }
        ],
    }


def build_emulator_fixture(
    *,
    job_count: int,
    candidate_count: int = 4,
    now: Optional[datetime] = None,
) -> FakeFirestore:
    current = now or utcnow()
    jobs: dict[str, dict[str, Any]] = {}
    private_media: dict[str, dict[str, Any]] = {}
    for index in range(job_count):
        uid = f"load_user_{index:04d}"
        job_id = f"load_job_{index:04d}"
        jobs[job_id] = _job_doc(job_id, uid, now=current, candidate_count=candidate_count)
        private_media[uid] = _private_media_doc(uid)
    return FakeFirestore({"avatarJobs": jobs, "userPrivateMedia": private_media})


def _stream_jobs(firestore_client: Any) -> list[dict[str, Any]]:
    return [
        dict(snapshot.to_dict() or {})
        for snapshot in firestore_client.collection("avatarJobs").stream()
    ]


def _privacy_status(emitted: Any) -> dict[str, Any]:
    encoded = json.dumps(emitted, default=str)
    has_private_ref = PRIVATE_BUCKET in encoded
    has_temp_ref = TEMP_BUCKET in encoded
    has_source_path = "/source/" in encoded or "\\source\\" in encoded
    has_signed_url = any(marker in encoded for marker in SIGNED_URL_MARKERS)
    leaked = has_private_ref or has_temp_ref or has_source_path or has_signed_url
    return {
        "status": "fail" if leaked else "pass",
        "leakageCheck": "fail" if leaked else "pass",
        "qaMarker": PRIVACY_QA_MARKER,
        "sourceRefsEmitted": bool(has_private_ref or has_temp_ref or has_source_path),
        "tempRefsEmitted": bool(has_temp_ref),
        "signedUrlsEmitted": bool(has_signed_url),
        "userIdsEmitted": False,
        "jobIdsEmitted": False,
    }


def _cost_report(
    claimed_jobs: Sequence[Mapping[str, Any]],
    *,
    num_users: int,
    simulate_worker: bool,
    claim_loop_seconds: float,
    config: AvatarJobLeaseConfig,
) -> dict[str, Any]:
    simulated_worker_seconds = len(claimed_jobs) * 30.0 if simulate_worker else 0.0
    approved_avatar_count = len(claimed_jobs) if simulate_worker else 0
    batch = estimate_batch_cost(
        claimed_jobs,
        duration_seconds=max(1.0, simulated_worker_seconds),
        config=AvatarCostConfig.from_env(),
    )
    batch_size = max(1, int(config.batch_size or 1))
    estimated_usd = batch.total_cost.usd
    return {
        "candidateCount": sum(int(job.get("candidateCount") or 4) for job in claimed_jobs),
        "estimatedBatches": math.ceil(len(claimed_jobs) / batch_size) if claimed_jobs else 0,
        "estimatedGpuSeconds": round(simulated_worker_seconds, 3),
        "totalSimulatedWorkerSeconds": round(simulated_worker_seconds, 3),
        "estimatedUsd": estimated_usd,
        "estimatedCostPerUser": round(estimated_usd / max(1, int(num_users)), 6),
        "costPerApprovedAvatar": (
            round(estimated_usd / approved_avatar_count, 6)
            if approved_avatar_count > 0
            else None
        ),
        "pricingVersion": batch.total_cost.pricing_version,
        "timing": {
            "claimLoopSeconds": round(max(0.0, claim_loop_seconds), 6),
            "estimatedBatchRuntimeSeconds": round(max(1.0, simulated_worker_seconds), 3),
        },
    }


def run_stale_lease_drill(
    firestore_client: Any,
    *,
    now: Optional[datetime] = None,
    config: Optional[AvatarJobLeaseConfig] = None,
) -> dict[str, Any]:
    summary = sweep_stale_avatar_job_leases(
        firestore_client,
        now=now or utcnow(),
        config=config or AvatarJobLeaseConfig.from_env(),
        dry_run=False,
    ).to_dict()
    return {
        "staleLeases": {
            "found": summary["stale"],
            "requeued": summary["requeued"],
            "failed": summary["failed"],
            "dryRun": False,
        }
    }


def run_load_test(
    *,
    firestore_client: Any,
    num_users: Optional[int] = None,
    users: Optional[int] = None,
    jobs_per_user: int = 1,
    candidate_count: int = 4,
    ci_jobs: int,
    simulate_worker: bool = False,
    dry_run: bool,
    no_real_gcs: bool,
    no_real_gpu: bool,
    firestore_emulator: bool,
    now: Optional[datetime] = None,
    config: Optional[AvatarJobLeaseConfig] = None,
) -> dict[str, Any]:
    current = now or utcnow()
    effective_users = int(num_users if num_users is not None else users if users is not None else 1000)
    lease_config = config or AvatarJobLeaseConfig.from_env()
    start = time.perf_counter()
    leases = []
    for _ in range(max(0, ci_jobs)):
        lease = claim_next_avatar_job(
            firestore_client,
            worker_id="pr7f-load-test",
            now=current,
            config=lease_config,
        )
        if lease is None:
            break
        leases.append(lease)
    claim_loop_seconds = time.perf_counter() - start

    duplicate_attempts = 0
    for lease in leases:
        duplicate = try_claim_avatar_job(
            firestore_client,
            lease.job_id,
            worker_id=f"duplicate-check-{lease.job_id}",
            now=current,
            config=lease_config,
        )
        if duplicate is not None and duplicate.job_id == lease.job_id:
            duplicate_attempts += 1

    jobs = _stream_jobs(firestore_client)
    claimed_ids = [lease.job_id for lease in leases]
    claimed_jobs = [
        job for job in jobs if str(job.get("jobId") or "") in set(claimed_ids)
    ]
    stale = sweep_stale_avatar_job_leases(
        firestore_client,
        now=current,
        config=lease_config,
        dry_run=True,
    ).to_dict()
    failed_count = sum(1 for job in jobs if job.get("status") == "failed")
    retryable_count = sum(1 for job in jobs if job.get("retryable") is True)
    batch_size = max(1, int(lease_config.batch_size or 1))
    number_of_batches = math.ceil(len(leases) / batch_size) if leases else 0

    report = {
        "generatedAt": current.isoformat(),
        "mode": {
            "dryRun": bool(dry_run),
            "firestoreEmulator": bool(firestore_emulator),
            "ciSafe": bool(dry_run and no_real_gcs and no_real_gpu and firestore_emulator),
        },
        "simulation": {
            "numUsers": effective_users,
            "users": effective_users,
            "jobsPerUser": int(jobs_per_user),
            "candidateCount": int(candidate_count),
            "ciJobs": int(ci_jobs),
            "simulateWorker": bool(simulate_worker),
            "defaultUsersScenario": 1000,
            "ciModeJobs": 10,
        },
        "claims": {
            "attempted": int(ci_jobs),
            "claimed": len(leases),
            "remainingQueued": sum(1 for job in jobs if job.get("status") == "queued"),
        },
        "duplicatePrevention": {
            "duplicateClaims": duplicate_attempts,
            "uniqueClaimedJobs": len(set(claimed_ids)),
        },
        "staleLeases": {
            "found": stale["stale"],
            "simulated": stale["stale"],
            "requeued": stale["requeued"],
            "recovered": stale["requeued"],
            "dryRun": stale["dryRun"],
        },
        "cost": _cost_report(
            claimed_jobs,
            num_users=effective_users,
            simulate_worker=simulate_worker,
            claim_loop_seconds=claim_loop_seconds,
            config=lease_config,
        ),
        "batches": {
            "batchSize": lease_config.batch_size,
            "numberOfBatches": number_of_batches,
            "averageBatchSize": round(len(leases) / number_of_batches, 3) if number_of_batches else 0.0,
            "batchingEnabled": lease_config.batching_enabled,
        },
        "failures": {
            "failed": failed_count,
            "duringClaim": max(0, int(ci_jobs) - len(leases) - sum(1 for job in jobs if job.get("status") == "queued")),
        },
        "retries": {
            "retryable": retryable_count,
        },
        "gcs": {"realGcsUsed": not no_real_gcs},
        "gpu": {"realGpuUsed": not no_real_gpu},
        "ok": duplicate_attempts == 0,
    }
    report["privacy"] = _privacy_status(report)
    report["ok"] = bool(report["ok"] and report["privacy"]["status"] == "pass")
    return report


def _write_report(report: Mapping[str, Any], path: Optional[str]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PR7-F CI-safe avatar pipeline load test.")
    parser.add_argument("--num_users", "--users", dest="num_users", type=int, default=1000)
    parser.add_argument("--jobs_per_user", type=int, default=1)
    parser.add_argument("--candidate_count", type=int, default=4)
    parser.add_argument("--batch_size", type=int)
    parser.add_argument("--ci_jobs", type=int)
    parser.add_argument("--simulate_worker", action="store_true")
    parser.add_argument("--dry_run", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no_real_gcs", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no_real_gpu", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--firestore_emulator", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--firestore_project")
    parser.add_argument("--firestore_database")
    parser.add_argument("--report_json", "--output_report_json", dest="output_report_json")
    args = parser.parse_args(argv)

    if not args.no_real_gpu and args.dry_run:
        parser.error("--no_real_gpu=false requires --no-dry_run and an explicit live environment.")
    if not args.dry_run and (args.no_real_gcs or args.no_real_gpu or args.firestore_emulator):
        parser.error("Live mode must explicitly disable dry_run/no_real_gcs/no_real_gpu/firestore_emulator.")

    argv_list = list(argv or [])
    prompt_job_flags_present = "--num_users" in argv_list or "--jobs_per_user" in argv_list
    ci_jobs = (
        int(args.ci_jobs)
        if args.ci_jobs is not None
        else int(args.num_users) * int(args.jobs_per_user)
        if prompt_job_flags_present
        else 10
    )
    lease_config = AvatarJobLeaseConfig.from_env()
    if args.batch_size is not None:
        lease_config = AvatarJobLeaseConfig(
            lease_seconds=lease_config.lease_seconds,
            heartbeat_seconds=lease_config.heartbeat_seconds,
            max_attempts=lease_config.max_attempts,
            batch_size=max(1, int(args.batch_size)),
            deadline_safety_seconds=lease_config.deadline_safety_seconds,
            max_scan=lease_config.max_scan,
            source_photo_bucket=lease_config.source_photo_bucket,
            batching_enabled=lease_config.batching_enabled,
            batch_mode=lease_config.batch_mode,
            max_batch_seconds=lease_config.max_batch_seconds,
            max_idle_wait_seconds=lease_config.max_idle_wait_seconds,
            poll_interval_seconds=lease_config.poll_interval_seconds,
            require_approved_source_consent=lease_config.require_approved_source_consent,
            concurrency_per_gpu=lease_config.concurrency_per_gpu,
            candidates_per_user=lease_config.candidates_per_user,
            allow_stale_lease_recovery=lease_config.allow_stale_lease_recovery,
            force_single_job_mode=lease_config.force_single_job_mode,
        )

    client = (
        build_emulator_fixture(job_count=ci_jobs, candidate_count=args.candidate_count, now=utcnow())
        if args.dry_run or args.firestore_emulator
        else default_firestore_client(args.firestore_project, args.firestore_database)
    )
    report = run_load_test(
        firestore_client=client,
        num_users=args.num_users,
        jobs_per_user=args.jobs_per_user,
        candidate_count=args.candidate_count,
        ci_jobs=ci_jobs,
        simulate_worker=args.simulate_worker,
        dry_run=args.dry_run,
        no_real_gcs=args.no_real_gcs,
        no_real_gpu=args.no_real_gpu,
        firestore_emulator=args.firestore_emulator,
        config=lease_config,
    )
    _write_report(report, args.output_report_json)
    return 0 if report["ok"] else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
