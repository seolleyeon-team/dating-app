from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover - optional in pure unit tests
    firestore = None  # type: ignore[assignment]

try:
    from avatar_generation.cost import AvatarCostConfig, evaluate_cost_guard
except Exception:  # pragma: no cover - keeps lease helpers usable during partial installs
    AvatarCostConfig = None  # type: ignore[assignment]
    evaluate_cost_guard = None  # type: ignore[assignment]


DEFAULT_SOURCE_PHOTO_BUCKET = "seolleyeon-private-source-photos"
DEFAULT_LEASE_SECONDS = 30 * 60
DEFAULT_HEARTBEAT_SECONDS = 60
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_BATCH_SIZE = 5
DEFAULT_DEADLINE_SAFETY_SECONDS = 60
DEFAULT_MAX_SCAN = 250
DEFAULT_MAX_BATCH_SECONDS = 20 * 60
DEFAULT_MAX_IDLE_WAIT_SECONDS = 30
DEFAULT_POLL_INTERVAL_SECONDS = 2
DEFAULT_CONCURRENCY_PER_GPU = 1
DEFAULT_CANDIDATES_PER_USER = 4

TERMINAL_STATUSES = {"preview_ready", "approved", "cancelled", "superseded"}
RETRYABLE_FAILED_FLAGS = ("retryable", "isRetryable", "errorRetryable")
LEGACY_PROCESSING_FIELDS = {
    "attempt": "attempt",
    "batchId": "batchId",
    "leaseOwner": "leaseOwner",
    "leaseToken": "leaseToken",
    "leaseExpiresAt": "leaseExpiresAt",
    "leaseHeartbeatAt": "leaseHeartbeatAt",
    "startedAt": "startedAt",
    "lastErrorCode": "errorCode",
    "lastErrorMessage": "errorMessage",
}


class AvatarJobLeaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class AvatarJobLeaseConfig:
    lease_seconds: int = DEFAULT_LEASE_SECONDS
    heartbeat_seconds: int = DEFAULT_HEARTBEAT_SECONDS
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    batch_size: int = DEFAULT_BATCH_SIZE
    deadline_safety_seconds: int = DEFAULT_DEADLINE_SAFETY_SECONDS
    max_scan: int = DEFAULT_MAX_SCAN
    source_photo_bucket: str = DEFAULT_SOURCE_PHOTO_BUCKET
    batching_enabled: bool = True
    batch_mode: str = "drain"
    max_batch_seconds: int = DEFAULT_MAX_BATCH_SECONDS
    max_idle_wait_seconds: int = DEFAULT_MAX_IDLE_WAIT_SECONDS
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS
    require_approved_source_consent: bool = True
    concurrency_per_gpu: int = DEFAULT_CONCURRENCY_PER_GPU
    candidates_per_user: int = DEFAULT_CANDIDATES_PER_USER
    allow_stale_lease_recovery: bool = True
    force_single_job_mode: bool = False

    @classmethod
    def from_env(cls) -> "AvatarJobLeaseConfig":
        return cls(
            lease_seconds=_env_int(
                ("AVATAR_BATCH_LEASE_SECONDS", "AVATAR_JOB_LEASE_SECONDS", "AVATAR_LEASE_SECONDS"),
                DEFAULT_LEASE_SECONDS,
            ),
            heartbeat_seconds=_env_int(
                ("AVATAR_JOB_HEARTBEAT_SECONDS", "AVATAR_HEARTBEAT_SECONDS"),
                DEFAULT_HEARTBEAT_SECONDS,
            ),
            max_attempts=_env_int(
                ("AVATAR_BATCH_MAX_ATTEMPTS", "AVATAR_JOB_MAX_ATTEMPTS", "AVATAR_MAX_ATTEMPTS"),
                DEFAULT_MAX_ATTEMPTS,
            ),
            batch_size=_env_int(
                ("AVATAR_BATCH_MAX_JOBS", "AVATAR_JOB_BATCH_SIZE", "AVATAR_CLAIM_BATCH_SIZE"),
                DEFAULT_BATCH_SIZE,
            ),
            deadline_safety_seconds=_env_int(
                (
                    "AVATAR_BATCH_SOFT_STOP_BEFORE_DEADLINE_SECONDS",
                    "AVATAR_JOB_DEADLINE_SAFETY_SECONDS",
                    "AVATAR_DEADLINE_SAFETY_SECONDS",
                ),
                DEFAULT_DEADLINE_SAFETY_SECONDS,
            ),
            max_scan=_env_int(("AVATAR_JOB_MAX_SCAN", "AVATAR_CLAIM_MAX_SCAN"), DEFAULT_MAX_SCAN),
            source_photo_bucket=_env_str(("SOURCE_PHOTO_BUCKET", "AVATAR_SOURCE_PHOTO_BUCKET"), DEFAULT_SOURCE_PHOTO_BUCKET),
            batching_enabled=_env_bool_any(("AVATAR_BATCHING_ENABLED",), True),
            batch_mode=_env_str(("AVATAR_BATCH_MODE",), "drain"),
            max_batch_seconds=_env_int(("AVATAR_BATCH_MAX_SECONDS",), DEFAULT_MAX_BATCH_SECONDS),
            max_idle_wait_seconds=_env_int(
                ("AVATAR_BATCH_MAX_IDLE_WAIT_SECONDS",),
                DEFAULT_MAX_IDLE_WAIT_SECONDS,
            ),
            poll_interval_seconds=_env_int(
                ("AVATAR_BATCH_POLL_INTERVAL_SECONDS",),
                DEFAULT_POLL_INTERVAL_SECONDS,
            ),
            require_approved_source_consent=_env_bool_any(
                ("AVATAR_BATCH_REQUIRE_APPROVED_SOURCE_CONSENT",),
                True,
            ),
            concurrency_per_gpu=_env_int(
                ("AVATAR_BATCH_CONCURRENCY_PER_GPU",),
                DEFAULT_CONCURRENCY_PER_GPU,
            ),
            candidates_per_user=_env_int(
                ("AVATAR_BATCH_CANDIDATES_PER_USER",),
                DEFAULT_CANDIDATES_PER_USER,
            ),
            allow_stale_lease_recovery=_env_bool_any(("AVATAR_ALLOW_STALE_LEASE_RECOVERY",), True),
            force_single_job_mode=_env_bool_any(("AVATAR_FORCE_SINGLE_JOB_MODE",), False),
        )


@dataclass(frozen=True)
class ClaimDeadline:
    deadline_at: datetime
    safety_seconds: int = DEFAULT_DEADLINE_SAFETY_SECONDS

    @classmethod
    def from_timeout(
        cls,
        timeout_seconds: int,
        *,
        now: Optional[datetime] = None,
        safety_seconds: int = DEFAULT_DEADLINE_SAFETY_SECONDS,
    ) -> "ClaimDeadline":
        return cls(deadline_at=(now or utcnow()) + timedelta(seconds=max(0, timeout_seconds)), safety_seconds=safety_seconds)

    def remaining_seconds(self, *, now: Optional[datetime] = None) -> float:
        current = now or utcnow()
        return (normalize_datetime(self.deadline_at) - normalize_datetime(current)).total_seconds()

    def should_stop(self, *, now: Optional[datetime] = None) -> bool:
        return self.remaining_seconds(now=now) <= max(0, self.safety_seconds)


@dataclass(frozen=True)
class LeasedAvatarJob:
    job_id: str
    uid: str
    attempt: int
    lease_owner: str
    lease_token: str
    lease_expires_at: datetime
    batch_id: str
    payload: Dict[str, Any]


