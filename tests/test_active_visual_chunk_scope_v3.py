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


CHUNK_ID = "chunk_scope_test"


def _make_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (512, 768), (50, 90, 130)).save(path)


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


def _asset_payload(asset_ids: list[str], *, root: Path, rows_by_asset: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for asset_id in asset_ids:
        source = rows_by_asset[asset_id]
        rows.append(
            {
                "assetId": asset_id,
                "profileId": source["profileId"],
                "gender": source["gender"],
                "shotType": source["shotType"],
                "targetFaceType": "deer_like",
                "observedFaceType": "deer_like",
                "faceTypeConfidence": 0.9,
                "targetLooksLevelBand": "2.5-3.2",
                "observedLooksLevelBand": "2.5-3.2",
                "looksLevelConfidence": 0.9,
                "adultVisual": True,
                "photoRealism": 4.2,
                "campusRealism": 4.2,
                "brandFit": 4.2,
                "shotTypeReadable": True,
                "influencerRisk": 0,
                "childlikeRisk": 0,
                "schoolUniformRisk": 0,
                "sexualizationRisk": 0,
                "artifactRisk": 0,
                "metadataMismatch": False,
                "decision": "approved",
                "rejectReasons": [],
                "notes": f"reviewed in {root.name}",
            }
        )
    return {
        "qaType": "seolleyeon_visual_verdict_asset_v3",
        "sheetId": "strict_scope_test",
        "assets": rows,
        "summary": {
            "approvedCount": len(rows),
            "needsReviewCount": 0,
            "rejectedCount": 0,
            "hardRejectCount": 0,
            "metadataMismatchCount": 0,
        },
    }


class ActiveVisualChunkScopeV3Tests(unittest.TestCase):
    def _config(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import ActiveVisualConfig

        return ActiveVisualConfig(
            codex_bin="codex",
            image_arg_mode="auto",
            exec_mode="auto",
            timeout_sec=30,
            max_images_per_call=1,
            max_sheets_per_run=10,
            strict=True,
        )

    def _write_chunk_fixture(self, root: Path) -> dict[str, dict[str, Any]]:
        prompts = root / "ai_image" / "prompts"
        prompts.mkdir(parents=True, exist_ok=True)
        for name in (
            "VISUAL_VERDICT_ASSET_QA_PROMPT.md",
            "VISUAL_VERDICT_IDENTITY_QA_PROMPT.md",
            "VISUAL_VERDICT_DISTRIBUTION_AUDIT_PROMPT.md",
        ):
            (prompts / name).write_text("Return strict JSON only.", encoding="utf-8")

        planned_rows = [_asset_row(root, "female_001", shot) for shot in SHOT_ORDER]
        extra_rows = [
            _asset_row(root, "female_301", "face_card"),
            _asset_row(root, "female_901", "face_card"),
            _asset_row(root, "female_902", "silhouette_card"),
            _asset_row(root, "male_901", "vibe_card"),
        ]
        for row in [*planned_rows, *extra_rows]:
            _make_png(Path(row["finalPath"]))

        manifests = root / "ai_image" / "manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        write_jsonl(manifests / "generation_manifest.jsonl", [*planned_rows, *extra_rows])
        write_jsonl(manifests / "ai_profile_assets_v3.jsonl", planned_rows)
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
                for row in planned_rows
            ],
        )
        (manifests / "current_chunk_plan.json").write_text(
            json.dumps(
                {
                    "chunkId": CHUNK_ID,
                    "status": "needs_manual_review",
                    "identities": [
                        {
                            "profileId": "female_001",
                            "gender": "female",
                            "numericId": "001",
                            "assets": planned_rows,
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return {row["assetId"]: row for row in planned_rows}

    def _fake_run(self, root: Path, rows_by_asset: dict[str, dict[str, Any]], *, out_of_scope: bool = False):
        prompts: list[str] = []

        def run(args, **kwargs):
            if "--help" in args:
                return subprocess.CompletedProcess(args, 0, stdout="--image -i", stderr="")
            prompt = kwargs.get("input") or args[-1]
            prompts.append(prompt)
            if "seolleyeon_visual_verdict_identity_v3" in prompt:
                raise AssertionError("identity QA must not run after asset scope failure")
            match = re.search(r"allowedAssetIds: (\[.*?\])", prompt)
            asset_ids = json.loads(match.group(1)) if match else []
            if out_of_scope:
                asset_ids = ["female_301__face_card__v001"]
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps(_asset_payload(asset_ids, root=root, rows_by_asset=rows_by_asset)),
                stderr="",
            )

        run.prompts = prompts  # type: ignore[attr-defined]
        return run

    def test_strict_chunk_contact_sheet_index_excludes_extra_generation_assets(self):
        from scripts.ai_image_pipeline_v3.contact_sheet import generate_strict_chunk_contact_sheets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows_by_asset = self._write_chunk_fixture(root)
            result = generate_strict_chunk_contact_sheets(root=root, chunk_id=CHUNK_ID)
            index = json.loads(Path(result["contactSheetIndexPath"]).read_text(encoding="utf-8"))
            sheet_asset_ids = {asset_id for sheet in index["sheets"] for asset_id in sheet["assetIds"]}

            self.assertEqual(sheet_asset_ids, set(rows_by_asset))
            self.assertNotIn("female_301__face_card__v001", sheet_asset_ids)
            self.assertNotIn("female_901__face_card__v001", sheet_asset_ids)
            self.assertTrue(all(not sheet["outOfScopeAssetIds"] for sheet in index["sheets"]))

    def test_strict_asset_qa_uses_whitelist_prompt_and_applies_only_chunk_assets(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import run_active_visual_asset_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows_by_asset = self._write_chunk_fixture(root)
            fake_run = self._fake_run(root, rows_by_asset)
            result = run_active_visual_asset_qa(
                root=root,
                chunk_id=CHUNK_ID,
                strict_chunk_scope=True,
                config=self._config(),
                run_func=fake_run,
            )
            manifest_rows = (root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl").read_text(encoding="utf-8")

            self.assertEqual(result["checked"], 3)
            self.assertEqual(result["allowedAssetCount"], 3)
            self.assertIn("STRICT CURRENT-CHUNK SCOPE", "\n".join(fake_run.prompts))  # type: ignore[attr-defined]
            self.assertNotIn("female_301__face_card__v001", manifest_rows)
            self.assertNotIn("female_901__face_card__v001", manifest_rows)

    def test_out_of_scope_asset_payload_fails_before_apply(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import ActiveVisualVerdictError, run_active_visual_asset_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows_by_asset = self._write_chunk_fixture(root)
            rows_by_asset["female_301__face_card__v001"] = _asset_row(root, "female_301", "face_card")
            with self.assertRaises(ActiveVisualVerdictError):
                run_active_visual_asset_qa(
                    root=root,
                    chunk_id=CHUNK_ID,
                    strict_chunk_scope=True,
                    config=self._config(),
                    run_func=self._fake_run(root, rows_by_asset, out_of_scope=True),
                )

            self.assertFalse((root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl").exists())
            invalid = list((root / "ai_image" / "reports" / "visual_verdict" / "invalid").glob("asset_qa_out_of_scope_*.json"))
            self.assertTrue(invalid)

    def test_payload_larger_than_chunk_scope_fails_without_silent_drop(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import ActiveVisualVerdictError, validate_asset_payload_scope

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed = {f"asset_{index:03d}" for index in range(72)}
            payload = {
                "qaType": "seolleyeon_visual_verdict_asset_v3",
                "assets": [{"assetId": f"asset_{index % 72:03d}", "profileId": "profile_001"} for index in range(143)],
            }
            with self.assertRaises(ActiveVisualVerdictError):
                validate_asset_payload_scope(
                    payload,
                    root=root,
                    chunk_id=CHUNK_ID,
                    allowed_asset_ids=allowed,
                    allowed_profile_ids={"profile_001"},
                    expected_by_asset={asset_id: {"profileId": "profile_001"} for asset_id in allowed},
                )

            flag = root / "ai_image" / "manifests" / "manual_review_required.flag"
            self.assertIn("asset_visual_qa_payload_exceeds_chunk_scope", flag.read_text(encoding="utf-8"))

    def test_run_all_does_not_reach_identity_qa_when_asset_scope_fails(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import ActiveVisualVerdictError, run_active_visual_qa_all

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows_by_asset = self._write_chunk_fixture(root)
            rows_by_asset["female_301__face_card__v001"] = _asset_row(root, "female_301", "face_card")
            with self.assertRaises(ActiveVisualVerdictError):
                run_active_visual_qa_all(
                    root=root,
                    chunk_id=CHUNK_ID,
                    strict_chunk_scope=True,
                    config=self._config(),
                    run_func=self._fake_run(root, rows_by_asset, out_of_scope=True),
                )

            self.assertFalse((root / "ai_image" / "reports" / "visual_verdict" / "identity_qa_latest.json").exists())

    def test_distribution_audit_preserves_manual_review_flag(self):
        from scripts.ai_image_pipeline_v3.distribution_audit import audit_distribution

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = root / "ai_image" / "manifests"
            manifests.mkdir(parents=True, exist_ok=True)
            flag = manifests / "manual_review_required.flag"
            flag.write_text(
                json.dumps(
                    {
                        "schemaVersion": "seolleyeon_visual_distribution_audit_apply_v3",
                        "needsManualReview": True,
                        "disagreements": ["approvedImageCount"],
                    }
                ),
                encoding="utf-8",
            )

            audit_distribution(root=root, write_outputs=True)

            self.assertTrue(flag.exists())

    def test_visual_qa_success_bookkeeping_marks_chunk_flags_only(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import mark_current_chunk_visual_qa_complete

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = root / "ai_image" / "manifests"
            manifests.mkdir(parents=True, exist_ok=True)
            state_path = manifests / "current_chunk_state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "seolleyeon_bounded_chunk_state_v3",
                        "chunkId": CHUNK_ID,
                        "status": "needs_manual_review",
                        "activeVisualQaComplete": False,
                        "distributionAuditComplete": False,
                    }
                ),
                encoding="utf-8",
            )

            result = mark_current_chunk_visual_qa_complete(root=root, chunk_id=CHUNK_ID, distribution_audit_complete=True)
            state = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertTrue(result["updated"])
            self.assertTrue(state["activeVisualQaComplete"])
            self.assertTrue(state["distributionAuditComplete"])
            self.assertEqual(state["status"], "needs_manual_review")


if __name__ == "__main__":
    unittest.main()
