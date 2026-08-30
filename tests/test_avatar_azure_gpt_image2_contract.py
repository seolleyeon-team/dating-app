from __future__ import annotations

import base64
import io
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.model_adapters.azure_gpt_image_2 import (  # noqa: E402
    AVATAR_GENERAL_PROMPT_V0_TEMP,
    AVATAR_GENERAL_PROMPT_VERSION,
    AzureGptImage2Config,
    AzureGptImage2Provider,
    AzureProviderResponse,
    AzureRequestBudget,
    AzureTransportError,
    AzureUnknownOutcomeError,
)
from avatar_generation.model_adapters.azure_rate_limit import AzureRequestRateLimiter  # noqa: E402


def _image_bytes(*, format: str = "JPEG", color: tuple[int, int, int] = (30, 60, 90)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (64, 48), color=color).save(output, format=format)
    return output.getvalue()


def _config(**overrides: object) -> AzureGptImage2Config:
    values = {
        "endpoint": "https://test-resource.openai.azure.com",
        "deployment": "test-deployment",
        "api_version": "test-api-version",
        "api_key": "TEST_AZURE_SECRET_DO_NOT_LEAK_123",
        "max_attempts": 3,
        "backoff_base_seconds": 0.0,
        "max_backoff_seconds": 0.0,
        "max_concurrency": 2,
        "requests_per_minute": 120,
    }
    values.update(overrides)
    return AzureGptImage2Config(**values)


