#!/usr/bin/env python3
"""Reset a staging user's avatar generation state without printing private refs."""

from __future__ import annotations

import argparse
import json
from typing import Any, Mapping


FORBIDDEN_PROJECTS = {"seolleyeon", "production", "prod"}


def _client(project: str):
    try:
        from google.cloud import firestore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("google-cloud-firestore is required") from exc
    return firestore.Client(project=project)


def _storage_client():
    try:
        from google.cloud import storage
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("google-cloud-storage is required for --delete_objects") from exc
    return storage.Client()


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_project(project: str) -> str:
    normalized = project.strip()
    if not normalized:
        raise ValueError("--project is required")
    if normalized in FORBIDDEN_PROJECTS or not normalized.endswith("-final"):
        raise ValueError("refusing to mutate non-staging project")
    return normalized


def _redacted_summary(**values: Any) -> dict[str, Any]:
    return dict(values)


def reset_avatar_state(
    *,
    project: str,
    uid: str,
    apply: bool,
    delete_objects: bool,
) -> dict[str, Any]:
    project = _safe_project(project)
    db = _client(project)
    user_ref = db.collection("users").document(uid)
    private_ref = db.collection("userPrivateMedia").document(uid)
    user_doc = user_ref.get().to_dict() or {}
    private_doc = private_ref.get().to_dict() or {}
    avatar = _as_mapping(user_doc.get("avatar"))
    onboarding = dict(_as_mapping(user_doc.get("onboarding")))
    source_photos = [
        dict(item)
        for item in _as_list(private_doc.get("sourcePhotos"))
        if isinstance(item, Mapping)
    ]
    current_job_id = str(private_doc.get("currentAvatarJobId") or avatar.get("sourceJobId") or "")

    job_query = db.collection("avatarJobs").where("uid", "==", uid).limit(200)
    jobs = {snap.id: (snap.to_dict() or {}) for snap in job_query.stream()}
    affected_jobs = [
        job_id
        for job_id, data in jobs.items()
        if str(data.get("status") or "") not in {"approved", "cancelled", "canceled", "superseded"}
    ]
    cancelled_sources = 0
    for entry in source_photos:
        if entry.get("avatarGenerationState") == "current":
            cancelled_sources += 1
        if entry.get("avatarGenerationState") in {"current", "superseded"}:
            entry["avatarGenerationState"] = "cancelled"
            entry["status"] = "cancelled" if entry.get("status") == "active" else entry.get("status")

    approved_storage_path = str(avatar.get("approvedAvatarStoragePath") or "")
    approved_bucket = str(avatar.get("approvedAvatarBucket") or "")
    deleted_objects = 0

    if apply:
        from google.cloud import firestore

        onboarding.pop("avatarUrls", None)
        onboarding.pop("photoUrls", None)
        user_ref.set(
            {
                "avatar": firestore.DELETE_FIELD,
                "onboarding": onboarding,
                "profileImageMode": "avatar",
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        private_ref.set(
            {
                "sourcePhotos": source_photos,
                "currentAvatarSourcePhotoId": firestore.DELETE_FIELD,
                "currentAvatarJobId": firestore.DELETE_FIELD,
                "avatarSourceSelectionVersion": firestore.DELETE_FIELD,
                "updatedAt": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )
        for job_id in affected_jobs:
            db.collection("avatarJobs").document(job_id).set(
                {
                    "status": "cancelled",
                    "errorCode": "staging_avatar_state_reset",
                    "updatedAt": firestore.SERVER_TIMESTAMP,
                },
                merge=True,
            )
        if delete_objects and approved_bucket and approved_storage_path:
            bucket = _storage_client().bucket(approved_bucket)
            bucket.blob(approved_storage_path).delete()
            deleted_objects += 1

    return _redacted_summary(
        project=project,
        uidHash=__import__("hashlib").sha256(uid.encode("utf-8")).hexdigest()[:12],
        dryRun=not apply,
        currentJobPresent=bool(current_job_id),
        avatarWasPresent=bool(avatar),
        sourcePhotosScanned=len(source_photos),
        sourcesCancelled=cancelled_sources,
        avatarJobsScanned=len(jobs),
        avatarJobsToCancel=len(affected_jobs),
        deleteObjectsRequested=delete_objects,
        approvedAvatarObjectDeleted=deleted_objects,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--uid", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--delete_objects", action="store_true")
    args = parser.parse_args(argv)
    report = reset_avatar_state(
        project=args.project,
        uid=args.uid,
        apply=args.apply,
        delete_objects=args.delete_objects,
    )
    json.dump(report, fp=__import__("sys").stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
