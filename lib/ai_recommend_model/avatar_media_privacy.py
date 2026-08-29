from __future__ import annotations

from io import BytesIO
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, unquote, urlparse

from PIL import Image


# The legacy bucket is retained for compatibility with historical fixtures.
# Staging uses the final-project alias; both are private and never displayable.
PRIVATE_SOURCE_PHOTO_BUCKET = "seolleyeon-private-source-photos"
PRIVATE_SOURCE_PHOTO_BUCKETS = frozenset(
    {PRIVATE_SOURCE_PHOTO_BUCKET, "seolleyeon-final-private-source-photos"}
)
CHAT_PROFILE_PHOTO_BUCKETS = frozenset(
    {"seolleyeon-chat-profile-photos", "seolleyeon-final-chat-profile-photos"}
)
AVATAR_TEMP_BUCKETS = frozenset(
    {"seolleyeon-avatar-temp", "seolleyeon-final-avatar-temp"}
)
_SIGNED_QUERY_KEYS = {"googleaccessid", "signature", "expires", "awsaccesskeyid"}
_SIGNED_QUERY_PREFIXES = ("x-goog-", "x-amz-")
_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
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
        "embedding",
        "embeddings",
        "rawvector",
        "rawvectors",
        "approvedavatarstoragepath",
    }
)
_DROP = object()


def _parse_gcs_uri(uri: str) -> tuple[str, str]:
    if not isinstance(uri, str):
        raise ValueError("GCS URI must be a string.")
    parsed = urlparse(uri.strip())
    if parsed.scheme.lower() not in {"gs", "gcs"}:
        raise ValueError("GCS URI must use gs:// or gcs://.")
    bucket = parsed.netloc.strip()
    object_path = unquote(parsed.path.lstrip("/")).strip()
    if not bucket or not object_path:
        raise ValueError("GCS URI must include bucket and object path.")
    if parsed.query or parsed.fragment:
        raise ValueError("GCS URI must not contain query or fragment data.")
    return bucket, object_path


def _load_image_from_gcs(
    uri: str,
    *,
    max_bytes: int,
    allowed_buckets: set[str],
    storage_client: Any | None = None,
) -> Image.Image:
    bucket_name, object_path = _parse_gcs_uri(uri)
    allowed = {str(value).strip() for value in allowed_buckets if str(value).strip()}
    if bucket_name not in allowed:
        raise ValueError(f"Bucket not allowed: {bucket_name}")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive.")
    client = storage_client
    if client is None:
        from google.cloud import storage

        client = storage.Client()
    blob = client.bucket(bucket_name).blob(object_path)
    reload_blob = getattr(blob, "reload", None)
    if callable(reload_blob):
        reload_blob()
    if hasattr(blob, "exists") and callable(blob.exists) and not blob.exists():
        raise ValueError("Image not found.")
    size = getattr(blob, "size", None)
    if size is not None and int(size) > max_bytes:
        raise ValueError(f"Image too large (content-length: {size} > {max_bytes}).")
    data = blob.download_as_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"Image too large (downloaded {len(data)} > {max_bytes}).")
    try:
        return Image.open(BytesIO(data)).convert("RGB")
    except Exception as exc:
        raise ValueError("Image decode failed.") from exc


def _is_signed_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered in _SIGNED_QUERY_KEYS or lowered.startswith(_SIGNED_QUERY_PREFIXES):
            return True
    lowered = value.lower()
    return any(marker in lowered for marker in ("x-goog-", "x-amz-", "googleaccessid=", "signature=", "expires=", "awsaccesskeyid="))


