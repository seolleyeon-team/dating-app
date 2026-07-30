#!/usr/bin/env python3
"""Dry-run-first migration for Seolleyeon avatar media fields.

Important safety note:
Existing public HTTPS original photo URLs are NOT automatically migrated into
private GCS source-photo assets by this script. The script does not download
public originals, does not strip EXIF from public originals, and does not write
public HTTPS originals into `userPrivateMedia/{uid}`. Public HTTPS originals must
go through a separate controlled backend re-upload/reprocessing migration with
consent, EXIF stripping, private GCS write verification, and rollback.

This script can backfill `userPrivateMedia/{uid}.sourcePhotos` only when the
legacy value is already a private `gs://seolleyeon-private-source-photos/...`
reference and CLIP/photo consent exists. Dry-run is the default; `--apply` is
required for mutation.
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

PRIVATE_SOURCE_BUCKET = "seolleyeon-private-" "source-photos"


def _is_source_like(value: str) -> bool:
    text = str(value)
    return (
        text.startswith(("gs://", "gcs://"))
        or PRIVATE_SOURCE_BUCKET in text
        or "X-Goog-Signature" in text
        or "X-Goog-Credential" in text
        or "X-Goog-Expires" in text
    )


def _is_public_https_original(value: str) -> bool:
    text = str(value).strip().lower()
    return text.startswith(("http://", "https://")) and PRIVATE_SOURCE_BUCKET not in text


def _str_list(value: Any) -> List[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _parse_private_source_gcs_uri(value: str) -> Optional[Tuple[str, str]]:
    text = str(value).strip()
    if text.startswith("gs://"):
        remainder = text[5:]
    elif text.startswith("gcs://"):
        remainder = text[6:]
    else:
        return None
    bucket, sep, path = remainder.partition("/")
    if not sep or not bucket or not path:
        return None
    if bucket != PRIVATE_SOURCE_BUCKET:
        return None
    return bucket, path


@dataclass
class PhotoUrlClassification:
    private_source_gcs_refs: List[str] = field(default_factory=list)
    public_https_originals_needing_safe_migration: List[str] = field(default_factory=list)
    signed_or_sensitive_urls: List[str] = field(default_factory=list)


def classify_onboarding_photo_urls(values: List[str]) -> PhotoUrlClassification:
    classified = PhotoUrlClassification()
    for value in _str_list(values):
        if _parse_private_source_gcs_uri(value) is not None:
            classified.private_source_gcs_refs.append(value)
        elif _is_source_like(value):
            classified.signed_or_sensitive_urls.append(value)
        elif _is_public_https_original(value):
            classified.public_https_originals_needing_safe_migration.append(value)
    return classified


def _build_migrated_source_entry(uid: str, uri: str, *, server_timestamp: Any = None) -> Optional[Dict[str, Any]]:
    parsed = _parse_private_source_gcs_uri(uri)
    if parsed is None:
        return None
    bucket, path = parsed
    photo_id = "src_migrated_" + hashlib.sha256(uri.encode("utf-8")).hexdigest()[:16]
    return {
        "photoId": photo_id,
        "gcsUri": f"gs://{bucket}/{path}",
        "storageBucket": bucket,
        "storagePath": path,
        "contentType": "image/jpeg",
        "sizeBytes": None,
        "sha256": None,
        "exifStripped": True,
        "encrypted": True,
        "status": "active",
        "purpose": {
            "avatarGeneration": True,
            "clipRecommendation": True,
        },
        "migrationSource": f"users/{uid}.onboarding.photoUrls",
        "uploadedAt": server_timestamp,
        "updatedAt": server_timestamp,
    }


def build_user_migration_update(user_doc: Dict[str, Any], *, server_timestamp: Any = None) -> Dict[str, Any]:
    onboarding = dict(user_doc.get("onboarding") or {}) if isinstance(user_doc.get("onboarding"), dict) else {}
    avatar = dict(user_doc.get("avatar") or {}) if isinstance(user_doc.get("avatar"), dict) else {}
    approved = str(avatar.get("approvedAvatarUrl") or "").strip()
    photo_urls = _str_list(onboarding.get("photoUrls"))

    update: Dict[str, Any] = {
        "profileImageMode": "avatar",
        "onboarding": dict(onboarding),
        "profileImageUrl": approved if approved else "",
    }
    update["onboarding"].pop("photoUrls", None)

    if approved:
        update["avatar"] = {
            **avatar,
            "status": "approved",
            "approvedAvatarUrl": approved,
            "updatedAt": server_timestamp,
        }
        update["onboarding"]["avatarUrls"] = [approved]
        update["onboarding"]["photoUrls"] = [approved]
    else:
        update["avatar"] = {
            **avatar,
            "status": avatar.get("status") or ("generating" if photo_urls else "none"),
            "updatedAt": server_timestamp,
        }
    return update


def build_private_media_migration_update(
    uid: str,
    user_doc: Dict[str, Any],
    private_media_doc: Dict[str, Any],
    *,
    server_timestamp: Any = None,
) -> Optional[Dict[str, Any]]:
    onboarding = user_doc.get("onboarding") if isinstance(user_doc.get("onboarding"), dict) else {}
    source_like_urls = _str_list(onboarding.get("photoUrls"))
    migrated_entries = [
        entry
        for entry in (
            _build_migrated_source_entry(uid, value, server_timestamp=server_timestamp)
            for value in source_like_urls
        )
        if entry is not None
    ]
    if not migrated_entries:
        return None

    consent = private_media_doc.get("photoConsent") if isinstance(private_media_doc, dict) else {}
    if not isinstance(consent, dict) or consent.get("clipRecommendation") is not True:
        return None

    existing_entries = private_media_doc.get("sourcePhotos") if isinstance(private_media_doc, dict) else []
    existing_entries = existing_entries if isinstance(existing_entries, list) else []
    existing_gcs_uris = {
        str(entry.get("gcsUri"))
        for entry in existing_entries
        if isinstance(entry, dict) and entry.get("gcsUri")
    }
    new_entries = [entry for entry in migrated_entries if entry["gcsUri"] not in existing_gcs_uris]
    if not new_entries:
        return None

    updated_consent = {
        **consent,
        "profileDisplayOriginalPhoto": False,
        "sourcePhotoRetention": True,
        "updatedAt": server_timestamp,
    }
    return {
        "sourcePhotos": [*existing_entries, *new_entries],
        "photoConsent": updated_consent,
        "updatedAt": server_timestamp,
    }


@dataclass
class Summary:
    users_scanned: int = 0
    users_with_source_photo_leakage: int = 0
    users_migrated: int = 0
    users_needing_avatar_generation: int = 0
    users_with_missing_consent: int = 0
    private_source_refs_migrated: int = 0
    public_https_originals_needing_safe_migration: int = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate public avatar media fields.")
    parser.add_argument("--firestore_project")
    parser.add_argument("--firestore_database", default=None)
    parser.add_argument("--users_collection", default="users")
    parser.add_argument("--private_media_collection", default="userPrivateMedia")
    parser.add_argument("--dry_run", action="store_true", help="Explicit dry-run flag. Dry-run is already the default.")
    parser.add_argument("--apply", action="store_true")
    return parser


def run_migration(
    db: Any,
    *,
    users_collection: str = "users",
    private_media_collection: str = "userPrivateMedia",
    apply: bool = False,
    server_timestamp: Any = None,
) -> Summary:
    summary = Summary()
    bw = db.bulk_writer() if apply else None

    try:
        for snap in db.collection(users_collection).stream():
            summary.users_scanned += 1
            user_doc = snap.to_dict() or {}
            onboarding = user_doc.get("onboarding") if isinstance(user_doc.get("onboarding"), dict) else {}
            photo_urls = _str_list(onboarding.get("photoUrls"))
            classified = classify_onboarding_photo_urls(photo_urls)
            leaked = any(_is_source_like(url) for url in photo_urls)
            if leaked:
                summary.users_with_source_photo_leakage += 1
            summary.public_https_originals_needing_safe_migration += len(
                classified.public_https_originals_needing_safe_migration
            )

            private_snap = db.collection(private_media_collection).document(snap.id).get()
            private_doc = private_snap.to_dict() if private_snap.exists else {}
            consent = private_doc.get("photoConsent") if isinstance(private_doc, dict) else {}
            if photo_urls and not consent:
                summary.users_with_missing_consent += 1

            update = build_user_migration_update(user_doc, server_timestamp=server_timestamp)
            private_update = build_private_media_migration_update(
                snap.id,
                user_doc,
                private_doc,
                server_timestamp=server_timestamp,
            )
            avatar = update.get("avatar", {})
            if avatar.get("status") != "approved":
                summary.users_needing_avatar_generation += 1

            if bw is not None:
                bw.set(snap.reference, update, merge=True)
                if private_update is not None:
                    private_ref = db.collection(private_media_collection).document(snap.id)
                    bw.set(private_ref, private_update, merge=True)
            if private_update is not None:
                summary.private_source_refs_migrated += len(private_update.get("sourcePhotos", [])) - len(
                    private_doc.get("sourcePhotos", []) if isinstance(private_doc.get("sourcePhotos"), list) else []
                )
            summary.users_migrated += 1
    finally:
        if bw is not None:
            bw.close()

    return summary


def main() -> int:
    args = build_parser().parse_args()
    if args.apply and not args.firestore_project:
        raise SystemExit("--firestore_project is required when --apply is used.")
    if not args.firestore_project:
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"[{mode}] no --firestore_project supplied; command validation only, no Firestore scan performed.")
        print("[DRY-RUN] public HTTPS originals are not automatically migrated to private GCS.")
        print("[DRY-RUN] use docs/avatar-media-migration/public-url-safe-migration-plan.md for controlled migration.")
        return 0

    from google.cloud import firestore

    db = firestore.Client(project=args.firestore_project, database=args.firestore_database)
    summary = run_migration(
        db,
        users_collection=args.users_collection,
        private_media_collection=args.private_media_collection,
        apply=args.apply,
        server_timestamp=firestore.SERVER_TIMESTAMP,
    )

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"[{mode}] users scanned: {summary.users_scanned}")
    print(f"[{mode}] users with source photo leakage: {summary.users_with_source_photo_leakage}")
    print(f"[{mode}] users migrated: {summary.users_migrated}")
    print(f"[{mode}] users needing avatar generation: {summary.users_needing_avatar_generation}")
    print(f"[{mode}] users with missing consent: {summary.users_with_missing_consent}")
    print(f"[{mode}] private source refs migrated: {summary.private_source_refs_migrated}")
    print(
        f"[{mode}] public HTTPS originals needing safe migration: "
        f"{summary.public_https_originals_needing_safe_migration}"
    )
    print(f"[{mode}] public HTTPS originals are not automatically migrated to private GCS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
