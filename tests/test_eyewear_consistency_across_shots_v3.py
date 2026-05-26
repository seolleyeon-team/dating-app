import importlib.util
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "lib" / "ai_recommend_model" / "seolleyeon_ai_profile_prompt_v3_package" / "seolleyeon_ai_profile_prompt_v3.py"


def load_prompt_module():
    spec = importlib.util.spec_from_file_location("seolleyeon_ai_profile_prompt_v3", PROMPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class EyewearConsistencyAcrossShotsV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_prompt_module()

    def _spec_with_eyewear(self):
        specs = self.m.generate_specs(female_count=30, male_count=30, seed=20260522)
        return next(spec for spec in specs if spec["accessories"]["eyewearGroup"] == "glasses")

    def _spec_without_eyewear(self):
        specs = self.m.generate_specs(female_count=30, male_count=30, seed=20260522)
        return next(spec for spec in specs if spec["accessories"]["eyewearGroup"] == "none")

    def test_prompt_targeting_version_bumped_to_v15_and_hash_changes(self):
        spec = self._spec_with_eyewear()
        self.assertEqual(self.m.PROMPT_TARGETING_VERSION, "face_type_looks_level_targeting_v24")
        baseline = self.m.build_asset_record(spec, "face_card")
        original = self.m.PROMPT_TARGETING_VERSION
        try:
            self.m.PROMPT_TARGETING_VERSION = "face_type_looks_level_targeting_test"
            changed = self.m.build_asset_record(spec, "face_card")
        finally:
            self.m.PROMPT_TARGETING_VERSION = original
        self.assertNotEqual(baseline["promptHash"], changed["promptHash"])

    def test_eyewear_identity_metadata_is_same_across_all_shots(self):
        spec = self._spec_with_eyewear()
        assets = self.m.build_asset_records(spec)
        canonical = spec["accessories"]["canonicalEyewear"]
        self.assertEqual({asset["hasEyewear"] for asset in assets}, {True})
        self.assertEqual({asset["eyewearGroup"] for asset in assets}, {"glasses"})
        self.assertEqual({asset["eyewear"] for asset in assets}, {canonical})
        self.assertEqual({asset["canonicalEyewear"] for asset in assets}, {canonical})
        self.assertEqual({asset["shotEyewearExpected"] for asset in assets}, {canonical})
        self.assertEqual({asset["temporaryEyewearAllowed"] for asset in assets}, {False})

    def test_no_eyewear_identity_expects_none_across_all_shots(self):
        spec = self._spec_without_eyewear()
        assets = self.m.build_asset_records(spec)
        self.assertEqual({asset["hasEyewear"] for asset in assets}, {False})
        self.assertEqual({asset["eyewearGroup"] for asset in assets}, {"none"})
        self.assertEqual({asset["canonicalEyewear"] for asset in assets}, {"none"})
        self.assertEqual({asset["shotEyewearExpected"] for asset in assets}, {"none"})
        self.assertEqual({asset["targetHasEyewear"] for asset in assets}, {False})

    def test_all_shot_prompts_preserve_assigned_eyewear(self):
        spec = self._spec_with_eyewear()
        eyewear_text = self.m.EYEWEAR_VISUAL[spec["accessories"]["canonicalEyewear"]]
        for shot in self.m.SHOT_TYPES:
            prompt = self.m.build_prompt(spec, shot)
            self.assertIn(eyewear_text, prompt)
            self.assertIn("Eyewear consistency:", prompt)
            self.assertIn("same", prompt.lower())

    def test_no_eyewear_vibe_prompt_does_not_add_study_glasses(self):
        spec = deepcopy(self._spec_without_eyewear())
        spec["location"] = {
            "locationType": "library_lounge",
            "scene": self.m.LOCATION_CATALOG["library_lounge"]["scene"],
            "privacyRisk": "low",
            "logoTextRisk": "low",
            "seasonCompatibility": ["spring", "summer", "autumn", "winter"],
        }
        spec["vibeActivity"] = self.m.LOCATION_VIBE_ACTIVITIES["library_lounge"][0]
        prompt = self.m.build_prompt(spec, "vibe_card")
        positive, negative = self.m.split_positive_and_negative_prompt(prompt)
        for banned in ("glasses", "eyeglasses", "spectacles", "sunglasses", "tinted lenses"):
            self.assertNotIn(banned, positive.lower())
        self.assertIn("glasses", negative.lower())
        self.m.validate_no_banned_positive_terms(prompt)

    def test_rare_variation_disabled_by_default(self):
        self.assertEqual(self.m.RARE_EYEWEAR_VARIATION_RATE, 0.0)
        spec = self._spec_without_eyewear()
        spec["accessories"]["temporaryEyewearForShot"] = {"vibe_card": True}
        with self.assertRaises(ValueError):
            self.m.validate_spec(self.m.normalize_spec_defaults(spec))

    def test_full_distribution_keeps_identity_level_eyewear_counts(self):
        specs = self.m.generate_specs(female_count=120, male_count=120, seed=20260512)
        female = [spec for spec in specs if spec["gender"] == "female"]
        male = [spec for spec in specs if spec["gender"] == "male"]
        self.assertEqual(sum(spec["accessories"]["eyewearGroup"] == "glasses" for spec in female), 12)
        self.assertEqual(sum(spec["accessories"]["eyewearGroup"] == "glasses" for spec in male), 24)
        assets = [asset for spec in specs for asset in self.m.build_asset_records(spec)]
        for spec in specs:
            spec_assets = [asset for asset in assets if asset["profileId"] == spec["profileId"]]
            self.assertEqual(len(spec_assets), 3)
            self.assertEqual({asset["canonicalEyewear"] for asset in spec_assets}, {spec["accessories"]["canonicalEyewear"]})

    def _write_jsonl(self, path: Path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")

    def _visual_root(self, target_has=True, observed_values=None):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths

        root = Path(tempfile.mkdtemp())
        paths = pipeline_paths(root)
        rows = []
        file_qa = []
        expected = "thin_round_metal" if target_has else "none"
        for index, shot in enumerate(("face_card", "silhouette_card", "vibe_card"), start=1):
            asset_id = f"female_001__{shot}__v001"
            final = paths.final / "female" / "001" / f"{shot}.png"
            final.parent.mkdir(parents=True, exist_ok=True)
            image = Image.new("RGB", (512, 768), (20 * index, 30 * index, 40 * index))
            draw = ImageDraw.Draw(image)
            draw.ellipse((176, 90, 336, 250), fill=(168, 132, 112))
            draw.rectangle((210, 250, 302, 500), fill=(80, 110, 150))
            image.save(final)
            row = {
                "assetId": asset_id,
                "profileId": "female_001",
                "gender": "female",
                "numericId": "001",
                "shotType": shot,
                "targetFaceType": "deer_like",
                "targetLooksLevelBand": "2.5-3.2",
                "promptTargetingVersion": "face_type_looks_level_targeting_v6",
                "promptHash": f"hash-{shot}",
                "finalPath": str(final),
                "localPath": str(final),
                "hasEyewear": target_has,
                "eyewearGroup": "glasses" if target_has else "none",
                "eyewear": expected,
                "canonicalEyewear": expected,
                "targetHasEyewear": target_has,
                "targetEyewearGroup": "glasses" if target_has else "none",
                "targetEyewear": expected,
                "targetCanonicalEyewear": expected,
                "targetShotEyewearExpected": expected,
                "shotEyewearExpected": expected,
                "temporaryEyewearAllowed": False,
                "temporaryEyewearApplied": False,
            }
            rows.append(row)
            file_qa.append({**row, "status": "file_qa_passed", "decision": "file_qa_passed"})
        manifests = paths.manifests
        self._write_jsonl(manifests / "generation_manifest.jsonl", rows)
        self._write_jsonl(manifests / "ai_profile_assets_v3.jsonl", rows)
        self._write_jsonl(manifests / "asset_manifest.jsonl", rows)
        self._write_jsonl(manifests / "file_qa_manifest.jsonl", file_qa)
        return root, rows

    def _asset_payload(self, rows, overrides=None):
        overrides = overrides or {}
        assets = []
        for row in rows:
            observed = overrides.get(row["shotType"], {})
            assets.append(
                {
                    "assetId": row["assetId"],
                    "profileId": row["profileId"],
                    "gender": row["gender"],
                    "shotType": row["shotType"],
                    "targetFaceType": row["targetFaceType"],
                    "observedFaceType": row["targetFaceType"],
                    "faceTypeConfidence": 0.95,
                    "targetLooksLevelBand": row["targetLooksLevelBand"],
                    "observedLooksLevelBand": row["targetLooksLevelBand"],
                    "looksLevelConfidence": 0.95,
                    "observedHasEyewear": observed.get("observedHasEyewear", row["targetHasEyewear"]),
                    "observedEyewearGroup": observed.get("observedEyewearGroup", row["targetEyewearGroup"]),
                    "observedEyewear": observed.get("observedEyewear", row["targetShotEyewearExpected"]),
                    "eyewearReadable": observed.get("eyewearReadable", True),
                    "eyewearMismatch": observed.get("eyewearMismatch", False),
                    "adultVisual": True,
                    "photoRealism": 4.5,
                    "campusRealism": 4.5,
                    "brandFit": 4.5,
                    "shotTypeReadable": True,
                    "influencerRisk": 0,
                    "childlikeRisk": 0,
                    "schoolUniformRisk": 0,
                    "sexualizationRisk": 0,
                    "artifactRisk": 0,
                    "metadataMismatch": False,
                    "mismatchFields": [],
                    "decision": "approved",
                    "rejectReasons": [],
                    "notes": "reviewed",
                }
            )
        return {"qaType": "seolleyeon_visual_verdict_asset_v3", "sheetId": "asset", "assets": assets}

    def test_asset_apply_flags_missing_required_eyewear(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_asset_qa

        root, rows = self._visual_root(target_has=True)
        payload = self._asset_payload(rows, {"face_card": {"observedHasEyewear": False, "observedEyewearGroup": "none", "observedEyewear": "none"}})
        source = root / "asset_qa.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        apply_asset_qa(root=root, input_path=str(source))
        records = [json.loads(line) for line in (root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
        face = next(row for row in records if row["shotType"] == "face_card")
        self.assertTrue(face["metadataMismatch"])
        self.assertIn("eyewear", face["mismatchFields"])
        self.assertIn(face["finalDecision"], {"needs_review", "rejected"})

    def test_asset_apply_rejects_unexpected_eyewear_and_hard_rejects_sunglasses(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_asset_qa

        root, rows = self._visual_root(target_has=False)
        payload = self._asset_payload(
            rows,
            {
                "face_card": {"observedHasEyewear": True, "observedEyewearGroup": "glasses", "observedEyewear": "thin_round_metal"},
                "vibe_card": {"observedHasEyewear": True, "observedEyewearGroup": "sunglasses", "observedEyewear": "sunglasses"},
            },
        )
        source = root / "asset_qa.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        apply_asset_qa(root=root, input_path=str(source))
        records = [json.loads(line) for line in (root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()]
        face = next(row for row in records if row["shotType"] == "face_card")
        vibe = next(row for row in records if row["shotType"] == "vibe_card")
        self.assertTrue(face["metadataMismatch"])
        self.assertIn("eyewear", face["mismatchFields"])
        self.assertEqual(vibe["finalDecision"], "rejected")
        self.assertIn("eyewear_sunglasses", vibe["hardRejectReasons"])

    def test_identity_with_unexpected_eyewear_change_does_not_approve(self):
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        root, rows = self._visual_root(target_has=True)
        asset_rows = []
        for row in rows:
            observed = "none" if row["shotType"] == "vibe_card" else row["targetShotEyewearExpected"]
            asset_rows.append(
                {
                    **row,
                    "finalDecision": "approved",
                    "decision": "approved",
                    "metadataMismatch": False,
                    "mismatchFields": [],
                    "hardReject": False,
                    "observedHasEyewear": observed != "none",
                    "observedEyewear": observed,
                    "observedEyewearGroup": "glasses" if observed != "none" else "none",
                }
            )
        self._write_jsonl(root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl", asset_rows)
        identity_payload = {
            "qaType": "seolleyeon_visual_verdict_identity_v3",
            "identities": [
                {
                    "profileId": "female_001",
                    "gender": "female",
                    "targetFaceType": "deer_like",
                    "observedFaceType": "deer_like",
                    "targetLooksLevelBand": "2.5-3.2",
                    "observedLooksLevelBand": "2.5-3.2",
                    "assetIds": {row["shotType"]: row["assetId"] for row in rows},
                    "assetDecisions": {row["shotType"]: "approved" for row in rows},
                    "faceToSilhouetteConsistency": 4.4,
                    "faceToVibeConsistency": 4.4,
                    "sameIdentity": True,
                    "completeIdentityDecision": "approved",
                    "countsTowardDistribution": True,
                    "failedShotTypes": [],
                    "retryShotTypes": [],
                    "rejectReasons": [],
                    "notes": "reviewed",
                }
            ],
        }
        source = root / "identity_qa.json"
        source.write_text(json.dumps(identity_payload), encoding="utf-8")
        apply_identity_qa(root=root, input_path=str(source))
        identity = json.loads((root / "ai_image" / "manifests" / "identity_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertNotEqual(identity["finalCompleteIdentityDecision"], "approved")
        self.assertIn("eyewear", identity["mismatchFields"])


if __name__ == "__main__":
    unittest.main()
