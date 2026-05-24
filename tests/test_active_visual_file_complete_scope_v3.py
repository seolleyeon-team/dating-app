from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from PIL import Image

from scripts.ai_image_pipeline_v3.config import SHOT_ORDER, write_jsonl


CHUNK_ID = "chunk_20260514T225735Z"
EXCLUDED_PROFILES = {"female_052", "female_060", "female_066", "female_072"}


def _make_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (512, 768), (80, 100, 140)).save(path)


def _asset_row(root: Path, profile_id: str, shot_type: str) -> dict[str, Any]:
    gender, numeric_id = profile_id.split("_", 1)
    final_path = root / "ai_image" / gender / numeric_id / f"{shot_type}.png"
    return {
        "assetId": f"{profile_id}__{shot_type}__v001",
        "profileId": profile_id,
        "gender": gender,
        "numericId": numeric_id,
        "shotType": shot_type,
        "targetFaceType": "deer_like",
        "targetLooksLevelBand": "2.5-3.2",
        "finalPath": str(final_path),
        "localPath": str(final_path),
        "status": "file_qa_passed",
    }


def _write_prompts(root: Path) -> None:
    prompts = root / "ai_image" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    for name in (
        "VISUAL_VERDICT_ASSET_QA_PROMPT.md",
        "VISUAL_VERDICT_IDENTITY_QA_PROMPT.md",
        "VISUAL_VERDICT_DISTRIBUTION_AUDIT_PROMPT.md",
    ):
        (prompts / name).write_text("Return strict JSON only.", encoding="utf-8")


