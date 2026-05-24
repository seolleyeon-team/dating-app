import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class HermesFailedAssetContinueV3Tests(unittest.TestCase):
    def _tmp(self):
        return tempfile.TemporaryDirectory()

    def _write_plan_state(self, root, *, failed_asset_id="female_120__vibe_card__v001", failed_shot="vibe_card", failed_profile="female_120", extra_assets=None):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, now_utc
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import current_plan_path, current_state_path

        paths = pipeline_paths(root)
        paths.manifests.mkdir(parents=True, exist_ok=True)
        paths.reports.mkdir(parents=True, exist_ok=True)
        extra_assets = list(extra_assets or [
            ("male_001", "male_001__face_card__v001", "face_card", "planned"),
        ])
        now = now_utc()
        identities = [
            {
                "profileId": failed_profile,
                "gender": "female" if failed_profile.startswith("female") else "male",
                "numericId": failed_profile.split("_")[-1],
                "status": "failed",
                "assets": [
                    {
                        "assetId": failed_asset_id,
                        "shotType": failed_shot,
                        "order": 3 if failed_shot == "vibe_card" else 1,
                        "status": "failed",
                        "attempt": 3,
                        "maxAttempts": 3,
                        "prompt": "prompt",
                        "promptHash": "hash_failed",
                        "promptBuilderVersion": "v3",
                        "promptTargetingVersion": "v3",
                        "finalPath": str(Path(root) / "ai_image" / "female" / "120" / (failed_shot + ".png")),
                        "rawPathPattern": str(Path(root) / "ai_image" / "raw" / f"{failed_asset_id}__attemptXX.png"),
                    }
                ],
            }
        ]
        for profile_id, asset_id, shot_type, status in extra_assets:
            identities.append(
                {
                    "profileId": profile_id,
                    "gender": "male" if profile_id.startswith("male") else "female",
                    "numericId": profile_id.split("_")[-1],
                    "status": "planned",
                    "assets": [
                        {
                            "assetId": asset_id,
                            "shotType": shot_type,
                            "order": 1,
                            "status": status,
                            "attempt": 0,
                            "maxAttempts": 3,
                            "prompt": "prompt",
                            "promptHash": f"hash_{asset_id}",
                            "promptBuilderVersion": "v3",
                            "promptTargetingVersion": "v3",
                            "finalPath": str(Path(root) / "ai_image" / "male" / "001" / (shot_type + ".png")),
                            "rawPathPattern": str(Path(root) / "ai_image" / "raw" / f"{asset_id}__attemptXX.png"),
                        }
                    ],
                }
            )
        asset_states = {failed_asset_id: "failed"}
        identity_states = {failed_profile: "failed"}
        for profile_id, asset_id, _shot_type, status in extra_assets:
            asset_states[asset_id] = status
            identity_states[profile_id] = "planned"
        plan = {
            "schemaVersion": "seolleyeon_bounded_chunk_plan_v3",
            "chunkId": "chunk_test",
            "createdAt": now,
            "updatedAt": now,
            "dryRun": False,
            "planMode": "production",
            "planType": "full_identity_generation",
            "partialPlanAllowed": False,
            "reusePolicy": {},
            "reuseJustifications": {},
            "executable": True,
            "status": "failed",
            "maxIdentities": 24,
            "maxAssets": 72,
            "selectedIdentityCount": len(identities),
            "selectedAssetCount": sum(len(i["assets"]) for i in identities),
            "selectionSource": "unit_test",
            "root": str(root),
            "targetsJson": "",
            "distributionAuditJson": "",
            "queueJson": "",
            "assetManifestJson": "",
            "inputHashes": {},
            "inputMtimes": {},
            "identities": identities,
            "initialProgress": {},
            "planHash": "unit_hash",
        }
        state = {
            "schemaVersion": "seolleyeon_bounded_chunk_state_v3",
            "chunkId": "chunk_test",
            "planHash": "unit_hash",
            "status": "failed",
            "currentAssetId": "",
            "completedAssetIds": [],
            "failedAssetIds": [failed_asset_id],
            "assetStates": asset_states,
            "identityStates": identity_states,
            "activeVisualQaComplete": False,
            "distributionAuditComplete": False,
            "startedAt": now,
            "createdAt": now,
            "updatedAt": now,
            "recoveredAssets": 0,
            "pendingFinalization": False,
        }
        current_plan_path(root).write_text(json.dumps(plan), encoding="utf-8")
        current_state_path(root).write_text(json.dumps(state), encoding="utf-8")
        return failed_asset_id

    def test_vibe_card_failed_terminal_does_not_block_next_identity_after_reconcile(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import reconcile_bounded_chunk, read_current_state
        with self._tmp() as tmp:
            failed = self._write_plan_state(tmp)
            result = reconcile_bounded_chunk(root=tmp, dry_run=False, apply=True)
            state = read_current_state(tmp)
        self.assertTrue(result["chunkStatusRestored"])
        self.assertEqual(state["status"], "running")
        self.assertEqual(state["assetStates"][failed], "failed")
        self.assertEqual(state["assetStates"]["male_001__face_card__v001"], "planned")

    def test_current_plan_not_executable_disappears_after_failed_terminal_reconcile(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import reconcile_bounded_chunk, validate_current_chunk_plan
        with self._tmp() as tmp:
            self._write_plan_state(tmp)
            before = validate_current_chunk_plan(root=tmp, strict=False)
            reconcile_bounded_chunk(root=tmp, dry_run=False, apply=True)
            after = validate_current_chunk_plan(root=tmp, strict=False)
        self.assertFalse(before["canRun"])
        self.assertIn("current_plan_not_executable", before["reasons"])
        self.assertNotIn("current_plan_not_executable", after["reasons"])

    def test_failed_terminal_asset_is_not_approved_by_reconcile(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import reconcile_bounded_chunk, read_current_state
        with self._tmp() as tmp:
            failed = self._write_plan_state(tmp)
            reconcile_bounded_chunk(root=tmp, dry_run=False, apply=True)
            state = read_current_state(tmp)
        self.assertNotIn(state["assetStates"][failed], {"approved", "visual_qa_approved"})
        self.assertEqual(state["identityStates"]["female_120"], "failed")

    def test_failed_terminal_identity_is_not_marked_assets_complete(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import reconcile_bounded_chunk, read_current_state
        with self._tmp() as tmp:
            self._write_plan_state(tmp)
            reconcile_bounded_chunk(root=tmp, dry_run=False, apply=True)
            state = read_current_state(tmp)
        self.assertEqual(state["identityStates"]["female_120"], "failed")
        self.assertNotEqual(state["identityStates"]["female_120"], "assets_complete")

    def test_face_card_failed_terminal_can_restore_chunk_for_unrelated_identity(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import reconcile_bounded_chunk, read_current_state
        with self._tmp() as tmp:
            failed = self._write_plan_state(
                tmp,
                failed_asset_id="female_120__face_card__v001",
                failed_shot="face_card",
                failed_profile="female_120",
            )
            result = reconcile_bounded_chunk(root=tmp, dry_run=False, apply=True)
            state = read_current_state(tmp)
        self.assertTrue(result["chunkStatusRestored"])
        self.assertEqual(state["assetStates"][failed], "failed")
        self.assertEqual(state["assetStates"]["male_001__face_card__v001"], "planned")

    def test_reconcile_does_not_restore_when_active_pending_blocker_remains(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import reconcile_bounded_chunk, read_current_state
        with self._tmp() as tmp:
            self._write_plan_state(
                tmp,
                extra_assets=[("male_001", "male_001__face_card__v001", "face_card", "pending_imagegen")],
            )
            result = reconcile_bounded_chunk(root=tmp, dry_run=False, apply=True)
            state = read_current_state(tmp)
        self.assertFalse(result["chunkStatusRestored"])
        self.assertEqual(state["status"], "failed")


if __name__ == "__main__":
    unittest.main()
