#!/usr/bin/env python3
"""Create or verify Firebase Auth staging users A/B/C.

Dry-run is the default. Apply mode uses the Firebase Admin SDK and writes
generated passwords only to .local_secrets/staging_test_users.json.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
from pathlib import Path
from typing import Any


TARGET_PROJECT = "seolleyeon-final"
DEFAULT_EMAILS = {
    "A": "staging-user-a@seolleyeon-final.local",
    "B": "staging-user-b@seolleyeon-final.local",
    "C": "staging-user-c@seolleyeon-final.local",
}


def strong_password(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def load_admin_modules():
    try:
        import firebase_admin
        from firebase_admin import auth, credentials, firestore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "firebase_admin is required for --apply. Install it in the active Python environment first."
        ) from exc
    return firebase_admin, auth, credentials, firestore


def build_users(args: argparse.Namespace) -> dict[str, dict[str, str]]:
    users: dict[str, dict[str, str]] = {}
    for label in ("A", "B", "C"):
        email = os.getenv(f"TEST_USER_{label}_EMAIL") or getattr(args, f"user_{label.lower()}_email") or DEFAULT_EMAILS[label]
        password = os.getenv(f"TEST_USER_{label}_PASSWORD") or strong_password()
        users[label] = {"email": email, "password": password}
    return users


def write_secret_file(users: dict[str, dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    merged = {**existing, "project": TARGET_PROJECT, "users": users}
    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")


def ensure_user(auth_mod: Any, email: str, password: str, disabled: bool = False) -> tuple[str, str]:
    try:
        user = auth_mod.get_user_by_email(email)
        auth_mod.update_user(user.uid, password=password, email_verified=True, disabled=disabled)
        return user.uid, "updated"
    except Exception:
        user = auth_mod.create_user(email=email, password=password, email_verified=True, disabled=disabled)
        return user.uid, "created"


def create_safe_firestore_fixtures(firestore_mod: Any, users: dict[str, dict[str, str]], uid_map: dict[str, str]) -> None:
    db = firestore_mod.client()
    for label, uid in uid_map.items():
        db.collection("users").document(uid).set(
            {
                "uid": uid,
                "nickname": f"Staging User {label}",
                "profileImageMode": "avatar",
                "isStudentVerified": True,
                "studentEmail": users[label]["email"],
                "avatar": {},
                "onboarding": {"sourcePhotoUploadCount": 0},
            },
            merge=True,
        )

    room_id = "staging-chat-user-a-user-b"
    db.collection("chat_rooms").document(room_id).set(
        {
            "roomId": room_id,
            "participants": [uid_map["A"], uid_map["B"]],
            "participantIds": [uid_map["A"], uid_map["B"]],
            "status": "active",
            "stagingFixture": True,
        },
        merge=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_project", default=TARGET_PROJECT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--create_firestore_fixtures", action="store_true")
    parser.add_argument("--user_a_email", default="")
    parser.add_argument("--user_b_email", default="")
    parser.add_argument("--user_c_email", default="")
    parser.add_argument("--secret_file", default=".local_secrets/staging_test_users.json")
    parser.add_argument("--report_json", default="out/staging_auth_test_users_dry_run.json")
    args = parser.parse_args()

    if args.target_project != TARGET_PROJECT:
        raise SystemExit("target_project must be seolleyeon-final")

    users = build_users(args)
    report: dict[str, Any] = {
        "mode": "apply" if args.apply else "dry_run",
        "target_project": args.target_project,
        "users": {
            label: {"email": data["email"], "passwordStoredLocally": bool(args.apply)}
            for label, data in users.items()
        },
        "status": "planned",
    }

    if args.apply:
        firebase_admin, auth_mod, credentials_mod, firestore_mod = load_admin_modules()
        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials_mod.ApplicationDefault(), {"projectId": TARGET_PROJECT})
        uid_map: dict[str, str] = {}
        results: dict[str, Any] = {}
        for label, data in users.items():
            uid, action = ensure_user(auth_mod, data["email"], data["password"])
            uid_map[label] = uid
            results[label] = {"uid": uid, "email": data["email"], "action": action}
        write_secret_file(users, Path(args.secret_file))
        if args.create_firestore_fixtures:
            create_safe_firestore_fixtures(firestore_mod, users, uid_map)
        report["users"] = results
        report["secretFile"] = args.secret_file
        report["firestoreFixtures"] = bool(args.create_firestore_fixtures)
        report["status"] = "pass"

    Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report_json).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
