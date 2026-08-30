from __future__ import annotations

import argparse
import base64
import hashlib
import inspect
import io
import json
import logging
import os
import re
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageStat

from avatar_generation import FLUX2_KLEIN_MODEL_ID, FLUX2_KLEIN_VERSION
from avatar_generation.avatar_prompt_contract import (
    AVATAR_GENERAL_PROMPT_V0_TEMP,
    AVATAR_GENERAL_PROMPT_VERSION,
)
from avatar_generation.adaptive_generation import (
    AdaptiveGenerationPolicy,
    GenerationBudget,
    plan_generation_round,
)
from avatar_generation.analysis.source_analyzer import analyze_avatar_source_image
from avatar_generation.analysis.visual_risk import (
    STATUS_CRITICAL_UNAVAILABLE,
    unavailable_visual_risk_analysis,
)
from avatar_generation.admission_policy import (
    AdmissionDecision,
    AdmissionPolicy,
    AdmissionRequest,
    CumulativeUsage,
    evaluate_admission,
    usage_from_cost_aggregate,
)
from avatar_generation.batching import claim_avatar_job_batch
from avatar_generation.environment import (
    configured_environment_names,
    is_local_or_dev_environment as _shared_is_local_or_dev_environment,
    is_production_like_environment,
)
from avatar_generation.cost import (
    AvatarCostConfig,
    build_batch_cost_document,
    build_job_cost_document,
    evaluate_cost_guard,
)
from avatar_generation.job_lease import AvatarJobLeaseConfig, ClaimDeadline
from avatar_generation.model_adapters.azure_contracts import (
    AZURE_GPT_IMAGE_2_MODEL_ID,
    AZURE_GPT_IMAGE_2_VERSION,
    AzureGenerationResult,
    AzureProviderError,
    AzureUnknownOutcomeError,
    provider_usage,
)
from avatar_generation.model_adapters.azure_gpt_image_2 import (
    AzureGptImage2Provider,
    get_azure_gpt_image2_provider as _build_azure_gpt_image2_provider,
)
from avatar_generation.fidelity_corridor import CorridorCandidate
from avatar_generation.fidelity_shadow import (
    build_shadow_corridor_evidence,
    build_shadow_ranking_document,
)
from avatar_generation.flux_config import (
    Flux2KleinExecutionConfig,
    build_flux2_klein_execution_audit,
    resolve_flux2_klein_execution_config,
)
from avatar_generation.model_adapters.florence2 import Florence2TraitExtractionAdapter
from avatar_generation.preprocessing import (
    ReferencePreprocessConfig,
    preprocess_reference_image,
    validate_reference_preprocess_enabled_for_environment,
)
from avatar_generation.preprocessing.reference import REFERENCE_PREPROCESS_PROFILES
from avatar_generation.preview_policy import (
    is_preview_eligible,
    passes_absolute_preview_checks,
)
from avatar_generation.quality_context import AvatarQualityContext
from avatar_generation.qa import (
    QA_INPUT_CONTRACT_VERSION,
    AvatarQAResult,
    run_avatar_candidate_qa,
)
from avatar_generation.qa_preflight import (
    QARuntimeReadiness,
    get_qa_runtime_readiness,
)
from avatar_generation.rerank import rerank_preview_candidates
from avatar_generation.seolleyeon_avatar_prompt_builder_v4 import (
    AvatarTraitCard as PromptAvatarTraitCard,
    build_avatar_prompt,
)
from avatar_generation.storage import build_temp_candidate_ref, build_temp_candidate_path
from avatar_generation.trait_card import (
    TraitCardValidationResult,
    merge_trait_card_with_broad_hints,
    normalize_avatar_presentation_gender,
)
from avatar_generation.trait_card.region_features import extract_region_color_traits

try:
    from google.cloud import firestore, storage
    from google.cloud.firestore import SERVER_TIMESTAMP
except Exception:  # pragma: no cover - optional in pure unit tests
    firestore = None  # type: ignore[assignment]
    storage = None  # type: ignore[assignment]
    SERVER_TIMESTAMP = datetime.now(tz=timezone.utc)


DEFAULT_SOURCE_PHOTO_BUCKET = "seolleyeon-final-private-source-photos"
DEFAULT_AVATAR_TEMP_BUCKET = "seolleyeon-final-avatar-temp"
BRIDGE_ENVIRONMENT = "production_bridge"
FESTIVAL_DATA_PROJECT = "seolleyeon-festival"
FORBIDDEN_BRIDGE_BUCKET_PREFIX = "seolleyeon-final-"
CANONICAL_AZURE_WORKER_MODE = AZURE_GPT_IMAGE_2_MODEL_ID
DEFAULT_MAX_CANDIDATES = 4
DEFAULT_CANDIDATE_TTL_HOURS = 72
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024
DEFAULT_STEPS = 4
DEFAULT_GUIDANCE_SCALE = 1.0
DEFAULT_REFERENCE_PRIVACY_DOWNSAMPLE_SIZE = 96
DEFAULT_REFERENCE_PRIVACY_BLUR_RADIUS = 1.5
TERMINAL_JOB_STATUSES = {
    "preview_ready",
    "approved",
    "cancelled",
    "canceled",
    "superseded",
    "needs_review",
    "no_previewable_candidates",
}
NORMALIZED_STAGE_COST_KEYS = (
    ("model_load_seconds", "modelLoadSeconds"),
    ("face_detect_seconds", "faceDetectSeconds"),
    ("trait_extract_seconds", "traitExtractSeconds"),
    ("preprocess_seconds", "preprocessSeconds"),
    ("sam_seconds", "samSeconds"),
    ("generation_seconds", "generationSeconds"),
    ("qa_seconds", "qaSeconds"),
    ("rerank_seconds", "rerankSeconds"),
    ("upload_seconds", "uploadSeconds"),
    ("total_worker_seconds", "totalWorkerSeconds"),
)

logger = logging.getLogger(__name__)
_TRAIT_ADAPTER_CACHE: Dict[Tuple[Any, ...], Florence2TraitExtractionAdapter] = {}
_AZURE_PROVIDER_CACHE: Optional[AzureGptImage2Provider] = None


class AvatarGenerationError(RuntimeError):
    pass


class AvatarQAReadinessError(AvatarGenerationError):
    """Raised when canonical Azure generation cannot safely enter QA."""

    def __init__(self, readiness: QARuntimeReadiness) -> None:
        self.readiness = readiness
        self.error_code = readiness.failure_code or "avatar_qa_preflight_failed"
        super().__init__("Avatar QA preflight is not ready; generation is paused.")


@dataclass
class AvatarWorkerDeadline:
    started_at: float
    max_request_seconds: int
    max_job_seconds: int
    soft_stop_margin_seconds: int

    @classmethod
    def from_env(cls) -> "AvatarWorkerDeadline":
        max_request = _int_env(
            "AVATAR_WORKER_MAX_REQUEST_SECONDS",
            900,
            minimum=60,
            maximum=3600,
        )
        max_job = _int_env(
            "AVATAR_WORKER_MAX_JOB_SECONDS",
            300,
            minimum=30,
            maximum=3600,
        )
        margin = _int_env(
            "AVATAR_WORKER_SOFT_STOP_MARGIN_SECONDS",
            30,
            minimum=0,
            maximum=300,
        )
        return cls(
            started_at=time.monotonic(),
            max_request_seconds=max_request,
            max_job_seconds=max_job,
            soft_stop_margin_seconds=margin,
        )

    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.started_at)

    def remaining_seconds(self) -> float:
        limit = min(self.max_request_seconds, self.max_job_seconds)
        return max(0.0, float(limit) - self.elapsed_seconds())

    def deadline_monotonic(self) -> float:
        """Return the absolute monotonic deadline shared with provider retries."""
        return self.started_at + min(self.max_request_seconds, self.max_job_seconds)

    def capped_by_claim_deadline(
        self,
        deadline: Optional[ClaimDeadline],
    ) -> "AvatarWorkerDeadline":
        if deadline is None:
            return self
        remaining = deadline.remaining_seconds()
        available = max(0, int(remaining - max(0, deadline.safety_seconds)))
        return AvatarWorkerDeadline(
            started_at=self.started_at,
            max_request_seconds=min(self.max_request_seconds, available),
            max_job_seconds=min(self.max_job_seconds, available),
            soft_stop_margin_seconds=self.soft_stop_margin_seconds,
        )

    def ensure_can_continue(self, stage: str, *, min_remaining_seconds: int = 0) -> None:
        required = max(0, min_remaining_seconds) + max(0, self.soft_stop_margin_seconds)
        if self.remaining_seconds() <= required:
            raise AvatarGenerationError(
                f"avatar_worker_deadline_exceeded at {stage}."
            )


_FLUX_ALWAYS_DROPPED_KWARGS = frozenset({"negative_prompt"})


def build_flux_prompt_with_avoid(prompt: str, negative_prompt: str = "") -> str:
    """Fold text-only negative constraints into the FLUX prompt.

    Flux2KleinPipeline does not accept a normal `
egative_prompt`` string
    kwarg. Keeping the constraints in the prompt preserves the policy without
    relying on unsupported provider parameters.
    """

    positive = str(prompt or "").strip()
    negative = str(negative_prompt or "").strip()
    if not negative:
        return positive
    if "\navoid:" in positive.lower() or positive.lower().startswith("avoid:"):
        return positive
    return f"{positive}\n\nAvoid:\n{negative}"


def call_flux_pipeline_safely(pipe: Any, **kwargs: Any) -> Any:
    """Call a FLUX pipeline after dropping unsupported kwargs by name only."""

    remaining = {
        key: value
        for key, value in kwargs.items()
        if key not in _FLUX_ALWAYS_DROPPED_KWARGS
    }
    dropped = set(kwargs) - set(remaining)

    try:
        signature = inspect.signature(pipe.__call__)
    except (TypeError, ValueError):  # pragma: no cover - depends on provider object
        safe_kwargs = remaining
    else:
        parameters = signature.parameters
        accepts_var_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters.values()
        )
        if accepts_var_kwargs:
            safe_kwargs = remaining
        else:
            supported = set(parameters)
            safe_kwargs = {
                key: value
                for key, value in remaining.items()
                if key in supported
             }
            dropped.update(set(remaining) - set(safe_kwargs))

    if dropped:
        logger.warning(
            "Dropped unsupported FLUX pipeline kwargs: %s",
            sorted(dropped),
        )
    return pipe(**safe_kwargs)


@dataclass(frozen=True)
class GcsRef:
    bucket: str
    path: str


@dataclass(frozen=True)
class AvatarGenerationPayload:
    job_id: str
    uid: str
    source_photo_ids: List[str]
    source_photo_refs: List[str]
    candidate_count: int
    model_id: str
    job_type: str
    schema_version: str
    idempotency_key: str = ""
    avatar_presentation_gender: str = "unknown"


@dataclass(frozen=True)
class CandidateArtifact:
    candidate_id: str
    image_ref: str
    image_bytes: bytes
    seed: int
    generation_params: Dict[str, Any]


@dataclass(frozen=True)
class AvatarGenerationResult:
    job_id: str
    uid: str
    status: str
    candidate_ids: List[str]
    preview_ready_count: int
    rejected_count: int
    needs_review_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jobId": self.job_id,
            "uid": self.uid,
            "status": self.status,
            "candidateIds": list(self.candidate_ids),
            "previewReadyCount": self.preview_ready_count,
            "rejectedCount": self.rejected_count,
            "needsReviewCount": self.needs_review_count,
         }


@dataclass(frozen=True)
class AvatarBatchRunResult:
    status: str
    schema_version: str
    batch_id: str
    processed_count: int
    success_count: int
    failed_count: int
    skipped_count: int
    job_results: List[Dict[str, Any]]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "schemaVersion": self.schema_version,
            "batchId": self.batch_id,
            "processedCount": self.processed_count,
            "successCount": self.success_count,
            "failedCount": self.failed_count,
            "skippedCount": self.skipped_count,
            "jobResults": list(self.job_results),
            "metrics": dict(self.metrics),
         }


QARunner = Callable[[str, str, Dict[str, Any]], AvatarQAResult]
MetricHook = Callable[[str, Mapping[str, Any]], None]

_FLUX_GENERATOR_CACHE: Dict[tuple[str, str, int, int, int, float], "Flux2KleinImageGenerator"] = {}
_MODEL_METRICS: Dict[str, int] = {
    "modelCacheHits": 0,
    "modelCacheMisses": 0,
    "modelLoadCalls": 0,
}


@dataclass(frozen=True)
class ResolvedBatchPayload:
    jobs: List[Dict[str, Any]]
    batch_id: str
    deadline_seconds: Optional[int]


def env_value(name: str, fallback: str) -> str:
    value = os.environ.get(name, "").strip()
    return value if value else fallback


def _bool_env(name: str) -> Optional[bool]:
    raw = os.environ.get(name)
    if raw is None:
        return None
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise AvatarGenerationError(f"{name} must be a boolean value.")


def is_production_environment() -> bool:
    return is_production_like_environment()


def is_local_or_dev_environment() -> bool:
    return _shared_is_local_or_dev_environment()


def resolve_worker_mode(mode: Optional[str] = None) -> str:
    dry_run_flag = _bool_env("AVATAR_WORKER_DRY_RUN")
    production = is_production_environment()
    if production and dry_run_flag is True:
        raise AvatarGenerationError("dry_run is not allowed when ENVIRONMENT=production.")
    if dry_run_flag is True and not is_local_or_dev_environment():
        raise AvatarGenerationError("dry_run is only allowed in local/dev/test environments.")

    explicit_mode = (mode or "").strip().lower()
    env_mode = os.environ.get("AVATAR_WORKER_MODE", "").strip().lower()
    if explicit_mode:
        run_mode = explicit_mode
    elif env_mode:
        run_mode = env_mode
    elif dry_run_flag is True:
        run_mode = "dry_run"
    elif production:
        run_mode = CANONICAL_AZURE_WORKER_MODE
    else:
        run_mode = "dry_run"

    if run_mode == "azure":
        run_mode = CANONICAL_AZURE_WORKER_MODE
    if run_mode not in {"dry_run", "flux", CANONICAL_AZURE_WORKER_MODE}:
        raise AvatarGenerationError(
            "AVATAR_WORKER_MODE must be dry_run, flux (local legacy only), or azure_gpt_image_2."
        )
    if production and run_mode == "flux":
        raise AvatarGenerationError("legacy_flux_is_not_a_production_generation_backend")
    if production and run_mode == "dry_run":
        raise AvatarGenerationError("dry_run is not allowed when ENVIRONMENT=production.")
    if run_mode == "dry_run" and not is_local_or_dev_environment():
        raise AvatarGenerationError("dry_run is only allowed in local/dev/test environments.")
    return run_mode


