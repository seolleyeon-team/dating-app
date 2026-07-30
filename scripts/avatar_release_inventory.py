#!/usr/bin/env python3
"""Read-only avatar release inventory and drift report."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import signal
import shutil
import subprocess
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence


SCHEMA_VERSION = "avatar_release_inventory_v1"
MANIFEST_VERSION = "avatar_release_manifest_v1"
ALLOWED_PROJECTS = {"seolleyeon-final", "seolleyeon-festival"}
FORBIDDEN_PROJECTS = {"", "default", "seolleyeon"}
WRITE_VERBS = {"apply", "create", "delete", "deploy", "set-iam-policy", "update"}
DEFAULT_COMMAND_TIMEOUT_SECONDS = 30
MIN_COMMAND_TIMEOUT_SECONDS = 1
MAX_COMMAND_TIMEOUT_SECONDS = 120
PROCESS_REAP_TIMEOUT_SECONDS = 1
WINDOWS_CREATE_SUSPENDED = 0x00000004
UNAVAILABLE_MARKER = "_inventoryUnavailable"
COMMAND_ERROR_CODES = {"timeout", "command-failed", "missing-executable", "invalid-response"}
CommandRunner = Callable[[Sequence[str]], str]


class InventoryError(RuntimeError):
    """Raised when read-only inventory cannot be collected."""


class InventoryCommandError(InventoryError):
    """Carries only a stable, sanitized command failure code."""

    def __init__(self, error: str):
        self.error = error if error in COMMAND_ERROR_CODES else "command-failed"
        super().__init__(self.error)


def build_release_report(
    *,
    project: str,
    manifest_path: Path,
    fixture_path: Optional[Path] = None,
    runner: Optional[CommandRunner] = None,
    command_timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Build a sanitized avatar release inventory and drift report.

    When fixture_path is provided, no external commands are run. Otherwise the
    runner is used for read-only gcloud list/describe commands only.
    """

    project = _validate_project(project)
    command_timeout_seconds = _validate_command_timeout(command_timeout_seconds)
    manifest = _load_manifest(Path(manifest_path))
    expected = manifest["projects"][project]
    raw = (
        _load_fixture(Path(fixture_path))
        if fixture_path
        else _collect_live(project, expected, runner, command_timeout_seconds)
    )
    inventory = _normalize_inventory(project, expected, raw)
    drift = _build_drift(expected, inventory)
    incomplete_resources = _count_incomplete_resources(inventory)
    complete = incomplete_resources == 0
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": project,
        "mode": "fixture" if fixture_path else "live-read-only",
        "complete": complete,
        "ok": complete and not any(item["severity"] == "error" for item in drift),
        "summary": {
            "incompleteResources": incomplete_resources,
            "expectedSelectedFunctions": len(expected["selectedFunctions"]),
            "actualSelectedFunctions": inventory["selectedFunctions"]["actualCount"],
            "expectedCloudRunServices": len(expected["cloudRunServices"]),
            "actualCloudRunServices": sum(
                1 for service in inventory["cloudRunServices"].values() if service.get("present")
            ),
            "expectedQueues": len(expected["queues"]),
            "actualQueues": sum(1 for queue in inventory["queues"].values() if queue.get("present")),
            "expectedMediaBuckets": len(expected["mediaBuckets"]),
            "actualMediaBuckets": sum(
                1 for bucket in inventory["mediaBuckets"].values() if bucket.get("present")
            ),
        },
        "inventory": inventory,
        "drift": drift,
        "redaction": {
            "sanitized": True,
            "omitted": [
                "environment values",
                "IAM tokens",
                "signed URLs",
                "private object paths",
                "raw identities",
                "service account identities",
            ],
        },
    }


def _validate_project(project: str) -> str:
    normalized = str(project or "").strip()
    if normalized in FORBIDDEN_PROJECTS or normalized not in ALLOWED_PROJECTS:
        raise ValueError("refusing project; pass explicit seolleyeon-final or seolleyeon-festival")
    return normalized


def _load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != MANIFEST_VERSION:
        raise ValueError(f"unsupported manifest schemaVersion: {data.get('schemaVersion')}")
    projects = data.get("projects")
    if not isinstance(projects, Mapping):
        raise ValueError("manifest must define projects")
    if set(projects) != ALLOWED_PROJECTS:
        raise ValueError("manifest must define exactly seolleyeon-final and seolleyeon-festival")
    return data


