"""Verify and optionally remove one proven TypeScript-generated JSON artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


SOURCE_RELATIVE = Path("functions/src/avatarQaHardRejectContract.json")
GENERATED_RELATIVE = Path("functions/lib/avatarQaHardRejectContract.json")


class GeneratedArtifactError(RuntimeError):
    """The exact build artifact cannot be proven to match its tracked source."""


def _scoped_path(repo_root: Path, relative_path: Path) -> Path:
    root = repo_root.resolve()
    candidate = root / relative_path
    current = root
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise GeneratedArtifactError("GENERATED_ARTIFACT_SYMLINK_REFUSED")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise GeneratedArtifactError("GENERATED_ARTIFACT_PATH_ESCAPE_REFUSED") from error
    return candidate


def verify_generated_artifact(repo_root: Path) -> Path | None:
    source = _scoped_path(repo_root, SOURCE_RELATIVE)
    generated = _scoped_path(repo_root, GENERATED_RELATIVE)
    if not generated.exists():
        return None
    if not source.is_file() or not generated.is_file():
        raise GeneratedArtifactError("GENERATED_ARTIFACT_SOURCE_OR_OUTPUT_MISSING")
    try:
        source_value = json.loads(source.read_text(encoding="utf-8"))
        generated_value = json.loads(generated.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GeneratedArtifactError("GENERATED_ARTIFACT_JSON_INVALID") from error
    if source_value != generated_value:
        raise GeneratedArtifactError("GENERATED_ARTIFACT_SOURCE_MISMATCH")
    return generated


def remove_generated_artifact(repo_root: Path) -> bool:
    generated = verify_generated_artifact(repo_root)
    if generated is None:
        return False
    generated.unlink()
    return True


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--remove", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.remove:
            removed = remove_generated_artifact(args.repo_root.resolve())
            print("GENERATED_ARTIFACT_REMOVED" if removed else "GENERATED_ARTIFACT_ABSENT")
        else:
            verified = verify_generated_artifact(args.repo_root.resolve())
            print("GENERATED_ARTIFACT_VERIFIED" if verified else "GENERATED_ARTIFACT_ABSENT")
        return 0
    except (GeneratedArtifactError, OSError) as error:
        print(f"GENERATED_ARTIFACT_GUARD: FAIL\n  {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
