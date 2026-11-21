"""Repository file enumeration for whole-repo guard tests.

A guard that walks the working tree with ``Path.rglob`` also reads ignored
local artifacts (``.tmp/`` scratch worktrees, restored snapshots, caches).
Those are not part of the repository, so a stale copy there turned guards red
on a developer machine while CI — a clean checkout — stayed green. Guards about
"what the repository contains" must ask git instead.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def repository_files(repo_root: Path) -> list[Path] | None:
    """Tracked files plus untracked files that are not ignored.

    Returns ``None`` when git metadata is unavailable (for example a source
    archive), so the caller can fall back to walking the tree.
    """
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    paths = (
        repo_root / raw.decode("utf-8")
        for raw in completed.stdout.split(b"\0")
        if raw
    )
    # A tracked file deleted in the working tree is still listed by git.
    return sorted(path for path in paths if path.is_file())
