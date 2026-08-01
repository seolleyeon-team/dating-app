import base64
import io
import json
import logging
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
from avatar_generation.trait_card import validate_trait_card_response
import avatar_generation.worker as worker_module
from avatar_generation.jobs import build_candidate_doc
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
    generate_candidate_artifacts,
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

    def get(self, **_kwargs):
        return FakeSnapshot(self.store.get(self.collection, {}).get(self.doc_id), self.doc_id)

    def set(self, data, merge=True):
        collection = self.store.setdefault(self.collection, {})
        if merge and self.doc_id in collection:
            collection[self.doc_id].update(data)
        else:
            collection[self.doc_id] = dict(data)

    def update(self, data):
        self.set(data, merge=True)


class FakeTransaction:
    _codex_fake_transaction = True

    def __init__(self, firestore):
        self.firestore = firestore

    def get(self, ref):
        return ref.get()

    def set(self, ref, data, merge=True):
        hook = self.firestore.before_transaction_set
        if hook is not None:
            hook(ref, data)
        current = ref.get().to_dict()
        if str(current.get("status") or "") in {
            "preview_ready",
            "approved",
            "cancelled",
            "canceled",
            "superseded",
        }:
            return f"terminal_skipped:{current.get('status')}"
        return ref.set(data, merge=merge)


class RecordingTransaction(FakeTransaction):
    def __init__(self, firestore):
        super().__init__(firestore)
        self.ref_get_called_with_transaction = False
        self.transaction_get_called = False
        self.read_after_write = False
        self._wrote = False

    def get(self, ref):
        self.transaction_get_called = True
        return super().get(ref)

    def set(self, ref, data, merge=True):
        self._wrote = True
        return super().set(ref, data, merge=merge)


class RecordingDocRef(FakeDocRef):
    def get(self, **kwargs):
        transaction = kwargs.get("transaction")
        if isinstance(transaction, RecordingTransaction):
            transaction.ref_get_called_with_transaction = True
            if transaction._wrote:
                transaction.read_after_write = True
        return super().get(**kwargs)


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
        self.before_transaction_set = None

    def collection(self, name):
        return FakeCollection(self.data, name)


class AtomicFakeFirestore(FakeFirestore):
    def transaction(self):
        return FakeTransaction(self)


class RecordingCollection(FakeCollection):
    def document(self, doc_id):
        return RecordingDocRef(self.store, self.name, doc_id)


class RecordingAtomicFakeFirestore(AtomicFakeFirestore):
    def __init__(self, data):
        super().__init__(data)
        self.last_transaction = None

    def collection(self, name):
        return RecordingCollection(self.data, name)

    def transaction(self):
        self.last_transaction = RecordingTransaction(self)
        return self.last_transaction



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
                    "currentAvatarSourcePhotoId": payload["sourcePhotoIds"][0],
                    "currentAvatarJobId": payload["jobId"],
                    "avatarSourceSelectionVersion": 1,
                    "photoConsent": {
                        "avatarGeneration": True,
                        "profileDisplayOriginalPhoto": False,
                    },
                    "sourcePhotos": [
                        {
                            "photoId": payload["sourcePhotoIds"][0],
                            "gcsUri": payload["sourcePhotoRefs"][0],
                            "status": "active",
                            "avatarGenerationState": "current",
                            "purpose": {"avatarGeneration": True},
                        }
                    ],
                }
            },
            "avatarCandidates": {},
        }
    )


def _fake_atomic_firestore(payload=None):
    return AtomicFakeFirestore(_fake_firestore(payload).data)


def _fake_recording_atomic_firestore(payload=None):
    return RecordingAtomicFakeFirestore(_fake_firestore(payload).data)


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


def _soft_pass_qa(_source_ref, _candidate_ref, _metadata):
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
        previewAllowed=False,
        requiresHumanReview=False,
        softPass=True,
        softPassReasons=["test_soft_pass"],
        qaVersion="test_soft_pass",
    )


