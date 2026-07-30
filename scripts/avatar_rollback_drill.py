#!/usr/bin/env python3
"""Versioned bounded avatar rollback drill.

The default mode is a sanitized plan and performs no external calls. Verification
uses read-only and dry-run operations only. Apply requires both --apply and the
project-specific confirmation token.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence


SCHEMA_VERSION = "avatar_rollback_drill_v1"
ALLOWED_PROJECTS = {"seolleyeon-final", "seolleyeon-festival"}
FORBIDDEN_PROJECTS = {"", "default", "seolleyeon"}
FORBIDDEN_COMMAND_TERMS = {
    "consent-withdrawal",
    "account-deletion",
    "source-retention",
    "onAvatarJobSourceRetention",
    "onClipEmbeddingSourceRetention",
}
CommandRunner = Callable[[Sequence[str]], str]


class RollbackDrillError(RuntimeError):
    """Raised when the rollback drill would exceed its bounded contract."""


class CommandUnavailableError(RollbackDrillError):
    """Raised when a required local command cannot be resolved."""


def build_rollback_report(
    *,
    project: str,
    config_path: Path,
    mode: str = "plan",
    apply: bool = False,
    confirmation_token: str = "",
    prior_worker_revision: str = "",
    resume_confirmation_token: str = "",
    runner: Optional[CommandRunner] = None,
) -> dict[str, Any]:
    """Build, verify, or apply a bounded rollback drill report."""

    project = _validate_project(project)
    mode = _validate_mode(mode)
    config = _load_config(Path(config_path))
    project_config = config["projects"][project]
    expected_token = _confirmation_token(config, project)
    steps = _build_steps(
        project=project,
        project_config=project_config,
        prior_worker_revision=prior_worker_revision,
        resume_confirmation_token=resume_confirmation_token,
    )

    if mode == "apply" and (not apply or confirmation_token != expected_token):
        raise RollbackDrillError("apply requires --apply and the exact confirmation token")
    if mode != "apply" and apply:
        raise RollbackDrillError("--apply is only valid with --mode apply")

    executed: list[dict[str, Any]] = []
    source_before: Optional[dict[str, Any]] = None
    source_after: Optional[dict[str, Any]] = None
    command_runner = runner or _run_command

    verification_failures = 0
    if mode in {"verify", "apply"}:
        try:
            source_before = _source_aggregate(command_runner, project, project_config)
        except (OSError, RollbackDrillError):
            if mode == "apply":
                raise
            verification_failures += 1

        for step in steps:
            if mode == "verify" and step["mutation"]:
                executed.append(_execution_record(step, "skipped_mutation_in_verify"))
                continue
            try:
                output = _run_step(command_runner, step, mode)
                executed.append(_execution_record(step, "executed", output))
            except (OSError, RollbackDrillError) as error:
                if mode == "apply":
                    raise
                verification_failures += 1
                executed.append(_execution_record(step, _verification_failure_status(error)))

        try:
            source_after = _source_aggregate(command_runner, project, project_config)
        except (OSError, RollbackDrillError):
            if mode == "apply":
                raise
            verification_failures += 1

    source_invariant = _source_invariant(source_before, source_after)
    verification_passed: Optional[bool] = None
    if mode in {"verify", "apply"}:
        verification_passed = (
            verification_failures == 0
            and source_invariant["verified"]
            and source_invariant["unchanged"] is True
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": project,
        "mode": mode,
        "applied": mode == "apply",
        "mutationsPerformed": sum(1 for item in executed if item["mutating"] and item["status"] == "executed"),
        "verification": {
            "passed": verification_passed,
            "failureCount": verification_failures,
        },
        "confirmation": {
            "requiredForApply": True,
            "resumeRequiresSeparateConfirmation": True,
        },
        "plan": [_public_step(step) for step in steps],
        "executed": executed,
        "sourcePreservation": source_invariant,
        "redaction": {
            "sanitized": True,
            "omitted": [
                "raw command lines",
                "private paths",
                "UIDs",
                "tokens",
                "signed URLs",
            ],
        },
    }


def _validate_project(project: str) -> str:
    normalized = str(project or "").strip()
    if normalized in FORBIDDEN_PROJECTS or normalized not in ALLOWED_PROJECTS:
        raise ValueError("refusing project; pass explicit seolleyeon-final or seolleyeon-festival")
    return normalized


def _validate_mode(mode: str) -> str:
    normalized = str(mode or "plan").strip()
    if normalized not in {"plan", "verify", "apply"}:
        raise ValueError("mode must be plan, verify, or apply")
    return normalized


def _load_config(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"unsupported rollback schemaVersion: {data.get('schemaVersion')}")
    if set(data.get("allowedProjects", [])) != ALLOWED_PROJECTS:
        raise ValueError("rollback config must allow exactly seolleyeon-final and seolleyeon-festival")
    if set(data.get("projects", {})) != ALLOWED_PROJECTS:
        raise ValueError("rollback config must define exactly seolleyeon-final and seolleyeon-festival")
    return data


def _confirmation_token(config: Mapping[str, Any], project: str) -> str:
    template = str(config.get("confirmationTokenTemplate") or "")
    return template.format(project=project)


def _build_steps(
    *,
    project: str,
    project_config: Mapping[str, Any],
    prior_worker_revision: str,
    resume_confirmation_token: str,
) -> list[dict[str, Any]]:
    queue = str(project_config["queueName"])
    queue_location = str(project_config["queueLocation"])
    worker_service = str(project_config["workerService"])
    worker_region = str(project_config["workerRegion"])
    steps: list[dict[str, Any]] = [
        {
            "name": "disable_generation_cost_kill_switch",
            "mutation": True,
            "command": [
                "gcloud",
                "run",
                "services",
                "update",
                worker_service,
                "--project",
                project,
                "--region",
                worker_region,
                "--update-env-vars",
                "AVATAR_GENERATION_ENABLED=false,AVATAR_COST_KILL_SWITCH=true",
            ],
        },
        {
            "name": "pause_queue",
            "mutation": True,
            "command": [
                "gcloud",
                "tasks",
                "queues",
                "pause",
                queue,
                "--project",
                project,
                "--location",
                queue_location,
            ],
        },
        {
            "name": "verify_claim_rate_backlog",
            "mutation": False,
            "command": [
                "gcloud",
                "tasks",
                "queues",
                "describe",
                queue,
                "--project",
                project,
                "--location",
                queue_location,
                "--format",
                "json",
            ],
        },
        {
            "name": "dry_run_stale_lease_recovery",
            "mutation": False,
            "command": [
                sys.executable,
                "scripts/avatar_job_lease_sweeper.py",
                "--firestore_project",
                project,
                "--dry_run",
            ],
        },
        {
            "name": "dry_run_temp_rejected_cleanup",
            "mutation": False,
            "command": [
                sys.executable,
                "scripts/avatar_media_cleanup.py",
                "--mode",
                "expired_candidates",
                "--dry_run",
                "--firestore_project",
                project,
            ],
        },
        {
            "name": "verify_private_source_aggregate_unchanged",
            "mutation": False,
            "command": _source_aggregate_command(project, project_config),
        },
        {
            "name": "optional_route_prior_worker_revision",
            "mutation": bool(prior_worker_revision),
            "optional": True,
            "command": _prior_route_command(
                project=project,
                worker_service=worker_service,
                worker_region=worker_region,
                prior_worker_revision=prior_worker_revision,
            ),
        },
        {
            "name": "resume_requires_separate_confirmation",
            "mutation": bool(resume_confirmation_token),
            "requiresSeparateConfirmation": True,
            "command": [
                "gcloud",
                "tasks",
                "queues",
                "resume",
                queue,
                "--project",
                project,
                "--location",
                queue_location,
            ]
            if resume_confirmation_token == f"RESUME_AVATAR_QUEUE:{project}"
            else [],
        },
    ]
    for step in steps:
        _assert_safe_command(step["command"])
    return steps


def _prior_route_command(
    *,
    project: str,
    worker_service: str,
    worker_region: str,
    prior_worker_revision: str,
) -> list[str]:
    if prior_worker_revision:
        _validate_revision(prior_worker_revision)
        return [
            "gcloud",
            "run",
            "services",
            "update-traffic",
            worker_service,
            "--project",
            project,
            "--region",
            worker_region,
            "--to-revisions",
            f"{prior_worker_revision}=100",
        ]
    return []


def _validate_revision(value: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", value):
        raise ValueError("prior worker revision must be an explicit sanitized revision name")




def _source_aggregate_command(project: str, project_config: Mapping[str, Any]) -> list[str]:
    bucket = f"{project}-{project_config['privateSourceBucketSuffix']}"
    return [
        "gcloud",
        "storage",
        "du",
        "--summarize",
        f"gs://{bucket}",
    ]


def _assert_safe_command(command: Sequence[str]) -> None:
    joined = " ".join(map(str, command))
    if any(term in joined for term in FORBIDDEN_COMMAND_TERMS):
        raise RollbackDrillError("refusing forbidden cleanup operation")
    if ("delete" in command or "rm" in command) and "source" in joined.lower():
        raise RollbackDrillError("refusing source delete command")


def _source_aggregate(
    runner: CommandRunner,
    project: str,
    project_config: Mapping[str, Any],
) -> dict[str, Any]:
    output = runner(_source_aggregate_command(project, project_config))
    parsed = _parse_json(output)
    if isinstance(parsed, Mapping) and parsed:
        return {
            "objectCount": _parse_int(parsed.get("objectCount") or parsed.get("count")),
            "totalBytes": _parse_int(parsed.get("totalBytes") or parsed.get("size")),
        }
    if isinstance(parsed, list) and parsed:
        first = parsed[0] if isinstance(parsed[0], Mapping) else {}
        return {
            "objectCount": _parse_int(first.get("objectCount") or first.get("count")),
            "totalBytes": _parse_int(first.get("totalBytes") or first.get("size")),
        }
    total_bytes = _parse_du_total_bytes(output)
    return {"objectCount": None, "totalBytes": total_bytes}


def _parse_du_total_bytes(output: str) -> Optional[int]:
    match = re.search(r"(?m)^\s*([\d,]+)\s+", str(output or ""))
    return int(match.group(1).replace(",", "")) if match else None


def _run_step(runner: CommandRunner, step: Mapping[str, Any], mode: str) -> str:
    command = step.get("command") or []
    if not command:
        return ""
    if mode == "verify" and step.get("mutation"):
        return ""
    _assert_safe_command(command)
    return runner(command)


def _verification_failure_status(error: BaseException) -> str:
    if isinstance(error, (CommandUnavailableError, FileNotFoundError)):
        return "failed_command_unavailable"
    return "failed_command"


def _execution_record(step: Mapping[str, Any], status: str, output: str = "") -> dict[str, Any]:
    parsed = _parse_json(output)
    return {
        "name": step["name"],
        "status": status,
        "mutating": bool(step["mutation"]),
        "aggregate": _aggregate_only(parsed),
    }


def _public_step(step: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": step["name"],
        "mutating": bool(step["mutation"]),
        "dryRunOnly": step["name"].startswith("dry_run_"),
        "optional": bool(step.get("optional", False)),
        "requiresSeparateConfirmation": bool(step.get("requiresSeparateConfirmation", False)),
    }


def _source_invariant(before: Optional[Mapping[str, Any]], after: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if before is None or after is None:
        return {"verified": False, "unchanged": None}
    before_has_signal = any(before.get(key) is not None for key in ("objectCount", "totalBytes"))
    after_has_signal = any(after.get(key) is not None for key in ("objectCount", "totalBytes"))
    if not before_has_signal or not after_has_signal:
        return {"verified": False, "unchanged": None}
    unchanged = before == after
    return {
        "verified": True,
        "unchanged": unchanged,
        "before": dict(before),
        "after": dict(after),
    }


def _aggregate_only(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    aggregate: dict[str, Any] = {}
    for key in ("objectCount", "count", "totalBytes", "size", "backlogCount", "claimRatePerMinute", "staleLeaseCount", "deletedCount"):
        if key not in value:
            continue
        number = _parse_number(value[key])
        if number is not None:
            aggregate[key] = number
    return aggregate


def _parse_number(value: Any) -> Optional[int | float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    text = str(value).strip()
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_json(output: str) -> Any:
    if not str(output).strip():
        return {}
    try:
        return json.loads(str(output))
    except json.JSONDecodeError:
        return {}


def _parse_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _resolve_executable(executable: str) -> str:
    candidates = [executable]
    if not Path(executable).suffix:
        candidates.append(f"{executable}.cmd")
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise CommandUnavailableError("required rollback drill command is unavailable")


def _run_command(command: Sequence[str]) -> str:
    _assert_safe_command(command)
    resolved_command = list(command)
    if not resolved_command:
        raise RollbackDrillError("rollback drill command is empty")
    resolved_command[0] = _resolve_executable(str(resolved_command[0]))
    try:
        completed = subprocess.run(
            resolved_command,
            check=False,
            capture_output=True,
            text=True,
            shell=False,
        )
    except FileNotFoundError:
        raise CommandUnavailableError("required rollback drill command is unavailable") from None
    if completed.returncode != 0:
        raise RollbackDrillError("rollback drill operation failed")
    return completed.stdout


def format_report(report: Mapping[str, Any]) -> str:
    encoded = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    _assert_report_sanitized(encoded)
    return encoded


def _assert_report_sanitized(encoded: str) -> None:
    forbidden_fragments = ("gs://", "X-Goog-", "Signature=", "token=", "ya29.", "sourcePhotoRefs")
    if any(fragment in encoded for fragment in forbidden_fragments):
        raise RollbackDrillError("refusing to print sensitive rollback report")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Plan, verify, or apply a bounded avatar rollback drill.")
    parser.add_argument("--project", required=True, help="Only seolleyeon-final or seolleyeon-festival.")
    parser.add_argument("--config", type=Path, default=Path("config/avatar-ops/avatar-rollback.json"))
    parser.add_argument("--mode", choices=("plan", "verify", "apply"), default="plan")
    parser.add_argument("--apply", action="store_true", help="Required with --mode apply.")
    parser.add_argument("--confirmation-token", default="")
    parser.add_argument("--prior-worker-revision", default="")
    parser.add_argument("--resume-confirmation-token", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    report = build_rollback_report(
        project=args.project,
        config_path=args.config,
        mode=args.mode,
        apply=args.apply,
        confirmation_token=args.confirmation_token,
        prior_worker_revision=args.prior_worker_revision,
        resume_confirmation_token=args.resume_confirmation_token,
    )
    rendered = format_report(report)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


