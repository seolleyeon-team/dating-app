import json
import subprocess
import tempfile
import unittest
from pathlib import Path


class HermesWrapperV3Tests(unittest.TestCase):
    def _jsonl_rows(self, path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_dry_run_writes_deterministic_run_artifacts_without_subprocess(self):
        from scripts.ai_image_pipeline_v3.hermes_wrapper import HermesWrapperConfig, run_hermes_wrapper

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def forbidden_run(*args, **kwargs):
                calls.append(args)
                raise AssertionError("dry-run must not invoke subprocesses")

            result = run_hermes_wrapper(
                HermesWrapperConfig(
                    root=root,
                    run_id="run_a_dry_run",
                    task_brief="Generate a safe fixture image set without real image generation.",
                    execution_mode="dry-run",
                ),
                run_func=forbidden_run,
            )

            run_dir = root / "ai_image" / "runs" / "run_a_dry_run"
            self.assertEqual(result.status, "dry_run")
            self.assertEqual(calls, [])
            for relative in (
                "brief.md",
                "run.json",
                "manifest.jsonl",
                "prompts",
                "generated/raw",
                "generated/processed",
                "verdicts",
                "diffs",
                "final",
                "logs",
            ):
                self.assertTrue((run_dir / relative).exists(), relative)

            rows = self._jsonl_rows(run_dir / "manifest.jsonl")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["schemaVersion"], "seolleyeon_hermes_wrapper_attempt_v1")
            self.assertEqual(rows[0]["run_id"], "run_a_dry_run")
            self.assertEqual(rows[0]["status"], "dry_run")
            self.assertEqual(rows[0]["provider"], "codex-built-in-imagegen")
            self.assertEqual(rows[0]["command_used"], ["dry-run"])
            self.assertIn("no existing OMX pipeline command was invoked", (run_dir / "logs" / "attempt01.stdout.txt").read_text(encoding="utf-8"))

    def test_fixture_mode_writes_prompt_and_verdict_without_image_generation(self):
        from scripts.ai_image_pipeline_v3.hermes_wrapper import HermesWrapperConfig, run_hermes_wrapper

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            result = run_hermes_wrapper(
                HermesWrapperConfig(
                    root=root,
                    run_id="run_a_fixture",
                    task_brief="Fixture mode for Hermes wrapper tests.",
                    execution_mode="fixture",
                ),
                run_func=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fixture must not invoke subprocesses")),
            )

            run_dir = root / "ai_image" / "runs" / "run_a_fixture"
            self.assertEqual(result.status, "fixture_complete")
            prompt = run_dir / "prompts" / "attempt01_fixture_prompt.md"
            verdict = run_dir / "verdicts" / "attempt01_fixture_verdict.json"
            self.assertTrue(prompt.exists())
            self.assertTrue(verdict.exists())
            verdict_payload = json.loads(verdict.read_text(encoding="utf-8"))
            self.assertEqual(verdict_payload["score"], 100)
            self.assertEqual(verdict_payload["verdict"], "pass")
            row = self._jsonl_rows(run_dir / "manifest.jsonl")[0]
            self.assertEqual(row["status"], "fixture_complete")
            self.assertEqual(row["score"], 100)
            self.assertTrue(row["verdict_path"].endswith("attempt01_fixture_verdict.json"))

    def test_status_mode_invokes_existing_dispatcher_and_logs_output(self):
        from scripts.ai_image_pipeline_v3.hermes_wrapper import HermesWrapperConfig, run_hermes_wrapper

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def fake_run(args, **kwargs):
                calls.append((args, kwargs))
                return subprocess.CompletedProcess(args, 0, stdout='{"status":"ok"}\n', stderr="")

            result = run_hermes_wrapper(
                HermesWrapperConfig(
                    root=root,
                    run_id="run_a_status",
                    task_brief="Poll current bounded chunk status.",
                    execution_mode="status",
                ),
                run_func=fake_run,
            )

            run_dir = root / "ai_image" / "runs" / "run_a_status"
            self.assertEqual(result.status, "succeeded")
            self.assertEqual(len(calls), 1)
            self.assertIn("run_ai_image_pipeline_v3.py", calls[0][0][1])
            self.assertIn("bounded-chunk-status", calls[0][0])
            self.assertEqual(calls[0][1]["cwd"], str(root))
            self.assertIn('"status":"ok"', (run_dir / "logs" / "attempt01.stdout.txt").read_text(encoding="utf-8"))
            row = self._jsonl_rows(run_dir / "manifest.jsonl")[0]
            self.assertEqual(row["status"], "succeeded")
            self.assertEqual(row["return_code"], 0)

    def test_real_generation_modes_require_explicit_allow_flag(self):
        from scripts.ai_image_pipeline_v3.hermes_wrapper import HermesWrapperConfig, HermesWrapperError, run_hermes_wrapper

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(HermesWrapperError):
                run_hermes_wrapper(
                    HermesWrapperConfig(
                        root=Path(tmp),
                        run_id="run_a_blocked",
                        task_brief="This would run real image generation.",
                        execution_mode="bounded-run",
                    )
                )

    def test_autopilot_mode_resolves_git_bash_when_bash_is_not_on_path(self):
        from scripts.ai_image_pipeline_v3.hermes_wrapper import HermesWrapperConfig, _command_for_mode

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git_bash = root / "Git" / "bin" / "bash.exe"
            git_bash.parent.mkdir(parents=True)
            git_bash.write_text("", encoding="utf-8")
            config = HermesWrapperConfig(
                root=root,
                run_id="run_a_autopilot",
                execution_mode="autopilot",
                allow_real_imagegen=True,
                bash_bin="bash",
            )

            command = _command_for_mode(config, which_func=lambda cmd: None, bash_candidates=(git_bash,))

            self.assertEqual(command[0], str(git_bash))
            self.assertTrue(command[1].endswith("codex_imagegen_chunk_autopilot_v3.sh"))

    def test_missing_reference_fails_with_manifest_and_logs(self):
        from scripts.ai_image_pipeline_v3.hermes_wrapper import HermesWrapperConfig, run_hermes_wrapper

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_hermes_wrapper(
                HermesWrapperConfig(
                    root=root,
                    run_id="run_a_missing_reference",
                    task_brief="Validate reference image handling.",
                    reference_images=("missing-reference.png",),
                    execution_mode="dry-run",
                )
            )

            run_dir = root / "ai_image" / "runs" / "run_a_missing_reference"
            self.assertEqual(result.status, "failed")
            rows = self._jsonl_rows(run_dir / "manifest.jsonl")
            self.assertEqual(rows[0]["status"], "failed")
            self.assertIn("missing reference images", rows[0]["error"])
            self.assertIn("missing reference images", (run_dir / "logs" / "attempt01.stderr.txt").read_text(encoding="utf-8"))

    def test_dispatcher_exposes_hermes_wrapper_command(self):
        from scripts.ai_image_pipeline_v3.cli import build_parser

        choices = next(action.choices for action in build_parser()._actions if action.dest == "command")
        self.assertIn("hermes-wrapper", choices)


if __name__ == "__main__":
    unittest.main()
