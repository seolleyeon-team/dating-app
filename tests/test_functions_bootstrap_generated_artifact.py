"""Fail-closed path-specific generated JSON artifact handling."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import functions_bootstrap_generated_artifact as generated  # noqa: E402


def _files(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / generated.SOURCE_RELATIVE
    output = tmp_path / generated.GENERATED_RELATIVE
    source.parent.mkdir(parents=True)
    output.parent.mkdir(parents=True)
    return source, output


def test_only_structurally_equal_exact_generated_file_is_removed(tmp_path):
    source, output = _files(tmp_path)
    source.write_text('{"enabled":true,"threshold":2}\n', encoding="utf-8")
    output.write_text('{"threshold":2,"enabled":true}\n', encoding="utf-8")
    unrelated = tmp_path / "functions" / "lib" / "unrelated.json"
    unrelated.write_text('{"preserve":true}\n', encoding="utf-8")

    assert generated.remove_generated_artifact(tmp_path) is True
    assert not output.exists()
    assert unrelated.is_file()


def test_mismatching_output_is_preserved_and_refused(tmp_path):
    source, output = _files(tmp_path)
    source.write_text(json.dumps({"approved": True}), encoding="utf-8")
    output.write_text(json.dumps({"user": "data"}), encoding="utf-8")

    with pytest.raises(generated.GeneratedArtifactError, match="SOURCE_MISMATCH"):
        generated.remove_generated_artifact(tmp_path)

    assert output.read_text(encoding="utf-8") == '{"user": "data"}'