@dataclass
class LeaseSweepSummary:
    dry_run: bool
    scanned: int = 0
    stale: int = 0
    requeued: int = 0
    failed: int = 0
    skipped: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dryRun": self.dry_run,
            "scanned": self.scanned,
            "stale": self.stale,
            "requeued": self.requeued,
            "failed": self.failed,
            "skipped": list(self.skipped),
        }


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def claim_next_avatar_job(
    firestore_client: Any,
    *,
    worker_id: str,
    now: Optional[datetime] = None,
    config: Optional[AvatarJobLeaseConfig] = None,
    deadline: Optional[ClaimDeadline] = None,
    max_scan: Optional[int] = None,
    batch_id: str = "",
) -> Optional[LeasedAvatarJob]:
    config = config or AvatarJobLeaseConfig.from_env()
    current = normalize_datetime(now or utcnow())
    if (
        not avatar_job_claims_enabled()
        or not _cost_guard_allows_claims(firestore_client, current)
        or _deadline_reached(deadline, current)
    ):
        return None

    scanned = 0
    for job_id, _doc in _sorted_job_docs(firestore_client):
        if max_scan is not None and scanned >= max_scan:
            break
        if scanned >= config.max_scan:
            break
        scanned += 1
        if _deadline_reached(deadline, current):
            return None
        lease = try_claim_avatar_job(
            firestore_client,
            job_id,
            worker_id=worker_id,
            now=current,
            config=config,
            deadline=deadline,
            batch_id=batch_id,
        )
        if lease is not None:
            return lease
    return None


def try_claim_avatar_job(
    firestore_client: Any,
    job_id: str,
    *,
    worker_id: str,
    now: Optional[datetime] = None,
    config: Optional[AvatarJobLeaseConfig] = None,
    deadline: Optional[ClaimDeadline] = None,
    batch_id: str = "",
) -> Optional[LeasedAvatarJob]:
    config = config or AvatarJobLeaseConfig.from_env()
    current = normalize_datetime(now or utcnow())
    if (
        not avatar_job_claims_enabled()
        or not _cost_guard_allows_claims(firestore_client, current)
        or _deadline_reached(deadline, current)
    ):
        return None

    job_ref = _doc_ref(firestore_client, "avatarJobs", job_id)

    def _claim(transaction: Any = None) -> Optional[LeasedAvatarJob]:
        snapshot = _get_doc(job_ref, transaction=transaction)
        job_doc = _doc_to_dict(snapshot)
        if job_doc is None:
            return None
        if not _is_claimable_status(job_doc, now=current, config=config):
            return None

        source_refs = _source_refs(job_doc)
        if not _private_source_refs_are_valid(source_refs, config.source_photo_bucket):
            _mark_job_rejected(
                job_ref,
                transaction=transaction,
                now=current,
                job_doc=job_doc,
                error_code="invalid_source_refs",
                error_message="Avatar generation source refs are missing or not private.",
            )
            return None

        uid = str(job_doc.get("uid") or "").strip()
        if not uid:
            _mark_job_rejected(
                job_ref,
                transaction=transaction,
                now=current,
                job_doc=job_doc,
                error_code="invalid_avatar_job",
                error_message="Avatar generation job is missing required user metadata.",
            )
            return None

        private_doc = _load_private_media_doc(firestore_client, uid, transaction=transaction)
        if not _consent_allows_avatar_generation(
            private_doc,
            source_refs,
            require_doc=config.require_approved_source_consent,
        ):
            _mark_job_rejected(
                job_ref,
                transaction=transaction,
                now=current,
                job_doc=job_doc,
                error_code="avatar_consent_not_granted",
                error_message="Avatar generation consent is unavailable or revoked.",
            )
            return None

        attempt = _attempt(job_doc) + 1
        lease_token = uuid.uuid4().hex
        lease_expires_at = current + timedelta(seconds=max(1, config.lease_seconds))
        lease_batch_id = str(batch_id or "").strip()
        processing = _merged_processing(
            job_doc,
            {
                "attempt": attempt,
                "batchId": lease_batch_id,
                "leaseOwner": worker_id,
                "leaseToken": lease_token,
                "leaseExpiresAt": lease_expires_at,
                "leaseHeartbeatAt": current,
                "startedAt": current,
                "lastErrorCode": "",
                "lastErrorMessage": "",
            },
        )
        update = {
            "status": "running",
            "processing": processing,
            "retryable": False,
            "updatedAt": current,
        }
        _update_doc(job_ref, update, transaction=transaction)

        payload = _claim_payload(job_doc, job_id=job_id, processing=processing, config=config)
        return LeasedAvatarJob(
            job_id=str(payload["jobId"]),
            uid=uid,
            attempt=attempt,
            lease_owner=worker_id,
            lease_token=lease_token,
            lease_expires_at=lease_expires_at,
            batch_id=lease_batch_id,
            payload=payload,
        )

    return _run_transaction(firestore_client, _claim)


