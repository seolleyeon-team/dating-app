import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class ActiveVisualVerdictRunnerV3Tests(unittest.TestCase):
    def _config(self, *, image_arg_mode="auto", exec_mode="auto"):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import ActiveVisualConfig

        return ActiveVisualConfig(
            codex_bin="codex",
            image_arg_mode=image_arg_mode,
            exec_mode=exec_mode,
            timeout_sec=30,
            max_images_per_call=1,
            max_sheets_per_run=10,
            strict=True,
        )

    def _write_fixture(self, root: Path) -> None:
        from scripts.ai_image_pipeline_v3.config import write_jsonl
        from PIL import Image

        prompts = root / "ai_image" / "prompts"
        prompts.mkdir(parents=True, exist_ok=True)
        for name in (
            "VISUAL_VERDICT_ASSET_QA_PROMPT.md",
            "VISUAL_VERDICT_IDENTITY_QA_PROMPT.md",
            "VISUAL_VERDICT_DISTRIBUTION_AUDIT_PROMPT.md",
        ):
            (prompts / name).write_text("Return strict JSON only.", encoding="utf-8")

        final_dir = root / "ai_image" / "female" / "001"
        final_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        file_qa_rows = []
        for shot in ("face_card", "silhouette_card", "vibe_card"):
            image_path = final_dir / f"{shot}.png"
            Image.new("RGB", (512, 768), (42, 84, 126)).save(image_path)
            row = (
                {
                    "assetId": f"female_001__{shot}__v001",
                    "profileId": "female_001",
                    "gender": "female",
                    "numericId": "001",
                    "shotType": shot,
                    "targetFaceType": "deer_like",
                    "targetLooksLevelBand": "2.5-3.2",
                    "finalPath": str(image_path),
                    "localPath": str(image_path),
                    "status": "recovered",
                }
            )
            rows.append(row)
            file_qa_rows.append(
                {
                    "assetId": row["assetId"],
                    "profileId": row["profileId"],
                    "gender": row["gender"],
                    "shotType": shot,
                    "qaStage": "file_qa",
                    "status": "file_qa_passed",
                    "decision": "file_qa_passed",
                }
            )
        manifests = root / "ai_image" / "manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        write_jsonl(manifests / "generation_manifest.jsonl", rows)
        write_jsonl(manifests / "ai_profile_assets_v3.jsonl", rows)
        write_jsonl(manifests / "file_qa_manifest.jsonl", file_qa_rows)

        sheets = root / "ai_image" / "reports" / "contact_sheets"
        (sheets / "identities").mkdir(parents=True, exist_ok=True)
        (sheets / "chunks").mkdir(parents=True, exist_ok=True)
        (sheets / "pilot_contact_sheet_female_face_card.png").write_bytes(b"asset sheet")
        (sheets / "identities" / "female_001.png").write_bytes(b"identity sheet")
        (sheets / "chunks" / "chunk_001.png").write_bytes(b"overview sheet")

    def _asset_payload(self):
        return {
            "qaType": "seolleyeon_visual_verdict_asset_v3",
            "sheetId": "asset",
            "assets": [
                {
                    "assetId": f"female_001__{shot}__v001",
                    "profileId": "female_001",
                    "gender": "female",
                    "shotType": shot,
                    "targetFaceType": "deer_like",
                    "observedFaceType": "deer_like",
                    "faceTypeConfidence": 0.9,
                    "targetLooksLevelBand": "2.5-3.2",
                    "observedLooksLevelBand": "2.5-3.2",
                    "looksLevelConfidence": 0.9,
                    "adultVisual": True,
                    "photoRealism": 4.4,
                    "campusRealism": 4.3,
                    "brandFit": 4.4,
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
                for shot in ("face_card", "silhouette_card", "vibe_card")
            ],
            "summary": {"approvedCount": 3, "needsReviewCount": 0, "rejectedCount": 0, "hardRejectCount": 0, "metadataMismatchCount": 0},
        }

    def _identity_payload(self):
        return {
            "qaType": "seolleyeon_visual_verdict_identity_v3",
            "identities": [
                {
                    "profileId": "female_001",
                    "gender": "female",
                    "targetFaceType": "deer_like",
                    "observedFaceType": "deer_like",
                    "targetLooksLevelBand": "2.5-3.2",
                    "observedLooksLevelBand": "2.5-3.2",
                    "assetIds": {shot: f"female_001__{shot}__v001" for shot in ("face_card", "silhouette_card", "vibe_card")},
                    "assetDecisions": {"face_card": "approved", "silhouette_card": "approved", "vibe_card": "approved"},
                    "faceToSilhouetteConsistency": 4.2,
                    "faceToVibeConsistency": 4.2,
                    "sameIdentity": True,
                    "completeIdentityDecision": "approved",
                    "countsTowardDistribution": True,
                    "failedShotTypes": [],
                    "retryShotTypes": [],
                    "rejectReasons": [],
                    "notes": "reviewed",
                }
            ],
            "summary": {"approvedCompleteIdentities": 1, "needsReviewIdentities": 0, "rejectedIdentities": 0, "missingShotIdentities": 0, "identityMismatchCount": 0},
        }

    def _distribution_payload(self, root: Path):
        from scripts.ai_image_pipeline_v3.distribution_audit import audit_distribution

        audit = audit_distribution(root=root)
        return {
            "qaType": "seolleyeon_visual_verdict_distribution_v3",
            "finalDecision": audit["finalDecision"],
            "approvedCompleteIdentityCount": audit["approvedCompleteIdentityCount"],
            "approvedImageCount": audit["approvedImageCount"],
            "femaleApprovedIdentityCount": audit["femaleApprovedIdentityCount"],
            "maleApprovedIdentityCount": audit["maleApprovedIdentityCount"],
            "globalFaceTypeCounts": audit["globalFaceTypeCounts"],
            "globalFaceTypeDeficits": audit["globalFaceTypeDeficits"],
            "globalFaceTypeSurpluses": audit["globalFaceTypeSurpluses"],
            "genderFaceTypeCounts": audit["genderFaceTypeCounts"],
            "genderFaceTypeDeficits": audit["genderFaceTypeDeficits"],
            "genderFaceTypeSurpluses": audit["genderFaceTypeSurpluses"],
            "globalLooksLevelBandCounts": audit["globalLooksLevelBandCounts"],
            "globalLooksLevelBandDeficits": audit["globalLooksLevelBandDeficits"],
            "globalLooksLevelBandSurpluses": audit["globalLooksLevelBandSurpluses"],
            "genderLooksLevelBandCounts": audit["genderLooksLevelBandCounts"],
            "genderLooksLevelBandDeficits": audit["genderLooksLevelBandDeficits"],
            "genderLooksLevelBandSurpluses": audit["genderLooksLevelBandSurpluses"],
            "invalidIdentities": audit.get("invalidIdentities", []),
            "nextGenerationDirective": {"shouldGenerateMore": True, "targetBuckets": audit.get("nextTargetBuckets", []), "stopGeneratingBuckets": audit.get("forbiddenBuckets", [])},
            "notes": "reviewed",
        }

    def _fake_run(self, root: Path, *, fail_actual=False, invalid_actual=False, help_text="--image -i"):
        def run(args, **kwargs):
            if "--help" in args:
                return subprocess.CompletedProcess(args, 0, stdout=help_text, stderr="")
            if fail_actual:
                return subprocess.CompletedProcess(args, 3, stdout="", stderr="failed")
            prompt = kwargs.get("input") or args[-1]
            if invalid_actual:
                return subprocess.CompletedProcess(args, 0, stdout="not json", stderr="")
            if "seolleyeon_visual_verdict_identity_v3" in prompt:
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(self._identity_payload()), stderr="")
            if "seolleyeon_visual_verdict_asset_v3" in prompt:
                return subprocess.CompletedProcess(args, 0, stdout=json.dumps(self._asset_payload()), stderr="")
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(self._distribution_payload(root)), stderr="")

        return run

    def test_command_builder_supports_all_codex_image_forms(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import CodexCommandForm, build_codex_args

        image = Path("sheet.png")
        cases = (
            (CodexCommandForm("direct", "image"), ["codex", "--image", str(image.resolve()), "prompt"]),
            (CodexCommandForm("direct", "short_i"), ["codex", "-i", str(image.resolve()), "prompt"]),
            (CodexCommandForm("exec", "image"), ["codex", "exec", "--image", str(image.resolve()), "prompt"]),
            (CodexCommandForm("exec", "short_i"), ["codex", "exec", "-i", str(image.resolve()), "prompt"]),
        )
        for form, expected in cases:
            with self.subTest(form=form):
                self.assertEqual(build_codex_args("prompt", [image], config=self._config(), form=form), expected)
        rooted = build_codex_args("prompt", [image], config=self._config(), form=CodexCommandForm("exec", "image"), root=Path("C:/work"))
        self.assertEqual(rooted[-3:], ["-C", str(Path("C:/work").resolve()), "prompt"])
        stdin_args = build_codex_args("prompt", [image], config=self._config(), form=CodexCommandForm("exec", "image"), root=Path("C:/work"), prompt_via_stdin=True)
        self.assertEqual(stdin_args[-2:], ["-C", str(Path("C:/work").resolve())])
        self.assertNotIn("prompt", stdin_args)

    def test_contact_sheet_classification_ignores_final_in_workspace_path(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import _classify_sheet

        base = Path("C:/Users/samsung/StudioProjects/semisemifinal/ai_image/reports/chunks/e2e/contact_sheets")
        self.assertEqual(_classify_sheet(base / "e2e_contact_sheet_female_face_card.png"), "asset")
        self.assertEqual(_classify_sheet(base / "female_997.png"), "identity")
        self.assertEqual(_classify_sheet(base / "chunk_001.png"), "overview")
        self.assertEqual(_classify_sheet(base / "distribution_overview.png"), "distribution")

    def test_chunk_filter_keeps_only_chunk_scoped_contact_sheets(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import ContactSheetEntry, _filter_chunk_entries

        entries = [
            ContactSheetEntry("e2e_chunk__contact_sheet_female_face_card", Path("chunk-face.png"), "asset"),
            ContactSheetEntry("e2e_chunk__identities__female_997", Path("chunk-identity.png"), "identity"),
            ContactSheetEntry("pilot_contact_sheet_female_face_card", Path("global-face.png"), "asset"),
            ContactSheetEntry("identities__female_001", Path("global-identity.png"), "identity"),
        ]
        filtered = _filter_chunk_entries(entries, "e2e_chunk")
        self.assertEqual([entry.sheet_id for entry in filtered], ["e2e_chunk__contact_sheet_female_face_card", "e2e_chunk__identities__female_997"])

    def test_chunk_index_scopes_stage_asset_and_plan_identity_sheets(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import build_contact_sheet_index, _filter_chunk_entries

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            manifests = root / "ai_image" / "manifests"
            chunk_id = "chunk_test_001"
            (manifests / "current_chunk_plan.json").write_text(
                json.dumps({"chunkId": chunk_id, "identities": [{"profileId": "female_001"}]}),
                encoding="utf-8",
            )
            sheets = root / "ai_image" / "reports" / "contact_sheets"
            (sheets / f"{chunk_id}_contact_sheet_female_face_card.png").write_bytes(b"asset sheet")

            entries = build_contact_sheet_index(root=root, chunk_id=chunk_id)
            filtered = _filter_chunk_entries(entries, chunk_id)
            sheet_ids = [entry.sheet_id for entry in filtered]

            self.assertIn(f"{chunk_id}__{chunk_id}_contact_sheet_female_face_card", sheet_ids)
            self.assertIn(f"{chunk_id}__identities__female_001", sheet_ids)
            self.assertNotIn("pilot_contact_sheet_female_face_card", sheet_ids)

    def test_probe_prefers_exec_image_form_when_available(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import discover_command_forms

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            forms = discover_command_forms(root=root, config=self._config(), run_func=self._fake_run(root, help_text="--image -i"))
            self.assertGreaterEqual(len(forms), 2)
            self.assertEqual(forms[0].exec_mode, "exec")
            self.assertEqual(forms[0].image_arg_mode, "image")

    def test_probe_fails_gracefully_when_image_input_is_unavailable(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import probe_codex_image_input

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = probe_codex_image_input(root=root, config=self._config(), run_func=self._fake_run(root, help_text="usage only"))
            self.assertFalse(result["available"])
            self.assertTrue((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())

    def test_json_extraction_plain_fenced_invalid_and_multiple(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import extract_json_object

        self.assertEqual(extract_json_object('{"a":1}')["a"], 1)
        self.assertEqual(extract_json_object('```json\n{"a":2}\n```')["a"], 2)
        noisy = "SUCCESS: The process with PID 123 (child process of PID 456) has been terminated.\n{\"a\":3}"
        self.assertEqual(extract_json_object(noisy)["a"], 3)
        with self.assertRaises(ValueError):
            extract_json_object("no json")
        with self.assertRaises(ValueError):
            extract_json_object('Here is JSON:\n{"a":1}')
        with self.assertRaises(ValueError):
            extract_json_object('{"a":1} {"b":2}')

    def test_part_merges_and_conflict_rejection(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import merge_asset_parts, merge_identity_parts

        asset_part = self._asset_payload()
        identity_part = self._identity_payload()
        self.assertEqual(len(merge_asset_parts([asset_part])["assets"]), 3)
        self.assertEqual(len(merge_identity_parts([identity_part])["identities"]), 1)
        conflict = json.loads(json.dumps(asset_part))
        conflict["assets"][0]["observedFaceType"] = "fox_like"
        with self.assertRaises(ValueError):
            merge_asset_parts([asset_part, conflict])
        identity_conflict = json.loads(json.dumps(identity_part))
        identity_conflict["identities"][0]["sameIdentity"] = False
        with self.assertRaises(ValueError):
            merge_identity_parts([identity_part, identity_conflict])

    def test_successful_mocked_asset_identity_and_distribution_write_latest_json(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import (
            run_active_visual_asset_qa,
            run_active_visual_distribution_qa,
            run_active_visual_identity_qa,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            fake_run = self._fake_run(root)
            run_active_visual_asset_qa(root=root, config=self._config(), run_func=fake_run)
            self.assertTrue((root / "ai_image" / "reports" / "visual_verdict" / "asset_qa_latest.json").exists())
            run_active_visual_identity_qa(root=root, config=self._config(), run_func=fake_run)
            self.assertTrue((root / "ai_image" / "reports" / "visual_verdict" / "identity_qa_latest.json").exists())
            run_active_visual_distribution_qa(root=root, config=self._config(), run_func=fake_run)
            self.assertTrue((root / "ai_image" / "reports" / "visual_verdict" / "distribution_audit_latest.json").exists())

    def test_distribution_qa_falls_back_to_text_only_when_image_input_unavailable(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import run_active_visual_distribution_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            run_active_visual_asset_qa = __import__(
                "scripts.ai_image_pipeline_v3.active_visual_verdict_runner",
                fromlist=["run_active_visual_asset_qa"],
            ).run_active_visual_asset_qa
            run_active_visual_identity_qa = __import__(
                "scripts.ai_image_pipeline_v3.active_visual_verdict_runner",
                fromlist=["run_active_visual_identity_qa"],
            ).run_active_visual_identity_qa
            run_active_visual_asset_qa(root=root, config=self._config(), run_func=self._fake_run(root))
            run_active_visual_identity_qa(root=root, config=self._config(), run_func=self._fake_run(root))

            calls = []

            def fake_run(args, **kwargs):
                calls.append(args)
                return self._fake_run(root, help_text="usage only")(args, **kwargs)

            result = run_active_visual_distribution_qa(root=root, config=self._config(), run_func=fake_run)
            self.assertTrue((root / "ai_image" / "reports" / "visual_verdict" / "distribution_audit_latest.json").exists())
            self.assertTrue(result["applied"])
            actual_calls = [args for args in calls if "--help" not in args]
            self.assertTrue(actual_calls)
            self.assertFalse(any("--image" in args or "-i" in args for args in actual_calls))
            self.assertFalse((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())

    def test_active_visual_all_stops_on_asset_failure_and_then_runs_successfully(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import run_active_visual_qa_all

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            with self.assertRaises(Exception):
                run_active_visual_qa_all(root=root, config=self._config(), run_func=self._fake_run(root, invalid_actual=True))
            self.assertTrue((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            result = run_active_visual_qa_all(root=root, config=self._config(), run_func=self._fake_run(root))
            self.assertIn("distributionAuditAfter", result)
            self.assertFalse(result["completion"]["passed"])

    def test_coverage_rejects_unbacked_approved_identity_and_overlevel_asset(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import coverage_check
        from scripts.ai_image_pipeline_v3.config import write_jsonl

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            manifests = root / "ai_image" / "manifests"
            write_jsonl(
                manifests / "identity_qa_manifest.jsonl",
                [
                    {
                        "profileId": "female_001",
                        "finalCompleteIdentityDecision": "approved",
                        "countsTowardDistribution": True,
                        "sameIdentity": True,
                        "metadataMismatch": False,
                        "observedLooksLevelBand": "2.5-3.2",
                    }
                ],
            )
            write_jsonl(
                manifests / "approved_identity_manifest.jsonl",
                [{"profileId": "female_001", "assetIds": {shot: f"female_001__{shot}__v001" for shot in ("face_card", "silhouette_card", "vibe_card")}}],
            )
            result = coverage_check(root=root)
            self.assertFalse(result["passed"])
            self.assertIn("female_001", result["invalidApprovedProfileIds"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            manifests = root / "ai_image" / "manifests"
            asset_rows = self._asset_payload()["assets"]
            asset_rows[0]["finalDecision"] = "approved"
            asset_rows[0]["observedLooksLevelBand"] = "4.4-5.0"
            write_jsonl(manifests / "asset_qa_manifest.jsonl", asset_rows)
            result = coverage_check(root=root)
            self.assertFalse(result["passed"])
            self.assertIn("female_001__face_card__v001", result["invalidApprovedAssetIds"])

    def test_runner_does_not_fabricate_json_on_subprocess_failure_or_missing_image(self):
        from scripts.ai_image_pipeline_v3.active_visual_verdict_runner import run_active_visual_asset_qa, run_codex_visual_call

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_fixture(root)
            with self.assertRaises(Exception):
                run_active_visual_asset_qa(root=root, config=self._config(), run_func=self._fake_run(root, fail_actual=True), apply_after=False)
            self.assertFalse((root / "ai_image" / "reports" / "visual_verdict" / "asset_qa_latest.json").exists())
            with self.assertRaises(Exception):
                run_codex_visual_call(root=root, qa_slug="asset_qa", prompt="{}", image_paths=[], config=self._config(), run_func=self._fake_run(root))


if __name__ == "__main__":
    unittest.main()
