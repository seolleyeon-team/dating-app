from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from scripts.ai_image_pipeline_v3.config import SHOT_ORDER, prompt_hash, write_jsonl
from scripts.ai_image_pipeline_v3.distribution_targets import DEFAULT_DISTRIBUTION_TARGETS
from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module


def write_small_targets(
    root: Path,
    *,
    gender: str = "female",
    face_type: str = "deer_like",
    looks_band: str = "2.5-3.2",
    has_eyewear: bool = False,
    season: str = "spring",
) -> None:
    targets = copy.deepcopy(DEFAULT_DISTRIBUTION_TARGETS)
    female_count = 1 if gender == "female" else 0
    male_count = 1 if gender == "male" else 0
    targets["finalTarget"].update(
        {
            "approvedCompleteIdentities": 1,
            "approvedImages": 3,
            "femaleApprovedIdentities": female_count,
            "maleApprovedIdentities": male_count,
        }
    )
    for scope in ("global", "female", "male"):
        for bucket in targets["faceTypeTargets"][scope]:
            targets["faceTypeTargets"][scope][bucket] = 0
        for bucket in targets["looksLevelBandTargets"][scope]:
            targets["looksLevelBandTargets"][scope][bucket] = 0
    targets["faceTypeTargets"]["global"][face_type] = 1
    targets["looksLevelBandTargets"]["global"][looks_band] = 1
    targets["faceTypeTargets"][gender][face_type] = 1
    targets["looksLevelBandTargets"][gender][looks_band] = 1
    eyewear_bucket = "with_eyewear" if has_eyewear else "without_eyewear"
    for scope in ("global", "female", "male"):
        targets["eyewearTargets"][scope] = {"with_eyewear": 0, "without_eyewear": 0}
    targets["eyewearTargets"]["global"][eyewear_bucket] = 1
    targets["eyewearTargets"][gender][eyewear_bucket] = 1
    targets["seasonTargets"] = {"global": {"spring": 0, "summer": 0, "autumn": 0, "winter": 0}}
    targets["seasonTargets"]["global"][season] = 1
    path = root / "ai_image" / "config" / "AI_IMAGE_DISTRIBUTION_TARGETS_V3.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")


def make_png(path: Path, color: tuple[int, int, int] = (40, 90, 140)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (512, 768), color)
    draw = ImageDraw.Draw(image)
    draw.ellipse((176, 90, 336, 250), fill=(168, 132, 112))
    draw.rectangle((210, 250, 302, 500), fill=(max(0, color[0] - 20), max(0, color[1] - 20), max(0, color[2] - 20)))
    draw.line((190, 320, 125, 500), fill=(70, 90, 120), width=14)
    draw.line((322, 320, 387, 500), fill=(70, 90, 120), width=14)
    image.save(path)


def identity_asset_rows(
    root: Path,
    *,
    profile_id: str = "female_001",
    face_type: str = "deer_like",
    looks_band: str = "2.5-3.2",
    has_eyewear: bool = False,
    season: str = "spring",
) -> list[dict[str, Any]]:
    gender, numeric_id = profile_id.split("_", 1)
    prompt_module = load_prompt_module()
    prompt_builder_version = str(getattr(prompt_module, "PROMPT_BUILDER_VERSION", ""))
    prompt_targeting_version = str(getattr(prompt_module, "PROMPT_TARGETING_VERSION", ""))
    rows: list[dict[str, Any]] = []
    for shot in SHOT_ORDER:
        prompt = f"prompt for {profile_id} {shot}"
        final_path = root / "ai_image" / gender / numeric_id / f"{shot}.png"
        rows.append(
            {
                "assetId": f"{profile_id}__{shot}__v001",
                "profileId": profile_id,
                "gender": gender,
                "numericId": numeric_id,
                "shotType": shot,
                "prompt": prompt,
                "promptHash": prompt_hash(prompt),
                "promptBuilderVersion": prompt_builder_version,
                "promptTargetingVersion": prompt_targeting_version,
                "targetFaceType": face_type,
                "targetLooksLevel": 3.0,
                "targetLooksLevelBand": looks_band,
                "observedFaceType": face_type,
                "observedLooksLevelBand": looks_band,
                "hasEyewear": has_eyewear,
                "eyewearGroup": "glasses" if has_eyewear else "none",
                "season": season,
                "finalPath": str(final_path),
                "expectedFinalPath": str(final_path),
                "localPath": str(final_path),
                "status": "file_qa_passed",
                "activeForTarget": True,
                "isReserve": False,
            }
        )
    return rows