def source_photo_bucket() -> str:
    return env_value("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET)


def avatar_temp_bucket() -> str:
    return env_value("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET)


def _explicit_data_project_from_env() -> Optional[str]:
    for name in ("AVATAR_DATA_PROJECT", "FIRESTORE_PROJECT", "GCP_PROJECT"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def resolve_firestore_project(explicit_project: Optional[str] = None) -> Optional[str]:
    return explicit_project or _explicit_data_project_from_env()


def validate_bridge_runtime_config(firestore_project: Optional[str] = None) -> None:
    if BRIDGE_ENVIRONMENT not in configured_environment_names():
        return

    data_project = resolve_firestore_project(firestore_project)
    if data_project != FESTIVAL_DATA_PROJECT:
        raise AvatarGenerationError(
            "production_bridge requires AVATAR_DATA_PROJECT/FIRESTORE_PROJECT/GCP_PROJECT=seolleyeon-festival."
        )

    forbidden_buckets: List[str] = []
    for name in ("SOURCE_PHOTO_BUCKET", "AVATAR_TEMP_BUCKET", "APPROVED_AVATAR_BUCKET"):
        value = os.environ.get(name, "").strip()
        if value.startswith(FORBIDDEN_BRIDGE_BUCKET_PREFIX):
            forbidden_buckets.append(name)
    if forbidden_buckets:
        raise AvatarGenerationError(
            "production_bridge cannot use seolleyeon-final avatar/source/temp buckets: "
            + ", ".join(sorted(forbidden_buckets))
        )


def max_candidates() -> int:
    raw = os.environ.get("MAX_CANDIDATES", str(DEFAULT_MAX_CANDIDATES))
    try:
        return max(1, min(DEFAULT_MAX_CANDIDATES, int(raw)))
    except ValueError:
        return DEFAULT_MAX_CANDIDATES


def candidate_ttl_hours() -> int:
    raw = os.environ.get("AVATAR_CANDIDATE_TTL_HOURS", str(DEFAULT_CANDIDATE_TTL_HOURS))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_CANDIDATE_TTL_HOURS


def _int_env(name: str, fallback: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    try:
        value = int(raw)
    except ValueError:
        return fallback
    return max(minimum, min(maximum, value))


def _float_env(name: str, fallback: float, *, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    try:
        value = float(raw)
    except ValueError:
        return fallback
    return max(minimum, min(maximum, value))


def _reference_privacy_preprocess_enabled() -> bool:
    return _bool_env("AVATAR_REFERENCE_PRIVACY_PREPROCESS") is not False


def _bool_env_default(name: str, default: bool) -> bool:
    parsed = _bool_env(name)
    return default if parsed is None else parsed


def _generation_pause_reason() -> str:
    if _bool_env_default("AVATAR_GPU_WORKER_ENABLED", True) is False:
        return "gpu_worker_disabled"
    if _env_bool_any_default(
        ("AVATAR_DISABLE_NEW_GENERATION", "AVATAR_GENERATION_DISABLED", "AVATAR_GENERATION_PAUSED"),
        False,
    ):
        return "new_generation_disabled"
    if _env_bool_any_default(
        ("AVATAR_COST_KILL_SWITCH_ENABLED", "AVATAR_KILL_SWITCH", "AVATAR_GENERATION_BUDGET_EXHAUSTED"),
        False,
    ):
        return "cost_kill_switch_enabled"
    return ""

def _env_bool_any_default(names: Sequence[str], default: bool) -> bool:
    found_explicit = False
    for name in names:
        raw = os.environ.get(name)
        if raw is None or not str(raw).strip():
            continue
        found_explicit = True
        if _bool_env_default(name, False):
            return True
    return False if found_explicit else default

def _source_analysis_enabled(run_mode: str) -> bool:
    if run_mode == CANONICAL_AZURE_WORKER_MODE:
        return False
    if run_mode == "flux" and is_production_environment():
        return True
    return _bool_env_default("AVATAR_FACE_DETECTOR_ENABLED", run_mode == "flux")


def _trait_extraction_enabled(run_mode: str) -> bool:
    if run_mode == CANONICAL_AZURE_WORKER_MODE:
        return False
    return _bool_env_default("AVATAR_TRAIT_EXTRACTION_ENABLED", run_mode == "flux")


def _candidate_trait_qa_enabled(run_mode: str) -> bool:
    if run_mode == CANONICAL_AZURE_WORKER_MODE:
        return False
    return _bool_env_default("AVATAR_CANDIDATE_TRAIT_QA_ENABLED", run_mode == "flux")


def _trait_extraction_uses_privacy_reference() -> bool:
    return _bool_env_default("AVATAR_TRAIT_USE_PRIVACY_REFERENCE", False)


def _trait_require_validated() -> bool:
    return _bool_env_default("AVATAR_TRAIT_REQUIRE_VALIDATED", True)


def _source_visual_risk_enabled(run_mode: str) -> bool:
    if run_mode == CANONICAL_AZURE_WORKER_MODE:
        return False
    if run_mode == "flux" and is_production_environment():
        return True
    parsed = _bool_env("AVATAR_SOURCE_VISUAL_RISK_ENABLED")
    return bool(parsed) if parsed is not None else False


def _default_source_visual_risk_adapter() -> Any:
    from avatar_generation.qa_runtime import get_default_visual_risk_adapter

    return get_default_visual_risk_adapter()


def _primary_face_bbox_xyxy_pixels(source_analysis: Any, image_size: tuple[int, int]) -> Optional[tuple[float, float, float, float]]:
    bbox = getattr(source_analysis, "primary_face_bbox", None)
    if bbox is None and getattr(source_analysis, "primary_face", None) is not None:
        bbox = getattr(source_analysis.primary_face, "bbox", None)
    if bbox is None or len(bbox) < 4:
        return None
    width, height = image_size
    left, top, box_width, box_height = (float(bbox[index]) for index in range(4))
    if max(abs(left), abs(top), abs(box_width), abs(box_height)) <= 1.0:
        left *= width
        top *= height
        box_width *= width
        box_height *= height
    right = left + max(0.0, box_width)
    bottom = top + max(0.0, box_height)
    return (
        max(0.0, min(float(width), left)),
        max(0.0, min(float(height), top)),
        max(0.0, min(float(width), right)),
        max(0.0, min(float(height), bottom)),
    )


def _analyze_source_visual_risk(
    source_image: Image.Image,
    *,
    source_analysis: Any,
    run_mode: str,
    source_visual_risk_adapter: Any = None,
) -> Any:
    if not _source_visual_risk_enabled(run_mode):
        return None
    adapter = source_visual_risk_adapter or _default_source_visual_risk_adapter()
    try:
        return adapter.analyze(
            source_image,
            primary_face_bbox_xyxy=_primary_face_bbox_xyxy_pixels(
                source_analysis,
                source_image.size,
            ),
        )
    except Exception:
        provider = str(getattr(adapter, "provider", "source_visual_risk") or "source_visual_risk")
        return unavailable_visual_risk_analysis(
            provider,
            error_code="source_visual_risk_adapter_unavailable",
        )


def _is_critical_visual_risk_unavailable(visual_risk: Any) -> bool:
    if visual_risk is None:
        return False
    if getattr(visual_risk, "provider_available", True) is False:
        return True
    return str(getattr(visual_risk, "status", "")).strip().lower() == STATUS_CRITICAL_UNAVAILABLE


def _quality_context_metadata(metadata: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in dict(metadata or {}).items()
        if not str(key).startswith("_")
    }


def _finalize_needs_review_without_generation(
    fs: Any,
    payload: AvatarGenerationPayload,
    *,
    error_code: str,
    error_message: str,
    seconds_by_stage: Dict[str, float],
    job_started_at: float,
    extra_update: Optional[Mapping[str, Any]] = None,
) -> AvatarGenerationResult:
    seconds_by_stage["total"] = _elapsed_seconds(job_started_at)
    seconds_by_stage["total_seconds"] = seconds_by_stage["total"]
    seconds_by_stage["total_worker_seconds"] = seconds_by_stage["total"]
    final_update: Dict[str, Any] = {
        "status": "needs_review",
        "candidateIds": [],
        "errorCode": error_code,
        "errorMessage": error_message,
    }
    if extra_update:
        final_update.update(dict(extra_update))
    final_update.update(
        _cost_document_for_job(
            duration_seconds=seconds_by_stage["total"],
            candidate_count=0,
            seconds_by_stage=seconds_by_stage,
        )
    )
    _update_job_status(fs, payload.job_id, final_update)
    return AvatarGenerationResult(
        job_id=payload.job_id,
        uid=payload.uid,
        status="needs_review",
        candidate_ids=[],
        preview_ready_count=0,
        rejected_count=0,
        needs_review_count=0,
    )


def _processing_attempt_from_job_doc(job_doc: Optional[Mapping[str, Any]]) -> int:
    processing = (job_doc or {}).get("processing")
    value = processing.get("attempt") if isinstance(processing, Mapping) else None
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _admission_remaining_seconds(deadline: Optional[ClaimDeadline]) -> Optional[float]:
    if deadline is None:
        return None
    return max(0.0, deadline.remaining_seconds() - max(0, deadline.safety_seconds))


def _worker_admission_remaining_seconds(deadline: AvatarWorkerDeadline) -> float:
    return max(
        0.0,
        deadline.remaining_seconds() - deadline.soft_stop_margin_seconds,
    )

def _evaluate_worker_admission(
    firestore_client: Any,
    *,
    phase: str,
    existing_candidate_count: int,
    retry_attempt: int,
    remaining_deadline_seconds: Optional[float],
) -> AdmissionDecision:
    estimated_usd_per_candidate = _float_env_optional("AVATAR_ESTIMATED_USD_PER_CANDIDATE")
    if AvatarCostConfig is None or evaluate_cost_guard is None:
        return evaluate_admission(
            AdmissionRequest(
                phase=phase,
                existing_candidate_count=existing_candidate_count,
                retry_attempt=retry_attempt,
                remaining_deadline_seconds=remaining_deadline_seconds,
                usage=None,
            ),
            policy=AdmissionPolicy.from_env(),
        )

    cost_config = AvatarCostConfig.from_env()
    policy = AdmissionPolicy.from_cost_config(
        cost_config,
        estimated_usd_per_candidate=estimated_usd_per_candidate,
    )
    if not policy.production_like and not policy.enforce_budget:
        return evaluate_admission(
            AdmissionRequest(
                phase=phase,
                existing_candidate_count=existing_candidate_count,
                retry_attempt=retry_attempt,
                remaining_deadline_seconds=remaining_deadline_seconds,
                usage=CumulativeUsage(),
            ),
            policy=policy,
        )

    guard = evaluate_cost_guard(firestore_client, config=cost_config)
    usage = usage_from_cost_aggregate(guard.aggregate)
    decision = evaluate_admission(
        AdmissionRequest(
            phase=phase,
            existing_candidate_count=existing_candidate_count,
            retry_attempt=retry_attempt,
            remaining_deadline_seconds=remaining_deadline_seconds,
            usage=usage,
        ),
        policy=policy,
    )
    if guard.allowed or not decision.allowed:
        return decision
    return AdmissionDecision(
        allowed=False,
        reason=guard.reason or "cost_guard_denied",
        projected_daily_count=usage.daily_count,
        projected_monthly_count=usage.monthly_count,
        projected_daily_usd=usage.daily_usd,
        projected_monthly_usd=usage.monthly_usd,
        blocked_reasons=(guard.reason or "cost_guard_denied",),
    )


def _finalize_admission_denied(
    fs: Any,
    payload: AvatarGenerationPayload,
    decision: AdmissionDecision,
) -> AvatarGenerationResult:
    deadline_insufficient = decision.reason == "deadline_insufficient"
    error_code = (
        "avatar_worker_deadline_exceeded"
        if deadline_insufficient
        else "avatar_worker_cost_guard_paused"
    )
    error_message = (
        "Avatar generation deadline is insufficient."
        if deadline_insufficient
        else "Avatar generation is currently paused."
    )
    _update_job_status(
        fs,
        payload.job_id,
        {
            "status": "failed",
            "errorCode": error_code,
            "errorMessage": error_message,
            "admissionDecision": decision.to_dict(),
            "processing": {
                "lastErrorCode": error_code,
                "lastErrorMessage": decision.reason,
             },
            "retryable": False,
         },
    )
    return AvatarGenerationResult(
        job_id=payload.job_id,
        uid=payload.uid,
        status="failed",
        candidate_ids=[],
        preview_ready_count=0,
        rejected_count=0,
        needs_review_count=0,
    )

def _blocked_extra_round(extra_plan: Any, decision: AdmissionDecision, candidate_count: int) -> Dict[str, Any]:
    blocked_plan = dict(extra_plan.to_dict())
    blocked_plan["candidateCount"] = 0
    blocked_plan["reason"] = decision.reason
    blocked_plan["admissionDecision"] = decision.to_dict()
    blocked_reasons = list(blocked_plan.get("blockedReasons") or [])
    if decision.reason not in blocked_reasons:
        blocked_reasons.append(decision.reason)
    blocked_plan["blockedReasons"] = blocked_reasons
    return {
        "reason": "extra_blocked",
        "candidateCount": 0,
        "startIndex": candidate_count,
        "plan": blocked_plan,
    }


def _trait_input_uses_analysis_reference(run_mode: str, quality_context: Optional[AvatarQualityContext]) -> bool:
    return run_mode == "flux" and quality_context is not None and quality_context.analysis_image is not None


def _merge_region_color_traits(
    validation: TraitCardValidationResult,
    *,
    image: Image.Image,
    quality_context: Optional[AvatarQualityContext],
    avatar_presentation_gender: str,
) -> TraitCardValidationResult:
    if quality_context is None:
        return validation
    region_traits = extract_region_color_traits(
        image,
        primary_face_hint=(quality_context.face_hints[0] if quality_context.face_hints else None),
        foreground_mask=quality_context.foreground_mask,
    )
    raw_updates = region_traits.to_trait_card_update()
    updates: Dict[str, str] = {}
    for key, value in raw_updates.items():
        hint = region_traits.hair_color_range if key == "hair_color_range" else region_traits.clothing_color
        if hint.confidence in {"medium", "high"}:
            updates[key] = value
    if not updates:
        return validation
    data = validation.trait_card.to_dict()
    for key, value in updates.items():
        hint = region_traits.hair_color_range if key == "hair_color_range" else region_traits.clothing_color
        if hint.confidence in {"medium", "high"}:
            data[key] = value
    data["avatar_presentation_gender"] = avatar_presentation_gender
    from avatar_generation.trait_card.schema import AvatarTraitCard

    return TraitCardValidationResult(
        schema_version=validation.schema_version,
        trait_card=AvatarTraitCard(**data),
        privacy_safe=validation.privacy_safe,
        confidence=validation.confidence,
        errors=list(validation.errors),
        removed_keys=list(validation.removed_keys),
        invalid_enum_fields=list(validation.invalid_enum_fields),
        sanitized_fields=sorted(set(validation.sanitized_fields + ["region_color_traits"])),
    )


def _float_env_optional(name: str) -> Optional[float]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return max(0.0, value)


def _generation_budget(worker_deadline: AvatarWorkerDeadline, *, generated_count: int, max_total_candidates: int, min_extra_round_seconds: float = 30.0) -> GenerationBudget:
    max_total = max(0, int(max_total_candidates))
    estimated = _float_env_optional("AVATAR_ESTIMATED_USD_PER_CANDIDATE")
    max_usd = _float_env_optional("AVATAR_JOB_MAX_GENERATION_USD")
    remaining_usd = None
    if max_usd is not None and estimated is not None:
        remaining_usd = max(0.0, max_usd - (generated_count * estimated))
    return GenerationBudget(
        remaining_deadline_seconds=worker_deadline.remaining_seconds() - worker_deadline.soft_stop_margin_seconds,
        min_extra_round_seconds=min_extra_round_seconds,
        remaining_candidate_budget=max(0, max_total - generated_count),
        remaining_usd=remaining_usd,
        estimated_usd_per_candidate=estimated,
    )


def _qa_critical_models_unavailable(candidate_summaries: Sequence[Mapping[str, Any]]) -> bool:
    unavailable = {"unavailable", "critical_unavailable", "uncalibrated"}
    for summary in candidate_summaries:
        qa = summary.get("qa") if isinstance(summary, Mapping) else None
        if not isinstance(qa, Mapping):
            continue
        version = str(qa.get("qaVersion") or "").strip().lower()
        if "model_unavailable" in version:
            return True
        review_reasons = {str(reason) for reason in (qa.get("reviewReasons") or [])}
        if "model_unavailable" in review_reasons or any(reason.endswith("_unavailable") for reason in review_reasons):
            return True
        if qa.get("modelsUnavailable") is True:
            return True
        availability = qa.get("modelAvailability") if isinstance(qa.get("modelAvailability"), Mapping) else {}
        for value in availability.values():
            if str(value).strip().lower() in unavailable:
                return True
    return False


def _heuristic_preview_version_blocked(qa_doc: Mapping[str, Any]) -> bool:
    if not is_production_environment():
        return False
    version = str(qa_doc.get("qaVersion") or qa_doc.get("version") or "").strip().lower()
    return any(token in version for token in ("dev", "staging", "bridge", "heuristic"))


def _reference_preprocess_config_from_env() -> ReferencePreprocessConfig:
    requested_profile = os.environ.get("AVATAR_REFERENCE_PROFILE", "").strip().lower()
    profile_name = (
        requested_profile
        if requested_profile in REFERENCE_PREPROCESS_PROFILES
        else "privacy_strict"
    )
    return ReferencePreprocessConfig(
        profile_name=profile_name,
        face_downsample_px=_int_env(
            "AVATAR_REFERENCE_FACE_EQUIVALENT_SIZE",
            32,
            minimum=16,
            maximum=128,
        ),
        style_downsample_px=_int_env(
            "AVATAR_REFERENCE_NONFACE_EQUIVALENT_SIZE",
            96,
            minimum=32,
            maximum=256,
        ),
        face_blur_radius=_float_env(
            "AVATAR_REFERENCE_FACE_BLUR_RADIUS",
            4.0,
            minimum=0.0,
            maximum=16.0,
        ),
        style_blur_radius=_float_env(
            "AVATAR_REFERENCE_NONFACE_BLUR_RADIUS",
            1.5,
            minimum=0.0,
            maximum=8.0,
        ),
        sam_enabled=_bool_env_default("AVATAR_SAM_ENABLED", False),
        sam_model_path=os.environ.get("AVATAR_SAM_MODEL_PATH", "").strip() or None,
        sam_model_type=os.environ.get("AVATAR_SAM_MODEL_TYPE", "").strip() or "vit_b",
        sam_device=os.environ.get("AVATAR_SAM_DEVICE", "").strip() or None,
        background_neutralization_enabled=_bool_env_default(
            "AVATAR_BACKGROUND_NEUTRALIZATION_ENABLED",
            True,
        ),
        background_neutral_color=os.environ.get(
            "AVATAR_BACKGROUND_NEUTRAL_COLOR",
            "#F7F2EC",
        ).strip()
        or "#F7F2EC",
        secondary_face_blur_radius=_float_env(
            "AVATAR_SECONDARY_FACE_BLUR_RADIUS",
            12.0,
            minimum=0.0,
            maximum=48.0,
        ),
        background_blur_radius=_float_env(
            "AVATAR_BACKGROUND_BLUR_RADIUS",
            10.0,
            minimum=0.0,
            maximum=64.0,
        ),
        background_desaturate=_bool_env_default(
            "AVATAR_BACKGROUND_DESATURATE",
            True,
        ),
        background_text_logo_blur=_bool_env_default(
            "AVATAR_BACKGROUND_TEXT_LOGO_BLUR",
            True,
        ),
        metadata_extra={
            "referencePreprocessVersion": "region_privacy_v1",
            "enabled": True,
            "faceEquivalentSize": _int_env(
                "AVATAR_REFERENCE_FACE_EQUIVALENT_SIZE",
                32,
                minimum=16,
                maximum=128,
            ),
            "nonFaceEquivalentSize": _int_env(
                "AVATAR_REFERENCE_NONFACE_EQUIVALENT_SIZE",
                96,
                minimum=32,
                maximum=256,
            ),
            "hardPrivacyMode": is_production_environment(),
         },
    )


def prepare_privacy_reference_image(
    source_image: Image.Image,
    *,
    source_analysis: Any = None,
) -> Image.Image:
    """Reduce exact biometric detail before image-conditioned generation."""
    if not _reference_privacy_preprocess_enabled():
        validate_reference_preprocess_enabled_for_environment(
            preprocess_enabled=False,
        )
        return source_image.convert("RGB")

    validate_reference_preprocess_enabled_for_environment(preprocess_enabled=True)
    return preprocess_reference_image(
        source_image,
        source_analysis=source_analysis,
        config=_reference_preprocess_config_from_env(),
    ).image


def parse_gcs_uri(source: str) -> GcsRef:
    match = re.match(r"^(?:gs|gcs)://([^/]+)/(.+)$", source.strip())
    if not match:
        raise AvatarGenerationError("Image source must be a private gs:// or gcs:// URI.")
    bucket = match.group(1).strip()
    path = match.group(2).strip()
    if not bucket or not path or path.startswith("/") or ".." in path.split("/"):
        raise AvatarGenerationError("Image source is not a safe GCS object ref.")
    return GcsRef(bucket=bucket, path=path)


def validate_private_source_refs(source_refs: Sequence[str]) -> List[GcsRef]:
    if not source_refs:
        raise AvatarGenerationError("At least one sourcePhotoRef is required.")
    allowed_bucket = source_photo_bucket()
    parsed: List[GcsRef] = []
    for source in source_refs:
        ref = parse_gcs_uri(source)
        if ref.bucket != allowed_bucket:
            raise AvatarGenerationError("Source photo bucket is not allowed.")
        parsed.append(ref)
    return parsed


def validate_source_refs_belong_to_uid(source_refs: Sequence[GcsRef], uid: str) -> None:
    expected_prefix = f"users/{uid}/source/"
    for ref in source_refs:
        if not ref.path.startswith(expected_prefix):
            raise AvatarGenerationError("Source photo ref does not belong to the avatar job uid.")


def decode_task_payload(raw_payload: Mapping[str, Any]) -> Dict[str, Any]:
    message = raw_payload.get("message")
    if isinstance(message, Mapping) and isinstance(message.get("data"), str):
        try:
            decoded = base64.b64decode(message["data"]).decode("utf-8")
            payload = json.loads(decoded)
        except Exception as exc:  # pragma: no cover - exact JSON error is not important
            raise AvatarGenerationError("Invalid Pub/Sub message.data payload.") from exc
        if not isinstance(payload, dict):
            raise AvatarGenerationError("Pub/Sub message.data must decode to a JSON object.")
        return payload
    return dict(raw_payload)


def parse_avatar_generation_payload(raw_payload: Mapping[str, Any]) -> AvatarGenerationPayload:
    payload = decode_task_payload(raw_payload)
    if payload.get("schemaVersion") != "avatar_job_v1":
        raise AvatarGenerationError("Unsupported avatar job schemaVersion.")
    if payload.get("jobType") != "avatar_generation":
        raise AvatarGenerationError("Unsupported avatar jobType.")

    job_id = str(payload.get("jobId") or "").strip()
    uid = str(payload.get("uid") or "").strip()
    if not re.match(r"^[A-Za-z0-9_-]+$", job_id):
        raise AvatarGenerationError("jobId is required and must be a safe id.")
    if not re.match(r"^[A-Za-z0-9_-]+$", uid):
        raise AvatarGenerationError("uid is required and must be a safe id.")

    source_photo_ids = [
        str(value).strip()
        for value in payload.get("sourcePhotoIds", [])
        if str(value).strip()
    ]
    source_photo_refs = [
        str(value).strip()
        for value in payload.get("sourcePhotoRefs", [])
        if str(value).strip()
    ]
    parsed_source_refs = validate_private_source_refs(source_photo_refs)
    validate_source_refs_belong_to_uid(parsed_source_refs, uid)

    candidate_count = int(payload.get("candidateCount") or DEFAULT_MAX_CANDIDATES)
    if candidate_count < 1 or candidate_count > max_candidates():
        raise AvatarGenerationError("candidateCount must be between 1 and MAX_CANDIDATES.")

    model_id = str(payload.get("modelId") or AZURE_GPT_IMAGE_2_MODEL_ID).strip()
    if model_id not in {FLUX2_KLEIN_MODEL_ID, AZURE_GPT_IMAGE_2_MODEL_ID}:
        raise AvatarGenerationError("Unsupported avatar generation modelId.")

    return AvatarGenerationPayload(
        job_id=job_id,
        uid=uid,
        source_photo_ids=source_photo_ids,
        source_photo_refs=source_photo_refs,
        candidate_count=candidate_count,
        model_id=model_id,
        job_type="avatar_generation",
        schema_version="avatar_job_v1",
        idempotency_key=str(payload.get("idempotencyKey") or "").strip(),
        avatar_presentation_gender=normalize_avatar_presentation_gender(
            payload.get("avatarPresentationGender")
        ),
    )


def deterministic_seed(job_id: str, index: int) -> int:
    digest = hashlib.sha256(f"{job_id}:{index}:avatar_generation_v2".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def candidate_id_for(job_id: str, index: int) -> str:
    return f"cand_{job_id}_{index + 1:02d}"


def redact_gcs_ref(value: str) -> str:
    try:
        ref = parse_gcs_uri(value)
    except AvatarGenerationError:
        return "<invalid-image-ref>"
    if ref.bucket == source_photo_bucket():
        return "gs://<private-source-photo-redacted>"
    return f"gs://{ref.bucket}/<redacted>"


def redact_error_message(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"g(?:s|cs)://[^\s\"']+", "<private-ref-redacted>", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?i)(X-Goog-[^=&\s]+|GoogleAccessId|Signature|Expires|X-Amz-[^=&\s]+)=([^&\s]+)",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp|chat-profile-photos)",
        "<private-bucket-redacted>",
        text,
        flags=re.IGNORECASE,
    )
    return text[:240]


def _doc_ref(client: Any, collection: str, doc_id: str) -> Any:
    col = client.collection(collection)
    if hasattr(col, "document"):
        return col.document(doc_id)
    return col.doc(doc_id)


def _doc_to_dict(snapshot: Any) -> Optional[Dict[str, Any]]:
    exists = bool(getattr(snapshot, "exists", False))
    if not exists:
        return None
    if hasattr(snapshot, "to_dict"):
        data = snapshot.to_dict()
    elif hasattr(snapshot, "data"):
        data = snapshot.data()
    else:
        data = None
    return dict(data or {})


def _set_doc(ref: Any, payload: Dict[str, Any], *, merge: bool = True) -> None:
    ref.set(payload, merge=merge)


def _update_doc(ref: Any, payload: Dict[str, Any]) -> None:
    if hasattr(ref, "update"):
        ref.update(payload)
    else:
        ref.set(payload, merge=True)


def _load_job_doc(firestore_client: Any, job_id: str) -> Optional[Dict[str, Any]]:
    return _doc_to_dict(_doc_ref(firestore_client, "avatarJobs", job_id).get())


def _load_private_media_doc(firestore_client: Any, uid: str) -> Optional[Dict[str, Any]]:
    return _doc_to_dict(_doc_ref(firestore_client, "userPrivateMedia", uid).get())


def _assert_job_can_run(job_doc: Optional[Dict[str, Any]], payload: AvatarGenerationPayload) -> None:
    if not job_doc:
        raise AvatarGenerationError("avatarJobs document was not found.")
    if str(job_doc.get("uid") or "") != payload.uid:
        raise AvatarGenerationError("avatarJobs uid does not match payload uid.")
    if str(job_doc.get("status") or "") in TERMINAL_JOB_STATUSES:
        raise AvatarGenerationError("Avatar job is already complete.")


def _azure_generation_claim_active(job_doc: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(job_doc, Mapping):
        return False
    if str(job_doc.get("generationBackend") or "").strip() != AZURE_GPT_IMAGE_2_MODEL_ID:
        return False
    status = str(job_doc.get("status") or "").strip()
    if status == "failed":
        return False
    if status in {"provider_inflight", "generated", "persisted", "qa_pending"}:
        return True
    claim = job_doc.get("generationClaim")
    return isinstance(claim, Mapping) and claim.get("state") == "active"


def _result_for_active_azure_generation(
    payload: AvatarGenerationPayload,
    job_doc: Mapping[str, Any],
) -> AvatarGenerationResult:
    raw_ids = job_doc.get("candidateIds")
    candidate_ids = (
        [str(value) for value in raw_ids if str(value).strip()]
        if isinstance(raw_ids, Sequence) and not isinstance(raw_ids, str)
        else []
    )
    return AvatarGenerationResult(
        job_id=payload.job_id,
        uid=payload.uid,
        status=str(job_doc.get("status") or "provider_inflight"),
        candidate_ids=candidate_ids,
        preview_ready_count=0,
        rejected_count=0,
        needs_review_count=0,
    )


def _claim_azure_generation_run(
    firestore_client: Any,
    payload: AvatarGenerationPayload,
) -> bool:
    ref = _doc_ref(firestore_client, "avatarJobs", payload.job_id)
    claim = {
        "state": "active",
        "backend": AZURE_GPT_IMAGE_2_MODEL_ID,
        "idempotencyKey": payload.idempotency_key,
        "claimedAt": SERVER_TIMESTAMP,
    }

    def claim_transaction(transaction: Any) -> bool:
        current = _doc_to_dict(ref.get(transaction=transaction)) or {}
        if _azure_generation_claim_active(current):
            return False
        transaction.set(
            ref,
            {
                "generationClaim": claim,
                "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
                "provenance": _azure_provenance_document(),
            },
            merge=True,
        )
        return True

    transaction_factory = getattr(firestore_client, "transaction", None)
    if not callable(transaction_factory):
        current = _doc_to_dict(ref.get()) or {}
        if _azure_generation_claim_active(current):
            return False
        _set_doc(
            ref,
            {
                "generationClaim": claim,
                "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
                "provenance": _azure_provenance_document(),
            },
            merge=True,
        )
        return True

    transaction = transaction_factory()
    if (
        firestore is not None
        and hasattr(firestore, "transactional")
        and not getattr(transaction, "_codex_fake_transaction", False)
    ):
        return bool(firestore.transactional(claim_transaction)(transaction))
    return bool(claim_transaction(transaction))


def _assert_avatar_generation_consent(private_doc: Optional[Dict[str, Any]]) -> None:
    if not private_doc:
        raise AvatarGenerationError("userPrivateMedia document was not found.")
    consent = private_doc.get("photoConsent") or {}
    if not isinstance(consent, Mapping):
        raise AvatarGenerationError("photoConsent is invalid.")
    if consent.get("avatarGeneration") is not True:
        raise AvatarGenerationError("avatarGeneration consent is missing.")
    if consent.get("profileDisplayOriginalPhoto") is not False:
        raise AvatarGenerationError("profileDisplayOriginalPhoto consent must be false.")


def _blob_for(storage_client: Any, ref: GcsRef) -> Any:
    return storage_client.bucket(ref.bucket).blob(ref.path)


def load_source_image_bytes_from_gcs(
    storage_client: Any,
    source_ref: GcsRef,
) -> Tuple[bytes, str]:
    blob = _blob_for(storage_client, source_ref)
    if hasattr(blob, "exists") and not blob.exists():
        raise AvatarGenerationError("Private source photo does not exist.")
    data = bytes(blob.download_as_bytes())
    _validate_stored_source_image_bytes(data)
    declared_content_type = str(getattr(blob, "content_type", "") or "").lower().split(";", 1)[0].strip()
    content_type = declared_content_type if declared_content_type in {
        "image/jpeg",
        "image/png",
        "image/webp",
    } else "image/jpeg"
    return data, content_type


def image_from_stored_source_bytes(data: bytes) -> Image.Image:
    _validate_stored_source_image_bytes(data)
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGB")


def load_source_image_from_gcs(storage_client: Any, source_ref: GcsRef) -> Image.Image:
    data, _content_type = load_source_image_bytes_from_gcs(storage_client, source_ref)
    return image_from_stored_source_bytes(data)


def _validate_stored_source_image_bytes(data: bytes) -> None:
    if not data:
        raise AvatarGenerationError("Private source photo is empty.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.width <= 0 or image.height <= 0:
                raise ValueError("invalid dimensions")
    except Exception as exc:
        raise AvatarGenerationError("Private source photo is invalid or corrupt.") from exc


def _assert_azure_source_bytes_are_normalized_jpeg(
    data: Optional[bytes],
    content_type: str,
) -> None:
    if content_type != "image/jpeg" or not data:
        raise AvatarGenerationError("azure_source_not_normalized_jpeg")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = str(image.format or "").upper()
            image.verify()
    except Exception as exc:
        raise AvatarGenerationError("azure_source_not_normalized_jpeg") from exc
    if image_format != "JPEG":
        raise AvatarGenerationError("azure_source_not_normalized_jpeg")


def image_to_png_bytes(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def build_fixture_avatar_image(source_image: Image.Image, *, seed: int, index: int) -> Image.Image:
    base = source_image.resize((32, 32)).convert("RGB")
    avg = tuple(int(value) for value in ImageStat.Stat(base).mean[:3])
    accent = (
        (avg[0] + 28 + index * 9) % 255,
        (avg[1] + 18 + index * 13) % 255,
        (avg[2] + 34 + index * 17) % 255,
    )
    image = Image.new("RGB", (DEFAULT_WIDTH, DEFAULT_HEIGHT), (246, 242, 235))
    draw = ImageDraw.Draw(image)
    draw.ellipse((262, 170, 762, 720), fill=tuple(max(0, min(255, c + 12)) for c in avg))
    draw.ellipse((318, 284, 430, 384), fill=(48, 54, 60))
    draw.ellipse((594, 284, 706, 384), fill=(48, 54, 60))
    draw.arc((378, 418, 646, 590), 15, 165, fill=(82, 64, 58), width=16)
    draw.rounded_rectangle((286, 720, 738, 1020), radius=90, fill=accent)
    for offset in range(0, 96, 24):
        x = 212 + ((seed + offset) % 80)
        draw.arc((x, 110 + offset, x + 600, 360 + offset), 180, 350, fill=(64, 52, 45), width=20)
    return image


class Flux2KleinImageGenerator:
    def __init__(self, config: Flux2KleinExecutionConfig | None = None) -> None:
        self.config = config or resolve_flux2_klein_execution_config()
        self.model_id = self.config.logical_model_id
        self.model_artifact_revision = self.config.model_artifact_revision
        self._pipeline: Any = None
        self.model_load_seconds_total = 0.0

    def _load_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        started_at = time.perf_counter()
        try:
            import torch
            from diffusers import Flux2KleinPipeline
        except Exception as exc:  # pragma: no cover - expensive dependency path
            raise AvatarGenerationError(
                "Flux2KleinPipeline is unavailable. Install a diffusers version that "
                "supports black-forest-labs/FLUX.2-klein-4B in the GPU worker image."
            ) from exc

        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        pipe = Flux2KleinPipeline.from_pretrained(
            self.model_id,
            revision=self.model_artifact_revision,
            torch_dtype=dtype,
        )
        if torch.cuda.is_available():
            pipe = pipe.to("cuda")
        elif hasattr(pipe, "enable_model_cpu_offload"):
            pipe.enable_model_cpu_offload()
        self._pipeline = pipe
        self.model_load_seconds_total = round(
            self.model_load_seconds_total + _elapsed_seconds(started_at),
            3,
        )
        return pipe

    def generate(
        self,
        *,
        source_image: Image.Image,
        prompt: str,
        avoid_prompt: str = "",
        seed: int,
    ) -> Image.Image:
        try:
            import torch
        except Exception as exc:  # pragma: no cover - expensive dependency path
            raise AvatarGenerationError("PyTorch is required for FLUX generation.") from exc

        pipe = self._load_pipeline()
        generator = torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu").manual_seed(seed)
        final_prompt = build_flux_prompt_with_avoid(prompt, avoid_prompt)
        result = call_flux_pipeline_safely(
            pipe,
            prompt=final_prompt,
            image=source_image,
            width=int(self.config.width),
            height=int(self.config.height),
            num_inference_steps=int(self.config.num_inference_steps),
            guidance_scale=float(self.config.guidance_scale),
            generator=generator,
        )
        images = getattr(result, "images", None)
        if not images:
            raise AvatarGenerationError("FLUX generation returned no images.")
        return images[0].convert("RGB")


def get_azure_gpt_image2_provider() -> AzureGptImage2Provider:
    global _AZURE_PROVIDER_CACHE
    if _AZURE_PROVIDER_CACHE is None:
        _AZURE_PROVIDER_CACHE = _build_azure_gpt_image2_provider()
    return _AZURE_PROVIDER_CACHE


def reset_model_cache_for_tests() -> None:
    global _AZURE_PROVIDER_CACHE
    _FLUX_GENERATOR_CACHE.clear()
    _AZURE_PROVIDER_CACHE = None
    for key in _MODEL_METRICS:
        _MODEL_METRICS[key] = 0


def model_cache_metrics() -> Dict[str, int]:
    metrics = dict(_MODEL_METRICS)
    metrics["modelCacheSize"] = len(_FLUX_GENERATOR_CACHE)
    return metrics


def _flux_generator_cache_key(config: Flux2KleinExecutionConfig) -> tuple[str, str, int, int, int, float]:
    return (
        config.logical_model_id,
        config.model_artifact_revision,
        int(config.width),
        int(config.height),
        int(config.num_inference_steps),
        float(config.guidance_scale),
    )


def get_flux2_klein_generator(
    model_id: str = FLUX2_KLEIN_MODEL_ID,
    *,
    config: Flux2KleinExecutionConfig | None = None,
) -> Flux2KleinImageGenerator:
    resolved_config = config or resolve_flux2_klein_execution_config()
    if model_id != resolved_config.logical_model_id:
        resolved_config = replace(resolved_config, logical_model_id=model_id)
    cache_key = _flux_generator_cache_key(resolved_config)
    generator = _FLUX_GENERATOR_CACHE.get(cache_key)
    if generator is not None:
        _MODEL_METRICS["modelCacheHits"] += 1
        return generator
    _MODEL_METRICS["modelCacheMisses"] += 1
    _MODEL_METRICS["modelLoadCalls"] += 1
    generator = Flux2KleinImageGenerator(resolved_config)
    _FLUX_GENERATOR_CACHE[cache_key] = generator
    return generator
def warmup_avatar_model(*, mode: Optional[str] = None) -> Dict[str, Any]:
    run_mode = resolve_worker_mode(mode)
    warmed = False
    if run_mode == "flux":
        get_flux2_klein_generator(FLUX2_KLEIN_MODEL_ID)._load_pipeline()
        warmed = True
    return {
        "status": "ok",
        "mode": run_mode,
        "warmed": warmed,
        "metrics": model_cache_metrics(),
    }


def _candidate_generation_execution_audit(
    payload: AvatarGenerationPayload,
    *,
    mode: str,
    seed: int,
    generator: Any,
) -> Dict[str, Any]:
    if mode == "flux" and generator is not None:
        config = getattr(generator, "config", None)
        if isinstance(config, Flux2KleinExecutionConfig):
            audit = build_flux2_klein_execution_audit(config, seed=seed)
            return {**audit, "mode": mode, "candidateSeed": int(seed)}
    return {
        "modelId": payload.model_id,
        "modelVersion": FLUX2_KLEIN_VERSION,
        "mode": mode,
        "width": DEFAULT_WIDTH,
        "height": DEFAULT_HEIGHT,
        "numInferenceSteps": DEFAULT_STEPS,
        "guidanceScale": DEFAULT_GUIDANCE_SCALE,
        "candidateSeed": int(seed),
    }


def generate_candidate_artifacts(
    payload: AvatarGenerationPayload,
    source_image: Image.Image,
    *,
    mode: str,
    source_analysis: Any = None,
    trait_card: PromptAvatarTraitCard | None = None,
    privacy_reference_image: Optional[Image.Image] = None,
    reference_preprocess_metadata: Optional[Mapping[str, Any]] = None,
    candidate_start_index: int = 0,
    candidate_count: Optional[int] = None,
    seconds_by_stage: Optional[Dict[str, float]] = None,
    source_image_bytes: Optional[bytes] = None,
    source_content_type: str = "image/jpeg",
    deadline_monotonic: Optional[float] = None,
    azure_provider: Optional[AzureGptImage2Provider] = None,
    provider_usage_doc: Optional[Dict[str, Any]] = None,
) -> List[CandidateArtifact]:
    artifacts: List[CandidateArtifact] = []
    generator = get_flux2_klein_generator(payload.model_id) if mode == "flux" else None
    if mode == CANONICAL_AZURE_WORKER_MODE:
        _assert_azure_source_bytes_are_normalized_jpeg(source_image_bytes, source_content_type)
    provider = (
        azure_provider or get_azure_gpt_image2_provider()
        if mode == CANONICAL_AZURE_WORKER_MODE
        else None
    )
    model_load_seconds_before = _generator_model_load_seconds(generator)
    generation_reference = (
        privacy_reference_image
        or prepare_privacy_reference_image(source_image, source_analysis=source_analysis)
        if mode == "flux"
        else source_image
    )
    round_count = int(candidate_count or payload.candidate_count)
    total_count = max(payload.candidate_count, candidate_start_index + round_count)
    for index in range(candidate_start_index, candidate_start_index + round_count):
        candidate_id = candidate_id_for(payload.job_id, index)
        seed = deterministic_seed(payload.job_id, index)
        prompt = None
        generation_audit: Dict[str, Any]
        if mode == "flux":
            assert generator is not None
            prompt = build_avatar_prompt(
                trait_card=trait_card,
                candidate_index=index,
                candidate_count=total_count,
                seed=seed,
            )
            image = generator.generate(
                source_image=generation_reference,
                prompt=prompt.positive,
                avoid_prompt=prompt.provider_negative or prompt.negative,
                seed=seed,
            )
            candidate_image_bytes = image_to_png_bytes(image)
            generation_audit = {
                **_candidate_generation_execution_audit(
                    payload,
                    mode=mode,
                    seed=seed,
                    generator=generator,
                ),
                "referencePrivacyPreprocess": _reference_privacy_preprocess_enabled(),
                "referencePreprocess": dict(reference_preprocess_metadata or {}),
                "promptVersion": str(prompt.meta.get("prompt_version") or "seolleyeon_avatar_v4"),
                "promptBuilder": "seolleyeon_avatar_prompt_builder_v4",
                "candidateSeed": seed,
            }
        elif mode == CANONICAL_AZURE_WORKER_MODE:
            if provider is None or source_image_bytes is None:
                raise AvatarGenerationError("Azure generation requires stored source bytes.")
            provider_key = (
                f"{payload.idempotency_key or payload.job_id}:candidate:{candidate_id}:"
                f"{AZURE_GPT_IMAGE_2_MODEL_ID}"
            )
            try:
                generated: AzureGenerationResult = provider.generate(
                    source_image_bytes=source_image_bytes,
                    source_content_type=source_content_type,
                    prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
                    idempotency_key=provider_key,
                    deadline_monotonic=deadline_monotonic,
                )
            except AzureProviderError as exc:
                _merge_provider_usage(
                    provider_usage_doc,
                    exc.provider_usage
                    or provider_usage(
                        attempts=exc.attempts or 1,
                        outcome="unknown" if exc.unknown_outcome else "failure",
                    ),
                )
                raise
            _merge_provider_usage(
                provider_usage_doc,
                provider_usage(
                    attempts=generated.audit.attempts,
                    outcome=generated.audit.outcome,
                ),
            )
            candidate_image_bytes = generated.image_bytes
            generation_audit = generated.audit.to_dict()
            generation_audit["candidateSeed"] = seed
        else:
            image = build_fixture_avatar_image(source_image, seed=seed, index=index)
            candidate_image_bytes = image_to_png_bytes(image)
            generation_audit = {
                **_candidate_generation_execution_audit(
                    payload,
                    mode=mode,
                    seed=seed,
                    generator=generator,
                ),
                "candidateSeed": seed,
            }
        image_ref = build_temp_candidate_ref(
            uid=payload.uid,
            job_id=payload.job_id,
            candidate_id=candidate_id,
        )
        artifacts.append(
            CandidateArtifact(
                candidate_id=candidate_id,
                image_ref=image_ref,
                image_bytes=candidate_image_bytes,
                seed=seed,
                generation_params=generation_audit,
            )
        )
    if seconds_by_stage is not None and generator is not None:
        _add_stage_seconds(
            seconds_by_stage,
            "model_load_seconds",
            _generator_model_load_seconds(generator) - model_load_seconds_before,
        )
    return artifacts


def _merge_provider_usage(
    target: Optional[Dict[str, Any]],
    update: Optional[Mapping[str, Any]],
) -> None:
    if target is None or not isinstance(update, Mapping):
        return
    for key, value in update.items():
        if key in {"requestCount", "attemptCount", "successCount", "failureCount", "unknownOutcomeCount"}:
            target[key] = int(target.get(key) or 0) + int(value or 0)
        else:
            target[key] = value


def _upload_candidate(storage_client: Any, artifact: CandidateArtifact) -> None:
    ref = parse_gcs_uri(artifact.image_ref)
    if ref.bucket != avatar_temp_bucket():
        raise AvatarGenerationError("Generated candidate imageRef is not in avatar temp bucket.")
    blob = _blob_for(storage_client, ref)
    blob.upload_from_string(
        artifact.image_bytes,
        content_type="image/png",
        predefined_acl=None,
    )
    if hasattr(blob, "patch"):
        blob.cache_control = "private, max-age=0, no-store"
        blob.patch()


def _write_fixture_file(output_dir: Path, artifact: CandidateArtifact) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{artifact.candidate_id}.png").write_bytes(artifact.image_bytes)


def _candidate_status_from_qa(qa_doc: Mapping[str, Any]) -> str:
    candidate_for_gate = {"status": "hard_pass", "qa": qa_doc}
    if _heuristic_preview_version_blocked(qa_doc):
        return "needs_review"
    if qa_doc.get("rejectReasons"):
        return "rejected"
    if qa_doc.get("requiresHumanReview") is True:
        return "needs_review"
    if qa_doc.get("previewAllowed") is True and passes_absolute_preview_checks(candidate_for_gate):
        return "hard_pass"
    if (
        (qa_doc.get("softPass") is True or qa_doc.get("soft_pass") is True)
        and passes_absolute_preview_checks({"status": "soft_pass", "qa": qa_doc})
    ):
        return "soft_pass"
    if qa_doc.get("previewAllowed") is True or qa_doc.get("softPass") is True or qa_doc.get("soft_pass") is True:
        return "needs_review"
    return "rejected"


def _candidate_doc(
    payload: AvatarGenerationPayload,
    artifact: CandidateArtifact,
    *,
    status: str,
    qa_doc: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=candidate_ttl_hours())
    return {
        "candidateId": artifact.candidate_id,
        "jobId": payload.job_id,
        "uid": payload.uid,
        "imageRef": artifact.image_ref,
        "modelId": payload.model_id,
        "modelVersion": (
            AZURE_GPT_IMAGE_2_VERSION
            if payload.model_id == AZURE_GPT_IMAGE_2_MODEL_ID
            else FLUX2_KLEIN_VERSION
        ),
        "seed": artifact.seed,
        "generationParams": artifact.generation_params,
        "status": status,
        "qa": dict(qa_doc or {}),
        "createdAt": SERVER_TIMESTAMP,
        "updatedAt": SERVER_TIMESTAMP,
        "expiresAt": expires_at,
    }


def _update_job_status(firestore_client: Any, job_id: str, payload: Dict[str, Any]) -> str:
    ref = _doc_ref(firestore_client, "avatarJobs", job_id)
    update_payload = {
        **payload,
        "updatedAt": SERVER_TIMESTAMP,
    }
    transaction_factory = getattr(firestore_client, "transaction", None)
    if callable(transaction_factory):
        transaction = transaction_factory()
        if (
            firestore is not None
            and hasattr(firestore, "transactional")
            and not getattr(transaction, "_codex_fake_transaction", False)
        ):
            transactional = firestore.transactional(_update_job_status_transactional)
            return str(transactional(transaction, ref, update_payload))
        return str(_update_job_status_transactional(transaction, ref, update_payload))

    current = _doc_to_dict(ref.get()) or {}
    current_status = str(current.get("status") or "").strip()
    if current_status in TERMINAL_JOB_STATUSES:
        logger.info(
            "Skipping avatar job status update because job is terminal: jobId=%s status=%s",
            job_id,
            current_status,
        )
        return current_status

    _set_doc(ref, update_payload, merge=True)
    return str(payload.get("status") or current_status)


def _update_job_status_transactional(transaction: Any, ref: Any, payload: Dict[str, Any]) -> str:
    snapshot = ref.get(transaction=transaction)
    current = _doc_to_dict(snapshot) or {}
    current_status = str(current.get("status") or "").strip()
    if current_status in TERMINAL_JOB_STATUSES:
        logger.info(
            "Skipping avatar job status update because job is terminal: jobId=%s status=%s",
            getattr(ref, "id", ""),
            current_status,
        )
        return current_status

    write_result = transaction.set(ref, payload, merge=True)
    if isinstance(write_result, str) and write_result.startswith("terminal_skipped:"):
        return write_result.split(":", 1)[1]
    return str(payload.get("status") or current_status)


def _update_job_status_if_not_terminal(
    firestore_client: Any,
    job_id: str,
    payload: Dict[str, Any],
) -> str:
    return _update_job_status(firestore_client, job_id, payload)


def _elapsed_seconds(started_at: float) -> float:
    return round(max(0.0, time.perf_counter() - started_at), 3)


def _add_stage_seconds(seconds_by_stage: Dict[str, float], key: str, seconds: float) -> None:
    seconds_by_stage[key] = round(
        max(0.0, float(seconds_by_stage.get(key, 0.0))) + max(0.0, float(seconds)),
        3,
    )


def _generator_model_load_seconds(generator: Any) -> float:
    try:
        return max(0.0, float(getattr(generator, "model_load_seconds_total", 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _normalized_seconds_by_stage(
    seconds_by_stage: Mapping[str, float],
    *,
    total_worker_seconds: float,
) -> Dict[str, float]:
    normalized = {
        key: round(max(0.0, float(seconds_by_stage.get(key, 0.0) or 0.0)), 3)
        for key, _cost_key in NORMALIZED_STAGE_COST_KEYS
    }
    if normalized["upload_seconds"] == 0.0:
        normalized["upload_seconds"] = round(
            max(0.0, float(seconds_by_stage.get("candidate_upload_seconds", 0.0) or 0.0)),
            3,
        )
    if normalized["total_worker_seconds"] == 0.0:
        normalized["total_worker_seconds"] = round(max(0.0, float(total_worker_seconds)), 3)
    return normalized


def _seconds_by_stage_document(
    seconds_by_stage: Mapping[str, float],
    *,
    total_worker_seconds: float,
) -> Dict[str, float]:
    document = {
        str(key): round(max(0.0, float(value)), 3)
        for key, value in seconds_by_stage.items()
    }
    normalized = _normalized_seconds_by_stage(
        seconds_by_stage,
        total_worker_seconds=total_worker_seconds,
    )
    document.update(normalized)
    document.setdefault("total_seconds", normalized["total_worker_seconds"])
    document.setdefault("total", normalized["total_worker_seconds"])
    document.setdefault("candidate_upload_seconds", normalized["upload_seconds"])
    return document


def _json_safe_cost_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe_cost_value(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [_json_safe_cost_value(nested) for nested in value]
    return value


def _cost_document_for_job(
    *,
    duration_seconds: float,
    candidate_count: int,
    seconds_by_stage: Mapping[str, float],
    generation_backend: str = "local_cloud_run_flux",
    provider_usage_document: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    estimate = build_job_cost_document(
        duration_seconds=duration_seconds,
        estimated_at=datetime.now(tz=timezone.utc),
        generation_backend=generation_backend,
        provider_usage=provider_usage_document,
    )
    cost_estimate = _json_safe_cost_value(dict(estimate["costEstimate"]))
    seconds_document = _seconds_by_stage_document(
        seconds_by_stage,
        total_worker_seconds=cost_estimate["durationSeconds"],
    )
    normalized_seconds = _normalized_seconds_by_stage(
        seconds_document,
        total_worker_seconds=cost_estimate["durationSeconds"],
    )
    cost = {
        "candidateCount": int(candidate_count),
        "estimatedUsd": estimate["costEstimateUsd"],
        "pricingVersion": cost_estimate["pricingVersion"],
        "secondsByStage": seconds_document,
        "breakdown": dict(cost_estimate.get("breakdown") or {}),
        "estimatedAt": cost_estimate.get("estimatedAt"),
    }
    cost.update(
        {
            cost_key: normalized_seconds[stage_key]
            for stage_key, cost_key in NORMALIZED_STAGE_COST_KEYS
         }
    )
    result = {
        "cost": cost,
        "costEstimateUsd": estimate["costEstimateUsd"],
        "costEstimate": cost_estimate,
        "durationSeconds": cost_estimate["durationSeconds"],
    }
    if provider_usage_document:
        result["providerUsage"] = dict(provider_usage_document)
    return result


def _cost_metrics_for_batch(
    jobs: Sequence[Mapping[str, Any]],
    *,
    duration_seconds: float,
) -> Dict[str, Any]:
    estimate = build_batch_cost_document(
        jobs,
        duration_seconds=duration_seconds,
        estimated_at=datetime.now(tz=timezone.utc),
    )
    batch_estimate = _json_safe_cost_value(dict(estimate["batchCostEstimate"]))
    total_cost = dict(batch_estimate.get("totalCost") or {})
    return {
        "jobCount": int(batch_estimate.get("jobCount") or 0),
        "candidateCount": int(batch_estimate.get("candidateCount") or 0),
        "totalWorkerSeconds": total_cost.get("durationSeconds", 0.0),
        "estimatedUsd": estimate["batchCostEstimateUsd"],
        "pricingVersion": batch_estimate.get("pricingVersion") or total_cost.get("pricingVersion", ""),
        "savingsUsd": batch_estimate.get("savingsUsd", 0.0),
        "savingsRatio": batch_estimate.get("savingsRatio", 0.0),
        "estimate": batch_estimate,
    }


def _job_cost_input(job_doc: Mapping[str, Any], result: AvatarGenerationResult) -> Dict[str, Any]:
    cost = job_doc.get("cost")
    duration = None
    if isinstance(cost, Mapping):
        duration = cost.get("totalWorkerSeconds")
    if duration is None:
        duration = job_doc.get("durationSeconds")
    return {
        "jobId": result.job_id,
        "status": result.status,
        "candidateCount": len(result.candidate_ids),
        "durationSeconds": duration or 0.0,
        "costEstimateUsd": job_doc.get("costEstimateUsd", 0.0),
    }


def _ensure_source_refs_match_private_media(
    private_doc: Optional[Dict[str, Any]],
    payload: AvatarGenerationPayload,
) -> None:
    if not private_doc:
        return
    active_refs = {
        str(entry.get("gcsUri") or "").strip()
        for entry in private_doc.get("sourcePhotos", [])
        if isinstance(entry, Mapping)
        and entry.get("status") == "active"
        and isinstance(entry.get("purpose"), Mapping)
        and entry["purpose"].get("avatarGeneration") is True
    }
    missing = [ref for ref in payload.source_photo_refs if ref not in active_refs]
    if missing:
        raise AvatarGenerationError("Payload sourcePhotoRefs do not match active private media refs.")


def _current_source_entry(
    private_doc: Optional[Dict[str, Any]],
    source_photo_id: str,
) -> Optional[Mapping[str, Any]]:
    if not private_doc:
        return None
    source_photos = private_doc.get("sourcePhotos")
    if not isinstance(source_photos, Sequence) or isinstance(source_photos, str):
        return None
    for entry in source_photos:
        if isinstance(entry, Mapping) and str(entry.get("photoId") or "") == source_photo_id:
            return entry
    return None


def _has_selection_version(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _selection_version(value: Any) -> Optional[int]:
    if not _has_selection_version(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _current_avatar_contract_mismatch(
    job_doc: Optional[Dict[str, Any]],
    private_doc: Optional[Dict[str, Any]],
    payload: AvatarGenerationPayload,
    source_refs: Sequence[GcsRef],
) -> str:
    if not job_doc:
        return "missing_job"
    if not private_doc:
        return "missing_private_media"
    current_job_id = str(private_doc.get("currentAvatarJobId") or "").strip()
    current_source_id = str(private_doc.get("currentAvatarSourcePhotoId") or "").strip()
    payload_source_id = payload.source_photo_ids[0] if payload.source_photo_ids else ""
    job_source_ids = job_doc.get("sourcePhotoIds")
    job_source_id = (
        str(job_source_ids[0]).strip()
        if isinstance(job_source_ids, Sequence)
        and not isinstance(job_source_ids, str)
        and job_source_ids
        else ""
    )
    if current_job_id != payload.job_id:
        return "current_job_mismatch"
    job_selection_raw = job_doc.get("avatarSourceSelectionVersion")
    private_selection_raw = private_doc.get("avatarSourceSelectionVersion")
    if _has_selection_version(job_selection_raw) and _has_selection_version(private_selection_raw):
        job_selection_version = _selection_version(job_selection_raw)
        private_selection_version = _selection_version(private_selection_raw)
        if (
            job_selection_version is None
            or private_selection_version is None
            or job_selection_version != private_selection_version
        ):
            return "selection_version_mismatch"
    if not current_source_id or payload_source_id != current_source_id:
        return "current_source_mismatch"
    if job_source_id and job_source_id != current_source_id:
        return "job_source_mismatch"
    if not source_refs or not source_refs[0].path.startswith(f"users/{payload.uid}/source/"):
        return "source_path_uid_mismatch"
    source_entry = _current_source_entry(private_doc, current_source_id)
    if source_entry is None:
        return "current_source_missing"
    if source_entry.get("status") != "active":
        return "current_source_not_active"
    if source_entry.get("avatarGenerationState") != "current":
        return "current_source_not_current"
    if str(source_entry.get("gcsUri") or "").strip() != payload.source_photo_refs[0]:
        return "current_source_ref_mismatch"
    return ""


def _mark_avatar_job_superseded(
    firestore_client: Any,
    payload: AvatarGenerationPayload,
    reason: str,
) -> AvatarGenerationResult:
    _update_job_status(
        firestore_client,
        payload.job_id,
        {
            "status": "superseded",
            "errorCode": "avatar_job_superseded",
            "errorMessage": f"Avatar job is no longer current: {reason}.",
         },
    )
    return AvatarGenerationResult(
        job_id=payload.job_id,
        uid=payload.uid,
        status="superseded",
        candidate_ids=[],
        preview_ready_count=0,
        rejected_count=0,
        needs_review_count=0,
    )


def _mark_candidates_superseded(
    firestore_client: Any,
    candidate_ids: Sequence[str],
) -> None:
    for candidate_id in candidate_ids:
        if not candidate_id:
            continue
        try:
            _doc_ref(firestore_client, "avatarCandidates", candidate_id).set(
                {
                    "status": "superseded",
                    "updatedAt": SERVER_TIMESTAMP,
                 },
                merge=True,
            )
        except Exception as exc:
            logger.warning(
                "Failed to mark stale avatar candidate superseded.",
                extra={
                    "candidateIdHash": hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:12],
                    "errorType": type(exc).__name__,
                    "error": redact_error_message(exc),
                 },
            )


def _avatar_presentation_gender_for_job(
    payload: AvatarGenerationPayload,
    job_doc: Optional[Mapping[str, Any]],
) -> str:
    payload_gender = normalize_avatar_presentation_gender(
        payload.avatar_presentation_gender
    )
    if payload_gender != "unknown":
        return payload_gender
    if isinstance(job_doc, Mapping):
        return normalize_avatar_presentation_gender(
            job_doc.get("avatarPresentationGender")
            or job_doc.get("avatar_presentation_gender")
        )
    return "unknown"


def _source_reject_error_code(analysis_doc: Mapping[str, Any]) -> str:
    reasons = {
        str(value)
        for value in analysis_doc.get("rejectReasons", [])
        if str(value).strip()
    }
    if "no_face" in reasons:
        return "avatar_source_no_face"
    if "multiple_faces" in reasons or "multi_face_primary" in reasons:
        return "avatar_source_multi_face"
    if "ambiguous_primary_face" in reasons:
        return "avatar_source_multi_face"
    if "face_too_small" in reasons:
        return "avatar_source_face_too_small"
    if "face_too_blurry" in reasons:
        return "avatar_source_face_too_blurry"
    if "face_out_of_frame" in reasons:
        return "avatar_source_face_out_of_frame"
    if "landmarks_unstable" in reasons:
        return "avatar_source_landmarks_unstable"
    if "low_light" in reasons:
        return "avatar_source_low_light"
    if "compression_damage" in reasons:
        return "avatar_source_compression_damage"
    if "analysis_uncertain" in reasons:
        return "avatar_source_analysis_uncertain"
    if reasons & {
        "background_text_logo_risk",
        "background_logo_text_risk",
        "school_sign_or_logo",
        "large_background_text_logo",
    }:
        return "avatar_background_text_logo_risky"
    return "avatar_source_safety_rejected"


def _source_reject_error_message(analysis_doc: Mapping[str, Any]) -> str:
    error_code = _source_reject_error_code(analysis_doc)
    if error_code == "avatar_source_multi_face":
        return "얼굴이 여러 명 감지됐어요. 혼자 나온 사진을 선택해주세요."
    if error_code == "avatar_source_face_too_small":
        return "얼굴이 너무 작게 보여요. 얼굴이 더 잘 보이는 사진을 선택해주세요."
    if error_code == "avatar_source_face_too_blurry":
        return "사진이 흐려 얼굴 특징을 확인하기 어려워요. 선명한 다른 사진을 선택해주세요."
    if error_code == "avatar_source_face_out_of_frame":
        return "얼굴이 사진 안에 충분히 들어오도록 촬영한 다른 사진을 선택해주세요."
    if error_code == "avatar_source_landmarks_unstable":
        return "얼굴 특징을 안정적으로 확인하기 어려워요. 정면에 가까운 다른 사진을 선택해주세요."
    if error_code == "avatar_source_low_light":
        return "사진이 너무 어두워 얼굴을 확인하기 어려워요. 밝은 곳에서 촬영한 사진을 선택해주세요."
    if error_code == "avatar_source_compression_damage":
        return "사진 화질이 많이 손상되어 있어요. 원본에 가까운 다른 사진을 선택해주세요."
    if error_code == "avatar_source_analysis_uncertain":
        return "사진 상태를 확실히 판단하기 어려워요. 선명한 다른 사진을 선택해주세요."
    if error_code == "avatar_background_text_logo_risky":
        return "배경의 글자나 로고가 크게 보여요. 다른 사진을 권장해요."
    if error_code == "avatar_source_no_face":
        return "얼굴이 잘 보이는 사진을 선택해주세요."
    return "아바타를 만들기 어려운 사진이에요. 다른 사진을 선택해주세요."

def _worker_error_code(exc: Exception) -> str:
    if isinstance(exc, AvatarQAReadinessError):
        return exc.error_code
    if isinstance(exc, AzureProviderError):
        return exc.error_code
    message = str(exc).lower()
    if "deadline" in message:
        return "avatar_worker_deadline_exceeded"
    if "cost_kill_switch" in message or "generation_disabled" in message or "gpu_worker_disabled" in message:
        return "avatar_worker_cost_guard_paused"
    if "trait extraction" in message:
        return "avatar_trait_extraction_failed"
    if "trait card" in message or "trait validation" in message:
        return "avatar_trait_validation_failed"
    if "reference preprocess" in message:
        return "avatar_reference_preprocess_failed"
    if "no previewable" in message:
        return "avatar_no_previewable_candidates"
    return "avatar_generation_worker_error"


def _run_qa_runtime_preflight_if_required(
    firestore_client: Any,
    payload: AvatarGenerationPayload,
    *,
    run_mode: str,
    qa_runner: QARunner,
    metrics_hook: Optional[MetricHook],
) -> None:
    """Gate canonical non-local Azure jobs before any provider claim/call.

    Custom QA runners are intentionally exempt for local/unit fixture flows;
    the deployed canonical worker always uses ``run_avatar_candidate_qa``.
    """
    if (
        run_mode != CANONICAL_AZURE_WORKER_MODE
        or is_local_or_dev_environment()
        or qa_runner is not run_avatar_candidate_qa
    ):
        return

    readiness = get_qa_runtime_readiness()
    if readiness.ready:
        return

    error = AvatarQAReadinessError(readiness)
    preflight_document = readiness.to_document()
    _update_job_status(
        firestore_client,
        payload.job_id,
        {
            "status": "failed",
            "errorCode": error.error_code,
            "errorMessage": str(error),
            "retryable": True,
            "queueStatus": "qa_preflight_blocked",
            "qaPreflight": preflight_document,
            "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
            "providerUsage": {
                "provider": "azure",
                "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
                "requestCount": 0,
                "attemptCount": 0,
                "successCount": 0,
                "failureCount": 0,
                "unknownOutcomeCount": 0,
            },
            "processing": {
                "lastErrorCode": error.error_code,
                "lastErrorMessage": str(error),
                "retryable": True,
            },
        },
    )
    _emit_metric(
        metrics_hook,
        "avatar_qa_preflight_blocked",
        {
            "jobId": payload.job_id,
            "uid": payload.uid,
            "errorCode": error.error_code,
            "blockingComponentCount": len(readiness.blocking_components),
        },
    )
    raise error


def _resize_for_trait_extraction(image: Image.Image) -> Image.Image:
    max_edge = _int_env(
        "AVATAR_TRAIT_MAX_IMAGE_EDGE",
        768,
        minimum=256,
        maximum=1536,
    )
    resized = image.copy().convert("RGB")
    resized.thumbnail((max_edge, max_edge), Image.Resampling.BICUBIC)
    return resized


def _trait_adapter_for_env(run_mode: str) -> Florence2TraitExtractionAdapter:
    key = (
        os.environ.get("AVATAR_TRAIT_MODEL_ID", "").strip()
        or "microsoft/Florence-2-large-ft",
        _bool_env_default("AVATAR_TRAIT_DRY_RUN", run_mode == "dry_run"),
        _bool_env_default("AVATAR_TRAIT_LOCAL_FILES_ONLY", True),
        os.environ.get("AVATAR_TRAIT_ATTENTION_IMPLEMENTATION", "eager").strip()
        or "eager",
        os.environ.get("AVATAR_TRAIT_FLORENCE_TASK_PROMPT", "MORE_DETAILED_CAPTION").strip()
        or "MORE_DETAILED_CAPTION",
    )
    adapter = _TRAIT_ADAPTER_CACHE.get(key)
    if adapter is None:
        adapter = Florence2TraitExtractionAdapter(
            model_id=str(key[0]),
            dry_run=bool(key[1]),
            local_files_only=bool(key[2]),
            attn_implementation=str(key[3]),
            task_prompt=str(key[4]),
        )
        _TRAIT_ADAPTER_CACHE[key] = adapter
    return adapter


def _extract_trait_card_for_generation(
    image: Image.Image,
    *,
    run_mode: str,
    avatar_presentation_gender: str = "unknown",
    broad_trait_hints: Optional[Mapping[str, Any]] = None,
) -> tuple[Optional[TraitCardValidationResult], Optional[PromptAvatarTraitCard]]:
    if not _trait_extraction_enabled(run_mode):
        return None, None

    adapter = _trait_adapter_for_env(run_mode)
    validation = adapter.extract_traits(
        image=_resize_for_trait_extraction(image),
        avatar_presentation_gender=avatar_presentation_gender,
    )
    validation = merge_trait_card_with_broad_hints(validation, broad_trait_hints)
    if _trait_require_validated() and not validation.privacy_safe:
        raise AvatarGenerationError("avatar trait card did not pass privacy validation.")
    prompt_card = PromptAvatarTraitCard(
        **validation.trait_card.to_prompt_builder_dict()
    )
    return validation, prompt_card


def _source_eyewear_needs_candidate_check(
    source_trait_card: Mapping[str, Any],
) -> bool:
    present = source_trait_card.get("eyewear_present")
    confidence = str(source_trait_card.get("eyewear_confidence") or "").strip().lower()
    return present in {True, False} and confidence in {"medium", "high"}


def _extract_candidate_trait_card_for_qa(
    artifact: CandidateArtifact,
    *,
    run_mode: str,
    avatar_presentation_gender: str,
    source_trait_card: Mapping[str, Any],
) -> Dict[str, Any]:
    if not _candidate_trait_qa_enabled(run_mode):
        return {}
    if not _source_eyewear_needs_candidate_check(source_trait_card):
        return {}
    try:
        with Image.open(io.BytesIO(artifact.image_bytes)) as image:
            adapter = _trait_adapter_for_env(run_mode)
            validation = adapter.extract_traits(
                image=_resize_for_trait_extraction(image.convert("RGB")),
                avatar_presentation_gender=avatar_presentation_gender,
            )
        return PromptAvatarTraitCard(
            **validation.trait_card.to_prompt_builder_dict()
        ).to_prompt_dict()
    except Exception as exc:
        logger.warning(
            "Candidate trait QA extraction failed: %s: %s",
            type(exc).__name__,
            str(exc).splitlines()[0][:160],
        )
        return {}


def _trait_extraction_input_metadata(
    reference_preprocess_doc: Mapping[str, Any],
    *,
    using_privacy_reference: bool,
    using_analysis_reference: bool = False,
) -> Dict[str, Any]:
    neutralization = reference_preprocess_doc.get("backgroundNeutralization")
    if not isinstance(neutralization, Mapping):
        neutralization = {}
    return {
        "input": (
            "analysis_reference_image"
            if using_analysis_reference
            else ("privacy_processed_reference" if using_privacy_reference else "source_image")
        ),
        "primaryCropApplied": bool(reference_preprocess_doc.get("primaryCropApplied"))
        if using_privacy_reference or using_analysis_reference
        else False,
        "cropType": reference_preprocess_doc.get("cropType")
        if using_privacy_reference or using_analysis_reference
        else None,
        "backgroundNeutralized": bool(reference_preprocess_doc.get("backgroundNeutralized"))
        if using_privacy_reference or using_analysis_reference
        else False,
        "backgroundRiskNotes": {
            "secondaryFaceCount": neutralization.get("secondaryFaceCount", 0),
            "secondaryFaceAction": neutralization.get("secondaryFaceAction", "none"),
            "textLogoRiskDetected": bool(neutralization.get("textLogoRiskDetected")),
            "textLogoAction": neutralization.get("textLogoAction", "none"),
         },
    }


def _candidate_qa_metadata(
    payload: AvatarGenerationPayload,
    artifact: CandidateArtifact,
    *,
    run_mode: Optional[str] = None,
    source_analysis_doc: Mapping[str, Any],
    reference_preprocess_doc: Mapping[str, Any],
    source_trait_card: Optional[Mapping[str, Any]] = None,
    candidate_trait_card: Optional[Mapping[str, Any]] = None,
    analysis_reference_image: Optional[Image.Image] = None,
    source_image: Optional[Image.Image] = None,
    candidate_image: Optional[Image.Image] = None,
) -> Dict[str, Any]:
    effective_run_mode = (
        CANONICAL_AZURE_WORKER_MODE
        if payload.model_id == AZURE_GPT_IMAGE_2_MODEL_ID
        else str(run_mode or "").strip().lower() or "unknown"
    )
    metadata = {
        "jobId": payload.job_id,
        "uid": payload.uid,
        "candidateId": artifact.candidate_id,
        "modelId": payload.model_id,
        "seed": artifact.seed,
        "redactedSourceRef": redact_gcs_ref(payload.source_photo_refs[0]),
    }
    if payload.model_id == AZURE_GPT_IMAGE_2_MODEL_ID:
        metadata.update(
            {
                "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
                "sourceInputMode": "storage_normalized_original_direct",
                "uploadNormalization": "existing_avatar_media_ingestion",
                "preGenerationTransform": "none",
                "qaInputMode": "storage_source_vs_generated_candidate",
                "compareSourceVisualRisk": True,
                "legacyTraitExtraction": False,
                "legacyReferencePreprocessing": False,
                "legacyFlux": False,
                "pipelineMode": effective_run_mode,
                "traitQaMode": "disabled_by_pipeline",
                "traitQaAuthority": "server",
                "uniqueMarkQaMode": "disabled_by_pipeline",
                "uniqueMarkQaAuthority": "server",
                "qaContract": QA_INPUT_CONTRACT_VERSION,
                "qaChecks": {
                    "postGeneration": [
                        "image_decode",
                        "adult_safety",
                        "privacy_identifiability",
                        "brand_and_watermark",
                        "crop_consistency",
                        "secondary_face_leakage",
                    ],
                    "legacyReferenceChecks": [],
                },
            }
        )
        if source_image is not None:
            metadata["_source_image"] = source_image
        if candidate_image is not None:
            metadata["_candidate_image"] = candidate_image
    else:
        metadata.update(
            {
                "sourceAnalysis": dict(source_analysis_doc or {}),
                "referencePreprocess": dict(reference_preprocess_doc or {}),
                "sourceTraitCard": dict(source_trait_card or {}),
                "pipelineMode": effective_run_mode,
                "traitQaMode": (
                    "enabled"
                    if effective_run_mode in {"flux", "dry_run"}
                    else "unknown"
                ),
                "traitQaAuthority": "server",
                "uniqueMarkQaMode": "unknown",
                "uniqueMarkQaAuthority": "server",
            }
        )
    if analysis_reference_image is not None and reference_preprocess_doc:
        metadata["_source_image"] = analysis_reference_image
        metadata["_analysis_reference_image"] = analysis_reference_image
    if candidate_trait_card:
        metadata["candidateTraitCard"] = dict(candidate_trait_card)
        metadata["candidateTraitExtraction"] = {
            "status": "available",
            "input": "generated_candidate",
         }
    elif source_trait_card:
        metadata["candidateTraitExtraction"] = {
            "status": "unavailable",
            "input": "generated_candidate",
         }
    return metadata


def _azure_provenance_document() -> Dict[str, Any]:
    return {
        "provider": "azure",
        "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
        "modelFamily": AZURE_GPT_IMAGE_2_VERSION,
        "promptVersion": AVATAR_GENERAL_PROMPT_VERSION,
        "sourceInputMode": "storage_normalized_original_direct",
        "uploadNormalization": "existing_avatar_media_ingestion",
        "preGenerationTransform": "none",
        "legacyTraitExtraction": False,
        "legacyReferencePreprocessing": False,
        "legacyFlux": False,
        "pipelineMode": CANONICAL_AZURE_WORKER_MODE,
        "traitQaMode": "disabled_by_pipeline",
        "traitQaAuthority": "server",
        "uniqueMarkQaMode": "disabled_by_pipeline",
        "uniqueMarkQaAuthority": "server",
    }


def _prepare_reference_preprocess_for_generation(
    source_image: Image.Image,
    *,
    source_analysis: Any = None,
    visual_risk_regions: Sequence[Any] = (),
    run_mode: str,
) -> AvatarQualityContext:
    if run_mode != "flux":
        return AvatarQualityContext(
            generation_image=None,
            analysis_image=source_image.convert("RGB"),
            metadata={},
        )
    if not _reference_privacy_preprocess_enabled():
        validate_reference_preprocess_enabled_for_environment(
            preprocess_enabled=False,
        )
        image = source_image.convert("RGB")
        return AvatarQualityContext(
            generation_image=image,
            analysis_image=image,
            metadata={"enabled": False},
        )
    pipeline_analysis_reference = getattr(
        source_analysis, "analysis_reference_image", None
    )
    result = preprocess_reference_image(
        source_image,
        source_analysis=source_analysis,
        visual_risk_regions=visual_risk_regions,
        config=_reference_preprocess_config_from_env(),
    )
    analysis_image = result.analysis_image
    if pipeline_analysis_reference is not None:
        # Prefer small-face pipeline analysis reference (crop + neutralized).
        analysis_image = pipeline_analysis_reference.convert("RGB")
    return AvatarQualityContext(
        generation_image=result.image,
        analysis_image=analysis_image,
        foreground_mask=result.foreground_mask,
        face_hints=result.face_hints,
        metadata={
            **result.metadata,
            "smallFaceAnalysisReferenceUsed": pipeline_analysis_reference is not None,
         },
    )


def _candidate_summary(
    artifact: CandidateArtifact,
    *,
    status: str,
    qa_doc: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "candidateId": artifact.candidate_id,
        "status": status,
        "qa": dict(qa_doc),
        "seed": artifact.seed,
    }


def _apply_preview_selection(
    firestore_client: Any,
    candidate_summaries: List[Dict[str, Any]],
    *,
    policy: AdaptiveGenerationPolicy,
) -> tuple[int, int, int, Dict[str, Any]]:
    rerank = rerank_preview_candidates(candidate_summaries, policy=policy)
    selected_ids = set(rerank.selected_candidate_ids)
    allow_preview_selection = _has_required_preview_count(len(selected_ids), policy)
    preview_ready = 0
    rejected = 0
    needs_review = 0

    for summary in candidate_summaries:
        candidate_id = str(summary.get("candidateId") or "")
        rerank_doc = rerank.metadata_by_candidate_id.get(candidate_id, {})
        qa_doc = dict(summary.get("qa") or {})
        status = str(summary.get("status") or "rejected")

        candidate_for_gate = {
            "candidateId": candidate_id,
            "status": status,
            "qa": qa_doc,
            "rerank": rerank_doc,
         }
        if (
            candidate_id in selected_ids
            and allow_preview_selection
            and is_preview_eligible(candidate_for_gate)
        ):
            status = "preview_ready"
            qa_doc["previewAllowed"] = True
            qa_doc["selectedForPreview"] = True
            preview_ready += 1
        elif candidate_id in selected_ids:
            status = "needs_review"
            qa_doc["previewAllowed"] = False
            qa_doc["selectedForPreview"] = False
            qa_doc["previewShortfall"] = _preview_shortfall(len(selected_ids), policy)
            needs_review += 1
        elif status == "preview_ready":
            status = "not_selected"
            qa_doc["previewAllowed"] = False
            qa_doc["selectedForPreview"] = False
        elif status in {"needs_review", "soft_pass"}:
            needs_review += 1
        else:
            rejected += 1

        summary["status"] = status
        summary["qa"] = qa_doc
        _set_doc(
            _doc_ref(firestore_client, "avatarCandidates", candidate_id),
            {
                "qa": qa_doc,
                "rerank": rerank_doc,
                "status": status,
                "updatedAt": SERVER_TIMESTAMP,
             },
            merge=True,
        )

    return preview_ready, rejected, needs_review, rerank.to_dict()


def _has_required_preview_count(
    preview_ready_count: int,
    policy: AdaptiveGenerationPolicy,
) -> bool:
    min_preview_count = max(1, int(policy.min_preview_candidate_count))
    if preview_ready_count < min_preview_count:
        return False
    if not policy.require_four_preview:
        return True
    return preview_ready_count >= max(0, int(policy.preview_candidate_count))


def _preview_shortfall(
    preview_ready_count: int,
    policy: AdaptiveGenerationPolicy,
) -> int:
    required = (
        int(policy.preview_candidate_count)
        if policy.require_four_preview
        else max(1, int(policy.min_preview_candidate_count))
    )
    return max(0, required - int(preview_ready_count))


def _no_previewable_reason_code(candidate_summaries: Sequence[Mapping[str, Any]]) -> str:
    saw_needs_review = False
    saw_too_identifiable = False
    saw_background_text_logo = False
    for summary in candidate_summaries:
        qa_doc = summary.get("qa")
        if not isinstance(qa_doc, Mapping):
            continue
        reasons = qa_doc.get("rejectReasons")
        if isinstance(reasons, Sequence) and not isinstance(reasons, (str, bytes)):
            if any(str(reason) == "too_identifiable" for reason in reasons):
                saw_too_identifiable = True
            if any(
                str(reason) in {"logo_text_watermark", "background_leakage"}
                for reason in reasons
            ):
                saw_background_text_logo = True
        if (
            qa_doc.get("textLogoWatermarkRisk") == "high"
            or qa_doc.get("logoTextWatermarkRisk") == "high"
            or qa_doc.get("backgroundLeakageRisk") == "high"
        ):
            saw_background_text_logo = True
        if qa_doc.get("requiresHumanReview") is True:
            saw_needs_review = True
    if saw_too_identifiable:
        return "too_identifiable_candidates"
    if saw_background_text_logo:
        return "avatar_background_text_logo_risky"
    if saw_needs_review:
        return "qa_requires_review"
    return "no_safe_avatar_candidates"


def _default_firestore_client(project: Optional[str] = None, database: Optional[str] = None) -> Any:
    if firestore is None:
        raise AvatarGenerationError("google-cloud-firestore is required for worker execution.")
    kwargs: Dict[str, Any] = {}
    if project:
        kwargs["project"] = project
    if database:
        kwargs["database"] = database
    return firestore.Client(**kwargs)


def _default_storage_client(project: Optional[str] = None) -> Any:
    if storage is None:
        raise AvatarGenerationError("google-cloud-storage is required for worker execution.")
    return storage.Client(project=project)


def process_avatar_generation_payload(
    raw_payload: Mapping[str, Any],
    *,
    firestore_client: Any = None,
    storage_client: Any = None,
    qa_runner: QARunner = run_avatar_candidate_qa,
    mode: Optional[str] = None,
    fixture_output_dir: Optional[Path] = None,
    firestore_project: Optional[str] = None,
    firestore_database: Optional[str] = None,
    metrics_hook: Optional[MetricHook] = None,
    deadline: Optional[ClaimDeadline] = None,
    source_visual_risk_adapter: Any = None,
) -> AvatarGenerationResult:
    job_started_at = time.perf_counter()
    validate_bridge_runtime_config(firestore_project)
    resolved_firestore_project = resolve_firestore_project(firestore_project)
    worker_deadline = AvatarWorkerDeadline.from_env().capped_by_claim_deadline(deadline)
    seconds_by_stage: Dict[str, float] = {
        "loadSource": 0.0,
        "generate": 0.0,
        "uploadAndQa": 0.0,
        "model_load_seconds": 0.0,
        "source_load_seconds": 0.0,
        "face_detect_seconds": 0.0,
        "trait_extract_seconds": 0.0,
        "preprocess_seconds": 0.0,
        "sam_seconds": 0.0,
        "generation_seconds": 0.0,
        "candidate_upload_seconds": 0.0,
        "upload_seconds": 0.0,
        "qa_seconds": 0.0,
        "rerank_seconds": 0.0,
        "total": 0.0,
        "total_seconds": 0.0,
        "total_worker_seconds": 0.0,
    }
    provider_usage_doc: Dict[str, Any] = {
        "provider": "azure",
        "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
        "requestCount": 0,
        "attemptCount": 0,
        "successCount": 0,
        "failureCount": 0,
        "unknownOutcomeCount": 0,
    }
    payload = parse_avatar_generation_payload(raw_payload)
    run_mode = resolve_worker_mode(mode)
    if run_mode != CANONICAL_AZURE_WORKER_MODE:
        provider_usage_doc = {}

    fs = firestore_client or _default_firestore_client(resolved_firestore_project, firestore_database)
    st = storage_client or _default_storage_client(resolved_firestore_project)

    job_doc = _load_job_doc(fs, payload.job_id)
    _assert_job_can_run(job_doc, payload)
    if run_mode == CANONICAL_AZURE_WORKER_MODE and _azure_generation_claim_active(job_doc):
        return _result_for_active_azure_generation(payload, job_doc or {})
    _run_qa_runtime_preflight_if_required(
        fs,
        payload,
        run_mode=run_mode,
        qa_runner=qa_runner,
        metrics_hook=metrics_hook,
    )
    initial_admission = _evaluate_worker_admission(
        fs,
        phase="initial",
        existing_candidate_count=0,
        retry_attempt=_processing_attempt_from_job_doc(job_doc),
        remaining_deadline_seconds=_worker_admission_remaining_seconds(worker_deadline),
    )
    if not initial_admission.allowed:
        denied_result = _finalize_admission_denied(fs, payload, initial_admission)
        if initial_admission.reason == "deadline_insufficient":
            raise AvatarGenerationError(
                "avatar_worker_deadline_exceeded at initial_admission."
            )
        return denied_result
    if initial_admission.candidate_count < payload.candidate_count:
        payload = replace(payload, candidate_count=initial_admission.candidate_count)
    avatar_presentation_gender = _avatar_presentation_gender_for_job(
        payload,
        job_doc,
    )
    private_doc = _load_private_media_doc(fs, payload.uid)
    _assert_avatar_generation_consent(private_doc)
    _ensure_source_refs_match_private_media(private_doc, payload)
    source_refs = validate_private_source_refs(payload.source_photo_refs)
    current_mismatch = _current_avatar_contract_mismatch(
        job_doc,
        private_doc,
        payload,
        source_refs,
    )
    if current_mismatch:
        return _mark_avatar_job_superseded(fs, payload, current_mismatch)
    if run_mode == CANONICAL_AZURE_WORKER_MODE and not _claim_azure_generation_run(fs, payload):
        latest_job_doc = _load_job_doc(fs, payload.job_id) or job_doc or {}
        return _result_for_active_azure_generation(payload, latest_job_doc)
    _emit_metric(
        metrics_hook,
        "avatar_job_started",
        {
            "jobId": payload.job_id,
            "uid": payload.uid,
            "mode": run_mode,
            "candidateCount": payload.candidate_count,
         },
    )

    _update_job_status(
        fs,
        payload.job_id,
        {
            "status": "running",
            "startedAt": SERVER_TIMESTAMP,
            "workerMode": run_mode,
            "admissionDecision": initial_admission.to_dict(),
        },
    )

    try:
        worker_deadline.ensure_can_continue("load_source", min_remaining_seconds=10)
        stage_started_at = time.perf_counter()
        source_image_bytes, source_content_type = load_source_image_bytes_from_gcs(
            st,
            source_refs[0],
        )
        source_image = image_from_stored_source_bytes(source_image_bytes)
        source_selection_version = _selection_version(
            (job_doc or {}).get("avatarSourceSelectionVersion")
        )
        if source_selection_version is None:
            source_selection_version = _selection_version(
                (private_doc or {}).get("avatarSourceSelectionVersion")
            )
        source_reference_audit: Dict[str, Any] = {
            "jobId": payload.job_id,
            "sourcePhotoId": payload.source_photo_ids[0] if payload.source_photo_ids else "",
            "sourceSelectionVersion": source_selection_version,
        }
        elapsed = _elapsed_seconds(stage_started_at)
        seconds_by_stage["loadSource"] += elapsed
        seconds_by_stage["source_load_seconds"] += elapsed
        _update_job_status(
            fs,
            payload.job_id,
            {"sourceReferenceAudit": source_reference_audit},
        )

        source_analysis = None
        source_visual_risk = None
        source_analysis_doc: Dict[str, Any] = {}
        if _source_analysis_enabled(run_mode):
            worker_deadline.ensure_can_continue("source_analysis", min_remaining_seconds=10)
            stage_started_at = time.perf_counter()
            source_analysis = analyze_avatar_source_image(
                source_image,
                source_ref=payload.source_photo_refs[0],
            )
            seconds_by_stage["face_detect_seconds"] += _elapsed_seconds(stage_started_at)
            source_analysis_doc = source_analysis.to_document()
            source_visual_risk = _analyze_source_visual_risk(
                source_image,
                source_analysis=source_analysis,
                run_mode=run_mode,
                source_visual_risk_adapter=source_visual_risk_adapter,
            )
            if source_visual_risk is not None:
                source_analysis_doc["visualRisk"] = source_visual_risk.to_document()
            _update_job_status(
                fs,
                payload.job_id,
                {"sourceAnalysis": source_analysis_doc},
            )
            if _is_critical_visual_risk_unavailable(source_visual_risk) and is_production_environment():
                return _finalize_needs_review_without_generation(
                    fs,
                    payload,
                    error_code="avatar_source_visual_risk_model_unavailable",
                    error_message="Source visual risk analysis is unavailable for production avatar generation.",
                    seconds_by_stage=seconds_by_stage,
                    job_started_at=job_started_at,
                    extra_update={"sourceAnalysis": source_analysis_doc},
                )
            if source_analysis.hard_reject:
                final_status = "failed"
                final_update = {
                    "status": final_status,
                    "candidateIds": [],
                    "sourceAnalysis": source_analysis_doc,
                    "errorCode": _source_reject_error_code(source_analysis_doc),
                    "errorMessage": _source_reject_error_message(source_analysis_doc),
                 }
                seconds_by_stage["total"] = _elapsed_seconds(job_started_at)
                seconds_by_stage["total_seconds"] = seconds_by_stage["total"]
                seconds_by_stage["total_worker_seconds"] = seconds_by_stage["total"]
                final_update.update(
                    _cost_document_for_job(
                        duration_seconds=seconds_by_stage["total"],
                        candidate_count=0,
                        seconds_by_stage=seconds_by_stage,
                        generation_backend=(
                            AZURE_GPT_IMAGE_2_MODEL_ID
                            if run_mode == CANONICAL_AZURE_WORKER_MODE
                            else "local_cloud_run_flux"
                        ),
                        provider_usage_document=provider_usage_doc,
                    )
                )
                _update_job_status(fs, payload.job_id, final_update)
                return AvatarGenerationResult(
                    job_id=payload.job_id,
                    uid=payload.uid,
                    status=final_status,
                    candidate_ids=[],
                    preview_ready_count=0,
                    rejected_count=0,
                    needs_review_count=0,
                )

        if run_mode == CANONICAL_AZURE_WORKER_MODE:
            # The stored normalized JPEG is the generation source. No
            # generation-purpose image derivative is created or persisted.
            quality_context = AvatarQualityContext()
            privacy_reference_image = None
            analysis_reference_image = None
            reference_preprocess_doc: Dict[str, Any] = {}
        else:
            stage_started_at = time.perf_counter()
            quality_context = _prepare_reference_preprocess_for_generation(
                source_image,
                source_analysis=source_analysis,
                visual_risk_regions=getattr(source_visual_risk, "regions", ()),
                run_mode=run_mode,
            )
            privacy_reference_image = quality_context.generation_image
            analysis_reference_image = quality_context.analysis_image or source_image.convert("RGB")
            reference_preprocess_doc = quality_context.persisted_metadata()
            preprocess_elapsed = _elapsed_seconds(stage_started_at)
            seconds_by_stage["preprocess_seconds"] += preprocess_elapsed
            if (
                isinstance(reference_preprocess_doc, Mapping)
                and isinstance(reference_preprocess_doc.get("sam"), Mapping)
                and reference_preprocess_doc["sam"].get("enabled") is True
            ):
                seconds_by_stage["sam_seconds"] += preprocess_elapsed
            if reference_preprocess_doc:
                _update_job_status(
                    fs,
                    payload.job_id,
                    {
                        "referencePreprocess": reference_preprocess_doc,
                        "sourceReferenceAudit": source_reference_audit,
                    },
                )

        trait_validation = None
        trait_card_doc: Optional[Dict[str, Any]] = None
        prompt_trait_card = None
        source_trait_card_doc: Dict[str, Any] = {}
        if _trait_extraction_enabled(run_mode):
            try:
                worker_deadline.ensure_can_continue("trait_extraction", min_remaining_seconds=20)
                stage_started_at = time.perf_counter()
                trait_uses_analysis_reference = _trait_input_uses_analysis_reference(run_mode, quality_context)
                trait_uses_privacy_reference = False
                trait_input_image = analysis_reference_image if trait_uses_analysis_reference else source_image
                trait_validation, prompt_trait_card = _extract_trait_card_for_generation(
                    trait_input_image,
                    run_mode=run_mode,
                    avatar_presentation_gender=avatar_presentation_gender,
                    broad_trait_hints=(
                        source_analysis.broad_trait_hints
                        if source_analysis is not None
                        else None
                    ),
                )
                if trait_validation is not None:
                    trait_validation = _merge_region_color_traits(
                        trait_validation,
                        image=analysis_reference_image,
                        quality_context=quality_context,
                        avatar_presentation_gender=avatar_presentation_gender,
                    )
                    prompt_trait_card = PromptAvatarTraitCard(
                        **trait_validation.trait_card.to_prompt_builder_dict()
                    )
                seconds_by_stage["trait_extract_seconds"] += _elapsed_seconds(stage_started_at)
            except Exception as exc:
                detail = str(exc).splitlines()[0][:200]
                logger.warning(
                    "Avatar trait extraction failed: %s: %s",
                    type(exc).__name__,
                    detail,
                )
                if is_production_environment():
                    return _finalize_needs_review_without_generation(
                        fs,
                        payload,
                        error_code="avatar_trait_extraction_failed",
                        error_message="Avatar trait extraction is unavailable for production avatar generation.",
                        seconds_by_stage=seconds_by_stage,
                        job_started_at=job_started_at,
                        extra_update={
                            "sourceAnalysis": source_analysis_doc,
                            "referencePreprocess": reference_preprocess_doc,
                            "traitExtraction": {"status": "critical_unavailable"},
                         },
                    )
                raise AvatarGenerationError("avatar trait extraction failed.") from exc
            trait_card_doc = (
                trait_validation.to_dict()
                if trait_validation is not None
                else None
            )
            source_trait_card_doc = (
                prompt_trait_card.to_prompt_dict()
                if prompt_trait_card is not None
                else {}
            )
            _update_job_status(
                fs,
                payload.job_id,
                {
                    "traitCard": trait_card_doc,
                    "traitExtraction": _trait_extraction_input_metadata(
                        reference_preprocess_doc,
                        using_privacy_reference=trait_uses_privacy_reference,
                        using_analysis_reference=trait_uses_analysis_reference,
                    ),
                    "sourceReferenceAudit": source_reference_audit,
                },
            )

        worker_deadline.ensure_can_continue("generate_initial", min_remaining_seconds=30)
        if run_mode == CANONICAL_AZURE_WORKER_MODE:
            _update_job_status(
                fs,
                payload.job_id,
                {
                    "status": "provider_inflight",
                    "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
                    "provenance": _azure_provenance_document(),
                },
            )
        stage_started_at = time.perf_counter()
        policy = AdaptiveGenerationPolicy.from_env()
        initial_plan = plan_generation_round(
            [],
            policy=policy,
            budget=_generation_budget(
                worker_deadline,
                generated_count=0,
                max_total_candidates=policy.max_candidate_count,
            ),
        )
        initial_count = min(max(0, int(payload.candidate_count)), initial_plan.candidate_count)
        if initial_count <= 0:
            return _finalize_needs_review_without_generation(
                fs,
                payload,
                error_code="avatar_generation_budget_blocked",
                error_message="Avatar generation budget blocked initial candidate generation.",
                seconds_by_stage=seconds_by_stage,
                job_started_at=job_started_at,
                extra_update={"generationPlan": {"initial": initial_plan.to_dict()}},
            )
        model_load_before = seconds_by_stage["model_load_seconds"]
        artifacts = generate_candidate_artifacts(
            payload,
            source_image,
            mode=run_mode,
            source_analysis=source_analysis,
            trait_card=prompt_trait_card,
            privacy_reference_image=privacy_reference_image,
            reference_preprocess_metadata=reference_preprocess_doc,
            candidate_start_index=0,
            candidate_count=initial_count,
            seconds_by_stage=seconds_by_stage,
            source_image_bytes=source_image_bytes,
            source_content_type=source_content_type,
            deadline_monotonic=worker_deadline.deadline_monotonic(),
            provider_usage_doc=provider_usage_doc,
        )
        elapsed = _elapsed_seconds(stage_started_at)
        model_load_delta = max(0.0, seconds_by_stage["model_load_seconds"] - model_load_before)
        generation_elapsed = round(max(0.0, elapsed - model_load_delta), 3)
        seconds_by_stage["generate"] += generation_elapsed
        seconds_by_stage["generation_seconds"] += generation_elapsed
        _update_job_status(
            fs,
            payload.job_id,
            {
                "status": "generated" if run_mode == CANONICAL_AZURE_WORKER_MODE else "qa_pending",
                "generationBackend": (
                    AZURE_GPT_IMAGE_2_MODEL_ID
                    if run_mode == CANONICAL_AZURE_WORKER_MODE
                    else payload.model_id
                ),
            },
        )
        _update_job_status(fs, payload.job_id, {"status": "qa_pending"})

        candidate_ids: List[str] = []
        candidate_summaries: List[Dict[str, Any]] = []
        shadow_corridor_candidates: List[CorridorCandidate] = []
        generation_rounds: List[Dict[str, Any]] = [
            {
                "reason": "initial",
                "candidateCount": initial_count,
                "startIndex": 0,
                "plan": initial_plan.to_dict(),
             }
        ]
        stage_started_at = time.perf_counter()
        for artifact in artifacts:
            worker_deadline.ensure_can_continue("upload_and_qa", min_remaining_seconds=10)
            upload_started_at = time.perf_counter()
            if fixture_output_dir is not None:
                _write_fixture_file(fixture_output_dir, artifact)
            else:
                _upload_candidate(st, artifact)

            candidate_ref = _doc_ref(fs, "avatarCandidates", artifact.candidate_id)
            _set_doc(candidate_ref, _candidate_doc(payload, artifact, status="qa_pending"), merge=True)
            upload_elapsed = _elapsed_seconds(upload_started_at)
            seconds_by_stage["candidate_upload_seconds"] += upload_elapsed
            seconds_by_stage["upload_seconds"] += upload_elapsed

            qa_started_at = time.perf_counter()
            candidate_trait_card_doc = _extract_candidate_trait_card_for_qa(
                artifact,
                run_mode=run_mode,
                avatar_presentation_gender=avatar_presentation_gender,
                source_trait_card=source_trait_card_doc,
            )
            qa_result = qa_runner(
                payload.source_photo_refs[0],
                artifact.image_ref,
                _candidate_qa_metadata(
                    payload,
                    artifact,
                    run_mode=run_mode,
                    source_analysis_doc=source_analysis_doc,
                    reference_preprocess_doc=reference_preprocess_doc,
                    source_trait_card=source_trait_card_doc,
                    candidate_trait_card=candidate_trait_card_doc,
                    analysis_reference_image=analysis_reference_image,
                    source_image=source_image if run_mode == CANONICAL_AZURE_WORKER_MODE else None,
                    candidate_image=(
                        image_from_stored_source_bytes(artifact.image_bytes)
                        if run_mode == CANONICAL_AZURE_WORKER_MODE
                        else None
                    ),
                ),
            )
            qa_doc = qa_result.to_document()
            shadow_evidence = build_shadow_corridor_evidence(
                active_qa=qa_doc,
                candidate_id=artifact.candidate_id,
                source_trait_validation=trait_card_doc,
            )
            qa_doc = shadow_evidence.qa_document
            shadow_corridor_candidates.append(shadow_evidence.candidate)
            seconds_by_stage["qa_seconds"] += _elapsed_seconds(qa_started_at)
            candidate_status = _candidate_status_from_qa(qa_doc)
            _set_doc(
                candidate_ref,
                {
                    "qa": qa_doc,
                    "status": candidate_status,
                    "updatedAt": SERVER_TIMESTAMP,
                 },
                merge=True,
            )

            candidate_ids.append(artifact.candidate_id)
            candidate_summaries.append(
                _candidate_summary(
                    artifact,
                    status=candidate_status,
                    qa_doc=qa_doc,
                )
            )

        qa_models_unavailable = _qa_critical_models_unavailable(candidate_summaries)
        extra_plan = plan_generation_round(
            candidate_summaries,
            policy=policy,
            budget=_generation_budget(
                worker_deadline,
                generated_count=len(candidate_summaries),
                max_total_candidates=policy.max_candidate_count,
            ),
        )
        extra_admission = _evaluate_worker_admission(
            fs,
            phase="extra",
            existing_candidate_count=len(candidate_summaries),
            retry_attempt=_processing_attempt_from_job_doc(job_doc),
            remaining_deadline_seconds=_worker_admission_remaining_seconds(worker_deadline),
        ) if extra_plan.should_generate else AdmissionDecision(allowed=True, reason="admitted")
        extra_count = min(extra_plan.candidate_count, extra_admission.candidate_count)
        if (
            payload.candidate_count >= policy.min_safe_before_extra
            and extra_plan.should_generate
            and extra_admission.allowed
            and extra_count > 0
            and not qa_models_unavailable
        ):
            worker_deadline.ensure_can_continue("generate_extra", min_remaining_seconds=30)
            stage_generate_extra_started_at = time.perf_counter()
            model_load_before = seconds_by_stage["model_load_seconds"]
            extra_artifacts = generate_candidate_artifacts(
                payload,
                source_image,
                mode=run_mode,
                source_analysis=source_analysis,
                trait_card=prompt_trait_card,
                privacy_reference_image=privacy_reference_image,
                reference_preprocess_metadata=reference_preprocess_doc,
                candidate_start_index=len(candidate_summaries),
                candidate_count=extra_count,
                seconds_by_stage=seconds_by_stage,
                source_image_bytes=source_image_bytes,
                source_content_type=source_content_type,
                deadline_monotonic=worker_deadline.deadline_monotonic(),
                provider_usage_doc=provider_usage_doc,
            )
            elapsed = _elapsed_seconds(stage_generate_extra_started_at)
            model_load_delta = max(0.0, seconds_by_stage["model_load_seconds"] - model_load_before)
            generation_elapsed = round(max(0.0, elapsed - model_load_delta), 3)
            seconds_by_stage["generate"] += generation_elapsed
            seconds_by_stage["generation_seconds"] += generation_elapsed
            generation_rounds.append(
                {
                    "reason": extra_plan.reason,
                    "candidateCount": extra_count,
                    "startIndex": len(candidate_summaries),
                    "plan": extra_plan.to_dict(),
                }
            )

            for artifact in extra_artifacts:
                worker_deadline.ensure_can_continue("upload_and_qa_extra", min_remaining_seconds=10)
                upload_started_at = time.perf_counter()
                if fixture_output_dir is not None:
                    _write_fixture_file(fixture_output_dir, artifact)
                else:
                    _upload_candidate(st, artifact)

                candidate_ref = _doc_ref(fs, "avatarCandidates", artifact.candidate_id)
                _set_doc(candidate_ref, _candidate_doc(payload, artifact, status="qa_pending"), merge=True)
                upload_elapsed = _elapsed_seconds(upload_started_at)
                seconds_by_stage["candidate_upload_seconds"] += upload_elapsed
                seconds_by_stage["upload_seconds"] += upload_elapsed

                qa_started_at = time.perf_counter()
                candidate_trait_card_doc = _extract_candidate_trait_card_for_qa(
                    artifact,
                    run_mode=run_mode,
                    avatar_presentation_gender=avatar_presentation_gender,
                    source_trait_card=source_trait_card_doc,
                )
                qa_result = qa_runner(
                    payload.source_photo_refs[0],
                    artifact.image_ref,
                    _candidate_qa_metadata(
                        payload,
                        artifact,
                        run_mode=run_mode,
                        source_analysis_doc=source_analysis_doc,
                        reference_preprocess_doc=reference_preprocess_doc,
                            source_trait_card=source_trait_card_doc,
                            candidate_trait_card=candidate_trait_card_doc,
                            analysis_reference_image=analysis_reference_image,
                            source_image=source_image if run_mode == CANONICAL_AZURE_WORKER_MODE else None,
                            candidate_image=(
                                image_from_stored_source_bytes(artifact.image_bytes)
                                if run_mode == CANONICAL_AZURE_WORKER_MODE
                                else None
                            ),
                        ),
                )
                qa_doc = qa_result.to_document()
                shadow_evidence = build_shadow_corridor_evidence(
                    active_qa=qa_doc,
                    candidate_id=artifact.candidate_id,
                    source_trait_validation=trait_card_doc,
                )
                qa_doc = shadow_evidence.qa_document
                shadow_corridor_candidates.append(shadow_evidence.candidate)
                seconds_by_stage["qa_seconds"] += _elapsed_seconds(qa_started_at)
                candidate_status = _candidate_status_from_qa(qa_doc)
                _set_doc(
                    candidate_ref,
                    {
                        "qa": qa_doc,
                        "status": candidate_status,
                        "updatedAt": SERVER_TIMESTAMP,
                     },
                    merge=True,
                )

                candidate_ids.append(artifact.candidate_id)
                candidate_summaries.append(
                    _candidate_summary(
                        artifact,
                        status=candidate_status,
                        qa_doc=qa_doc,
                    )
                )

        if (
            payload.candidate_count >= policy.min_safe_before_extra
            and extra_plan.should_generate
            and not extra_admission.allowed
            and not qa_models_unavailable
        ):
            generation_rounds.append(
                _blocked_extra_round(extra_plan, extra_admission, len(candidate_summaries))
            )

        if qa_models_unavailable and extra_plan.should_generate:
            blocked_plan = dict(extra_plan.to_dict())
            blocked_plan["candidateCount"] = 0
            blocked_reasons = list(blocked_plan.get("blockedReasons") or [])
            if "qa_critical_model_unavailable" not in blocked_reasons:
                blocked_reasons.append("qa_critical_model_unavailable")
            blocked_plan["blockedReasons"] = blocked_reasons
            generation_rounds.append(
                {
                    "reason": "extra_blocked",
                    "candidateCount": 0,
                    "startIndex": len(candidate_summaries),
                    "plan": blocked_plan,
                 }
            )
        if (
            qa_models_unavailable
            and not extra_plan.should_generate
            and extra_plan.reason == "extra_suppressed_systemic_unavailable"
        ):
            generation_rounds.append(
                {
                    "reason": extra_plan.reason,
                    "candidateCount": 0,
                    "startIndex": len(candidate_summaries),
                    "plan": extra_plan.to_dict(),
                }
            )
        seconds_by_stage["uploadAndQa"] += _elapsed_seconds(stage_started_at)
        rerank_started_at = time.perf_counter()
        preview_ready, rejected, needs_review, rerank_doc = _apply_preview_selection(
            fs,
            candidate_summaries,
            policy=policy,
        )
        shadow_ranking_doc = build_shadow_ranking_document(
            shadow_corridor_candidates
        )
        seconds_by_stage["rerank_seconds"] += _elapsed_seconds(rerank_started_at)
        selected_preview_candidate_count = len(
            rerank_doc.get("selectedCandidateIds", [])
            if isinstance(rerank_doc.get("selectedCandidateIds"), list)
            else []
        )
        filled_with_soft_pass = any(
            candidate_id in rerank_doc.get("selectedCandidateIds", [])
            and rerank_doc.get("metadataByCandidateId", {})
            .get(candidate_id, {})
            .get("selectionTier")
            == "soft_pass"
            for candidate_id in candidate_ids
        )
        rerank_metadata = rerank_doc.get("metadataByCandidateId", {})
        hard_pass_count = sum(
            1
            for metadata in rerank_metadata.values()
            if isinstance(metadata, Mapping)
            and metadata.get("selectionTier") == "hard_pass"
        )
        soft_pass_count = sum(
            1
            for metadata in rerank_metadata.values()
            if isinstance(metadata, Mapping)
            and metadata.get("selectionTier") == "soft_pass"
        )
        generation_plan = {
            "initialCount": initial_count,
            "extraCount": sum(
                int(round_doc.get("candidateCount") or 0)
                for round_doc in generation_rounds[1:]
            ),
            "totalGenerated": len(candidate_ids),
            "safePassCount": hard_pass_count + soft_pass_count,
            "hardPassCount": hard_pass_count,
            "softPassCount": soft_pass_count,
            "previewCount": preview_ready,
            "filledWithSoftPass": filled_with_soft_pass,
            "qwenFallbackUsed": False,
            "rounds": generation_rounds,
            "policy": {
                "previewCount": policy.preview_candidate_count,
                "minPreviewCount": policy.min_preview_candidate_count,
                "requireFourPreview": policy.require_four_preview,
                "minSafeBeforeExtra": policy.min_safe_before_extra,
                "fillWithSoftPass": policy.soft_pass_fill_enabled,
                "fillHardReject": policy.hard_reject_fill_enabled,
                "fillWithNeedsReviewLowRisk": policy.needs_review_low_risk_enabled,
             },
            "previewShortfall": _preview_shortfall(
                selected_preview_candidate_count
                if rerank_doc.get("status") == "insufficient_preview_candidates"
                else preview_ready,
                policy,
            ),
         }
        if _has_required_preview_count(preview_ready, policy):
            final_status = "preview_ready"
            final_update = {
                "status": final_status,
                "previewReadyAt": SERVER_TIMESTAMP,
                "candidateIds": candidate_ids,
                "previewReadyCandidateCount": preview_ready,
                "errorCode": "",
                "errorMessage": "",
                "generationPlan": generation_plan,
                "previewRerank": rerank_doc,
             }
        elif preview_ready > 0 or needs_review > 0:
            rerank_status = str(rerank_doc.get("status") or "")
            if rerank_status == "no_previewable":
                final_status = "no_previewable_candidates"
            else:
                final_status = "needs_review"
            error_code = (
                "requires_more_preview_candidates"
                if rerank_status == "insufficient_preview_candidates"
                else _no_previewable_reason_code(candidate_summaries)
            )
            final_update = {
                "status": final_status,
                "candidateIds": candidate_ids,
                "errorCode": error_code,
                "errorMessage": "No avatar candidates are safe for preview yet.",
                "generationPlan": generation_plan,
                "previewRerank": rerank_doc,
             }
        else:
            final_status = "no_previewable_candidates"
            final_update = {
                "status": final_status,
                "candidateIds": candidate_ids,
                "errorCode": _no_previewable_reason_code(candidate_summaries),
                "errorMessage": "All generated avatar candidates were rejected by QA.",
                "generationPlan": generation_plan,
                "previewRerank": rerank_doc,
             }
        final_update["fidelityCorridorShadowRanking"] = shadow_ranking_doc
        seconds_by_stage["total"] = _elapsed_seconds(job_started_at)
        seconds_by_stage["total_seconds"] = seconds_by_stage["total"]
        seconds_by_stage["total_worker_seconds"] = seconds_by_stage["total"]
        final_update.update(
            _cost_document_for_job(
                duration_seconds=seconds_by_stage["total"],
                candidate_count=len(candidate_ids),
                seconds_by_stage=seconds_by_stage,
                generation_backend=(
                    AZURE_GPT_IMAGE_2_MODEL_ID
                    if run_mode == CANONICAL_AZURE_WORKER_MODE
                    else "local_cloud_run_flux"
                ),
                provider_usage_document=provider_usage_doc,
            )
        )
        latest_job_doc = _load_job_doc(fs, payload.job_id)
        latest_private_doc = _load_private_media_doc(fs, payload.uid)
        latest_mismatch = _current_avatar_contract_mismatch(
            latest_job_doc,
            latest_private_doc,
            payload,
            source_refs,
        )
        if latest_mismatch:
            _mark_candidates_superseded(fs, candidate_ids)
            return _mark_avatar_job_superseded(fs, payload, latest_mismatch)
        persisted_status = _update_job_status(fs, payload.job_id, final_update)
        if persisted_status in TERMINAL_JOB_STATUSES and persisted_status != final_status:
            final_status = persisted_status
        _emit_metric(
            metrics_hook,
            "avatar_job_completed",
            {
                "jobId": payload.job_id,
                "uid": payload.uid,
                "status": final_status,
                "candidateCount": len(candidate_ids),
                "previewReadyCount": preview_ready,
                "needsReviewCount": needs_review,
                "rejectedCount": rejected,
             },
        )
        return AvatarGenerationResult(
            job_id=payload.job_id,
            uid=payload.uid,
            status=final_status,
            candidate_ids=candidate_ids,
            preview_ready_count=preview_ready,
            rejected_count=rejected,
            needs_review_count=needs_review,
        )
    except Exception as exc:
        _emit_metric(
            metrics_hook,
            "avatar_job_failed",
            {
                "jobId": payload.job_id,
                "uid": payload.uid,
                "errorType": exc.__class__.__name__,
             },
        )
        is_unknown_provider_outcome = isinstance(exc, AzureUnknownOutcomeError)
        error_update: Dict[str, Any] = {
            "status": "needs_review" if is_unknown_provider_outcome else "failed",
            "errorCode": _worker_error_code(exc),
            "errorMessage": redact_error_message(exc),
        }
        if isinstance(exc, AzureProviderError):
            error_update["providerUsage"] = dict(provider_usage_doc)
            error_update["retryable"] = bool(exc.retryable and not exc.unknown_outcome)
            error_update["generationBackend"] = AZURE_GPT_IMAGE_2_MODEL_ID
        if run_mode == CANONICAL_AZURE_WORKER_MODE:
            error_update["generationClaim"] = {
                "state": "active" if is_unknown_provider_outcome else "failed",
                "backend": AZURE_GPT_IMAGE_2_MODEL_ID,
                "idempotencyKey": payload.idempotency_key,
                "lastErrorCode": _worker_error_code(exc),
            }
        _update_job_status(fs, payload.job_id, error_update)
        if isinstance(exc, AvatarGenerationError):
            raise
        raise AvatarGenerationError("Avatar generation worker failed.") from exc


def _emit_metric(metrics_hook: Optional[MetricHook], name: str, payload: Mapping[str, Any]) -> None:
    if metrics_hook is not None:
        metrics_hook(name, dict(payload))


def _failure_job_result(job_id: str, error: Exception) -> Dict[str, Any]:
    return {
        "jobId": job_id,
        "status": "failed",
        "error": redact_error_message(error),
        "errorType": error.__class__.__name__,
    }


def _payload_with_source_refs_from_job_doc(
    firestore_client: Any,
    payload: Mapping[str, Any],
) -> Dict[str, Any]:
    enriched = dict(payload)
    if enriched.get("sourcePhotoRefs"):
        return enriched
    job_id = str(enriched.get("jobId") or "").strip()
    if not job_id:
        return enriched
    job_doc = _load_job_doc(firestore_client, job_id) or {}
    source_refs = job_doc.get("sourcePhotoRefs")
    if isinstance(source_refs, Sequence) and not isinstance(source_refs, str):
        enriched["sourcePhotoRefs"] = [str(value) for value in source_refs if str(value).strip()]
    source_photo_ids = job_doc.get("sourcePhotoIds")
    if not enriched.get("sourcePhotoIds") and isinstance(source_photo_ids, Sequence) and not isinstance(source_photo_ids, str):
        enriched["sourcePhotoIds"] = [str(value) for value in source_photo_ids if str(value).strip()]
    return enriched


def _safe_job_id(value: Any) -> str:
    job_id = str(value or "").strip()
    if not re.match(r"^[A-Za-z0-9_-]+$", job_id):
        raise AvatarGenerationError("avatar batch jobIds must contain safe job ids.")
    return job_id


def _optional_positive_int(value: Any, field_name: str) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise AvatarGenerationError(f"{field_name} must be a positive integer.") from exc
    if parsed < 1:
        raise AvatarGenerationError(f"{field_name} must be a positive integer.")
    return parsed


def _job_payload_from_firestore(firestore_client: Any, job_id: str) -> Dict[str, Any]:
    job_doc = _load_job_doc(firestore_client, job_id)
    if not job_doc:
        raise AvatarGenerationError("avatarJobs document was not found.")
    payload = dict(job_doc)
    payload["jobId"] = str(payload.get("jobId") or job_id)
    payload.setdefault("schemaVersion", "avatar_job_v1")
    payload.setdefault("jobType", "avatar_generation")
    return payload


def _resolve_batch_payload(raw_payload: Mapping[str, Any], firestore_client: Any) -> ResolvedBatchPayload:
    payload = decode_task_payload(raw_payload)
    if payload.get("schemaVersion") == "avatar_job_v1":
        if payload.get("jobType") != "avatar_generation":
            raise AvatarGenerationError("Unsupported avatar jobType.")
        return ResolvedBatchPayload(jobs=[dict(payload)], batch_id="", deadline_seconds=None)
    if payload.get("schemaVersion") != "avatar_batch_job_v1":
        raise AvatarGenerationError("Unsupported avatar batch schemaVersion.")

    if payload.get("jobType") != "avatar_generation_batch":
        raise AvatarGenerationError("Unsupported avatar batch jobType.")

    batch_id = str(payload.get("batchId") or "").strip()
    max_jobs = _optional_positive_int(payload.get("maxJobs"), "maxJobs")
    deadline_seconds = _optional_positive_int(payload.get("deadlineSeconds"), "deadlineSeconds")

    job_ids = payload.get("jobIds")
    if isinstance(job_ids, Sequence) and not isinstance(job_ids, str):
        safe_job_ids = [_safe_job_id(value) for value in job_ids if str(value or "").strip()]
        if max_jobs is not None:
            safe_job_ids = safe_job_ids[:max_jobs]
        return ResolvedBatchPayload(
            jobs=[_job_payload_from_firestore(firestore_client, job_id) for job_id in safe_job_ids],
            batch_id=batch_id,
            deadline_seconds=deadline_seconds,
        )

    jobs = payload.get("jobs")
    if isinstance(jobs, str) or not isinstance(jobs, Sequence):
        raise AvatarGenerationError("avatar_batch_job_v1 requires jobIds or a jobs array.")
    resolved_jobs = [dict(job) for job in jobs if isinstance(job, Mapping)]
    if max_jobs is not None:
        resolved_jobs = resolved_jobs[:max_jobs]
    return ResolvedBatchPayload(jobs=resolved_jobs, batch_id=batch_id, deadline_seconds=deadline_seconds)


def process_avatar_generation_batch_payload(
    raw_payload: Mapping[str, Any],
    *,
    firestore_client: Any = None,
    storage_client: Any = None,
    qa_runner: QARunner = run_avatar_candidate_qa,
    mode: Optional[str] = None,
    fixture_output_dir: Optional[Path] = None,
    firestore_project: Optional[str] = None,
    firestore_database: Optional[str] = None,
    metrics_hook: Optional[MetricHook] = None,
    continue_on_error: bool = True,
) -> AvatarBatchRunResult:
    batch_started_at = time.perf_counter()
    validate_bridge_runtime_config(firestore_project)
    resolved_firestore_project = resolve_firestore_project(firestore_project)
    fs = firestore_client or _default_firestore_client(resolved_firestore_project, firestore_database)
    st = storage_client or _default_storage_client(resolved_firestore_project)
    resolved = _resolve_batch_payload(raw_payload, fs)
    jobs = resolved.jobs
    deadline = (
        ClaimDeadline.from_timeout(resolved.deadline_seconds, safety_seconds=0)
        if resolved.deadline_seconds is not None
        else _deadline_from_env(AvatarJobLeaseConfig.from_env())
    )
    results: List[Dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    completed_job_ids: set[str] = set()
    cost_jobs: List[Dict[str, Any]] = []

    for job in jobs:
        if deadline is not None and deadline.should_stop():
            break
        job_id = str(job.get("jobId") or "")
        try:
            result = process_avatar_generation_payload(
                _payload_with_source_refs_from_job_doc(fs, job),
                firestore_client=fs,
                storage_client=st,
                qa_runner=qa_runner,
                mode=mode,
                fixture_output_dir=fixture_output_dir,
                metrics_hook=metrics_hook,
                deadline=deadline,
            )
            if result.job_id in completed_job_ids:
                continue
            completed_job_ids.add(result.job_id)
            results.append(result.to_dict())
            cost_jobs.append(_job_cost_input(_load_job_doc(fs, result.job_id) or {}, result))
            success_count += 1
        except Exception as exc:
            failed_count += 1
            results.append(_failure_job_result(job_id, exc))
            if not continue_on_error:
                raise

    status = "ok" if failed_count == 0 else ("partial_failure" if success_count > 0 else "failed")
    batch_cost = _cost_metrics_for_batch(cost_jobs, duration_seconds=_elapsed_seconds(batch_started_at))
    return AvatarBatchRunResult(
        status=status,
        schema_version="avatar_batch_run_result_v1",
        batch_id=resolved.batch_id,
        processed_count=success_count + failed_count,
        success_count=success_count,
        failed_count=failed_count,
        skipped_count=max(0, len(jobs) - success_count - failed_count),
        job_results=results,
        metrics={**model_cache_metrics(), "batchId": resolved.batch_id, "cost": batch_cost},
    )


def _deadline_from_env(config: AvatarJobLeaseConfig) -> Optional[ClaimDeadline]:
    raw = os.environ.get("AVATAR_WORKER_DEADLINE_SECONDS", "").strip()
    if not raw:
        raw = os.environ.get("CLOUD_RUN_TASK_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return None
    try:
        return ClaimDeadline.from_timeout(int(raw), safety_seconds=config.deadline_safety_seconds)
    except ValueError:
        return None


def process_avatar_generation_drain(
    *,
    firestore_client: Any = None,
    storage_client: Any = None,
    qa_runner: QARunner = run_avatar_candidate_qa,
    mode: Optional[str] = None,
    fixture_output_dir: Optional[Path] = None,
    firestore_project: Optional[str] = None,
    firestore_database: Optional[str] = None,
    worker_id: Optional[str] = None,
    config: Optional[AvatarJobLeaseConfig] = None,
    deadline: Optional[ClaimDeadline] = None,
    metrics_hook: Optional[MetricHook] = None,
) -> AvatarBatchRunResult:
    batch_started_at = time.perf_counter()
    validate_bridge_runtime_config(firestore_project)
    resolved_firestore_project = resolve_firestore_project(firestore_project)
    config = config or AvatarJobLeaseConfig.from_env()
    if config.concurrency_per_gpu != 1:
        raise AvatarGenerationError("GPU worker batch/drain mode requires AVATAR_BATCH_CONCURRENCY_PER_GPU=1.")
    fs = firestore_client or _default_firestore_client(resolved_firestore_project, firestore_database)
    st = storage_client or _default_storage_client(resolved_firestore_project)
    active_deadline = deadline if deadline is not None else _deadline_from_env(config)
    active_worker_id = worker_id or os.environ.get("AVATAR_WORKER_ID", "").strip() or f"avatar-worker-{os.getpid()}"
    start = time.monotonic()
    idle_started: Optional[float] = None
    results: List[Dict[str, Any]] = []
    success_count = 0
    failed_count = 0
    completed_job_ids: set[str] = set()
    cost_jobs: List[Dict[str, Any]] = []

    while True:
        if active_deadline is not None and active_deadline.should_stop():
            break
        if time.monotonic() - start >= config.max_batch_seconds:
            break
        leases = claim_avatar_job_batch(
            fs,
            worker_id=active_worker_id,
            config=config,
            deadline=active_deadline,
        )
        if not leases:
            if idle_started is None:
                idle_started = time.monotonic()
            if time.monotonic() - idle_started >= config.max_idle_wait_seconds:
                break
            time.sleep(min(config.poll_interval_seconds, 1))
            continue
        idle_started = None

        for lease in leases:
            if active_deadline is not None and active_deadline.should_stop():
                break
            if lease.job_id in completed_job_ids:
                continue
            try:
                result = process_avatar_generation_payload(
                    _payload_with_source_refs_from_job_doc(fs, lease.payload),
                    firestore_client=fs,
                    storage_client=st,
                    qa_runner=qa_runner,
                    mode=mode,
                    fixture_output_dir=fixture_output_dir,
                    metrics_hook=metrics_hook,
                    deadline=active_deadline,
                )
                completed_job_ids.add(result.job_id)
                results.append(result.to_dict())
                cost_jobs.append(_job_cost_input(_load_job_doc(fs, result.job_id) or {}, result))
                success_count += 1
            except Exception as exc:
                failed_count += 1
                results.append(_failure_job_result(lease.job_id, exc))

    status = "ok" if failed_count == 0 else ("partial_failure" if success_count > 0 else "failed")
    batch_cost = _cost_metrics_for_batch(cost_jobs, duration_seconds=_elapsed_seconds(batch_started_at))
    return AvatarBatchRunResult(
        status=status,
        schema_version="avatar_batch_run_result_v1",
        batch_id="",
        processed_count=success_count + failed_count,
        success_count=success_count,
        failed_count=failed_count,
        skipped_count=0,
        job_results=results,
        metrics={
            **model_cache_metrics(),
            "drainMode": True,
            "concurrencyPerGpu": config.concurrency_per_gpu,
            "cost": batch_cost,
         },
    )


def _load_payload_from_path(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Process a Seolleyeon avatar_generation job payload."
    )
    parser.add_argument("--payload_json", help="Path to avatar_job_v1 JSON payload.")
    parser.add_argument(
        "--mode",
        choices=["dry_run", "flux", "azure", CANONICAL_AZURE_WORKER_MODE],
        default=None,
    )
    parser.add_argument("--fixture_output_dir", help="Optional local directory for generated fixture PNGs.")
    parser.add_argument("--firestore_project")
    parser.add_argument("--firestore_database")
    args = parser.parse_args(argv)

    if args.payload_json:
        payload = _load_payload_from_path(args.payload_json)
    else:
        payload = json.loads(os.sys.stdin.read())

    result = process_avatar_generation_payload(
        payload,
        mode=args.mode,
        fixture_output_dir=Path(args.fixture_output_dir) if args.fixture_output_dir else None,
        firestore_project=args.firestore_project,
        firestore_database=args.firestore_database,
    ) if payload.get("schemaVersion") == "avatar_job_v1" else process_avatar_generation_batch_payload(
        payload,
        mode=args.mode,
        fixture_output_dir=Path(args.fixture_output_dir) if args.fixture_output_dir else None,
        firestore_project=args.firestore_project,
        firestore_database=args.firestore_database,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
