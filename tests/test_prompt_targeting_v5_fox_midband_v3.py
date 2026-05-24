import importlib.util
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"
EXPECTED_VERSION = "face_type_looks_level_targeting_v8"
OLD_VERSION = "face_type_looks_level_targeting_v7"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v5_fox_midband", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PromptTargetingV5FoxMidbandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _spec(self, *, gender="male", numeric_id=11, face_type="fox_like", band="2.5-3.2", level=3.0, location_type=None):
        spec = deepcopy(self.m.sample_spec(gender, numeric_id, seed=20260521 + numeric_id))
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = level
        if location_type:
            spec["location"] = deepcopy(self.m.LOCATION_CATALOG[location_type])
            spec["location"]["locationType"] = location_type
            spec["vibeActivity"] = self.m.LOCATION_VIBE_ACTIVITIES[location_type][0]
        return self.m.normalize_spec_defaults(spec)

    def _positive(self, prompt: str) -> str:
        return self.m.split_positive_and_negative_prompt(prompt)[0].lower()

    def test_prompt_targeting_version_is_v5(self):
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, EXPECTED_VERSION)
        spec = self._spec()
        assets = self.m.build_asset_records(spec)
        self.assertEqual({a["promptTargetingVersion"] for a in assets}, {EXPECTED_VERSION})
        self.assertEqual({a["metadata"]["promptTargetingVersion"] for a in assets}, {EXPECTED_VERSION})
        self.assertTrue(all(f"Prompt targeting version: {EXPECTED_VERSION}." in a["prompt"] for a in assets))

    def test_prompt_hash_changes_from_v4_to_v5(self):
        spec = self._spec()
        current = self.m.build_asset_record(spec, "face_card")
        with mock.patch.object(self.m, "PROMPT_TARGETING_VERSION", OLD_VERSION):
            old = self.m.build_asset_record(spec, "face_card")
        self.assertNotEqual(current["promptHash"], old["promptHash"])

    def test_fox_like_face_card_includes_anti_dog_guard_and_restrained_cues(self):
        positive = self._positive(self.m.build_prompt(self._spec(), "face_card"))
        for phrase in (
            "less round friendly softness than dog_like",
            "calm composed expression rather than openly puppyish warmth",
            "avoid dog_like warm puppy impression",
            "avoid round friendly puppy-like eyes",
            "avoid overly soft cheeks and bubbly approachability",
            "avoid cute dog-like warmth",
            "fox_like should not be interpreted as dog_like",
            "do not soften into a rounded puppy-like friendly look",
            "subtle composed fox-like impression",
            "restrained facial angularity",
        ):
            self.assertIn(phrase, positive)

    def test_fox_like_face_card_positive_section_passes_banned_scanner(self):
        prompt = self.m.build_prompt(self._spec(), "face_card")
        self.assertEqual(self.m.scan_prompt_for_banned_terms(prompt), [])
        self.m.validate_no_banned_positive_terms(prompt)

    def test_mid_band_face_card_has_below_high_band_and_no_upgrade_guards(self):
        positive = self._positive(self.m.build_prompt(self._spec(), "face_card"))
        for phrase in (
            "not attractive enough for 3.3-3.8",
            "ordinary facial proportions",
            "no refined jawline",
            "no noticeably sharp nose bridge",
            "no enlarged bright eyes",
            "no glossy smooth skin",
            "small natural asymmetry and everyday skin texture",
            "if target lookslevelband is 2.5-3.2, do not let observed appearance enter 3.3-3.8",
            "neat styling must not raise facial attractiveness",
            "ordinary smartphone-like profile framing",
            "soft plain lighting without studio-beauty effect",
            "no beauty-filter glow",
            "no commercial headshot style",
        ):
            self.assertIn(phrase, positive)

    def test_combined_guard_only_for_fox_like_25_to_32(self):
        fox_mid = self._positive(self.m.build_prompt(self._spec(face_type="fox_like", band="2.5-3.2", level=3.0), "face_card"))
        dog_mid = self._positive(self.m.build_prompt(self._spec(face_type="dog_like", band="2.5-3.2", level=3.0), "face_card"))
        fox_high = self._positive(self.m.build_prompt(self._spec(face_type="fox_like", band="3.3-3.8", level=3.5), "face_card"))
        marker = "target-specific face_card guard: keep the fox_like impression subtle and composed, but ordinary"
        self.assertIn(marker, fox_mid)
        self.assertNotIn(marker, dog_mid)
        self.assertNotIn(marker, fox_high)
        self.assertNotIn("fox_like should not be interpreted as dog_like", dog_mid)

    def test_silhouette_keeps_identity_readability_and_not_full_fox_block(self):
        positive = self._positive(self.m.build_prompt(self._spec(), "silhouette_card"))
        for phrase in (
            "face clearly visible and identity-readable",
            "front-facing or mild three-quarter face angle",
            "face large enough to recognize the same person from the face_card",
            "body proportions remain readable",
            "avoid tiny face",
            "avoid back view",
        ):
            self.assertIn(phrase, positive)
        self.assertIn("same broad fox_like impression", positive)
        self.assertNotIn("avoid dog_like warm puppy impression", positive)

    def test_vibe_location_activity_safety_still_passes(self):
        spec = self._spec(gender="female", numeric_id=12, location_type="flower_viewing_path")
        prompt = self.m.build_prompt(spec, "vibe_card")
        positive, negative = self.m.split_positive_and_negative_prompt(prompt)
        self.assertIn(spec["vibeActivity"], positive)
        self.assertIn(self.m.LOCATION_CATALOG["flower_viewing_path"]["scene"], positive)
        self.assertIn("Preserve the same person from the face_card reference", prompt)
        self.assertIn("Do not beautify beyond the target looksLevelBand", prompt)
        self.assertEqual(self.m.scan_prompt_for_banned_terms(prompt), [])
        self.assertIn("influencer photoshoot", negative.lower())

    def test_exact_distributions_unchanged(self):
        specs = self.m.generate_specs(female_count=120, male_count=120, seed=20260512)
        audit = self.m.audit_prompt_distribution(specs)
        self.assertTrue(audit["passed"], audit["mismatches"])
        self.assertEqual(audit["counts"]["faceType"], self.m.FACE_TYPE_TARGETS["global"])
        self.assertEqual(audit["counts"]["looksLevelBand"], self.m.LOOKS_LEVEL_BAND_TARGETS["global"])
        self.assertEqual(audit["counts"]["eyewear"], {"with_eyewear": 36, "without_eyewear": 204})
        self.assertEqual(audit["counts"]["season"], self.m.SEASON_TARGETS)

    def test_export_metadata_includes_prompt_targeting_version_and_hash(self):
        assets = self.m.build_asset_records(self._spec(gender="female", numeric_id=13))
        for asset in assets:
            self.assertEqual(asset["promptTargetingVersion"], EXPECTED_VERSION)
            self.assertEqual(asset["metadata"]["promptTargetingVersion"], EXPECTED_VERSION)
            self.assertIn("promptHash", asset)
            self.assertTrue(asset["promptHash"])


if __name__ == "__main__":
    unittest.main()
