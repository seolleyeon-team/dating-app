import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ReservePoolActivationV3Tests(unittest.TestCase):
    def _write_audit(self, root: Path) -> None:
        reports = root / "ai_image" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        bucket_checks = []
        for scope in ("global", "female", "male"):
            bucket_checks.append({"scope": scope, "dimension": "faceType", "bucket": "fox_like", "deficit": 20})
            bucket_checks.append({"scope": scope, "dimension": "looksLevelBand", "bucket": "2.5-3.2", "deficit": 20})
            bucket_checks.append({"scope": scope, "dimension": "looksLevelBand", "bucket": "4.4-5.0", "deficit": 20})
        audit = {
            "approvedCompleteIdentityCount": 0,
            "approvedImageCount": 0,
            "countChecks": {"femaleApprovedIdentities": {"deficit": 120}, "maleApprovedIdentities": {"deficit": 120}},
            "bucketChecks": bucket_checks,
            "globalFaceTypeDeficits": {"fox_like": 20},
            "genderFaceTypeDeficits": {"female": {"fox_like": 20}, "male": {"fox_like": 20}},
            "globalLooksLevelBandDeficits": {"2.5-3.2": 20, "4.4-5.0": 20},
            "genderLooksLevelBandDeficits": {"female": {"2.5-3.2": 20, "4.4-5.0": 20}, "male": {"2.5-3.2": 20, "4.4-5.0": 20}},
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
        for profile_id, gender, face_type, looks, active, reserve, status in specs:
            numeric = profile_id.split("_")[-1]
            for shot in ("face_card", "silhouette_card", "vibe_card"):
                prompt = f"reserve prompt {profile_id} {shot}"
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
                        "status": status,
                        "activeForTarget": active,
                        "isReserve": reserve,
                        "identityScope": "reserve" if reserve else "primary",
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
        return self._write_rows(root, specs or [("female_121", "female", "fox_like", "2.5-3.2", False, True, "prepared")])

    def test_cli_help_exposes_activate_reserve(self):
        result = subprocess.run([sys.executable, "scripts/run_ai_image_pipeline_v3.py", "bounded-chunk-plan", "--help"], text=True, capture_output=True, check=True)
        self.assertIn("--activate-reserve", result.stdout)

    def test_without_activate_reserve_reserve_profiles_remain_excluded(self):
        from scripts.ai_image_pipeline_v3.distribution_selection import select_distribution_buckets
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            selection = select_distribution_buckets(root=root, max_identities=3)
            self.assertEqual(selection["selectedIdentities"], [])

    def test_with_activate_reserve_reserve_profiles_become_eligible(self):
        from scripts.ai_image_pipeline_v3.distribution_selection import select_distribution_buckets
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            selection = select_distribution_buckets(root=root, max_identities=3, activate_reserve=True)
            self.assertEqual([i["profileId"] for i in selection["selectedIdentities"]], ["female_121"])
            self.assertTrue(selection["selectedIdentities"][0]["reserveActivation"])

    def test_rejected_reserve_profile_remains_excluded(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.distribution_selection import select_distribution_buckets
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            write_jsonl(pipeline_paths(root).manifests / "rejected_identity_manifest.jsonl", [{"profileId": "female_121", "status": "rejected"}])
            self.assertEqual(select_distribution_buckets(root=root, activate_reserve=True)["selectedIdentities"], [])

    def test_approved_reserve_profile_remains_excluded(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.distribution_selection import select_distribution_buckets
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            write_jsonl(pipeline_paths(root).manifests / "identity_qa_manifest.jsonl", [{"profileId": "female_121", "status": "approved"}])
            self.assertEqual(select_distribution_buckets(root=root, activate_reserve=True)["selectedIdentities"], [])

    def test_prompt_targeting_version_mismatch_excluded_by_active_rows(self):
        from scripts.ai_image_pipeline_v3.distribution_selection import select_distribution_buckets
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = self._setup(root)
            from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
            for row in rows:
                row["promptTargetingVersion"] = "stale_version"
            write_jsonl(pipeline_paths(root).manifests / "ai_profile_assets_v3.jsonl", rows)
            self.assertEqual(select_distribution_buckets(root=root, activate_reserve=True)["selectedIdentities"], [])

    def test_prompt_hash_mismatch_excluded_by_active_rows(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.distribution_selection import select_distribution_buckets
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = self._setup(root)
            for row in rows:
                row["promptHash"] = "bad_hash"
            write_jsonl(pipeline_paths(root).manifests / "ai_profile_assets_v3.jsonl", rows)
            self.assertEqual(select_distribution_buckets(root=root, activate_reserve=True)["selectedIdentities"], [])

    def test_four_point_four_to_five_reserve_target_excluded(self):
        from scripts.ai_image_pipeline_v3.distribution_selection import select_distribution_buckets
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root, [("female_121", "female", "fox_like", "4.4-5.0", False, True, "prepared")])
            self.assertEqual(select_distribution_buckets(root=root, activate_reserve=True)["selectedIdentities"], [])

    def test_selected_asset_count_is_identity_count_times_three_and_no_files_touched(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=1, max_assets=3, activate_reserve=True)
            self.assertEqual(plan["selectedAssetCount"], plan["selectedIdentityCount"] * 3)
            self.assertEqual(list((root / "ai_image" / "raw").glob("*.png")) if (root / "ai_image" / "raw").exists() else [], [])

    def test_no_deficit_assets_available_not_raised_when_reserve_exists(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=1, max_assets=3, activate_reserve=True)
            self.assertEqual(plan["selectedIdentityCount"], 1)
            self.assertEqual(plan["reserveActivation"]["selectedReserveIdentityCount"], 1)


if __name__ == "__main__":
    unittest.main()
