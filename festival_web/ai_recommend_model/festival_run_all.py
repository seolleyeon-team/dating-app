#!/usr/bin/env python3
"""Run full festival web recommendation pipeline."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run_step(script: str, args: list[str]) -> None:
    cmd = [sys.executable, str(ROOT / script), *args]
    print(f"\n==> {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--database", default=None)
    parser.add_argument("--date_key", default=None)
    parser.add_argument("--skip_ai_embeddings", action="store_true")
    parser.add_argument("--skip_profile_embeddings", action="store_true")
    args = parser.parse_args()

    common = ["--project", args.project]
    if args.database:
        common.extend(["--database", args.database])

    if not args.skip_ai_embeddings:
        run_step("festival_export_ai_embeddings.py", common)
    if not args.skip_profile_embeddings:
        run_step("festival_export_profile_embeddings.py", common)

    rec_args = list(common)
    if args.date_key:
        rec_args.extend(["--date_key", args.date_key])
    run_step("festival_clip_recommend.py", rec_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
