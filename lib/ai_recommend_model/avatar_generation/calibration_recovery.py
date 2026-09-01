"""Read-only recovery of G004 QA evidence after a completed paid run.

This module deliberately has no generation-provider dependency. It reads the
generation-pinned source and already-generated candidate objects, recomputes
the pinned QA contract process-locally, and returns redacted scalar evidence.
"""

from __future__ import annotations

from dataclasses import replace
import math
import time
from typing import Any, Callable, Mapping

from .calibration_artifact import CalibrationArtifact, load_configured_calibration_artifact
from .calibration_evaluator import (
    CALIBRATION_EVALUATION_VERSION,
    redact_calibration_report,
)
from .calibration_runner import (
    CALIBRATION_PURPOSE,
    EXPECTED_STAGING_PROJECT,
    CalibrationRunnerConfig,
    CalibrationRunnerError,
    ManifestParticipant,
    validate_calibration_manifest_value,
)
from .calibration_service import (
    PROCESS_LOCAL_CANDIDATE_REF,
    PROCESS_LOCAL_SOURCE_REF,
    _avatar_temp_bucket,
    _blob_exists,
    _build_current_source_contract_checker,
    _decode_generated_png,
    _default_qa_readiness,
    _load_and_validate_sources,
    _qa_document,
    _qa_metadata,
    _readiness_ready,
    _require_current_source_contract,
    _require_pinned_source_generation,
    _require_run_id,
    _review_object_path,
    _selection_tier,
    _storage_client,
    _validate_calibration_version,
    _validate_service_config,
)
from .qa import run_avatar_candidate_qa
from .qa import QA_CONTRACT_VERSION
from .analysis.watermark import WATERMARK_POLICY_VERSION


CALIBRATION_RECOVERY_REQUEST_SCHEMA = "g004_calibration_recovery_request_v1"
CALIBRATION_RECOVERY_REPORT_SCHEMA = "g004_calibration_recovery_v2_watermark_evidence"
CALIBRATION_RECOVERY_EVALUATION_SUFFIX = "QA-RECOVERY-2"
EXPECTED_PARTICIPANT_COUNT = 5
EXPECTED_CANDIDATES_PER_PARTICIPANT = 4
EXPECTED_ORIGINAL_CANDIDATE_COUNT = 20
EXPECTED_QUOTA_RPM = 2.0
_MAX_CANDIDATE_BYTES = 20 * 1024 * 1024


class _PinnedCandidateSet:
    """Generation-pin every expected review object before any QA begins."""

    def __init__(self, storage_client: Any, *, bucket_name: str, run_id: str) -> None:
        self._bucket = storage_client.bucket(bucket_name)
        self._run_id = run_id
        self._pinned: dict[tuple[str, int], tuple[Any, str]] = {}

    def preflight(
        self,
        participant_ordinals: tuple[str, ...],
        candidate_count: int,
    ) -> int:
        for participant_ordinal in participant_ordinals:
            for candidate_ordinal in range(1, candidate_count + 1):
                blob = self._bucket.blob(
                    _review_object_path(
                        self._run_id,
                        participant_ordinal,
                        candidate_ordinal,
                    )
                )
                if not _blob_exists(blob):
                    raise CalibrationRunnerError(
                        "calibration_recovery_candidate_missing",
                        "A required calibration recovery candidate is unavailable.",
                    )
                _reload_candidate(blob)
                generation = str(getattr(blob, "generation", "") or "").strip()
                content_type = str(getattr(blob, "content_type", "") or "").lower()
                if not generation.isdigit() or content_type.split(";", 1)[0].strip() != "image/png":
                    raise CalibrationRunnerError(
                        "calibration_recovery_candidate_invalid",
                        "A calibration recovery candidate is invalid.",
                    )
                self._pinned[(participant_ordinal, candidate_ordinal)] = (
                    blob,
                    generation,
                )
        return len(self._pinned)

    def read(self, participant_ordinal: str, candidate_ordinal: int) -> bytes:
        target = self._pinned.get((participant_ordinal, int(candidate_ordinal)))
        if target is None:
            raise CalibrationRunnerError(
                "calibration_recovery_candidate_invalid",
                "A calibration recovery candidate is invalid.",
            )
        blob, expected_generation = target
        _reload_candidate(blob)
        observed_generation = str(getattr(blob, "generation", "") or "").strip()
        if observed_generation != expected_generation:
            raise CalibrationRunnerError(
                "calibration_recovery_candidate_generation_mismatch",
                "A calibration recovery candidate generation changed.",
            )
        try:
            data = bytes(
                blob.download_as_bytes(
                    if_generation_match=int(expected_generation),
                )
            )
        except Exception as exc:
            raise CalibrationRunnerError(
                "calibration_recovery_candidate_unavailable",
                "A calibration recovery candidate is unavailable.",
            ) from exc
        if not data or len(data) > _MAX_CANDIDATE_BYTES:
            raise CalibrationRunnerError(
                "calibration_recovery_candidate_invalid",
                "A calibration recovery candidate is invalid.",
            )
        return data


