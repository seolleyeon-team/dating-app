import tempfile
import unittest
from pathlib import Path
from unittest import mock


class HermesAutoPendingReconcileV3Tests(unittest.TestCase):
    def _tmp(self):
        return tempfile.TemporaryDirectory()

    def _config(self, root, **kwargs):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import LoopConfig
        data = dict(root=Path(root), mode="chunk", max_cycles=3, write_report=False, retry_delay_seconds=0)
        data.update(kwargs)
        return LoopConfig(**data)

    def _completion(self):
        return {"passed": False, "approvedCompleteIdentities": 0, "approvedImages": 0, "failureReasons": []}

    def test_resolved_pending_not_reconciled_auto_applies_safe_reconcile(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "resolved", "resolved": True, "assetId": "a1", "chunkId": "c1"}
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": False, "chunkId": "c1", "currentAssetId": "a1", "assetStates": {"a1": "pending_imagegen"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.reconcile_bounded_chunk", side_effect=[{"stateChanged": True, "extraGenerationAssetCount": 0, "unknownFiles": [], "reasonsIfCannotClear": []}, {"stateChanged": True}]) as rec, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                run_loop(self._config(tmp, once=True))
        self.assertEqual(rec.call_count, 2)
        self.assertFalse(rec.call_args_list[0].kwargs["apply"])
        self.assertTrue(rec.call_args_list[1].kwargs["apply"])

    def test_resolved_pending_already_reconciled_does_not_block_controller(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "resolved", "resolved": True, "assetId": "a_done", "chunkId": "c1"}
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": True, "chunkId": "c1", "currentAssetId": "", "assetStates": {"a_done": "file_qa_passed", "a_next": "planned"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.run_bounded_chunk", return_value={"status": "pending_imagegen", "assetId": "a_next"}) as bounded, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.reconcile_bounded_chunk") as rec, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                run_loop(self._config(tmp, once=True))
        self.assertTrue(bounded.called)
        self.assertFalse(rec.called)

    def test_reconcile_unsafe_blocks_without_apply(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "resolved", "resolved": True, "assetId": "a1", "chunkId": "c1"}
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": False, "chunkId": "c1", "currentAssetId": "a1", "assetStates": {"a1": "pending_imagegen"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.reconcile_bounded_chunk", return_value={"stateChanged": False, "unknownFiles": ["x.png"]}) as rec, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                result = run_loop(self._config(tmp, once=True))
        self.assertIn("RECONCILE_UNSAFE", result["hardBlockers"])
        self.assertEqual(rec.call_count, 1)

    def test_unresolved_pending_existing_valid_file_resolves_without_imagegen(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import process_pending_imagegen_once
        pending = {"status": "pending_imagegen", "assetId": "a1", "chunkId": "c1", "attempt": 1, "expectedFinalPath": "final.png", "expectedRawPath": "final.png"}
        with self._tmp() as tmp:
            root = Path(tmp)
            (root / "final.png").write_bytes(b"not-an-image-but-inspector-is-mocked")
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.inspect_image_detail", return_value={"ok": True, "width": 1024, "height": 1536, "fileBytes": 1234, "format": "PNG", "reasons": []}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.load_generation_manifest", return_value=[]), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.write_pending") as write_pending, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.write_receipt"):
                result = process_pending_imagegen_once(root, allow_imagegen=False)
        self.assertEqual(result["status"], "succeeded")
        self.assertTrue(result["recoveredExistingFile"])
        self.assertTrue(write_pending.called)


if __name__ == "__main__":
    unittest.main()
