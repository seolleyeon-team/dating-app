#!/usr/bin/env python3
"""Read-only live verifier for the seolleyeon-final avatar staging pipeline.

This script intentionally composes existing redacting probes instead of reading
user documents, source photo refs, signed URLs, tokens, or secret values.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


DEFAULT_PROJECT = "seolleyeon-final"
DEFAULT_LOCATION = "asia-northeast3"
DEFAULT_WORKER_LOCATION = "asia-southeast1"
DEFAULT_ACCOUNT = "seolleyeon.official@gmail.com"
DEFAULT_SERVICE = "seolleyeon-avatar-worker"


def _gcloud_executable() -> str:
    return shutil.which("gcloud") or shutil.which("gcloud.cmd") or "gcloud"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(command: Sequence[str], *, cwd: Optional[Path] = None) -> dict[str, Any]:
    completed = subprocess.run(
        list(command),
        cwd=str(cwd or _repo_root()),
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "command": _safe_command(command),
        "exitCode": completed.returncode,
        "stdout": _parse_json_or_text(completed.stdout),
        "stderr": _redact_text(completed.stderr.strip()),
        "ok": completed.returncode == 0,
    }


def _safe_command(command: Sequence[str]) -> list[str]:
    safe: list[str] = []
    skip_next = False
    secretish_flags = {
        "--token",
        "--token_file",
        "--payload_json",
        "--source_gcs_uri",
        "--uid",
        "--job_id",
    }
    for index, part in enumerate(command):
        if skip_next:
            safe.append("<redacted>")
            skip_next = False
            continue
        if part in secretish_flags:
            safe.append(part)
            skip_next = True
            continue
        lowered = str(part).lower()
        if (
            lowered.startswith("--token=")
            or lowered.startswith("--source_gcs_uri=")
            or lowered.startswith("--uid=")
            or lowered.startswith("--job_id=")
        ):
            key = str(part).split("=", 1)[0]
            safe.append(f"{key}=<redacted>")
        elif index == 0:
            safe.append(Path(part).name)
        else:
            safe.append(str(part))
    return safe


def _redact_text(value: str) -> str:
    text = str(value)
    for marker in (
        "Authorization: Bearer ",
        "authorization: bearer ",
        "Bearer ",
        "bearer ",
    ):
        if marker in text:
            prefix, _, _ = text.partition(marker)
            return f"{prefix}{marker}<redacted>"
    text = text.replace("seolleyeon-final-private-source-photos", "<private-source-bucket-redacted>")
    text = text.replace("seolleyeon-private-source-photos", "<private-source-bucket-redacted>")
    text = text.replace("sourcePhotoRefs", "<sourcePhotoRefs-redacted>")
    text = text.replace("gcsUri", "<gcsUri-redacted>")
    return text[:4000]


def _parse_json_or_text(value: str) -> Any:
    stripped = value.strip()
    if not stripped:
        return ""
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return _redact_text(stripped)


def _gcloud_value(args: Sequence[str]) -> str:
    result = _run([_gcloud_executable(), *args])
    if not result["ok"]:
        return ""
    stdout = result.get("stdout")
    return stdout if isinstance(stdout, str) else ""


def _worker_url(*, project: str, location: str, service: str) -> str:
    return _gcloud_value(
        [
            "run",
            "services",
            "describe",
            service,
            f"--region={location}",
            f"--project={project}",
            "--format=value(status.url)",
        ]
    ).strip()


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    root = _repo_root()
    python = sys.executable
    account = _gcloud_value(["config", "get-value", "account"]).strip()
    active_project = _gcloud_value(["config", "get-value", "project"]).strip()
    worker_url = args.worker_url.strip() or _worker_url(
        project=args.project,
        location=args.worker_location,
        service=args.worker_service,
    )

    checks: dict[str, Any] = {
        "guard": {
            "account": account,
            "activeProject": active_project,
            "accountOk": account == args.expected_account,
            "projectOk": active_project == args.project,
        },
        "worker": {
            "service": args.worker_service,
            "url": worker_url,
            "urlPresent": bool(worker_url),
        },
    }

    checks["preflight"] = _run(
        [
            python,
            "scripts/staging_avatar_live_preflight.py",
            "--avatar_only",
            "--stage=live",
            f"--project={args.project}",
            f"--location={args.location}",
            f"--worker_location={args.worker_location}",
            f"--expected_account={args.expected_account}",
        ],
        cwd=root,
    )

    if worker_url:
        checks["iam"] = _run(
            [
                python,
                "scripts/avatar_live_iam_check.py",
                "--worker_url",
                worker_url,
                "--use_gcloud_token",
                "--gcloud_token_without_audience",
                "--timeout_seconds",
                str(args.timeout_seconds),
            ],
            cwd=root,
        )
        checks["canary"] = _run(
            [
                python,
                "scripts/avatar_staging_canary.py",
                "--live",
                "--worker_url",
                worker_url,
                "--id_token_from_gcloud",
                "--gcloud_token_without_audience",
            ],
            cwd=root,
        )
    else:
        checks["iam"] = {"ok": False, "reason": "worker_url_missing"}
        checks["canary"] = {"ok": False, "reason": "worker_url_missing"}

    checks["queue"] = _run(
        [
            python,
            "scripts/avatar_queue_status.py",
            "--firestore_project",
            args.project,
            "--firestore_database",
            args.firestore_database,
            "--limit",
            str(args.queue_limit),
        ],
        cwd=root,
    )

    if args.uid.strip():
        avatar_job_command = [
            python,
            "scripts/debug_avatar_job_status.py",
            f"--project={args.project}",
            f"--database={args.firestore_database}",
            "--uid",
            args.uid.strip(),
            "--recent_minutes",
            str(args.recent_minutes),
        ]
        if args.job_id.strip():
            avatar_job_command.extend(["--job_id", args.job_id.strip()])
        avatar_job = _run(avatar_job_command, cwd=root)
        avatar_job["previewReadyOk"] = _avatar_job_preview_ready_ok(
            avatar_job.get("stdout")
        )
        avatar_job["approvedOk"] = _avatar_job_approved_ok(
            avatar_job.get("stdout")
        )
        if args.require_preview_ready and avatar_job.get("ok") is True:
            avatar_job["ok"] = bool(avatar_job["previewReadyOk"])
        if args.require_approved and avatar_job.get("ok") is True:
            avatar_job["ok"] = bool(avatar_job["approvedOk"])
        checks["avatarJob"] = avatar_job

    blocking = _blocking_findings(checks)
    return {
        "project": args.project,
        "location": args.location,
        "workerLocation": args.worker_location,
        "ok": not blocking,
        "blocking": blocking,
        "checks": checks,
    }


def _avatar_job_preview_ready_ok(stdout: Any) -> bool:
    if not isinstance(stdout, Mapping):
        return False
    jobs = stdout.get("jobs")
    if not isinstance(jobs, list):
        return False
    for job in jobs:
        if not isinstance(job, Mapping):
            continue
        status = str(job.get("status") or "").strip().lower()
        candidate_qa = (
            job.get("candidateQa") if isinstance(job.get("candidateQa"), Mapping) else {}
        )
        candidates_by_status = (
            job.get("candidatesByStatus")
            if isinstance(job.get("candidatesByStatus"), Mapping)
            else {}
        )
        preview_allowed = int(candidate_qa.get("previewAllowedCount") or 0)
        preview_ready_count = int(candidates_by_status.get("preview_ready") or 0)
        if status in {"preview_ready", "approved", "completed"} and (
            preview_allowed > 0 or preview_ready_count > 0
        ):
            return True
    return False


def _avatar_job_approved_ok(stdout: Any) -> bool:
    if not isinstance(stdout, Mapping):
        return False
    user_doc = stdout.get("userDocument")
    if isinstance(user_doc, Mapping):
        if (
            str(user_doc.get("avatarStatus") or "").strip().lower() == "approved"
            and bool(user_doc.get("approvedAvatarUrlPresent"))
            and int(user_doc.get("onboardingAvatarUrlsCount") or 0) > 0
        ):
            return True
    jobs = stdout.get("jobs")
    if not isinstance(jobs, list):
        return False
    return any(
        isinstance(job, Mapping)
        and str(job.get("status") or "").strip().lower() in {"approved", "completed"}
        for job in jobs
    )


def _blocking_findings(checks: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    guard = checks.get("guard") if isinstance(checks.get("guard"), Mapping) else {}
    if not guard.get("accountOk"):
        findings.append("account_mismatch")
    if not guard.get("projectOk"):
        findings.append("project_mismatch")
    worker = checks.get("worker") if isinstance(checks.get("worker"), Mapping) else {}
    if not worker.get("urlPresent"):
        findings.append("worker_url_missing")
    for key in ("preflight", "iam", "canary", "queue", "avatarJob"):
        check = checks.get(key)
        if isinstance(check, Mapping) and check.get("ok") is not True:
            findings.append(f"{key}_failed")
    return findings


def _write_report(report: Mapping[str, Any], path: Optional[str]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        Path(path).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run read-only live checks for the seolleyeon-final avatar staging pipeline."
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--worker_location", default=DEFAULT_WORKER_LOCATION)
    parser.add_argument("--expected_account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--worker_service", default=DEFAULT_SERVICE)
    parser.add_argument("--worker_url", default="")
    parser.add_argument("--firestore_database", default="(default)")
    parser.add_argument("--queue_limit", type=int, default=20)
    parser.add_argument("--uid", default="")
    parser.add_argument("--job_id", default="")
    parser.add_argument("--recent_minutes", type=int, default=120)
    parser.add_argument("--require_preview_ready", action="store_true")
    parser.add_argument("--require_approved", action="store_true")
    parser.add_argument("--timeout_seconds", type=int, default=30)
    parser.add_argument("--output_report_json")
    args = parser.parse_args(argv)

    report = build_report(args)
    _write_report(report, args.output_report_json)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
