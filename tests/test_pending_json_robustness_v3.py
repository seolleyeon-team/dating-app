import json
import tempfile
import unittest
from pathlib import Path


class PendingJsonRobustnessV3Tests(unittest.TestCase):
    def test_read_pending_all_zero_returns_invalid_payload(self):
        from scripts.ai_image_pipeline_v3.codex_imagegen import read_pending
        from scripts.ai_image_pipeline_v3.pending_state import pending_is_unresolved, pending_unresolved_reason

        with tempfile.TemporaryDirectory() as tmp:
            pending = Path(tmp) / "pending-imagegen.json"
            pending.write_bytes(b"\x00" * 16)

            payload = read_pending(pending)

        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["status"], "invalid")
        self.assertEqual(payload["pendingInvalidReason"], "pending_json_all_zero")
        self.assertTrue(payload["allZero"])
        self.assertTrue(pending_is_unresolved(payload))
        self.assertEqual(pending_unresolved_reason(payload), "pending_json_all_zero")

    def test_pending_status_report_all_zero_does_not_crash(self):
        from scripts.ai_image_pipeline_v3.pending_admin import pending_status_report

        with tempfile.TemporaryDirectory() as tmp:
            pending = Path(tmp) / "pending-imagegen.json"
            pending.write_bytes(b"\x00" * 16)

            report = pending_status_report(root=tmp, pending=pending)

        self.assertEqual(report["status"], "invalid")
        self.assertTrue(report["unresolved"])
        self.assertEqual(report["reason"], "pending_json_all_zero")

    def test_bounded_chunk_status_all_zero_pending_does_not_crash(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import bounded_chunk_status
        from scripts.ai_image_pipeline_v3.config import pipeline_paths

        with tempfile.TemporaryDirectory() as tmp:
            paths = pipeline_paths(tmp)
            paths.manifests.mkdir(parents=True, exist_ok=True)
            (paths.manifests / "pending-imagegen.json").write_bytes(b"\x00" * 16)

            report = bounded_chunk_status(root=tmp)

        self.assertIsInstance(report, dict)
        self.assertIn("canRun", report)

    def test_completion_check_all_zero_pending_reports_reason(self):
        from scripts.ai_image_pipeline_v3.completion import completion_check
        from scripts.ai_image_pipeline_v3.config import pipeline_paths

        with tempfile.TemporaryDirectory() as tmp:
            paths = pipeline_paths(tmp)
            paths.manifests.mkdir(parents=True, exist_ok=True)
            paths.reports.mkdir(parents=True, exist_ok=True)
            (paths.manifests / "pending-imagegen.json").write_bytes(b"\x00" * 16)
            (paths.reports / "latest_distribution_audit.json").write_text(json.dumps({
                "passed": False,
                "approvedCompleteIdentities": 0,
                "approvedImages": 0,
                "femaleApprovedCompleteIdentities": 0,
                "maleApprovedCompleteIdentities": 0,
                "countChecks": {},
                "bucketChecks": [],
                "exactFinalCountMatch": False,
                "exactDistributionMatch": False,
                "overLevelApprovedIdentities": [],
            }), encoding="utf-8")

            report = completion_check(root=tmp)

        self.assertFalse(report["passed"])
        self.assertTrue(report["unresolvedPendingImagegen"])
        self.assertEqual(report["pendingReason"], "pending_json_all_zero")


if __name__ == "__main__":
    unittest.main()
