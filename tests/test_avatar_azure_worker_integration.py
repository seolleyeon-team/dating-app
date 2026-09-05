from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.avatar_prompt_contract import (  # noqa: E402
    AVATAR_GENERAL_PROMPT_V0_TEMP,
)
from avatar_generation.model_adapters.azure_contracts import (  # noqa: E402
    AzureGenerationAudit,
    AzureGenerationResult,
    AZURE_GPT_IMAGE_2_MODEL_ID,
    AzureProviderError,
    AzureUnknownOutcomeError,
)
from avatar_generation.qa import AvatarQAResult  # noqa: E402
import avatar_generation.qa as qa_module  # noqa: E402
import avatar_generation.worker as worker_module  # noqa: E402
from avatar_generation.worker import (  # noqa: E402
    AvatarGenerationError,
    DEFAULT_AVATAR_TEMP_BUCKET,
    DEFAULT_SOURCE_PHOTO_BUCKET,
    process_avatar_generation_payload,
)
from tests.test_avatar_generation_worker import (  # noqa: E402
    _fake_firestore,
    _fake_storage,
    _payload,
)


def _generated_png_bytes() -> bytes:
    output = io.BytesIO()
    image = Image.new("RGB", (128, 128), color=(40, 90, 150))
    image.save(output, format="PNG")
    return output.getvalue()


class FakeAzureProvider:
    model_id = AZURE_GPT_IMAGE_2_MODEL_ID
    version = "gpt-image-2"

    def __init__(self) -> None:
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return AzureGenerationResult(
            image_bytes=_generated_png_bytes(),
            audit=AzureGenerationAudit(
                attempts=1,
                latency_seconds=0.001,
                provider_status=200,
                outcome="success",
                output_format="png",
                output_bytes=len(_generated_png_bytes()),
            ),
        )


def _passing_qa(_source_ref, _candidate_ref, metadata):
    return AvatarQAResult(
        adultQa="pass",
        childlikeRisk="low",
        privacyQa="pass",
        brandQa="pass",
        beautificationRisk="low",
        cropConsistency="pass",
        uniqueMarkCopyRisk="low",
        logoTextWatermarkRisk="low",
        identifiabilityRisk="low",
        previewAllowed=True,
        requiresHumanReview=False,
        qaVersion="azure_contract_test",
    )


