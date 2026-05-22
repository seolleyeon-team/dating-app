import base64
import io
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.model_adapters.base import AvatarGenerationRequest
from avatar_generation.model_adapters.flux2_klein import Flux2KleinAdapter
from avatar_generation.qa import AvatarQAResult
from avatar_generation.seolleyeon_avatar_prompt_builder_v4 import (
    AvatarTraitCard as PromptAvatarTraitCard,
    build_avatar_prompt,
)
from avatar_generation.worker import (
    AvatarGenerationError,
    Flux2KleinImageGenerator,
    build_flux_prompt_with_avoid,
    candidate_id_for,
    call_flux_pipeline_safely,
    decode_task_payload,
    deterministic_seed,
    model_cache_metrics,
    parse_avatar_generation_payload,
    prepare_privacy_reference_image,
    process_avatar_generation_batch_payload,
    process_avatar_generation_drain,
    process_avatar_generation_payload,
    reset_model_cache_for_tests,
    resolve_worker_mode,
)
from avatar_generation.job_lease import AvatarJobLeaseConfig, ClaimDeadline


class FakeSnapshot:
    def __init__(self, data, doc_id=""):
        self._data = data
        self.exists = data is not None
        self.id = doc_id

    def to_dict(self):
        return dict(self._data or {})


class FakeDocRef:
    def __init__(self, store, collection, doc_id):
        self.store = store
        self.collection = collection
        self.doc_id = doc_id

    def get(self):
        return FakeSnapshot(self.store.get(self.collection, {}).get(self.doc_id), self.doc_id)

    def set(self, data, merge=True):
        collection = self.store.setdefault(self.collection, {})
        if merge and self.doc_id in collection:
            collection[self.doc_id].update(data)
        else:
            collection[self.doc_id] = dict(data)

    def update(self, data):
        self.set(data, merge=True)


class FakeCollection:
    def __init__(self, store, name):
        self.store = store
        self.name = name

    def document(self, doc_id):
        return FakeDocRef(self.store, self.name, doc_id)

    def stream(self):
        for doc_id, data in self.store.get(self.name, {}).items():
            yield FakeSnapshot(data, doc_id)


class FakeFirestore:
    def __init__(self, data):
        self.data = data

    def collection(self, name):
        return FakeCollection(self.data, name)


class FakeBlob:
    def __init__(self, data=b""):
        self.data = data
        self.cache_control = None

    def exists(self):
        return bool(self.data)

    def download_as_bytes(self):
        return self.data

    def upload_from_string(self, data, **_kwargs):
        self.data = data

    def patch(self):
        return None


class FakeBucket:
    def __init__(self, blobs):
        self.blobs = blobs

    def blob(self, path):
        return self.blobs.setdefault(path, FakeBlob())


class FakeStorage:
    def __init__(self, buckets):
        self.buckets = buckets

    def bucket(self, name):
        return self.buckets.setdefault(name, FakeBucket({}))


def _png_bytes(color=(128, 96, 80)):
    out = io.BytesIO()
    Image.new("RGB", (32, 32), color=color).save(out, format="PNG")
    return out.getvalue()


def _payload(job_id="avatar_job_1", uid="u1"):
    return {
        "jobId": job_id,
        "uid": uid,
        "sourcePhotoIds": ["src_001"],
        "sourcePhotoRefs": [
            "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg"
        ],
        "candidateCount": 4,
        "modelId": "black-forest-labs/FLUX.2-klein-4B",
        "jobType": "avatar_generation",
        "schemaVersion": "avatar_job_v1",
        "idempotencyKey": "u1:src_001:avatar_generation_v1",
    }


def _fake_firestore(payload=None):
    payload = payload or _payload()
    return FakeFirestore(
        {
            "avatarJobs": {
                payload["jobId"]: {
                    "jobId": payload["jobId"],
                    "uid": payload["uid"],
                    "status": "queued",
                    "sourcePhotoIds": list(payload["sourcePhotoIds"]),
                    "sourcePhotoRefs": list(payload["sourcePhotoRefs"]),
                    "candidateCount": payload["candidateCount"],
                    "modelId": payload["modelId"],
                    "jobType": payload["jobType"],
                    "schemaVersion": payload["schemaVersion"],
                    "idempotencyKey": payload["idempotencyKey"],
                }
            },
            "userPrivateMedia": {
                payload["uid"]: {
                    "photoConsent": {
                        "avatarGeneration": True,
                        "profileDisplayOriginalPhoto": False,
                    },
                    "sourcePhotos": [
                        {
                            "gcsUri": payload["sourcePhotoRefs"][0],
                            "status": "active",
                            "purpose": {"avatarGeneration": True},
                        }
                    ],
                }
            },
            "avatarCandidates": {},
        }
    )


