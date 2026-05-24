import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v3_under_test_v12", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PromptTargetingV14ControlledRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _base_spec(self, *, face_type="cat_like", band="1.5-2.4", has_eyewear=False, eyewear="soft_rectangular_metal"):
        level = {"1.5-2.4": 2.0, "2.5-3.2": 2.9, "3.3-3.8": 3.5, "3.9-4.3": 4.0}[band]
        specs = self.m.generate_specs(female_count=8, male_count=24, seed=20260522)
        spec = deepcopy(next(s for s in specs if s["gender"] == "male"))
        spec["profileId"] = "male_912"
        spec["numericId"] = 912
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = level
        spec["accessories"]["hasEyewear"] = bool(has_eyewear)
        if has_eyewear:
            spec["accessories"]["eyewearGroup"] = "glasses"
            spec["accessories"]["eyewear"] = eyewear
            spec["accessories"]["canonicalEyewear"] = eyewear
        else:
            spec["accessories"]["eyewearGroup"] = "none"
            spec["accessories"]["eyewear"] = "none"
            spec["accessories"]["canonicalEyewear"] = "none"
        return self.m.normalize_spec_defaults(spec)

    def test_prompt_targeting_version_is_v15(self):
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, "face_type_looks_level_targeting_v22")

    def test_cat_like_low_band_all_shots_prevent_ordinary_to_neat_upgrade(self):
        spec = self._base_spec(face_type="cat_like", band="1.5-2.4", has_eyewear=False)
        for shot in self.m.SHOT_TYPES:
            prompt = self.m.build_prompt(spec, shot)
            self.assertIn("cat_like 1.5-2.4 low-band no-upgrade lock", prompt)
            self.assertIn("plain low-band cat_like", prompt)
            self.assertIn("do not convert ordinary cat_like into fox_like neatness", prompt)
            self.assertIn("do not let neat styling read as 2.5-3.2 or 3.3-3.8", prompt)
            self.assertIn("v13 cat_like 1.5-2.4 reject-neatness lock", prompt)
            self.assertIn("a clean campus outfit or sincere expression must not raise observedLooksLevelBand above 1.5-2.4", prompt)
            self.assertIn("prefer plainer facial balance over likable polish", prompt)
            self.m.validate_no_banned_positive_terms(prompt)

    def test_eyewear_silhouette_has_mandatory_visibility_lock(self):
        spec = self._base_spec(face_type="bear_like", band="2.5-3.2", has_eyewear=True, eyewear="soft_rectangular_metal")
        prompt = self.m.build_prompt(spec, "silhouette_card")
        self.assertIn("v14 silhouette eyewear readability lock", prompt)
        self.assertIn("glasses are a required identity feature in this silhouette_card", prompt)
        self.assertIn("full-body framing must still show the soft rectangular metal-frame glasses", prompt)
        self.assertIn("use a three-quarter crop close enough that the frames are plainly readable", prompt)
        self.assertIn("if the frames would be too small, crop closer rather than removing them", prompt)
        self.assertIn("do not approve a no-glasses silhouette for this identity", prompt)
        self.assertIn("front or three-quarter face angle only; avoid rear, far-profile, tiny-face, or backlit crops that hide transparent or metal frames", prompt)
        self.assertIn("for clear-frame or thin metal eyewear, add crisp edge highlights and visible temple arms so QA can read the assigned frame style", prompt)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_clear_frame_silhouette_requires_edges_and_temple_arms(self):
        spec = self._base_spec(face_type="mixed_neutral", band="3.3-3.8", has_eyewear=True, eyewear="clear_frame")
        prompt = self.m.build_prompt(spec, "silhouette_card")
        self.assertIn("v14 silhouette eyewear readability lock", prompt)
        self.assertIn("clear-frame glasses", prompt)
        self.assertIn("crisp edge highlights", prompt)
        self.assertIn("visible temple arms", prompt)
        self.assertIn("not translucent eyewear that disappears into skin tone or background", prompt)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_cat_like_low_band_eyewear_silhouette_keeps_plain_band_and_visible_frames(self):
        spec = self._base_spec(face_type="cat_like", band="1.5-2.4", has_eyewear=True, eyewear="thin_round_metal")
        prompt = self.m.build_prompt(spec, "silhouette_card")
        self.assertIn("v13 cat_like eyewear silhouette double lock", prompt)
        self.assertIn("thin round metal glasses stay visible without making the face read neater", prompt)
        self.assertIn("do not let glasses, library context, or clean styling upgrade the face into 2.5-3.2", prompt)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_dog_low_band_eyewear_silhouette_keeps_plain_band(self):
        spec = self._base_spec(face_type="dog_like", band="1.5-2.4", has_eyewear=True, eyewear="soft_rectangular_metal")
        prompt = self.m.build_prompt(spec, "silhouette_card")
        self.assertIn("dog_like eyewear silhouette low-band lock", prompt)
        self.assertIn("glasses must not make the face read smarter, neater, or 2.5-3.2", prompt)
        self.assertIn("plain low-band dog_like ordinariness remains visible behind the glasses", prompt)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_hamster_mid_band_vibe_prevents_bear_like_broadening(self):
        spec = self._base_spec(face_type="hamster_like", band="2.5-3.2", has_eyewear=False)
        prompt = self.m.build_prompt(spec, "vibe_card")
        self.assertIn("v12 hamster_like vibe anti-bear lock", prompt)
        self.assertIn("do not broaden into bear_like grounded fullness", prompt)
        self.assertIn("keep compact rounded adult cheeks visible in the lifestyle context", prompt)
        self.assertIn("activity and posture must not make the face broader or sturdier", prompt)
        self.m.validate_no_banned_positive_terms(prompt)


if __name__ == "__main__":
    unittest.main()
