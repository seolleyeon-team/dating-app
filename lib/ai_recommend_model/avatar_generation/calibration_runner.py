"""Staging-only, side-effect-free calibration acquisition primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import inspect
import json
import math
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Sequence

from .calibration_evaluator import redact_calibration_report


CALIBRATION_PURPOSE = "g004_quality_calibration"
EXPECTED_STAGING_PROJECT = "seolleyeon-final"
MAX_CANDIDATES_PER_PARTICIPANT = 4
# provider quota 는 endpoint 별 단일 authority 에서만 온다.
# calibration 과 runtime generation 이 서로 다른 env 를 읽어 상대를 무시하던
# 문제를 막는다(2026-09-05).
from avatar_generation.model_adapters.azure_endpoint_quota import (
    declared_endpoint_quota,
    resolve_endpoint_rpm,
)

MAX_VERIFIED_PROVIDER_RPM = declared_endpoint_quota().rpm_limit


class CalibrationRunnerError(RuntimeError):
    """Stable, redacted calibration runner failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code)
        super().__init__(str(message))


class RetryAfterError(RuntimeError):
    """Retryable provider failure carrying a sanitized Retry-After duration."""

    def __init__(self, retry_after_seconds: float = 0.0) -> None:
        self.retry_after_seconds = max(0.0, float(retry_after_seconds))
        super().__init__("provider request is retryable")


@dataclass(frozen=True)
class CalibrationRunnerConfig:
    enabled: bool = False
    environment: str = ""
    project: str = EXPECTED_STAGING_PROJECT
    data_project: str = EXPECTED_STAGING_PROJECT
    purpose: str = ""
    queue_status: str = "PAUSED"
    candidate_count: int = MAX_CANDIDATES_PER_PARTICIPANT
    quota_rpm: float = 2.0
    run_id: str = ""
    calibration_version: str = ""
    max_retries: int = 0
    worker_image_digest: str = ""
    operator_timeout_seconds: int = 1800
    job_lease_seconds: int = 1800

    def __post_init__(self) -> None:
        environment = str(self.environment or "").strip().lower()
        project = str(self.project or "").strip()
        data_project = str(self.data_project or "").strip()
        purpose = str(self.purpose or "").strip()
        queue_status = str(self.queue_status or "").strip().upper()
        if not 1 <= int(self.candidate_count) <= MAX_CANDIDATES_PER_PARTICIPANT:
            raise ValueError("Calibration candidate count must be between 1 and 4.")
        if not math.isfinite(float(self.quota_rpm)) or float(self.quota_rpm) <= 0:
            raise ValueError("Calibration quota RPM must be positive.")
        if float(self.quota_rpm) > declared_endpoint_quota().rpm_limit:
            raise ValueError(
                "Calibration quota RPM cannot exceed the verified 2 RPM provider quota."
            )
        if int(self.max_retries) < 0 or int(self.max_retries) > 3:
            raise ValueError("Calibration retry count is outside the allowed range.")
        object.__setattr__(self, "enabled", bool(self.enabled))
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "project", project)
        object.__setattr__(self, "data_project", data_project)
        object.__setattr__(self, "purpose", purpose)
        object.__setattr__(self, "queue_status", queue_status)
        object.__setattr__(self, "candidate_count", int(self.candidate_count))
        object.__setattr__(self, "quota_rpm", float(self.quota_rpm))
        object.__setattr__(self, "max_retries", int(self.max_retries))
        object.__setattr__(self, "operator_timeout_seconds", max(1, int(self.operator_timeout_seconds)))
        object.__setattr__(self, "job_lease_seconds", max(1, int(self.job_lease_seconds)))

    @classmethod
    def from_env(cls) -> "CalibrationRunnerConfig":
        environment = _env_text("ENVIRONMENT")
        project = _env_text("AVATAR_CALIBRATION_PROJECT") or _env_text("GOOGLE_CLOUD_PROJECT") or EXPECTED_STAGING_PROJECT
        data_project = (
            _env_text("AVATAR_DATA_PROJECT")
            or _env_text("FIRESTORE_PROJECT")
            or _env_text("GCP_PROJECT")
        )
        purpose = _env_text("AVATAR_CALIBRATION_PURPOSE")
        enabled = _env_bool("AVATAR_CALIBRATION_RUN_ENABLED")
        rpm = resolve_endpoint_rpm()
        run_id = _env_text("AVATAR_CALIBRATION_RUN_ID") or _default_run_id()
        return cls(
            enabled=enabled,
            environment=environment,
            project=project,
            data_project=data_project,
            purpose=purpose,
            queue_status=_env_text("AVATAR_GENERAL_QUEUE_STATUS")
            or _env_text("AVATAR_QUEUE_STATUS")
            or "PAUSED",
            candidate_count=_env_int("AVATAR_CALIBRATION_CANDIDATE_COUNT", MAX_CANDIDATES_PER_PARTICIPANT),
            quota_rpm=rpm,
            run_id=run_id,
            calibration_version=_env_text("AVATAR_QA_CALIBRATION_VERSION"),
            max_retries=_env_int("AVATAR_CALIBRATION_MAX_RETRIES", 0),
            worker_image_digest=_env_text("AVATAR_WORKER_IMAGE_DIGEST"),
            operator_timeout_seconds=_env_int("AVATAR_CALIBRATION_OPERATOR_TIMEOUT_SECONDS", 1800),
            job_lease_seconds=_env_int("AVATAR_CALIBRATION_JOB_LEASE_SECONDS", 1800),
        )

    @property
    def request_start_interval_seconds(self) -> float:
        return 60.0 / self.quota_rpm


