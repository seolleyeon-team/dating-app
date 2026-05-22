from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    from google.cloud import firestore, storage
    from google.cloud.firestore import SERVER_TIMESTAMP
except Exception:  # pragma: no cover - optional in unit tests
    firestore = None  # type: ignore[assignment]
    storage = None  # type: ignore[assignment]
    SERVER_TIMESTAMP = datetime.now(tz=timezone.utc)


PRIVATE_SOURCE_BUCKET = "seolleyeon-private-source-photos"
AVATAR_TEMP_BUCKET = "seolleyeon-avatar-temp"
APPROVED_AVATAR_BUCKET = "seolleyeon-approved-avatars"
CHAT_PROFILE_PHOTO_BUCKET = "seolleyeon-chat-profile-photos"


class AvatarCleanupError(RuntimeError):
    pass


@dataclass(frozen=True)
class GcsRef:
    bucket: str
    path: str


@dataclass(frozen=True)
class CandidateCleanupAction:
    candidate_id: str
    image_ref: str
    reason: str


@dataclass
class CleanupSummary:
    dry_run: bool
    temp_candidates_scanned: int = 0
    temp_candidates_planned_for_delete: int = 0
    temp_candidates_deleted: int = 0
    source_photos_deleted: int = 0
    chat_profile_photos_deleted: int = 0
    approved_avatars_deleted: int = 0
    clip_embeddings_deleted: int = 0
    users_updated: int = 0
    jobs_updated: int = 0
    candidates_updated: int = 0
    skipped: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dryRun": self.dry_run,
            "tempCandidatesScanned": self.temp_candidates_scanned,
            "tempCandidatesPlannedForDelete": self.temp_candidates_planned_for_delete,
            "tempCandidatesDeleted": self.temp_candidates_deleted,
            "sourcePhotosDeleted": self.source_photos_deleted,
            "chatProfilePhotosDeleted": self.chat_profile_photos_deleted,
            "approvedAvatarsDeleted": self.approved_avatars_deleted,
            "clipEmbeddingsDeleted": self.clip_embeddings_deleted,
            "usersUpdated": self.users_updated,
            "jobsUpdated": self.jobs_updated,
            "candidatesUpdated": self.candidates_updated,
            "skipped": list(self.skipped),
        }


def parse_gcs_uri(source: str) -> GcsRef:
    match = re.match(r"^(?:gs|gcs)://([^/]+)/(.+)$", str(source).strip())
    if not match:
        raise AvatarCleanupError("Expected gs:// or gcs:// URI.")
    bucket = match.group(1).strip()
    path = match.group(2).strip()
    if not bucket or not path or path.startswith("/") or ".." in path.split("/"):
        raise AvatarCleanupError("Unsafe GCS URI.")
    return GcsRef(bucket=bucket, path=path)


def is_temp_candidate_ref(image_ref: str) -> bool:
    try:
        return parse_gcs_uri(image_ref).bucket == os.environ.get("AVATAR_TEMP_BUCKET", AVATAR_TEMP_BUCKET)
    except AvatarCleanupError:
        return False


def is_private_source_ref(image_ref: str) -> bool:
    try:
        return parse_gcs_uri(image_ref).bucket == os.environ.get("SOURCE_PHOTO_BUCKET", PRIVATE_SOURCE_BUCKET)
    except AvatarCleanupError:
        return False


def is_approved_avatar_ref(image_ref: str) -> bool:
    try:
        return parse_gcs_uri(image_ref).bucket == os.environ.get("APPROVED_AVATAR_BUCKET", APPROVED_AVATAR_BUCKET)
    except AvatarCleanupError:
        return False


def is_chat_profile_ref(image_ref: str) -> bool:
    try:
        return parse_gcs_uri(image_ref).bucket == os.environ.get(
            "CHAT_PROFILE_PHOTO_BUCKET", CHAT_PROFILE_PHOTO_BUCKET
        )
    except AvatarCleanupError:
        return False


def timestamp_ms(value: Any) -> Optional[int]:
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return int(parsed.timestamp() * 1000)
    if hasattr(value, "timestamp"):
        return int(value.timestamp() * 1000)
    if hasattr(value, "to_datetime"):
        return int(value.to_datetime().timestamp() * 1000)
    if hasattr(value, "toMillis"):
        return int(value.toMillis())
    return None


