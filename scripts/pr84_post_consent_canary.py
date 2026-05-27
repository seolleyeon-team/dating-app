from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PR84_SECRET = REPO_ROOT / ".local_secrets" / "staging_pr84_canary_users.json"
EXPECTED_ACCOUNT = "seolleyeon.official@gmail.com"
EXPECTED_PROJECT = "seolleyeon-final"
UID_PHOTO_INPUT_BLOCKERS = {
    "confirm_uid_photo_consent_required",
    "uid_photo_pair_consent_missing",
}
CONSENT_MISMATCH_BLOCKER = "uid_photo_consent_map_mismatch"
GENERAL_CONSENT_EXACT_MISMATCH_BLOCKER = "general_consent_exact_uid_photo_mismatch"
DEFAULT_GATE_CONSENT_FILE = "canary_uid_photo_consent.txt"
RUNNER_NO_UPLOAD_STATUSES = {
    "READY_DRY_RUN",
    "BLOCKED_MIN_ELIGIBLE",
    "BLOCKED_MIN_ELIGIBLE_NO_UPLOAD",
}
RUNNER_ERROR_STATUSES = {"COMPLETE_WITH_ERRORS"}


def _redact_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for index, value in enumerate(command):
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
            continue
        redacted.append(value)
        if value in {"--auth_secret_json", "--api_key"} and index + 1 < len(command):
            skip_next = True
    return redacted


