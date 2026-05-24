import json
import tempfile
import unittest
from pathlib import Path


class IdentityApplyFileQaReasonMappingTests(unittest.TestCase):
    def test_current_chunk_state_overrides_stale_chunk_file_qa_for_visual_metadata(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import _file_qa_by_asset, _file_qa_status_for

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = root / "ai_image" / "manifests"
            manifests.mkdir(parents=True)
            chunk_dir = root / "ai_image" / "reports" / "chunks" / "chunk_test"
            chunk_dir.mkdir(parents=True)
            asset_id = "male_048__vibe_card__v001"
            (chunk_dir / "file_qa.jsonl").write_text(
                json.dumps({"assetId": asset_id, "qaStatus": "file_needs_review", "reasonCodes": []}) + "\n",
                encoding="utf-8",
            )
            (manifests / "current_chunk_state.json").write_text(
                json.dumps({"chunkId": "chunk_test", "assetStates": {asset_id: "file_qa_passed"}}),
                encoding="utf-8",
            )

            rows = _file_qa_by_asset(root)
            self.assertEqual(rows[asset_id]["fileQaStatus"], "file_qa_passed")
            self.assertEqual(rows[asset_id]["status"], "file_qa_passed")
            self.assertEqual(_file_qa_status_for(asset_id, rows), "file_qa_passed")

    def test_invalid_file_qa_evidence_still_surfaces_when_state_does_not_override(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import _file_qa_by_asset, _file_qa_status_for

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chunk_dir = root / "ai_image" / "reports" / "chunks" / "chunk_test"
            chunk_dir.mkdir(parents=True)
            asset_id = "male_048__vibe_card__v001"
            (chunk_dir / "file_qa.jsonl").write_text(
                json.dumps({"assetId": asset_id, "qaStatus": "file_needs_review", "reasonCodes": ["manual_review"]}) + "\n",
                encoding="utf-8",
            )

            rows = _file_qa_by_asset(root)
            self.assertEqual(_file_qa_status_for(asset_id, rows), "file_needs_review")

    def test_all_file_qa_passed_assets_do_not_expose_stale_file_reason_to_identity_prompt(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import _file_qa_by_asset, _file_qa_status_for

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests = root / "ai_image" / "manifests"
            manifests.mkdir(parents=True)
            chunk_dir = root / "ai_image" / "reports" / "chunks" / "chunk_test"
            chunk_dir.mkdir(parents=True)
            asset_ids = [f"male_048__{shot}__v001" for shot in ("face_card", "silhouette_card", "vibe_card")]
            (chunk_dir / "file_qa.jsonl").write_text(
                "".join(json.dumps({"assetId": aid, "qaStatus": "file_needs_review"}) + "\n" for aid in asset_ids),
                encoding="utf-8",
            )
            (manifests / "current_chunk_state.json").write_text(
                json.dumps({"chunkId": "chunk_test", "assetStates": {aid: "file_qa_passed" for aid in asset_ids}}),
                encoding="utf-8",
            )
            rows = _file_qa_by_asset(root)
            self.assertEqual({_file_qa_status_for(aid, rows) for aid in asset_ids}, {"file_qa_passed"})


if __name__ == "__main__":
    unittest.main()
