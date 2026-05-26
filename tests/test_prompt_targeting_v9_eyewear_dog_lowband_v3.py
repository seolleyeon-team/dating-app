import importlib.util
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


class PromptTargetingV9EyewearDogLowBandV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _base_spec(self, *, face_type="dog_like", band="2.5-3.2", has_eyewear=False):
        specs = self.m.generate_specs(female_count=8, male_count=24, seed=20260522)
        spec = deepcopy(next(s for s in specs if s["gender"] == "male"))
        spec["profileId"] = "male_901"
        spec["numericId"] = 901
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = 2.0 if band == "1.5-2.4" else 2.9
        spec["accessories"]["hasEyewear"] = bool(has_eyewear)
        if has_eyewear:
            spec["accessories"]["eyewearGroup"] = "glasses"
            spec["accessories"]["eyewear"] = "clear_frame"
            spec["accessories"]["canonicalEyewear"] = "clear_frame"
        else:
            spec["accessories"]["eyewearGroup"] = "none"
            spec["accessories"]["eyewear"] = "none"
            spec["accessories"]["canonicalEyewear"] = "none"
        return self.m.normalize_spec_defaults(spec)

    def test_prompt_targeting_version_bumped_to_v9_and_hash_changes_from_v8(self):
        spec = self._base_spec(has_eyewear=True)
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, "face_type_looks_level_targeting_v23")
        baseline = self.m.build_asset_record(spec, "vibe_card")
        original = self.m.PROMPT_TARGETING_VERSION
        try:
            self.m.PROMPT_TARGETING_VERSION = "face_type_looks_level_targeting_v8"
            old = self.m.build_asset_record(spec, "vibe_card")
        finally:
            self.m.PROMPT_TARGETING_VERSION = original
        self.assertNotEqual(baseline["promptHash"], old["promptHash"])

    def test_eyewear_identity_silhouette_and_vibe_repeat_exact_canonical_eyewear(self):
        spec = self._base_spec(face_type="horse_like", band="3.3-3.8", has_eyewear=True)
        for shot in ("silhouette_card", "vibe_card"):
            prompt = self.m.build_prompt(spec, shot).lower()
            self.assertIn("wearing the same clear-frame glasses from the face_card", prompt)
            self.assertIn("frames visible enough to verify identity consistency", prompt)
            self.assertIn("do not remove glasses in this shot", prompt)
            self.assertIn("face and eyewear remain readable", prompt)
        self.assertIn("do not let full-body framing make glasses unreadable", self.m.build_prompt(spec, "silhouette_card").lower())
        self.assertIn("location or activity must not remove eyewear", self.m.build_prompt(spec, "vibe_card").lower())

    def test_no_eyewear_prompts_still_do_not_add_glasses_in_positive_prompt(self):
        spec = self._base_spec(face_type="mixed_neutral", band="2.5-3.2", has_eyewear=False)
        for shot in self.m.SHOT_TYPES:
            prompt = self.m.build_prompt(spec, shot)
            positive, negative = self.m.split_positive_and_negative_prompt(prompt)
            self.assertNotIn("glasses", positive.lower())
            self.assertIn("glasses", negative.lower())
            self.m.validate_no_banned_positive_terms(prompt)

    def test_dog_like_1_5_to_2_4_prompt_says_friendly_does_not_mean_attractive_cute_or_handsome(self):
        spec = self._base_spec(face_type="dog_like", band="1.5-2.4")
        prompt = self.m.build_prompt(spec, "face_card").lower()
        self.assertIn("friendly does not mean cute or handsome", prompt)
        self.assertIn("friendly does not mean higher attractiveness", prompt)
        self.assertIn("avoid polished warmth", prompt)
        self.assertIn("avoid bright attractive smile", prompt)

    def test_dog_like_2_5_to_3_2_prompt_says_warmth_must_not_raise_band_to_3_3_to_3_8(self):
        spec = self._base_spec(face_type="dog_like", band="2.5-3.2")
        prompt = self.m.build_prompt(spec, "face_card").lower()
        self.assertIn("warmth must not raise lookslevelband into 3.3-3.8", prompt)
        self.assertIn("average or mildly pleasant only", prompt)
        self.assertIn("friendly warmth must stay ordinary", prompt)

    def test_vibe_same_person_lock_remains(self):
        spec = self._base_spec(face_type="dog_like", band="2.5-3.2")
        prompt = self.m.build_prompt(spec, "vibe_card")
        self.assertIn("canonical face_card same-person lock", prompt)
        self.assertIn("environmental context is secondary to identity", prompt)

    def test_fox_like_midband_guard_remains(self):
        spec = self._base_spec(face_type="fox_like", band="2.5-3.2")
        face_prompt = self.m.build_prompt(spec, "face_card")
        vibe_prompt = self.m.build_prompt(spec, "vibe_card")
        self.assertIn("Target-specific face_card guard", face_prompt)
        self.assertIn("Combined fox_like 2.5-3.2 guard", vibe_prompt)
        self.assertIn("do not let camera, lighting, styling, or pose raise it into 3.3-3.8", face_prompt)

    def test_exact_distributions_unchanged(self):
        specs = self.m.generate_specs(female_count=120, male_count=120, seed=20260512)
        self.assertEqual(sum(s["face"]["faceType"] == "dog_like" for s in specs), 38)
        self.assertEqual(sum(s["face"]["looksLevelBand"] == "1.5-2.4" for s in specs), 36)
        self.assertEqual(sum(s["face"]["looksLevelBand"] == "2.5-3.2" for s in specs), 108)
        self.assertEqual(sum(s["face"]["looksLevelBand"] == "3.3-3.8" for s in specs), 72)
        self.assertEqual(sum(s["face"]["looksLevelBand"] == "3.9-4.3" for s in specs), 24)
        self.assertEqual(sum(s["face"]["looksLevelBand"] == "4.4-5.0" for s in specs), 0)


if __name__ == "__main__":
    unittest.main()