def execute_g004_calibration_recovery_request(
    payload: Mapping[str, Any],
    *,
    config: CalibrationRunnerConfig | None = None,
    storage_client: Any = None,
    qa_runner: Callable[..., Any] = run_avatar_candidate_qa,
    artifact: CalibrationArtifact | Any = None,
    qa_readiness_checker: Callable[[], Any] | None = None,
    participant_contract_checker: Callable[[ManifestParticipant], bool] | None = None,
    clock: Any = time,
) -> dict[str, Any]:
    """Recompute QA for one complete candidate set without generation calls."""

    request_value = _require_recovery_request(payload)
    run_id = _require_run_id(request_value.get("runId"))
    configured = config or CalibrationRunnerConfig.from_env()
    configured_run_id = str(configured.run_id or "").strip().upper()
    if configured_run_id and configured_run_id != run_id:
        raise CalibrationRunnerError(
            "calibration_recovery_run_id_mismatch",
            "Calibration recovery run ID does not match the configured run.",
        )
    active_config = replace(configured, run_id=run_id)
    _validate_recovery_config(active_config)
    original_evidence = _require_original_run_evidence(
        request_value.get("originalRunEvidence"),
        active_config,
    )

    manifest = validate_calibration_manifest_value(
        request_value.get("manifest"),
        expected_project=EXPECTED_STAGING_PROJECT,
    )
    if (
        manifest.total_count != EXPECTED_PARTICIPANT_COUNT
        or manifest.eligible_count != EXPECTED_PARTICIPANT_COUNT
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
    _validate_calibration_version(
        active_config,
        manifest.calibration_version,
        active_artifact,
    )

    readiness_check = qa_readiness_checker or _default_qa_readiness
    if not _readiness_ready(readiness_check()):
        raise CalibrationRunnerError(
            "calibration_qa_not_ready",
            "Calibration QA runtime is not ready.",
        )

    current_source_checker = (
        participant_contract_checker
        or _build_current_source_contract_checker(
            project=active_config.data_project,
            calibration_version=manifest.calibration_version,
        )
    )
    preflight_contract_checks = 0
    for participant in manifest.participants:
        _require_current_source_contract(current_source_checker, participant)
        preflight_contract_checks += 1

    client = storage_client or _storage_client(active_config.project)
    candidates = _PinnedCandidateSet(
        client,
        bucket_name=_avatar_temp_bucket(),
        run_id=run_id,
    )
    candidate_preflight_count = candidates.preflight(
        tuple(participant.ordinal for participant in manifest.participants),
        active_config.candidate_count,
    )

    # Candidate completeness is proven before source bytes are downloaded.
    sources = _load_and_validate_sources(client, manifest.participants)
    source_generation_preflight_checks = len(sources)
    model_versions = {
        str(key): str(value)
        for key, value in dict(active_artifact.model_versions).items()
    }
    artifact_metadata = _artifact_metadata(active_artifact, model_versions)

    started_at = _monotonic(clock)
    rows: list[dict[str, Any]] = []
    pre_qa_contract_checks = 0
    pre_qa_source_generation_checks = 0
    candidate_generation_checks = 0
    qa_evaluation_count = 0
    for participant in manifest.participants:
        row: dict[str, Any] = {
            "participantOrdinal": participant.ordinal,
            "consent": participant.safe_consent(),
            "cohortSlice": dict(participant.cohort_slice),
            "candidates": [],
        }
        for candidate_ordinal in range(1, active_config.candidate_count + 1):
            _require_current_source_contract(current_source_checker, participant)
            pre_qa_contract_checks += 1
            _source_bytes, source_image, source_blob, source_generation = sources[
                participant.ordinal
            ]
            _require_pinned_source_generation(source_blob, source_generation)
            pre_qa_source_generation_checks += 1

            candidate_bytes = candidates.read(
                participant.ordinal,
                candidate_ordinal,
            )
            candidate_generation_checks += 1
            candidate_image = _decode_generated_png(candidate_bytes)
            qa_started_at = _monotonic(clock)
            try:
                qa_result = qa_runner(
                    PROCESS_LOCAL_SOURCE_REF,
                    PROCESS_LOCAL_CANDIDATE_REF,
                    _qa_metadata(source_image, candidate_image),
                )
                qa_document = _qa_document(qa_result)
            except CalibrationRunnerError:
                raise
            except Exception as exc:
                raise CalibrationRunnerError(
                    "calibration_recovery_qa_failed",
                    "Calibration recovery QA evaluation failed.",
                ) from exc
            qa_evaluation_count += 1
            row["candidates"].append(
                {
                    "candidateOrdinal": candidate_ordinal,
                    "qa": qa_document,
                    "selectionTier": _selection_tier(qa_document),
                    "modelVersions": model_versions,
                    "metrics": {
                        "payloadBytes": len(candidate_bytes),
                        "qaRecoveryLatencyMs": round(
                            max(0.0, _monotonic(clock) - qa_started_at) * 1000.0,
                            3,
                        ),
                    },
                    "previewExposed": False,
                    "approvalPerformed": False,
                    "publicProjection": False,
                }
            )
        rows.append(row)

    recovery_duration = max(0.0, _monotonic(clock) - started_at)
    total_requests = manifest.eligible_count * active_config.candidate_count
    report = {
        "schemaVersion": CALIBRATION_RECOVERY_REPORT_SCHEMA,
        "runId": run_id,
        "evaluationId": f"{run_id}-{CALIBRATION_RECOVERY_EVALUATION_SUFFIX}",
        "status": "completed",
        "nextState": "HUMAN_REVIEW_REQUIRED",
        "environment": active_config.environment,
        "project": active_config.project,
        "purpose": CALIBRATION_PURPOSE,
        "calibrationVersion": manifest.calibration_version,
        "participantCount": manifest.eligible_count,
        "participantOrdinals": [
            participant.ordinal for participant in manifest.participants
        ],
        "candidateCount": total_requests,
        "azureCallCount": EXPECTED_ORIGINAL_CANDIDATE_COUNT,
        "retryCount": 0,
        "generationCallsPerformedByRecovery": 0,
        "qaEvaluationVersion": QA_CONTRACT_VERSION,
        "watermarkPolicyVersion": WATERMARK_POLICY_VERSION,
        "calibrationEvaluationVersion": CALIBRATION_EVALUATION_VERSION,
        "thresholdSnapshot": artifact_metadata["thresholdSnapshot"],
        "calibrationArtifactIntegrity": artifact_metadata["integrity"],
        "gitRevision": artifact_metadata["gitRevision"],
        "quotaRpm": active_config.quota_rpm,
        "requestStartIntervalSeconds": active_config.request_start_interval_seconds,
        "minimumObservedStartIntervalSeconds": None,
        "durationSeconds": original_evidence["serverDurationSeconds"],
        "recoveryDurationSeconds": round(recovery_duration, 3),
        "queueStatus": active_config.queue_status,
        "previewSideEffects": 0,
        "approvalSideEffects": 0,
        "publicProjectionSideEffects": 0,
        "qaEvaluation": {"rows": rows},
        "providerRequestBudget": original_evidence["providerRequestBudget"],
        "originalRunEvidence": {
            "serverRequestCount": original_evidence["serverRequestCount"],
            "serverHttpStatus": original_evidence["serverHttpStatus"],
            "serverDurationSeconds": original_evidence["serverDurationSeconds"],
            "candidateCount": original_evidence["candidateCount"],
            "retryCount": original_evidence["retryCount"],
            "completeCandidateSet": True,
            "responseBodyAvailableToOperator": False,
        },
        "currentSourceContractChecks": {
            "preflightCount": preflight_contract_checks,
            "preQaCount": pre_qa_contract_checks,
            "referencesExposed": False,
        },
        "sourceGenerationChecks": {
            "preflightCount": source_generation_preflight_checks,
            "preQaCount": pre_qa_source_generation_checks,
            "referencesExposed": False,
        },
        "candidateGenerationChecks": {
            "preflightCount": candidate_preflight_count,
            "preQaCount": candidate_generation_checks,
            "referencesExposed": False,
        },
        "reviewArtifacts": {
            "count": candidate_preflight_count,
            "private": True,
            "referencesExposed": False,
            "retention": "delete_after_verified_local_recovery",
        },
        "recovery": {
            "mode": "qa_only_from_complete_generated_candidate_set",
            "candidatePreflightCount": candidate_preflight_count,
            "qaEvaluationCount": qa_evaluation_count,
            "qaEvidenceRecomputed": True,
            "providerPerCandidateLatencyRecovered": False,
            "readOnly": True,
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
        "rawImagePersistence": 0,
        "rawBiometricPersistence": 0,
        "redacted": True,
    }
    return redact_calibration_report(report)


def _artifact_metadata(
    artifact: CalibrationArtifact | Any,
    model_versions: Mapping[str, str],
) -> dict[str, Any]:
    """Return immutable calibration metadata without exposing artifact internals."""

    payload = getattr(artifact, "payload", {})
    payload = payload if isinstance(payload, Mapping) else {}
    preprocessing = payload.get("preprocessingVersions")
    if not isinstance(preprocessing, Mapping):
        preprocessing = getattr(artifact, "preprocessing_versions", {})
    if not isinstance(preprocessing, Mapping):
        preprocessing = {}
    integrity = payload.get("integrity")
    integrity = integrity if isinstance(integrity, Mapping) else {}
    revision = payload.get("gitRevision")
    if not isinstance(revision, str) or not revision.strip():
        revision = "unavailable"
    checksum = integrity.get("sha256")
    if not isinstance(checksum, str) or not checksum.strip():
        checksum = "unavailable"
    return {
        "thresholdSnapshot": {
            "calibrationVersion": str(getattr(artifact, "calibration_version", "") or ""),
            "modelVersions": dict(model_versions),
            "preprocessingVersions": {
                str(key): str(value)
                for key, value in preprocessing.items()
                if str(key).strip() and str(value).strip()
            },
        },
        "integrity": checksum.strip(),
        "gitRevision": revision.strip(),
    }


def _require_recovery_request(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise CalibrationRunnerError(
            "calibration_recovery_request_invalid",
            "Calibration recovery request is invalid.",
        )
    if str(payload.get("schemaVersion") or "").strip() != CALIBRATION_RECOVERY_REQUEST_SCHEMA:
        raise CalibrationRunnerError(
            "calibration_recovery_request_schema_invalid",
            "Calibration recovery request schema is invalid.",
        )
    return payload


def _validate_recovery_config(config: CalibrationRunnerConfig) -> None:
    _validate_service_config(config)
    if (
        config.candidate_count != EXPECTED_CANDIDATES_PER_PARTICIPANT
        or config.quota_rpm != EXPECTED_QUOTA_RPM
        or config.max_retries != 0
    ):
        raise CalibrationRunnerError(
            "calibration_recovery_config_invalid",
            "Calibration recovery configuration does not match the completed run.",
        )


def _require_original_run_evidence(
    value: Any,
    config: CalibrationRunnerConfig,
) -> dict[str, Any]:
    evidence = value if isinstance(value, Mapping) else {}
    budget = evidence.get("providerRequestBudget")
    budget_value = budget if isinstance(budget, Mapping) else {}
    duration = _finite_nonnegative_float(evidence.get("serverDurationSeconds"))
    minimum_span = (
        EXPECTED_ORIGINAL_CANDIDATE_COUNT - 1
    ) * config.request_start_interval_seconds
    valid = bool(
        _exact_int(evidence.get("serverRequestCount"), 1)
        and _exact_int(evidence.get("serverHttpStatus"), 200)
        and _exact_int(evidence.get("candidateCount"), EXPECTED_ORIGINAL_CANDIDATE_COUNT)
        and _exact_int(evidence.get("retryCount"), 0)
        and _exact_int(budget_value.get("limit"), EXPECTED_ORIGINAL_CANDIDATE_COUNT)
        and _exact_int(budget_value.get("consumed"), EXPECTED_ORIGINAL_CANDIDATE_COUNT)
        and _exact_int(budget_value.get("remaining"), 0)
        and duration is not None
        and duration >= minimum_span
        and duration < min(config.operator_timeout_seconds, config.job_lease_seconds)
    )
    if not valid:
        raise CalibrationRunnerError(
            "calibration_recovery_original_audit_invalid",
            "Original calibration run evidence is incomplete or inconsistent.",
        )
    return {
        "serverRequestCount": 1,
        "serverHttpStatus": 200,
        "serverDurationSeconds": round(float(duration), 9),
        "candidateCount": EXPECTED_ORIGINAL_CANDIDATE_COUNT,
        "retryCount": 0,
        "providerRequestBudget": {
            "limit": EXPECTED_ORIGINAL_CANDIDATE_COUNT,
            "consumed": EXPECTED_ORIGINAL_CANDIDATE_COUNT,
            "remaining": 0,
        },
    }


def _reload_candidate(blob: Any) -> None:
    reload_blob = getattr(blob, "reload", None)
    if not callable(reload_blob):
        raise CalibrationRunnerError(
            "calibration_recovery_candidate_unavailable",
            "A calibration recovery candidate is unavailable.",
        )
    try:
        reload_blob()
    except Exception as exc:
        raise CalibrationRunnerError(
            "calibration_recovery_candidate_unavailable",
            "A calibration recovery candidate is unavailable.",
        ) from exc


def _exact_int(value: Any, expected: int) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value == expected


def _finite_nonnegative_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def _monotonic(clock: Any) -> float:
    function = getattr(clock, "monotonic", None)
    if not callable(function):
        raise CalibrationRunnerError(
            "calibration_recovery_clock_invalid",
            "Calibration recovery clock is invalid.",
        )
    return float(function())


__all__ = [
    "CALIBRATION_RECOVERY_EVALUATION_SUFFIX",
    "CALIBRATION_RECOVERY_REPORT_SCHEMA",
    "CALIBRATION_RECOVERY_REQUEST_SCHEMA",
    "execute_g004_calibration_recovery_request",
]
