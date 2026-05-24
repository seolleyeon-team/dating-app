import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET_PROMPT = ROOT / "ai_image" / "prompts" / "VISUAL_VERDICT_ASSET_QA_PROMPT.md"
IDENTITY_PROMPT = ROOT / "ai_image" / "prompts" / "VISUAL_VERDICT_IDENTITY_QA_PROMPT.md"


class VisualVerdictFaceTypeTaxonomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.asset_text = ASSET_PROMPT.read_text(encoding="utf-8")
        cls.identity_text = IDENTITY_PROMPT.read_text(encoding="utf-8")
        cls.all_text = (cls.asset_text + "\n" + cls.identity_text).lower()

    def test_fox_like_not_automatically_high_attractiveness(self):
        self.assertIn("not necessarily highly attractive", self.all_text)
        self.assertIn("not automatically 3.3-3.8", self.asset_text)
        self.assertIn("should not be upgraded in looks level just because the photo is clean", self.identity_text)

    def test_fox_like_distinguished_from_dog_like_warmth(self):
        self.assertIn("dog_like` warmth/open puppy-like approachability", self.asset_text)
        self.assertIn("warm/open/puppy-like approachability", self.identity_text)
        self.assertIn("do not use `dog_like` for a restrained composed face", self.asset_text.lower())

    def test_fox_like_distinguished_from_hamster_like_compact_cuteness(self):
        self.assertIn("hamster_like` compact rounded cuteness", self.asset_text)
        self.assertIn("compact rounded cute softness", self.identity_text)
        self.assertIn("do not use `hamster_like` for a non-compact composed face", self.asset_text.lower())

    def test_mixed_neutral_not_used_when_subtle_fox_cues_visible(self):
        self.assertIn("do not classify as `mixed_neutral` merely because the cues are understated", self.asset_text)
        self.assertIn("do not use it merely because fox_like cues are understated but visible", self.identity_text)

    def test_looks_level_not_upgraded_solely_due_clean_lighting(self):
        self.assertIn("do not upgrade solely because image quality, lighting, or styling is clean", self.asset_text)
        self.assertIn("not merely because the photo is sharp, neat, or well exposed", self.asset_text)

    def test_metadata_mismatch_remains_strict_for_confident_mismatch(self):
        self.assertIn("keep mismatch rejection strict for confident visual evidence", self.asset_text)
        self.assertIn("targetFaceType` differs from `observedFaceType` and `faceTypeConfidence >= 0.70", self.asset_text)
        self.assertIn("targetLooksLevelBand` differs from `observedLooksLevelBand` and `looksLevelConfidence >= 0.70", self.asset_text)

    def test_eyewear_target_observed_fields_still_present(self):
        for field in (
            "targetHasEyewear",
            "targetEyewearGroup",
            "targetEyewear",
            "targetCanonicalEyewear",
            "targetShotEyewearExpected",
            "observedHasEyewear",
            "observedEyewearGroup",
            "observedEyewear",
        ):
            self.assertIn(field, self.asset_text)
        for field in (
            "targetHasEyewear",
            "targetEyewearGroup",
            "targetEyewear",
            "targetCanonicalEyewear",
            "targetShotEyewearExpected",
            "observedEyewearConsistency",
            "eyewearMismatchReason",
        ):
            self.assertIn(field, self.identity_text)

    def test_no_out_of_scope_rows_accepted_by_runner_guard(self):
        runner = (ROOT / "scripts" / "ai_image_pipeline_v3" / "active_visual_verdict_runner.py").read_text(encoding="utf-8")
        self.assertIn("mark_latest_asset_qa_invalid_if_out_of_scope", runner)
        self.assertIn("validate_identity_payload_scope", runner)
        self.assertIn("out_of_scope", runner)


if __name__ == "__main__":
    unittest.main()