def _fake_storage():
    return FakeStorage(
        {
            "seolleyeon-private-source-photos": FakeBucket(
                {"users/u1/source/src_001.jpg": FakeBlob(_png_bytes())}
            ),
            "seolleyeon-avatar-temp": FakeBucket({}),
        }
    )


def _passing_qa(_source_ref, _candidate_ref, _metadata):
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
        qaVersion="test_pass",
    )


def _rejecting_qa(_source_ref, _candidate_ref, _metadata):
    return AvatarQAResult(
        adultQa="fail",
        privacyQa="fail",
        brandQa="fail",
        previewAllowed=False,
        requiresHumanReview=False,
        rejectReasons=["too_identifiable"],
        qaVersion="test_reject",
    )


def _needs_review_qa(_source_ref, _candidate_ref, _metadata):
    return AvatarQAResult(
        adultQa="needs_review",
        childlikeRisk="medium",
        privacyQa="needs_review",
        brandQa="needs_review",
        beautificationRisk="medium",
        cropConsistency="needs_review",
        uniqueMarkCopyRisk="unknown",
        logoTextWatermarkRisk="medium",
        identifiabilityRisk="medium",
        previewAllowed=False,
        requiresHumanReview=True,
        qaVersion="test_needs_review",
    )


class FakeFluxGenerator:
    def __init__(self):
        self.calls = []

    def generate(self, *, source_image, prompt, avoid_prompt, seed):
        self.calls.append(
            {
                "source_size": source_image.size,
                "prompt": prompt,
                "avoid_prompt": avoid_prompt,
                "seed": seed,
            }
        )
        return Image.new("RGB", (16, 16), color=(seed % 255, 80, 120))


def test_decode_pubsub_avatar_generation_payload():
    encoded = base64.b64encode(json.dumps(_payload()).encode("utf-8")).decode("ascii")
    assert decode_task_payload({"message": {"data": encoded}})["schemaVersion"] == "avatar_job_v1"


def test_payload_rejects_non_private_source_bucket():
    payload = _payload()
    payload["sourcePhotoRefs"] = ["gs://wrong-bucket/users/u/source/src.jpg"]
    with pytest.raises(AvatarGenerationError, match="bucket"):
        parse_avatar_generation_payload(payload)


def test_payload_rejects_source_ref_for_different_uid():
    payload = _payload(uid="u2")
    payload["sourcePhotoRefs"] = [
        "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg"
    ]

    with pytest.raises(AvatarGenerationError, match="uid"):
        parse_avatar_generation_payload(payload)


def test_candidate_seed_and_id_are_deterministic():
    assert candidate_id_for("avatar_job_1", 0) == "cand_avatar_job_1_01"
    assert deterministic_seed("avatar_job_1", 0) == deterministic_seed("avatar_job_1", 0)
    assert deterministic_seed("avatar_job_1", 0) != deterministic_seed("avatar_job_1", 1)


def test_prompt_contains_privacy_and_not_beautified_constraints():
    prompt = build_avatar_prompt()
    positive = prompt.positive.lower()
    negative = prompt.negative.lower()
    assert "privacy-preserving" in positive
    assert "not exact identity" in positive
    assert "ordinary adult university student" in positive
    assert "not beautified" in positive
    assert "exact biometric face copy" in negative
    assert "beauty upgrade" in negative


def test_prompt_uses_user_provided_gender_as_broad_presentation_only():
    prompt = build_avatar_prompt(
        trait_card=PromptAvatarTraitCard(avatar_presentation_gender="female")
    )
    positive = prompt.positive.lower()

    assert "user-provided onboarding gender" in positive
    assert "ordinary adult female university student" in positive
    assert "do not infer gender from the face" in positive


def test_flux_prompt_folds_negative_terms_into_avoid_block():
    prompt = build_avatar_prompt()

    final_prompt = build_flux_prompt_with_avoid(prompt.positive, prompt.negative)
    lowered = final_prompt.lower()

    assert "privacy-preserving adult 3d avatar" in lowered
    assert "ordinary adult university student" in lowered
    assert "not beautified" in lowered
    assert "\navoid:\n" in lowered
    assert "photorealistic clone" in lowered
    assert "exact biometric face copy" in lowered
    assert "face-recognition likeness" in lowered
    assert "idol" in lowered
    assert "beauty upgrade" in lowered
    assert "babyface" in lowered
    assert "logo" in lowered
    assert "watermark" in lowered


