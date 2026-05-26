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


class PromptTargetingV15ProductQaRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _base_spec(self, *, face_type="dog_like", band="1.5-2.4", has_eyewear=False):
        specs = self.m.generate_specs(female_count=8, male_count=24, seed=20260523)
        spec = deepcopy(next(s for s in specs if s["gender"] == "male"))
        spec["profileId"] = "male_915"
        spec["numericId"] = 915
        spec["face"]["faceType"] = face_type
        spec["face"]["looksLevelBand"] = band
        spec["face"]["looksLevel"] = 2.0 if band == "1.5-2.4" else 2.9
        spec["accessories"]["hasEyewear"] = bool(has_eyewear)
        if has_eyewear:
            spec["accessories"]["eyewearGroup"] = "glasses"
            spec["accessories"]["eyewear"] = "clear_frame"
            spec["accessories"]["canonicalEyewear"] = "clear_frame"
        else:
            spec["accessories"]["eyewearGroup"] = "none"
            spec["accessories"]["eyewear"] = "none"
            spec["accessories"]["canonicalEyewear"] = "none"
        return self.m.normalize_spec_defaults(spec)

    def test_prompt_targeting_version_is_v17_and_hash_changes_from_v16(self):
        spec = self._base_spec(face_type="dog_like", band="1.5-2.4")
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, "face_type_looks_level_targeting_v23")
        baseline = self.m.build_asset_record(spec, "vibe_card")
        original = self.m.PROMPT_TARGETING_VERSION
        try:
            self.m.PROMPT_TARGETING_VERSION = "face_type_looks_level_targeting_v16"
            old = self.m.build_asset_record(spec, "vibe_card")
        finally:
            self.m.PROMPT_TARGETING_VERSION = original
        self.assertNotEqual(baseline["promptHash"], old["promptHash"])

    def test_dog_like_low_band_face_and_vibe_block_neatness_overread(self):
        spec = self._base_spec(face_type="dog_like", band="1.5-2.4")
        face_prompt = self.m.build_prompt(spec, "face_card").lower()
        vibe_prompt = self.m.build_prompt(spec, "vibe_card").lower()
        for prompt in (face_prompt, vibe_prompt):
            self.assertIn("v15 dog_like low-band anti-overread", prompt)
            self.assertIn("v16 dog_like low-band no-polish rescue", prompt)
            self.assertIn("confident campus portrait styling must not", prompt)
            self.assertIn("must not be enough to read 2.5-3.2", prompt)
            self.assertIn("qa should still choose 1.5-2.4 over 2.5-3.2", prompt)
        self.assertIn("v16 dog_like low-band vibe no-upgrade lock", vibe_prompt)
        self.assertIn("not a polished confident campus portrait", vibe_prompt)

    def test_dog_like_2_5_to_3_2_guard_is_not_narrowed_by_low_band_no_polish_rules(self):
        spec = self._base_spec(face_type="dog_like", band="2.5-3.2")
        prompt = self.m.build_prompt(spec, "vibe_card").lower()
        self.assertIn("combined dog_like 2.5-3.2 guard", prompt)
        self.assertNotIn("v16 dog_like low-band no-polish rescue", prompt)
        self.assertNotIn("qa should still choose 1.5-2.4 over 2.5-3.2", prompt)

    def test_dog_like_vibe_preserves_face_card_anchors_and_blocks_horse_like(self):
        spec = self._base_spec(face_type="dog_like", band="1.5-2.4")
        prompt = self.m.build_prompt(spec, "vibe_card").lower()
        self.assertIn("v15 dog_like vibe identity lock", prompt)
        self.assertIn("rounded friendly dog_like anchors", prompt)
        self.assertIn("do not elongate into horse_like mature long-face structure", prompt)
        self.assertIn("same dog_like face remains recognizable", prompt)

    def test_hamster_like_vibe_keeps_adult_boundary_without_losing_soft_cues(self):
        spec = self._base_spec(face_type="hamster_like", band="2.5-3.2")
        prompt = self.m.build_prompt(spec, "vibe_card").lower()
        self.assertIn("v15 hamster_like vibe adult-boundary lock", prompt)
        self.assertIn("clearly adult university age", prompt)
        self.assertIn("no babyface emphasis", prompt)
        self.assertIn("no teenager cues", prompt)
        self.assertIn("soft hamster_like cues", prompt)

    def test_hamster_like_silhouette_preserves_compact_round_cues_and_blocks_bear_broadness(self):
        spec = self._base_spec(face_type="hamster_like", band="2.5-3.2")
        prompt = self.m.build_prompt(spec, "silhouette_card").lower()
        self.assertIn("v16 hamster_like silhouette compact-round lock", prompt)
        self.assertIn("compact rounded same-person cues", prompt)
        self.assertIn("do not broaden into bear_like", prompt)
        self.assertIn("avoid broad jaw, thick brows, sturdy bear_like fullness", prompt)

    def test_soft_rectangular_metal_and_thin_glasses_persist_readably_in_dependent_shots(self):
        spec = self._base_spec(face_type="dog_like", band="3.3-3.8", has_eyewear=True)
        spec["accessories"]["eyewear"] = "soft_rectangular_metal"
        spec["accessories"]["canonicalEyewear"] = "soft_rectangular_metal"
        for shot in ("silhouette_card", "vibe_card"):
            prompt = self.m.build_prompt(self.m.normalize_spec_defaults(spec), shot).lower()
            self.assertIn("v16 required eyewear persistence lock", prompt)
            self.assertIn("soft rectangular metal-frame glasses", prompt)
            self.assertIn("qa can point to frame outline, bridge, and temple arm", prompt)
            self.assertIn("same-person eyewear consistency", prompt)

    def test_clear_frame_silhouette_requires_pointable_rims_bridge_and_temple_arm(self):
        spec = self._base_spec(face_type="dog_like", band="1.5-2.4", has_eyewear=True)
        prompt = self.m.build_prompt(spec, "silhouette_card").lower()
        self.assertIn("v15 clear-frame silhouette readability lock", prompt)
        self.assertIn("visible lens rims, bridge, and temple arms", prompt)
        self.assertIn("qa can point to both lenses and at least one temple arm", prompt)
        self.assertIn("never a tiny face", prompt)

    def test_banned_positive_scanner_and_distribution_invariants_remain_clean(self):
        cases = [
            ("dog_like", "1.5-2.4", "face_card", False),
            ("dog_like", "1.5-2.4", "vibe_card", False),
            ("hamster_like", "2.5-3.2", "vibe_card", False),
            ("dog_like", "1.5-2.4", "silhouette_card", True),
        ]
        for face_type, band, shot, has_eyewear in cases:
            prompt = self.m.build_prompt(self._base_spec(face_type=face_type, band=band, has_eyewear=has_eyewear), shot)
            self.assertEqual(self.m.scan_prompt_for_banned_terms(prompt), [])
            self.m.validate_no_banned_positive_terms(prompt)
        specs = self.m.generate_specs(female_count=120, male_count=120, seed=20260512)
        self.assertEqual(sum(s["face"]["faceType"] == "dog_like" for s in specs), 38)
        self.assertEqual(sum(s["face"]["faceType"] == "hamster_like" for s in specs), 24)
        self.assertEqual(sum(s["face"]["looksLevelBand"] == "1.5-2.4" for s in specs), 36)
        self.assertEqual(sum(s["face"]["looksLevelBand"] == "2.5-3.2" for s in specs), 108)
        self.assertEqual(sum(s["face"]["looksLevelBand"] == "3.3-3.8" for s in specs), 72)
        self.assertEqual(sum(s["face"]["looksLevelBand"] == "3.9-4.3" for s in specs), 24)
        self.assertEqual(sum(s["face"]["looksLevelBand"] == "4.4-5.0" for s in specs), 0)


if __name__ == "__main__":
    unittest.main()