def test_canonical_azure_worker_uses_storage_bytes_and_skips_legacy_generation_chain(monkeypatch):
    payload = _payload(job_id="azure_job_1")
    payload.update(
        {
            "modelId": AZURE_GPT_IMAGE_2_MODEL_ID,
            "candidateCount": 1,
        }
    )
    fs = _fake_firestore(payload)
    st = _fake_storage()
    source_bytes = st.buckets[DEFAULT_SOURCE_PHOTO_BUCKET].blobs[
        "users/u1/source/src_001.jpg"
    ].data
    provider = FakeAzureProvider()
    qa_metadata = []

    monkeypatch.setenv("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET)
    monkeypatch.setenv("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("AVATAR_WORKER_MODE", AZURE_GPT_IMAGE_2_MODEL_ID)
    monkeypatch.setattr(worker_module, "get_azure_gpt_image2_provider", lambda: provider)

    def record_qa(source_ref, candidate_ref, metadata):
        qa_metadata.append(metadata)
        assert isinstance(metadata["_source_image"], Image.Image)
        assert isinstance(metadata["_candidate_image"], Image.Image)
        return _passing_qa(source_ref, candidate_ref, metadata)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy generation prerequisite was called")

    for name in (
        "analyze_avatar_source_image",
        "_analyze_source_visual_risk",
        "_prepare_reference_preprocess_for_generation",
        "_extract_trait_card_for_generation",
        "prepare_privacy_reference_image",
    ):
        monkeypatch.setattr(worker_module, name, forbidden)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=record_qa,
        mode=AZURE_GPT_IMAGE_2_MODEL_ID,
    )

    assert result.status == "preview_ready"
    assert len(provider.calls) == 1
    assert provider.calls[0]["source_image_bytes"] == source_bytes
    assert provider.calls[0]["prompt"] == AVATAR_GENERAL_PROMPT_V0_TEMP
    assert qa_metadata
    assert "sourceAnalysis" not in qa_metadata[0]
    assert "referencePreprocess" not in qa_metadata[0]
    assert "sourceTraitCard" not in qa_metadata[0]
    assert qa_metadata[0]["sourceInputMode"] == "storage_normalized_original_direct"
    assert qa_metadata[0]["qaContract"] == "azure_post_generation_direct_source_v2_watermark_evidence"
    assert qa_metadata[0]["compareSourceVisualRisk"] is True
    generation_params = next(iter(fs.data["avatarCandidates"].values()))["generationParams"]
    assert generation_params["provider"] == "azure"
    assert generation_params["generationBackend"] == AZURE_GPT_IMAGE_2_MODEL_ID
    assert generation_params["preGenerationTransform"] == "none"
    assert generation_params["legacyFlux"] is False
    assert generation_params["legacyReferencePreprocessing"] is False
    assert generation_params["legacyTraitExtraction"] is False


def test_canonical_azure_initial_success_makes_exactly_two_provider_calls(monkeypatch):
    payload = _payload(job_id="azure_job_initial_two")
    payload.update(
        {
            "modelId": AZURE_GPT_IMAGE_2_MODEL_ID,
            "candidateCount": 2,
        }
    )
    fs = _fake_firestore(payload)
    st = _fake_storage()
    provider = FakeAzureProvider()
    source_bytes = st.buckets[DEFAULT_SOURCE_PHOTO_BUCKET].blobs[
        "users/u1/source/src_001.jpg"
    ].data
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setattr(worker_module, "get_azure_gpt_image2_provider", lambda: provider)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=_passing_qa,
        mode=AZURE_GPT_IMAGE_2_MODEL_ID,
    )

    assert result.status == "preview_ready"
    assert len(provider.calls) == 2
    assert all(call["source_image_bytes"] == source_bytes for call in provider.calls)


def test_canonical_azure_extra_round_stops_at_four_using_same_source(monkeypatch):
    payload = _payload(job_id="azure_job_extra_two")
    payload.update(
        {
            "modelId": AZURE_GPT_IMAGE_2_MODEL_ID,
            "candidateCount": 2,
        }
    )
    fs = _fake_firestore(payload)
    st = _fake_storage()
    provider = FakeAzureProvider()
    source_bytes = st.buckets[DEFAULT_SOURCE_PHOTO_BUCKET].blobs[
        "users/u1/source/src_001.jpg"
    ].data
    qa_calls = []

    def only_one_initial_candidate_is_safe(source_ref, candidate_ref, metadata):
        qa_calls.append(metadata["candidateId"])
        if len(qa_calls) == 2:
            return AvatarQAResult(
                adultQa="fail",
                privacyQa="fail",
                brandQa="fail",
                previewAllowed=False,
                requiresHumanReview=False,
                rejectReasons=["simulation_rejected"],
                qaVersion="azure_contract_test_reject",
            )
        return _passing_qa(source_ref, candidate_ref, metadata)

    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setattr(worker_module, "get_azure_gpt_image2_provider", lambda: provider)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=only_one_initial_candidate_is_safe,
        mode=AZURE_GPT_IMAGE_2_MODEL_ID,
    )

    assert result.status == "preview_ready"
    assert len(provider.calls) == 4
    assert all(call["source_image_bytes"] == source_bytes for call in provider.calls)
    plan = fs.data["avatarJobs"][payload["jobId"]]["generationPlan"]
    assert plan["initialCount"] == 2
    assert plan["extraCount"] == 2
    assert plan["totalGenerated"] == 4


def test_azure_canonical_qa_compares_storage_source_directly_without_reference_placeholder(monkeypatch):
    source = Image.new("RGB", (128, 128), color=(10, 70, 140))
    candidate = Image.new("RGB", (128, 128), color=(180, 70, 30))
    monkeypatch.setattr(qa_module, "_is_production_environment", lambda: True)

    result = qa_module.run_avatar_candidate_qa(
        "gs://private/source.jpg",
        "gs://private/candidate.png",
        {
            "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
            "sourceInputMode": "storage_normalized_original_direct",
            "_source_image": source,
            "_candidate_image": candidate,
        },
    )

    assert "analysis_reference_image_unavailable" not in result.reviewReasons