def test_call_flux_pipeline_safely_filters_unsupported_kwargs():
    calls = []

    class FakePipeline:
        def __call__(self, *, prompt, image, width, height, generator):
            calls.append(
                {
                    "prompt": prompt,
                    "image": image,
                    "width": width,
                    "height": height,
                    "generator": generator,
                }
            )
            return "ok"

    result = call_flux_pipeline_safely(
        FakePipeline(),
        prompt="prompt",
        image=object(),
        width=1024,
        height=1024,
        generator=object(),
        negative_prompt="must be dropped",
        unsupported_private_ref="gs://private/source.jpg",
    )

    assert result == "ok"
    assert calls
    assert "negative_prompt" not in calls[0]
    assert "unsupported_private_ref" not in calls[0]


def test_flux_adapter_generate_candidates_uses_real_generation_path():
    payload = _payload()
    generator = FakeFluxGenerator()
    adapter = Flux2KleinAdapter(
        storage_client=_fake_storage(),
        image_generator=generator,
    )

    candidates = adapter.generate_candidates(
        AvatarGenerationRequest(
            job_id=payload["jobId"],
            uid=payload["uid"],
            source_photo_refs=payload["sourcePhotoRefs"],
        )
    )

    assert [candidate.candidate_id for candidate in candidates] == [
        "cand_01",
        "cand_02",
        "cand_03",
        "cand_04",
    ]
    assert len(generator.calls) == 4
    assert all("privacy-preserving" in call["prompt"] for call in generator.calls)
    assert all("beauty upgrade" in call["avoid_prompt"] for call in generator.calls)
    assert candidates[0].image_ref.startswith("gs://seolleyeon-avatar-temp/")


def test_missing_flux2_klein_pipeline_fails_fast(monkeypatch):
    fake_torch = types.ModuleType("torch")
    fake_torch.bfloat16 = object()
    fake_torch.float32 = object()
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "diffusers", types.ModuleType("diffusers"))

    with pytest.raises(AvatarGenerationError, match="Flux2KleinPipeline is unavailable"):
        Flux2KleinImageGenerator()._load_pipeline()


def test_flux2_klein_generate_does_not_pass_text_negative_prompt(monkeypatch):
    class FakeGenerator:
        def __init__(self, device):
            self.device = device

        def manual_seed(self, seed):
            self.seed = seed
            return self

    fake_torch = types.ModuleType("torch")
    fake_torch.Generator = FakeGenerator
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    calls = []

    class FakePipeline:
        def __call__(self, *, prompt, image, width, height, num_inference_steps, guidance_scale, generator):
            kwargs = {
                "prompt": prompt,
                "image": image,
                "width": width,
                "height": height,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "generator": generator,
            }
            calls.append(kwargs)
            return types.SimpleNamespace(images=[Image.new("RGB", (16, 16))])

    generator = Flux2KleinImageGenerator()
    monkeypatch.setattr(generator, "_load_pipeline", lambda: FakePipeline())

    image = generator.generate(
        source_image=Image.new("RGB", (16, 16)),
        prompt="positive prompt",
        avoid_prompt="must not be passed as text",
        seed=123,
    )

    assert image.size == (16, 16)
    assert calls
    assert "negative_prompt" not in calls[0]
    assert calls[0]["prompt"].startswith("positive prompt")
    assert "Avoid:" in calls[0]["prompt"]
    assert "must not be passed as text" in calls[0]["prompt"]


def test_privacy_reference_preprocess_reduces_exact_detail(monkeypatch):
    monkeypatch.delenv("AVATAR_REFERENCE_PRIVACY_PREPROCESS", raising=False)
    monkeypatch.setenv("AVATAR_REFERENCE_FACE_EQUIVALENT_SIZE", "32")
    monkeypatch.setenv("AVATAR_REFERENCE_FACE_BLUR_RADIUS", "2")
    monkeypatch.setenv("AVATAR_REFERENCE_NONFACE_EQUIVALENT_SIZE", "96")
    monkeypatch.setenv("AVATAR_REFERENCE_NONFACE_BLUR_RADIUS", "1.5")
    source = Image.new("RGB", (128, 128), color=(245, 245, 245))
    for x in range(0, 128, 4):
        for y in range(0, 128, 4):
            color = (20, 20, 20) if (x + y) % 8 == 0 else (230, 120, 80)
            for dx in range(2):
                for dy in range(2):
                    source.putpixel((x + dx, y + dy), color)

    prepared = prepare_privacy_reference_image(source)

    assert prepared.size == source.size
    assert prepared.tobytes() != source.tobytes()