def test_worker_source_reject_codes_map_to_user_guidance():
    cases = (
        ("multi_face_primary", "avatar_source_multi_face", "얼굴이 여러 명 감지됐어요. 혼자 나온 사진을 선택해주세요."),
        ("face_too_small", "avatar_source_face_too_small", "얼굴이 너무 작게 보여요. 얼굴이 더 잘 보이는 사진을 선택해주세요."),
        ("face_too_blurry", "avatar_source_face_too_blurry", "사진이 흐려 얼굴 특징을 확인하기 어려워요. 선명한 다른 사진을 선택해주세요."),
        ("face_out_of_frame", "avatar_source_face_out_of_frame", "얼굴이 사진 안에 충분히 들어오도록 촬영한 다른 사진을 선택해주세요."),
        ("landmarks_unstable", "avatar_source_landmarks_unstable", "얼굴 특징을 안정적으로 확인하기 어려워요. 정면에 가까운 다른 사진을 선택해주세요."),
        ("low_light", "avatar_source_low_light", "사진이 너무 어두워 얼굴을 확인하기 어려워요. 밝은 곳에서 촬영한 사진을 선택해주세요."),
        ("compression_damage", "avatar_source_compression_damage", "사진 화질이 많이 손상되어 있어요. 원본에 가까운 다른 사진을 선택해주세요."),
        ("analysis_uncertain", "avatar_source_analysis_uncertain", "사진 상태를 확실히 판단하기 어려워요. 선명한 다른 사진을 선택해주세요."),
        ("background_text_logo_risk", "avatar_background_text_logo_risky", "배경의 글자나 로고가 크게 보여요. 다른 사진을 권장해요."),
        ("no_face", "avatar_source_no_face", "얼굴이 잘 보이는 사진을 선택해주세요."),
    )

    for reason, error_code, expected_message in cases:
        analysis = {"rejectReasons": [reason]}
        message = worker_module._source_reject_error_message(analysis)
        assert worker_module._source_reject_error_code(analysis) == error_code
        assert message == expected_message
        assert "?" not in message
        assert "\ufffd" not in message

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
    assert "use simple neutral background" in positive
    assert "do not preserve or recreate the original background" in positive
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
    assert all("Preserve broad resemblance" in call["prompt"] for call in generator.calls)
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
    fs.data["avatarJobs"][payload["jobId"]]["errorCode"] = "avatar_worker_deadline_exceeded"
    fs.data["avatarJobs"][payload["jobId"]]["errorMessage"] = "stale previous retry error"
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
    assert fs.data["avatarJobs"][payload["jobId"]]["errorCode"] == ""
    assert fs.data["avatarJobs"][payload["jobId"]]["errorMessage"] == ""
    assert all(doc["qa"]["previewAllowed"] is True for doc in fs.data["avatarCandidates"].values())
    assert len(st.buckets["seolleyeon-avatar-temp"].blobs) == 4


def test_worker_direct_terminal_guard_rejects_no_preview_and_review_statuses():
    payload = parse_avatar_generation_payload(_payload())
    for status in ("needs_review", "no_previewable_candidates"):
        with pytest.raises(AvatarGenerationError, match="already complete"):
            worker_module._assert_job_can_run(
                {"uid": payload.uid, "status": status},
                payload,
            )


def test_worker_respects_external_claim_deadline_before_expensive_work():
    payload = _payload(job_id="avatar_job_external_deadline")
    fs = _fake_firestore(payload)

    with pytest.raises(AvatarGenerationError, match="deadline_exceeded"):
        process_avatar_generation_payload(
            payload,
            firestore_client=fs,
            storage_client=_fake_storage(),
            qa_runner=_passing_qa,
            mode="dry_run",
            deadline=ClaimDeadline.from_timeout(5, safety_seconds=4),
        )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "failed"
    assert job["errorCode"] == "avatar_worker_deadline_exceeded"


def test_worker_supersedes_non_current_job_without_generation():
    payload = _payload(job_id="avatar_job_old")
    fs = _fake_firestore(payload)
    fs.data["userPrivateMedia"][payload["uid"]]["currentAvatarJobId"] = "avatar_job_new"

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    assert result.status == "superseded"
    assert fs.data["avatarJobs"][payload["jobId"]]["status"] == "superseded"
    assert fs.data["avatarJobs"][payload["jobId"]]["errorCode"] == "avatar_job_superseded"
    assert fs.data["avatarCandidates"] == {}


def test_worker_supersedes_current_source_mismatch_without_generation():
    payload = _payload(job_id="avatar_job_source_mismatch")
    fs = _fake_firestore(payload)
    fs.data["userPrivateMedia"][payload["uid"]]["currentAvatarSourcePhotoId"] = "src_other"

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    assert result.status == "superseded"
    assert fs.data["avatarJobs"][payload["jobId"]]["status"] == "superseded"
    assert fs.data["avatarCandidates"] == {}


