import tempfile
import unittest
from pathlib import Path
from unittest import mock


class HermesPendingRetryPolicyV3Tests(unittest.TestCase):
    def _tmp(self):
        return tempfile.TemporaryDirectory()

    def _config(self, root, **kwargs):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import LoopConfig
        data = dict(root=Path(root), mode="chunk", max_cycles=3, max_pending_attempts=3, retry_delay_seconds=0, write_report=False)
        data.update(kwargs)
        return LoopConfig(**data)

    def _completion(self):
        return {"passed": False, "approvedCompleteIdentities": 0, "approvedImages": 0, "failureReasons": []}

    def test_imagegen_failure_retries_same_pending_without_advancing_controller(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "pending_imagegen", "assetId": "a1", "chunkId": "c1", "attempt": 1}
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": True, "chunkId": "c1", "currentAssetId": "a1", "assetStates": {"a1": "pending_imagegen", "a2": "planned"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.process_pending_imagegen_once", return_value={"status": "failed", "assetId": "a1", "reasonCode": "PENDING_IMAGEGEN_FAILED"}) as worker, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.run_bounded_chunk") as bounded, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.finalize_pending_failed", return_value={"action": "finalize_failed"}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                run_loop(self._config(tmp, max_cycles=2, max_pending_attempts=3))
        self.assertEqual(worker.call_count, 2)
        self.assertFalse(bounded.called)

    def test_max_attempts_exhausted_finalizes_pending(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "pending_imagegen", "assetId": "a1", "chunkId": "c1", "attempt": 1}
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": False, "chunkId": "c1", "currentAssetId": "a1", "assetStates": {"a1": "pending_imagegen"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.process_pending_imagegen_once", return_value={"status": "failed", "assetId": "a1", "reasonCode": "PENDING_IMAGEGEN_FAILED"}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.finalize_pending_failed", return_value={"action": "finalize_failed"}) as finalize, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                run_loop(self._config(tmp, max_cycles=2, max_pending_attempts=2))
        self.assertTrue(finalize.called)
        self.assertEqual(finalize.call_args.kwargs["asset_id"], "a1")

    def test_max_attempts_exhausted_blocks_if_finalization_fails(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "pending_imagegen", "assetId": "face1", "chunkId": "c1", "attempt": 1, "shotType": "face_card"}
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": False, "chunkId": "c1", "currentAssetId": "face1", "assetStates": {"face1": "pending_imagegen", "sil1": "planned", "vibe1": "planned"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.process_pending_imagegen_once", return_value={"status": "failed", "assetId": "face1", "reasonCode": "PENDING_IMAGEGEN_FAILED"}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.finalize_pending_failed", side_effect=RuntimeError("dependency policy requires full identity retry")), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                result = run_loop(self._config(tmp, max_cycles=1, max_pending_attempts=1))
        self.assertEqual(result["result"], "LOOP_STOPPED_HARD_BLOCKER")
        self.assertTrue(any("max_attempts_finalization_failed" in item for item in result["hardBlockers"]))

    def test_vibe_failure_never_approves(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "pending_imagegen", "assetId": "vibe1", "chunkId": "c1", "attempt": 1, "shotType": "vibe_card"}
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": False, "chunkId": "c1", "currentAssetId": "vibe1", "assetStates": {"vibe1": "pending_imagegen"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.process_pending_imagegen_once", return_value={"status": "failed", "assetId": "vibe1", "reasonCode": "PENDING_IMAGEGEN_FAILED"}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.finalize_pending_failed", return_value={"action": "finalize_failed"}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                result = run_loop(self._config(tmp, max_cycles=1, max_pending_attempts=1))
        self.assertEqual(result["identitiesApproved"], 0)
        self.assertEqual(result["imagesApproved"], 0)


if __name__ == "__main__":
    unittest.main()