def _load_fixture(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ValueError("fixture JSON must contain an object")
    return data


def _collect_live(
    project: str,
    expected: Mapping[str, Any],
    runner: Optional[CommandRunner],
    command_timeout_seconds: float,
) -> Mapping[str, Any]:
    command_runner = runner or (
        lambda command: _run_json_command(command, timeout_seconds=command_timeout_seconds)
    )
    regions = expected["regions"]
    raw: dict[str, Any] = {}

    raw["functions"] = _run_read_command(
        command_runner,
        [
            "gcloud",
            "functions",
            "list",
            "--project",
            project,
            "--regions",
            regions["functions"],
            "--format",
            "json",
        ],
    )
    raw["cloudRunServices"] = _run_read_command(
        command_runner,
        [
            "gcloud",
            "run",
            "services",
            "list",
            "--project",
            project,
            "--region",
            regions["cloudRun"],
            "--format",
            "json",
        ],
    )
    raw["cloudRunIam"] = {}
    for service_name, service in expected["cloudRunServices"].items():
        raw["cloudRunIam"][service_name] = _run_read_command(
            command_runner,
            [
                "gcloud",
                "run",
                "services",
                "get-iam-policy",
                service_name,
                "--project",
                project,
                "--region",
                service["region"],
                "--format",
                "json",
            ],
        )
    raw["queues"] = {}
    for queue_name, queue in expected["queues"].items():
        raw["queues"][queue_name] = _run_read_command(
            command_runner,
            [
                "gcloud",
                "tasks",
                "queues",
                "describe",
                queue_name,
                "--project",
                project,
                "--location",
                queue["location"],
                "--format",
                "json",
            ],
        )
    raw["buckets"] = {}
    raw["bucketIam"] = {}
    for bucket_key, bucket in expected["mediaBuckets"].items():
        bucket_name = f"{project}-{bucket['nameSuffix']}"
        bucket_uri = f"gs://{bucket_name}"
        raw["buckets"][bucket_key] = _run_read_command(
            command_runner,
            [
                "gcloud",
                "storage",
                "buckets",
                "describe",
                bucket_uri,
                "--format",
                "json",
            ],
        )
        raw["bucketIam"][bucket_key] = _run_read_command(
            command_runner,
            [
                "gcloud",
                "storage",
                "buckets",
                "get-iam-policy",
                bucket_uri,
                "--format",
                "json",
            ],
        )
    return raw


def _run_read_command(runner: CommandRunner, command: Sequence[str]) -> Any:
    _assert_read_only(command)
    try:
        output = runner(command)
    except subprocess.TimeoutExpired:
        return _unavailable("timeout")
    except FileNotFoundError:
        return _unavailable("missing-executable")
    except InventoryCommandError as exc:
        return _unavailable(exc.error)
    except OSError:
        return _unavailable("command-failed")
    except Exception:
        return _unavailable("command-failed")

    if not str(output).strip():
        return {}
    try:
        return json.loads(str(output))
    except (json.JSONDecodeError, TypeError, ValueError):
        return _unavailable("invalid-response")


def _unavailable(error: str) -> dict[str, Any]:
    safe_error = error if error in COMMAND_ERROR_CODES else "command-failed"
    return {UNAVAILABLE_MARKER: True, "error": safe_error}


def _unavailable_error(value: Any) -> Optional[str]:
    if not isinstance(value, Mapping) or value.get(UNAVAILABLE_MARKER) is not True:
        return None
    error = str(value.get("error") or "")
    return error if error in COMMAND_ERROR_CODES else "command-failed"


def _unavailable_resource(error: str) -> dict[str, Any]:
    return {"status": "unavailable", "error": error, "present": None}


def _assert_read_only(command: Sequence[str]) -> None:
    parts = {str(part) for part in command}
    if parts & WRITE_VERBS:
        raise InventoryError(f"refusing mutating command: {' '.join(map(str, command[:4]))}")
    if not ({"list", "describe", "get-iam-policy"} & parts):
        raise InventoryError(f"refusing non-inventory command: {' '.join(map(str, command[:4]))}")


def _resolve_executable(name: str) -> str:
    for candidate in (name, f"{name}.cmd", f"{name}.exe"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return name


def _run_json_command(
    command: Sequence[str],
    *,
    timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS,
) -> str:
    timeout_seconds = _validate_command_timeout(timeout_seconds)
    resolved_command = list(command)
    resolved_command[0] = _resolve_executable(resolved_command[0])
    try:
        process, job_handle = _start_process(resolved_command)
    except FileNotFoundError:
        raise InventoryCommandError("missing-executable") from None
    except OSError:
        raise InventoryCommandError("command-failed") from None

    try:
        stdout, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process, job_handle)
        job_handle = None
        _drain_terminated_process(process)
        raise InventoryCommandError("timeout") from None
    finally:
        if job_handle is not None:
            _close_windows_handle(job_handle)

    if process.returncode != 0:
        raise InventoryCommandError("command-failed")
    return stdout or ""


def _start_process(command: Sequence[str]) -> tuple[subprocess.Popen[str], Optional[int]]:
    options: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "text": True,
        "shell": False,
    }
    job_handle: Optional[int] = None
    if os.name == "nt":
        job_handle = _create_windows_kill_job()
        options["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | WINDOWS_CREATE_SUSPENDED
        )
    else:
        options["start_new_session"] = True

    try:
        process = subprocess.Popen(list(command), **options)
    except Exception:
        if job_handle is not None:
            _close_windows_handle(job_handle)
        raise

    if job_handle is not None:
        try:
            _assign_and_resume_windows_process(process, job_handle)
        except OSError:
            try:
                process.kill()
            except OSError:
                pass
            _close_windows_handle(job_handle)
            raise
    return process, job_handle


