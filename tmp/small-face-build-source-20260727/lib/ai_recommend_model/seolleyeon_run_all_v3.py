#!/usr/bin/env python3
"""
Seolleyeon 추천 파이프라인 전체 실행 v3

실행 순서:
1. CLIP 학습 + Firestore 저장 (modelRecs/.../sources/clip)
2. SVD 학습 + Firestore 저장 (modelRecs/.../sources/svd)
3. KNN 학습 + Firestore 저장 (modelRecs/.../sources/knn)
4. RRF 통합 + Firestore 저장 (modelRecs/.../sources/rrf, `seolleyeon_rrf_export.py`)

기본 전략:
- CLIP을 anchor source로 두고
- SVD/KNN은 warm-user, pruned collaborative source로만 사용
- RRF는 clip required + conservative weights + limited non-anchor items
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


DEFAULT_RRF_SOURCE_WEIGHTS = '{"clip":1.0,"svd":0.35,"knn":0.25}'


def run_script(script_name: str, args: list[str]) -> bool:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, script_name)
    if not os.path.isfile(script_path):
        print(f"[!] Script not found: {script_path}")
        return False

    cmd = [sys.executable, script_path] + args
    print(f"\n{'='*80}")
    print(f"[RUN] {' '.join(cmd)}")
    print("="*80)
    ret = subprocess.call(cmd)
    if ret != 0:
        print(f"[!] {script_name} failed with exit code {ret}")
        return False
    print(f"[OK] {script_name} completed")
    return True


def main() -> int:
    p = argparse.ArgumentParser(description="Run full Seolleyeon recommendation pipeline v3")
    p.add_argument("--firestore_project", type=str, required=True)
    p.add_argument("--firestore_database", type=str, default=None)
    p.add_argument("--date_key", type=str, required=True, help="YYYYMMDD (KST)")
    p.add_argument("--lookback_days", type=int, default=120)
    p.add_argument("--events_layout", type=str, default="auto", choices=["auto", "top_level", "user_subcollections"])
    p.add_argument("--apply_policy_filters", action="store_true")
    p.add_argument("--skip_svd", action="store_true")
    p.add_argument("--skip_knn", action="store_true")
    p.add_argument("--skip_clip", action="store_true")
    p.add_argument("--skip_rrf", action="store_true")
    args = p.parse_args()

    base_args = [
        "--firestore_project", args.firestore_project,
        "--date_key", args.date_key,
        "--lookback_days", str(args.lookback_days),
        "--events_layout", args.events_layout,
        "--firestore_events",
    ]
    if args.firestore_database:
        base_args.extend(["--firestore_database", args.firestore_database])
    if args.apply_policy_filters:
        base_args.append("--apply_policy_filters")

    all_ok = True

    if not args.skip_clip:
        clip_args = list(base_args)
        if not run_script("seolleyeon_clip_train_export_v3.py", clip_args):
            all_ok = False

    if not args.skip_svd:
        svd_args = list(base_args)
        if not run_script("seolleyeon_svd_train_export_v3.py", svd_args):
            all_ok = False

    if not args.skip_knn:
        knn_args = list(base_args)
        if not run_script("seolleyeon_knn_train_export_v3.py", knn_args):
            all_ok = False

    if not args.skip_rrf:
        # RRF는 리포지토리 공용 `seolleyeon_rrf_export.py`(개선 RRF)를 사용합니다.
        # (별도 `seolleyeon_rrf_export_v3.py` 없이 v3 파이프라인과 호환되도록 함.)
        rrf_args = [
            "--firestore_project", args.firestore_project,
            "--date_key", args.date_key,
            "--sources", "clip,svd,knn",
            "--required_sources", "clip",
            "--topn", "400",
            "--max_items_per_source", "400",
            "--min_sources_per_user", "2",
            "--source_weights_json", DEFAULT_RRF_SOURCE_WEIGHTS,
        ]
        if args.firestore_database:
            rrf_args.extend(["--firestore_database", args.firestore_database])
        if not run_script("seolleyeon_rrf_export.py", rrf_args):
            all_ok = False

    if all_ok:
        print("\n[SUCCESS] Full pipeline completed.")
        return 0
    print("\n[FAILED] Some steps failed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