def test_worker_supersedes_selection_version_mismatch_without_generation():
    payload = _payload(job_id="avatar_job_selection_version_mismatch")
    fs = _fake_firestore(payload)
    fs.data["avatarJobs"][payload["jobId"]]["avatarSourceSelectionVersion"] = 1
    fs.data["userPrivateMedia"][payload["uid"]]["avatarSourceSelectionVersion"] = 2

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert result.status == "superseded"
    assert job["status"] == "superseded"
    assert "selection_version_mismatch" in job["errorMessage"]
    assert fs.data["avatarCandidates"] == {}


def test_worker_recheck_prevents_stale_preview_ready_race():
    payload = _payload(job_id="avatar_job_race")
    fs = _fake_firestore(payload)
    original_update = worker_module._update_job_status

    def wrapped_update(firestore_client, job_id, update):
        result = original_update(firestore_client, job_id, update)
        if update.get("status") == "qa_pending":
            fs.data["userPrivateMedia"][payload["uid"]]["currentAvatarJobId"] = "avatar_job_new"
        return result

    worker_module._update_job_status = wrapped_update
    try:
        result = process_avatar_generation_payload(
            payload,
            firestore_client=fs,
            storage_client=_fake_storage(),
            qa_runner=_passing_qa,
            mode="dry_run",
        )
    finally:
        worker_module._update_job_status = original_update

    assert result.status == "superseded"
    assert fs.data["avatarJobs"][payload["jobId"]]["status"] == "superseded"
    assert all(
        doc["status"] == "superseded"
        for doc in fs.data["avatarCandidates"].values()
    )


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


def test_worker_trait_and_flux_use_privacy_processed_references(monkeypatch):
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("AVATAR_FACE_DETECTOR_ENABLED", "true")
    captured = []
    generated_refs = []
    qa_metadata = []

    class FakeSourceAnalysis:
        hard_reject = False
        broad_trait_hints = {}
        primary_face = types.SimpleNamespace(bbox=(0.25, 0.25, 0.5, 0.5), confidence=0.98)

        def to_document(self):
            return {
                "status": "accepted",
                "hardReject": False,
                "rejectReasons": [],
                "primaryFaceBbox": [0.25, 0.25, 0.5, 0.5],
                "backgroundNeutralizationRequired": True,
            }

    class FakeTraitAdapter:
        def __init__(self, **_kwargs):
            pass

        def extract_traits(self, *, image, avatar_presentation_gender):
            captured.append(image.copy())
            return validate_trait_card_response(
                json.dumps(
                    {
                        "schemaVersion": "seolleyeon_avatar_trait_card_v3",
                        "privacySafe": True,
                        "confidence": 0.9,
                        "traitCard": {
                            "visible_crop": "head_and_shoulders",
                            "avatar_presentation_gender": avatar_presentation_gender,
                        },
                    }
                )
            )

    class FakeGenerator:
        def __init__(self, _model_id):
            pass

        def generate(self, *, source_image, prompt, avoid_prompt, seed):
            generated_refs.append(source_image.copy())
            return Image.new("RGB", (16, 16), color=(seed % 255, 80, 120))

    monkeypatch.setattr(worker_module, "analyze_avatar_source_image", lambda *_args, **_kwargs: FakeSourceAnalysis())
    monkeypatch.setattr(worker_module, "Florence2TraitExtractionAdapter", FakeTraitAdapter)
    monkeypatch.setattr(worker_module, "Flux2KleinImageGenerator", FakeGenerator)
    worker_module._TRAIT_ADAPTER_CACHE.clear()
    worker_module._FLUX_GENERATOR_CACHE.clear()
    payload = _payload(job_id="avatar_job_trait_privacy_ref")
    fs = _fake_firestore(payload)

    def passing_qa_with_metadata(source_ref, candidate_ref, metadata):
        qa_metadata.append(dict(metadata))
        return _passing_qa(source_ref, candidate_ref, metadata)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=passing_qa_with_metadata,
        mode="flux",
    )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert result.status == "preview_ready"
    assert captured
    corner = captured[0].getpixel((0, 0))
    assert all(
        abs(actual - expected) <= 5
        for actual, expected in zip(corner, (247, 242, 236))
    )
    assert generated_refs
    generation_corner = generated_refs[0].getpixel((0, 0))
    assert all(
        abs(actual - expected) <= 5
        for actual, expected in zip(generation_corner, (247, 242, 236))
    )
    assert job["referencePreprocess"]["backgroundNeutralized"] is True
    assert job["traitExtraction"]["input"] == "analysis_reference_image"
    assert job["traitExtraction"]["backgroundNeutralized"] is True
    assert qa_metadata
    assert qa_metadata[0]["sourceAnalysis"]["backgroundNeutralizationRequired"] is True
    assert qa_metadata[0]["referencePreprocess"]["backgroundNeutralized"] is True
    persisted_metadata = {
        key: value for key, value in qa_metadata[0].items() if not key.startswith("_")
    }
    assert "sourcePhotoRefs" not in json.dumps(persisted_metadata)


