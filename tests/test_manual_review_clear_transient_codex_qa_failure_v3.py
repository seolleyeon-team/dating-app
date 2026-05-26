from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.ai_image_pipeline_v3.manual_review import (
    TRANSIENT_CODEX_QA_CLEAR_REASON,
    TRANSIENT_CODEX_QA_FAILURE_REASON,
    _active_pipeline_processes,
    clear_manual_review,
)


PRE_TRANSIENT = {
    "passed": False,
    "failureReasons": [
        "manual_review_required",
        "active_visual_qa_incomplete",
        "distribution_audit_incomplete",
        "distribution_mismatch",
    ],
    "approvedCompleteIdentities": 74,
    "approvedImages": 222,
}
POST_TRANSIENT = {
    "passed": False,
    "failureReasons": ["active_visual_qa_incomplete", "distribution_audit_incomplete", "distribution_mismatch"],
    "approvedCompleteIdentities": 74,
    "approvedImages": 222,
}
AUDIT = {
    "passed": False,
    "finalDecision": "needs_more_generation",
    "approvedCompleteIdentityCount": 74,
    "approvedImageCount": 222,
}


class ManualReviewTransientCodexQaClearTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.chunk_id = "chunk_test"
        self.asset_ids = [f"male_001__{shot}__v001" for shot in ("face_card", "silhouette_card", "vibe_card")]
        self._write_fixture()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_json(self, rel: str, payload: dict) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def _write_fixture(self) -> None:
        manifests = self.root / "ai_image" / "manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        self._write_json(
            "ai_image/manifests/manual_review_required.flag",
            {"schemaVersion": "seolleyeon_active_visual_manual_review_v3", "reason": TRANSIENT_CODEX_QA_FAILURE_REASON},
        )
        assets = []
        states = {}
        for asset_id in self.asset_ids:
            shot = asset_id.split("__")[1]
            final = self.root / "ai_image" / "male" / "001" / f"{shot}.png"
            final.parent.mkdir(parents=True, exist_ok=True)
            final.write_bytes(b"png")
            assets.append({"assetId": asset_id, "shotType": shot, "finalPath": str(final)})
            states[asset_id] = "file_qa_passed"
        self._write_json(
            "ai_image/manifests/current_chunk_plan.json",
            {
                "chunkId": self.chunk_id,
                "status": "generation_paused",
                "selectedAssetCount": len(self.asset_ids),
                "identities": [{"profileId": "male_001", "assets": assets}],
            },
        )
        self._write_json(
            "ai_image/manifests/current_chunk_state.json",
            {
                "chunkId": self.chunk_id,
                "status": "generation_paused",
                "assetStates": states,
                "activeVisualQaComplete": False,
                "distributionAuditComplete": False,
            },
        )
        self._write_json(
            f"ai_image/reports/chunks/{self.chunk_id}/file_complete_identity_whitelist.json",
            {
                "schemaVersion": "seolleyeon_file_complete_identity_whitelist_v3",
                "chunkId": self.chunk_id,
                "profileCount": 1,
                "assetCount": len(self.asset_ids),
                "assetIds": self.asset_ids,
                "profiles": [{"profileId": "male_001", "assets": {a["shotType"]: a for a in assets}}],
            },
        )
        self._write_json(
            f"ai_image/reports/chunks/{self.chunk_id}/contact_sheets/file_complete_contact_sheet_index.json",
            {
                "schemaVersion": "seolleyeon_contact_sheet_index_v3",
                "chunkId": self.chunk_id,
                "sheetScope": "file_complete_identities_only",
                "assetCount": len(self.asset_ids),
                "sheets": [{"sheetId": "asset_sheet_001", "assetIds": self.asset_ids, "profileIds": ["male_001"], "outOfScopeAssetIds": []}],
            },
        )

    def _clear(self, *, pre=PRE_TRANSIENT, post=POST_TRANSIENT, audit=AUDIT, active_processes=None):
        with mock.patch("scripts.ai_image_pipeline_v3.manual_review.audit_distribution", return_value=audit), \
            mock.patch("scripts.ai_image_pipeline_v3.manual_review.completion_check", side_effect=[pre, post]), \
            mock.patch("scripts.ai_image_pipeline_v3.manual_review._active_pipeline_processes", return_value=active_processes or []):
            return clear_manual_review(root=self.root, reason=TRANSIENT_CODEX_QA_FAILURE_REASON)

    def test_exact_reason_can_clear_when_all_readiness_gates_pass(self):
        report = self._clear()
        self.assertTrue(report["cleared"])
        self.assertEqual(report["clearReason"], TRANSIENT_CODEX_QA_CLEAR_REASON)
        self.assertFalse((self.root / "ai_image/manifests/manual_review_required.flag").exists())

    def test_clear_archives_flag_with_sidecar(self):
        report = self._clear()
        archive = Path(report["archivePath"])
        sidecar = Path(report["archiveSidecarPath"])
        self.assertTrue(archive.exists())
        self.assertTrue(sidecar.exists())
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        self.assertEqual(payload["originalReason"], TRANSIENT_CODEX_QA_FAILURE_REASON)
        self.assertEqual(payload["chunkId"], self.chunk_id)

    def test_clear_does_not_set_active_visual_qa_complete(self):
        self._clear()
        state = json.loads((self.root / "ai_image/manifests/current_chunk_state.json").read_text(encoding="utf-8"))
        self.assertFalse(state["activeVisualQaComplete"])

    def test_clear_does_not_set_distribution_audit_complete(self):
        self._clear()
        state = json.loads((self.root / "ai_image/manifests/current_chunk_state.json").read_text(encoding="utf-8"))
        self.assertFalse(state["distributionAuditComplete"])

    def test_clear_does_not_approve_assets_or_identities(self):
        before_state = (self.root / "ai_image/manifests/current_chunk_state.json").read_text(encoding="utf-8")
        report = self._clear()
        after_state = (self.root / "ai_image/manifests/current_chunk_state.json").read_text(encoding="utf-8")
        self.assertEqual(before_state, after_state)
        self.assertEqual(report["postClearCompletion"]["approvedCompleteIdentities"], 74)
        self.assertEqual(report["postClearCompletion"]["approvedImages"], 222)

    def test_clear_fails_if_pending_unresolved(self):
        self._write_json("ai_image/manifests/pending-imagegen.json", {"status": "pending", "assetId": self.asset_ids[0]})
        report = self._clear()
        self.assertFalse(report["cleared"])
        self.assertIn("unresolved_pending_imagegen", report["readiness"]["reasonsIfUnsafe"])

    def test_clear_fails_if_active_process_present(self):
        report = self._clear(active_processes=[{"pid": 123, "commandLine": "active-visual-qa-all"}])
        self.assertFalse(report["cleared"])
        self.assertIn("active_generation_or_visual_qa_process", report["readiness"]["reasonsIfUnsafe"])

    def test_clear_fails_if_file_qa_incomplete(self):
        state_path = self.root / "ai_image/manifests/current_chunk_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["assetStates"][self.asset_ids[0]] = "pending_imagegen"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        report = self._clear()
        self.assertFalse(report["cleared"])
        self.assertIn("transient_codex_qa_file_qa_incomplete", report["readiness"]["reasonsIfUnsafe"])

    def test_clear_fails_if_contact_sheet_index_missing(self):
        (self.root / f"ai_image/reports/chunks/{self.chunk_id}/contact_sheets/file_complete_contact_sheet_index.json").unlink()
        report = self._clear()
        self.assertFalse(report["cleared"])
        self.assertIn("transient_codex_qa_contact_sheet_index_missing", report["readiness"]["reasonsIfUnsafe"])

    def test_clear_fails_if_whitelist_missing(self):
        (self.root / f"ai_image/reports/chunks/{self.chunk_id}/file_complete_identity_whitelist.json").unlink()
        report = self._clear()
        self.assertFalse(report["cleared"])
        self.assertIn("transient_codex_qa_whitelist_missing", report["readiness"]["reasonsIfUnsafe"])

    def test_clear_fails_if_scope_mismatches_chunk(self):
        path = self.root / f"ai_image/reports/chunks/{self.chunk_id}/contact_sheets/file_complete_contact_sheet_index.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["chunkId"] = "other_chunk"
        path.write_text(json.dumps(data), encoding="utf-8")
        report = self._clear()
        self.assertFalse(report["cleared"])
        self.assertIn("transient_codex_qa_contact_sheet_chunk_mismatch", report["readiness"]["reasonsIfUnsafe"])

    def test_clear_fails_for_no_deficit_assets_available(self):
        self._write_json("ai_image/manifests/manual_review_required.flag", {"reason": "no_deficit_assets_available"})
        report = self._clear()
        self.assertFalse(report["cleared"])
        self.assertTrue(any(r.startswith("transient_codex_qa_flag_reason_mismatch") for r in report["readiness"]["reasonsIfUnsafe"]))

    def test_clear_fails_for_unknown_reason(self):
        with mock.patch("scripts.ai_image_pipeline_v3.manual_review.audit_distribution", return_value=AUDIT), \
            mock.patch("scripts.ai_image_pipeline_v3.manual_review.completion_check", return_value=PRE_TRANSIENT):
            report = clear_manual_review(root=self.root, reason="unknown_reason")
        self.assertFalse(report["cleared"])

    def test_clear_fails_if_approved_evidence_count_regresses(self):
        post = dict(POST_TRANSIENT)
        post["approvedCompleteIdentities"] = 73
        report = self._clear(post=post)
        self.assertFalse(report["cleared"])
        self.assertTrue((self.root / "ai_image/manifests/manual_review_required.flag").exists())
        self.assertIn("approved_identity_count_regressed", report["postClearCompletion"]["unexpectedFailures"])

    def test_original_strict_clear_still_allows_finalized_chunk(self):
        state_path = self.root / "ai_image/manifests/current_chunk_state.json"
        plan_path = self.root / "ai_image/manifests/current_chunk_plan.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        state.update({"status": "finalized", "activeVisualQaComplete": True, "distributionAuditComplete": True})
        plan["status"] = "finalized"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        pre = {"passed": False, "failureReasons": ["manual_review_required", "distribution_mismatch"], "approvedCompleteIdentities": 74, "approvedImages": 222}
        post = {"passed": False, "failureReasons": ["distribution_mismatch"], "approvedCompleteIdentities": 74, "approvedImages": 222}
        with mock.patch("scripts.ai_image_pipeline_v3.manual_review.audit_distribution", return_value=AUDIT), \
            mock.patch("scripts.ai_image_pipeline_v3.manual_review.completion_check", side_effect=[pre, post]):
            report = clear_manual_review(root=self.root, reason="operator_safe_clear")
        self.assertTrue(report["cleared"])

    def test_active_process_probe_tolerates_non_utf8_process_output(self):
        raw = b"Node,CommandLine,ParentProcessId,ProcessId\r\nHOST,active-visual-qa-all \xbe,1,123\r\n"
        with mock.patch("scripts.ai_image_pipeline_v3.manual_review.subprocess.check_output", return_value=raw), \
            mock.patch("scripts.ai_image_pipeline_v3.manual_review.os.name", "nt"), \
            mock.patch("scripts.ai_image_pipeline_v3.manual_review.os.getpid", return_value=999):
            rows = _active_pipeline_processes()
        self.assertEqual(rows[0]["pid"], 123)


if __name__ == "__main__":
    unittest.main()
