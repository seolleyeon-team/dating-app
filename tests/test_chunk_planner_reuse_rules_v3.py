import json
import tempfile
import unittest
from pathlib import Path


class ChunkPlannerReuseRulesV3Tests(unittest.TestCase):
    def _write_audit(self, root: Path) -> None:
        reports = root / "ai_image" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        audit = {
            "approvedCompleteIdentityCount": 0,
            "approvedImageCount": 0,
            "femaleApprovedIdentityCount": 0,
            "maleApprovedIdentityCount": 0,
            "countChecks": {
                "femaleApprovedIdentities": {"deficit": 120},
                "maleApprovedIdentities": {"deficit": 120},
            },
            "bucketChecks": [
                {"scope": "global", "dimension": "faceType", "bucket": "bear_like", "deficit": 29},
                {"scope": "female", "dimension": "faceType", "bucket": "bear_like", "deficit": 15},
                {"scope": "global", "dimension": "looksLevelBand", "bucket": "2.5-3.2", "deficit": 108},
                {"scope": "female", "dimension": "looksLevelBand", "bucket": "2.5-3.2", "deficit": 54},
            ],
            "globalFaceTypeDeficits": {"bear_like": 29},
            "genderFaceTypeDeficits": {"female": {"bear_like": 15}, "male": {}},
            "globalLooksLevelBandDeficits": {"2.5-3.2": 108, "4.4-5.0": 0},
            "genderLooksLevelBandDeficits": {"female": {"2.5-3.2": 54, "4.4-5.0": 0}, "male": {}},
            "globalFaceTypeSurpluses": {},
            "genderFaceTypeSurpluses": {"female": {}, "male": {}},
            "globalLooksLevelBandSurpluses": {},
            "genderLooksLevelBandSurpluses": {"female": {}, "male": {}},
            "passed": False,
            "finalDecision": "needs_more_generation",
        }
        (reports / "latest_distribution_audit.json").write_text(json.dumps(audit), encoding="utf-8")

    def _write_profile(self, root: Path, profile_id: str = "female_001", statuses: dict[str, str] | None = None) -> None:
        from scripts.ai_image_pipeline_v3.codex_imagegen import write_imagegen_queue
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, prompt_hash, write_jsonl
        from scripts.ai_image_pipeline_v3.manifest import write_generation_outputs
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        paths = pipeline_paths(root)
        prompt_module = load_prompt_module()
        statuses = statuses or {}
        numeric = profile_id.split("_", 1)[1]
        rows = []
        for shot in ("face_card", "silhouette_card", "vibe_card"):
            prompt = f"prompt {profile_id} {shot}"
            rows.append(
                {
                    "assetId": f"{profile_id}__{shot}__v001",
                    "profileId": profile_id,
                    "gender": "female",
                    "numericId": numeric,
                    "shotType": shot,
                    "prompt": prompt,
                    "promptHash": prompt_hash(prompt),
                    "promptBuilderVersion": str(getattr(prompt_module, "PROMPT_BUILDER_VERSION", "")),
                    "promptTargetingVersion": str(getattr(prompt_module, "PROMPT_TARGETING_VERSION", "")),
                    "status": statuses.get(shot, "prepared"),
                    "activeForTarget": True,
                    "isReserve": False,
                    "targetFaceType": "bear_like",
                    "targetLooksLevelBand": "2.5-3.2",
                    "finalPath": str(root / "ai_image" / "female" / numeric / f"{shot}.png"),
                    "localPath": str(root / "ai_image" / "raw" / f"{profile_id}__{shot}__v001__attempt01.png"),
                }
            )
        write_generation_outputs(paths, rows)
        write_imagegen_queue(root, rows)
        write_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl", rows)

    def _write_visual_history(self, root: Path, profile_id: str = "female_001", *, face_decision: str = "rejected", identity_decision: str = "rejected") -> None:
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl

        paths = pipeline_paths(root)
        asset_rows = []
        for shot, decision in {
            "face_card": face_decision,
            "silhouette_card": "approved",
            "vibe_card": "needs_review",
        }.items():
            asset_rows.append(
                {
                    "schemaVersion": "seolleyeon_asset_qa_manifest_v3",
                    "assetId": f"{profile_id}__{shot}__v001",
                    "profileId": profile_id,
                    "shotType": shot,
                    "decision": decision,
                }
            )
        write_jsonl(paths.manifests / "asset_qa_manifest.jsonl", asset_rows)
        write_jsonl(
            paths.manifests / "identity_qa_manifest.jsonl",
            [
                {
                    "schemaVersion": "seolleyeon_identity_qa_manifest_v3",
                    "profileId": profile_id,
                    "decision": identity_decision,
                    "finalCompleteIdentityDecision": identity_decision,
                    "countsTowardDistribution": False,
                    "metadataMismatch": identity_decision == "rejected",
                }
            ],
        )

    def test_rejected_identity_asset_approved_silhouette_is_not_reused_by_planner(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_profile(
                root,
                statuses={
                    "face_card": "vision_rejected",
                    "silhouette_card": "vision_approved",
                    "vibe_card": "vision_needs_review",
                },
            )
            self._write_visual_history(root, face_decision="rejected", identity_decision="rejected")

            from scripts.ai_image_pipeline_v3.config import pipeline_paths, read_jsonl, write_jsonl

            paths = pipeline_paths(root)
            rejected_generation = read_jsonl(paths.manifests / "generation_manifest.jsonl")
            rejected_assets = read_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl")
            self._write_profile(root, profile_id="female_002")
            write_jsonl(paths.manifests / "generation_manifest.jsonl", rejected_generation + read_jsonl(paths.manifests / "generation_manifest.jsonl"))
            write_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl", rejected_assets + read_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl"))

            plan = create_chunk_plan(root=root, production=True, max_identities=1)

            self.assertEqual(plan["planType"], "full_identity_generation")
            self.assertFalse(plan["partialPlanAllowed"])
            self.assertEqual(plan["selectedIdentityCount"], 1)
            self.assertEqual(plan["selectedAssetCount"], 3)
            self.assertEqual(plan["identities"][0]["profileId"], "female_002")
            shots = [asset["shotType"] for asset in plan["identities"][0]["assets"]]
            self.assertEqual(shots, ["face_card", "silhouette_card", "vibe_card"])

    def test_rejected_identity_manifest_excludes_profile_from_next_distribution_selection(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, read_jsonl, write_jsonl
        from scripts.ai_image_pipeline_v3.distribution_selection import select_distribution_buckets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_profile(root, profile_id="female_001", statuses={"face_card": "vision_approved", "silhouette_card": "vision_approved", "vibe_card": "vision_rejected"})
            paths = pipeline_paths(root)
            first_profile_generation = read_jsonl(paths.manifests / "generation_manifest.jsonl")
            first_profile_assets = read_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl")

            self._write_profile(root, profile_id="female_002")
            write_jsonl(paths.manifests / "generation_manifest.jsonl", first_profile_generation + read_jsonl(paths.manifests / "generation_manifest.jsonl"))
            write_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl", first_profile_assets + read_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl"))
            write_jsonl(
                paths.manifests / "rejected_identity_manifest.jsonl",
                [
                    {
                        "profileId": "female_001",
                        "completeIdentityDecision": "rejected",
                        "rejected": True,
                        "completeApproved": False,
                    }
                ],
            )

            selection = select_distribution_buckets(root=root, max_identities=1)

            self.assertEqual([row["profileId"] for row in selection["selectedIdentities"]], ["female_002"])

    def test_partial_plan_without_justification_is_rejected_with_reuse_reasons(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import PlanValidationError, create_chunk_plan, validate_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_profile(root, statuses={"face_card": "vision_rejected", "silhouette_card": "vision_approved", "vibe_card": "vision_needs_review"})
            plan = create_chunk_plan(root=root, production=True, max_identities=1)
            self._write_visual_history(root, face_decision="rejected", identity_decision="rejected")
            plan["identities"][0]["assets"] = [asset for asset in plan["identities"][0]["assets"] if asset["shotType"] != "silhouette_card"]
            plan["selectedAssetCount"] = 2

            with self.assertRaises(PlanValidationError) as context:
                validate_chunk_plan(plan, root=root)

            reasons = set(context.exception.details.get("reasons", []))
            self.assertIn("unsafe_partial_plan", reasons)
            self.assertIn("omitted_asset_without_reuse_justification", reasons)
            self.assertIn("reuse_from_rejected_identity", reasons)
            self.assertIn("silhouette_reuse_without_approved_face_anchor", reasons)

    def test_partial_plan_requires_valid_face_anchor_and_non_rejected_identity(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import PlanValidationError, create_chunk_plan, validate_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_profile(root, statuses={"face_card": "vision_needs_review", "silhouette_card": "vision_approved", "vibe_card": "prepared"})
            self._write_visual_history(root, face_decision="needs_review", identity_decision="needs_review")
            plan = create_chunk_plan(root=root, production=True, max_identities=1)
            plan["identities"][0]["assets"] = [asset for asset in plan["identities"][0]["assets"] if asset["shotType"] != "silhouette_card"]
            plan["selectedAssetCount"] = 2
            plan["planType"] = "partial_salvage"
            plan["partialPlanAllowed"] = True
            plan["reusePolicy"] = {"allowAssetReuse": True, "allowSilhouetteReuseWithoutApprovedFaceAnchor": False, "allowReuseFromRejectedIdentity": False}
            plan["reuseJustifications"] = [
                {
                    "assetId": "female_001__silhouette_card__v001",
                    "profileId": "female_001",
                    "shotType": "silhouette_card",
                    "reason": "valid_face_anchor_salvage",
                    "fileQaPassed": True,
                    "assetVisualQaApproved": True,
                    "identityQaStatus": "needs_review",
                    "faceAnchorAssetId": "female_001__face_card__v001",
                    "faceAnchorApproved": False,
                    "sourceChunkId": "chunk_old",
                    "sourceChunkStatus": "finalized",
                    "allowed": True,
                }
            ]

            with self.assertRaises(PlanValidationError) as context:
                validate_chunk_plan(plan, root=root)

            self.assertIn("silhouette_reuse_without_approved_face_anchor", set(context.exception.details.get("reasons", [])))

    def test_validate_current_chunk_plan_rejects_unsafe_partial_plan(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, current_plan_path, validate_current_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_profile(root, statuses={"face_card": "vision_rejected", "silhouette_card": "vision_approved", "vibe_card": "vision_needs_review"})
            plan = create_chunk_plan(root=root, production=True, max_identities=1)
            self._write_visual_history(root, face_decision="rejected", identity_decision="rejected")
            plan["identities"][0]["assets"] = [asset for asset in plan["identities"][0]["assets"] if asset["shotType"] != "silhouette_card"]
            plan["selectedAssetCount"] = 2
            current_plan_path(root).write_text(json.dumps(plan), encoding="utf-8")

            validation = validate_current_chunk_plan(root=root, strict=False)

            self.assertFalse(validation["canRun"])
            self.assertIn("unsafe_partial_plan", validation["reasons"])
            self.assertIn("reuse_from_rejected_identity", validation["reasons"])

    def _write_tiny_png(self, path: Path) -> None:
        import base64

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="))

    def _reuse_context_for_asset(self, root: Path, profile_id: str = "female_001", *, shot: str = "silhouette_card", face_decision: str = "approved", identity_decision: str = "approved", abandoned: bool = False, include_asset: bool = True) -> dict:
        final_dir = root / "ai_image" / "female" / profile_id.split("_", 1)[1]
        face_id = f"{profile_id}__face_card__v001"
        asset_id = f"{profile_id}__{shot}__v001"
        face_row = {"assetId": face_id, "profileId": profile_id, "shotType": "face_card", "finalPath": str(final_dir / "face_card.png"), "targetLooksLevelBand": "2.5-3.2"}
        asset_row = {"assetId": asset_id, "profileId": profile_id, "shotType": shot, "finalPath": str(final_dir / f"{shot}.png"), "targetLooksLevelBand": "2.5-3.2"}
        self._write_tiny_png(Path(face_row["finalPath"]))
        self._write_tiny_png(Path(asset_row["finalPath"]))
        asset_manifest = {face_id: face_row}
        if include_asset:
            asset_manifest[asset_id] = asset_row
        return {
            "assetManifestByAssetId": asset_manifest,
            "generationByAssetId": {face_id: face_row, asset_id: asset_row},
            "fileQaByAssetId": {face_id: {"assetId": face_id, "status": "file_qa_passed"}, asset_id: {"assetId": asset_id, "status": "file_qa_passed"}},
            "assetQaByAssetId": {face_id: {"assetId": face_id, "decision": face_decision}, asset_id: {"assetId": asset_id, "decision": "approved"}},
            "identityQaByProfileId": {profile_id: {"profileId": profile_id, "finalCompleteIdentityDecision": identity_decision}},
            "abandonedProfileIds": {profile_id} if abandoned else set(),
        }

    def test_plan_validation_rejects_stale_prompt_targeting_version(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import PlanValidationError, create_chunk_plan, validate_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_profile(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=1)
            plan["identities"][0]["assets"][0]["promptTargetingVersion"] = "old_prompt_targeting_version"

            with self.assertRaises(PlanValidationError) as context:
                validate_chunk_plan(plan, root=root)

            self.assertEqual(context.exception.reason_code, "stale_prompt_targeting_version")

    def test_is_asset_reusable_blocks_rejected_identity_even_with_asset_approval(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import is_asset_reusable_for_new_plan

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._reuse_context_for_asset(Path(tmp), identity_decision="rejected")
            self.assertFalse(is_asset_reusable_for_new_plan("female_001__silhouette_card__v001", "female_001", "silhouette_card", ctx))

    def test_is_asset_reusable_blocks_needs_review_face_anchor(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import is_asset_reusable_for_new_plan

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._reuse_context_for_asset(Path(tmp), face_decision="needs_review")
            self.assertFalse(is_asset_reusable_for_new_plan("female_001__silhouette_card__v001", "female_001", "silhouette_card", ctx))

    def test_is_asset_reusable_blocks_rejected_face_anchor(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import is_asset_reusable_for_new_plan

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._reuse_context_for_asset(Path(tmp), face_decision="rejected")
            self.assertFalse(is_asset_reusable_for_new_plan("female_001__silhouette_card__v001", "female_001", "silhouette_card", ctx))

    def test_is_asset_reusable_blocks_approved_silhouette_without_active_manifest_row(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import is_asset_reusable_for_new_plan

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._reuse_context_for_asset(Path(tmp), include_asset=False)
            self.assertFalse(is_asset_reusable_for_new_plan("female_001__silhouette_card__v001", "female_001", "silhouette_card", ctx))

    def test_is_asset_reusable_blocks_abandoned_chunk_assets_by_default(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import is_asset_reusable_for_new_plan

        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._reuse_context_for_asset(Path(tmp), abandoned=True)
            self.assertFalse(is_asset_reusable_for_new_plan("female_001__silhouette_card__v001", "female_001", "silhouette_card", ctx))

    def test_partial_plan_reuse_justification_fails_for_rejected_identity(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import PlanValidationError, create_chunk_plan, validate_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_profile(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=1)
            self._write_visual_history(root, face_decision="approved", identity_decision="rejected")
            plan["identities"][0]["assets"] = [asset for asset in plan["identities"][0]["assets"] if asset["shotType"] != "silhouette_card"]
            plan["selectedAssetCount"] = 2
            plan["planType"] = "partial_salvage"
            plan["partialPlanAllowed"] = True
            plan["reuseJustifications"] = [{"assetId": "female_001__silhouette_card__v001", "profileId": "female_001", "shotType": "silhouette_card", "identityQaStatus": "rejected", "faceAnchorApproved": True, "sourceChunkStatus": "finalized", "allowed": True}]

            with self.assertRaises(PlanValidationError) as context:
                validate_chunk_plan(plan, root=root)
            self.assertIn("reuse_from_rejected_identity", set(context.exception.details.get("reasons", [])))

    def test_selected_asset_count_mismatch_is_reported(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import PlanValidationError, create_chunk_plan, validate_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_profile(root)
            plan = create_chunk_plan(root=root, production=True, max_identities=1)
            plan["selectedAssetCount"] = 2

            with self.assertRaises(PlanValidationError) as context:
                validate_chunk_plan(plan, root=root)
            self.assertEqual(context.exception.reason_code, "selected_asset_count_mismatch")


if __name__ == "__main__":
    unittest.main()