@dataclass(frozen=True)
class ManifestParticipant:
    ordinal: str
    uid: str = field(repr=False)
    source_ref: str = field(repr=False)
    source_version: str = ""
    source_generation: str = field(default="", repr=False)
    auth_project: str = ""
    consent: Mapping[str, Any] = field(default_factory=dict, repr=False)
    cohort_slice: Mapping[str, str] = field(default_factory=dict)
    human_review: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def safe_consent(self) -> dict[str, Any]:
        return {
            "exact": True,
            "calibrationPurpose": True,
            "sourceImageUse": True,
            "azureExternalAiProcessing": True,
            "qaScoring": True,
            "humanReview": True,
            "temporaryRetention": "bounded",
            "calibrationVersion": _safe_text(self.consent.get("calibrationVersion")),
        }


@dataclass(frozen=True)
class RedactedManifestSummary:
    expected_project: str
    project: str
    purpose: str
    calibration_version: str
    total_count: int
    eligible_count: int
    blocked_reason_counts: Mapping[str, int]
    participants: tuple[ManifestParticipant, ...] = field(default_factory=tuple, repr=False)

    def to_report(self) -> dict[str, Any]:
        return {
            "schemaVersion": "g004_calibration_manifest_summary_v1",
            "project": self.project,
            "purpose": self.purpose,
            "calibrationVersion": self.calibration_version,
            "totalCount": self.total_count,
            "eligibleCount": self.eligible_count,
            "blockedReasonCounts": dict(sorted(self.blocked_reason_counts.items())),
            "participantOrdinals": [participant.ordinal for participant in self.participants],
            "redacted": True,
        }


