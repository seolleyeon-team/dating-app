#!/usr/bin/env python3
"""Watch Seolleyeon parent-managed Kanban pipeline progress.

This intentionally does not generate images or call nested child Codex.
It keeps the Hermes Kanban dispatcher moving while gateway warms up and
emits a concise status report every loop. Stop when all female/male 001-140
folders contain the three expected shots, or when a handoff/manual blocker
needs parent imagegen/operator intervention.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS = [
    "t_8828cb42",  # reset/plan
    "t_096d124a",  # handoff
    "t_94bbb47b",  # parent imagegen
    "t_a349135e",  # recover/resume
    "t_a96197ed",  # loop controller
]
SHOTS = ["face_card.png", "silhouette_card.png", "vibe_card.png"]
LOG = ROOT / "ai_image" / "reports" / "pipeline_audit" / "parent_managed_kanban_watchdog.log"
STATUS_JSON = ROOT / "ai_image" / "reports" / "pipeline_audit" / "parent_managed_kanban_watchdog_status.json"


def run(args: list[str], timeout: int = 120) -> dict:
    try:
        p = subprocess.run(
            args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return {"args": args, "code": p.returncode, "out": p.stdout, "err": p.stderr}
    except subprocess.TimeoutExpired as e:
        return {"args": args, "code": 124, "out": e.stdout or "", "err": (e.stderr or "") + "\nTIMEOUT"}
    except Exception as e:  # noqa: BLE001
        return {"args": args, "code": 125, "out": "", "err": repr(e)}


def json_cmd(args: list[str]) -> dict | list | None:
    r = run(args)
    txt = (r["out"] or "").strip()
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        return {"_parse_error": True, "raw": txt[-4000:], "code": r["code"], "err": r["err"][-1000:]}


def counts() -> dict:
    total_complete = 0
    by_gender = {}
    for gender in ["female", "male"]:
        base = ROOT / "ai_image" / gender
        complete = []
        partial = []
        missing = []
        for i in range(1, 141):
            d = base / f"{i:03d}"
            n = sum((d / s).exists() for s in SHOTS)
            if n == 3:
                complete.append(i)
            elif n > 0:
                partial.append([i, n])
            else:
                missing.append(i)
        total_complete += len(complete)
        by_gender[gender] = {
            "complete": len(complete),
            "partial": len(partial),
            "missing": len(missing),
            "first_missing": missing[:10],
            "first_partial": partial[:10],
        }
    return {"complete_identities": total_complete, "target_identities": 280, "by_gender": by_gender}


def task_runs() -> dict:
    out = {}
    for t in TASKS:
        data = json_cmd(["hermes", "kanban", "runs", t, "--json"])
        out[t] = data
    return out


def latest_run_status(runs):
    if not isinstance(runs, list) or not runs:
        return None
    return runs[-1].get("status"), runs[-1].get("outcome"), runs[-1].get("summary")


def pipeline_status() -> dict:
    bounded = json_cmd(["python", "scripts/run_ai_image_pipeline_v3.py", "bounded-chunk-status", "--root", "."])
    pending = json_cmd(["python", "scripts/run_ai_image_pipeline_v3.py", "pending-status", "--root", "."])
    return {"bounded": bounded, "pending": pending}


def log_line(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    line = f"{stamp} {msg}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="", flush=True)


def main() -> int:
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    max_loops = int(sys.argv[2]) if len(sys.argv) > 2 else 100000
    log_line(f"watchdog_start root={ROOT} interval={interval}s")

    # Gateway may already be running; this is idempotent enough for this setup.
    gw = run(["hermes", "gateway", "start"], timeout=180)
    log_line(f"gateway_start code={gw['code']} out={gw['out'][-300:].replace(chr(10), ' | ')} err={gw['err'][-300:].replace(chr(10), ' | ')}")

    for loop in range(1, max_loops + 1):
        c = counts()
        pstat = pipeline_status()
        runs = task_runs()
        dispatch = run(["hermes", "kanban", "dispatch"], timeout=180)
        dry = run(["hermes", "kanban", "dispatch", "--dry-run"], timeout=180)
        summary = {
            "loop": loop,
            "counts": c,
            "pipeline": pstat,
            "task_latest": {t: latest_run_status(runs.get(t)) for t in TASKS},
            "dispatch_code": dispatch["code"],
            "dispatch_tail": (dispatch["out"] + dispatch["err"])[-1200:],
            "dry_tail": (dry["out"] + dry["err"])[-1200:],
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        STATUS_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

        bg = pstat.get("bounded") if isinstance(pstat, dict) else None
        pend = pstat.get("pending") if isinstance(pstat, dict) else None
        manual = isinstance(bg, dict) and bg.get("manualReviewRequired")
        pending_unresolved = isinstance(pend, dict) and pend.get("unresolved")
        handoff = None
        if isinstance(pend, dict):
            handoff = pend.get("handoffPromptPath") or pend.get("promptPath")
        log_line(
            "loop={loop} complete={complete}/280 female={f}/140 male={m}/140 manual={manual} pending_unresolved={pending} handoff={handoff} dispatch_code={code}".format(
                loop=loop,
                complete=c["complete_identities"],
                f=c["by_gender"]["female"]["complete"],
                m=c["by_gender"]["male"]["complete"],
                manual=manual,
                pending=pending_unresolved,
                handoff=handoff or "",
                code=dispatch["code"],
            )
        )

        if c["complete_identities"] >= 280:
            log_line("TARGET_COMPLETE all 280 identities have 3 images")
            return 0

        time.sleep(interval)
    log_line("MAX_LOOPS_REACHED")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
