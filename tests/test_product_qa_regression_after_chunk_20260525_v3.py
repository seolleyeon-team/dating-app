import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v3_after_chunk", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ProductQaRegressionAfterChunk20260525Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _distribution_fingerprint(self, specs):
        fingerprint = []
        for spec in specs:
            face = spec.get("face", {})
            accessories = spec.get("accessories", {})
            fingerprint.append(
                (
                    spec.get("gender"),
                    face.get("faceType"),
                    face.get("looksLevelBand"),
                    accessories.get("eyewearGroup"),
                    accessories.get("canonicalEyewear"),
                )
            )
        return sorted(fingerprint)

    def _spec(self, *, gender="male", face_type="fox_like", band="1.5-2.4"):
        specs = self.m.generate_specs(female_count=24, male_count=24, seed=20260525)
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
        spec["accessories"]["hasEyewear"] = True
        spec["accessories"]["eyewearGroup"] = "glasses"
        spec["accessories"]["eyewear"] = "thin_round_metal"
        spec["accessories"]["canonicalEyewear"] = "thin_round_metal"
        return self.m.normalize_spec_defaults(spec)

    def test_prompt_targeting_version_increments_and_prompt_hash_changes(self):
        spec = self._spec(gender="male", face_type="fox_like", band="1.5-2.4")
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, "face_type_looks_level_targeting_v24")
        current = self.m.build_asset_record(spec, "vibe_card")
        original = self.m.PROMPT_TARGETING_VERSION
        try:
            self.m.PROMPT_TARGETING_VERSION = "face_type_looks_level_targeting_v23"
            previous = self.m.build_asset_record(spec, "vibe_card")
        finally:
            self.m.PROMPT_TARGETING_VERSION = original
        self.assertNotEqual(current["promptHash"], previous["promptHash"])

    def test_distribution_unchanged_by_prompt_version_bump(self):
        before = self._distribution_fingerprint(self.m.generate_specs(female_count=12, male_count=12, seed=20260525))
        original = self.m.PROMPT_TARGETING_VERSION
        try:
            self.m.PROMPT_TARGETING_VERSION = "face_type_looks_level_targeting_v23"
            after = self._distribution_fingerprint(self.m.generate_specs(female_count=12, male_count=12, seed=20260525))
        finally:
            self.m.PROMPT_TARGETING_VERSION = original
        self.assertEqual(before, after)

    def test_positive_prompt_scanner_passes_for_failure_classes(self):
        cases = [
            ("male", "fox_like", "1.5-2.4"),
            ("male", "horse_like", "2.5-3.2"),
            ("male", "bear_like", "3.9-4.3"),
        ]
        for gender, face_type, band in cases:
            with self.subTest(gender=gender, face_type=face_type, band=band):
                spec = self._spec(gender=gender, face_type=face_type, band=band)
                for shot in self.m.SHOT_TYPES:
                    self.m.validate_no_banned_positive_terms(self.m.build_prompt(spec, shot))

    def test_same_person_vibe_environment_eyewear_and_adult_cues_remain(self):
        spec = self._spec(gender="male", face_type="fox_like", band="1.5-2.4")
        prompt = self.m.build_prompt(spec, "vibe_card").lower()
        self.assertIn("same person", prompt)
        self.assertIn("face_card", prompt)
        self.assertIn("environment", prompt)
        self.assertIn("secondary", prompt)
        self.assertIn("glasses", prompt)
        self.assertIn("adult", prompt)
        self.assertIn("childlike", prompt)

    def test_failure_class_guards_present(self):
        cases = [
            ("male", "fox_like", "1.5-2.4", "v24 male fox_like 1.5-2.4 all-shot no-upgrade lock"),
            ("male", "horse_like", "2.5-3.2", "v24 horse_like 2.5-3.2 no-upgrade lock"),
            ("male", "bear_like", "3.9-4.3", "v24 bear_like 3.9-4.3 no-undershoot lock"),
        ]
        for gender, face_type, band, expected in cases:
            with self.subTest(face_type=face_type, band=band):
                prompt = self.m.build_prompt(self._spec(gender=gender, face_type=face_type, band=band), "vibe_card").lower()
                self.assertIn(expected, prompt)

    def test_prior_v23_guards_remain(self):
        spec = self._spec(gender="female", face_type="fox_like", band="1.5-2.4")
        prompt = self.m.build_prompt(spec, "vibe_card").lower()
        self.assertIn("v23 female 1.5-2.4 all-shot no-upgrade lock", prompt)
        self.assertIn("v23 female low-band vibe phone-snapshot lock", prompt)


if __name__ == "__main__":
    unittest.main()
