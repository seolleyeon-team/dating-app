from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    script_path = REPO_ROOT / "scripts" / "avatar_auth_secrets.py"
    spec = importlib.util.spec_from_file_location("avatar_auth_secrets", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_load_auth_secret_users_supports_mapping_schema(tmp_path):
    module = _load_module()
    secret = tmp_path / "mapping.json"
    secret.write_text(
        json.dumps(
            {
                "users": {
                    "MINI_001": {
                        "email": "first@example.test",
                        "password": "not-a-real-secret",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    users = module.load_auth_secret_users([secret], load_json=_load_json)

    assert users == [
        {
            "label": "MINI_001",
            "email": "first@example.test",
            "password": "not-a-real-secret",
        }
    ]


def test_load_auth_secret_users_supports_list_schema_and_preserves_label(tmp_path):
    module = _load_module()
    secret = tmp_path / "list.json"
    secret.write_text(
        json.dumps(
            {
                "users": [
                    {
                        "label": "MINI_010",
                        "email": "listed@example.test",
                        "password": "not-a-real-secret",
                    },
                    {
                        "email": "unlabeled@example.test",
                        "password": "not-a-real-secret",
                    },
                    "invalid-entry",
                ]
            }
        ),
        encoding="utf-8",
    )

    users = module.load_auth_secret_users([secret], load_json=_load_json)

    assert [user["label"] for user in users] == ["MINI_010", "2"]
    assert [user["email"] for user in users] == [
        "listed@example.test",
        "unlabeled@example.test",
    ]


def _load_validator_module():
    script_path = REPO_ROOT / "scripts" / "validate_canary_uid_photo_map.py"
    spec = importlib.util.spec_from_file_location(
        "validate_canary_uid_photo_map_exact_consent",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_validator_inputs(tmp_path: Path, *, consent_photo: str):
    photo = tmp_path / "photo.jpeg"
    photo.write_bytes(b"jpeg")
    mapping = tmp_path / "map.txt"
    mapping.write_text(f"uid-1={photo}\n", encoding="utf-8")
    consent = tmp_path / "consent.txt"
    consent.write_text(
        "seolleyeon-final staging avatar canary explicit consent "
        f"privacy monitoring not production\nuid-1={consent_photo}\n",
        encoding="utf-8",
    )
    preflight = tmp_path / "preflight.json"
    preflight.write_text(
        json.dumps(
            {
                "images": [
                    {
                        "normalizedFile": photo.name,
                        "recommendation": "PASS",
                        "faceCount": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return photo, mapping, consent, preflight


def _stub_validator_identity(module, monkeypatch):
    monkeypatch.setattr(
        module,
        "_auth_uid_lookup",
        lambda _key, _secrets: {"uid-1": "A"},
    )
    monkeypatch.setattr(
        module,
        "_user_state",
        lambda _project, _uid: {
            "exists": True,
            "approvedLock": False,
            "isStudentVerified": True,
            "studentEmailDomainOk": True,
        },
    )


def test_mapping_validator_requires_exact_consent_row(monkeypatch, tmp_path):
    module = _load_validator_module()
    _, mapping, consent, preflight = _write_validator_inputs(
        tmp_path,
        consent_photo="different.jpeg",
    )
    _stub_validator_identity(module, monkeypatch)

    report = module.build_report(
        project="seolleyeon-final",
        mapping_path=mapping,
        consent_file=consent,
        preflight_json=preflight,
        api_key="test",
        auth_secret_paths=[],
    )

    assert report["eligibleUploadRows"] == 0
    assert report["consentEvidence"]["valid"] is True
    exact = report["consentEvidence"]["exactUidPhotoConsent"]
    assert exact["satisfiedByThisFile"] is False
    assert report["rows"][0]["blockers"] == ["exact_uid_photo_consent_mismatch"]
    assert "uid-1" not in json.dumps(report)


def test_mapping_validator_accepts_exact_consent_row(monkeypatch, tmp_path):
    module = _load_validator_module()
    _, mapping, consent, preflight = _write_validator_inputs(
        tmp_path,
        consent_photo="photo.jpeg",
    )
    _stub_validator_identity(module, monkeypatch)

    report = module.build_report(
        project="seolleyeon-final",
        mapping_path=mapping,
        consent_file=consent,
        preflight_json=preflight,
        api_key="test",
        auth_secret_paths=[],
    )

    assert report["eligibleUploadRows"] == 1
    exact = report["consentEvidence"]["exactUidPhotoConsent"]
    assert exact["satisfiedByThisFile"] is True
    assert report["rows"][0]["blockers"] == []
    assert "uid-1" not in json.dumps(report)
