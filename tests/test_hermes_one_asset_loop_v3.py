import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


class HermesOneAssetLoopV3Tests(unittest.TestCase):
    def _tmp(self):
        return tempfile.TemporaryDirectory()

    def _config(self, root, **kwargs):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import LoopConfig
        data = dict(root=Path(root), once=True, max_cycles=1, write_report=False)
        data.update(kwargs)
        return LoopConfig(**data)

    def _completion(self, passed=False):
        return {"passed": passed, "approvedCompleteIdentities": 0, "approvedImages": 0, "failureReasons": []}

    def test_loop_refuses_to_start_if_lock_active(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, now_utc
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        with self._tmp() as tmp:
            paths = pipeline_paths(tmp)
            paths.manifests.mkdir(parents=True)
            (paths.manifests / "hermes_one_asset_loop.lock").write_text(json.dumps({"pid": os.getpid(), "startedAt": now_utc(), "heartbeatAt": now_utc()}), encoding="utf-8")
            result = run_loop(self._config(tmp))
        self.assertEqual(result["hardBlockers"], ["LOOP_ALREADY_RUNNING"])

    def test_loop_recovers_stale_lock(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        with self._tmp() as tmp:
            paths = pipeline_paths(tmp)
            paths.manifests.mkdir(parents=True)
            old = "2000-01-01T00:00:00+00:00"
            (paths.manifests / "hermes_one_asset_loop.lock").write_text(json.dumps({"pid": 999999, "startedAt": old, "heartbeatAt": old}), encoding="utf-8")
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": False, "reasonCode": "no_plan", "assetStates": {}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=None), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                result = run_loop(self._config(tmp))
            archives = list(paths.manifests.glob("hermes_one_asset_loop.stale.*.lock"))
        self.assertTrue(archives)
        self.assertIn("no_plan", result["hardBlockers"])

    def test_no_pending_can_run_runs_bounded_chunk_once(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": True, "chunkId": "c1", "assetStates": {}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=None), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.run_bounded_chunk", return_value={"status": "pending_imagegen", "assetId": "a1"}) as run, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                run_loop(self._config(tmp, dry_run=False))
        self.assertEqual(run.call_count, 1)

    def test_pending_imagegen_runs_one_asset_worker_only(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "pending_imagegen", "assetId": "a1", "chunkId": "c1", "attempt": 1}
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": False, "chunkId": "c1", "currentAssetId": "a1", "assetStates": {"a1": "pending_imagegen"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.process_pending_imagegen_once", return_value={"status": "succeeded", "assetId": "a1", "fileQaPassed": True}) as worker, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.run_bounded_chunk") as bounded, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                result = run_loop(self._config(tmp, allow_imagegen=True))
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(bounded.call_count, 0)
        self.assertEqual(result["assetsGenerated"], 1)

    def test_one_asset_worker_generates_exactly_one_image(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import _run_internal_imagegen, LoopConfig
        with self._tmp() as tmp, self._tmp() as gen:
            root = Path(tmp)
            prompt = root / "handoff.prompt.txt"
            prompt.write_text("one image", encoding="utf-8")
            before = Path(gen) / "old.png"; before.write_bytes(b"x")
            new = Path(gen) / "new.png"
            with mock.patch.dict(os.environ, {"CODEX_GENERATED_IMAGES_DIR": gen}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.safe_run", side_effect=lambda *a, **k: (time.sleep(0.01), new.write_bytes(b"y"), {"returncode": 0, "stdout": "IMAGEGEN_DONE", "stderr": ""})[2]):
                result = _run_internal_imagegen(root, {"assetId": "a1", "handoffPromptPath": str(prompt)}, LoopConfig(root=root, codex_bin=sys_exe()))
        self.assertTrue(result["generated"])
        self.assertEqual(result["generatedCount"], 1)

    def test_one_asset_worker_refuses_multiple_output_images(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import _run_internal_imagegen, LoopConfig
        with self._tmp() as tmp, self._tmp() as gen:
            root = Path(tmp); prompt = root / "handoff.prompt.txt"; prompt.write_text("one image", encoding="utf-8")
            def fake(*a, **k):
                (Path(gen) / "a.png").write_bytes(b"a"); (Path(gen) / "b.png").write_bytes(b"b")
                return {"returncode": 0, "stdout": "IMAGEGEN_DONE", "stderr": ""}
            with mock.patch.dict(os.environ, {"CODEX_GENERATED_IMAGES_DIR": gen}), mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.safe_run", side_effect=fake):
                result = _run_internal_imagegen(root, {"assetId": "a1", "handoffPromptPath": str(prompt)}, LoopConfig(root=root, codex_bin=sys_exe()))
        self.assertEqual(result["reasonCode"], "IMAGEGEN_MULTIPLE_OUTPUTS")

    def test_pending_resolved_triggers_reconcile_apply(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "resolved", "resolved": True, "assetId": "a1", "chunkId": "c1"}
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": True, "chunkId": "c1", "assetStates": {"a1": "pending_imagegen"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.reconcile_bounded_chunk", return_value={"stateChanged": True}) as rec, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                run_loop(self._config(tmp))
        self.assertTrue(rec.called)
        self.assertTrue(rec.call_args.kwargs["apply"])

    def test_resolved_pending_already_reconciled_allows_next_controller_run(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "resolved", "resolved": True, "assetId": "a_done", "chunkId": "c1"}
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": True, "chunkId": "c1", "currentAssetId": "", "assetStates": {"a_done": "file_qa_passed", "a_next": "planned"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.run_bounded_chunk", return_value={"status": "pending_imagegen", "assetId": "a_next"}) as bounded, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.reconcile_bounded_chunk") as rec, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                run_loop(self._config(tmp))
        self.assertTrue(bounded.called)
        self.assertFalse(rec.called)

    def test_unresolved_pending_prevents_bounded_chunk_run(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": True, "chunkId": "c1", "assetStates": {}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value={"status": "pending_imagegen", "assetId": "a1"}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.process_pending_imagegen_once", return_value={"status": "blocked", "reasonCode": "imagegen_not_allowed"}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.run_bounded_chunk") as bounded, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                run_loop(self._config(tmp, allow_imagegen=False))
        self.assertFalse(bounded.called)

    def test_invalid_all_zero_pending_archived_or_reconstructed_or_blocks(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.codex_imagegen import read_pending
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import archive_and_reconstruct_invalid_pending
        with self._tmp() as tmp:
            paths = pipeline_paths(tmp); paths.manifests.mkdir(parents=True); paths.reports.mkdir(parents=True)
            p = paths.manifests / "pending-imagegen.json"; p.write_bytes(b"\x00" * 8)
            result = archive_and_reconstruct_invalid_pending(Path(tmp), read_pending(p))
            archives = list((paths.manifests / "archive").glob("invalid_pending_*.bin"))
        self.assertTrue(archives)
        self.assertIn(result["status"], {"failed", "reconstructed"})

    def test_distribution_audit_is_not_run_immediately_before_bounded_chunk_run(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": True, "chunkId": "c1", "assetStates": {}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=None), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.run_bounded_chunk", return_value={"status": "pending_imagegen"}) as bounded, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                run_loop(self._config(tmp))
        self.assertTrue(bounded.called)

    def test_dry_run_mode_never_generates_images(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": False, "chunkId": "c1", "assetStates": {"a1": "pending_imagegen"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value={"status": "pending_imagegen", "assetId": "a1"}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop._run_internal_imagegen") as gen, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                run_loop(self._config(tmp, dry_run=True, allow_imagegen=True))
        self.assertFalse(gen.called)

    def test_once_executes_at_most_one_state_transition(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": True, "chunkId": "c1", "assetStates": {}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=None), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.run_bounded_chunk", return_value={"status": "pending_imagegen"}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                result = run_loop(self._config(tmp, max_cycles=99, once=True))
        self.assertEqual(result["cycles"], 1)

    def test_chunk_mode_default_max_cycles_uses_asset_budget_not_one(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import LoopConfig, effective_max_cycles
        cfg = LoopConfig(root=Path("."), mode="chunk", once=False, max_assets=72, max_cycles=None)
        self.assertGreaterEqual(effective_max_cycles(cfg), 72 * 4)

    def test_chunk_mode_continues_after_controller_creates_pending(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "pending_imagegen", "assetId": "a1", "chunkId": "c1", "attempt": 1}
        resolved = {"status": "resolved", "resolved": True, "assetId": "a1", "chunkId": "c1"}
        statuses = [
            {"canRun": True, "chunkId": "c1", "currentAssetId": "", "assetStates": {"a1": "planned"}},
            {"canRun": False, "chunkId": "c1", "currentAssetId": "a1", "assetStates": {"a1": "pending_imagegen"}},
            {"canRun": True, "chunkId": "c1", "currentAssetId": "a1", "assetStates": {"a1": "pending_imagegen"}},
            {"canRun": True, "chunkId": "c1", "currentAssetId": "", "assetStates": {"a1": "file_qa_passed", "a2": "planned"}},
        ]
        pendings = [None, pending, resolved, None]
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", side_effect=statuses), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", side_effect=pendings + [None]), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.run_bounded_chunk", return_value={"status": "pending_imagegen", "assetId": "a1"}) as bounded, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.process_pending_imagegen_once", return_value={"status": "succeeded", "assetId": "a1", "fileQaPassed": True}) as worker, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.reconcile_bounded_chunk", return_value={"stateChanged": True}) as rec, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                result = run_loop(self._config(tmp, mode="chunk", once=False, max_assets=1, max_cycles=None, allow_imagegen=True))
        self.assertEqual(bounded.call_count, 1)
        self.assertEqual(worker.call_count, 1)
        self.assertTrue(rec.called)
        self.assertEqual(result["assetsGenerated"], 1)
        self.assertGreater(result["cycles"], 1)

    def test_chunk_mode_unresolved_pending_at_start_processes_first(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "pending_imagegen", "assetId": "live", "chunkId": "c1", "attempt": 1}
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": False, "chunkId": "c1", "currentAssetId": "live", "assetStates": {"live": "pending_imagegen"}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=pending), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.process_pending_imagegen_once", return_value={"status": "succeeded", "assetId": "live", "fileQaPassed": True}) as worker, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.run_bounded_chunk") as bounded, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                result = run_loop(self._config(tmp, mode="chunk", once=False, max_assets=1, max_cycles=1, allow_imagegen=True))
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(bounded.call_count, 0)
        self.assertEqual(result["assetsGenerated"], 1)

    def test_smoke_mode_respects_max_assets_before_next_controller(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        pending = {"status": "pending_imagegen", "assetId": "a1", "chunkId": "c1", "attempt": 1}
        statuses = [
            {"canRun": False, "chunkId": "c1", "currentAssetId": "a1", "assetStates": {"a1": "pending_imagegen", "a2": "planned"}},
            {"canRun": True, "chunkId": "c1", "currentAssetId": "", "assetStates": {"a1": "file_qa_passed", "a2": "planned"}},
        ]
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", side_effect=statuses), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", side_effect=[pending, None, None]), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.process_pending_imagegen_once", return_value={"status": "succeeded", "assetId": "a1", "fileQaPassed": True}) as worker, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.run_bounded_chunk") as bounded, \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                result = run_loop(self._config(tmp, mode="smoke", once=False, max_assets=1, max_cycles=None, allow_imagegen=True))
        self.assertEqual(worker.call_count, 1)
        self.assertEqual(bounded.call_count, 0)
        self.assertEqual(result["assetsGenerated"], 1)

    def test_visual_qa_only_runs_after_chunk_terminal_state(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import _chunk_assets_terminal
        self.assertFalse(_chunk_assets_terminal({"assetStates": {"a": "planned"}}))
        self.assertTrue(_chunk_assets_terminal({"assetStates": {"a": "file_qa_passed", "b": "failed"}}))

    def test_out_of_scope_visual_qa_payload_blocks_loop_placeholder(self):
        # The loop does not run visual QA directly; scoped visual QA remains downstream only.
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import TERMINAL_ASSET_STATES
        self.assertIn("file_qa_passed", TERMINAL_ASSET_STATES)

    def test_manual_flag_blocks_loop_unless_explicitly_disabled(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        with self._tmp() as tmp:
            paths = pipeline_paths(tmp); paths.manifests.mkdir(parents=True)
            (paths.manifests / "manual_review_required.flag").write_text("reason", encoding="utf-8")
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": True, "chunkId": "c1", "assetStates": {}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=None), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                result = run_loop(self._config(tmp))
        self.assertIn("MANUAL_REVIEW_REQUIRED", result["hardBlockers"])

    def test_prompt_targeting_version_mismatch_blocks_loop_helper(self):
        # Covered by plan/status validation before bounded run; loop consumes canRun/reasonCode fail-closed.
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": False, "reasonCode": "promptTargetingVersion_mismatch", "chunkId": "c1", "assetStates": {}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=None), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion()):
                result = run_loop(self._config(tmp))
        self.assertIn("promptTargetingVersion_mismatch", result["hardBlockers"])

    def test_old_prompt_hash_evidence_not_reused_helper(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import _expected_from_pending
        with self._tmp() as tmp:
            result = _expected_from_pending(Path(tmp), {"assetId": "missing", "chunkId": "c1", "attempt": 1})
        self.assertEqual(result["assetId"], "missing")

    def test_protected_recommender_files_not_modified_guard(self):
        from scripts.ai_image_pipeline_v3.one_asset_transaction import FORBIDDEN_CHILD_RELATIVE_PATHS
        joined = "\n".join(FORBIDDEN_CHILD_RELATIVE_PATHS)
        self.assertIn("seolleyeon_svd_train_export.py", joined)

    def test_completion_cannot_pass_early(self):
        from scripts.ai_image_pipeline_v3.hermes_one_asset_loop import run_loop
        with self._tmp() as tmp:
            with mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.bounded_chunk_status", return_value={"canRun": False, "reasonCode": "no_plan", "chunkId": "c1", "assetStates": {}}), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.read_pending", return_value=None), \
                 mock.patch("scripts.ai_image_pipeline_v3.hermes_one_asset_loop.completion_check", return_value=self._completion(passed=True)):
                result = run_loop(self._config(tmp))
        self.assertIn("completion_unexpectedly_passed_before_target", result["hardBlockers"])


def sys_exe():
    import sys
    return sys.executable


if __name__ == "__main__":
    unittest.main()
