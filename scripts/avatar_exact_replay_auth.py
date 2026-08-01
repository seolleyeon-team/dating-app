from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

STAGING_PROJECT = "seolleyeon-final"
ACTIVE_JOB_STATUSES = frozenset(
    {
        "queued",
        "running",
        "qa_pending",
        "preview_ready",
        "needs_review",
        "no_previewable",
        "no_previewable_candidates",
        "retryable_failed",
        "pending",
        "generating",
    }
)
BLOCKED_ACCOUNT_STATUSES = frozenset({"deleted", "suspended", "disabled"})


def initialize_exact_replay_admin(project: str):
    if project != STAGING_PROJECT:
        raise ValueError("operator_custom_token_project_mismatch")
    try:
        import firebase_admin
        from firebase_admin import auth, credentials
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("firebase_admin_required") from exc
    app_name = "exact-seven-staging-replay"
    app = (
        firebase_admin.get_app(app_name)
        if app_name in firebase_admin._apps
        else firebase_admin.initialize_app(
            credentials.ApplicationDefault(),
            {
                "projectId": STAGING_PROJECT,
                "serviceAccountId": f"{STAGING_PROJECT}@appspot.gserviceaccount.com",
            },
            name=app_name,
        )
    )
    return auth, app


def _record(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _photo_consent(private_data: Mapping[str, Any]) -> Mapping[str, Any]:
    consent = _record(private_data.get("photoConsent"))
    purposes = _record(consent.get("purposes"))
    return purposes if purposes else consent


def _query_uid_jobs(db: Any, uid: str):
    collection = db.collection("avatarJobs")
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter

        return collection.where(filter=FieldFilter("uid", "==", uid)).stream()
    except (ImportError, TypeError):  # pragma: no cover - older SDK or test fake
        return collection.where("uid", "==", uid).stream()


def validate_exact_replay_preupload(
    *,
    project: str,
    db: Any,
    auth_mod: Any,
    admin_app: Any,
    row: Mapping[str, Any],
) -> dict[str, Any]:
    if project != STAGING_PROJECT:
        raise ValueError("operator_custom_token_project_mismatch")
    uid = str(row.get("uid") or "")
    photo_path = Path(str(row.get("photoPath") or ""))
    expected_digest = str(row.get("expectedPhotoSha256") or "")
    if not uid:
        raise ValueError("operator_custom_token_uid_missing")
    try:
        auth_user = auth_mod.get_user(uid, app=admin_app)
    except Exception as exc:
        raise ValueError("operator_custom_token_auth_user_missing") from exc
    if str(getattr(auth_user, "uid", "")) != uid:
        raise ValueError("operator_custom_token_auth_uid_mismatch")
    if bool(getattr(auth_user, "disabled", False)):
        raise ValueError("operator_custom_token_auth_user_disabled")
    if not photo_path.is_file() or len(expected_digest) != 64:
        raise ValueError("operator_custom_token_photo_digest_missing")
    if hashlib.sha256(photo_path.read_bytes()).hexdigest() != expected_digest:
        raise ValueError("operator_custom_token_photo_digest_mismatch")
    if row.get("sourceQualityPass") is not True:
        raise ValueError("operator_custom_token_source_quality_not_passed")

    user_snapshot = db.collection("users").document(uid).get()
    if not bool(getattr(user_snapshot, "exists", False)):
        raise ValueError("operator_custom_token_user_doc_missing")
    user_data = user_snapshot.to_dict() or {}
    account_status = str(
        user_data.get("accountStatus") or user_data.get("status") or ""
    ).strip().lower()
    if (
        user_data.get("disabled") is True
        or user_data.get("deleted") is True
        or user_data.get("suspended") is True
        or account_status in BLOCKED_ACCOUNT_STATUSES
    ):
        raise ValueError("operator_custom_token_account_blocked")
    avatar = _record(user_data.get("avatar"))
    if (
        str(avatar.get("status") or "").strip().lower() == "approved"
        or bool(avatar.get("approvedAvatarUrl"))
    ):
        raise ValueError("operator_custom_token_approved_avatar")

    private_snapshot = db.collection("userPrivateMedia").document(uid).get()
    private_data = private_snapshot.to_dict() or {}
    consent_container = _record(private_data.get("photoConsent"))
    consent = _photo_consent(private_data)
    if (
        consent_container.get("withdrawnAt") is not None
        or consent.get("withdrawnAt") is not None
        or consent.get("avatarGeneration") is False
    ):
        raise ValueError("operator_custom_token_consent_withdrawn")

    active_jobs = 0
    for snapshot in _query_uid_jobs(db, uid):
        job = snapshot.to_dict() or {}
        if str(job.get("status") or "").strip().lower() in ACTIVE_JOB_STATUSES:
            active_jobs += 1
    if active_jobs:
        raise ValueError("operator_custom_token_active_job")
    return {
        "authUserExists": True,
        "authUidMatched": True,
        "photoDigestMatched": True,
        "sourceQualityPassed": True,
        "consentNotWithdrawn": True,
        "accountEligible": True,
        "approvedAvatarAbsent": True,
        "activeJobCount": 0,
    }


def mint_exact_replay_id_token(
    *,
    project: str,
    uid: str,
    api_key: str,
    auth_mod: Any,
    admin_app: Any,
    post_json: Callable[..., tuple[int, Mapping[str, Any], str]],
) -> str:
    if project != STAGING_PROJECT:
        raise ValueError("operator_custom_token_project_mismatch")
    if not uid or not api_key:
        raise ValueError("operator_custom_token_exchange_config_missing")
    try:
        custom_token_value = auth_mod.create_custom_token(uid, app=admin_app)
    except Exception as exc:
        raise ValueError("operator_custom_token_signing_failed") from exc
    custom_token = (
        custom_token_value.decode("utf-8")
        if isinstance(custom_token_value, bytes)
        else str(custom_token_value)
    )
    try:
        status, payload, _ = post_json(
            f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={api_key}",
            {"token": custom_token, "returnSecureToken": True},
            timeout_seconds=60,
        )
        id_token = str(payload.get("idToken") or "")
        if status != 200 or not id_token:
            raise ValueError("operator_custom_token_exchange_failed")
        response_uid = str(payload.get("localId") or "")
        if response_uid and response_uid != uid:
            raise ValueError("operator_custom_token_exchange_uid_mismatch")
        decoded = auth_mod.verify_id_token(
            id_token,
            app=admin_app,
            check_revoked=True,
        )
        decoded_uid = str(decoded.get("uid") or decoded.get("sub") or "")
        if decoded_uid != uid:
            raise ValueError("operator_custom_token_decoded_uid_mismatch")
        return id_token
    finally:
        custom_token = ""
        custom_token_value = b""