def _assert_forbidden_observability_fields_absent(value):
    serialized = json.dumps(value, sort_keys=True, default=str)
    forbidden = {
        "sourceImageSha256Prefix",
        "cleanedSourceSha256Prefix",
        "privacyReferenceSha256Prefix",
        "promptHash",
        "traitCardHash",
        "uidHash",
        "generationKwargs",
        "promptMeta",
        "trait_card",
    }
    assert not [field for field in forbidden if field in serialized]


def test_worker_persists_lineage_without_prompt_trait_or_image_hash_observability(monkeypatch, caplog):
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "false")
    caplog.set_level(logging.INFO, logger="avatar_generation.worker")
    payload = _payload(job_id="avatar_job_zero_hash_source")
    fs = _fake_firestore(payload)
    st = FakeStorage(
        {
            "seolleyeon-private-source-photos": FakeBucket(
                {"users/u1/source/src_001.jpg": FakeBlob(_png_bytes((120, 64, 48)))}
            ),
            "seolleyeon-avatar-temp": FakeBucket({}),
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
    job = fs.data["avatarJobs"][payload["jobId"]]
    candidate = next(iter(fs.data["avatarCandidates"].values()))
    assert job["sourceReferenceAudit"] == {
        "jobId": "avatar_job_zero_hash_source",
        "sourcePhotoId": "src_001",
        "sourceSelectionVersion": 1,
    }
    assert candidate["generationParams"]["candidateSeed"] == deterministic_seed(
        payload["jobId"],
        0,
    )
    assert "sourceReferenceAudit" not in candidate["generationParams"]
    assert candidate["qa"]["previewAllowed"] is True
    assert candidate["qa"]["fidelityCorridor"]["mode"] == "shadow"
    assert candidate["qa"]["fidelityCorridor"]["calibrationVersion"] == "uncalibrated"
    assert candidate["qa"]["fidelityCorridor"]["criticalSignalsAvailable"] is False
    assert job["fidelityCorridorShadowRanking"]["rankedCandidateIds"] == []
    assert job["previewRerank"]["selectedCandidateIds"]
    _assert_forbidden_observability_fields_absent(job)
    _assert_forbidden_observability_fields_absent(candidate)
    assert all("sourceReferenceAudit" not in record.__dict__ for record in caplog.records)


def test_worker_adds_candidate_eyewear_trait_to_qa_metadata(monkeypatch):
    monkeypatch.setenv("AVATAR_TRAIT_EXTRACTION_ENABLED", "true")
    monkeypatch.setenv("AVATAR_CANDIDATE_TRAIT_QA_ENABLED", "true")
    monkeypatch.setenv("AVATAR_TRAIT_DRY_RUN", "false")
    worker_module._TRAIT_ADAPTER_CACHE.clear()

    def trait_payload(eyewear_present, confidence="high"):
        return json.dumps(
            {
                "schemaVersion": "seolleyeon_avatar_trait_card_v3",
                "privacySafe": True,
                "confidence": 0.94,
                "traitCard": {
                    "visible_crop": "head_and_shoulders",
                    "hair_length": "medium",
                    "hair_volume": "medium",
                    "hair_direction": "side_part",
                    "hair_bangs": "side_bangs",
                    "hair_color_range": "dark_brown",
                    "eyewear_present": eyewear_present,
                    "eyewear_style": "none"
                    if eyewear_present == "no"
                    else "rectangular_dark",
                    "eyewear_confidence": confidence,
                    "eyewear_source": "florence",
                    "facial_hair_present": "no",
                    "facial_hair_style": "none",
                    "face_shape_category": "oval",
                    "facial_feature_balance": "balanced",
                    "eye_size_category": "medium",
                    "eye_tilt_category": "neutral",
                    "eye_shape_mood": "calm",
                    "brow_thickness": "natural",
                    "brow_shape": "natural",
                    "nose_prominence": "medium",
                    "nose_bridge_impression": "medium",
                    "cheek_fullness": "moderate",
                    "jaw_impression": "soft",
                    "mouth_expression": "calm_closed",
                    "mouth_fullness_category": "medium",
                    "skin_tone_range": "natural_beige",
                    "expression_mood": "calm",
                    "clothing_category": "knit",
                    "clothing_color": "gray",
                    "avatar_presentation_gender": "unknown",
                },
            }
        )

    class FakeTraitAdapter:
        calls = 0

        def __init__(self, **_kwargs):
            pass

        def extract_traits(self, *, image, avatar_presentation_gender):
            FakeTraitAdapter.calls += 1
            if FakeTraitAdapter.calls == 1:
                return validate_trait_card_response(trait_payload("no"))
            return validate_trait_card_response(trait_payload("yes"))

    monkeypatch.setattr(worker_module, "Florence2TraitExtractionAdapter", FakeTraitAdapter)
    captured_metadata = []
    payload = _payload(job_id="avatar_job_candidate_eyewear_trait")
    fs = _fake_firestore(payload)

    def qa_runner(source_ref, candidate_ref, metadata):
        captured_metadata.append(metadata)
        return _passing_qa(source_ref, candidate_ref, metadata)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=_fake_storage(),
        qa_runner=qa_runner,
        mode="dry_run",
    )

    assert result.status == "preview_ready"
    assert FakeTraitAdapter.calls == 1 + payload["candidateCount"]
    assert captured_metadata
    first = captured_metadata[0]
    assert first["sourceTraitCard"]["eyewear_present"] is False
    assert first["sourceTraitCard"]["eyewear_confidence"] == "high"
    assert first["candidateTraitCard"]["eyewear_present"] is True
    assert first["candidateTraitCard"]["eyewear_confidence"] == "high"
    assert first["candidateTraitExtraction"]["status"] == "available"
    assert "sourcePhotoRefs" not in json.dumps(first)


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
    expected_stage_keys = {
        "model_load_seconds",
        "face_detect_seconds",
        "trait_extract_seconds",
        "preprocess_seconds",
        "sam_seconds",
        "generation_seconds",
        "qa_seconds",
        "rerank_seconds",
        "upload_seconds",
        "total_worker_seconds",
    }
    assert set(job["cost"]["secondsByStage"]) >= expected_stage_keys
    assert job["cost"]["modelLoadSeconds"] == job["cost"]["secondsByStage"]["model_load_seconds"]
    assert job["cost"]["faceDetectSeconds"] == job["cost"]["secondsByStage"]["face_detect_seconds"]
    assert job["cost"]["traitExtractSeconds"] == job["cost"]["secondsByStage"]["trait_extract_seconds"]
    assert job["cost"]["preprocessSeconds"] == job["cost"]["secondsByStage"]["preprocess_seconds"]
    assert job["cost"]["samSeconds"] == job["cost"]["secondsByStage"]["sam_seconds"]
    assert job["cost"]["generationSeconds"] == job["cost"]["secondsByStage"]["generation_seconds"]
    assert job["cost"]["qaSeconds"] == job["cost"]["secondsByStage"]["qa_seconds"]
    assert job["cost"]["rerankSeconds"] == job["cost"]["secondsByStage"]["rerank_seconds"]
    assert job["cost"]["uploadSeconds"] == job["cost"]["secondsByStage"]["upload_seconds"]
    assert job["cost"]["totalWorkerSeconds"] == job["cost"]["secondsByStage"]["total_worker_seconds"]
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
    assert fs.data["avatarJobs"]["avatar_job_drain_2"]["status"] == "superseded"
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

    assert result.status == "no_previewable_candidates"
    assert result.rejected_count == 8
    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "no_previewable_candidates"
    assert job["errorCode"] == "too_identifiable_candidates"
    assert job["generationPlan"]["initialCount"] == 4
    assert job["generationPlan"]["extraCount"] == 4
    assert job["generationPlan"]["totalGenerated"] == 8


def test_worker_requires_full_preview_count_when_policy_requires_four(monkeypatch):
    monkeypatch.setenv("AVATAR_PREVIEW_REQUIRE_FOUR", "true")
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


def test_worker_allows_soft_pass_preview_when_min_preview_count_met(monkeypatch):
    monkeypatch.setenv("AVATAR_PREVIEW_REQUIRE_FOUR", "false")
    monkeypatch.setenv("AVATAR_MIN_PREVIEW_CANDIDATES", "1")
    payload = _payload(job_id="avatar_job_soft_pass_preview")
    fs = _fake_firestore(payload)
    st = _fake_storage()

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=_soft_pass_qa,
        mode="dry_run",
    )

    assert result.status == "preview_ready"
    assert result.preview_ready_count == 4
    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "preview_ready"
    assert job["generationPlan"]["softPassCount"] == 4
    assert job["generationPlan"]["filledWithSoftPass"] is True
    assert set(job["cost"]["secondsByStage"]) >= {
        "model_load_seconds",
        "face_detect_seconds",
        "trait_extract_seconds",
        "preprocess_seconds",
        "sam_seconds",
        "generation_seconds",
        "qa_seconds",
        "rerank_seconds",
        "upload_seconds",
        "total_worker_seconds",
    }
    assert all(
        doc["status"] == "preview_ready" and doc["qa"]["previewAllowed"] is True
        for doc in fs.data["avatarCandidates"].values()
    )


