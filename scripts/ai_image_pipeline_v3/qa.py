from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from .config import (
    SHOT_ORDER,
    approved_asset_mirror_path,
    ensure_base_dirs,
    local_image_path,
    now_utc,
    pipeline_paths,
    rejected_attempt_path,
    to_portable_path,
    write_csv,
    write_jsonl,
)
from .manifest import load_generation_manifest, public_final_path, write_generation_outputs


QA_FIELDS = (
    "assetId",
    "profileId",
    "gender",
    "shotType",
    "qaStatus",
    "localPath",
    "approvedPath",
    "rejectedPath",
    "finalPath",
    "width",
    "height",
    "fileBytes",
    "semanticReviewRequired",
    "error",
    "reasonCodes",
    "updatedAt",
)

SUPPORTED_FORMATS = {"PNG", "JPEG", "JPG", "WEBP"}
MIN_WIDTH = 512
MIN_HEIGHT = 512
MIN_FILE_BYTES = 1024
MIN_ASPECT_RATIO = 0.55
MAX_ASPECT_RATIO = 0.85


def _file_sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def inspect_image(path: Path) -> tuple[bool, int, int, str]:
    detail = inspect_image_detail(path)
    return bool(detail["ok"]), int(detail["width"]), int(detail["height"]), "; ".join(detail["reasons"])


def inspect_image_detail(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"ok": False, "width": 0, "height": 0, "fileBytes": 0, "format": "", "reasons": ["missing_image"]}
    file_bytes = path.stat().st_size
    if file_bytes < MIN_FILE_BYTES:
        return {"ok": False, "width": 0, "height": 0, "fileBytes": file_bytes, "format": "", "reasons": ["file_too_small"]}
    try:
        from PIL import Image
    except ImportError:
        return {"ok": True, "width": 0, "height": 0, "fileBytes": file_bytes, "format": "unknown", "reasons": []}
    try:
        with Image.open(path) as image:
            image_format = str(image.format or "").upper()
            width, height = image.size
            image.verify()
        reasons: list[str] = []
        if image_format not in SUPPORTED_FORMATS:
            reasons.append("unsupported_format")
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            reasons.append("dimensions_below_minimum")
        if height <= 0:
            reasons.append("invalid_height")
        else:
            ratio = width / height
            if ratio < MIN_ASPECT_RATIO or ratio > MAX_ASPECT_RATIO:
                reasons.append("bad_aspect_ratio")
        return {
            "ok": not reasons,
            "width": width,
            "height": height,
            "fileBytes": file_bytes,
            "format": image_format,
            "reasons": reasons,
        }
    except Exception as exc:  # noqa: BLE001 - report corrupt asset and continue.
        return {"ok": False, "width": 0, "height": 0, "fileBytes": file_bytes, "format": "", "reasons": ["decode_failed", str(exc)]}


def _profile_number_from_row(row: dict[str, Any]) -> str:
    numeric = str(row.get("numericId") or "")
    if numeric:
        return numeric
    profile_id = str(row.get("profileId") or "")
    if "_" in profile_id:
        return profile_id.split("_", 1)[1]
    return ""