def _create_windows_kill_job() -> int:
    class JobObjectBasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JobObjectExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JobObjectBasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.SetInformationJobObject.restype = wintypes.BOOL

    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        raise OSError(ctypes.get_last_error(), "unable to create bounded process job")

    information = JobObjectExtendedLimitInformation()
    information.BasicLimitInformation.LimitFlags = 0x00002000
    configured = kernel32.SetInformationJobObject(
        job_handle,
        9,
        ctypes.byref(information),
        ctypes.sizeof(information),
    )
    if not configured:
        error = ctypes.get_last_error()
        _close_windows_handle(job_handle)
        raise OSError(error, "unable to configure bounded process job")
    return int(job_handle)


def _assign_and_resume_windows_process(
    process: subprocess.Popen[str],
    job_handle: int,
) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    process_handle = wintypes.HANDLE(int(process._handle))
    if not kernel32.AssignProcessToJobObject(wintypes.HANDLE(job_handle), process_handle):
        raise OSError(ctypes.get_last_error(), "unable to assign bounded process job")

    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    ntdll.NtResumeProcess.restype = ctypes.c_long
    if ntdll.NtResumeProcess(process_handle) != 0:
        raise OSError("unable to resume bounded process")


def _close_windows_handle(handle: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle(wintypes.HANDLE(handle))


def _terminate_process_tree(
    process: subprocess.Popen[str],
    job_handle: Optional[int],
) -> None:
    if os.name == "nt" and job_handle is not None:
        _close_windows_handle(job_handle)
    elif process.poll() is None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except OSError:
            pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def _drain_terminated_process(process: subprocess.Popen[str]) -> None:
    try:
        process.communicate(timeout=PROCESS_REAP_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _normalize_inventory(
    project: str,
    expected: Mapping[str, Any],
    raw: Mapping[str, Any],
) -> dict[str, Any]:
    functions_raw = raw.get("functions", [])
    functions_error = _unavailable_error(functions_raw)
    function_names = _function_names(functions_raw) if functions_error is None else set()
    selected = list(expected["selectedFunctions"])
    services_raw = raw.get("cloudRunServices", [])
    services_error = _unavailable_error(services_raw)
    service_rows = _service_rows(services_raw) if services_error is None else {}
    service_iam_rows = raw.get("cloudRunIam", {}) if isinstance(raw.get("cloudRunIam"), Mapping) else {}
    queue_rows = raw.get("queues", {}) if isinstance(raw.get("queues"), Mapping) else {}
    bucket_rows = raw.get("buckets", {}) if isinstance(raw.get("buckets"), Mapping) else {}
    bucket_iam_rows = raw.get("bucketIam", {}) if isinstance(raw.get("bucketIam"), Mapping) else {}

    return {
        "selectedFunctions": _sanitize_selected_functions(
            selected,
            function_names,
            functions_error,
        ),
        "cloudRunServices": {
            service_name: (
                _unavailable_resource(services_error)
                if services_error is not None
                else _sanitize_service(
                    service_name,
                    service_rows.get(service_name),
                    service_iam_rows.get(service_name, {}),
                )
            )
            for service_name in expected["cloudRunServices"]
        },
        "queues": {
            queue_name: _sanitize_queue(queue_rows.get(queue_name))
            for queue_name in expected["queues"]
        },
        "mediaBuckets": {
            bucket_key: _sanitize_bucket(
                bucket_rows.get(bucket_key),
                bucket_iam_rows.get(bucket_key, {}),
            )
            for bucket_key in expected["mediaBuckets"]
        },
        "evidencePlaceholders": {
            key: "placeholder-present" if value else "missing"
            for key, value in expected.get("evidencePlaceholders", {}).items()
        },
        "temporaryBridge": {
            "status": str(expected.get("temporaryBridge", {}).get("status", "unknown")),
            "expectedDirectFestivalWorker": bool(
                expected.get("temporaryBridge", {}).get("expectedDirectFestivalWorker", False)
            ),
        },
    }


def _sanitize_selected_functions(
    selected: Sequence[str],
    function_names: set[str],
    error: Optional[str],
) -> dict[str, Any]:
    if error is not None:
        return {
            "status": "unavailable",
            "error": error,
            "expectedCount": len(selected),
            "actualCount": None,
            "present": [],
            "missingCount": None,
        }
    return {
        "expectedCount": len(selected),
        "actualCount": sum(1 for name in selected if name in function_names),
        "present": sorted(name for name in selected if name in function_names),
        "missingCount": sum(1 for name in selected if name not in function_names),
    }


def _function_names(rows: Any) -> set[str]:
    if isinstance(rows, Mapping):
        rows = rows.get("functions", [])
    names: set[str] = set()
    if not isinstance(rows, list):
        return names
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        raw_name = str(row.get("name") or row.get("id") or "")
        name = raw_name.rsplit("/", 1)[-1]
        if name:
            names.add(name)
    return names


def _service_rows(rows: Any) -> dict[str, Mapping[str, Any]]:
    if isinstance(rows, Mapping):
        rows = rows.get("services", rows)
    if isinstance(rows, Mapping):
        return {str(key): value for key, value in rows.items() if isinstance(value, Mapping)}
    if not isinstance(rows, list):
        return {}
    services: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), Mapping) else {}
        name = str(metadata.get("name") or row.get("name") or "")
        if name:
            services[name] = row
    return services


