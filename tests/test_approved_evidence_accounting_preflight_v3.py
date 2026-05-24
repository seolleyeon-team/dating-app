import json
import tempfile
import unittest
from pathlib import Path

from tests.ai_image_strict_fixture import make_png, write_identity_fixture


SHOT_ORDER = ("face_card", "silhouette_card", "vibe_card")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _write_receipts(root: Path, rows: list[dict], *, file_qa_passed: bool = True) -> None:
    tx_dir = root / "ai_image" / "reports" / "chunks" / "archived_chunk" / "transactions"
    tx_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        raw = root / "ai_image" / "raw" / f"{row['assetId']}__attempt01.png"
        make_png(raw)
        payload = {
            "schemaVersion": "seolleyeon_one_asset_transaction_v3",
            "chunkId": "archived_chunk",
            "assetId": row["assetId"],
            "profileId": row["profileId"],
            "gender": row["gender"],
            "numericId": row["numericId"],
            "shotType": row["shotType"],
            "attempt": 1,
            "fileQaPassed": file_qa_passed,
            "rawPath": str(raw),
            "finalPath": row["finalPath"],
            "fileQa": {"decision": "file_passed" if file_qa_passed else "file_rejected", "reasons": []},
            "status": "succeeded" if file_qa_passed else "failed",
        }
        (tx_dir / f"{row['assetId']}_attempt1.json").write_text(json.dumps(payload), encoding="utf-8")


def _evidence(root: Path) -> dict:
    from scripts.ai_image_pipeline_v3.approval_evidence import evaluate_approved_identity_evidence

    return evaluate_approved_identity_evidence(root=root)


def _distribution(root: Path) -> dict:
    from scripts.ai_image_pipeline_v3.distribution_audit import audit_distribution

    return audit_distribution(root=root, write_outputs=False)


def _completion(root: Path) -> dict:
    from scripts.ai_image_pipeline_v3.completion import completion_check

    return completion_check(root=root)


