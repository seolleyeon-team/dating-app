from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from .codex_imagegen import queue_path, pending_path, read_pending, write_imagegen_queue, write_pending
from .config import (
    approved_asset_path,
    local_image_path,
    now_utc,
    pipeline_paths,
    profile_number,
    raw_attempt_path,
    read_csv,
    read_jsonl,
    rejected_attempt_path,
    to_portable_path,
    write_status_csv,
)
from .manifest import load_generation_manifest, write_generation_outputs

PATH_FIELDS = (
    "localPath",
    "rawPath",
    "finalPath",
    "approvedPath",
    "rejectedPath",
    "expectedRawPath",
    "expectedFinalPath",
    "expectedApprovedPath",
    "expectedRejectedPath",
    "referenceLocalPath",
    "resolvedReferencePath",
    "pendingPath",
    "codexGeneratedSourcePath",
    "approvedMirrorPath",
)
PENDING_PATH_FIELDS = (
    "queuePath",
    "manifestPath",
    "pendingPath",
    "expectedRawPath",
    "expectedFinalPath",
    "expectedApprovedPath",
    "expectedRejectedPath",
    "referenceImagePath",
    "expectedReceiptPath",
)


def _backup(path: Path, backup_dir: Path, *, dry_run: bool) -> str | None:
    if not path.exists():
        return None
    target = backup_dir / path.name
    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return to_portable_path(target)


def _path_for_row(paths: Any, row: Mapping[str, Any], key: str) -> str:
    asset_id = str(row["assetId"])
    attempt = int(row.get("attemptCount") or row.get("attempt") or 1)
    if key in {"localPath", "rawPath", "expectedRawPath"}:
        return to_portable_path(raw_attempt_path(paths, asset_id, attempt))
    if key in {"finalPath", "expectedFinalPath"}:
        return to_portable_path(local_image_path(paths, row, root_key="final"))
    if key in {"approvedPath", "expectedApprovedPath"}:
        return to_portable_path(approved_asset_path(paths, row))
    if key == "approvedMirrorPath":
        return to_portable_path(paths.approved / str(row["gender"]) / profile_number(str(row["profileId"])) / f"{row['shotType']}.png")
    if key in {"rejectedPath", "expectedRejectedPath"}:
        return to_portable_path(rejected_attempt_path(paths, asset_id, attempt))
    if key in {"referenceLocalPath", "resolvedReferencePath"}:
        if str(row.get("shotType") or "") == "face_card":
            return ""
        return to_portable_path(paths.final / str(row["gender"]) / profile_number(str(row["profileId"])) / "face_card.png")
    if key == "pendingPath":
        return to_portable_path(pending_path(paths.root)) if str(row.get("status") or "") == "pending_imagegen" else ""
    if key == "codexGeneratedSourcePath":
        value = str(row.get(key) or "")
        # This field is historical provenance only. If it points to another
        # Windows user/workspace it will break workspace-integrity gates and
        # cannot be used for deterministic recovery on this machine.
        return "" if "C:/Users/samsung" in value.replace("\\", "/") else value
    return str(row.get(key) or "")


