import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v3_v24", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PromptTargetingV24ProductQaRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _spec(self, *, gender="male", face_type="fox_like", band="1.5-2.4"):
        specs = self.m.generate_specs(female_count=4, male_count=8, seed=20260525)
        spec = deepcopy(next(s for s in specs if s["gender"] == gender))
        spec["profileId"] = f"{gender}_930"
        spec["numericId"] = 930
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = {
            "1.5-2.4": 2.0,
            "2.5-3.2": 2.9,
            "3.3-3.8": 3.5,
            "3.9-4.3": 4.0,
        }[band]
        spec["accessories"]["hasEyewear"] = False
        spec["accessories"]["eyewearGroup"] = "none"
        spec["accessories"]["eyewear"] = "none"
        spec["accessories"]["canonicalEyewear"] = "none"
        return self.m.normalize_spec_defaults(spec)

    def test_version_is_v24(self):
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, "face_type_looks_level_targeting_v24")

    def test_male_fox_like_lowband_all_shots_block_average_upgrade(self):
        spec = self._spec(gender="male", face_type="fox_like", band="1.5-2.4")
        for shot in ("face_card", "silhouette_card", "vibe_card"):
            prompt = self.m.build_prompt(spec, shot).lower()
            self.assertIn("v24 male fox_like 1.5-2.4 all-shot no-upgrade lock", prompt)
            self.assertIn("qa must not upgrade observedlookslevelband into 2.5-3.2 or 3.3-3.8", prompt)
            self.assertIn("avoid handsome narrow-eye polish", prompt)
        for shot in ("silhouette_card", "vibe_card"):
            prompt = self.m.build_prompt(spec, shot).lower()
            self.assertIn("v24 male fox_like low-band dependent-shot lock", prompt)
            self.assertIn("dependent shots must match the face_card's plain 1.5-2.4 ordinariness exactly", prompt)

    def test_horse_like_midband_all_shots_block_3_3_upgrade(self):
        spec = self._spec(gender="male", face_type="horse_like", band="2.5-3.2")
        for shot in ("face_card", "silhouette_card", "vibe_card"):
            prompt = self.m.build_prompt(spec, shot).lower()
            self.assertIn("v24 horse_like 2.5-3.2 no-upgrade lock", prompt)
            self.assertIn("horse_like maturity must not become sharp handsome 3.3-3.8", prompt)
        prompt = self.m.build_prompt(spec, "silhouette_card").lower()
        self.assertIn("v24 horse_like dependent no-upgrade lock", prompt)

    def test_bear_like_highband_blocks_dependent_undershoot(self):
        spec = self._spec(gender="male", face_type="bear_like", band="3.9-4.3")
        for shot in ("face_card", "silhouette_card", "vibe_card"):
            prompt = self.m.build_prompt(spec, shot).lower()
            self.assertIn("v24 bear_like 3.9-4.3 no-undershoot lock", prompt)
            self.assertIn("do not let dependent-shot distance", prompt)
            self.assertIn("keeping the assigned 3.9-4.3 polish", prompt)


if __name__ == "__main__":
    unittest.main()