def heartbeat_avatar_job_lease(
    firestore_client: Any,
    job_id: str,
    *,
    lease_token: str,
    worker_id: Optional[str] = None,
    now: Optional[datetime] = None,
    config: Optional[AvatarJobLeaseConfig] = None,
) -> bool:
    return update_avatar_job_lease(
        firestore_client,
        job_id,
        lease_token=lease_token,
        worker_id=worker_id,
        now=now,
        config=config,
        updates={},
        extend=True,
    )


def update_avatar_job_lease(
    firestore_client: Any,
    job_id: str,
    *,
    lease_token: str,
    worker_id: Optional[str] = None,
    updates: Mapping[str, Any],
    now: Optional[datetime] = None,
    config: Optional[AvatarJobLeaseConfig] = None,
    extend: bool = True,
) -> bool:
    if not lease_token:
        return False
    config = config or AvatarJobLeaseConfig.from_env()
    current = normalize_datetime(now or utcnow())
    job_ref = _doc_ref(firestore_client, "avatarJobs", job_id)

    def _update(transaction: Any = None) -> bool:
        snapshot = _get_doc(job_ref, transaction=transaction)
        job_doc = _doc_to_dict(snapshot)
        if job_doc is None:
            return False
        if str(job_doc.get("status") or "") != "running":
            return False
        if str(_processing_value(job_doc, "leaseToken") or "") != lease_token:
            return False
        if worker_id is not None and str(_processing_value(job_doc, "leaseOwner") or "") != worker_id:
            return False
        lease_expires_at = parse_datetime(_processing_value(job_doc, "leaseExpiresAt"))
        if lease_expires_at is not None and lease_expires_at < current:
            return False

        safe_updates = dict(updates)
        processing_update = dict(safe_updates.pop("processing", {}) or {})
        processing_update["leaseHeartbeatAt"] = current
        safe_updates["updatedAt"] = current
        if extend:
            processing_update["leaseExpiresAt"] = current + timedelta(seconds=max(1, config.lease_seconds))
        safe_updates["processing"] = _merged_processing(job_doc, processing_update)
        _update_doc(job_ref, safe_updates, transaction=transaction)
        return True

    return bool(_run_transaction(firestore_client, _update))


def sweep_stale_avatar_job_leases(
    firestore_client: Any,
    *,
    now: Optional[datetime] = None,
    config: Optional[AvatarJobLeaseConfig] = None,
    dry_run: bool = True,
    max_jobs: Optional[int] = None,
) -> LeaseSweepSummary:
    config = config or AvatarJobLeaseConfig.from_env()
    current = normalize_datetime(now or utcnow())
    summary = LeaseSweepSummary(dry_run=dry_run)
    stale_processed = 0

    for job_id, job_doc in _sorted_job_docs(firestore_client):
        summary.scanned += 1
        if str(job_doc.get("status") or "") != "running":
            continue
        if not config.allow_stale_lease_recovery:
            continue
        if not _lease_is_expired(job_doc, current):
            continue
        if max_jobs is not None and stale_processed >= max_jobs:
            break
        summary.stale += 1
        stale_processed += 1
        if dry_run:
            continue

        job_ref = _doc_ref(firestore_client, "avatarJobs", job_id)
        attempt = _attempt(job_doc)
        if attempt < config.max_attempts:
            processing = _merged_processing(
                job_doc,
                {
                    "leaseOwner": "",
                    "leaseToken": "",
                    "leaseExpiresAt": None,
                    "leaseHeartbeatAt": None,
                    "batchId": "",
                    "lastErrorCode": "lease_expired",
                    "lastErrorMessage": "Avatar generation lease expired before completion.",
                },
            )
            _update_doc(
                job_ref,
                {
                    "status": "queued",
                    "retryable": True,
                    "processing": processing,
                    "updatedAt": current,
                },
            )
            summary.requeued += 1
        else:
            processing = _merged_processing(
                job_doc,
                {
                    "leaseOwner": "",
                    "leaseToken": "",
                    "leaseExpiresAt": None,
                    "leaseHeartbeatAt": None,
                    "batchId": "",
                    "lastErrorCode": "lease_expired_max_attempts",
                    "lastErrorMessage": "Avatar generation lease expired after max attempts.",
                },
            )
            _update_doc(
                job_ref,
                {
                    "status": "failed",
                    "retryable": False,
                    "processing": processing,
                    "updatedAt": current,
                },
            )
            summary.failed += 1

    return summary


