import json
import tempfile
import unittest
from pathlib import Path

from tests.ai_image_strict_fixture import make_png, write_identity_fixture, write_small_targets


class AiImageCompletionStrictV3Tests(unittest.TestCase):
    def _completion(self, root: Path) -> dict:
        from scripts.ai_image_pipeline_v3.completion import completion_check

        return completion_check(root=root)

    def test_passes_only_with_exact_file_and_qa_backed_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root)

            result = self._completion(root)

            self.assertTrue(result["passed"], result["failureReasons"])
            self.assertEqual(result["approvedCompleteIdentities"], 1)
            self.assertEqual(result["approvedImages"], 3)

    def test_fabricated_approved_manifest_without_files_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, make_files=False, write_asset_manifest=False, write_generation_manifest=False, write_file_qa=False, write_asset_qa=False, write_identity_qa=False)

            result = self._completion(root)

            self.assertFalse(result["passed"])
            self.assertIn("approved_identity_missing_final_file", result["failureReasons"])
            self.assertIn("approved_asset_not_in_asset_manifest", result["failureReasons"])
            self.assertIn("approved_asset_missing_file_qa", result["failureReasons"])

    def test_final_files_without_any_file_qa_evidence_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, write_file_qa=False)
            gen_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            gen_rows = [json.loads(line) for line in gen_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            for row in gen_rows:
                row["status"] = "planned"
            gen_path.write_text("".join(json.dumps(row) + "\n" for row in gen_rows), encoding="utf-8")

            result = self._completion(root)

            self.assertFalse(result["passed"])
            self.assertIn("approved_asset_missing_file_qa", result["failureReasons"])

    def test_asset_qa_without_identity_qa_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, write_identity_qa=False)

            result = self._completion(root)

            self.assertFalse(result["passed"])
            self.assertIn("approved_identity_missing_identity_qa", result["failureReasons"])

    def test_manual_review_flag_blocks_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root)
            flag = root / "ai_image" / "manifests" / "manual_review_required.flag"
            flag.write_text(json.dumps({"reason": "operator_review"}), encoding="utf-8")

            result = self._completion(root)

            self.assertFalse(result["passed"])
            self.assertIn("manual_review_required", result["failureReasons"])

    def test_unresolved_pending_imagegen_blocks_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root)
            pending = root / "ai_image" / "manifests" / "pending-imagegen.json"
            pending.write_text(json.dumps({"status": "pending_imagegen", "assetId": "female_001__face_card__v001"}), encoding="utf-8")

            result = self._completion(root)

            self.assertFalse(result["passed"])
            self.assertIn("unresolved_pending_imagegen", result["failureReasons"])

    def test_needs_manual_review_chunk_blocks_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root)
            manifests = root / "ai_image" / "manifests"
            (manifests / "current_chunk_plan.json").write_text(
                json.dumps({"chunkId": "chunk_test", "status": "needs_manual_review", "executable": False, "dryRun": False}),
                encoding="utf-8",
            )
            (manifests / "current_chunk_state.json").write_text(
                json.dumps(
                    {
                        "chunkId": "chunk_test",
                        "status": "needs_manual_review",
                        "assetStates": {"female_001__face_card__v001": "file_qa_passed"},
                        "activeVisualQaComplete": False,
                        "distributionAuditComplete": False,
                    }
                ),
                encoding="utf-8",
            )

            result = self._completion(root)

            self.assertFalse(result["passed"])
            self.assertIn("stale_current_chunk_plan", result["failureReasons"])
            self.assertIn("non_executable_current_chunk", result["failureReasons"])
            self.assertIn("active_visual_qa_incomplete", result["failureReasons"])
            self.assertIn("distribution_audit_incomplete", result["failureReasons"])

    def test_raw_or_final_file_counts_alone_never_satisfy_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_small_targets(root)
            make_png(root / "ai_image" / "female" / "001" / "face_card.png")
            make_png(root / "ai_image" / "female" / "001" / "silhouette_card.png")
            make_png(root / "ai_image" / "female" / "001" / "vibe_card.png")
            make_png(root / "ai_image" / "raw" / "female_001__face_card__v001__attempt01.png")

            result = self._completion(root)

            self.assertFalse(result["passed"])
            self.assertIn("missing_asset_qa_manifest", result["failureReasons"])
            self.assertIn("missing_identity_qa_manifest", result["failureReasons"])
            self.assertIn("missing_approved_identity_manifest", result["failureReasons"])

    def test_stale_identity_qa_count_flag_is_not_counted_without_approved_manifest(self):
        from scripts.ai_image_pipeline_v3.config import write_jsonl

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_approved_manifest=False, metadata_mismatch=True)
            manifests = root / "ai_image" / "manifests"
            identity_rows = [
                {
                    "profileId": "female_001",
                    "gender": "female",
                    "assetIds": {row["shotType"]: row["assetId"] for row in rows},
                    "assetDecisions": {row["shotType"]: "approved" for row in rows},
                    "completeIdentityDecision": "approved",
                    "finalCompleteIdentityDecision": "approved",
                    "countsTowardDistribution": True,
                    "sameIdentity": True,
                    "metadataMismatch": False,
                }
            ]
            asset_rows = []
            for row in rows:
                asset_rows.append(
                    {
                        "assetId": row["assetId"],
                        "profileId": row["profileId"],
                        "gender": row["gender"],
                        "shotType": row["shotType"],
                        "targetFaceType": row["targetFaceType"],
                        "observedFaceType": row["targetFaceType"],
                        "targetLooksLevelBand": row["targetLooksLevelBand"],
                        "observedLooksLevelBand": row["targetLooksLevelBand"],
                        "finalDecision": "approved",
                        "decision": "approved",
                        "status": "vision_approved",
                        "metadataMismatch": row["shotType"] == "face_card",
                    }
                )
            write_jsonl(manifests / "identity_qa_manifest.jsonl", identity_rows)
            write_jsonl(manifests / "asset_qa_manifest.jsonl", asset_rows)
            (manifests / "approved_identity_manifest.jsonl").write_text("", encoding="utf-8")

            result = self._completion(root)

            self.assertFalse(result["passed"])
            self.assertNotIn("approved_identity_missing_identity_qa", result["failureReasons"])
            self.assertIn("distribution_mismatch", result["failureReasons"])


if __name__ == "__main__":
    unittest.main()