def normalize_generation_paths(*, root: Path | str | None = None, dry_run: bool = False, backup: bool = True) -> dict[str, Any]:
    paths = pipeline_paths(root)
    rows = load_generation_manifest(paths)
    timestamp = now_utc().replace(":", "").replace("+", "")
    backup_dir = paths.manifests / f"path_normalize_backup_{timestamp}"
    backups: dict[str, str | None] = {}
    if backup:
        backups["generationManifest"] = _backup(paths.manifests / "generation_manifest.jsonl", backup_dir, dry_run=dry_run)
        backups["imagegenQueue"] = _backup(queue_path(paths.root), backup_dir, dry_run=dry_run)
        backups["generationStatus"] = _backup(paths.reports / "generation_status.csv", backup_dir, dry_run=dry_run)
        backups["pending"] = _backup(pending_path(paths.root), backup_dir, dry_run=dry_run)

    changed_rows = 0
    changed_fields: dict[str, int] = {key: 0 for key in PATH_FIELDS}
    normalized: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        row_changed = False
        for key in PATH_FIELDS:
            if key not in row and key not in {"rawPath", "pendingPath"}:
                continue
            new_value = _path_for_row(paths, row, key)
            old_value = str(row.get(key) or "")
            if old_value != new_value:
                row[key] = new_value
                changed_fields[key] = changed_fields.get(key, 0) + 1
                row_changed = True
        if row_changed:
            row["updatedAt"] = now_utc()
            changed_rows += 1
        normalized.append(row)

    pending_changed_fields: dict[str, int] = {}
    pending_payload = read_pending(pending_path(paths.root))
    normalized_pending: dict[str, Any] | None = None
    if pending_payload:
        normalized_pending = dict(pending_payload)
        asset_id = str(normalized_pending.get("assetId") or "")
        manifest_row = next((row for row in normalized if str(row.get("assetId")) == asset_id), None)
        if manifest_row:
            attempt = int(normalized_pending.get("attempt") or manifest_row.get("attempt") or manifest_row.get("attemptCount") or 1)
            replacements = {
                "queuePath": to_portable_path(queue_path(paths.root)),
                "manifestPath": to_portable_path(paths.manifests / "generation_manifest.jsonl"),
                "pendingPath": to_portable_path(pending_path(paths.root)),
                "expectedRawPath": to_portable_path(raw_attempt_path(paths, asset_id, attempt)),
                "expectedFinalPath": to_portable_path(local_image_path(paths, manifest_row, root_key="final")),
                "expectedApprovedPath": to_portable_path(approved_asset_path(paths, manifest_row)),
                "expectedRejectedPath": to_portable_path(rejected_attempt_path(paths, asset_id, attempt)),
                "referenceImagePath": "" if str(manifest_row.get("shotType") or "") == "face_card" else to_portable_path(paths.final / str(manifest_row["gender"]) / profile_number(str(manifest_row["profileId"])) / "face_card.png"),
            }
            chunk_id = str(normalized_pending.get("chunkId") or "")
            if chunk_id:
                replacements["expectedReceiptPath"] = to_portable_path(paths.reports / "chunks" / chunk_id / "transactions" / f"{asset_id}_attempt{attempt}.json")
            for key, new_value in replacements.items():
                old_value = str(normalized_pending.get(key) or "")
                if old_value != new_value:
                    normalized_pending[key] = new_value
                    pending_changed_fields[key] = pending_changed_fields.get(key, 0) + 1
            generated_dir = normalized_pending.get("codexGeneratedImagesDir")
            if generated_dir and "C:/Users/samsung" in str(generated_dir).replace("\\", "/"):
                # Let recovery use this machine's configured default instead of a migrated user's home dir.
                normalized_pending.pop("codexGeneratedImagesDir", None)
                pending_changed_fields["codexGeneratedImagesDir"] = pending_changed_fields.get("codexGeneratedImagesDir", 0) + 1
            if pending_changed_fields:
                normalized_pending["updatedAt"] = now_utc()

    reference_mismatches = 0
    by_asset = {str(row.get("assetId")): row for row in normalized}
    for row in normalized:
        if str(row.get("shotType") or "") == "face_card":
            continue
        face = by_asset.get(str(row.get("referenceAssetId") or ""))
        if face and str(row.get("referenceLocalPath") or "") != str(face.get("finalPath") or ""):
            reference_mismatches += 1

    if not dry_run:
        write_generation_outputs(paths, normalized)
        write_imagegen_queue(paths.root, normalized)
        if normalized_pending is not None and pending_changed_fields:
            write_pending(pending_path(paths.root), normalized_pending)

    status_rows = read_csv(paths.reports / "generation_status.csv")
    stale_active_files: dict[str, int] = {}
    stale_marker = "C:/Users/samsung"
    for label, path in {
        "generationManifest": paths.manifests / "generation_manifest.jsonl",
        "imagegenQueue": queue_path(paths.root),
        "generationStatus": paths.reports / "generation_status.csv",
        "pending": pending_path(paths.root),
    }.items():
        if path.exists():
            stale_active_files[label] = path.read_text(encoding="utf-8", errors="ignore").replace("\\", "/").count(stale_marker)

    return {
        "schemaVersion": "seolleyeon_manifest_path_normalize_v1",
        "dryRun": dry_run,
        "root": to_portable_path(paths.root),
        "rowCount": len(rows),
        "changedRows": changed_rows,
        "changedFields": {key: value for key, value in changed_fields.items() if value},
        "pendingChangedFields": pending_changed_fields,
        "referenceMismatchesAfter": reference_mismatches,
        "statusRowsAfter": len(status_rows) if status_rows else len(normalized),
        "staleActiveFileOccurrencesAfter": stale_active_files,
        "backups": backups,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Normalize active manifest/queue/status/pending absolute paths to this workspace.")
    parser.add_argument("--root", default=None)
    parser.add_argument("--dry-run", "--dry_run", dest="dry_run", action="store_true", default=False)
    parser.add_argument("--no-backup", dest="backup", action="store_false", default=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(json.dumps(normalize_generation_paths(root=args.root, dry_run=args.dry_run, backup=args.backup), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
