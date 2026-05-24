from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from PIL import Image

from scripts.ai_image_pipeline_v3.config import write_jsonl


CHUNK_ID = "chunk_metadata_001"


def _write_prompts(root: Path) -> None:
    prompts = root / "ai_image" / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    for name in (
        "VISUAL_VERDICT_ASSET_QA_PROMPT.md",
        "VISUAL_VERDICT_IDENTITY_QA_PROMPT.md",
        "VISUAL_VERDICT_DISTRIBUTION_AUDIT_PROMPT.md",
    ):
        (prompts / name).write_text("Return strict JSON only.", encoding="utf-8")


def _make_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (512, 768), (90, 120, 150)).save(path)


def _asset_row(root: Path, index: int, *, face_type: str = "deer_like", looks: str = "2.5-3.2") -> dict[str, Any]:
    profile_id = f"female_{index:03d}"
    shot_type = "face_card"
    final_path = root / "ai_image" / "female" / f"{index:03d}" / f"{shot_type}.png"
    return {
        "assetId": f"{profile_id}__{shot_type}__v001",
        "profileId": profile_id,
        "gender": "female",
        "numericId": f"{index:03d}",
        "shotType": shot_type,
        "targetFaceType": face_type,
        "targetLooksLevelBand": looks,
        "targetLooksLevel": 3.0,
        "season": "spring",
        "promptHash": f"hash-{index}",
        "finalPath": str(final_path),
        "localPath": str(final_path),
        "prompt": "PROMPT_TEXT_SHOULD_NOT_BE_VISIBLE_" + ("x" * 50000),
    }


