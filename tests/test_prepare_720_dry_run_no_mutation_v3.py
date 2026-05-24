import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


ACTIVE_RELATIVE_PATHS = (
    "ai_image/manifests/identity_manifest.jsonl",
    "ai_image/manifests/imagegen_queue.jsonl",
    "ai_image/manifests/ai_profile_specs_v3.jsonl",
    "ai_image/manifests/ai_profile_assets_v3.jsonl",
    "ai_image/manifests/ai_profile_assets_v3.csv",
    "ai_image/manifests/generation_manifest.jsonl",
    "ai_image/reports/generation_status.csv",
    "ai_image/manifests/current_chunk_plan.json",
    "ai_image/manifests/current_chunk_state.json",
    "ai_image/manifests/pending-imagegen.json",
    "ai_image/manifests/approved_identity_manifest.jsonl",
    "ai_image/manifests/rejected_identity_manifest.jsonl",
    "ai_image/manifests/asset_qa_manifest.jsonl",
    "ai_image/manifests/identity_qa_manifest.jsonl",
)


class Prepare720DryRunNoMutationV3Tests(unittest.TestCase):
    def _seed_active_files(self, root: Path) -> dict[str, tuple[str, int]]:
        before = {}
        for idx, rel in enumerate(ACTIVE_RELATIVE_PATHS):
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            content = f"sentinel-{idx}-{rel}\n"
            path.write_text(content, encoding="utf-8")
            before[rel] = (content, path.stat().st_mtime_ns)
        return before

    def _assert_active_unchanged(self, root: Path, before: dict[str, tuple[str, int]], *, check_mtime: bool = True) -> None:
        for rel, (content, mtime_ns) in before.items():
            path = root / rel
            self.assertTrue(path.exists(), rel)
            self.assertEqual(path.read_text(encoding="utf-8"), content, rel)
            if check_mtime:
                self.assertEqual(path.stat().st_mtime_ns, mtime_ns, rel)

    def test_cli_passes_dry_run_to_prepare_assets(self):
        from scripts.ai_image_pipeline_v3 import cli
        from scripts.ai_image_pipeline_v3.prepare import PrepareResult

        fake = PrepareResult(1, 3, Path("a"), Path("b"), Path("c"), Path("d"), Path("e"))
        with mock.patch("scripts.ai_image_pipeline_v3.prepare.prepare_assets", return_value=fake) as mocked:
            code = cli.main(["prepare-720", "--root", ".", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertTrue(mocked.call_args.kwargs["dry_run"])

    def test_prepare_assets_dry_run_does_not_write_active_manifest_files(self):
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = self._seed_active_files(root)
            result = prepare_assets(root=root, dry_run=True)
            self._assert_active_unchanged(root, before)
            self.assertEqual(result.specs_count, 280)
            self.assertEqual(result.asset_count, 840)
            self.assertTrue((root / "ai_image/reports/pipeline_audit/prepare_720_dry_run_latest.json").exists())
            self.assertTrue((root / "ai_image/reports/pipeline_audit/prepare_720_dry_run_latest.md").exists())

    def test_prepare_assets_non_dry_run_still_writes_active_manifests(self):
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_assets(root=root, force=True, replace_manifest=True)
            self.assertTrue((root / "ai_image/manifests/identity_manifest.jsonl").exists())
            self.assertTrue((root / "ai_image/manifests/imagegen_queue.jsonl").exists())
            self.assertTrue((root / "ai_image/manifests/ai_profile_specs_v3.jsonl").exists())
            self.assertTrue((root / "ai_image/manifests/ai_profile_assets_v3.jsonl").exists())
            self.assertTrue((root / "ai_image/manifests/ai_profile_assets_v3.csv").exists())
            self.assertTrue((root / "ai_image/manifests/generation_manifest.jsonl").exists())
            self.assertTrue((root / "ai_image/reports/generation_status.csv").exists())

    def test_dispatcher_prepare_720_dry_run_is_non_mutating(self):
        from scripts.ai_image_pipeline_v3 import cli

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = self._seed_active_files(root)
            code = cli.main(["prepare-720", "--root", str(root), "--dry-run"])
            self.assertEqual(code, 0)
            self._assert_active_unchanged(root, before)
            self.assertTrue((root / "ai_image/reports/pipeline_audit/prepare_720_dry_run_latest.json").exists())

    def test_dry_run_report_includes_required_fields_and_v4_counts(self):
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        prompt_module = load_prompt_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_assets(root=root, dry_run=True)
            report_path = root / "ai_image/reports/pipeline_audit/prepare_720_dry_run_latest.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))

        self.assertEqual(report["specs"], 280)
        self.assertEqual(report["assets"], 840)
        self.assertEqual(report["primaryIdentities"], 240)
        self.assertEqual(report["reserveIdentities"], 40)
        self.assertEqual(report["primaryAssets"], 720)
        self.assertEqual(report["reserveAssets"], 120)
        self.assertIn("distributionCounts", report)
        self.assertIn("promptHashMissing", report)
        self.assertIn("promptHashMismatches", report)
        self.assertEqual(report["promptTargetingVersionCounts"].get(prompt_module.PROMPT_TARGETING_VERSION), 840)
        self.assertEqual(report["oldVersionCount"], 0)
        self.assertEqual(report["missingPromptTargetingVersion"], 0)
        self.assertEqual(report["promptHashMissing"], 0)
        self.assertEqual(report["promptHashMismatches"], 0)

    def test_active_refresh_after_dry_run_writes_v4_manifests(self):
        from scripts.ai_image_pipeline_v3.config import pipeline_paths, read_jsonl
        from scripts.ai_image_pipeline_v3.prepare import prepare_assets
        from scripts.ai_image_pipeline_v3.prompt_source import load_prompt_module

        prompt_module = load_prompt_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_assets(root=root, dry_run=True)
            prepare_assets(root=root, force=True, replace_manifest=True)
            paths = pipeline_paths(root)
            assets = read_jsonl(paths.manifests / "ai_profile_assets_v3.jsonl")
            generation = read_jsonl(paths.manifests / "generation_manifest.jsonl")

        self.assertEqual(len(assets), 840)
        self.assertEqual(len(generation), 840)
        self.assertTrue(all(row.get("promptTargetingVersion") == prompt_module.PROMPT_TARGETING_VERSION for row in assets))
        self.assertTrue(all(row.get("promptTargetingVersion") == prompt_module.PROMPT_TARGETING_VERSION for row in generation))


if __name__ == "__main__":
    unittest.main()
