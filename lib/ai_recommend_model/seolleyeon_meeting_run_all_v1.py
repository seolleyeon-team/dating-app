#!/usr/bin/env python3
"""Run the full Seolleyeon meeting recommender v1 pipeline."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def run_script(script_name: str, args: list[str]) -> bool:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, script_name)
    if not os.path.isfile(script_path):
        print(f"[missing] {script_path}")
        return False
    cmd = [sys.executable, script_path] + args
    print(f"[run] {' '.join(cmd)}")
    return subprocess.call(cmd) == 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run meeting recommender v1 pipeline.")
    parser.add_argument("--firestore_project", required=True, type=str)
    parser.add_argument("--firestore_database", default=None, type=str)
    parser.add_argument("--date_key", required=True, type=str, help="YYYYMMDD (KST)")
    parser.add_argument("--skip_group_index", action="store_true")
    parser.add_argument("--skip_recommend", action="store_true")
    parser.add_argument("--skip_daily", action="store_true")
    parser.add_argument("--skip_verify", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    base_args = [
        "--firestore_project",
        args.firestore_project,
        "--date_key",
        args.date_key,
    ]
    if args.firestore_database:
        base_args.extend(["--firestore_database", args.firestore_database])

    ok = True
    if not args.skip_group_index:
        ok = run_script("seolleyeon_meeting_group_index_export_v1.py", list(base_args)) and ok
    if not args.skip_recommend:
        ok = run_script("seolleyeon_meeting_recommend_export_v1.py", list(base_args)) and ok
    if not args.skip_daily:
        ok = run_script("seolleyeon_meeting_daily_recs_export_v1.py", list(base_args)) and ok
    if not args.skip_verify:
        ok = run_script("seolleyeon_meeting_verify_v1.py", list(base_args)) and ok

    print("[success]" if ok else "[failed]")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
