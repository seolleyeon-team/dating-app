from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .config import (
    DEFAULT_MODEL,
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_QUALITY,
    DEFAULT_SIZE,
    PipelinePaths,
    approved_asset_path,
    local_image_path,
    now_utc,
    profile_number,
    prompt_hash,
    raw_attempt_path,
    rejected_attempt_path,
    read_jsonl,
    shot_sort_key,
    to_portable_path,
    write_jsonl,
    write_status_csv,
)
from .distribution_targets import target_face_type, target_looks_level, target_looks_level_band


def manifest_path(paths: PipelinePaths) -> Path:
    return paths.manifests / "generation_manifest.jsonl"


def status_path(paths: PipelinePaths) -> Path:
    return paths.reports / "generation_status.csv"


def public_final_path(paths: PipelinePaths, asset: Mapping[str, Any]) -> Path:
    return local_image_path(paths, asset, root_key="final")


def enrich_asset(
    asset: Mapping[str, Any],
    paths: PipelinePaths,
    *,
    model: str = DEFAULT_MODEL,
    size: str = DEFAULT_SIZE,
    quality: str = DEFAULT_QUALITY,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
    status: str = "prepared",
    dry_run: bool = False,
) -> dict[str, Any]:
    row = dict(asset)
    image_path = raw_attempt_path(paths, str(row["assetId"]), 1)
    final_path = public_final_path(paths, row)
    approved_path = approved_asset_path(paths, row)
    rejected_path = rejected_attempt_path(paths, str(row["assetId"]), 1)
    if not dry_run:
        image_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        approved_path.parent.mkdir(parents=True, exist_ok=True)
        rejected_path.parent.mkdir(parents=True, exist_ok=True)
    reference_asset_id = ""
    reference_local_path = ""
    if row.get("shotType") != "face_card":
        reference_asset_id = f"{row['profileId']}__face_card__v001"
        reference_local_path = to_portable_path(
            paths.final / str(row["gender"]) / profile_number(str(row["profileId"])) / "face_card.png"
        )
    row.update(
        {
            "promptHash": prompt_hash(str(row.get("prompt", ""))),
            "numericId": profile_number(str(row["profileId"])),
            "targetFaceType": target_face_type(row),
            "targetLooksLevel": target_looks_level(row) if target_looks_level(row) is not None else "",
            "targetLooksLevelBand": target_looks_level_band(row),
            "identityScope": str(row.get("identityScope") or "production"),
            "isReserve": bool(row.get("isReserve") or False),
            "reserveStatus": str(row.get("reserveStatus") or ("standby" if row.get("isReserve") else "")),
            "activeForTarget": bool(row.get("activeForTarget") if "activeForTarget" in row else not row.get("isReserve")),
            "identityDecision": str(row.get("identityDecision") or ""),
            "model": model,
            "size": size,
            "quality": quality,
            "outputFormat": output_format,
            "status": status,
            "localPath": to_portable_path(image_path),
            "finalPath": to_portable_path(final_path),
            "approvedPath": to_portable_path(approved_path),
            "rejectedPath": to_portable_path(rejected_path),
            "expectedRawPath": to_portable_path(image_path),
            "expectedFinalPath": to_portable_path(final_path),
            "expectedApprovedPath": to_portable_path(approved_path),
            "expectedRejectedPath": to_portable_path(rejected_path),
            "referenceAssetId": reference_asset_id,
            "referenceLocalPath": reference_local_path,
            "resolvedReferencePath": reference_local_path,
            "attempt": 0,
            "attemptCount": 0,
            "dryRun": bool(dry_run),
            "updatedAt": now_utc(),
            "error": "",
        }
    )
    return row

def load_generation_manifest(paths: PipelinePaths) -> list[dict[str, Any]]:
    return sorted(read_jsonl(manifest_path(paths)), key=shot_sort_key)


def write_generation_outputs(paths: PipelinePaths, rows: list[Mapping[str, Any]]) -> None:
    ordered = sorted([dict(row) for row in rows], key=shot_sort_key)
    write_jsonl(manifest_path(paths), ordered)
    write_status_csv(status_path(paths), ordered)


def merge_manifest_rows(existing: list[Mapping[str, Any]], incoming: list[Mapping[str, Any]], *, force: bool) -> list[dict[str, Any]]:
    by_asset_id = {str(row["assetId"]): dict(row) for row in existing}
    for row in incoming:
        asset_id = str(row["assetId"])
        if asset_id in by_asset_id and not force:
            current = by_asset_id[asset_id]
            merged = dict(row)
            for key in (
                "status",
                "attemptCount",
                "dryRun",
                "updatedAt",
                "error",
                "reserveStatus",
                "activeForTarget",
                "identityDecision",
            ):
                merged[key] = current.get(key, merged.get(key, ""))
            if current.get("localPath"):
                merged["localPath"] = current["localPath"]
            for path_key in (
                "finalPath",
                "approvedPath",
                "rejectedPath",
                "expectedRawPath",
                "expectedFinalPath",
                "expectedApprovedPath",
                "expectedRejectedPath",
                "resolvedReferencePath",
            ):
                if current.get(path_key):
                    merged[path_key] = current[path_key]
            by_asset_id[asset_id] = merged
        else:
            by_asset_id[asset_id] = dict(row)
    return sorted(by_asset_id.values(), key=shot_sort_key)
