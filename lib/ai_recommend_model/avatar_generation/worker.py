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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageStat

from avatar_generation import FLUX2_KLEIN_MODEL_ID, FLUX2_KLEIN_VERSION
from avatar_generation.adaptive_generation import AdaptiveGenerationPolicy, plan_generation_round
from avatar_generation.analysis.source_analyzer import analyze_avatar_source_image
from avatar_generation.batching import claim_avatar_job_batch
from avatar_generation.cost import build_batch_cost_document, build_job_cost_document
from avatar_generation.job_lease import AvatarJobLeaseConfig, ClaimDeadline
from avatar_generation.model_adapters.florence2 import Florence2TraitExtractionAdapter
from avatar_generation.preprocessing import (
    ReferencePreprocessConfig,
    preprocess_reference_image,
    validate_reference_preprocess_enabled_for_environment,
)
from avatar_generation.qa import AvatarQAResult, run_avatar_candidate_qa
from avatar_generation.rerank import rerank_preview_candidates
from avatar_generation.seolleyeon_avatar_prompt_builder_v4 import (
    AvatarTraitCard as PromptAvatarTraitCard,
    build_avatar_prompt,
)
from avatar_generation.storage import build_temp_candidate_ref, build_temp_candidate_path
from avatar_generation.trait_card import (
    TraitCardValidationResult,
    normalize_avatar_presentation_gender,
)

try:
    from google.cloud import firestore, storage
    from google.cloud.firestore import SERVER_TIMESTAMP
except Exception:  # pragma: no cover - optional in pure unit tests
    firestore = None  # type: ignore[assignment]
    storage = None  # type: ignore[assignment]
    SERVER_TIMESTAMP = datetime.now(tz=timezone.utc)


DEFAULT_SOURCE_PHOTO_BUCKET = "seolleyeon-private-source-photos"
DEFAULT_AVATAR_TEMP_BUCKET = "seolleyeon-avatar-temp"
DEFAULT_MAX_CANDIDATES = 4
DEFAULT_CANDIDATE_TTL_HOURS = 72
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024
DEFAULT_STEPS = 4
DEFAULT_GUIDANCE_SCALE = 1.0
DEFAULT_REFERENCE_PRIVACY_DOWNSAMPLE_SIZE = 96
DEFAULT_REFERENCE_PRIVACY_BLUR_RADIUS = 1.5

logger = logging.getLogger(__name__)


class AvatarGenerationError(RuntimeError):
    pass


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

    def ensure_can_continue(self, stage: str, *, min_remaining_seconds: int = 0) -> None:
        required = max(0, min_remaining_seconds) + max(0, self.soft_stop_margin_seconds)
        if self.remaining_seconds() <= required:
            raise AvatarGenerationError(
                f"avatar_worker_deadline_exceeded at {stage}."
            )


_FLUX_ALWAYS_DROPPED_KWARGS = frozenset({"negative_prompt"})