def select_expired_candidate_cleanup_actions(
    candidate_docs: Mapping[str, Mapping[str, Any]],
    *,
    now: datetime,
) -> List[CandidateCleanupAction]:
    now_ms = int(now.timestamp() * 1000)
    cleanup_statuses = {"rejected", "expired", "unselected", "failed"}
    actions: List[CandidateCleanupAction] = []
    for candidate_id, doc in candidate_docs.items():
        status = str(doc.get("status") or "")
        image_ref = str(doc.get("imageRef") or "")
        expires_at_ms = timestamp_ms(doc.get("expiresAt"))
        if not image_ref or not is_temp_candidate_ref(image_ref):
            continue
        should_delete = status in cleanup_statuses
        if status in {"preview_ready", "needs_review"} and expires_at_ms is not None and expires_at_ms <= now_ms:
            should_delete = True
        if should_delete:
            actions.append(
                CandidateCleanupAction(
                    candidate_id=str(doc.get("candidateId") or candidate_id),
                    image_ref=image_ref,
                    reason="expired_or_rejected_temp_candidate",
                )
            )
    return actions


def _doc_ref(client: Any, collection: str, doc_id: str) -> Any:
    col = client.collection(collection)
    if hasattr(col, "document"):
        return col.document(doc_id)
    return col.doc(doc_id)


def _doc_to_dict(snapshot: Any) -> Optional[Dict[str, Any]]:
    if not bool(getattr(snapshot, "exists", False)):
        return None
    if hasattr(snapshot, "to_dict"):
        data = snapshot.to_dict()
    elif hasattr(snapshot, "data"):
        data = snapshot.data()
    else:
        data = None
    return dict(data or {})


def _stream_collection(client: Any, collection: str) -> Iterable[Tuple[str, Dict[str, Any]]]:
    col = client.collection(collection)
    if hasattr(col, "stream"):
        for snap in col.stream():
            data = _doc_to_dict(snap)
            if data is not None:
                yield snap.id, data
        return
    if hasattr(client, "data"):
        for doc_id, data in client.data.get(collection, {}).items():
            yield doc_id, dict(data)


def _set_doc(ref: Any, payload: Dict[str, Any], *, merge: bool = True) -> None:
    ref.set(payload, merge=merge)


def _delete_doc(ref: Any) -> None:
    if hasattr(ref, "delete"):
        ref.delete()
    else:
        ref.set({}, merge=False)


def _redacted_cleanup_audit_id(uid: str, reason: str) -> str:
    digest = hashlib.sha256(f"{uid}:{reason}:{datetime.now(tz=timezone.utc).isoformat()}".encode("utf-8")).hexdigest()
    return f"audit_{digest[:24]}"


def _redacted_uid_hash(uid: str) -> str:
    return hashlib.sha256(uid.encode("utf-8")).hexdigest()[:16]


def _write_user_media_cleanup_audit(
    firestore_client: Any,
    *,
    uid: str,
    reason: str,
    summary: CleanupSummary,
) -> None:
    _set_doc(
        _doc_ref(firestore_client, "avatarMediaCleanupAudit", _redacted_cleanup_audit_id(uid, reason)),
        {
            "event": "user_media_cleanup_completed",
            "reason": reason,
            "uidHash": _redacted_uid_hash(uid),
            "dryRun": summary.dry_run,
            "sourcePhotosDeleted": summary.source_photos_deleted,
            "tempCandidatesDeleted": summary.temp_candidates_deleted,
            "approvedAvatarsDeleted": summary.approved_avatars_deleted,
            "clipEmbeddingsDeleted": summary.clip_embeddings_deleted,
            "usersUpdated": summary.users_updated,
            "jobsUpdated": summary.jobs_updated,
            "candidatesUpdated": summary.candidates_updated,
            "completedAt": SERVER_TIMESTAMP,
        },
        merge=False,
    )


def _blob_for(storage_client: Any, ref: GcsRef) -> Any:
    return storage_client.bucket(ref.bucket).blob(ref.path)


def _delete_blob(storage_client: Any, gcs_uri: str, *, dry_run: bool) -> bool:
    ref = parse_gcs_uri(gcs_uri)
    if dry_run:
        return False
    blob = _blob_for(storage_client, ref)
    try:
        blob.delete()
    except Exception as exc:
        if "not found" in str(exc).lower():
            return False
        raise
    return True


