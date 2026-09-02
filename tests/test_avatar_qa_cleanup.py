import json
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.cleanup import (
    AvatarCleanupError,
    cleanup_expired_avatar_candidates,
    cleanup_user_media,
    select_expired_candidate_cleanup_actions,
)
from avatar_generation.qa import (
    AvatarQAResult,
    apply_avatar_qa_rejection_logic,
    build_avatar_qa_from_signals,
    needs_review_model_unavailable_result,
    run_avatar_candidate_qa,
)


class FakeSnapshot:
    def __init__(self, doc_id, data):
        self.id = doc_id
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class FakeDocRef:
    def __init__(self, store, collection, doc_id):
        self.store = store
        self.collection = collection
        self.doc_id = doc_id

    def get(self):
        return FakeSnapshot(self.doc_id, self.store.get(self.collection, {}).get(self.doc_id))

    def set(self, data, merge=True):
        collection = self.store.setdefault(self.collection, {})
        if merge and self.doc_id in collection:
            collection[self.doc_id].update(data)
        else:
            collection[self.doc_id] = dict(data)

    def delete(self):
        self.store.setdefault(self.collection, {}).pop(self.doc_id, None)


class FakeCollection:
    def __init__(self, store, name):
        self.store = store
        self.name = name

    def document(self, doc_id):
        return FakeDocRef(self.store, self.name, doc_id)

    def stream(self):
        for doc_id, data in self.store.get(self.name, {}).items():
            yield FakeSnapshot(doc_id, data)


class FakeFirestore:
    def __init__(self, data):
        self.data = data

    def collection(self, name):
        return FakeCollection(self.data, name)


class FakeBlob:
    def __init__(self, exists=True):
        self.deleted = False
        self._exists = exists

    def delete(self):
        self.deleted = True
        self._exists = False


class FakeBucket:
    def __init__(self, blobs):
        self.blobs = blobs

    def blob(self, path):
        return self.blobs.setdefault(path, FakeBlob(False))


class FakeStorage:
    def __init__(self, buckets):
        self.buckets = buckets

    def bucket(self, name):
        return self.buckets.setdefault(name, FakeBucket({}))


def _pattern_image(size=(96, 96)):
    image = Image.new("RGB", size, (32, 46, 62))
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], 12):
        color = ((x * 5) % 255, 108, 190 - (x % 80))
        draw.line((x, 0, size[0] - x // 2, size[1]), fill=color, width=3)
    draw.rectangle((14, 16, 54, 66), fill=(214, 164, 104))
    draw.ellipse((42, 28, 84, 82), fill=(78, 132, 186))
    draw.line((4, size[1] - 8, size[0] - 6, 10), fill=(238, 224, 146), width=2)
    return image


def _other_pattern_image(size=(96, 96)):
    image = Image.new("RGB", size, (208, 220, 196))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], 10):
        draw.rectangle((0, y, size[0], y + 4), fill=(64 + y, 78, 96))
    draw.ellipse((8, 12, 58, 62), fill=(172, 84, 118))
    draw.rectangle((58, 34, 90, 88), fill=(44, 122, 108))
    return image


def _save_png(tmp_path, name, image):
    path = tmp_path / name
    image.save(path, format="PNG")
    return str(path)


def test_qa_schema_unknown_model_requires_review_not_preview():
    result = needs_review_model_unavailable_result()
    doc = result.to_document()

    assert doc["previewAllowed"] is False
    assert doc["requiresHumanReview"] is True
    assert doc["qaVersion"] == "avatar_qa_v1_model_unavailable"
    assert "embedding" not in doc