def test_worker_does_not_overwrite_cancelled_job_during_generation(monkeypatch):
    monkeypatch.setenv("AVATAR_PREVIEW_REQUIRE_FOUR", "false")
    payload = _payload(job_id="avatar_job_cancelled_mid_generation")
    fs = _fake_firestore(payload)
    st = _fake_storage()
    cancelled = {"done": False}

    def cancel_then_pass(source_ref, candidate_ref, metadata):
        if not cancelled["done"]:
            fs.data["avatarJobs"][payload["jobId"]]["status"] = "cancelled"
            cancelled["done"] = True
        return _passing_qa(source_ref, candidate_ref, metadata)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=cancel_then_pass,
        mode="dry_run",
    )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert result.status == "cancelled"
    assert job["status"] == "cancelled"
    assert "previewReadyAt" not in job


def test_worker_terminal_guard_handles_status_flip_during_final_write(monkeypatch):
    monkeypatch.setenv("AVATAR_PREVIEW_REQUIRE_FOUR", "false")
    payload = _payload(job_id="avatar_job_cancelled_at_final_write")
    fs = _fake_recording_atomic_firestore(payload)
    st = _fake_storage()

    def cancel_on_final_preview_update(ref, data):
        if (
            ref.collection == "avatarJobs"
            and data.get("status") == "preview_ready"
            and "previewReadyAt" in data
        ):
            fs.data["avatarJobs"][payload["jobId"]]["status"] = "cancelled"

    fs.before_transaction_set = cancel_on_final_preview_update

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert result.status == "cancelled"
    assert job["status"] == "cancelled"
    assert "previewReadyAt" not in job
    assert fs.last_transaction.ref_get_called_with_transaction is True
    assert fs.last_transaction.transaction_get_called is False
    assert fs.last_transaction.read_after_write is False