def test_privacy_reference_preprocess_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AVATAR_REFERENCE_PRIVACY_PREPROCESS", "false")
    source = Image.new("RGB", (32, 32), color=(1, 2, 3))

    prepared = prepare_privacy_reference_image(source)

    assert prepared.tobytes() == source.tobytes()


def test_production_does_not_default_to_dry_run(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("AVATAR_WORKER_MODE", raising=False)
    monkeypatch.delenv("AVATAR_WORKER_DRY_RUN", raising=False)

    assert resolve_worker_mode(None) == "flux"


def test_production_rejects_dry_run_mode(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(AvatarGenerationError, match="dry_run"):
        resolve_worker_mode("dry_run")

    monkeypatch.setenv("AVATAR_WORKER_DRY_RUN", "true")
    with pytest.raises(AvatarGenerationError, match="dry_run"):
        resolve_worker_mode(None)


def test_worker_dry_run_writes_four_preview_ready_candidates():
    payload = _payload()
    fs = _fake_firestore(payload)
    st = _fake_storage()

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    assert result.status == "preview_ready"
    assert result.preview_ready_count == 4
    assert len(fs.data["avatarCandidates"]) == 4
    assert fs.data["avatarJobs"][payload["jobId"]]["status"] == "preview_ready"
    assert all(doc["qa"]["previewAllowed"] is True for doc in fs.data["avatarCandidates"].values())
    assert len(st.buckets["seolleyeon-avatar-temp"].blobs) == 4


def test_worker_trait_card_uses_job_onboarding_gender(monkeypatch):
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("AVATAR_TRAIT_DRY_RUN", "true")
    payload = _payload(job_id="avatar_job_gender")
    fs = _fake_firestore(payload)
    fs.data["avatarJobs"][payload["jobId"]]["avatarPresentationGender"] = "female"

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    trait_card = fs.data["avatarJobs"][payload["jobId"]]["traitCard"]
    assert result.status == "preview_ready"
    assert trait_card["traitCard"]["avatar_presentation_gender"] == "female"


def test_worker_uses_env_avatar_temp_bucket(monkeypatch):
    monkeypatch.setenv("AVATAR_TEMP_BUCKET", "seolleyeon-final-avatar-temp")
    payload = _payload(job_id="avatar_job_env_bucket")
    fs = _fake_firestore(payload)
    st = FakeStorage(
        {
            "seolleyeon-private-source-photos": FakeBucket(
                {"users/u1/source/src_001.jpg": FakeBlob(_png_bytes())}
            ),
            "seolleyeon-final-avatar-temp": FakeBucket({}),
        }
    )

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    assert result.status == "preview_ready"
    assert len(st.buckets["seolleyeon-final-avatar-temp"].blobs) == 4
    assert all(
        doc["imageRef"].startswith("gs://seolleyeon-final-avatar-temp/")
        for doc in fs.data["avatarCandidates"].values()
    )


def test_worker_records_job_cost_after_successful_dry_run(monkeypatch):
    monkeypatch.setenv("CLOUD_RUN_L4_GPU_USD_PER_SECOND", "0.10")
    monkeypatch.setenv("CLOUD_RUN_CPU_USD_PER_VCPU_SECOND", "0.01")
    monkeypatch.setenv("CLOUD_RUN_MEMORY_USD_PER_GIB_SECOND", "0.001")
    monkeypatch.setenv("CLOUD_RUN_VCPU", "2")
    monkeypatch.setenv("CLOUD_RUN_MEMORY_GIB", "8")
    monkeypatch.setenv("CLOUD_RUN_PRICING_VERSION", "worker-test-pricing")
    payload = _payload(job_id="avatar_job_cost")
    fs = _fake_firestore(payload)

    process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["cost"]["candidateCount"] == 4
    assert job["cost"]["totalWorkerSeconds"] >= 0
    assert job["cost"]["estimatedUsd"] >= 0
    assert job["cost"]["pricingVersion"] == "worker-test-pricing"
    assert set(job["cost"]["secondsByStage"]) >= {"loadSource", "generate", "uploadAndQa", "total"}
    assert job["costEstimateUsd"] == job["cost"]["estimatedUsd"]
    assert "sourcePhotoRefs" not in json.dumps(job["cost"])


def test_worker_batch_payload_processes_jobs_sequentially():
    first = _payload(job_id="avatar_job_batch_1")
    second = _payload(job_id="avatar_job_batch_2")
    fs = _fake_firestore(first)
    fs.data["avatarJobs"][second["jobId"]] = dict(fs.data["avatarJobs"][first["jobId"]], jobId=second["jobId"])
    st = _fake_storage()

    result = process_avatar_generation_batch_payload(
        {
            "schemaVersion": "avatar_batch_job_v1",
            "jobType": "avatar_generation_batch",
            "jobs": [first, second],
        },
        firestore_client=fs,
        storage_client=st,
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    assert result.status == "ok"
    assert result.processed_count == 2
    assert [job["jobId"] for job in result.job_results] == ["avatar_job_batch_1", "avatar_job_batch_2"]
    assert all("sourcePhotoRefs" not in json.dumps(job) for job in result.job_results)


def test_worker_batch_result_metrics_include_aggregate_cost(monkeypatch):
    monkeypatch.setenv("CLOUD_RUN_L4_GPU_USD_PER_SECOND", "0.10")
    monkeypatch.setenv("CLOUD_RUN_CPU_USD_PER_VCPU_SECOND", "0.01")
    monkeypatch.setenv("CLOUD_RUN_MEMORY_USD_PER_GIB_SECOND", "0.001")
    monkeypatch.setenv("CLOUD_RUN_VCPU", "2")
    monkeypatch.setenv("CLOUD_RUN_MEMORY_GIB", "8")
    monkeypatch.setenv("CLOUD_RUN_PRICING_VERSION", "worker-batch-pricing")
    first = _payload(job_id="avatar_job_batch_cost_1")
    second = _payload(job_id="avatar_job_batch_cost_2")
    fs = _fake_firestore(first)
    fs.data["avatarJobs"][second["jobId"]] = dict(fs.data["avatarJobs"][first["jobId"]], jobId=second["jobId"])

    result = process_avatar_generation_batch_payload(
        {
            "schemaVersion": "avatar_batch_job_v1",
            "jobType": "avatar_generation_batch",
            "batchId": "batch_cost_001",
            "jobIds": [first["jobId"], second["jobId"]],
            "maxJobs": 2,
        },
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    cost = result.metrics["cost"]
    assert cost["candidateCount"] == 8
    assert cost["jobCount"] == 2
    assert cost["totalWorkerSeconds"] >= 0
    assert cost["estimatedUsd"] >= 0
    assert cost["pricingVersion"] == "worker-batch-pricing"
    assert "sourcePhotoRefs" not in json.dumps(result.to_dict())


def test_worker_batch_payload_loads_canonical_job_ids_without_returning_source_refs():
    first = _payload(job_id="avatar_job_ids_batch_1")
    second = _payload(job_id="avatar_job_ids_batch_2")
    fs = _fake_firestore(first)
    fs.data["avatarJobs"][second["jobId"]] = dict(fs.data["avatarJobs"][first["jobId"]], jobId=second["jobId"])

    result = process_avatar_generation_batch_payload(
        {
            "schemaVersion": "avatar_batch_job_v1",
            "jobType": "avatar_generation_batch",
            "batchId": "batch_prompt_001",
            "jobIds": [first["jobId"], second["jobId"]],
            "maxJobs": 2,
            "deadlineSeconds": 120,
        },
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    assert result.status == "ok"
    assert result.processed_count == 2
    assert result.batch_id == "batch_prompt_001"
    assert result.metrics["batchId"] == "batch_prompt_001"
    assert [job["jobId"] for job in result.job_results] == ["avatar_job_ids_batch_1", "avatar_job_ids_batch_2"]
    assert "sourcePhotoRefs" not in json.dumps(result.to_dict())
    assert "users/u1/source/src_001.jpg" not in json.dumps(result.to_dict())


def test_worker_batch_payload_rejects_unsupported_batch_job_type():
    with pytest.raises(AvatarGenerationError, match="Unsupported avatar batch jobType"):
        process_avatar_generation_batch_payload(
            {
                "schemaVersion": "avatar_batch_job_v1",
                "jobType": "avatar_generation",
                "jobIds": ["avatar_job_1"],
            },
            firestore_client=_fake_firestore(),
            storage_client=_fake_storage(),
            qa_runner=_passing_qa,
            mode="dry_run",
        )


def test_worker_drain_claims_additional_jobs():
    first = _payload(job_id="avatar_job_drain_1")
    second = _payload(job_id="avatar_job_drain_2")
    fs = _fake_firestore(first)
    fs.data["avatarJobs"][second["jobId"]] = dict(fs.data["avatarJobs"][first["jobId"]], jobId=second["jobId"])
    st = _fake_storage()

    result = process_avatar_generation_drain(
        firestore_client=fs,
        storage_client=st,
        qa_runner=_passing_qa,
        mode="dry_run",
        config=AvatarJobLeaseConfig(
            batching_enabled=True,
            batch_mode="drain",
            batch_size=2,
            max_batch_seconds=1,
            max_idle_wait_seconds=1,
            poll_interval_seconds=1,
            concurrency_per_gpu=1,
        ),
    )

    assert result.status == "ok"
    assert result.processed_count == 2
    assert fs.data["avatarJobs"]["avatar_job_drain_1"]["status"] == "preview_ready"
    assert fs.data["avatarJobs"]["avatar_job_drain_2"]["status"] == "preview_ready"
    assert result.metrics["drainMode"] is True


def test_worker_drain_stops_before_deadline():
    payload = _payload(job_id="avatar_job_deadline")
    fs = _fake_firestore(payload)

    result = process_avatar_generation_drain(
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="dry_run",
        config=AvatarJobLeaseConfig(
            batching_enabled=True,
            batch_mode="drain",
            batch_size=1,
            max_idle_wait_seconds=1,
            concurrency_per_gpu=1,
        ),
        deadline=ClaimDeadline.from_timeout(0, safety_seconds=1),
    )

    assert result.processed_count == 0
    assert fs.data["avatarJobs"][payload["jobId"]]["status"] == "queued"


def test_batch_partial_failure_does_not_duplicate_completed_jobs():
    first = _payload(job_id="avatar_job_partial_1")
    second = _payload(job_id="avatar_job_partial_2")
    second["sourcePhotoRefs"] = ["gs://seolleyeon-private-source-photos/users/u1/source/missing.jpg"]
    fs = _fake_firestore(first)
    fs.data["avatarJobs"][second["jobId"]] = dict(fs.data["avatarJobs"][first["jobId"]], jobId=second["jobId"])
    fs.data["avatarJobs"][second["jobId"]]["sourcePhotoRefs"] = list(second["sourcePhotoRefs"])

    result = process_avatar_generation_batch_payload(
        {
            "schemaVersion": "avatar_batch_job_v1",
            "jobType": "avatar_generation_batch",
            "jobs": [first, second, first],
        },
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    completed_ids = [job["jobId"] for job in result.job_results if job["status"] == "preview_ready"]
    assert result.status == "partial_failure"
    assert completed_ids == ["avatar_job_partial_1"]


def test_flux_model_generator_is_cached_once(monkeypatch):
    monkeypatch.setenv("AVATAR_FACE_DETECTOR_ENABLED", "false")
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "false")

    class FakeCachedGenerator:
        def __init__(self, _model_id):
            self.calls = 0

        def generate(self, *, source_image, prompt, avoid_prompt, seed):
            self.calls += 1
            return Image.new("RGB", (16, 16), color=(seed % 255, 80, 120))

    reset_model_cache_for_tests()
    monkeypatch.setattr("avatar_generation.worker.Flux2KleinImageGenerator", FakeCachedGenerator)
    first = _payload(job_id="avatar_job_flux_cache_1")
    second = _payload(job_id="avatar_job_flux_cache_2")
    first["candidateCount"] = 1
    second["candidateCount"] = 1
    fs = _fake_firestore(first)
    fs.data["avatarJobs"][first["jobId"]]["candidateCount"] = 1
    fs.data["avatarJobs"][second["jobId"]] = dict(fs.data["avatarJobs"][first["jobId"]], jobId=second["jobId"])

    result = process_avatar_generation_batch_payload(
        {
            "schemaVersion": "avatar_batch_job_v1",
            "jobType": "avatar_generation_batch",
            "jobs": [first, second],
        },
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="flux",
    )

    assert result.status == "ok"
    assert model_cache_metrics()["modelLoadCalls"] == 1
    reset_model_cache_for_tests()


def test_worker_marks_job_failed_when_all_candidates_rejected():
    payload = _payload(job_id="avatar_job_2")
    fs = _fake_firestore(payload)
    st = _fake_storage()

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=_rejecting_qa,
        mode="dry_run",
    )

    assert result.status == "failed"
    assert result.rejected_count == 8
    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "failed"
    assert job["errorCode"] == "no_previewable_candidates"
    assert job["generationPlan"]["initialCount"] == 4
    assert job["generationPlan"]["extraCount"] == 4
    assert job["generationPlan"]["totalGenerated"] == 8


def test_worker_requires_full_preview_count_when_policy_requires_four():
    payload = _payload(job_id="avatar_job_partial_preview")
    fs = _fake_firestore(payload)
    st = _fake_storage()
    seen = []

    def first_two_pass_then_review(source_ref, candidate_ref, metadata):
        seen.append(metadata["candidateId"])
        if len(seen) <= 2:
            return _passing_qa(source_ref, candidate_ref, metadata)
        return _needs_review_qa(source_ref, candidate_ref, metadata)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=first_two_pass_then_review,
        mode="dry_run",
    )

    assert result.status == "needs_review"
    assert result.preview_ready_count == 0
    assert result.needs_review_count == 4
    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "needs_review"
    assert job["errorCode"] == "requires_more_preview_candidates"
    assert job["generationPlan"]["previewCount"] == 0
    assert job["generationPlan"]["previewShortfall"] == 2
    assert job["generationPlan"]["policy"]["requireFourPreview"] is True
    assert all(
        doc["status"] != "preview_ready"
        for doc in fs.data["avatarCandidates"].values()
    )
    assert all(
        doc["rerank"]["selectedForPreview"] is False
        for doc in fs.data["avatarCandidates"].values()
    )


def test_worker_failure_error_message_is_redacted(monkeypatch):
    monkeypatch.setenv("AVATAR_FACE_DETECTOR_ENABLED", "false")
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "false")
    payload = _payload(job_id="avatar_job_redacted_failure")
    fs = _fake_firestore(payload)

    def boom(*_args, **_kwargs):
        raise RuntimeError(
            "failed reading gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg"
        )

    monkeypatch.setattr("avatar_generation.worker.generate_candidate_artifacts", boom)

    with pytest.raises(AvatarGenerationError):
        process_avatar_generation_payload(
            payload,
            firestore_client=fs,
            storage_client=_fake_storage(),
            qa_runner=_passing_qa,
            mode="flux",
        )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "failed"
    assert job["errorCode"] == "avatar_generation_worker_error"
    assert "gs://" not in job["errorMessage"]
    assert "seolleyeon-final-private-source-photos" not in job["errorMessage"]
    assert "src_001.jpg" not in job["errorMessage"]


def test_direct_worker_cost_kill_switch_marks_job_failed(monkeypatch):
    monkeypatch.setenv("AVATAR_COST_KILL_SWITCH_ENABLED", "true")
    payload = _payload(job_id="avatar_job_paused")
    fs = _fake_firestore(payload)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert result.status == "failed"
    assert job["status"] == "failed"
    assert job["errorCode"] == "avatar_worker_cost_guard_paused"


def test_worker_deadline_marks_job_failed(monkeypatch):
    monkeypatch.setenv("AVATAR_WORKER_MAX_JOB_SECONDS", "30")
    monkeypatch.setenv("AVATAR_WORKER_SOFT_STOP_MARGIN_SECONDS", "30")
    payload = _payload(job_id="avatar_job_deadline_fail")
    fs = _fake_firestore(payload)

    with pytest.raises(AvatarGenerationError, match="deadline"):
        process_avatar_generation_payload(
            payload,
            firestore_client=fs,
            storage_client=_fake_storage(),
            qa_runner=_passing_qa,
            mode="dry_run",
        )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "failed"
    assert job["errorCode"] == "avatar_worker_deadline_exceeded"


def test_worker_marks_candidates_needs_review_after_qa():
    payload = _payload(job_id="avatar_job_review")
    fs = _fake_firestore(payload)
    st = _fake_storage()

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=_needs_review_qa,
        mode="dry_run",
    )

    assert result.status == "needs_review"
    assert result.needs_review_count == 8
    assert all(
        doc["status"] == "needs_review"
        for doc in fs.data["avatarCandidates"].values()
    )
    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "needs_review"
    assert job["errorCode"] == "requires_human_review"
    assert job["generationPlan"]["initialCount"] == 4
    assert job["generationPlan"]["extraCount"] == 4


def test_worker_service_rejects_unauthenticated_production_request(monkeypatch):
    import avatar_generation.worker_service as worker_service

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("AVATAR_WORKER_AUTH_MODE", raising=False)
    monkeypatch.delenv("AVATAR_WORKER_REQUIRE_SHARED_SECRET", raising=False)
    monkeypatch.delenv("AVATAR_WORKER_SHARED_SECRET", raising=False)

    if worker_service.app is None:
        with pytest.raises(worker_service.AvatarWorkerAuthError, match="authorized"):
            worker_service._require_worker_auth()
        return

    response = worker_service.app.test_client().post("/tasks/avatar-generation", json=_payload())

    assert response.status_code == 401
    assert "authorized" in response.get_json()["error"]


def test_worker_service_local_insecure_bypass_must_be_explicit(monkeypatch):
    import avatar_generation.worker_service as worker_service

    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.delenv("AVATAR_WORKER_AUTH_MODE", raising=False)
    monkeypatch.delenv("AVATAR_WORKER_REQUIRE_SHARED_SECRET", raising=False)
    monkeypatch.delenv("AVATAR_WORKER_SHARED_SECRET", raising=False)
    monkeypatch.delenv("ALLOW_INSECURE_WORKER_LOCAL", raising=False)

    with pytest.raises(worker_service.AvatarWorkerAuthError, match="ALLOW_INSECURE_WORKER_LOCAL"):
        worker_service._require_worker_auth()

    monkeypatch.setenv("ALLOW_INSECURE_WORKER_LOCAL", "true")
    worker_service._require_worker_auth()


def test_worker_service_production_cloud_run_iam_posture_allows_request(monkeypatch):
    import avatar_generation.worker_service as worker_service

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AVATAR_WORKER_AUTH_MODE", "cloud_run_iam")
    monkeypatch.setenv("AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED", "true")
    monkeypatch.setenv("K_SERVICE", "avatar-worker")
    monkeypatch.delenv("ALLOW_INSECURE_WORKER_LOCAL", raising=False)

    worker_service._require_worker_auth()


def test_worker_service_staging_cloud_run_iam_posture_allows_request(monkeypatch):
    import avatar_generation.worker_service as worker_service

    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("AVATAR_WORKER_AUTH_MODE", "cloud_run_iam")
    monkeypatch.setenv("AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED", "true")
    monkeypatch.setenv("K_SERVICE", "avatar-worker")
    monkeypatch.delenv("ALLOW_INSECURE_WORKER_LOCAL", raising=False)

    worker_service._require_worker_auth()


def test_worker_service_readyz_reports_auth_posture(monkeypatch):
    import avatar_generation.worker_service as worker_service

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AVATAR_WORKER_AUTH_MODE", "cloud_run_iam")
    monkeypatch.setenv("AVATAR_BATCHING_ENABLED", "true")
    monkeypatch.setenv("AVATAR_BATCH_MODE", "drain")

    posture = worker_service.readyz_status()
    assert posture["status"] == "ok"
    assert posture["authMode"] == "cloud_run_iam"
    assert posture["batchDrainEnabled"] is True

    if worker_service.app is None:
        return

    response = worker_service.app.test_client().get("/readyz")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["authMode"] == "cloud_run_iam"
    assert body["batchDrainEnabled"] is True


def test_smoke_script_dry_run_writes_redacted_report(tmp_path):
    report_path = tmp_path / "avatar_worker_smoke_report.json"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "avatar_worker_smoke_test.py"),
            "--dry_run",
            "--job_id",
            "avatar_job_1",
            "--uid",
            "u1",
            "--source_gcs_uri",
            "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg",
            "--output_report_json",
            str(report_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "dry_run"
    assert report["result"]["status"] in {"preview_ready", "needs_review", "failed"}
    report_text = json.dumps(report)
    assert "users/u1/source/src_001.jpg" not in report_text


def test_staging_smoke_script_dry_run_command_writes_redacted_report(tmp_path):
    report_path = tmp_path / "avatar_worker_staging_smoke_report.json"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "avatar_worker_staging_smoke.py"),
            "--dry_run",
            "--job_id",
            "avatar_job_1",
            "--uid",
            "u1",
            "--source_gcs_uri",
            "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg",
            "--output_report_json",
            str(report_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "dry_run"
    assert report["status"] == "ok"
    assert "users/u1/source/src_001.jpg" not in json.dumps(report)


def test_avatar_generation_code_does_not_use_external_image_api_strings():
    code = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (AI_MODEL_DIR / "avatar_generation").rglob("*.py")
    )
    forbidden = [
        "OpenAI",
        "Imagen",
        "Stability",
        "Replicate",
        "DALL",
        "gpt-image",
        "external image API",
    ]
    assert not [token for token in forbidden if token in code]
