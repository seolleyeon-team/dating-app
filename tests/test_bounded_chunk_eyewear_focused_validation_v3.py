import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class BoundedChunkEyewearFocusedValidationV3Tests(unittest.TestCase):
    def _write_audit(self, root: Path) -> None:
        reports = root / "ai_image" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        bucket_checks = []
        for scope in ("global", "female", "male"):
            for face_type in ("fox_like", "deer_like"):
                bucket_checks.append({"scope": scope, "dimension": "faceType", "bucket": face_type, "deficit": 20})
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
        for profile_id, gender, face_type, looks, has_eyewear in specs:
            numeric = profile_id.split("_")[-1]
            eyewear_group = "glasses" if has_eyewear else "none"
            eyewear = "thin_round_metal" if has_eyewear else "none"
            for shot in ("face_card", "silhouette_card", "vibe_card"):
                prompt = f"eyewear focused prompt {profile_id} {shot} {eyewear}"
                rows.append(
                    {
                        "assetId": f"{profile_id}__{shot}__v001",
                        "profileId": profile_id,
                        "gender": gender,
                        "numericId": numeric,
                        "shotType": shot,
                        "targetFaceType": face_type,
                        "targetLooksLevelBand": looks,
                        "hasEyewear": has_eyewear,
                        "eyewearGroup": eyewear_group,
                        "eyewear": eyewear,
                        "canonicalEyewear": eyewear,
                        "shotEyewearExpected": eyewear,
                        "temporaryEyewearAllowed": False,
                        "temporaryEyewearApplied": False,
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
                ("female_001", "female", "fox_like", "2.5-3.2", True),
                ("female_002", "female", "fox_like", "2.5-3.2", False),
                ("male_001", "male", "fox_like", "2.5-3.2", False),
                ("male_002", "male", "fox_like", "2.5-3.2", True),
                ("female_003", "female", "deer_like", "2.5-3.2", False),
                ("male_003", "male", "fox_like", "4.4-5.0", True),
            ],
        )

    def test_cli_help_exposes_eyewear_filters(self):
        result = subprocess.run(
            [sys.executable, "scripts/run_ai_image_pipeline_v3.py", "bounded-chunk-plan", "--help"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("--has_eyewear", result.stdout)
        self.assertIn("--eyewear_group", result.stdout)
        self.assertIn("--require-eyewear-mix", result.stdout)

    def test_has_eyewear_true_filter_selects_only_eyewear_identities(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=2, max_assets=6, has_eyewear="true", require_focused_match=True)
            self.assertEqual({identity["hasEyewear"] for identity in plan["identities"]}, {True})
            self.assertEqual({identity["eyewearGroup"] for identity in plan["identities"]}, {"glasses"})

    def test_has_eyewear_false_filter_selects_only_no_eyewear_identities(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=2, max_assets=6, has_eyewear="false", require_focused_match=True)
            self.assertEqual({identity["hasEyewear"] for identity in plan["identities"]}, {False})
            self.assertEqual({identity["eyewearGroup"] for identity in plan["identities"]}, {"none"})

    def test_eyewear_group_filter_selects_only_matching_group(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=2, max_assets=6, eyewear_group="glasses", require_focused_match=True)
            self.assertEqual({identity["eyewearGroup"] for identity in plan["identities"]}, {"glasses"})

    def test_require_eyewear_mix_selects_eyewear_and_no_eyewear_identities(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=3, max_assets=9, require_eyewear_mix=True, require_focused_match=True)
            self.assertIn(True, {identity["hasEyewear"] for identity in plan["identities"]})
            self.assertIn(False, {identity["hasEyewear"] for identity in plan["identities"]})
            self.assertEqual(plan["selectedAssetCount"], plan["selectedIdentityCount"] * 3)

    def test_face_band_and_eyewear_mix_selects_v6_full_identities(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        from scripts.ai_image_pipeline_v3.config import prompt_hash
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            expected = str(getattr(load_prompt_module(), "PROMPT_TARGETING_VERSION", ""))
            plan = create_chunk_plan(
                root=root,
                production=True,
                max_identities=3,
                max_assets=9,
                face_type="fox_like",
                looks_level_band="2.5-3.2",
                require_eyewear_mix=True,
                require_focused_match=True,
            )
            self.assertEqual({identity["targetFaceType"] for identity in plan["identities"]}, {"fox_like"})
            self.assertEqual({identity["targetLooksLevelBand"] for identity in plan["identities"]}, {"2.5-3.2"})
            self.assertIn(True, {identity["hasEyewear"] for identity in plan["identities"]})
            self.assertIn(False, {identity["hasEyewear"] for identity in plan["identities"]})
            self.assertTrue(all(asset["promptTargetingVersion"] == expected for identity in plan["identities"] for asset in identity["assets"]))
            for identity in plan["identities"]:
                expected_eyewear = identity["canonicalEyewear"]
                self.assertEqual({asset["hasEyewear"] for asset in identity["assets"]}, {identity["hasEyewear"]})
                self.assertEqual({asset["canonicalEyewear"] for asset in identity["assets"]}, {expected_eyewear})
                self.assertEqual({asset["shotEyewearExpected"] for asset in identity["assets"]}, {expected_eyewear})
                self.assertEqual({asset["temporaryEyewearApplied"] for asset in identity["assets"]}, {False})
            self.assertEqual(
                [
                    asset["assetId"]
                    for identity in plan["identities"]
                    for asset in identity["assets"]
                    if asset["promptHash"] != prompt_hash(asset["prompt"])
                ],
                [],
            )

    def test_strict_focus_fails_clearly_when_eyewear_mix_is_insufficient(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import PlanValidationError, create_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(
                root,
                [
                    ("female_001", "female", "fox_like", "2.5-3.2", False),
                    ("female_002", "female", "fox_like", "2.5-3.2", False),
                    ("male_001", "male", "fox_like", "2.5-3.2", False),
                ],
            )
            with self.assertRaises(PlanValidationError) as ctx:
                create_chunk_plan(root=root, production=True, max_identities=3, max_assets=9, require_eyewear_mix=True, require_focused_match=True)
            self.assertEqual(ctx.exception.reason_code, "focused_selection_insufficient_candidates")
            self.assertIn("eyewear_mix_missing", json.dumps(ctx.exception.details))

    def test_no_rejected_identity_reuse_with_eyewear_focus(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._setup(root)
            write_jsonl(pipeline_paths(root).manifests / "rejected_identity_manifest.jsonl", [{"profileId": "female_001", "status": "rejected"}])
            plan = create_chunk_plan(root=root, production=True, max_identities=3, max_assets=9, require_eyewear_mix=True, require_focused_match=True)
            self.assertNotIn("female_001", {identity["profileId"] for identity in plan["identities"]})


if __name__ == "__main__":
    unittest.main()
