from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, Optional

from avatar_generation.avatar_prompt_contract import (
    AVATAR_GENERAL_PROMPT_V0_TEMP,
    AVATAR_GENERAL_PROMPT_VERSION,
)


AZURE_GPT_IMAGE_2_MODEL_ID = "azure_gpt_image_2"
AZURE_GPT_IMAGE_2_VERSION = "gpt-image-2"


class AzureProviderError(RuntimeError):
    """Sanitized provider failure with bounded retry metadata."""

    def __init__(
        self,
        error_code: str,
        *,
        retryable: bool = False,
        unknown_outcome: bool = False,
        attempts: int = 0,
        provider_status: Optional[int] = None,
        provider_usage: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.error_code = str(error_code)
        self.retryable = bool(retryable)
        self.unknown_outcome = bool(unknown_outcome)
        self.attempts = max(0, int(attempts))
        self.provider_status = provider_status
        self.provider_usage = dict(provider_usage or {})
        super().__init__(self.error_code)


class AzureConfigurationError(AzureProviderError):
    def __init__(self, error_code: str = "azure_provider_configuration_invalid") -> None:
        super().__init__(error_code, retryable=False)


class AzureTransportError(AzureProviderError):
    def __init__(
        self,
        error_code: str = "azure_transport_error",
        *,
        request_sent: bool = False,
    ) -> None:
        self.request_sent = bool(request_sent)
        super().__init__(error_code, retryable=not self.request_sent)


class AzureUnknownOutcomeError(AzureProviderError):
    def __init__(self, attempts: int = 1) -> None:
        super().__init__(
            "azure_unknown_post_send_outcome",
            retryable=False,
            unknown_outcome=True,
            attempts=attempts,
        )


@dataclass(frozen=True)
class AzureGptImage2Config:
    endpoint: str
    deployment: str
    api_version: str
    api_key: str = field(repr=False)
    api_style: str = "foundry_v1"
    max_attempts: int = 3
    request_timeout_seconds: float = 90.0
    max_concurrency: int = 1
    requests_per_minute: int = 2
    backoff_base_seconds: float = 0.5
    max_backoff_seconds: float = 8.0
    quality: Optional[str] = None
    size: Optional[str] = None

    @classmethod
    def from_env(cls, *, require_credentials: bool = True) -> "AzureGptImage2Config":
        import os

        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip()
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "").strip()
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "").strip()
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
        api_style = (
            os.environ.get("AZURE_OPENAI_API_STYLE", "foundry_v1").strip().lower()
            or "foundry_v1"
        )
        if api_style not in {"foundry_v1", "legacy_deployment"}:
            raise AzureConfigurationError("azure_provider_api_style_invalid")
        if require_credentials:
            missing = [
                name
                for name, value in (
                    ("AZURE_OPENAI_ENDPOINT", endpoint),
                    ("AZURE_OPENAI_DEPLOYMENT", deployment),
                    ("AZURE_OPENAI_API_VERSION", api_version),
                    ("AZURE_OPENAI_API_KEY", api_key),
                )
                if not value
            ]
            if missing:
                raise AzureConfigurationError(
                    "azure_provider_configuration_missing_" + "_".join(missing)
                )
        return cls(
            endpoint=endpoint,
            deployment=deployment,
            api_version=api_version,
            api_key=api_key,
            api_style=api_style,
            max_attempts=_bounded_int(os.environ.get("AZURE_OPENAI_MAX_ATTEMPTS"), 3, 1, 5),
            request_timeout_seconds=_bounded_float(
                os.environ.get("AZURE_OPENAI_TIMEOUT_SECONDS"),
                90.0,
                5.0,
                300.0,
            ),
            max_concurrency=_bounded_int(
                os.environ.get("AZURE_OPENAI_MAX_CONCURRENCY"),
                1,
                1,
                8,
            ),
            requests_per_minute=_bounded_int(
                os.environ.get("AZURE_OPENAI_REQUESTS_PER_MINUTE"),
                2,
                1,
                2,
            ),
            backoff_base_seconds=_bounded_float(
                os.environ.get("AZURE_OPENAI_RETRY_BASE_SECONDS"),
                0.5,
                0.0,
                10.0,
            ),
            max_backoff_seconds=_bounded_float(
                os.environ.get("AZURE_OPENAI_RETRY_MAX_SECONDS"),
                8.0,
                0.0,
                60.0,
            ),
            quality=_optional_text(os.environ.get("AZURE_OPENAI_IMAGE_QUALITY")),
            size=_optional_text(os.environ.get("AZURE_OPENAI_IMAGE_SIZE")),
        )

    def safe_dict(self) -> dict[str, Any]:
        return {
            "endpointConfigured": bool(self.endpoint),
            "deploymentConfigured": bool(self.deployment),
            "apiVersionConfigured": bool(self.api_version),
            "apiStyle": self.api_style,
            "credentialConfigured": bool(self.api_key),
            "maxAttempts": self.max_attempts,
            "requestTimeoutSeconds": self.request_timeout_seconds,
            "maxConcurrency": self.max_concurrency,
            "requestsPerMinute": self.requests_per_minute,
            "qualityConfigured": bool(self.quality),
            "sizeConfigured": bool(self.size),
        }


