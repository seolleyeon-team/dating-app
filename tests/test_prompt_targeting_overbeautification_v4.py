import importlib.util
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"
EXPECTED_VERSION = "face_type_looks_level_targeting_v23"
OLD_VERSION = "face_type_looks_level_targeting_v4"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v4_overbeautification", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class PromptTargetingOverbeautificationV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _spec(
        self,
        *,
        gender="male",
        numeric_id=10,
        face_type="fox_like",
        band="2.5-3.2",
        level=2.8,
        eyewear=False,
        location_type=None,
    ):
        spec = deepcopy(self.m.sample_spec(gender, numeric_id, seed=20260604))
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = level
        if eyewear:
            spec["accessories"]["eyewearGroup"] = "glasses"
            spec["accessories"]["eyewear"] = "thin_round_metal"
            spec["accessories"]["canonicalEyewear"] = "thin_round_metal"
            spec["accessories"]["hasEyewear"] = True
        if location_type:
            spec["location"] = deepcopy(self.m.LOCATION_CATALOG[location_type])
            spec["location"]["locationType"] = location_type
            spec["vibeActivity"] = self.m.LOCATION_VIBE_ACTIVITIES[location_type][0]
        return self.m.normalize_spec_defaults(spec)

    def _positive(self, prompt: str) -> str:
        return self.m.split_positive_and_negative_prompt(prompt)[0].lower()

    def test_prompt_targeting_version_is_current_in_constants_prompts_assets_and_metadata(self):
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, EXPECTED_VERSION)
        spec = self._spec()
        asset = self.m.build_asset_record(spec, "face_card")
        self.assertEqual(asset["promptTargetingVersion"], EXPECTED_VERSION)
        self.assertEqual(asset["metadata"]["promptTargetingVersion"], EXPECTED_VERSION)
        self.assertIn(f"Prompt targeting version: {EXPECTED_VERSION}.", asset["prompt"])

    def test_prompt_hash_changes_from_previous_version_text(self):
        spec = self._spec()
        current = self.m.build_asset_record(spec, "face_card")
        with mock.patch.object(self.m, "PROMPT_TARGETING_VERSION", OLD_VERSION):
            old = self.m.build_asset_record(spec, "face_card")
        self.assertNotEqual(current["promptHash"], old["promptHash"])

    def test_fox_like_mid_band_face_card_has_combined_ordinary_guard(self):
        prompt = self.m.build_prompt(self._spec(), "face_card")
        positive = self._positive(prompt)
        for phrase in (
            "subtle composed fox-like impression",
            "slightly alert but ordinary campus face",
            "restrained facial angularity",
            "less round friendly softness than dog_like",
            "calm composed expression rather than openly puppyish warmth",
            "natural non-glossy skin",
            "no dramatic eye enlargement",
            "no slim v-line jaw",
            "fox_like does not mean highly attractive",
            "fox_like does not mean celebrity/idol styling",
            "fox_like should remain within the assigned looksLevelBand",
            "target-specific face_card guard",
            "keep the fox_like impression subtle and composed, but ordinary",
            "avoid sharp handsome transformation",
            "avoid model-like profile",
            "preserve the average-to-mildly-pleasant 2.5-3.2 band",
            "do not let camera, lighting, styling, or pose raise it into 3.3-3.8",
        ):
            self.assertIn(phrase.lower(), positive)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_fox_like_mid_band_positive_section_has_no_glamour_or_public_figure_styling(self):
        prompt = self.m.build_prompt(self._spec(), "face_card")
        positive = self._positive(prompt)
        for forbidden in (
            "glamour styling",
            "influencer styling",
            "celebrity styling",
            "sharp handsome face",
            "model-like profile pose",
        ):
            self.assertNotIn(forbidden, positive)
        self.assertEqual(self.m.scan_prompt_for_banned_terms(prompt), [])

    def test_mid_band_looks_block_is_grounded_and_below_33_38(self):
        block = self.m.looks_level_band_target_visual("2.5-3.2").lower()
        for phrase in (
            "average to mildly pleasant",
            "ordinary student realism",
            "keep facial attractiveness clearly below 3.3-3.8",
            "do not let styling, lighting, or camera polish raise the perceived looks band",
            "ordinary student realism is more important than attractiveness",
        ):
            self.assertIn(phrase, block)
        for forbidden in ("neat handsome", "highly polished"):
            self.assertNotIn(forbidden, block)
        for negated_phrase in ("no refined jawline", "no noticeably sharp nose bridge"):
            self.assertIn(negated_phrase, block)

    def test_silhouette_card_balances_body_and_identity_readability(self):
        prompt = self.m.build_prompt(self._spec(), "silhouette_card")
        positive = self._positive(prompt)
        for phrase in (
            "three-quarter body or full body, but keep the face clearly visible and identity-readable",
            "front-facing or mild three-quarter face angle, not a strict side profile",
            "face large enough to recognize the same person from the face_card",
            "body proportions remain readable, but identity consistency is still required",
            "face occupies enough pixels to confirm same person",
            "keep same broad face impression, skin tone, hairstyle, and eyewear if present",
        ):
            self.assertIn(phrase.lower(), positive)
        for phrase in (
            "do not use strict side-profile",
            "do not use far-distance full-body shot",
            "avoid back view",
            "avoid tiny face",
        ):
            self.assertIn(phrase, positive)
        self.assertIn("body proportions readable", positive)
        self.assertIn("avoid head-and-shoulders crop", positive)
        self.assertIn("avoid close-up crop", positive)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_silhouette_card_with_glasses_keeps_eyes_visible_and_body_readable(self):
        prompt = self.m.build_prompt(self._spec(eyewear=True), "silhouette_card")
        positive = self._positive(prompt)
        self.assertIn("same thin round metal-frame glasses", positive)
        self.assertIn("eyes clearly visible", positive)
        self.assertIn("body proportions readable", positive)
        self.assertIn("identity-readable", positive)
        self.m.validate_no_banned_positive_terms(prompt)

    def test_vibe_card_location_activity_safety_and_no_upward_upgrade_remain(self):
        spec = self._spec(gender="female", numeric_id=11, location_type="flower_viewing_path")
        prompt = self.m.build_prompt(spec, "vibe_card")
        positive, negative = self.m.split_positive_and_negative_prompt(prompt)
        self.assertIn(spec["vibeActivity"], positive)
        self.assertIn(self.m.LOCATION_CATALOG["flower_viewing_path"]["scene"], positive)
        self.assertIn("Preserve the same person from the face_card reference", prompt)
        self.assertIn("Do not beautify beyond the target looksLevelBand", prompt)
        self.assertNotIn("influencer photoshoot", positive.lower())
        self.assertIn("influencer photoshoot", negative.lower())
        self.m.validate_no_banned_positive_terms(prompt)

    def test_exact_distributions_unchanged(self):
        specs = self.m.generate_specs(female_count=120, male_count=120, seed=20260512)
        audit = self.m.audit_prompt_distribution(specs)
        self.assertTrue(audit["passed"], audit["mismatches"])
        self.assertEqual(audit["counts"]["faceType"], self.m.FACE_TYPE_TARGETS["global"])
        self.assertEqual(audit["counts"]["looksLevelBand"], self.m.LOOKS_LEVEL_BAND_TARGETS["global"])
        self.assertEqual(audit["counts"]["eyewear"], {"with_eyewear": 36, "without_eyewear": 204})
        self.assertEqual(audit["counts"]["season"], self.m.SEASON_TARGETS)

    def test_export_metadata_includes_prompt_targeting_version_hash_and_targets(self):
        spec = self._spec(gender="female", numeric_id=12)
        assets = self.m.build_asset_records(spec)
        self.assertEqual(len(assets), 3)
        for asset in assets:
            self.assertEqual(asset["promptTargetingVersion"], EXPECTED_VERSION)
            self.assertIn("promptHash", asset)
            self.assertTrue(asset["promptHash"])
            self.assertEqual(asset["targetFaceType"], "fox_like")
            self.assertEqual(asset["targetLooksLevelBand"], "2.5-3.2")
            self.assertEqual(asset["metadata"]["promptTargetingVersion"], EXPECTED_VERSION)
            self.assertIn(f"Prompt targeting version: {EXPECTED_VERSION}.", asset["prompt"])
            self.m.validate_no_banned_positive_terms(asset["prompt"])


if __name__ == "__main__":
    unittest.main()
