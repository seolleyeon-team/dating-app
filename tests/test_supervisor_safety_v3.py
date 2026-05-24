import tempfile
import unittest
from pathlib import Path


class SupervisorSafetyV3Tests(unittest.TestCase):
    def test_status_supervisor_is_explicitly_status_only_and_uses_bounded_executor(self):
        from scripts.ai_image_pipeline_v3.supervisor import supervisor_status

        with tempfile.TemporaryDirectory() as tmp:
            status = supervisor_status(root=Path(tmp), mode="chunk")

        self.assertTrue(status["dryRunStatusOnly"])
        self.assertEqual(status["chunkExecutor"], "bounded_batch_executor")
        self.assertIn("bounded-chunk-run", status["chunkCommand"])

    def test_shell_supervisor_stops_for_manual_review_and_does_not_auto_clear(self):
        shell = Path("scripts/codex_imagegen_supervisor_v3.sh").read_text(encoding="utf-8")

        self.assertIn("manual_review_required.flag", shell)
        self.assertIn("bounded-chunk-status --root .", shell)
        self.assertIn("recommended next step: bounded-chunk-reconcile --root . --dry-run", shell)
        self.assertNotIn("bounded-chunk-reconcile --root . --apply --clear-manual-flag-if-safe", shell)

    def test_shell_supervisor_disables_legacy_identity_asset_fallback_by_default(self):
        shell = Path("scripts/codex_imagegen_supervisor_v3.sh").read_text(encoding="utf-8")

        self.assertIn('ALLOW_LEGACY_SUPERVISOR_RALPH_FALLBACK="${ALLOW_LEGACY_SUPERVISOR_RALPH_FALLBACK:-0}"', shell)
        self.assertIn("MODE=identity is disabled by default", shell)
        self.assertIn("MODE=asset is disabled by default", shell)
        self.assertIn("stopping before legacy fallback", shell)

    def test_no_progress_uses_qa_recovery_and_rejection_progress_not_raw_file_count(self):
        from scripts.ai_image_pipeline_v3.supervisor import no_progress

        before = {
            "approvedIdentityCount": 0,
            "approvedAssetCount": 0,
            "assetQaCount": 1,
            "identityQaCount": 1,
            "resolvedPendingCount": 1,
            "rejectedIdentityCount": 1,
        }
        self.assertTrue(no_progress(before, dict(before)))
        after = dict(before)
        after["assetQaCount"] = 2
        self.assertFalse(no_progress(before, after))

    def test_mode_transition_log_can_be_created(self):
        from scripts.ai_image_pipeline_v3.supervisor import log_mode_transition

        with tempfile.TemporaryDirectory() as tmp:
            path = log_mode_transition(root=Path(tmp), from_mode="chunk", to_mode="identity", reason="unit")

            self.assertTrue(path.exists())
            self.assertIn("unit", path.read_text(encoding="utf-8"))

    def test_makefile_supervisor_run_targets_are_not_ambiguous_production_routes(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")
        run_section = makefile.split("ai-image-supervisor-720:", 1)[1].split("\n\n", 1)[0]
        status_section = makefile.split("ai-image-supervisor-status-720:", 1)[1].split("\n\n", 1)[0]

        self.assertIn("Deprecated ambiguous target", run_section)
        self.assertIn("@exit 2", run_section)
        self.assertIn("supervisor-720 --root .", status_section)


if __name__ == "__main__":
    unittest.main()
