#!/usr/bin/env python3
"""Live Cloud Run IAM/OIDC probe for Seolleyeon avatar queue workers."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, NamedTuple, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class HttpResult(NamedTuple):
    status_code: int
    body: str = ""
    error: str = ""


HttpGet = Callable[..., HttpResult]


PRIVATE_KEY_NAMES = {
    "authorization",
    "token",
    "id_token",
    "idToken",
    "sourcePhotoRefs",
    "sourcePhotoIds",
    "source_gcs_uri",
    "idempotencyKey",
}


def redact_sensitive_text(value: Any) -> str:
    text = str(value)
    text = re.sub(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~+/=-]+", "Authorization: Bearer <redacted>", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", text)
    text = re.sub(r"(?i)(id[_-]?token|token)=([^&\s]+)", r"\1=<redacted>", text)
    text = re.sub(r"(?i)(X-Goog-[^=&\s]+|GoogleAccessId|Signature|Expires)=([^&\s]+)", r"\1=<redacted>", text)
    text = re.sub(r"gcs?://[^\s\"']+", "gs://<private-source-ref-redacted>", text)
    text = re.sub(r"seolleyeon-private-source-photos", "<private-source-bucket-redacted>", text)
    return text


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in PRIVATE_KEY_NAMES:
                continue
            sanitized[key_text] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def _healthz_url(worker_url: str) -> str:
    base = worker_url.strip()
    if not base:
        raise ValueError("worker_url is required.")
    parsed = urlparse(base)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("worker_url must be an absolute URL.")
    if parsed.path.rstrip("/").endswith("/readyz"):
        return base
    return urljoin(base.rstrip("/") + "/", "readyz")


def http_get(url: str, *, token: Optional[str] = None, timeout_seconds: int = 10) -> HttpResult:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 - operator CLI target
            body = response.read(4096).decode("utf-8", errors="replace")
            return HttpResult(status_code=int(response.status), body=redact_sensitive_text(body))
    except HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        return HttpResult(status_code=int(exc.code), body=redact_sensitive_text(body))
    except URLError as exc:
        return HttpResult(status_code=0, error=redact_sensitive_text(exc.reason))
    except Exception as exc:
        return HttpResult(status_code=0, error=redact_sensitive_text(exc))


def fetch_gcloud_id_token(
    *,
    audience: Optional[str] = None,
    impersonate_service_account: Optional[str] = None,
) -> str:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd") or "gcloud"
    command = [gcloud, "auth", "print-identity-token"]
    if audience:
        command.append(f"--audiences={audience}")
    if impersonate_service_account:
        command.append(f"--impersonate-service-account={impersonate_service_account}")
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        error = redact_sensitive_text(completed.stderr.strip() or completed.stdout.strip())
        raise RuntimeError(f"gcloud identity token failed: {error}")
    token = completed.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty identity token.")
    return token


def describe_task_creation(task_dry_run: Mapping[str, Any]) -> dict[str, Any]:
    payload = task_dry_run.get("payload")
    payload_summary: dict[str, Any] = {"privatePayloadFieldsOmitted": True}
    if isinstance(payload, Mapping):
        for key in ("jobType", "schemaVersion", "candidateCount", "embeddingVersion"):
            if key in payload:
                payload_summary[key] = _sanitize(payload[key])

    task_url = str(task_dry_run.get("task_url") or "")
    parsed = urlparse(task_url)
    return {
        "mode": "dry_run_description_only",
        "willCreateTask": False,
        "queueName": redact_sensitive_text(task_dry_run.get("queue_name", "")),
        "targetPath": parsed.path or redact_sensitive_text(task_url),
        "oidc": {
            "serviceAccountEmail": redact_sensitive_text(
                task_dry_run.get("service_account_email", "")
            ),
            "audience": redact_sensitive_text(task_dry_run.get("audience", "")),
        },
        "payloadSummary": payload_summary,
    }


def _check_result(name: str, result: HttpResult, ok: bool, message: str) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "status_code": result.status_code,
        "message": redact_sensitive_text(message),
        "body": redact_sensitive_text(result.body[:240]) if result.body else "",
        "error": redact_sensitive_text(result.error) if result.error else "",
    }


def run_live_iam_check(
    *,
    worker_url: str,
    token: Optional[str] = None,
    http_get: HttpGet = http_get,
    timeout_seconds: int = 10,
    require_unauthenticated_rejected: bool = True,
    task_dry_run: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    healthz = _healthz_url(worker_url)
    checks: list[dict[str, Any]] = []

    unauthenticated = http_get(healthz, token=None, timeout_seconds=timeout_seconds)
    unauthenticated_rejected = unauthenticated.status_code in {401, 403}
    unauthenticated_ok = (
        unauthenticated_rejected if require_unauthenticated_rejected else unauthenticated.status_code < 500
    )
    checks.append(
        _check_result(
            "unauthenticated_healthz_rejected",
            unauthenticated,
            unauthenticated_ok,
            (
                "Unauthenticated /healthz was rejected by IAM."
                if unauthenticated_rejected
                else "Unauthenticated /healthz was not rejected; verify Cloud Run IAM."
            ),
        )
    )

    if token:
        authenticated = http_get(healthz, token=token, timeout_seconds=timeout_seconds)
        authenticated_ok = 200 <= authenticated.status_code < 300
        checks.append(
            _check_result(
                "authenticated_healthz",
                authenticated,
                authenticated_ok,
                (
                    "Authenticated /healthz succeeded."
                    if authenticated_ok
                    else "Authenticated /healthz did not return a 2xx response."
                ),
            )
        )
    else:
        checks.append(
            {
                "name": "authenticated_healthz",
                "ok": False,
                "status_code": 0,
                "message": "No ID token was provided or generated.",
                "body": "",
                "error": "",
            }
        )

    report: dict[str, Any] = {
        "ok": all(check["ok"] for check in checks),
        "worker_url": redact_sensitive_text(worker_url),
        "healthz_url": redact_sensitive_text(healthz),
        "checks": checks,
    }
    if task_dry_run is not None:
        report["task_dry_run"] = describe_task_creation(task_dry_run)
    return _sanitize(report)


def format_report(report: Mapping[str, Any]) -> str:
    return json.dumps(_sanitize(report), ensure_ascii=False, indent=2, sort_keys=True)


def _load_payload_json(path: Optional[str]) -> Optional[dict[str, Any]]:
    if not path:
        return None
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("--payload_json must contain a JSON object.")
    return dict(raw)


def _token_from_args(args: argparse.Namespace) -> Optional[str]:
    if args.token:
        return args.token.strip()
    if args.token_file:
        return Path(args.token_file).read_text(encoding="utf-8").strip()
    if args.use_gcloud_token:
        return fetch_gcloud_id_token(
            audience=None if args.gcloud_token_without_audience else args.audience or args.worker_url,
            impersonate_service_account=args.impersonate_service_account,
        )
    return None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Probe Cloud Run IAM/OIDC for avatar workers.")
    parser.add_argument("--worker_url", required=True)
    parser.add_argument("--token", help="Provided ID token. The token is never printed.")
    parser.add_argument("--token_file", help="File containing an ID token. The token is never printed.")
    parser.add_argument("--use_gcloud_token", action="store_true")
    parser.add_argument("--audience")
    parser.add_argument(
        "--gcloud_token_without_audience",
        action="store_true",
        help="Use gcloud auth print-identity-token without --audiences for user-account Cloud Run checks.",
    )
    parser.add_argument("--impersonate_service_account")
    parser.add_argument("--timeout_seconds", type=int, default=10)
    parser.add_argument("--skip_unauthenticated_check", action="store_true")
    parser.add_argument("--describe_task_dry_run", action="store_true")
    parser.add_argument("--queue_name")
    parser.add_argument("--task_url")
    parser.add_argument("--service_account_email")
    parser.add_argument("--payload_json")
    parser.add_argument("--output_report_json")
    args = parser.parse_args(argv)

    token = _token_from_args(args)
    task_dry_run = None
    if args.describe_task_dry_run:
        task_dry_run = {
            "queue_name": args.queue_name or "",
            "task_url": args.task_url or args.worker_url.rstrip("/") + "/tasks/avatar-generation",
            "service_account_email": args.service_account_email or "",
            "audience": args.audience or args.worker_url,
            "payload": _load_payload_json(args.payload_json) or {},
        }
    report = run_live_iam_check(
        worker_url=args.worker_url,
        token=token,
        timeout_seconds=args.timeout_seconds,
        require_unauthenticated_rejected=not args.skip_unauthenticated_check,
        task_dry_run=task_dry_run,
    )
    rendered = format_report(report)
    if args.output_report_json:
        Path(args.output_report_json).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