class RecordingTransport:
    def __init__(self, responses: list[AzureProviderResponse | Exception]) -> None:
        self.responses = list(responses)
        self.requests = []

    def send(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _success_response() -> AzureProviderResponse:
    return AzureProviderResponse(
        status_code=200,
        headers={},
        payload={"data": [{"b64_json": base64.b64encode(_image_bytes(format="PNG")).decode("ascii")}]},
    )


def test_provider_sends_storage_bytes_and_exact_general_prompt_without_prompt_suffixes():
    source_bytes = _image_bytes()
    transport = RecordingTransport([_success_response()])
    provider = AzureGptImage2Provider(config=_config(), transport=transport)

    result = provider.generate(
        source_image_bytes=source_bytes,
        source_content_type="image/jpeg",
        prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
        idempotency_key="job-1:candidate-1",
    )

    request = transport.requests[0]
    assert request.source_image_bytes is source_bytes
    assert request.prompt == (
        "레퍼런스 정면 사진의 인물과 얼굴 특징과 인상을 최대한 동일하게 유지한 2D 아바타를 생성한다.\n\n"
        "스타일은 깔끔한 Live2D 애니메이션 텍스처 스타일로, 자연스러운 애니메이션풍 얼굴 비율, 선명하고 정돈된 라인, "
        "부드러운 셀 셰이딩과 은은한 입체감, 매끈한 피부 표현을 사용한다. 과도한 미화나 눈 확대, 얼굴형 변형은 하지 않는다.\n\n"
        "헤어스타일, 머리색, 눈·코·입 형태, 얼굴형, 피부톤, 의상과 전체적인 인상을 레퍼런스와 충실하게 유지한다.\n\n"
        "정면·눈높이 시점, 가슴 위까지 보이는 중앙 구도, 자연스러운 무표정, 단색 밝은 아이보리 배경.\n\n"
        "표정 시트, 분리 파츠, 텍스트, 장식, 소품은 넣지 않고 완성된 아바타 1명만 출력한다."
    )
    assert request.prompt == AVATAR_GENERAL_PROMPT_V0_TEMP
    assert "negative" not in request.prompt.lower()
    assert "trait" not in request.prompt.lower()
    assert result.audit.prompt_version == AVATAR_GENERAL_PROMPT_VERSION
    assert result.audit.source_input_mode == "storage_normalized_original_direct"
    assert "TEST_AZURE_SECRET_DO_NOT_LEAK_123" not in repr(result)


def test_provider_normalizes_only_the_generated_result_to_png():
    transport = RecordingTransport([_success_response()])
    provider = AzureGptImage2Provider(config=_config(), transport=transport)

    result = provider.generate(
        source_image_bytes=_image_bytes(),
        source_content_type="image/jpeg",
        prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
        idempotency_key="job-1:candidate-1",
    )

    with Image.open(io.BytesIO(result.image_bytes)) as image:
        assert image.format == "PNG"
        assert image.size == (64, 48)
    assert result.audit.output_format == "png"


def test_provider_requires_the_existing_normalized_jpeg_source_contract():
    transport = RecordingTransport([_success_response()])
    provider = AzureGptImage2Provider(config=_config(), transport=transport)

    with pytest.raises(Exception, match="source_content_type_invalid"):
        provider.generate(
            source_image_bytes=_image_bytes(format="WEBP"),
            source_content_type="image/webp",
            prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
            idempotency_key="job-1:candidate-webp",
        )

    assert transport.requests == []


def test_provider_retries_only_bounded_429_and_5xx_responses():
    retry_429 = AzureProviderResponse(status_code=429, headers={"Retry-After": "0"}, payload={})
    retry_500 = AzureProviderResponse(status_code=500, headers={}, payload={})
    transport = RecordingTransport([retry_429, retry_500, _success_response()])
    provider = AzureGptImage2Provider(config=_config(max_attempts=3), transport=transport)

    result = provider.generate(
        source_image_bytes=_image_bytes(),
        source_content_type="image/jpeg",
        prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
        idempotency_key="job-1:candidate-1",
    )

    assert result.audit.attempts == 3
    assert len(transport.requests) == 3


def test_provider_honors_retry_after_even_when_backoff_cap_is_lower():
    clock = FakeClock()
    transport = RecordingTransport(
        [
            AzureProviderResponse(status_code=429, headers={"Retry-After": "5"}, payload={}),
            _success_response(),
        ]
    )
    provider = AzureGptImage2Provider(
        config=_config(max_backoff_seconds=1.0),
        transport=transport,
        sleep_fn=clock.sleep,
        random_fn=lambda: 0.0,
    )

    provider.generate(
        source_image_bytes=_image_bytes(),
        source_content_type="image/jpeg",
        prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
        idempotency_key="job-1:candidate-retry-after",
    )

    assert clock.sleeps == [5.0]


def test_shared_request_budget_caps_internal_retries_before_extra_send():
    clock = FakeClock()
    transport = RecordingTransport(
        [
            AzureProviderResponse(status_code=429, headers={"Retry-After": "5"}, payload={}),
            _success_response(),
        ]
    )
    provider = AzureGptImage2Provider(
        config=_config(max_attempts=3),
        transport=transport,
        sleep_fn=clock.sleep,
        random_fn=lambda: 0.0,
    )
    budget = AzureRequestBudget(1)

    with pytest.raises(Exception) as caught:
        provider.generate(
            source_image_bytes=_image_bytes(),
            source_content_type="image/jpeg",
            prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
            idempotency_key="job-1:candidate-budgeted-retry",
            request_budget=budget,
        )

    assert caught.value.error_code == "azure_request_budget_exhausted"
    assert len(transport.requests) == 1
    assert clock.sleeps == [5.0]
    assert budget.limit == 1
    assert budget.consumed == 1
    assert budget.remaining == 0


def test_request_budget_is_shared_across_logical_candidate_calls():
    transport = RecordingTransport([_success_response(), _success_response(), _success_response()])
    provider = AzureGptImage2Provider(
        config=_config(max_attempts=1),
        transport=transport,
    )
    budget = AzureRequestBudget(2)

    for index in range(2):
        provider.generate(
            source_image_bytes=_image_bytes(),
            source_content_type="image/jpeg",
            prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
            idempotency_key=f"job-1:candidate-budget-{index}",
            request_budget=budget,
        )

    with pytest.raises(Exception) as caught:
        provider.generate(
            source_image_bytes=_image_bytes(),
            source_content_type="image/jpeg",
            prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
            idempotency_key="job-1:candidate-budget-overflow",
            request_budget=budget,
        )

    assert caught.value.error_code == "azure_request_budget_exhausted"
    assert len(transport.requests) == 2
    assert budget.consumed == 2


def test_provider_does_not_retry_auth_or_invalid_request():
    transport = RecordingTransport(
        [AzureProviderResponse(status_code=401, headers={}, payload={"error": {"code": "auth"}})]
    )
    provider = AzureGptImage2Provider(config=_config(), transport=transport)

    with pytest.raises(Exception) as caught:
        provider.generate(
            source_image_bytes=_image_bytes(),
            source_content_type="image/jpeg",
            prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
            idempotency_key="job-1:candidate-1",
        )

    assert len(transport.requests) == 1
    assert "TEST_AZURE_SECRET_DO_NOT_LEAK_123" not in str(caught.value)


def test_azure_config_and_provider_errors_are_secret_free():
    config = _config()
    assert "TEST_AZURE_SECRET_DO_NOT_LEAK_123" not in repr(config)
    assert "TEST_AZURE_SECRET_DO_NOT_LEAK_123" not in repr(config.safe_dict())

    transport = RecordingTransport(
        [
            AzureProviderResponse(
                status_code=400,
                headers={"x-request-id": "request-id-only"},
                payload={
                    "error": {
                        "code": "invalid_request",
                        "message": "TEST_AZURE_SECRET_DO_NOT_LEAK_123",
                    }
                },
            )
        ]
    )
    provider = AzureGptImage2Provider(config=config, transport=transport)
    with pytest.raises(Exception) as caught:
        provider.generate(
            source_image_bytes=_image_bytes(),
            source_content_type="image/jpeg",
            prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
            idempotency_key="job-1:candidate-secret",
        )
    assert "TEST_AZURE_SECRET_DO_NOT_LEAK_123" not in str(caught.value)
    assert "TEST_AZURE_SECRET_DO_NOT_LEAK_123" not in repr(caught.value)


def test_post_send_timeout_becomes_bounded_unknown_outcome_without_blind_retry():
    transport = RecordingTransport([AzureTransportError("timeout", request_sent=True)])
    provider = AzureGptImage2Provider(config=_config(max_attempts=5), transport=transport)

    with pytest.raises(AzureUnknownOutcomeError) as caught:
        provider.generate(
            source_image_bytes=_image_bytes(),
            source_content_type="image/jpeg",
            prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
            idempotency_key="job-1:candidate-1",
        )

    assert len(transport.requests) == 1
    assert caught.value.unknown_outcome is True


@dataclass
class SlowTransport:
    active: int = 0
    max_active: int = 0
    lock: threading.Lock = threading.Lock()

    def send(self, request):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.01)
            return _success_response()
        finally:
            with self.lock:
                self.active -= 1


