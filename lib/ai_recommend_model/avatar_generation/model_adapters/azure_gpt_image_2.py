from __future__ import annotations

import base64
import io
import random
import threading
import time
from typing import Any, Callable, Mapping, Optional

from PIL import Image

from avatar_generation.avatar_prompt_contract import (
    AVATAR_GENERAL_PROMPT_V0_TEMP,
    AVATAR_GENERAL_PROMPT_VERSION,
)

from .azure_contracts import (
    AZURE_GPT_IMAGE_2_MODEL_ID,
    AZURE_GPT_IMAGE_2_VERSION,
    AzureConfigurationError,
    AzureGenerationAudit,
    AzureGenerationResult,
    AzureGptImage2Config,
    AzureImageEditRequest,
    AzureImageTransport,
    AzureProviderError,
    AzureProviderResponse,
    AzureTransportError,
    AzureUnknownOutcomeError,
    provider_usage,
)
from .azure_transport import AzureHttpImageTransport
from .azure_rate_limit import AzureRequestRateLimiter


class AzureConcurrencyLimiter:
    def __init__(self, maximum: int) -> None:
        self._semaphore = threading.BoundedSemaphore(max(1, int(maximum)))

    def acquire(self, timeout: Optional[float]) -> bool:
        if timeout is None:
            return self._semaphore.acquire()
        return self._semaphore.acquire(timeout=max(0.0, timeout))

    def release(self) -> None:
        self._semaphore.release()


class AzureRequestBudget:
    """Thread-safe, process-local cap on actual provider send attempts."""

    def __init__(self, maximum_requests: int) -> None:
        maximum = int(maximum_requests)
        if maximum <= 0:
            raise ValueError("Azure request budget must be positive.")
        self._limit = maximum
        self._consumed = 0
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def consumed(self) -> int:
        with self._lock:
            return self._consumed

    @property
    def remaining(self) -> int:
        with self._lock:
            return max(0, self._limit - self._consumed)

    def acquire(self) -> bool:
        with self._lock:
            if self._consumed >= self._limit:
                return False
            self._consumed += 1
            return True


class AzureGptImage2Provider:
    """Provider adapter with a fixed prompt and bounded Azure request policy."""

    def __init__(
        self,
        *,
        config: AzureGptImage2Config,
        transport: Optional[AzureImageTransport] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        random_fn: Callable[[], float] = random.random,
        limiter: Optional[AzureConcurrencyLimiter] = None,
        rate_limiter: Optional[AzureRequestRateLimiter] = None,
    ) -> None:
        self.config = config
        self.model_id = AZURE_GPT_IMAGE_2_MODEL_ID
        self.version = AZURE_GPT_IMAGE_2_VERSION
        self._transport = transport or AzureHttpImageTransport(config)
        self._sleep = sleep_fn
        self._random = random_fn
        self._limiter = limiter or AzureConcurrencyLimiter(config.max_concurrency)
        self._rate_limiter = rate_limiter or AzureRequestRateLimiter(config.requests_per_minute)

    def generate(
        self,
        *,
        source_image_bytes: bytes,
        source_content_type: str,
        prompt: str,
        idempotency_key: str,
        deadline_monotonic: Optional[float] = None,
        request_budget: Optional[AzureRequestBudget] = None,
    ) -> AzureGenerationResult:
        if prompt != AVATAR_GENERAL_PROMPT_V0_TEMP:
            raise AzureProviderError("azure_prompt_contract_mismatch")
        if not source_image_bytes:
            raise AzureProviderError("azure_source_image_empty")
        if source_content_type != "image/jpeg":
            raise AzureProviderError("azure_source_content_type_invalid")
        if not str(idempotency_key or "").strip():
            raise AzureProviderError("azure_idempotency_key_missing")

        remaining = None
        if deadline_monotonic is not None:
            remaining = max(0.0, deadline_monotonic - time.monotonic())
        if not self._limiter.acquire(remaining):
            raise AzureProviderError("azure_concurrency_limit_timeout", retryable=True)
        try:
            return self._generate_with_retry(
                source_image_bytes=source_image_bytes,
                source_content_type=source_content_type,
                prompt=prompt,
                deadline_monotonic=deadline_monotonic,
                request_budget=request_budget,
            )
        finally:
            self._limiter.release()

    def _generate_with_retry(
        self,
        *,
        source_image_bytes: bytes,
        source_content_type: str,
        prompt: str,
        deadline_monotonic: Optional[float],
        request_budget: Optional[AzureRequestBudget],
    ) -> AzureGenerationResult:
        started_at = time.perf_counter()
        attempts = 0
        last_status = 0
        while attempts < self.config.max_attempts:
            request = AzureImageEditRequest(
                source_image_bytes=source_image_bytes,
                source_content_type=source_content_type,
                prompt=prompt,
                deployment=self.config.deployment,
                api_version=self.config.api_version,
                quality=self.config.quality,
                size=self.config.size,
            )
            remaining = None
            if deadline_monotonic is not None:
                remaining = max(0.0, deadline_monotonic - time.monotonic())
            if not self._rate_limiter.acquire(remaining):
                raise AzureProviderError(
                    "azure_rate_limit_timeout",
                    retryable=True,
                    attempts=attempts,
                    provider_usage=provider_usage(attempts=attempts, outcome="failure"),
                )
            if request_budget is not None and not request_budget.acquire():
                raise AzureProviderError(
                    "azure_request_budget_exhausted",
                    retryable=False,
                    attempts=attempts,
                    provider_usage=provider_usage(attempts=attempts, outcome="failure"),
                )
            attempts += 1
            try:
                response = self._transport.send(request)
            except AzureTransportError as exc:
                if exc.request_sent:
                    raise AzureUnknownOutcomeError(attempts) from exc
                if attempts >= self.config.max_attempts:
                    raise AzureProviderError(
                        exc.error_code,
                        retryable=True,
                        attempts=attempts,
                        provider_usage=provider_usage(attempts=attempts, outcome="failure"),
                    ) from exc
                self._wait_before_retry(attempts, deadline_monotonic, retry_after=None)
                continue

            last_status = int(response.status_code)
            if 200 <= last_status < 300:
                image_bytes = _normalize_generated_image(response.payload)
                return AzureGenerationResult(
                    image_bytes=image_bytes,
                    audit=AzureGenerationAudit(
                        attempts=attempts,
                        latency_seconds=time.perf_counter() - started_at,
                        provider_status=last_status,
                        outcome="success",
                        output_format="png",
                        output_bytes=len(image_bytes),
                    ),
                )

            retry_after = _retry_after_seconds(response.headers)
            if last_status == 429 or 500 <= last_status <= 599:
                if attempts < self.config.max_attempts:
                    self._wait_before_retry(attempts, deadline_monotonic, retry_after=retry_after)
                    continue
                raise AzureProviderError(
                    "azure_rate_limited" if last_status == 429 else "azure_server_error",
                    retryable=True,
                    attempts=attempts,
                    provider_status=last_status,
                    provider_usage=provider_usage(attempts=attempts, outcome="failure"),
                )

            raise AzureProviderError(
                _error_code_for_status(last_status, response.payload),
                retryable=False,
                attempts=attempts,
                provider_status=last_status,
                provider_usage=provider_usage(attempts=attempts, outcome="failure"),
            )

        raise AzureProviderError(
            "azure_retry_exhausted",
            retryable=True,
            attempts=attempts,
            provider_status=last_status,
            provider_usage=provider_usage(attempts=attempts, outcome="failure"),
        )

    def _wait_before_retry(
        self,
        attempt: int,
        deadline_monotonic: Optional[float],
        *,
        retry_after: Optional[float],
    ) -> None:
        exponential = self.config.backoff_base_seconds * (2 ** max(0, attempt - 1))
        jitter = exponential * 0.25 * self._random()
        if retry_after is not None:
            # Retry-After is a provider instruction, not an exponential-backoff
            # hint. The worker deadline below is the upper safety bound.
            delay = max(0.0, retry_after)
        else:
            delay = min(
                self.config.max_backoff_seconds,
                max(0.0, exponential + jitter),
            )
        if deadline_monotonic is not None:
            remaining = max(0.0, deadline_monotonic - time.monotonic())
            if remaining <= delay:
                raise AzureProviderError(
                    "azure_retry_deadline_exceeded",
                    retryable=True,
                    attempts=attempt,
                    provider_usage=provider_usage(attempts=attempt, outcome="failure"),
                )
        self._sleep(delay)