def _is_private_or_signed_image_ref(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    text = unquote(value.strip())
    lowered = text.lower()
    if lowered.startswith(("gs://", "gcs://")):
        return True
    if _is_signed_url(text):
        return True
    if any(bucket.lower() in lowered for bucket in (*PRIVATE_SOURCE_PHOTO_BUCKETS, *CHAT_PROFILE_PHOTO_BUCKETS, *AVATAR_TEMP_BUCKETS)):
        return True
    if any(marker in lowered for marker in ("private-source-photos", "avatar-temp", "chat-profile-photos")):
        return True
    try:
        parsed = urlparse(text)
    except Exception:
        return False
    if (parsed.netloc or "").lower() in {"storage.googleapis.com", "firebasestorage.googleapis.com"}:
        return "/source/" in unquote(parsed.path or "").lower()
    return False


def _consent_value(consent: Mapping[str, Any], key: str) -> bool:
    purposes = consent.get("purposes")
    if isinstance(purposes, Mapping) and key in purposes:
        return purposes.get(key) is True
    return consent.get(key) is True


def _active_source_ref(uid: str, entry: Mapping[str, Any]) -> str | None:
    if str(entry.get("status") or "").strip().lower() != "active":
        return None
    uri = str(entry.get("gcsUri") or "").strip()
    try:
        bucket, object_path = _parse_gcs_uri(uri)
    except ValueError:
        return None
    if bucket not in PRIVATE_SOURCE_PHOTO_BUCKETS:
        return None
    if not object_path.startswith(f"users/{uid}/source/") or object_path.endswith("/"):
        return None
    if any(key in entry for key in ("downloadUrl", "downloadURL", "signedUrl", "previewUrl")):
        return None
    purpose = entry.get("purpose")
    if not isinstance(purpose, Mapping) or not _consent_value(purpose, "clipRecommendation"):
        return None
    return uri


def load_users_with_private_source_photos_from_docs(
    docs: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for uid, doc in docs.items():
        if not isinstance(doc, Mapping):
            continue
        consent = doc.get("photoConsent")
        if not isinstance(consent, Mapping) or not _consent_value(consent, "clipRecommendation"):
            continue
        source_photos = doc.get("sourcePhotos")
        if not isinstance(source_photos, list):
            continue
        refs = [
            ref
            for entry in source_photos
            if isinstance(entry, Mapping)
            for ref in [_active_source_ref(str(uid), entry)]
            if ref is not None
        ]
        if refs:
            result[str(uid)] = refs
    return result


def extract_display_avatar_url(doc: Mapping[str, Any]) -> str:
    avatar = doc.get("avatar")
    if not isinstance(avatar, Mapping) or str(avatar.get("status") or "").strip().lower() != "approved":
        return ""
    value = str(avatar.get("approvedAvatarUrl") or "").strip()
    if not value.startswith("https://") or _is_private_or_signed_image_ref(value):
        return ""
    return value


def load_avatar_display_status_from_docs(
    docs: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for uid, doc in docs.items():
        if not isinstance(doc, Mapping):
            continue
        avatar = doc.get("avatar") if isinstance(doc.get("avatar"), Mapping) else {}
        avatar_status = str(avatar.get("status") or "none")
        approved_url = extract_display_avatar_url(doc)
        profile_ready = all(
            doc.get(key, True) is not False
            for key in ("isActive", "isStudentVerified", "isProfileComplete")
        )
        ready = bool(approved_url) and profile_ready
        result[str(uid)] = {
            "displayReady": ready,
            "approvedAvatarUrl": approved_url if ready else "",
            "avatarStatus": avatar_status,
            "reason": None if ready else "missing_approved_avatar",
        }
    return result


def _forbidden_key(key: Any) -> bool:
    lowered = str(key).replace("_", "").lower()
    return lowered in _FORBIDDEN_PUBLIC_KEYS or "sourcephoto" in lowered or lowered.startswith("faceembedding")


def _forbidden_value(value: Any) -> bool:
    return isinstance(value, str) and (_is_private_or_signed_image_ref(value) or value.strip().lower().startswith(("gs://", "gcs://")))


def validate_public_recommendation_item(item: Mapping[str, Any]) -> None:
    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if _forbidden_key(key) or _forbidden_value(child):
                    raise ValueError("Forbidden public recommendation field.")
                visit(child)
        elif isinstance(value, list):
            for child in value:
                if _forbidden_value(child):
                    raise ValueError("Forbidden public recommendation field.")
                visit(child)
        elif _forbidden_value(value):
            raise ValueError("Forbidden public recommendation field.")
    visit(item)


def sanitize_public_recommendation_item(
    item: Mapping[str, Any],
    *,
    approved_avatar_url: str | None = None,
) -> dict[str, Any]:
    def sanitize(value: Any) -> Any:
        if isinstance(value, Mapping):
            output: dict[str, Any] = {}
            for key, child in value.items():
                if _forbidden_key(key):
                    continue
                cleaned = sanitize(child)
                if cleaned is not _DROP:
                    output[str(key)] = cleaned
            return output
        if isinstance(value, list):
            output = []
            for child in value:
                cleaned = sanitize(child)
                if cleaned is not _DROP:
                    output.append(cleaned)
            return output
        if _forbidden_value(value):
            return _DROP
        return value

    output = sanitize(item)
    if not isinstance(output, dict):
        output = {}
    if approved_avatar_url and approved_avatar_url.startswith("https://") and not _forbidden_value(approved_avatar_url):
        output["approvedAvatarUrl"] = approved_avatar_url
    return output


def filter_recommendation_items_for_display_ready(
    items: Iterable[Mapping[str, Any]],
    display_status: Mapping[str, Mapping[str, Any]],
    *,
    require_approved_avatar: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    filtered: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    for item in items:
        uid = str(item.get("uid") or "") if isinstance(item, Mapping) else ""
        status = display_status.get(uid, {})
        if require_approved_avatar and status.get("displayReady") is not True:
            reason = str(status.get("reason") or "missing_approved_avatar")
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        cleaned = sanitize_public_recommendation_item(
            item,
            approved_avatar_url=str(status.get("approvedAvatarUrl") or "") or None,
        )
        validate_public_recommendation_item(cleaned)
        filtered.append(cleaned)
    return filtered, skipped


__all__ = [
    "PRIVATE_SOURCE_PHOTO_BUCKET",
    "PRIVATE_SOURCE_PHOTO_BUCKETS",
    "_is_private_or_signed_image_ref",
    "_load_image_from_gcs",
    "_parse_gcs_uri",
    "extract_display_avatar_url",
    "filter_recommendation_items_for_display_ready",
    "load_avatar_display_status_from_docs",
    "load_users_with_private_source_photos_from_docs",
    "sanitize_public_recommendation_item",
    "validate_public_recommendation_item",
]
