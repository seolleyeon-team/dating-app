import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path


class DistributionPrepareTargetsV3Tests(unittest.TestCase):
    def test_default_full_prepare_has_exact_face_looks_eyewear_and_season_targets(self):
        from scripts.ai_image_pipeline_v3.distribution_prepare import build_distribution_controlled_asset_records, distribution_counts
        from scripts.ai_image_pipeline_v3.distribution_targets import DEFAULT_DISTRIBUTION_TARGETS
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        prompt_module = load_prompt_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            specs, assets = build_distribution_controlled_asset_records(
                root=root,
                female_count=120,
                male_count=120,
                reserve_female_count=20,
                reserve_male_count=20,
                start_female=1,
                start_male=1,
                start_reserve_female=901,
                start_reserve_male=901,
                seed=20260514,
                id_width=3,
            )

        targets = DEFAULT_DISTRIBUTION_TARGETS
        counts = distribution_counts(specs)
        self.assertEqual(counts["faceType"], targets["faceTypeTargets"]["global"])
        self.assertEqual(counts["looksLevelBand"], targets["looksLevelBandTargets"]["global"])
        self.assertEqual(counts["eyewear"], targets["eyewearTargets"]["global"])
        self.assertEqual(counts["season"], targets["seasonTargets"]["global"])
        self.assertEqual(counts["genderEyewear"]["female_with_eyewear"], 12)
        self.assertEqual(counts["genderEyewear"]["male_with_eyewear"], 24)
        self.assertEqual(counts["looksLevelBand"]["4.4-5.0"], 0)

        reserve_counts = Counter()
        for spec in specs:
            if not spec.get("isReserve"):
                continue
            accessories = spec.get("accessories") if isinstance(spec.get("accessories"), dict) else {}
            bucket = "with_eyewear" if accessories.get("hasEyewear") or accessories.get("eyewearGroup") == "glasses" else "without_eyewear"
            reserve_counts[f"{spec['gender']}_{bucket}"] += 1
        self.assertEqual(reserve_counts["female_with_eyewear"], 2)
        self.assertEqual(reserve_counts["male_with_eyewear"], 4)

        by_profile: dict[str, list[dict]] = defaultdict(list)
        for asset in assets:
            by_profile[str(asset["profileId"])].append(dict(asset))
            self.assertTrue(asset.get("promptHash"), asset["assetId"])
            self.assertEqual(asset.get("promptTargetingVersion"), prompt_module.PROMPT_TARGETING_VERSION)
            self.assertEqual(asset.get("promptBuilderVersion"), prompt_module.PROMPT_BUILDER_VERSION)
        for profile_assets in by_profile.values():
            self.assertEqual({asset.get("hasEyewear") for asset in profile_assets}, {profile_assets[0].get("hasEyewear")})
            self.assertEqual({asset.get("eyewearGroup") for asset in profile_assets}, {profile_assets[0].get("eyewearGroup")})
            self.assertEqual({asset.get("season") for asset in profile_assets}, {profile_assets[0].get("season")})
            self.assertEqual({asset["shotType"] for asset in profile_assets}, {"face_card", "silhouette_card", "vibe_card"})

    def test_prompt_hash_is_present_and_deterministic_in_prompt_builder_records(self):
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        module = load_prompt_module()
        spec = module.sample_spec("female", 1, seed=123, id_width=3)
        first = module.build_asset_records(spec)
        second = module.build_asset_records(spec)

        self.assertEqual([row["promptHash"] for row in first], [row["promptHash"] for row in second])
        self.assertTrue(all(row["promptHash"] for row in first))
        self.assertTrue(all(row.get("promptTargetingVersion") == module.PROMPT_TARGETING_VERSION for row in first))


if __name__ == "__main__":
    unittest.main()