def cleanup_expired_avatar_candidates(
    *,
    firestore_client: Any,
    storage_client: Any,
    now: Optional[datetime] = None,
    dry_run: bool = True,
    max_delete_per_run: int = 500,
) -> CleanupSummary:
    now = now or datetime.now(tz=timezone.utc)
    docs = dict(_stream_collection(firestore_client, "avatarCandidates"))
    actions = select_expired_candidate_cleanup_actions(docs, now=now)[:max_delete_per_run]
    summary = CleanupSummary(dry_run=dry_run, temp_candidates_scanned=len(docs))
    summary.temp_candidates_planned_for_delete = len(actions)
    for action in actions:
        if not is_temp_candidate_ref(action.image_ref):
            summary.skipped.append(f"{action.candidate_id}: non-temp imageRef")
            continue
        deleted = _delete_blob(storage_client, action.image_ref, dry_run=dry_run)
        if deleted:
            summary.temp_candidates_deleted += 1
        if not dry_run:
            _set_doc(
                _doc_ref(firestore_client, "avatarCandidates", action.candidate_id),
                {
                    "status": "expired",
                    "cleanupReason": action.reason,
                    "imageDeletedAt": SERVER_TIMESTAMP,
                    "updatedAt": SERVER_TIMESTAMP,
                },
                merge=True,
            )
            summary.candidates_updated += 1
    return summary


def _load_doc(client: Any, collection: str, doc_id: str) -> Optional[Dict[str, Any]]:
    return _doc_to_dict(_doc_ref(client, collection, doc_id).get())


def _user_candidate_docs(client: Any, uid: str) -> Dict[str, Dict[str, Any]]:
    return {
        doc_id: doc
        for doc_id, doc in _stream_collection(client, "avatarCandidates")
        if str(doc.get("uid") or "") == uid
    }


def _user_job_docs(client: Any, uid: str) -> Dict[str, Dict[str, Any]]:
    return {
        doc_id: doc
        for doc_id, doc in _stream_collection(client, "avatarJobs")
        if str(doc.get("uid") or "") == uid
    }


def cleanup_user_media(
    *,
    uid: str,
    reason: str,
    firestore_client: Any,
    storage_client: Any,
    dry_run: bool = True,
) -> CleanupSummary:
    allowed_reasons = {"consent_withdrawal", "account_deletion", "admin_delete", "retention_policy"}
    if reason not in allowed_reasons:
        raise AvatarCleanupError(f"Unsupported cleanup reason: {reason}")

    summary = CleanupSummary(dry_run=dry_run)
    private_doc = _load_doc(firestore_client, "userPrivateMedia", uid) or {}
    source_photos = [
        entry
        for entry in private_doc.get("sourcePhotos", [])
        if isinstance(entry, Mapping) and str(entry.get("gcsUri") or "")
    ]

    for entry in source_photos:
        gcs_uri = str(entry.get("gcsUri"))
        if not is_private_source_ref(gcs_uri):
            summary.skipped.append(f"source:{entry.get('photoId', '')}: non-private-source ref")
            continue
        if _delete_blob(storage_client, gcs_uri, dry_run=dry_run):
            summary.source_photos_deleted += 1

    chat_real_photo = private_doc.get("chatRealPhoto")
    if isinstance(chat_real_photo, Mapping):
        chat_gcs_uri = str(chat_real_photo.get("gcsUri") or "")
        if chat_gcs_uri and is_chat_profile_ref(chat_gcs_uri):
            if _delete_blob(storage_client, chat_gcs_uri, dry_run=dry_run):
                summary.chat_profile_photos_deleted += 1

    candidate_docs = _user_candidate_docs(firestore_client, uid)
    summary.temp_candidates_planned_for_delete = len(
        [
            doc
            for doc in candidate_docs.values()
            if str(doc.get("imageRef") or "") and is_temp_candidate_ref(str(doc.get("imageRef") or ""))
        ]
    )
    for candidate_id, doc in candidate_docs.items():
        image_ref = str(doc.get("imageRef") or "")
        if image_ref and is_temp_candidate_ref(image_ref):
            if _delete_blob(storage_client, image_ref, dry_run=dry_run):
                summary.temp_candidates_deleted += 1
        if not dry_run:
            _set_doc(
                _doc_ref(firestore_client, "avatarCandidates", candidate_id),
                {
                    "status": "deleted",
                    "cleanupReason": reason,
                    "imageRef": "",
                    "previewUrl": "",
                    "approvedAvatarUrl": "",
                    "approvedAvatarStoragePath": "",
                    "qa": {},
                    "imageDeletedAt": SERVER_TIMESTAMP,
                    "updatedAt": SERVER_TIMESTAMP,
                },
                merge=True,
            )
            summary.candidates_updated += 1

    user_doc = _load_doc(firestore_client, "users", uid) or {}
    avatar = user_doc.get("avatar") if isinstance(user_doc.get("avatar"), Mapping) else {}
    approved_ref = str(avatar.get("approvedAvatarStoragePath") or "")
    if approved_ref and is_approved_avatar_ref(approved_ref):
        if _delete_blob(storage_client, approved_ref, dry_run=dry_run):
            summary.approved_avatars_deleted += 1

    if not dry_run:
        _set_doc(
            _doc_ref(firestore_client, "userPrivateMedia", uid),
            {
                "sourcePhotos": [
                    {
                        **dict(entry),
                        "gcsUri": "",
                        "storageBucket": "",
                        "storagePath": "",
                        "status": "deleted",
                        "deletedAt": SERVER_TIMESTAMP,
                        "updatedAt": SERVER_TIMESTAMP,
                    }
                    for entry in source_photos
                ],
                "photoConsent": {
                    **dict(private_doc.get("photoConsent") or {}),
                    "avatarGeneration": False,
                    "clipRecommendation": False,
                    "profileDisplayOriginalPhoto": False,
                    "chatPartnerRealPhotoDisclosure": False,
                    "sourcePhotoRetention": False,
                    "withdrawnAt": SERVER_TIMESTAMP,
                },
                "chatRealPhoto": {
                    "enabled": False,
                    "photoId": "",
                    "sourcePhotoId": "",
                    "storageBucket": "",
                    "storagePath": "",
                    "gcsUri": "",
                    "deletedAt": SERVER_TIMESTAMP,
                    "updatedAt": SERVER_TIMESTAMP,
                },
                "clip": {
                    **dict(private_doc.get("clip") or {}),
                    "embeddingStatus": "deleted",
                    "deletedAt": SERVER_TIMESTAMP,
                },
                "updatedAt": SERVER_TIMESTAMP,
            },
            merge=True,
        )
        _delete_doc(_doc_ref(firestore_client, "clipEmbeddings", uid))
        summary.clip_embeddings_deleted += 1

        user_update = {
            "profileImageMode": "avatar",
            "avatar": {
                "status": "none",
                "approvedAvatarUrl": "",
                "approvedAvatarStoragePath": "",
                "avatarId": "",
                "selectedCandidateId": "",
                "sourceJobId": "",
                "updatedAt": SERVER_TIMESTAMP,
            },
            "onboarding": {
                "avatarUrls": [],
                "photoUrls": [],
            },
            "profileImageUrl": "",
            "photoUrls": [],
            "updatedAt": SERVER_TIMESTAMP,
        }
        _set_doc(_doc_ref(firestore_client, "users", uid), user_update, merge=True)
        summary.users_updated += 1

        for job_id in _user_job_docs(firestore_client, uid):
            _set_doc(
                _doc_ref(firestore_client, "avatarJobs", job_id),
                {
                    "status": "cancelled",
                    "cleanupReason": reason,
                    "sourcePhotoRefs": [],
                    "sourcePhotoIds": [],
                    "selectedCandidateId": "",
                    "updatedAt": SERVER_TIMESTAMP,
                },
                merge=True,
            )
            summary.jobs_updated += 1

        _write_user_media_cleanup_audit(
            firestore_client,
            uid=uid,
            reason=reason,
            summary=summary,
        )

    return summary