def write_identity_fixture(
    root: Path,
    *,
    profile_id: str = "female_001",
    face_type: str = "deer_like",
    looks_band: str = "2.5-3.2",
    has_eyewear: bool = False,
    season: str = "spring",
    write_targets: bool = True,
    make_files: bool = True,
    write_asset_manifest: bool = True,
    write_generation_manifest: bool = True,
    write_file_qa: bool = True,
    write_asset_qa: bool = True,
    write_identity_qa: bool = True,
    write_approved_manifest: bool = True,
    asset_decision: str = "approved",
    identity_decision: str = "approved",
    metadata_mismatch: bool = False,
    omit_asset_qa_shots: set[str] | None = None,
) -> list[dict[str, Any]]:
    if write_targets:
        write_small_targets(
            root,
            gender=profile_id.split("_", 1)[0],
            face_type=face_type,
            looks_band=looks_band,
            has_eyewear=has_eyewear,
            season=season,
        )
    manifests = root / "ai_image" / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    rows = identity_asset_rows(
        root,
        profile_id=profile_id,
        face_type=face_type,
        looks_band=looks_band,
        has_eyewear=has_eyewear,
        season=season,
    )
    if make_files:
        for index, row in enumerate(rows):
            make_png(Path(row["finalPath"]), (40 + index * 40, 80, 140))
    if write_asset_manifest:
        write_jsonl(manifests / "ai_profile_assets_v3.jsonl", rows)
    if write_generation_manifest:
        write_jsonl(manifests / "generation_manifest.jsonl", rows)
    if write_file_qa:
        write_jsonl(
            manifests / "file_qa_manifest.jsonl",
            [
                {
                    "assetId": row["assetId"],
                    "profileId": row["profileId"],
                    "gender": row["gender"],
                    "shotType": row["shotType"],
                    "qaStage": "file_qa",
                    "decision": "file_qa_passed",
                    "status": "file_qa_passed",
                }
                for row in rows
            ],
        )
    omitted = omit_asset_qa_shots or set()
    if write_asset_qa:
        write_jsonl(
            manifests / "asset_qa_manifest.jsonl",
            [
                {
                    "schemaVersion": "seolleyeon_asset_qa_manifest_v3",
                    "assetId": row["assetId"],
                    "profileId": row["profileId"],
                    "gender": row["gender"],
                    "numericId": row["numericId"],
                    "shotType": row["shotType"],
                    "targetFaceType": face_type,
                    "observedFaceType": face_type,
                    "targetLooksLevelBand": looks_band,
                    "observedLooksLevelBand": looks_band,
                    "finalDecision": asset_decision,
                    "decision": asset_decision,
                    "status": f"vision_{asset_decision}",
                    "metadataMismatch": metadata_mismatch,
                }
                for row in rows
                if row["shotType"] not in omitted
            ],
        )
    asset_ids = {row["shotType"]: row["assetId"] for row in rows}
    asset_decisions = {shot: asset_decision for shot in SHOT_ORDER}
    if write_identity_qa:
        write_jsonl(
            manifests / "identity_qa_manifest.jsonl",
            [
                {
                    "schemaVersion": "seolleyeon_identity_qa_manifest_v3",
                    "profileId": profile_id,
                    "gender": profile_id.split("_", 1)[0],
                    "numericId": profile_id.split("_", 1)[1],
                    "targetFaceType": face_type,
                    "observedFaceType": face_type,
                    "targetLooksLevelBand": looks_band,
                    "observedLooksLevelBand": looks_band,
                    "assetIds": asset_ids,
                    "assetDecisions": asset_decisions,
                    "sameIdentity": True,
                    "completeIdentityDecision": identity_decision,
                    "finalCompleteIdentityDecision": identity_decision,
                    "countsTowardDistribution": identity_decision == "approved",
                    "metadataMismatch": metadata_mismatch,
                    "hasEyewear": has_eyewear,
                    "eyewearGroup": "glasses" if has_eyewear else "none",
                    "season": season,
                }
            ],
        )
    if write_approved_manifest:
        write_jsonl(
            manifests / "approved_identity_manifest.jsonl",
            [
                {
                    "schemaVersion": "seolleyeon_approved_identity_manifest_v3",
                    "profileId": profile_id,
                    "gender": profile_id.split("_", 1)[0],
                    "numericId": profile_id.split("_", 1)[1],
                    "faceType": face_type,
                    "looksLevelBand": looks_band,
                    "observedFaceType": face_type,
                    "observedLooksLevelBand": looks_band,
                    "assetIds": asset_ids,
                    "finalPaths": {row["shotType"]: row["finalPath"] for row in rows},
                    "countsTowardDistribution": True,
                    "metadataMismatch": metadata_mismatch,
                    "hasEyewear": has_eyewear,
                    "eyewearGroup": "glasses" if has_eyewear else "none",
                    "season": season,
                }
            ],
        )
    return rows