def test_worker_does_not_write_preview_ready_before_final_selection(monkeypatch):
    monkeypatch.setenv("AVATAR_PREVIEW_REQUIRE_FOUR", "false")
    payload = _payload(job_id="avatar_job_no_intermediate_preview_ready")
    fs = _fake_firestore(payload)
    st = _fake_storage()
    written_statuses = []

    original_set = FakeDocRef.set

    def record_candidate_status(self, data, merge=True):
        if self.collection == "avatarCandidates" and "status" in data:
            written_statuses.append(data["status"])
        return original_set(self, data, merge=merge)

    monkeypatch.setattr(FakeDocRef, "set", record_candidate_status)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=_passing_qa,
        mode="dry_run",
    )

    assert result.status == "preview_ready"
    assert "preview_ready" in written_statuses
    first_preview_ready = written_statuses.index("preview_ready")
    assert written_statuses[:first_preview_ready] == [
        "qa_pending",
        "hard_pass",
        "qa_pending",
        "hard_pass",
        "qa_pending",
        "hard_pass",
        "qa_pending",
        "hard_pass",
    ]


def test_worker_does_not_preview_conflicting_qa_flags(monkeypatch):
    monkeypatch.setenv("AVATAR_PREVIEW_REQUIRE_FOUR", "false")
    payload = _payload(job_id="avatar_job_conflicting_qa_flags")
    fs = _fake_firestore(payload)
    st = _fake_storage()

    def conflicting_qa(_source_ref, _candidate_ref, _metadata):
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
            requiresHumanReview=True,
            qaVersion="test_conflicting_review",
        )

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=conflicting_qa,
        mode="dry_run",
    )

    assert result.status == "no_previewable_candidates"
    assert result.preview_ready_count == 0
    assert all(
        doc["status"] not in {"preview_ready", "hard_pass"}
        for doc in fs.data["avatarCandidates"].values()
    )


