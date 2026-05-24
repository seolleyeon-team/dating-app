import importlib.util
import json
import random
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v3", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class VibeLocationActivityMappingV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _spec_for_location(self, location_type: str):
        spec = self.m.sample_spec("female", 1, seed=123)
        spec["location"] = deepcopy(self.m.LOCATION_CATALOG[location_type])
        spec["location"]["locationType"] = location_type
        spec["vibeActivity"] = self.m.sample_vibe_activity_for_location(location_type, "female", random.Random(909))
        return self.m.normalize_spec_defaults(spec)

    def _positive_vibe_prompt(self, location_type: str) -> str:
        prompt = self.m.build_prompt(self._spec_for_location(location_type), "vibe_card")
        positive, _ = self.m.split_positive_and_negative_prompt(prompt)
        return positive.lower()

    def _split_vibe_prompt(self, location_type: str):
        prompt = self.m.build_prompt(self._spec_for_location(location_type), "vibe_card")
        positive, negative = self.m.split_positive_and_negative_prompt(prompt)
        return positive.lower(), negative.lower()

    def test_all_vibe_locations_have_activity_mapping(self):
        missing = []
        for location_type, entry in self.m.LOCATION_CATALOG.items():
            if "vibe_card" not in entry.get("allowedShots", []):
                continue
            if len(self.m.LOCATION_VIBE_ACTIVITIES.get(location_type, [])) < 3:
                missing.append(location_type)
        self.assertEqual(missing, [])

    def test_new_locations_exist(self):
        expected = {
            "seaside_walk",
            "safe_mirror_snapshot",
            "forest_bench",
            "casual_restaurant_table",
            "amusement_park_daytime",
            "travel_destination_casual",
            "flower_viewing_path",
        }
        self.assertLessEqual(expected, set(self.m.LOCATION_CATALOG))
        self.assertLessEqual(expected, set(self.m.LOCATION_VIBE_ACTIVITIES))

    def test_sample_vibe_activity_for_location_is_deterministic(self):
        first = self.m.sample_vibe_activity_for_location("seaside_walk", "female", random.Random(77))
        second = self.m.sample_vibe_activity_for_location("seaside_walk", "female", random.Random(77))
        self.assertEqual(first, second)
        self.assertIn(first, self.m.LOCATION_VIBE_ACTIVITIES["seaside_walk"])

    def test_vibe_prompt_uses_activity_from_selected_location(self):
        spec = self._spec_for_location("forest_bench")
        prompt = self.m.build_prompt(spec, "vibe_card")
        self.assertIn(spec["vibeActivity"], prompt)
        self.assertIn(self.m.LOCATION_CATALOG["forest_bench"]["scene"], prompt)

    def test_vibe_prompt_resamples_mismatched_activity(self):
        spec = self._spec_for_location("seaside_walk")
        spec["vibeActivity"] = self.m.LOCATION_VIBE_ACTIVITIES["campus_cafe"][0]
        normalized = self.m.normalize_spec_defaults(spec)
        self.assertIn(normalized["vibeActivity"], self.m.LOCATION_VIBE_ACTIVITIES["seaside_walk"])
        self.assertNotEqual(normalized["vibeActivity"], self.m.LOCATION_VIBE_ACTIVITIES["campus_cafe"][0])

    def test_new_location_prompts_pass_positive_safety_scanner(self):
        for location_type in (
            "seaside_walk",
            "safe_mirror_snapshot",
            "forest_bench",
            "casual_restaurant_table",
            "amusement_park_daytime",
            "travel_destination_casual",
            "flower_viewing_path",
        ):
            with self.subTest(location=location_type):
                self.m.validate_no_banned_positive_terms(self.m.build_prompt(self._spec_for_location(location_type), "vibe_card"))

    def test_new_location_prompts_avoid_unsafe_positive_terms(self):
        checks = {
            "safe_mirror_snapshot": (
                "bathroom",
                "gym",
                "bedroom",
                "bathroom mirror",
                "gym mirror",
                "bedroom mirror",
                "private intimate room",
                "locker room",
            ),
            "seaside_walk": ("swimsuit", "bikini", "pool", "beach party", "revealing", "body-focused"),
            "casual_restaurant_table": ("alcohol", "bar", "readable menu", "brand logo", "pub", "nightclub"),
            "amusement_park_daytime": (
                "logo",
                "influencer pose",
                "children",
                "mascot",
                "readable sign",
                "crowd-focused",
            ),
            "travel_destination_casual": (
                "famous landmark",
                "flag",
                "national symbol",
                "readable sign",
                "luxury hotel",
                "times square",
                "eiffel tower",
                "big ben",
                "tokyo tower",
                "tourist influencer",
            ),
            "flower_viewing_path": ("influencer photoshoot", "wedding staging"),
            "forest_bench": ("dark isolated forest", "horror", "fantasy forest", "hidden face", "hidden body"),
        }
        for location_type, forbidden_terms in checks.items():
            positive = self._positive_vibe_prompt(location_type)
            with self.subTest(location=location_type):
                for term in forbidden_terms:
                    self.assertNotIn(term, positive)

    def test_medium_risk_locations_move_safety_text_to_negative_section(self):
        for location_type, entry in self.m.LOCATION_CATALOG.items():
            if "vibe_card" not in entry.get("allowedShots", []):
                continue
            if entry.get("privacyRisk") != "medium" and entry.get("logoTextRisk") != "medium":
                continue
            positive, negative = self._split_vibe_prompt(location_type)
            with self.subTest(location=location_type):
                self.assertNotIn("no visible logo", positive)
                self.assertNotIn("no readable text", positive)
                self.assertNotIn("no identifiable location", positive)
                self.assertIn("visible logo", negative)
                self.assertIn("readable text", negative)
                self.assertIn("identifiable location", negative)

    def test_banned_terms_fail_in_positive_but_are_allowed_in_negative_section(self):
        positive_failures = (
            "A student wearing a swimsuit beside the sea.",
            "A student taking a bathroom mirror outfit photo.",
            "A student standing beside a brand logo.",
            "A student making an influencer pose.",
        )
        for prompt in positive_failures:
            with self.subTest(prompt=prompt):
                with self.assertRaises(ValueError):
                    self.m.validate_no_banned_positive_terms(prompt)

        negative_allowed = (
            "A student on a quiet campus path.\n\nAvoid: swimsuit.",
            "A student in a clean neutral interior.\n\nAvoid: bathroom mirror.",
            "A student beside a simple wall.\n\nAvoid: brand logo.",
            "A student in an ordinary profile pose.\n\nAvoid: influencer pose.",
        )
        for prompt in negative_allowed:
            with self.subTest(prompt=prompt):
                self.assertEqual(self.m.scan_prompt_for_banned_terms(prompt), [])
                self.m.validate_no_banned_positive_terms(prompt)

    def test_existing_api_and_export_metadata_still_work(self):
        spec = self._spec_for_location("flower_viewing_path")
        assets = self.m.build_asset_records(spec)
        self.assertEqual({asset["promptTargetingVersion"] for asset in assets}, {self.m.PROMPT_TARGETING_VERSION})
        self.assertEqual({asset["locationType"] for asset in assets}, {"flower_viewing_path"})
        self.assertEqual(assets[0]["metadata"]["vibeActivity"], spec["vibeActivity"])
        context = self.m.make_rec_event_context(assets[-1])
        self.assertEqual(context["assetId"], assets[-1]["assetId"])
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.m.export_batch([spec], Path(tmp))
            rows = [
                json.loads(line)
                for line in Path(paths["assetsJsonl"]).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        self.assertEqual({row["metadata"]["vibeActivity"] for row in rows}, {spec["vibeActivity"]})

    def test_prompt_hash_changes_when_vibe_activity_or_location_changes(self):
        spec = self._spec_for_location("seaside_walk")
        first = deepcopy(spec)
        second = deepcopy(spec)
        second["vibeActivity"] = self.m.LOCATION_VIBE_ACTIVITIES["seaside_walk"][1]
        self.assertNotEqual(
            self.m.build_asset_record(first, "vibe_card")["promptHash"],
            self.m.build_asset_record(second, "vibe_card")["promptHash"],
        )

        forest = self._spec_for_location("forest_bench")
        self.assertNotEqual(
            self.m.build_asset_record(first, "vibe_card")["promptHash"],
            self.m.build_asset_record(forest, "vibe_card")["promptHash"],
        )


if __name__ == "__main__":
    unittest.main()
