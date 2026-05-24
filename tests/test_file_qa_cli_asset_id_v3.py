import json
import tempfile
import unittest
from pathlib import Path


class FileQaCliAssetIdV3Tests(unittest.TestCase):
    def _make_png(self, path: Path) -> None:
        from PIL import Image, ImageDraw
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (1024, 1536), color=(200, 200, 200))
        draw = ImageDraw.Draw(image)
        draw.ellipse((352, 180, 672, 500), fill=(168, 132, 112))
        draw.rectangle((420, 500, 604, 980), fill=(80, 110, 150))
        draw.line((380, 640, 250, 980), fill=(70, 90, 120), width=28)
        draw.line((644, 640, 774, 980), fill=(70, 90, 120), width=28)
        image.save(path)

    def test_inspect_image_rejects_black_or_near_empty_content(self):
        from PIL import Image
        from scripts.ai_image_pipeline_v3.qa import inspect_image_detail
        with tempfile.TemporaryDirectory() as tmp:
            black = Path(tmp) / "black.png"
            empty = Path(tmp) / "empty.png"
            valid = Path(tmp) / "valid.png"
            Image.new("RGB", (1024, 1536), color=(2, 2, 2)).save(black)
            Image.new("RGB", (1024, 1536), color=(200, 200, 200)).save(empty)
            self._make_png(valid)

            black_detail = inspect_image_detail(black)
            empty_detail = inspect_image_detail(empty)
            valid_detail = inspect_image_detail(valid)

        self.assertFalse(black_detail["ok"])
        self.assertIn("near_black_or_no_visible_content", black_detail["reasons"])
        self.assertFalse(empty_detail["ok"])
        self.assertIn("low_visual_detail_or_near_empty", empty_detail["reasons"])
        self.assertTrue(valid_detail["ok"], valid_detail)

    def test_file_qa_asset_id_checks_exactly_one_asset(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.qa import qa_images
        with tempfile.TemporaryDirectory() as tmp:
            paths = pipeline_paths(tmp)
            paths.manifests.mkdir(parents=True, exist_ok=True)
            paths.reports.mkdir(parents=True, exist_ok=True)
            img1 = Path(tmp) / "ai_image" / "female" / "001" / "face_card.png"
            img2 = Path(tmp) / "ai_image" / "female" / "002" / "face_card.png"
            self._make_png(img1); self._make_png(img2)
            rows = [
                {"assetId": "a1", "profileId": "female_001", "gender": "female", "numericId": "001", "shotType": "face_card", "status": "recovered_pending_qa", "localPath": str(img1), "finalPath": str(img1), "promptHash": "h1", "promptTargetingVersion": "face_type_looks_level_targeting_v2"},
                {"assetId": "a2", "profileId": "female_002", "gender": "female", "numericId": "002", "shotType": "face_card", "status": "recovered_pending_qa", "localPath": str(img2), "finalPath": str(img2), "promptHash": "h2", "promptTargetingVersion": "face_type_looks_level_targeting_v2"},
            ]
            write_jsonl(paths.manifests / "generation_manifest.jsonl", rows)
            counts = qa_images(root=tmp, asset_id="a1")
            report = json.loads((paths.reports / "file_qa_report.json").read_text(encoding="utf-8"))
        self.assertEqual(counts["checked"], 1)
        self.assertEqual(report["rows"][0]["assetId"], "a1")

    def test_file_qa_missing_asset_id_does_not_clobber_existing_manifest(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.qa import qa_images
        with tempfile.TemporaryDirectory() as tmp:
            paths = pipeline_paths(tmp)
            paths.manifests.mkdir(parents=True, exist_ok=True)
            paths.reports.mkdir(parents=True, exist_ok=True)
            existing = paths.manifests / "file_qa_manifest.jsonl"
            existing.write_text('{"assetId":"keep"}\n', encoding="utf-8")
            write_jsonl(paths.manifests / "generation_manifest.jsonl", [])
            counts = qa_images(root=tmp, asset_id="missing")
            after = existing.read_text(encoding="utf-8")
        self.assertEqual(counts["checked"], 0)
        self.assertIn("keep", after)

    def test_file_qa_asset_id_merges_existing_manifest_rows(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.qa import qa_images
        with tempfile.TemporaryDirectory() as tmp:
            paths = pipeline_paths(tmp)
            paths.manifests.mkdir(parents=True, exist_ok=True)
            paths.reports.mkdir(parents=True, exist_ok=True)
            existing = paths.manifests / "file_qa_manifest.jsonl"
            existing.write_text('{"assetId":"keep"}\n', encoding="utf-8")
            img = Path(tmp) / "ai_image" / "female" / "001" / "face_card.png"
            self._make_png(img)
            rows = [{"assetId": "a1", "profileId": "female_001", "gender": "female", "numericId": "001", "shotType": "face_card", "status": "recovered_pending_qa", "localPath": str(img), "finalPath": str(img)}]
            write_jsonl(paths.manifests / "generation_manifest.jsonl", rows)
            counts = qa_images(root=tmp, asset_id="a1")
            after = existing.read_text(encoding="utf-8")
        self.assertEqual(counts["checked"], 1)
        self.assertIn("keep", after)
        self.assertIn("a1", after)

    def test_file_qa_no_rows_does_not_clobber_existing_manifest(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.qa import qa_images
        with tempfile.TemporaryDirectory() as tmp:
            paths = pipeline_paths(tmp)
            paths.manifests.mkdir(parents=True, exist_ok=True)
            paths.reports.mkdir(parents=True, exist_ok=True)
            existing = paths.manifests / "file_qa_manifest.jsonl"
            existing.write_text('{"assetId":"keep"}\n', encoding="utf-8")
            write_jsonl(paths.manifests / "generation_manifest.jsonl", [])
            counts = qa_images(root=tmp)
            after = existing.read_text(encoding="utf-8")
        self.assertEqual(counts["skipped_empty_scope"], 1)
        self.assertIn("keep", after)

    def test_file_qa_manifest_remains_valid_jsonl(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl, read_jsonl
        from scripts.ai_image_pipeline_v3.qa import qa_images
        with tempfile.TemporaryDirectory() as tmp:
            paths = pipeline_paths(tmp)
            paths.manifests.mkdir(parents=True, exist_ok=True)
            img = Path(tmp) / "ai_image" / "female" / "001" / "face_card.png"
            self._make_png(img)
            write_jsonl(paths.manifests / "generation_manifest.jsonl", [{"assetId": "a1", "profileId": "female_001", "gender": "female", "numericId": "001", "shotType": "face_card", "status": "recovered_pending_qa", "localPath": str(img), "finalPath": str(img)}])
            qa_images(root=tmp, asset_id="a1")
            rows = read_jsonl(paths.manifests / "file_qa_manifest.jsonl")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["assetId"], "a1")

    def test_approval_evidence_current_state_fallback_still_available(self):
        from scripts.ai_image_pipeline_v3.approval_evidence import resolve_file_qa_evidence
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        with tempfile.TemporaryDirectory() as tmp:
            paths = pipeline_paths(tmp)
            paths.manifests.mkdir(parents=True, exist_ok=True)
            img = Path(tmp) / "ai_image" / "female" / "001" / "face_card.png"
            self._make_png(img)
            active = {"assetId": "a1", "profileId": "female_001", "gender": "female", "numericId": "001", "shotType": "face_card", "promptHash": "h", "promptTargetingVersion": "face_type_looks_level_targeting_v2", "finalPath": str(img)}
            gen = dict(active)
            (paths.manifests / "current_chunk_state.json").write_text(json.dumps({"assetStates": {"a1": "file_qa_passed"}}), encoding="utf-8")
            evidence = resolve_file_qa_evidence(root=tmp, asset_id="a1", active_asset=active, generation_row=gen)
        self.assertTrue(evidence.get("ok"))


if __name__ == "__main__":
    unittest.main()