def _write_scope_fixture(root: Path, count: int = 3) -> list[dict[str, Any]]:
    _write_prompts(root)
    rows = [_asset_row(root, index) for index in range(1, count + 1)]
    for row in rows:
        _make_png(Path(row["finalPath"]))
    manifests = root / "ai_image" / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    write_jsonl(manifests / "generation_manifest.jsonl", rows)
    write_jsonl(manifests / "ai_profile_assets_v3.jsonl", rows)
    write_jsonl(
        manifests / "file_qa_manifest.jsonl",
        [
            {
                "assetId": row["assetId"],
                "profileId": row["profileId"],
                "gender": row["gender"],
                "shotType": row["shotType"],
                "status": "file_qa_passed",
                "decision": "file_qa_passed",
            }
            for row in rows
        ],
    )
    (manifests / "current_chunk_plan.json").write_text(
        json.dumps(
            {
                "chunkId": CHUNK_ID,
                "identities": [
                    {
                        "profileId": row["profileId"],
                        "gender": row["gender"],
                        "numericId": row["numericId"],
                        "targetFaceType": row["targetFaceType"],
                        "targetLooksLevelBand": row["targetLooksLevelBand"],
                        "assets": [row],
                    }
                    for row in rows
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (manifests / "current_chunk_state.json").write_text(json.dumps({"chunkId": CHUNK_ID, "assetStates": {row["assetId"]: "file_qa_passed" for row in rows}}), encoding="utf-8")
    chunk_dir = root / "ai_image" / "reports" / "chunks" / CHUNK_ID
    sheet_path = chunk_dir / "contact_sheets" / "asset_sheet_001.png"
    _make_png(sheet_path)
    whitelist_path = chunk_dir / "current_chunk_asset_whitelist.json"
    whitelist_path.parent.mkdir(parents=True, exist_ok=True)
    whitelist = {
        "schemaVersion": "seolleyeon_current_chunk_asset_whitelist_v3",
        "chunkId": CHUNK_ID,
        "assetIds": [row["assetId"] for row in rows],
        "profileIds": [row["profileId"] for row in rows],
        "assetCount": len(rows),
        "profileCount": len(rows),
        "assets": [
            {
                "assetId": row["assetId"],
                "profileId": row["profileId"],
                "gender": row["gender"],
                "numericId": row["numericId"],
                "shotType": row["shotType"],
                "targetFaceType": row["targetFaceType"],
                "targetLooksLevelBand": row["targetLooksLevelBand"],
                "finalPath": row["finalPath"],
                "fileQaStatus": "file_qa_passed",
            }
            for row in rows
        ],
    }
    whitelist_path.write_text(json.dumps(whitelist, ensure_ascii=False, indent=2), encoding="utf-8")
    index_path = chunk_dir / "contact_sheets" / "contact_sheet_index.json"
    index_path.write_text(
        json.dumps(
            {
                "schemaVersion": "seolleyeon_contact_sheet_index_v3",
                "chunkId": CHUNK_ID,
                "sheetScope": "current_chunk_only",
                "sheets": [
                    {
                        "sheetId": "asset_sheet_001",
                        "sheetType": "asset",
                        "sheetPath": str(sheet_path),
                        "assetIds": [row["assetId"] for row in rows],
                        "profileIds": [row["profileId"] for row in rows],
                        "outOfScopeAssetIds": [],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return rows


def _asset_payload(rows: list[dict[str, Any]], *, target_face: str | None = None, target_looks: str | None = None, mismatch_second: bool = False) -> dict[str, Any]:
    assets = []
    for index, row in enumerate(rows):
        observed_face = "dog_like" if mismatch_second and index == 1 else row["targetFaceType"]
        assets.append(
            {
                "assetId": row["assetId"],
                "profileId": row["profileId"],
                "gender": row["gender"],
                "shotType": row["shotType"],
                "targetFaceType": target_face if target_face is not None else row["targetFaceType"],
                "observedFaceType": observed_face,
                "faceTypeConfidence": 0.9,
                "targetLooksLevelBand": target_looks if target_looks is not None else row["targetLooksLevelBand"],
                "observedLooksLevelBand": row["targetLooksLevelBand"],
                "looksLevelConfidence": 0.9,
                "adultVisual": True,
                "photoRealism": 4.2,
                "campusRealism": 4.2,
                "brandFit": 4.2,
                "shotTypeReadable": True,
                "influencerRisk": 0.0,
                "childlikeRisk": 0.0,
                "schoolUniformRisk": 0.0,
                "sexualizationRisk": 0.0,
                "artifactRisk": 0.0,
                "metadataMismatch": False,
                "mismatchFields": [],
                "decision": "approved",
                "rejectReasons": [],
                "notes": "fixture",
            }
        )
    return {
        "qaType": "seolleyeon_visual_verdict_asset_v3",
        "checked": len(assets),
        "sheetId": "asset_sheet_001",
        "assets": assets,
        "summary": {"approvedCount": len(assets), "needsReviewCount": 0, "rejectedCount": 0},
    }


class ActiveVisualMetadataInjectionV3Tests(unittest.TestCase):
    def _config(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import ActiveVisualConfig

        return ActiveVisualConfig(codex_bin="codex", image_arg_mode="auto", exec_mode="auto", timeout_sec=30, max_images_per_call=1, max_sheets_per_run=1, strict=True)

    def test_compact_visible_metadata_excludes_prompt_text_and_keeps_targets(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import ContactSheetEntry, build_asset_prompt

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = _write_scope_fixture(root, count=3)
            entry = ContactSheetEntry("asset_sheet_001", root / "sheet.png", "asset", tuple(row["assetId"] for row in rows), tuple(row["profileId"] for row in rows))

            prompt = build_asset_prompt(root, entry)

            self.assertIn("compactVisibleMetadata:", prompt)
            self.assertNotIn("PROMPT_TEXT_SHOULD_NOT_BE_VISIBLE", prompt)
            self.assertIn("Copy targetFaceType and targetLooksLevelBand exactly", prompt)
            for row in rows:
                self.assertIn(row["assetId"], prompt)
                self.assertIn('"targetFaceType":"deer_like"', prompt)
                self.assertIn('"targetLooksLevelBand":"2.5-3.2"', prompt)

    def test_asset_payload_with_unknown_target_is_rejected_before_apply(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import ActiveVisualVerdictError, run_active_visual_asset_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = _write_scope_fixture(root, count=1)
            chunk_dir = root / "ai_image" / "reports" / "chunks" / CHUNK_ID

            def run(args, **kwargs):
                if "--help" in args:
                    return subprocess.CompletedProcess(args, 0, stdout="--image -i", stderr="")
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(_asset_payload(rows, target_face="unknown")), stderr="")

            with self.assertRaises(ActiveVisualVerdictError) as raised:
                run_active_visual_asset_qa(
                    root=root,
                    chunk_id=CHUNK_ID,
                    strict_chunk_scope=True,
                    asset_whitelist=chunk_dir / "current_chunk_asset_whitelist.json",
                    contact_sheet_index=chunk_dir / "contact_sheets" / "contact_sheet_index.json",
                    config=self._config(),
                    run_func=run,
                )

            self.assertIn("visual_qa_target_metadata_unknown", str(raised.exception))

    def test_apply_rejects_old_payload_with_unknown_target(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_asset_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = _write_scope_fixture(root, count=1)
            payload_path = root / "asset_qa_latest.json"
            payload_path.write_text(json.dumps(_asset_payload(rows, target_looks="unknown"), ensure_ascii=False), encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                apply_asset_qa(root=root, input_path=str(payload_path))

            self.assertIn("visual_qa_target_metadata_unknown", str(raised.exception))

    def test_raw_and_applied_asset_counts_are_reported_separately(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import run_active_visual_asset_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = _write_scope_fixture(root, count=2)
            chunk_dir = root / "ai_image" / "reports" / "chunks" / CHUNK_ID

            def run(args, **kwargs):
                if "--help" in args:
                    return subprocess.CompletedProcess(args, 0, stdout="--image -i", stderr="")
                prompt = kwargs.get("input") or ""
                self.assertIn("allowedAssetIds: [", prompt)
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(_asset_payload(rows, mismatch_second=True)), stderr="")

            result = run_active_visual_asset_qa(
                root=root,
                chunk_id=CHUNK_ID,
                strict_chunk_scope=True,
                asset_whitelist=chunk_dir / "current_chunk_asset_whitelist.json",
                contact_sheet_index=chunk_dir / "contact_sheets" / "contact_sheet_index.json",
                config=self._config(),
                run_func=run,
                apply_after=True,
            )

            self.assertEqual(result["rawAssetQaCounts"], {"approved": 2, "needs_review": 0, "rejected": 0})
            self.assertEqual(result["appliedAssetQaCounts"], {"approved": 1, "needs_review": 1, "rejected": 0})
            self.assertEqual(result["downgradeSummary"]["rawApprovedButAppliedDowngraded"], 1)


if __name__ == "__main__":
    unittest.main()
