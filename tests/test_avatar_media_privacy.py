import io
import re
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _png_bytes(size=(4, 4), color=(240, 120, 160)):
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


class _FakeBlob:
    def __init__(self, data: bytes, *, exists=True, size=None):
        self._data = data
        self._exists = exists
        self.size = len(data) if size is None else size

    def exists(self):
        return self._exists

    def reload(self):
        return None

    def download_as_bytes(self):
        return self._data


class _FakeBucket:
    def __init__(self, blobs):
        self._blobs = blobs

    def blob(self, path):
        return self._blobs[path]


class _FakeStorageClient:
    def __init__(self, buckets):
        self._buckets = buckets

    def bucket(self, name):
        return self._buckets[name]


def test_gcs_uri_parsing_accepts_gs_and_gcs_schemes():
    from seolleyeon_clip_embedder import _parse_gcs_uri

    assert _parse_gcs_uri("gs://bucket/path/to/image.jpg") == (
        "bucket",
        "path/to/image.jpg",
    )
    assert _parse_gcs_uri("gcs://bucket/path/to/image.jpg") == (
        "bucket",
        "path/to/image.jpg",
    )


def test_gcs_uri_parsing_rejects_missing_object_path():
    from seolleyeon_clip_embedder import _parse_gcs_uri

    with pytest.raises(ValueError):
        _parse_gcs_uri("gs://bucket")


def test_gcs_loader_enforces_allowed_bucket_and_size():
    from seolleyeon_clip_embedder import _load_image_from_gcs

    data = _png_bytes()
    client = _FakeStorageClient(
        {
            "seolleyeon-private-source-photos": _FakeBucket(
                {"users/u1/source/src_001.png": _FakeBlob(data)}
            )
        }
    )

    image = _load_image_from_gcs(
        "gs://seolleyeon-private-source-photos/users/u1/source/src_001.png",
        max_bytes=len(data) + 1,
        allowed_buckets={"seolleyeon-private-source-photos"},
        storage_client=client,
    )

    assert image.mode == "RGB"
    assert image.size == (4, 4)

    with pytest.raises(ValueError, match="Bucket not allowed"):
        _load_image_from_gcs(
            "gs://public-bucket/users/u1/source/src_001.png",
            max_bytes=len(data) + 1,
            allowed_buckets={"seolleyeon-private-source-photos"},
            storage_client=client,
        )

    too_large_client = _FakeStorageClient(
        {
            "seolleyeon-private-source-photos": _FakeBucket(
                {"users/u1/source/src_001.png": _FakeBlob(data, size=len(data) + 10)}
            )
        }
    )
    with pytest.raises(ValueError, match="Image too large"):
        _load_image_from_gcs(
            "gs://seolleyeon-private-source-photos/users/u1/source/src_001.png",
            max_bytes=len(data),
            allowed_buckets={"seolleyeon-private-source-photos"},
            storage_client=too_large_client,
        )


def test_private_media_loader_filters_consent_status_and_scheme():
    from seolleyeon_rec_common_v3 import load_users_with_private_source_photos_from_docs

    private_docs = {
        "active": {
            "photoConsent": {
                "clipRecommendation": True,
                "profileDisplayOriginalPhoto": False,
            },
            "sourcePhotos": [
                {
                    "photoId": "src_001",
                    "gcsUri": "gs://seolleyeon-private-source-photos/users/active/source/src_001.jpg",
                    "status": "active",
                    "purpose": {"clipRecommendation": True},
                },
                {
                    "photoId": "src_old",
                    "gcsUri": "gs://seolleyeon-private-source-photos/users/active/source/src_old.jpg",
                    "status": "deleted",
                    "purpose": {"clipRecommendation": True},
                },
                {
                    "photoId": "src_http",
                    "gcsUri": "https://example.com/original.jpg",
                    "status": "active",
                    "purpose": {"clipRecommendation": True},
                },
            ],
        },
        "no_consent": {
            "photoConsent": {
                "clipRecommendation": False,
                "profileDisplayOriginalPhoto": False,
            },
            "sourcePhotos": [
                {
                    "photoId": "src_001",
                    "gcsUri": "gs://seolleyeon-private-source-photos/users/no_consent/source/src_001.jpg",
                    "status": "active",
                    "purpose": {"clipRecommendation": True},
                }
            ],
        },
    }

    assert load_users_with_private_source_photos_from_docs(private_docs) == {
        "active": [
            "gs://seolleyeon-private-source-photos/users/active/source/src_001.jpg"
        ]
    }