def avatar_job_claims_enabled() -> bool:
    if _env_bool("AVATAR_GPU_WORKER_ENABLED", True) is False:
        return False
    if _env_bool_any(("AVATAR_DISABLE_NEW_GENERATION", "AVATAR_GENERATION_DISABLED", "AVATAR_GENERATION_PAUSED"), False) is True:
        return False
    if _env_bool_any(("AVATAR_COST_KILL_SWITCH_ENABLED", "AVATAR_KILL_SWITCH", "AVATAR_GENERATION_BUDGET_EXHAUSTED"), False) is True:
        return False
    return True


def _production_environment() -> bool:
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    node_env = os.environ.get("NODE_ENV", "").strip().lower()
    return environment in {"production", "prod", "production_bridge"} or node_env == "production"


def _cost_guard_allows_claims(firestore_client: Any, now: datetime) -> bool:
    if AvatarCostConfig is None or evaluate_cost_guard is None:
        return not _production_environment()
    config = AvatarCostConfig.from_env()
    if _production_environment() and not config.enforce_budget:
        return False
    result = evaluate_cost_guard(
        firestore_client,
        now=now,
        config=config,
    )
    return bool(result.allowed)


def default_firestore_client(project: Optional[str] = None, database: Optional[str] = None) -> Any:
    if firestore is None:
        raise AvatarJobLeaseError("google-cloud-firestore is required.")
    kwargs: Dict[str, Any] = {}
    if project:
        kwargs["project"] = project
    if database:
        kwargs["database"] = database
    return firestore.Client(**kwargs)