def _write_file_complete_fixture(root: Path) -> dict[str, dict[str, Any]]:
    _write_prompts(root)
    profile_ids = [f"female_{index:03d}" for index in range(49, 73)]
    planned_rows: list[dict[str, Any]] = []
    asset_states: dict[str, str] = {}
    rows_by_asset: dict[str, dict[str, Any]] = {}
    for profile_id in profile_ids:
        for shot in SHOT_ORDER:
            row = _asset_row(root, profile_id, shot)
            planned_rows.append(row)
            rows_by_asset[row["assetId"]] = row
            state = "file_qa_passed"
            if profile_id == "female_052" and shot == "vibe_card":
                state = "file_qa_failed"
            if profile_id == "female_060" and shot == "vibe_card":
                state = "planned"
            if profile_id in {"female_066", "female_072"} and shot == "face_card":
                state = "file_qa_failed"
            asset_states[row["assetId"]] = state
            if not (profile_id == "female_060" and shot == "vibe_card"):
                _make_png(Path(row["finalPath"]))

    extra_rows = [_asset_row(root, "female_901", shot) for shot in SHOT_ORDER]
    for row in extra_rows:
        _make_png(Path(row["finalPath"]))

    manifests = root / "ai_image" / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    write_jsonl(manifests / "generation_manifest.jsonl", [*planned_rows, *extra_rows])
    write_jsonl(manifests / "ai_profile_assets_v3.jsonl", planned_rows)
    (manifests / "current_chunk_plan.json").write_text(
        json.dumps(
            {
                "chunkId": CHUNK_ID,
                "identities": [
                    {
                        "profileId": profile_id,
                        "gender": "female",
                        "numericId": profile_id.split("_", 1)[1],
                        "assets": [row for row in planned_rows if row["profileId"] == profile_id],
                    }
                    for profile_id in profile_ids
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (manifests / "current_chunk_state.json").write_text(
        json.dumps({"chunkId": CHUNK_ID, "assetStates": asset_states}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return rows_by_asset


def _asset_payload(asset_ids: list[str], rows_by_asset: dict[str, dict[str, Any]]) -> dict[str, Any]:
    assets = []
    for asset_id in asset_ids:
        row = rows_by_asset[asset_id]
        assets.append(
            {
                "assetId": asset_id,
                "profileId": row["profileId"],
                "gender": row["gender"],
                "shotType": row["shotType"],
                "targetFaceType": "deer_like",
                "observedFaceType": "deer_like",
                "targetLooksLevelBand": "2.5-3.2",
                "observedLooksLevelBand": "2.5-3.2",
                "adultVisual": True,
                "photoRealism": 4.2,
                "brandFit": 4.2,
                "shotTypeReadable": True,
                "metadataMismatch": False,
                "decision": "approved",
            }
        )
    return {"qaType": "seolleyeon_visual_verdict_asset_v3", "checked": len(assets), "assets": assets}


class ActiveVisualFileCompleteScopeV3Tests(unittest.TestCase):
    def test_file_complete_whitelist_has_expected_20_profiles_and_60_assets(self):
        from scripts.ai_image_pipeline_v3.contact_sheet import build_file_complete_identity_whitelist

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_file_complete_fixture(root)

            whitelist = build_file_complete_identity_whitelist(root, CHUNK_ID)

            self.assertEqual(whitelist["profileCount"], 20)
            self.assertEqual(whitelist["assetCount"], 60)
            self.assertFalse(EXCLUDED_PROFILES.intersection(whitelist["profileIds"]))
            self.assertNotIn("female_901__face_card__v001", whitelist["assetIds"])

    def test_file_complete_contact_sheet_index_contains_only_whitelisted_assets(self):
        from scripts.ai_image_pipeline_v3.contact_sheet import generate_file_complete_identity_contact_sheets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_file_complete_fixture(root)

            result = generate_file_complete_identity_contact_sheets(root=root, chunk_id=CHUNK_ID)
            index = json.loads(Path(result["contactSheetIndexPath"]).read_text(encoding="utf-8"))
            sheet_asset_ids = {asset_id for sheet in index["sheets"] for asset_id in sheet["assetIds"]}
            sheet_profile_ids = {profile_id for sheet in index["sheets"] for profile_id in sheet["profileIds"]}

            self.assertEqual(index["sheetScope"], "file_complete_identities_only")
            self.assertEqual(len(sheet_asset_ids), 60)
            self.assertFalse(EXCLUDED_PROFILES.intersection(sheet_profile_ids))
            self.assertNotIn("female_901__face_card__v001", sheet_asset_ids)
            self.assertTrue(all(not sheet["outOfScopeAssetIds"] for sheet in index["sheets"]))

    def test_asset_visual_qa_uses_file_complete_index_and_rejects_out_of_scope(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import ActiveVisualConfig, ActiveVisualVerdictError, run_active_visual_asset_qa
        from scripts.ai_image_pipeline_v3.contact_sheet import generate_file_complete_identity_contact_sheets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows_by_asset = _write_file_complete_fixture(root)
            scope = generate_file_complete_identity_contact_sheets(root=root, chunk_id=CHUNK_ID)

            def run(args, **kwargs):
                if "--help" in args:
                    return subprocess.CompletedProcess(args, 0, stdout="--image -i", stderr="")
                prompt = kwargs.get("input") or ""
                match = re.search(r"allowedAssetIds: (\[.*?\])", prompt)
                asset_ids = json.loads(match.group(1)) if match else []
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(_asset_payload(asset_ids, rows_by_asset)), stderr="")

            result = run_active_visual_asset_qa(
                root=root,
                chunk_id=CHUNK_ID,
                strict_chunk_scope=True,
                asset_whitelist=scope["assetWhitelistPath"],
                contact_sheet_index=scope["contactSheetIndexPath"],
                config=ActiveVisualConfig(codex_bin="codex", image_arg_mode="auto", exec_mode="auto", timeout_sec=30, max_images_per_call=1, max_sheets_per_run=1, strict=True),
                run_func=run,
                apply_after=False,
            )

            self.assertLessEqual(result["checked"], 60)
            self.assertEqual(result["allowedAssetCount"], 20)

            def out_of_scope_run(args, **kwargs):
                if "--help" in args:
                    return subprocess.CompletedProcess(args, 0, stdout="--image -i", stderr="")
                return subprocess.CompletedProcess(
                    args,
                    0,
                    stdout=json.dumps(_asset_payload(["female_052__vibe_card__v001"], rows_by_asset)),
                    stderr="",
                )

            with self.assertRaises(ActiveVisualVerdictError):
                run_active_visual_asset_qa(
                    root=root,
                    chunk_id=CHUNK_ID,
                    strict_chunk_scope=True,
                    asset_whitelist=scope["assetWhitelistPath"],
                    contact_sheet_index=scope["contactSheetIndexPath"],
                    config=ActiveVisualConfig(codex_bin="codex", image_arg_mode="auto", exec_mode="auto", timeout_sec=30, max_images_per_call=1, max_sheets_per_run=1, strict=True),
                    run_func=out_of_scope_run,
                    apply_after=False,
                )


if __name__ == "__main__":
    unittest.main()
