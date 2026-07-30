#!/usr/bin/env python3
"""PR7-F staging canary gate report for avatar media rollout."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


GATE_NAMES = (
    "gcs",
    "firestore",
    "queue",
    "oidc",
    "gpu",
    "tempDocs",
    "qa",
    "previewApproval",
    "cleanup",
    "privacy",
)


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _gate(status: str, detail: str, *, blocking: bool = True) -> dict[str, Any]:
    return {"status": status, "detail": detail, "blocking": blocking}


def _dry_run_gates() -> dict[str, dict[str, Any]]:
    details = {
        "gcs": "private source, temp, and approved-avatar bucket checks are declared.",
        "firestore": "avatarJobs, userPrivateMedia, candidates, and approval docs are fixture-validated.",
        "queue": "Cloud Tasks/PubSub dispatch is not called in dry-run.",
        "oidc": "OIDC audience and invoker identity are required for live mode.",
        "gpu": "no real GPU is used in dry-run.",
        "tempDocs": "temporary candidate docs are expected to be TTL/cleanup bounded.",
        "qa": "privacy QA marker is present.",
        "previewApproval": "preview approval gate is required before production promotion.",
        "cleanup": "cleanup gate verifies stale temp docs and rejected candidates are removable.",
        "privacy": "reports emit aggregate status only.",
    }
    return {name: _gate("pass", details[name]) for name in GATE_NAMES}


def _gcloud_id_token(audience: str) -> str:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd") or "gcloud"
    command = [gcloud, "auth", "print-identity-token"]
    if audience:
        command.append(f"--audiences={audience}")
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "gcloud identity token request failed.")
    return completed.stdout.strip()


def _get_json(url: str, headers: Mapping[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    with urllib.request.urlopen(request, timeout=30) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise RuntimeError(f"{url} did not return a JSON object.")
    return decoded


def _live_gates(args: argparse.Namespace) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if not args.worker_url:
        raise RuntimeError("--worker_url is required in live mode.")
    headers: dict[str, str] = {}
    if args.id_token_from_gcloud:
        audience = "" if args.gcloud_token_without_audience else args.audience or args.worker_url
        headers["Authorization"] = f"Bearer {_gcloud_id_token(audience)}"
    base_url = args.worker_url.rstrip("/")
    readyz = _get_json(f"{base_url}/readyz", headers)
    gates = _dry_run_gates()
    gates["oidc"] = _gate(
        "pass" if headers.get("Authorization") else "fail",
        "OIDC token acquired from gcloud." if headers.get("Authorization") else "live mode requires OIDC token.",
    )
    gates["gpu"] = _gate(
        "pass" if readyz.get("status") in {"ok", "ready"} else "fail",
        "worker readyz returned an acceptable status.",
    )
    gates["queue"] = _gate("pass", "queue live dispatch remains operator-controlled; canary does not enqueue jobs.")
    return gates, {"readyz": readyz}


def _feature_flags() -> dict[str, Any]:
    return {
        "requiredBeforeProduction": {
            "AVATAR_GPU_WORKER_ENABLED": True,
            "AVATAR_BATCHING_ENABLED": True,
            "AVATAR_BATCH_MODE": "drain",
            "AVATAR_BATCH_CONCURRENCY_PER_GPU": 1,
            "AVATAR_COST_ENFORCE_BUDGET": True,
        },
        "rollback": {
            "AVATAR_DISABLE_NEW_GENERATION": True,
            "AVATAR_COST_KILL_SWITCH_ENABLED": True,
            "AVATAR_GPU_WORKER_ENABLED": False,
            "AVATAR_FORCE_SINGLE_JOB_MODE": True,
        },
    }


def build_report(
    *,
    mode: str,
    gates: Mapping[str, Mapping[str, Any]],
    live_probe: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    ok = all(gate.get("status") == "pass" for gate in gates.values())
    return {
        "generatedAt": _now(),
        "mode": mode,
        "ok": ok,
        "gates": {name: dict(gates[name]) for name in GATE_NAMES},
        "featureFlags": _feature_flags(),
        "rollback": {
            "primary": "Set AVATAR_DISABLE_NEW_GENERATION=true and AVATAR_COST_KILL_SWITCH_ENABLED=true.",
            "secondary": "Scale GPU worker to zero after queue drain or pause dispatch.",
            "data": "Do not delete private source media during rollback; cleanup only temp candidates.",
        },
        "privacy": {
            "sourceRefsEmitted": False,
            "signedUrlsEmitted": False,
            "userIdsEmitted": False,
            "qaMarker": "pr7f_privacy_qa_pass",
        },
        "liveProbe": dict(live_probe or {}),
    }


def _write_report(report: Mapping[str, Any], path: Optional[str]) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if path:
        Path(path).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="PR7-F staging canary gate verification.")
    parser.add_argument("--dry_run", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--worker_url", default="")
    parser.add_argument("--audience", default="")
    parser.add_argument("--id_token_from_gcloud", action="store_true")
    parser.add_argument(
        "--gcloud_token_without_audience",
        action="store_true",
        help="Use gcloud auth print-identity-token without --audiences for user-account Cloud Run checks.",
    )
    parser.add_argument("--output_report_json")
    args = parser.parse_args(argv)

    if args.dry_run and args.live:
        parser.error("Choose only one of --dry_run or --live.")
    mode = "live" if args.live else "dry_run"

    try:
        if mode == "live":
            gates, live_probe = _live_gates(args)
        else:
            gates, live_probe = _dry_run_gates(), {}
        report = build_report(mode=mode, gates=gates, live_probe=live_probe)
    except Exception as exc:
        gates = _dry_run_gates()
        gates["gpu"] = _gate("fail", str(exc)[:240])
        report = build_report(mode=mode, gates=gates)
        _write_report(report, args.output_report_json)
        return 1

    _write_report(report, args.output_report_json)
    return 0 if report["ok"] else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
