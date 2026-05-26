import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v3_under_test_v11", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PromptTargetingV11SilhouetteRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _base_spec(self, *, face_type="hamster_like", band="2.5-3.2", has_eyewear=True):
        level = {"1.5-2.4": 2.0, "2.5-3.2": 2.9, "3.3-3.8": 3.5, "3.9-4.3": 4.0}[band]
        specs = self.m.generate_specs(female_count=8, male_count=24, seed=20260522)
        spec = deepcopy(next(s for s in specs if s["gender"] == "male"))
        spec["profileId"] = "male_911"
        spec["numericId"] = 911
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = level
        spec["accessories"]["hasEyewear"] = bool(has_eyewear)
        if has_eyewear:
            spec["accessories"]["eyewearGroup"] = "glasses"
            spec["accessories"]["eyewear"] = "black_acetate"
            spec["accessories"]["canonicalEyewear"] = "black_acetate"
        else:
            spec["accessories"]["eyewearGroup"] = "none"
            spec["accessories"]["eyewear"] = "none"
            spec["accessories"]["canonicalEyewear"] = "none"
        return spec

    def test_prompt_targeting_version_is_v11(self):
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, "face_type_looks_level_targeting_v23")

    def test_silhouette_includes_face_type_target_and_v11_readability_lock(self):
        spec = self._base_spec(face_type="hamster_like", band="2.5-3.2", has_eyewear=True)
        prompt = self.m.build_prompt(spec, "silhouette_card")
        self.assertIn("Target faceType hamster_like", prompt)
        self.assertIn("v11 silhouette face readability lock", prompt)
        self.assertIn("Dependent-shot hamster_like 2.5-3.2 identity lock", prompt)
        self.assertIn("avoid fox_like narrowness", prompt)
        self.assertIn("do not raise the dependent shot into 3.3-3.8", prompt)
        self.assertIn("wearing the same simple black acetate-frame glasses from the face_card", prompt)

    def test_deer_like_silhouette_gets_readability_guard(self):
        spec = self._base_spec(face_type="deer_like", band="3.3-3.8", has_eyewear=False)
        prompt = self.m.build_prompt(spec, "silhouette_card")
        self.assertIn("Silhouette deer_like 3.3-3.8 readability lock", prompt)
        self.assertIn("do not flatten into mixed_neutral", prompt)
        self.assertIn("deer_like lock: preserve soft oval face", prompt)

    def test_cat_like_high_band_face_card_gets_undershoot_guard(self):
        spec = self._base_spec(face_type="cat_like", band="3.9-4.3", has_eyewear=False)
        prompt = self.m.build_prompt(spec, "face_card")
        self.assertIn("face_card high-band cat_like guard", prompt)
        self.assertIn("does not soften into deer_like", prompt)
        self.assertIn("keep it in 3.9-4.3", prompt)
        self.assertIn("avoid influencer, celebrity, model", prompt)


if __name__ == "__main__":
    unittest.main()
