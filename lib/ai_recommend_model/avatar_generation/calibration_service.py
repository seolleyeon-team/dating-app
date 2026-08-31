"""Controlled staging-only G004 calibration acquisition service.

The service keeps private manifest fields and source images process-local.  It
persists only generated review images under ordinal-only object names and
returns redacted scalar QA evidence.
"""

from __future__ import annotations

from dataclasses import replace
import io
import os
import re
import time
from typing import Any, Callable, Mapping

from PIL import Image

from .avatar_prompt_contract import AVATAR_GENERAL_PROMPT_V0_TEMP
from .calibration_artifact import (
    CalibrationArtifact,
    load_configured_calibration_artifact,
)
from .calibration_evaluator import redact_calibration_report
from .calibration_runner import (
    CALIBRATION_PURPOSE,
    EXPECTED_STAGING_PROJECT,
    CalibrationRunnerConfig,
    CalibrationRunnerError,
    ManifestParticipant,
    run_calibration,
    validate_calibration_manifest_value,
)
from .model_adapters.azure_contracts import AZURE_GPT_IMAGE_2_MODEL_ID
from .model_adapters.azure_gpt_image_2 import (
    AzureRequestBudget,
    get_azure_gpt_image2_provider,
)
from .qa import QA_INPUT_CONTRACT_VERSION, run_avatar_candidate_qa
from .qa_pipeline_contract import canonical_azure_qa_pipeline_contract
from .qa_preflight import get_qa_runtime_readiness


CALIBRATION_REQUEST_SCHEMA = "g004_calibration_request_v1"
PROCESS_LOCAL_SOURCE_REF = "process-local://source"
PROCESS_LOCAL_CANDIDATE_REF = "process-local://candidate"
_RUN_ID_PATTERN = re.compile(r"^G004-[A-Z0-9][A-Z0-9_-]{6,79}$")
_MAX_SOURCE_BYTES = 20 * 1024 * 1024


class _ReviewArtifactStore:
    def __init__(self, storage_client: Any, *, bucket_name: str, run_id: str) -> None:
        self._bucket = storage_client.bucket(bucket_name)
        self._run_id = run_id
        self._targets: dict[tuple[str, int], Any] = {}
        self._touched: list[tuple[Any, int]] = []

    def preflight(self, participant_ordinals: tuple[str, ...], candidate_count: int) -> None:
        for participant_ordinal in participant_ordinals:
            for candidate_ordinal in range(1, candidate_count + 1):
                key = (participant_ordinal, candidate_ordinal)
                blob = self._bucket.blob(
                    _review_object_path(
                        self._run_id,
                        participant_ordinal,
                        candidate_ordinal,
                    )
                )
                if _blob_exists(blob):
                    raise CalibrationRunnerError(
                        "calibration_review_artifact_exists",
                        "Calibration run ID already has review artifacts.",
                    )
                self._targets[key] = blob

    def write(self, participant_ordinal: str, candidate_ordinal: int, image_bytes: bytes) -> None:
        key = (participant_ordinal, int(candidate_ordinal))
        blob = self._targets.get(key)
        if blob is None:
            raise CalibrationRunnerError(
                "calibration_review_target_invalid",
                "Calibration review target is invalid.",
            )
        blob.upload_from_string(
            bytes(image_bytes),
            content_type="image/png",
            predefined_acl=None,
            if_generation_match=0,
        )
        reload_blob = getattr(blob, "reload", None)
        if callable(reload_blob):
            reload_blob()
        generation_text = str(getattr(blob, "generation", "") or "").strip()
        if not generation_text.isdigit():
            raise CalibrationRunnerError(
                "calibration_review_generation_missing",
                "Calibration review artifact generation is unavailable.",
            )
        self._touched.append((blob, int(generation_text)))

    @property
    def written_count(self) -> int:
        return len(self._touched)

    def rollback(self) -> bool:
        complete = True
        for blob, generation in reversed(self._touched):
            try:
                if _blob_exists(blob):
                    blob.delete(if_generation_match=generation)
            except Exception:
                complete = False
        self._touched.clear()
        return complete


