"""Fail-closed readiness checks for the actual avatar QA runtime.

The preflight deliberately loads only local model artifacts. It never performs
network downloads or image inference, and its persisted document contains only
stable reason codes rather than exception text, paths, URLs, or model output.
"""

from dataclasses import dataclass
import logging
import os
import re
from typing import Any, Dict, Mapping, Optional, Tuple

from PIL import Image

from .calibration_artifact import CalibrationArtifactError, load_configured_calibration_artifact
from .environment import is_local_or_dev_environment
from .model_adapters.clip_risk import ClipRiskCalibrationPolicy
from .qa_runtime import (
    _clip_risk_policy_from_env,
    _similarity_policy_from_env,
    get_default_clip_risk_scorer,
    get_default_face_detector,
    get_default_similarity_adapter,
    get_default_visual_risk_adapter,
)


STATUS_AVAILABLE = "available"
STATUS_UNAVAILABLE = "unavailable"
STATUS_UNCALIBRATED = "uncalibrated"
STATUS_NOT_REQUIRED = "not_required"

_VALID_STATUSES = frozenset(
    {
        STATUS_AVAILABLE,
        STATUS_UNAVAILABLE,
        STATUS_UNCALIBRATED,
        STATUS_NOT_REQUIRED,
        "critical_unavailable",
    }
)
_SAFE_REASON_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


@dataclass(frozen=True)
class QAComponentReadiness:
    name: str
    status: str
    critical: bool
    reason: str
    provider: Optional[str] = None

    def __post_init__(self) -> None:
        name = str(self.name).strip()
        status = str(self.status).strip().lower()
        reason = str(self.reason).strip().lower()
        if not name or not re.match(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$", name):
            raise ValueError("QA component name is invalid.")
        if status not in _VALID_STATUSES:
            raise ValueError("QA component status is invalid.")
        if not _SAFE_REASON_RE.match(reason):
            raise ValueError("QA component reason is invalid.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason", reason)
        if self.provider is not None:
            provider = str(self.provider).strip()
            if not provider or not re.match(r"^[A-Za-z0-9_.:-]{1,80}$", provider):
                object.__setattr__(self, "provider", None)
            else:
                object.__setattr__(self, "provider", provider)

    def to_document(self) -> Dict[str, Any]:
        document: Dict[str, Any] = {
            "status": self.status,
            "critical": bool(self.critical),
            "reason": self.reason,
        }
        if self.provider:
            document["provider"] = self.provider
        return document


@dataclass(frozen=True)
class QARuntimeReadiness:
    components: Tuple[QAComponentReadiness, ...]
    schema_version: str = "avatar_qa_preflight_v1"

    @property
    def blocking_components(self) -> Tuple[str, ...]:
        return tuple(
            component.name
            for component in self.components
            if component.critical and component.status != STATUS_AVAILABLE
        )

    @property
    def ready(self) -> bool:
        return not self.blocking_components

    @property
    def failure_code(self) -> str:
        statuses = {
            component.status
            for component in self.components
            if component.name in self.blocking_components
        }
        if STATUS_UNAVAILABLE in statuses or "critical_unavailable" in statuses:
            return "avatar_qa_runtime_unavailable"
        if STATUS_UNCALIBRATED in statuses:
            return "avatar_qa_calibration_unavailable"
        if statuses:
            return "avatar_qa_preflight_failed"
        return ""

    def to_document(self) -> Dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "ready": self.ready,
            "failureCode": self.failure_code,
            "blockingComponents": list(self.blocking_components),
            "components": {
                component.name: component.to_document()
                for component in self.components
            },
            "signalCoverage": {
                "cropConsistency": "faceDetector",
                "watermark": "visualRisk",
                "secondaryFaceLeakage": "visualRisk",
                "childlikeRisk": "localSafetyRisk",
                "identitySimilarity": "faceSimilarity",
                "dinoRerank": "not_required_in_active_qa_contract",
            },
        }


_READINESS_CACHE: Optional[QARuntimeReadiness] = None
_LOGGER = logging.getLogger(__name__)


def build_qa_runtime_readiness() -> QARuntimeReadiness:
    """Probe all critical QA dependencies using local-only model loading."""

    _force_offline_model_loading()

    components = (
        _probe_image_decode(),
        _probe_face_detector(),
        _probe_visual_risk(),
        _probe_local_safety(),
        _probe_face_similarity(),
        _probe_device(),
        QAComponentReadiness(
            name="dino",
            status=STATUS_NOT_REQUIRED,
            critical=False,
            reason="not_in_active_qa_contract",
        ),
    )
    if _calibration_artifact_check_enabled():
        components = components[:-1] + (build_calibration_artifact_readiness(), components[-1])
    return QARuntimeReadiness(components=components)