def test_candidate_doc_helper_uses_preview_policy():
    default_doc = build_candidate_doc(
        candidate_id="candidate_default",
        job_id="job",
        uid="u",
        image_ref="gs://bucket/path.png",
    )
    passing_doc = build_candidate_doc(
        candidate_id="candidate_pass",
        job_id="job",
        uid="u",
        image_ref="gs://bucket/path.png",
        qa=_passing_qa("", "", {}),
    )
    conflicting_doc = build_candidate_doc(
        candidate_id="candidate_conflicting",
        job_id="job",
        uid="u",
        image_ref="gs://bucket/path.png",
        qa=AvatarQAResult(
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
            requiresHumanReview=True,
        ),
    )

    assert default_doc["status"] == "needs_review"
    assert passing_doc["status"] == "preview_ready"
    assert conflicting_doc["status"] == "needs_review"


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

    assert result.status == "no_previewable_candidates"
    assert result.needs_review_count == 8
    assert all(
        doc["status"] == "needs_review"
        for doc in fs.data["avatarCandidates"].values()
    )
    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "no_previewable_candidates"
    assert job["errorCode"] == "qa_requires_review"
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
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["mode"] == "dry_run"
    assert report["result"]["status"] in {
        "preview_ready",
        "needs_review",
        "failed",
        "no_previewable_candidates",
    }
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
        timeout=60,
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


def test_flux_generator_resolves_config_once_and_loads_pinned_revision(monkeypatch):
    from avatar_generation.flux_config import FLUX2_KLEIN_ARTIFACT_REVISION, Flux2KleinExecutionConfig

    fake_config = Flux2KleinExecutionConfig(width=640, height=768, num_inference_steps=5, guidance_scale=1.25)
    resolve_calls = []
    monkeypatch.setattr(worker_module, "resolve_flux2_klein_execution_config", lambda: resolve_calls.append("resolve") or fake_config)

    fake_torch = types.ModuleType("torch")
    fake_torch.bfloat16 = object()
    fake_torch.float32 = object()
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    fake_torch.Generator = lambda device: types.SimpleNamespace(manual_seed=lambda seed: (device, seed))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    pretrained_calls = []

    class FakePipeline:
        @classmethod
        def from_pretrained(cls, model_id, **kwargs):
            pretrained_calls.append({"model_id": model_id, **kwargs})
            return cls()

        def __call__(self, *, prompt, image, width, height, num_inference_steps, guidance_scale, generator):
            return types.SimpleNamespace(images=[Image.new("RGB", (16, 16))])

    fake_diffusers = types.ModuleType("diffusers")
    fake_diffusers.Flux2KleinPipeline = FakePipeline
    monkeypatch.setitem(sys.modules, "diffusers", fake_diffusers)

    generator = Flux2KleinImageGenerator()
    generator.generate(source_image=Image.new("RGB", (16, 16)), prompt="p", avoid_prompt="n", seed=7)
    generator.generate(source_image=Image.new("RGB", (16, 16)), prompt="p", avoid_prompt="n", seed=8)

    assert resolve_calls == ["resolve"]
    assert len(pretrained_calls) == 1
    assert pretrained_calls[0]["revision"] == FLUX2_KLEIN_ARTIFACT_REVISION
    assert generator.config is fake_config