def build_flux_prompt_with_avoid(prompt: str, negative_prompt: str = "") -> str:
    """Fold text-only negative constraints into the FLUX prompt.

    Flux2KleinPipeline does not accept a normal ``negative_prompt`` string
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

_FLUX_GENERATOR_CACHE: Dict[str, "Flux2KleinImageGenerator"] = {}
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
    return os.environ.get("ENVIRONMENT", "").strip().lower() in {"prod", "production"}


def is_local_or_dev_environment() -> bool:
    return os.environ.get("ENVIRONMENT", "").strip().lower() in {"", "local", "dev", "development", "test"}


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
        run_mode = "flux"
    else:
        run_mode = "dry_run"

    if run_mode not in {"dry_run", "flux"}:
        raise AvatarGenerationError("AVATAR_WORKER_MODE must be dry_run or flux.")
    if production and run_mode == "dry_run":
        raise AvatarGenerationError("dry_run is not allowed when ENVIRONMENT=production.")
    if run_mode == "dry_run" and not is_local_or_dev_environment():
        raise AvatarGenerationError("dry_run is only allowed in local/dev/test environments.")
    return run_mode


def source_photo_bucket() -> str:
    return env_value("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET)


def avatar_temp_bucket() -> str:
    return env_value("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET)


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
    if _bool_env_default("AVATAR_DISABLE_NEW_GENERATION", False) is True:
        return "new_generation_disabled"
    if _bool_env_default("AVATAR_COST_KILL_SWITCH_ENABLED", False) is True:
        return "cost_kill_switch_enabled"
    return ""


def _source_analysis_enabled(run_mode: str) -> bool:
    return _bool_env_default("AVATAR_FACE_DETECTOR_ENABLED", run_mode == "flux")


def _trait_extraction_enabled(run_mode: str) -> bool:
    return _bool_env_default("AVATAR_TRAIT_EXTRACTION_ENABLED", run_mode == "flux")


def _trait_require_validated() -> bool:
    return _bool_env_default("AVATAR_TRAIT_REQUIRE_VALIDATED", True)


def _reference_preprocess_config_from_env() -> ReferencePreprocessConfig:
    return ReferencePreprocessConfig(
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

    model_id = str(payload.get("modelId") or FLUX2_KLEIN_MODEL_ID).strip()
    if model_id != FLUX2_KLEIN_MODEL_ID:
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
    digest = hashlib.sha256(f"{job_id}:{index}:flux2_klein_avatar_v1".encode("utf-8")).hexdigest()
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
    if str(job_doc.get("status") or "") in {"preview_ready", "approved"}:
        raise AvatarGenerationError("Avatar job is already complete.")


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


def load_source_image_from_gcs(storage_client: Any, source_ref: GcsRef) -> Image.Image:
    blob = _blob_for(storage_client, source_ref)
    if hasattr(blob, "exists") and not blob.exists():
        raise AvatarGenerationError("Private source photo does not exist.")
    data = blob.download_as_bytes()
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGB")


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
    def __init__(self, model_id: str = FLUX2_KLEIN_MODEL_ID) -> None:
        self.model_id = model_id
        self._pipeline: Any = None

    def _load_pipeline(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        try:
            import torch
            from diffusers import Flux2KleinPipeline
        except Exception as exc:  # pragma: no cover - expensive dependency path
            raise AvatarGenerationError(
                "Flux2KleinPipeline is unavailable. Install a diffusers version that "
                "supports black-forest-labs/FLUX.2-klein-4B in the GPU worker image."
            ) from exc

        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        pipe = Flux2KleinPipeline.from_pretrained(self.model_id, torch_dtype=dtype)
        if torch.cuda.is_available():
            pipe = pipe.to("cuda")
        elif hasattr(pipe, "enable_model_cpu_offload"):
            pipe.enable_model_cpu_offload()
        self._pipeline = pipe
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
            width=int(os.environ.get("AVATAR_GENERATION_WIDTH", DEFAULT_WIDTH)),
            height=int(os.environ.get("AVATAR_GENERATION_HEIGHT", DEFAULT_HEIGHT)),
            num_inference_steps=int(os.environ.get("AVATAR_GENERATION_STEPS", DEFAULT_STEPS)),
            guidance_scale=float(os.environ.get("AVATAR_GENERATION_GUIDANCE_SCALE", DEFAULT_GUIDANCE_SCALE)),
            generator=generator,
        )
        images = getattr(result, "images", None)
        if not images:
            raise AvatarGenerationError("FLUX generation returned no images.")
        return images[0].convert("RGB")


def reset_model_cache_for_tests() -> None:
    _FLUX_GENERATOR_CACHE.clear()
    for key in _MODEL_METRICS:
        _MODEL_METRICS[key] = 0


def model_cache_metrics() -> Dict[str, int]:
    metrics = dict(_MODEL_METRICS)
    metrics["modelCacheSize"] = len(_FLUX_GENERATOR_CACHE)
    return metrics


def get_flux2_klein_generator(model_id: str = FLUX2_KLEIN_MODEL_ID) -> Flux2KleinImageGenerator:
    generator = _FLUX_GENERATOR_CACHE.get(model_id)
    if generator is not None:
        _MODEL_METRICS["modelCacheHits"] += 1
        return generator
    _MODEL_METRICS["modelCacheMisses"] += 1
    _MODEL_METRICS["modelLoadCalls"] += 1
    generator = Flux2KleinImageGenerator(model_id)
    _FLUX_GENERATOR_CACHE[model_id] = generator
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
) -> List[CandidateArtifact]:
    artifacts: List[CandidateArtifact] = []
    generator = get_flux2_klein_generator(payload.model_id) if mode == "flux" else None
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
        prompt = build_avatar_prompt(
            trait_card=trait_card,
            candidate_index=index,
            candidate_count=total_count,
            seed=seed,
        )
        if mode == "flux":
            assert generator is not None
            image = generator.generate(
                source_image=generation_reference,
                prompt=prompt.positive,
                avoid_prompt=prompt.provider_negative or prompt.negative,
                seed=seed,
            )
        else:
            image = build_fixture_avatar_image(source_image, seed=seed, index=index)
        image_ref = build_temp_candidate_ref(
            uid=payload.uid,
            job_id=payload.job_id,
            candidate_id=candidate_id,
        )
        artifacts.append(
            CandidateArtifact(
                candidate_id=candidate_id,
                image_ref=image_ref,
                image_bytes=image_to_png_bytes(image),
                seed=seed,
                generation_params={
                    "modelId": payload.model_id,
                    "modelVersion": FLUX2_KLEIN_VERSION,
                    "mode": mode,
                    "width": int(os.environ.get("AVATAR_GENERATION_WIDTH", DEFAULT_WIDTH)),
                    "height": int(os.environ.get("AVATAR_GENERATION_HEIGHT", DEFAULT_HEIGHT)),
                    "numInferenceSteps": int(os.environ.get("AVATAR_FLUX_NUM_INFERENCE_STEPS", os.environ.get("AVATAR_GENERATION_STEPS", DEFAULT_STEPS))),
                    "guidanceScale": float(os.environ.get("AVATAR_FLUX_GUIDANCE_SCALE", os.environ.get("AVATAR_GENERATION_GUIDANCE_SCALE", DEFAULT_GUIDANCE_SCALE))),
                    "referencePrivacyPreprocess": _reference_privacy_preprocess_enabled(),
                    "referencePreprocess": dict(reference_preprocess_metadata or {}),
                    "promptVersion": str(prompt.meta.get("prompt_version") or "seolleyeon_avatar_v4"),
                    "promptBuilder": "seolleyeon_avatar_prompt_builder_v4",
                    "promptMeta": dict(prompt.meta),
                    "generationKwargs": dict(prompt.generation_kwargs),
                },
            )
        )
    return artifacts


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
    if qa_doc.get("previewAllowed") is True:
        return "preview_ready"
    if qa_doc.get("requiresHumanReview") is True:
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
        "modelVersion": FLUX2_KLEIN_VERSION,
        "seed": artifact.seed,
        "generationParams": artifact.generation_params,
        "status": status,
        "qa": dict(qa_doc or {}),
        "createdAt": SERVER_TIMESTAMP,
        "updatedAt": SERVER_TIMESTAMP,
        "expiresAt": expires_at,
    }


def _update_job_status(firestore_client: Any, job_id: str, payload: Dict[str, Any]) -> None:
    _set_doc(
        _doc_ref(firestore_client, "avatarJobs", job_id),
        {
            **payload,
            "updatedAt": SERVER_TIMESTAMP,
        },
        merge=True,
    )


def _elapsed_seconds(started_at: float) -> float:
    return round(max(0.0, time.perf_counter() - started_at), 3)


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
) -> Dict[str, Any]:
    estimate = build_job_cost_document(
        duration_seconds=duration_seconds,
        estimated_at=datetime.now(tz=timezone.utc),
    )
    cost_estimate = _json_safe_cost_value(dict(estimate["costEstimate"]))
    cost = {
        "candidateCount": int(candidate_count),
        "totalWorkerSeconds": cost_estimate["durationSeconds"],
        "estimatedUsd": estimate["costEstimateUsd"],
        "pricingVersion": cost_estimate["pricingVersion"],
        "secondsByStage": {key: round(max(0.0, float(value)), 3) for key, value in seconds_by_stage.items()},
        "breakdown": dict(cost_estimate.get("breakdown") or {}),
        "estimatedAt": cost_estimate.get("estimatedAt"),
    }
    return {
        "cost": cost,
        "costEstimateUsd": estimate["costEstimateUsd"],
        "costEstimate": cost_estimate,
        "durationSeconds": cost_estimate["durationSeconds"],
    }


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
    if "multiple_faces" in reasons:
        return "avatar_source_multi_face"
    return "avatar_source_safety_rejected"


def _worker_error_code(exc: Exception) -> str:
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


def _extract_trait_card_for_generation(
    image: Image.Image,
    *,
    run_mode: str,
    avatar_presentation_gender: str = "unknown",
) -> tuple[Optional[TraitCardValidationResult], Optional[PromptAvatarTraitCard]]:
    if not _trait_extraction_enabled(run_mode):
        return None, None

    adapter = Florence2TraitExtractionAdapter(
        model_id=os.environ.get("AVATAR_TRAIT_MODEL_ID", "").strip()
        or "microsoft/Florence-2-large-ft",
        dry_run=_bool_env_default("AVATAR_TRAIT_DRY_RUN", run_mode == "dry_run"),
        local_files_only=_bool_env_default("AVATAR_TRAIT_LOCAL_FILES_ONLY", True),
        attn_implementation=os.environ.get(
            "AVATAR_TRAIT_ATTENTION_IMPLEMENTATION",
            "eager",
        ).strip()
        or "eager",
        task_prompt=os.environ.get(
            "AVATAR_TRAIT_FLORENCE_TASK_PROMPT",
            "MORE_DETAILED_CAPTION",
        ).strip()
        or "MORE_DETAILED_CAPTION",
    )
    validation = adapter.extract_traits(
        image=_resize_for_trait_extraction(image),
        avatar_presentation_gender=avatar_presentation_gender,
    )
    if _trait_require_validated() and not validation.privacy_safe:
        raise AvatarGenerationError("avatar trait card did not pass privacy validation.")
    prompt_card = PromptAvatarTraitCard(
        **validation.trait_card.to_prompt_builder_dict()
    )
    return validation, prompt_card


def _prepare_reference_preprocess_for_generation(
    source_image: Image.Image,
    *,
    source_analysis: Any = None,
    run_mode: str,
) -> tuple[Optional[Image.Image], Dict[str, Any]]:
    if run_mode != "flux":
        return None, {}
    if not _reference_privacy_preprocess_enabled():
        validate_reference_preprocess_enabled_for_environment(
            preprocess_enabled=False,
        )
        return source_image.convert("RGB"), {"enabled": False}
    result = preprocess_reference_image(
        source_image,
        source_analysis=source_analysis,
        config=_reference_preprocess_config_from_env(),
    )
    return result.image, result.metadata


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

        if candidate_id in selected_ids and allow_preview_selection:
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
        elif status == "needs_review":
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
    if preview_ready_count <= 0:
        return False
    if not policy.require_four_preview:
        return True
    return preview_ready_count >= max(0, int(policy.preview_candidate_count))


def _preview_shortfall(
    preview_ready_count: int,
    policy: AdaptiveGenerationPolicy,
) -> int:
    if not policy.require_four_preview:
        return 0
    return max(0, int(policy.preview_candidate_count) - int(preview_ready_count))


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
) -> AvatarGenerationResult:
    job_started_at = time.perf_counter()
    worker_deadline = AvatarWorkerDeadline.from_env()
    seconds_by_stage: Dict[str, float] = {
        "loadSource": 0.0,
        "generate": 0.0,
        "uploadAndQa": 0.0,
        "total": 0.0,
    }
    payload = parse_avatar_generation_payload(raw_payload)
    run_mode = resolve_worker_mode(mode)

    fs = firestore_client or _default_firestore_client(firestore_project, firestore_database)
    st = storage_client or _default_storage_client(firestore_project)

    job_doc = _load_job_doc(fs, payload.job_id)
    _assert_job_can_run(job_doc, payload)
    pause_reason = _generation_pause_reason()
    if pause_reason:
        _update_job_status(
            fs,
            payload.job_id,
            {
                "status": "failed",
                "errorCode": "avatar_worker_cost_guard_paused",
                "errorMessage": "Avatar generation is currently paused.",
                "processing": {
                    "lastErrorCode": "avatar_worker_cost_guard_paused",
                    "lastErrorMessage": pause_reason,
                },
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
    avatar_presentation_gender = _avatar_presentation_gender_for_job(
        payload,
        job_doc,
    )
    private_doc = _load_private_media_doc(fs, payload.uid)
    _assert_avatar_generation_consent(private_doc)
    _ensure_source_refs_match_private_media(private_doc, payload)
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

    source_refs = validate_private_source_refs(payload.source_photo_refs)
    _update_job_status(
        fs,
        payload.job_id,
        {
            "status": "running",
            "startedAt": SERVER_TIMESTAMP,
            "workerMode": run_mode,
        },
    )

    try:
        worker_deadline.ensure_can_continue("load_source", min_remaining_seconds=10)
        stage_started_at = time.perf_counter()
        source_image = load_source_image_from_gcs(st, source_refs[0])
        seconds_by_stage["loadSource"] += _elapsed_seconds(stage_started_at)

        source_analysis = None
        source_analysis_doc: Dict[str, Any] = {}
        if _source_analysis_enabled(run_mode):
            worker_deadline.ensure_can_continue("source_analysis", min_remaining_seconds=10)
            source_analysis = analyze_avatar_source_image(
                source_image,
                source_ref=payload.source_photo_refs[0],
            )
            source_analysis_doc = source_analysis.to_document()
            _update_job_status(
                fs,
                payload.job_id,
                {"sourceAnalysis": source_analysis_doc},
            )
            if source_analysis.hard_reject:
                final_status = "failed"
                final_update = {
                    "status": final_status,
                    "candidateIds": [],
                    "sourceAnalysis": source_analysis_doc,
                    "errorCode": _source_reject_error_code(source_analysis_doc),
                    "errorMessage": "Source image was not usable for avatar generation.",
                }
                seconds_by_stage["total"] = _elapsed_seconds(job_started_at)
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
                    status=final_status,
                    candidate_ids=[],
                    preview_ready_count=0,
                    rejected_count=0,
                    needs_review_count=0,
                )

        trait_validation = None
        prompt_trait_card = None
        if _trait_extraction_enabled(run_mode):
            try:
                worker_deadline.ensure_can_continue("trait_extraction", min_remaining_seconds=20)
                trait_validation, prompt_trait_card = _extract_trait_card_for_generation(
                    source_image,
                    run_mode=run_mode,
                    avatar_presentation_gender=avatar_presentation_gender,
                )
            except Exception as exc:
                detail = str(exc).splitlines()[0][:200]
                logger.warning(
                    "Avatar trait extraction failed: %s: %s",
                    type(exc).__name__,
                    detail,
                )
                raise AvatarGenerationError("avatar trait extraction failed.") from exc
            _update_job_status(
                fs,
                payload.job_id,
                {
                    "traitCard": trait_validation.to_dict()
                    if trait_validation is not None
                    else None
                },
            )

        privacy_reference_image, reference_preprocess_doc = (
            _prepare_reference_preprocess_for_generation(
                source_image,
                source_analysis=source_analysis,
                run_mode=run_mode,
            )
        )
        if reference_preprocess_doc:
            _update_job_status(
                fs,
                payload.job_id,
                {"referencePreprocess": reference_preprocess_doc},
            )

        worker_deadline.ensure_can_continue("generate_initial", min_remaining_seconds=30)
        stage_started_at = time.perf_counter()
        policy = AdaptiveGenerationPolicy.from_env()
        initial_count = min(
            max(1, int(payload.candidate_count)),
            max(1, int(policy.initial_candidate_count)),
        )
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
        )
        seconds_by_stage["generate"] += _elapsed_seconds(stage_started_at)
        _update_job_status(fs, payload.job_id, {"status": "qa_pending"})

        candidate_ids: List[str] = []
        candidate_summaries: List[Dict[str, Any]] = []
        generation_rounds: List[Dict[str, Any]] = [
            {
                "reason": "initial",
                "candidateCount": initial_count,
                "startIndex": 0,
            }
        ]
        stage_started_at = time.perf_counter()
        for artifact in artifacts:
            worker_deadline.ensure_can_continue("upload_and_qa", min_remaining_seconds=10)
            if fixture_output_dir is not None:
                _write_fixture_file(fixture_output_dir, artifact)
            else:
                _upload_candidate(st, artifact)

            candidate_ref = _doc_ref(fs, "avatarCandidates", artifact.candidate_id)
            _set_doc(candidate_ref, _candidate_doc(payload, artifact, status="qa_pending"), merge=True)

            qa_result = qa_runner(
                payload.source_photo_refs[0],
                artifact.image_ref,
                {
                    "jobId": payload.job_id,
                    "uid": payload.uid,
                    "candidateId": artifact.candidate_id,
                    "modelId": payload.model_id,
                    "seed": artifact.seed,
                    "redactedSourceRef": redact_gcs_ref(payload.source_photo_refs[0]),
                },
            )
            qa_doc = qa_result.to_document()
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

        extra_plan = plan_generation_round(candidate_summaries, policy=policy)
        if (
            payload.candidate_count >= policy.min_safe_before_extra
            and extra_plan.should_generate
        ):
            worker_deadline.ensure_can_continue("generate_extra", min_remaining_seconds=30)
            stage_generate_extra_started_at = time.perf_counter()
            extra_artifacts = generate_candidate_artifacts(
                payload,
                source_image,
                mode=run_mode,
                source_analysis=source_analysis,
                trait_card=prompt_trait_card,
                privacy_reference_image=privacy_reference_image,
                reference_preprocess_metadata=reference_preprocess_doc,
                candidate_start_index=len(candidate_summaries),
                candidate_count=extra_plan.candidate_count,
            )
            seconds_by_stage["generate"] += _elapsed_seconds(stage_generate_extra_started_at)
            generation_rounds.append(
                {
                    "reason": extra_plan.reason,
                    "candidateCount": extra_plan.candidate_count,
                    "startIndex": len(candidate_summaries),
                }
            )

            for artifact in extra_artifacts:
                worker_deadline.ensure_can_continue("upload_and_qa_extra", min_remaining_seconds=10)
                if fixture_output_dir is not None:
                    _write_fixture_file(fixture_output_dir, artifact)
                else:
                    _upload_candidate(st, artifact)

                candidate_ref = _doc_ref(fs, "avatarCandidates", artifact.candidate_id)
                _set_doc(candidate_ref, _candidate_doc(payload, artifact, status="qa_pending"), merge=True)

                qa_result = qa_runner(
                    payload.source_photo_refs[0],
                    artifact.image_ref,
                    {
                        "jobId": payload.job_id,
                        "uid": payload.uid,
                        "candidateId": artifact.candidate_id,
                        "modelId": payload.model_id,
                        "seed": artifact.seed,
                        "redactedSourceRef": redact_gcs_ref(payload.source_photo_refs[0]),
                    },
                )
                qa_doc = qa_result.to_document()
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

        seconds_by_stage["uploadAndQa"] += _elapsed_seconds(stage_started_at)
        preview_ready, rejected, needs_review, rerank_doc = _apply_preview_selection(
            fs,
            candidate_summaries,
            policy=policy,
        )
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
        generation_plan = {
            "initialCount": initial_count,
            "extraCount": sum(
                int(round_doc.get("candidateCount") or 0)
                for round_doc in generation_rounds[1:]
            ),
            "totalGenerated": len(candidate_ids),
            "safePassCount": hard_pass_count,
            "previewCount": preview_ready,
            "filledWithSoftPass": filled_with_soft_pass,
            "qwenFallbackUsed": False,
            "rounds": generation_rounds,
            "policy": {
                "previewCount": policy.preview_candidate_count,
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
                "generationPlan": generation_plan,
                "previewRerank": rerank_doc,
            }
        elif preview_ready > 0 or needs_review > 0:
            final_status = "needs_review"
            error_code = (
                "requires_more_preview_candidates"
                if rerank_doc.get("status") == "insufficient_preview_candidates"
                else "requires_human_review"
            )
            final_update = {
                "status": final_status,
                "candidateIds": candidate_ids,
                "errorCode": error_code,
                "generationPlan": generation_plan,
                "previewRerank": rerank_doc,
            }
        else:
            final_status = "failed"
            final_update = {
                "status": final_status,
                "candidateIds": candidate_ids,
                "errorCode": "no_previewable_candidates",
                "errorMessage": "All generated avatar candidates were rejected by QA.",
                "generationPlan": generation_plan,
                "previewRerank": rerank_doc,
            }
        seconds_by_stage["total"] = _elapsed_seconds(job_started_at)
        final_update.update(
            _cost_document_for_job(
                duration_seconds=seconds_by_stage["total"],
                candidate_count=len(candidate_ids),
                seconds_by_stage=seconds_by_stage,
            )
        )
        _update_job_status(fs, payload.job_id, final_update)
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
        _update_job_status(
            fs,
            payload.job_id,
            {
                "status": "failed",
                "errorCode": _worker_error_code(exc),
                "errorMessage": redact_error_message(exc),
            },
        )
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
    fs = firestore_client or _default_firestore_client(firestore_project, firestore_database)
    st = storage_client or _default_storage_client(firestore_project)
    resolved = _resolve_batch_payload(raw_payload, fs)
    jobs = resolved.jobs
    deadline = (
        ClaimDeadline.from_timeout(resolved.deadline_seconds, safety_seconds=0)
        if resolved.deadline_seconds is not None
        else None
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
    config = config or AvatarJobLeaseConfig.from_env()
    if config.concurrency_per_gpu != 1:
        raise AvatarGenerationError("GPU worker batch/drain mode requires AVATAR_BATCH_CONCURRENCY_PER_GPU=1.")
    fs = firestore_client or _default_firestore_client(firestore_project, firestore_database)
    st = storage_client or _default_storage_client(firestore_project)
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
    parser.add_argument("--mode", choices=["dry_run", "flux"], default=None)
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
