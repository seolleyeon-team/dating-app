import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class AiImagePipelineV3Tests(unittest.TestCase):
    def _write_exact_visual_fixture(self, root: Path, *, mutate: str | None = None) -> None:
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.distribution_targets import DEFAULT_DISTRIBUTION_TARGETS, write_default_distribution_targets
        from scripts.ai_image_pipeline_v3.manifest import enrich_asset, write_generation_outputs

        write_default_distribution_targets(root=root, force=True)
        manifests = root / "ai_image" / "manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        identities = []
        assets = []
        season_sequence = [season for season, count in DEFAULT_DISTRIBUTION_TARGETS["seasonTargets"]["global"].items() for _ in range(count)]
        eyewear_seen_by_gender = {"female": 0, "male": 0}
        index = 0
        for gender in ("female", "male"):
            face_targets = DEFAULT_DISTRIBUTION_TARGETS["faceTypeTargets"][gender]
            looks_targets = DEFAULT_DISTRIBUTION_TARGETS["looksLevelBandTargets"][gender]
            faces = [face for face, count in face_targets.items() for _ in range(count)]
            looks = [band for band, count in looks_targets.items() for _ in range(count)]
            for number, (face_type, band) in enumerate(zip(faces, looks), start=1):
                profile_id = f"{gender}_{number:03d}"
                eyewear_seen_by_gender[gender] += 1
                with_eyewear_target = int(DEFAULT_DISTRIBUTION_TARGETS["eyewearTargets"][gender]["with_eyewear"])
                eyewear_bucket = "with_eyewear" if eyewear_seen_by_gender[gender] <= with_eyewear_target else "without_eyewear"
                season = season_sequence[index]
                identity = {
                    "profileId": profile_id,
                    "gender": gender,
                    "targetFaceType": face_type,
                    "observedFaceType": face_type,
                    "faceTypeConfidence": 0.9,
                    "targetLooksLevelBand": band,
                    "observedLooksLevelBand": band,
                    "looksLevelConfidence": 0.9,
                    "eyewearBucket": eyewear_bucket,
                    "season": season,
                    "assetDecisions": {"face_card": "approved", "silhouette_card": "approved", "vibe_card": "approved"},
                    "completeIdentityDecision": "approved",
                    "countsTowardDistribution": True,
                    "sameIdentity": True,
                    "metadataMismatch": False,
                }
                if index == 0 and mutate == "metadataMismatch":
                    identity["metadataMismatch"] = True
                    identity["mismatchFields"] = ["targetFaceType"]
                if index == 0 and mutate == "over_level":
                    identity["observedLooksLevelBand"] = "4.4-5.0"
                    identity["looksLevelConfidence"] = 0.95
                if index == 0 and mutate == "needs_review":
                    identity["completeIdentityDecision"] = "needs_review"
                if index == 0 and mutate == "missing_vibe":
                    identity["assetDecisions"]["vibe_card"] = "missing"
                identities.append(identity)
                for shot in ("face_card", "silhouette_card", "vibe_card"):
                    asset_decision = identity["assetDecisions"][shot]
                    assets.append(
                        {
                            "assetId": f"{profile_id}__{shot}__v001",
                            "profileId": profile_id,
                            "gender": gender,
                            "shotType": shot,
                            "targetFaceType": face_type,
                            "observedFaceType": identity["observedFaceType"],
                            "faceTypeConfidence": 0.9,
                            "targetLooksLevelBand": band,
                            "observedLooksLevelBand": identity["observedLooksLevelBand"],
                            "looksLevelConfidence": 0.9,
                            "eyewearBucket": identity["eyewearBucket"],
                            "hasEyewear": identity["eyewearBucket"] == "with_eyewear",
                            "eyewearGroup": "glasses" if identity["eyewearBucket"] == "with_eyewear" else "none",
                            "season": identity["season"],
                            "decision": "approved" if asset_decision == "approved" else asset_decision,
                            "metadataMismatch": bool(identity.get("metadataMismatch")),
                        }
                    )
                index += 1
        write_jsonl(manifests / "identity_qa_manifest.jsonl", identities)
        write_jsonl(manifests / "asset_qa_manifest.jsonl", assets)

        paths = pipeline_paths(root)
        generation_rows = [
            enrich_asset(
                {
                    "profileId": asset["profileId"],
                    "assetId": asset["assetId"],
                    "gender": asset["gender"],
                    "shotType": asset["shotType"],
                    "targetFaceType": asset["targetFaceType"],
                    "targetLooksLevelBand": asset["targetLooksLevelBand"],
                    "prompt": "p",
                },
                paths,
                status="file_qa_passed",
            )
            for asset in assets
        ]
        write_generation_outputs(paths, generation_rows)
        write_jsonl(manifests / "ai_profile_assets_v3.jsonl", generation_rows)
        generation_by_asset = {row["assetId"]: row for row in generation_rows}
        try:
            from PIL import Image

            sample = paths.root / "ai_image" / "fixture_sample.png"
            sample.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (512, 768), color=(200, 200, 200)).save(sample)
            image_bytes = sample.read_bytes()
        except Exception:
            image_bytes = b""
        file_qa_rows = []
        for row in generation_rows:
            final_path = Path(row["finalPath"])
            final_path.parent.mkdir(parents=True, exist_ok=True)
            if image_bytes:
                final_path.write_bytes(image_bytes)
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
        write_jsonl(manifests / "file_qa_manifest.jsonl", file_qa_rows)
        approved_rows = []
        for identity in identities:
            profile_id = identity["profileId"]
            asset_ids = {shot: f"{profile_id}__{shot}__v001" for shot in ("face_card", "silhouette_card", "vibe_card")}
            approved_rows.append(
                {
                    "schemaVersion": "seolleyeon_approved_identity_manifest_v3",
                    "profileId": profile_id,
                    "gender": identity["gender"],
                    "numericId": profile_id.split("_", 1)[1],
                    "faceType": identity["observedFaceType"],
                    "looksLevelBand": identity["observedLooksLevelBand"],
                    "observedFaceType": identity["observedFaceType"],
                    "observedLooksLevelBand": identity["observedLooksLevelBand"],
                    "eyewearBucket": identity["eyewearBucket"],
                    "hasEyewear": identity["eyewearBucket"] == "with_eyewear",
                    "eyewearGroup": "glasses" if identity["eyewearBucket"] == "with_eyewear" else "none",
                    "season": identity["season"],
                    "assetIds": asset_ids,
                    "finalPaths": {shot: generation_by_asset[asset_id]["finalPath"] for shot, asset_id in asset_ids.items()},
                    "finalCompleteIdentityDecision": identity["completeIdentityDecision"],
                    "countsTowardDistribution": True,
                    "metadataMismatch": bool(identity.get("metadataMismatch")),
                }
            )
        write_jsonl(manifests / "approved_identity_manifest.jsonl", approved_rows)

    def _write_generation_rows(self, root: Path, rows: list[dict]) -> None:
        from scripts.ai_image_pipeline_v3.config import write_jsonl

        manifests = root / "ai_image" / "manifests"
        manifests.mkdir(parents=True, exist_ok=True)
        write_jsonl(manifests / "generation_manifest.jsonl", rows)

    def test_default_image_model_uses_codex_builtin_imagegen(self) -> None:
        from scripts.ai_image_pipeline_v3.config import DEFAULT_MODEL

        self.assertEqual(DEFAULT_MODEL, "codex-built-in-imagegen")

    def test_makefile_exposes_required_imagegen_operator_targets(self) -> None:
        makefile = Path("Makefile").read_text(encoding="utf-8")

        for target in (
            "ai-image-dry-run:",
            "ai-image-prepare-smoke:",
            "ai-image-prepare-pilot:",
            "ai-image-prepare-720:",
            "ai-image-next:",
            "ai-image-recover:",
            "ai-image-qa:",
            "ai-image-retry:",
            "ai-image-summary:",
        ):
            self.assertIn(target, makefile)
        self.assertIn("scripts/prepare_ai_image_assets_v3.py --root . --female_count 1 --male_count 0", makefile)
        self.assertIn("scripts/next_codex_imagegen_prompt_v3.py --root .", makefile)

    def test_prepare_dry_run_writes_three_asset_manifest_and_status(self) -> None:
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = prepare_assets(
                root=root,
                female_count=1,
                male_count=0,
                limit=3,
                dry_run=True,
                force=True,
            )

            assets_path = root / "ai_image" / "manifests" / "ai_profile_assets_v3.jsonl"
            manifest_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            status_path = root / "ai_image" / "reports" / "generation_status.csv"

            self.assertEqual(result.asset_count, 3)
            self.assertTrue(assets_path.exists())
            self.assertTrue(manifest_path.exists())
            self.assertTrue(status_path.exists())

            assets = [json.loads(line) for line in assets_path.read_text(encoding="utf-8").splitlines()]
            manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
            with status_path.open("r", encoding="utf-8", newline="") as f:
                status_rows = list(csv.DictReader(f))

            self.assertEqual([row["shotType"] for row in assets], ["face_card", "silhouette_card", "vibe_card"])
            self.assertEqual([row["status"] for row in manifest], ["prepared", "prepared", "prepared"])
            self.assertEqual([row["status"] for row in status_rows], ["prepared", "prepared", "prepared"])
            self.assertTrue((root / "ai_image" / "raw").exists())
            self.assertTrue(manifest[0]["localPath"].endswith("ai_image/raw/female_001__face_card__v001__attempt01.png"))
            self.assertTrue(manifest[0]["approvedPath"].endswith("ai_image/approved/female_001__face_card__v001.png"))
            self.assertTrue(
                manifest[0]["rejectedPath"].endswith("ai_image/rejected/female_001__face_card__v001__attempt01.png")
            )

    def test_default_prepare_targets_720_final_assets_plus_reserves_for_full_workflow(self) -> None:
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = prepare_assets(root=root, dry_run=True, force=True)
            manifest_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(result.specs_count, 280)
            self.assertEqual(result.asset_count, 840)
            self.assertEqual(len(manifest), 840)
            self.assertEqual(sum(row["gender"] == "female" for row in manifest), 420)
            self.assertEqual(sum(row["gender"] == "male" for row in manifest), 420)
            self.assertEqual(sum(row["identityScope"] == "reserve" for row in manifest), 120)

    def test_public_final_path_matches_ai_image_gender_id_shot(self) -> None:
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.manifest import public_final_path

        with tempfile.TemporaryDirectory() as tmp:
            paths = pipeline_paths(Path(tmp))
            asset = {
                "profileId": "female_001",
                "gender": "female",
                "shotType": "vibe_card",
            }

            self.assertEqual(
                public_final_path(paths, asset),
                Path(tmp).resolve() / "ai_image" / "female" / "001" / "vibe_card.png",
            )

    def test_prepare_supports_reserved_identity_profile_ids(self) -> None:
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = prepare_assets(
                root=root,
                female_count=0,
                male_count=0,
                reserve_female_count=0,
                reserve_male_count=0,
                reserve_identities=["female_901", "male_902"],
                dry_run=True,
                force=True,
            )

            manifest_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(result.specs_count, 2)
            self.assertEqual(result.asset_count, 6)
            self.assertEqual({row["profileId"] for row in manifest}, {"female_901", "male_902"})
            self.assertEqual({row["identityScope"] for row in manifest}, {"reserve"})
            self.assertEqual({row["isReserve"] for row in manifest}, {True})
            self.assertTrue(
                any(row["localPath"].endswith("ai_image/raw/female_901__face_card__v001__attempt01.png") for row in manifest)
            )
            self.assertTrue(
                any(row["localPath"].endswith("ai_image/raw/male_902__face_card__v001__attempt01.png") for row in manifest)
            )

    def test_prepare_replace_manifest_drops_stale_reserve_rows_for_dry_run(self) -> None:
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_assets(
                root=root,
                female_count=0,
                male_count=0,
                reserve_female_count=0,
                reserve_male_count=0,
                reserve_identities=["female_901"],
                dry_run=True,
                replace_manifest=True,
            )
            prepare_assets(
                root=root,
                female_count=1,
                male_count=0,
                reserve_female_count=0,
                reserve_male_count=0,
                limit=3,
                dry_run=True,
                replace_manifest=True,
            )

            manifest_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(len(manifest), 3)
            self.assertEqual({row["profileId"] for row in manifest}, {"female_001"})
            self.assertEqual({row["identityScope"] for row in manifest}, {"production"})

    def test_two_pass_generation_sequences_all_faces_before_dependents(self) -> None:
        from scripts.ai_image_pipeline_v3.generate import generation_sequence

        rows = [
            {"assetId": "female_001__face_card__v001", "profileId": "female_001", "shotType": "face_card"},
            {"assetId": "female_001__silhouette_card__v001", "profileId": "female_001", "shotType": "silhouette_card"},
            {"assetId": "female_001__vibe_card__v001", "profileId": "female_001", "shotType": "vibe_card"},
            {"assetId": "female_002__face_card__v001", "profileId": "female_002", "shotType": "face_card"},
            {"assetId": "female_002__silhouette_card__v001", "profileId": "female_002", "shotType": "silhouette_card"},
            {"assetId": "female_002__vibe_card__v001", "profileId": "female_002", "shotType": "vibe_card"},
        ]
        selected_ids = {row["assetId"] for row in rows}

        ordered = generation_sequence(rows, selected_ids=selected_ids, two_pass_reference=True)

        self.assertEqual(
            [row["shotType"] for row in ordered],
            ["face_card", "face_card", "silhouette_card", "vibe_card", "silhouette_card", "vibe_card"],
        )

    def test_target_approved_identity_filters_generation_and_uses_final_face_reference(self) -> None:
        from scripts.ai_image_pipeline_v3.generate import generate_images
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_assets(root=root, female_count=2, male_count=0, dry_run=True, force=True)
            final_face = root / "ai_image" / "female" / "001" / "face_card.png"
            final_face.parent.mkdir(parents=True, exist_ok=True)
            final_face.write_bytes(b"approved-face")

            counts = generate_images(
                root=root,
                dry_run=True,
                target_approved_identity="female_001",
            )

            manifest_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
            selected = [row for row in manifest if row["profileId"] == "female_001"]
            untouched = [row for row in manifest if row["profileId"] == "female_002"]

            self.assertEqual(counts["selected"], 3)
            self.assertEqual([row["status"] for row in selected], ["dry_run", "dry_run", "dry_run"])
            self.assertEqual([row["status"] for row in untouched], ["prepared", "prepared", "prepared"])
            self.assertTrue(
                all(
                    row["resolvedReferencePath"].endswith("ai_image/female/001/face_card.png")
                    for row in selected
                    if row["shotType"] != "face_card"
                )
            )

    def test_retry_plan_excludes_assets_over_max_attempts_and_approved_outputs(self) -> None:
        from scripts.ai_image_pipeline_v3.retry_plan import select_retryable_assets

        rows = [
            {"assetId": "a", "status": "failed", "attemptCount": 1, "finalPath": ""},
            {"assetId": "b", "status": "failed", "attemptCount": 3, "finalPath": ""},
            {"assetId": "c", "status": "qa_approved", "attemptCount": 1, "finalPath": ""},
        ]

        selected = select_retryable_assets(rows, max_attempts=3, force=False)

        self.assertEqual([row["assetId"] for row in selected], ["a"])

    def test_vision_qa_dry_run_writes_contract_based_report_without_api_call(self) -> None:
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets
        from scripts.ai_image_pipeline_v3.vision_qa import run_vision_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_assets(root=root, female_count=1, male_count=0, limit=3, dry_run=True, force=True)

            counts = run_vision_qa(root=root, dry_run=True)

            report_path = root / "ai_image" / "reports" / "vision_qa_report.jsonl"
            rows = [json.loads(line) for line in report_path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(counts["checked"], 3)
            self.assertEqual({row["decision"] for row in rows}, {"needs_review"})
            self.assertTrue(all(row["adultVisual"] for row in rows))
            self.assertTrue(all("dry_run_no_api_call" in row["reasons"] for row in rows))

    def test_identity_consistency_qa_detects_available_reference_for_identity(self) -> None:
        from scripts.ai_image_pipeline_v3.identity_consistency import run_identity_consistency_qa
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_assets(root=root, female_count=1, male_count=0, limit=3, dry_run=True, force=True)
            manifest_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
            face = Path(next(row["localPath"] for row in manifest if row["shotType"] == "face_card"))
            face.parent.mkdir(parents=True, exist_ok=True)
            face.write_bytes(b"fake-face-reference")

            counts = run_identity_consistency_qa(root=root)

            report_path = root / "ai_image" / "reports" / "identity_consistency_report.jsonl"
            rows = [json.loads(line) for line in report_path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(counts["checkedIdentities"], 1)
            self.assertEqual(rows[0]["completeIdentityDecision"], "needs_retry")
            self.assertEqual(rows[0]["profileId"], "female_001")

    def test_duplicate_audit_groups_duplicate_image_hashes(self) -> None:
        from scripts.ai_image_pipeline_v3.duplicate_audit import audit_duplicates
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_assets(root=root, female_count=1, male_count=0, limit=3, dry_run=True, force=True)
            manifest_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
            for shot in ("face_card", "silhouette_card"):
                path = Path(next(row["localPath"] for row in manifest if row["shotType"] == shot))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"same-image-bytes")

            counts = audit_duplicates(root=root)

            report_path = root / "ai_image" / "reports" / "duplicate_audit_report.csv"
            with report_path.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))

            self.assertEqual(counts["duplicateGroups"], 1)
            self.assertEqual(len(rows), 2)
            self.assertEqual({row["duplicateGroup"] for row in rows}, {"sha256:0"})

    def test_duplicate_audit_ignores_empty_or_directory_image_paths(self) -> None:
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.duplicate_audit import audit_duplicates
        from scripts.ai_image_pipeline_v3.manifest import enrich_asset, write_generation_outputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = pipeline_paths(root)
            row = enrich_asset(
                {
                    "profileId": "female_001",
                    "assetId": "female_001__face_card__v001",
                    "gender": "female",
                    "shotType": "face_card",
                    "prompt": "p",
                    "status": "qa_rejected",
                },
                paths,
            )
            row["localPath"] = ""
            row["rawPath"] = ""
            row["finalPath"] = ""
            write_generation_outputs(paths, [row])

            counts = audit_duplicates(root=root)

            self.assertEqual(counts["checked"], 0)

    def test_contact_sheet_generation_writes_png_for_existing_assets(self) -> None:
        from PIL import Image

        from scripts.ai_image_pipeline_v3.contact_sheet import generate_contact_sheet
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_assets(root=root, female_count=1, male_count=0, limit=3, dry_run=True, force=True)
            manifest_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
            for index, shot in enumerate(("face_card", "silhouette_card", "vibe_card")):
                path = Path(next(row["localPath"] for row in manifest if row["shotType"] == shot))
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (64, 64), (40 + index * 20, 80, 120)).save(path)

            result = generate_contact_sheet(root=root, output_name="test_contact_sheet.png")

            self.assertTrue(result.output_path.exists())
            self.assertEqual(result.image_count, 3)

    def test_full_runner_requires_smoke_and_pilot_gate_before_starting(self) -> None:
        from scripts.ai_image_pipeline_v3.runner import run_pipeline

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                run_pipeline(mode="full", root=Path(tmp), dry_run=True, qa=False)

    def test_runner_supports_target_approved_identity_mode(self) -> None:
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets
        from scripts.ai_image_pipeline_v3.runner import run_pipeline

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_assets(root=root, female_count=1, male_count=0, dry_run=True, force=True)
            final_face = root / "ai_image" / "female" / "001" / "face_card.png"
            final_face.parent.mkdir(parents=True, exist_ok=True)
            final_face.write_bytes(b"approved-face")

            result = run_pipeline(
                mode="target-approved-identity",
                root=root,
                dry_run=True,
                qa=False,
                target_approved_identity="female_001",
            )

            self.assertEqual(result["mode"], "target-approved-identity")
            self.assertEqual(result["generation"]["selected"], 3)

    def test_target_approved_identity_keeps_existing_face_anchor_without_api_call(self) -> None:
        from scripts.ai_image_pipeline_v3.generate import generate_images
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_assets(root=root, female_count=1, male_count=0, dry_run=True, force=True)
            final_face = root / "ai_image" / "female" / "001" / "face_card.png"
            final_face.parent.mkdir(parents=True, exist_ok=True)
            final_face.write_bytes(b"approved-face")

            counts = generate_images(
                root=root,
                limit=1,
                dry_run=False,
                target_approved_identity="female_001",
            )

            manifest_path = root / "ai_image" / "manifests" / "generation_manifest.jsonl"
            manifest = [json.loads(line) for line in manifest_path.read_text(encoding="utf-8").splitlines()]
            face_row = next(row for row in manifest if row["shotType"] == "face_card")

            self.assertEqual(counts["selected"], 1)
            self.assertEqual(counts["skipped"], 1)
            self.assertEqual(face_row["status"], "qa_approved")
            self.assertFalse(face_row["dryRun"])
            self.assertTrue(face_row["resolvedReferencePath"].endswith("ai_image/female/001/face_card.png"))

    def test_smoke_run_gate_rejects_generation_failures(self) -> None:
        from scripts.ai_image_pipeline_v3.runner import run_pipeline

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failed_generation = {
                "selected": 3,
                "completed": 2,
                "skipped": 0,
                "failed": 1,
                "dry_run": 0,
                "waiting_reference": 0,
            }
            with patch("scripts.ai_image_pipeline_v3.runner.generate_images", return_value=failed_generation):
                with self.assertRaises(RuntimeError):
                    run_pipeline(mode="smoke", root=root, dry_run=False, qa=False)

            gate = json.loads((root / "ai_image" / "reports" / "smoke_run_gate.json").read_text(encoding="utf-8"))
            self.assertFalse(gate["passed"])
            self.assertIn("generation_failed", gate["reasons"])

    def test_smoke_run_gate_rejects_manual_review_status(self) -> None:
        from scripts.ai_image_pipeline_v3.runner import run_pipeline

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            successful_generation = {
                "selected": 3,
                "completed": 3,
                "skipped": 0,
                "failed": 0,
                "dry_run": 0,
                "waiting_reference": 0,
            }
            manual_review_qa = {
                "checked": 3,
                "approved": 0,
                "needs_manual_review": 3,
                "rejected": 0,
                "missing": 0,
            }
            with patch("scripts.ai_image_pipeline_v3.runner.generate_images", return_value=successful_generation):
                with patch("scripts.ai_image_pipeline_v3.runner.qa_images", return_value=manual_review_qa):
                    with self.assertRaises(RuntimeError):
                        run_pipeline(mode="smoke", root=root, dry_run=False, qa=True)

            gate = json.loads((root / "ai_image" / "reports" / "smoke_run_gate.json").read_text(encoding="utf-8"))
            self.assertFalse(gate["passed"])
            self.assertIn("qa_needs_manual_review", gate["reasons"])

    def test_distribution_audit_does_not_count_unbacked_visual_approved_complete_identities(self) -> None:
        from scripts.ai_image_pipeline_v3.distribution_audit import audit_distribution
        from scripts.ai_image_pipeline_v3.distribution_targets import write_default_distribution_targets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_default_distribution_targets(root=root, force=True)
            manifests = root / "ai_image" / "manifests"
            manifests.mkdir(parents=True, exist_ok=True)
            identity = {
                "profileId": "female_001",
                "gender": "female",
                "targetFaceType": "cat_like",
                "observedFaceType": "cat_like",
                "faceTypeConfidence": 0.82,
                "targetLooksLevelBand": "2.5-3.2",
                "observedLooksLevelBand": "2.5-3.2",
                "looksLevelConfidence": 0.9,
                "assetDecisions": {"face_card": "approved", "silhouette_card": "approved", "vibe_card": "approved"},
                "completeIdentityDecision": "approved",
                "countsTowardDistribution": True,
                "metadataMismatch": False,
            }
            assets = [
                {
                    "assetId": f"female_001__{shot}__v001",
                    "profileId": "female_001",
                    "gender": "female",
                    "shotType": shot,
                    "targetFaceType": "cat_like",
                    "observedFaceType": "cat_like",
                    "faceTypeConfidence": 0.82,
                    "targetLooksLevelBand": "2.5-3.2",
                    "observedLooksLevelBand": "2.5-3.2",
                    "looksLevelConfidence": 0.9,
                    "decision": "approved",
                    "metadataMismatch": False,
                }
                for shot in ("face_card", "silhouette_card", "vibe_card")
            ]
            (manifests / "identity_qa_manifest.jsonl").write_text(json.dumps(identity) + "\n", encoding="utf-8")
            (manifests / "asset_qa_manifest.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in assets),
                encoding="utf-8",
            )

            audit = audit_distribution(root=root)

            self.assertEqual(audit["approvedCompleteIdentityCount"], 0)
            self.assertEqual(audit["approvedImageCount"], 0)
            self.assertEqual(audit["femaleApprovedIdentityCount"], 0)
            self.assertEqual(audit["globalFaceTypeCounts"]["cat_like"], 0)
            self.assertEqual(audit["globalLooksLevelBandCounts"]["2.5-3.2"], 0)
            self.assertTrue((root / "ai_image" / "reports" / "distribution_report.csv").exists())
            self.assertTrue((root / "ai_image" / "reports" / "distribution_audit.json").exists())
            self.assertTrue((root / "ai_image" / "reports" / "latest_distribution_audit.json").exists())
            self.assertTrue(any(row["reason"] == "over_level_risk" for row in audit["forbiddenBuckets"]))
            self.assertTrue(all(row["looksLevelBand"] != "4.4-5.0" for row in audit["nextTargetBuckets"]))

    def test_distribution_audit_rejects_over_level_and_unclear_observed_buckets(self) -> None:
        from scripts.ai_image_pipeline_v3.distribution_audit import audit_distribution
        from scripts.ai_image_pipeline_v3.distribution_targets import write_default_distribution_targets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_default_distribution_targets(root=root, force=True)
            manifests = root / "ai_image" / "manifests"
            manifests.mkdir(parents=True, exist_ok=True)
            identities = [
                {
                    "profileId": "female_001",
                    "gender": "female",
                    "targetFaceType": "cat_like",
                    "observedFaceType": "cat_like",
                    "faceTypeConfidence": 0.8,
                    "targetLooksLevelBand": "3.9-4.3",
                    "observedLooksLevelBand": "4.4-5.0",
                    "looksLevelConfidence": 0.8,
                    "assetDecisions": {"face_card": "approved", "silhouette_card": "approved", "vibe_card": "approved"},
                    "completeIdentityDecision": "approved",
                    "countsTowardDistribution": True,
                    "metadataMismatch": False,
                },
                {
                    "profileId": "male_001",
                    "gender": "male",
                    "targetFaceType": "dog_like",
                    "observedFaceType": "unclear",
                    "targetLooksLevelBand": "2.5-3.2",
                    "assetDecisions": {"face_card": "approved", "silhouette_card": "approved", "vibe_card": "approved"},
                    "completeIdentityDecision": "approved",
                    "countsTowardDistribution": True,
                    "metadataMismatch": False,
                },
            ]
            assets = []
            for identity in identities:
                for shot in ("face_card", "silhouette_card", "vibe_card"):
                    assets.append(
                        {
                            "assetId": f"{identity['profileId']}__{shot}__v001",
                            "profileId": identity["profileId"],
                            "gender": identity["gender"],
                            "shotType": shot,
                            "decision": "approved",
                            "metadataMismatch": False,
                        }
                    )
            (manifests / "identity_qa_manifest.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in identities),
                encoding="utf-8",
            )
            (manifests / "asset_qa_manifest.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in assets),
                encoding="utf-8",
            )

            audit = audit_distribution(root=root)

            self.assertEqual(audit["approvedCompleteIdentityCount"], 0)
            self.assertIn("approved_4.4-5.0_identity", audit["failConditions"])
            self.assertEqual(len(audit["overLevelApprovedIdentities"]), 1)
            self.assertTrue(any(row["profileId"] == "male_001" for row in audit["needsReviewIdentities"]))

    def test_distribution_audit_flags_visual_distribution_disagreement(self) -> None:
        from scripts.ai_image_pipeline_v3.distribution_audit import audit_distribution
        from scripts.ai_image_pipeline_v3.distribution_targets import write_default_distribution_targets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_default_distribution_targets(root=root, force=True)
            manifests = root / "ai_image" / "manifests"
            reports = root / "ai_image" / "reports" / "visual_verdict"
            manifests.mkdir(parents=True, exist_ok=True)
            reports.mkdir(parents=True, exist_ok=True)
            identity = {
                "profileId": "female_001",
                "gender": "female",
                "targetFaceType": "cat_like",
                "targetLooksLevelBand": "2.5-3.2",
                "assetDecisions": {"face_card": "approved", "silhouette_card": "approved", "vibe_card": "approved"},
                "completeIdentityDecision": "approved",
                "countsTowardDistribution": True,
                "metadataMismatch": False,
            }
            assets = [
                {
                    "assetId": f"female_001__{shot}__v001",
                    "profileId": "female_001",
                    "gender": "female",
                    "shotType": shot,
                    "decision": "approved",
                    "metadataMismatch": False,
                }
                for shot in ("face_card", "silhouette_card", "vibe_card")
            ]
            (manifests / "identity_qa_manifest.jsonl").write_text(json.dumps(identity) + "\n", encoding="utf-8")
            (manifests / "asset_qa_manifest.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in assets),
                encoding="utf-8",
            )
            (reports / "distribution_audit.json").write_text(
                json.dumps({"qaType": "seolleyeon_visual_verdict_distribution_v3", "approvedCompleteIdentityCount": 2}),
                encoding="utf-8",
            )

            audit = audit_distribution(root=root)

            self.assertIn("python_visual_distribution_audit_disagree", audit["failConditions"])
            self.assertTrue((manifests / "manual_review_required.flag").exists())

    def test_distribution_audit_clears_stale_visual_distribution_manual_flag_only(self) -> None:
        from scripts.ai_image_pipeline_v3.distribution_audit import audit_distribution
        from scripts.ai_image_pipeline_v3.distribution_targets import write_default_distribution_targets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_default_distribution_targets(root=root, force=True)
            flag = root / "ai_image" / "manifests" / "manual_review_required.flag"
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text(json.dumps({"failConditions": ["python_visual_distribution_audit_disagree"]}), encoding="utf-8")

            audit = audit_distribution(root=root)

            self.assertNotIn("python_visual_distribution_audit_disagree", audit["failConditions"])
            self.assertFalse(flag.exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_default_distribution_targets(root=root, force=True)
            flag = root / "ai_image" / "manifests" / "manual_review_required.flag"
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text(json.dumps({"reason": "human_review_required"}), encoding="utf-8")

            audit_distribution(root=root)

            self.assertTrue(flag.exists())

    def test_completion_exact_fixture_passes_only_without_manual_flag_or_pending(self) -> None:
        from scripts.ai_image_pipeline_v3.completion import completion_check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_exact_visual_fixture(root)

            result = completion_check(root=root)

            self.assertTrue(result["passed"])
            self.assertEqual(result["failureReasons"], [])

    def test_completion_exact_fixture_fails_with_manual_review_flag(self) -> None:
        from scripts.ai_image_pipeline_v3.completion import completion_check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_exact_visual_fixture(root)
            flag = root / "ai_image" / "manifests" / "manual_review_required.flag"
            flag.write_text("manual", encoding="utf-8")

            result = completion_check(root=root)

            self.assertFalse(result["passed"])
            self.assertIn("manual_review_required", result["failureReasons"])

    def test_completion_exact_fixture_fails_with_unresolved_pending(self) -> None:
        from scripts.ai_image_pipeline_v3.completion import completion_check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_exact_visual_fixture(root)
            pending = root / "ai_image" / "manifests" / "pending-imagegen.json"
            pending.write_text(json.dumps({"status": "pending_imagegen", "assetId": "female_001__face_card__v001"}), encoding="utf-8")

            result = completion_check(root=root)

            self.assertFalse(result["passed"])
            self.assertIn("unresolved_pending_imagegen", result["failureReasons"])

    def test_completion_raw_720_files_without_visual_qa_fails(self) -> None:
        from scripts.ai_image_pipeline_v3.completion import completion_check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "ai_image" / "raw"
            raw.mkdir(parents=True, exist_ok=True)
            for index in range(720):
                (raw / f"raw_{index:03d}.png").write_bytes(b"raw")

            result = completion_check(root=root)

            self.assertFalse(result["passed"])
            self.assertIn("missing_visual_verdict", result["failureReasons"])

    def test_completion_invalid_counted_identity_mutations_fail(self) -> None:
        from scripts.ai_image_pipeline_v3.completion import completion_check

        for mutation, expected_reason in (
            ("metadataMismatch", "invalid_counted_identity"),
            ("needs_review", "invalid_counted_identity"),
            ("over_level", "over_level_approved"),
            ("missing_vibe", "invalid_counted_identity"),
        ):
            with self.subTest(mutation=mutation):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    self._write_exact_visual_fixture(root, mutate=mutation)

                    result = completion_check(root=root)

                    self.assertFalse(result["passed"])
                    self.assertIn(expected_reason, result["failureReasons"])

    def test_visual_verdict_asset_nested_schema_maps_observed_and_hard_rejects_over_level(self) -> None:
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.manifest import enrich_asset, write_generation_outputs
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_asset_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = pipeline_paths(root)
            rows = [
                enrich_asset({"profileId": "female_001", "assetId": "female_001__face_card__v001", "gender": "female", "shotType": "face_card", "targetFaceType": "cat_like", "targetLooksLevelBand": "2.5-3.2", "prompt": "p"}, paths),
                enrich_asset({"profileId": "female_001", "assetId": "female_001__vibe_card__v001", "gender": "female", "shotType": "vibe_card", "targetFaceType": "cat_like", "targetLooksLevelBand": "2.5-3.2", "prompt": "p"}, paths),
            ]
            write_generation_outputs(paths, rows)
            visual = {
                "qaType": "seolleyeon_visual_verdict_asset_v3",
                "sheetId": "s1",
                "assets": [
                    {
                        "assetId": rows[0]["assetId"],
                        "profileId": "female_001",
                        "gender": "female",
                        "shotType": "face_card",
                        "targetFaceType": "cat_like",
                        "observedFaceType": "cat_like",
                        "faceTypeConfidence": 0.9,
                        "targetLooksLevelBand": "2.5-3.2",
                        "observedLooksLevelBand": "2.5-3.2",
                        "looksLevelConfidence": 0.9,
                        "adultVisual": True,
                        "photoRealism": 5,
                        "campusRealism": 5,
                        "brandFit": 5,
                        "shotTypeReadable": True,
                        "metadataMismatch": False,
                        "mismatchFields": [],
                        "decision": "approved",
                    },
                    {
                        "assetId": rows[1]["assetId"],
                        "profileId": "female_001",
                        "gender": "female",
                        "shotType": "vibe_card",
                        "targetFaceType": "cat_like",
                        "observedFaceType": "cat_like",
                        "faceTypeConfidence": 0.9,
                        "targetLooksLevelBand": "2.5-3.2",
                        "observedLooksLevelBand": "4.4-5.0",
                        "looksLevelConfidence": 0.9,
                        "adultVisual": True,
                        "photoRealism": 5,
                        "campusRealism": 5,
                        "brandFit": 5,
                        "shotTypeReadable": True,
                        "metadataMismatch": False,
                        "mismatchFields": [],
                        "decision": "approved",
                    },
                ],
            }
            visual_path = root / "asset.json"
            visual_path.write_text(json.dumps(visual), encoding="utf-8")

            counts = apply_asset_qa(root=root, input_path=str(visual_path))
            rows_out = [json.loads(line) for line in (paths.manifests / "asset_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()]

            self.assertEqual(counts["checked"], 2)
            self.assertEqual(rows_out[0]["observedFaceType"], "cat_like")
            self.assertEqual(rows_out[1]["decision"], "rejected")

    def test_visual_verdict_identity_nested_schema_same_identity_false_does_not_count(self) -> None:
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.manifest import enrich_asset, write_generation_outputs
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_identity_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = pipeline_paths(root)
            manifest_rows = []
            for profile in ("female_001", "female_002"):
                for shot in ("face_card", "silhouette_card", "vibe_card"):
                    manifest_rows.append(enrich_asset({"profileId": profile, "assetId": f"{profile}__{shot}__v001", "gender": "female", "shotType": shot, "targetFaceType": "cat_like", "targetLooksLevelBand": "2.5-3.2", "prompt": "p"}, paths))
            write_generation_outputs(paths, manifest_rows)
            identities = []
            for profile, same_identity in (("female_001", True), ("female_002", False)):
                identities.append(
                    {
                        "profileId": profile,
                        "gender": "female",
                        "targetFaceType": "cat_like",
                        "observedFaceType": "cat_like",
                        "targetLooksLevelBand": "2.5-3.2",
                        "observedLooksLevelBand": "2.5-3.2",
                        "assetIds": {shot: f"{profile}__{shot}__v001" for shot in ("face_card", "silhouette_card", "vibe_card")},
                        "assetDecisions": {"face_card": "approved", "silhouette_card": "approved", "vibe_card": "approved"},
                        "faceToSilhouetteConsistency": 4.2,
                        "faceToVibeConsistency": 4.2,
                        "sameIdentity": same_identity,
                        "completeIdentityDecision": "approved",
                        "countsTowardDistribution": True,
                    }
                )
            visual_path = root / "identity.json"
            visual_path.write_text(json.dumps({"qaType": "seolleyeon_visual_verdict_identity_v3", "identities": identities}), encoding="utf-8")

            counts = apply_identity_qa(root=root, input_path=str(visual_path))
            rows_out = [json.loads(line) for line in (paths.manifests / "identity_qa_manifest.jsonl").read_text(encoding="utf-8").splitlines()]

            self.assertEqual(counts["checked"], 2)
            self.assertFalse(next(row for row in rows_out if row["profileId"] == "female_002")["countsTowardDistribution"])

    def test_visual_verdict_invalid_and_empty_inputs_are_rejected(self) -> None:
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

    def test_visual_distribution_disagreement_apply_creates_manual_review_flag(self) -> None:
        from scripts.ai_image_pipeline_v3.distribution_targets import write_default_distribution_targets
        from scripts.ai_image_pipeline_v3.visual_verdict import apply_distribution_audit

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_default_distribution_targets(root=root, force=True)
            visual_path = root / "dist.json"
            visual_path.write_text(json.dumps({"qaType": "seolleyeon_visual_verdict_distribution_v3", "approvedCompleteIdentityCount": 99}), encoding="utf-8")

            result = apply_distribution_audit(root=root, input_path=str(visual_path))

            self.assertTrue(result["needsManualReview"])
            self.assertTrue((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())

    def test_file_qa_detects_aspect_path_duplicates_and_missing_required_shot(self) -> None:
        from PIL import Image

        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.manifest import enrich_asset, write_generation_outputs
        from scripts.ai_image_pipeline_v3.qa import qa_images

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = pipeline_paths(root)
            rows = []
            for shot in ("face_card", "silhouette_card"):
                row = enrich_asset({"profileId": "female_001", "assetId": f"female_001__{shot}__v001", "gender": "female", "shotType": shot, "targetFaceType": "cat_like", "targetLooksLevelBand": "2.5-3.2", "prompt": "p"}, paths)
                Path(row["localPath"]).parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (512, 512), (10, 20, 30)).save(row["localPath"])
                rows.append(row)
            rows[0]["finalPath"] = str(root / "ai_image" / "male" / "001" / "face_card.png")
            duplicate = dict(rows[1])
            duplicate["assetId"] = rows[1]["assetId"]
            duplicate["finalPath"] = rows[0]["finalPath"]
            rows.append(duplicate)
            write_generation_outputs(paths, rows)

            counts = qa_images(root=root, limit=3)
            with (paths.reports / "file_qa_report.csv").open("r", encoding="utf-8", newline="") as report_file:
                report = list(csv.DictReader(report_file))
            reason_text = " ".join(row["reasonCodes"] for row in report)


            self.assertEqual(counts["rejected"], 3)
            self.assertIn("bad_aspect_ratio", reason_text)
            self.assertIn("path_gender_mismatch", reason_text)
            self.assertIn("duplicate_assetId", reason_text)
            self.assertIn("duplicate_final_path", reason_text)
            self.assertIn("duplicate_image_hash", reason_text)
            self.assertIn("missing_required_shot:vibe_card", reason_text)

    def test_valid_file_qa_does_not_create_distribution_approval(self) -> None:
        from PIL import Image

        from scripts.ai_image_pipeline_v3.completion import completion_check
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.manifest import enrich_asset, write_generation_outputs
        from scripts.ai_image_pipeline_v3.qa import qa_images

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = pipeline_paths(root)
            rows = []
            for index, shot in enumerate(("face_card", "silhouette_card", "vibe_card"), start=1):
                row = enrich_asset({"profileId": "female_001", "assetId": f"female_001__{shot}__v001", "gender": "female", "shotType": shot, "targetFaceType": "cat_like", "targetLooksLevelBand": "2.5-3.2", "prompt": "p"}, paths)
                Path(row["localPath"]).parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (512, 768), (10 * index, 20 * index, 30 * index)).save(row["localPath"])
                rows.append(row)
            write_generation_outputs(paths, rows)

            qa_counts = qa_images(root=root, limit=3)
            completion = completion_check(root=root)

            self.assertEqual(qa_counts["file_qa_passed"], 3)
            self.assertEqual(qa_counts["visual_qa_pending"], 3)
            self.assertFalse((root / "ai_image" / "approved" / "female" / "001" / "face_card.png").exists())
            self.assertFalse((root / "ai_image" / "approved" / "female_001__face_card__v001.png").exists())

            self.assertIn("missing_visual_verdict", completion["failureReasons"])

    def test_cli_dispatcher_and_supervisor_helpers(self) -> None:
        from scripts.ai_image_pipeline_v3.cli import build_parser
        from scripts.ai_image_pipeline_v3.supervisor import (
            log_mode_transition,
            parse_config,
            should_promote_to_chunk,
            supervisor_status,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            command_choices = next(action.choices for action in build_parser()._actions if action.dest == "command")
            self.assertIn("pending-status", command_choices)
            self.assertIn("resolve-pending", command_choices)
            self.assertIn("clear-cancelled-pending", command_choices)
            config = parse_config({"MODE": "auto"})
            self.assertEqual(config.mode, "auto")
            self.assertFalse(config.allow_promote_back_to_chunk)
            self.assertFalse(
                should_promote_to_chunk(
                    config=config,
                    consecutive_identity_success_ticks=999,
                    remaining_deficit_identities=999,
                )
            )
            enabled = parse_config({"MODE": "identity", "ALLOW_PROMOTE_BACK_TO_CHUNK": "1", "PROMOTE_AFTER_IDENTITY_SUCCESS_TICKS": "2", "MIN_DEFICIT_IDENTITIES_FOR_CHUNK": "3"})
            self.assertTrue(
                should_promote_to_chunk(
                    config=enabled,
                    consecutive_identity_success_ticks=2,
                    remaining_deficit_identities=3,
                )
            )
            before = {"approvedIdentityCount": 1, "approvedAssetCount": 3}
            after = {"approvedIdentityCount": 1, "approvedAssetCount": 3}
            log_mode_transition(root=root, from_mode="chunk", to_mode="identity", reason="no_progress", before=before, after=after)
            log_mode_transition(root=root, from_mode="identity", to_mode="asset", reason="no_progress", before=before, after=after)
            log_path = root / "ai_image" / "reports" / "autopilot_logs" / "mode_transitions.log"
            self.assertTrue(log_path.exists())
            self.assertIn("chunk", log_path.read_text(encoding="utf-8"))
            self.assertFalse(supervisor_status(root=root, mode="asset")["completionPassed"])

    def test_completion_allows_only_resolved_or_cleared_pending_state(self) -> None:
        from scripts.ai_image_pipeline_v3.completion import completion_check

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_exact_visual_fixture(root)
            pending = root / "ai_image" / "manifests" / "pending-imagegen.json"

            pending.write_text(json.dumps({"status": "resolved", "assetId": "female_001__face_card__v001"}), encoding="utf-8")
            self.assertTrue(completion_check(root=root)["passed"])

            pending.write_text(json.dumps({"status": "recovered", "assetId": "female_001__face_card__v001"}), encoding="utf-8")
            recovered_result = completion_check(root=root)
            self.assertFalse(recovered_result["passed"])
            self.assertIn("unresolved_pending_imagegen", recovered_result["failureReasons"])

            pending.write_text(json.dumps({"resolved": True, "status": "recovered", "assetId": "female_001__face_card__v001"}), encoding="utf-8")
            self.assertTrue(completion_check(root=root)["passed"])

    def test_recover_pending_marks_pending_resolved_for_completion_gate(self) -> None:
        from PIL import Image

        from scripts.ai_image_pipeline_v3.codex_imagegen import (
            build_pending_payload,
            pending_path,
            recover_pending_imagegen,
            write_pending,
        )
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.manifest import enrich_asset, manifest_path, write_generation_outputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = pipeline_paths(root)
            row = enrich_asset(
                {
                    "profileId": "female_001",
                    "assetId": "female_001__face_card__v001",
                    "gender": "female",
                    "shotType": "face_card",
                    "targetFaceType": "cat_like",
                    "targetLooksLevelBand": "2.5-3.2",
                    "prompt": "prompt",
                },
                paths,
            )
            write_generation_outputs(paths, [row])
            source = root / "generated" / "codex.png"
            source.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (512, 768), (20, 30, 40)).save(source)

            pending_file = pending_path(root)
            payload = build_pending_payload(
                paths_root=root,
                row=row,
                attempt=1,
                queue_file=paths.manifests / "imagegen_queue.jsonl",
                manifest_file=manifest_path(paths),
                out_pending=pending_file,
                generated_root=source.parent,
            )
            write_pending(pending_file, payload)

            recover_pending_imagegen(root=root, pending=pending_file, source=source, run_qa=False)

            resolved = json.loads(pending_file.read_text(encoding="utf-8"))
            completed = [
                json.loads(line)
                for line in (paths.manifests / "completed_pending_imagegen.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(resolved["status"], "resolved")
            self.assertTrue(resolved["resolved"])
            self.assertEqual(completed[0]["status"], "resolved")
            self.assertEqual(completed[0]["recoveryStatus"], "recovered")

    def test_distribution_chunk_blocks_non_resolved_pending_state(self) -> None:
        from scripts.ai_image_pipeline_v3.codex_imagegen import pending_path
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.distribution_chunk import next_distribution_chunk
        from scripts.ai_image_pipeline_v3.distribution_targets import write_default_distribution_targets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_default_distribution_targets(root=root, force=True)
            paths = pipeline_paths(root)
            paths.manifests.mkdir(parents=True, exist_ok=True)
            pending_path(root).write_text(
                json.dumps({"status": "cancelled_before_imagegen", "assetId": "female_002__face_card__v001"}),
                encoding="utf-8",
            )

            result = next_distribution_chunk(root=root, refresh_audit=False)

            self.assertEqual(result["status"], "unresolved_pending_imagegen")
            self.assertEqual(result["reason"], "female_002__face_card__v001")

    def test_pending_admin_reports_and_clears_cancelled_checkpoint(self) -> None:
        from scripts.ai_image_pipeline_v3.codex_imagegen import pending_path
        from scripts.ai_image_pipeline_v3.pending_admin import clear_cancelled_pending, pending_resolution_path, pending_status_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "ai_image" / "raw" / "female_002__face_card__v001__attempt01.png"
            final = root / "ai_image" / "female" / "002" / "face_card.png"
            raw.parent.mkdir(parents=True, exist_ok=True)
            final.parent.mkdir(parents=True, exist_ok=True)
            raw.write_bytes(b"not-a-real-image")
            final.write_bytes(b"not-a-real-image")
            pending_file = pending_path(root)
            pending_file.parent.mkdir(parents=True, exist_ok=True)
            pending_file.write_text(
                json.dumps(
                    {
                        "status": "cancelled_before_imagegen",
                        "assetId": "female_002__face_card__v001",
                        "profileId": "female_002",
                        "shotType": "face_card",
                        "attempt": 1,
                        "expectedRawPath": str(raw),
                        "expectedFinalPath": str(final),
                    }
                ),
                encoding="utf-8",
            )

            before = pending_status_report(root=root)
            self.assertTrue(before["unresolved"])
            self.assertFalse(before["requiresRecovery"])
            self.assertTrue(before["expectedRawPath"]["exists"])
            self.assertTrue(before["expectedFinalPath"]["exists"])

            after = clear_cancelled_pending(root=root, reason="test_clear")
            self.assertEqual(after["status"], "cleared")
            self.assertTrue(after["resolved"])
            resolved_payload = json.loads(pending_file.read_text(encoding="utf-8"))
            self.assertEqual(resolved_payload["status"], "cleared")
            self.assertTrue(resolved_payload["resolved"])

            rows = [json.loads(line) for line in pending_resolution_path(root).read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["beforeStatus"], "cancelled_before_imagegen")
            self.assertEqual(rows[0]["afterStatus"], "cleared")
            self.assertEqual(rows[0]["action"], "clear_cancelled")

    def test_pending_admin_refuses_active_pending_manual_resolution(self) -> None:
        from scripts.ai_image_pipeline_v3.codex_imagegen import pending_path
        from scripts.ai_image_pipeline_v3.pending_admin import clear_cancelled_pending, resolve_pending

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pending_file = pending_path(root)
            pending_file.parent.mkdir(parents=True, exist_ok=True)
            pending_file.write_text(
                json.dumps({"status": "pending_imagegen", "assetId": "female_002__face_card__v001"}),
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError):
                clear_cancelled_pending(root=root)
            with self.assertRaises(RuntimeError):
                resolve_pending(root=root)

    def test_latest_generated_image_rejects_ambiguous_recovery_candidates(self) -> None:
        from PIL import Image

        from scripts.ai_image_pipeline_v3.codex_imagegen import latest_generated_image

        with tempfile.TemporaryDirectory() as tmp:
            generated = Path(tmp) / "generated"
            generated.mkdir(parents=True, exist_ok=True)
            for name in ("one.png", "two.png"):
                Image.new("RGB", (512, 768), (20, 30, 40)).save(generated / name)

            with self.assertRaises(RuntimeError):
                latest_generated_image(generated, created_at="1970-01-01T00:00:00+00:00")

    def test_latest_generated_image_refuses_stale_candidate_before_pending_timestamp(self) -> None:
        from PIL import Image

        from scripts.ai_image_pipeline_v3.codex_imagegen import latest_generated_image

        with tempfile.TemporaryDirectory() as tmp:
            generated = Path(tmp) / "generated"
            generated.mkdir(parents=True, exist_ok=True)
            source = generated / "old.png"
            Image.new("RGB", (512, 768), (20, 30, 40)).save(source)

            with self.assertRaises(FileNotFoundError):
                latest_generated_image(generated, created_at="2999-01-01T00:00:00+00:00")

    def test_recover_pending_rejects_reused_generated_source_or_duplicate_final_hash(self) -> None:
        from PIL import Image

        from scripts.ai_image_pipeline_v3.codex_imagegen import (
            build_pending_payload,
            completed_pending_path,
            pending_path,
            recover_pending_imagegen,
            write_pending,
        )
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.manifest import enrich_asset, manifest_path, write_generation_outputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = pipeline_paths(root)
            source = root / "generated" / "codex.png"
            source.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (512, 768), (20, 30, 40)).save(source)

            first = enrich_asset(
                {
                    "profileId": "female_001",
                    "assetId": "female_001__face_card__v001",
                    "gender": "female",
                    "shotType": "face_card",
                    "prompt": "first",
                    "status": "recovered_pending_qa",
                },
                paths,
            )
            first_final = Path(first["finalPath"])
            first_raw = Path(first["localPath"])
            first_final.parent.mkdir(parents=True, exist_ok=True)
            first_raw.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (512, 768), (20, 30, 40)).save(first_final)
            Image.new("RGB", (512, 768), (20, 30, 40)).save(first_raw)

            second = enrich_asset(
                {
                    "profileId": "female_002",
                    "assetId": "female_002__face_card__v001",
                    "gender": "female",
                    "shotType": "face_card",
                    "prompt": "second",
                    "status": "pending_imagegen",
                },
                paths,
            )
            write_generation_outputs(paths, [first, second])
            write_jsonl(
                completed_pending_path(root),
                [
                    {
                        "assetId": first["assetId"],
                        "status": "resolved",
                        "sourcePath": str(source),
                    }
                ],
            )

            pending_file = pending_path(root)
            payload = build_pending_payload(
                paths_root=root,
                row=second,
                attempt=1,
                queue_file=paths.manifests / "imagegen_queue.jsonl",
                manifest_file=manifest_path(paths),
                out_pending=pending_file,
                generated_root=source.parent,
            )
            write_pending(pending_file, payload)

            with self.assertRaises(RuntimeError):
                recover_pending_imagegen(root=root, pending=pending_file, source=source, run_qa=False)

    def test_ralph_and_supervisor_prompts_require_visual_verdict_strict_stop(self) -> None:
        ralph_prompt = Path("ai_image/prompts/RALPH_DISTRIBUTION_AWARE_CHUNK_PROMPT.md").read_text(encoding="utf-8")
        supervisor_shell = Path("scripts/codex_imagegen_supervisor_v3.sh").read_text(encoding="utf-8")
        autopilot_shell = Path("scripts/codex_imagegen_chunk_autopilot_v3.sh").read_text(encoding="utf-8")

        for text in (ralph_prompt, supervisor_shell):
            self.assertIn("visual-verdict is unavailable", text)
            self.assertIn("manual_review_required.flag and stop", text)
        for text in (supervisor_shell, autopilot_shell):
            self.assertIn("unresolved_pending:", text)

    def test_visual_verdict_prompts_keep_canonical_brand_and_reject_language(self) -> None:
        canonical_rejects = [
            "appears under 20",
            "childlike or teenager-like",
            "school uniform",
            "idol trainee styling",
            "celebrity lookalike",
            "influencer photoshoot",
            "glamour studio lighting",
            "nightclub / party / neon / bar / luxury hotel mood",
            "sexualized styling",
            "revealing outfit / swimsuit / lingerie",
            "heavy beauty filter",
            "plastic skin",
            "distorted face",
            "distorted hands / fingers / arms / legs / body",
            "unrealistic body proportions",
            "visible school logo",
            "readable university name",
            "brand logo",
            "watermark",
            "generated text inside image",
            "image feels like a dating-app face-rating game asset",
        ]
        visual_prompts = [
            Path("ai_image/prompts/VISUAL_VERDICT_ASSET_QA_PROMPT.md"),
            Path("ai_image/prompts/VISUAL_VERDICT_IDENTITY_QA_PROMPT.md"),
            Path("ai_image/prompts/VISUAL_VERDICT_DISTRIBUTION_AUDIT_PROMPT.md"),
            Path("ai_image/prompts/VISUAL_VERDICT_LOOKSLEVEL_CALIBRATION_PROMPT.md"),
        ]
        for path in visual_prompts:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Return strict JSON only", text)
            self.assertIn("Seolleyeon is a university-only, trust-based relationship platform", text)
            self.assertIn("It is not a lightweight dating app", text)
            self.assertIn("cold-start preference learning", text)
            for phrase in canonical_rejects:
                self.assertIn(phrase, text, f"{path} missing {phrase}")
            self.assertNotIn("AI?먭쾶", text)
        feature_text = Path("AI_IMAGE_DISTRIBUTION_CONTROL_README.md").read_text(encoding="utf-8")
        self.assertIn("AI에게 내 취향 알려주기", feature_text)


if __name__ == "__main__":
    unittest.main()
