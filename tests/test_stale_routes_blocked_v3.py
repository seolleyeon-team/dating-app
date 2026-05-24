import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class StaleRoutesBlockedV3Tests(unittest.TestCase):
    def test_makefile_autopilot_and_supervisor_run_targets_are_hard_gated(self):
        makefile = Path("Makefile").read_text(encoding="utf-8")

        autopilot_section = makefile.split("ai-image-autopilot-chunks-720:", 1)[1].split("\n\n", 1)[0]
        self.assertIn("Deprecated unsafe route", autopilot_section)
        self.assertNotIn("codex_imagegen_chunk_autopilot_v3.sh", autopilot_section)
        self.assertNotIn("run_hermes_image_pipeline_v3.py", autopilot_section)

        supervisor_section = makefile.split("ai-image-supervisor-720:", 1)[1].split("\n\n", 1)[0]
        self.assertIn("Deprecated ambiguous target", supervisor_section)
        self.assertIn("@exit 2", supervisor_section)

    def test_deprecated_hermes_entrypoint_returns_nonzero_by_default(self):
        result = subprocess.run(
            [sys.executable, "scripts/run_hermes_image_pipeline_v3.py", "--help"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("deprecated", result.stderr)

    def test_hermes_wrapper_autopilot_mode_is_disabled_even_when_real_imagegen_flag_is_set(self):
        from scripts.ai_image_pipeline_v3.hermes_wrapper import HermesWrapperConfig, HermesWrapperError, run_hermes_wrapper

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = HermesWrapperConfig(
                root=root,
                run_id="unit",
                execution_mode="autopilot",
                allow_real_imagegen=True,
            )
            with self.assertRaises(HermesWrapperError):
                run_hermes_wrapper(config)

    def test_openai_image_client_is_disabled_by_default(self):
        from scripts.ai_image_pipeline_v3.openai_image import OpenAIImageClient

        with self.assertRaises(RuntimeError):
            OpenAIImageClient()

    def test_dispatcher_keeps_production_route_on_bounded_executor(self):
        from scripts.ai_image_pipeline_v3.cli import build_parser

        choices = next(action.choices for action in build_parser()._actions if action.dest == "command")
        self.assertIn("bounded-chunk-run", choices)
        self.assertIn("bounded-chunk-reconcile", choices)
        self.assertIn("bounded-chunk-status", choices)
        dispatcher = Path("scripts/ai_image_pipeline_v3/cli.py").read_text(encoding="utf-8")
        self.assertIn("run_bounded_chunk(root=args.root)", dispatcher)


if __name__ == "__main__":
    unittest.main()
