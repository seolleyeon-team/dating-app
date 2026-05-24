import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ai_image_strict_fixture import identity_asset_rows, make_png


class BoundedReconcileCurrentStateV3Tests(unittest.TestCase):
    def _write_audit(self, root: Path) -> None:
        reports = root / "ai_image" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        audit = {
            "approvedCompleteIdentityCount": 0,
            "approvedImageCount": 0,
            "femaleApprovedIdentityCount": 0,
            "maleApprovedIdentityCount": 0,
            "countChecks": {
                "femaleApprovedIdentities": {"deficit": 1},
                "maleApprovedIdentities": {"deficit": 0},
            },
            "bucketChecks": [
                {"scope": "global", "dimension": "faceType", "bucket": "deer_like", "deficit": 1, "surplus": 0},
                {"scope": "global", "dimension": "looksLevelBand", "bucket": "2.5-3.2", "deficit": 1, "surplus": 0},
                {"scope": "female", "dimension": "faceType", "bucket": "deer_like", "deficit": 1, "surplus": 0},
                {"scope": "female", "dimension": "looksLevelBand", "bucket": "2.5-3.2", "deficit": 1, "surplus": 0},
            ],
            "globalFaceTypeDeficits": {"deer_like": 1},
            "genderFaceTypeDeficits": {"female": {"deer_like": 1}, "male": {"deer_like": 0}},
            "globalLooksLevelBandDeficits": {"2.5-3.2": 1, "4.4-5.0": 0},
            "genderLooksLevelBandDeficits": {"female": {"2.5-3.2": 1, "4.4-5.0": 0}, "male": {"2.5-3.2": 0, "4.4-5.0": 0}},
            "globalFaceTypeSurpluses": {},
            "genderFaceTypeSurpluses": {"female": {}, "male": {}},
            "globalLooksLevelBandSurpluses": {},
            "genderLooksLevelBandSurpluses": {"female": {}, "male": {}},
            "passed": False,
            "finalDecision": "needs_more_generation",
        }
        (reports / "latest_distribution_audit.json").write_text(json.dumps(audit), encoding="utf-8")

    def _write_manifest_and_plan(self, root: Path):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        from scripts.ai_image_pipeline_v3.codex_imagegen import write_imagegen_queue
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.manifest import write_generation_outputs

        self._write_audit(root)
        paths = pipeline_paths(root)
        rows = identity_asset_rows(root)
        for row in rows:
            row["status"] = "prepared"
        write_generation_outputs(paths, rows)
        write_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl", rows)
        write_imagegen_queue(root, rows)
        return create_chunk_plan(root=root)

    def test_run_refuses_when_manual_review_flag_exists(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest_and_plan(root)
            flag = root / "ai_image" / "manifests" / "manual_review_required.flag"
            flag.write_text(json.dumps({"reason": "operator_review"}), encoding="utf-8")
            calls = []

            result = run_bounded_chunk(
                root=root,
                run_func=lambda args, **kwargs: calls.append(args) or subprocess.CompletedProcess(args, 0),
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "needs_manual_review")
            self.assertEqual(result["reasonCode"], "manual_review_required")
            self.assertFalse(result["canRun"])
            self.assertEqual(calls, [])

    def test_run_refuses_non_executable_needs_manual_review_plan(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest_and_plan(root)
            manifests = root / "ai_image" / "manifests"
            plan = json.loads((manifests / "current_chunk_plan.json").read_text(encoding="utf-8"))
            plan.update({"status": "needs_manual_review", "executable": False})
            (manifests / "current_chunk_plan.json").write_text(json.dumps(plan), encoding="utf-8")
            state = json.loads((manifests / "current_chunk_state.json").read_text(encoding="utf-8"))
            state["status"] = "needs_manual_review"
            (manifests / "current_chunk_state.json").write_text(json.dumps(state), encoding="utf-8")

            result = run_bounded_chunk(root=root, run_func=lambda args, **kwargs: subprocess.CompletedProcess(args, 0), which_func=lambda cmd: f"C:/bin/{cmd}.exe")

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reasonCode"], "current_plan_not_executable")

    def test_reconcile_dry_run_does_not_mutate_or_approve(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import reconcile_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest_and_plan(root)
            final = root / "ai_image" / "female" / "001" / "face_card.png"
            make_png(final)
            state_path = root / "ai_image" / "manifests" / "current_chunk_state.json"
            before = state_path.read_text(encoding="utf-8")

            report = reconcile_bounded_chunk(root=root, dry_run=True)

            self.assertEqual(report["plannedExistingFiles"], 1)
            self.assertFalse(report["stateChanged"])
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)
            self.assertFalse((root / "ai_image" / "manifests" / "approved_identity_manifest.jsonl").exists())

    def test_extra_generation_assets_not_in_manifest_are_reported_not_counted(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import reconcile_bounded_chunk
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.manifest import load_generation_manifest, write_generation_outputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest_and_plan(root)
            paths = pipeline_paths(root)
            rows = load_generation_manifest(paths)
            extra = dict(rows[0])
            extra["assetId"] = "female_901__face_card__v001"
            extra["profileId"] = "female_901"
            rows.append(extra)
            write_generation_outputs(paths, rows)

            report = reconcile_bounded_chunk(root=root, dry_run=True)

            self.assertEqual(report["extraGenerationAssetCount"], 1)
            self.assertEqual(report["extraGenerationAssetsNotInManifest"][0]["assetId"], "female_901__face_card__v001")
            self.assertIn("extra_generation_assets_not_in_asset_manifest", report["reasonsIfCannotClear"])

    def test_resolved_pending_match_is_not_treated_as_failure_but_mismatch_is(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import reconcile_bounded_chunk
        from scripts.ai_image_pipeline_v3.codex_imagegen import pending_path, write_pending

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_manifest_and_plan(root)
            final = root / "ai_image" / "female" / "001" / "face_card.png"
            make_png(final)
            write_pending(
                pending_path(root),
                {
                    "status": "resolved",
                    "resolved": True,
                    "chunkId": json.loads((root / "ai_image" / "manifests" / "current_chunk_plan.json").read_text(encoding="utf-8"))["chunkId"],
                    "assetId": "female_001__face_card__v001",
                    "expectedFinalPath": str(final),
                },
            )

            matched = reconcile_bounded_chunk(root=root, dry_run=True)
            self.assertTrue(matched["resolvedPendingReconciled"])
            self.assertNotIn("pending_unresolved", matched["reasonsIfCannotClear"])

            write_pending(
                pending_path(root),
                {
                    "status": "resolved",
                    "resolved": True,
                    "chunkId": "wrong_chunk",
                    "assetId": "female_999__face_card__v001",
                    "expectedFinalPath": str(final),
                },
            )
            mismatched = reconcile_bounded_chunk(root=root, dry_run=True)
            self.assertIn("resolved_pending_mismatch", mismatched["reasonsIfCannotClear"])
            self.assertTrue(mismatched["resolvedPendingMismatch"])


if __name__ == "__main__":
    unittest.main()
