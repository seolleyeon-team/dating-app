import json
import tempfile
import unittest
from pathlib import Path

from tests.ai_image_strict_fixture import write_identity_fixture


SHOT_ORDER = ("face_card", "silhouette_card", "vibe_card")


def _write_payload(root: Path, payload: dict) -> Path:
    path = root / "identity_qa_latest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _identity_payload(profile_id: str = "female_001") -> dict:
    asset_ids = {shot: f"{profile_id}__{shot}__v001" for shot in SHOT_ORDER}
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
                "observedLooksLevelBand": "2.5-3.2",
                "assetIds": asset_ids,
                "assetDecisions": {shot: "approved" for shot in SHOT_ORDER},
                "faceToSilhouetteConsistency": 4.3,
                "faceToVibeConsistency": 4.2,
                "sameIdentity": True,
                "completeIdentityDecision": "approved",
                "countsTowardDistribution": True,
            }
        ],
    }


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _write_state_file_qa_passed(root: Path, rows: list[dict]) -> None:
    state = {
        "schemaVersion": "seolleyeon_bounded_chunk_state_v3",
        "chunkId": "chunk_unit",
        "assetStates": {row["assetId"]: "file_qa_passed" for row in rows},
    }
    path = root / "ai_image" / "manifests" / "current_chunk_state.json"
    path.write_text(json.dumps(state), encoding="utf-8")


class FileQaEvidenceIdentityApplyV3Tests(unittest.TestCase):
    def test_raw_approved_passes_when_generation_manifest_has_file_qa_passed_without_file_qa_manifest_or_state(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, write_file_qa=False, write_identity_qa=False, write_approved_manifest=False)
            result = apply_identity_qa(root=root, input_path=str(_write_payload(root, _identity_payload())))
            row = _jsonl(root / "ai_image" / "manifests" / "identity_qa_manifest.jsonl")[0]

            self.assertEqual(result["approved"], 1)
            self.assertEqual(row["fileQaEvidence"]["face_card"]["source"], "generation_manifest")
            self.assertIn("file_qa_evidence_valid", row["fileQaEvidence"]["face_card"]["reasons"])

    def test_raw_approved_passes_when_file_qa_manifest_has_all_three_assets(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, write_identity_qa=False, write_approved_manifest=False)
            result = apply_identity_qa(root=root, input_path=str(_write_payload(root, _identity_payload())))
            approved = _jsonl(root / "ai_image" / "manifests" / "approved_identity_manifest.jsonl")

            self.assertEqual(result["approved"], 1)
            self.assertEqual(len(approved), 1)

    def test_current_chunk_state_only_file_qa_evidence_is_accepted_with_explicit_reason(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = write_identity_fixture(root, write_file_qa=False, write_identity_qa=False, write_approved_manifest=False)
            gen_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            gen_rows = _jsonl(gen_path)
            for gen_row in gen_rows:
                gen_row["status"] = "planned"
            _write_jsonl(gen_path, gen_rows)
            _write_state_file_qa_passed(root, rows)
            result = apply_identity_qa(root=root, input_path=str(_write_payload(root, _identity_payload())))
            row = _jsonl(root / "ai_image" / "manifests" / "identity_qa_manifest.jsonl")[0]

            self.assertEqual(result["approved"], 1)
            self.assertEqual(row["fileQaEvidence"]["face_card"]["source"], "current_chunk_state")
            self.assertIn("file_qa_found_in_state_only", row["fileQaEvidence"]["face_card"]["reasons"])
            self.assertIn("file_qa_evidence_valid", row["fileQaEvidence"]["face_card"]["reasons"])

    def test_file_qa_evidence_final_path_mismatch_fails(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, write_identity_qa=False, write_approved_manifest=False)
            gen_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            rows = _jsonl(gen_path)
            rows[0]["finalPath"] = str(root / "ai_image" / "female" / "001" / "wrong.png")
            _write_jsonl(gen_path, rows)
            result = apply_identity_qa(root=root, input_path=str(_write_payload(root, _identity_payload())))
            row = _jsonl(root / "ai_image" / "manifests" / "identity_qa_manifest.jsonl")[0]

            self.assertEqual(result["approved"], 0)
            self.assertIn("final_path_mismatch:face_card", row["needsReviewReasons"])

    def test_prompt_version_and_hash_mismatches_fail(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        for key, value, reason in (
            ("promptTargetingVersion", "old_prompt_targeting", "prompt_targeting_version_mismatch:face_card"),
            ("promptHash", "stale_hash", "prompt_hash_mismatch:face_card"),
        ):
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    write_identity_fixture(root, write_identity_qa=False, write_approved_manifest=False)
                    gen_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
                    rows = _jsonl(gen_path)
                    rows[0][key] = value
                    _write_jsonl(gen_path, rows)
                    result = apply_identity_qa(root=root, input_path=str(_write_payload(root, _identity_payload())))
                    row = _jsonl(root / "ai_image" / "manifests" / "identity_qa_manifest.jsonl")[0]

                    self.assertEqual(result["approved"], 0)
                    self.assertIn(reason, row["needsReviewReasons"])

    def test_identity_apply_uses_applied_asset_final_decision_not_raw_identity_claim(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(
                root,
                write_identity_qa=False,
                write_approved_manifest=False,
                omit_asset_qa_shots={"vibe_card"},
            )
            result = apply_identity_qa(root=root, input_path=str(_write_payload(root, _identity_payload())))
            row = _jsonl(root / "ai_image" / "manifests" / "identity_qa_manifest.jsonl")[0]

            self.assertEqual(result["approved"], 0)
            self.assertIn("asset_qa_missing:vibe_card", row["needsReviewReasons"])

    def test_approved_manifest_excludes_stale_approved_identity_without_active_file_backing(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_identity_fixture(root, write_identity_qa=False, write_approved_manifest=False)
            manifest = root / "ai_image" / "manifests" / "identity_qa_manifest.jsonl"
            stale_asset_ids = {shot: f"female_901__{shot}__v001" for shot in SHOT_ORDER}
            _write_jsonl(
                manifest,
                [
                    {
                        "schemaVersion": "seolleyeon_identity_qa_manifest_v3",
                        "profileId": "female_901",
                        "gender": "female",
                        "numericId": "901",
                        "targetFaceType": "deer_like",
                        "observedFaceType": "deer_like",
                        "targetLooksLevelBand": "2.5-3.2",
                        "observedLooksLevelBand": "2.5-3.2",
                        "assetIds": stale_asset_ids,
                        "assetDecisions": {shot: "approved" for shot in SHOT_ORDER},
                        "sameIdentity": True,
                        "completeIdentityDecision": "approved",
                        "finalCompleteIdentityDecision": "approved",
                        "countsTowardDistribution": True,
                        "metadataMismatch": False,
                    }
                ],
            )

            result = apply_identity_qa(root=root, input_path=str(_write_payload(root, _identity_payload())))
            approved = _jsonl(root / "ai_image" / "manifests" / "approved_identity_manifest.jsonl")

            self.assertEqual(result["approved"], 1)
            self.assertEqual([row["profileId"] for row in approved], ["female_001"])


if __name__ == "__main__":
    unittest.main()
