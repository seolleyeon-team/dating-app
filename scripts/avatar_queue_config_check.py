#!/usr/bin/env python3
"""Validate production queue configuration for avatar generation fanout."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import urlparse


PRODUCTION_ENVS = {"production", "prod"}
QUEUE_MODES = {"dry_run", "cloud_tasks", "pubsub"}


def _env_text(env: Mapping[str, str], name: str, default: str = "") -> str:
    return str(env.get(name, default) or "").strip()


def _env_bool(env: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = _env_text(env, name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "y", "on"}


def _is_production(env: Mapping[str, str]) -> bool:
    return (
        _env_text(env, "ENVIRONMENT").lower() in PRODUCTION_ENVS
        or _env_text(env, "NODE_ENV").lower() == "production"
    )


def _issue(severity: str, field: str, message: str) -> dict[str, str]:
    return {"severity": severity, "field": field, "message": message}


def _require_present(
    issues: list[dict[str, str]],
    env: Mapping[str, str],
    name: str,
    *,
    production: bool,
    message: Optional[str] = None,
) -> None:
    if _env_text(env, name):
        return
    severity = "error" if production else "warning"
    issues.append(_issue(severity, name, message or f"{name} is required."))


def _parse_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _require_int(
    issues: list[dict[str, str]],
    env: Mapping[str, str],
    name: str,
    *,
    production: bool,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> Optional[int]:
    raw = _env_text(env, name)
    if not raw:
        issues.append(
            _issue(
                "error" if production else "warning",
                name,
                f"{name} should be set explicitly for queue retry and dispatch control.",
            )
        )
        return None
    parsed = _parse_int(raw)
    if parsed is None:
        issues.append(_issue("error", name, f"{name} must be an integer."))
        return None
    if minimum is not None and parsed < minimum:
        issues.append(_issue("error", name, f"{name} must be >= {minimum}."))
    if maximum is not None and parsed > maximum:
        issues.append(_issue("error", name, f"{name} must be <= {maximum}."))
    return parsed


def _validate_https_url(
    issues: list[dict[str, str]],
    env: Mapping[str, str],
    name: str,
    *,
    production: bool,
) -> None:
    value = _env_text(env, name)
    if not value:
        return
    parsed = urlparse(value)
    if production and parsed.scheme != "https":
        issues.append(_issue("error", name, f"{name} must use https in production."))
    if not parsed.scheme or not parsed.netloc:
        issues.append(_issue("error", name, f"{name} must be an absolute URL."))
    if parsed.netloc.upper() in {"AVATAR_WORKER", "CLIP_WORKER"} or "<" in value or ">" in value:
        issues.append(_issue("error", name, f"{name} still contains a placeholder URL."))


def _validate_cloud_tasks(
    issues: list[dict[str, str]],
    env: Mapping[str, str],
    *,
    production: bool,
) -> None:
    clip_enabled = _env_bool(env, "CLIP_EMBEDDING_QUEUE_ENABLED", default=True)
    for name in (
        "CLOUD_TASKS_PROJECT",
        "GCP_LOCATION",
        "AVATAR_GENERATION_QUEUE_NAME",
        "AVATAR_GENERATION_TASK_URL",
    ):
        _require_present(issues, env, name, production=production)
    if clip_enabled:
        for name in ("CLIP_EMBEDDING_QUEUE_NAME", "CLIP_EMBEDDING_TASK_URL"):
            _require_present(issues, env, name, production=production)

    _require_present(
        issues,
        env,
        "TASK_INVOKER_SERVICE_ACCOUNT",
        production=production,
        message=(
            "TASK_INVOKER_SERVICE_ACCOUNT is required so Cloud Tasks can mint "
            "OIDC tokens for Cloud Run run.invoker."
        ),
    )
    if production and not _env_text(env, "TASK_OIDC_AUDIENCE"):
        issues.append(
            _issue(
                "warning",
                "TASK_OIDC_AUDIENCE",
                "Set TASK_OIDC_AUDIENCE when the Cloud Run service expects a custom audience.",
            )
        )
    _validate_https_url(issues, env, "AVATAR_GENERATION_TASK_URL", production=production)
    if clip_enabled:
        _validate_https_url(issues, env, "CLIP_EMBEDDING_TASK_URL", production=production)


def _validate_pubsub(
    issues: list[dict[str, str]],
    env: Mapping[str, str],
    *,
    production: bool,
) -> None:
    for name in ("CLOUD_TASKS_PROJECT", "AVATAR_GENERATION_TOPIC", "CLIP_EMBEDDING_TOPIC"):
        _require_present(issues, env, name, production=production)
    _require_present(
        issues,
        env,
        "PUBSUB_DEAD_LETTER_TOPIC",
        production=production,
        message="PUBSUB_DEAD_LETTER_TOPIC is required for poison-message isolation.",
    )
    if production and not (
        _env_text(env, "PUBSUB_PUSH_SERVICE_ACCOUNT")
        or _env_text(env, "TASK_INVOKER_SERVICE_ACCOUNT")
    ):
        issues.append(
            _issue(
                "error",
                "PUBSUB_PUSH_SERVICE_ACCOUNT",
                "Pub/Sub push to Cloud Run must use an OIDC service account with roles/run.invoker.",
            )
        )


def _validate_retry_controls(
    issues: list[dict[str, str]],
    env: Mapping[str, str],
    *,
    production: bool,
) -> None:
    max_dispatch = _require_int(
        issues,
        env,
        "AVATAR_QUEUE_MAX_DISPATCHES_PER_SECOND",
        production=production,
        minimum=1,
        maximum=5,
    )
    max_concurrent = _require_int(
        issues,
        env,
        "AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES",
        production=production,
        minimum=1,
        maximum=8,
    )
    gpu_max = _require_int(
        issues,
        env,
        "AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS",
        production=production,
        minimum=1,
        maximum=4,
    )
    deadline = _require_int(
        issues,
        env,
        "AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS",
        production=production,
        minimum=60,
        maximum=1800,
    )
    max_attempts = _require_int(
        issues,
        env,
        "AVATAR_QUEUE_MAX_ATTEMPTS",
        production=production,
        minimum=2,
        maximum=5,
    )
    min_backoff = _require_int(
        issues,
        env,
        "AVATAR_QUEUE_MIN_BACKOFF_SECONDS",
        production=production,
        minimum=5,
        maximum=600,
    )
    max_backoff = _require_int(
        issues,
        env,
        "AVATAR_QUEUE_MAX_BACKOFF_SECONDS",
        production=production,
        minimum=30,
        maximum=3600,
    )
    _require_int(
        issues,
        env,
        "AVATAR_QUEUE_MAX_DOUBLINGS",
        production=production,
        minimum=0,
        maximum=16,
    )

    if max_concurrent is not None and gpu_max is not None and max_concurrent > gpu_max:
        issues.append(
            _issue(
                "error",
                "AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES",
                (
                    "AVATAR_QUEUE_MAX_CONCURRENT_DISPATCHES creates unbounded GPU fanout; "
                    "keep it <= AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS."
                ),
            )
        )
    if max_dispatch is not None and max_concurrent is not None and max_dispatch > max_concurrent:
        issues.append(
            _issue(
                "warning",
                "AVATAR_QUEUE_MAX_DISPATCHES_PER_SECOND",
                "Dispatch rate is above concurrency; bursts may pile up against a single GPU worker.",
            )
        )
    if deadline is not None and deadline < 600:
        issues.append(
            _issue(
                "warning",
                "AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS",
                "Avatar generation jobs usually need a deadline near 900 seconds.",
            )
        )
    if max_attempts is not None and max_attempts > 3:
        issues.append(
            _issue(
                "warning",
                "AVATAR_QUEUE_MAX_ATTEMPTS",
                "High retry counts can multiply GPU cost; prefer dead-letter triage after 3 attempts.",
            )
        )
    if min_backoff is not None and max_backoff is not None and min_backoff > max_backoff:
        issues.append(
            _issue(
                "error",
                "AVATAR_QUEUE_MIN_BACKOFF_SECONDS",
                "AVATAR_QUEUE_MIN_BACKOFF_SECONDS must be <= AVATAR_QUEUE_MAX_BACKOFF_SECONDS.",
            )
        )


def validate_queue_config(env: Mapping[str, str] = os.environ) -> dict[str, Any]:
    env = {str(key): str(value) for key, value in env.items() if value is not None}
    production = _is_production(env)
    mode = _env_text(env, "JOB_QUEUE_MODE", "dry_run").lower()
    issues: list[dict[str, str]] = []

    if mode not in QUEUE_MODES:
        issues.append(
            _issue("error", "JOB_QUEUE_MODE", "JOB_QUEUE_MODE must be dry_run, cloud_tasks, or pubsub.")
        )
    if production and mode == "dry_run":
        issues.append(
            _issue("error", "JOB_QUEUE_MODE", "Production must use cloud_tasks or pubsub, not dry_run.")
        )
    if mode == "cloud_tasks":
        _validate_cloud_tasks(issues, env, production=production)
    elif mode == "pubsub":
        _validate_pubsub(issues, env, production=production)

    _validate_retry_controls(issues, env, production=production)

    if not _env_text(env, "AVATAR_QUEUE_DEAD_LETTER_TOPIC") and mode == "cloud_tasks":
        issues.append(
            _issue(
                "warning",
                "AVATAR_QUEUE_DEAD_LETTER_TOPIC",
                "Document a dead-letter or quarantine queue for jobs that exhaust Cloud Tasks retries.",
            )
        )

    return {
        "ok": not any(issue["severity"] == "error" for issue in issues),
        "environment": _env_text(env, "ENVIRONMENT") or _env_text(env, "NODE_ENV") or "unknown",
        "mode": mode,
        "issues": issues,
        "guidance": {
            "avatarQueue": _env_text(env, "AVATAR_GENERATION_QUEUE_NAME", "avatar-generation"),
            "clipQueue": _env_text(env, "CLIP_EMBEDDING_QUEUE_NAME", "clip-embedding"),
            "recommendedRegion": _env_text(env, "GCP_LOCATION", "asia-northeast3"),
            "cloudRunRole": "roles/run.invoker",
            "maxGpuConcurrencyEnv": "AVATAR_QUEUE_GPU_MAX_CONCURRENT_JOBS",
        },
    }


def _write_report(report: Mapping[str, Any], path: Optional[str]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        Path(path).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def _load_env_file(path: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate avatar queue production config.")
    parser.add_argument("--env_json", help="Optional JSON file of env values to validate.")
    parser.add_argument("--env_file", help="Optional dotenv-style env file to validate.")
    parser.add_argument("--output_report_json")
    args = parser.parse_args(argv)

    if args.env_json and args.env_file:
        parser.error("Use only one of --env_json or --env_file.")

    if args.env_file:
        env = _load_env_file(args.env_file)
    elif args.env_json:
        env = json.loads(Path(args.env_json).read_text(encoding="utf-8"))
        if not isinstance(env, Mapping):
            raise SystemExit("--env_json must contain a JSON object.")
    else:
        env = os.environ

    report = validate_queue_config(env)
    _write_report(report, args.output_report_json)
    return 0 if report["ok"] else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
