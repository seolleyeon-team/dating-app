import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"
EXPECTED_VERSION = "face_type_looks_level_targeting_v22"
OLD_VERSION = "face_type_looks_level_targeting_v6"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v7_fox_midband", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PromptTargetingV7FoxMidbandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _spec(self, *, gender="male", numeric_id=47, face_type="fox_like", band="2.5-3.2", level=3.0):
        spec = deepcopy(self.m.sample_spec(gender, numeric_id, seed=20260521 + numeric_id))
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = level
        return self.m.normalize_spec_defaults(spec)

    def _positive(self, prompt: str) -> str:
        return self.m.split_positive_and_negative_prompt(prompt)[0].lower()

    def test_prompt_targeting_version_is_v7(self):
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, EXPECTED_VERSION)
        assets = self.m.build_asset_records(self._spec())
        self.assertEqual({asset["promptTargetingVersion"] for asset in assets}, {EXPECTED_VERSION})
        self.assertTrue(all(f"Prompt targeting version: {EXPECTED_VERSION}." in asset["prompt"] for asset in assets))

    def test_prompt_hash_changes_from_v6_to_v7(self):
        spec = self._spec()
        current = self.m.build_asset_record(spec, "face_card")
        with mock.patch.object(self.m, "PROMPT_TARGETING_VERSION", OLD_VERSION):
            old = self.m.build_asset_record(spec, "face_card")
        self.assertNotEqual(current["promptHash"], old["promptHash"])

    def test_face_card_has_stronger_non_dog_non_hamster_non_mixed_guard(self):
        positive = self._positive(self.m.build_prompt(self._spec(), "face_card"))
        for phrase in (
            "one or two visible but understated fox_like cues",
            "does not collapse into mixed_neutral",
            "avoid compact hamster-like cheek softness",
            "do not compact into hamster_like rounded cuteness",
            "do not become fully mixed_neutral",
            "do not flatten it into mixed_neutral when subtle fox_like cues are visible",
            "preserve one or two understated fox_like cues",
            "avoid fully balanced mixed_neutral face",
        ):
            self.assertIn(phrase, positive)
        self.assertEqual(self.m.scan_prompt_for_banned_terms(self.m.build_prompt(self._spec(), "face_card")), [])

    def test_face_card_camera_constraints_are_more_ordinary(self):
        positive = self._positive(self.m.build_prompt(self._spec(), "face_card"))
        for phrase in (
            "very ordinary phone camera profile feel",
            "flatter everyday lighting",
            "no portrait-style depth",
            "no dramatic catchlights",
            "no polished dating-profile crop",
            "facial realism over styling",
        ):
            self.assertIn(phrase, positive)

    def test_vibe_card_preserves_same_person_fox_like_cues(self):
        positive = self._positive(self.m.build_prompt(self._spec(), "vibe_card"))
        for phrase in (
            "preserve the same subtle fox_like cues from the face_card",
            "face visible enough to read the slightly narrow composed eye impression",
            "avoid over-smiling into dog_like warmth",
            "avoid overly soft cheeks or hamster_like compact cuteness",
            "do not shrink the face too much",
            "not fully mixed_neutral",
        ):
            self.assertIn(phrase, positive)

    def test_silhouette_readability_and_eyewear_consistency_survive(self):
        spec = self._spec()
        spec["accessories"]["eyewearGroup"] = "glasses"
        spec["accessories"]["eyewear"] = "black_acetate"
        spec["accessories"]["canonicalEyewear"] = "black_acetate"
        spec["accessories"]["hasEyewear"] = True
        spec = self.m.normalize_spec_defaults(spec)
        silhouette = self._positive(self.m.build_prompt(spec, "silhouette_card"))
        self.assertIn("face clearly visible and identity-readable", silhouette)
        self.assertIn("face large enough to recognize the same person from the face_card", silhouette)
        for shot in self.m.SHOT_TYPES:
            prompt = self.m.build_prompt(spec, shot)
            self.assertIn("black acetate", prompt.lower())
            self.assertEqual(self.m.scan_prompt_for_banned_terms(prompt), [])

    def test_exact_distributions_unchanged(self):
        specs = self.m.generate_specs(female_count=120, male_count=120, seed=20260512)
        audit = self.m.audit_prompt_distribution(specs)
        self.assertTrue(audit["passed"], audit["mismatches"])
        self.assertEqual(audit["counts"]["faceType"], self.m.FACE_TYPE_TARGETS["global"])
        self.assertEqual(audit["counts"]["looksLevelBand"], self.m.LOOKS_LEVEL_BAND_TARGETS["global"])
        self.assertEqual(audit["counts"]["eyewear"], {"with_eyewear": 36, "without_eyewear": 204})
        self.assertEqual(audit["counts"]["season"], self.m.SEASON_TARGETS)


if __name__ == "__main__":
    unittest.main()
