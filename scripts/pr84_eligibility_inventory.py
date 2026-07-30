from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


DEFAULT_AUTH_SECRET_PATHS = (
    Path(".local_secrets/staging_test_users.json"),
    Path(".local_secrets/staging_test_users_de.json"),
    Path(".local_secrets/staging_pr84_canary_users.json"),
)


def _hash_text(value: Any, *, length: int = 12) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _api_key_from_google_services(path: Path) -> str:
    payload = _load_json(path)
    clients = payload.get("client")
    if not isinstance(clients, list):
        return ""
    for client in clients:
        if not isinstance(client, Mapping):
            continue
        api_keys = client.get("api_key")
        if not isinstance(api_keys, list):
            continue
        for api_key in api_keys:
            if isinstance(api_key, Mapping) and api_key.get("current_key"):
                return str(api_key["current_key"])
    return ""


def _load_auth_secrets(paths: list[Path]) -> list[Mapping[str, Any]]:
    users: list[Mapping[str, Any]] = []
    for path in paths:
        payload = _load_json(path)
        for label, entry in (payload.get("users") or {}).items():
            if isinstance(entry, Mapping):
                item = dict(entry)
                item["label"] = str(label)
                users.append(item)
    return users


def _post_json(url: str, payload: Mapping[str, Any]) -> tuple[int, Mapping[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            parsed = json.loads(response.read().decode("utf-8"))
            return int(response.status), parsed if isinstance(parsed, Mapping) else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"error": {"message": text[:160]}}
        return int(exc.code), parsed if isinstance(parsed, Mapping) else {}


def _auth_uid_records(api_key: str, secrets: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not api_key:
        return [
            {
                "labelHash": f"label:{_hash_text(item.get('label'))}",
                "localAuthUidHash": "",
                "authOk": False,
                "authError": "missing_api_key",
            }
            for item in secrets
        ]
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    records: list[dict[str, Any]] = []
    for item in secrets:
        email = str(item.get("email") or "")
        password = str(item.get("password") or "")
        label = str(item.get("label") or "")
        record = {
            "labelHash": f"label:{_hash_text(label)}",
            "localAuthUidHash": "",
            "authOk": False,
            "authError": "",
        }
        if not email or not password:
            record["authError"] = "missing_email_or_password"
            records.append(record)
            continue
        status, parsed = _post_json(
            url,
            {"email": email, "password": password, "returnSecureToken": True},
        )
        if status == 200 and parsed.get("localId"):
            record["authOk"] = True
            record["localAuthUid"] = str(parsed["localId"])
            record["localAuthUidHash"] = f"uid:{_hash_text(parsed['localId'])}"
        else:
            error = parsed.get("error") if isinstance(parsed.get("error"), Mapping) else {}
            record["authError"] = str(error.get("message") or f"http_{status}")[:80]
        records.append(record)
    return records


def _firestore_client(project: str):
    try:
        from google.cloud import firestore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("google-cloud-firestore is required") from exc
    return firestore.Client(project=project)


def _user_state(client: Any, uid: str) -> dict[str, Any]:
    data = client.collection("users").document(uid).get().to_dict() or {}
    avatar = data.get("avatar") if isinstance(data.get("avatar"), Mapping) else {}
    return {
        "exists": bool(data),
        "approvedLock": str(avatar.get("status") or "") == "approved"
        and bool(avatar.get("approvedAvatarUrl")),
        "isStudentVerified": bool(data.get("isStudentVerified")),
        "studentEmailDomainOk": str(data.get("studentEmail") or "").endswith("@yonsei.ac.kr"),
    }


def _auth_user_blockers(state: Mapping[str, Any], auth_ok: bool) -> list[str]:
    blockers: list[str] = []
    if not auth_ok:
        blockers.append("auth_sign_in_failed")
    if not state.get("exists"):
        blockers.append("user_doc_missing")
    if state.get("approvedLock"):
        blockers.append("approved_avatar_lock")
    if not state.get("isStudentVerified"):
        blockers.append("student_not_verified")
    if not state.get("studentEmailDomainOk"):
        blockers.append("student_email_not_yonsei")
    return blockers


def _pass_fixture_files(preflight: Mapping[str, Any]) -> list[str]:
    files: list[str] = []
    for item in preflight.get("images", []):
        if isinstance(item, Mapping) and item.get("recommendation") == "PASS":
            filename = str(item.get("normalizedFile") or "").strip()
            if filename:
                files.append(filename)
    return sorted(files)


def _mapped_files(validation: Mapping[str, Any]) -> set[str]:
    mapped: set[str] = set()
    for row in validation.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        filename = str(row.get("photoFile") or "").strip()
        if filename:
            mapped.add(filename)
    return mapped


def build_inventory(
    *,
    project: str,
    preflight: Mapping[str, Any],
    validation: Mapping[str, Any],
    api_key: str,
    auth_secrets: list[Mapping[str, Any]],
    firestore_client: Any | None = None,
) -> dict[str, Any]:
    pass_files = _pass_fixture_files(preflight)
    mapped = _mapped_files(validation)
    auth_records = _auth_uid_records(api_key, auth_secrets)
    client = firestore_client or _firestore_client(project)
    auth_users: list[dict[str, Any]] = []
    for record in auth_records:
        uid = str(record.pop("localAuthUid", "") or "")
        state = _user_state(client, uid) if uid else {
            "exists": False,
            "approvedLock": False,
            "isStudentVerified": False,
            "studentEmailDomainOk": False,
        }
        blockers = _auth_user_blockers(state, bool(record.get("authOk")))
        auth_users.append(
            {
                **record,
                "userDocExists": state["exists"],
                "approvedLock": state["approvedLock"],
                "isStudentVerified": state["isStudentVerified"],
                "studentEmailDomainOk": state["studentEmailDomainOk"],
                "eligibleForNewCanary": not blockers,
                "blockers": blockers,
            }
        )
    eligible_auth_count = sum(1 for user in auth_users if user["eligibleForNewCanary"])
    unmapped_pass = sorted(filename for filename in pass_files if filename not in mapped)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "passFixtureCount": len(pass_files),
        "mappedPassFixtureCount": len([filename for filename in pass_files if filename in mapped]),
        "unmappedPassFixtureCount": len(unmapped_pass),
        "unmappedPassFixtures": unmapped_pass,
        "eligibleAuthUserCount": eligible_auth_count,
        "eligiblePairUpperBound": min(len(pass_files), eligible_auth_count),
        "neededForThreeUserRerun": max(0, 3 - min(len(pass_files), eligible_auth_count)),
        "authUsers": auth_users,
        "notes": [
            "This report is redacted: it contains hashed labels and UID hashes only.",
            "A PASS fixture still requires explicit consent and a matching eligible staging UID before upload.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a redacted PR8.4 canary eligibility inventory.")
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--preflight_json", default="out/canary_preflight_report_mediapipe.json")
    parser.add_argument("--validation_json", default="out/canary_mapping_validation_mediapipe.json")
    parser.add_argument("--google_services_json", default="android/app/google-services.json")
    parser.add_argument("--api_key", default="")
    parser.add_argument("--auth_secret_json", action="append", default=[])
    parser.add_argument("--output_json", default="out/pr84_eligibility_inventory.json")
    args = parser.parse_args(argv)

    auth_paths = [Path(path) for path in args.auth_secret_json] or list(DEFAULT_AUTH_SECRET_PATHS)
    report = build_inventory(
        project=args.project,
        preflight=_load_json(Path(args.preflight_json)),
        validation=_load_json(Path(args.validation_json)),
        api_key=args.api_key or _api_key_from_google_services(Path(args.google_services_json)),
        auth_secrets=_load_auth_secrets(auth_paths),
    )
    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path.resolve()),
                "passFixtureCount": report["passFixtureCount"],
                "eligibleAuthUserCount": report["eligibleAuthUserCount"],
                "eligiblePairUpperBound": report["eligiblePairUpperBound"],
                "neededForThreeUserRerun": report["neededForThreeUserRerun"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
