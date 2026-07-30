#!/usr/bin/env python3
"""Invoke one IAM-protected avatar worker drain pass without exposing payload refs.

Default mode is a dry-run report. Use --apply to actually POST to the worker.
The request body is empty because the worker claims queued avatarJobs itself.
"""

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


HttpPost = Callable[..., HttpResult]


SENSITIVE_KEYS = {
    "authorization",
    "token",
    "id_token",
    "idToken",
    "sourcePhotoRefs",
    "sourcePhotoIds",
    "source_gcs_uri",
    "idempotencyKey",
    "gcsUri",
    "signedUrl",
    "previewUrl",
}


def redact_sensitive_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(
        r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~+/=-]+",
        "Authorization: Bearer <redacted>",
        text,
    )
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", text)
    text = re.sub(r"(?i)(id[_-]?token|token)=([^&\s]+)", r"\1=<redacted>", text)
    text = re.sub(
        r"(?i)(X-Goog-[^=&\s]+|GoogleAccessId|Signature|Expires|X-Amz-[^=&\s]+)=([^&\s]+)",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(r"g(?:s|cs)://[^\s\"']+", "gs://<private-ref-redacted>", text)
    text = re.sub(
        r"seolleyeon(?:-final)?-(?:private-source-photos|avatar-temp)",
        "<private-bucket-redacted>",
        text,
        flags=re.IGNORECASE,
    )
    return text[:4000]


def sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in SENSITIVE_KEYS:
                continue
            sanitized[key_text] = sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def drain_url(worker_url: str) -> str:
    base = worker_url.strip()
    if not base:
        raise ValueError("worker_url is required.")
    parsed = urlparse(base)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("worker_url must be an absolute URL.")
    if parsed.path.rstrip("/").endswith("/tasks/avatar-generation/drain"):
        return base
    return urljoin(base.rstrip("/") + "/", "tasks/avatar-generation/drain")


def fetch_gcloud_id_token(
    *,
    audience: Optional[str] = None,
    impersonate_service_account: Optional[str] = None,
) -> str:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if not gcloud:
        raise RuntimeError("gcloud was not found in PATH.")
    command = [gcloud, "auth", "print-identity-token"]
    if audience:
        command.append(f"--audiences={audience}")
    if impersonate_service_account:
        command.append(f"--impersonate-service-account={impersonate_service_account}")
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        error = redact_sensitive_text(completed.stderr.strip() or completed.stdout.strip())
        raise RuntimeError(f"gcloud identity token failed: {error}")
    token = completed.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty identity token.")
    return token


def http_post_json(
    url: str,
    *,
    token: str,
    timeout_seconds: int = 60,
) -> HttpResult:
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    request = Request(url, data=b"{}", headers=headers, method="POST")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 - operator CLI target
            body = response.read(8192).decode("utf-8", errors="replace")
            return HttpResult(status_code=int(response.status), body=body)
    except HTTPError as exc:
        body = exc.read(8192).decode("utf-8", errors="replace")
        return HttpResult(status_code=int(exc.code), body=body)
    except URLError as exc:
        return HttpResult(status_code=0, error=redact_sensitive_text(exc.reason))
    except Exception as exc:
        return HttpResult(status_code=0, error=redact_sensitive_text(exc))


def _parse_body(body: str) -> Any:
    if not body:
        return ""
    try:
        return sanitize(json.loads(body))
    except json.JSONDecodeError:
        return redact_sensitive_text(body)


def build_drain_report(
    *,
    worker_url: str,
    apply: bool,
    token: Optional[str] = None,
    http_post: HttpPost = http_post_json,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    endpoint = drain_url(worker_url)
    if not apply:
        return {
            "ok": True,
            "applied": False,
            "wouldPost": True,
            "endpointPath": urlparse(endpoint).path,
            "privacy": {
                "sourceRefsEmitted": False,
                "signedUrlsEmitted": False,
                "tokensEmitted": False,
            },
        }
    if not token:
        raise ValueError("--apply requires an ID token from --use_gcloud_token, --token, or --token_file.")
    result = http_post(endpoint, token=token, timeout_seconds=timeout_seconds)
    ok = 200 <= int(result.status_code) < 300
    return {
        "ok": ok,
        "applied": True,
        "endpointPath": urlparse(endpoint).path,
        "statusCode": int(result.status_code),
        "body": _parse_body(result.body),
        "error": redact_sensitive_text(result.error),
        "privacy": {
            "sourceRefsEmitted": False,
            "signedUrlsEmitted": False,
            "tokensEmitted": False,
        },
    }


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


def _write_report(report: Mapping[str, Any], path: Optional[str]) -> None:
    encoded = json.dumps(sanitize(report), ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        Path(path).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one avatar worker drain pass after staging worker deployment."
    )
    parser.add_argument("--worker_url", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--token", help="Provided ID token. The token is never printed.")
    parser.add_argument("--token_file", help="File containing an ID token. The token is never printed.")
    parser.add_argument("--use_gcloud_token", action="store_true")
    parser.add_argument("--audience")
    parser.add_argument(
        "--gcloud_token_without_audience",
        action="store_true",
        help="Use gcloud auth print-identity-token without --audiences for user-account smoke checks.",
    )
    parser.add_argument("--impersonate_service_account")
    parser.add_argument("--timeout_seconds", type=int, default=900)
    parser.add_argument("--output_report_json")
    args = parser.parse_args(argv)

    token = _token_from_args(args) if args.apply else None
    report = build_drain_report(
        worker_url=args.worker_url,
        apply=bool(args.apply),
        token=token,
        timeout_seconds=args.timeout_seconds,
    )
    _write_report(report, args.output_report_json)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
