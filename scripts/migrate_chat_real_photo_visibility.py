#!/usr/bin/env python3
"""Dry-run first migration helper for chat-partner real profile photo visibility."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

CHAT_PROFILE_PHOTO_BUCKET = "seolleyeon-chat-profile-photos"
PRIVATE_SOURCE_PHOTO_BUCKET = "seolleyeon-private-source-photos"
CONSENT_VERSION = "chat_real_photo_visibility_v1"

try:
    from google.cloud import firestore, storage
except Exception:  # pragma: no cover - optional for local dry-run docs
    firestore = None
    storage = None


@dataclass
class MigrationDecision:
    uid: str
    status: str
    source_photo_id: str = ""
    source_gcs_uri: str = ""
    target_bucket: str = CHAT_PROFILE_PHOTO_BUCKET
    target_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "status": self.status,
            "sourcePhotoId": self.source_photo_id,
            "sourceGcsUri": self.source_gcs_uri,
            "targetBucket": self.target_bucket,
            "targetPath": self.target_path,
        }


def _parse_gcs_uri(uri: str) -> Tuple[str, str]:
    if not uri.startswith("gs://"):
        raise ValueError("GCS URI must start with gs://")
    without_scheme = uri[5:]
    bucket, _, path = without_scheme.partition("/")
    if not bucket or not path:
        raise ValueError("GCS URI must include bucket and object path")
    return bucket, path


def _iter_active_source_photos(private_doc: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    source_photos = private_doc.get("sourcePhotos")
    if not isinstance(source_photos, list):
        return []
    return (
        entry
        for entry in source_photos
        if isinstance(entry, Mapping) and entry.get("status") == "active"
    )


def decide_chat_real_photo_migration(uid: str, private_doc: Mapping[str, Any]) -> MigrationDecision:
    consent = private_doc.get("photoConsent")
    if not isinstance(consent, Mapping) or consent.get("chatPartnerRealPhotoDisclosure") is not True:
        return MigrationDecision(uid=uid, status="missing_chat_real_photo_consent")

    for source in _iter_active_source_photos(private_doc):
        photo_id = str(source.get("photoId") or "")
        gcs_uri = str(source.get("gcsUri") or "")
        if gcs_uri.startswith("http://") or gcs_uri.startswith("https://"):
            return MigrationDecision(
                uid=uid,
                status="needs_safe_reupload_or_reprocess",
                source_photo_id=photo_id,
                source_gcs_uri=gcs_uri,
            )
        try:
            source_bucket, _ = _parse_gcs_uri(gcs_uri)
        except ValueError:
            continue
        if source_bucket != PRIVATE_SOURCE_PHOTO_BUCKET:
            continue
        target_path = f"users/{uid}/chat-profile/{photo_id}.jpg"
        return MigrationDecision(
            uid=uid,
            status="ready_to_copy",
            source_photo_id=photo_id,
            source_gcs_uri=gcs_uri,
            target_path=target_path,
        )

    return MigrationDecision(uid=uid, status="no_active_private_source_photo")


def build_chat_real_photo_update(decision: MigrationDecision, *, server_timestamp: Any) -> Optional[Dict[str, Any]]:
    if decision.status != "ready_to_copy":
        return None
    return {
        "photoConsent.chatPartnerRealPhotoDisclosure": True,
        "photoConsent.version": "photo_consent_v3",
        "chatRealPhoto": {
            "photoId": decision.source_photo_id,
            "enabled": True,
            "consentVersion": CONSENT_VERSION,
            "sourcePhotoId": decision.source_photo_id,
            "storageBucket": CHAT_PROFILE_PHOTO_BUCKET,
            "storagePath": decision.target_path,
            "gcsUri": f"gs://{CHAT_PROFILE_PHOTO_BUCKET}/{decision.target_path}",
            "contentType": "image/jpeg",
            "exifStripped": True,
            "updatedAt": server_timestamp,
        },
        "updatedAt": server_timestamp,
    }


def _load_firestore_docs(project: str, database: Optional[str], collection: str, limit: int) -> Dict[str, Mapping[str, Any]]:
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is not installed.")
    db = firestore.Client(project=project, database=database)
    query = db.collection(collection)
    if limit > 0:
        query = query.limit(limit)
    return {doc.id: (doc.to_dict() or {}) for doc in query.stream()}


def _apply_decision(project: str, database: Optional[str], collection: str, decision: MigrationDecision) -> None:
    if firestore is None or storage is None:
        raise RuntimeError("google-cloud-firestore and google-cloud-storage are required for --apply.")
    source_bucket, source_path = _parse_gcs_uri(decision.source_gcs_uri)
    storage_client = storage.Client(project=project)
    source_blob = storage_client.bucket(source_bucket).blob(source_path)
    target_blob = storage_client.bucket(CHAT_PROFILE_PHOTO_BUCKET).blob(decision.target_path)
    target_blob.rewrite(source_blob)

    db = firestore.Client(project=project, database=database)
    update = build_chat_real_photo_update(decision, server_timestamp=firestore.SERVER_TIMESTAMP)
    if update is None:
        return
    db.collection(collection).document(decision.uid).update(update)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare chat-visible real profile photo assets.")
    parser.add_argument("--firestore_project", default=None)
    parser.add_argument("--firestore_database", default=None)
    parser.add_argument("--private_media_collection", default="userPrivateMedia")
    parser.add_argument("--fixture_json", default=None)
    parser.add_argument("--output_json", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry_run", action="store_true", help="Explicit no-op alias; dry-run is the default.")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.fixture_json:
        docs = json.loads(Path(args.fixture_json).read_text(encoding="utf-8"))
    elif args.firestore_project:
        docs = _load_firestore_docs(
            args.firestore_project,
            args.firestore_database,
            args.private_media_collection,
            args.limit,
        )
    else:
        docs = {}

    decisions = [
        decide_chat_real_photo_migration(str(uid), doc)
        for uid, doc in docs.items()
        if isinstance(doc, Mapping)
    ]

    if args.apply:
        if not args.firestore_project:
            raise SystemExit("--firestore_project is required with --apply")
        for decision in decisions:
            if decision.status == "ready_to_copy":
                _apply_decision(
                    args.firestore_project,
                    args.firestore_database,
                    args.private_media_collection,
                    decision,
                )

    report = {
        "mode": "apply" if args.apply else "dry_run",
        "total": len(decisions),
        "counts": {},
        "decisions": [decision.to_dict() for decision in decisions],
    }
    for decision in decisions:
        report["counts"][decision.status] = report["counts"].get(decision.status, 0) + 1

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output_json:
        Path(args.output_json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