def _calibration_artifact_check_enabled() -> bool:
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    return bool(os.environ.get("AVATAR_QA_CALIBRATION_ARTIFACT_PATH", "").strip()) or environment in {
        "staging",
        "production",
        "production_bridge",
        "prod",
    }


def build_calibration_artifact_readiness() -> QAComponentReadiness:
    required = _calibration_artifact_check_enabled()
    try:
        artifact = load_configured_calibration_artifact(required=required)
    except CalibrationArtifactError as exc:
        text = str(exc).lower()
        reason = (
            "calibration_artifact_missing"
            if "missing" in text or "unavailable" in text
            else "calibration_artifact_invalid"
        )
        return QAComponentReadiness(
            name="calibrationArtifact",
            status=STATUS_UNCALIBRATED,
            critical=True,
            reason=reason,
            provider="local_file",
        )
    if artifact is None:
        return QAComponentReadiness(
            name="calibrationArtifact",
            status=STATUS_NOT_REQUIRED,
            critical=False,
            reason="artifact_not_configured",
            provider="local_file",
        )
    return QAComponentReadiness(
        name="calibrationArtifact",
        status=STATUS_AVAILABLE,
        critical=True,
        reason="artifact_loaded",
        provider="local_file",
    )


def _force_offline_model_loading() -> None:
    """Prevent library-side conversion/check threads from reaching model hubs."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"


def get_qa_runtime_readiness(*, force_refresh: bool = False) -> QARuntimeReadiness:
    global _READINESS_CACHE
    if _READINESS_CACHE is None or force_refresh:
        _READINESS_CACHE = build_qa_runtime_readiness()
    return _READINESS_CACHE


def reset_qa_runtime_readiness_for_tests() -> None:
    global _READINESS_CACHE
    _READINESS_CACHE = None


def _probe_image_decode() -> QAComponentReadiness:
    try:
        image = Image.new("RGB", (2, 2), (0, 0, 0))
        image.convert("RGB").load()
    except Exception as exc:
        _log_probe_failure("imageDecode", "image_decode_unavailable", exc)
        return QAComponentReadiness(
            name="imageDecode",
            status=STATUS_UNAVAILABLE,
            critical=True,
            reason="image_decode_unavailable",
            provider="pillow",
        )
    return QAComponentReadiness(
        name="imageDecode",
        status=STATUS_AVAILABLE,
        critical=True,
        reason="ok",
        provider="pillow",
    )


def _probe_face_detector() -> QAComponentReadiness:
    try:
        detector = get_default_face_detector()
        provider = str(getattr(detector, "provider_name", "") or "").strip()
        lowered = provider.lower()
        if not provider or "deterministic_fallback" in lowered or lowered == "fallback":
            return QAComponentReadiness(
                name="faceDetector",
                status=STATUS_UNAVAILABLE,
                critical=True,
                reason="face_detector_fallback",
                provider=provider or None,
            )
        return QAComponentReadiness(
            name="faceDetector",
            status=STATUS_AVAILABLE,
            critical=True,
            reason="ok",
            provider=provider,
        )
    except Exception as exc:
        _log_probe_failure("faceDetector", "face_detector_unavailable", exc)
        return QAComponentReadiness(
            name="faceDetector",
            status=STATUS_UNAVAILABLE,
            critical=True,
            reason="face_detector_unavailable",
        )


def _probe_visual_risk() -> QAComponentReadiness:
    try:
        adapter = get_default_visual_risk_adapter()
        ensure_loaded = getattr(adapter, "_ensure_loaded", None)
        if not callable(ensure_loaded):
            raise RuntimeError("visual risk adapter cannot load")
        ensure_loaded()
        return QAComponentReadiness(
            name="visualRisk",
            status=STATUS_AVAILABLE,
            critical=True,
            reason="local_artifact_loaded",
            provider=str(getattr(adapter, "provider", "florence2")),
        )
    except Exception as exc:
        _log_probe_failure("visualRisk", "model_artifact_unavailable", exc)
        return QAComponentReadiness(
            name="visualRisk",
            status=STATUS_UNAVAILABLE,
            critical=True,
            reason="model_artifact_unavailable",
            provider="florence2",
        )


def _probe_local_safety() -> QAComponentReadiness:
    try:
        scorer = get_default_clip_risk_scorer()
        if not bool(scorer.is_available()):
            return QAComponentReadiness(
                name="localSafetyRisk",
                status=STATUS_UNAVAILABLE,
                critical=True,
                reason="model_artifact_unavailable",
                provider=str(getattr(scorer, "provider", "clip")),
            )
        policy = _clip_risk_policy_from_env()
        if policy is None or not bool(policy.is_valid):
            return QAComponentReadiness(
                name="localSafetyRisk",
                status=STATUS_UNCALIBRATED,
                critical=True,
                reason="calibration_missing_or_invalid",
                provider=str(getattr(scorer, "provider", "clip")),
            )
        return QAComponentReadiness(
            name="localSafetyRisk",
            status=STATUS_AVAILABLE,
            critical=True,
            reason="local_artifact_and_calibration_loaded",
            provider=str(getattr(scorer, "provider", "clip")),
        )
    except Exception as exc:
        _log_probe_failure("localSafetyRisk", "local_safety_runtime_unavailable", exc)
        return QAComponentReadiness(
            name="localSafetyRisk",
            status=STATUS_UNAVAILABLE,
            critical=True,
            reason="local_safety_runtime_unavailable",
            provider="clip",
        )


def _probe_face_similarity() -> QAComponentReadiness:
    try:
        adapter = get_default_similarity_adapter()
        if not _similarity_adapter_is_available(adapter):
            return QAComponentReadiness(
                name="faceSimilarity",
                status=STATUS_UNAVAILABLE,
                critical=True,
                reason="model_artifact_unavailable",
                provider=str(getattr(adapter, "provider", "clip")),
            )
        policy = _similarity_policy_from_env()
        if policy is None or not bool(getattr(policy, "is_calibrated", False)):
            return QAComponentReadiness(
                name="faceSimilarity",
                status=STATUS_UNCALIBRATED,
                critical=True,
                reason="calibration_missing_or_invalid",
                provider=str(getattr(adapter, "provider", "clip")),
            )
        return QAComponentReadiness(
            name="faceSimilarity",
            status=STATUS_AVAILABLE,
            critical=True,
            reason="local_artifact_and_calibration_loaded",
            provider=str(getattr(adapter, "provider", "clip")),
        )
    except Exception as exc:
        _log_probe_failure("faceSimilarity", "face_similarity_runtime_unavailable", exc)
        return QAComponentReadiness(
            name="faceSimilarity",
            status=STATUS_UNAVAILABLE,
            critical=True,
            reason="face_similarity_runtime_unavailable",
            provider="clip",
        )


def _similarity_adapter_is_available(adapter: Any) -> bool:
    is_available = getattr(adapter, "is_available", None)
    if callable(is_available):
        return bool(is_available())
    encoder = getattr(adapter, "encoder", None)
    encoder_is_available = getattr(encoder, "is_available", None)
    if callable(encoder_is_available):
        return bool(encoder_is_available())
    return False


def _probe_device() -> QAComponentReadiness:
    critical = not is_local_or_dev_environment()
    try:
        import torch  # type: ignore

        if not bool(torch.cuda.is_available()):
            return QAComponentReadiness(
                name="device",
                status=STATUS_UNAVAILABLE,
                critical=critical,
                reason="cuda_unavailable",
                provider="torch",
            )
        return QAComponentReadiness(
            name="device",
            status=STATUS_AVAILABLE,
            critical=critical,
            reason="cuda_available",
            provider="torch",
        )
    except Exception as exc:
        _log_probe_failure("device", "cuda_runtime_unavailable", exc)
        return QAComponentReadiness(
            name="device",
            status=STATUS_UNAVAILABLE,
            critical=critical,
            reason="cuda_runtime_unavailable",
            provider="torch",
        )


def _log_probe_failure(component: str, reason: str, exc: Exception) -> None:
    """Log only stable diagnostic metadata; never exception text or paths."""

    _LOGGER.warning(
        "Avatar QA preflight component unavailable",
        extra={
            "qaComponent": component,
            "qaReason": reason,
            "exceptionType": type(exc).__name__,
        },
    )


__all__ = [
    "QAComponentReadiness",
    "QARuntimeReadiness",
    "STATUS_AVAILABLE",
    "STATUS_NOT_REQUIRED",
    "STATUS_UNAVAILABLE",
    "STATUS_UNCALIBRATED",
    "build_calibration_artifact_readiness",
    "build_qa_runtime_readiness",
    "get_qa_runtime_readiness",
    "reset_qa_runtime_readiness_for_tests",
]
