from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

try:
    from pr84_consent_evidence import evaluate_consent_file
except ModuleNotFoundError:  # pragma: no cover - importlib test path support
    import importlib.util

    _CONSENT_SPEC = importlib.util.spec_from_file_location(
        "pr84_consent_evidence",
        Path(__file__).with_name("pr84_consent_evidence.py"),
    )
    if _CONSENT_SPEC is None or _CONSENT_SPEC.loader is None:
        raise
    _CONSENT_MODULE = importlib.util.module_from_spec(_CONSENT_SPEC)
    _CONSENT_SPEC.loader.exec_module(_CONSENT_MODULE)
    evaluate_consent_file = _CONSENT_MODULE.evaluate_consent_file

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
    return json.loads(path.read_text(encoding="utf-8"))


def _api_key_from_google_services(path: Path) -> str:
    if not path.is_file():
        return ""
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


def _load_preflight(preflight_json: Path) -> dict[str, Mapping[str, Any]]:
    report = _load_json(preflight_json)
    return {
        str(item.get("normalizedFile") or ""): item
        for item in report.get("images", [])
        if isinstance(item, Mapping)
    }


def _load_mapping(path: Path) -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        uid, photo_path = line.split("=", 1)
        rows.append((uid.strip().strip("<>"), Path(photo_path.strip())))
    return rows


def _load_auth_secrets(paths: list[Path]) -> list[Mapping[str, Any]]:
    users: list[Mapping[str, Any]] = []
    for path in paths:
        if not path.is_file():
            continue
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


def _auth_uid_lookup(api_key: str, secrets: list[Mapping[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    if not api_key:
        return lookup
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={api_key}"
    for item in secrets:
        email = str(item.get("email") or "")
        password = str(item.get("password") or "")
        if not email or not password:
            continue
        status, parsed = _post_json(
            url,
            {"email": email, "password": password, "returnSecureToken": True},
        )
        if status == 200 and parsed.get("localId"):
            lookup[str(parsed["localId"])] = str(item.get("label") or "")
    return lookup


def _firestore_client(project: str):
    try:
        from google.cloud import firestore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("google-cloud-firestore is required") from exc
    return firestore.Client(project=project)


def _user_state(project: str, uid: str) -> dict[str, Any]:
    client = _firestore_client(project)
    data = client.collection("users").document(uid).get().to_dict() or {}
    avatar = data.get("avatar") if isinstance(data.get("avatar"), Mapping) else {}
    return {
        "exists": bool(data),
        "approvedLock": str(avatar.get("status") or "") == "approved"
        and bool(avatar.get("approvedAvatarUrl")),
        "isStudentVerified": bool(data.get("isStudentVerified")),
        "studentEmailDomainOk": str(data.get("studentEmail") or "").endswith("@yonsei.ac.kr"),
    }


def build_report(
    *,
    project: str,
    mapping_path: Path,
    consent_file: Path,
    preflight_json: Path,
    api_key: str,
    auth_secret_paths: list[Path],
) -> dict[str, Any]:
    preflight = _load_preflight(preflight_json)
    auth_lookup = _auth_uid_lookup(api_key, _load_auth_secrets(auth_secret_paths))
    consent = evaluate_consent_file(consent_file)
    rows = []
    for uid, photo_path in _load_mapping(mapping_path):
        item = preflight.get(photo_path.name, {})
        user = _user_state(project, uid)
        local_auth_match = uid in auth_lookup
        eligible = (
            item.get("recommendation") == "PASS"
            and local_auth_match
            and user["exists"]
            and user["isStudentVerified"]
            and user["studentEmailDomainOk"]
            and not user["approvedLock"]
            and photo_path.is_file()
            and consent["valid"]
        )
        rows.append(
            {
                "uidHash": f"uid:{_hash_text(uid)}",
                "photoFile": photo_path.name,
                "photoExists": photo_path.is_file(),
                "normalizedPath": "normalized" in [part.lower() for part in photo_path.parts],
                "preflightRecommendation": str(item.get("recommendation") or "MISSING_PREFLIGHT"),
                "faceCount": item.get("faceCount"),
                "localAuthUidMatchesMapping": local_auth_match,
                "approvedLock": user["approvedLock"],
                "isStudentVerified": user["isStudentVerified"],
                "studentEmailDomainOk": user["studentEmailDomainOk"],
                "eligibleForUpload": eligible,
                "blockers": _blockers(item, user, photo_path, local_auth_match, consent),
            }
        )
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "project": project,
        "mappingFile": mapping_path.name,
        "consentFilePresent": consent_file.is_file(),
        "consentEvidence": consent,
        "preflightFile": preflight_json.name,
        "rowCount": len(rows),
        "eligibleUploadRows": sum(1 for row in rows if row["eligibleForUpload"]),
        "rows": rows,
        "redacted": True,
    }


def _blockers(
    preflight: Mapping[str, Any],
    user: Mapping[str, Any],
    photo_path: Path,
    local_auth_match: bool,
    consent: Mapping[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if not consent.get("valid"):
        blockers.append("consent_evidence_invalid")
    if not photo_path.is_file():
        blockers.append("photo_missing")
    if preflight.get("recommendation") != "PASS":
        blockers.append(str(preflight.get("recommendation") or "missing_preflight").lower())
    if not local_auth_match:
        blockers.append("auth_uid_mismatch_or_missing_secret")
    if not user.get("exists"):
        blockers.append("user_doc_missing")
    if user.get("approvedLock"):
        blockers.append("approved_avatar_lock")
    if not user.get("isStudentVerified"):
        blockers.append("student_not_verified")
    if not user.get("studentEmailDomainOk"):
        blockers.append("student_email_not_yonsei")
    return blockers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate canary UID/photo mapping.")
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--mapping_file", required=True)
    parser.add_argument("--consent_file", required=True)
    parser.add_argument("--preflight_json", required=True)
    parser.add_argument("--output_json", required=True)
    parser.add_argument("--api_key", default="")
    parser.add_argument("--google_services_json", default="")
    parser.add_argument("--auth_secret_json", action="append", default=[])
    args = parser.parse_args(argv)

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(
        project=args.project,
        mapping_path=Path(args.mapping_file),
        consent_file=Path(args.consent_file),
        preflight_json=Path(args.preflight_json),
        api_key=args.api_key
        or _api_key_from_google_services(Path(args.google_services_json)),
        auth_secret_paths=[Path(path) for path in args.auth_secret_json] or list(DEFAULT_AUTH_SECRET_PATHS),
    )
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(output_path.resolve()),
                "rowCount": report["rowCount"],
                "eligibleUploadRows": report["eligibleUploadRows"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
