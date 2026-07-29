from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    path = REPO_ROOT / "scripts" / "avatar_exact_replay_auth.py"
    spec = importlib.util.spec_from_file_location("avatar_exact_replay_auth_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data or {}
        self.exists = exists

    def to_dict(self):
        return dict(self._data)


class _Document:
    def __init__(self, snapshot):
        self._snapshot = snapshot

    def get(self):
        return self._snapshot


class _Collection:
    def __init__(self, *, document_snapshot=None, stream_snapshots=None):
        self._document_snapshot = document_snapshot or _Snapshot({}, exists=False)
        self._stream_snapshots = stream_snapshots or []

    def document(self, _uid):
        return _Document(self._document_snapshot)

    def where(self, *args, **kwargs):
        return self

    def stream(self):
        return list(self._stream_snapshots)


class _Db:
    def __init__(self, *, user=None, private=None, jobs=None):
        self._collections = {
            "users": _Collection(document_snapshot=_Snapshot(user or {})),
            "userPrivateMedia": _Collection(document_snapshot=_Snapshot(private or {})),
            "avatarJobs": _Collection(
                stream_snapshots=[_Snapshot(job) for job in (jobs or [])]
            ),
        }

    def collection(self, name):
        return self._collections[name]


class _Auth:
    def __init__(self, uid="uid-1", *, disabled=False, decoded_uid=None):
        self.uid = uid
        self.disabled = disabled
        self.decoded_uid = decoded_uid if decoded_uid is not None else uid
        self.created_custom_token = None
        self.verified_id_token = None

    def get_user(self, uid, *, app):
        assert app == "admin-app"
        assert uid == self.uid
        return SimpleNamespace(uid=self.uid, disabled=self.disabled)

    def create_custom_token(self, uid, *, app):
        assert app == "admin-app"
        assert uid == self.uid
        self.created_custom_token = b"custom-secret"
        return self.created_custom_token

    def verify_id_token(self, token, *, app, check_revoked):
        assert app == "admin-app"
        assert check_revoked is True
        self.verified_id_token = token
        return {"uid": self.decoded_uid}


def _valid_row(photo: Path):
    return {
        "uid": "uid-1",
        "photoPath": str(photo),
        "expectedPhotoSha256": hashlib.sha256(photo.read_bytes()).hexdigest(),
        "sourceQualityPass": True,
    }


def _valid_db():
    return _Db(
        user={"accountStatus": "active", "avatar": {"status": "not_started"}},
        private={"photoConsent": {"purposes": {"avatarGeneration": True}}},
        jobs=[{"status": "terminal_failed"}],
    )


def test_preupload_gate_accepts_exact_staging_target(tmp_path):
    module = _load_module()
    photo = tmp_path / "source.jpg"
    photo.write_bytes(b"exact-photo")

    result = module.validate_exact_replay_preupload(
        project="seolleyeon-final",
        db=_valid_db(),
        auth_mod=_Auth(),
        admin_app="admin-app",
        row=_valid_row(photo),
    )

    assert result == {
        "authUserExists": True,
        "authUidMatched": True,
        "photoDigestMatched": True,
        "sourceQualityPassed": True,
        "consentNotWithdrawn": True,
        "accountEligible": True,
        "approvedAvatarAbsent": True,
        "activeJobCount": 0,
    }


@pytest.mark.parametrize(
    ("auth", "db", "row_change", "error_code"),
    [
        (_Auth(disabled=True), _valid_db(), {}, "operator_custom_token_auth_user_disabled"),
        (_Auth(), _Db(user={"suspended": True}), {}, "operator_custom_token_account_blocked"),
        (
            _Auth(),
            _Db(user={"avatar": {"status": "approved"}}),
            {},
            "operator_custom_token_approved_avatar",
        ),
        (
            _Auth(),
            _Db(private={"photoConsent": {"withdrawnAt": "now"}}),
            {},
            "operator_custom_token_consent_withdrawn",
        ),
        (
            _Auth(),
            _Db(jobs=[{"status": "running"}]),
            {},
            "operator_custom_token_active_job",
        ),
        (_Auth(), _valid_db(), {"expectedPhotoSha256": "0" * 64}, "operator_custom_token_photo_digest_mismatch"),
        (_Auth(), _valid_db(), {"sourceQualityPass": False}, "operator_custom_token_source_quality_not_passed"),
    ],
)
def test_preupload_gate_rejects_each_blocker(tmp_path, auth, db, row_change, error_code):
    module = _load_module()
    photo = tmp_path / "source.jpg"
    photo.write_bytes(b"exact-photo")
    row = _valid_row(photo)
    row.update(row_change)

    with pytest.raises(ValueError, match=f"^{error_code}$"):
        module.validate_exact_replay_preupload(
            project="seolleyeon-final",
            db=db,
            auth_mod=auth,
            admin_app="admin-app",
            row=row,
        )


def test_custom_token_is_exchanged_and_only_verified_id_token_is_returned():
    module = _load_module()
    auth = _Auth()
    captured = {}

    def post_json(url, payload, **kwargs):
        captured["url"] = url
        captured["payload"] = payload
        captured["kwargs"] = kwargs
        return 200, {
            "idToken": "firebase-id-token",
            "refreshToken": "must-not-be-returned",
            "localId": "uid-1",
        }, "raw-response-must-not-be-returned"

    result = module.mint_exact_replay_id_token(
        project="seolleyeon-final",
        uid="uid-1",
        api_key="api-key",
        auth_mod=auth,
        admin_app="admin-app",
        post_json=post_json,
    )

    assert result == "firebase-id-token"
    assert result != "custom-secret"
    assert captured["payload"] == {
        "token": "custom-secret",
        "returnSecureToken": True,
    }
    assert "signInWithCustomToken" in captured["url"]
    assert captured["kwargs"]["timeout_seconds"] == 60
    assert auth.verified_id_token == "firebase-id-token"


def test_custom_token_exchange_rejects_decoded_uid_mismatch():
    module = _load_module()
    auth = _Auth(decoded_uid="other-uid")

    with pytest.raises(ValueError, match="^operator_custom_token_decoded_uid_mismatch$"):
        module.mint_exact_replay_id_token(
            project="seolleyeon-final",
            uid="uid-1",
            api_key="api-key",
            auth_mod=auth,
            admin_app="admin-app",
            post_json=lambda *args, **kwargs: (
                200,
                {"idToken": "firebase-id-token", "localId": "uid-1"},
                "",
            ),
        )


def test_custom_token_scope_rejects_non_staging_project():
    module = _load_module()

    with pytest.raises(ValueError, match="^operator_custom_token_project_mismatch$"):
        module.mint_exact_replay_id_token(
            project="seolleyeon",
            uid="uid-1",
            api_key="api-key",
            auth_mod=_Auth(),
            admin_app="admin-app",
            post_json=lambda *args, **kwargs: (500, {}, ""),
        )