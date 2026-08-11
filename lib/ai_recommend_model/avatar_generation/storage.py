from __future__ import annotations

import os

PRIVATE_SOURCE_BUCKET = "seolleyeon-final-private-" "source-photos"
AVATAR_TEMP_BUCKET = "seolleyeon-final-avatar-temp"
APPROVED_AVATAR_BUCKET = "seolleyeon-final-approved-" "avatars"


def _bucket_from_env(name: str, fallback: str) -> str:
    return os.environ.get(name, "").strip() or fallback


def build_temp_candidate_path(*, uid: str, job_id: str, candidate_id: str) -> str:
    return f"users/{uid}/jobs/{job_id}/candidates/{candidate_id}.png"


def build_temp_candidate_ref(*, uid: str, job_id: str, candidate_id: str) -> str:
    bucket = _bucket_from_env("AVATAR_TEMP_BUCKET", AVATAR_TEMP_BUCKET)
    return f"gs://{bucket}/{build_temp_candidate_path(uid=uid, job_id=job_id, candidate_id=candidate_id)}"


def build_approved_avatar_path(*, uid: str, avatar_id: str) -> str:
    return f"users/{uid}/avatar/{avatar_id}.png"


def build_approved_avatar_ref(*, uid: str, avatar_id: str) -> str:
    bucket = _bucket_from_env("APPROVED_AVATAR_BUCKET", APPROVED_AVATAR_BUCKET)
    return f"gs://{bucket}/{build_approved_avatar_path(uid=uid, avatar_id=avatar_id)}"
