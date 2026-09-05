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

from avatar_generation.trait_card import validate_trait_card_response
import avatar_generation.worker as worker_module
from avatar_generation.jobs import build_candidate_doc
from avatar_generation.qa import AvatarQAResult
from avatar_generation.worker import (
    AvatarGenerationError,
    AvatarWorkerDeadline,
    DEFAULT_AVATAR_TEMP_BUCKET,
    DEFAULT_SOURCE_PHOTO_BUCKET,
    candidate_id_for,
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
from avatar_generation.analysis.avatar_source_quality import SourceQualitySignals
from avatar_generation.source_selection_runtime import (
    NO_ELIGIBLE_SOURCE_ERROR,
    SourceSelectionError,
)


def test_worker_deadline_exposes_absolute_provider_deadline():
    deadline = AvatarWorkerDeadline(
        started_at=100.0,
        max_request_seconds=1800,
        max_job_seconds=1500,
        soft_stop_margin_seconds=30,
    )

    assert deadline.deadline_monotonic() == 1600.0


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
    def __init__(self, data=b"", generation=""):
        self.data = data
        self.generation = generation
        self.cache_control = None

    def exists(self):
        return bool(self.data)

    def reload(self):
        return None

    def download_as_bytes(self, **_kwargs):
        return self.data

    def upload_from_string(self, data, **_kwargs):
        self.data = data

    def patch(self):
        return None

    def delete(self, **_kwargs):
        self.data = b""


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


def _jpeg_bytes(color=(128, 96, 80)):
    out = io.BytesIO()
    Image.new("RGB", (32, 32), color=color).save(out, format="JPEG", quality=90)
    return out.getvalue()


def _payload(job_id="avatar_job_1", uid="u1"):
    return {
        "jobId": job_id,
        "uid": uid,
        "sourcePhotoIds": ["src_001"],
        "sourcePhotoRefs": [
            f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_001.jpg"
        ],
        "sourcePhotoObjectGenerations": ["101"],
        "sourceSelectionMode": "quality_selector_v1",
        "candidateCount": 4,
        "modelId": worker_module.CANONICAL_AZURE_WORKER_MODE,
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
                    "sourcePhotoObjectGenerations": list(
                        payload["sourcePhotoObjectGenerations"]
                    ),
                    "sourceSelectionMode": payload["sourceSelectionMode"],
                    "sourceSelection": {"status": "selected"},
                    "selectedSource": {
                        "photoId": payload["sourcePhotoIds"][0],
                        "gcsUri": payload["sourcePhotoRefs"][0],
                        "objectGeneration": payload[
                            "sourcePhotoObjectGenerations"
                        ][0],
                    },
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
            DEFAULT_SOURCE_PHOTO_BUCKET: FakeBucket(
                {
                    "users/u1/source/src_001.jpg": FakeBlob(
                        _jpeg_bytes(), generation="101"
                    )
                }
            ),
            DEFAULT_AVATAR_TEMP_BUCKET: FakeBucket({}),
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

class RetiredGeneratorTestDouble:
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
        f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_001.jpg"
    ]

    with pytest.raises(AvatarGenerationError, match="uid"):
        parse_avatar_generation_payload(payload)


def test_quality_selector_payload_preserves_candidate_generation_pins():
    payload = _payload()
    payload.update(
        {
            "sourcePhotoIds": ["src_001", "src_002"],
            "sourcePhotoRefs": [
                f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_001.jpg",
                f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_002.jpg",
            ],
            "sourcePhotoObjectGenerations": ["101", "102"],
            "sourceSelectionMode": "quality_selector_v1",
            "candidateCount": 2,
            "modelId": "azure_gpt_image_2",
        }
    )

    parsed = parse_avatar_generation_payload(payload)

    assert parsed.source_photo_object_generations == ["101", "102"]
    assert parsed.source_selection_mode == "quality_selector_v1"


def test_quality_selector_locks_best_source_once_before_generation(monkeypatch):
    payload_data = _payload(job_id="avatar_job_select_once")
    refs = [
        f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_001.jpg",
        f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_002.jpg",
    ]
    payload_data.update({
        "sourcePhotoIds": ["src_001", "src_002"],
        "sourcePhotoRefs": refs,
        "sourcePhotoObjectGenerations": ["101", "102"],
        "sourceSelectionMode": "quality_selector_v1",
        "candidateCount": 2,
        "modelId": "azure_gpt_image_2",
    })
    private_sources = [
        {
            "photoId": photo_id,
            "gcsUri": ref,
            "objectGeneration": generation,
            "status": "active",
            "avatarGenerationState": "selection_candidate",
            "purpose": {"avatarGeneration": True},
        }
        for photo_id, ref, generation in zip(
            payload_data["sourcePhotoIds"], refs, ["101", "102"]
        )
    ]
    fs = AtomicFakeFirestore({
        "avatarJobs": {payload_data["jobId"]: {
            **payload_data,
            "status": "queued",
            "avatarSourceSelectionVersion": 1,
            "sourceSelection": {"status": "pending"},
        }},
        "userPrivateMedia": {"u1": {
            "currentAvatarJobId": payload_data["jobId"],
            "avatarSourceSelectionVersion": 1,
            "sourcePhotos": private_sources,
        }},
        "users": {"u1": {"avatar": {"status": "queued"}}},
    })

    class PinnedBlob(FakeBlob):
        def __init__(self, data, generation):
            super().__init__(data)
            self.generation = generation
            self.content_type = "image/jpeg"

        def reload(self):
            return None

        def download_as_bytes(self, **_kwargs):
            return self.data

    bucket = FakeBucket({
        "users/u1/source/src_001.jpg": PinnedBlob(_jpeg_bytes(), "101"),
        "users/u1/source/src_002.jpg": PinnedBlob(_jpeg_bytes(), "102"),
    })
    st = FakeStorage({DEFAULT_SOURCE_PHOTO_BUCKET: bucket})
    monkeypatch.setattr(worker_module, "SmallFaceSourcePipeline", lambda **_kwargs: object())
    monkeypatch.setattr(
        worker_module,
        "analyze_avatar_source_image",
        lambda *_args, **_kwargs: types.SimpleNamespace(detector_metadata={}),
    )

    def signals(*, photo_id, stable_order, analysis):
        del analysis
        return SourceQualitySignals(
            photo_id=photo_id,
            stable_order=stable_order,
            image_width=1200,
            image_height=1600,
            primary_face_confidence=0.96,
            primary_bbox=(0.28, 0.18, 0.44, 0.42),
            face_short_side_px=520,
            face_sharpness=0.40 if photo_id == "src_001" else 0.95,
            yaw_degrees=4.0,
            pitch_degrees=2.0,
            roll_degrees=1.0,
            illumination_quality=0.9,
            face_luminance=128.0,
            face_visibility=0.95,
            landmarks_reliable=True,
        )

    monkeypatch.setattr(worker_module, "source_quality_signals_from_analysis", signals)
    parsed = parse_avatar_generation_payload(payload_data)
    selected = worker_module._resolve_avatar_source_selection(
        fs, st, parsed, fs.data["avatarJobs"][payload_data["jobId"]], None
    )

    assert selected.source_photo_ids == ["src_002"]
    assert fs.data["avatarJobs"][payload_data["jobId"]]["selectedSource"]["photoId"] == "src_002"
    assert "selectedAt" in fs.data["avatarJobs"][payload_data["jobId"]]["selectedSource"]
    assert "selectedAt" in fs.data["avatarJobs"][payload_data["jobId"]]["sourceSelection"]
    assert fs.data["userPrivateMedia"]["u1"]["currentAvatarSourcePhotoId"] == "src_002"

    monkeypatch.setattr(
        worker_module,
        "analyze_avatar_source_image",
        lambda *_args, **_kwargs: pytest.fail("selector reran after source lock"),
    )
    selected_again = worker_module._resolve_avatar_source_selection(
        fs, st, parsed, fs.data["avatarJobs"][payload_data["jobId"]], None
    )
    assert selected_again.source_photo_ids == ["src_002"]


def test_no_eligible_source_failure_releases_server_source_lock():
    payload_data = _payload(job_id="avatar_job_no_eligible")
    payload_data.update(
        {
            "sourcePhotoIds": ["src_001", "src_002"],
            "sourcePhotoRefs": [
                f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_001.jpg",
                f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_002.jpg",
            ],
            "sourcePhotoObjectGenerations": ["101", "102"],
            "sourceSelectionMode": "quality_selector_v1",
            "candidateCount": 2,
            "modelId": "azure_gpt_image_2",
        }
    )
    source_photos = [
        {
            "photoId": photo_id,
            "gcsUri": source_ref,
            "objectGeneration": generation,
            "status": "active",
            "avatarGenerationState": "selection_candidate",
            "purpose": {"avatarGeneration": True},
        }
        for photo_id, source_ref, generation in zip(
            payload_data["sourcePhotoIds"],
            payload_data["sourcePhotoRefs"],
            payload_data["sourcePhotoObjectGenerations"],
        )
    ]
    fs = FakeFirestore(
        {
            "avatarJobs": {
                payload_data["jobId"]: {
                    **payload_data,
                    "status": "queued",
                    "sourceSelection": {"status": "pending"},
                }
            },
            "userPrivateMedia": {
                "u1": {
                    "currentAvatarJobId": payload_data["jobId"],
                    "sourcePhotos": source_photos,
                }
            },
            "users": {"u1": {"avatar": {"status": "queued"}}},
        }
    )
    payload = parse_avatar_generation_payload(payload_data)

    result = worker_module._finalize_source_selection_failure(
        fs,
        payload,
        SourceSelectionError(NO_ELIGIBLE_SOURCE_ERROR),
    )

    assert result.status == "failed"
    job = fs.data["avatarJobs"][payload.job_id]
    assert job["errorCode"] == NO_ELIGIBLE_SOURCE_ERROR
    assert job["retryable"] is False
    private = fs.data["userPrivateMedia"][payload.uid]
    assert private["currentAvatarJobId"] == ""
    assert private["avatarSourceSelection"]["failureCode"] == NO_ELIGIBLE_SOURCE_ERROR
    assert {
        source["avatarGenerationState"] for source in private["sourcePhotos"]
    } == {"selection_rejected"}
    user = fs.data["users"][payload.uid]
    assert user["avatar.status"] == "source_rejected"
    assert user["avatar.errorCode"] == NO_ELIGIBLE_SOURCE_ERROR
    assert user["onboarding.avatarGenerationJobId"] == ""


def test_selected_source_populates_consented_chat_real_photo_asset():
    payload = parse_avatar_generation_payload(_payload())
    fs = _fake_firestore()
    st = _fake_storage()
    source_bytes = _jpeg_bytes()

    worker_module._persist_chat_real_photo_if_consented(
        fs,
        st,
        payload,
        {"chatPartnerRealPhotoDisclosure": True},
        source_bytes,
    )

    path = "users/u1/chat-profile/src_001.jpg"
    chat_blob = st.bucket(worker_module.DEFAULT_CHAT_PROFILE_PHOTO_BUCKET).blob(path)
    assert chat_blob.data == source_bytes
    chat_real_photo = fs.data["userPrivateMedia"]["u1"]["chatRealPhoto"]
    assert chat_real_photo["enabled"] is True
    assert chat_real_photo["sourcePhotoId"] == "src_001"
    assert chat_real_photo["storagePath"] == path
    assert chat_real_photo["contentType"] == "image/jpeg"


def test_all_ineligible_source_set_stops_before_azure_provider(monkeypatch):
    payload_data = _payload(job_id="avatar_job_all_sources_ineligible")
    refs = [
        f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_001.jpg",
        f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_002.jpg",
    ]
    payload_data.update(
        {
            "sourcePhotoIds": ["src_001", "src_002"],
            "sourcePhotoRefs": refs,
            "sourcePhotoObjectGenerations": ["101", "102"],
            "sourceSelectionMode": "quality_selector_v1",
            "candidateCount": 2,
            "modelId": "azure_gpt_image_2",
        }
    )
    private_sources = [
        {
            "photoId": photo_id,
            "gcsUri": source_ref,
            "objectGeneration": generation,
            "status": "active",
            "avatarGenerationState": "selection_candidate",
            "purpose": {"avatarGeneration": True},
        }
        for photo_id, source_ref, generation in zip(
            payload_data["sourcePhotoIds"], refs, ["101", "102"]
        )
    ]
    fs = AtomicFakeFirestore(
        {
            "avatarJobs": {
                payload_data["jobId"]: {
                    **payload_data,
                    "status": "queued",
                    "avatarSourceSelectionVersion": 1,
                    "sourceSelection": {"status": "pending"},
                }
            },
            "userPrivateMedia": {
                "u1": {
                    "currentAvatarJobId": payload_data["jobId"],
                    "avatarSourceSelectionVersion": 1,
                    "photoConsent": {
                        "avatarGeneration": True,
                        "profileDisplayOriginalPhoto": False,
                    },
                    "sourcePhotos": private_sources,
                }
            },
            "users": {"u1": {"avatar": {"status": "queued"}}},
            "avatarCandidates": {},
        }
    )

    class PinnedBlob(FakeBlob):
        def __init__(self, generation):
            super().__init__(_jpeg_bytes())
            self.generation = generation
            self.content_type = "image/jpeg"

        def reload(self):
            return None

        def download_as_bytes(self, **_kwargs):
            return self.data

    st = FakeStorage(
        {
            DEFAULT_SOURCE_PHOTO_BUCKET: FakeBucket(
                {
                    "users/u1/source/src_001.jpg": PinnedBlob("101"),
                    "users/u1/source/src_002.jpg": PinnedBlob("102"),
                }
            )
        }
    )
    monkeypatch.setattr(worker_module, "SmallFaceSourcePipeline", lambda **_kwargs: object())
    monkeypatch.setattr(
        worker_module,
        "analyze_avatar_source_image",
        lambda *_args, **_kwargs: types.SimpleNamespace(detector_metadata={}),
    )
    monkeypatch.setattr(
        worker_module,
        "source_quality_signals_from_analysis",
        lambda *, photo_id, stable_order, analysis: SourceQualitySignals(
            photo_id=photo_id,
            stable_order=stable_order,
            image_width=1200,
            image_height=1600,
            primary_face_confidence=None,
            primary_bbox=None,
            corrupt=True,
        ),
    )
    provider_calls = []
    monkeypatch.setattr(
        worker_module,
        "get_azure_gpt_image2_provider",
        lambda: provider_calls.append("constructed") or pytest.fail(
            "Azure provider must not be constructed for ineligible sources"
        ),
    )

    result = process_avatar_generation_payload(
        payload_data,
        firestore_client=fs,
        storage_client=st,
        mode=worker_module.CANONICAL_AZURE_WORKER_MODE,
    )

    assert result.status == "failed"
    assert provider_calls == []
    assert (
        fs.data["avatarJobs"][payload_data["jobId"]]["errorCode"]
        == NO_ELIGIBLE_SOURCE_ERROR
    )
    assert not st.bucket(DEFAULT_SOURCE_PHOTO_BUCKET).blob(
        "users/u1/source/src_001.jpg"
    ).exists()
    assert not st.bucket(DEFAULT_SOURCE_PHOTO_BUCKET).blob(
        "users/u1/source/src_002.jpg"
    ).exists()
    for source in fs.data["userPrivateMedia"]["u1"]["sourcePhotos"]:
        assert source["status"] == "source_deleted"
        assert "gcsUri" not in source
        assert "storagePath" not in source


def test_candidate_seed_and_id_are_deterministic():
    assert candidate_id_for("avatar_job_1", 0) == "cand_avatar_job_1_01"
    assert deterministic_seed("avatar_job_1", 0) == deterministic_seed("avatar_job_1", 0)
    assert deterministic_seed("avatar_job_1", 0) != deterministic_seed("avatar_job_1", 1)


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

    assert resolve_worker_mode(None) == "azure_gpt_image_2"


def test_production_rejects_dry_run_mode(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(AvatarGenerationError, match="dry_run"):
        resolve_worker_mode("dry_run")

    monkeypatch.setenv("AVATAR_WORKER_DRY_RUN", "true")
    with pytest.raises(AvatarGenerationError, match="dry_run"):
        resolve_worker_mode(None)


def test_worker_dry_run_writes_two_preview_ready_candidates():
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
    assert result.preview_ready_count == 2
    assert len(fs.data["avatarCandidates"]) == 2
    assert fs.data["avatarJobs"][payload["jobId"]]["status"] == "preview_ready"
    assert fs.data["avatarJobs"][payload["jobId"]]["errorCode"] == ""
    assert fs.data["avatarJobs"][payload["jobId"]]["errorMessage"] == ""
    assert all(doc["qa"]["previewAllowed"] is True for doc in fs.data["avatarCandidates"].values())
    assert len(st.buckets[DEFAULT_AVATAR_TEMP_BUCKET].blobs) == 2


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
            DEFAULT_SOURCE_PHOTO_BUCKET: FakeBucket(
                    {
                        "users/u1/source/src_001.jpg": FakeBlob(
                            _png_bytes((120, 64, 48)), generation="101"
                        )
                    }
            ),
            DEFAULT_AVATAR_TEMP_BUCKET: FakeBucket({}),
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


def test_worker_uses_env_avatar_temp_bucket(monkeypatch):
    monkeypatch.setenv("AVATAR_TEMP_BUCKET", "seolleyeon-final-avatar-temp")
    payload = _payload(job_id="avatar_job_env_bucket")
    fs = _fake_firestore(payload)
    st = FakeStorage(
        {
            DEFAULT_SOURCE_PHOTO_BUCKET: FakeBucket(
                {
                    "users/u1/source/src_001.jpg": FakeBlob(
                        _png_bytes(), generation="101"
                    )
                }
            ),
            DEFAULT_AVATAR_TEMP_BUCKET: FakeBucket({}),
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
    assert len(st.buckets[DEFAULT_AVATAR_TEMP_BUCKET].blobs) == 2
    assert all(
        doc["imageRef"].startswith(f"gs://{DEFAULT_AVATAR_TEMP_BUCKET}/")
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
    assert job["cost"]["candidateCount"] == 2
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
    assert cost["candidateCount"] == 6
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
            source_photo_bucket=DEFAULT_SOURCE_PHOTO_BUCKET,
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
    second["sourcePhotoRefs"] = [f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/missing.jpg"]
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
    assert result.rejected_count == 4
    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "no_previewable_candidates"
    assert job["errorCode"] == "too_identifiable_candidates"
    assert job["generationPlan"]["initialCount"] == 2
    assert job["generationPlan"]["extraCount"] == 2
    assert job["generationPlan"]["totalGenerated"] == 4


def test_worker_exposes_one_safe_candidate_without_filling_with_rejected_candidates():
    payload = _payload(job_id="avatar_job_one_safe_preview")
    fs = _fake_firestore(payload)
    st = _fake_storage()
    qa_calls = []

    def only_first_candidate_passes(source_ref, candidate_ref, metadata):
        qa_calls.append(metadata["candidateId"])
        if len(qa_calls) == 1:
            return _passing_qa(source_ref, candidate_ref, metadata)
        return _rejecting_qa(source_ref, candidate_ref, metadata)

    result = process_avatar_generation_payload(
        payload,
        firestore_client=fs,
        storage_client=st,
        qa_runner=only_first_candidate_passes,
        mode="dry_run",
    )

    assert result.status == "preview_ready"
    assert result.preview_ready_count == 1
    assert result.rejected_count == 3
    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["generationPlan"]["initialCount"] == 2
    assert job["generationPlan"]["extraCount"] == 2
    assert job["generationPlan"]["previewCount"] == 1
    selected = [
        candidate
        for candidate in fs.data["avatarCandidates"].values()
        if candidate["rerank"]["selectedForPreview"] is True
    ]
    assert len(selected) == 1
    assert selected[0]["status"] == "preview_ready"
    assert selected[0]["qa"]["rejectReasons"] == []


def test_worker_requires_full_preview_count_when_policy_requires_four(monkeypatch):
    monkeypatch.setenv("AVATAR_PREVIEW_REQUIRE_FOUR", "true")
    monkeypatch.setenv("AVATAR_PREVIEW_COUNT", "4")
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
    assert result.needs_review_count == 2
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
    assert result.preview_ready_count == 2
    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "preview_ready"
    assert job["generationPlan"]["softPassCount"] == 2
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
            f"failed reading gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_001.jpg"
        )

    monkeypatch.setattr("avatar_generation.worker.generate_candidate_artifacts", boom)

    with pytest.raises(AvatarGenerationError):
        process_avatar_generation_payload(
            payload,
            firestore_client=fs,
            storage_client=_fake_storage(),
            qa_runner=_passing_qa,
            mode="dry_run",
        )

    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "failed"
    assert job["errorCode"] == "avatar_generation_worker_error"
    assert "gs://" not in job["errorMessage"]
    assert DEFAULT_SOURCE_PHOTO_BUCKET not in job["errorMessage"]
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
    assert result.needs_review_count == 4
    assert all(
        doc["status"] == "needs_review"
        for doc in fs.data["avatarCandidates"].values()
    )
    job = fs.data["avatarJobs"][payload["jobId"]]
    assert job["status"] == "no_previewable_candidates"
    assert job["errorCode"] == "qa_requires_review"
    assert job["generationPlan"]["initialCount"] == 2
    assert job["generationPlan"]["extraCount"] == 2


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
    from avatar_generation.qa_preflight import QAComponentReadiness, QARuntimeReadiness

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AVATAR_WORKER_AUTH_MODE", "cloud_run_iam")
    monkeypatch.setenv("AVATAR_BATCHING_ENABLED", "true")
    monkeypatch.setenv("AVATAR_BATCH_MODE", "drain")
    monkeypatch.setattr(
        worker_service,
        "get_qa_runtime_readiness",
        lambda: QARuntimeReadiness(
            components=(
                QAComponentReadiness(
                    name="qaRuntime",
                    status="available",
                    critical=True,
                    reason="test_ready",
                ),
            )
        ),
    )

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
            f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_001.jpg",
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
            f"gs://{DEFAULT_SOURCE_PHOTO_BUCKET}/users/u1/source/src_001.jpg",
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
        "provider": "azure",
        "generationBackend": "azure_gpt_image_2",
        "modelFamily": "gpt-image-2",
        "promptVersion": "avatar_general_prompt_v1",
        "sourceInputMode": "storage_normalized_original_direct",
        "uploadNormalization": "existing_avatar_media_ingestion",
        "preGenerationTransform": "none",
        "azureConfig": {
            "endpointConfigured": False,
            "deploymentConfigured": False,
            "apiVersionConfigured": False,
            "apiStyle": "foundry_v1",
            "credentialConfigured": False,
            "maxAttempts": 3,
            "requestTimeoutSeconds": 90.0,
            "maxConcurrency": 1,
            "requestsPerMinute": 2,
            "qualityConfigured": False,
            "sizeConfigured": False,
        },
        "generationPrerequisites": {
            "referencePreprocessing": False,
            "traitExtraction": False,
        },
            "fidelityCorridor": {
                "mode": "shadow",
                "calibrationVersion": "uncalibrated",
                "enforced": False,
            },
            "publicRollout": False,
            "g004Endpoints": {
                "paidCalibration": False,
                "qaRecovery": False,
            },
        }


def test_worker_reference_profile_unknown_value_falls_back_to_privacy_strict(monkeypatch):
    import avatar_generation.worker as worker

    monkeypatch.setenv("AVATAR_REFERENCE_PROFILE", "not-a-profile")
    config = worker._reference_preprocess_config_from_env()
    assert config.profile_name == "privacy_strict"
