#!/usr/bin/env python3
"""CI-friendly checks for Seolleyeon avatar/source-photo separation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import parse_qsl, unquote, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

try:
    from privacy_client_scanner import (
        PRIVATE_MEDIA_MARKERS,
        count_leaky_records,
        scan_client_files,
    )
except ModuleNotFoundError:  # pragma: no cover - package import path
    from scripts.privacy_client_scanner import (
        PRIVATE_MEDIA_MARKERS,
        count_leaky_records,
        scan_client_files,
    )

from seolleyeon_rec_common_v3 import (  # noqa: E402
    PRIVATE_SOURCE_PHOTO_BUCKET,
    _is_private_or_signed_image_ref,
    load_avatar_display_status_from_docs,
    load_users_with_private_source_photos_from_docs,
    validate_public_recommendation_item,
)

try:
    from google.cloud import firestore
except Exception:  # pragma: no cover - optional for fixture-only CI
    firestore = None

AVATAR_TEMP_BUCKET = "seolleyeon-avatar-temp"
APPROVED_AVATAR_BUCKET = "seolleyeon-approved-avatars"
CHAT_PROFILE_PHOTO_BUCKET = "seolleyeon-chat-profile-photos"
APPROVED_AVATAR_GCS_PREFIX = f"gs://{APPROVED_AVATAR_BUCKET}/"
PRIVATE_OR_TEMP_BUCKET_MARKERS = PRIVATE_MEDIA_MARKERS
SIGNED_URL_MARKERS = (
    "X-Goog-",
    "GoogleAccessId",
    "Signature=",
    "Expires=",
    "AWSAccessKeyId",
    "X-Amz-",
)
SIGNED_QUERY_KEYS = {"googleaccessid", "signature", "expires", "awsaccesskeyid"}
SIGNED_QUERY_PREFIXES = ("x-goog-", "x-amz-")
SIGNED_RAW_RE = re.compile(
    r"(?:^|[?&])(?:x-goog-[^=&]*|x-amz-[^=&]*|googleaccessid|signature|expires|awsaccesskeyid)=",
    re.IGNORECASE,
)
PUBLIC_USER_FORBIDDEN_KEYS = {
    "sourcephotos",
    "sourcephotourls",
    "sourcephotorefs",
    "sourcephotogcsuri",
    "sourcephotogcsuris",
    "chatrealphoto",
    "chatrealphotourl",
    "realphotourl",
    "realprofilephotourl",
    "gcsuri",
    "gcsuris",
    "imageref",
    "signedurl",
    "signedurls",
    "candidatepreviewurl",
    "candidatepreviewurls",
    "previewurl",
    "previewurls",
    "clipembedding",
    "clipembeddings",
    "faceembedding",
    "faceembeddings",
    "qaembeddings",
    "vector",
    "vectors",
}
PUBLIC_REC_FORBIDDEN_KEYS = PUBLIC_USER_FORBIDDEN_KEYS | {
    "embedding",
    "embeddings",
    "rawvector",
    "rawvectors",
}
CLIENT_DART_SCAN_ROOTS = (
    Path("lib/features"),
    Path("lib/services"),
    Path("lib/shared"),
    Path("lib/data"),
)
CLIENT_SCOPE_ALLOWLIST_NOTES = {
    "lib/ai_recommend_model/**": "backend/ML pipeline, not Flutter UI runtime",
    "functions/src/chatRealPhoto.ts": "backend runtime-only getSignedUrl exception",
    "functions/src/avatarApproval.ts": "backend runtime-only getSignedUrl exception",
    "test/**": "test fixtures only",
    "tests/**": "test fixtures only",
    "docs/**": "documentation only",
}
CLIENT_SENSITIVE_POLICY_FILES = {
    "lib/shared/utils/profile_display_image_resolver.dart",
}
CLIENT_LEGACY_PHOTO_URL_MODEL_FILES = {
    "lib/data/models/user/user_profile_model.dart",
    "lib/data/models/matching/match_model.dart",
}


@dataclass
class PrivacyQASummary:
    total_users_scanned: int = 0
    public_leakage_count: int = 0
    private_media_invalid_count: int = 0
    missing_approved_avatar_count: int = 0
    model_recs_unsafe_exposure_count: int = 0
    client_code_leakage_count: int = 0
    clip_embeddings_invalid_count: int = 0
    chat_room_leakage_count: int = 0
    browser_storage_leakage_count: int = 0
    public_report_leakage_count: int = 0
    public_log_leakage_count: int = 0
    scanned_file_count: int = 0

    @property
    def leakage_count(self) -> int:
        return self.client_code_leakage_count

    @property
    def passed(self) -> bool:
        return (
            self.public_leakage_count == 0
            and self.private_media_invalid_count == 0
            and self.missing_approved_avatar_count == 0
            and self.model_recs_unsafe_exposure_count == 0
            and self.client_code_leakage_count == 0
            and self.clip_embeddings_invalid_count == 0
            and self.chat_room_leakage_count == 0
            and self.browser_storage_leakage_count == 0
            and self.public_report_leakage_count == 0
            and self.public_log_leakage_count == 0
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_users_scanned": self.total_users_scanned,
            "public_leakage_count": self.public_leakage_count,
            "private_media_invalid_count": self.private_media_invalid_count,
            "missing_approved_avatar_count": self.missing_approved_avatar_count,
            "model_recs_unsafe_exposure_count": self.model_recs_unsafe_exposure_count,
            "client_code_leakage_count": self.client_code_leakage_count,
            "clip_embeddings_invalid_count": self.clip_embeddings_invalid_count,
            "chat_room_leakage_count": self.chat_room_leakage_count,
            "browser_storage_leakage_count": self.browser_storage_leakage_count,
            "public_report_leakage_count": self.public_report_leakage_count,
            "public_log_leakage_count": self.public_log_leakage_count,
            "scanned_file_count": self.scanned_file_count,
            "status": "pass" if self.passed else "fail",
        }


def _iter_values(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, Mapping):
        for child in value.values():
            yield from _iter_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_values(child)


def _contains_private_or_signed_ref(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return (
        _is_private_or_signed_image_ref(value)
        or _contains_sensitive_bucket_marker(value)
        or _contains_signed_url_marker(value)
        or _contains_storage_source_path(value)
    )


def _contains_sensitive_bucket_marker(value: str) -> bool:
    lowered = unquote(value).lower()
    return any(marker.lower() in lowered for marker in PRIVATE_OR_TEMP_BUCKET_MARKERS)


def _contains_signed_url_marker(value: str) -> bool:
    if SIGNED_RAW_RE.search(value):
        return True
    try:
        parsed = urlparse(value)
    except Exception:
        parsed = None
    if parsed is not None:
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
            lowered = key.lower()
            if lowered in SIGNED_QUERY_KEYS or lowered.startswith(SIGNED_QUERY_PREFIXES):
                return True
    lowered_value = value.lower()
    return any(marker.lower() in lowered_value for marker in SIGNED_URL_MARKERS)


def _contains_storage_source_path(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    if host not in {"storage.googleapis.com", "firebasestorage.googleapis.com"}:
        return False
    return "/source/" in unquote(parsed.path or "").lower()


def _contains_any_gcs_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("gs://", "gcs://"))


def _is_allowed_public_user_string(path: str, value: str) -> bool:
    if path == "avatar.approvedAvatarStoragePath":
        return value.startswith(APPROVED_AVATAR_GCS_PREFIX)
    if path in {"avatar.approvedAvatarUrl", "profileImageUrl"}:
        return not _contains_any_gcs_ref(value) and not _contains_private_or_signed_ref(value)
    if path.startswith("onboarding.avatarUrls.") or path.startswith("onboarding.photoUrls."):
        return not _contains_any_gcs_ref(value) and not _contains_private_or_signed_ref(value)
    return not _contains_any_gcs_ref(value) and not _contains_private_or_signed_ref(value)


def _public_key_is_forbidden(key: str, forbidden: set[str]) -> bool:
    lowered = key.lower()
    return lowered in forbidden or "sourcephoto" in lowered or lowered.startswith("faceembedding")


def _public_doc_has_source_photo_leak(doc: Mapping[str, Any]) -> bool:
    def visit(value: Any, path: str = "") -> bool:
        if isinstance(value, Mapping):
            for key, child in value.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}" if path else key_text
                if _public_key_is_forbidden(key_text, PUBLIC_USER_FORBIDDEN_KEYS):
                    return True
                if visit(child, child_path):
                    return True
        elif isinstance(value, list):
            for index, child in enumerate(value):
                if visit(child, f"{path}.{index}"):
                    return True
        elif isinstance(value, str) and not _is_allowed_public_user_string(path, value):
            return True
        return False

    if visit(doc):
        return True
    onboarding = doc.get("onboarding")
    if isinstance(onboarding, Mapping):
        photo_urls = onboarding.get("photoUrls")
        avatar = doc.get("avatar") if isinstance(doc.get("avatar"), Mapping) else {}
        approved = str(avatar.get("approvedAvatarUrl") or "")
        if isinstance(photo_urls, list) and photo_urls:
            if len(photo_urls) > 1:
                return True
            if not approved or str(photo_urls[0]) != approved:
                return True
            if _contains_private_or_signed_ref(photo_urls[0]) or _contains_any_gcs_ref(photo_urls[0]):
                return True
        avatar_urls = onboarding.get("avatarUrls")
        if isinstance(avatar_urls, list):
            if any(_contains_private_or_signed_ref(item) or _contains_any_gcs_ref(item) for item in avatar_urls):
                return True
    avatar = doc.get("avatar")
    if isinstance(avatar, Mapping):
        approved_url = avatar.get("approvedAvatarUrl")
        if isinstance(approved_url, str) and (
            _contains_private_or_signed_ref(approved_url) or _contains_any_gcs_ref(approved_url)
        ):
            return True
        approved_path = avatar.get("approvedAvatarStoragePath")
        if isinstance(approved_path, str) and not approved_path.startswith(APPROVED_AVATAR_GCS_PREFIX):
            return True
        profile_image_url = doc.get("profileImageUrl")
        if isinstance(profile_image_url, str) and profile_image_url.strip():
            if profile_image_url != approved_url:
                return True
    elif isinstance(doc.get("profileImageUrl"), str) and str(doc.get("profileImageUrl")).strip():
        return True
    return False


def _private_media_doc_is_invalid(uid: str, doc: Mapping[str, Any]) -> bool:
    consent = doc.get("photoConsent")
    if not isinstance(consent, Mapping):
        return True
    if consent.get("profileDisplayOriginalPhoto") is not False:
        return True

    source_photos = doc.get("sourcePhotos")
    if not isinstance(source_photos, list):
        return True
    allowed_statuses = {"active", "replaced", "deleted", "blocked"}
    for entry in source_photos:
        if not isinstance(entry, Mapping):
            return True
        status = entry.get("status")
        if status not in allowed_statuses:
            return True
        gcs_uri = str(entry.get("gcsUri") or "")
        expected_prefix = f"gs://{PRIVATE_SOURCE_PHOTO_BUCKET}/users/{uid}/source/"
        alternate_prefix = f"gcs://{PRIVATE_SOURCE_PHOTO_BUCKET}/users/{uid}/source/"
        if not (gcs_uri.startswith(expected_prefix) or gcs_uri.startswith(alternate_prefix)):
            return True
        if any(key in entry for key in ("downloadUrl", "downloadURL", "signedUrl", "previewUrl")):
            return True
        if status == "active":
            purpose = entry.get("purpose")
            if not isinstance(purpose, Mapping):
                return True
            if purpose.get("avatarGeneration") is not True and purpose.get("clipRecommendation") is not True:
                return True
            if purpose.get("clipRecommendation") is True and consent.get("clipRecommendation") is not True:
                return True
    chat_real_photo = doc.get("chatRealPhoto")
    if isinstance(chat_real_photo, Mapping):
        enabled = chat_real_photo.get("enabled") is True
        if enabled and consent.get("chatPartnerRealPhotoDisclosure") is not True:
            return True
        if enabled:
            if chat_real_photo.get("storageBucket") != CHAT_PROFILE_PHOTO_BUCKET:
                return True
            storage_path = str(chat_real_photo.get("storagePath") or "")
            if not storage_path.startswith(f"users/{uid}/chat-profile/"):
                return True
            gcs_uri = str(chat_real_photo.get("gcsUri") or "")
            if gcs_uri and not gcs_uri.startswith(f"gs://{CHAT_PROFILE_PHOTO_BUCKET}/users/{uid}/chat-profile/"):
                return True
            if any(key in chat_real_photo for key in ("downloadUrl", "downloadURL", "signedUrl", "previewUrl")):
                return True
    return False


def _clip_embedding_doc_is_invalid(doc: Mapping[str, Any]) -> bool:
    required = ("modelId", "embeddingVersion", "dims", "normalized", "sourcePhotoIds")
    if any(key not in doc for key in required):
        return True
    if not isinstance(doc.get("modelId"), str) or not str(doc.get("modelId")).strip():
        return True
    if not isinstance(doc.get("embeddingVersion"), str) or not str(doc.get("embeddingVersion")).strip():
        return True
    if not isinstance(doc.get("dims"), int) or int(doc.get("dims")) <= 0:
        return True
    if doc.get("normalized") is not True:
        return True
    source_photo_ids = doc.get("sourcePhotoIds")
    if (
        not isinstance(source_photo_ids, list)
        or not source_photo_ids
        or not all(isinstance(item, str) and item for item in source_photo_ids)
    ):
        return True
    vector = doc.get("vector")
    if vector is not None and (
        not isinstance(vector, list)
        or len(vector) != int(doc.get("dims"))
        or not all(isinstance(item, (int, float)) for item in vector)
    ):
        return True
    if any(_contains_private_or_signed_ref(value) for value in _iter_values(doc)):
        return True
    return False


def _public_recommendation_doc_is_unsafe(doc: Mapping[str, Any]) -> bool:
    try:
        validate_public_recommendation_item(dict(doc))
    except ValueError:
        return True

    def visit(value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if _public_key_is_forbidden(str(key), PUBLIC_REC_FORBIDDEN_KEYS):
                    return True
                if visit(child):
                    return True
        elif isinstance(value, list):
            return any(visit(child) for child in value)
        elif isinstance(value, str):
            return _contains_private_or_signed_ref(value) or _contains_any_gcs_ref(value)
        return False

    return visit(doc)


def _chat_room_doc_has_real_photo_leak(doc: Mapping[str, Any]) -> bool:
    chat_forbidden = PUBLIC_USER_FORBIDDEN_KEYS | {
        "privatephotourl",
        "privatephotourls",
    }

    def visit(value: Any) -> bool:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if _public_key_is_forbidden(str(key), chat_forbidden):
                    return True
                if visit(child):
                    return True
        elif isinstance(value, list):
            return any(visit(child) for child in value)
        elif isinstance(value, str):
            return _contains_private_or_signed_ref(value) or _contains_any_gcs_ref(value)
        return False

    return visit(doc)


def _iter_client_dart_files(repo_root: Path) -> Iterable[Path]:
    for root in CLIENT_DART_SCAN_ROOTS:
        scan_root = repo_root / root
        if scan_root.exists():
            yield from scan_root.rglob("*.dart")


def _scan_client_code(repo_root: Path) -> int:
    count = 0
    forbidden_patterns = [
        PRIVATE_SOURCE_PHOTO_BUCKET,
        AVATAR_TEMP_BUCKET,
        CHAT_PROFILE_PHOTO_BUCKET,
        "userPrivateMedia",
        "clipEmbeddings",
        "avatarCandidates",
        "avatarJobs",
    ]
    display_photo_urls = re.compile(r"onboarding\s*(?:\[(['\"])photoUrls\1\]|\.photoUrls)")
    resolver_photo_fallback = re.compile(r"ProfileDisplayImageResolver[\s\S]{0,800}photoUrls")
    direct_photo_url_display = re.compile(
        r"\b(?:Image\.network|CaptureProtectedImage)\s*\([^;]*\bphotoUrls\b",
        re.DOTALL,
    )

    allow_photo_url_files = {
        "lib/features/onboarding/screens/photo_upload_screen.dart",
        "lib/features/profile/screens/profile_edit_screen.dart",
        "lib/features/onboarding/providers/onboarding_provider.dart",
        "lib/services/onboarding_save_helper.dart",
        "lib/services/user_service.dart",
        "lib/data/models/user/user_profile_model.dart",
        "lib/data/models/matching/match_model.dart",
        "lib/data/repositories/user_repository.dart",
    }

    for path in _iter_client_dart_files(repo_root):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(repo_root).as_posix()
        if direct_photo_url_display.search(text):
            count += 1
        for pattern in forbidden_patterns:
            if pattern not in text:
                continue
            if (
                pattern in {PRIVATE_SOURCE_PHOTO_BUCKET, AVATAR_TEMP_BUCKET, CHAT_PROFILE_PHOTO_BUCKET}
                and rel in CLIENT_SENSITIVE_POLICY_FILES
            ):
                continue
            count += 1
            break
        if rel in CLIENT_LEGACY_PHOTO_URL_MODEL_FILES and not direct_photo_url_display.search(text):
            continue
        if display_photo_urls.search(text) and rel not in allow_photo_url_files:
            count += 1
        if path.name == "profile_display_image_resolver.dart" and resolver_photo_fallback.search(text):
            count += 1
    return count


def scan_client_surfaces(
    repo_root: Path,
    *,
    festival_roots: Iterable[Path] = (),
) -> PrivacyQASummary:
    scan = scan_client_files(
        repo_root,
        festival_roots=tuple(Path(root) for root in festival_roots),
    )
    return PrivacyQASummary(
        client_code_leakage_count=scan.leakage_count,
        scanned_file_count=scan.scanned_file_count,
    )


def run_fixture_checks(
    fixture: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
    check_client_code: bool = True,
    festival_roots: Iterable[Path] = (),
) -> PrivacyQASummary:
    users = fixture.get("users") if isinstance(fixture.get("users"), Mapping) else {}
    private_media = fixture.get("userPrivateMedia") if isinstance(fixture.get("userPrivateMedia"), Mapping) else {}
    clip_embeddings = fixture.get("clipEmbeddings") if isinstance(fixture.get("clipEmbeddings"), Mapping) else {}
    model_recs = fixture.get("modelRecs") if isinstance(fixture.get("modelRecs"), Mapping) else {}
    chat_rooms = fixture.get("chatRooms") if isinstance(fixture.get("chatRooms"), Mapping) else {}
    browser_storage = fixture.get("browserStorage") if isinstance(fixture.get("browserStorage"), Mapping) else {}
    public_reports = fixture.get("reports") if isinstance(fixture.get("reports"), Mapping) else {}
    public_logs = fixture.get("logs") if isinstance(fixture.get("logs"), Mapping) else {}

    summary = PrivacyQASummary(total_users_scanned=len(users))
    summary.browser_storage_leakage_count = count_leaky_records(browser_storage)
    summary.public_report_leakage_count = count_leaky_records(public_reports)
    summary.public_log_leakage_count = count_leaky_records(public_logs)
    summary.public_leakage_count = sum(
        1 for doc in users.values() if isinstance(doc, Mapping) and _public_doc_has_source_photo_leak(doc)
    )
    summary.private_media_invalid_count = sum(
        1
        for uid, doc in private_media.items()
        if isinstance(doc, Mapping) and _private_media_doc_is_invalid(str(uid), doc)
    )
    summary.clip_embeddings_invalid_count = sum(
        1 for doc in clip_embeddings.values() if isinstance(doc, Mapping) and _clip_embedding_doc_is_invalid(doc)
    )
    summary.model_recs_unsafe_exposure_count = sum(
        1 for doc in model_recs.values() if isinstance(doc, Mapping) and _public_recommendation_doc_is_unsafe(doc)
    )
    summary.chat_room_leakage_count = sum(
        1 for doc in chat_rooms.values() if isinstance(doc, Mapping) and _chat_room_doc_has_real_photo_leak(doc)
    )

    display_status = load_avatar_display_status_from_docs(dict(users))
    for value in model_recs.values():
        for nested in _iter_values(value):
            if not isinstance(nested, Mapping):
                continue
            items = nested.get("items") or nested.get("candidates")
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                try:
                    validate_public_recommendation_item(item)
                except ValueError:
                    summary.model_recs_unsafe_exposure_count += 1
                uid = item.get("uid")
                if isinstance(uid, str):
                    status = display_status.get(uid)
                    if not status or status.get("displayReady") is not True:
                        summary.missing_approved_avatar_count += 1

    load_users_with_private_source_photos_from_docs(dict(private_media))
    if check_client_code:
        client_scan = scan_client_surfaces(repo_root, festival_roots=festival_roots)
        summary.client_code_leakage_count = max(
            _scan_client_code(repo_root),
            client_scan.client_code_leakage_count,
        )
        summary.scanned_file_count = client_scan.scanned_file_count
    return summary


def _load_firestore_fixture(
    project: str,
    database: Optional[str],
    users_collection: str,
    private_media_collection: str,
    clip_embeddings_collection: str,
    chat_rooms_collection: str,
    model_recs_collection_group: str,
    model_recs_root: str,
    model_recs_limit: int,
) -> Dict[str, Any]:
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is not installed.")
    db = firestore.Client(project=project, database=database)
    fixture = {
        "users": {doc.id: (doc.to_dict() or {}) for doc in db.collection(users_collection).stream()},
        "userPrivateMedia": {
            doc.id: (doc.to_dict() or {})
            for doc in db.collection(private_media_collection).stream()
        },
        "clipEmbeddings": {
            doc.id: (doc.to_dict() or {})
            for doc in db.collection(clip_embeddings_collection).stream()
        },
        "modelRecs": {},
        "chatRooms": {doc.id: (doc.to_dict() or {}) for doc in db.collection(chat_rooms_collection).stream()},
    }
    if model_recs_collection_group.lower() not in {"", "none", "skip"}:
        query = db.collection_group(model_recs_collection_group)
        if model_recs_limit > 0:
            query = query.limit(model_recs_limit)
        model_recs: Dict[str, Any] = {}
        for doc in query.stream():
            path = doc.reference.path
            if model_recs_root and not path.startswith(f"{model_recs_root}/"):
                continue
            model_recs[path] = doc.to_dict() or {}
        fixture["modelRecs"] = model_recs
    return fixture


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Seolleyeon media privacy invariants.")
    parser.add_argument("--firestore_project", default=None)
    parser.add_argument("--firestore_database", default=None)
    parser.add_argument("--users", "--users_collection", dest="users_collection", default="users")
    parser.add_argument(
        "--private_media",
        "--private_media_collection",
        dest="private_media_collection",
        default="userPrivateMedia",
    )
    parser.add_argument(
        "--clip",
        "--clip_embeddings_collection",
        dest="clip_embeddings_collection",
        default="clipEmbeddings",
    )
    parser.add_argument("--chat_rooms", "--chat_rooms_collection", dest="chat_rooms_collection", default="chat_rooms")
    parser.add_argument(
        "--model_recs",
        dest="model_recs_collection_group",
        default="sources",
        help="Firestore collection group containing model recommendation source docs; use 'none' to skip.",
    )
    parser.add_argument("--model_recs_root", "--model_recs_collection", dest="model_recs_root", default="modelRecs")
    parser.add_argument("--model_recs_limit", type=int, default=500)
    parser.add_argument("--fixture", "--fixture_json", "--fixtures_path", dest="fixture_json", default=None)
    parser.add_argument("--scan_client_code", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--no_client_code_check", action="store_true")
    parser.add_argument(
        "--festival_root",
        action="append",
        default=[],
        help="Additional festival client repository root to scan; repeat as needed.",
    )
    parser.add_argument("--fail_on_warning", action="store_true")
    parser.add_argument("--dry_run", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.fixture_json:
        fixture = json.loads(Path(args.fixture_json).read_text(encoding="utf-8"))
    elif args.firestore_project and not args.dry_run:
        fixture = _load_firestore_fixture(
            args.firestore_project,
            args.firestore_database,
            args.users_collection,
            args.private_media_collection,
            args.clip_embeddings_collection,
            args.chat_rooms_collection,
            args.model_recs_collection_group,
            args.model_recs_root,
            args.model_recs_limit,
        )
    else:
        fixture = {
            "users": {},
            "userPrivateMedia": {},
            "clipEmbeddings": {},
            "modelRecs": {},
            "chatRooms": {},
        }

    summary = run_fixture_checks(
        fixture,
        repo_root=REPO_ROOT,
        check_client_code=bool(args.scan_client_code) and not args.no_client_code_check,
        festival_roots=[Path(value).resolve() for value in args.festival_root],
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0 if summary.passed or not args.fail_on_warning else 1


if __name__ == "__main__":
    raise SystemExit(main())