def _env_str(names: Sequence[str], fallback: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return fallback


def _env_int(names: Sequence[str], fallback: int) -> int:
    for name in names:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        try:
            return max(1, int(raw))
        except ValueError:
            return fallback
    return fallback


def _env_bool(name: str, fallback: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return fallback
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise AvatarJobLeaseError(f"{name} must be a boolean value.")


def _env_bool_any(names: Sequence[str], fallback: bool) -> bool:
    found_explicit = False
    for name in names:
        raw = os.environ.get(name)
        if raw is None or not raw.strip():
            continue
        found_explicit = True
        if _env_bool(name, False):
            return True
    return False if found_explicit else fallback

def _deadline_reached(deadline: Optional[ClaimDeadline], now: datetime) -> bool:
    return deadline is not None and deadline.should_stop(now=now)


def _doc_ref(client: Any, collection: str, doc_id: str) -> Any:
    col = client.collection(collection)
    if hasattr(col, "document"):
        return col.document(doc_id)
    return col.doc(doc_id)


def _doc_to_dict(snapshot: Any) -> Optional[Dict[str, Any]]:
    if not bool(getattr(snapshot, "exists", False)):
        return None
    if hasattr(snapshot, "to_dict"):
        data = snapshot.to_dict()
    elif hasattr(snapshot, "data"):
        data = snapshot.data()
    else:
        data = None
    return dict(data or {})


def _get_doc(ref: Any, *, transaction: Any = None) -> Any:
    if transaction is not None:
        try:
            return ref.get(transaction=transaction)
        except TypeError:
            if hasattr(transaction, "get"):
                return transaction.get(ref)
            raise
    return ref.get()


def _update_doc(ref: Any, payload: Mapping[str, Any], *, transaction: Any = None) -> None:
    data = dict(payload)
    if transaction is not None and hasattr(transaction, "update"):
        transaction.update(ref, data)
        return
    if hasattr(ref, "update"):
        ref.update(data)
    else:
        ref.set(data, merge=True)


def _run_transaction(client: Any, callback: Callable[[Any], Any]) -> Any:
    if firestore is not None and hasattr(client, "transaction"):
        transaction_factory = getattr(client, "transaction", None)
        transactional = getattr(firestore, "transactional", None)
        if transaction_factory is not None and transactional is not None:
            transaction = transaction_factory()
            if getattr(transaction, "_codex_fake_transaction", False):
                return callback(transaction)

            @transactional
            def _wrapped(active_transaction: Any) -> Any:
                return callback(active_transaction)

            return _wrapped(transaction)
    return callback(None)


def _stream_collection(client: Any, collection: str) -> Iterable[Tuple[str, Dict[str, Any]]]:
    col = client.collection(collection)
    if hasattr(col, "stream"):
        for snap in col.stream():
            data = _doc_to_dict(snap)
            if data is not None:
                yield str(getattr(snap, "id", data.get("jobId", ""))), data
        return
    if hasattr(client, "data"):
        for doc_id, data in client.data.get(collection, {}).items():
            yield str(doc_id), dict(data)


def _sorted_job_docs(client: Any) -> List[Tuple[str, Dict[str, Any]]]:
    docs = list(_stream_collection(client, "avatarJobs"))
    return sorted(docs, key=lambda item: (_sort_timestamp(item[1].get("createdAt")), item[0]))


def _sort_timestamp(value: Any) -> float:
    parsed = parse_datetime(value)
    if parsed is None:
        return 0.0
    return parsed.timestamp()


def parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return normalize_datetime(value)
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000.0
        return datetime.fromtimestamp(number, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return normalize_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    if hasattr(value, "to_datetime"):
        return normalize_datetime(value.to_datetime())
    if hasattr(value, "timestamp"):
        return datetime.fromtimestamp(value.timestamp(), tz=timezone.utc)
    return None


def _processing(job_doc: Mapping[str, Any]) -> Dict[str, Any]:
    processing = job_doc.get("processing")
    if isinstance(processing, Mapping):
        return dict(processing)
    return {}


def _processing_value(job_doc: Mapping[str, Any], key: str) -> Any:
    processing = _processing(job_doc)
    if key in processing:
        return processing.get(key)
    legacy_key = LEGACY_PROCESSING_FIELDS.get(key)
    if legacy_key:
        return job_doc.get(legacy_key)
    return None


def _merged_processing(job_doc: Mapping[str, Any], updates: Mapping[str, Any]) -> Dict[str, Any]:
    processing = _processing(job_doc)
    for key, value in updates.items():
        processing[key] = value
    return processing


def _claim_payload(
    job_doc: Mapping[str, Any],
    *,
    job_id: str,
    processing: Mapping[str, Any],
    config: AvatarJobLeaseConfig,
) -> Dict[str, Any]:
    source_refs = _source_refs(job_doc)
    source_photo_ids = job_doc.get("sourcePhotoIds")
    if isinstance(source_photo_ids, str) or not isinstance(source_photo_ids, Sequence):
        source_photo_ids = []
    candidate_count = job_doc.get("candidateCount") or config.candidates_per_user
    return {
        "jobId": str(job_doc.get("jobId") or job_id),
        "uid": str(job_doc.get("uid") or ""),
        "sourcePhotoIds": [str(value) for value in source_photo_ids if str(value).strip()],
        "sourcePhotoRefCount": len(source_refs),
        "candidateCount": int(candidate_count),
        "modelId": str(job_doc.get("modelId") or ""),
        "jobType": str(job_doc.get("jobType") or "avatar_generation"),
        "schemaVersion": str(job_doc.get("schemaVersion") or "avatar_job_v1"),
        "idempotencyKey": str(job_doc.get("idempotencyKey") or ""),
        "processing": dict(processing),
    }


def _attempt(job_doc: Mapping[str, Any]) -> int:
    try:
        return max(0, int(_processing_value(job_doc, "attempt") or 0))
    except (TypeError, ValueError):
        return 0


def _is_claimable_status(job_doc: Mapping[str, Any], *, now: datetime, config: AvatarJobLeaseConfig) -> bool:
    status = str(job_doc.get("status") or "").strip()
    if status in TERMINAL_STATUSES:
        return False
    attempt = _attempt(job_doc)
    if attempt >= config.max_attempts:
        return False
    if status == "queued":
        return True
    if status == "running":
        return config.allow_stale_lease_recovery and _lease_is_expired(job_doc, now)
    if status == "failed":
        return _is_retryable_failed(job_doc)
    return False


def _is_retryable_failed(job_doc: Mapping[str, Any]) -> bool:
    processing = _processing(job_doc)
    return any(job_doc.get(flag) is True or processing.get(flag) is True for flag in RETRYABLE_FAILED_FLAGS)


def _lease_is_expired(job_doc: Mapping[str, Any], now: datetime) -> bool:
    expires_at = parse_datetime(_processing_value(job_doc, "leaseExpiresAt"))
    if expires_at is None:
        return True
    return expires_at <= now


def _source_refs(job_doc: Mapping[str, Any]) -> List[str]:
    raw_refs = job_doc.get("sourcePhotoRefs")
    if isinstance(raw_refs, str) or not isinstance(raw_refs, Sequence):
        return []
    return [str(value).strip() for value in raw_refs if str(value).strip()]


def _private_source_refs_are_valid(source_refs: Sequence[str], allowed_bucket: str) -> bool:
    if not source_refs:
        return False
    for source_ref in source_refs:
        parsed = _parse_gcs_ref(source_ref)
        if parsed is None:
            return False
        bucket, path = parsed
        if bucket != allowed_bucket:
            return False
        if "?" in path or "#" in path:
            return False
    return True


def _parse_gcs_ref(value: str) -> Optional[Tuple[str, str]]:
    match = re.match(r"^(?:gs|gcs)://([^/]+)/(.+)$", str(value).strip())
    if not match:
        return None
    bucket = match.group(1).strip()
    path = match.group(2).strip()
    if not bucket or not path or path.startswith("/") or ".." in path.split("/"):
        return None
    return bucket, path


def _load_private_media_doc(client: Any, uid: str, *, transaction: Any = None) -> Optional[Dict[str, Any]]:
    snapshot = _get_doc(_doc_ref(client, "userPrivateMedia", uid), transaction=transaction)
    return _doc_to_dict(snapshot)


def _consent_allows_avatar_generation(
    private_doc: Optional[Mapping[str, Any]],
    source_refs: Sequence[str],
    *,
    require_doc: bool,
) -> bool:
    if private_doc is None:
        return not require_doc
    consent = private_doc.get("photoConsent")
    if not isinstance(consent, Mapping):
        return False
    if consent.get("avatarGeneration") is not True:
        return False
    if consent.get("profileDisplayOriginalPhoto") is not False:
        return False

    source_photos = private_doc.get("sourcePhotos")
    if not isinstance(source_photos, Sequence) or isinstance(source_photos, str):
        return False
    active_refs = {
        str(entry.get("gcsUri") or "").strip()
        for entry in source_photos
        if isinstance(entry, Mapping)
        and entry.get("status") == "active"
        and isinstance(entry.get("purpose"), Mapping)
        and entry["purpose"].get("avatarGeneration") is True
    }
    return all(source_ref in active_refs for source_ref in source_refs)


def _mark_job_rejected(
    job_ref: Any,
    *,
    transaction: Any,
    now: datetime,
    job_doc: Mapping[str, Any],
    error_code: str,
    error_message: str,
) -> None:
    processing = _merged_processing(
        job_doc,
        {
            "leaseOwner": "",
            "leaseToken": "",
            "leaseExpiresAt": None,
            "leaseHeartbeatAt": None,
            "batchId": "",
            "lastErrorCode": error_code,
            "lastErrorMessage": error_message,
        },
    )
    _update_doc(
        job_ref,
        {
            "status": "failed",
            "retryable": False,
            "processing": processing,
            "updatedAt": now,
        },
        transaction=transaction,
    )
