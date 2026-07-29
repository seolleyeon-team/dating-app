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

def _load_runner_module():
    script_path = REPO_ROOT / "scripts" / "run_canary_from_validated_map.py"
    spec = importlib.util.spec_from_file_location(
        "run_canary_from_validated_map_app_check",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_canary_runner_loads_app_check_token_without_exposing_file_shape(tmp_path):
    module = _load_runner_module()
    plain = tmp_path / "plain.txt"
    plain.write_text("plain-token\n", encoding="utf-8")
    structured = tmp_path / "structured.json"
    structured.write_text(
        json.dumps({"appCheckToken": "structured-token"}),
        encoding="utf-8",
    )

    assert module._load_app_check_token(plain) == "plain-token"
    assert module._load_app_check_token(structured) == "structured-token"
    assert module._load_app_check_token(tmp_path / "missing.txt") == ""


def test_canary_runner_apply_without_app_check_token_is_no_upload(tmp_path):
    module = _load_runner_module()
    photo = tmp_path / "photo.jpeg"
    photo.write_bytes(b"jpeg")
    mapping = tmp_path / "map.txt"
    mapping.write_text(f"uid-1={photo}\n", encoding="utf-8")
    validation = tmp_path / "validation.json"
    validation.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "photoFile": photo.name,
                        "eligibleForUpload": True,
                        "blockers": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "runner.json"

    result = module.main(
        [
            "--mapping_file",
            str(mapping),
            "--validation_json",
            str(validation),
            "--output_json",
            str(output),
            "--min_users",
            "1",
            "--apply",
        ]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert result == 1
    assert report["status"] == "BLOCKED_MISSING_APPCHECK_TOKEN_NO_UPLOAD"
    assert report["appCheckTokenConfigured"] is False
    assert "jobs" not in report

def test_canary_runner_exchanges_registered_debug_token_without_url_leak(monkeypatch):
    module = _load_runner_module()
    captured = {}

    def fake_post(url, payload, **kwargs):
        captured["url"] = url
        captured["payload"] = payload
        captured["kwargs"] = kwargs
        return 200, {"token": "minted-app-check-token", "ttl": "3600s"}, "{}"

    monkeypatch.setattr(module, "_post_json", fake_post)

    status, token = module._exchange_app_check_debug_token(
        project_number="123456789",
        app_id="1:123456789:android:test",
        api_key="test-api-key",
        debug_token="00000000-0000-4000-8000-000000000000",
    )

    assert status == 200
    assert token == "minted-app-check-token"
    assert "00000000-0000-4000-8000-000000000000" not in captured["url"]
    assert captured["payload"] == {
        "debugToken": "00000000-0000-4000-8000-000000000000",
        "limitedUse": False,
    }
    assert captured["kwargs"]["timeout_seconds"] == 60

def _write_exact_replay_inputs(tmp_path: Path, *, count: int = 10):
    import hashlib

    mapping = tmp_path / "map.txt"
    consent = tmp_path / "consent.txt"
    validation = tmp_path / "validation.json"
    prior = tmp_path / "prior.json"
    mapping_lines = []
    validation_rows = []
    prior_jobs = []
    for index in range(count):
        uid = f"uid-{index}"
        photo = tmp_path / f"photo-{index}.jpeg"
        photo.write_bytes(f"jpeg-{index}".encode())
        mapping_lines.append(f"{uid}={photo}")
        uid_hash = "uid:" + hashlib.sha256(uid.encode()).hexdigest()[:12]
        is_eligible = index < 7
        validation_rows.append(
            {
                "uidHash": uid_hash,
                "photoFile": photo.name,
                "eligibleForUpload": is_eligible,
                "preflightRecommendation": "PASS" if is_eligible else "BLOCK",
                "blockers": [] if is_eligible else ["blocked_fixture"],
            }
        )
        if is_eligible:
            prior_jobs.append(
                {
                    "uidHash": uid_hash,
                    "photoFile": photo.name,
                    "imageSha256Prefix": hashlib.sha256(photo.read_bytes()).hexdigest()[:12],
                }
            )
    assignment_text = "\n".join(mapping_lines) + "\n"
    mapping.write_text(assignment_text, encoding="utf-8")
    consent.write_text(assignment_text, encoding="utf-8")
    validation.write_text(json.dumps({"rows": validation_rows}), encoding="utf-8")
    prior.write_text(json.dumps({"jobs": prior_jobs}), encoding="utf-8")
    return mapping, consent, validation, prior


def test_operator_exact_replay_selects_canary_then_remaining_six(tmp_path):
    module = _load_runner_module()
    mapping, consent, validation, prior = _write_exact_replay_inputs(tmp_path)
    mapping_sha = module._sha256_file(mapping)

    canary, full_count = module._operator_exact_replay_rows(
        mapping_file=mapping,
        consent_file=consent,
        validation_json=validation,
        prior_report_json=prior,
        expected_mapping_sha256=mapping_sha,
        row_start=0,
        row_limit=1,
    )
    remaining, remaining_full_count = module._operator_exact_replay_rows(
        mapping_file=mapping,
        consent_file=consent,
        validation_json=validation,
        prior_report_json=prior,
        expected_mapping_sha256=mapping_sha,
        row_start=1,
        row_limit=6,
    )

    assert full_count == remaining_full_count == 7
    assert [row["rowIndex"] for row in canary] == [1]
    assert [row["rowIndex"] for row in remaining] == [2, 3, 4, 5, 6, 7]


def test_operator_exact_replay_rejects_wrong_mapping_digest(tmp_path):
    module = _load_runner_module()
    mapping, consent, validation, prior = _write_exact_replay_inputs(tmp_path)

    try:
        module._operator_exact_replay_rows(
            mapping_file=mapping,
            consent_file=consent,
            validation_json=validation,
            prior_report_json=prior,
            expected_mapping_sha256="0" * 64,
            row_start=0,
            row_limit=1,
        )
    except ValueError as exc:
        assert str(exc) == "operator_exact_replay_mapping_digest_mismatch"
    else:
        raise AssertionError("wrong mapping digest must be rejected")


def test_operator_replay_request_id_is_new_and_deterministic():
    module = _load_runner_module()
    legacy = module._safe_client_request_id("uid-1", "photo.jpeg")
    first = module._operator_replay_client_request_id(
        "uid-1",
        "photo.jpeg",
        mapping_sha256="a" * 64,
        replay_id="recovery-20260729",
    )
    second = module._operator_replay_client_request_id(
        "uid-1",
        "photo.jpeg",
        mapping_sha256="a" * 64,
        replay_id="recovery-20260729",
    )

    assert first == second
    assert first != legacy
    assert first.startswith("operator_replay_")
def test_operator_exact_replay_main_dry_run_is_sanitized(tmp_path):
    module = _load_runner_module()
    mapping, consent, validation, prior = _write_exact_replay_inputs(tmp_path)
    output = tmp_path / "operator-dry-run.json"

    result = module.main(
        [
            "--mapping_file", str(mapping),
            "--consent_file", str(consent),
            "--validation_json", str(validation),
            "--prior_report_json", str(prior),
            "--output_json", str(output),
            "--expected_mapping_sha256", module._sha256_file(mapping),
            "--operator_replay_id", "recovery-20260729",
            "--operator_authorized_exact_replay",
            "--skip_approval",
            "--row_start", "0",
            "--row_limit", "1",
            "--min_users", "1",
        ]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    serialized = json.dumps(report)
    assert result == 0
    assert report["status"] == "READY"
    assert report["eligibleCount"] == 1
    assert report["fullEligibleCount"] == 7
    assert report["operatorAuthorizedExactReplay"] is True
    assert report["approvalSkipped"] is True
    assert report["eligible"] == [{"rowIndex": 1}]
    assert "rowLineage" not in serialized
    assert "uid-" not in serialized
    assert "photo-" not in serialized


def test_operator_exact_replay_main_wrong_digest_blocks_before_upload(tmp_path):
    module = _load_runner_module()
    mapping, consent, validation, prior = _write_exact_replay_inputs(tmp_path)
    output = tmp_path / "operator-blocked.json"

    result = module.main(
        [
            "--mapping_file", str(mapping),
            "--consent_file", str(consent),
            "--validation_json", str(validation),
            "--prior_report_json", str(prior),
            "--output_json", str(output),
            "--expected_mapping_sha256", "0" * 64,
            "--operator_replay_id", "recovery-20260729",
            "--operator_authorized_exact_replay",
            "--skip_approval",
            "--row_start", "0",
            "--row_limit", "1",
            "--min_users", "1",
            "--apply",
        ]
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert result == 1
    assert report["status"] == "BLOCKED_OPERATOR_EXACT_REPLAY_NO_UPLOAD"
    assert report["blockers"] == ["operator_exact_replay_mapping_digest_mismatch"]
    assert "jobs" not in report