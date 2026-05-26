import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v3_under_test_v10", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PromptTargetingV10Controlled18RegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _base_spec(self, *, face_type="dog_like", band="1.5-2.4", has_eyewear=True):
        level = {"1.5-2.4": 2.0, "2.5-3.2": 2.9, "3.3-3.8": 3.5, "3.9-4.3": 4.0}[band]
        specs = self.m.generate_specs(female_count=8, male_count=24, seed=20260522)
        spec = deepcopy(next(s for s in specs if s["gender"] == "male"))
        spec["profileId"] = "male_901"
        spec["numericId"] = 901
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = level
        spec["accessories"]["hasEyewear"] = bool(has_eyewear)
        if has_eyewear:
            spec["accessories"]["eyewearGroup"] = "glasses"
            spec["accessories"]["eyewear"] = "thin_round_metal"
            spec["accessories"]["canonicalEyewear"] = "thin_round_metal"
        else:
            spec["accessories"]["eyewearGroup"] = "none"
            spec["accessories"]["eyewear"] = "none"
            spec["accessories"]["canonicalEyewear"] = "none"
        return spec

    def test_prompt_targeting_version_is_v11(self):
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, "face_type_looks_level_targeting_v23")

    def test_dog_like_low_band_dependent_shots_get_extra_lock(self):
        spec = self._base_spec(face_type="dog_like", band="1.5-2.4", has_eyewear=True)
        face_prompt = self.m.build_prompt(spec, "face_card")
        silhouette_prompt = self.m.build_prompt(spec, "silhouette_card")
        vibe_prompt = self.m.build_prompt(spec, "vibe_card")
        self.assertIn("Combined dog_like 1.5-2.4 guard", face_prompt)
        self.assertNotIn("Dependent-shot dog_like 1.5-2.4 lock", face_prompt)
        for prompt in (silhouette_prompt, vibe_prompt):
            self.assertIn("Dependent-shot dog_like 1.5-2.4 lock", prompt)
            self.assertIn("do not let outfit, posture, outdoor lighting, glasses, or friendly action upgrade", prompt)
            self.assertIn("match the face_card's plain low-band ordinariness exactly", prompt)
            self.assertIn("wearing the same thin round metal-frame glasses from the face_card", prompt)
            self.assertIn("do not remove glasses in this shot", prompt)

    def test_mixed_neutral_33_38_guard_prevents_undershoot(self):
        spec = self._base_spec(face_type="mixed_neutral", band="3.3-3.8", has_eyewear=False)
        prompt = self.m.build_prompt(spec, "face_card")
        self.assertIn("Mixed_neutral 3.3-3.8 guard", prompt)
        self.assertIn("do not undershoot into 2.5-3.2 ordinary/plain", prompt)
        self.assertIn("above-average but sincere student realism", prompt)
        self.assertIn("avoid celebrity, influencer, model, luxury", prompt)


if __name__ == "__main__":
    unittest.main()
