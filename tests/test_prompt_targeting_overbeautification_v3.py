import importlib.util
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v3_overbeautification", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PromptTargetingOverbeautificationV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _spec(self, *, gender="female", face_type="cat_like", band="1.5-2.4", level=None, location_type=None):
        level_by_band = {"1.5-2.4": 1.9, "2.5-3.2": 2.8, "3.3-3.8": 3.5, "3.9-4.3": 4.1}
        spec = deepcopy(self.m.sample_spec(gender, 1 if gender == "female" else 2, seed=20260601))
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = level if level is not None else level_by_band[band]
        if location_type:
            spec["location"] = deepcopy(self.m.LOCATION_CATALOG[location_type])
            spec["location"]["locationType"] = location_type
            spec["vibeActivity"] = self.m.LOCATION_VIBE_ACTIVITIES[location_type][0]
        return self.m.normalize_spec_defaults(spec)

    def _positive(self, prompt: str) -> str:
        return self.m.split_positive_and_negative_prompt(prompt)[0].lower()

    def test_prompt_targeting_version_is_current(self):
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, "face_type_looks_level_targeting_v5")
        spec = self._spec()
        asset = self.m.build_asset_record(spec, "face_card")
        self.assertEqual(asset["promptTargetingVersion"], "face_type_looks_level_targeting_v5")
        self.assertEqual(asset["metadata"]["promptTargetingVersion"], "face_type_looks_level_targeting_v5")

    def test_prompt_hash_changes_when_targeting_version_changes(self):
        spec = self._spec(face_type="bear_like", band="2.5-3.2")
        current = self.m.build_asset_record(spec, "face_card")
        with mock.patch.object(self.m, "PROMPT_TARGETING_VERSION", "face_type_looks_level_targeting_v2"):
            old = self.m.build_asset_record(spec, "face_card")
        self.assertNotEqual(current["promptHash"], old["promptHash"])

    def test_face_card_low_band_contains_ordinary_anti_beautification_constraints(self):
        prompt = self.m.build_prompt(self._spec(face_type="cat_like", band="1.5-2.4"), "face_card")
        for phrase in (
            "very ordinary, plain, realistic everyday campus face",
            "natural asymmetry",
            "ordinary skin texture",
            "no refined jawline",
            "no large bright eyes",
            "preserve a sincere and kind impression without attractiveness upgrade",
            "match the assigned looksLevelBand exactly",
            "do not upgrade the face",
        ):
            self.assertIn(phrase, prompt)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_face_card_mid_band_contains_average_modest_non_polished_constraints(self):
        prompt = self.m.build_prompt(self._spec(face_type="dog_like", band="2.5-3.2"), "face_card")
        for phrase in (
            "average to mildly pleasant everyday appearance",
            "not highly styled",
            "no dramatic facial refinement",
            "ordinary student realism",
            "keep facial attractiveness clearly below 3.3-3.8",
        ):
            self.assertIn(phrase, prompt)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_face_card_33_38_contains_neat_but_not_model_like_constraints(self):
        prompt = self.m.build_prompt(self._spec(face_type="hamster_like", band="3.3-3.8"), "face_card")
        for phrase in (
            "neat and pleasant but still realistic",
            "mildly attractive but not model-like",
            "natural campus profile tone",
            "avoid over-sharpened jaw, perfect symmetry, heavy retouching",
        ):
            self.assertIn(phrase, prompt)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_face_card_39_43_contains_attractive_but_not_overlevel_constraints(self):
        prompt = self.m.build_prompt(self._spec(face_type="fox_like", band="3.9-4.3"), "face_card")
        for phrase in (
            "clearly attractive but still grounded and non-public-figure",
            "trust-based profile realism",
            "no 4.4-5.0 over-level public-figure look",
            "no commercial photoshoot",
            "no extreme beauty filter",
        ):
            self.assertIn(phrase, prompt)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_no_prompt_assigns_44_50_and_default_specs_count_zero(self):
        specs = self.m.generate_specs(female_count=120, male_count=120, seed=20260512)
        self.assertEqual(Counter(spec["face"]["looksLevelBand"] for spec in specs)["4.4-5.0"], 0)
        for spec in specs[:12]:
            for shot in self.m.SHOT_TYPES:
                prompt = self.m.build_prompt(spec, shot)
                positive = self._positive(prompt)
                self.assertNotIn("target lookslevelband 4.4-5.0", positive)
                self.m.validate_no_banned_positive_terms(prompt)

    def test_low_band_prompts_do_not_use_glamour_terms_as_positive_descriptors(self):
        prompt = self.m.build_prompt(self._spec(gender="male", face_type="fox_like", band="1.5-2.4"), "face_card")
        positive = self._positive(prompt)
        for forbidden in ("glamorous", "influencer profile", "model-like proportions", "glow-up"):
            self.assertNotIn(forbidden, positive)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_vibe_card_keeps_location_activity_logic_and_new_location_safety(self):
        spec = self._spec(face_type="mixed_neutral", band="2.5-3.2", location_type="flower_viewing_path")
        prompt = self.m.build_prompt(spec, "vibe_card")
        positive, negative = self.m.split_positive_and_negative_prompt(prompt)
        self.assertIn(spec["vibeActivity"], positive)
        self.assertIn(self.m.LOCATION_CATALOG["flower_viewing_path"]["scene"], positive)
        self.assertNotIn("influencer photoshoot", positive.lower())
        self.assertIn("influencer photoshoot", negative.lower())
        self.m.validate_no_banned_positive_terms(prompt)

    def test_face_type_blocks_include_distinction_safeguards(self):
        expected = {
            "cat_like": ("slightly sharper, neat, alert impression", "avoid turning into mixed_neutral", "avoid overly cute large-eye style"),
            "dog_like": ("warm, approachable, rounded friendly impression", "avoid deer_like long delicate face", "avoid bear_like heavy square fullness"),
            "hamster_like": ("soft cheeks, compact and gentle impression", "avoid babyface / childlike", "adult proportions"),
            "bear_like": ("grounded, soft-solid impression", "avoid deer_like delicate narrowness", "avoid dog_like overly puppyish cuteness"),
            "fox_like": ("subtle composed fox-like impression", "slightly alert but ordinary campus face", "fox_like should remain within the assigned looksLevelBand"),
            "deer_like": ("gentle, calm, softer delicate impression", "not automatically more attractive", "avoid taking over other faceTypes"),
            "horse_like": ("longer facial impression, mature and calm", "avoid caricature", "adult grounded proportions"),
            "mixed_neutral": ("balanced ordinary mixed impression", "no strong animal-type cue", "avoid drifting to deer_like attractiveness"),
        }
        for face_type, phrases in expected.items():
            block = self.m.face_type_target_visual(face_type)
            with self.subTest(face_type=face_type):
                for phrase in phrases:
                    self.assertIn(phrase, block)

    def test_deer_like_and_mixed_neutral_do_not_imply_higher_looks_level(self):
        deer = self.m.face_type_target_visual("deer_like").lower()
        mixed = self.m.face_type_target_visual("mixed_neutral").lower()
        self.assertIn("not automatically more attractive", deer)
        self.assertIn("avoid taking over other facetypes", deer)
        self.assertIn("avoid drifting to deer_like attractiveness", mixed)
        self.assertNotIn("more beautiful", deer)
        self.assertNotIn("more beautiful", mixed)

    def test_silhouette_and_vibe_include_no_beauty_upgrade_reminders(self):
        spec = self._spec(face_type="bear_like", band="2.5-3.2")
        silhouette = self.m.build_prompt(spec, "silhouette_card")
        vibe = self.m.build_prompt(spec, "vibe_card")
        for prompt in (silhouette, vibe):
            self.assertIn("do not change looksLevelBand upward", prompt)
            self.assertIn("no body or face beauty upgrade", prompt)
            self.m.validate_no_banned_positive_terms(prompt)

    def test_distribution_regressions_remain_unchanged(self):
        specs = self.m.generate_specs(female_count=120, male_count=120, seed=20260512)
        audit = self.m.audit_prompt_distribution(specs)
        self.assertTrue(audit["passed"], audit["mismatches"])
        self.assertEqual(audit["counts"]["faceType"], self.m.FACE_TYPE_TARGETS["global"])
        self.assertEqual(audit["counts"]["looksLevelBand"], self.m.LOOKS_LEVEL_BAND_TARGETS["global"])
        self.assertEqual(audit["counts"]["eyewear"], {"with_eyewear": 36, "without_eyewear": 204})
        self.assertEqual(audit["counts"]["season"], self.m.SEASON_TARGETS)

    def test_export_metadata_still_includes_targeting_hash_band_and_face_type(self):
        spec = self._spec(face_type="mixed_neutral", band="2.5-3.2")
        assets = self.m.build_asset_records(spec)
        self.assertEqual(len(assets), 3)
        for asset in assets:
            self.assertEqual(asset["promptTargetingVersion"], "face_type_looks_level_targeting_v5")
            self.assertTrue(asset["promptHash"])
            self.assertEqual(asset["looksLevelBand"], "2.5-3.2")
            self.assertEqual(asset["faceType"], "mixed_neutral")
            self.assertIn("promptTargetingVersion", asset["metadata"])


if __name__ == "__main__":
    unittest.main()