class ApprovedEvidenceAccountingPreflightV3Tests(unittest.TestCase):
    def test_completion_counts_archived_approved_identity_from_transaction_receipts_without_current_chunk_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)

            result = _completion(root)

            self.assertEqual(result["approvedCompleteIdentities"], 1)
            self.assertEqual(result["approvedImages"], 3)
            self.assertNotIn("approved_asset_missing_file_qa", result["failureReasons"])

    def test_distribution_counts_same_archived_approved_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)

            result = _distribution(root)

            self.assertEqual(result["approvedCompleteIdentityCount"], 1)
            self.assertEqual(result["approvedImageCount"], 3)

    def test_completion_and_distribution_agree_on_approved_identity_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)

            completion = _completion(root)
            distribution = _distribution(root)

            self.assertEqual(completion["approvedCompleteIdentities"], distribution["approvedCompleteIdentityCount"])
            self.assertEqual(completion["approvedImages"], distribution["approvedImageCount"])

    def test_missing_file_qa_manifest_does_not_block_valid_receipt_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)

            result = _evidence(root)

            self.assertEqual(len(result["validIdentities"]), 1)
            sources = [asset["source"] for asset in _asset_evidence_rows(root, rows)]
            self.assertEqual(sources, ["transaction_receipt", "transaction_receipt", "transaction_receipt"])

    def test_stale_file_qa_manifest_missing_entry_does_not_override_receipt_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)
            _write_jsonl(
                root / "ai_image" / "manifests" / "file_qa_manifest.jsonl",
                [{"assetId": "unrelated__face_card__v001", "status": "file_qa_failed"}],
            )

            result = _evidence(root)

            self.assertEqual(len(result["validIdentities"]), 1)

    def test_explicit_failed_file_qa_manifest_conflict_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)
            _write_jsonl(
                root / "ai_image" / "manifests" / "file_qa_manifest.jsonl",
                [{"assetId": rows[0]["assetId"], "status": "file_qa_failed", "decision": "file_qa_failed"}],
            )

            result = _evidence(root)

            self.assertEqual(result["validIdentities"], [])
            self.assertIn("file_qa_evidence_conflict", result["invalidApprovedAssets"][0]["reasons"])

    def test_final_file_missing_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)
            Path(rows[0]["finalPath"]).unlink()

            result = _evidence(root)

            self.assertEqual(result["validIdentities"], [])
            self.assertIn("final_file_missing", result["invalidApprovedAssets"][0]["reasons"])

    def test_final_file_not_decodable_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)
            Path(rows[0]["finalPath"]).write_text("not a png", encoding="utf-8")

            result = _evidence(root)

            self.assertEqual(result["validIdentities"], [])
            self.assertIn("final_file_not_decodable", result["invalidApprovedAssets"][0]["reasons"])

    def test_prompt_hash_mismatch_rejects(self):
        self._generation_mutation_rejects("promptHash", "wrong_hash", "prompt_hash_mismatch")

    def test_prompt_targeting_version_mismatch_rejects(self):
        self._generation_mutation_rejects("promptTargetingVersion", "face_type_looks_level_targeting_v0", "prompt_targeting_version_mismatch")

    def _generation_mutation_rejects(self, key: str, value: str, expected_reason: str) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)
            generation_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            generation_rows = [json.loads(line) for line in generation_path.read_text(encoding="utf-8").splitlines()]
            generation_rows[0][key] = value
            _write_jsonl(generation_path, generation_rows)

            result = _evidence(root)

            self.assertEqual(result["validIdentities"], [])
            self.assertIn(expected_reason, result["invalidApprovedAssets"][0]["reasons"])

    def test_asset_qa_needs_review_or_rejected_rejects(self):
        for decision, reason in (("needs_review", "needs_review_counted"), ("rejected", "rejected_counted")):
            with self.subTest(decision=decision):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    rows = write_identity_fixture(root, write_file_qa=False, asset_decision=decision)
                    _write_receipts(root, rows)

                    result = _evidence(root)

                    self.assertEqual(result["validIdentities"], [])
                    self.assertIn(reason, result["invalidApprovedIdentities"][0]["reasons"])

    def test_identity_qa_missing_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False, write_identity_qa=False)
            _write_receipts(root, rows)

            result = _evidence(root)

            self.assertEqual(result["validIdentities"], [])
            self.assertIn("approved_identity_missing_identity_qa", result["invalidApprovedIdentities"][0]["reasons"])

    def test_less_than_3_approved_shots_triggers_only_for_real_missing_or_invalid_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False, omit_asset_qa_shots={"vibe_card"})
            _write_receipts(root, rows)

            result = _evidence(root)

            self.assertEqual(result["validIdentities"], [])
            self.assertIn("less_than_3_approved_shots", result["invalidApprovedIdentities"][0]["reasons"])
            self.assertTrue(any(asset["shotType"] == "vibe_card" for asset in result["invalidApprovedAssets"]))

    def test_memory_safe_targeted_generation_manifest_scan_includes_needed_approved_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            generation_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            generation_rows = [json.loads(line) for line in generation_path.read_text(encoding="utf-8").splitlines()]
            noise = [{"assetId": f"noise_{i}", "status": "file_qa_passed"} for i in range(200)]
            _write_jsonl(generation_path, noise + generation_rows)

            result = _evidence(root)

            self.assertEqual(len(result["validIdentities"]), 1)

    def test_generation_manifest_file_qa_passed_evidence_counts_when_manifest_and_receipts_are_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, write_file_qa=False)

            result = _evidence(root)

            self.assertEqual(len(result["validIdentities"]), 1)
            self.assertEqual(result["validIdentities"][0]["approvedShotCount"], 3)

    def test_current_chunk_state_fallback_still_works_for_active_current_chunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False, write_generation_manifest=False)
            state_path = root / "ai_image" / "manifests" / "current_chunk_state.json"
            state_path.write_text(json.dumps({"assetStates": {row["assetId"]: "file_qa_passed" for row in rows}}), encoding="utf-8")

            result = _evidence(root)

            self.assertEqual(len(result["validIdentities"]), 1)


def _asset_evidence_rows(root: Path, rows: list[dict]) -> list[dict]:
    from scripts.ai_image_pipeline_v3.approval_evidence import resolve_file_qa_evidence

    generation_by_asset = {row["assetId"]: row for row in rows}
    asset_by_asset = {row["assetId"]: row for row in rows}
    return [
        resolve_file_qa_evidence(
            root,
            row["assetId"],
            active_asset=asset_by_asset[row["assetId"]],
            generation_row=generation_by_asset[row["assetId"]],
            expected_profile_id=row["profileId"],
            expected_shot_type=row["shotType"],
        )
        for row in rows
    ]


if __name__ == "__main__":
    unittest.main()