def test_qa_raw_watermark_boolean_does_not_override_child_identity_rejects():
    result = build_avatar_qa_from_signals(
        {
            "adultLike": False,
            "childlikeScore": 0.9,
            "faceSimilarityScore": 0.8,
            "faceSimilarityReliable": True,
            "logoTextWatermarkDetected": True,
            "brandFit": True,
        }
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is False
    assert set(result.rejectReasons) >= {
        "childlike_or_teenager",
        "too_identifiable",
    }
    assert "logo_text_watermark" not in result.rejectReasons
    assert result.watermarkQaAction == "allow"
    assert result.textLogoWatermarkRisk == "low"


def test_qa_passes_only_low_risk_complete_signal_set():
    result = build_avatar_qa_from_signals(
        {
            "adultLike": True,
            "childlikeScore": 0.1,
            "faceSimilarityScore": 0.2,
            "faceSimilarityReliable": True,
            "beautificationScore": 0.1,
            "uniqueMarkCopied": False,
            "logoTextWatermarkDetected": False,
            "backgroundLeakageRisk": "low",
            "secondaryFaceLeakageRisk": "low",
            "textLogoWatermarkRisk": "low",
            "cropConsistent": True,
            "cropIsolationQuality": "pass",
            "brandFit": True,
        }
    )

    assert result.previewAllowed is True
    assert result.requiresHumanReview is False
    assert result.rejectReasons == []
    doc = result.to_document()
    assert doc["backgroundLeakageRisk"] == "low"
    assert doc["secondaryFaceLeakageRisk"] == "low"
    assert doc["textLogoWatermarkRisk"] == "low"
    assert doc["cropIsolationQuality"] == "pass"


def test_qa_raw_sign_boolean_does_not_override_other_hard_rejects():
    result = build_avatar_qa_from_signals(
        {
            "adultLike": True,
            "childlikeScore": 0.1,
            "faceSimilarityScore": 0.2,
            "beautificationScore": 0.1,
            "uniqueMarkCopied": False,
            "logoTextWatermarkDetected": False,
            "cropConsistent": True,
            "brandFit": True,
            "multipleFacesGenerated": True,
            "secondaryPersonGenerated": True,
            "originalBackgroundReproduced": True,
            "schoolSignDetected": True,
            "fullBodyInvented": True,
            "primaryFaceConfidence": 0.87,
        }
    )
    doc = result.to_document()

    assert result.previewAllowed is False
    assert result.requiresHumanReview is False
    assert set(doc["rejectReasons"]) >= {
        "multiple_faces_generated",
        "secondary_person_generated",
        "background_leakage",
        "crop_expanded_to_unseen_body",
    }
    assert "logo_text_watermark" not in doc["rejectReasons"]
    assert doc["backgroundLeakageRisk"] == "high"
    assert doc["secondaryFaceLeakageRisk"] == "high"
    assert doc["watermarkQaAction"] == "allow"
    assert doc["textLogoWatermarkRisk"] == "low"
    assert doc["cropIsolationQuality"] == "fail"
    assert doc["primaryFaceConfidence"] == 0.87


def test_qa_rejection_logic_does_not_store_raw_embeddings():
    result = apply_avatar_qa_rejection_logic(
        AvatarQAResult(
            privacyQa="fail",
            faceSimilarityScore=0.99,
        )
    )
    doc = result.to_document()

    assert "too_identifiable" in doc["rejectReasons"]
    assert "vector" not in doc
    assert "embedding" not in doc


def test_qa_debug_sanitizer_removes_private_media_fields_and_values():
    result = AvatarQAResult(
        debug={
            "sourcePhotoRef": "gs://seolleyeon-final-private-source-photos/users/u/source/a.jpg",
            "sourcePhotoRefs": ["gs://seolleyeon-private-source-photos/users/u/source/b.jpg"],
            "source_photo_refs": ["gs://seolleyeon-private-source-photos/users/u/source/c.jpg"],
            "gcsUri": "gcs://seolleyeon-final-avatar-temp/users/u/candidate.png",
            "gcs_uri": "gcs://seolleyeon-final-avatar-temp/users/u/candidate-2.png",
            "signedUrl": "https://example.test/c.png?X-Goog-Signature=secret",
            "signed_url": "https://example.test/d.png?X-Goog-Signature=secret",
            "nested": {
                "userPrivateMedia": "userPrivateMedia/u",
                "user_private_media": "userPrivateMedia/u",
                "clipEmbeddings": "clipEmbeddings/u",
                "clip_embeddings": "clipEmbeddings/u",
                "safeScore": 0.42,
            },
        }
    )

    doc = result.to_document()
    serialized = json.dumps(doc["debug"], sort_keys=True).lower()

    assert doc["debug"]["nested"]["safeScore"] == 0.42
    for forbidden in (
        "sourcephotoref",
        "sourcephotorefs",
        "source_photo_refs",
        "gcsuri",
        "gcs_uri",
        "signedurl",
        "signed_url",
        "userprivatemedia",
        "user_private_media",
        "clipembeddings",
        "clip_embeddings",
        "seolleyeon-final-private-source-photos",
        "x-goog-signature",
    ):
        assert forbidden not in serialized


def test_run_avatar_candidate_qa_rejects_corrupt_candidate(tmp_path):
    source_ref = _save_png(tmp_path, "source.png", _pattern_image())
    candidate_ref = tmp_path / "candidate.png"
    candidate_ref.write_bytes(b"not an image")

    result = run_avatar_candidate_qa(source_ref, str(candidate_ref), {})
    doc = result.to_document()

    assert doc["previewAllowed"] is False
    assert doc["requiresHumanReview"] is False
    assert "undecodable_image" in doc["rejectReasons"]


def test_run_avatar_candidate_qa_rejects_blank_candidate(tmp_path):
    source_ref = _save_png(tmp_path, "source.png", _pattern_image())
    candidate_ref = _save_png(
        tmp_path,
        "candidate.png",
        Image.new("RGB", (96, 96), (244, 244, 244)),
    )

    result = run_avatar_candidate_qa(source_ref, candidate_ref, {})

    assert result.previewAllowed is False
    assert result.requiresHumanReview is False
    assert "blank_or_monochrome_image" in result.rejectReasons


def test_run_avatar_candidate_qa_rejects_identical_source_and_candidate(tmp_path):
    source = _pattern_image()
    source_ref = _save_png(tmp_path, "source.png", source)
    candidate_ref = _save_png(tmp_path, "candidate.png", source.copy())

    result = run_avatar_candidate_qa(source_ref, candidate_ref, {})

    assert result.previewAllowed is False
    assert result.requiresHumanReview is False
    assert "source_candidate_identical" in result.rejectReasons
    assert "too_identifiable" in result.rejectReasons


def test_run_avatar_candidate_qa_does_not_hard_reject_perceptual_similarity_only(tmp_path):
    source = _pattern_image()
    candidate = source.copy()
    draw = ImageDraw.Draw(candidate)
    draw.rectangle((76, 76, 88, 88), fill=(18, 24, 36))
    source_ref = _save_png(tmp_path, "source.png", source)
    candidate_ref = _save_png(tmp_path, "candidate.png", candidate)

    result = run_avatar_candidate_qa(source_ref, candidate_ref, {})

    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert "too_identifiable" not in result.rejectReasons
    assert result.faceSimilarityScore is None
    assert result.debug["scores"]["perceptualSimilarityScore"] is not None


def test_run_avatar_candidate_qa_marks_medium_similarity_for_review(tmp_path):
    source = _pattern_image()
    candidate = Image.blend(source, _other_pattern_image(), alpha=0.90)
    source_ref = _save_png(tmp_path, "source.png", source)
    candidate_ref = _save_png(tmp_path, "candidate.png", candidate)

    result = run_avatar_candidate_qa(source_ref, candidate_ref, {})

    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert result.identifiabilityRisk == "medium"
    assert result.faceSimilarityScore is None
    assert result.debug["scores"]["perceptualSimilarityScore"] is not None
    assert result.rejectReasons == []


def test_run_avatar_candidate_qa_rejects_signed_url_markers(tmp_path):
    source_ref = _save_png(tmp_path, "source.png", _pattern_image())
    candidate_ref = _save_png(tmp_path, "candidate.png", _other_pattern_image())

    result = run_avatar_candidate_qa(
        f"{source_ref}?X-Goog-Signature=abc",
        candidate_ref,
        {"candidatePreviewUrl": "https://example.test/avatar.png?GoogleAccessId=abc"},
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is False
    assert "signed_url_marker" in result.rejectReasons


def test_run_avatar_candidate_qa_model_unavailable_needs_review(tmp_path):
    source_ref = _save_png(tmp_path, "source.png", _pattern_image())
    candidate_ref = _save_png(tmp_path, "candidate.png", _other_pattern_image())

    result = run_avatar_candidate_qa(
        source_ref,
        candidate_ref,
        {"modelsUnavailable": True},
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert result.rejectReasons == []
    assert result.brandQa == "needs_review"
    assert result.childlikeRisk == "medium"


def test_run_avatar_candidate_qa_uses_processed_reference_metadata(tmp_path):
    source_ref = _save_png(tmp_path, "source.png", _pattern_image())
    candidate_ref = _save_png(tmp_path, "candidate.png", _other_pattern_image())

    result = run_avatar_candidate_qa(
        source_ref,
        candidate_ref,
        {
            "sourceAnalysis": {
                "primaryFaceConfidence": 0.91,
                "secondaryFaceCount": 1,
                "backgroundNeutralizationRequired": True,
            },
            "referencePreprocess": {
                "primaryCropApplied": True,
                "cropType": "head_and_shoulders",
                "backgroundNeutralized": True,
                "backgroundNeutralization": {
                    "secondaryFaceCount": 1,
                    "secondaryFaceAction": "removed_with_background",
                },
            },
            "qaSignals": {
                "adultLike": True,
                "brandFit": True,
                "cropConsistent": True,
                "cropIsolationQuality": "pass",
                "logoTextWatermarkDetected": False,
                "backgroundLeakageRisk": "low",
                "secondaryFaceLeakageRisk": "low",
                "textLogoWatermarkRisk": "low",
                "uniqueMarkCopied": False,
                "faceSimilarityScore": 0.1,
                "faceSimilarityReliable": True,
                "childlikeScore": 0.1,
                "beautificationScore": 0.1,
            },
        },
    )
    doc = result.to_document()

    assert doc["primaryFaceConfidence"] == 0.91
    assert doc["backgroundLeakageRisk"] == "low"
    assert doc["secondaryFaceLeakageRisk"] == "low"
    assert doc["cropIsolationQuality"] == "pass"
    assert doc["previewAllowed"] is True


def test_run_avatar_candidate_qa_routes_invented_eyewear_to_review(tmp_path):
    source_ref = _save_png(tmp_path, "source.png", _pattern_image())
    candidate_ref = _save_png(tmp_path, "candidate.png", _other_pattern_image())

    result = run_avatar_candidate_qa(
        source_ref,
        candidate_ref,
        {
            "sourceTraitCard": {
                "eyewear_present": False,
                "eyewear_confidence": "high",
                "eyewear_style": "none",
            },
            "qaSignals": {
                "adultLike": True,
                "brandFit": True,
                "cropConsistent": True,
                "logoTextWatermarkDetected": False,
                "uniqueMarkCopied": False,
                "faceSimilarityScore": 0.1,
                "childlikeScore": 0.1,
                "beautificationScore": 0.1,
                "candidateEyewearPresent": True,
            },
        },
    )
    doc = result.to_document()

    assert doc["previewAllowed"] is False
    assert doc["requiresHumanReview"] is True
    assert doc["rejectReasons"] == []
    assert "invented_eyewear_from_no_glasses_source" in doc["reviewReasons"]
    assert doc["candidateTraitConsistency"]["eyewearMatch"] == "fail"
    assert doc["candidateTraitConsistency"]["eyewearReason"] == "invented_eyewear_from_no_glasses_source"


def test_run_avatar_candidate_qa_routes_omitted_eyewear_to_review(tmp_path):
    source_ref = _save_png(tmp_path, "source.png", _pattern_image())
    candidate_ref = _save_png(tmp_path, "candidate.png", _other_pattern_image())

    result = run_avatar_candidate_qa(
        source_ref,
        candidate_ref,
        {
            "sourceTraitCard": {
                "eyewear_present": True,
                "eyewear_confidence": "high",
                "eyewear_style": "rectangular",
            },
            "candidateTraitCard": {
                "eyewear_present": False,
                "eyewear_confidence": "high",
                "eyewear_style": "none",
            },
            "qaSignals": {
                "adultLike": True,
                "brandFit": True,
                "cropConsistent": True,
                "logoTextWatermarkDetected": False,
                "uniqueMarkCopied": False,
                "faceSimilarityScore": 0.1,
                "childlikeScore": 0.1,
                "beautificationScore": 0.1,
            },
        },
    )
    doc = result.to_document()

    assert doc["previewAllowed"] is False
    assert doc["requiresHumanReview"] is True
    assert doc["rejectReasons"] == []
    assert "omitted_eyewear_from_glasses_source" in doc["reviewReasons"]
    assert doc["candidateTraitConsistency"]["eyewearMatch"] == "fail"
    assert doc["candidateTraitConsistency"]["eyewearReason"] == "omitted_eyewear_from_glasses_source"


def test_run_avatar_candidate_qa_keeps_unclear_source_eyewear_non_blocking(tmp_path):
    source_ref = _save_png(tmp_path, "source.png", _pattern_image())
    candidate_ref = _save_png(tmp_path, "candidate.png", _other_pattern_image())

    result = run_avatar_candidate_qa(
        source_ref,
        candidate_ref,
        {
            "sourceTraitCard": {
                "eyewear_present": None,
                "eyewear_confidence": "unclear",
            },
            "qaSignals": {
                "adultLike": True,
                "brandFit": True,
                "cropConsistent": True,
                "logoTextWatermarkDetected": False,
                "uniqueMarkCopied": False,
                "faceSimilarityScore": 0.1,
                "childlikeScore": 0.1,
                "beautificationScore": 0.1,
                "candidateEyewearPresent": True,
            },
        },
    )
    doc = result.to_document()

    assert "eyewear_invented_or_omitted" not in doc["rejectReasons"]
    assert doc["candidateTraitConsistency"]["eyewearMatch"] == "uncertain"


def test_run_avatar_candidate_qa_dev_bypass_cannot_work_in_production(monkeypatch):
    monkeypatch.setenv("AVATAR_QA_ALLOW_DEV_BYPASS", "true")
    monkeypatch.setenv("ENVIRONMENT", "production")

    result = run_avatar_candidate_qa(
        "C:/does/not/exist/source.png",
        "C:/does/not/exist/candidate.png",
        {},
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is True
    assert result.qaVersion != "avatar_qa_v1_dev_bypass"


def test_run_avatar_candidate_qa_staging_heuristic_preview_is_non_production_only(
    monkeypatch,
    tmp_path,
):
    source_ref = _save_png(tmp_path, "source.png", _pattern_image())
    candidate_ref = _save_png(tmp_path, "candidate.png", _other_pattern_image())
    monkeypatch.setenv("ENVIRONMENT", "staging")
    monkeypatch.setenv("AVATAR_QA_ALLOW_STAGING_HEURISTIC_PREVIEW", "true")
    monkeypatch.setenv("AVATAR_QA_FACE_SIMILARITY_REVIEW_THRESHOLD", "0.99")
    monkeypatch.setenv("AVATAR_QA_FACE_SIMILARITY_REJECT_THRESHOLD", "1.01")

    result = run_avatar_candidate_qa(source_ref, candidate_ref, {})

    assert result.previewAllowed is False
    assert result.softPass is True
    assert result.requiresHumanReview is False
    assert result.qaVersion == "avatar_qa_v1_staging_heuristic_preview"

    monkeypatch.setenv("ENVIRONMENT", "production")
    production_result = run_avatar_candidate_qa(source_ref, candidate_ref, {})

    assert production_result.previewAllowed is False
    assert production_result.qaVersion != "avatar_qa_v1_staging_heuristic_preview"


def test_run_avatar_candidate_qa_hard_reject_never_allows_preview(tmp_path):
    source_ref = _save_png(tmp_path, "source.png", _pattern_image())
    candidate_ref = _save_png(tmp_path, "candidate.png", Image.new("RGB", (96, 96), (0, 0, 0)))

    result = run_avatar_candidate_qa(
        source_ref,
        candidate_ref,
        {
            "qaSignals": {
                "adultLike": True,
                "brandFit": True,
                "cropConsistent": True,
                "logoTextWatermarkDetected": False,
                "uniqueMarkCopied": False,
                "faceSimilarityScore": 0.1,
                "childlikeScore": 0.1,
                "beautificationScore": 0.1,
            }
        },
    )

    assert result.previewAllowed is False
    assert result.requiresHumanReview is False
    assert "blank_or_monochrome_image" in result.rejectReasons


def test_run_avatar_candidate_qa_does_not_store_raw_embeddings(tmp_path):
    source_ref = _save_png(tmp_path, "source.png", _pattern_image())
    candidate_ref = _save_png(tmp_path, "candidate.png", _other_pattern_image())

    result = run_avatar_candidate_qa(
        source_ref,
        candidate_ref,
        {
            "qaSignals": {
                "adultLike": True,
                "brandFit": True,
                "cropConsistent": True,
                "logoTextWatermarkDetected": False,
                "uniqueMarkCopied": False,
                "faceSimilarityScore": 0.1,
                "childlikeScore": 0.1,
                "beautificationScore": 0.1,
                "sourceEmbedding": [0.1, 0.2, 0.3],
                "candidateEmbedding": [0.4, 0.5, 0.6],
            }
        },
    )
    encoded = json.dumps(result.to_document(), sort_keys=True)

    assert "sourceEmbedding" not in encoded
    assert "candidateEmbedding" not in encoded
    assert "embedding" not in encoded.lower()


def test_expired_candidate_cleanup_selects_only_temp_candidates():
    now = datetime.now(tz=timezone.utc)
    docs = {
        "expired": {
            "candidateId": "expired",
            "status": "preview_ready",
            "expiresAt": (now - timedelta(hours=1)).isoformat(),
            "imageRef": "gs://seolleyeon-final-avatar-temp/users/u/jobs/j/candidates/expired.png",
        },
        "approved": {
            "candidateId": "approved",
            "status": "approved",
            "expiresAt": (now - timedelta(hours=1)).isoformat(),
            "imageRef": "gs://seolleyeon-final-approved-avatars/users/u/avatar/a.png",
        },
        "source": {
            "candidateId": "source",
            "status": "rejected",
            "imageRef": "gs://seolleyeon-final-private-source-photos/users/u/source/src.jpg",
        },
        "needs_review": {
            "candidateId": "needs_review",
            "status": "needs_review",
            "expiresAt": (now - timedelta(hours=1)).isoformat(),
            "imageRef": "gs://seolleyeon-final-avatar-temp/users/u/jobs/j/candidates/needs_review.png",
        },
    }

    actions = select_expired_candidate_cleanup_actions(docs, now=now)

    assert [action.candidate_id for action in actions] == ["expired", "needs_review"]


def test_cleanup_expired_candidates_deletes_only_temp_bucket_objects():
    now = datetime.now(tz=timezone.utc)
    fs = FakeFirestore(
        {
            "avatarCandidates": {
                "cand_1": {
                    "candidateId": "cand_1",
                    "status": "rejected",
                    "imageRef": "gs://seolleyeon-final-avatar-temp/users/u/jobs/j/candidates/cand_1.png",
                },
                "cand_approved": {
                    "candidateId": "cand_approved",
                    "status": "approved",
                    "imageRef": "gs://seolleyeon-final-approved-avatars/users/u/avatar/avatar_1.png",
                    "expiresAt": (now - timedelta(days=3)).isoformat(),
                },
            }
        }
    )
    temp_blob = FakeBlob()
    approved_blob = FakeBlob()
    st = FakeStorage(
        {
            "seolleyeon-final-avatar-temp": FakeBucket(
                {"users/u/jobs/j/candidates/cand_1.png": temp_blob}
            ),
            "seolleyeon-final-approved-avatars": FakeBucket(
                {"users/u/avatar/avatar_1.png": approved_blob}
            ),
        }
    )

    summary = cleanup_expired_avatar_candidates(
        firestore_client=fs,
        storage_client=st,
        now=now,
        dry_run=False,
    )

    assert summary.temp_candidates_deleted == 1
    assert summary.temp_candidates_planned_for_delete == 1
    assert temp_blob.deleted is True
    assert approved_blob.deleted is False
    assert fs.data["avatarCandidates"]["cand_1"]["status"] == "expired"


def test_user_media_cleanup_deletes_source_temp_approved_and_clip():
    fs = FakeFirestore(
        {
            "users": {
                "u1": {
                    "avatar": {
                        "approvedAvatarStoragePath": "gs://seolleyeon-final-approved-avatars/users/u1/avatar/avatar_1.png"
                    }
                }
            },
            "userPrivateMedia": {
                "u1": {
                    "photoConsent": {
                        "avatarGeneration": True,
                        "clipRecommendation": True,
                        "profileDisplayOriginalPhoto": False,
                    },
                    "sourcePhotos": [
                        {
                            "photoId": "src_001",
                            "status": "active",
                            "gcsUri": "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg",
                        }
                    ],
                    "clip": {"embeddingStatus": "ready"},
                }
            },
            "clipEmbeddings": {"u1": {"vector": [0.1], "sourcePhotoIds": ["src_001"]}},
            "avatarCandidates": {
                "cand_1": {
                    "uid": "u1",
                    "status": "preview_ready",
                    "imageRef": "gs://seolleyeon-final-avatar-temp/users/u1/jobs/j/candidates/cand_1.png",
                }
            },
            "avatarJobs": {"avatar_job_1": {"uid": "u1", "status": "queued"}},
        }
    )
    source_blob = FakeBlob()
    temp_blob = FakeBlob()
    approved_blob = FakeBlob()
    st = FakeStorage(
        {
            "seolleyeon-final-private-source-photos": FakeBucket(
                {"users/u1/source/src_001.jpg": source_blob}
            ),
            "seolleyeon-final-avatar-temp": FakeBucket(
                {"users/u1/jobs/j/candidates/cand_1.png": temp_blob}
            ),
            "seolleyeon-final-approved-avatars": FakeBucket(
                {"users/u1/avatar/avatar_1.png": approved_blob}
            ),
        }
    )

    summary = cleanup_user_media(
        uid="u1",
        reason="consent_withdrawal",
        firestore_client=fs,
        storage_client=st,
        dry_run=False,
    )

    assert source_blob.deleted is True
    assert temp_blob.deleted is True
    assert approved_blob.deleted is True
    assert "u1" not in fs.data["clipEmbeddings"]
    assert fs.data["userPrivateMedia"]["u1"]["clip"]["embeddingStatus"] == "deleted"
    assert fs.data["userPrivateMedia"]["u1"]["sourcePhotos"][0]["gcsUri"] == ""
    assert fs.data["userPrivateMedia"]["u1"]["sourcePhotos"][0]["storagePath"] == ""
    assert fs.data["users"]["u1"]["avatar"]["status"] == "none"
    assert fs.data["users"]["u1"]["profileImageUrl"] == ""
    assert fs.data["avatarJobs"]["avatar_job_1"]["status"] == "cancelled"
    assert fs.data["avatarJobs"]["avatar_job_1"]["sourcePhotoRefs"] == []
    assert fs.data["avatarJobs"]["avatar_job_1"]["sourcePhotoIds"] == []
    assert fs.data["avatarCandidates"]["cand_1"]["imageRef"] == ""
    assert fs.data["avatarCandidates"]["cand_1"]["qa"] == {}
    assert summary.source_photos_deleted == 1
    assert summary.clip_embeddings_deleted == 1


def test_user_media_cleanup_writes_redacted_audit_log():
    fs = FakeFirestore(
        {
            "users": {"u1": {"avatar": {}}},
            "userPrivateMedia": {
                "u1": {
                    "sourcePhotos": [
                        {
                            "photoId": "src_001",
                            "status": "active",
                            "gcsUri": "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg",
                        }
                    ],
                    "clip": {"embeddingStatus": "ready"},
                }
            },
            "clipEmbeddings": {"u1": {"vector": [0.1], "sourcePhotoIds": ["src_001"]}},
            "avatarCandidates": {},
            "avatarJobs": {},
        }
    )
    source_blob = FakeBlob()
    st = FakeStorage(
        {
            "seolleyeon-final-private-source-photos": FakeBucket(
                {"users/u1/source/src_001.jpg": source_blob}
            )
        }
    )

    cleanup_user_media(
        uid="u1",
        reason="account_deletion",
        firestore_client=fs,
        storage_client=st,
        dry_run=False,
    )

    audit_docs = fs.data.get("avatarMediaCleanupAudit", {})
    assert len(audit_docs) == 1
    audit_text = json.dumps(list(audit_docs.values()), default=str, sort_keys=True)
    assert "account_deletion" in audit_text
    assert "u1" not in audit_text
    assert "seolleyeon-final-private-source-photos" not in audit_text
    assert "users/u1/source/src_001.jpg" not in audit_text
    assert "0.1" not in audit_text


def test_user_media_cleanup_rejects_normal_generation_reason():
    with pytest.raises(AvatarCleanupError, match="Unsupported cleanup reason"):
        cleanup_user_media(
            uid="u1",
            reason="avatar_generation",
            firestore_client=FakeFirestore({}),
            storage_client=FakeStorage({}),
            dry_run=True,
        )


def test_cleanup_dry_run_reports_planned_not_actual_deletes():
    now = datetime.now(tz=timezone.utc)
    fs = FakeFirestore(
        {
            "avatarCandidates": {
                "cand_1": {
                    "candidateId": "cand_1",
                    "status": "rejected",
                    "imageRef": "gs://seolleyeon-final-avatar-temp/users/u/jobs/j/candidates/cand_1.png",
                }
            }
        }
    )
    temp_blob = FakeBlob()
    st = FakeStorage(
        {
            "seolleyeon-final-avatar-temp": FakeBucket(
                {"users/u/jobs/j/candidates/cand_1.png": temp_blob}
            )
        }
    )

    summary = cleanup_expired_avatar_candidates(
        firestore_client=fs,
        storage_client=st,
        now=now,
        dry_run=True,
    )

    assert summary.temp_candidates_planned_for_delete == 1
    assert summary.temp_candidates_deleted == 0
    assert temp_blob.deleted is False


def test_avatar_ttl_cleanup_script_defaults_to_dry_run_and_writes_report(tmp_path, monkeypatch):
    script_path = REPO_ROOT / "scripts" / "avatar_ttl_cleanup.py"
    spec = importlib.util.spec_from_file_location("avatar_ttl_cleanup", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    now = datetime.now(tz=timezone.utc)
    fs = FakeFirestore(
        {
            "avatarCandidates": {
                "cand_temp": {
                    "candidateId": "cand_temp",
                    "status": "preview_ready",
                    "expiresAt": (now - timedelta(hours=1)).isoformat(),
                    "imageRef": "gs://seolleyeon-final-avatar-temp/users/u1/jobs/j/candidates/cand_temp.png",
                },
                "cand_source": {
                    "candidateId": "cand_source",
                    "status": "rejected",
                    "imageRef": "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg",
                },
            }
        }
    )
    temp_blob = FakeBlob()
    source_blob = FakeBlob()
    st = FakeStorage(
        {
            "seolleyeon-final-avatar-temp": FakeBucket(
                {"users/u1/jobs/j/candidates/cand_temp.png": temp_blob}
            ),
            "seolleyeon-final-private-source-photos": FakeBucket(
                {"users/u1/source/src_001.jpg": source_blob}
            ),
        }
    )
    report_path = tmp_path / "ttl_report.json"
    monkeypatch.setattr(module, "default_firestore_client", lambda project=None, database=None: fs)
    monkeypatch.setattr(module, "default_storage_client", lambda project=None: st)

    result = module.main(
        [
            "--firestore_project",
            "test-project",
            "--firestore_database",
            "(default)",
            "--max_delete_per_run",
            "10",
            "--output_report_json",
            str(report_path),
        ]
    )

    assert result == 0
    assert temp_blob.deleted is False
    assert source_blob.deleted is False
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["dryRun"] is True
    assert report["tempCandidatesPlannedForDelete"] == 1