def test_display_ready_loader_requires_approved_avatar():
    from seolleyeon_rec_common_v3 import load_avatar_display_status_from_docs

    users = {
        "ready": {
            "profileImageMode": "avatar",
            "isActive": True,
            "isStudentVerified": True,
            "isProfileComplete": True,
            "avatar": {
                "status": "approved",
                "approvedAvatarUrl": "https://cdn.example/avatar.png",
            },
        },
        "missing_avatar": {
            "profileImageMode": "avatar",
            "isActive": True,
            "isStudentVerified": True,
            "isProfileComplete": True,
            "avatar": {"status": "none"},
        },
    }

    status = load_avatar_display_status_from_docs(users)

    assert status["ready"]["displayReady"] is True
    assert status["ready"]["approvedAvatarUrl"] == "https://cdn.example/avatar.png"
    assert status["missing_avatar"] == {
        "displayReady": False,
        "approvedAvatarUrl": "",
        "avatarStatus": "none",
        "reason": "missing_approved_avatar",
    }


def test_backend_display_resolver_ignores_profile_image_url_and_photo_urls():
    from seolleyeon_rec_common_v3 import extract_display_avatar_url

    assert (
        extract_display_avatar_url(
            {
                "profileImageMode": "avatar",
                "profileImageUrl": "https://example.com/legacy-source.jpg",
                "onboarding": {
                    "photoUrls": ["https://example.com/source-photo.jpg"],
                },
            }
        )
        == ""
    )


@pytest.mark.parametrize(
    "private_ref",
    [
        "gs://qa-tenant-17-private-source-photos/users/u/source/p.jpg",
        "https://storage.googleapis.com/tenant.alpha-avatar-temp/users/u/candidate/p.png",
        "https://tenant99-chat-profile-photos.storage.googleapis.com/users/u/chat-profile/p.jpg",
    ],
)
def test_backend_display_resolver_rejects_private_media_for_any_project_prefix(private_ref):
    from seolleyeon_rec_common_v3 import extract_display_avatar_url

    assert (
        extract_display_avatar_url(
            {
                "avatar": {
                    "status": "approved",
                    "approvedAvatarUrl": private_ref,
                },
                "onboarding": {"avatarUrls": [private_ref]},
            }
        )
        == ""
    )


def test_qa_flags_legacy_profile_image_url_as_public_leak():
    from scripts.qa_media_privacy import _public_doc_has_source_photo_leak

    assert _public_doc_has_source_photo_leak(
        {
            "profileImageMode": "avatar",
            "profileImageUrl": "https://example.com/legacy-source.jpg",
        }
    )


def test_public_recommendation_items_are_filtered_and_sanitized():
    from seolleyeon_rec_common_v3 import (
        filter_recommendation_items_for_display_ready,
        validate_public_recommendation_item,
    )

    display_status = {
        "safe": {
            "displayReady": True,
            "approvedAvatarUrl": "https://cdn.example/avatar.png",
            "avatarStatus": "approved",
            "reason": None,
        },
        "unsafe": {
            "displayReady": False,
            "approvedAvatarUrl": "",
            "avatarStatus": "none",
            "reason": "missing_approved_avatar",
        },
    }
    items = [
        {"uid": "safe", "rank": 1, "score": 0.9, "sourcePhotoGcsUri": "gs://secret"},
        {"uid": "unsafe", "rank": 2, "score": 0.8},
    ]

    filtered, skipped = filter_recommendation_items_for_display_ready(
        items,
        display_status,
        require_approved_avatar=True,
    )

    assert filtered == [
        {
            "uid": "safe",
            "rank": 1,
            "score": 0.9,
            "approvedAvatarUrl": "https://cdn.example/avatar.png",
        }
    ]
    assert skipped == {"missing_approved_avatar": 1}
    validate_public_recommendation_item(filtered[0])
    with pytest.raises(ValueError, match="Forbidden public recommendation field"):
        validate_public_recommendation_item(items[0])


