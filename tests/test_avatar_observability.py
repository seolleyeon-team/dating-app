import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.observability import (
    AVATAR_OBSERVABILITY_EVENTS,
    CANONICAL_AVATAR_OBSERVABILITY_EVENTS,
    FORBIDDEN_OBSERVABILITY_FIELDS,
    REDACTED_VALUE,
    build_avatar_event,
    build_avatar_metric_payload,
    redact_observability_payload,
)


PRIVATE_GCS_REF = "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg"
SIGNED_URL = "https://storage.googleapis.com/bucket/object.png?X-Goog-Signature=abc123"


def test_canonical_pr7_event_set_is_supported():
    required_events = {
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

    assert CANONICAL_AVATAR_OBSERVABILITY_EVENTS == required_events
    assert required_events.issubset(AVATAR_OBSERVABILITY_EVENTS)


def test_event_schema_is_structured_and_uses_allowed_event_names():
    event = build_avatar_event(
        "avatar_job_preview_ready",
        job_id="job_123",
        uid="u1",
        batch_id="batch_1",
        status="preview_ready",
        severity="info",
        attributes={"candidateCount": 4, "sourcePhotoRefs": [PRIVATE_GCS_REF]},
    )

    assert event["schemaVersion"] == "avatar_observability_event_v1"
    assert event["service"] == "avatar-generation"
    assert event["eventName"] in AVATAR_OBSERVABILITY_EVENTS
    assert event["jobId"] == "job_123"
    assert event["uidHash"]
    assert "uid" not in event
    assert event["attributes"]["candidateCount"] == 4


def test_live_iam_check_completed_event_uses_canonical_name():
    event = build_avatar_event(
        "avatar_live_iam_check_completed",
        severity="info",
        attributes={
            "status": "pass",
            "workerUrl": SIGNED_URL,
            "sourceRef": PRIVATE_GCS_REF,
        },
    )

    assert event["eventName"] == "avatar_live_iam_check_completed"
    assert event["attributes"]["status"] == "pass"
    assert event["attributes"]["workerUrl"] == REDACTED_VALUE
    assert event["attributes"]["sourceRef"] == REDACTED_VALUE


def test_log_redaction_removes_signed_urls_embeddings_and_source_refs():
    payload = {
        "signedUrl": SIGNED_URL,
        "embedding": [0.1, 0.2, 0.3],
        "sourcePhotoRefs": [PRIVATE_GCS_REF],
        "nested": {
            "rawEmbedding": [0.4],
            "candidateImageRef": "gs://seolleyeon-avatar-temp/users/u1/avatar/c1.png",
        },
    }

    redacted = redact_observability_payload(payload)
    encoded = json.dumps(redacted, sort_keys=True)

    assert SIGNED_URL not in encoded
    assert PRIVATE_GCS_REF not in encoded
    assert "0.1" not in encoded
    assert redacted["signedUrl"] == REDACTED_VALUE
    assert redacted["sourcePhotoRefs"] == REDACTED_VALUE
    assert redacted["nested"]["rawEmbedding"] == REDACTED_VALUE
    assert redacted["nested"]["candidateImageRef"] == REDACTED_VALUE


def test_forbidden_fields_are_not_logged_in_event_attributes():
    event = build_avatar_event(
        "avatar_job_failed",
        job_id="job_123",
        uid="u1",
        status="failed",
        attributes={field: "secret" for field in FORBIDDEN_OBSERVABILITY_FIELDS},
    )
    encoded = json.dumps(event, sort_keys=True)

    assert "secret" not in encoded
    for field in FORBIDDEN_OBSERVABILITY_FIELDS:
        assert event["attributes"][field] == REDACTED_VALUE


def test_metric_payload_construction_is_redacted_and_log_metric_ready():
    payload = build_avatar_metric_payload(
        "avatar_generation_completed_count",
        value=1,
        labels={
            "status": "preview_ready",
            "modelId": "azure_gpt_image_2",
            "sourceRef": PRIVATE_GCS_REF,
        },
        resource={"jobId": "job_123", "uid": "u1"},
    )

    assert payload["schemaVersion"] == "avatar_metric_payload_v1"
    assert payload["metricName"] == "avatar_generation_completed_count"
    assert payload["value"] == 1
    assert payload["labels"]["status"] == "preview_ready"
    assert payload["labels"]["sourceRef"] == REDACTED_VALUE
    assert payload["resource"]["uidHash"]
    assert "uid" not in payload["resource"]


def test_pr7_observability_runbook_exists_with_required_sections():
    runbook = REPO_ROOT / "docs" / "avatar-media-migration" / "pr7-observability-runbook.md"

    text = runbook.read_text(encoding="utf-8")

    for required in (
        "Log-Based Metrics",
        "Dashboard Metrics",
        "Alerts",
        "Stuck Jobs",
        "Stale Lease Recovery",
        "Pause",
        "Resume",
        "Retry",
        "Drain",
        "Canary",
        "Cost",
        "GPU Smoke",
        "IAM",
        "Privacy QA",
    ):
        assert required in text