def test_flux_generator_call_uses_config_without_unsupported_knobs(monkeypatch):
    from avatar_generation.flux_config import Flux2KleinExecutionConfig

    fake_torch = types.ModuleType("torch")
    fake_torch.Generator = lambda device: types.SimpleNamespace(manual_seed=lambda seed: {"device": device, "seed": seed})
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    calls = []

    class FakePipeline:
        def __call__(self, **kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(images=[Image.new("RGB", (16, 16))])

    config = Flux2KleinExecutionConfig(width=704, height=832, num_inference_steps=6, guidance_scale=1.5)
    generator = Flux2KleinImageGenerator(config)
    monkeypatch.setattr(generator, "_load_pipeline", lambda: FakePipeline())

    generator.generate(source_image=Image.new("RGB", (16, 16)), prompt="positive", avoid_prompt="avoid", seed=99)

    call = calls[0]
    assert call["width"] == 704
    assert call["height"] == 832
    assert call["num_inference_steps"] == 6
    assert call["guidance_scale"] == 1.5
    assert call["generator"]["seed"] == 99
    assert "negative_prompt" not in call
    assert "scheduler" not in call
    assert "strength" not in call


def test_flux_candidate_audit_uses_generator_config_and_seed(monkeypatch):
    from avatar_generation.flux_config import FLUX2_KLEIN_ARTIFACT_REVISION, Flux2KleinExecutionConfig

    config = Flux2KleinExecutionConfig(width=640, height=704, num_inference_steps=5, guidance_scale=1.25)

    class FakeGenerator:
        def __init__(self):
            self.config = config
            self.calls = []
            self.model_load_seconds_total = 0.0

        def generate(self, *, source_image, prompt, avoid_prompt, seed):
            self.calls.append(seed)
            return Image.new("RGB", (16, 16), color=(seed % 255, 80, 120))

    fake_generator = FakeGenerator()
    monkeypatch.setattr(worker_module, "get_flux2_klein_generator", lambda *_a, **_k: fake_generator)
    payload = parse_avatar_generation_payload(_payload(job_id="avatar_job_flux_config_audit"))

    artifacts = generate_candidate_artifacts(
        payload,
        Image.new("RGB", (32, 32)),
        mode="flux",
        privacy_reference_image=Image.new("RGB", (32, 32)),
        candidate_count=1,
    )

    params = artifacts[0].generation_params
    assert fake_generator.calls == [artifacts[0].seed]
    assert params["seed"] == artifacts[0].seed
    assert params["candidateSeed"] == artifacts[0].seed
    assert params["width"] == 640
    assert params["height"] == 704
    assert params["numInferenceSteps"] == 5
    assert params["guidanceScale"] == 1.25
    assert params["modelArtifactRevision"] == FLUX2_KLEIN_ARTIFACT_REVISION
    assert "promptHash" not in params
    assert "sourceReferenceAudit" not in params


def test_flux_generator_cache_key_uses_model_revision_and_config_only():
    from avatar_generation.flux_config import Flux2KleinExecutionConfig

    base = Flux2KleinExecutionConfig(width=640, height=704, num_inference_steps=5, guidance_scale=1.25)
    same = Flux2KleinExecutionConfig(width=640, height=704, num_inference_steps=5, guidance_scale=1.25)
    changed = Flux2KleinExecutionConfig(width=768, height=704, num_inference_steps=5, guidance_scale=1.25)

    assert worker_module._flux_generator_cache_key(base) == worker_module._flux_generator_cache_key(same)
    assert worker_module._flux_generator_cache_key(base) != worker_module._flux_generator_cache_key(changed)
    serialized = json.dumps(worker_module._flux_generator_cache_key(base), default=str)
    assert "prompt" not in serialized.lower()
    assert "source" not in serialized.lower()
    assert "image" not in serialized.lower()
    assert "hash" not in serialized.lower()


def test_generate_initial_deadline_is_common_path_after_trait_block():
    source = (REPO_ROOT / "lib" / "ai_recommend_model" / "avatar_generation" / "worker.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    marker = 'worker_deadline.ensure_can_continue("generate_initial", min_remaining_seconds=30)'
    assert marker in source
    line = next(line for line in source.splitlines() if marker in line)
    assert line.startswith("        worker_deadline")

def test_worker_reference_profile_and_readyz_release_posture_contract(monkeypatch):
    import avatar_generation.worker as worker
    import avatar_generation.worker_service as worker_service

    monkeypatch.setenv("AVATAR_REFERENCE_PROFILE", "fidelity_balanced")
    monkeypatch.setenv(
        "AVATAR_FLUX_MODEL_ARTIFACT_REVISION",
        "e7b7dc27f91deacad38e78976d1f2b499d76a294",
    )
    monkeypatch.setenv("AVATAR_FIDELITY_CORRIDOR_MODE", "shadow")
    monkeypatch.setenv(
        "AVATAR_FIDELITY_CORRIDOR_CALIBRATION_VERSION",
        "uncalibrated",
    )
    monkeypatch.setenv("AVATAR_PUBLIC_ROLLOUT_ENABLED", "false")

    config = worker._reference_preprocess_config_from_env()
    assert config.profile_name == "fidelity_balanced"

    release = worker_service.readyz_status()["releasePosture"]
    assert release == {
        "fluxModelArtifactRevision": "e7b7dc27f91deacad38e78976d1f2b499d76a294",
        "promptVersion": "seolleyeon_avatar_v3_flux2_klein",
        "referenceProfile": {
            "name": "fidelity_balanced",
            "version": "fidelity_balanced_v1",
        },
        "fidelityCorridor": {
            "mode": "shadow",
            "calibrationVersion": "uncalibrated",
            "enforced": False,
        },
        "publicRollout": False,
    }


def test_worker_reference_profile_unknown_value_falls_back_to_privacy_strict(monkeypatch):
    import avatar_generation.worker as worker

    monkeypatch.setenv("AVATAR_REFERENCE_PROFILE", "not-a-profile")
    config = worker._reference_preprocess_config_from_env()
    assert config.profile_name == "privacy_strict"