def default_firestore_client(project: Optional[str] = None, database: Optional[str] = None) -> Any:
    if firestore is None:
        raise AvatarCleanupError("google-cloud-firestore is required.")
    kwargs: Dict[str, Any] = {}
    if project:
        kwargs["project"] = project
    if database:
        kwargs["database"] = database
    return firestore.Client(**kwargs)


def default_storage_client(project: Optional[str] = None) -> Any:
    if storage is None:
        raise AvatarCleanupError("google-cloud-storage is required.")
    return storage.Client(project=project)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Clean Seolleyeon avatar media.")
    parser.add_argument("--mode", choices=["expired_candidates", "user_media"], default="expired_candidates")
    parser.add_argument("--uid")
    parser.add_argument("--reason", default="consent_withdrawal")
    parser.add_argument("--apply", action="store_true", help="Mutate Firestore/GCS. Default is dry-run.")
    parser.add_argument("--firestore_project")
    parser.add_argument("--firestore_database")
    parser.add_argument("--max_delete_per_run", type=int, default=500)
    args = parser.parse_args(argv)

    fs = default_firestore_client(args.firestore_project, args.firestore_database)
    st = default_storage_client(args.firestore_project)
    if args.mode == "expired_candidates":
        summary = cleanup_expired_avatar_candidates(
            firestore_client=fs,
            storage_client=st,
            dry_run=not args.apply,
            max_delete_per_run=args.max_delete_per_run,
        )
    else:
        if not args.uid:
            raise AvatarCleanupError("--uid is required for user_media cleanup")
        summary = cleanup_user_media(
            uid=args.uid,
            reason=args.reason,
            firestore_client=fs,
            storage_client=st,
            dry_run=not args.apply,
        )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