def test_qa_fixture_detects_public_photo_url_leakage():
    from scripts.qa_media_privacy import run_fixture_checks

    summary = run_fixture_checks(
        {
            "users": {
                "leaky": {
                    "onboarding": {
                        "photoUrls": [
                            "gs://seolleyeon-private-source-photos/users/leaky/source/src_001.jpg"
                        ]
                    }
                }
            },
            "userPrivateMedia": {},
            "clipEmbeddings": {},
            "modelRecs": {},
        },
        repo_root=REPO_ROOT,
        check_client_code=False,
    )

    assert summary.public_leakage_count == 1
    assert summary.passed is False


def test_client_scan_allows_legacy_photo_url_models_without_display(tmp_path):
    from scripts.qa_media_privacy import _scan_client_code

    model_path = tmp_path / "lib" / "data" / "models" / "user" / "user_profile_model.dart"
    model_path.parent.mkdir(parents=True)
    model_path.write_text(
        """
class UserProfileModel {
  final List<String> photoUrls;
  const UserProfileModel({this.photoUrls = const []});
}
""",
        encoding="utf-8",
    )

    assert _scan_client_code(tmp_path) == 0


def test_client_scan_rejects_direct_photo_urls_image_display(tmp_path):
    from scripts.qa_media_privacy import _scan_client_code

    screen_path = tmp_path / "lib" / "features" / "profile" / "leaky_screen.dart"
    screen_path.parent.mkdir(parents=True)
    screen_path.write_text(
        """
import 'package:flutter/widgets.dart';

Widget buildLeakyPhoto(List<String> photoUrls) {
  return Image.network(photoUrls.first);
}
""",
        encoding="utf-8",
    )

    assert _scan_client_code(tmp_path) == 1


def test_qa_fixture_detects_chat_room_real_photo_leakage():
    from scripts.qa_media_privacy import run_fixture_checks

    summary = run_fixture_checks(
        {
            "users": {},
            "userPrivateMedia": {},
            "clipEmbeddings": {},
            "modelRecs": {},
            "chatRooms": {
                "room1": {
                    "participantIds": ["u1", "u2"],
                    "realProfilePhotoUrl": (
                        "https://storage.googleapis.com/seolleyeon-chat-profile-photos/"
                        "users/u2/chat-profile/src.jpg?X-Goog-Signature=secret"
                    ),
                }
            },
        },
        repo_root=REPO_ROOT,
        check_client_code=False,
    )

    assert summary.chat_room_leakage_count == 1
    assert summary.passed is False


@pytest.mark.parametrize(
    "bad_ref",
    [
        "https://storage.googleapis.com/seolleyeon-avatar-temp/users/u/jobs/j/c.png",
        "https://storage.googleapis.com/seolleyeon-private-source-photos/users/u/source/src.jpg",
        "gs://seolleyeon-avatar-temp/users/u/jobs/j/c.png",
        "gcs://seolleyeon-private-source-photos/users/u/source/src.jpg",
        "https://cdn.example/avatar.png?X-Goog-Algorithm=GOOG4-RSA-SHA256",
        "https://cdn.example/avatar.png?GoogleAccessId=svc@example.iam.gserviceaccount.com",
        "https://cdn.example/avatar.png?Signature=abc&Expires=9999999999",
        "https://cdn.example/avatar.png?AWSAccessKeyId=key&Signature=abc",
        "https://cdn.example/avatar.png?X-Amz-Signature=abc",
        (
            "https://firebasestorage.googleapis.com/v0/b/seolleyeon-private-source-photos/o/"
            "users%2Fu%2Fsource%2Fsrc.jpg?alt=media"
        ),
    ],
)
def test_public_recommendation_validator_rejects_signed_private_and_temp_refs(bad_ref):
    from seolleyeon_rec_common_v3 import validate_public_recommendation_item

    with pytest.raises(ValueError, match="Forbidden public recommendation"):
        validate_public_recommendation_item({"uid": "u1", "approvedAvatarUrl": bad_ref})


@pytest.mark.parametrize(
    "bad_item",
    [
        {"uid": "u1", "vectors": [0.1, 0.2]},
        {"uid": "u1", "faceEmbeddingV2": [0.1, 0.2]},
        {"uid": "u1", "imageRef": "gs://seolleyeon-avatar-temp/users/u/jobs/j/c.png"},
        {"uid": "u1", "nested": {"gcsUri": "gs://seolleyeon-private-source-photos/users/u/source/src.jpg"}},
    ],
)
def test_public_recommendation_validator_rejects_sensitive_fields(bad_item):
    from seolleyeon_rec_common_v3 import validate_public_recommendation_item

    with pytest.raises(ValueError, match="Forbidden public recommendation"):
        validate_public_recommendation_item(bad_item)


