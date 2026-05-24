import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class BoundedChunkFocusedValidationV3Tests(unittest.TestCase):
    def _write_audit(self, root: Path) -> None:
        reports = root / "ai_image" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        bucket_checks = []
        for scope in ("global", "female", "male"):
            bucket_checks.append({"scope": scope, "dimension": "faceType", "bucket": "fox_like", "deficit": 20})
            bucket_checks.append({"scope": scope, "dimension": "faceType", "bucket": "deer_like", "deficit": 20})
            bucket_checks.append({"scope": scope, "dimension": "looksLevelBand", "bucket": "2.5-3.2", "deficit": 20})
            bucket_checks.append({"scope": scope, "dimension": "looksLevelBand", "bucket": "4.4-5.0", "deficit": 0})
        audit = {
            "approvedCompleteIdentityCount": 0,
            "approvedImageCount": 0,
            "femaleApprovedIdentityCount": 0,
            "maleApprovedIdentityCount": 0,
            "countChecks": {
                "femaleApprovedIdentities": {"deficit": 120},
                "maleApprovedIdentities": {"deficit": 120},
            },
            "bucketChecks": bucket_checks,
            "globalFaceTypeDeficits": {"fox_like": 20, "deer_like": 20},
            "genderFaceTypeDeficits": {"female": {"fox_like": 20, "deer_like": 20}, "male": {"fox_like": 20, "deer_like": 20}},
            "globalLooksLevelBandDeficits": {"2.5-3.2": 20, "4.4-5.0": 0},
            "genderLooksLevelBandDeficits": {"female": {"2.5-3.2": 20, "4.4-5.0": 0}, "male": {"2.5-3.2": 20, "4.4-5.0": 0}},
            "globalFaceTypeSurpluses": {},
            "genderFaceTypeSurpluses": {"female": {}, "male": {}},
            "globalLooksLevelBandSurpluses": {},
            "genderLooksLevelBandSurpluses": {"female": {}, "male": {}},
            "passed": False,
            "finalDecision": "needs_more_generation",
        }
        (reports / "latest_distribution_audit.json").write_text(json.dumps(audit), encoding="utf-8")

    def _write_rows(self, root: Path, specs):
        from scripts.ai_image_pipeline_v3.codex_imagegen import write_imagegen_queue
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, prompt_hash, write_jsonl
        from scripts.ai_image_pipeline_v3.manifest import write_generation_outputs
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        paths = pipeline_paths(root)
        prompt_module = load_prompt_module()
        rows = []
        for profile_id, gender, face_type, looks in specs:
            numeric = profile_id.split("_")[-1]
            for shot in ("face_card", "silhouette_card", "vibe_card"):
                prompt = f"focused prompt {profile_id} {shot}"
                rows.append(
                    {
                        "assetId": f"{profile_id}__{shot}__v001",
                        "profileId": profile_id,
                        "gender": gender,
                        "numericId": numeric,
                        "shotType": shot,
                        "targetFaceType": face_type,
                        "targetLooksLevelBand": looks,
                        "prompt": prompt,
                        "promptHash": prompt_hash(prompt),
                        "promptBuilderVersion": str(getattr(prompt_module, "PROMPT_BUILDER_VERSION", "")),
                        "promptTargetingVersion": str(getattr(prompt_module, "PROMPT_TARGETING_VERSION", "")),
                        "status": "prepared",
                        "activeForTarget": True,
                        "attempt": 0,
                        "attemptCount": 0,
                        "finalPath": str(root / "ai_image" / gender / numeric / f"{shot}.png"),
                        "localPath": str(root / "ai_image" / "raw" / f"{profile_id}__{shot}__v001__attempt01.png"),
                    }
                )
        write_generation_outputs(paths, rows)
        write_imagegen_queue(root, rows)
        write_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl", rows)
        return rows

    def _setup(self, root: Path, specs=None):
        self._write_audit(root)
        return self._write_rows(
            root,
            specs
            or [
                ("female_001", "female", "fox_like", "2.5-3.2"),
                ("male_001", "male", "fox_like", "2.5-3.2"),
                ("female_002", "female", "fox_like", "2.5-3.2"),
                ("female_003", "female", "deer_like", "2.5-3.2"),
                ("male_002", "male", "fox_like", "4.4-5.0"),
            ],
        )

    def test_cli_help_exposes_focused_filters(self):
        result = subprocess.run(
            [sys.executable, "scripts/run_ai_image_pipeline_v3.py", "bounded-chunk-plan", "--help"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("--face_type", result.stdout)
        self.assertIn("--looks_level_band", result.stdout)
        self.assertIn("--require-focused-match", result.stdout)

    def test_focused_selector_selects_only_requested_face_and_band(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=3, max_assets=9, face_type="fox_like", looks_level_band="2.5-3.2", require_focused_match=True)
            self.assertEqual({i["targetFaceType"] for i in plan["identities"]}, {"fox_like"})
            self.assertEqual({i["targetLooksLevelBand"] for i in plan["identities"]}, {"2.5-3.2"})

    def test_selected_asset_count_is_identity_count_times_three(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=3, max_assets=9, face_type="fox_like", looks_level_band="2.5-3.2", require_focused_match=True)
            self.assertEqual(plan["selectedAssetCount"], plan["selectedIdentityCount"] * 3)

    def test_selected_assets_are_all_v4(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            expected = str(getattr(load_prompt_module(), "PROMPT_TARGETING_VERSION", ""))
            plan = create_chunk_plan(root=root, production=True, max_identities=3, max_assets=9, face_type="fox_like", looks_level_band="2.5-3.2", require_focused_match=True)
            self.assertTrue(expected)
            self.assertTrue(all(asset["promptTargetingVersion"] == expected for identity in plan["identities"] for asset in identity["assets"]))

    def test_prompt_hash_mismatches_zero(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        from scripts.ai_image_pipeline_v3.config import prompt_hash
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=3, max_assets=9, face_type="fox_like", looks_level_band="2.5-3.2", require_focused_match=True)
            mismatches = [asset["assetId"] for identity in plan["identities"] for asset in identity["assets"] if asset["promptHash"] != prompt_hash(asset["prompt"])]
            self.assertEqual(mismatches, [])

    def test_no_four_point_four_to_five_selected(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=3, max_assets=9, face_type="fox_like", looks_level_band="2.5-3.2", require_focused_match=True)
            self.assertNotIn("4.4-5.0", {i["targetLooksLevelBand"] for i in plan["identities"]})

    def test_no_rejected_identity_reuse(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root, [("female_001", "female", "fox_like", "2.5-3.2"), ("female_002", "female", "fox_like", "2.5-3.2"), ("male_001", "male", "fox_like", "2.5-3.2"), ("male_002", "male", "fox_like", "2.5-3.2")])
            write_jsonl(pipeline_paths(root).manifests / "rejected_identity_manifest.jsonl", [{"profileId": "female_001", "status": "rejected"}])
            plan = create_chunk_plan(root=root, production=True, max_identities=3, max_assets=9, face_type="fox_like", looks_level_band="2.5-3.2", require_focused_match=True)
            self.assertNotIn("female_001", {i["profileId"] for i in plan["identities"]})

    def test_insufficient_candidates_fail_clearly(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import PlanValidationError, create_chunk_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root, [("female_001", "female", "fox_like", "2.5-3.2"), ("male_001", "male", "fox_like", "2.5-3.2")])
            with self.assertRaises(PlanValidationError) as ctx:
                create_chunk_plan(root=root, production=True, max_identities=3, max_assets=9, face_type="fox_like", looks_level_band="2.5-3.2", require_focused_match=True)
            self.assertEqual(ctx.exception.reason_code, "focused_selection_insufficient_candidates")

    def test_abandon_current_preserves_historical_files_and_approved_manifest(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, current_plan_path, current_state_path
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            paths = pipeline_paths(root)
            approved_path = paths.manifests / "approved_identity_manifest.jsonl"
            write_jsonl(approved_path, [{"profileId": "approved_001", "status": "approved"}])
            before = approved_path.read_text(encoding="utf-8")
            old_report = paths.reports / "chunks" / "chunk_old" / "keep.txt"
            old_report.parent.mkdir(parents=True, exist_ok=True)
            old_report.write_text("historical evidence", encoding="utf-8")
            current_plan_path(root).write_text(json.dumps({"schemaVersion": "seolleyeon_bounded_chunk_plan_v3", "chunkId": "chunk_old", "planMode": "production", "status": "generation_paused", "identities": [{"profileId": "old_001", "assets": []}]}), encoding="utf-8")
            current_state_path(root).write_text(json.dumps({"schemaVersion": "seolleyeon_bounded_chunk_state_v3", "chunkId": "chunk_old", "status": "generation_paused", "assetStates": {}, "identityStates": {}}), encoding="utf-8")
            plan = create_chunk_plan(root=root, production=True, force_replan=True, abandon_current=True, max_identities=3, max_assets=9, face_type="fox_like", looks_level_band="2.5-3.2", require_focused_match=True)
            self.assertNotEqual(plan["chunkId"], "chunk_old")
            self.assertEqual(approved_path.read_text(encoding="utf-8"), before)
            self.assertTrue(old_report.exists())
            self.assertTrue((paths.reports / "chunks" / "chunk_old" / "abandoned_current_chunk_plan.json").exists())

    def test_no_image_generation_occurs_during_planning(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            create_chunk_plan(root=root, production=True, max_identities=3, max_assets=9, face_type="fox_like", looks_level_band="2.5-3.2", require_focused_match=True)
            raw_dir = root / "ai_image" / "raw"
            self.assertEqual(list(raw_dir.glob("*.png")) if raw_dir.exists() else [], [])


if __name__ == "__main__":
    unittest.main()