def _sanitize_service(
    service_name: str,
    row: Optional[Mapping[str, Any]],
    iam_policy: Any,
) -> dict[str, Any]:
    if not isinstance(row, Mapping) or not row:
        return {"present": False}
    iam_error = _unavailable_error(iam_policy)
    if iam_error is not None:
        return _unavailable_resource(iam_error)
    template = _template(row)
    template_meta = template.get("metadata", {}) if isinstance(template.get("metadata"), Mapping) else {}
    annotations = template_meta.get("annotations", {}) if isinstance(template_meta.get("annotations"), Mapping) else {}
    spec = template.get("spec", {}) if isinstance(template.get("spec"), Mapping) else {}
    containers = spec.get("containers", []) if isinstance(spec.get("containers"), list) else []
    image = str(containers[0].get("image", "")) if containers and isinstance(containers[0], Mapping) else ""
    status = row.get("status", {}) if isinstance(row.get("status"), Mapping) else {}
    return {
        "present": True,
        "latestReadyRevisionName": _safe_revision(str(status.get("latestReadyRevisionName") or "")),
        "imageDigest": _image_digest(image),
        "minInstances": _parse_int(annotations.get("autoscaling.knative.dev/minScale") or 0),
        "maxInstances": _parse_int(annotations.get("autoscaling.knative.dev/maxScale")),
        "concurrency": _parse_int(spec.get("containerConcurrency")),
        "timeoutSeconds": _parse_int(spec.get("timeoutSeconds")),
        "privateInvocation": not _has_public_iam_principal(iam_policy),
        "serviceAccountConfigured": bool(spec.get("serviceAccountName")),
    }


def _template(row: Mapping[str, Any]) -> Mapping[str, Any]:
    spec = row.get("spec", {}) if isinstance(row.get("spec"), Mapping) else {}
    template = spec.get("template", {}) if isinstance(spec.get("template"), Mapping) else {}
    return template if isinstance(template, Mapping) else {}