def test_public_recommendation_sanitizer_recursively_strips_sensitive_fields_and_values():
    from seolleyeon_rec_common_v3 import sanitize_public_recommendation_item

    sanitized = sanitize_public_recommendation_item(
        {
            "uid": "u1",
            "rank": 1,
            "nested": {
                "safe": "ok",
                "imageRef": "https://storage.googleapis.com/seolleyeon-avatar-temp/users/u/c.png",
                "safeImageRef": "https://cdn.example/avatar.png",
            },
            "items": [
                {"uid": "u2", "score": 0.4, "sourcePhotoUrl": "https://example.com/source.jpg"},
                "https://cdn.example/safe.png",
                "https://cdn.example/signed.png?X-Amz-Signature=abc",
            ],
            "vectors": [0.1, 0.2],
        },
        approved_avatar_url="https://cdn.example/approved.png",
    )

    assert sanitized == {
        "uid": "u1",
        "rank": 1,
        "nested": {
            "safe": "ok",
            "safeImageRef": "https://cdn.example/avatar.png",
        },
        "items": [
            {"uid": "u2", "score": 0.4},
            "https://cdn.example/safe.png",
        ],
        "approvedAvatarUrl": "https://cdn.example/approved.png",
    }


@pytest.mark.parametrize(
    "bad_url",
    [
        "https://storage.googleapis.com/seolleyeon-avatar-temp/users/u/jobs/j/c.png",
        "https://storage.googleapis.com/seolleyeon-private-source-photos/users/u/source/src.jpg",
        "https://storage.googleapis.com/public-bucket/avatar.png?X-Goog-Algorithm=GOOG4-RSA-SHA256",
        "https://storage.googleapis.com/public-bucket/avatar.png?GoogleAccessId=svc@example.iam.gserviceaccount.com",
        "https://storage.googleapis.com/public-bucket/avatar.png?Signature=abc&Expires=9999999999",
        "https://storage.googleapis.com/public-bucket/avatar.png?AWSAccessKeyId=key&Signature=abc",
        "https://storage.googleapis.com/public-bucket/avatar.png?X-Amz-Signature=abc",
        (
            "https://firebasestorage.googleapis.com/v0/b/seolleyeon-avatar-temp/o/"
            "users%2Fu%2Fjobs%2Fj%2Fc.png?alt=media"
        ),
    ],
)
def test_clip_https_loader_rejects_signed_private_and_temp_urls_before_download(monkeypatch, bad_url):
    import seolleyeon_clip_embedder as clip

    def fail_get(*args, **kwargs):
        raise AssertionError("signed or sensitive media URL should be rejected before download")

    monkeypatch.setattr(clip.requests, "get", fail_get)

    with pytest.raises(ValueError, match="Sensitive or signed image URL"):
        clip._load_image_from_url(
            bad_url,
            timeout=0.1,
            max_bytes=16,
            allowed_hosts={"storage.googleapis.com", "firebasestorage.googleapis.com"},
        )


def test_qa_fixture_detects_onboarding_avatar_url_temp_leakage():
    from scripts.qa_media_privacy import run_fixture_checks

    summary = run_fixture_checks(
        {
            "users": {
                "leaky": {
                    "onboarding": {
                        "avatarUrls": [
                            "https://storage.googleapis.com/seolleyeon-avatar-temp/users/leaky/jobs/j/c.png"
                        ]
                    }
                }
            },
            "userPrivateMedia": {},
            "clipEmbeddings": {},
            "modelRecs": {},
        },
        repo_root=REPO_ROOT,
        check_client_code=False,
    )

    assert summary.public_leakage_count == 1
    assert summary.passed is False


