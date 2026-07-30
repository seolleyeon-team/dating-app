from __future__ import annotations

import argparse
import json
import secrets
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import auth, credentials, firestore


TARGET_PROJECT = "seolleyeon-final"


def _password(length: int = 28) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=TARGET_PROJECT)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-project", default="")
    parser.add_argument("--secret-file", default="")
    parser.add_argument("--report-file", default="")
    args = parser.parse_args()

    if args.project != TARGET_PROJECT:
        raise SystemExit("project must be seolleyeon-final")
    if args.count < 10 or args.count > 20:
        raise SystemExit("count must be between 10 and 20")
    if args.apply and args.confirm_project != TARGET_PROJECT:
        raise SystemExit("--apply requires --confirm-project seolleyeon-final")

    now = datetime.now(timezone.utc)
    batch_id = now.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    users = [
        {
            "label": f"MINI_{index:03d}",
            "email": (
                f"mini-avatar-{batch_id.lower()}-{index:03d}"
                "@seolleyeon-final.local"
            ),
            "password": _password(),
        }
        for index in range(1, args.count + 1)
    ]

    report: dict[str, Any] = {
        "generatedAt": now.isoformat(),
        "project": TARGET_PROJECT,
        "batchId": batch_id,
        "mode": "apply" if args.apply else "dry_run",
        "requestedCount": args.count,
        "status": "planned",
        "passwordPrinted": False,
        "users": [
            {"label": item["label"], "email": item["email"]}
            for item in users
        ],
    }

    if not args.apply:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    secret_file = Path(
        args.secret_file
        or f".local_secrets/avatar_mini_calibration/users_{batch_id}.json"
    )
    report_file = Path(
        args.report_file
        or f"out/avatar_preprod_fresh_users_{batch_id}.json"
    )

    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            credentials.ApplicationDefault(),
            {"projectId": TARGET_PROJECT},
        )
    db = firestore.client()

    created: list[dict[str, str]] = []
    secret_users: list[dict[str, str]] = []
    try:
        for item in users:
            record = auth.create_user(
                email=item["email"],
                password=item["password"],
                email_verified=True,
                disabled=False,
            )
            uid = str(record.uid)
            db.collection("users").document(uid).set(
                {
                    "uid": uid,
                    "nickname": item["label"],
                    "profileImageMode": "avatar",
                    "isStudentVerified": True,
                    "studentEmail": item["email"],
                    "avatar": {},
                    "onboarding": {
                        "avatarUrls": [],
                        "photoUrls": [],
                        "sourcePhotoUploadCount": 0,
                    },
                    "stagingCalibration": {
                        "scope": "avatar_preproduction_mini_calibration",
                        "batchId": batch_id,
                        "createdAt": now,
                    },
                }
            )
            created.append(
                {
                    "label": item["label"],
                    "uid": uid,
                    "email": item["email"],
                    "action": "created",
                }
            )
            secret_users.append(
                {
                    "label": item["label"],
                    "uid": uid,
                    "email": item["email"],
                    "password": item["password"],
                }
            )
    except Exception:
        report["status"] = "partial_failure"
        report["createdCount"] = len(created)
        report["users"] = created
        _write_json(report_file, report)
        if secret_users:
            _write_json(
                secret_file,
                {
                    "project": TARGET_PROJECT,
                    "batchId": batch_id,
                    "users": secret_users,
                },
            )
        raise

    verification: list[dict[str, Any]] = []
    for item in created:
        auth_user = auth.get_user(item["uid"])
        user_doc = db.collection("users").document(item["uid"]).get()
        private_doc = db.collection("userPrivateMedia").document(item["uid"]).get()
        data = user_doc.to_dict() or {}
        avatar = data.get("avatar") if isinstance(data.get("avatar"), dict) else {}
        verification.append(
            {
                "uid": item["uid"],
                "authExists": auth_user.uid == item["uid"],
                "userDocExists": user_doc.exists,
                "approvedAvatar": (
                    avatar.get("status") == "approved"
                    or bool(avatar.get("approvedAvatarUrl"))
                ),
                "privateMediaExists": private_doc.exists,
            }
        )

    _write_json(
        secret_file,
        {
            "project": TARGET_PROJECT,
            "batchId": batch_id,
            "users": secret_users,
        },
    )
    report.update(
        {
            "status": "pass",
            "createdCount": len(created),
            "secretFile": str(secret_file),
            "reportFile": str(report_file),
            "users": created,
            "verification": verification,
        }
    )
    _write_json(report_file, report)
    print(
        json.dumps(
            {
                "project": TARGET_PROJECT,
                "batchId": batch_id,
                "status": report["status"],
                "createdCount": len(created),
                "reportFile": str(report_file),
                "passwordPrinted": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