@dataclass(frozen=True)
class CalibrationRunResult:
    run_id: str
    status: str
    environment: str
    project: str
    purpose: str
    calibration_version: str
    participant_count: int
    candidate_count: int
    azure_call_count: int
    retry_count: int
    request_start_interval_seconds: float
    observed_start_intervals_seconds: tuple[float, ...]
    duration_seconds: float
    queue_status: str
    preview_side_effects: int
    approval_side_effects: int
    public_projection_side_effects: int
    qa_report: Mapping[str, Any]
    participant_ordinals: tuple[str, ...] = field(default_factory=tuple)

    def to_report(self) -> dict[str, Any]:
        minimum_observed = (
            min(self.observed_start_intervals_seconds)
            if self.observed_start_intervals_seconds
            else None
        )
        return redact_calibration_report(
            {
                "schemaVersion": "g004_calibration_run_v1",
                "runId": self.run_id,
                "status": self.status,
                "environment": self.environment,
                "project": self.project,
                "purpose": self.purpose,
                "calibrationVersion": self.calibration_version,
                "participantCount": self.participant_count,
                "participantOrdinals": list(self.participant_ordinals),
                "candidateCount": self.candidate_count,
                "azureCallCount": self.azure_call_count,
                "retryCount": self.retry_count,
                "quotaRpm": round(60.0 / self.request_start_interval_seconds, 6),
                "requestStartIntervalSeconds": round(self.request_start_interval_seconds, 6),
                "minimumObservedStartIntervalSeconds": (
                    None if minimum_observed is None else round(minimum_observed, 6)
                ),
                "durationSeconds": round(max(0.0, self.duration_seconds), 3),
                "queueStatus": self.queue_status,
                "previewSideEffects": self.preview_side_effects,
                "approvalSideEffects": self.approval_side_effects,
                "publicProjectionSideEffects": self.public_projection_side_effects,
                "qaEvaluation": dict(self.qa_report),
                "rawImagePersistence": 0,
                "rawEmbeddingPersistence": 0,
                "redacted": True,
            }
        )


RedactedCalibrationRun = CalibrationRunResult


class ProviderRateLimiter:
    def __init__(self, quota_rpm: float) -> None:
        self.interval_seconds = 60.0 / float(quota_rpm)
        self._last_start: float | None = None

    def wait_for_start(
        self,
        clock: Any,
        *,
        not_before: float = 0.0,
        deadline_monotonic: float | None = None,
    ) -> float:
        now = _clock_monotonic(clock)
        target = max(now, float(not_before))
        if self._last_start is not None:
            target = max(target, self._last_start + self.interval_seconds)
        if deadline_monotonic is not None and target >= float(deadline_monotonic):
            raise CalibrationRunnerError(
                "calibration_deadline_exceeded",
                "Calibration execution deadline was exceeded.",
            )
        if target > now:
            _clock_sleep(clock, target - now)
        started = _clock_monotonic(clock)
        self._last_start = started
        return started