def _path_sanity_issues(paths: Any, row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    expected = public_final_path(paths, row)
    final_value = str(row.get("finalPath") or row.get("expectedFinalPath") or expected)
    final_path = Path(final_value)
    try:
        if final_path.resolve() != expected.resolve():
            issues.append("final_path_mismatch")
    except OSError:
        issues.append("final_path_invalid")
    parts = [part.lower() for part in final_path.parts]
    gender = str(row.get("gender") or "").lower()
    numeric = _profile_number_from_row(row).lower()
    shot = str(row.get("shotType") or "").lower()
    if gender and gender not in parts:
        issues.append("path_gender_mismatch")
    if numeric and numeric not in parts:
        issues.append("path_numeric_id_mismatch")
    if shot and final_path.name.lower() != f"{shot}.png":
        issues.append("path_shot_type_mismatch")
    return issues


def _row_existing_image_path(row: dict[str, Any]) -> Path | None:
    for key in ("localPath", "rawPath", "finalPath", "expectedFinalPath"):
        value = str(row.get(key) or "")
        if not value:
            continue
        path = Path(value)
        if path.exists() and path.is_file():
            return path
    return None


def _manifest_integrity_issues(paths: Any, rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    issues_by_asset: dict[str, list[str]] = {str(row.get("assetId") or ""): [] for row in rows}
    asset_seen: dict[str, int] = {}
    final_seen: dict[str, set[str]] = {}
    by_profile: dict[str, set[str]] = {}
    hash_seen: dict[str, set[str]] = {}
    for row in rows:
        asset_id = str(row.get("assetId") or "")
        asset_seen[asset_id] = asset_seen.get(asset_id, 0) + 1
        final_path = str(row.get("finalPath") or row.get("expectedFinalPath") or public_final_path(paths, row))
        final_seen.setdefault(final_path, set()).add(asset_id)
        by_profile.setdefault(str(row.get("profileId") or ""), set()).add(str(row.get("shotType") or ""))
        issues_by_asset.setdefault(asset_id, []).extend(_path_sanity_issues(paths, row))
        image_path = _row_existing_image_path(row)
        digest = _file_sha256(image_path) if image_path else None
        if digest:
            hash_seen.setdefault(digest, set()).add(asset_id)

    duplicate_asset_ids = {asset_id for asset_id, count in asset_seen.items() if asset_id and count > 1}
    duplicate_final_paths = {path for path, asset_ids in final_seen.items() if path and len(asset_ids) > 1}
    duplicate_hash_asset_ids = {
        asset_id
        for asset_ids in hash_seen.values()
        if len(asset_ids) > 1
        for asset_id in asset_ids
    }
    for row in rows:
        asset_id = str(row.get("assetId") or "")
        if asset_id in duplicate_asset_ids:
            issues_by_asset.setdefault(asset_id, []).append("duplicate_assetId")
        if asset_id in duplicate_hash_asset_ids:
            issues_by_asset.setdefault(asset_id, []).append("duplicate_image_hash")
        final_path = str(row.get("finalPath") or row.get("expectedFinalPath") or public_final_path(paths, row))
        if final_path in duplicate_final_paths:
            issues_by_asset.setdefault(asset_id, []).append("duplicate_final_path")
    for profile_id, shots in by_profile.items():
        missing = [shot for shot in SHOT_ORDER if shot not in shots]
        if not missing:
            continue
        for row in rows:
            if str(row.get("profileId") or "") == profile_id:
                issues_by_asset.setdefault(str(row.get("assetId") or ""), []).extend(f"missing_required_shot:{shot}" for shot in missing)
    pending = paths.manifests / "pending-imagegen.json"
    if pending.exists():
        try:
            payload = json.loads(pending.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        resolved = isinstance(payload, dict) and (payload.get("resolved") is True or str(payload.get("status") or "") in {"resolved", "cleared"})
        if not resolved:
            for row in rows:
                issues_by_asset.setdefault(str(row.get("assetId") or ""), []).append("unresolved_pending_imagegen")
    return {asset_id: sorted(set(issues)) for asset_id, issues in issues_by_asset.items()}


def qa_images(
    *,
    root: Path | str | None = None,
    limit: int | None = None,
    shot_type: str | None = None,
    force: bool = False,
    approve_integrity_only: bool = False,
    copy_approved: bool = True,
) -> dict[str, int]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    rows = load_generation_manifest(paths)
    integrity_issues = _manifest_integrity_issues(paths, rows)
    default_statuses = {"recovered_pending_qa", "needs_manual_review"}
    candidates = [
        row
        for row in rows
        if (not shot_type or str(row.get("shotType")) == str(shot_type))
        and (limit is not None or shot_type is not None or str(row.get("status") or "") in default_statuses)
    ]
    selected = candidates[:limit] if limit else candidates
    selected_ids = {str(row["assetId"]) for row in selected}
    report: list[dict[str, Any]] = []
    qa_manifest: list[dict[str, Any]] = []
    vision_rows: list[dict[str, Any]] = []
    counts = {"checked": 0, "approved": 0, "needs_manual_review": 0, "rejected": 0, "missing": 0}

    for row in rows:
        if str(row["assetId"]) not in selected_ids:
            continue
        counts["checked"] += 1
        local_path = next(
            (
                path
                for path in (
                    Path(str(row.get("localPath") or "")),
                    Path(str(row.get("rawPath") or "")),
                    Path(str(row.get("finalPath") or "")),
                )
                if str(path) not in {"", "."}
            ),
            Path(str(row.get("localPath") or "")),
        )
        image_detail = inspect_image_detail(local_path)
        ok = bool(image_detail["ok"])
        width = int(image_detail["width"])
        height = int(image_detail["height"])
        reason_codes = [*list(image_detail.get("reasons", [])), *integrity_issues.get(str(row["assetId"]), [])]
        error = "; ".join(str(reason) for reason in reason_codes)
        approved_path = local_image_path(paths, row, root_key="approved")
        approved_mirror_path = approved_asset_mirror_path(paths, row)
        rejected_path_value = str(row.get("rejectedPath") or "")
        rejected_path = (
            Path(rejected_path_value)
            if rejected_path_value
            else rejected_attempt_path(paths, str(row["assetId"]), int(row.get("attemptCount") or 1))
        )
        final_path = public_final_path(paths, row)
        qa_status = "file_needs_review"

        if not ok or reason_codes:
            qa_status = "missing" if "missing_image" in reason_codes else "file_rejected"
            row["status"] = qa_status
            row["error"] = error
            if qa_status == "file_rejected" and local_path.exists():
                rejected_path.parent.mkdir(parents=True, exist_ok=True)
                if force or not rejected_path.exists():
                    shutil.copy2(local_path, rejected_path)
            counts["missing" if qa_status == "missing" else "rejected"] += 1
        elif approve_integrity_only:
            qa_status = "file_passed"
            if copy_approved:
                for target in (approved_path, approved_mirror_path, final_path):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if force or not target.exists():
                        shutil.copy2(local_path, target)
            row["status"] = "file_passed"
            row["error"] = ""
            counts["approved"] += 1
        else:
            row["status"] = "file_needs_review"
            row["error"] = "Integrity passed; visual policy QA still requires manual review."
            counts["needs_manual_review"] += 1

        row["updatedAt"] = now_utc()
        row["approvedPath"] = to_portable_path(approved_path)
        row["approvedMirrorPath"] = to_portable_path(approved_mirror_path)
        row["rejectedPath"] = to_portable_path(rejected_path)
        row["finalPath"] = to_portable_path(final_path)
        report.append(
            {
                "assetId": row["assetId"],
                "profileId": row["profileId"],
                "gender": row["gender"],
                "shotType": row["shotType"],
                "qaStatus": qa_status,
                "localPath": to_portable_path(local_path),
                "approvedPath": to_portable_path(approved_path),
                "rejectedPath": to_portable_path(rejected_path),
                "finalPath": to_portable_path(final_path),
                "width": width,
                "height": height,
                "fileBytes": image_detail.get("fileBytes", local_path.stat().st_size if local_path.exists() else 0),
                "semanticReviewRequired": not approve_integrity_only,
                "error": error,
                "reasonCodes": json.dumps(reason_codes, ensure_ascii=False),
                "updatedAt": now_utc(),
            }
        )
        qa_manifest.append(
            {
                "assetId": row["assetId"],
                "profileId": row["profileId"],
                "gender": row["gender"],
                "shotType": row["shotType"],
                "qaStage": "file_qa",
                "decision": qa_status,
                "status": qa_status,
                "reasons": reason_codes or [row.get("error") or "file_integrity_passed_visual_verdict_required"],
                "updatedAt": now_utc(),
            }
        )
        if ok:
            vision_rows.append(
                {
                    "assetId": row["assetId"],
                    "profileId": row["profileId"],
                    "shotType": row["shotType"],
                    "adultVisual": True,
                    "photoRealism": 0,
                    "campusRealism": 0,
                    "brandFit": 0,
                    "influencerRisk": 0,
                    "childlikeRisk": 0,
                    "schoolUniformRisk": 0,
                    "sexualizationRisk": 0,
                    "artifactRisk": 0,
                    "shotTypeReadable": False,
                    "decision": "needs_review",
                    "reasons": ["file_integrity_passed_manual_visual_policy_review_required"],
                }
            )

    write_csv(paths.reports / "qa_report.csv", report, QA_FIELDS)
    write_csv(paths.reports / "asset_qa_report.csv", report, QA_FIELDS)
    write_jsonl(paths.manifests / "qa_manifest.jsonl", qa_manifest)
    write_jsonl(paths.manifests / "asset_qa_manifest.jsonl", qa_manifest)
    write_jsonl(paths.reports / "vision_qa_report.jsonl", vision_rows)
    (paths.reports / "qa_summary.json").write_text(json.dumps(counts, ensure_ascii=False, indent=2), encoding="utf-8")
    write_generation_outputs(paths, rows)
    return counts


def promote_approved_assets(
    *,
    root: Path | str | None = None,
    shot_type: str | None = None,
    force: bool = False,
    statuses: tuple[str, ...] = ("vision_approved",),
) -> dict[str, int]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    rows = load_generation_manifest(paths)
    counts = {"checked": 0, "promoted": 0, "skipped": 0, "missing": 0}
    for row in rows:
        if shot_type and str(row.get("shotType")) != str(shot_type):
            continue
        if str(row.get("status") or "") not in statuses:
            continue
        counts["checked"] += 1
        local_path = Path(str(row.get("localPath") or ""))
        if not local_path.exists():
            counts["missing"] += 1
            continue
        for target in (local_image_path(paths, row, root_key="approved"), approved_asset_mirror_path(paths, row), public_final_path(paths, row)):
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not force:
                counts["skipped"] += 1
                continue
            shutil.copy2(local_path, target)
            counts["promoted"] += 1
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run integrity QA for Seolleyeon AI profile images.")
    parser.add_argument("--root", default=None, help="Workspace root. Defaults to the repository root.")
    parser.add_argument("--manifest", default=None, help="Compatibility option; generation_manifest.jsonl remains the source of truth.")
    parser.add_argument("--out_dir", default=None, help="Compatibility option for Makefile targets.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--shot_type", choices=["face_card", "silhouette_card", "vibe_card"], default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--approve_integrity_only", action="store_true")
    parser.add_argument("--no_copy_approved", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    counts = qa_images(
        root=args.root,
        limit=args.limit,
        shot_type=args.shot_type,
        force=args.force,
        approve_integrity_only=args.approve_integrity_only,
        copy_approved=not args.no_copy_approved,
    )
    print(counts)
    return 0
