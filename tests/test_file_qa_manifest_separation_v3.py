import json
import tempfile
import unittest
from pathlib import Path

from tests.ai_image_strict_fixture import identity_asset_rows, make_png


class FileQaManifestSeparationV3Tests(unittest.TestCase):
    def _write_generation(self, root: Path) -> list[dict]:
        from scripts.ai_image_pipeline_v3.config import write_jsonl

        rows = identity_asset_rows(root)
        for index, row in enumerate(rows):
            make_png(Path(row["finalPath"]), (40 + index * 40, 90, 140))
            row["localPath"] = row["finalPath"]
            row["status"] = "recovered_pending_qa"
        manifests = root / "ai_image" / "manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        write_jsonl(manifests / "generation_manifest.jsonl", rows)
        return rows

    def _asset_payload(self, rows: list[dict], path: Path) -> None:
        payload = {
            "qaType": "seolleyeon_visual_verdict_asset_v3",
            "sheetId": "unit",
            "checked": len(rows),
            "assets": [
                {
                    "assetId": row["assetId"],
                    "profileId": row["profileId"],
                    "gender": row["gender"],
                    "shotType": row["shotType"],
                    "targetFaceType": "deer_like",
                    "observedFaceType": "deer_like",
                    "faceTypeConfidence": 0.9,
                    "targetLooksLevelBand": "2.5-3.2",
                    "observedLooksLevelBand": "2.5-3.2",
                    "looksLevelConfidence": 0.9,
                    "adultVisual": True,
                    "photoRealism": 4.4,
                    "brandFit": 4.4,
                    "shotTypeReadable": True,
                    "metadataMismatch": False,
                    "decision": "approved",
                }
                for row in rows
            ],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_file_qa_writes_only_file_qa_manifest_and_reports(self):
        from scripts.ai_image_pipeline_v3.qa import qa_images

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_generation(root)

            counts = qa_images(root=root, limit=3)

            self.assertEqual(counts["file_qa_passed"], 3)
            self.assertEqual(counts["approved"], 0)
            self.assertTrue((root / "ai_image" / "manifests" / "file_qa_manifest.jsonl").exists())
            self.assertTrue((root / "ai_image" / "reports" / "file_qa_report.json").exists())
            self.assertTrue((root / "ai_image" / "reports" / "file_qa_report.csv").exists())
            self.assertFalse((root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl").exists())
            self.assertFalse((root / "ai_image" / "manifests" / "approved_identity_manifest.jsonl").exists())

    def test_cli_file_qa_only_file_complete_identities_checks_vision_approved_assets(self):
        from scripts.ai_image_pipeline_v3.cli import main
        from scripts.ai_image_pipeline_v3.config import read_jsonl, write_jsonl

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = self._write_generation(root)
            for row in rows:
                row["status"] = "vision_approved"
                row["visualDecision"] = "approved"
                row["identityDecision"] = "approved"
            write_jsonl(root / "ai_image" / "manifests" / "generation_manifest.jsonl", rows)

            exit_code = main(["file-qa", "--root", str(root), "--only-file-complete-identities"])

            self.assertEqual(exit_code, 0)
            file_qa_rows = read_jsonl(root / "ai_image" / "manifests" / "file_qa_manifest.jsonl")
            self.assertEqual(len(file_qa_rows), 3)
            self.assertTrue(all(row["status"] == "file_qa_passed" for row in file_qa_rows))
            self.assertFalse((root / "ai_image" / "manifests" / "approved_identity_manifest.jsonl").exists())

    def test_file_qa_does_not_modify_existing_visual_manifest(self):
        from scripts.ai_image_pipeline_v3.qa import qa_images

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_generation(root)
            visual_manifest = root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl"
            visual_manifest.write_text('{"schemaVersion":"seolleyeon_asset_qa_manifest_v3","assetId":"kept"}\n', encoding="utf-8")

            qa_images(root=root, limit=3)

            self.assertEqual(visual_manifest.read_text(encoding="utf-8"), '{"schemaVersion":"seolleyeon_asset_qa_manifest_v3","assetId":"kept"}\n')

    def test_legacy_integrity_approval_option_is_disabled(self):
        from scripts.ai_image_pipeline_v3.qa import qa_images

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_generation(root)

            with self.assertRaises(ValueError):
                qa_images(root=root, limit=1, approve_integrity_only=True)

    def test_visual_asset_qa_apply_is_the_asset_manifest_writer(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_asset_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = self._write_generation(root)
            payload_path = root / "asset_qa.json"
            self._asset_payload(rows, payload_path)

            result = apply_asset_qa(root=root, input_path=str(payload_path))

            self.assertEqual(result["approved"], 3)
            self.assertTrue((root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl").exists())
            self.assertFalse((root / "ai_image" / "manifests" / "approved_identity_manifest.jsonl").exists())

    def test_leakage_audit_flags_file_qa_rows_inside_visual_manifest(self):
        from scripts.ai_image_pipeline_v3.qa import audit_file_qa_leakage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl"
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text('{"qaStage":"file_qa","assetId":"bad"}\n', encoding="utf-8")

            result = audit_file_qa_leakage(root=root)

            self.assertFalse(result["passed"])
            self.assertEqual(result["suspiciousCount"], 1)


if __name__ == "__main__":
    unittest.main()