def test_qa_fixture_detects_signed_markers_and_storage_source_paths():
    from scripts.qa_media_privacy import run_fixture_checks

    summary = run_fixture_checks(
        {
            "users": {
                "source_path": {
                    "onboarding": {
                        "avatarUrls": [
                            "https://storage.googleapis.com/public-bucket/users/source_path/source/src.jpg"
                        ]
                    }
                },
                "signed": {
                    "avatar": {
                        "status": "approved",
                        "approvedAvatarUrl": (
                            "https://cdn.example/avatar.png?"
                            "GoogleAccessId=svc@example.iam.gserviceaccount.com&Signature=abc&Expires=9999999999"
                        ),
                    }
                },
            },
            "userPrivateMedia": {},
            "clipEmbeddings": {},
            "modelRecs": {
                "modelRecs/u1/daily/20260514/sources/clip": {
                    "items": [
                        {
                            "uid": "candidate",
                            "rank": 1,
                            "candidatePreviewUrl": (
                                "https://storage.googleapis.com/public-bucket/avatar.png?"
                                "AWSAccessKeyId=key&X-Amz-Signature=abc"
                            ),
                        }
                    ]
                }
            },
        },
        repo_root=REPO_ROOT,
        check_client_code=False,
    )

    assert summary.public_leakage_count == 2
    assert summary.model_recs_unsafe_exposure_count >= 1
    assert summary.passed is False


def test_firestore_rules_protect_client_written_avatar_display_fields():
    rules = (REPO_ROOT / "firestore.rules").read_text(encoding="utf-8")

    assert re.search(r"function\s+onboardingAvatarPhotoFieldsUnchanged", rules)
    assert re.search(r"function\s+avatarApprovalFieldsUnchanged", rules)
    assert re.search(r"function\s+isStorageSourcePath", rules)
    assert "lower()" in rules
    assert "x-goog-" in rules
    assert "x-amz-" in rules
    assert "googleaccessid" in rules
    assert "signature=" in rules
    assert "expires=" in rules
    assert "awsaccesskeyid" in rules
    assert "request.resource.data.onboarding.diff(resource.data.onboarding)" in rules
    assert "request.resource.data.avatar.diff(resource.data.avatar)" in rules
    assert "'avatarUrls'" in rules
    assert "'photoUrls'" in rules
    assert "'approvedAvatarUrl'" in rules
    assert "'approvedAvatarStoragePath'" in rules
    assert "chatRoomDoesNotPersistPrivateMedia" in rules
    assert "'realProfilePhotoUrl'" in rules
    assert "seolleyeon-chat-profile-photos" in rules


def test_qa_fixture_allows_only_approved_avatar_photo_url_compatibility():
    from scripts.qa_media_privacy import run_fixture_checks

    approved = "https://cdn.example/avatar.png"
    summary = run_fixture_checks(
        {
            "users": {
                "safe": {
                    "profileImageMode": "avatar",
                    "avatar": {
                        "status": "approved",
                        "approvedAvatarUrl": approved,
                        "approvedAvatarStoragePath": (
                            "gs://seolleyeon-final-approved-avatars/users/safe/avatar/avatar_001.png"
                        ),
                    },
                    "onboarding": {
                        "photoUrls": [approved],
                        "avatarUrls": [approved],
                    },
                }
            },
            "userPrivateMedia": {},
            "clipEmbeddings": {},
            "modelRecs": {},
        },
        repo_root=REPO_ROOT,
        check_client_code=False,
    )

    assert summary.public_leakage_count == 0


def test_qa_fixture_detects_private_media_wrong_bucket_and_signed_preview():
    from scripts.qa_media_privacy import run_fixture_checks

    summary = run_fixture_checks(
        {
            "users": {},
            "userPrivateMedia": {
                "u1": {
                    "photoConsent": {
                        "clipRecommendation": True,
                        "profileDisplayOriginalPhoto": False,
                    },
                    "sourcePhotos": [
                        {
                            "photoId": "src_001",
                            "gcsUri": "gs://wrong-bucket/users/u1/source/src_001.jpg",
                            "status": "active",
                            "purpose": {"clipRecommendation": True},
                            "signedUrl": "https://storage.googleapis.com/x?X-Goog-Signature=secret",
                        }
                    ],
                }
            },
            "clipEmbeddings": {},
            "modelRecs": {},
        },
        repo_root=REPO_ROOT,
        check_client_code=False,
    )

    assert summary.private_media_invalid_count == 1
    assert summary.passed is False