def _safe_revision(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Za-z0-9_.-]", "", value)[:120]


def _image_digest(image: str) -> str:
    match = re.search(r"@(sha256:[A-Fa-f0-9]+)", image)
    return match.group(1).lower() if match else ""


def _sanitize_queue(row: Any) -> dict[str, Any]:
    error = _unavailable_error(row)
    if error is not None:
        return _unavailable_resource(error)
    if not isinstance(row, Mapping) or not row:
        return {"present": False}
    return {
        "present": True,
        "state": str(row.get("state") or ""),
        "rateLimits": {
            "maxConcurrentDispatches": _parse_int((row.get("rateLimits") or {}).get("maxConcurrentDispatches")),
            "maxDispatchesPerSecond": _parse_number((row.get("rateLimits") or {}).get("maxDispatchesPerSecond")),
        },
        "retryConfig": {
            "maxAttempts": _parse_int((row.get("retryConfig") or {}).get("maxAttempts")),
            "minBackoff": str((row.get("retryConfig") or {}).get("minBackoff") or ""),
            "maxBackoff": str((row.get("retryConfig") or {}).get("maxBackoff") or ""),
        },
    }


def _sanitize_bucket(row: Any, iam_policy: Any = None) -> dict[str, Any]:
    error = _unavailable_error(row)
    if error is not None:
        return _unavailable_resource(error)
    if not isinstance(row, Mapping) or not row:
        return {"present": False}
    iam_error = _unavailable_error(iam_policy)
    if iam_error is not None:
        return _unavailable_resource(iam_error)
    iam = row.get("iamConfiguration", {}) if isinstance(row.get("iamConfiguration"), Mapping) else {}
    ubla = iam.get("uniformBucketLevelAccess", {}) if isinstance(iam.get("uniformBucketLevelAccess"), Mapping) else {}
    retention_policy = row.get("retentionPolicy") or row.get("retention_policy")
    return {
        "present": True,
        "uniformBucketLevelAccess": bool(
            row.get(
                "uniformBucketLevelAccess",
                row.get("uniform_bucket_level_access", ubla.get("enabled", False)),
            )
        ),
        "publicAccessPrevention": str(
            row.get("publicAccessPrevention")
            or row.get("public_access_prevention")
            or iam.get("publicAccessPrevention")
            or ""
        ),
        "noPublicIamPrincipals": not _has_public_iam_principal(iam_policy),
        "retentionPolicy": (
            "present"
            if retention_policy
            else str(
                row.get("retentionPolicyStatus")
                or row.get("retention_policy_status")
                or "absent"
            )
        ),
    }


def _has_public_iam_principal(policy: Any) -> bool:
    if not isinstance(policy, Mapping):
        return False
    bindings = policy.get("bindings")
    if not isinstance(bindings, list):
        return False
    for binding in bindings:
        if not isinstance(binding, Mapping):
            continue
        members = binding.get("members")
        if not isinstance(members, list):
            continue
        if any(str(member) in {"allUsers", "allAuthenticatedUsers"} for member in members):
            return True
    return False


def _parse_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _parse_number(value: Any) -> Optional[float | int]:
    if value is None or value == "":
        return None
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _count_incomplete_resources(inventory: Mapping[str, Any]) -> int:
    count = 1 if inventory["selectedFunctions"].get("status") == "unavailable" else 0
    for group_name in ("cloudRunServices", "queues", "mediaBuckets"):
        count += sum(
            1
            for resource in inventory[group_name].values()
            if resource.get("status") == "unavailable"
        )
    return count