def test_azure_qa_declaration_does_not_become_watermark_signal():
    refs = ["gs://private/source.jpg", "gs://private/candidate.png"]

    assert qa_module._contains_text_watermark_marker(
        {"qaChecks": {"postGeneration": ["brand_and_watermark"]}},
        refs,
    ) is False
    assert qa_module._contains_text_watermark_marker(
        {"qaSignals": {"logoTextWatermarkDetected": True}},
        refs,
    ) is True


def test_duplicate_azure_delivery_observes_provider_inflight_claim_without_second_call(monkeypatch):
    payload = _payload(job_id="azure_job_inflight")
    payload.update(
        {
            "modelId": AZURE_GPT_IMAGE_2_MODEL_ID,
            "candidateCount": 1,
        }
    )
    fs = _fake_firestore(payload)
    fs.data["avatarJobs"][payload["jobId"]].update(
        {
            "status": "provider_inflight",
            "generationBackend": AZURE_GPT_IMAGE_2_MODEL_ID,
        }
    )
    provider = FakeAzureProvider()
    monkeypatch.setenv("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET)
    monkeypatch.setenv("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("AVATAR_WORKER_MODE", AZURE_GPT_IMAGE_2_MODEL_ID)
    monkeypatch.setattr(worker_module, "get_azure_gpt_image2_provider", lambda: provider)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode=AZURE_GPT_IMAGE_2_MODEL_ID,
    )

    assert result.status == "provider_inflight"
    assert provider.calls == []


def test_retryable_azure_failure_releases_claim_for_cloud_tasks_redelivery(monkeypatch):
    payload = _payload(job_id="azure_job_retryable_redelivery")
    payload.update(
        {
            "modelId": AZURE_GPT_IMAGE_2_MODEL_ID,
            "candidateCount": 1,
        }
    )
    fs = _fake_firestore(payload)

    class RetryableOnceProvider(FakeAzureProvider):
        def generate(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                raise AzureProviderError("azure_connect_error", retryable=True, attempts=1)
            return AzureGenerationResult(
                image_bytes=_generated_png_bytes(),
                audit=AzureGenerationAudit(
                    attempts=1,
                    latency_seconds=0.001,
                    provider_status=200,
                    outcome="success",
                    output_format="png",
                    output_bytes=len(_generated_png_bytes()),
                ),
            )

    provider = RetryableOnceProvider()
    monkeypatch.setenv("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET)
    monkeypatch.setenv("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("AVATAR_WORKER_MODE", AZURE_GPT_IMAGE_2_MODEL_ID)
    monkeypatch.setattr(worker_module, "get_azure_gpt_image2_provider", lambda: provider)

    with pytest.raises(Exception):
        process_avatar_generation_payload(
            payload,
            firestore_client=fs,
            storage_client=_fake_storage(),
            qa_runner=_passing_qa,
            mode=AZURE_GPT_IMAGE_2_MODEL_ID,
        )

    failed_job = fs.data["avatarJobs"][payload["jobId"]]
    assert failed_job["status"] == "failed"
    assert failed_job["retryable"] is True
    assert failed_job["generationClaim"]["state"] == "failed"

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode=AZURE_GPT_IMAGE_2_MODEL_ID,
    )

    assert result.status == "preview_ready"
    assert len(provider.calls) == 2


def test_azure_worker_rejects_non_jpeg_source_bytes_before_provider(monkeypatch):
    payload = _payload(job_id="azure_job_non_jpeg_source")
    payload.update(
        {
            "modelId": AZURE_GPT_IMAGE_2_MODEL_ID,
            "candidateCount": 1,
        }
    )
    fs = _fake_firestore(payload)
    st = _fake_storage()
    st.buckets[DEFAULT_SOURCE_PHOTO_BUCKET].blobs[
        "users/u1/source/src_001.jpg"
    ].data = _generated_png_bytes()

    monkeypatch.setenv("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET)
    monkeypatch.setenv("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("AVATAR_WORKER_MODE", AZURE_GPT_IMAGE_2_MODEL_ID)

    def provider_must_not_be_constructed():
        raise AssertionError("provider must not be constructed for non-JPEG source bytes")

    monkeypatch.setattr(
        worker_module,
        "get_azure_gpt_image2_provider",
        provider_must_not_be_constructed,
    )

    with pytest.raises(AvatarGenerationError, match="azure_source_not_normalized_jpeg"):
        process_avatar_generation_payload(
            payload,
            firestore_client=fs,
            storage_client=st,
            qa_runner=_passing_qa,
            mode=AZURE_GPT_IMAGE_2_MODEL_ID,
        )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "failed"
    assert job["generationClaim"]["state"] == "failed"


def test_azure_post_send_unknown_outcome_is_review_and_never_blindly_retried(monkeypatch):
    payload = _payload(job_id="azure_job_unknown_outcome")
    payload.update(
        {
            "modelId": AZURE_GPT_IMAGE_2_MODEL_ID,
            "candidateCount": 1,
        }
    )
    fs = _fake_firestore(payload)

    class UnknownOutcomeProvider:
        model_id = AZURE_GPT_IMAGE_2_MODEL_ID
        version = "gpt-image-2"

        def __init__(self):
            self.calls = 0

        def generate(self, **_kwargs):
            self.calls += 1
            raise AzureUnknownOutcomeError(attempts=1)

    provider = UnknownOutcomeProvider()
    monkeypatch.setenv("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET)
    monkeypatch.setenv("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setenv("AVATAR_WORKER_MODE", AZURE_GPT_IMAGE_2_MODEL_ID)
    monkeypatch.setattr(worker_module, "get_azure_gpt_image2_provider", lambda: provider)

    with pytest.raises(Exception):
        process_avatar_generation_payload(
            payload,
            firestore_client=fs,
            storage_client=_fake_storage(),
            qa_runner=_passing_qa,
            mode=AZURE_GPT_IMAGE_2_MODEL_ID,
        )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert provider.calls == 1
    assert job["status"] == "needs_review"
    assert job["errorCode"] == "azure_unknown_post_send_outcome"
    assert job["retryable"] is False
    assert job["providerUsage"]["unknownOutcomeCount"] == 1


def test_legacy_local_dry_run_does_not_emit_azure_provider_usage(monkeypatch):
    payload = _payload(job_id="legacy_dry_run_no_azure_usage")
    fs = _fake_firestore(payload)
    monkeypatch.setenv("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET)
    monkeypatch.setenv("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET)
    monkeypatch.setenv("ENVIRONMENT", "local")

    process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert "providerUsage" not in job
    assert job["generationBackend"] == "dry_run_fixture"


def test_existing_avatar_media_normalized_jpeg_is_the_direct_azure_source(monkeypatch):
    payload = _payload(job_id="azure_normalized_jpeg_source")
    payload.update(
        {
            "modelId": AZURE_GPT_IMAGE_2_MODEL_ID,
            "candidateCount": 1,
        }
    )
    fs = _fake_firestore(payload)
    st = _fake_storage()
    jpeg_output = io.BytesIO()
    Image.new("RGB", (48, 48), color=(120, 80, 40)).save(jpeg_output, format="JPEG", quality=91)
    normalized_jpeg = jpeg_output.getvalue()
    st.buckets[DEFAULT_SOURCE_PHOTO_BUCKET].blobs[
        "users/u1/source/src_001.jpg"
    ].data = normalized_jpeg
    provider = FakeAzureProvider()
    monkeypatch.setenv("SOURCE_PHOTO_BUCKET", DEFAULT_SOURCE_PHOTO_BUCKET)
    monkeypatch.setenv("AVATAR_TEMP_BUCKET", DEFAULT_AVATAR_TEMP_BUCKET)
    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setattr(worker_module, "get_azure_gpt_image2_provider", lambda: provider)

    process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=_passing_qa,
        mode=AZURE_GPT_IMAGE_2_MODEL_ID,
    )

    assert provider.calls[0]["source_image_bytes"] == normalized_jpeg
    assert provider.calls[0]["source_content_type"] == "image/jpeg"
