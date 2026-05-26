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


class PromptTargetingV23ProductQaRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _female_spec(self, *, face_type="fox_like", band="1.5-2.4"):
        specs = self.m.generate_specs(female_count=24, male_count=1, seed=20260524)
        spec = deepcopy(next(s for s in specs if s["gender"] == "female"))
        spec["profileId"] = "female_923"
        spec["numericId"] = 923
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = {
            "1.5-2.4": 2.0,
            "2.5-3.2": 2.9,
            "3.3-3.8": 3.5,
        }.get(band, 3.0)
        spec["accessories"]["hasEyewear"] = False
        spec["accessories"]["eyewearGroup"] = "none"
        spec["accessories"]["eyewear"] = "none"
        spec["accessories"]["canonicalEyewear"] = "none"
        return self.m.normalize_spec_defaults(spec)

    def test_prompt_targeting_version_is_v24_and_hash_changes_from_v23(self):
        spec = self._female_spec(face_type="fox_like", band="1.5-2.4")
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, "face_type_looks_level_targeting_v24")
        baseline = self.m.build_asset_record(spec, "vibe_card")
        original = self.m.PROMPT_TARGETING_VERSION
        try:
            self.m.PROMPT_TARGETING_VERSION = "face_type_looks_level_targeting_v23"
            old = self.m.build_asset_record(spec, "vibe_card")
        finally:
            self.m.PROMPT_TARGETING_VERSION = original
        self.assertNotEqual(baseline["promptHash"], old["promptHash"])

    def test_female_fox_like_lowband_all_shots_block_polished_lifestyle_upgrade(self):
        for shot in ("face_card", "silhouette_card", "vibe_card"):
            prompt = self.m.build_prompt(self._female_spec(face_type="fox_like", band="1.5-2.4"), shot).lower()
            self.assertIn("v23 female 1.5-2.4 all-shot no-upgrade lock", prompt)
            self.assertIn("must remain plainly below-average and unpolished", prompt)
            self.assertIn("must not upgrade observedlookslevelband into 2.5-3.2 or 3.3-3.8", prompt)
            self.assertIn("v23 female fox_like 1.5-2.4 guard", prompt)
        vibe = self.m.build_prompt(self._female_spec(face_type="fox_like", band="1.5-2.4"), "vibe_card").lower()
        self.assertIn("v23 female low-band vibe phone-snapshot lock", vibe)
        self.assertIn("not a lifestyle profile photo", vibe)
        self.assertIn("avoid flattering cafe/bookstore polish", vibe)

    def test_female_bear_like_lowband_blocks_hamster_cute_or_average_upgrade(self):
        for shot in ("face_card", "silhouette_card", "vibe_card"):
            prompt = self.m.build_prompt(self._female_spec(face_type="bear_like", band="1.5-2.4"), shot).lower()
            self.assertIn("v23 female bear_like 1.5-2.4 anti-hamster/no-cute guard", prompt)
            self.assertIn("without compact hamster_like roundness", prompt)
            self.assertIn("avoid cute lovable cheeks", prompt)
        face = self.m.build_prompt(self._female_spec(face_type="bear_like", band="1.5-2.4"), "face_card").lower()
        self.assertIn("v23 female bear_like low-band anti-cute lock", face)
        self.assertIn("not compact hamster_like cuteness", face)

    def test_female_mixed_neutral_midband_face_card_blocks_deer_like_upgrade(self):
        prompt = self.m.build_prompt(self._female_spec(face_type="mixed_neutral", band="2.5-3.2"), "face_card").lower()
        self.assertIn("v23 female mixed_neutral 2.5-3.2 face-card no-upgrade lock", prompt)
        self.assertIn("not deer_like and not 3.3-3.8", prompt)
        self.assertIn("avoid deer_like elongated softness", prompt)
        self.assertIn("neutral-balanced with ordinary proportions", prompt)

    def test_female_horse_like_midband_dependent_shots_preserve_same_person_structure(self):
        for shot in ("silhouette_card", "vibe_card"):
            prompt = self.m.build_prompt(self._female_spec(face_type="horse_like", band="2.5-3.2"), shot).lower()
            self.assertIn("v23 female horse_like dependent-shot identity lock", prompt)
            self.assertIn("preserve the face_card's longer/elegant horse_like structure", prompt)
            self.assertIn("do not soften into deer_like delicacy", prompt)
            self.assertIn("compact into hamster_like roundness", prompt)
            self.assertIn("must stay same-person with face_card", prompt)

    def test_female_dog_like_high_mid_face_card_blocks_undershoot_without_overpolish(self):
        prompt = self.m.build_prompt(self._female_spec(face_type="dog_like", band="3.3-3.8"), "face_card").lower()
        self.assertIn("v23 female dog_like 3.3-3.8 face-card no-undershoot lock", prompt)
        self.assertIn("must clearly remain 3.3-3.8", prompt)
        self.assertIn("do not flatten it into ordinary 2.5-3.2", prompt)
        self.assertIn("avoid influencer, celebrity, idol, model, beauty-filter, or 4.4-5.0 polish", prompt)

    def test_v23_guards_do_not_pollute_male_fox_lowband(self):
        specs = self.m.generate_specs(female_count=1, male_count=8, seed=20260524)
        spec = deepcopy(next(s for s in specs if s["gender"] == "male"))
        spec["face"]["faceType"] = "fox_like"
        spec["face"]["looksLevelBand"] = "1.5-2.4"
        spec["face"]["looksLevel"] = 2.0
        spec = self.m.normalize_spec_defaults(spec)
        prompt = self.m.build_prompt(spec, "vibe_card").lower()
        self.assertNotIn("v23 female 1.5-2.4 all-shot no-upgrade lock", prompt)
        self.assertNotIn("v23 female fox_like 1.5-2.4 guard", prompt)


if __name__ == "__main__":
    unittest.main()
