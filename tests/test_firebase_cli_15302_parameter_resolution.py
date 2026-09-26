"""Local regression for Firebase CLI 15.30.2 parameter resolution."""

from __future__ import annotations

import os
import glob
import json
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "scripts" / "test_firebase_cli_15302_parameter_resolution.js"
PINNED_VERSION = "15.30.2"


def _pinned_cli_root() -> Path:
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm is not None, "npm is required to locate the pinned Firebase CLI cache"
    cache = subprocess.run(
        [npm, "config", "get", "cache"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout.strip()
    packages = sorted(
        Path(candidate)
        for candidate in glob.glob(
            str(Path(cache) / "_npx" / "*" / "node_modules" / "firebase-tools")
        )
    )
    for package in packages:
        metadata = json.loads((package / "package.json").read_text(encoding="utf-8"))
        if metadata.get("version") == PINNED_VERSION:
            return package
    raise AssertionError(
        "Firebase CLI 15.30.2 must be installed in npm's npx cache before this regression runs"
    )


def test_absent_dotenv_parameter_fails_before_source_default_prompt_path():
    cli_root = _pinned_cli_root()
    node = shutil.which("node.exe" if os.name == "nt" else "node")
    assert node is not None, "Node.js is required for the pinned Firebase CLI regression"
    package_bin = cli_root.parent / ".bin"
    completed = subprocess.run(
        [
            node,
            str(PROBE),
        ],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "CI": "1",
            "PATH": str(package_bin) + os.pathsep + os.environ.get("PATH", ""),
        },
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr[-4000:]
    assert completed.stdout.strip() == "PINNED_FIREBASE_CLI_PARAMETER_RESOLUTION_PASS"
