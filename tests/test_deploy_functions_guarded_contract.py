"""Tests for the exact Firebase dotenv/target contract used by the wrapper."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import deploy_functions_guarded_contract as contract  # noqa: E402


PROJECT = "seolleyeon-final"
FUNCTION = "cleanupAvatarMedia"


def _firebase_json(root: Path) -> Path:
    path = root / "firebase.json"
    path.write_text(
        json.dumps({"functions": [{"codebase": "default", "source": "functions"}]}),
        encoding="utf-8",
    )
    return path


def _root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    source = root / "functions"
    (source / "src").mkdir(parents=True)
    (source / "src" / "placeholder.ts").write_text("export {};\n", encoding="utf-8")
    _firebase_json(root)
    candidate = source / f".env.{PROJECT}"
    candidate.write_text(
        "RESEND_FROM_EMAIL=mail@example.com\n"
        "RESEND_REPLY_TO=reply@example.com\n",
        encoding="utf-8",
    )
    return root, candidate


def _validate(root: Path, candidate: Path, *functions: str, **kwargs):
    return contract.validate_deploy_env_contract(
        firebase_json=root / "firebase.json",
        project_id=PROJECT,
        env_file=candidate,
        functions=functions or (FUNCTION,),
        **kwargs,
    )


def test_the_guarded_file_is_the_exact_firebase_project_dotenv(tmp_path):
    root, candidate = _root(tmp_path)

    result = _validate(root, candidate)

    assert result.candidate == candidate.resolve()
    assert result.loaded_dotenv_files == (candidate.resolve(),)


def test_an_arbitrary_snapshot_outside_the_functions_source_is_refused(tmp_path):
    root, candidate = _root(tmp_path)
    snapshot = tmp_path / "live-derived.env"
    snapshot.write_bytes(candidate.read_bytes())

    with pytest.raises(contract.DeployContractError, match="NOT_BOUND"):
        _validate(root, snapshot)


@pytest.mark.parametrize("conflict", [".env", ".env.other-project", ".env.alias"])
def test_any_additional_deploy_dotenv_is_refused(tmp_path, conflict):
    root, candidate = _root(tmp_path)
    (candidate.parent / conflict).write_text("OTHER=value\n", encoding="utf-8")

    with pytest.raises(contract.DeployContractError, match="NOT_BOUND"):
        _validate(root, candidate)


def test_emulator_and_example_files_are_not_deploy_inputs(tmp_path):
    root, candidate = _root(tmp_path)
    (candidate.parent / ".env.local").write_text("LOCAL=value\n", encoding="utf-8")
    (candidate.parent / ".env.other.example").write_text(
        "EXAMPLE=value\n", encoding="utf-8"
    )

    assert _validate(root, candidate).loaded_dotenv_files == (candidate.resolve(),)


def test_hash_change_between_guard_and_deploy_is_refused(tmp_path):
    root, candidate = _root(tmp_path)
    expected = contract.sha256_file(candidate)
    candidate.write_text(candidate.read_text(encoding="utf-8") + "CHANGED=1\n", encoding="utf-8")

    with pytest.raises(contract.DeployContractError, match="CHANGED_AFTER_GUARD"):
        contract.require_unchanged(candidate, expected)


def test_hash_is_value_free_and_stable(tmp_path):
    root, candidate = _root(tmp_path)
    expected = hashlib.sha256(candidate.read_bytes()).hexdigest()

    assert contract.sha256_file(candidate) == expected
    assert "mail@example.com" not in contract.sha256_file(candidate)
    assert root.exists()


def test_validated_firebase_cli_version_is_single_contract_authority():
    assert contract.FIREBASE_TOOLS_VERSION == "15.30.2"
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "deploy_functions_guarded_contract.py"), "version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == contract.FIREBASE_TOOLS_VERSION


def test_guarded_wrapper_does_not_use_unvalidated_latest_cli_selector():
    wrapper = (SCRIPTS_DIR / "deploy_functions_guarded.sh").read_text(encoding="utf-8")

    assert "firebase-tools@latest" not in wrapper
    assert 'firebase-tools@$FIREBASE_TOOLS_VERSION' in wrapper


def test_multi_function_target_requires_explicit_opt_in():
    with pytest.raises(contract.DeployContractError, match="MULTI_FUNCTION"):
        contract.validate_function_targets([FUNCTION, "otherFunction"])

    assert contract.validate_function_targets(
        [FUNCTION, "otherFunction"], allow_multiple=True
    ) == (FUNCTION, "otherFunction")


@pytest.mark.parametrize("target", ["*", "functions", "functions:cleanupAvatarMedia", "cleanup/avatar"])
def test_full_or_non_exact_targets_are_refused(target):
    with pytest.raises(contract.DeployContractError):
        contract.validate_function_targets([target])


@pytest.mark.skipif(os.name == "nt", reason="shell wrapper integration runs in CI on POSIX")
def test_wrapper_deploys_only_the_explicit_function_with_the_same_dotenv(tmp_path):
    root, candidate = _root(tmp_path)
    scripts = root / "scripts"
    scripts.mkdir()
    for name in (
        "deploy_functions_guarded.sh",
        "deploy_functions_guarded_contract.py",
        "functions_env_regression_guard.py",
    ):
        (scripts / name).write_bytes((REPO_ROOT / "scripts" / name).read_bytes())

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gcloud = bin_dir / "gcloud"
    gcloud.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'spec': {'template': {'spec': {'containers': ["
        "{'env': ["
        "{'name': 'RESEND_FROM_EMAIL', 'value': 'mail@example.com'},"
        "{'name': 'RESEND_REPLY_TO', 'value': 'reply@example.com'},"
        "{'name': 'FIREBASE_CONFIG', 'value': '{}'},"
        "{'name': 'GCLOUD_PROJECT', 'value': 'seolleyeon-final'},"
        "{'name': 'EVENTARC_CLOUD_EVENT_SOURCE', 'value': 'source'},"
        "{'name': 'FUNCTION_REGION', 'value': 'asia-northeast3'},"
        "{'name': 'FUNCTION_TARGET', 'value': 'cleanupAvatarMedia'},"
        "{'name': 'LOG_EXECUTION_ID', 'value': 'true'}"
        "]}]}}}}))\n",
        encoding="utf-8",
    )
    gcloud.chmod(gcloud.stat().st_mode | stat.S_IXUSR)
    deploy_log = tmp_path / "npx.log"
    npx = bin_dir / "npx"
    npx.write_text(
        "#!/bin/sh\n"
        "if [ \"$3\" = \"--version\" ]; then\n"
        "  printf '15.30.2\\n'\n"
        "  exit 0\n"
        "fi\n"
        f"printf '%s\\n' \"$*\" >> '{deploy_log}'\n",
        encoding="utf-8",
    )
    npx.chmod(npx.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
    completed = subprocess.run(
        [
            "bash",
            str(scripts / "deploy_functions_guarded.sh"),
            "--project",
            PROJECT,
            "--region",
            "asia-northeast3",
            "--env-file",
            str(candidate.relative_to(root)),
            FUNCTION,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "ENV DEPLOY CONTRACT: PASS" in completed.stdout
    assert "ENV REGRESSION GUARD: PASS" in completed.stdout
    assert deploy_log.read_text(encoding="utf-8").strip() == (
        "-y firebase-tools@15.30.2 deploy --only functions:cleanupAvatarMedia "
        "--project seolleyeon-final --non-interactive"
    )

    dry_run = subprocess.run(
        [
            "bash",
            str(scripts / "deploy_functions_guarded.sh"),
            "--project",
            PROJECT,
            "--region",
            "asia-northeast3",
            "--env-file",
            str(candidate.relative_to(root)),
            "--dry-run",
            FUNCTION,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert dry_run.returncode == 0, dry_run.stdout + dry_run.stderr
    assert "dry-run: Firebase CLI was not invoked" in dry_run.stdout
    assert deploy_log.read_text(encoding="utf-8").strip() == (
        "-y firebase-tools@15.30.2 deploy --only functions:cleanupAvatarMedia "
        "--project seolleyeon-final --non-interactive"
    )


@pytest.mark.skipif(os.name == "nt", reason="shell wrapper integration runs in CI on POSIX")
def test_wrapper_refuses_firebase_cli_version_mismatch_before_deploy(tmp_path):
    root, candidate = _root(tmp_path)
    scripts = root / "scripts"
    scripts.mkdir()
    for name in (
        "deploy_functions_guarded.sh",
        "deploy_functions_guarded_contract.py",
    ):
        (scripts / name).write_bytes((REPO_ROOT / "scripts" / name).read_bytes())

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    deploy_log = tmp_path / "npx.log"
    npx = bin_dir / "npx"
    npx.write_text(
        "#!/bin/sh\n"
        "if [ \"$3\" = \"--version\" ]; then\n"
        "  printf '15.30.1\\n'\n"
        "  exit 0\n"
        "fi\n"
        f"printf '%s\\n' \"$*\" >> '{deploy_log}'\n",
        encoding="utf-8",
    )
    npx.chmod(npx.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
    completed = subprocess.run(
        [
            "bash",
            str(scripts / "deploy_functions_guarded.sh"),
            "--project",
            PROJECT,
            "--region",
            "asia-northeast3",
            "--env-file",
            str(candidate.relative_to(root)),
            FUNCTION,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "FIREBASE_CLI_VERSION_MISMATCH" in completed.stderr
    assert not deploy_log.exists()


@pytest.mark.skipif(os.name == "nt", reason="shell wrapper integration runs in CI on POSIX")
def test_wrapper_refuses_dotenv_mutation_after_guard(tmp_path):
    root, candidate = _root(tmp_path)
    scripts = root / "scripts"
    scripts.mkdir()
    for name in (
        "deploy_functions_guarded.sh",
        "deploy_functions_guarded_contract.py",
        "functions_env_regression_guard.py",
    ):
        (scripts / name).write_bytes((REPO_ROOT / "scripts" / name).read_bytes())

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gcloud = bin_dir / "gcloud"
    gcloud.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'spec': {'template': {'spec': {'containers': ["
        "{'env': ["
        "{'name': 'RESEND_FROM_EMAIL', 'value': 'mail@example.com'},"
        "{'name': 'RESEND_REPLY_TO', 'value': 'reply@example.com'},"
        "{'name': 'FIREBASE_CONFIG', 'value': '{}'},"
        "{'name': 'GCLOUD_PROJECT', 'value': 'seolleyeon-final'},"
        "{'name': 'EVENTARC_CLOUD_EVENT_SOURCE', 'value': 'source'},"
        "{'name': 'FUNCTION_REGION', 'value': 'asia-northeast3'},"
        "{'name': 'FUNCTION_TARGET', 'value': 'cleanupAvatarMedia'},"
        "{'name': 'LOG_EXECUTION_ID', 'value': 'true'}"
        "]}]}}}}))\n",
        encoding="utf-8",
    )
    gcloud.chmod(gcloud.stat().st_mode | stat.S_IXUSR)
    deploy_log = tmp_path / "npx.log"
    npx = bin_dir / "npx"
    npx.write_text(
        "#!/bin/sh\n"
        "if [ \"$3\" = \"--version\" ]; then\n"
        "  printf '15.30.2\\n'\n"
        "  exit 0\n"
        "fi\n"
        f"printf '%s\\n' \"$*\" >> '{deploy_log}'\n",
        encoding="utf-8",
    )
    npx.chmod(npx.stat().st_mode | stat.S_IXUSR)

    real_python = Path(sys.executable)
    mutation_sentinel = tmp_path / "mutated.once"
    fake_python = bin_dir / "python"
    fake_python.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"scripts/functions_env_regression_guard.py\" ] && "
        f"[ ! -e '{mutation_sentinel}' ]; then\n"
        f"  '{real_python}' \"$@\"\n"
        f"  printf 'CHANGED_AFTER_GUARD=1\\n' >> '{candidate}'\n"
        f"  touch '{mutation_sentinel}'\n"
        "  exit $?\n"
        "fi\n"
        f"exec '{real_python}' \"$@\"\n",
        encoding="utf-8",
    )
    fake_python.chmod(fake_python.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
    completed = subprocess.run(
        [
            "bash",
            str(scripts / "deploy_functions_guarded.sh"),
            "--project",
            PROJECT,
            "--region",
            "asia-northeast3",
            "--env-file",
            str(candidate.relative_to(root)),
            FUNCTION,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "GUARDED_ENV_CHANGED_AFTER_GUARD" in completed.stderr
    assert not deploy_log.exists()
