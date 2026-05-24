import json
import tempfile
import unittest
from pathlib import Path

from tests.ai_image_strict_fixture import make_png, write_identity_fixture


SHOT_ORDER = ("face_card", "silhouette_card", "vibe_card")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _write_receipts(root: Path, rows: list[dict]) -> None:
    tx_dir = root / "ai_image" / "reports" / "chunks" / "chunk_unit" / "transactions"
    tx_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        raw = root / "ai_image" / "raw" / f"{row['assetId']}__attempt01.png"
        make_png(raw)
        payload = {
            "schemaVersion": "seolleyeon_one_asset_transaction_v3",
            "chunkId": "chunk_unit",
            "assetId": row["assetId"],
            "profileId": row["profileId"],
            "gender": row["gender"],
            "numericId": row["numericId"],
            "shotType": row["shotType"],
            "attempt": 1,
            "generated": True,
            "recovered": True,
            "pendingResolved": True,
            "fileQaRan": True,
            "fileQaPassed": True,
            "rawPath": str(raw),
            "finalPath": row["finalPath"],
            "fileQa": {"decision": "file_passed", "reasons": []},
            "status": "succeeded",
        }
        (tx_dir / f"{row['assetId']}_attempt1.json").write_text(json.dumps(payload), encoding="utf-8")


def _audit(root: Path) -> dict:
    from scripts.ai_image_pipeline_v3.approval_evidence import evaluate_approved_identity_evidence

    return evaluate_approved_identity_evidence(root=root)


class ApprovedEvidencePersistenceV3Tests(unittest.TestCase):
    def test_approved_identity_counts_without_current_chunk_state_from_transaction_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)

            result = _audit(root)

            self.assertEqual([row["profileId"] for row in result["validIdentities"]], ["female_001"])
            self.assertEqual(result["validIdentities"][0]["approvedShotCount"], 3)

    def test_file_qa_only_assets_do_not_count_without_visual_identity_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_identity_qa=False, write_approved_manifest=False)
            _write_jsonl(
                root / "ai_image" / "manifests" / "approved_identity_manifest.jsonl",
                [
                    {
                        "profileId": "female_001",
                        "gender": "female",
                        "numericId": "001",
                        "assetIds": {row["shotType"]: row["assetId"] for row in rows},
                    }
                ],
            )

            result = _audit(root)

            self.assertEqual(result["validIdentities"], [])
            self.assertIn("approved_identity_missing_identity_qa", result["invalidApprovedIdentities"][0]["reasons"])

    def test_missing_final_file_rejects_transaction_receipt_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)
            Path(rows[0]["finalPath"]).unlink()

            result = _audit(root)

            self.assertEqual(result["validIdentities"], [])
            self.assertIn("final_file_missing", result["invalidApprovedAssets"][0]["reasons"])

    def test_prompt_hash_and_version_mismatch_reject(self):
        for key, value, reason in (
            ("promptHash", "stale_hash", "prompt_hash_mismatch"),
            ("promptTargetingVersion", "old_version", "prompt_targeting_version_mismatch"),
        ):
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    rows = write_identity_fixture(root, write_file_qa=False)
                    _write_receipts(root, rows)
                    gen_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
                    gen_rows = [json.loads(line) for line in gen_path.read_text(encoding="utf-8").splitlines()]
                    gen_rows[0][key] = value
                    _write_jsonl(gen_path, gen_rows)

                    result = _audit(root)

                    self.assertEqual(result["validIdentities"], [])
                    self.assertIn(reason, result["invalidApprovedAssets"][0]["reasons"])

    def test_asset_qa_rejected_and_identity_qa_missing_reject(self):
        cases = [
            {"asset_decision": "rejected", "expected": "rejected_counted"},
            {"write_identity_qa": False, "expected": "approved_identity_missing_identity_qa"},
        ]
        for case in cases:
            with self.subTest(case=case):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    kwargs = {k: v for k, v in case.items() if k != "expected"}
                    rows = write_identity_fixture(root, write_file_qa=False, **kwargs)
                    _write_receipts(root, rows)

                    result = _audit(root)

                    self.assertEqual(result["validIdentities"], [])
                    self.assertIn(case["expected"], result["invalidApprovedIdentities"][0]["reasons"])

    def test_current_chunk_state_fallback_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            state = {"assetStates": {row["assetId"]: "file_qa_passed" for row in rows}}
            state_path = root / "ai_image" / "manifests" / "current_chunk_state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = _audit(root)

            self.assertEqual(len(result["validIdentities"]), 1)

    def test_manifest_conflict_rejects_even_with_transaction_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False)
            _write_receipts(root, rows)
            _write_jsonl(
                root / "ai_image" / "manifests" / "file_qa_manifest.jsonl",
                [{"assetId": rows[0]["assetId"], "status": "file_qa_failed", "decision": "file_qa_failed"}],
            )

            result = _audit(root)

            self.assertEqual(result["validIdentities"], [])
            self.assertIn("file_qa_evidence_conflict", result["invalidApprovedAssets"][0]["reasons"])


if __name__ == "__main__":
    unittest.main()
