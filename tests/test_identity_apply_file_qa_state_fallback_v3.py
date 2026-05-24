from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.ai_image_pipeline_v3.approval_evidence import resolve_file_qa_evidence
from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa


class IdentityApplyFileQaStateFallbackV3Test(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.paths = pipeline_paths(self.root)
        self.paths.manifests.mkdir(parents=True, exist_ok=True)
        (self.paths.reports / "visual_verdict").mkdir(parents=True, exist_ok=True)
        self.prompt_hash = "prompt-hash-1"
        self.prompt_version = "targeting-v3"
        self.profile_id = "female_104"
        self.asset_ids = {shot: f"{self.profile_id}__{shot}__v001" for shot in ("face_card", "silhouette_card", "vibe_card")}
        self._write_valid_final_images()
        self._write_base_manifests()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_valid_final_images(self) -> None:
        from PIL import Image, ImageDraw

        for shot in ("face_card", "silhouette_card", "vibe_card"):
            path = self.paths.ai_image / "female" / "104" / f"{shot}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            image = Image.new("RGB", (512, 768), color=(120, 140, 160))
            draw = ImageDraw.Draw(image)
            draw.ellipse((176, 90, 336, 250), fill=(168, 132, 112))
            draw.rectangle((210, 250, 302, 500), fill=(80, 110, 150))
            image.save(path, format="PNG")

    def _asset_row(self, shot: str) -> dict:
        asset_id = self.asset_ids[shot]
        final_path = self.paths.ai_image / "female" / "104" / f"{shot}.png"
        return {
            "assetId": asset_id,
            "profileId": self.profile_id,
            "gender": "female",
            "numericId": "104",
            "shotType": shot,
            "targetFaceType": "cat_like",
            "targetLooksLevelBand": "3.9-4.3",
            "promptHash": self.prompt_hash,
            "promptTargetingVersion": self.prompt_version,
            "finalPath": str(final_path),
            "status": "file_qa_passed",
        }

    def _write_base_manifests(self) -> None:
        assets = [self._asset_row(shot) for shot in ("face_card", "silhouette_card", "vibe_card")]
        write_jsonl(self.paths.manifests / "ai_profile_assets_v3.jsonl", assets)
        write_jsonl(self.paths.manifests / "generation_manifest.jsonl", assets)
        write_jsonl(
            self.paths.manifests / "asset_qa_manifest.jsonl",
            [
                {
                    **row,
                    "schemaVersion": "seolleyeon_asset_qa_manifest_v3",
                    "finalDecision": "approved",
                    "decision": "approved",
                    "metadataMismatch": False,
                }
                for row in assets
            ],
        )
        (self.paths.manifests / "current_chunk_state.json").write_text(
            json.dumps({"chunkId": "chunk_20260520T143832Z", "assetStates": {asset_id: "file_qa_passed" for asset_id in self.asset_ids.values()}}),
            encoding="utf-8",
        )
        (self.paths.manifests / "current_chunk_plan.json").write_text(
            json.dumps({"chunkId": "chunk_20260520T143832Z", "assets": assets}),
            encoding="utf-8",
        )
        write_jsonl(self.paths.manifests / "approved_identity_manifest.jsonl", [])
        write_jsonl(self.paths.manifests / "rejected_identity_manifest.jsonl", [])
        write_jsonl(self.paths.manifests / "needs_review_identity_manifest.jsonl", [])

    def _write_identity_json(self, *, metadata_mismatch: bool = False, same_identity: bool = True, asset_decisions: dict | None = None) -> Path:
        asset_decisions = asset_decisions or {shot: "approved" for shot in ("face_card", "silhouette_card", "vibe_card")}
        path = self.paths.reports / "visual_verdict" / "identity_qa_latest.json"
        path.write_text(
            json.dumps(
                {
                    "qaType": "seolleyeon_visual_verdict_identity_v3",
                    "checked": 1,
                    "identities": [
                        {
                            "profileId": self.profile_id,
                            "gender": "female",
                            "targetFaceType": "cat_like",
                            "observedFaceType": "cat_like",
                            "targetLooksLevelBand": "3.9-4.3",
                            "observedLooksLevelBand": "3.9-4.3",
                            "assetIds": self.asset_ids,
                            "assetDecisions": asset_decisions,
                            "faceToSilhouetteConsistency": 4.0,
                            "faceToVibeConsistency": 4.1,
                            "sameIdentity": same_identity,
                            "metadataMismatch": metadata_mismatch,
                            "completeIdentityDecision": "approved",
                            "countsTowardDistribution": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_raw_approved_identity_counts_when_silhouette_file_qa_manifest_missing_but_state_is_passed(self) -> None:
        write_jsonl(
            self.paths.manifests / "file_qa_manifest.jsonl",
            [self._asset_row("face_card"), self._asset_row("vibe_card")],
        )
        result = apply_identity_qa(root=self.root, input_path=str(self._write_identity_json()))
        self.assertEqual(1, result["approved"])
        approved_rows = [json.loads(line) for line in (self.paths.manifests / "approved_identity_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual([self.profile_id], [row["profileId"] for row in approved_rows])
        identity_rows = [json.loads(line) for line in (self.paths.manifests / "identity_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        silhouette_evidence = identity_rows[0]["fileQaEvidence"]["silhouette_card"]
        self.assertTrue(silhouette_evidence["ok"])
        self.assertEqual("current_chunk_state", silhouette_evidence["source"])
        self.assertIn("file_qa_found_in_state_only", silhouette_evidence["reasons"])
        self.assertIn("file_qa_evidence_valid", silhouette_evidence["reasons"])

    def test_stale_missing_manifest_entry_falls_back_to_valid_current_chunk_state(self) -> None:
        stale = {**self._asset_row("silhouette_card"), "status": "missing"}
        write_jsonl(self.paths.manifests / "file_qa_manifest.jsonl", [self._asset_row("face_card"), stale, self._asset_row("vibe_card")])
        evidence = resolve_file_qa_evidence(
            self.root,
            self.asset_ids["silhouette_card"],
            active_asset=self._asset_row("silhouette_card"),
            generation_row=self._asset_row("silhouette_card"),
            file_qa_row=stale,
            expected_profile_id=self.profile_id,
            expected_shot_type="silhouette_card",
        )
        self.assertTrue(evidence["ok"])
        self.assertEqual("current_chunk_state", evidence["source"])
        self.assertIn("file_qa_found_in_state_only", evidence["reasons"])

    def test_manifest_failed_state_passed_conflict_rejects(self) -> None:
        failed = {**self._asset_row("silhouette_card"), "status": "file_rejected"}
        evidence = resolve_file_qa_evidence(
            self.root,
            self.asset_ids["silhouette_card"],
            active_asset=self._asset_row("silhouette_card"),
            generation_row=self._asset_row("silhouette_card"),
            file_qa_row=failed,
            expected_profile_id=self.profile_id,
            expected_shot_type="silhouette_card",
        )
        self.assertFalse(evidence["ok"])
        self.assertIn("file_qa_evidence_conflict", evidence["reasons"])

    def test_final_file_missing_rejects(self) -> None:
        (self.paths.ai_image / "female" / "104" / "silhouette_card.png").unlink()
        write_jsonl(self.paths.manifests / "file_qa_manifest.jsonl", [])
        result = apply_identity_qa(root=self.root, input_path=str(self._write_identity_json()))
        self.assertEqual(0, result["approved"])
        self.assertEqual(1, result["needs_review"])

    def test_prompt_hash_mismatch_rejects(self) -> None:
        bad_generation = self._asset_row("silhouette_card")
        bad_generation["promptHash"] = "other-hash"
        evidence = resolve_file_qa_evidence(
            self.root,
            self.asset_ids["silhouette_card"],
            active_asset=self._asset_row("silhouette_card"),
            generation_row=bad_generation,
            file_qa_row={},
            expected_profile_id=self.profile_id,
            expected_shot_type="silhouette_card",
        )
        self.assertFalse(evidence["ok"])
        self.assertIn("prompt_hash_mismatch", evidence["reasons"])

    def test_prompt_targeting_version_mismatch_rejects(self) -> None:
        bad_generation = self._asset_row("silhouette_card")
        bad_generation["promptTargetingVersion"] = "other-version"
        evidence = resolve_file_qa_evidence(
            self.root,
            self.asset_ids["silhouette_card"],
            active_asset=self._asset_row("silhouette_card"),
            generation_row=bad_generation,
            file_qa_row={},
            expected_profile_id=self.profile_id,
            expected_shot_type="silhouette_card",
        )
        self.assertFalse(evidence["ok"])
        self.assertIn("prompt_targeting_version_mismatch", evidence["reasons"])

    def test_asset_qa_rejected_or_needs_review_rejects_identity(self) -> None:
        for final_decision in ("rejected", "needs_review"):
            with self.subTest(final_decision=final_decision):
                rows = [
                    {
                        **self._asset_row(shot),
                        "schemaVersion": "seolleyeon_asset_qa_manifest_v3",
                        "finalDecision": final_decision if shot == "silhouette_card" else "approved",
                        "decision": final_decision if shot == "silhouette_card" else "approved",
                        "metadataMismatch": False,
                    }
                    for shot in ("face_card", "silhouette_card", "vibe_card")
                ]
                write_jsonl(self.paths.manifests / "asset_qa_manifest.jsonl", rows)
                write_jsonl(self.paths.manifests / "file_qa_manifest.jsonl", [])
                result = apply_identity_qa(root=self.root, input_path=str(self._write_identity_json()))
                self.assertEqual(0, result["approved"])

    def test_metadata_mismatch_rejects_identity(self) -> None:
        write_jsonl(self.paths.manifests / "file_qa_manifest.jsonl", [])
        result = apply_identity_qa(root=self.root, input_path=str(self._write_identity_json(metadata_mismatch=True)))
        self.assertEqual(0, result["approved"])
        self.assertEqual(1, result["needs_review"])

    def test_partial_failed_vibe_identity_does_not_count(self) -> None:
        state = {"chunkId": "chunk_20260520T143832Z", "assetStates": {**{asset_id: "file_qa_passed" for asset_id in self.asset_ids.values()}, self.asset_ids["vibe_card"]: "failed"}}
        (self.paths.manifests / "current_chunk_state.json").write_text(json.dumps(state), encoding="utf-8")
        write_jsonl(self.paths.manifests / "file_qa_manifest.jsonl", [self._asset_row("face_card"), self._asset_row("silhouette_card")])
        result = apply_identity_qa(root=self.root, input_path=str(self._write_identity_json()))
        self.assertEqual(0, result["approved"])

    def test_file_qa_only_asset_does_not_count_without_visual_asset_approval(self) -> None:
        rows = [
            {
                **self._asset_row(shot),
                "schemaVersion": "seolleyeon_asset_qa_manifest_v3",
                "finalDecision": "approved",
                "decision": "approved",
                "metadataMismatch": False,
            }
            for shot in ("face_card", "vibe_card")
        ]
        write_jsonl(self.paths.manifests / "asset_qa_manifest.jsonl", rows)
        write_jsonl(self.paths.manifests / "file_qa_manifest.jsonl", [])
        result = apply_identity_qa(root=self.root, input_path=str(self._write_identity_json()))
        self.assertEqual(0, result["approved"])
        self.assertEqual(1, result["needs_review"])


if __name__ == "__main__":
    unittest.main()
