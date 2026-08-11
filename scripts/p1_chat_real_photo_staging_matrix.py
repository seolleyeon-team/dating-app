#!/usr/bin/env python3
"""Run or plan the chat-only real profile photo staging auth matrix.

The script is intentionally read-only: it calls the callable and inspects
responses, but it does not create users, edit chat rooms, or toggle consent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FORBIDDEN_RESPONSE_TOKENS = [
    "sourcePhotoRefs",
    "sourcePhotoGcsUri",
    "gcsUri",
    "userPrivateMedia",
    "seolleyeon-final-private-source-photos",
    "clipEmbeddings",
    "vector",
]


@dataclass(frozen=True)
class MatrixCase:
    name: str
    requester_token_env: str
    chat_room_env: str
    target_uid_env: str
    expected: str
    required: bool = True


CASES = [
    MatrixCase(
        "participant_consent_true_real_photo",
        "STAGING_USER_A_ID_TOKEN",
        "STAGING_CHAT_ROOM_ID_CONSENT_TRUE",
        "STAGING_USER_B_UID_CONSENT_TRUE",
        "real_photo",
    ),
    MatrixCase(
        "participant_consent_false_avatar",
        "STAGING_USER_A_ID_TOKEN",
        "STAGING_CHAT_ROOM_ID_CONSENT_FALSE",
        "STAGING_USER_B_UID_CONSENT_FALSE",
        "avatar",
    ),
    MatrixCase(
        "non_participant_denied",
        "STAGING_USER_C_ID_TOKEN",
        "STAGING_CHAT_ROOM_ID_CONSENT_TRUE",
        "STAGING_USER_B_UID_CONSENT_TRUE",
        "deny",
    ),
    MatrixCase(
        "participant_requests_nonparticipant_target_denied",
        "STAGING_USER_A_ID_TOKEN",
        "STAGING_CHAT_ROOM_ID_CONSENT_TRUE",
        "STAGING_NONPARTICIPANT_TARGET_UID",
        "deny",
    ),
    MatrixCase(
        "inactive_chat_room_denied",
        "STAGING_USER_A_ID_TOKEN",
        "STAGING_INACTIVE_CHAT_ROOM_ID",
        "STAGING_USER_B_UID_CONSENT_TRUE",
        "deny",
        required=False,
    ),
    MatrixCase(
        "blocked_relationship_denied",
        "STAGING_USER_A_ID_TOKEN",
        "STAGING_BLOCKED_CHAT_ROOM_ID",
        "STAGING_BLOCKED_TARGET_UID",
        "deny",
        required=False,
    ),
    MatrixCase(
        "suspended_target_avatar_or_denied",
        "STAGING_USER_A_ID_TOKEN",
        "STAGING_SUSPENDED_CHAT_ROOM_ID",
        "STAGING_SUSPENDED_TARGET_UID",
        "avatar_or_deny",
        required=False,
    ),
    MatrixCase(
        "self_view_denied",
        "STAGING_USER_A_ID_TOKEN",
        "STAGING_CHAT_ROOM_ID_CONSENT_TRUE",
        "STAGING_USER_A_UID",
        "deny",
    ),
    MatrixCase(
        "missing_chat_real_photo_avatar",
        "STAGING_USER_A_ID_TOKEN",
        "STAGING_MISSING_REAL_PHOTO_CHAT_ROOM_ID",
        "STAGING_MISSING_REAL_PHOTO_TARGET_UID",
        "avatar",
        required=False,
    ),
]


def env(name: str, fallback: str = "") -> str:
    return os.environ.get(name, fallback).strip()


def project_looks_production(project: str) -> bool:
    lowered = project.lower()
    return not any(marker in lowered for marker in ("stage", "staging", "dev", "test", "sandbox"))


def callable_url(project: str, region: str, callable_name: str) -> str:
    return f"https://{region}-{project}.cloudfunctions.net/{callable_name}"


def redact_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    if parsed.query:
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "<redacted-query>", parsed.fragment))
    return value


def redact_response(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("<redacted-url>" if k == "imageUrl" and isinstance(v, str) else redact_response(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_response(item) for item in value]
    if isinstance(value, str) and value.startswith("http"):
        return redact_url(value)
    return value


def contains_forbidden(value: Any) -> list[str]:
    text = json.dumps(value, ensure_ascii=False)
    return [token for token in FORBIDDEN_RESPONSE_TOKENS if token in text]


def firebase_error_status(body: dict[str, Any]) -> str:
    error = body.get("error")
    if isinstance(error, dict):
        status = str(error.get("status") or error.get("code") or "").upper()
        if status:
            return status
    return ""


def validate_real_photo_result(result: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    chat_bucket = env(
        "CHAT_PROFILE_PHOTO_BUCKET", "seolleyeon-final-chat-profile-photos"
    )
    source_bucket = env(
        "SOURCE_PHOTO_BUCKET", "seolleyeon-final-private-source-photos"
    )
    image_url = str(result.get("imageUrl") or "")
    expires_at = str(result.get("expiresAt") or "")
    if not image_url:
        issues.append("missing_imageUrl")
    if source_bucket and source_bucket in image_url:
        issues.append("signed_source_bucket_url")
    if chat_bucket and chat_bucket not in image_url and "storage.googleapis.com" in image_url:
        issues.append("imageUrl_not_chat_profile_bucket")
    if not expires_at:
        issues.append("missing_expiresAt")
    else:
        try:
            parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            delta = (parsed - datetime.now(timezone.utc)).total_seconds()
            if delta <= 0:
                issues.append("expiresAt_already_expired")
            if delta > 310:
                issues.append("expiresAt_exceeds_300_seconds")
        except ValueError:
            issues.append("invalid_expiresAt")
    return issues


def call_callable(url: str, token: str, chat_room_id: str, target_uid: str) -> tuple[int, dict[str, Any]]:
    payload = json.dumps({"data": {"chatRoomId": chat_room_id, "targetUid": target_uid}}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return resp.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"raw": raw}
        return exc.code, body


def classify_result(expected: str, status: int, body: dict[str, Any]) -> str:
    error_status = firebase_error_status(body)
    allowed_denial_statuses = {"UNAUTHENTICATED", "PERMISSION_DENIED", "NOT_FOUND"}
    if expected == "deny":
        return "PASS" if error_status in allowed_denial_statuses else "FAIL"
    if expected == "avatar_or_deny" and error_status in allowed_denial_statuses:
        return "PASS"
    result = body.get("result", body)
    display_mode = result.get("displayMode") if isinstance(result, dict) else None
    if expected == "avatar_or_deny":
        return "PASS" if display_mode == "avatar" else "FAIL"
    if display_mode != expected:
        return "FAIL"
    if expected == "real_photo":
        if not isinstance(result, dict) or validate_real_photo_result(result):
            return "FAIL"
    return "PASS"


def build_case_env(case: MatrixCase) -> tuple[str, str, str]:
    chat_room_id = env(case.chat_room_env) or env("STAGING_CHAT_ROOM_ID")
    target_uid = env(case.target_uid_env) or env("STAGING_USER_B_UID")
    requester_token = env(case.requester_token_env)
    return requester_token, chat_room_id, target_uid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run live callable checks using env-provided ID tokens.")
    parser.add_argument("--output", default="out/chat_real_photo_p1_matrix_report.json")
    parser.add_argument("--allow-production-like-project", action="store_true")
    args = parser.parse_args()

    project = env("FIREBASE_PROJECT") or env("GCP_PROJECT")
    gcp_project = env("GCP_PROJECT")
    firebase_project = env("FIREBASE_PROJECT")
    region = env("FUNCTIONS_REGION", "asia-northeast3")
    callable_name = env("CHAT_REAL_PHOTO_CALLABLE", "getChatRealProfilePhoto")
    url = callable_url(project or "<FIREBASE_PROJECT>", region, callable_name)

    report: dict[str, Any] = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "live" if args.live else "dry_run",
        "project": project,
        "region": region,
        "callable": callable_name,
        "url": url if not project else redact_url(url),
        "cases": [],
    }

    if not args.live:
        report["requiredEnv"] = sorted(
            {
                "FIREBASE_PROJECT",
                "FUNCTIONS_REGION",
                "STAGING_USER_A_ID_TOKEN",
                "STAGING_USER_C_ID_TOKEN",
                "STAGING_USER_A_UID",
                "STAGING_USER_B_UID",
                "STAGING_CHAT_ROOM_ID",
                "STAGING_CHAT_ROOM_ID_CONSENT_TRUE",
                "STAGING_USER_B_UID_CONSENT_TRUE",
            }
        )
        report["status"] = "DRY_RUN_ONLY"
    else:
        if not project:
            raise SystemExit("FIREBASE_PROJECT or GCP_PROJECT is required for --live.")
        if gcp_project and firebase_project and gcp_project != firebase_project:
            raise SystemExit(
                f"Refusing live matrix with mismatched projects: GCP_PROJECT={gcp_project} FIREBASE_PROJECT={firebase_project}"
            )
        if project_looks_production(project) and not args.allow_production_like_project and env("ALLOW_PRODUCTION") != "true":
            raise SystemExit(
                f"Refusing live checks against production-like project '{project}'. Use a staging project or explicit approval."
            )
        for case in CASES:
            token, chat_room_id, target_uid = build_case_env(case)
            missing = [
                name
                for name, value in (
                    (case.requester_token_env, token),
                    (case.chat_room_env, chat_room_id),
                    (case.target_uid_env, target_uid),
                )
                if not value
            ]
            if missing:
                report["cases"].append(
                    {
                        "case": case.name,
                        "expected": case.expected,
                        "status": "SKIPPED" if not case.required else "BLOCKED",
                        "missingEnv": missing,
                    }
                )
                continue
            status, body = call_callable(url, token, chat_room_id, target_uid)
            forbidden = contains_forbidden(body)
            result = body.get("result", body)
            real_photo_issues = (
                validate_real_photo_result(result)
                if isinstance(result, dict) and result.get("displayMode") == "real_photo"
                else []
            )
            outcome = classify_result(case.expected, status, body)
            if forbidden or real_photo_issues:
                outcome = "FAIL"
            report["cases"].append(
                {
                    "case": case.name,
                    "expected": case.expected,
                    "httpStatus": status,
                    "firebaseErrorStatus": firebase_error_status(body),
                    "status": outcome,
                    "forbiddenResponseTokens": forbidden,
                    "realPhotoValidationIssues": real_photo_issues,
                    "response": redact_response(body),
                }
            )
        statuses = {case["status"] for case in report["cases"]}
        report["status"] = "PASS" if "FAIL" not in statuses and "BLOCKED" not in statuses else "FAIL_OR_BLOCKED"

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"PASS", "DRY_RUN_ONLY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