def validate_calibration_manifest(
    path: Path,
    *,
    expected_project: str,
) -> RedactedManifestSummary:
    """Validate a private manifest while returning only a redacted summary."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise CalibrationRunnerError("calibration_manifest_invalid", "Calibration manifest is unavailable or invalid.") from exc
    return validate_calibration_manifest_value(value, expected_project=expected_project)


def validate_calibration_manifest_value(
    value: Any,
    *,
    expected_project: str,
) -> RedactedManifestSummary:
    """Validate an in-memory private manifest without creating a plaintext file."""

    if isinstance(value, list):
        value = {"participants": value}
    if not isinstance(value, Mapping):
        raise CalibrationRunnerError("calibration_manifest_invalid", "Calibration manifest is invalid.")

    project = _safe_text(value.get("projectId") or value.get("project"))
    purpose = _safe_text(value.get("purpose"))
    calibration_version = _safe_text(value.get("calibrationVersion"))
    expected = _safe_text(expected_project)
    participants_value = value.get("participants")
    participant_items = (
        list(participants_value)
        if isinstance(participants_value, Sequence) and not isinstance(participants_value, (str, bytes))
        else []
    )
    blocked: dict[str, int] = {}
    eligible: list[ManifestParticipant] = []
    seen_uids: set[str] = set()
    for index, raw in enumerate(participant_items, start=1):
        item = raw if isinstance(raw, Mapping) else {}
        reasons: list[str] = []
        uid = _safe_text(item.get("uid") or item.get("authUid"))
        source_ref = _safe_text(item.get("sourcePhotoRef") or item.get("sourcePhotoPath"))
        auth_project = _safe_text(item.get("authProject") or item.get("firebaseProject"))
        source_version = _safe_text(item.get("sourceVersion"))
        source_generation = _safe_text(item.get("sourceGeneration"))
        consent = _mapping(item.get("consent"))
        if project != expected:
            reasons.append("manifest_project_mismatch")
        if purpose != CALIBRATION_PURPOSE:
            reasons.append("calibration_purpose_mismatch")
        if not uid:
            reasons.append("participant_missing")
        elif uid in seen_uids:
            reasons.append("participant_duplicate")
        if not source_ref:
            reasons.append("source_photo_missing")
        if not source_version:
            reasons.append("source_version_missing")
        if not source_generation:
            reasons.append("source_generation_missing")
        elif not source_generation.isdigit():
            reasons.append("source_generation_invalid")
        if auth_project and auth_project != expected:
            reasons.append("auth_project_mismatch")
        if item.get("fresh") is not True:
            reasons.append("participant_not_fresh")
        if item.get("approvedAvatarLocked") is True:
            reasons.append("approved_avatar_lock")
        if not _exact_consent(consent):
            reasons.append("exact_consent_incomplete")
        cohort_slice = _safe_slice(item.get("cohortSlice"))
        if not cohort_slice:
            reasons.append("cohort_slice_missing")
        if reasons:
            for reason in sorted(set(reasons)):
                blocked[reason] = blocked.get(reason, 0) + 1
            continue
        seen_uids.add(uid)
        eligible.append(
            ManifestParticipant(
                ordinal=f"P{len(eligible) + 1:02d}",
                uid=uid,
                source_ref=source_ref,
                source_version=source_version,
                source_generation=source_generation,
                auth_project=auth_project or expected,
                consent=dict(consent),
                cohort_slice=cohort_slice,
                human_review=_mapping(item.get("humanReview")),
            )
        )
    return RedactedManifestSummary(
        expected_project=expected,
        project=project,
        purpose=purpose,
        calibration_version=calibration_version,
        total_count=len(participant_items),
        eligible_count=len(eligible),
        blocked_reason_counts=blocked,
        participants=tuple(eligible),
    )


def run_calibration(
    config: CalibrationRunnerConfig,
    manifest: RedactedManifestSummary,
    *,
    generator: Callable[..., Mapping[str, Any]],
    qa_evaluator: Callable[..., Mapping[str, Any]],
    clock: Any = time,
) -> RedactedCalibrationRun:
    """Run controlled generation with no preview, approval, or public writes."""

    _validate_runner_guard(config, manifest)
    if manifest.eligible_count != 5:
        raise CalibrationRunnerError(
            "G004_CALIBRATION_COHORT_SIZE_INVALID",
            "Exactly five exact-consent participants are required.",
        )
    if not callable(generator) or not callable(qa_evaluator):
        raise CalibrationRunnerError("calibration_dependency_invalid", "Calibration dependencies are invalid.")

    started_at = _clock_monotonic(clock)
    execution_budget_seconds = float(
        min(config.operator_timeout_seconds, config.job_lease_seconds)
    )
    required_request_span_seconds = max(
        0.0,
        (manifest.eligible_count * config.candidate_count - 1)
        * config.request_start_interval_seconds,
    )
    if required_request_span_seconds >= execution_budget_seconds:
        raise CalibrationRunnerError(
            "calibration_time_budget_insufficient",
            "Calibration timeout is shorter than the provider request schedule.",
        )
    deadline_monotonic = started_at + execution_budget_seconds
    limiter = ProviderRateLimiter(config.quota_rpm)
    starts: list[float] = []
    rows: list[dict[str, Any]] = []
    azure_calls = 0
    retries = 0
    for participant in manifest.participants:
        row: dict[str, Any] = {
            "participantOrdinal": participant.ordinal,
            "consent": participant.safe_consent(),
            "cohortSlice": dict(participant.cohort_slice),
            "humanReview": dict(participant.human_review),
            "candidates": [],
        }
        for candidate_ordinal in range(1, config.candidate_count + 1):
            attempt = 0
            not_before = 0.0
            while True:
                start = limiter.wait_for_start(
                    clock,
                    not_before=not_before,
                    deadline_monotonic=deadline_monotonic,
                )
                starts.append(start)
                azure_calls += 1
                remaining_seconds = max(
                    0.0,
                    deadline_monotonic - _clock_monotonic(clock),
                )
                context = {
                    "runId": config.run_id,
                    "participantOrdinal": participant.ordinal,
                    "candidateOrdinal": candidate_ordinal,
                    "purpose": CALIBRATION_PURPOSE,
                    "previewAllowed": False,
                    "approvalAllowed": False,
                    "publicProjectionAllowed": False,
                    "deadlineMonotonic": deadline_monotonic,
                    "remainingSeconds": remaining_seconds,
                }
                try:
                    generated = _invoke_generator(generator, participant, candidate_ordinal, context)
                    if not isinstance(generated, Mapping):
                        raise CalibrationRunnerError(
                            "calibration_generation_invalid",
                            "Calibration generation returned invalid evidence.",
                        )
                    _reject_side_effects(generated)
                    provider_attempts = _provider_attempt_count(generated)
                    if provider_attempts > 1:
                        azure_calls += provider_attempts - 1
                        retries += provider_attempts - 1
                    row["candidates"].append(_scalar_candidate_evidence(generated, candidate_ordinal))
                    break
                except RetryAfterError as exc:
                    if attempt >= config.max_retries:
                        raise CalibrationRunnerError(
                            "calibration_provider_retry_exhausted",
                            "Calibration provider retry budget was exhausted.",
                        ) from exc
                    retries += 1
                    attempt += 1
                    not_before = _clock_monotonic(clock) + max(0.0, exc.retry_after_seconds)
                except CalibrationRunnerError:
                    raise
                except Exception as exc:
                    retry_after = _retry_after_from_exception(exc)
                    if retry_after is not None and attempt < config.max_retries:
                        retries += 1
                        attempt += 1
                        not_before = _clock_monotonic(clock) + retry_after
                        continue
                    raise CalibrationRunnerError(
                        "calibration_provider_failed",
                        "Calibration provider call failed.",
                    ) from exc
        rows.append(row)

    try:
        if _clock_monotonic(clock) >= deadline_monotonic:
            raise CalibrationRunnerError(
                "calibration_deadline_exceeded",
                "Calibration execution deadline was exceeded.",
            )
        qa_report = _invoke_qa_evaluator(qa_evaluator, rows, config)
    except CalibrationRunnerError:
        raise
    except Exception as exc:
        raise CalibrationRunnerError(
            "calibration_qa_evaluation_failed",
            "Calibration QA evaluation failed.",
        ) from exc
    if not isinstance(qa_report, Mapping):
        qa_report = {"status": "invalid"}

    finished_at = _clock_monotonic(clock)
    intervals = tuple(
        max(0.0, right - left)
        for left, right in zip(starts, starts[1:])
    )
    return CalibrationRunResult(
        run_id=_safe_text(config.run_id) or _default_run_id(),
        status="completed",
        environment=config.environment,
        project=config.project,
        purpose=CALIBRATION_PURPOSE,
        calibration_version=config.calibration_version or manifest.calibration_version,
        participant_count=manifest.eligible_count,
        candidate_count=manifest.eligible_count * config.candidate_count,
        azure_call_count=azure_calls,
        retry_count=retries,
        request_start_interval_seconds=config.request_start_interval_seconds,
        observed_start_intervals_seconds=intervals,
        duration_seconds=max(0.0, finished_at - started_at),
        queue_status=config.queue_status,
        preview_side_effects=0,
        approval_side_effects=0,
        public_projection_side_effects=0,
        qa_report=dict(qa_report),
        participant_ordinals=tuple(participant.ordinal for participant in manifest.participants),
    )


def _validate_runner_guard(config: CalibrationRunnerConfig, manifest: RedactedManifestSummary) -> None:
    if not config.enabled:
        raise CalibrationRunnerError("calibration_mode_disabled", "Calibration mode is disabled.")
    if config.environment != "staging" or config.project != EXPECTED_STAGING_PROJECT:
        raise CalibrationRunnerError("calibration_staging_only", "Calibration acquisition is staging-only.")
    if config.data_project != EXPECTED_STAGING_PROJECT:
        raise CalibrationRunnerError(
            "calibration_data_project_invalid",
            "Calibration data project must be the staging project.",
        )
    if config.purpose != CALIBRATION_PURPOSE:
        raise CalibrationRunnerError("calibration_purpose_invalid", "Calibration purpose is invalid.")
    if config.queue_status != "PAUSED":
        raise CalibrationRunnerError("calibration_queue_must_be_paused", "The general avatar queue must remain PAUSED.")
    if manifest.expected_project != EXPECTED_STAGING_PROJECT or manifest.project != EXPECTED_STAGING_PROJECT:
        raise CalibrationRunnerError("calibration_manifest_project_invalid", "Calibration manifest project is invalid.")
    if manifest.purpose != CALIBRATION_PURPOSE:
        raise CalibrationRunnerError("calibration_manifest_purpose_invalid", "Calibration manifest purpose is invalid.")


def _invoke_generator(
    generator: Callable[..., Mapping[str, Any]],
    participant: ManifestParticipant,
    candidate_ordinal: int,
    context: Mapping[str, Any],
) -> Mapping[str, Any]:
    parameter_count = _positional_parameter_count(generator)
    if parameter_count >= 3:
        return generator(participant, candidate_ordinal, context)
    return generator(participant, candidate_ordinal)


def _invoke_qa_evaluator(
    evaluator: Callable[..., Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
    config: CalibrationRunnerConfig,
) -> Mapping[str, Any]:
    if _positional_parameter_count(evaluator) >= 2:
        return evaluator(rows, config)
    return evaluator(rows)


def _positional_parameter_count(function: Callable[..., Any]) -> int:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return 2
    parameters = list(signature.parameters.values())
    if any(parameter.kind is inspect.Parameter.VAR_POSITIONAL for parameter in parameters):
        return 3
    return sum(
        parameter.kind in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }
        for parameter in parameters
    )


def _reject_side_effects(value: Mapping[str, Any]) -> None:
    flattened = _flatten_keys(value)
    status = _safe_text(value.get("status")).lower()
    if status in {"preview", "preview_ready", "approved", "public"}:
        raise CalibrationRunnerError("calibration_side_effect_forbidden", "Calibration output attempted a public side effect.")
    forbidden_true_keys = {
        "previewexposed",
        "approved",
        "approvalperformed",
        "publicprofile",
        "publicprojection",
        "approvedstoragewritten",
    }
    for key, item in flattened:
        if key in forbidden_true_keys and item is True:
            raise CalibrationRunnerError("calibration_side_effect_forbidden", "Calibration output attempted a public side effect.")


def _scalar_candidate_evidence(value: Mapping[str, Any], candidate_ordinal: int) -> dict[str, Any]:
    qa_value = value.get("qa") or value.get("qaSignals") or {}
    qa = redact_calibration_report(qa_value if isinstance(qa_value, Mapping) else {})
    metrics_source = _mapping(value.get("metrics"))
    metrics: dict[str, Any] = {}
    for key in (
        "latencyMs",
        "costUsd",
        "payloadBytes",
        "retryCount",
        "providerAttempts",
        "deadlineExceeded",
    ):
        if key in metrics_source and isinstance(metrics_source[key], (bool, int, float)):
            metrics[key] = metrics_source[key]
    for key in ("latencyMs", "costUsd", "payloadBytes"):
        if key not in metrics and isinstance(value.get(key), (int, float)) and not isinstance(value.get(key), bool):
            metrics[key] = value[key]
    model_versions = _mapping(value.get("modelVersions") or _mapping(qa).get("modelVersions"))
    result: dict[str, Any] = {
        "candidateOrdinal": int(candidate_ordinal),
        "qa": qa,
        "metrics": metrics,
    }
    if model_versions:
        result["modelVersions"] = {str(key): _safe_text(item) for key, item in model_versions.items() if _safe_text(item)}
    for key in ("traitCoverage", "selectionTier"):
        if key in value and isinstance(value[key], (int, float, str)) and not isinstance(value[key], bool):
            result[key] = value[key]
    return redact_calibration_report(result)


def _flatten_keys(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    output: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key).replace("_", "").replace("-", "").lower()
            output.append((key_text, child))
            output.extend(_flatten_keys(child, f"{prefix}.{key_text}"))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            output.extend(_flatten_keys(child, prefix))
    return output


def _retry_after_from_exception(exc: Exception) -> float | None:
    for attribute in ("retry_after_seconds", "retry_after"):
        value = getattr(exc, attribute, None)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return max(0.0, float(value))
    status = getattr(exc, "status_code", None)
    headers = getattr(exc, "headers", None)
    if status == 429 and isinstance(headers, Mapping):
        value = headers.get("Retry-After") or headers.get("retry-after")
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0
    return None


def _provider_attempt_count(value: Mapping[str, Any]) -> int:
    raw = _mapping(value.get("metrics")).get("providerAttempts")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return 1
    attempts = int(raw)
    return attempts if 1 <= attempts <= 5 else 1


def _exact_consent(consent: Mapping[str, Any]) -> bool:
    if consent.get("exact") is not True:
        return False
    for key in (
        "calibrationPurpose",
        "sourceImageUse",
        "azureExternalAiProcessing",
        "qaScoring",
        "humanReview",
    ):
        if consent.get(key) is not True:
            return False
    return bool(
        _safe_text(consent.get("temporaryRetention"))
        and _safe_text(consent.get("calibrationDate"))
        and _safe_text(consent.get("calibrationVersion"))
    )


def _safe_slice(value: Any) -> dict[str, str]:
    source = _mapping(value)
    result: dict[str, str] = {}
    for key in ("background", "eyewear", "hair", "onboardingGender"):
        item = _safe_text(source.get(key)).lower()
        if item and len(item) <= 40 and all(character.isalnum() or character in "_-" for character in item):
            result[key] = item
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _env_text(name: str) -> str:
    import os

    return _safe_text(os.environ.get(name))


def _env_bool(name: str) -> bool:
    return _env_text(name).lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(_env_text(name) or fallback)
    except ValueError:
        return int(fallback)


def _env_float(name: str, fallback: float) -> float:
    try:
        return float(_env_text(name) or fallback)
    except ValueError:
        return float(fallback)


def _default_run_id() -> str:
    return f"G004-AZURE-CAL-{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}-001"


def _clock_monotonic(clock: Any) -> float:
    function = getattr(clock, "monotonic", None)
    if callable(function):
        return float(function())
    return time.monotonic()


def _clock_sleep(clock: Any, seconds: float) -> None:
    function = getattr(clock, "sleep", None)
    if callable(function):
        function(max(0.0, float(seconds)))
        return
    time.sleep(max(0.0, float(seconds)))


__all__ = [
    "CALIBRATION_PURPOSE",
    "CalibrationRunnerConfig",
    "CalibrationRunnerError",
    "CalibrationRunResult",
    "EXPECTED_STAGING_PROJECT",
    "ManifestParticipant",
    "MAX_VERIFIED_PROVIDER_RPM",
    "MAX_CANDIDATES_PER_PARTICIPANT",
    "ProviderRateLimiter",
    "RedactedCalibrationRun",
    "RedactedManifestSummary",
    "RetryAfterError",
    "run_calibration",
    "validate_calibration_manifest",
    "validate_calibration_manifest_value",
]
