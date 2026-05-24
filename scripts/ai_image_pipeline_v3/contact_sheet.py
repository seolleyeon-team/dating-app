from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .config import SHOT_ORDER, ensure_base_dirs, now_utc, pipeline_paths, read_jsonl, to_portable_path
from .manifest import load_generation_manifest


def _resolve_under_root(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


@dataclass(frozen=True)
class ContactSheetResult:
    output_path: Path
    image_count: int
    columns: int
    rows: int


def _load_current_chunk_plan(root: Path | str | None, chunk_id: str) -> dict[str, Any]:
    plan_path = pipeline_paths(root).manifests / "current_chunk_plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"current_chunk_plan.json does not exist: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    if str(plan.get("chunkId") or "") != str(chunk_id):
        raise ValueError(f"current_chunk_plan chunkId mismatch: expected {chunk_id}, got {plan.get('chunkId') or '<missing>'}")
    return plan


def _planned_assets_from_chunk_plan(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    for identity in plan.get("identities", []):
        if not isinstance(identity, Mapping):
            continue
        profile_id = str(identity.get("profileId") or "")
        gender = str(identity.get("gender") or "")
        numeric_id = str(identity.get("numericId") or "")
        for asset in identity.get("assets", []):
            if not isinstance(asset, Mapping):
                continue
            row = dict(asset)
            row.setdefault("profileId", profile_id)
            row.setdefault("gender", gender)
            row.setdefault("numericId", numeric_id)
            row.setdefault("targetFaceType", identity.get("targetFaceType"))
            row.setdefault("targetLooksLevelBand", identity.get("targetLooksLevelBand"))
            if row.get("assetId"):
                assets.append(row)
    return assets


def _latest_by_asset_id(rows: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        asset_id = str(row.get("assetId") or "")
        if asset_id:
            latest[asset_id] = dict(row)
    return latest


def _file_qa_status(row: Mapping[str, Any]) -> str:
    for key in ("fileQaStatus", "fileQAStatus", "decision", "status", "qaStatus"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return "unknown"


def _file_qa_passed_for_asset(asset_id: str, state: Mapping[str, Any], file_qa: Mapping[str, Any]) -> bool:
    asset_states = state.get("assetStates") if isinstance(state.get("assetStates"), Mapping) else {}
    if str(asset_states.get(asset_id) or "") == "file_qa_passed":
        return True
    return _file_qa_status(file_qa) in {"file_qa_passed", "file_passed", "passed"}


def _load_current_chunk_state(root: Path | str | None, chunk_id: str) -> dict[str, Any]:
    state_path = pipeline_paths(root).manifests / "current_chunk_state.json"
    if not state_path.exists():
        return {}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    if str(state.get("chunkId") or "") != str(chunk_id):
        return {}
    return state


def _chunk_file_qa_rows(paths, chunk_id: str) -> list[dict[str, Any]]:
    return read_jsonl(paths.manifests / "file_qa_manifest.jsonl") + read_jsonl(paths.reports / "chunks" / chunk_id / "file_qa.jsonl")


def build_current_chunk_whitelist(root: Path | str | None, chunk_id: str) -> dict[str, Any]:
    paths = pipeline_paths(root)
    plan = _load_current_chunk_plan(root, chunk_id)
    planned_assets = _planned_assets_from_chunk_plan(plan)
    generation_by_asset = {str(row.get("assetId") or ""): dict(row) for row in load_generation_manifest(paths)}
    file_qa_by_asset = {str(row.get("assetId") or ""): dict(row) for row in read_jsonl(paths.manifests / "file_qa_manifest.jsonl")}
    assets: list[dict[str, Any]] = []
    for asset in planned_assets:
        asset_id = str(asset.get("assetId") or "")
        generation_row = generation_by_asset.get(asset_id, {})
        final_path = str(asset.get("finalPath") or generation_row.get("finalPath") or "")
        final_file = _resolve_under_root(paths.root, final_path) if final_path else None
        file_qa = file_qa_by_asset.get(asset_id, {})
        file_qa_status = str(file_qa.get("status") or file_qa.get("decision") or "missing")
        assets.append(
            {
                "assetId": asset_id,
                "profileId": str(asset.get("profileId") or generation_row.get("profileId") or ""),
                "gender": str(asset.get("gender") or generation_row.get("gender") or ""),
                "numericId": str(asset.get("numericId") or generation_row.get("numericId") or ""),
                "shotType": str(asset.get("shotType") or generation_row.get("shotType") or ""),
                "finalPath": final_path,
                "fileExists": bool(final_file and final_file.is_file()),
                "fileQaStatus": file_qa_status or "unknown",
            }
        )
    asset_ids = [row["assetId"] for row in assets]
    profile_ids = sorted({row["profileId"] for row in assets if row["profileId"]})
    return {
        "schemaVersion": "seolleyeon_current_chunk_asset_whitelist_v3",
        "chunkId": chunk_id,
        "assetIds": asset_ids,
        "profileIds": profile_ids,
        "assetCount": len(asset_ids),
        "profileCount": len(profile_ids),
        "assets": assets,
    }


def write_current_chunk_whitelists(root: Path | str | None, chunk_id: str) -> dict[str, Any]:
    paths = pipeline_paths(root)
    chunk_dir = paths.reports / "chunks" / chunk_id
    chunk_dir.mkdir(parents=True, exist_ok=True)
    asset_payload = build_current_chunk_whitelist(root, chunk_id)
    by_profile: dict[str, list[str]] = {}
    for row in asset_payload["assets"]:
        by_profile.setdefault(str(row.get("profileId") or ""), []).append(str(row.get("assetId") or ""))
    profile_payload = {
        "schemaVersion": "seolleyeon_current_chunk_profile_whitelist_v3",
        "chunkId": chunk_id,
        "profileIds": asset_payload["profileIds"],
        "profileCount": asset_payload["profileCount"],
        "profiles": [
            {"profileId": profile_id, "assetIds": sorted(asset_ids)}
            for profile_id, asset_ids in sorted(by_profile.items())
            if profile_id
        ],
    }
    asset_path = chunk_dir / "current_chunk_asset_whitelist.json"
    profile_path = chunk_dir / "current_chunk_profile_whitelist.json"
    asset_path.write_text(json.dumps(asset_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    profile_path.write_text(json.dumps(profile_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "assetWhitelistPath": asset_path,
        "profileWhitelistPath": profile_path,
        "assetWhitelist": asset_payload,
        "profileWhitelist": profile_payload,
    }


def build_file_complete_identity_whitelist(root: Path | str | None, chunk_id: str) -> dict[str, Any]:
    paths = pipeline_paths(root)
    plan = _load_current_chunk_plan(root, chunk_id)
    state = _load_current_chunk_state(root, chunk_id)
    planned_assets = _planned_assets_from_chunk_plan(plan)
    generation_by_asset = {str(row.get("assetId") or ""): dict(row) for row in load_generation_manifest(paths)}
    file_qa_by_asset = _latest_by_asset_id(_chunk_file_qa_rows(paths, chunk_id))

    by_profile: dict[str, dict[str, Any]] = {}
    for asset in planned_assets:
        profile_id = str(asset.get("profileId") or "")
        if not profile_id:
            continue
        gender = str(asset.get("gender") or "")
        numeric_id = str(asset.get("numericId") or "")
        by_profile.setdefault(
            profile_id,
            {
                "profileId": profile_id,
                "gender": gender,
                "numericId": numeric_id,
                "assets": {},
                "_assetRows": [],
            },
        )
        generation_row = generation_by_asset.get(str(asset.get("assetId") or ""), {})
        final_path = str(asset.get("finalPath") or generation_row.get("finalPath") or "")
        final_file = _resolve_under_root(paths.root, final_path) if final_path else None
        file_qa = file_qa_by_asset.get(str(asset.get("assetId") or ""), {})
        file_qa_passed = _file_qa_passed_for_asset(str(asset.get("assetId") or ""), state, file_qa)
        file_qa_status = "file_qa_passed" if file_qa_passed else _file_qa_status(file_qa)
        row = {
            "assetId": str(asset.get("assetId") or ""),
            "profileId": profile_id,
            "gender": gender,
            "numericId": numeric_id,
            "shotType": str(asset.get("shotType") or generation_row.get("shotType") or ""),
            "finalPath": final_path,
            "fileExists": bool(final_file and final_file.is_file()),
            "fileQaStatus": file_qa_status,
            "targetFaceType": asset.get("targetFaceType") or generation_row.get("targetFaceType"),
            "targetLooksLevelBand": asset.get("targetLooksLevelBand") or generation_row.get("targetLooksLevelBand"),
        }
        by_profile[profile_id]["assets"][row["shotType"]] = {
            "assetId": row["assetId"],
            "fileQaStatus": row["fileQaStatus"],
            "finalPath": row["finalPath"],
        }
        by_profile[profile_id]["_assetRows"].append(row)

    included_profiles: list[dict[str, Any]] = []
    excluded_profiles: list[dict[str, Any]] = []
    flat_assets: list[dict[str, Any]] = []
    for profile_id, profile in sorted(by_profile.items()):
        rows_by_shot = {str(row.get("shotType") or ""): row for row in profile["_assetRows"]}
        missing_shots = [shot for shot in SHOT_ORDER if shot not in rows_by_shot]
        if missing_shots:
            excluded_profiles.append({"profileId": profile_id, "reason": f"missing_planned_{missing_shots[0]}"})
            continue
        failed_row = next((rows_by_shot[shot] for shot in SHOT_ORDER if rows_by_shot[shot]["fileQaStatus"] != "file_qa_passed"), None)
        if failed_row is not None:
            status = str(failed_row.get("fileQaStatus") or "unknown")
            shot = str(failed_row.get("shotType") or "unknown")
            reason = f"file_qa_failed_{shot}" if "failed" in status or "rejected" in status else f"file_qa_not_passed_{shot}"
            excluded_profiles.append({"profileId": profile_id, "reason": reason})
            continue
        missing_file = next((rows_by_shot[shot] for shot in SHOT_ORDER if not rows_by_shot[shot]["fileExists"]), None)
        if missing_file is not None:
            excluded_profiles.append({"profileId": profile_id, "reason": f"missing_file_{missing_file['shotType']}"})
            continue
        profile_payload = {
            "profileId": profile_id,
            "gender": profile["gender"],
            "numericId": profile["numericId"],
            "assets": {shot: rows_by_shot[shot] for shot in SHOT_ORDER},
        }
        included_profiles.append(profile_payload)
        flat_assets.extend(rows_by_shot[shot] for shot in SHOT_ORDER)

    return {
        "schemaVersion": "seolleyeon_file_complete_identity_whitelist_v3",
        "chunkId": chunk_id,
        "profileCount": len(included_profiles),
        "assetCount": len(flat_assets),
        "excludedProfiles": excluded_profiles,
        "profiles": included_profiles,
        "assetIds": [row["assetId"] for row in flat_assets],
        "profileIds": [row["profileId"] for row in included_profiles],
        "assets": flat_assets,
        "createdAt": now_utc(),
    }


def write_file_complete_identity_whitelist(root: Path | str | None, chunk_id: str) -> dict[str, Any]:
    paths = pipeline_paths(root)
    chunk_dir = paths.reports / "chunks" / chunk_id
    chunk_dir.mkdir(parents=True, exist_ok=True)
    asset_payload = build_file_complete_identity_whitelist(root, chunk_id)
    asset_path = chunk_dir / "file_complete_identity_whitelist.json"
    asset_path.write_text(json.dumps(asset_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    profile_payload = {
        "schemaVersion": "seolleyeon_file_complete_profile_whitelist_v3",
        "chunkId": chunk_id,
        "profileIds": asset_payload["profileIds"],
        "profileCount": asset_payload["profileCount"],
        "profiles": [
            {"profileId": profile["profileId"], "assetIds": [profile["assets"][shot]["assetId"] for shot in SHOT_ORDER]}
            for profile in asset_payload["profiles"]
        ],
        "createdAt": asset_payload["createdAt"],
    }
    profile_path = chunk_dir / "file_complete_profile_whitelist.json"
    profile_path.write_text(json.dumps(profile_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "assetWhitelistPath": asset_path,
        "profileWhitelistPath": profile_path,
        "assetWhitelist": asset_payload,
        "profileWhitelist": profile_payload,
    }


def existing_image_rows(
    rows: list[Mapping[str, Any]],
    *,
    limit: int | None,
    gender: str | None = None,
    shot_type: str | None = None,
    approved_only: bool = False,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        if gender and str(row.get("gender")) != gender:
            continue
        if shot_type and str(row.get("shotType")) != shot_type:
            continue
        candidate_paths = [Path(str(value)) for value in (row.get("finalPath"), row.get("localPath")) if str(value or "").strip()]
        image_path = next((path for path in candidate_paths if path.is_file()), None)
        if not image_path:
            continue
        if approved_only and str(row.get("status")) not in {"qa_approved", "vision_approved"}:
            continue
        enriched = dict(row)
        enriched["_contactSheetPath"] = str(image_path)
        selected.append(enriched)
        if limit and len(selected) >= limit:
            break
    return selected


def _draw_sheet(rows: list[Mapping[str, Any]], output_path: Path, *, columns: int, thumb_size: tuple[int, int]) -> ContactSheetResult:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("Pillow is required to generate contact sheets: pip install Pillow") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    safe_columns = max(1, int(columns))
    caption_height = 58
    if not rows:
        blank = Image.new("RGB", (thumb_size[0], 90), "white")
        draw = ImageDraw.Draw(blank)
        draw.text((8, 8), "No images", fill=(20, 20, 20))
        blank.save(output_path)
        return ContactSheetResult(output_path=output_path, image_count=0, columns=1, rows=1)

    row_count = (len(rows) + safe_columns - 1) // safe_columns
    cell_width, cell_height = thumb_size[0], thumb_size[1] + caption_height
    sheet = Image.new("RGB", (safe_columns * cell_width, row_count * cell_height), "white")
    draw = ImageDraw.Draw(sheet)

    for index, row in enumerate(rows):
        source = Path(str(row.get("_contactSheetPath") or row.get("localPath") or ""))
        with Image.open(source) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail(thumb_size)
            x = (index % safe_columns) * cell_width + (thumb_size[0] - thumb.width) // 2
            y = (index // safe_columns) * cell_height + (thumb_size[1] - thumb.height) // 2
            sheet.paste(thumb, (x, y))
        caption_y = (index // safe_columns) * cell_height + thumb_size[1] + 4
        caption = f"{row.get('assetId', '')}"
        if len(caption) > 34:
            caption = caption[:31] + "..."
        draw.text(((index % safe_columns) * cell_width + 6, caption_y), caption, fill=(20, 20, 20))
        draw.text(
            ((index % safe_columns) * cell_width + 6, caption_y + 18),
            f"{row.get('profileId', '')} {row.get('shotType', '')}",
            fill=(70, 70, 70),
        )

    sheet.save(output_path)
    return ContactSheetResult(output_path=output_path, image_count=len(rows), columns=safe_columns, rows=row_count)


def generate_contact_sheet(
    *,
    root: Path | str | None = None,
    output_name: str = "contact_sheet.png",
    limit: int | None = None,
    columns: int = 3,
    thumb_size: tuple[int, int] = (220, 220),
    gender: str | None = None,
    shot_type: str | None = None,
    approved_only: bool = False,
) -> ContactSheetResult:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    rows = existing_image_rows(
        load_generation_manifest(paths),
        limit=limit,
        gender=gender,
        shot_type=shot_type,
        approved_only=approved_only,
    )
    output_path = paths.reports / output_name
    return _draw_sheet(rows, output_path, columns=columns, thumb_size=thumb_size)


def generate_grouped_contact_sheets(
    *,
    root: Path | str | None = None,
    stage: str = "pilot",
    limit: int | None = None,
    columns: int = 4,
    approved_only: bool = False,
) -> list[ContactSheetResult]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    all_rows = load_generation_manifest(paths)
    results: list[ContactSheetResult] = []
    for gender in ("female", "male"):
        for shot_type in SHOT_ORDER:
            rows = existing_image_rows(
                all_rows,
                limit=limit,
                gender=gender,
                shot_type=shot_type,
                approved_only=approved_only,
            )
            output = paths.reports / "contact_sheets" / f"{stage}_contact_sheet_{gender}_{shot_type}.png"
            results.append(_draw_sheet(rows, output, columns=columns, thumb_size=(220, 300)))
    return results


def generate_identity_contact_sheets(
    *,
    root: Path | str | None = None,
    limit_identities: int | None = None,
    columns: int = 3,
    approved_only: bool = False,
) -> list[ContactSheetResult]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    all_rows = load_generation_manifest(paths)
    by_profile: dict[str, list[dict[str, Any]]] = {}
    for row in all_rows:
        by_profile.setdefault(str(row.get("profileId") or ""), []).append(dict(row))
    results: list[ContactSheetResult] = []
    for index, (profile_id, profile_rows) in enumerate(sorted(by_profile.items())):
        if limit_identities is not None and index >= limit_identities:
            break
        rows = existing_image_rows(sorted(profile_rows, key=lambda row: SHOT_ORDER.index(str(row.get("shotType"))) if str(row.get("shotType")) in SHOT_ORDER else 99), limit=None, approved_only=approved_only)
        output = paths.reports / "contact_sheets" / "identities" / f"{profile_id}.png"
        results.append(_draw_sheet(rows, output, columns=columns, thumb_size=(220, 300)))
    return results


def generate_chunk_contact_sheets(
    *,
    root: Path | str | None = None,
    chunk_size: int = 24,
    columns: int = 4,
    approved_only: bool = False,
) -> list[ContactSheetResult]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    all_rows = load_generation_manifest(paths)
    profile_ids = sorted({str(row.get("profileId") or "") for row in all_rows if bool(row.get("activeForTarget", True))})
    results: list[ContactSheetResult] = []
    for chunk_index in range(0, len(profile_ids), max(1, int(chunk_size))):
        chunk_profiles = set(profile_ids[chunk_index : chunk_index + max(1, int(chunk_size))])
        rows = existing_image_rows([row for row in all_rows if str(row.get("profileId") or "") in chunk_profiles], limit=None, approved_only=approved_only)
        output = paths.reports / "contact_sheets" / "chunks" / f"chunk_{chunk_index // max(1, int(chunk_size)) + 1:03d}.png"
        results.append(_draw_sheet(rows, output, columns=columns, thumb_size=(220, 300)))
    return results


def _generate_scoped_contact_sheets(
    *,
    root: Path | str | None = None,
    chunk_id: str,
    whitelist_bundle: Mapping[str, Any],
    sheet_scope: str,
    index_filename: str,
    columns: int = 4,
) -> dict[str, Any]:
    paths = pipeline_paths(root)
    ensure_base_dirs(paths)
    asset_whitelist = whitelist_bundle["assetWhitelist"]
    profile_ids = set(asset_whitelist["profileIds"])
    asset_ids = set(asset_whitelist["assetIds"])
    generation_by_asset = {str(row.get("assetId") or ""): dict(row) for row in load_generation_manifest(paths)}
    rows: list[dict[str, Any]] = []
    for planned in asset_whitelist["assets"]:
        asset_id = str(planned.get("assetId") or "")
        generation_row = dict(generation_by_asset.get(asset_id, {}))
        if not generation_row:
            continue
        final_path = str(planned.get("finalPath") or generation_row.get("finalPath") or "")
        local_path = str(generation_row.get("localPath") or "")
        image_path = next(
            (
                _resolve_under_root(paths.root, value)
                for value in (final_path, local_path)
                if value and _resolve_under_root(paths.root, value).is_file()
            ),
            None,
        )
        if image_path is None:
            continue
        generation_row.update(planned)
        generation_row["_contactSheetPath"] = str(image_path)
        rows.append(generation_row)

    out_dir = paths.reports / "chunks" / chunk_id / "contact_sheets"
    identity_dir = out_dir / "identities"
    identity_dir.mkdir(parents=True, exist_ok=True)
    sheets: list[dict[str, Any]] = []
    results: list[ContactSheetResult] = []

    asset_sheet_index = 0
    for gender in ("female", "male"):
        for shot_type in SHOT_ORDER:
            sheet_rows = [
                row
                for row in rows
                if str(row.get("gender") or "") == gender
                and str(row.get("shotType") or "") == shot_type
                and str(row.get("assetId") or "") in asset_ids
                and str(row.get("profileId") or "") in profile_ids
            ]
            if not sheet_rows:
                continue
            asset_sheet_index += 1
            output = out_dir / f"asset_sheet_{asset_sheet_index:03d}_{gender}_{shot_type}.png"
            result = _draw_sheet(sheet_rows, output, columns=columns, thumb_size=(220, 300))
            results.append(result)
            sheets.append(
                {
                    "sheetId": f"asset_sheet_{asset_sheet_index:03d}",
                    "sheetType": "asset",
                    "sheetPath": to_portable_path(output),
                    "assetIds": [str(row.get("assetId") or "") for row in sheet_rows],
                    "profileIds": sorted({str(row.get("profileId") or "") for row in sheet_rows if str(row.get("profileId") or "")}),
                    "outOfScopeAssetIds": [],
                }
            )

    by_profile: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_profile.setdefault(str(row.get("profileId") or ""), []).append(row)
    identity_sheet_index = 0
    for profile_id in asset_whitelist["profileIds"]:
        profile_rows = sorted(
            by_profile.get(profile_id, []),
            key=lambda row: SHOT_ORDER.index(str(row.get("shotType"))) if str(row.get("shotType")) in SHOT_ORDER else 99,
        )
        identity_sheet_index += 1
        output = identity_dir / f"{profile_id}.png"
        result = _draw_sheet(profile_rows, output, columns=3, thumb_size=(220, 300))
        results.append(result)
        sheets.append(
            {
                "sheetId": f"identity_sheet_{identity_sheet_index:03d}_{profile_id}",
                "sheetType": "identity",
                "sheetPath": to_portable_path(output),
                "assetIds": [str(row.get("assetId") or "") for row in profile_rows],
                "profileIds": [profile_id],
                "outOfScopeAssetIds": [],
            }
        )

    for sheet in sheets:
        out_of_scope = sorted(set(sheet["assetIds"]) - asset_ids)
        out_of_scope.extend(sorted(set(sheet["profileIds"]) - profile_ids))
        if out_of_scope:
            raise RuntimeError(f"Strict chunk contact sheet contains out-of-scope IDs: {out_of_scope}")

    index_payload = {
        "schemaVersion": "seolleyeon_contact_sheet_index_v3",
        "chunkId": chunk_id,
        "sheetScope": sheet_scope,
        "profileCount": len(profile_ids),
        "assetCount": len(asset_ids),
        "generatedAt": now_utc(),
        "assetWhitelistPath": to_portable_path(whitelist_bundle["assetWhitelistPath"]),
        "profileWhitelistPath": to_portable_path(whitelist_bundle["profileWhitelistPath"]),
        "whitelistPath": to_portable_path(whitelist_bundle["assetWhitelistPath"]),
        "sheets": sheets,
    }
    index_path = out_dir / index_filename
    index_path.write_text(json.dumps(index_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "outputs": [result.output_path for result in results],
        "imageCount": sum(result.image_count for result in results),
        "sheetCount": len(sheets),
        "assetSheetCount": sum(1 for sheet in sheets if sheet["sheetType"] == "asset"),
        "identitySheetCount": sum(1 for sheet in sheets if sheet["sheetType"] == "identity"),
        "contactSheetIndexPath": index_path,
        "assetWhitelistPath": whitelist_bundle["assetWhitelistPath"],
        "profileWhitelistPath": whitelist_bundle["profileWhitelistPath"],
    }


def generate_strict_chunk_contact_sheets(
    *,
    root: Path | str | None = None,
    chunk_id: str,
    columns: int = 4,
    asset_whitelist: Path | str | None = None,
) -> dict[str, Any]:
    if asset_whitelist:
        payload = json.loads(Path(asset_whitelist).read_text(encoding="utf-8-sig"))
        profile_payload = {
            "schemaVersion": "seolleyeon_explicit_profile_whitelist_v3",
            "chunkId": chunk_id,
            "profileIds": payload.get("profileIds", []),
            "profileCount": payload.get("profileCount", 0),
            "profiles": [
                {"profileId": profile_id, "assetIds": sorted(str(row.get("assetId") or "") for row in payload.get("assets", []) if str(row.get("profileId") or "") == profile_id)}
                for profile_id in payload.get("profileIds", [])
            ],
        }
        whitelist_bundle = {
            "assetWhitelistPath": Path(asset_whitelist).resolve(),
            "profileWhitelistPath": Path(asset_whitelist).resolve(),
            "assetWhitelist": payload,
            "profileWhitelist": profile_payload,
        }
    else:
        whitelist_bundle = write_current_chunk_whitelists(root, chunk_id)
    return _generate_scoped_contact_sheets(
        root=root,
        chunk_id=chunk_id,
        whitelist_bundle=whitelist_bundle,
        sheet_scope="current_chunk_only",
        index_filename="contact_sheet_index.json",
        columns=columns,
    )


def generate_file_complete_identity_contact_sheets(
    *,
    root: Path | str | None = None,
    chunk_id: str,
    columns: int = 4,
) -> dict[str, Any]:
    whitelist_bundle = write_file_complete_identity_whitelist(root, chunk_id)
    return _generate_scoped_contact_sheets(
        root=root,
        chunk_id=chunk_id,
        whitelist_bundle=whitelist_bundle,
        sheet_scope="file_complete_identities_only",
        index_filename="file_complete_contact_sheet_index.json",
        columns=columns,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate contact sheets for Seolleyeon AI image review.")
    parser.add_argument("--root", default=None, help="Workspace root. Defaults to the repository root.")
    parser.add_argument("--manifest", default=None, help="Compatibility option; generation_manifest.jsonl remains the source of truth.")
    parser.add_argument("--out_dir", default=None, help="Compatibility option for Makefile targets.")
    parser.add_argument("--output_name", default=None)
    parser.add_argument("--stage", choices=["pilot", "full", "smoke", "custom"], default="pilot")
    parser.add_argument("--grouped", action="store_true", help="Generate gender/shotType grouped contact sheets under reports/contact_sheets.")
    parser.add_argument("--identity_sheets", action="store_true", help="Generate one 3-shot contact sheet per identity.")
    parser.add_argument("--chunked", action="store_true", help="Generate review contact sheets split by identity chunks.")
    parser.add_argument("--chunk_size", type=int, default=24)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--gender", choices=["female", "male"], default=None)
    parser.add_argument("--shot_type", choices=list(SHOT_ORDER), default=None)
    parser.add_argument("--approved_only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.out_dir and not args.grouped and not args.output_name:
        args.grouped = True
    if args.grouped:
        results = generate_grouped_contact_sheets(
            root=args.root,
            stage=args.stage,
            limit=args.limit,
            columns=args.columns,
            approved_only=args.approved_only,
        )
        print(
            {
                "outputs": [str(result.output_path) for result in results],
                "imageCount": sum(result.image_count for result in results),
            }
        )
        if not args.identity_sheets and not args.chunked:
            return 0
    combined_results: list[ContactSheetResult] = []
    if args.identity_sheets:
        combined_results.extend(
            generate_identity_contact_sheets(
                root=args.root,
                limit_identities=args.limit,
                columns=3,
                approved_only=args.approved_only,
            )
        )
    if args.chunked:
        combined_results.extend(
            generate_chunk_contact_sheets(
                root=args.root,
                chunk_size=args.chunk_size,
                columns=args.columns,
                approved_only=args.approved_only,
            )
        )
    if combined_results:
        print(
            {
                "outputs": [str(result.output_path) for result in combined_results],
                "imageCount": sum(result.image_count for result in combined_results),
            }
        )
        return 0
    result = generate_contact_sheet(
        root=args.root,
        output_name=args.output_name or "contact_sheet.png",
        limit=args.limit,
        columns=args.columns,
        gender=args.gender,
        shot_type=args.shot_type,
        approved_only=args.approved_only,
    )
    print(
        {
            "outputPath": str(result.output_path),
            "imageCount": result.image_count,
            "columns": result.columns,
            "rows": result.rows,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
