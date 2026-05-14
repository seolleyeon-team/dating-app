import json
import hashlib
import tempfile
import unittest
from pathlib import Path


class OneAssetTransactionV3Tests(unittest.TestCase):
    def _image(self, path: Path) -> None:
        from PIL import Image

        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (512, 768), (30, 60, 90)).save(path)

    def _expected(self, root: Path) -> dict:
        raw = root / "ai_image" / "raw" / "female_001__face_card__v001__attempt01.png"
        final = root / "ai_image" / "female" / "001" / "face_card.png"
        return {
            "chunkId": "chunk_test",
            "assetId": "female_001__face_card__v001",
            "profileId": "female_001",
            "gender": "female",
            "numericId": "001",
            "shotType": "face_card",
            "attempt": 1,
            "expectedRawPath": str(raw),
            "expectedFinalPath": str(final),
        }

    def _receipt(self, root: Path, **overrides) -> dict:
        expected = self._expected(root)
        receipt = {
            "schemaVersion": "seolleyeon_one_asset_transaction_v3",
            "transactionId": "chunk_test_female_001__face_card__v001_attempt1",
            "chunkId": expected["chunkId"],
            "assetId": expected["assetId"],
            "profileId": expected["profileId"],
            "gender": expected["gender"],
            "numericId": expected["numericId"],
            "shotType": expected["shotType"],
            "attempt": expected["attempt"],
            "startedAt": "2026-05-10T00:00:00+00:00",
            "finishedAt": "2026-05-10T00:00:10+00:00",
            "generated": True,
            "recovered": True,
            "pendingResolved": True,
            "fileQaRan": True,
            "fileQaPassed": True,
            "rawPath": expected["expectedRawPath"],
            "finalPath": expected["expectedFinalPath"],
            "sourceGeneratedImagePath": "",
            "referencePath": None,
            "fileQa": {"decision": "file_passed", "width": 512, "height": 768, "format": "PNG", "aspectRatio": 0.6667, "sizeBytes": 1000, "reasons": []},
            "workerActions": ["imagegen_called", "recovered_to_raw", "copied_to_final", "pending_resolved", "file_qa_ran"],
            "stdoutLog": "",
            "stderrLog": "",
            "error": None,
            "status": "succeeded",
        }
        receipt.update(overrides)
        return receipt

    def _write_receipt(self, root: Path, payload: dict) -> Path:
        from scripts.ai_image_pipeline_v3.one_asset_transaction import transaction_receipt_path

        path = transaction_receipt_path(root, payload["chunkId"], payload["assetId"], int(payload["attempt"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_valid_receipt_verifies(self):
        from scripts.ai_image_pipeline_v3.one_asset_transaction import verify_one_asset_transaction

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = self._expected(root)
            self._image(Path(expected["expectedRawPath"]))
            self._image(Path(expected["expectedFinalPath"]))
            receipt_path = self._write_receipt(root, self._receipt(root))
            result = verify_one_asset_transaction(root=root, receipt_path=receipt_path, expected=expected, pending_payload={**expected, "status": "resolved", "resolved": True})
            self.assertTrue(result["valid"])
            self.assertEqual(result["assetId"], expected["assetId"])

    def test_receipt_loader_accepts_utf8_bom_receipt(self):
        from scripts.ai_image_pipeline_v3.one_asset_transaction import _load_receipt

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"
            payload = self._receipt(Path(tmp))
            path.write_text(json.dumps(payload), encoding="utf-8-sig")

            self.assertEqual(_load_receipt(path), payload)

    def test_receipt_identity_path_and_file_failures_are_rejected(self):
        from scripts.ai_image_pipeline_v3.one_asset_transaction import OneAssetTransactionError, verify_one_asset_transaction

        cases = [
            {"assetId": "wrong"},
            {"chunkId": "wrong"},
            {"finalPath": "ai_image/female/999/face_card.png"},
            {"status": "failed"},
            {"visualQaApproved": True},
            {"distributionApproved": True},
        ]
        for override in cases:
            with self.subTest(override=override), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                expected = self._expected(root)
                self._image(Path(expected["expectedRawPath"]))
                self._image(Path(expected["expectedFinalPath"]))
                payload = self._receipt(root, **override)
                if override.get("assetId") == "wrong":
                    payload["assetId"] = expected["assetId"]
                    path = self._write_receipt(root, payload)
                    payload["assetId"] = "wrong"
                    path.write_text(json.dumps(payload), encoding="utf-8")
                else:
                    path = self._write_receipt(root, payload)
                with self.assertRaises(OneAssetTransactionError):
                    verify_one_asset_transaction(root=root, receipt_path=path, expected=expected, pending_payload={**expected, "status": "resolved", "resolved": True})

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = self._expected(root)
            self._image(Path(expected["expectedFinalPath"]))
            path = self._write_receipt(root, self._receipt(root))
            with self.assertRaises(OneAssetTransactionError):
                verify_one_asset_transaction(root=root, receipt_path=path, expected=expected, pending_payload={**expected, "status": "resolved", "resolved": True})

    def test_pending_mismatch_fails(self):
        from scripts.ai_image_pipeline_v3.one_asset_transaction import OneAssetTransactionError, verify_one_asset_transaction

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = self._expected(root)
            self._image(Path(expected["expectedRawPath"]))
            self._image(Path(expected["expectedFinalPath"]))
            path = self._write_receipt(root, self._receipt(root))
            with self.assertRaises(OneAssetTransactionError):
                verify_one_asset_transaction(root=root, receipt_path=path, expected=expected, pending_payload={**expected, "assetId": "other", "status": "resolved", "resolved": True})

    def test_dependent_receipt_requires_attached_reference_hash(self):
        from scripts.ai_image_pipeline_v3.one_asset_transaction import OneAssetTransactionError, verify_one_asset_transaction

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = self._expected(root)
            reference = root / "ai_image" / "female" / "001" / "face_card.png"
            expected.update({"referencePath": str(reference)})
            self._image(Path(expected["expectedRawPath"]))
            self._image(Path(expected["expectedFinalPath"]))
            self._image(reference)
            reference_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
            expected["referencePathSha256"] = reference_hash

            valid = self._receipt(root, referencePath=str(reference), referenceAttached=True, referencePathSha256=reference_hash)
            path = self._write_receipt(root, valid)
            result = verify_one_asset_transaction(root=root, receipt_path=path, expected=expected, pending_payload={**expected, "status": "resolved", "resolved": True})
            self.assertTrue(result["valid"])

            invalid = dict(valid)
            invalid["referencePathSha256"] = "wrong"
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaises(OneAssetTransactionError):
                verify_one_asset_transaction(root=root, receipt_path=path, expected=expected, pending_payload={**expected, "status": "resolved", "resolved": True})

            invalid = dict(valid)
            invalid.pop("referenceAttached")
            path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaises(OneAssetTransactionError):
                verify_one_asset_transaction(root=root, receipt_path=path, expected=expected, pending_payload={**expected, "status": "resolved", "resolved": True})

    def test_worker_prompt_boundaries(self):
        from scripts.ai_image_pipeline_v3.one_asset_transaction import build_one_asset_worker_prompt

        prompt = build_one_asset_worker_prompt(self._expected(Path(".")), reference_path="ai_image/female/001/face_card.png")
        self.assertIn("Generate exactly one image", prompt)
        self.assertIn("Recover that generated image", prompt)
        self.assertIn("Run single-asset file QA only", prompt)
        self.assertIn("do not run the global file-qa command", prompt)
        self.assertIn("Write the transaction receipt JSON", prompt)
        self.assertIn("Allowed write paths", prompt)
        self.assertIn("Do not run scripts/run_ai_image_pipeline_v3.py file-qa", prompt)
        self.assertIn("Do not run scripts/run_ai_image_pipeline_v3.py apply-visual-asset-qa", prompt)
        self.assertIn("Do not run distribution audit", prompt)
        self.assertIn("Do not run completion check", prompt)
        self.assertIn("Do not run visual QA", prompt)
        self.assertIn("Do not update approved_identity_manifest.jsonl", prompt)
        self.assertIn("Do not process any other asset", prompt)
        self.assertIn("referenceAttached=true", prompt)

    def test_forbidden_mutation_guard(self):
        from scripts.ai_image_pipeline_v3.one_asset_transaction import backup_forbidden_files, detect_forbidden_mutations, restore_forbidden_files, snapshot_forbidden_files

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed = root / "ai_image" / "raw" / "female_001__face_card__v001__attempt01.png"
            allowed.parent.mkdir(parents=True, exist_ok=True)
            qa_manifest = root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl"
            qa_manifest.parent.mkdir(parents=True, exist_ok=True)
            qa_manifest.write_text('{"schemaVersion":"seolleyeon_asset_qa_manifest_v3","assetId":"a"}\n', encoding="utf-8")
            before = snapshot_forbidden_files(root)
            backup = backup_forbidden_files(root, before, chunk_id="chunk_test", asset_id="female_001__face_card__v001", attempt=1)
            allowed.write_text("allowed", encoding="utf-8")
            self.assertEqual(detect_forbidden_mutations(root, before), [])

            state = root / "ai_image" / "manifests" / "current_chunk_state.json"
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text("changed", encoding="utf-8")
            qa_manifest.write_text('{"qaStage":"file_qa","assetId":"child"}\n', encoding="utf-8")
            violations = detect_forbidden_mutations(root, before)
            self.assertTrue(any("current_chunk_state.json" in item["path"] for item in violations))
            restore = restore_forbidden_files(root, backup, violations)
            self.assertTrue(any(item["action"] == "restored_from_backup" for item in restore["items"]))
            self.assertIn("seolleyeon_asset_qa_manifest_v3", qa_manifest.read_text(encoding="utf-8"))
            self.assertNotIn("qaStage", qa_manifest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
