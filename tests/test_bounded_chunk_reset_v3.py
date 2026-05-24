import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class BoundedChunkResetV3Tests(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_jsonl(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    def _fixture(
        self,
        root: Path,
        *,
        status: str = "needs_manual_review",
        executable: bool = False,
        manual_flag: bool = True,
        pending: dict | None = None,
        include_extra: bool = True,
    ) -> dict:
        from scripts.ai_image_pipeline_v3.codex_imagegen import pending_path
        from scripts.ai_image_pipeline_v3.config import pipeline_paths

        paths = pipeline_paths(root)
        chunk_id = "chunk_test_reset"
        assets = []
        for shot in ("face_card", "silhouette_card", "vibe_card"):
            asset_id = f"female_001__{shot}__v001"
            final = paths.final / "female" / "001" / f"{shot}.png"
            if shot == "face_card":
                final.parent.mkdir(parents=True, exist_ok=True)
                final.write_bytes(b"preserve-me")
            assets.append(
                {
                    "assetId": asset_id,
                    "profileId": "female_001",
                    "gender": "female",
                    "numericId": "001",
                    "shotType": shot,
                    "finalPath": str(final),
                    "status": "file_qa_passed",
                }
            )
        plan = {
            "schemaVersion": "seolleyeon_bounded_chunk_plan_v3",
            "chunkId": chunk_id,
            "status": status,
            "planMode": "production",
            "executable": executable,
            "selectedIdentityCount": 1,
            "selectedAssetCount": 3,
            "identities": [
                {
                    "profileId": "female_001",
                    "gender": "female",
                    "numericId": "001",
                    "targetFaceType": "deer_like",
                    "targetLooksLevelBand": "2.5-3.2",
                    "assets": assets,
                }
            ],
        }
        state = {
            "schemaVersion": "seolleyeon_bounded_chunk_state_v3",
            "chunkId": chunk_id,
            "planHash": "",
            "status": status,
            "currentAssetId": "",
            "assetStates": {asset["assetId"]: "file_qa_passed" for asset in assets},
            "identityStates": {"female_001": "rejected"},
            "activeVisualQaComplete": True,
            "distributionAuditComplete": True,
        }
        self._write_json(paths.manifests / "current_chunk_plan.json", plan)
        self._write_json(paths.manifests / "current_chunk_state.json", state)
        if manual_flag:
            self._write_json(paths.manifests / "manual_review_required.flag", {"reason": "bounded_active_visual_qa_failed"})
        if pending is not None:
            self._write_json(pending_path(root), pending)
        else:
            self._write_json(pending_path(root), {"status": "cleared", "resolved": True, "assetId": assets[0]["assetId"], "chunkId": chunk_id})

        generation_rows = list(assets)
        extra_final = paths.final / "female" / "901" / "face_card.png"
        if include_extra:
            extra_final.parent.mkdir(parents=True, exist_ok=True)
            extra_final.write_bytes(b"extra")
            generation_rows.append(
                {
                    "assetId": "female_901__face_card__v001",
                    "profileId": "female_901",
                    "gender": "female",
                    "numericId": "901",
                    "shotType": "face_card",
                    "finalPath": str(extra_final),
                    "localPath": str(extra_final),
                    "status": "file_qa_passed",
                }
            )
        self._write_jsonl(paths.manifests / "generation_manifest.jsonl", generation_rows)
        self._write_jsonl(paths.manifests / "asset_manifest.jsonl", assets)
        self._write_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl", assets)
        self._write_jsonl(paths.manifests / "identity_manifest.jsonl", [{"profileId": "female_001"}])
        self._write_jsonl(paths.manifests / "ai_profile_specs_v3.jsonl", [{"profileId": "female_001"}])
        for name in (
            "file_qa_manifest.jsonl",
            "asset_qa_manifest.jsonl",
            "identity_qa_manifest.jsonl",
            "approved_identity_manifest.jsonl",
            "rejected_identity_manifest.jsonl",
            "needs_review_identity_manifest.jsonl",
            "imagegen_queue.jsonl",
        ):
            self._write_jsonl(paths.manifests / name, [])

        chunk_dir = paths.reports / "chunks" / chunk_id
        self._write_json(chunk_dir / "chunk_report.json", {"chunkId": chunk_id, "status": status})
        self._write_json(chunk_dir / "reconcile_report.json", {"chunkId": chunk_id})
        self._write_json(chunk_dir / "current_chunk_retry_decision.json", {"chunkId": chunk_id})
        self._write_json(chunk_dir / "current_chunk_reset_recommendation.json", {"chunkId": chunk_id})
        self._write_json(chunk_dir / "transactions" / "female_001__face_card__v001_attempt1.json", {"assetId": assets[0]["assetId"]})
        self._write_json(chunk_dir / "contact_sheets" / "contact_sheet_index.json", {"chunkId": chunk_id})
        (chunk_dir / "events.jsonl").write_text(json.dumps({"eventType": "test"}) + "\n", encoding="utf-8")
        visual_dir = paths.reports / "visual_verdict"
        self._write_json(visual_dir / "asset_qa_latest.json", {"checked": 0, "assets": []})
        self._write_json(visual_dir / "identity_qa_latest.json", {"checked": 0, "identities": []})
        self._write_json(visual_dir / "distribution_audit_latest.json", {"checked": 0})
        self._write_json(paths.reports / "latest_distribution_audit.json", {"approvedCompleteIdentityCount": 0, "approvedImageCount": 0, "passed": False, "finalDecision": "needs_more_generation"})
        return {"chunkId": chunk_id, "finalFile": paths.final / "female" / "001" / "face_card.png", "extraFile": extra_final}

    def test_dispatcher_help_exposes_bounded_chunk_reset(self):
        from scripts.ai_image_pipeline_v3.cli import build_parser

        self.assertIn("bounded-chunk-reset", build_parser().format_help())
        self.assertIn("clear-manual-review", build_parser().format_help())

    def test_dry_run_reset_creates_report_without_mutating_current_pointers(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import bounded_chunk_reset

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            plan_path = root / "ai_image" / "manifests" / "current_chunk_plan.json"
            state_path = root / "ai_image" / "manifests" / "current_chunk_state.json"
            pending_path = root / "ai_image" / "manifests" / "pending-imagegen.json"
            before = (plan_path.read_text(encoding="utf-8"), state_path.read_text(encoding="utf-8"), pending_path.read_text(encoding="utf-8"))

            report = bounded_chunk_reset(root=root, archive_current=True, dry_run=True)

            self.assertTrue(report["safeToApply"])
            self.assertTrue((root / "ai_image" / "reports" / "chunks" / fixture["chunkId"] / "reset_dry_run_report.json").exists())
            self.assertEqual(before, (plan_path.read_text(encoding="utf-8"), state_path.read_text(encoding="utf-8"), pending_path.read_text(encoding="utf-8")))
            self.assertTrue(fixture["finalFile"].exists())

    def test_apply_reset_archives_pointers_reports_and_manifest_snapshots(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import bounded_chunk_reset

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            report = bounded_chunk_reset(root=root, archive_current=True)

            self.assertEqual(report["status"], "reset")
            self.assertFalse((root / "ai_image" / "manifests" / "current_chunk_plan.json").exists())
            self.assertFalse((root / "ai_image" / "manifests" / "current_chunk_state.json").exists())
            self.assertFalse((root / "ai_image" / "manifests" / "pending-imagegen.json").exists())
            self.assertTrue(Path(report["archivedPlanPath"]).exists())
            self.assertTrue(Path(report["archivedStatePath"]).exists())
            self.assertTrue((Path(report["archivedReportsDir"]) / "chunk_reports" / "chunk_report.json").exists())
            self.assertTrue((Path(report["archivedReportsDir"]) / "chunk_reports" / "events.jsonl").exists())
            self.assertTrue((Path(report["archivedManifestSnapshotDir"]) / "generation_manifest.jsonl").exists())
            self.assertTrue(fixture["finalFile"].exists())
            self.assertFalse(report["approvedCountChanged"])
            self.assertFalse(report["distributionCountChanged"])
            self.assertTrue((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())

    def test_clear_manual_flag_only_when_explicit_and_completion_safe(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import bounded_chunk_reset

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            report = bounded_chunk_reset(root=root, archive_current=True, clear_manual_flag_if_safe=True)

            self.assertTrue(report["manualFlagClearResult"]["requested"])
            self.assertTrue(report["manualFlagClearResult"]["cleared"])
            self.assertFalse((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())

    def test_extra_assets_are_left_by_default_and_copied_only_when_requested(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import bounded_chunk_reset

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            report = bounded_chunk_reset(root=root, archive_current=True)

            self.assertEqual(report["extraAssetsAction"], "left_in_place")
            self.assertTrue(fixture["extraFile"].exists())
            self.assertFalse((root / "ai_image" / "quarantine").exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = self._fixture(root)
            report = bounded_chunk_reset(root=root, archive_current=True, quarantine_extra=True)

            self.assertEqual(report["extraAssetsAction"], "copy_to_quarantine_original_preserved")
            self.assertTrue(report["quarantinedFiles"])
            self.assertTrue(fixture["extraFile"].exists())
            self.assertTrue(Path(report["quarantinedFiles"][0]["target"]).exists())

    def test_reset_refuses_unresolved_pending_and_healthy_running_chunk_without_force(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import bounded_chunk_reset

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root, pending={"status": "pending_imagegen", "resolved": False, "assetId": "female_001__face_card__v001"})
            report = bounded_chunk_reset(root=root, archive_current=True, dry_run=True)
            self.assertFalse(report["safeToApply"])
            self.assertIn("pending_unresolved", report["reasonsIfUnsafe"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root, status="running", executable=True, manual_flag=False, pending={})
            report = bounded_chunk_reset(root=root, archive_current=True, dry_run=True)
            self.assertFalse(report["safeToApply"])
            self.assertIn("active_executable_chunk_not_resettable", report["reasonsIfUnsafe"])
            forced = bounded_chunk_reset(root=root, archive_current=True, dry_run=True, force=True)
            self.assertTrue(forced["safeToApply"])

    def test_completion_still_fails_after_default_reset(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import bounded_chunk_reset
        from scripts.ai_image_pipeline_v3.completion import completion_check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            bounded_chunk_reset(root=root, archive_current=True)
            completion = completion_check(root=root)

            self.assertFalse(completion["passed"])
            self.assertIn("manual_review_required", completion["failureReasons"])
            self.assertIn("distribution_mismatch", completion["failureReasons"])

    def test_clear_manual_review_archives_flag_after_reset(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import bounded_chunk_reset
        from scripts.ai_image_pipeline_v3.manual_review import clear_manual_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            bounded_chunk_reset(root=root, archive_current=True)

            result = clear_manual_review(root=root, reason="archived_chunk_reset_complete")

            self.assertTrue(result["cleared"])
            self.assertFalse((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())
            self.assertTrue(Path(result["archivePath"]).exists())
            self.assertEqual(result["postClearCompletion"]["failureReasons"], ["distribution_mismatch"])

    def test_clear_manual_review_refuses_active_chunk(self):
        from scripts.ai_image_pipeline_v3.manual_review import clear_manual_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)

            result = clear_manual_review(root=root, reason="archived_chunk_reset_complete")

            self.assertFalse(result["cleared"])
            self.assertIn("active_current_chunk_not_finalized", result["readiness"]["reasonsIfUnsafe"])
            self.assertTrue((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())

    def test_clear_manual_review_allows_finalized_active_chunk_with_preserved_counts(self):
        from scripts.ai_image_pipeline_v3.manual_review import clear_manual_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root, status="finalized", manual_flag=True, include_extra=False)
            audit = {
                "passed": False,
                "finalDecision": "needs_more_generation",
                "approvedCompleteIdentityCount": 5,
                "approvedImageCount": 15,
            }
            pre_completion = {
                "passed": False,
                "failureReasons": ["manual_review_required", "distribution_mismatch"],
                "approvedCompleteIdentities": 5,
                "approvedImages": 15,
            }
            post_completion = {
                "passed": False,
                "failureReasons": ["distribution_mismatch"],
                "approvedCompleteIdentities": 5,
                "approvedImages": 15,
            }

            with patch("scripts.ai_image_pipeline_v3.manual_review.audit_distribution", return_value=audit), patch(
                "scripts.ai_image_pipeline_v3.manual_review.completion_check",
                side_effect=[pre_completion, post_completion],
            ):
                result = clear_manual_review(root=root, reason="current_chunk_partial_finalized")

            self.assertTrue(result["cleared"])
            self.assertTrue(result["readiness"]["activeChunk"]["allowed"])
            self.assertEqual(result["readiness"]["activeChunk"]["stateStatus"], "finalized")
            self.assertFalse((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())


if __name__ == "__main__":
    unittest.main()
