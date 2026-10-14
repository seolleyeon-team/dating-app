#!/usr/bin/env python3
"""Fail-closed contract checks for the guarded Firebase Functions wrapper.

Firebase CLI 15.30.2 loads deploy dotenv files from the Functions source in
this order: ``.env``, ``.env.<projectId>``, and (when a project alias is in
use) ``.env.<alias>``. The wrapper must guard the exact file Firebase will
load, not an arbitrary snapshot elsewhere on disk.

This module deliberately reports paths, key-free hashes, and contract errors;
it never parses or prints dotenv values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{4,29}$")
FUNCTION_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
# This is the single version authority for the audited Firebase CLI contract.
FIREBASE_TOOLS_VERSION = "15.30.2"


class DeployContractError(RuntimeError):
    """The guarded file or target cannot be proven safe for Firebase CLI."""


@dataclass(frozen=True)
class DeployEnvContract:
    project_id: str
    functions_source: Path
    candidate: Path
    loaded_dotenv_files: tuple[Path, ...]
    # Tracked key manifest the candidate was checked against (None when the
    # repository has no manifest for this project).
    key_manifest: Path | None = None


def dotenv_key_names(path: Path) -> set[str]:
    """Key names of a dotenv file. Values are never read into memory as such."""
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())
    return keys


def key_manifest_path(firebase_json: Path, project_id: str) -> Path:
    return (
        firebase_json.resolve().parent
        / "scripts"
        / f"functions_env_key_manifest.{project_id}.json"
    )


def validate_env_key_manifest(env_file: Path, manifest: Path) -> None:
    """Refuse a dotenv whose KEY set differs from the tracked manifest.

    `firebase deploy` writes the dotenv file to every targeted function, so an
    incomplete local file silently removes variables from production (the
    2026-09-08 incident; the 2026-10-13 P0-1 deploy found a 12-of-31-key file).
    The serving-revision guard catches that per function, but only after the
    operator already built a wrong file. This check is the earlier, static
    gate: the gitignored file must carry exactly the keys the repository says
    the codebase deploys with, and never a Secret Manager parameter as plain
    text.
    """
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise DeployContractError(
            f"ENV_KEY_MANIFEST_UNREADABLE: {manifest.name}: {error}"
        ) from error
    expected = data.get("plain_env_keys")
    secrets = data.get("secret_parameter_names", [])
    if not isinstance(expected, list) or not all(isinstance(k, str) for k in expected):
        raise DeployContractError(
            f"ENV_KEY_MANIFEST_MALFORMED: {manifest.name} has no plain_env_keys list"
        )
    expected_keys = set(expected)
    actual = dotenv_key_names(env_file)
    plaintext_secrets = sorted(actual & set(secrets))
    if plaintext_secrets:
        raise DeployContractError(
            "ENV_SECRET_AS_PLAINTEXT_REFUSED: "
            f"{', '.join(plaintext_secrets)} must stay in Secret Manager"
        )
    missing = sorted(expected_keys - actual)
    extra = sorted(actual - expected_keys)
    if missing or extra:
        raise DeployContractError(
            "ENV_KEY_MANIFEST_MISMATCH: dotenv keys differ from "
            f"{manifest.name} (missing: {', '.join(missing) or '-'}; "
            f"extra: {', '.join(extra) or '-'}). Restore the missing keys from "
            "the serving revisions, or update the manifest in the same reviewed "
            "change that intentionally adds or retires a variable."
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def functions_source_from_firebase_json(firebase_json: Path) -> Path:
    """Resolve the only configured Functions source for this wrapper."""

    config_path = firebase_json.resolve()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeployContractError(
            f"cannot read Firebase config {config_path}: {error}"
        ) from error

    functions = config.get("functions")
    if not isinstance(functions, list) or len(functions) != 1:
        raise DeployContractError(
            "GUARDED_ENV_NOT_BOUND_TO_FIREBASE_DEPLOY_ENV: expected exactly "
            "one Firebase Functions codebase"
        )
    source = functions[0].get("source") if isinstance(functions[0], dict) else None
    if not isinstance(source, str) or not source.strip():
        raise DeployContractError(
            "GUARDED_ENV_NOT_BOUND_TO_FIREBASE_DEPLOY_ENV: Functions source "
            "is missing"
        )
    return (config_path.parent / source).resolve()


def _actual_dotenv_files(functions_source: Path) -> tuple[Path, ...]:
    """Return the non-example dotenv files Firebase could load for deploy."""

    files: list[Path] = []
    for path in sorted(functions_source.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        name = path.name
        # Firebase CLI only loads .env.local for emulation. Example files are
        # documentation, not deployment inputs.
        if name == ".env.local" or name.endswith(".example"):
            continue
        if name == ".env" or name.startswith(".env."):
            files.append(path.resolve())
    return tuple(files)


def validate_function_targets(
    functions: Iterable[str], *, allow_multiple: bool = False
) -> tuple[str, ...]:
    targets = tuple(functions)
    if not targets:
        raise DeployContractError("at least one function name is required")
    if len(set(targets)) != len(targets):
        raise DeployContractError("duplicate function target is not allowed")
    if len(targets) > 1 and not allow_multiple:
        raise DeployContractError(
            "MULTI_FUNCTION_TARGET_REFUSED: pass --allow-multiple-functions "
            "to make a multi-function deployment explicit"
        )
    for function in targets:
        if function in {"all", "functions"} or not FUNCTION_NAME_PATTERN.fullmatch(function):
            raise DeployContractError(
                f"invalid exact function target {function!r}; wildcards and "
                "full-functions selectors are not allowed"
            )
    return targets


def validate_deploy_env_contract(
    *,
    firebase_json: Path,
    project_id: str,
    env_file: Path,
    functions: Iterable[str],
    allow_multiple_functions: bool = False,
) -> DeployEnvContract:
    if not PROJECT_ID_PATTERN.fullmatch(project_id):
        raise DeployContractError(
            f"project must be a concrete Firebase project id, got {project_id!r}"
        )
    validate_function_targets(
        functions, allow_multiple=allow_multiple_functions
    )

    source = functions_source_from_firebase_json(firebase_json)
    if not source.is_dir():
        raise DeployContractError(f"Functions source is not a directory: {source}")

    candidate = env_file.resolve()
    expected = (source / f".env.{project_id}").resolve()
    if candidate != expected:
        raise DeployContractError(
            "GUARDED_ENV_NOT_BOUND_TO_FIREBASE_DEPLOY_ENV: --env-file must be "
            f"the exact Firebase project dotenv path {expected}"
        )
    if candidate.is_symlink():
        raise DeployContractError(
            "GUARDED_ENV_NOT_BOUND_TO_FIREBASE_DEPLOY_ENV: symlinked dotenv "
            "files are not accepted"
        )
    if not candidate.is_file():
        raise DeployContractError(f"candidate dotenv file does not exist: {candidate}")

    loaded = _actual_dotenv_files(source)
    if loaded != (candidate,):
        names = ", ".join(path.name for path in loaded) or "<none>"
        raise DeployContractError(
            "GUARDED_ENV_NOT_BOUND_TO_FIREBASE_DEPLOY_ENV: Firebase CLI would "
            f"load dotenv files [{names}], not only {candidate.name}"
        )

    manifest = key_manifest_path(firebase_json, project_id)
    if manifest.is_file():
        validate_env_key_manifest(candidate, manifest)

    return DeployEnvContract(
        project_id=project_id,
        functions_source=source,
        candidate=candidate,
        loaded_dotenv_files=loaded,
        key_manifest=manifest if manifest.is_file() else None,
    )


def require_unchanged(path: Path, expected_sha256: str) -> None:
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise DeployContractError(
            "GUARDED_ENV_CHANGED_AFTER_GUARD: dotenv SHA-256 changed between "
            f"guard and deploy ({expected_sha256} -> {actual})"
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    source = subparsers.add_parser("source")
    source.add_argument("--firebase-json", type=Path, required=True)

    subparsers.add_parser("version")

    validate = subparsers.add_parser("validate")
    validate.add_argument("--firebase-json", type=Path, required=True)
    validate.add_argument("--project", required=True)
    validate.add_argument("--env-file", type=Path, required=True)
    validate.add_argument("--function", action="append", required=True)
    validate.add_argument("--allow-multiple-functions", action="store_true")

    digest = subparsers.add_parser("sha256")
    digest.add_argument("--file", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "source":
            print(functions_source_from_firebase_json(args.firebase_json))
            return 0
        if args.command == "version":
            print(FIREBASE_TOOLS_VERSION)
            return 0
        if args.command == "sha256":
            print(sha256_file(args.file.resolve()))
            return 0

        contract = validate_deploy_env_contract(
            firebase_json=args.firebase_json,
            project_id=args.project,
            env_file=args.env_file,
            functions=args.function,
            allow_multiple_functions=args.allow_multiple_functions,
        )
        print(
            "ENV DEPLOY CONTRACT: PASS "
            f"dotenv={contract.candidate.name} "
            f"sha256={sha256_file(contract.candidate)} "
            f"keys={len(dotenv_key_names(contract.candidate))} "
            f"manifest={contract.key_manifest.name if contract.key_manifest else 'none'}"
        )
        return 0
    except DeployContractError as error:
        print(f"ENV DEPLOY CONTRACT: FAIL\n  {error}")
        return 1
    except OSError as error:
        print(f"ENV DEPLOY CONTRACT: FAIL\n  {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
