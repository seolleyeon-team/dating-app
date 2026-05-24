import tempfile
import unittest
from pathlib import Path

from tests.ai_image_strict_fixture import identity_asset_rows, make_png, write_identity_fixture, write_small_targets


class DistributionAuditFileBackedV3Tests(unittest.TestCase):
    def _audit(self, root: Path) -> dict:
        from scripts.ai_image_pipeline_v3.distribution_audit import audit_distribution

        return audit_distribution(root=root, write_outputs=False)

    def test_counts_only_file_backed_qa_backed_complete_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root)

            audit = self._audit(root)

            self.assertTrue(audit["passed"], audit["failConditions"])
            self.assertEqual(audit["approvedCompleteIdentities"], 1)
            self.assertEqual(audit["approvedImages"], 3)

    def test_fabricated_approved_manifest_is_excluded_when_final_files_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, make_files=False, write_asset_manifest=False, write_generation_manifest=False, write_file_qa=False, write_asset_qa=False, write_identity_qa=False)

            audit = self._audit(root)

            self.assertFalse(audit["passed"])
            self.assertEqual(audit["approvedCompleteIdentities"], 0)
            self.assertEqual(audit["approvedManifestRowsExcluded"], 1)
            self.assertIn("approved_manifest_missing_file_backing", audit["failConditions"])

    def test_generated_only_and_file_qa_only_assets_are_excluded(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.manifest import write_generation_outputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_small_targets(root)
            rows = identity_asset_rows(root)
            for row in rows:
                make_png(Path(row["finalPath"]))
            paths = pipeline_paths(root)
            write_generation_outputs(paths, rows)
            write_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl", rows)

            generated_only = self._audit(root)
            self.assertEqual(generated_only["approvedCompleteIdentities"], 0)

            write_jsonl(
                paths.manifests / "file_qa_manifest.jsonl",
                [{"assetId": row["assetId"], "status": "file_qa_passed", "decision": "file_qa_passed"} for row in rows],
            )
            file_qa_only = self._audit(root)
            self.assertEqual(file_qa_only["approvedCompleteIdentities"], 0)

    def test_stale_visual_distribution_apply_does_not_force_manual_review_after_identity_reapply(self):
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root)
            visual_dir = root / "ai_image" / "reports" / "visual_verdict"
            visual_dir.mkdir(parents=True, exist_ok=True)
            (visual_dir / "distribution_audit_apply.json").write_text(
                json.dumps(
                    {
                        "schemaVersion": "seolleyeon_visual_distribution_audit_apply_v3",
                        "visualAudit": {
                            "qaType": "seolleyeon_visual_verdict_distribution_v3",
                            "approvedCompleteIdentityCount": 0,
                            "approvedImageCount": 0,
                            "femaleApprovedIdentityCount": 0,
                            "maleApprovedIdentityCount": 0,
                        },
                        "needsManualReview": True,
                        "disagreements": ["approvedCompleteIdentityCount"],
                    }
                ),
                encoding="utf-8",
            )

            audit = self._audit(root)

            self.assertEqual(audit["approvedCompleteIdentities"], 1)
            self.assertNotIn("python_visual_distribution_audit_disagree", audit["failConditions"])
            self.assertEqual("", audit["visualDistributionAuditPath"])
            self.assertEqual(["visual_distribution_audit_stale_after_identity_reapply"], audit["visualDistributionAuditIgnoredReasons"])

    def test_incomplete_metadata_mismatch_needs_review_rejected_and_overlevel_are_excluded(self):
        cases = [
            {"omit_asset_qa_shots": {"vibe_card"}},
            {"metadata_mismatch": True},
            {"asset_decision": "needs_review"},
            {"asset_decision": "rejected"},
            {"looks_band": "4.4-5.0"},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    write_identity_fixture(root, **kwargs)

                    audit = self._audit(root)

                    self.assertFalse(audit["passed"])
                    self.assertEqual(audit["approvedCompleteIdentities"], 0)
                    self.assertTrue(audit["invalidApprovedIdentities"], audit)


if __name__ == "__main__":
    unittest.main()
