from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(r"C:/Users/Mickey/StudioProjects/dating-app-ai_profile_image")
TASK_ID = "t_43f8cc90"


def run(cmd: list[str], *, timeout: int = 180) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        return {"cmd": cmd, "exit": proc.returncode, "out": proc.stdout[-12000:]}
    except subprocess.TimeoutExpired as exc:
        return {"cmd": cmd, "exit": 124, "out": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "timeout"}
    except Exception as exc:  # noqa: BLE001 - watchdog must report, not crash silently.
        return {"cmd": cmd, "exit": 1, "out": f"watchdog command failed: {exc}"}


def json_cmd(cmd: list[str], *, timeout: int = 180) -> tuple[dict[str, Any] | list[Any] | None, dict[str, Any]]:
    result = run(cmd, timeout=timeout)
    try:
        return json.loads(result["out"]), result
    except Exception:
        return None, result


def latest_run() -> tuple[dict[str, Any] | None, dict[str, Any]]:
    payload, raw = json_cmd(["hermes", "kanban", "runs", TASK_ID, "--json"])
    if isinstance(payload, list) and payload:
        return payload[-1], raw
    return None, raw


def compact_result(label: str, result: dict[str, Any]) -> str:
    out = str(result.get("out") or "").strip()
    if len(out) > 2000:
        out = out[-2000:]
    return f"## {label}\nexit={result.get('exit')}\n{out}"


def main() -> int:
    latest, runs_raw = latest_run()
    if not latest:
        # Non-empty output because a broken watchdog should be visible.
        print(compact_result("failed_to_read_runs", runs_raw))
        return 0
    if latest.get("status") != "blocked" and latest.get("outcome") != "blocked":
        return 0

    started = datetime.now(timezone.utc).isoformat()
    summary = str(latest.get("summary") or latest.get("error") or "blocked")
    actions: list[tuple[str, dict[str, Any]]] = []

    for label, cmd, timeout in [
        ("show_before", ["hermes", "kanban", "show", TASK_ID, "--json"], 120),
        ("pending_before", ["python", "scripts/run_ai_image_pipeline_v3.py", "pending-status", "--root", "."], 120),
        ("validate_before", ["python", "scripts/run_ai_image_pipeline_v3.py", "bounded-chunk-validate-plan", "--root", "."], 120),
        ("recover", ["python", "scripts/run_ai_image_pipeline_v3.py", "recover", "--root", "."], 240),
        ("reconcile_apply", ["python", "scripts/run_ai_image_pipeline_v3.py", "bounded-chunk-reconcile", "--root", ".", "--apply", "--clear-manual-flag-if-safe"], 300),
        ("pending_after", ["python", "scripts/run_ai_image_pipeline_v3.py", "pending-status", "--root", "."], 120),
        ("validate_after", ["python", "scripts/run_ai_image_pipeline_v3.py", "bounded-chunk-validate-plan", "--root", "."], 120),
    ]:
        actions.append((label, run(cmd, timeout=timeout)))

    validate_after = actions[-1][1]
    recovery_ok = validate_after.get("exit") == 0 and '"canRun": true' in str(validate_after.get("out") or "")
    if recovery_ok:
        comment = (
            f"Automated T06 watchdog recovery at {started}: latest blocked run summary was: {summary}\n"
            "Ran pending-status, validate-plan, recover, bounded-chunk-reconcile --apply --clear-manual-flag-if-safe, "
            "then validate-plan returned canRun=true. Unblocking and dispatching one worker."
        )
        actions.append(("comment", run(["hermes", "kanban", "comment", TASK_ID, comment], timeout=120)))
        actions.append(("unblock", run(["hermes", "kanban", "unblock", TASK_ID], timeout=120)))
        actions.append(("dispatch", run(["hermes", "kanban", "dispatch", "--max", "1", "--json"], timeout=180)))
    else:
        comment = (
            f"Automated T06 watchdog diagnosed blocked state at {started} but did not unblock because validate-plan is still not canRun=true. "
            f"Latest blocked run summary: {summary}"
        )
        actions.append(("comment_unresolved", run(["hermes", "kanban", "comment", TASK_ID, comment], timeout=120)))

    lines = [
        "T06 watchdog acted on blocked task.",
        f"time_utc={started}",
        f"latest_summary={summary}",
        f"recovery_ok={recovery_ok}",
    ]
    for label, result in actions:
        lines.append(compact_result(label, result))
    print("\n\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