def test_provider_limits_concurrent_azure_calls():
    transport = SlowTransport()
    provider = AzureGptImage2Provider(config=_config(max_concurrency=2), transport=transport)
    errors: list[Exception] = []

    def run(index: int) -> None:
        try:
            provider.generate(
                source_image_bytes=_image_bytes(color=(index, 60, 90)),
                source_content_type="image/jpeg",
                prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
                idempotency_key=f"job-1:candidate-{index}",
            )
        except Exception as exc:  # pragma: no cover - assertion below reports unexpected errors
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert transport.max_active <= 2


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.mark.parametrize(
    ("request_count", "expected_starts", "expected_sleeps"),
    [
        (4, [0.0, 30.0, 60.0, 90.0], [30.0, 30.0, 30.0]),
        (8, [0.0, 30.0, 60.0, 90.0, 120.0, 150.0, 180.0, 210.0], [30.0] * 7),
    ],
)
def test_two_rpm_limiter_schedule_covers_four_and_eight_candidate_requests(
    request_count, expected_starts, expected_sleeps
):
    clock = FakeClock()
    limiter = AzureRequestRateLimiter(
        maximum_requests=2,
        window_seconds=60.0,
        clock_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )

    starts = []
    for _ in range(request_count):
        assert limiter.acquire(timeout=1500.0) is True
        starts.append(clock.now)

    assert starts == expected_starts
    assert clock.sleeps == expected_sleeps


def test_provider_paces_two_requests_per_minute_before_third_request():
    clock = FakeClock()
    transport = RecordingTransport([_success_response(), _success_response(), _success_response()])
    limiter = AzureRequestRateLimiter(
        maximum_requests=2,
        window_seconds=60.0,
        clock_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )
    provider = AzureGptImage2Provider(
        config=_config(requests_per_minute=2),
        transport=transport,
        rate_limiter=limiter,
    )

    for index in range(3):
        provider.generate(
            source_image_bytes=_image_bytes(),
            source_content_type="image/jpeg",
            prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
            idempotency_key=f"job-1:candidate-{index}",
        )

    assert len(transport.requests) == 3
    assert clock.sleeps == [30.0, 30.0]


def test_retry_attempts_use_the_same_paced_limiter():
    clock = FakeClock()
    limiter = AzureRequestRateLimiter(
        maximum_requests=2,
        window_seconds=60.0,
        clock_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )
    transport = RecordingTransport(
        [
            AzureProviderResponse(status_code=429, headers={"Retry-After": "0"}, payload={}),
            _success_response(),
        ]
    )
    provider = AzureGptImage2Provider(
        config=_config(max_attempts=2, requests_per_minute=2),
        transport=transport,
        sleep_fn=clock.sleep,
        rate_limiter=limiter,
    )

    provider.generate(
        source_image_bytes=_image_bytes(),
        source_content_type="image/jpeg",
        prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
        idempotency_key="job-1:candidate-retry-paced",
    )

    assert len(transport.requests) == 2
    assert clock.sleeps == [0.0, 30.0]


def test_limiter_fails_closed_when_deadline_cannot_reach_next_paced_start():
    clock = FakeClock()
    limiter = AzureRequestRateLimiter(
        maximum_requests=2,
        window_seconds=60.0,
        clock_fn=clock.monotonic,
        sleep_fn=clock.sleep,
    )

    assert limiter.acquire() is True
    assert limiter.acquire(timeout=30.0) is False
    assert limiter.acquire(timeout=40.0) is True
    assert limiter.acquire(timeout=10.0) is False
    assert clock.sleeps == [30.0]


def test_limiter_releases_lock_when_wait_is_cancelled():
    class Cancelled(Exception):
        pass

    clock = FakeClock()

    def cancelled_sleep(_seconds):
        raise Cancelled()

    limiter = AzureRequestRateLimiter(
        maximum_requests=2,
        window_seconds=60.0,
        clock_fn=clock.monotonic,
        sleep_fn=cancelled_sleep,
    )

    assert limiter.acquire() is True
    with pytest.raises(Cancelled):
        limiter.acquire(timeout=40.0)
    assert limiter.acquire(timeout=0.0) is False
