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


class PromptTargetingV22ProductQaRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _base_spec(self, *, face_type="cat_like", band="1.5-2.4"):
        specs = self.m.generate_specs(female_count=8, male_count=24, seed=20260523)
        spec = deepcopy(next(s for s in specs if s["gender"] == "male"))
        spec["profileId"] = "male_917"
        spec["numericId"] = 917
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = 2.0 if band == "1.5-2.4" else 2.9
        spec["accessories"]["hasEyewear"] = False
        spec["accessories"]["eyewearGroup"] = "none"
        spec["accessories"]["eyewear"] = "none"
        spec["accessories"]["canonicalEyewear"] = "none"
        return self.m.normalize_spec_defaults(spec)

    def test_prompt_targeting_version_is_v22_and_hash_changes_from_v21(self):
        spec = self._base_spec(face_type="cat_like", band="1.5-2.4")
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, "face_type_looks_level_targeting_v22")
        baseline = self.m.build_asset_record(spec, "vibe_card")
        original = self.m.PROMPT_TARGETING_VERSION
        try:
            self.m.PROMPT_TARGETING_VERSION = "face_type_looks_level_targeting_v21"
            old = self.m.build_asset_record(spec, "vibe_card")
        finally:
            self.m.PROMPT_TARGETING_VERSION = original
        self.assertNotEqual(baseline["promptHash"], old["promptHash"])

    def test_cat_like_low_band_dependent_shots_block_average_pleasant_drift(self):
        spec = self._base_spec(face_type="cat_like", band="1.5-2.4")
        for shot in ("silhouette_card", "vibe_card"):
            prompt = self.m.build_prompt(spec, shot).lower()
            self.assertIn("v18 cat_like low-band dependent-shot lock", prompt)
            self.assertIn("qa must still choose 1.5-2.4 rather than 2.5-3.2", prompt)
            self.assertIn("do not let neat outfit, calm activity, or campus lighting create average-pleasant appeal", prompt)
            self.assertIn("preserve subtle almond-eye cat_like cue without converting to dog_like, bear_like, or mixed_neutral", prompt)

    def test_vibe_card_requires_face_type_readable_gaze_not_downward_or_object_first(self):
        for face_type, band in (("dog_like", "2.5-3.2"), ("cat_like", "1.5-2.4")):
            prompt = self.m.build_prompt(self._base_spec(face_type=face_type, band=band), "vibe_card").lower()
            self.assertIn("v18 vibe face-type readability lock", prompt)
            self.assertIn("do not use a downward-looking or object-first pose", prompt)
            self.assertIn("face angle must remain front-facing or mild three-quarter", prompt)
            self.assertIn("face-type evidence must be readable enough for qa", prompt)

    def test_cat_like_low_band_guard_does_not_pollute_mid_band_dog_like(self):
        prompt = self.m.build_prompt(self._base_spec(face_type="dog_like", band="2.5-3.2"), "vibe_card").lower()
        self.assertIn("v18 vibe face-type readability lock", prompt)
        self.assertNotIn("v18 cat_like low-band dependent-shot lock", prompt)
        self.assertNotIn("qa must still choose 1.5-2.4 rather than 2.5-3.2", prompt)

    def test_dog_like_low_band_all_shots_block_bear_like_or_average_upgrade(self):
        for shot in ("face_card", "silhouette_card", "vibe_card"):
            prompt = self.m.build_prompt(self._base_spec(face_type="dog_like", band="1.5-2.4"), shot).lower()
            self.assertIn("v19 dog_like 1.5-2.4 full-shot hard lock", prompt)
            self.assertIn("qa must not read bear_like sturdiness", prompt)
            self.assertIn("without broad jaw, thick-brow sturdy bear_like structure", prompt)

    def test_dog_like_low_band_vibe_blocks_average_pleasant_upgrade(self):
        prompt = self.m.build_prompt(self._base_spec(face_type="dog_like", band="1.5-2.4"), "vibe_card").lower()
        self.assertIn("v18 dog_like 1.5-2.4 vibe strict plainness lock", prompt)
        self.assertIn("qa must still choose 1.5-2.4 for the vibe_card, not 2.5-3.2", prompt)
        self.assertIn("avoid any neat outfit-check, mirror/selfie, cafe, lounge, or campus activity", prompt)
        self.assertIn("no warm polished smile", prompt)
        self.assertIn("v19 dog_like low-band vibe hard reject avoidance", prompt)
        self.assertIn("do not use lounge-chair, notebook, cafe", prompt)


    def test_deer_like_high_mid_silhouette_blocks_side_facing_unclear_face(self):
        prompt = self.m.build_prompt(self._base_spec(face_type="deer_like", band="3.3-3.8"), "silhouette_card").lower()
        self.assertIn("v20 deer_like silhouette face-angle lock", prompt)
        self.assertIn("never use a side-facing silhouette", prompt)
        self.assertIn("both eyes/nose-mouth balance readable", prompt)

    def test_mixed_neutral_high_mid_silhouette_blocks_lower_band_undershoot(self):
        prompt = self.m.build_prompt(self._base_spec(face_type="mixed_neutral", band="3.3-3.8"), "silhouette_card").lower()
        self.assertIn("v20 mixed_neutral 3.3-3.8 silhouette no-undershoot lock", prompt)
        self.assertIn("must still read as 3.3-3.8, not neat everyday 2.5-3.2", prompt)
        self.assertIn("do not let distance, side angle, flat lighting", prompt)

    def test_hamster_like_midband_vibe_blocks_lifestyle_upgrade(self):
        prompt = self.m.build_prompt(self._base_spec(face_type="hamster_like", band="2.5-3.2"), "vibe_card").lower()
        self.assertIn("v21 hamster_like 2.5-3.2 vibe no-upgrade lock", prompt)
        self.assertIn("must not become cute, polished, or clearly attractive 3.3-3.8", prompt)
        self.assertIn("anchored to the face_card's 2.5-3.2 ordinariness", prompt)

    def test_fox_like_midband_vibe_blocks_lifestyle_upgrade(self):
        prompt = self.m.build_prompt(self._base_spec(face_type="fox_like", band="2.5-3.2"), "vibe_card").lower()
        self.assertIn("v21 fox_like 2.5-3.2 vibe no-upgrade lock", prompt)
        self.assertIn("must not turn restrained fox_like into clearly attractive 3.3-3.8", prompt)
        self.assertIn("avoid bookstore/cafe polish", prompt)

    def test_cat_like_lowband_silhouette_blocks_average_upgrade(self):
        prompt = self.m.build_prompt(self._base_spec(face_type="cat_like", band="1.5-2.4"), "silhouette_card").lower()
        self.assertIn("v21 cat_like 1.5-2.4 silhouette no-upgrade lock", prompt)
        self.assertIn("must still read low-band, not mixed_neutral 2.5-3.2", prompt)

    def test_cat_like_highband_dependent_blocks_undershoot(self):
        prompt = self.m.build_prompt(self._base_spec(face_type="cat_like", band="3.9-4.3"), "vibe_card").lower()
        self.assertIn("v21 cat_like 3.9-4.3 dependent no-undershoot lock", prompt)
        self.assertIn("should not fall to 3.3-3.8", prompt)

    def test_deer_like_midband_face_card_blocks_elegant_upgrade(self):
        prompt = self.m.build_prompt(self._base_spec(face_type="deer_like", band="2.5-3.2"), "face_card").lower()
        self.assertIn("v22 deer_like 2.5-3.2 face-card no-upgrade lock", prompt)
        self.assertIn("must stay ordinary", prompt)
        self.assertIn("must not become elegant 3.3-3.8", prompt)

    def test_cat_like_lowband_face_card_blocks_bear_hamster_misread(self):
        prompt = self.m.build_prompt(self._base_spec(face_type="cat_like", band="1.5-2.4"), "face_card").lower()
        self.assertIn("v22 face-card cat_like low-band hard lock", prompt)
        self.assertIn("must not read bear_like, hamster_like, mixed_neutral, or 2.5-3.2", prompt)
        self.assertIn("black-acetate intellectual neatness", prompt)

    def test_dog_like_lowband_face_card_blocks_youthful_review(self):
        prompt = self.m.build_prompt(self._base_spec(face_type="dog_like", band="1.5-2.4"), "face_card").lower()
        self.assertIn("v22 dog_like low-band adult-boundary lock", prompt)
        self.assertIn("clearly adult university age", prompt)
        self.assertIn("not borderline youthful", prompt)

if __name__ == "__main__":
    unittest.main()
