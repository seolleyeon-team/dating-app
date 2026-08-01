from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional


OBSERVABILITY_EVENT_SCHEMA_VERSION = "avatar_observability_event_v1"
OBSERVABILITY_METRIC_SCHEMA_VERSION = "avatar_metric_payload_v1"
OBSERVABILITY_SERVICE = "avatar-generation"
REDACTED_VALUE = "[REDACTED]"

CANONICAL_AVATAR_OBSERVABILITY_EVENTS = {
    "avatar_upload_enqueued",
    "avatar_job_claimed",
    "avatar_batch_started",
    "avatar_model_load_started",
    "avatar_model_load_completed",
    "avatar_job_generation_started",
    "avatar_candidates_generated",
    "avatar_candidate_qa_pass",
    "avatar_candidate_qa_reject",
    "avatar_job_preview_ready",
    "avatar_job_failed",
    "avatar_job_retry_scheduled",
    "avatar_stale_lease_recovered",
    "avatar_batch_completed",
    "avatar_batch_deadline_stop",
    "avatar_cost_guard_paused",
    "avatar_cleanup_completed",
    "avatar_live_gpu_smoke_started",
    "avatar_live_gpu_smoke_completed",
    "avatar_live_iam_check_completed",
}

LEGACY_AVATAR_OBSERVABILITY_EVENT_ALIASES = {
    "avatar.job.claimed",
    "avatar.job.started",
    "avatar.job.completed",
    "avatar.job.failed",
    "avatar.job.retried",
    "avatar.job.skipped",
    "avatar.batch.started",
    "avatar.batch.completed",
    "avatar.batch.failed",
    "avatar.drain.started",
    "avatar.drain.completed",
    "avatar.lease.stale_detected",
    "avatar.lease.recovered",
    "avatar.worker.paused",
    "avatar.worker.resumed",
    "avatar.worker.canary",
    "avatar.worker.gpu_smoke",
    "avatar.iam.check",
    "avatar.privacy_qa.completed",
    "avatar.cost.guard",
}

AVATAR_OBSERVABILITY_EVENTS = (
    CANONICAL_AVATAR_OBSERVABILITY_EVENTS | LEGACY_AVATAR_OBSERVABILITY_EVENT_ALIASES
)

FORBIDDEN_OBSERVABILITY_FIELDS = frozenset(
    {
        "signedUrl",
        "signedUrls",
        "url",
        "urls",
        "downloadUrl",
        "downloadUrls",
        "sourceRef",
        "sourceRefs",
        "sourcePhotoRef",
        "sourcePhotoRefs",
        "sourcePhotoGcsUri",
        "sourcePhotoGcsUris",
        "sourcePath",
        "sourcePaths",
        "candidateImageRef",
        "candidateImageRefs",
        "candidatePath",
        "candidatePaths",
        "embedding",
        "embeddings",
        "rawEmbedding",
        "rawEmbeddings",
        "sourceEmbedding",
        "sourceEmbeddings",
        "idempotencyKey",
        "prompt",
        "negativePrompt",
    }
)

_FORBIDDEN_KEY_FRAGMENTS = (
    "signedurl",
    "downloadurl",
    "sourcephotoref",
    "sourceref",
    "sourcepath",
    "sourcegcs",
    "candidateimageref",
    "candidatepath",
    "embedding",
    "idempotencykey",
    "prompt",
)


def build_avatar_event(
    event_name: str,
    *,
    job_id: str = "",
    uid: str = "",
    batch_id: str = "",
    status: str = "",
    severity: str = "info",
    attributes: Optional[Mapping[str, Any]] = None,
    timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    if event_name not in AVATAR_OBSERVABILITY_EVENTS:
        raise ValueError(f"unsupported avatar observability event: {event_name}")

    event: Dict[str, Any] = {
        "schemaVersion": OBSERVABILITY_EVENT_SCHEMA_VERSION,
        "service": OBSERVABILITY_SERVICE,
        "eventName": event_name,
        "severity": severity,
        "timestamp": _format_timestamp(timestamp),
        "attributes": redact_observability_payload(attributes or {}),
    }
    if job_id:
        event["jobId"] = str(job_id)
    if batch_id:
        event["batchId"] = str(batch_id)
    if uid:
        event["uidHash"] = hash_identifier(uid)
    if status:
        event["status"] = str(status)
    return event


def build_avatar_metric_payload(
    metric_name: str,
    *,
    value: float,
    labels: Optional[Mapping[str, Any]] = None,
    resource: Optional[Mapping[str, Any]] = None,
    timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    return {
        "schemaVersion": OBSERVABILITY_METRIC_SCHEMA_VERSION,
        "service": OBSERVABILITY_SERVICE,
        "metricName": str(metric_name),
        "value": value,
        "labels": redact_observability_payload(labels or {}),
        "resource": _redact_resource(resource or {}),
        "timestamp": _format_timestamp(timestamp),
    }


def redact_observability_payload(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        redacted: Dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            if _is_forbidden_key(key_text):
                redacted[key_text] = REDACTED_VALUE
            else:
                redacted[key_text] = redact_observability_payload(value)
        return redacted
    if isinstance(payload, list):
        return [redact_observability_payload(item) for item in payload]
    if isinstance(payload, tuple):
        return [redact_observability_payload(item) for item in payload]
    if isinstance(payload, str) and _looks_sensitive_value(payload):
        return REDACTED_VALUE
    return payload


def hash_identifier(value: str) -> str:
    salt = os.environ.get("AVATAR_OBSERVABILITY_HASH_SALT", "avatar-observability-v1")
    digest = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()
    return f"sha256:{digest[:32]}"


def _redact_resource(resource: Mapping[str, Any]) -> Dict[str, Any]:
    clean = dict(redact_observability_payload(resource))
    uid = clean.pop("uid", "")
    if uid:
        clean["uidHash"] = hash_identifier(str(uid))
    return clean


def _is_forbidden_key(key: str) -> bool:
    if key in FORBIDDEN_OBSERVABILITY_FIELDS:
        return True
    normalized = key.replace("_", "").replace("-", "").lower()
    return any(fragment in normalized for fragment in _FORBIDDEN_KEY_FRAGMENTS)


def _looks_sensitive_value(value: str) -> bool:
    if value.startswith("gs://"):
        return True
    if "X-Goog-Signature=" in value or "X-Goog-Credential=" in value:
        return True
    return False


def _format_timestamp(timestamp: Optional[datetime]) -> str:
    current = timestamp or datetime.now(tz=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