def _build_drift(expected: Mapping[str, Any], inventory: Mapping[str, Any]) -> list[dict[str, str]]:
    drift: list[dict[str, str]] = []
    selected = inventory["selectedFunctions"]
    if selected.get("status") == "unavailable":
        drift.append(
            _drift(
                "error",
                "selectedFunctions.inventory",
                f"inventory unavailable: {selected['error']}",
            )
        )
    elif selected["actualCount"] != selected["expectedCount"]:
        drift.append(
            _drift(
                "error",
                "selectedFunctions.count",
                f"expected {selected['expectedCount']} selected avatar Functions, found {selected['actualCount']}",
            )
        )

    for service_name, expected_service in expected["cloudRunServices"].items():
        actual = inventory["cloudRunServices"][service_name]
        prefix = f"cloudRunServices.{service_name}"
        if actual.get("status") == "unavailable":
            drift.append(_drift("error", f"{prefix}.inventory", f"inventory unavailable: {actual['error']}"))
            continue
        if not actual.get("present"):
            drift.append(_drift("error", f"{prefix}.present", "expected direct avatar worker service is absent"))
            continue
        for field in ("minInstances", "maxInstances", "concurrency", "timeoutSeconds", "privateInvocation"):
            if actual.get(field) != expected_service.get(field):
                drift.append(_drift("error", f"{prefix}.{field}", "actual value differs from manifest"))

    for queue_name, expected_queue in expected["queues"].items():
        actual = inventory["queues"][queue_name]
        prefix = f"queues.{queue_name}"
        if actual.get("status") == "unavailable":
            drift.append(_drift("error", f"{prefix}.inventory", f"inventory unavailable: {actual['error']}"))
            continue
        if not actual.get("present"):
            drift.append(_drift("error", f"{prefix}.present", "expected queue is absent"))
            continue
        for field, expected_value in expected_queue["rateLimits"].items():
            if actual.get("rateLimits", {}).get(field) != expected_value:
                drift.append(_drift("error", f"{prefix}.rateLimits.{field}", "actual value differs from manifest"))
        for field, expected_value in expected_queue["retryConfig"].items():
            if actual.get("retryConfig", {}).get(field) != expected_value:
                drift.append(_drift("error", f"{prefix}.retryConfig.{field}", "actual value differs from manifest"))

    for bucket_key, expected_bucket in expected["mediaBuckets"].items():
        actual = inventory["mediaBuckets"][bucket_key]
        prefix = f"mediaBuckets.{bucket_key}"
        if actual.get("status") == "unavailable":
            drift.append(_drift("error", f"{prefix}.inventory", f"inventory unavailable: {actual['error']}"))
            continue
        if not actual.get("present"):
            drift.append(_drift("error", f"{prefix}.present", "expected media bucket is absent"))
            continue
        for field in (
            "uniformBucketLevelAccess",
            "publicAccessPrevention",
            "retentionPolicy",
            "noPublicIamPrincipals",
        ):
            if actual.get(field) != expected_bucket.get(field):
                drift.append(_drift("error", f"{prefix}.{field}", "actual value differs from manifest"))

    bridge = inventory.get("temporaryBridge", {})
    if bridge.get("status") == "temporary":
        drift.append(_drift("warning", "temporaryBridge.status", "temporary bridge remains active"))
    return drift


def _drift(severity: str, field: str, message: str) -> dict[str, str]:
    return {"severity": severity, "field": field, "message": message}


def _validate_command_timeout(value: Any) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        raise ValueError("command timeout must be a number") from None
    if not MIN_COMMAND_TIMEOUT_SECONDS <= timeout <= MAX_COMMAND_TIMEOUT_SECONDS:
        raise ValueError(
            f"command timeout must be between {MIN_COMMAND_TIMEOUT_SECONDS} "
            f"and {MAX_COMMAND_TIMEOUT_SECONDS} seconds"
        )
    return int(timeout) if timeout.is_integer() else timeout


def _parse_command_timeout(value: str) -> float:
    try:
        return _validate_command_timeout(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build read-only avatar release inventory drift report.")
    parser.add_argument("--project", required=True, help="Only seolleyeon-final or seolleyeon-festival.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("config/avatar-ops/avatar-release-manifest.json"),
    )
    parser.add_argument("--fixture", type=Path, help="Deterministic inventory JSON fixture; disables live gcloud calls.")
    parser.add_argument(
        "--command-timeout-seconds",
        type=_parse_command_timeout,
        default=DEFAULT_COMMAND_TIMEOUT_SECONDS,
        help=(
            "Per-command live inventory timeout "
            f"({MIN_COMMAND_TIMEOUT_SECONDS}-{MAX_COMMAND_TIMEOUT_SECONDS} seconds)."
        ),
    )
    parser.add_argument("--output", type=Path, help="Optional path for the sanitized report JSON.")
    args = parser.parse_args(argv)

    report = build_release_report(
        project=args.project,
        manifest_path=args.manifest,
        fixture_path=args.fixture,
        command_timeout_seconds=args.command_timeout_seconds,
    )
    encoded = json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["ok"] else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