def test_private_media_allows_chat_profile_photo_copy_with_consent():
    from scripts.qa_media_privacy import run_fixture_checks

    summary = run_fixture_checks(
        {
            "users": {},
            "userPrivateMedia": {
                "u1": {
                    "photoConsent": {
                        "avatarGeneration": True,
                        "clipRecommendation": True,
                        "profileDisplayOriginalPhoto": False,
                        "chatPartnerRealPhotoDisclosure": True,
                    },
                    "sourcePhotos": [
                        {
                            "photoId": "src_001",
                            "gcsUri": "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg",
                            "status": "active",
                            "purpose": {"clipRecommendation": True, "avatarGeneration": True},
                        }
                    ],
                    "chatRealPhoto": {
                        "enabled": True,
                        "storageBucket": "seolleyeon-chat-profile-photos",
                        "storagePath": "users/u1/chat-profile/src_001.jpg",
                        "gcsUri": "gs://seolleyeon-chat-profile-photos/users/u1/chat-profile/src_001.jpg",
                    },
                }
            },
            "clipEmbeddings": {},
            "modelRecs": {},
            "chatRooms": {},
        },
        repo_root=REPO_ROOT,
        check_client_code=False,
    )

    assert summary.private_media_invalid_count == 0


def test_qa_fixture_detects_clip_metadata_and_public_rec_vectors():
    from scripts.qa_media_privacy import run_fixture_checks

    summary = run_fixture_checks(
        {
            "users": {
                "candidate": {
                    "profileImageMode": "avatar",
                    "isStudentVerified": True,
                    "isProfileComplete": True,
                    "avatar": {
                        "status": "approved",
                        "approvedAvatarUrl": "https://cdn.example/avatar.png",
                    },
                }
            },
            "userPrivateMedia": {},
            "clipEmbeddings": {
                "candidate": {
                    "modelId": "clip-vit-b32",
                    "embeddingVersion": "v1",
                    "dims": 2,
                    "normalized": True,
                    "sourcePhotoIds": ["src_001"],
                    "vector": [0.1],
                }
            },
            "modelRecs": {
                "modelRecs/u1/daily/20260514/sources/clip": {
                    "items": [
                        {
                            "uid": "candidate",
                            "rank": 1,
                            "vector": [0.1, 0.2],
                            "candidatePreviewUrl": (
                                "https://storage.googleapis.com/seolleyeon-avatar-temp/x"
                                "?X-Goog-Signature=secret"
                            ),
                        }
                    ]
                }
            },
        },
        repo_root=REPO_ROOT,
        check_client_code=False,
    )

    assert summary.clip_embeddings_invalid_count == 1
    assert summary.model_recs_unsafe_exposure_count >= 1
    assert summary.passed is False


def test_migration_backfills_private_gcs_refs_only_with_consent():
    from scripts.migrate_avatar_media_fields import (
        build_private_media_migration_update,
        classify_onboarding_photo_urls,
    )

    public_original = "https://example.com/original.jpg"
    user_doc = {
        "onboarding": {
            "photoUrls": [
                "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg",
                public_original,
            ]
        }
    }
    private_doc = {
        "photoConsent": {
            "clipRecommendation": True,
            "profileDisplayOriginalPhoto": True,
        },
        "sourcePhotos": [],
    }

    update = build_private_media_migration_update("u1", user_doc, private_doc, server_timestamp="now")

    assert update is not None
    assert update["photoConsent"]["profileDisplayOriginalPhoto"] is False
    assert len(update["sourcePhotos"]) == 1
    assert update["sourcePhotos"][0]["gcsUri"] == (
        "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg"
    )
    classified = classify_onboarding_photo_urls(user_doc["onboarding"]["photoUrls"])
    assert classified.public_https_originals_needing_safe_migration == [public_original]

    no_consent_update = build_private_media_migration_update(
        "u1",
        user_doc,
        {"photoConsent": {"clipRecommendation": False}, "sourcePhotos": []},
    )
    assert no_consent_update is None


def test_migration_does_not_auto_backfill_public_https_originals():
    from scripts.migrate_avatar_media_fields import build_private_media_migration_update

    update = build_private_media_migration_update(
        "u1",
        {"onboarding": {"photoUrls": ["https://public.example/original-user-photo.jpg"]}},
        {
            "photoConsent": {
                "clipRecommendation": True,
                "profileDisplayOriginalPhoto": True,
            },
            "sourcePhotos": [],
        },
    )

    assert update is None