def _resolve_executable(name: str) -> str:
    for candidate in (name, f"{name}.cmd", f"{name}.exe"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return name


def _run(command: list[str], *, cwd: Path) -> dict[str, Any]:
    resolved_command = list(command)
    resolved_command[0] = _resolve_executable(resolved_command[0])
    try:
        completed = subprocess.run(
            resolved_command,
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        return {
            "command": _redact_command(command),
            "returnCode": 127,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "command": _redact_command(command),
        "returnCode": completed.returncode,
        "stdout": completed.stdout.strip()[-4000:],
        "stderr": completed.stderr.strip()[-4000:],
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _activation_input_blockers(activation: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    blocker_counts = activation.get("blockerCounts", {})
    if isinstance(blocker_counts, Mapping):
        blockers.extend(
            blocker
            for blocker in sorted(UID_PHOTO_INPUT_BLOCKERS)
            if int(blocker_counts.get(blocker) or 0) > 0
        )
    consent_map = activation.get("uidPhotoConsentMap", {})
    unexpected_pair_count = int(activation.get("unexpectedConsentPairCount") or 0)
    if isinstance(consent_map, Mapping):
        unexpected_pair_count = max(
            unexpected_pair_count,
            int(consent_map.get("unexpectedPairCount") or 0),
        )
    if str(activation.get("status") or "") == "BLOCKED_CONSENT_MISMATCH" or unexpected_pair_count > 0:
        blockers.append(CONSENT_MISMATCH_BLOCKER)
    return list(dict.fromkeys(blockers))


def _general_consent_exact_mismatch(general_consent: Mapping[str, Any] | None) -> bool:
    if not isinstance(general_consent, Mapping):
        return False
    if not general_consent.get("present") or general_consent.get("valid") is not True:
        return False
    exact = general_consent.get("exactUidPhotoConsent")
    if not isinstance(exact, Mapping) or exact.get("satisfiedByThisFile") is True:
        return False
    parsed_count = int(exact.get("parsedRowCount") or 0)
    required_count = int(exact.get("requiredRowCount") or 0)
    matched_count = int(exact.get("matchedRowCount") or 0)
    unexpected_count = int(exact.get("unexpectedRowCount") or 0)
    return unexpected_count > 0 or (
        parsed_count > 0
        and required_count > 0
        and matched_count < required_count
    )


def _gate_executed(steps: list[dict[str, Any]]) -> bool:
    return any(step.get("name") == "activated_mapping_gate" for step in steps)


def _gate_step_failed(steps: list[dict[str, Any]], gate: Mapping[str, Any]) -> bool:
    for step in steps:
        if step.get("name") == "activated_mapping_gate":
            if int(step.get("returnCode") or 0) != 0:
                return True
    return bool(gate.get("failed"))


def _runner_did_not_upload(gate_runner: Mapping[str, Any], *, apply: bool) -> bool:
    if not apply:
        return False
    runner_status = str(gate_runner.get("status") or "")
    runner_job_count = int(gate_runner.get("jobCount") or 0)
    return runner_status in RUNNER_NO_UPLOAD_STATUSES or runner_job_count <= 0


def _runner_completed_with_errors(gate_runner: Mapping[str, Any], *, apply: bool) -> bool:
    if not apply:
        return False
    return str(gate_runner.get("status") or "") in RUNNER_ERROR_STATUSES


def _consent_map_summary(activation: Mapping[str, Any]) -> dict[str, Any]:
    consent_map = activation.get("uidPhotoConsentMap", {})
    if not isinstance(consent_map, Mapping):
        consent_map = {}
    pair_count = int(activation.get("consentPairCount") or consent_map.get("pairCount") or 0)
    matched_count = int(
        activation.get("matchedConsentPairCount") or consent_map.get("matchedPairCount") or 0
    )
    unexpected_count = int(
        activation.get("unexpectedConsentPairCount") or consent_map.get("unexpectedPairCount") or 0
    )
    return {
        "path": consent_map.get("path"),
        "present": bool(consent_map.get("present")),
        "pairCount": pair_count,
        "matchedPairCount": matched_count,
        "unexpectedPairCount": unexpected_count,
    }


def build_project_guard_steps(
    *,
    account_result: dict[str, Any],
    project_result: dict[str, Any],
    firebase_result: dict[str, Any],
    expected_account: str,
    expected_project: str,
) -> tuple[bool, dict[str, Any]]:
    account = str(account_result.get("stdout") or "").strip().splitlines()[-1:]
    project = str(project_result.get("stdout") or "").strip().splitlines()[-1:]
    firebase = str(firebase_result.get("stdout") or "").strip().splitlines()[-1:]
    account_value = account[0] if account else ""
    project_value = project[0] if project else ""
    firebase_value = firebase[0] if firebase else ""
    checks = {
        "account": account_value == expected_account,
        "gcloudProject": project_value == expected_project,
        "firebaseProject": firebase_value == expected_project,
    }
    return (
        all(checks.values())
        and account_result.get("returnCode") == 0
        and project_result.get("returnCode") == 0
        and firebase_result.get("returnCode") == 0,
        {
            "expectedAccount": expected_account,
            "expectedProject": expected_project,
            "account": account_value,
            "gcloudProject": project_value,
            "firebaseProject": firebase_value,
            "checks": checks,
        },
    )


def run_project_guard(args: argparse.Namespace) -> tuple[bool, dict[str, Any], list[dict[str, Any]]]:
    account_result = _run(["gcloud", "config", "get-value", "account"], cwd=REPO_ROOT)
    project_result = _run(["gcloud", "config", "get-value", "project"], cwd=REPO_ROOT)
    firebase_result = _run(["firebase", "use"], cwd=REPO_ROOT)
    ok, summary = build_project_guard_steps(
        account_result=account_result,
        project_result=project_result,
        firebase_result=firebase_result,
        expected_account=args.expected_account,
        expected_project=args.project,
    )
    return ok, summary, [
        {"name": "project_guard_account", **account_result},
        {"name": "project_guard_gcloud_project", **project_result},
        {"name": "project_guard_firebase_project", **firebase_result},
    ]


def build_activation_command(args: argparse.Namespace) -> list[str]:
    return [
        args.python,
        "scripts/pr84_activate_canary_mapping.py",
        "--template_json",
        args.template_json,
        "--uid_photo_consent_map",
        args.uid_photo_consent_map,
        "--output_mapping",
        args.activated_mapping,
        "--output_json",
        args.activation_json,
        "--required_consent_template",
        args.required_consent_template,
        "--confirm_uid_photo_consent",
        "--require_ready",
        "--min_users",
        str(args.min_users),
    ]


def build_general_consent_command(args: argparse.Namespace) -> list[str]:
    command = [
        args.python,
        "scripts/pr84_consent_evidence.py",
        "--output_json",
        args.general_consent_evidence_json,
    ]
    if args.general_consent_file:
        command.extend(["--consent_file", args.general_consent_file])
    return command


def _gate_consent_file(args: argparse.Namespace) -> str:
    return args.consent_file or args.general_consent_file or DEFAULT_GATE_CONSENT_FILE


def build_gate_command(args: argparse.Namespace) -> list[str]:
    command = [
        args.python,
        "scripts/pr84_canary_gate.py",
        "--project",
        args.project,
        "--region",
        args.region,
        "--input_dir",
        args.input_dir,
        "--output_dir",
        args.output_dir,
        "--mapping_file",
        args.activated_mapping,
        "--consent_file",
        _gate_consent_file(args),
        "--google_services_json",
        args.google_services_json,
        "--activation_json",
        args.activation_json,
        "--summary_json",
        args.gate_summary_json,
        "--runner_json",
        args.runner_json,
        "--min_users",
        str(args.min_users),
    ]
    for secret_path in args.auth_secret_json:
        command.extend(["--auth_secret_json", secret_path])
    if args.apply:
        command.append("--apply")
    return command


def build_report(
    *,
    steps: list[dict[str, Any]],
    project_guard: dict[str, Any],
    activation: dict[str, Any],
    gate: dict[str, Any],
    apply: bool,
    min_users: int,
    general_consent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    input_blockers = _activation_input_blockers(activation)
    if _general_consent_exact_mismatch(general_consent):
        input_blockers.insert(0, GENERAL_CONSENT_EXACT_MISMATCH_BLOCKER)
    input_blockers = list(dict.fromkeys(input_blockers))
    activation_ready = (
        int(activation.get("activeRowCount") or 0) >= min_users
        and str(activation.get("status") or "") == "READY"
        and CONSENT_MISMATCH_BLOCKER not in input_blockers
    )
    required_consent_rows = activation.get("requiredConsentMapRows", [])
    if not isinstance(required_consent_rows, list):
        required_consent_rows = []
    gate_executed = _gate_executed(steps)
    gate_failed = _gate_step_failed(steps, gate) if gate_executed else False
    gate_safe_to_apply = bool(gate.get("safeToApply")) if gate_executed else False
    gate_runner = gate.get("runner", {}) if gate_executed else {}
    gate_validation = gate.get("validation", {}) if gate_executed else {}
    runner_no_upload = _runner_did_not_upload(gate_runner, apply=apply) if gate_executed else False
    runner_completed_with_errors = (
        _runner_completed_with_errors(gate_runner, apply=apply) if gate_executed else False
    )
    gate_ready = gate_safe_to_apply or bool(apply and gate_runner.get("jobCount"))
    gate_next_action = gate.get("nextAction") if gate_executed else None
    if gate_next_action is None and input_blockers:
        gate_next_action = "activate_3_uid_photo_consent_rows"
    if gate_failed:
        input_blockers.append("gate_execution_failed")
    if runner_no_upload:
        input_blockers.append("apply_runner_did_not_upload")
    if runner_completed_with_errors:
        input_blockers.append("apply_runner_completed_with_errors")
    input_blockers = list(dict.fromkeys(input_blockers))
    status = "READY_DRY_RUN" if activation_ready and gate_safe_to_apply and not gate_failed else "BLOCKED"
    consent_map_summary = _consent_map_summary(activation)
    if gate_failed:
        status = "BLOCKED_GATE"
    elif runner_no_upload:
        status = "BLOCKED_RUNNER_NO_UPLOAD"
    elif runner_completed_with_errors:
        status = "BLOCKED_RUNNER_ERRORS"
    elif apply and activation_ready and gate_executed:
        status = "APPLY_ATTEMPTED"
    if project_guard and not all(project_guard.get("checks", {}).values()):
        status = "BLOCKED_PROJECT_GUARD"
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "applyRequested": apply,
        "status": status,
        "inputBlockers": input_blockers,
        "missingConsentRowCount": len(required_consent_rows),
        "consentMap": consent_map_summary,
        "generalConsentEvidence": {
            "present": bool((general_consent or {}).get("present")),
            "valid": bool((general_consent or {}).get("valid")),
            "scope": (general_consent or {}).get("scope"),
            "consentFile": (general_consent or {}).get("consentFile"),
            "consentFileSelection": (general_consent or {}).get("consentFileSelection"),
            "exactUidPhotoConsent": (general_consent or {}).get("exactUidPhotoConsent", {}),
            "blockers": (general_consent or {}).get("blockers", []),
        },
        "projectGuard": project_guard,
        "activationReady": activation_ready,
        "gateReady": gate_ready,
        "activation": {
            "status": activation.get("status"),
            "consentPairCount": consent_map_summary["pairCount"],
            "matchedConsentPairCount": consent_map_summary["matchedPairCount"],
            "unexpectedConsentPairCount": consent_map_summary["unexpectedPairCount"],
            "activeRowCount": activation.get("activeRowCount"),
            "blockedRowCount": activation.get("blockedRowCount"),
            "blockerCounts": activation.get("blockerCounts", {}),
            "requiredConsentMapRows": required_consent_rows,
            "uidPhotoConsentMap": activation.get("uidPhotoConsentMap", {}),
        },
        "gate": {
            "executed": gate_executed,
            "failed": gate_failed,
            "safeToApply": gate_safe_to_apply,
            "nextAction": gate_next_action,
            "eligibleUploadRows": gate_validation.get("eligibleUploadRows"),
            "runnerStatus": gate_runner.get("status"),
            "runnerJobCount": gate_runner.get("jobCount"),
        },
        "steps": steps,
    }


def build_console_summary(report: Mapping[str, Any], *, output_path: Path, required_consent_template: Path) -> dict[str, Any]:
    required_rows = report["activation"].get("requiredConsentMapRows") or []
    return {
        "output": str(output_path.resolve()),
        "status": report["status"],
        "inputBlockers": report.get("inputBlockers", []),
        "activationReady": report["activationReady"],
        "gateReady": report["gateReady"],
        "nextAction": report["gate"]["nextAction"],
        "generalConsentEvidence": report.get("generalConsentEvidence", {}),
        "consentMap": report.get("consentMap", {}),
        "missingConsentRowCount": report.get("missingConsentRowCount", len(required_rows)),
        "requiredConsentRows": required_rows,
        "requiredConsentTemplate": str(required_consent_template.resolve()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run PR8.4 activation and activated-mapping gate after exact UID/photo consent."
    )
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--expected_account", default=EXPECTED_ACCOUNT)
    parser.add_argument("--region", default="asia-northeast3")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--template_json", default="out/pr84_canary_uid_photo_map_template.json")
    parser.add_argument("--uid_photo_consent_map", default="pr84_uid_photo_consent_map.txt")
    parser.add_argument("--activated_mapping", default="out/pr84_canary_uid_photo_map_activated.txt")
    parser.add_argument("--activation_json", default="out/pr84_canary_uid_photo_map_activation.json")
    parser.add_argument("--general_consent_evidence_json", default="out/pr84_consent_evidence.json")
    parser.add_argument("--general_consent_file", default=None)
    parser.add_argument("--required_consent_template", default="out/pr84_uid_photo_consent_map_required.txt")
    parser.add_argument("--input_dir", default=str(REPO_ROOT / "canary_inputs"))
    parser.add_argument("--output_dir", default=str(REPO_ROOT / "canary_inputs" / "normalized"))
    parser.add_argument("--consent_file", default=None)
    parser.add_argument("--google_services_json", default="android/app/google-services.json")
    parser.add_argument("--gate_summary_json", default="out/pr84_canary_gate_summary.json")
    parser.add_argument("--runner_json", default="out/pr84_canary_runner_dry_run.json")
    parser.add_argument("--report_json", default="out/pr84_post_consent_canary_report.json")
    parser.add_argument("--auth_secret_json", action="append", default=[])
    parser.add_argument("--min_users", type=int, default=3)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm_staging_mutation", action="store_true")
    args = parser.parse_args(argv)

    if args.apply and not args.confirm_staging_mutation:
        parser.error("--apply requires --confirm_staging_mutation")
    if not args.auth_secret_json:
        args.auth_secret_json = [str(DEFAULT_PR84_SECRET)]

    steps: list[dict[str, Any]] = []
    guard_ok, project_guard, guard_steps = run_project_guard(args)
    steps.extend(guard_steps)
    activation: dict[str, Any] = {}

    if guard_ok:
        general_consent_result = _run(build_general_consent_command(args), cwd=REPO_ROOT)
        steps.append({"name": "general_canary_consent_evidence", **general_consent_result})
        activation_result = _run(build_activation_command(args), cwd=REPO_ROOT)
        steps.append({"name": "activate_uid_photo_mapping", **activation_result})
        activation = _load_json(Path(args.activation_json))
    else:
        activation = _load_json(Path(args.activation_json))

    if guard_ok and steps[-1]["name"] == "activate_uid_photo_mapping" and steps[-1]["returnCode"] == 0:
        gate_result = _run(build_gate_command(args), cwd=REPO_ROOT)
        steps.append({"name": "activated_mapping_gate", **gate_result})
    gate = _load_json(Path(args.gate_summary_json))
    general_consent = _load_json(Path(args.general_consent_evidence_json))

    report = build_report(
        steps=steps,
        project_guard=project_guard,
        activation=activation,
        gate=gate,
        general_consent=general_consent,
        apply=args.apply,
        min_users=args.min_users,
    )
    output_path = Path(args.report_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            build_console_summary(
                report,
                output_path=output_path,
                required_consent_template=Path(args.required_consent_template),
            ),
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] in {"READY_DRY_RUN", "APPLY_ATTEMPTED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
