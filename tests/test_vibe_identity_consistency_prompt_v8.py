import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"
EXPECTED_VERSION = "face_type_looks_level_targeting_v8"
OLD_VERSION = "face_type_looks_level_targeting_v7"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v8_vibe_identity", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class VibeIdentityConsistencyPromptV8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _spec(self, *, gender="male", numeric_id=48, face_type="fox_like", band="2.5-3.2", level=2.8):
        spec = deepcopy(self.m.sample_spec(gender, numeric_id, seed=20260521 + numeric_id))
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = level
        return self.m.normalize_spec_defaults(spec)

    def _positive(self, prompt: str) -> str:
        return self.m.split_positive_and_negative_prompt(prompt)[0].lower()

    def test_prompt_targeting_version_is_v8(self):
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, EXPECTED_VERSION)
        assets = self.m.build_asset_records(self._spec())
        self.assertEqual({asset["promptTargetingVersion"] for asset in assets}, {EXPECTED_VERSION})
        self.assertTrue(all(f"Prompt targeting version: {EXPECTED_VERSION}." in asset["prompt"] for asset in assets))

    def test_prompt_hash_changes_from_v7_to_v8(self):
        spec = self._spec()
        current = self.m.build_asset_record(spec, "vibe_card")
        with mock.patch.object(self.m, "PROMPT_TARGETING_VERSION", OLD_VERSION):
            old = self.m.build_asset_record(spec, "vibe_card")
        self.assertNotEqual(current["promptHash"], old["promptHash"])

    def test_vibe_card_has_canonical_face_card_same_person_lock(self):
        positive = self._positive(self.m.build_prompt(self._spec(), "vibe_card"))
        for phrase in (
            "canonical face_card same-person lock",
            "attached face_card as the authoritative identity anchor",
            "same face shape, eye impression, nose-mouth balance",
            "skin tone, hairstyle, hair volume, and grooming",
        ):
            self.assertIn(phrase, positive)

    def test_vibe_card_face_visible_for_identity_matching(self):
        positive = self._positive(self.m.build_prompt(self._spec(), "vibe_card"))
        for phrase in (
            "face visible enough for identity matching",
            "not a distant lifestyle figure",
            "face occupies enough pixels to compare with the face_card",
            "front-facing or mild three-quarter face angle",
            "no strict side profile",
        ):
            self.assertIn(phrase, positive)

    def test_vibe_card_environment_secondary_to_identity(self):
        positive = self._positive(self.m.build_prompt(self._spec(), "vibe_card"))
        self.assertIn("environmental context is secondary to identity", positive)
        self.assertIn("location or activity must not alter facial identity", positive)
        self.assertIn("do not let location, activity, expression, gaze, or pose create a different facial identity", positive)

    def test_vibe_card_preserves_eyewear_state(self):
        spec = self._spec()
        positive = self._positive(self.m.build_prompt(spec, "vibe_card"))
        self.assertIn("preserve the same eyewear or no-eyewear state", positive)
        self.assertIn("no-eyewear when absent", positive)
        spec["accessories"]["eyewearGroup"] = "glasses"
        spec["accessories"]["eyewear"] = "black_acetate"
        spec["accessories"]["canonicalEyewear"] = "black_acetate"
        spec["accessories"]["hasEyewear"] = True
        spec = self.m.normalize_spec_defaults(spec)
        self.assertIn("black acetate", self._positive(self.m.build_prompt(spec, "vibe_card")))

    def test_vibe_card_preserves_fox_like_cues(self):
        positive = self._positive(self.m.build_prompt(self._spec(), "vibe_card"))
        self.assertIn("preserve the same subtle fox_like cues from the face_card", positive)
        self.assertIn("preserve one or two understated fox_like cues even in the lifestyle setting", positive)
        self.assertIn("avoid over-smiling into dog_like warmth", positive)

    def test_existing_face_card_and_silhouette_guards_remain(self):
        face_positive = self._positive(self.m.build_prompt(self._spec(), "face_card"))
        self.assertIn("one or two visible but understated fox_like cues", face_positive)
        self.assertIn("keep facial attractiveness clearly below 3.3-3.8", face_positive)
        silhouette_positive = self._positive(self.m.build_prompt(self._spec(), "silhouette_card"))
        self.assertIn("face clearly visible and identity-readable", silhouette_positive)
        self.assertIn("face large enough to recognize the same person from the face_card", silhouette_positive)

    def test_positive_prompt_scanner_passes(self):
        for shot in self.m.SHOT_TYPES:
            self.assertEqual(self.m.scan_prompt_for_banned_terms(self.m.build_prompt(self._spec(), shot)), [])


if __name__ == "__main__":
    unittest.main()
