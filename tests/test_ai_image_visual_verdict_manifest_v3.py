import json
import tempfile
import unittest
from pathlib import Path


class VisualVerdictManifestV3Tests(unittest.TestCase):
    def _make_generation_rows(self, root: Path, profile: str = "female_001", *, shots=("face_card", "silhouette_card", "vibe_card"), backed: bool = True):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.manifest import enrich_asset, write_generation_outputs

        paths = pipeline_paths(root)
        rows = []
        gender = profile.split("_", 1)[0]
        for shot in shots:
            rows.append(
                enrich_asset(
                    {
                        "profileId": profile,
                        "assetId": f"{profile}__{shot}__v001",
                        "gender": gender,
                        "shotType": shot,
                        "targetFaceType": "deer_like",
                        "targetLooksLevelBand": "2.5-3.2",
                        "prompt": "p",
                    },
                    paths,
                )
            )
        write_generation_outputs(paths, rows)
        if backed:
            from PIL import Image

            write_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl", rows)
            file_qa_rows = []
            for row in rows:
                final_path = Path(row["finalPath"])
                final_path.parent.mkdir(parents=True, exist_ok=True)
                image = Image.effect_noise((768, 1024), 64).convert("RGB")
                image.save(final_path)
                file_qa_rows.append(
                    {
                        "assetId": row["assetId"],
                        "profileId": row["profileId"],
                        "gender": row["gender"],
                        "shotType": row["shotType"],
                        "status": "file_qa_passed",
                        "qaStatus": "file_qa_passed",
                        "finalPath": row["finalPath"],
                        "imagePath": row["finalPath"],
                        "promptHash": row.get("promptHash", ""),
                        "promptTargetingVersion": row.get("promptTargetingVersion", ""),
                    }
                )
            write_jsonl(paths.manifests / "file_qa_manifest.jsonl", file_qa_rows)
        return paths, rows

    def _asset_review(self, asset: dict, **overrides):
        row = {
            "assetId": asset["assetId"],
            "profileId": asset["profileId"],
            "gender": asset["gender"],
            "shotType": asset["shotType"],
            "targetFaceType": "deer_like",
            "observedFaceType": "deer_like",
            "faceTypeConfidence": 0.92,
            "targetLooksLevelBand": "2.5-3.2",
            "observedLooksLevelBand": "2.5-3.2",
            "looksLevelConfidence": 0.88,
            "adultVisual": True,
            "photoRealism": 4.6,
            "campusRealism": 4.4,
            "brandFit": 4.5,
            "shotTypeReadable": True,
            "influencerRisk": 0.2,
            "childlikeRisk": 0.0,
            "schoolUniformRisk": 0.0,
            "sexualizationRisk": 0.0,
            "artifactRisk": 0.2,
            "metadataMismatch": False,
            "mismatchFields": [],
            "decision": "approved",
            "rejectReasons": [],
            "notes": "ok",
        }
        row.update(overrides)
        return row

    def _apply_asset_reviews(self, root: Path, rows: list[dict], reviews: list[dict]):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_asset_qa

        visual_path = root / "asset_qa.json"
        visual_path.write_text(
            json.dumps({"qaType": "seolleyeon_visual_verdict_asset_v3", "sheetId": "asset-sheet", "assets": reviews}),
            encoding="utf-8",
        )
        return apply_asset_qa(root=root, input_path=str(visual_path))

    def _identity_review(self, profile: str = "female_001", **overrides):
        row = {
            "profileId": profile,
            "gender": profile.split("_", 1)[0],
            "targetFaceType": "deer_like",
            "observedFaceType": "deer_like",
            "targetLooksLevelBand": "2.5-3.2",
            "observedLooksLevelBand": "2.5-3.2",
            "assetIds": {shot: f"{profile}__{shot}__v001" for shot in ("face_card", "silhouette_card", "vibe_card")},
            "assetDecisions": {"face_card": "approved", "silhouette_card": "approved", "vibe_card": "approved"},
            "faceToSilhouetteConsistency": 4.2,
            "faceToVibeConsistency": 4.2,
            "sameIdentity": True,
            "completeIdentityDecision": "approved",
            "countsTowardDistribution": True,
            "failedShotTypes": [],
            "retryShotTypes": [],
            "rejectReasons": [],
            "notes": "ok",
        }
        row.update(overrides)
        return row

    def _apply_identity_reviews(self, root: Path, reviews: list[dict]):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        visual_path = root / "identity_qa.json"
        visual_path.write_text(json.dumps({"qaType": "seolleyeon_visual_verdict_identity_v3", "identities": reviews}), encoding="utf-8")
        return apply_identity_qa(root=root, input_path=str(visual_path))

    def test_asset_nested_schema_writes_latest_manifest_and_maps_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, rows = self._make_generation_rows(root, shots=("face_card", "vibe_card"))
            reviews = [
                self._asset_review(rows[0]),
                self._asset_review(rows[1], observedFaceType="fox_like", faceTypeConfidence=0.2),
            ]

            counts = self._apply_asset_reviews(root, rows, reviews)
            manifest = [json.loads(line) for line in (paths.manifests / "asset_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()]

            self.assertEqual(counts["checked"], 2)
            self.assertEqual(len(manifest), 2)
            self.assertEqual(manifest[1]["observedFaceType"], "fox_like")
            self.assertEqual(manifest[1]["observedLooksLevelBand"], "2.5-3.2")
            self.assertEqual(manifest[1]["schemaVersion"], "seolleyeon_asset_qa_manifest_v3")

            duplicate = [self._asset_review(rows[1], observedFaceType="deer_like", notes="latest")]
            self._apply_asset_reviews(root, rows, duplicate)
            latest = [json.loads(line) for line in (paths.manifests / "asset_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(latest), 2)
            self.assertEqual(next(row for row in latest if row["assetId"] == rows[1]["assetId"])["notes"], "latest")

    def test_asset_hard_reject_overrides_approved_decision(self):
        cases = (
            ("adultVisual", False),
            ("childlikeRisk", 2.0),
            ("schoolUniformRisk", 1.0),
            ("sexualizationRisk", 1.0),
            ("artifactRisk", 3.0),
            ("photoRealism", 3.9),
            ("brandFit", 3.9),
            ("shotTypeReadable", False),
            ("observedLooksLevelBand", "4.4-5.0"),
        )
        for field, value in cases:
            with self.subTest(field=field):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    paths, rows = self._make_generation_rows(root, shots=("face_card",))
                    counts = self._apply_asset_reviews(root, rows, [self._asset_review(rows[0], **{field: value})])
                    manifest = [json.loads(line) for line in (paths.manifests / "asset_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()]

                    self.assertEqual(counts["checked"], 1)
                    self.assertEqual(counts["rejected"], 1)
                    self.assertEqual(manifest[0]["finalDecision"], "rejected")
                    self.assertTrue(manifest[0]["hardReject"])

    def test_asset_metadata_mismatch_becomes_needs_review_not_approved(self):
        for overrides in (
            {"observedFaceType": "fox_like", "faceTypeConfidence": 0.9},
            {"observedLooksLevelBand": "3.3-3.8", "looksLevelConfidence": 0.9},
            {"metadataMismatch": True},
            {"observedFaceType": "unclear"},
            {"shotType": "unknown"},
        ):
            with self.subTest(overrides=overrides):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    paths, rows = self._make_generation_rows(root, shots=("face_card",))
                    self._apply_asset_reviews(root, rows, [self._asset_review(rows[0], **overrides)])
                    manifest = [json.loads(line) for line in (paths.manifests / "asset_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
                    self.assertNotEqual(manifest[0]["finalDecision"], "approved")
                    self.assertFalse(manifest[0]["countsTowardIdentityQa"])

    def test_non_vibe_location_type_mismatch_is_not_asset_rejecting_metadata_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, rows = self._make_generation_rows(root, shots=("silhouette_card",))
            review = self._asset_review(
                rows[0],
                metadataMismatch=True,
                mismatchFields=["locationType"],
                decision="approved",
            )
            counts = self._apply_asset_reviews(root, rows, [review])
            manifest = [json.loads(line) for line in (paths.manifests / "asset_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(counts["approved"], 1)
            self.assertEqual(manifest[0]["finalDecision"], "approved")
            self.assertFalse(manifest[0]["metadataMismatch"])
            self.assertEqual(manifest[0]["mismatchFields"], [])

    def test_vibe_location_type_mismatch_remains_asset_metadata_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, rows = self._make_generation_rows(root, shots=("vibe_card",))
            review = self._asset_review(
                rows[0],
                metadataMismatch=True,
                mismatchFields=["locationType"],
                decision="approved",
            )
            counts = self._apply_asset_reviews(root, rows, [review])
            manifest = [json.loads(line) for line in (paths.manifests / "asset_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(counts["needs_review"], 1)
            self.assertEqual(manifest[0]["finalDecision"], "needs_review")
            self.assertTrue(manifest[0]["metadataMismatch"])
            self.assertEqual(manifest[0]["mismatchFields"], ["locationType"])

    def test_asset_invalid_empty_and_unknown_qatype_rejected(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_asset_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid = root / "invalid.json"
            invalid.write_text("{", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                apply_asset_qa(root=root, input_path=str(invalid))
            empty = root / "empty.json"
            empty.write_text(json.dumps({"qaType": "seolleyeon_visual_verdict_asset_v3", "assets": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                apply_asset_qa(root=root, input_path=str(empty))
            unknown = root / "unknown.json"
            unknown.write_text(json.dumps({"qaType": "other", "assets": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                apply_asset_qa(root=root, input_path=str(unknown))

    def test_identity_approved_rejected_and_needs_review_manifests(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, rows = self._make_generation_rows(root)
            self._apply_asset_reviews(root, rows, [self._asset_review(row) for row in rows])

            counts = self._apply_identity_reviews(root, [self._identity_review()])
            identity_rows = [json.loads(line) for line in (paths.manifests / "identity_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
            approved = [json.loads(line) for line in (paths.manifests / "approved_identity_manifest.jsonl").read_text(encoding="utf-8").splitlines()]

            self.assertEqual(counts["checked"], 1)
            self.assertEqual(counts["approved"], 1)
            self.assertEqual(identity_rows[0]["finalCompleteIdentityDecision"], "approved")
            self.assertTrue(identity_rows[0]["countsTowardDistribution"])
            self.assertEqual(len(approved), 1)
            self.assertEqual(approved[0]["faceType"], "deer_like")

    def test_identity_decision_rules(self):
        cases = (
            ("missing_vibe", {"assetIds": {"face_card": "female_001__face_card__v001", "silhouette_card": "female_001__silhouette_card__v001", "vibe_card": ""}}, "needs_review"),
            ("same_false", {"sameIdentity": False}, "rejected"),
            ("low_silhouette", {"faceToSilhouetteConsistency": 3.7}, "rejected"),
            ("low_vibe", {"faceToVibeConsistency": 3.7}, "rejected"),
            ("over_level", {"observedLooksLevelBand": "4.4-5.0"}, "rejected"),
            ("metadata_mismatch", {"observedFaceType": "fox_like"}, "needs_review"),
        )
        for name, overrides, expected in cases:
            with self.subTest(name=name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    paths, rows = self._make_generation_rows(root)
                    self._apply_asset_reviews(root, rows, [self._asset_review(row) for row in rows])
                    self._apply_identity_reviews(root, [self._identity_review(**overrides)])
                    identity = [json.loads(line) for line in (paths.manifests / "identity_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()][0]
                    approved_text = (paths.manifests / "approved_identity_manifest.jsonl").read_text(encoding="utf-8")
                    self.assertEqual(identity["finalCompleteIdentityDecision"], expected)
                    if expected != "approved":
                        self.assertEqual(approved_text.strip(), "")

    def test_identity_uses_asset_qa_final_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, rows = self._make_generation_rows(root)
            reviews = [self._asset_review(rows[0]), self._asset_review(rows[1], observedFaceType="unclear"), self._asset_review(rows[2])]
            self._apply_asset_reviews(root, rows, reviews)
            self._apply_identity_reviews(root, [self._identity_review()])
            identity = [json.loads(line) for line in (paths.manifests / "identity_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()][0]
            self.assertEqual(identity["finalCompleteIdentityDecision"], "needs_review")
            self.assertIn("asset_needs_review:silhouette_card", identity["needsReviewReasons"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths, rows = self._make_generation_rows(root)
            reviews = [self._asset_review(rows[0]), self._asset_review(rows[1], adultVisual=False), self._asset_review(rows[2])]
            self._apply_asset_reviews(root, rows, reviews)
            self._apply_identity_reviews(root, [self._identity_review()])
            identity = [json.loads(line) for line in (paths.manifests / "identity_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()][0]
            rejected = [json.loads(line) for line in (paths.manifests / "rejected_identity_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(identity["finalCompleteIdentityDecision"], "rejected")
            self.assertEqual(len(rejected), 1)

    def test_distribution_and_completion_do_not_count_unbacked_visual_data(self):
        from scripts.ai_image_pipeline_v3.completion import completion_check
        from scripts.ai_image_pipeline_v3.config import write_jsonl
        from scripts.ai_image_pipeline_v3.distribution_audit import audit_distribution
        from scripts.ai_image_pipeline_v3.distribution_targets import write_default_distribution_targets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_default_distribution_targets(root=root, force=True)
            manifests = root / "ai_image" / "manifests"
            manifests.mkdir(parents=True, exist_ok=True)
            write_jsonl(
                manifests / "identity_qa_manifest.jsonl",
                [
                    {
                        "profileId": "female_001",
                        "gender": "female",
                        "targetFaceType": "deer_like",
                        "observedFaceType": "deer_like",
                        "targetLooksLevelBand": "2.5-3.2",
                        "observedLooksLevelBand": "2.5-3.2",
                        "assetFinalDecisions": {"face_card": "approved", "silhouette_card": "approved", "vibe_card": "approved"},
                        "finalCompleteIdentityDecision": "approved",
                        "completeIdentityDecision": "approved",
                        "countsTowardDistribution": True,
                        "sameIdentity": True,
                        "metadataMismatch": False,
                    }
                ],
            )
            audit = audit_distribution(root=root)
            completion = completion_check(root=root)

            self.assertEqual(audit["approvedCompleteIdentityCount"], 0)
            self.assertFalse(completion["passed"])
            self.assertIn("missing_visual_verdict", completion["failureReasons"])
    def test_identity_apply_preserves_unrelated_existing_approved_manifest_rows(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = pipeline_paths(root)
            (paths.manifests).mkdir(parents=True, exist_ok=True)
            write_jsonl(
                paths.manifests / "approved_identity_manifest.jsonl",
                [
                    {
                        "schemaVersion": "seolleyeon_approved_identity_manifest_v3",
                        "profileId": "female_001",
                        "gender": "female",
                        "numericId": "001",
                        "faceType": "deer_like",
                        "looksLevelBand": "2.5-3.2",
                        "observedFaceType": "deer_like",
                        "observedLooksLevelBand": "2.5-3.2",
                        "assetIds": {shot: f"female_001__{shot}__v001" for shot in ("face_card", "silhouette_card", "vibe_card")},
                        "finalPaths": {},
                        "finalCompleteIdentityDecision": "approved",
                        "countsTowardDistribution": True,
                    }
                ],
            )

            self._make_generation_rows(root, profile="female_002")
            self._apply_identity_reviews(root, [self._identity_review(profile="female_002", completeIdentityDecision="rejected", countsTowardDistribution=False)])
            approved = [json.loads(line) for line in (paths.manifests / "approved_identity_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
            rejected = [json.loads(line) for line in (paths.manifests / "rejected_identity_manifest.jsonl").read_text(encoding="utf-8").splitlines()]

            self.assertEqual([row["profileId"] for row in approved], ["female_001"])
            self.assertEqual([row["profileId"] for row in rejected], ["female_002"])


if __name__ == "__main__":
    unittest.main()
