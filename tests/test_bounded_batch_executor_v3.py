import json
import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class BoundedBatchExecutorV3Tests(unittest.TestCase):
    def _write_audit(self, root: Path, *, face_deficit: int = 120, looks_deficit: int = 120) -> None:
        reports = root / "ai_image" / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        bucket_checks = []
        for scope in ("global", "female"):
            bucket_checks.append({"scope": scope, "dimension": "faceType", "bucket": "deer_like", "deficit": face_deficit})
            bucket_checks.append({"scope": scope, "dimension": "looksLevelBand", "bucket": "2.5-3.2", "deficit": looks_deficit})
            bucket_checks.append({"scope": scope, "dimension": "faceType", "bucket": "dog_like", "deficit": 0})
            bucket_checks.append({"scope": scope, "dimension": "looksLevelBand", "bucket": "4.4-5.0", "deficit": 0})
        audit = {
            "approvedCompleteIdentityCount": 0,
            "approvedImageCount": 0,
            "femaleApprovedIdentityCount": 0,
            "maleApprovedIdentityCount": 0,
            "countChecks": {
                "femaleApprovedIdentities": {"deficit": 120},
                "maleApprovedIdentities": {"deficit": 120},
            },
            "bucketChecks": bucket_checks,
            "globalFaceTypeDeficits": {"deer_like": face_deficit, "dog_like": 0},
            "genderFaceTypeDeficits": {"female": {"deer_like": face_deficit, "dog_like": 0}, "male": {"deer_like": 0, "dog_like": 0}},
            "globalLooksLevelBandDeficits": {"2.5-3.2": looks_deficit, "4.4-5.0": 0},
            "genderLooksLevelBandDeficits": {"female": {"2.5-3.2": looks_deficit, "4.4-5.0": 0}, "male": {"2.5-3.2": 0, "4.4-5.0": 0}},
            "globalFaceTypeSurpluses": {},
            "genderFaceTypeSurpluses": {"female": {}, "male": {}},
            "globalLooksLevelBandSurpluses": {},
            "genderLooksLevelBandSurpluses": {"female": {}, "male": {}},
            "passed": False,
            "finalDecision": "needs_more_generation",
        }
        (reports / "latest_distribution_audit.json").write_text(json.dumps(audit), encoding="utf-8")

    def _write_manifest(
        self,
        root: Path,
        count: int,
        *,
        face_type: str = "deer_like",
        looks: str = "2.5-3.2",
        duplicate_final: bool = False,
        metadata_only_targets: bool = False,
    ) -> None:
        from scripts.ai_image_pipeline_v3.config import prompt_hash
        from scripts.ai_image_pipeline_v3.manifest import write_generation_outputs
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, write_jsonl
        from scripts.ai_image_pipeline_v3.codex_imagegen import write_imagegen_queue
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        paths = pipeline_paths(root)
        prompt_module = load_prompt_module()
        prompt_builder_version = str(getattr(prompt_module, "PROMPT_BUILDER_VERSION", ""))
        prompt_targeting_version = str(getattr(prompt_module, "PROMPT_TARGETING_VERSION", ""))
        rows = []
        for number in range(1, count + 1):
            profile_id = f"female_{number:03d}"
            for shot in ("face_card", "silhouette_card", "vibe_card"):
                final = root / "ai_image" / "female" / f"{number:03d}" / f"{shot}.png"
                if duplicate_final and shot == "silhouette_card":
                    final = root / "ai_image" / "female" / f"{number:03d}" / "face_card.png"
                prompt = f"prompt for {profile_id} {shot}"
                row = {
                        "assetId": f"{profile_id}__{shot}__v001",
                        "profileId": profile_id,
                        "gender": "female",
                        "numericId": f"{number:03d}",
                        "shotType": shot,
                        "prompt": prompt,
                        "promptHash": prompt_hash(prompt),
                        "promptBuilderVersion": prompt_builder_version,
                        "promptTargetingVersion": prompt_targeting_version,
                        "status": "prepared",
                        "activeForTarget": True,
                        "isReserve": False,
                        "attempt": 0,
                        "attemptCount": 0,
                        "finalPath": str(final),
                        "localPath": str(root / "ai_image" / "raw" / f"{profile_id}__{shot}__v001__attempt01.png"),
                    }
                if metadata_only_targets:
                    level = {"1.5-2.4": 2.0, "2.5-3.2": 3.0, "3.3-3.8": 3.6, "3.9-4.3": 4.1, "4.4-5.0": 4.6}[looks]
                    row["metadata"] = {"face": {"faceType": face_type, "looksLevel": level}}
                else:
                    row["targetFaceType"] = face_type
                    row["targetLooksLevelBand"] = looks
                rows.append(row)
        write_generation_outputs(paths, rows)
        write_imagegen_queue(root, rows)
        write_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl", rows)

    def _update_generation_row(self, root: Path, asset_id: str, **updates) -> None:
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.manifest import load_generation_manifest, write_generation_outputs

        paths = pipeline_paths(root)
        rows = []
        for row in load_generation_manifest(paths):
            out = dict(row)
            if out.get("assetId") == asset_id:
                out.update(updates)
            rows.append(out)
        write_generation_outputs(paths, rows)

    def _config(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import BoundedExecutorConfig

        return BoundedExecutorConfig(
            agent_cmd="omx",
            agent_mode="exec",
            imagegen_surface="child",
            timeout_sec=30,
            max_asset_attempts=3,
            allow_reserve_activation=False,
            max_identities=24,
            max_assets=72,
            reference_mode="path",
            active_visual_qa=True,
            image_arg_mode="image",
        )

    def _fake_recover(self, root: Path):
        def recover(*, pending, **kwargs):
            from scripts.ai_image_pipeline_v3.codex_imagegen import read_pending, write_pending
            from scripts.ai_image_pipeline_v3.config import now_utc
            from scripts.ai_image_pipeline_v3.manifest import load_generation_manifest, write_generation_outputs
            from scripts.ai_image_pipeline_v3.config import pipeline_paths

            payload = read_pending(Path(pending))
            final = Path(payload["expectedFinalPath"])
            final.parent.mkdir(parents=True, exist_ok=True)
            from PIL import Image

            digest = hashlib.sha256(str(payload["assetId"]).encode("utf-8")).digest()
            Image.new("RGB", (512, 768), tuple(40 + digest[index] % 160 for index in range(3))).save(final)
            paths = pipeline_paths(root)
            rows = []
            for row in load_generation_manifest(paths):
                out = dict(row)
                if out["assetId"] == payload["assetId"]:
                    out.update({"status": "recovered_pending_qa", "finalPath": str(final), "localPath": str(final), "attemptCount": payload["attempt"]})
                rows.append(out)
            write_generation_outputs(paths, rows)
            payload.update({"status": "resolved", "resolved": True, "updatedAt": now_utc()})
            write_pending(Path(pending), payload)
            return type("RecoverResult", (), {"final_path": final})()

        return recover

    def _fake_file_qa(self, root: Path):
        def file_qa(*, shot_type, **kwargs):
            from scripts.ai_image_pipeline_v3.manifest import load_generation_manifest, write_generation_outputs
            from scripts.ai_image_pipeline_v3.config import pipeline_paths

            paths = pipeline_paths(root)
            rows = []
            for row in load_generation_manifest(paths):
                out = dict(row)
                if out["shotType"] == shot_type and out["status"] == "recovered_pending_qa":
                    out["status"] = "file_needs_review"
                rows.append(out)
            write_generation_outputs(paths, rows)
            return {"checked": 1, "approved": 0, "needs_manual_review": 1, "rejected": 0, "missing": 0}

        return file_qa

    def test_single_asset_file_qa_rejects_duplicate_image_hash(self):
        from PIL import Image

        from scripts.ai_image_pipeline_v3.bounded_batch_executor import file_qa_single_asset
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.manifest import enrich_asset, load_generation_manifest, write_generation_outputs

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = pipeline_paths(root)
            rows = []
            for number in (1, 2):
                row = enrich_asset(
                    {
                        "profileId": f"female_{number:03d}",
                        "assetId": f"female_{number:03d}__face_card__v001",
                        "gender": "female",
                        "shotType": "face_card",
                        "prompt": "p",
                    },
                    paths,
                )
                final = Path(row["finalPath"])
                final.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (512, 768), (10, 20, 30)).save(final)
                row["localPath"] = str(final)
                rows.append(row)
            write_generation_outputs(paths, rows)

            counts = file_qa_single_asset(root=root, asset_id="female_002__face_card__v001", shot_type="face_card")
            updated = {row["assetId"]: row for row in load_generation_manifest(paths)}

            self.assertEqual(counts["rejected"], 1)
            self.assertEqual(updated["female_002__face_card__v001"]["status"], "file_rejected")
            self.assertIn("duplicate_image_hash", updated["female_002__face_card__v001"]["error"])

    def test_config_prefers_codex_bin_and_shorter_default_timeout(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import BoundedExecutorConfig

        config = BoundedExecutorConfig.from_env({"CODEX_BIN": "codex.cmd"})

        self.assertEqual(config.agent_cmd, "codex.cmd")
        self.assertEqual(config.timeout_sec, 300)

    def test_config_caps_explicit_timeout_to_safe_upper_bound(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import BoundedExecutorConfig

        config = BoundedExecutorConfig.from_env({"CODEX_BIN": "codex.cmd", "BOUNDED_EXECUTOR_TIMEOUT_SEC": "1800"})

        self.assertEqual(config.timeout_sec, 300)

    def test_config_explicit_bounded_agent_overrides_codex_bin(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import BoundedExecutorConfig

        config = BoundedExecutorConfig.from_env({"CODEX_BIN": "codex.cmd", "BOUNDED_EXECUTOR_AGENT_CMD": "omx", "BOUNDED_EXECUTOR_TIMEOUT_SEC": "42"})

        self.assertEqual(config.agent_cmd, "omx")
        self.assertEqual(config.timeout_sec, 42)

    def test_resolve_codex_cmd_shim_to_native_exe_on_windows(self):
        from unittest import mock
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import BoundedExecutorConfig, _resolve_agent_binary

        config = BoundedExecutorConfig.from_env({"CODEX_BIN": "codex.cmd"})
        with tempfile.TemporaryDirectory() as tmp:
            local_app_data = Path(tmp) / "LocalAppData"
            native = local_app_data / "OpenAI" / "Codex" / "bin" / "codex.exe"
            native.parent.mkdir(parents=True)
            native.write_text("", encoding="utf-8")
            shim = Path(tmp) / "codex.cmd"
            shim.write_text('@echo off\n"%LOCALAPPDATA%\\OpenAI\\Codex\\bin\\codex.exe" %*\n', encoding="utf-8")

            with mock.patch.dict("os.environ", {"LOCALAPPDATA": str(local_app_data)}):
                resolved = _resolve_agent_binary(config, which_func=lambda name: str(shim) if name == "codex.cmd" else None)

        self.assertEqual(Path(resolved), native)

    def test_child_agent_args_use_isolated_read_only_ephemeral_workspace(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import BoundedExecutorConfig, build_agent_args, child_workspace_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = child_workspace_path(root, "chunk_test", "female_001__face_card__v001", 1)
            config = BoundedExecutorConfig.from_env({"CODEX_BIN": "codex"})

            args = build_agent_args(
                "generate one image",
                root=root,
                config=config,
                agent_bin="codex",
                child_workspace=workspace,
            )

            self.assertIn("--ephemeral", args)
            self.assertIn("--ignore-rules", args)
            self.assertIn("--skip-git-repo-check", args)
            self.assertIn("-s", args)
            self.assertEqual(args[args.index("-s") + 1], "read-only")
            self.assertIn("-C", args)
            self.assertEqual(Path(args[args.index("-C") + 1]), workspace)
            self.assertNotEqual(Path(args[args.index("-C") + 1]), root)
            self.assertTrue(workspace.exists())

    def test_child_agent_env_removes_network_and_tool_disable_flags(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import child_agent_env

        env = child_agent_env(
            {
                "CODEX_SANDBOX_NETWORK_DISABLED": "1",
                "CODEX_DISABLE_TOOLS": "1",
                "CODEX_TOOLS_DISABLED": "1",
                "CODEX_IMAGEGEN_DISABLED": "1",
                "KEEP_ME": "yes",
            }
        )

        self.assertNotIn("CODEX_SANDBOX_NETWORK_DISABLED", env)
        self.assertNotIn("CODEX_DISABLE_TOOLS", env)
        self.assertNotIn("CODEX_TOOLS_DISABLED", env)
        self.assertNotIn("CODEX_IMAGEGEN_DISABLED", env)
        self.assertEqual(env["KEEP_ME"], "yes")

    def test_parent_managed_imagegen_writes_handoff_without_spawning_child(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import BoundedExecutorConfig, create_chunk_plan, run_bounded_chunk
        from scripts.ai_image_pipeline_v3.codex_imagegen import read_pending, pending_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root)
            commands = []
            config = BoundedExecutorConfig.from_env({"BOUNDED_EXECUTOR_IMAGEGEN_SURFACE": "parent"})

            def fake_run(args, **kwargs):
                commands.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="SHOULD_NOT_RUN", stderr="")

            result = run_bounded_chunk(
                root=root,
                config=config,
                run_func=fake_run,
                recover_func=lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("not called")),
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            pending = read_pending(pending_path(root))
            self.assertEqual(commands, [])
            self.assertEqual(result["status"], "awaiting_parent_imagegen")
            self.assertEqual(result["reasonCode"], "parent_managed_imagegen_required")
            self.assertTrue(pending)
            self.assertFalse(pending.get("resolved", False))
            self.assertEqual(pending["status"], "pending_imagegen")
            self.assertTrue(Path(result["handoffPromptPath"]).exists())
            self.assertIn("pending-imagegen.json", Path(result["handoffPromptPath"]).read_text(encoding="utf-8"))

    def test_one_asset_child_prompt_is_imagegen_only_and_hides_controller_paths(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import build_one_asset_child_prompt

        prompt = build_one_asset_child_prompt(
            {
                "assetId": "female_054__silhouette_card__v001",
                "profileId": "female_054",
                "shotType": "silhouette_card",
                "attempt": 1,
            },
            generation_prompt="realistic campus image",
            reference_path="C:/repo/ai_image/female/054/face_card.png",
        )

        self.assertIn("$imagegen", prompt)
        self.assertIn("Do not write files", prompt)
        self.assertIn("Do not run shell commands", prompt)
        self.assertIn("IMAGEGEN_DONE", prompt)
        self.assertIn("Use attached face_card as same-person reference", prompt)
        for forbidden in (
            "expectedRawPath",
            "expectedFinalPath",
            "expectedReceiptPath",
            "pending-imagegen.json",
            "current_chunk_plan.json",
            "current_chunk_state.json",
            "C:/repo/ai_image",
        ):
            self.assertNotIn(forbidden, prompt)

    def test_child_command_timeout_kills_windows_process_tree(self):
        from unittest import mock
        from scripts.ai_image_pipeline_v3 import bounded_batch_executor as executor

        proc = mock.Mock()
        proc.pid = 4242
        proc.returncode = -9
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired(["codex", "exec"], 3),
            ("partial stdout", "partial stderr"),
        ]

        with mock.patch.object(executor.os, "name", "nt"), mock.patch.object(executor.subprocess, "Popen", return_value=proc), mock.patch.object(executor.subprocess, "run") as taskkill:
            with self.assertRaises(subprocess.TimeoutExpired) as context:
                executor.run_child_command_with_tree_timeout(
                    ["codex", "exec"],
                    cwd="C:/sandbox",
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=3,
                    shell=False,
                )

        taskkill.assert_called_once()
        self.assertEqual(taskkill.call_args.args[0], ["taskkill", "/PID", "4242", "/T", "/F"])
        self.assertEqual(context.exception.output, "partial stdout")
        self.assertEqual(context.exception.stderr, "partial stderr")

    def test_plan_limits_order_references_and_state_files(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 30)
            plan = create_chunk_plan(root=root)

            self.assertEqual(plan["selectedIdentityCount"], 24)
            self.assertEqual(plan["selectedAssetCount"], 72)
            self.assertTrue((root / "ai_image" / "manifests" / "current_chunk_plan.json").exists())
            self.assertTrue((root / "ai_image" / "manifests" / "current_chunk_state.json").exists())
            self.assertTrue((root / "ai_image" / "reports" / "chunks" / plan["chunkId"] / "events.jsonl").exists())
            first = plan["identities"][0]["assets"]
            self.assertEqual([asset["shotType"] for asset in first], ["face_card", "silhouette_card", "vibe_card"])
            self.assertIsNone(first[0]["requiresReferenceAssetId"])
            self.assertEqual(first[1]["requiresReferenceAssetId"], first[0]["assetId"])
            self.assertEqual(first[2]["requiresReferenceAssetId"], first[0]["assetId"])

    def test_plan_uses_metadata_targets_when_top_level_target_fields_are_absent(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 2, metadata_only_targets=True)
            plan = create_chunk_plan(root=root, max_identities=2)
            self.assertEqual(plan["selectedIdentityCount"], 2)
            self.assertEqual(plan["selectedAssetCount"], 6)
            self.assertEqual(plan["identities"][0]["targetFaceType"], "deer_like")
            self.assertEqual(plan["identities"][0]["targetLooksLevelBand"], "2.5-3.2")

    def test_plan_skips_exhausted_face_card_and_selects_next_eligible_identity(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, validate_current_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 4)
            self._update_generation_row(root, "female_001__face_card__v001", status="failed", attempt=3, attemptCount=3)
            stale_final = root / "ai_image" / "female" / "002" / "face_card.png"
            stale_final.parent.mkdir(parents=True, exist_ok=True)
            stale_final.write_bytes(b"stale-not-approved")
            self._update_generation_row(root, "female_002__face_card__v001", status="failed", attempt=3, attemptCount=3, finalPath=str(stale_final))

            plan = create_chunk_plan(root=root, production=True, max_identities=2, max_assets=6)
            selected_profiles = [identity["profileId"] for identity in plan["identities"]]
            skipped = plan.get("skippedExhaustedCandidates", [])

            self.assertEqual(selected_profiles, ["female_003", "female_004"])
            self.assertEqual(plan["selectedIdentityCount"], 2)
            self.assertEqual(plan["selectedAssetCount"], 6)
            self.assertEqual(skipped[0]["profileId"], "female_001")
            self.assertEqual(skipped[0]["assetId"], "female_001__face_card__v001")
            self.assertEqual(skipped[0]["reason"], "face_card_max_attempts_exhausted")
            self.assertEqual(skipped[1]["profileId"], "female_002")
            self.assertEqual(skipped[1]["assetId"], "female_002__face_card__v001")
            self.assertTrue(validate_current_chunk_plan(root=root, strict=False)["canRun"])

    def test_plan_validation_rejects_exhausted_face_card_candidate(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import PlanValidationError, create_chunk_plan, validate_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            plan = create_chunk_plan(root=root, dry_run=True)
            plan["dryRun"] = False
            plan["planMode"] = "production"
            plan["executable"] = True
            plan["status"] = "planned"
            plan["identities"][0]["assets"][0].update({"status": "failed", "attempt": 3, "attemptCount": 3})

            with self.assertRaises(PlanValidationError) as context:
                validate_chunk_plan(plan, root=root)

            self.assertEqual(context.exception.reason_code, "face_card_max_attempts_exhausted")

    def test_planning_does_not_reduce_existing_approved_evidence_counts(self):
        from PIL import Image

        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.manifest import load_generation_manifest, write_generation_outputs
        from scripts.ai_image_pipeline_v3.targeting import approved_identity_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 3)
            paths = pipeline_paths(root)
            rows = []
            for row in load_generation_manifest(paths):
                out = dict(row)
                if out["profileId"] == "female_001":
                    final = Path(out["finalPath"])
                    final.parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGB", (512, 768), (20, 40, 60)).save(final)
                    out.update({"status": "qa_approved", "localPath": str(final)})
                elif out["assetId"] == "female_002__face_card__v001":
                    out.update({"status": "failed", "attempt": 3, "attemptCount": 3})
                rows.append(out)
            write_generation_outputs(paths, rows)
            before = approved_identity_report(load_generation_manifest(paths))

            create_chunk_plan(root=root, production=True, max_identities=1, max_assets=3)
            after = approved_identity_report(load_generation_manifest(paths))

            self.assertEqual(after["approvedIdentities"], before["approvedIdentities"])
            self.assertEqual(after["approvedAssets"], before["approvedAssets"])

    def test_dry_run_plan_is_non_executable_and_run_refuses_it(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk, validate_current_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            plan = create_chunk_plan(root=root, dry_run=True)
            self.assertTrue(plan["dryRun"])
            self.assertFalse(plan["executable"])
            self.assertEqual(plan["planMode"], "dry_run")
            validation = validate_current_chunk_plan(root=root, strict=False)
            self.assertFalse(validation["canRun"])
            self.assertEqual(validation["reasonCode"], "dry_run_plan_not_executable")

            calls = []

            def fake_run(args, **kwargs):
                calls.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="unexpected", stderr="")

            result = run_bounded_chunk(root=root, run_func=fake_run, which_func=lambda cmd: f"C:/bin/{cmd}.exe")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["reasonCode"], "dry_run_plan_not_executable")
            self.assertEqual(calls, [])

    def test_production_plan_schema_state_and_archive_old_dry_run(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, validate_current_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 2)
            dry = create_chunk_plan(root=root, dry_run=True)
            plan = create_chunk_plan(root=root, production=True, force_replan=True)
            self.assertFalse(plan["dryRun"])
            self.assertTrue(plan["executable"])
            self.assertEqual(plan["planMode"], "production")
            self.assertIn("inputHashes", plan)
            self.assertIn("planHash", plan)
            state = json.loads((root / "ai_image" / "manifests" / "current_chunk_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["chunkId"], plan["chunkId"])
            self.assertEqual(state["planHash"], plan["planHash"])
            self.assertTrue(validate_current_chunk_plan(root=root, strict=False)["canRun"])
            history = list((root / "ai_image" / "reports" / "chunks" / "plan_history").glob("current_chunk_plan_*.json"))
            self.assertTrue(history)
            archived_text = "\n".join(path.read_text(encoding="utf-8") for path in history)
            self.assertIn(dry["chunkId"], archived_text)

    def test_abandon_current_replan_archives_records_and_excludes_profiles(self):
        from PIL import Image

        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, bounded_chunk_status, validate_current_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 6)
            old_plan = create_chunk_plan(root=root, production=True, max_identities=2)
            old_profiles = {identity["profileId"] for identity in old_plan["identities"]}
            state_path = root / "ai_image" / "manifests" / "current_chunk_state.json"
            plan_path = root / "ai_image" / "manifests" / "current_chunk_plan.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            state["status"] = "running"
            plan["status"] = "running"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            first_final = Path(old_plan["identities"][0]["assets"][0]["finalPath"])
            first_final.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (512, 768), (20, 40, 60)).save(first_final)
            self._write_audit(root, face_deficit=119, looks_deficit=119)

            status_before = bounded_chunk_status(root=root)
            self.assertTrue(status_before["abandonable"])
            self.assertFalse(status_before["canRun"])

            new_plan = create_chunk_plan(root=root, production=True, force_replan=True, abandon_current=True, max_identities=2)
            new_profiles = {identity["profileId"] for identity in new_plan["identities"]}
            self.assertTrue(old_profiles.isdisjoint(new_profiles))
            self.assertFalse(new_plan["dryRun"])
            self.assertTrue(new_plan["executable"])
            self.assertEqual(new_plan["planMode"], "production")
            self.assertIn("abandonedPreviousChunk", new_plan)
            self.assertTrue(first_final.exists())
            self.assertTrue(validate_current_chunk_plan(root=root, strict=False)["canRun"])

            abandoned_manifest = root / "ai_image" / "manifests" / "abandoned_chunk_manifest.jsonl"
            self.assertTrue(abandoned_manifest.exists())
            abandoned_rows = [json.loads(line) for line in abandoned_manifest.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(abandoned_rows), 6)
            self.assertEqual({row["profileId"] for row in abandoned_rows}, old_profiles)
            self.assertEqual({row["abandonedChunkId"] for row in abandoned_rows}, {old_plan["chunkId"]})
            old_report = json.loads((root / "ai_image" / "reports" / "chunks" / old_plan["chunkId"] / "chunk_report.json").read_text(encoding="utf-8"))
            self.assertEqual(old_report["status"], "abandoned")
            self.assertEqual(old_report["replacementChunkId"], new_plan["chunkId"])
            history = list((root / "ai_image" / "reports" / "chunks" / "plan_history").glob("current_chunk_plan_*.json"))
            self.assertTrue(history)

            status_after = bounded_chunk_status(root=root)
            self.assertEqual(status_after["abandonedChunkCount"], 1)
            self.assertEqual(status_after["lastAbandonedChunkId"], old_plan["chunkId"])
            self.assertTrue(status_after["canRun"])

    def test_abandon_current_replan_blocks_unresolved_pending_and_manual_flag(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import PlanValidationError, create_chunk_plan
        from scripts.ai_image_pipeline_v3.codex_imagegen import pending_path, write_pending

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 3)
            create_chunk_plan(root=root, production=True, max_identities=1)
            state_path = root / "ai_image" / "manifests" / "current_chunk_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["status"] = "running"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            write_pending(pending_path(root), {"status": "pending_imagegen", "resolved": False, "assetId": "female_001__face_card__v001"})
            with self.assertRaises(PlanValidationError) as context:
                create_chunk_plan(root=root, production=True, force_replan=True, abandon_current=True, max_identities=1)
            self.assertEqual(context.exception.reason_code, "unresolved_pending_imagegen")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 3)
            create_chunk_plan(root=root, production=True, max_identities=1)
            (root / "ai_image" / "manifests" / "manual_review_required.flag").write_text("manual", encoding="utf-8")
            with self.assertRaises(PlanValidationError) as context:
                create_chunk_plan(root=root, production=True, force_replan=True, abandon_current=True, max_identities=1)
            self.assertEqual(context.exception.reason_code, "manual_review_required")

    def test_force_replan_running_chunk_requires_abandon_current(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import PlanValidationError, create_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 3)
            create_chunk_plan(root=root, production=True, max_identities=1)
            state_path = root / "ai_image" / "manifests" / "current_chunk_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["status"] = "running"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaises(PlanValidationError) as context:
                create_chunk_plan(root=root, production=True, force_replan=True, max_identities=1)
            self.assertEqual(context.exception.reason_code, "in_progress_plan_requires_abandon_current")

    def test_stale_plan_detected_when_inputs_or_state_change(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, validate_current_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root, production=True)
            queue = root / "ai_image" / "manifests" / "imagegen_queue.jsonl"
            queue.write_text(queue.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            validation = validate_current_chunk_plan(root=root, strict=False)
            self.assertFalse(validation["canRun"])
            self.assertIn("input_hash_changed:queueJsonSha256", validation["reasons"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root, production=True)
            state_path = root / "ai_image" / "manifests" / "current_chunk_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["planHash"] = "different"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            validation = validate_current_chunk_plan(root=root, strict=False)
            self.assertFalse(validation["canRun"])
            self.assertIn("state_plan_mismatch", validation["reasons"])

    def test_manual_review_and_unresolved_pending_block_run_precheck(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk, validate_current_chunk_plan
        from scripts.ai_image_pipeline_v3.codex_imagegen import pending_path, write_pending

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root, production=True)
            (root / "ai_image" / "manifests" / "manual_review_required.flag").write_text("manual", encoding="utf-8")
            validation = validate_current_chunk_plan(root=root, strict=False)
            self.assertFalse(validation["canRun"])
            self.assertIn("manual_review_required", validation["reasons"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root, production=True)
            write_pending(pending_path(root), {"status": "pending_imagegen", "resolved": False, "assetId": "female_001__face_card__v001"})
            calls = []
            result = run_bounded_chunk(root=root, run_func=lambda args, **kwargs: calls.append(args) or subprocess.CompletedProcess(args, 0))
            self.assertEqual(result["reasonCode"], "unresolved_pending_imagegen")
            self.assertEqual(calls, [])

    def test_plan_excludes_quota_full_and_overlevel_buckets(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1, face_type="dog_like")
            plan = create_chunk_plan(root=root, dry_run=True)
            self.assertEqual(plan["selectedAssetCount"], 0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1, looks="4.4-5.0")
            plan = create_chunk_plan(root=root, dry_run=True)
            self.assertEqual(plan["selectedAssetCount"], 0)

    def test_plan_rejects_duplicate_final_path(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import BoundedBatchExecutorError, create_chunk_plan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1, duplicate_final=True)
            with self.assertRaises(BoundedBatchExecutorError):
                create_chunk_plan(root=root)

    def test_run_processes_one_asset_at_a_time_and_uses_subprocess_list(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root)
            commands = []

            def fake_run(args, **kwargs):
                self.assertIsInstance(args, list)
                self.assertFalse(kwargs.get("shell"))
                commands.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

            result = run_bounded_chunk(
                root=root,
                config=self._config(),
                run_func=fake_run,
                recover_func=self._fake_recover(root),
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False, "finalDecision": "needs_more_generation", "approvedCompleteIdentityCount": 0, "approvedImageCount": 0},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "finalized")
            self.assertEqual(len(commands), 3)
            prompts = [cmd[-1] for cmd in commands]
            self.assertIn("assetId: female_001__face_card__v001", prompts[0])
            self.assertIn("assetId: female_001__silhouette_card__v001", prompts[1])
            self.assertIn("assetId: female_001__vibe_card__v001", prompts[2])
            self.assertNotIn("--image", commands[0])
            self.assertIn("--image", commands[1])
            self.assertIn(str((root / "ai_image" / "female" / "001" / "face_card.png").resolve()), commands[1])
            self.assertIn("--image", commands[2])
            self.assertIn("attached face_card image is the authoritative identity anchor", prompts[1])
            chunk_id = json.loads((root / "ai_image" / "manifests" / "current_chunk_plan.json").read_text(encoding="utf-8"))["chunkId"]
            self.assertFalse((root / "ai_image" / "reports" / "chunks" / chunk_id / "identity_context" / "female_001" / "identity_context.json").exists())
            self.assertIn("-C", commands[1])
            self.assertIn("child_workspaces", commands[1][commands[1].index("-C") + 1])

    def test_failed_command_retries_same_asset_to_max_attempts(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root)
            commands = []

            def fake_run(args, **kwargs):
                commands.append(args)
                return subprocess.CompletedProcess(args, 7, stdout="", stderr="failed")

            result = run_bounded_chunk(
                root=root,
                config=self._config(),
                run_func=fake_run,
                recover_func=self._fake_recover(root),
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(len(commands), 3)
            state = json.loads((root / "ai_image" / "manifests" / "current_chunk_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["assetStates"]["female_001__face_card__v001"], "failed")

    def test_child_timeout_without_image_is_non_consumptive_infrastructure_block(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk
        from scripts.ai_image_pipeline_v3.manifest import load_generation_manifest
        from scripts.ai_image_pipeline_v3.config import pipeline_paths
        from scripts.ai_image_pipeline_v3.pending_admin import pending_status_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            approved_manifest = root / "ai_image" / "manifests" / "approved_identity_manifest.jsonl"
            approved_manifest.write_text('{"profileId":"female_999","status":"approved"}\n', encoding="utf-8")
            create_chunk_plan(root=root)
            commands = []

            def fake_run(args, **kwargs):
                commands.append(args)
                raise subprocess.TimeoutExpired(args, kwargs.get("timeout") or 30)

            result = run_bounded_chunk(
                root=root,
                config=self._config(),
                run_func=fake_run,
                recover_func=lambda **kwargs: (_ for _ in ()).throw(FileNotFoundError("no generated image")),
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "needs_manual_review")
            self.assertEqual(result["reasonCode"], "imagegen_infrastructure_failure")
            self.assertEqual(len(commands), 1)
            state = json.loads((root / "ai_image" / "manifests" / "current_chunk_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["assetStates"]["female_001__face_card__v001"], "imagegen_infrastructure_blocked")
            rows = {row["assetId"]: row for row in load_generation_manifest(pipeline_paths(root))}
            row = rows["female_001__face_card__v001"]
            self.assertEqual(row["attemptCount"], 0)
            self.assertEqual(row["lastInfrastructureFailureAttempt"], 1)
            self.assertEqual(row["status"], "imagegen_infrastructure_blocked")
            pending = pending_status_report(root=root)
            self.assertEqual(pending["status"], "resolved")
            self.assertFalse(pending["unresolved"])
            self.assertEqual(pending["reason"], "imagegen_child_timeout_or_agent_exception_no_image")
            self.assertEqual(approved_manifest.read_text(encoding="utf-8"), '{"profileId":"female_999","status":"approved"}\n')
            events = (root / "ai_image" / "reports" / "chunks" / state["chunkId"] / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("imagegen_infrastructure_failure", events)
            self.assertNotIn("max_attempts_exhausted", events)

    def test_parent_recovered_final_attempt_file_qa_passed_advances_to_next_handoff(self):
        from PIL import Image

        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root)
            final = root / "ai_image" / "female" / "001" / "face_card.png"
            final.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (512, 768), (20, 40, 60)).save(final)
            self._update_generation_row(
                root,
                "female_001__face_card__v001",
                status="file_qa_passed",
                visualQaStatus="visual_qa_pending",
                attempt=3,
                attemptCount=3,
                finalPath=str(final),
                localPath=str(final),
            )
            config = type(self._config())(**{**self._config().__dict__, "imagegen_surface": "parent"})

            result = run_bounded_chunk(
                root=root,
                config=config,
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False},
            )

            self.assertEqual(result["status"], "awaiting_parent_imagegen")
            self.assertEqual(result["reasonCode"], "parent_managed_imagegen_required")
            state = json.loads((root / "ai_image" / "manifests" / "current_chunk_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["assetStates"]["female_001__face_card__v001"], "file_qa_passed")
            self.assertEqual(state["assetStates"]["female_001__silhouette_card__v001"], "pending_imagegen")
            self.assertEqual(state["status"], "generation_paused")
            events = (root / "ai_image" / "reports" / "chunks" / state["chunkId"] / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("manifest_file_qa_passed_resume", events)
            self.assertNotIn("max_attempts_exhausted", events)

    def test_bounded_chunk_qa_accepts_manifest_file_qa_passed_assets(self):
        from PIL import Image

        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk_qa

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root)
            for index, shot in enumerate(("face_card", "silhouette_card", "vibe_card")):
                final = root / "ai_image" / "female" / "001" / f"{shot}.png"
                final.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (512, 768), (20 + index * 30, 40 + index * 30, 60 + index * 30)).save(final)
                self._update_generation_row(
                    root,
                    f"female_001__{shot}__v001",
                    status="file_qa_passed",
                    visualQaStatus="visual_qa_pending",
                    attempt=3,
                    attemptCount=3,
                    finalPath=str(final),
                    localPath=str(final),
                )
            state_path = root / "ai_image" / "manifests" / "current_chunk_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["status"] = "failed"
            state["assetStates"] = {
                "female_001__face_card__v001": "pending_imagegen",
                "female_001__silhouette_card__v001": "planned",
                "female_001__vibe_card__v001": "planned",
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = run_bounded_chunk_qa(
                root=root,
                config=self._config(),
                active_visual_func=lambda **kwargs: {"ok": True},
            )

            self.assertEqual(result["status"], "active_visual_qa_complete")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["assetStates"]["female_001__face_card__v001"], "file_qa_passed")
            self.assertEqual(state["assetStates"]["female_001__silhouette_card__v001"], "file_qa_passed")
            self.assertEqual(state["assetStates"]["female_001__vibe_card__v001"], "file_qa_passed")

    def test_pending_status_marks_preexisting_paths_as_stale_for_checkpoint(self):
        from scripts.ai_image_pipeline_v3.codex_imagegen import pending_path, write_pending
        from scripts.ai_image_pipeline_v3.pending_admin import pending_status_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "ai_image" / "raw" / "female_001__face_card__v001__attempt01.png"
            final = root / "ai_image" / "female" / "001" / "face_card.png"
            raw.parent.mkdir(parents=True, exist_ok=True)
            final.parent.mkdir(parents=True, exist_ok=True)
            raw.write_bytes(b"old")
            final.write_bytes(b"old")
            old_time = 1_700_000_000
            os.utime(raw, (old_time, old_time))
            os.utime(final, (old_time, old_time))
            write_pending(
                pending_path(root),
                {
                    "status": "resolved",
                    "resolved": True,
                    "assetId": "female_001__face_card__v001",
                    "profileId": "female_001",
                    "shotType": "face_card",
                    "attempt": 1,
                    "createdAt": "2026-05-16T10:01:49+00:00",
                    "expectedRawPath": str(raw),
                    "expectedFinalPath": str(final),
                    "reason": "imagegen_child_timeout_or_agent_exception_no_image",
                },
            )

            report = pending_status_report(root=root)

            self.assertTrue(report["expectedRawPath"]["exists"])
            self.assertTrue(report["expectedFinalPath"]["exists"])
            self.assertFalse(report["expectedRawPath"]["newEnoughForPending"])
            self.assertFalse(report["expectedFinalPath"]["newEnoughForPending"])
            self.assertTrue(report["expectedRawPath"]["staleForPending"])
            self.assertTrue(report["expectedFinalPath"]["staleForPending"])

    def test_parent_owned_state_mutation_during_child_is_not_forbidden(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            plan = create_chunk_plan(root=root)
            state_path = root / "ai_image" / "manifests" / "current_chunk_state.json"
            commands = []

            def fake_run(args, **kwargs):
                commands.append(args)
                state = json.loads(state_path.read_text(encoding="utf-8"))
                state["boardHeartbeat"] = "parent-owned status ping"
                state_path.write_text(json.dumps(state), encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, stdout="IMAGEGEN_DONE", stderr="")

            result = run_bounded_chunk(
                root=root,
                config=self._config(),
                run_func=fake_run,
                recover_func=self._fake_recover(root),
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False, "finalDecision": "needs_more_generation", "approvedCompleteIdentityCount": 0, "approvedImageCount": 0},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "finalized")
            self.assertEqual(len(commands), 3)
            self.assertFalse((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())
            events = (root / "ai_image" / "reports" / "chunks" / plan["chunkId"] / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("imagegen_child_started", events)
            self.assertIn("imagegen_child_returned", events)

    def test_parent_recovery_receives_wait_window_after_child_return(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root)
            recovery_kwargs = []

            def fake_run(args, **kwargs):
                return subprocess.CompletedProcess(args, 0, stdout="IMAGEGEN_DONE", stderr="")

            def waiting_recover(**kwargs):
                recovery_kwargs.append(kwargs)
                return self._fake_recover(root)(pending=kwargs["pending"], run_qa=kwargs.get("run_qa", False))

            result = run_bounded_chunk(
                root=root,
                config=self._config(),
                run_func=fake_run,
                recover_func=waiting_recover,
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False, "finalDecision": "needs_more_generation", "approvedCompleteIdentityCount": 0, "approvedImageCount": 0},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "finalized")
            self.assertTrue(recovery_kwargs)
            self.assertGreaterEqual(recovery_kwargs[0].get("wait_seconds", 0), 30)
            self.assertGreater(recovery_kwargs[0].get("poll_interval", 0), 0)

    def test_recovery_failure_stops_before_next_asset_and_sets_manual_flag(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root)
            commands = []

            def fake_run(args, **kwargs):
                commands.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

            def bad_recover(**kwargs):
                raise RuntimeError("no generated image")

            result = run_bounded_chunk(
                root=root,
                config=self._config(),
                run_func=fake_run,
                recover_func=bad_recover,
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(len(commands), 1)
            self.assertTrue((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())

    def test_child_side_recovery_receipt_commits_without_parent_recovery(self):
        from PIL import Image

        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk
        from scripts.ai_image_pipeline_v3.codex_imagegen import pending_path, read_pending, write_pending
        from scripts.ai_image_pipeline_v3.one_asset_transaction import transaction_receipt_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            plan = create_chunk_plan(root=root)
            commands = []

            def fake_run(args, **kwargs):
                commands.append(args)
                pending = read_pending(pending_path(root))
                raw = Path(pending["expectedRawPath"])
                final = Path(pending["expectedFinalPath"])
                digest = hashlib.sha256(str(pending["assetId"]).encode("utf-8")).digest()
                color = tuple(40 + digest[index] % 160 for index in range(3))
                for path in (raw, final):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGB", (512, 768), color).save(path)
                receipt_path = Path(pending["expectedReceiptPath"])
                receipt_path.parent.mkdir(parents=True, exist_ok=True)
                reference_text = str(pending.get("referenceImagePath") or "")
                reference_path = Path(reference_text) if reference_text else None
                reference_hash = hashlib.sha256(reference_path.read_bytes()).hexdigest() if reference_path and reference_path.exists() else None
                receipt_path.write_text(
                    json.dumps(
                        {
                            "schemaVersion": "seolleyeon_one_asset_transaction_v3",
                            "transactionId": f"{pending['chunkId']}_{pending['assetId']}_attempt{pending['attempt']}",
                            "chunkId": pending["chunkId"],
                            "assetId": pending["assetId"],
                            "profileId": pending["profileId"],
                            "gender": pending["gender"],
                            "numericId": pending["numericId"],
                            "shotType": pending["shotType"],
                            "attempt": pending["attempt"],
                            "startedAt": "2026-05-10T00:00:00+00:00",
                            "finishedAt": "2026-05-10T00:00:10+00:00",
                            "generated": True,
                            "recovered": True,
                            "pendingResolved": True,
                            "fileQaRan": True,
                            "fileQaPassed": True,
                            "rawPath": pending["expectedRawPath"],
                            "finalPath": pending["expectedFinalPath"],
                            "sourceGeneratedImagePath": "",
                            "referencePath": pending.get("referenceImagePath") or None,
                            "referenceAttached": bool(reference_hash),
                            "referencePathSha256": reference_hash,
                            "fileQa": {"decision": "file_passed", "width": 512, "height": 768, "format": "PNG", "aspectRatio": 0.6667, "sizeBytes": final.stat().st_size, "reasons": []},
                            "workerActions": ["imagegen_called", "recovered_to_raw", "copied_to_final", "pending_resolved", "file_qa_ran"],
                            "stdoutLog": "",
                            "stderrLog": "",
                            "error": None,
                            "status": "succeeded",
                        }
                    ),
                    encoding="utf-8",
                )
                pending.update({"status": "resolved", "resolved": True, "resolvedBy": "one_asset_worker"})
                write_pending(pending_path(root), pending)
                return subprocess.CompletedProcess(args, 0, stdout="receipt written", stderr="")

            def forbidden_recover(**kwargs):
                raise AssertionError("parent recovery should not run when child receipt/files are valid")

            result = run_bounded_chunk(
                root=root,
                config=self._config(),
                run_func=fake_run,
                recover_func=forbidden_recover,
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False, "finalDecision": "needs_more_generation", "approvedCompleteIdentityCount": 0, "approvedImageCount": 0},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "finalized")
            self.assertEqual(len(commands), 3)
            self.assertTrue(transaction_receipt_path(root, plan["chunkId"], "female_001__face_card__v001", 1).exists())
            state = json.loads((root / "ai_image" / "manifests" / "current_chunk_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["assetStates"]["female_001__face_card__v001"], "file_qa_passed")

    def test_child_forbidden_mutation_restores_manifest_and_hard_stops(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 2)
            create_chunk_plan(root=root)
            asset_qa = root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl"
            asset_qa.write_text('{"schemaVersion":"seolleyeon_asset_qa_manifest_v3","assetId":"visual"}\n', encoding="utf-8")
            commands = []

            def fake_run(args, **kwargs):
                commands.append(args)
                asset_qa.write_text('{"qaStage":"file_qa","assetId":"child_mutation"}\n', encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, stdout="mutated", stderr="")

            result = run_bounded_chunk(
                root=root,
                config=self._config(),
                run_func=fake_run,
                recover_func=self._fake_recover(root),
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "needs_manual_review")
            self.assertEqual(result["reasonCode"], "child_forbidden_mutation")
            self.assertEqual(len(commands), 1)
            manifest_text = asset_qa.read_text(encoding="utf-8")
            self.assertIn("seolleyeon_asset_qa_manifest_v3", manifest_text)
            self.assertNotIn("qaStage", manifest_text)
            state = json.loads((root / "ai_image" / "manifests" / "current_chunk_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["assetStates"]["female_001__face_card__v001"], "failed")
            self.assertEqual(state["assetStates"]["female_002__face_card__v001"], "planned")
            quarantine_files = list((root / "ai_image" / "reports" / "chunks" / result["chunkId"] / "forbidden_file_backups").rglob("quarantine/*"))
            self.assertTrue(quarantine_files)

    def test_child_forbidden_mutation_auto_reconciles_and_resumes_when_safe(self):
        from PIL import Image

        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk
        from scripts.ai_image_pipeline_v3.codex_imagegen import pending_path, read_pending, write_pending
        from scripts.ai_image_pipeline_v3.one_asset_transaction import transaction_receipt_path

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            plan = create_chunk_plan(root=root)
            asset_qa = root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl"
            asset_qa.write_text('{"schemaVersion":"seolleyeon_asset_qa_manifest_v3","assetId":"visual"}\n', encoding="utf-8")
            commands = []

            def fake_run(args, **kwargs):
                commands.append(args)
                pending = read_pending(pending_path(root))
                raw = Path(pending["expectedRawPath"])
                final = Path(pending["expectedFinalPath"])
                digest = hashlib.sha256(str(pending["assetId"]).encode("utf-8")).digest()
                color = tuple(40 + digest[index] % 160 for index in range(3))
                for path in (raw, final):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGB", (512, 768), color).save(path)
                receipt_path = Path(pending["expectedReceiptPath"])
                receipt_path.parent.mkdir(parents=True, exist_ok=True)
                reference_text = str(pending.get("referenceImagePath") or "")
                reference_path = Path(reference_text) if reference_text else None
                reference_hash = hashlib.sha256(reference_path.read_bytes()).hexdigest() if reference_path and reference_path.exists() else None
                receipt_path.write_text(
                    json.dumps(
                        {
                            "schemaVersion": "seolleyeon_one_asset_transaction_v3",
                            "transactionId": f"{pending['chunkId']}_{pending['assetId']}_attempt{pending['attempt']}",
                            "chunkId": pending["chunkId"],
                            "assetId": pending["assetId"],
                            "profileId": pending["profileId"],
                            "gender": pending["gender"],
                            "numericId": pending["numericId"],
                            "shotType": pending["shotType"],
                            "attempt": pending["attempt"],
                            "startedAt": "2026-05-10T00:00:00+00:00",
                            "finishedAt": "2026-05-10T00:00:10+00:00",
                            "generated": True,
                            "recovered": True,
                            "pendingResolved": True,
                            "fileQaRan": True,
                            "fileQaPassed": True,
                            "rawPath": pending["expectedRawPath"],
                            "finalPath": pending["expectedFinalPath"],
                            "sourceGeneratedImagePath": "",
                            "referencePath": pending.get("referenceImagePath") or None,
                            "referenceAttached": bool(reference_hash),
                            "referencePathSha256": reference_hash,
                            "fileQa": {"decision": "file_passed", "width": 512, "height": 768, "format": "PNG", "aspectRatio": 0.6667, "sizeBytes": final.stat().st_size, "reasons": []},
                            "workerActions": ["imagegen_called", "recovered_to_raw", "copied_to_final", "pending_resolved", "file_qa_ran"],
                            "stdoutLog": "",
                            "stderrLog": "",
                            "error": None,
                            "status": "succeeded",
                        }
                    ),
                    encoding="utf-8",
                )
                pending.update({"status": "resolved", "resolved": True, "resolvedBy": "one_asset_worker"})
                write_pending(pending_path(root), pending)
                if len(commands) == 1:
                    asset_qa.write_text('{"qaStage":"file_qa","assetId":"child_mutation"}\n', encoding="utf-8")
                return subprocess.CompletedProcess(args, 0, stdout="receipt written", stderr="")

            result = run_bounded_chunk(
                root=root,
                config=self._config(),
                run_func=fake_run,
                recover_func=lambda **kwargs: (_ for _ in ()).throw(AssertionError("parent recovery should not run")),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False, "finalDecision": "needs_more_generation", "approvedCompleteIdentityCount": 0, "approvedImageCount": 0},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "finalized")
            self.assertEqual(len(commands), 3)
            self.assertFalse((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())
            self.assertTrue(transaction_receipt_path(root, plan["chunkId"], "female_001__face_card__v001", 1).exists())
            manifest_text = asset_qa.read_text(encoding="utf-8")
            self.assertIn("seolleyeon_asset_qa_manifest_v3", manifest_text)
            self.assertNotIn("qaStage", manifest_text)
            state = json.loads((root / "ai_image" / "manifests" / "current_chunk_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["assetStates"]["female_001__face_card__v001"], "file_qa_passed")
            self.assertEqual(state["assetStates"]["female_001__silhouette_card__v001"], "file_qa_passed")
            self.assertEqual(state["assetStates"]["female_001__vibe_card__v001"], "file_qa_passed")
            events = (root / "ai_image" / "reports" / "chunks" / plan["chunkId"] / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("child_forbidden_mutation_auto_reconciled", events)

    def test_existing_recoverable_manual_flag_blocks_run_until_operator_reconciles(self):
        from PIL import Image

        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            plan = create_chunk_plan(root=root)
            final = root / "ai_image" / "female" / "001" / "face_card.png"
            final.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (512, 768), (20, 40, 60)).save(final)
            flag = root / "ai_image" / "manifests" / "manual_review_required.flag"
            flag.write_text(json.dumps({"reason": "child_forbidden_mutation"}), encoding="utf-8")
            commands = []

            def fake_run(args, **kwargs):
                commands.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

            result = run_bounded_chunk(
                root=root,
                config=self._config(),
                run_func=fake_run,
                recover_func=self._fake_recover(root),
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False, "finalDecision": "needs_more_generation", "approvedCompleteIdentityCount": 0, "approvedImageCount": 0},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "needs_manual_review")
            self.assertEqual(result["reasonCode"], "manual_review_required")
            self.assertTrue(flag.exists())
            self.assertEqual(commands, [])

    def test_resolved_pending_manual_flag_blocks_run_until_operator_reconciles(self):
        from PIL import Image

        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk
        from scripts.ai_image_pipeline_v3.codex_imagegen import pending_path, write_pending

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            plan = create_chunk_plan(root=root)
            final = root / "ai_image" / "female" / "001" / "face_card.png"
            final.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (512, 768), (20, 40, 60)).save(final)
            pending = {
                "status": "recovered",
                "resolved": True,
                "assetId": "female_001__face_card__v001",
                "profileId": "female_001",
                "gender": "female",
                "numericId": "001",
                "shotType": "face_card",
                "attempt": 1,
                "expectedRawPath": str(final),
                "expectedFinalPath": str(final),
            }
            write_pending(pending_path(root), pending)
            flag = root / "ai_image" / "manifests" / "manual_review_required.flag"
            flag.write_text(json.dumps({"reason": "unresolved_pending_imagegen", "details": {"assetId": "female_001__face_card__v001", "status": "recovered"}}), encoding="utf-8")
            commands = []

            def fake_run(args, **kwargs):
                commands.append(args)
                return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

            result = run_bounded_chunk(
                root=root,
                config=self._config(),
                run_func=fake_run,
                recover_func=self._fake_recover(root),
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False, "finalDecision": "needs_more_generation", "approvedCompleteIdentityCount": 0, "approvedImageCount": 0},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )

            self.assertEqual(result["status"], "needs_manual_review")
            self.assertEqual(result["reasonCode"], "manual_review_required")
            self.assertTrue(flag.exists())
            self.assertEqual(commands, [])

    def test_reconcile_existing_files_dry_run_does_not_approve(self):
        from PIL import Image

        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, reconcile_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            plan = create_chunk_plan(root=root)
            final = root / "ai_image" / "female" / "001" / "face_card.png"
            final.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (512, 768), (20, 40, 60)).save(final)
            flag = root / "ai_image" / "manifests" / "manual_review_required.flag"
            flag.write_text(json.dumps({"reason": "bounded_recovery_failed"}), encoding="utf-8")

            report = reconcile_bounded_chunk(root=root, dry_run=True)
            self.assertEqual(report["chunkId"], plan["chunkId"])
            self.assertEqual(report["plannedExistingFiles"], 1)
            self.assertEqual(report["fileQaPassedAssets"], 1)
            self.assertFalse(report["stateChanged"])
            self.assertFalse((root / "ai_image" / "manifests" / "approved_identity_manifest.jsonl").exists())

    def test_reconcile_apply_quarantines_non_visual_asset_qa_rows(self):
        from PIL import Image

        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, reconcile_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root)
            self._write_audit(root, face_deficit=119, looks_deficit=119)
            final = root / "ai_image" / "female" / "001" / "face_card.png"
            final.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (512, 768), (20, 40, 60)).save(final)
            manifest = root / "ai_image" / "manifests" / "asset_qa_manifest.jsonl"
            manifest.write_text(
                '{"schemaVersion":"seolleyeon_asset_qa_manifest_v3","assetId":"visual"}\n'
                '{"qaStage":"file_qa","assetId":"child_file_qa"}\n',
                encoding="utf-8",
            )
            flag = root / "ai_image" / "manifests" / "manual_review_required.flag"
            flag.write_text(json.dumps({"reason": "child_forbidden_mutation"}), encoding="utf-8")

            report = reconcile_bounded_chunk(root=root, dry_run=False, apply=True, clear_manual_flag_if_safe=True)
            sanitize = report["assetQaManifestSanitization"]
            self.assertTrue(sanitize["applied"])
            self.assertEqual(sanitize["rowsQuarantined"], 1)
            self.assertTrue(report["planInputRefresh"]["applied"])
            text = manifest.read_text(encoding="utf-8")
            self.assertIn("seolleyeon_asset_qa_manifest_v3", text)
            self.assertNotIn("qaStage", text)
            self.assertFalse((root / "ai_image" / "manifests" / "approved_identity_manifest.jsonl").exists())
            status = json.loads((root / "ai_image" / "manifests" / "current_chunk_state.json").read_text(encoding="utf-8"))
            plan = json.loads((root / "ai_image" / "manifests" / "current_chunk_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(status["planHash"], plan["planHash"])

    def test_dependent_asset_requires_face_reference(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root)
            config = self._config()
            config = type(config)(**{**config.__dict__, "reference_mode": "disabled"})
            result = run_bounded_chunk(
                root=root,
                config=config,
                run_func=lambda args, **kwargs: subprocess.CompletedProcess(args, 0, stdout="ok", stderr=""),
                recover_func=self._fake_recover(root),
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )
            self.assertEqual(result["status"], "failed")
            flag = root / "ai_image" / "manifests" / "manual_review_required.flag"
            self.assertTrue(flag.exists())

    def test_dependent_asset_fails_when_image_input_probe_has_no_supported_arg(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import create_chunk_plan, run_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root)
            config = self._config()
            config = type(config)(**{**config.__dict__, "image_arg_mode": "auto"})
            commands = []

            def fake_run(args, **kwargs):
                commands.append(args)
                if args[-1] == "--help":
                    return subprocess.CompletedProcess(args, 0, stdout="usage: omx exec", stderr="")
                return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

            result = run_bounded_chunk(
                root=root,
                config=config,
                run_func=fake_run,
                recover_func=self._fake_recover(root),
                file_qa_func=self._fake_file_qa(root),
                active_visual_func=lambda **kwargs: {"ok": True},
                audit_func=lambda **kwargs: {"passed": False},
                which_func=lambda cmd: f"C:/bin/{cmd}.exe",
            )
            self.assertEqual(result["status"], "failed")
            self.assertTrue((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())
            self.assertTrue(any(command[-1] == "--help" for command in commands))

    def test_finalize_requires_active_visual_qa(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import BoundedBatchExecutorError, create_chunk_plan, finalize_bounded_chunk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_audit(root)
            self._write_manifest(root, 1)
            create_chunk_plan(root=root)
            with self.assertRaises(BoundedBatchExecutorError):
                finalize_bounded_chunk(root=root)

    def test_agent_binary_falls_back_from_omx_to_codex_and_fails_cleanly(self):
        from scripts.ai_image_pipeline_v3.bounded_batch_executor import BoundedBatchExecutorError, _resolve_agent_binary

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(_resolve_agent_binary(self._config(), root=root, which_func=lambda cmd: "codex.exe" if cmd == "codex" else None), "codex.exe")
            with self.assertRaises(BoundedBatchExecutorError):
                _resolve_agent_binary(self._config(), root=root, which_func=lambda cmd: None)
            self.assertTrue((root / "ai_image" / "manifests" / "manual_review_required.flag").exists())

    def test_dispatcher_and_supervisor_reference_bounded_chunk(self):
        from scripts.ai_image_pipeline_v3.cli import build_parser
        from scripts.ai_image_pipeline_v3.supervisor import supervisor_status

        choices = next(action.choices for action in build_parser()._actions if action.dest == "command")
        for command in ("bounded-chunk-plan", "bounded-chunk-run", "bounded-chunk-resume", "bounded-chunk-status", "bounded-chunk-validate-plan", "bounded-chunk-reconcile", "bounded-chunk-qa", "bounded-chunk-finalize"):
            self.assertIn(command, choices)
        shell = Path("scripts/codex_imagegen_supervisor_v3.sh").read_text(encoding="utf-8")
        self.assertIn("bounded-chunk-validate-plan", shell)
        self.assertIn("bounded-chunk-status", shell)
        self.assertIn("try_reconcile_manual_review_flag", shell)
        self.assertNotIn("bounded-chunk-reconcile --root . --apply --clear-manual-flag-if-safe", shell)
        autopilot = Path("scripts/codex_imagegen_chunk_autopilot_v3.sh").read_text(encoding="utf-8")
        self.assertIn("deprecated for production AI profile generation", autopilot)
        self.assertIn("exit 2", "\n".join(autopilot.splitlines()[:8]))
        self.assertIn("bounded-chunk-run", shell)
        self.assertIn("bounded_batch_executor", supervisor_status(root=Path(tempfile.mkdtemp()), mode="chunk")["chunkExecutor"])


if __name__ == "__main__":
    unittest.main()
