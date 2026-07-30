#!/usr/bin/env python3
"""Private source photo upload helpers for Seolleyeon avatar media.

These helpers are intentionally backend-only. They build the private media
Firestore update and idempotent job payloads without creating public download
URLs for original user photos.
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from PIL import Image


PRIVATE_SOURCE_BUCKET = "seolleyeon-private-" "source-photos"
APPROVED_AVATAR_BUCKET = "seolleyeon-approved-" "avatars"
AVATAR_TEMP_BUCKET = "seolleyeon-avatar-temp"
PHOTO_CONSENT_VERSION = "photo_consent_v2"


def sha256_bytes(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


def strip_exif(image_bytes: bytes, *, image_format: str = "JPEG", quality: int = 92) -> bytes:
    """Return image bytes re-encoded without EXIF metadata."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        rgb = image.convert("RGB")
        out = io.BytesIO()
        rgb.save(out, format=image_format, quality=quality, optimize=True)
        return out.getvalue()


def build_photo_id(image_sha256: str) -> str:
    if not image_sha256 or len(image_sha256) < 12:
        raise ValueError("image_sha256 must be a SHA-256 hex digest")
    return f"src_{image_sha256[:16]}"


def build_source_photo_storage_path(uid: str, photo_id: str) -> str:
    uid = str(uid).strip()
    photo_id = str(photo_id).strip()
    if not uid or "/" in uid or not photo_id or "/" in photo_id:
        raise ValueError("uid and photo_id must be non-empty path segments")
    return f"users/{uid}/source/{photo_id}.jpg"


def build_source_photo_gcs_uri(uid: str, photo_id: str, *, bucket: str = PRIVATE_SOURCE_BUCKET) -> str:
    return f"gs://{bucket}/{build_source_photo_storage_path(uid, photo_id)}"


def _server_timestamp_or_now(server_timestamp: Any = None) -> Any:
    return server_timestamp if server_timestamp is not None else datetime.now(tz=timezone.utc)


def build_user_private_media_update(
    *,
    uid: str,
    photo_id: str,
    storage_bucket: str,
    storage_path: str,
    content_type: str,
    size_bytes: int,
    sha256: str,
    existing_source_photos: Optional[Iterable[Dict[str, Any]]] = None,
    server_timestamp: Any = None,
) -> Dict[str, Any]:
    """Build a full private-media document merge payload with sha256 dedupe."""
    existing = [dict(item) for item in (existing_source_photos or []) if isinstance(item, dict)]
    timestamp = _server_timestamp_or_now(server_timestamp)
    gcs_uri = f"gs://{storage_bucket}/{storage_path}"

    source_entry = {
        "photoId": photo_id,
        "gcsUri": gcs_uri,
        "storageBucket": storage_bucket,
        "storagePath": storage_path,
        "contentType": content_type,
        "sizeBytes": int(size_bytes),
        "sha256": sha256,
        "exifStripped": True,
        "encrypted": True,
        "status": "active",
        "purpose": {
            "avatarGeneration": True,
            "clipRecommendation": True,
        },
        "uploadedAt": timestamp,
        "updatedAt": timestamp,
    }

    deduped: List[Dict[str, Any]] = []
    replaced = False
    for item in existing:
        if item.get("sha256") == sha256 and item.get("status") == "active":
            updated = dict(item)
            updated.update(source_entry)
            deduped.append(updated)
            replaced = True
        else:
            deduped.append(item)
    if not replaced:
        deduped.append(source_entry)

    return {
        "sourcePhotos": deduped,
        "photoConsent": {
            "avatarGeneration": True,
            "clipRecommendation": True,
            "profileDisplayOriginalPhoto": False,
            "sourcePhotoRetention": True,
            "consentedAt": timestamp,
            "version": PHOTO_CONSENT_VERSION,
        },
        "clip": {
            "embeddingStatus": "pending",
            "embeddingVersion": "clip-vit-large-patch14_v1",
            "sourcePhotoIds": sorted({str(item.get("photoId")) for item in deduped if item.get("photoId")}),
        },
    }


def build_clip_job_payload(uid: str, source_photo_ids: Iterable[str]) -> Dict[str, Any]:
    ids = sorted({str(photo_id) for photo_id in source_photo_ids if str(photo_id).strip()})
    return {
        "type": "clip_embedding",
        "uid": uid,
        "sourcePhotoIds": ids,
        "idempotencyKey": f"clip:{uid}:{','.join(ids)}",
    }


def build_avatar_job_payload(uid: str, source_photo_ids: Iterable[str], *, candidate_count: int = 4) -> Dict[str, Any]:
    ids = sorted({str(photo_id) for photo_id in source_photo_ids if str(photo_id).strip()})
    return {
        "type": "avatar_generation",
        "uid": uid,
        "sourcePhotoIds": ids,
        "candidateCount": int(candidate_count),
        "modelId": "black-forest-labs/FLUX.2-klein-4B",
        "idempotencyKey": f"avatar:{uid}:{','.join(ids)}:{int(candidate_count)}",
    }


def enqueue_clip_job(uid: str, source_photo_ids: Iterable[str]) -> Dict[str, Any]:
    """Return the Cloud Tasks/Pub/Sub payload; caller owns actual enqueue."""
    return build_clip_job_payload(uid, source_photo_ids)


def enqueue_avatar_job(uid: str, source_photo_ids: Iterable[str], *, candidate_count: int = 4) -> Dict[str, Any]:
    """Return the Cloud Tasks/Pub/Sub payload; caller owns actual enqueue."""
    return build_avatar_job_payload(uid, source_photo_ids, candidate_count=candidate_count)