def execute_g004_calibration_request(
    payload: Mapping[str, Any],
    *,
    config: CalibrationRunnerConfig | None = None,
    storage_client: Any = None,
    provider: Any = None,
    qa_runner: Callable[..., Any] = run_avatar_candidate_qa,
    artifact: CalibrationArtifact | Any = None,
    qa_readiness_checker: Callable[[], Any] | None = None,
    participant_contract_checker: Callable[[ManifestParticipant], bool] | None = None,
    clock: Any = time,
) -> dict[str, Any]:
    """Execute one isolated G004 run and return only redacted evidence."""

    request_value = _require_request(payload)
    run_id = _require_run_id(request_value.get("runId"))
    active_config = config or CalibrationRunnerConfig.from_env()
    active_config = replace(active_config, run_id=run_id)
    _validate_service_config(active_config)

    manifest = validate_calibration_manifest_value(
        request_value.get("manifest"),
        expected_project=EXPECTED_STAGING_PROJECT,
    )
    if (
        manifest.total_count != 5
        or manifest.eligible_count != 5
        or bool(manifest.blocked_reason_counts)
    ):
        raise CalibrationRunnerError(
            "G004_CALIBRATION_COHORT_SIZE_INVALID",
            "Exactly five eligible exact-consent participants are required.",
        )

    active_artifact = artifact or load_configured_calibration_artifact(required=True)
    if active_artifact is None:
        raise CalibrationRunnerError(
            "calibration_artifact_missing",
            "Calibration artifact is unavailable.",
        )
    _validate_calibration_version(active_config, manifest.calibration_version, active_artifact)

    readiness_check = qa_readiness_checker or _default_qa_readiness
    if not _readiness_ready(readiness_check()):
        raise CalibrationRunnerError(
            "calibration_qa_not_ready",
            "Calibration QA runtime is not ready.",
        )

    current_source_checker = participant_contract_checker or _build_current_source_contract_checker(
        project=active_config.data_project,
        calibration_version=manifest.calibration_version,
    )
    preflight_contract_checks = 0
    for participant in manifest.participants:
        _require_current_source_contract(current_source_checker, participant)
        preflight_contract_checks += 1

    client = storage_client or _storage_client(active_config.project)
    sources = _load_and_validate_sources(client, manifest.participants)
    source_generation_preflight_checks = len(sources)
    review_store = _ReviewArtifactStore(
        client,
        bucket_name=_avatar_temp_bucket(),
        run_id=run_id,
    )
    review_store.preflight(
        tuple(participant.ordinal for participant in manifest.participants),
        active_config.candidate_count,
    )
    active_provider = provider or get_azure_gpt_image2_provider()
    total_requests = manifest.eligible_count * active_config.candidate_count
    provider_request_budget = AzureRequestBudget(total_requests)
    pre_provider_contract_checks = 0
    pre_provider_generation_checks = 0
    model_versions = {
        str(key): str(value)
        for key, value in dict(active_artifact.model_versions).items()
    }

    def generate(
        participant: ManifestParticipant,
        candidate_ordinal: int,
        context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        nonlocal pre_provider_contract_checks, pre_provider_generation_checks
        _require_current_source_contract(current_source_checker, participant)
        pre_provider_contract_checks += 1
        source_bytes, source_image, source_blob, pinned_generation = sources[participant.ordinal]
        _require_pinned_source_generation(source_blob, pinned_generation)
        pre_provider_generation_checks += 1
        generated = active_provider.generate(
            source_image_bytes=source_bytes,
            source_content_type="image/jpeg",
            prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
            idempotency_key=(
                f"{run_id}:{participant.ordinal}:C{int(candidate_ordinal):02d}:"
                f"{AZURE_GPT_IMAGE_2_MODEL_ID}"
            ),
            deadline_monotonic=float(context["deadlineMonotonic"]),
            request_budget=provider_request_budget,
        )
        candidate_image = _decode_generated_png(generated.image_bytes)
        qa_result = qa_runner(
            PROCESS_LOCAL_SOURCE_REF,
            PROCESS_LOCAL_CANDIDATE_REF,
            _qa_metadata(source_image, candidate_image),
        )
        qa_document = _qa_document(qa_result)
        review_store.write(
            participant.ordinal,
            candidate_ordinal,
            generated.image_bytes,
        )
        attempts = _positive_int(getattr(generated.audit, "attempts", 1), fallback=1)
        latency_seconds = _nonnegative_float(
            getattr(generated.audit, "latency_seconds", 0.0)
        )
        return {
            "candidateOrdinal": int(candidate_ordinal),
            "qa": qa_document,
            "selectionTier": _selection_tier(qa_document),
            "modelVersions": model_versions,
            "metrics": {
                "latencyMs": round(latency_seconds * 1000.0, 3),
                "payloadBytes": len(generated.image_bytes),
                "providerAttempts": attempts,
                "retryCount": max(0, attempts - 1),
            },
            "previewExposed": False,
            "approvalPerformed": False,
            "publicProjection": False,
        }

    try:
        result = run_calibration(
            active_config,
            manifest,
            generator=generate,
            qa_evaluator=lambda rows: {"rows": list(rows)},
            clock=clock,
        )
        if result.azure_call_count != provider_request_budget.consumed:
            raise CalibrationRunnerError(
                "calibration_provider_budget_audit_mismatch",
                "Calibration provider request budget audit did not match.",
            )
    except Exception as exc:
        if not review_store.rollback():
            raise CalibrationRunnerError(
                "calibration_review_cleanup_failed",
                "Calibration failed and private review artifact cleanup was incomplete.",
            ) from exc
        raise

    report = result.to_report()
    report.update(
        {
            "providerRequestBudget": {
                "limit": provider_request_budget.limit,
                "consumed": provider_request_budget.consumed,
                "remaining": provider_request_budget.remaining,
            },
            "currentSourceContractChecks": {
                "preflightCount": preflight_contract_checks,
                "preProviderCount": pre_provider_contract_checks,
                "referencesExposed": False,
            },
            "sourceGenerationChecks": {
                "preflightCount": source_generation_preflight_checks,
                "preProviderCount": pre_provider_generation_checks,
                "referencesExposed": False,
            },
            "reviewArtifacts": {
                "count": review_store.written_count,
                "private": True,
                "referencesExposed": False,
                "retention": "delete_after_bounded_human_review",
            },
            "schedule": {
                "participantCandidateRequests": total_requests,
                "minimumProviderStartSpanSeconds": round(
                    max(0, total_requests - 1)
                    * active_config.request_start_interval_seconds,
                    3,
                ),
                "legacyEightCandidateStartSpanSeconds": round(
                    max(0, manifest.eligible_count * 8 - 1)
                    * active_config.request_start_interval_seconds,
                    3,
                ),
                "eightCandidateModeEnabled": False,
                "operatorTimeoutSeconds": active_config.operator_timeout_seconds,
                "jobLeaseSeconds": active_config.job_lease_seconds,
            },
        }
    )
    return redact_calibration_report(report)


def _require_request(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise CalibrationRunnerError(
            "calibration_request_invalid",
            "Calibration request is invalid.",
        )
    if str(payload.get("schemaVersion") or "").strip() != CALIBRATION_REQUEST_SCHEMA:
        raise CalibrationRunnerError(
            "calibration_request_schema_invalid",
            "Calibration request schema is invalid.",
        )
    return payload


def _require_run_id(value: Any) -> str:
    run_id = str(value or "").strip().upper()
    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise CalibrationRunnerError(
            "calibration_run_id_invalid",
            "Calibration run ID is invalid.",
        )
    return run_id


def _validate_service_config(config: CalibrationRunnerConfig) -> None:
    if not config.enabled:
        raise CalibrationRunnerError("calibration_mode_disabled", "Calibration mode is disabled.")
    if config.environment != "staging" or config.project != EXPECTED_STAGING_PROJECT:
        raise CalibrationRunnerError(
            "calibration_staging_only",
            "Calibration acquisition is staging-only.",
        )
    if config.data_project != EXPECTED_STAGING_PROJECT:
        raise CalibrationRunnerError(
            "calibration_data_project_invalid",
            "Calibration data project must be the staging project.",
        )
    if config.purpose != CALIBRATION_PURPOSE:
        raise CalibrationRunnerError(
            "calibration_purpose_invalid",
            "Calibration purpose is invalid.",
        )
    if config.queue_status != "PAUSED":
        raise CalibrationRunnerError(
            "calibration_queue_must_be_paused",
            "The general avatar queue must remain PAUSED.",
        )


def _validate_calibration_version(
    config: CalibrationRunnerConfig,
    manifest_version: str,
    artifact: Any,
) -> None:
    artifact_version = str(getattr(artifact, "calibration_version", "") or "").strip()
    expected = str(config.calibration_version or "").strip()
    if not expected or expected != manifest_version or expected != artifact_version:
        raise CalibrationRunnerError(
            "calibration_version_mismatch",
            "Calibration versions do not match.",
        )


def _default_qa_readiness() -> Any:
    return get_qa_runtime_readiness()


def _readiness_ready(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        return value.get("ready") is True
    return getattr(value, "ready", False) is True


def _build_current_source_contract_checker(
    *,
    project: str,
    calibration_version: str,
) -> Callable[[ManifestParticipant], bool]:
    try:
        from google.cloud import firestore

        client = firestore.Client(project=project)
    except Exception as exc:  # pragma: no cover - worker image dependency
        raise CalibrationRunnerError(
            "calibration_current_source_contract_unavailable",
            "Calibration current-source contract checker is unavailable.",
        ) from exc

    def check(participant: ManifestParticipant) -> bool:
        try:
            snapshot = client.collection("userPrivateMedia").document(participant.uid).get()
            if not bool(getattr(snapshot, "exists", False)):
                return False
            value = snapshot.to_dict()
        except Exception as exc:
            raise CalibrationRunnerError(
                "calibration_current_source_contract_unavailable",
                "Calibration current-source contract could not be read.",
            ) from exc
        return _current_source_contract_matches(
            value,
            participant,
            calibration_version=calibration_version,
        )

    return check


def _require_current_source_contract(
    checker: Callable[[ManifestParticipant], bool],
    participant: ManifestParticipant,
) -> None:
    try:
        valid = checker(participant)
    except CalibrationRunnerError:
        raise
    except Exception as exc:
        raise CalibrationRunnerError(
            "calibration_current_source_contract_unavailable",
            "Calibration current-source contract could not be verified.",
        ) from exc
    if valid is not True:
        raise CalibrationRunnerError(
            "calibration_current_source_contract_invalid",
            "Calibration current-source or consent contract is invalid.",
        )


def _current_source_contract_matches(
    private_doc: Any,
    participant: ManifestParticipant,
    *,
    calibration_version: str,
) -> bool:
    if not isinstance(private_doc, Mapping):
        return False
    source_photos = private_doc.get("sourcePhotos")
    if not isinstance(source_photos, list) or len(source_photos) != 1:
        return False
    source_entry = source_photos[0]
    consent = private_doc.get("photoConsent")
    staging = private_doc.get("stagingCalibration")
    if not all(isinstance(value, Mapping) for value in (source_entry, consent, staging)):
        return False
    source_purpose = source_entry.get("purpose")
    if not isinstance(source_purpose, Mapping):
        return False

    expected_consent = participant.consent
    required_true = (
        "calibrationPurpose",
        "azureExternalAiProcessing",
        "sourceImageUse",
        "qaScoring",
        "humanReview",
    )
    return bool(
        str(source_entry.get("gcsUri") or "").strip() == participant.source_ref
        and source_entry.get("status") == "active"
        and source_entry.get("contentType") == "image/jpeg"
        and source_entry.get("encrypted") is True
        and source_entry.get("exifStripped") is True
        and source_purpose.get("avatarGeneration") is True
        and consent.get("avatarGeneration") is True
        and consent.get("profileDisplayOriginalPhoto") is False
        and bool(str(consent.get("version") or "").strip())
        and all(
            consent.get(key) is True and expected_consent.get(key) is True
            for key in required_true
        )
        and str(consent.get("temporaryRetention") or "").strip()
        == str(expected_consent.get("temporaryRetention") or "").strip()
        and str(consent.get("calibrationDate") or "").strip()
        == str(expected_consent.get("calibrationDate") or "").strip()
        and str(consent.get("calibrationVersion") or "").strip()
        == calibration_version
        and str(staging.get("calibrationVersion") or "").strip()
        == calibration_version
        and str(staging.get("scope") or "").strip() == CALIBRATION_PURPOSE
        and staging.get("fresh") is True
        and participant.consent.get("exact") is True
        and staging.get("approvedAvatarLocked") is False
    )


def _storage_client(project: str) -> Any:
    try:
        from google.cloud import storage
    except Exception as exc:  # pragma: no cover - worker image dependency
        raise CalibrationRunnerError(
            "calibration_storage_unavailable",
            "Calibration storage client is unavailable.",
        ) from exc
    return storage.Client(project=project)


def _source_bucket() -> str:
    return os.environ.get(
        "SOURCE_PHOTO_BUCKET",
        "seolleyeon-final-private-source-photos",
    ).strip()


def _avatar_temp_bucket() -> str:
    return os.environ.get(
        "AVATAR_TEMP_BUCKET",
        "seolleyeon-final-avatar-temp",
    ).strip()


def _load_and_validate_sources(
    storage_client: Any,
    participants: tuple[ManifestParticipant, ...],
) -> dict[str, tuple[bytes, Image.Image, Any, str]]:
    expected_bucket = _source_bucket()
    result: dict[str, tuple[bytes, Image.Image, Any, str]] = {}
    for participant in participants:
        bucket, path = _parse_private_gcs_ref(participant.source_ref)
        if bucket != expected_bucket or not path.startswith(f"users/{participant.uid}/source/"):
            raise CalibrationRunnerError(
                "calibration_source_ref_invalid",
                "Calibration source photo reference is invalid.",
            )
        blob = storage_client.bucket(bucket).blob(path)
        if not _blob_exists(blob):
            raise CalibrationRunnerError(
                "calibration_source_missing",
                "Calibration source photo is unavailable.",
            )
        reload_blob = getattr(blob, "reload", None)
        if callable(reload_blob):
            try:
                reload_blob()
            except Exception as exc:
                raise CalibrationRunnerError(
                    "calibration_source_unavailable",
                    "Calibration source photo is unavailable.",
                ) from exc
        observed_generation = str(getattr(blob, "generation", "") or "").strip()
        if observed_generation != participant.source_generation:
            raise CalibrationRunnerError(
                "calibration_source_generation_mismatch",
                "Calibration source photo generation changed.",
            )
        try:
            data = bytes(
                blob.download_as_bytes(
                    if_generation_match=int(participant.source_generation)
                )
            )
        except Exception as exc:
            raise CalibrationRunnerError(
                "calibration_source_unavailable",
                "Calibration source photo is unavailable.",
            ) from exc
        image = _decode_normalized_source_jpeg(data, getattr(blob, "content_type", ""))
        result[participant.ordinal] = (
            data,
            image,
            blob,
            participant.source_generation,
        )
    return result


def _require_pinned_source_generation(blob: Any, expected_generation: str) -> None:
    reload_blob = getattr(blob, "reload", None)
    if not callable(reload_blob):
        raise CalibrationRunnerError(
            "calibration_source_unavailable",
            "Calibration source photo generation cannot be verified.",
        )
    try:
        reload_blob()
    except Exception as exc:
        raise CalibrationRunnerError(
            "calibration_source_unavailable",
            "Calibration source photo generation cannot be verified.",
        ) from exc
    observed_generation = str(getattr(blob, "generation", "") or "").strip()
    if observed_generation != str(expected_generation or "").strip():
        raise CalibrationRunnerError(
            "calibration_source_generation_mismatch",
            "Calibration source photo generation changed.",
        )


def _parse_private_gcs_ref(value: str) -> tuple[str, str]:
    match = re.fullmatch(r"(?:gs|gcs)://([^/]+)/(.+)", str(value or "").strip())
    if not match:
        raise CalibrationRunnerError(
            "calibration_source_ref_invalid",
            "Calibration source photo reference is invalid.",
        )
    bucket = match.group(1).strip()
    path = match.group(2).strip()
    if not bucket or not path or path.startswith("/") or ".." in path.split("/"):
        raise CalibrationRunnerError(
            "calibration_source_ref_invalid",
            "Calibration source photo reference is invalid.",
        )
    return bucket, path


def _decode_normalized_source_jpeg(data: bytes, content_type: Any) -> Image.Image:
    declared_type = str(content_type or "").lower().split(";", 1)[0].strip()
    if not data or len(data) > _MAX_SOURCE_BYTES or declared_type not in {"", "image/jpeg"}:
        raise CalibrationRunnerError(
            "calibration_source_not_normalized_jpeg",
            "Calibration source photo is not a normalized JPEG.",
        )
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.format != "JPEG" or image.width <= 0 or image.height <= 0:
                raise ValueError("invalid normalized source")
            return image.convert("RGB")
    except CalibrationRunnerError:
        raise
    except Exception as exc:
        raise CalibrationRunnerError(
            "calibration_source_not_normalized_jpeg",
            "Calibration source photo is not a normalized JPEG.",
        ) from exc


def _decode_generated_png(data: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(bytes(data))) as image:
            image.load()
            if image.format != "PNG" or image.width <= 0 or image.height <= 0:
                raise ValueError("invalid generated candidate")
            return image.convert("RGB")
    except Exception as exc:
        raise CalibrationRunnerError(
            "calibration_candidate_invalid",
            "Generated calibration candidate is invalid.",
        ) from exc


def _qa_metadata(source_image: Image.Image, candidate_image: Image.Image) -> dict[str, Any]:
    # The applicability policies (trait/unique-mark v6) read the canonical
    # server provenance keys; build them from the single shared contract so
    # the recovery route can never drift from the worker path again
    # (G004 PIPELINE_PROVENANCE_DRIFT, 2026-08-31).
    return {
        **canonical_azure_qa_pipeline_contract(),
        "qaInputMode": "process_local_source_vs_generated_candidate",
        "compareSourceVisualRisk": True,
        "qaContract": QA_INPUT_CONTRACT_VERSION,
        "_source_image": source_image,
        "_candidate_image": candidate_image,
    }


def _qa_document(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_document") and callable(value.to_document):
        value = value.to_document()
    if not isinstance(value, Mapping):
        raise CalibrationRunnerError(
            "calibration_qa_invalid",
            "Calibration QA result is invalid.",
        )
    return redact_calibration_report(value)


def _selection_tier(qa: Mapping[str, Any]) -> str:
    if qa.get("rejectReasons"):
        return "hard_reject"
    if qa.get("previewAllowed") is True:
        return "hard_pass"
    if qa.get("softPass") is True:
        return "soft_pass"
    return "needs_review"


def _review_object_path(run_id: str, participant_ordinal: str, candidate_ordinal: int) -> str:
    return (
        f"calibration/g004/{run_id}/{participant_ordinal}/"
        f"C{int(candidate_ordinal):02d}.png"
    )


def _blob_exists(blob: Any) -> bool:
    exists = getattr(blob, "exists", None)
    return bool(exists()) if callable(exists) else False


def _positive_int(value: Any, *, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _nonnegative_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, parsed)


__all__ = [
    "CALIBRATION_REQUEST_SCHEMA",
    "PROCESS_LOCAL_CANDIDATE_REF",
    "PROCESS_LOCAL_SOURCE_REF",
    "execute_g004_calibration_request",
]
