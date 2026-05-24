import unittest
from pathlib import Path


class IdentityQaVibeSamePersonRubricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prompt_path = Path(__file__).resolve().parents[1] / "ai_image" / "prompts" / "VISUAL_VERDICT_IDENTITY_QA_PROMPT.md"
        cls.prompt = cls.prompt_path.read_text(encoding="utf-8").lower()

    def test_emphasizes_core_facial_anchors(self):
        for phrase in (
            "core facial anchors",
            "face shape",
            "eye impression",
            "nose-mouth balance",
            "skin tone",
            "broad hairstyle/hair volume",
            "grooming",
            "canonical eyewear/no-eyewear state",
        ):
            self.assertIn(phrase, self.prompt)

    def test_expression_variation_alone_is_not_identity_mismatch(self):
        self.assertIn("normal expression, gaze, pose, crop, clothing, or activity variation is acceptable", self.prompt)
        self.assertIn("not against identical expression or identical styling", self.prompt)

    def test_far_small_hidden_face_stays_rejectable(self):
        self.assertIn("too small/far to compare", self.prompt)
        self.assertIn("hidden", self.prompt)
        self.assertIn("face_too_small_for_identity_match", self.prompt)
        self.assertIn("face_hidden_for_identity_match", self.prompt)

    def test_file_qa_needs_review_not_emitted_when_evidence_valid(self):
        self.assertIn("do not invent `file_qa_needs_review`", self.prompt)
        self.assertIn("file qa is valid/passed/approved", self.prompt)
        self.assertIn("use file-qa reasons only when", self.prompt)

    def test_same_identity_threshold_remains_strict(self):
        self.assertIn("approved` only if `faceto-vibeconsistency >= 3.8`".replace("-", ""), self.prompt.replace("-", ""))
        self.assertIn("rejected` if `facetovibeconsistency < 3.8`".replace("-", ""), self.prompt.replace("-", ""))
        self.assertIn("do not be generous", self.prompt)


if __name__ == "__main__":
    unittest.main()
