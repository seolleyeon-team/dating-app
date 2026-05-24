import json
import tempfile
import unittest
from pathlib import Path

from tests.ai_image_strict_fixture import write_identity_fixture


class VisualQaApplyStrictV3Tests(unittest.TestCase):
    def _asset_payload(self, rows: list[dict], *, checked: int | None = None, asset_id_override: str | None = None) -> dict:
        payload = {
            "qaType": "seolleyeon_visual_verdict_asset_v3",
            "sheetId": "unit",
            "assets": [
                {
                    "assetId": asset_id_override or row["assetId"],
                    "profileId": row["profileId"],
                    "gender": row["gender"],
                    "shotType": row["shotType"],
                    "targetFaceType": "deer_like",
                    "observedFaceType": "deer_like",
                    "faceTypeConfidence": 0.9,
                    "targetLooksLevelBand": "2.5-3.2",
                    "observedLooksLevelBand": "2.5-3.2",
                    "looksLevelConfidence": 0.9,
                    "adultVisual": True,
                    "photoRealism": 4.4,
                    "brandFit": 4.4,
                    "shotTypeReadable": True,
                    "metadataMismatch": False,
                    "decision": "approved",
                }
                for row in rows
            ],
        }
        if checked is not None:
            payload["checked"] = checked
        return payload

    def _identity_payload(self, *, profile_id: str = "female_001", decision: str = "approved", looks_band: str = "2.5-3.2", asset_decisions: dict | None = None) -> dict:
        asset_ids = {shot: f"{profile_id}__{shot}__v001" for shot in ("face_card", "silhouette_card", "vibe_card")}
        return {
            "qaType": "seolleyeon_visual_verdict_identity_v3",
            "checked": 1,
            "identities": [
                {
                    "profileId": profile_id,
                    "gender": profile_id.split("_", 1)[0],
                    "targetFaceType": "deer_like",
                    "observedFaceType": "deer_like",
                    "targetLooksLevelBand": "2.5-3.2",
                    "observedLooksLevelBand": looks_band,
                    "assetIds": asset_ids,
                    "assetDecisions": asset_decisions or {shot: "approved" for shot in asset_ids},
                    "faceToSilhouetteConsistency": 4.2,
                    "faceToVibeConsistency": 4.2,
                    "sameIdentity": True,
                    "completeIdentityDecision": decision,
                    "countsTowardDistribution": True,
                }
            ],
        }

    def _write_payload(self, root: Path, name: str, payload: dict) -> Path:
        path = root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_checked_zero_and_missing_nested_schemas_are_rejected(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_asset_qa, apply_identity_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_asset_qa=False, write_identity_qa=False, write_approved_manifest=False)
            with self.assertRaises(ValueError):
                apply_asset_qa(root=root, input_path=str(self._write_payload(root, "asset_zero.json", self._asset_payload(rows, checked=0))))
            with self.assertRaises(ValueError):
                apply_asset_qa(root=root, input_path=str(self._write_payload(root, "asset_missing.json", {"qaType": "seolleyeon_visual_verdict_asset_v3", "checked": 1})))
            with self.assertRaises(ValueError):
                apply_identity_qa(root=root, input_path=str(self._write_payload(root, "identity_missing.json", {"qaType": "seolleyeon_visual_verdict_identity_v3", "checked": 1})))

    def test_unknown_or_mismatched_asset_id_is_rejected(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_asset_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_asset_qa=False, write_identity_qa=False, write_approved_manifest=False)

            with self.assertRaises(ValueError):
                apply_asset_qa(root=root, input_path=str(self._write_payload(root, "asset_unknown.json", self._asset_payload(rows[:1], asset_id_override="female_999__face_card__v001"))))

    def test_asset_qa_does_not_create_identity_approval(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_asset_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_asset_qa=False, write_identity_qa=False, write_approved_manifest=False)

            result = apply_asset_qa(root=root, input_path=str(self._write_payload(root, "asset.json", self._asset_payload(rows))))

            self.assertEqual(result["approved"], 3)
            self.assertFalse((root / "ai_image" / "manifests" / "approved_identity_manifest.jsonl").exists())

    def test_identity_qa_requires_all_asset_qa_final_files_and_file_qa(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, omit_asset_qa_shots={"vibe_card"}, write_identity_qa=False, write_approved_manifest=False)
            result = apply_identity_qa(root=root, input_path=str(self._write_payload(root, "identity.json", self._identity_payload())))
            self.assertEqual(result["approved"], 0)
            self.assertEqual(result["needs_review"], 1)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, make_files=False, write_identity_qa=False, write_approved_manifest=False)
            result = apply_identity_qa(root=root, input_path=str(self._write_payload(root, "identity.json", self._identity_payload())))
            self.assertEqual(result["approved"], 0)
            self.assertEqual(result["needs_review"], 1)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, write_file_qa=False, write_identity_qa=False, write_approved_manifest=False)
            result = apply_identity_qa(root=root, input_path=str(self._write_payload(root, "identity.json", self._identity_payload())))
            self.assertEqual(result["approved"], 0)
            self.assertEqual(result["needs_review"], 1)

    def test_metadata_mismatch_and_overlevel_are_not_approved(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, metadata_mismatch=True, write_identity_qa=False, write_approved_manifest=False)
            result = apply_identity_qa(root=root, input_path=str(self._write_payload(root, "identity.json", self._identity_payload())))
            self.assertEqual(result["approved"], 0)
            self.assertEqual(result["needs_review"], 1)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, looks_band="4.4-5.0", write_identity_qa=False, write_approved_manifest=False)
            result = apply_identity_qa(root=root, input_path=str(self._write_payload(root, "identity.json", self._identity_payload(looks_band="4.4-5.0"))))
            self.assertEqual(result["approved"], 0)
            self.assertEqual(result["rejected"], 1)


if __name__ == "__main__":
    unittest.main()