def test_chat_real_photo_migration_requires_explicit_consent():
    from scripts.migrate_chat_real_photo_visibility import (
        build_chat_real_photo_update,
        decide_chat_real_photo_migration,
    )

    private_doc = {
        "photoConsent": {"chatPartnerRealPhotoDisclosure": True},
        "sourcePhotos": [
            {
                "photoId": "src_001",
                "status": "active",
                "gcsUri": "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg",
            }
        ],
    }
    decision = decide_chat_real_photo_migration("u1", private_doc)
    assert decision.status == "ready_to_copy"
    update = build_chat_real_photo_update(decision, server_timestamp="now")
    assert update is not None
    assert update["chatRealPhoto"]["storageBucket"] == "seolleyeon-chat-profile-photos"
    assert update["chatRealPhoto"]["gcsUri"].startswith("gs://seolleyeon-chat-profile-photos/")

    no_consent = decide_chat_real_photo_migration(
        "u1",
        {
            "photoConsent": {"chatPartnerRealPhotoDisclosure": False},
            "sourcePhotos": private_doc["sourcePhotos"],
        },
    )
    assert no_consent.status == "missing_chat_real_photo_consent"


def test_migration_user_update_never_writes_public_https_source_photo_url():
    from scripts.migrate_avatar_media_fields import build_user_migration_update

    public_original = "https://public.example/original-user-photo.jpg"
    update = build_user_migration_update(
        {
            "profileImageUrl": public_original,
            "onboarding": {
                "photoUrls": [public_original],
                "nickname": "safe",
            },
            "avatar": {"status": "none"},
        },
        server_timestamp="now",
    )

    assert public_original not in repr(update)
    assert update["profileImageUrl"] == ""
    assert "photoUrls" not in update["onboarding"]
    assert update["onboarding"]["nickname"] == "safe"


def test_migration_dry_run_reports_public_https_originals_without_writes():
    from scripts.migrate_avatar_media_fields import run_migration

    class FakeSnapshot:
        def __init__(self, doc_id, data, *, exists=True):
            self.id = doc_id
            self._data = data
            self.exists = exists
            self.reference = f"users/{doc_id}"

        def to_dict(self):
            return self._data

    class FakeCollection:
        def __init__(self, snapshots):
            self._snapshots = snapshots

        def stream(self):
            return list(self._snapshots.values())

        def document(self, doc_id):
            snapshots = self._snapshots

            class FakeDocument:
                def get(self):
                    return snapshots.get(doc_id, FakeSnapshot(doc_id, {}, exists=False))

            return FakeDocument()

    class FakeDb:
        def __init__(self):
            self.writes = []
            self.users = {
                "u1": FakeSnapshot(
                    "u1",
                    {
                        "onboarding": {
                            "photoUrls": [
                                "https://public.example/original-user-photo.jpg",
                                "gs://seolleyeon-private-source-photos/users/u1/source/src_001.jpg",
                            ]
                        }
                    },
                )
            }
            self.private = {
                "u1": FakeSnapshot(
                    "u1",
                    {
                        "photoConsent": {
                            "clipRecommendation": True,
                            "profileDisplayOriginalPhoto": True,
                        },
                        "sourcePhotos": [],
                    },
                )
            }

        def collection(self, name):
            if name == "users":
                return FakeCollection(self.users)
            if name == "userPrivateMedia":
                return FakeCollection(self.private)
            raise AssertionError(name)

        def bulk_writer(self):
            raise AssertionError("dry-run must not create a bulk writer")

    db = FakeDb()

    summary = run_migration(db, apply=False, server_timestamp="now")

    assert db.writes == []
    assert summary.users_scanned == 1
    assert summary.public_https_originals_needing_safe_migration == 1
    assert summary.private_source_refs_migrated == 1


def test_storage_rules_settle_public_readable_approved_avatar_model():
    rules = (REPO_ROOT / "storage.rules").read_text(encoding="utf-8")

    assert 'bucket == "seolleyeon-final-approved-avatars"' in rules
    assert "match /users/{userId}/avatar/{avatarId}" in rules
    assert "allow read: if isApprovedAvatarBucket();" in rules
    assert "allow write: if false;" in rules
    assert "match /users/{userId}/jobs/{jobId}/candidates/{candidateId}" in rules
