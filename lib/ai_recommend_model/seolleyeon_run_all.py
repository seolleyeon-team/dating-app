#!/usr/bin/env python3
"""
Seolleyeon AI 추천 파이프라인 전체 실행

실행 순서:
1. SVD 학습 + Firestore 저장 (modelRecs/.../sources/svd)
2. KNN 학습 + Firestore 저장 (modelRecs/.../sources/knn)
3. CLIP 학습 + Firestore 저장 (modelRecs/.../sources/clip)
4. RRF 통합 + Firestore 저장 (modelRecs/.../sources/rrf)

사용법:
  python seolleyeon_run_all.py --firestore_project seolleyeon --date_key 20250309

옵션:
  --skip_svd, --skip_knn, --skip_clip, --skip_rrf 로 단계별 스킵 가능
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def run_script(script_name: str, args: list[str]) -> bool:
    """스크립트 실행. 성공 시 True, 실패 시 False."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, script_name)
    if not os.path.isfile(script_path):
        print(f"[!] Script not found: {script_path}")
        return False

    cmd = [sys.executable, script_path] + args
    print(f"\n{'='*60}")
    print(f"[RUN] {' '.join(cmd)}")
    print("="*60)
    ret = subprocess.call(cmd)
    if ret != 0:
        print(f"[!] {script_name} failed with exit code {ret}")
        return False
    print(f"[OK] {script_name} completed")
    return True


def main():
    p = argparse.ArgumentParser(
        description="Run full Seolleyeon recommendation pipeline (SVD, KNN, CLIP, RRF)"
    )
    p.add_argument("--firestore_project", type=str, required=True)
    p.add_argument("--firestore_database", type=str, default=None)
    p.add_argument("--date_key", type=str, required=True, help="YYYYMMDD (KST)")
    p.add_argument("--firestore_events", action="store_true", default=True,
                   help="Load events from Firestore recEvents")
    p.add_argument("--lookback_days", type=int, default=120)
    p.add_argument("--skip_svd", action="store_true")
    p.add_argument("--skip_knn", action="store_true")
    p.add_argument("--skip_clip", action="store_true")
    p.add_argument("--skip_rrf", action="store_true")

    args = p.parse_args()

    base_args = [
        "--firestore_project", args.firestore_project,
        "--date_key", args.date_key,
    ]
    if args.firestore_database:
        base_args.extend(["--firestore_database", args.firestore_database])

    if args.firestore_events:
        base_args.append("--firestore_events")

    all_ok = True

    if not args.skip_svd:
        svd_args = base_args + ["--lookback_days", str(args.lookback_days)]
        if not run_script("seolleyeon_svd_train_export.py", svd_args):
            all_ok = False

    if not args.skip_knn:
        knn_args = base_args + ["--lookback_days", str(args.lookback_days)]
        if not run_script("seolleyeon_knn_train_export.py", knn_args):
            all_ok = False

    if not args.skip_clip:
        clip_args = base_args + ["--lookback_days", str(args.lookback_days)]
        if not run_script("seolleyeon_clip_train_export.py", clip_args):
            all_ok = False

    if not args.skip_rrf:
        rrf_args = base_args
        if not run_script("seolleyeon_rrf_export.py", rrf_args):
            all_ok = False

    if all_ok:
        print("\n[SUCCESS] Full pipeline completed.")
        return 0
    print("\n[FAILED] Some steps failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
