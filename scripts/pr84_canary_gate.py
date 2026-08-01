from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUTH_SECRET_PATHS = (
    REPO_ROOT / ".local_secrets" / "staging_test_users.json",
    REPO_ROOT / ".local_secrets" / "staging_test_users_de.json",
    REPO_ROOT / ".local_secrets" / "staging_pr84_canary_users.json",
)
RUNNER_NO_UPLOAD_STATUSES = {
    "READY_DRY_RUN",
    "BLOCKED_MIN_ELIGIBLE",
    "BLOCKED_MIN_ELIGIBLE_NO_UPLOAD",
}
RUNNER_ERROR_STATUSES = {"COMPLETE_WITH_ERRORS"}


def _run(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "command": _redact_command(command),
        "returnCode": completed.returncode,
        "stdout": completed.stdout.strip()[-4000:],
        "stderr": completed.stderr.strip()[-4000:],
    }


def _redact_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    skip_next = False
    for index, value in enumerate(command):
        if skip_next:
            redacted.append("<redacted>")
            skip_next = False
            continue
        redacted.append(value)
        if value in {"--api_key", "--auth_secret_json"} and index + 1 < len(command):
            skip_next = True
    return redacted


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _blocker_counts(validation: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in validation.get("rows", []):
        if not isinstance(row, dict) or row.get("eligibleForUpload"):
            continue
        for blocker in row.get("blockers", []):
            key = str(blocker or "").strip()
            if key:
                counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _mapped_photo_files(validation: dict[str, Any]) -> set[str]:
    mapped: set[str] = set()
    for row in validation.get("rows", []):
        if not isinstance(row, dict):
            continue
        photo_file = str(row.get("photoFile") or "").strip()
        if photo_file:
            mapped.add(photo_file)
    return mapped


def _unmapped_pass_fixtures(preflight: dict[str, Any], validation: dict[str, Any]) -> list[str]:
    mapped = _mapped_photo_files(validation)
    pass_files: list[str] = []
    for item in preflight.get("images", []):
        if not isinstance(item, dict):
            continue
        filename = str(item.get("normalizedFile") or "").strip()
        if filename and item.get("recommendation") == "PASS" and filename not in mapped:
            pass_files.append(filename)
    return sorted(pass_files)


def _next_action(
    *,
    eligible_rows: int,
    min_users: int,
    apply: bool,
    runner_status: Any,
    failed: bool,
    activation: dict[str, Any] | None = None,
) -> str:
    if failed:
        return "fix_failed_gate_step_before_upload"
    if activation:
        active_rows = int(activation.get("activeRowCount") or 0)
        if active_rows < min_users:
            return f"activate_{min_users - active_rows}_uid_photo_consent_rows"
        if eligible_rows < min_users:
            return "rerun_pr84_gate_with_activated_mapping"
    if eligible_rows < min_users:
        return f"provide_{min_users - eligible_rows}_more_eligible_uid_photo_rows"
    if not apply:
        return "dry_run_ready_add_apply_after_manual_review"
    if runner_status in RUNNER_NO_UPLOAD_STATUSES:
        return "apply_requested_but_runner_did_not_upload"
    if runner_status in RUNNER_ERROR_STATUSES:
        return "fix_runner_errors_before_completion"
    return "review_canary_runner_output"


def _summary(
    *,
    preflight_json: Path,
    validation_json: Path,
    runner_json: Path,
    activation_json: Path | None = None,
    apply: bool,
    min_users: int,
    failed: bool = False,
) -> dict[str, Any]:
    preflight = _load_json(preflight_json)
    validation = _load_json(validation_json)
    runner = _load_json(runner_json)
    activation = _load_json(activation_json) if activation_json else {}
    eligible_rows = int(validation.get("eligibleUploadRows", 0) or 0)
    runner_status = runner.get("status")
    unmapped_pass_fixtures = _unmapped_pass_fixtures(preflight, validation)
    activation_ready = not activation or int(activation.get("activeRowCount") or 0) >= min_users
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "applyRequested": apply,
        "minUsers": min_users,
        "safeToApply": eligible_rows >= min_users and activation_ready and not failed and not apply,
        "neededEligibleRows": max(0, min_users - eligible_rows),
        "nextAction": _next_action(
            eligible_rows=eligible_rows,
            min_users=min_users,
            apply=apply,
            runner_status=runner_status,
            failed=failed,
            activation=activation,
        ),
        "preflight": {
            "provider": preflight.get("provider"),
            "recommendationCounts": preflight.get("recommendationCounts", {}),
            "unmappedPassFixtureCount": len(unmapped_pass_fixtures),
            "unmappedPassFixtures": unmapped_pass_fixtures,
        },
        "validation": {
            "rowCount": validation.get("rowCount", 0),
            "eligibleUploadRows": eligible_rows,
            "consentEvidence": validation.get("consentEvidence", {}),
            "blockerCounts": _blocker_counts(validation),
            "blocked": [
                {
                    "uidHash": row.get("uidHash"),
                    "photoFile": row.get("photoFile"),
                    "blockers": row.get("blockers", []),
                }
                for row in validation.get("rows", [])
                if isinstance(row, dict) and not row.get("eligibleForUpload")
            ],
        },
        "runner": {
            "status": runner_status,
            "eligibleCount": runner.get("eligibleCount"),
            "jobCount": len(runner.get("jobs", [])) if isinstance(runner.get("jobs"), list) else 0,
        },
        "activation": _activation_summary(activation),
    }


