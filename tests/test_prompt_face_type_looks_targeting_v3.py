import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v3", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PromptFaceTypeLooksTargetingV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _spec(self, face_type="bear_like", looks_level=2.8, band="2.5-3.2"):
        spec = self.m.sample_spec("female", 1, seed=123)
        spec = deepcopy(spec)
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevel"] = looks_level
        spec["face"]["looksLevelBand"] = band
        return self.m.normalize_spec_defaults(spec)

    def test_every_canonical_face_type_has_visual_target_block(self):
        for face_type in self.m.FACE_TYPE_ORDER:
            with self.subTest(face_type=face_type):
                block = self.m.face_type_target_visual(face_type)
                self.assertIsInstance(block, str)
                self.assertGreater(len(block), 60)

    def test_neutral_mixed_alias_normalizes_to_mixed_neutral(self):
        self.assertEqual(self.m._canonical_face_type("neutral_mixed"), "mixed_neutral")
        spec = self._spec("neutral_mixed")
        self.assertEqual(spec["face"]["faceType"], "mixed_neutral")

    def test_face_card_prompt_includes_geometry_not_only_label(self):
        spec = self._spec("bear_like")
        prompt = self.m.build_prompt(spec, "face_card")
        self.assertIn("Target faceType bear_like", prompt)
        self.assertIn("broader warm facial structure", prompt)
        self.assertIn("thicker natural brows", prompt)
        self.assertGreater(prompt.count("bear_like"), 0)

    def test_face_type_blocks_keep_distinctive_cues(self):
        checks = {
            "bear_like": ("broader warm facial structure", "avoid delicate deer-like"),
            "fox_like": ("subtle composed fox-like impression", "slightly alert but ordinary campus face"),
            "deer_like": ("soft oval face", "medium-large calm eyes"),
            "hamster_like": ("compact rounded adult face", "not baby-faced"),
            "dog_like": ("warm approachable expression", "without puppy-like exaggeration"),
            "horse_like": ("longer mature face proportion", "not caricatured"),
            "mixed_neutral": ("balanced everyday facial proportions", "no single face-type cue dominates"),
            "cat_like": ("almond-shaped eyes", "slightly lifted outer corners"),
        }
        for face_type, phrases in checks.items():
            block = self.m.face_type_target_visual(face_type)
            with self.subTest(face_type=face_type):
                for phrase in phrases:
                    self.assertIn(phrase, block)

    def test_every_looks_level_band_has_visual_target_block(self):
        for band in self.m.LOOKS_LEVEL_BANDS:
            with self.subTest(band=band):
                block = self.m.looks_level_band_target_visual(band)
                self.assertIsInstance(block, str)
                self.assertGreater(len(block), 25)
        self.assertIn("forbidden", self.m.looks_level_band_target_visual("4.4-5.0"))

    def test_lower_looks_bands_do_not_push_polished_archetypes(self):
        lower = self.m.looks_level_band_target_visual("1.5-2.4").lower()
        mid = self.m.looks_level_band_target_visual("2.5-3.2").lower()
        self.assertIn("ordinary natural real student", lower)
        self.assertIn("do not improve", lower)
        self.assertIn("ordinary student realism", mid)
        self.assertIn("keep facial attractiveness clearly below 3.3-3.8", mid)

    def test_prompts_include_anti_beautification_language(self):
        spec = self._spec("fox_like", 3.6, "3.3-3.8")
        for shot_type in self.m.SHOT_TYPES:
            with self.subTest(shot_type=shot_type):
                prompt = self.m.build_prompt(spec, shot_type)
                self.assertIn("do not beautify beyond the target band", prompt)
                self.m.validate_no_banned_positive_terms(prompt)

    def test_shot_specific_targeting_integration(self):
        spec = self._spec("bear_like", 2.8, "2.5-3.2")
        face = self.m.build_prompt(spec, "face_card")
        silhouette = self.m.build_prompt(spec, "silhouette_card")
        vibe = self.m.build_prompt(spec, "vibe_card")

        self.assertIn("Target faceType bear_like", face)
        self.assertIn("Target looksLevelBand 2.5-3.2", face)
        self.assertIn("three-quarter body or full-body photo", silhouette)
        self.assertIn("without turning the full-body shot into a close portrait", silhouette)
        self.assertIn("Target looksLevelBand 2.5-3.2", silhouette)
        self.assertIn("same broad face-type impression", vibe)
        self.assertIn("no beauty upgrade across shots", vibe)

    def test_prompt_hash_changes_when_targeting_version_changes(self):
        spec = self._spec("bear_like", 2.8, "2.5-3.2")
        baseline = self.m.build_asset_record(spec, "face_card")
        with mock.patch.object(self.m, "PROMPT_TARGETING_VERSION", "face_type_looks_level_targeting_test_version"):
            changed = self.m.build_asset_record(spec, "face_card")
        self.assertNotEqual(baseline["promptHash"], changed["promptHash"])
        self.assertEqual(changed["promptTargetingVersion"], "face_type_looks_level_targeting_test_version")

    def test_asset_record_and_sample_include_prompt_targeting_version(self):
        spec = self._spec("deer_like", 3.4, "3.3-3.8")
        asset = self.m.build_asset_record(spec, "face_card")
        self.assertEqual(asset["promptTargetingVersion"], self.m.PROMPT_TARGETING_VERSION)
        self.assertIn("promptHash", asset)
        self.assertEqual(spec["promptTargetingVersion"], self.m.PROMPT_TARGETING_VERSION)
        self.assertEqual(asset["metadata"]["promptTargetingVersion"], self.m.PROMPT_TARGETING_VERSION)

    def test_prompt_safety_scanner_still_passes_sample_batch(self):
        specs = self.m.generate_specs(female_count=3, male_count=3, seed=20260514)
        for spec in specs:
            for shot_type in self.m.SHOT_TYPES:
                with self.subTest(profile=spec["profileId"], shot_type=shot_type):
                    prompt = self.m.build_prompt(spec, shot_type)
                    self.m.validate_no_banned_positive_terms(prompt)


if __name__ == "__main__":
    unittest.main()