@dataclass(frozen=True)
class AzureImageEditRequest:
    source_image_bytes: bytes = field(repr=False)
    source_content_type: str
    prompt: str
    deployment: str
    api_version: str
    quality: Optional[str] = None
    size: Optional[str] = None


@dataclass(frozen=True)
class AzureProviderResponse:
    status_code: int
    headers: Mapping[str, str]
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class AzureGenerationAudit:
    attempts: int
    latency_seconds: float
    provider_status: int
    outcome: str
    output_format: str
    output_bytes: int
    prompt_version: str = AVATAR_GENERAL_PROMPT_VERSION
    source_input_mode: str = "storage_normalized_original_direct"
    upload_normalization: str = "existing_avatar_media_ingestion"
    pre_generation_transform: str = "none"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": "azure",
            "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
            "modelFamily": AZURE_GPT_IMAGE_2_VERSION,
            "promptVersion": self.prompt_version,
            "sourceInputMode": self.source_input_mode,
            "uploadNormalization": self.upload_normalization,
            "preGenerationTransform": self.pre_generation_transform,
            "legacyTraitExtraction": False,
            "legacyReferencePreprocessing": False,
            "legacyFlux": False,
            "attempts": self.attempts,
            "latencySeconds": round(max(0.0, self.latency_seconds), 3),
            "providerStatus": self.provider_status,
            "outcome": self.outcome,
            "outputFormat": self.output_format,
            "outputBytes": self.output_bytes,
        }


@dataclass(frozen=True)
class AzureGenerationResult:
    image_bytes: bytes = field(repr=False)
    audit: AzureGenerationAudit


class AzureImageTransport(Protocol):
    def send(self, request: AzureImageEditRequest) -> AzureProviderResponse:
        ...


def provider_usage(*, attempts: int, outcome: str) -> dict[str, int | str]:
    normalized = str(outcome or "failure")
    return {
        "provider": "azure",
        "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
        "requestCount": max(0, int(attempts)),
        "attemptCount": max(0, int(attempts)),
        "successCount": 1 if normalized == "success" else 0,
        "failureCount": 1 if normalized == "failure" else 0,
        "unknownOutcomeCount": 1 if normalized == "unknown" else 0,
        "outcome": normalized,
    }


def _optional_text(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _bounded_int(value: Any, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(value).strip()) if str(value or "").strip() else fallback
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def _bounded_float(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(str(value).strip()) if str(value or "").strip() else fallback
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


__all__ = [
    "AVATAR_GENERAL_PROMPT_V0_TEMP",
    "AVATAR_GENERAL_PROMPT_VERSION",
    "AZURE_GPT_IMAGE_2_MODEL_ID",
    "AZURE_GPT_IMAGE_2_VERSION",
    "AzureConfigurationError",
    "AzureGenerationAudit",
    "AzureGenerationResult",
    "AzureGptImage2Config",
    "AzureImageEditRequest",
    "AzureImageTransport",
    "AzureProviderError",
    "AzureProviderResponse",
    "AzureTransportError",
    "AzureUnknownOutcomeError",
    "provider_usage",
]