def _activation_summary(report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return {
            "present": False,
            "status": None,
            "activeRowCount": None,
            "blockedRowCount": None,
            "blockerCounts": {},
        }
    return {
        "present": True,
        "status": report.get("status"),
        "activeRowCount": int(report.get("activeRowCount") or 0),
        "blockedRowCount": int(report.get("blockedRowCount") or 0),
        "blockerCounts": report.get("blockerCounts", {}),
    }


def build_commands(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    normalize_cmd = [
        args.python,
        "scripts/normalize_canary_images.py",
        "--input_dir",
        args.input_dir,
        "--output_dir",
        args.output_dir,
        "--manifest_json",
        args.manifest_json,
    ]
    preflight_cmd = [
        args.mediapipe_python,
        "scripts/preflight_canary_images_mediapipe_task.py",
        "--manifest_json",
        args.manifest_json,
        "--output_json",
        args.preflight_json,
        "--model_path",
        args.face_landmarker_model_path,
    ]
    validate_cmd = [
        args.python,
        "scripts/validate_canary_uid_photo_map.py",
        "--project",
        args.project,
        "--mapping_file",
        args.mapping_file,
        "--consent_file",
        args.consent_file,
        "--preflight_json",
        args.preflight_json,
        "--output_json",
        args.validation_json,
        "--google_services_json",
        args.google_services_json,
    ]
    for secret_path in args.auth_secret_json:
        validate_cmd.extend(["--auth_secret_json", secret_path])

    runner_cmd = [
        args.python,
        "scripts/run_canary_from_validated_map.py",
        "--project",
        args.project,
        "--region",
        args.region,
        "--mapping_file",
        args.mapping_file,
        "--validation_json",
        args.validation_json,
        "--output_json",
        args.runner_json,
        "--google_services_json",
        args.google_services_json,
        "--min_users",
        str(args.min_users),
    ]
    for secret_path in args.auth_secret_json:
        runner_cmd.extend(["--auth_secret_json", secret_path])
    if args.apply:
        runner_cmd.append("--apply")
    if args.allow_partial:
        runner_cmd.append("--allow_partial")
    return [
        ("normalize", normalize_cmd),
        ("mediapipe_preflight", preflight_cmd),
        ("validate_mapping", validate_cmd),
        ("run_guarded_canary", runner_cmd),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the PR8.4 canary normalization/preflight/validation gate."
    )
    parser.add_argument("--project", default="seolleyeon-final")
    parser.add_argument("--region", default="asia-northeast3")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--mediapipe_python",
        default=str(REPO_ROOT / ".venv_mediapipe_preflight" / "Scripts" / "python.exe"),
    )
    parser.add_argument("--input_dir", default=str(REPO_ROOT / "canary_inputs"))
    parser.add_argument("--output_dir", default=str(REPO_ROOT / "canary_inputs" / "normalized"))
    parser.add_argument("--mapping_file", default=str(REPO_ROOT / "canary_uid_photo_map.txt"))
    parser.add_argument("--consent_file", default=str(REPO_ROOT / "canary_uid_photo_consent.txt"))
    parser.add_argument("--google_services_json", default=str(REPO_ROOT / "android" / "app" / "google-services.json"))
    parser.add_argument("--face_landmarker_model_path", default=str(REPO_ROOT / ".cache" / "avatar_models" / "face_landmarker.task"))
    parser.add_argument("--manifest_json", default=str(REPO_ROOT / "out" / "canary_normalized_manifest.json"))
    parser.add_argument("--preflight_json", default=str(REPO_ROOT / "out" / "canary_preflight_report_mediapipe.json"))
    parser.add_argument("--validation_json", default=str(REPO_ROOT / "out" / "canary_mapping_validation_mediapipe.json"))
    parser.add_argument("--runner_json", default=str(REPO_ROOT / "out" / "pr84_canary_runner_dry_run.json"))
    parser.add_argument("--summary_json", default=str(REPO_ROOT / "out" / "pr84_canary_gate_summary.json"))
    parser.add_argument("--activation_json", default=str(REPO_ROOT / "out" / "pr84_canary_uid_photo_map_activation.json"))
    parser.add_argument("--auth_secret_json", action="append", default=[])
    parser.add_argument("--min_users", type=int, default=3)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow_partial", action="store_true")
    args = parser.parse_args(argv)

    if not args.auth_secret_json:
        args.auth_secret_json = [str(path) for path in DEFAULT_AUTH_SECRET_PATHS]

    steps = []
    failed = False
    for name, command in build_commands(args):
        result = _run(command, cwd=REPO_ROOT)
        steps.append({"name": name, **result})
        if result["returnCode"] != 0:
            failed = True
            break

    summary_path = Path(args.summary_json)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        **_summary(
            preflight_json=Path(args.preflight_json),
            validation_json=Path(args.validation_json),
            runner_json=Path(args.runner_json),
            activation_json=Path(args.activation_json),
            apply=args.apply,
            min_users=args.min_users,
            failed=failed,
        ),
        "failed": failed,
        "steps": steps,
    }
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(summary_path.resolve()),
                "failed": failed,
                "eligibleUploadRows": report["validation"]["eligibleUploadRows"],
                "neededEligibleRows": report["neededEligibleRows"],
                "runnerStatus": report["runner"]["status"],
                "nextAction": report["nextAction"],
            },
            ensure_ascii=False,
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
