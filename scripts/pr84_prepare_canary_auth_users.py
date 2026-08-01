from __future__ import annotations

import argparse
import json
import secrets
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


TARGET_PROJECT = "seolleyeon-final"
DEFAULT_USERS = {
    "PR84_A": "staging-pr84-a@yonsei.ac.kr",
    "PR84_B": "staging-pr84-b@yonsei.ac.kr",
    "PR84_C": "staging-pr84-c@yonsei.ac.kr",
}


def strong_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _load_admin_modules():
    try:
        import firebase_admin
        from firebase_admin import auth, credentials, firestore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "firebase_admin is required for --apply. Install it in the active Python environment first."
        ) from exc
    return firebase_admin, auth, credentials, firestore


def _load_existing_secret(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _planned_users(existing: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    existing_users = existing.get("users") if isinstance(existing.get("users"), Mapping) else {}
    users: dict[str, dict[str, str]] = {}
    for label, email in DEFAULT_USERS.items():
        existing_item = existing_users.get(label) if isinstance(existing_users.get(label), Mapping) else {}
        users[label] = {
            "email": str(existing_item.get("email") or email),
            "password": str(existing_item.get("password") or strong_password()),
        }
    return users


def _public_user_plan(users: Mapping[str, Mapping[str, str]], *, include_uid: bool = False) -> dict[str, Any]:
    planned: dict[str, Any] = {}
    for label, data in users.items():
        item = {
            "email": data["email"],
            "passwordStoredLocally": False,
        }
        if include_uid and data.get("uid"):
            item["uid"] = data["uid"]
        planned[label] = item
    return planned


def _write_secret_file(users: Mapping[str, Mapping[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "project": TARGET_PROJECT,
        "users": {
            label: {
                "email": data["email"],
                "password": data["password"],
                **({"uid": data["uid"]} if data.get("uid") else {}),
            }
            for label, data in users.items()
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_auth_user(auth_mod: Any, *, email: str, password: str) -> tuple[str, str]:
    try:
        user = auth_mod.get_user_by_email(email)
        auth_mod.update_user(user.uid, password=password, email_verified=True, disabled=False)
        return str(user.uid), "updated"
    except Exception:
        user = auth_mod.create_user(
            email=email,
            password=password,
            email_verified=True,
            disabled=False,
        )
        return str(user.uid), "created"


def _write_firestore_fixture(firestore_mod: Any, *, label: str, uid: str, email: str) -> None:
    db = firestore_mod.client()
    db.collection("users").document(uid).set(
        {
            "uid": uid,
            "nickname": f"PR8.4 Canary {label}",
            "profileImageMode": "avatar",
            "isStudentVerified": True,
            "studentEmail": email,
            "avatar": {},
            "onboarding": {
                "sourcePhotoUploadCount": 0,
                "avatarUrls": [],
                "photoUrls": [],
            },
            "stagingCanary": {
                "scope": "avatar_pr84",
                "createdAt": datetime.now(timezone.utc).isoformat(),
            },
        },
        merge=True,
    )


def build_dry_run_report(*, users: Mapping[str, Mapping[str, str]], secret_file: Path) -> dict[str, Any]:
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run",
        "targetProject": TARGET_PROJECT,
        "status": "planned",
        "willMutateStaging": False,
        "secretFile": str(secret_file),
        "users": _public_user_plan(users),
        "nextCommand": (
            ".venv\\Scripts\\python.exe scripts\\pr84_prepare_canary_auth_users.py "
            "--target_project seolleyeon-final --apply --confirm_staging_mutation"
        ),
    }


def apply_users(*, users: dict[str, dict[str, str]], secret_file: Path) -> dict[str, Any]:
    firebase_admin, auth_mod, credentials_mod, firestore_mod = _load_admin_modules()
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials_mod.ApplicationDefault(), {"projectId": TARGET_PROJECT})
    results: dict[str, dict[str, str]] = {}
    for label, data in users.items():
        uid, action = _ensure_auth_user(auth_mod, email=data["email"], password=data["password"])
        data["uid"] = uid
        _write_firestore_fixture(firestore_mod, label=label, uid=uid, email=data["email"])
        results[label] = {
            "email": data["email"],
            "uid": uid,
            "action": action,
            "passwordStoredLocally": True,
        }
    _write_secret_file(users, secret_file)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "apply",
        "targetProject": TARGET_PROJECT,
        "status": "pass",
        "willMutateStaging": True,
        "secretFile": str(secret_file),
        "users": results,
        "postApplyCommands": [
            ".venv\\Scripts\\python.exe scripts\\pr84_eligibility_inventory.py --project seolleyeon-final --auth_secret_json .local_secrets\\staging_pr84_canary_users.json",
            ".venv\\Scripts\\python.exe scripts\\pr84_canary_gate.py --project seolleyeon-final --min_users 3",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare unlocked PR8.4 staging canary Auth users.")
    parser.add_argument("--target_project", default=TARGET_PROJECT)
    parser.add_argument("--secret_file", default=".local_secrets/staging_pr84_canary_users.json")
    parser.add_argument("--report_json", default="out/pr84_prepare_canary_auth_users.json")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm_staging_mutation", action="store_true")
    args = parser.parse_args(argv)

    if args.target_project != TARGET_PROJECT:
        raise SystemExit("target_project must be seolleyeon-final")
    if args.apply and not args.confirm_staging_mutation:
        raise SystemExit("--apply requires --confirm_staging_mutation")

    secret_file = Path(args.secret_file)
    users = _planned_users(_load_existing_secret(secret_file))
    report = (
        apply_users(users=users, secret_file=secret_file)
        if args.apply
        else build_dry_run_report(users=users, secret_file=secret_file)
    )
    output_path = Path(args.report_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
