import tempfile
import unittest
from pathlib import Path


class PromptVersionManifestRefreshV3Tests(unittest.TestCase):
    def _prepare_full_manifest_set(self, root: Path):
        from scripts.ai_image_pipeline_v3.distribution_audit import audit_distribution
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        result = prepare_assets(root=root, force=True, replace_manifest=True)
        audit_distribution(root=root)
        return result

    def test_prepare_export_emits_prompt_targeting_version_everywhere(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, read_jsonl
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        prompt_module = load_prompt_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self._prepare_full_manifest_set(root)
            paths = pipeline_paths(root)

            specs = read_jsonl(paths.manifests / "ai_profile_specs_v3.jsonl")
            assets = read_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl")
            identities = read_jsonl(paths.manifests / "identity_manifest.jsonl")
            generation = read_jsonl(paths.manifests / "generation_manifest.jsonl")
            queue = read_jsonl(paths.manifests / "imagegen_queue.jsonl")

        self.assertEqual(result.specs_count, 280)
        self.assertEqual(result.asset_count, 840)
        self.assertEqual(sum(1 for row in assets if row.get("activeForTarget", True) and not row.get("isReserve")), 720)
        for rows in (specs, assets, identities, generation, queue):
            self.assertTrue(rows)
            self.assertTrue(all(row.get("promptTargetingVersion") == prompt_module.PROMPT_TARGETING_VERSION for row in rows))
        self.assertTrue(all(row.get("promptHash") for row in assets))
        self.assertTrue(all(row.get("promptHash") for row in generation))

    def test_prepare_force_replace_drops_stale_generation_rows(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, read_jsonl, write_jsonl
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        prompt_module = load_prompt_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_full_manifest_set(root)
            paths = pipeline_paths(root)
            generation_path = paths.manifests / "generation_manifest.jsonl"
            generation = read_jsonl(generation_path)
            stale = dict(generation[0])
            stale["assetId"] = "female_999__face_card__v001"
            stale["profileId"] = "female_999"
            stale["promptTargetingVersion"] = "old_prompt_targeting_version"
            write_jsonl(generation_path, [*generation, stale])

            prepare_assets(root=root, force=True, replace_manifest=True)
            refreshed = read_jsonl(generation_path)

        self.assertEqual(len(refreshed), 840)
        self.assertFalse(any(row.get("assetId") == "female_999__face_card__v001" for row in refreshed))
        self.assertTrue(all(row.get("promptTargetingVersion") == prompt_module.PROMPT_TARGETING_VERSION for row in refreshed))

    def test_active_generation_filter_ignores_old_prompt_version_evidence(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import _active_generation_rows
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, read_jsonl, write_jsonl
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        prompt_module = load_prompt_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_full_manifest_set(root)
            paths = pipeline_paths(root)
            generation_path = paths.manifests / "generation_manifest.jsonl"
            generation = read_jsonl(generation_path)
            stale_same_asset = dict(generation[0])
            stale_same_asset["promptTargetingVersion"] = "old_prompt_targeting_version"
            stale_same_asset["promptHash"] = "oldhash"
            stale_extra = dict(generation[1])
            stale_extra["assetId"] = "female_999__silhouette_card__v001"
            stale_extra["profileId"] = "female_999"
            stale_extra["promptTargetingVersion"] = prompt_module.PROMPT_TARGETING_VERSION
            write_jsonl(generation_path, [*generation, stale_same_asset, stale_extra])

            active_rows = _active_generation_rows(root)

        self.assertEqual(len(active_rows), 840)
        self.assertFalse(any(row.get("promptHash") == "oldhash" for row in active_rows))
        self.assertFalse(any(row.get("assetId") == "female_999__silhouette_card__v001" for row in active_rows))

    def test_fresh_plan_after_prompt_patch_selects_full_current_version_chunk(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        from scripts.ai_image_pipeline_v3.config import prompt_hash
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        prompt_module = load_prompt_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._prepare_full_manifest_set(root)

            plan = create_chunk_plan(root=root, production=True, force_replan=True)

        self.assertEqual(plan["planType"], "full_identity_generation")
        self.assertFalse(plan["partialPlanAllowed"])
        self.assertEqual(plan["selectedIdentityCount"], 24)
        self.assertEqual(plan["selectedAssetCount"], 72)
        for identity in plan["identities"]:
            self.assertEqual({asset["shotType"] for asset in identity["assets"]}, {"face_card", "silhouette_card", "vibe_card"})
            for asset in identity["assets"]:
                self.assertEqual(asset.get("promptTargetingVersion"), prompt_module.PROMPT_TARGETING_VERSION)
                self.assertEqual(asset.get("promptHash"), prompt_hash(asset.get("prompt") or ""))


if __name__ == "__main__":
    unittest.main()