def get_azure_gpt_image2_provider() -> AzureGptImage2Provider:
    return AzureGptImage2Provider(
        config=AzureGptImage2Config.from_env(require_credentials=True),
    )


def _normalize_generated_image(payload: Mapping[str, Any]) -> bytes:
    data = payload.get("data")
    if not isinstance(data, list) or not data or not isinstance(data[0], Mapping):
        raise AzureProviderError("azure_response_image_missing")
    encoded = data[0].get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        raise AzureProviderError("azure_response_b64_missing")
    try:
        raw = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            if image.width <= 0 or image.height <= 0 or max(image.size) > 3840:
                raise ValueError("invalid_output_dimensions")
            output = io.BytesIO()
            image.convert("RGBA" if "A" in image.getbands() else "RGB").save(output, format="PNG")
            normalized = output.getvalue()
    except Exception as exc:
        if isinstance(exc, AzureProviderError):
            raise
        raise AzureProviderError("azure_response_image_invalid") from exc
    if not normalized:
        raise AzureProviderError("azure_response_image_empty")
    return normalized


def _error_code_for_status(status_code: int, payload: Mapping[str, Any]) -> str:
    if status_code in {401, 403}:
        return "azure_auth_failed"
    if status_code in {400, 404, 409, 422}:
        raw_error = payload.get("error")
        if isinstance(raw_error, Mapping):
            code = str(raw_error.get("code") or "").strip().lower()
            if "content" in code or "policy" in code:
                return "azure_content_rejected"
        return "azure_invalid_request_or_configuration"
    return "azure_provider_http_error"


def _retry_after_seconds(headers: Mapping[str, str]) -> Optional[float]:
    for key, value in headers.items():
        if str(key).lower() != "retry-after":
            continue
        try:
            return max(0.0, float(str(value).strip()))
        except (TypeError, ValueError):
            return None
    return None


__all__ = [
    "AVATAR_GENERAL_PROMPT_V0_TEMP",
    "AVATAR_GENERAL_PROMPT_VERSION",
    "AZURE_GPT_IMAGE_2_MODEL_ID",
    "AZURE_GPT_IMAGE_2_VERSION",
    "AzureConfigurationError",
    "AzureConcurrencyLimiter",
    "AzureGenerationAudit",
    "AzureGenerationResult",
    "AzureGptImage2Config",
    "AzureGptImage2Provider",
    "AzureProviderError",
    "AzureProviderResponse",
    "AzureRequestBudget",
    "AzureRequestRateLimiter",
    "AzureTransportError",
    "AzureUnknownOutcomeError",
    "get_azure_gpt_image2_provider",
]
