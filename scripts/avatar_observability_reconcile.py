#!/usr/bin/env python3
"""Plan, verify, or apply avatar observability resources with gcloud."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence


ALLOWED_PROJECTS = {"seolleyeon-final", "seolleyeon-festival"}
FORBIDDEN_PROJECTS = {"", "default", "seolleyeon"}
SCHEMA_VERSION = "avatar_observability_reconcile_v1"
LOW_CARDINALITY_LABELS = {"service", "event_name", "status", "severity", "component", "signal"}
SENSITIVE_FRAGMENTS = ("token", "secret", "private", "signedurl", "sourceRef", "source_ref", "gs://")
NOT_FOUND_FRAGMENTS = ("not found", "does not exist", "404")
WINDOWS = os.name == "nt"


class CommandResult:
    __slots__ = ("returncode", "stdout", "stderr")

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


CommandRunner = Callable[[Sequence[str]], Any]


def load_config(config_path: Path) -> dict[str, Any]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"unsupported schemaVersion: {data.get('schemaVersion')}")
    _validate_config(data)
    return data


def reconcile(
    *,
    config_path: Path,
    project: str,
    mode: str = "plan",
    notification_channels: Sequence[str] = (),
    runner: Optional[CommandRunner] = None,
) -> dict[str, Any]:
    project = _validate_project(project)
    if mode not in {"plan", "verify", "apply"}:
        raise ValueError(f"unsupported mode: {mode}")
    config = load_config(Path(config_path))
    operations = build_operations(config, project=project, notification_channels=notification_channels)
    report: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "project": project,
        "mode": mode,
        "plannedOperations": (
            operations if mode == "plan" else [_operation_summary(operation) for operation in operations]
        ),
        "mutations": [],
    }
    if mode == "plan":
        return report

    command_runner = runner or run_command
    verification_records: list[tuple[dict[str, Any], CommandResult]] = []
    verification: list[dict[str, Any]] = []
    for operation in operations:
        result = _coerce_command_result(
            command_runner(_describe_command(operation, project))
        )
        verification_records.append((operation, result))
        verification.append(_verification_entry(operation, result))
    report["verification"] = verification
    if mode == "verify":
        return report

    for (operation, _), verified in zip(verification_records, verification):
        exists = verified["exists"]
        if exists is None:
            report["mutations"].append(
                {
                    "kind": operation["kind"],
                    "name": operation["name"],
                    "action": "skipped",
                    "reason": "verification_error",
                }
            )
            continue
        if (
            exists
            and operation["kind"] == "alertPolicy"
            and verified.get("notificationChannelsPresent")
            and not verified.get("notificationChannelsValid")
        ):
            report["mutations"].append(
                {
                    "kind": operation["kind"],
                    "name": operation["name"],
                    "action": "skipped",
                    "reason": "remote_notification_channels_unverifiable",
                }
            )
            continue
        resource_name = str(verified.get("resourceName") or "")
        if exists and operation["kind"] in {"alertPolicy", "dashboard"} and not resource_name:
            report["mutations"].append(
                {
                    "kind": operation["kind"],
                    "name": operation["name"],
                    "action": "skipped",
                    "reason": "remote_resource_name_missing",
                }
            )
            continue
        command = _mutation_command(
            operation,
            project=project,
            exists=exists,
            resource_name=resource_name,
            etag=str(verified.get("etag") or ""),
            preserved_notification_channels=verified.get("notificationChannels", ()),
        )
        cleanup_ok = True
        try:
            result = _coerce_command_result(command_runner(command))
        finally:
            cleanup_ok = _cleanup_json_file(command)
        report["mutations"].append(
            {
                "kind": operation["kind"],
                "name": operation["name"],
                "action": "update" if exists else "create",
                "command": redact_command(command),
                "exitCode": result.returncode,
                "errorCode": _command_error_code(result),
                "tempFileCleanup": cleanup_ok,
            }
        )
    report["ok"] = bool(report["mutations"]) and all(
        item.get("action") != "skipped"
        and item.get("exitCode") == 0
        and item.get("tempFileCleanup") is True
        for item in report["mutations"]
    )
    return report

def build_operations(
    config: Mapping[str, Any],
    *,
    project: str,
    notification_channels: Sequence[str] = (),
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for metric in config["logMetrics"]:
        name = metric["name"]
        body = {
            "name": name,
            "description": metric["description"],
            "filter": metric["filter"],
            "metricDescriptor": {
                "metricKind": "DELTA",
                "valueType": "INT64",
                "unit": "1",
                "labels": [
                    {"key": key, "valueType": "STRING", "description": key}
                    for key in sorted(metric.get("labels", {}))
                ],
            },
            "labelExtractors": {
                key: f"EXTRACT({field})"
                for key, field in metric.get("labels", {}).items()
            },
        }
        operations.append({"kind": "logMetric", "name": name, "action": "create", "body": body})

    for policy in config["alertPolicies"]:
        policy_id = f"avatar-{policy['name'].replace('_', '-')}"
        body = _alert_policy_body(policy, project=project, notification_channels=notification_channels)
        operations.append({"kind": "alertPolicy", "name": policy_id, "action": "create", "body": body})

    dashboard = config["dashboard"]
    operations.append(
        {
            "kind": "dashboard",
            "name": dashboard["name"],
            "action": "create",
            "body": _dashboard_body(dashboard, project=project),
        }
    )
    return operations


def redact_command(command: Sequence[str]) -> list[str]:
    clean: list[str] = []
    redact_next = False
    for part in command:
        text = str(part)
        if redact_next:
            clean.append("[TEMP_FILE]")
            redact_next = False
            continue
        lowered = text.lower()
        if any(fragment.lower() in lowered for fragment in SENSITIVE_FRAGMENTS):
            clean.append("[REDACTED]")
        else:
            clean.append(text)
        redact_next = text in {"--policy-from-file", "--config-from-file"}
    return clean


def run_command(command: Sequence[str]) -> CommandResult:
    resolved = _resolve_command(command)
    completed = subprocess.run(
        resolved,
        check=False,
        capture_output=True,
        text=True,
        shell=False,
    )
    return CommandResult(
        returncode=int(completed.returncode),
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def _resolve_command(command: Sequence[str]) -> list[str]:
    resolved = [str(part) for part in command]
    if not resolved:
        raise ValueError("command must not be empty")
    if resolved[0].lower() != "gcloud":
        return resolved

    candidates = ("gcloud.cmd", "gcloud.exe", "gcloud") if WINDOWS else ("gcloud",)
    for candidate in candidates:
        executable = shutil.which(candidate)
        if executable:
            resolved[0] = executable
            return resolved
    raise FileNotFoundError("gcloud executable was not found on PATH")


def _coerce_command_result(result: Any) -> CommandResult:
    if isinstance(result, CommandResult):
        return result
    if isinstance(result, int):
        return CommandResult(returncode=result)
    return CommandResult(
        returncode=int(result.returncode),
        stdout=str(result.stdout or ""),
        stderr=str(result.stderr or ""),
    )


def _operation_summary(operation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "kind": operation["kind"],
        "name": operation["name"],
        "action": operation["action"],
    }


def _verification_entry(
    operation: Mapping[str, Any],
    result: CommandResult,
) -> dict[str, Any]:
    entry = {
        "kind": operation["kind"],
        "name": operation["name"],
        "exists": None,
        "drift": None,
        "status": "error",
    }
    if result.returncode != 0:
        diagnostic = f"{result.stdout}\n{result.stderr}".lower()
        if any(fragment in diagnostic for fragment in NOT_FOUND_FRAGMENTS):
            entry.update(exists=False, drift=True, status="missing")
        return entry

    try:
        remote_body = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        entry.update(exists=True, status="unverifiable")
        return entry
    if isinstance(remote_body, list):
        display_name = str(operation.get("body", {}).get("displayName") or "")
        matches = [
            item
            for item in remote_body
            if isinstance(item, Mapping) and str(item.get("displayName") or "") == display_name
        ]
        if not matches:
            entry.update(exists=False, drift=True, status="missing")
            return entry
        if len(matches) != 1:
            entry.update(status="ambiguous")
            return entry
        remote_body = matches[0]
    if not isinstance(remote_body, Mapping):
        entry.update(exists=True, status="unverifiable")
        return entry

    resource_name = _safe_monitoring_resource_name(remote_body.get("name"))
    if resource_name:
        entry["resourceName"] = resource_name
    etag = _safe_etag(remote_body.get("etag"))
    if etag:
        entry["etag"] = etag
    if operation["kind"] == "alertPolicy":
        raw_channels = remote_body.get("notificationChannels")
        raw_channel_list = raw_channels if isinstance(raw_channels, list) else []
        safe_channels = [
            channel
            for channel in (
                _safe_notification_channel_name(value) for value in raw_channel_list
            )
            if channel
        ]
        entry["notificationChannels"] = safe_channels
        entry["notificationChannelsPresent"] = bool(raw_channels)
        entry["notificationChannelsValid"] = (
            raw_channels is None
            or (
                isinstance(raw_channels, list)
                and len(safe_channels) == len(raw_channel_list)
            )
        )

    desired_body = dict(operation["body"])
    desired_body.pop("name", None)
    projected_remote = _project_remote_body(remote_body, desired_body)
    drift = projected_remote != desired_body
    entry.update(
        exists=True,
        drift=drift,
        status="drifted" if drift else "in_sync",
    )
    if drift:
        entry["driftFields"] = _diff_paths(projected_remote, desired_body)
    return entry


def _safe_monitoring_resource_name(value: Any) -> str:
    text = str(value or "").strip()
    pattern = r"projects/[A-Za-z0-9_.-]+/(?:alertPolicies|dashboards)/[A-Za-z0-9_.-]+"
    return text if re.fullmatch(pattern, text) else ""


def _safe_etag(value: Any) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"[A-Za-z0-9_./+=-]{1,256}", text) else ""


def _safe_notification_channel_name(value: Any) -> str:
    text = str(value or "").strip()
    pattern = r"projects/[A-Za-z0-9_.-]+/notificationChannels/[A-Za-z0-9_.-]+"
    return text if re.fullmatch(pattern, text) else ""


def _diff_paths(actual: Any, expected: Any, prefix: str = "") -> list[str]:
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        paths: list[str] = []
        for key, expected_value in expected.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_diff_paths(actual.get(key), expected_value, child))
        return paths
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        paths = []
        for index, (actual_value, expected_value) in enumerate(zip(actual, expected)):
            child = f"{prefix}[{index}]"
            paths.extend(_diff_paths(actual_value, expected_value, child))
        return paths
    return [] if actual == expected else [prefix or "root"]


def _project_remote_body(remote: Any, desired: Any) -> Any:
    if isinstance(desired, Mapping):
        if not isinstance(remote, Mapping):
            return remote
        projected: dict[str, Any] = {}
        for key, value in desired.items():
            remote_value = remote.get(key)
            if remote_value is None and key in {"thresholdValue", "xPos", "yPos"} and value == 0:
                remote_value = value
            if remote_value is None and key == "valueType" and value == "STRING":
                remote_value = value
            projected[key] = _project_remote_body(remote_value, value)
        return projected
    if isinstance(desired, list):
        if not isinstance(remote, list):
            return remote
        if all(isinstance(item, Mapping) and item.get("key") for item in desired):
            remote_by_key = {
                item.get("key"): item
                for item in remote
                if isinstance(item, Mapping) and item.get("key")
            }
            desired_keys = {item.get("key") for item in desired}
            if set(remote_by_key) == desired_keys:
                return [
                    _project_remote_body(remote_by_key[item["key"]], item)
                    for item in desired
                ]
        return [
            _project_remote_body(remote_value, desired_value)
            for remote_value, desired_value in zip(remote, desired)
        ] if len(remote) == len(desired) else remote
    return remote


def _validate_project(project: str) -> str:
    normalized = str(project or "").strip()
    if normalized in FORBIDDEN_PROJECTS or normalized not in ALLOWED_PROJECTS:
        raise ValueError(
            "refusing project; pass explicit seolleyeon-final or seolleyeon-festival"
        )
    return normalized


def _validate_config(data: Mapping[str, Any]) -> None:
    metrics = data.get("logMetrics")
    policies = data.get("alertPolicies")
    dashboard = data.get("dashboard")
    if not isinstance(metrics, list) or not metrics:
        raise ValueError("config must define logMetrics")
    if not isinstance(policies, list) or not policies:
        raise ValueError("config must define alertPolicies")
    if not isinstance(dashboard, Mapping):
        raise ValueError("config must define dashboard")
    metric_names = {metric.get("name") for metric in metrics if isinstance(metric, Mapping)}
    for metric in metrics:
        labels = set((metric.get("labels") or {}).keys())
        if not labels <= LOW_CARDINALITY_LABELS:
            raise ValueError(f"metric {metric.get('name')} has high-cardinality labels")
        encoded = json.dumps(metric, sort_keys=True)
        if _contains_sensitive_text(encoded):
            raise ValueError(f"metric {metric.get('name')} contains sensitive text")
    for policy in policies:
        if policy.get("metric") not in metric_names:
            raise ValueError(f"policy {policy.get('name')} references missing metric")


def _contains_sensitive_text(text: str) -> bool:
    lowered = text.lower()
    return any(fragment.lower() in lowered for fragment in SENSITIVE_FRAGMENTS)


def _alert_policy_body(
    policy: Mapping[str, Any],
    *,
    project: str,
    notification_channels: Sequence[str],
) -> dict[str, Any]:
    metric_type = f"logging.googleapis.com/user/{policy['metric']}"
    body: dict[str, Any] = {
        "displayName": f"Avatar {policy['name'].replace('_', ' ')}",
        "enabled": True,
        "combiner": "OR",
        "userLabels": {
            "service": "avatar-generation",
            "severity": str(policy["severity"]),
            "component": "avatar",
        },
        "conditions": [
            {
                "displayName": f"{policy['metric']} above threshold",
                "conditionThreshold": {
                    "filter": f'resource.type="global" AND metric.type="{metric_type}"',
                    "comparison": "COMPARISON_GT",
                    "thresholdValue": max(0.0, float(policy["threshold"]) - 1.0),
                    "duration": policy["duration"],
                    "aggregations": [
                        {
                            "alignmentPeriod": "60s",
                            "perSeriesAligner": "ALIGN_SUM",
                            "crossSeriesReducer": "REDUCE_SUM",
                        }
                    ],
                },
            }
        ],
        "documentation": {
            "content": "Avatar observability policy managed from config/avatar-ops/avatar-observability.json.",
            "mimeType": "text/markdown",
        },
    }
    channels = [channel for channel in notification_channels if str(channel).strip()]
    if channels:
        body["notificationChannels"] = list(channels)
    return body


def _dashboard_body(dashboard: Mapping[str, Any], *, project: str) -> dict[str, Any]:
    widgets = []
    for widget in dashboard.get("widgets", []):
        metrics = widget.get("metrics", [])
        widgets.append(
            {
                "title": widget["title"],
                "xyChart": {
                    "dataSets": [
                        {
                            "timeSeriesQuery": {
                                "timeSeriesFilter": {
                                    "filter": (
                                        'resource.type="global" AND '
                                        f'metric.type="logging.googleapis.com/user/{metric}"'
                                    ),
                                    "aggregation": {
                                        "alignmentPeriod": "60s",
                                        "perSeriesAligner": "ALIGN_SUM",
                                        "crossSeriesReducer": "REDUCE_SUM",
                                    },
                                }
                            },
                            "plotType": "LINE",
                        }
                        for metric in metrics
                    ]
                },
            }
        )
    return {
        "displayName": "Avatar observability",
        "mosaicLayout": {
            "columns": 12,
            "tiles": [
                {
                    "xPos": (index % 2) * 6,
                    "yPos": (index // 2) * 4,
                    "width": 6,
                    "height": 4,
                    "widget": widget,
                }
                for index, widget in enumerate(widgets)
            ],
        },
    }


def _describe_command(operation: Mapping[str, Any], project: str) -> list[str]:
    kind = operation["kind"]
    if kind == "logMetric":
        command = ["gcloud", "logging", "metrics", "describe", operation["name"]]
    elif kind == "alertPolicy":
        command = ["gcloud", "monitoring", "policies", "list"]
    elif kind == "dashboard":
        command = ["gcloud", "monitoring", "dashboards", "list"]
    else:
        raise ValueError(f"unsupported operation kind: {kind}")
    return [*command, "--project", project, "--format=json"]


def _mutation_command(
    operation: Mapping[str, Any],
    *,
    project: str,
    exists: bool,
    resource_name: str = "",
    etag: str = "",
    preserved_notification_channels: Sequence[str] = (),
) -> list[str]:
    kind = operation["kind"]
    action = "update" if exists else "create"
    if kind == "logMetric":
        return _json_file_command(
            [
                "gcloud",
                "logging",
                "metrics",
                action,
                operation["name"],
                "--project",
                project,
            ],
            "--config-from-file",
            operation["body"],
        )
    if kind == "alertPolicy":
        prefix = ["gcloud", "monitoring", "policies", action]
        body = dict(operation["body"])
        if exists:
            prefix.append(resource_name)
            if "notificationChannels" not in body and preserved_notification_channels:
                body["notificationChannels"] = list(preserved_notification_channels)
        prefix.extend(["--project", project])
        return _json_file_command(
            prefix,
            "--policy-from-file",
            body,
        )
    if kind == "dashboard":
        prefix = ["gcloud", "monitoring", "dashboards", action]
        body = dict(operation["body"])
        if exists:
            prefix.append(resource_name)
            body["name"] = resource_name
            if etag:
                body["etag"] = etag
        prefix.extend(["--project", project])
        return _json_file_command(
            prefix,
            "--config-from-file",
            body,
        )
    raise ValueError(f"unsupported operation kind: {kind}")


def _json_file_command(prefix: list[str], flag: str, body: Mapping[str, Any]) -> list[str]:
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix="avatar_observability_",
        delete=False,
    )
    with handle:
        json.dump(body, handle, ensure_ascii=True, sort_keys=True)
    return [*prefix, flag, handle.name]


def _command_error_code(result: CommandResult) -> str:
    if result.returncode == 0:
        return ""
    diagnostic = f"{result.stdout}\n{result.stderr}".lower()
    if "already exists" in diagnostic:
        return "already_exists"
    if "permission denied" in diagnostic or "permission_denied" in diagnostic:
        return "permission_denied"
    if "has not been used" in diagnostic or "service_disabled" in diagnostic:
        return "api_disabled"
    if "invalid argument" in diagnostic or "invalid_argument" in diagnostic:
        return "invalid_argument"
    if "unrecognized arguments" in diagnostic or "required argument" in diagnostic:
        return "cli_argument_error"
    if "not found" in diagnostic or "does not exist" in diagnostic:
        return "not_found"
    return "command_failed"


def _cleanup_json_file(command: Sequence[str]) -> bool:
    cleanup_ok = True
    for flag in ("--policy-from-file", "--config-from-file"):
        if flag not in command:
            continue
        index = list(command).index(flag) + 1
        if index >= len(command):
            continue
        try:
            Path(str(command[index])).unlink(missing_ok=True)
        except OSError:
            cleanup_ok = False
    return cleanup_ok


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile avatar observability resources.")
    parser.add_argument("--project", required=True, help="Only seolleyeon-final or seolleyeon-festival.")
    parser.add_argument("--config", type=Path, default=Path("config/avatar-ops/avatar-observability.json"))
    parser.add_argument("--output", type=Path, help="Optional sanitized JSON report path.")
    parser.add_argument("--verify", action="store_true", help="Describe remote resources without mutation.")
    parser.add_argument("--apply", action="store_true", help="Opt in to create/update gcloud operations.")
    parser.add_argument(
        "--notification-channel",
        action="append",
        default=[],
        help="Explicit monitoring notification channel ID. May be repeated.",
    )
    args = parser.parse_args(argv)
    mode = "apply" if args.apply else "verify" if args.verify else "plan"
    report = reconcile(
        config_path=args.config,
        project=args.project,
        mode=mode,
        notification_channels=args.notification_channel,
    )
    encoded = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if mode != "apply" or report.get("ok") is True else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
