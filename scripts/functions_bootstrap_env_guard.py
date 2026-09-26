#!/usr/bin/env python3
"""Fail-closed bootstrap guard for a Function with no serving revision.

This guard is intentionally separate from the normal serving-revision
environment guard.  It is only valid when the target's Cloud Run service is
absent and the Cloud Functions object is in an explicitly approved recovery
state.  It never creates a dummy service or treats historical metadata as live
environment authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from deploy_functions_guarded_contract import FIREBASE_TOOLS_VERSION
from functions_env_regression_guard import GuardError, parse_env_file
from functions_codebase_parameter_contract import (
    ParameterContractError,
    expected_candidate_keys,
    validate_discovered_parameters,
    validate_live_parameter_authority,
)
from functions_source_env_contract import (
    ENV_KEY_PATTERN,
    PLATFORM_MANAGED_KEYS,
    SourceContractError,
    analyze_source_env_contract,
)
from functions_bootstrap_generated_artifact import (
    GeneratedArtifactError,
    verify_generated_artifact,
)


BOOTSTRAP_CONTRACT_VERSION = 2
BOOTSTRAP_REASON = "no_serving_revision_recovery"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
FUNCTION_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
PARAMETER_AUTHORITY_FUNCTIONS = frozenset(
    {
        "sendStudentVerificationEmail",
        "appStoreServerNotifications",
        "cleanupAvatarMedia",
    }
)


class BootstrapContractError(RuntimeError):
    """The narrow no-serving-revision contract cannot be proven safe."""


@dataclass(frozen=True)
class BootstrapManifest:
    contract_version: int
    reason: str
    function: str
    project: str
    region: str
    source_tree_sha: str
    expected_plain_env_keys: frozenset[str]
    expected_codebase_parameter_keys: frozenset[str]
    expected_codebase_parameter_types: Mapping[str, str]
    expected_codebase_secret_parameter_names: frozenset[str]
    expected_secret_bindings: frozenset[str]
    parameter_authority_functions: tuple[str, ...]
    source_entry: str
    source_export: str
    allowed_function_states: frozenset[str]
    allow_absent_function: bool


def _require_string(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise BootstrapContractError(f"manifest field {key!r} must be a non-empty string")
    return value


def _require_key_set(data: Mapping[str, Any], key: str) -> frozenset[str]:
    value = data.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise BootstrapContractError(f"manifest field {key!r} must be a string list")
    if len(set(value)) != len(value):
        raise BootstrapContractError(f"manifest field {key!r} contains duplicates")
    for item in value:
        if not ENV_KEY_PATTERN.fullmatch(item):
            raise BootstrapContractError(f"manifest field {key!r} has invalid key {item!r}")
        if item in PLATFORM_MANAGED_KEYS:
            raise BootstrapContractError(
                f"manifest field {key!r} contains platform-managed key {item!r}"
            )
    return frozenset(value)


def _optional_key_set(data: Mapping[str, Any], key: str) -> frozenset[str]:
    if key not in data:
        return frozenset()
    return _require_key_set(data, key)


def _require_parameter_type_map(data: Mapping[str, Any], key: str) -> dict[str, str]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise BootstrapContractError(f"manifest field {key!r} must be a string map")
    validated_keys = _require_key_set(
        {key: list(value)}, key
    )
    if any(not isinstance(parameter_type, str) or not parameter_type.strip() for parameter_type in value.values()):
        raise BootstrapContractError(f"manifest field {key!r} must map names to strings")
    if any(parameter_type.casefold() == "secret" for parameter_type in value.values()):
        raise BootstrapContractError(
            f"manifest field {key!r} cannot classify secret parameters as dotenv values"
        )
    return {name: value[name] for name in validated_keys}


def _require_function_list(data: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = data.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise BootstrapContractError(f"manifest field {key!r} must be a string list")
    if len(set(value)) != len(value):
        raise BootstrapContractError(f"manifest field {key!r} contains duplicates")
    if any(not FUNCTION_PATTERN.fullmatch(item) for item in value):
        raise BootstrapContractError(f"manifest field {key!r} contains an invalid function name")
    return tuple(value)


def load_manifest(path: Path) -> BootstrapManifest:
    try:
        data = json.loads(path.resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BootstrapContractError(f"cannot read bootstrap manifest {path}: {error}") from error
    if not isinstance(data, dict):
        raise BootstrapContractError("bootstrap manifest must be a JSON object")

    version = data.get("contract_version")
    if version != BOOTSTRAP_CONTRACT_VERSION:
        raise BootstrapContractError(
            f"unsupported bootstrap contract_version {version!r}; expected {BOOTSTRAP_CONTRACT_VERSION}"
        )
    reason = _require_string(data, "reason")
    if reason != BOOTSTRAP_REASON:
        raise BootstrapContractError(f"unexpected bootstrap reason {reason!r}")

    function = _require_string(data, "function")
    if not FUNCTION_PATTERN.fullmatch(function):
        raise BootstrapContractError(f"invalid manifest function {function!r}")
    project = _require_string(data, "project")
    region = _require_string(data, "region")
    source_tree_sha = _require_string(data, "source_tree_sha").lower()
    if not SHA_PATTERN.fullmatch(source_tree_sha):
        raise BootstrapContractError(
            "manifest source_tree_sha must be a 40-character Git tree object SHA-1"
        )

    allowed_states_raw = data.get("allowed_function_states", ["FAILED"])
    if not isinstance(allowed_states_raw, list) or any(
        not isinstance(item, str) for item in allowed_states_raw
    ):
        raise BootstrapContractError("manifest allowed_function_states must be a string list")
    allowed_states = frozenset(item.upper() for item in allowed_states_raw)
    if not allowed_states or not allowed_states <= {"FAILED", "ABSENT"}:
        raise BootstrapContractError(
            "manifest allowed_function_states may contain only FAILED or ABSENT"
        )
    allow_absent = data.get("allow_absent_function", False)
    if not isinstance(allow_absent, bool):
        raise BootstrapContractError("manifest allow_absent_function must be boolean")
    if "ABSENT" in allowed_states and not allow_absent:
        raise BootstrapContractError(
            "ABSENT function state requires allow_absent_function=true"
        )

    expected_codebase_parameter_keys = _optional_key_set(
        data, "expected_codebase_parameter_keys"
    )
    expected_codebase_parameter_types = (
        _require_parameter_type_map(data, "expected_codebase_parameter_types")
        if "expected_codebase_parameter_types" in data
        else {}
    )
    expected_codebase_secret_parameter_names = _optional_key_set(
        data, "expected_codebase_secret_parameter_names"
    )
    parameter_authority_functions = _require_function_list(
        data, "parameter_authority_functions"
    )
    if expected_codebase_parameter_keys and not parameter_authority_functions:
        raise BootstrapContractError(
            "manifest parameter_authority_functions are required for codebase parameters"
        )
    if not expected_codebase_parameter_keys and parameter_authority_functions:
        raise BootstrapContractError(
            "manifest parameter_authority_functions require codebase parameter keys"
        )
    if (
        expected_codebase_parameter_keys
        and frozenset(parameter_authority_functions) != PARAMETER_AUTHORITY_FUNCTIONS
    ):
        raise BootstrapContractError(
            "manifest parameter_authority_functions do not match approved live authorities"
        )
    if expected_codebase_parameter_types.keys() != expected_codebase_parameter_keys:
        raise BootstrapContractError(
            "manifest expected_codebase_parameter_types must describe every codebase parameter key"
        )
    if expected_codebase_secret_parameter_names & expected_codebase_parameter_keys:
        raise BootstrapContractError(
            "manifest secret parameter names cannot be codebase dotenv keys"
        )

    return BootstrapManifest(
        contract_version=version,
        reason=reason,
        function=function,
        project=project,
        region=region,
        source_tree_sha=source_tree_sha,
        expected_plain_env_keys=_require_key_set(data, "expected_plain_env_keys"),
        expected_codebase_parameter_keys=expected_codebase_parameter_keys,
        expected_codebase_parameter_types=expected_codebase_parameter_types,
        expected_codebase_secret_parameter_names=expected_codebase_secret_parameter_names,
        expected_secret_bindings=_require_key_set(data, "expected_secret_bindings"),
        parameter_authority_functions=parameter_authority_functions,
        source_entry=_require_string(data, "source_entry"),
        source_export=_require_string(data, "source_export"),
        allowed_function_states=allowed_states,
        allow_absent_function=allow_absent,
    )


def validate_firebase_cli_version(observed: str) -> None:
    if observed.strip() != FIREBASE_TOOLS_VERSION:
        raise BootstrapContractError(
            f"FIREBASE_CLI_VERSION_MISMATCH: expected {FIREBASE_TOOLS_VERSION}, got {observed.strip()}"
        )


def validate_bootstrap_invocation(
    *,
    functions: Sequence[str],
    allow_multiple_functions: bool = False,
    allow_authorizations: Sequence[str] = (),
) -> None:
    if allow_multiple_functions:
        raise BootstrapContractError(
            "BOOTSTRAP_MULTI_FUNCTION_REFUSED: bootstrap mode is exact one function only"
        )
    if len(functions) != 1:
        raise BootstrapContractError(
            "BOOTSTRAP_EXACT_TARGET_REQUIRED: bootstrap mode requires exactly one function"
        )
    if not FUNCTION_PATTERN.fullmatch(functions[0]):
        raise BootstrapContractError(f"invalid exact bootstrap target {functions[0]!r}")
    if allow_authorizations:
        raise BootstrapContractError(
            "BOOTSTRAP_ALLOW_FLAG_REFUSED: --allow-* flags are not valid in bootstrap mode"
        )


def _gcloud_executable() -> str:
    executable = shutil.which("gcloud")
    if executable is None:
        raise BootstrapContractError("gcloud is not on PATH")
    return executable


def _run_gcloud_json(args: Sequence[str], *, what: str) -> tuple[object | None, str]:
    completed = subprocess.run(
        [_gcloud_executable(), *args],
        capture_output=True,
        shell=False,
        env={**dict(__import__("os").environ), "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    stdout = completed.stdout.decode("utf-8", errors="backslashreplace")
    stderr = completed.stderr.decode("utf-8", errors="backslashreplace")
    if completed.returncode != 0:
        detail = stderr.strip() or stdout.strip()
        return None, detail[:500]
    try:
        return json.loads(stdout), ""
    except json.JSONDecodeError as error:
        raise BootstrapContractError(f"{what}: gcloud did not return JSON ({error})") from error


def describe_function_state(function: str, project: str, region: str) -> str:
    described, detail = _run_gcloud_json(
        [
            "functions",
            "describe",
            function,
            "--gen2",
            f"--region={region}",
            f"--project={project}",
            "--format=json",
        ],
        what=function,
    )
    if described is None:
        if "not found" in detail.lower() or "not_found" in detail.lower():
            return "ABSENT"
        raise BootstrapContractError(f"cannot describe function {function}: {detail}")
    if not isinstance(described, dict):
        raise BootstrapContractError(f"function {function}: unexpected gcloud JSON shape")
    state = described.get("state")
    if not isinstance(state, str) or not state.strip():
        raise BootstrapContractError(f"function {function}: state is missing")
    return state.upper()


def read_live_codebase_parameter_authority(
    function: str,
    project: str,
    region: str,
    expected_keys: frozenset[str],
) -> Mapping[str, str]:
    """Read only selected non-secret environment values from an ACTIVE function."""

    described, detail = _run_gcloud_json(
        [
            "functions",
            "describe",
            function,
            "--gen2",
            f"--region={region}",
            f"--project={project}",
            "--format=json",
        ],
        what=function,
    )
    if described is None:
        raise BootstrapContractError(
            f"cannot read parameter authority {function}: {detail}"
        )
    if not isinstance(described, dict):
        raise BootstrapContractError(
            f"parameter authority {function}: unexpected gcloud JSON shape"
        )
    state = described.get("state")
    if not isinstance(state, str) or state.upper() != "ACTIVE":
        observed = state.upper() if isinstance(state, str) else "MISSING"
        raise BootstrapContractError(
            f"PARAMETER_AUTHORITY_NOT_ACTIVE: {function}: {observed}"
        )
    service_config = described.get("serviceConfig")
    if not isinstance(service_config, dict):
        raise BootstrapContractError(
            f"PARAMETER_AUTHORITY_CONFIG_MISSING: {function}"
        )
    environment = service_config.get("environmentVariables", {})
    if not isinstance(environment, dict):
        raise BootstrapContractError(
            f"PARAMETER_AUTHORITY_ENVIRONMENT_INVALID: {function}"
        )
    selected: dict[str, str] = {}
    for key in expected_keys:
        if key in environment:
            value = environment[key]
            if not isinstance(value, str):
                raise BootstrapContractError(
                    f"PARAMETER_AUTHORITY_VALUE_INVALID: {function}: {key}"
                )
            selected[key] = value
    return selected


def assert_no_serving_service(function: str, project: str, region: str) -> None:
    service = function.lower()
    described, detail = _run_gcloud_json(
        [
            "run",
            "services",
            "describe",
            service,
            f"--project={project}",
            f"--region={region}",
            "--format=json",
        ],
        what=service,
    )
    if described is not None:
        raise BootstrapContractError(
            f"SERVING_ENV_AUTHORITY_EXISTS: Cloud Run service {service} exists; bootstrap refused"
        )
    lowered = detail.lower()
    if not any(marker in lowered for marker in ("not found", "not_found", "cannot find service")):
        raise BootstrapContractError(
            f"cannot establish NO_SERVING_ENV_AUTHORITY for {service}: {detail}"
        )


def _fresh_git_sha(repo_root: Path, ref: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise BootstrapContractError(f"cannot resolve fresh authority {ref}: {completed.stderr.strip()}")
    return completed.stdout.strip().lower()


def _git_tree_sha(repo_root: Path, ref: str, tree_path: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{ref}:{tree_path}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise BootstrapContractError(
            f"cannot resolve Functions source tree {tree_path!r} at {ref}: {completed.stderr.strip()}"
        )
    tree_sha = completed.stdout.strip().lower()
    if not SHA_PATTERN.fullmatch(tree_sha):
        raise BootstrapContractError(
            f"resolved Functions source tree at {ref} is not a 40-character Git tree SHA-1"
        )
    return tree_sha


def _require_clean_source(repo_root: Path, *, allow_exact_generated_artifact: bool = False) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise BootstrapContractError(f"cannot inspect source worktree: {completed.stderr.strip()}")
    changes = completed.stdout.splitlines()
    if not changes:
        return
    if allow_exact_generated_artifact and changes == [
        "?? functions/lib/avatarQaHardRejectContract.json"
    ]:
        try:
            verify_generated_artifact(repo_root)
            return
        except GeneratedArtifactError as error:
            raise BootstrapContractError(str(error)) from error
    raise BootstrapContractError(
        "SOURCE_WORKTREE_NOT_CLEAN: bootstrap source must be the clean fresh main checkout"
    )


def _require_deploy_source_matches_ref(
    repo_root: Path,
    reference: str,
    *,
    allow_exact_generated_artifact: bool = False,
) -> None:
    """Allow a committed guard implementation while pinning deployed source."""

    completed = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--quiet", reference, "--", "functions"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise BootstrapContractError(
            "SOURCE_AUTHORITY_MISMATCH: the deployable Functions tree differs from fresh github/main"
        )

    untracked = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            "functions",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if untracked.returncode != 0:
        raise BootstrapContractError(
            f"cannot inspect untracked Functions source files: {untracked.stderr.strip()}"
        )
    untracked_paths = untracked.stdout.splitlines()
    if not untracked_paths:
        return
    if allow_exact_generated_artifact and untracked_paths == [
        "functions/lib/avatarQaHardRejectContract.json"
    ]:
        try:
            verify_generated_artifact(repo_root)
            return
        except GeneratedArtifactError as error:
            raise BootstrapContractError(str(error)) from error
    raise BootstrapContractError(
        "SOURCE_AUTHORITY_MISMATCH: untracked deployable Functions files are present"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_bootstrap_contract(
    *,
    repo_root: Path,
    manifest_path: Path,
    project: str,
    region: str,
    function: str,
    env_file: Path,
    source_dir: Path,
    firebase_cli_version: str,
    discovered_build_params: Mapping[str, Any] | None = None,
    prebuild_source_only: bool = False,
) -> BootstrapManifest:
    """Validate every bootstrap invariant without invoking Firebase deploy."""

    manifest = load_manifest(manifest_path)
    validate_firebase_cli_version(firebase_cli_version)
    validate_bootstrap_invocation(functions=[function])

    if manifest.function != function:
        raise BootstrapContractError(
            f"BOOTSTRAP_FUNCTION_MISMATCH: manifest={manifest.function}, target={function}"
        )
    if manifest.project != project:
        raise BootstrapContractError(
            f"BOOTSTRAP_PROJECT_MISMATCH: manifest={manifest.project}, target={project}"
        )
    if manifest.region != region:
        raise BootstrapContractError(
            f"BOOTSTRAP_REGION_MISMATCH: manifest={manifest.region}, target={region}"
        )

    _require_clean_source(
        repo_root,
        allow_exact_generated_artifact=bool(manifest.expected_codebase_parameter_keys),
    )
    fresh_main = _fresh_git_sha(repo_root, "github/main")
    fresh_main_tree_sha = _git_tree_sha(repo_root, "github/main", "functions")
    head_tree_sha = _git_tree_sha(repo_root, "HEAD", "functions")
    if manifest.source_tree_sha != fresh_main_tree_sha or head_tree_sha != fresh_main_tree_sha:
        raise BootstrapContractError(
            "BOOTSTRAP_SOURCE_TREE_SHA_MISMATCH: manifest and checkout Functions trees must equal fresh github/main"
        )
    _require_deploy_source_matches_ref(
        repo_root,
        fresh_main,
        allow_exact_generated_artifact=bool(manifest.expected_codebase_parameter_keys),
    )

    try:
        source_contract = analyze_source_env_contract(
            source_dir=source_dir,
            entry_relative_path=manifest.source_entry,
            export_name=manifest.source_export,
        )
    except SourceContractError as error:
        raise BootstrapContractError(str(error)) from error

    if source_contract.unknown_reads:
        details = ", ".join(
            f"{read.module}:{read.line}" for read in source_contract.unknown_reads
        )
        raise BootstrapContractError(f"UNKNOWN_ENV_READ: {details}")
    if source_contract.custom_plain_env_keys != manifest.expected_plain_env_keys:
        raise BootstrapContractError(
            "BOOTSTRAP_SOURCE_ENV_MISMATCH: expected plain env keys do not match source closure"
        )
    if set(source_contract.secret_bindings) != set(manifest.expected_secret_bindings):
        raise BootstrapContractError(
            "BOOTSTRAP_SECRET_CONTRACT_MISMATCH: expected secret bindings do not match source closure"
        )

    if prebuild_source_only:
        if discovered_build_params is not None:
            raise BootstrapContractError(
                "BOOTSTRAP_SOURCE_PREFLIGHT_DISCOVERY_REFUSED"
            )
        print("BOOTSTRAP_SOURCE_PREFLIGHT_PASS")
        return manifest

    candidate_path = env_file.resolve()
    if not candidate_path.is_file():
        raise BootstrapContractError(f"candidate dotenv file does not exist: {candidate_path}")
    candidate = parse_env_file(candidate_path.read_text(encoding="utf-8"))
    candidate_keys = frozenset(candidate)
    if candidate_keys & PLATFORM_MANAGED_KEYS:
        raise BootstrapContractError("BOOTSTRAP_PLATFORM_ENV_REFUSED: dotenv contains platform-managed key")
    try:
        expected_candidates = expected_candidate_keys(
            source_contract.custom_plain_env_keys,
            manifest.expected_codebase_parameter_keys,
        )
    except ParameterContractError as error:
        raise BootstrapContractError(str(error)) from error
    if candidate_keys != expected_candidates:
        raise BootstrapContractError(
            "BOOTSTRAP_CANDIDATE_ENV_MISMATCH: candidate dotenv key set does not match source and codebase parameter contract"
        )

    state = describe_function_state(function, project, region)
    if state not in manifest.allowed_function_states:
        raise BootstrapContractError(
            f"BOOTSTRAP_FUNCTION_STATE_REFUSED: observed={state}, allowed={sorted(manifest.allowed_function_states)}"
        )
    if state == "ABSENT" and not manifest.allow_absent_function:
        raise BootstrapContractError("BOOTSTRAP_ABSENT_FUNCTION_REFUSED")
    assert_no_serving_service(function, project, region)

    if manifest.expected_codebase_parameter_keys:
        if not isinstance(discovered_build_params, Mapping):
            raise BootstrapContractError(
                "BOOTSTRAP_PARAMETER_DISCOVERY_REQUIRED: discovered Build metadata is missing"
            )
        if discovered_build_params.get("contractVersion") != 1:
            raise BootstrapContractError(
                "BOOTSTRAP_PARAMETER_DISCOVERY_VERSION_MISMATCH"
            )
        if discovered_build_params.get("firebaseToolsVersion") != FIREBASE_TOOLS_VERSION:
            raise BootstrapContractError(
                "BOOTSTRAP_PARAMETER_DISCOVERY_CLI_MISMATCH"
            )
        parameters = discovered_build_params.get("parameters")
        if not isinstance(parameters, list):
            raise BootstrapContractError(
                "BOOTSTRAP_PARAMETER_DISCOVERY_SHAPE_INVALID"
            )
        if discovered_build_params.get("parameterCount") != len(parameters):
            raise BootstrapContractError(
                "BOOTSTRAP_PARAMETER_DISCOVERY_COUNT_MISMATCH"
            )
        observed_secret_count = sum(
            1
            for parameter in parameters
            if isinstance(parameter, dict)
            and isinstance(parameter.get("type"), str)
            and parameter["type"].casefold() == "secret"
        )
        if discovered_build_params.get("secretParameterCount") != observed_secret_count:
            raise BootstrapContractError(
                "BOOTSTRAP_PARAMETER_DISCOVERY_SECRET_COUNT_MISMATCH"
            )
        try:
            validate_discovered_parameters(
                parameters,
                manifest.expected_codebase_parameter_keys,
                expected_types=manifest.expected_codebase_parameter_types,
                expected_secret_keys=manifest.expected_codebase_secret_parameter_names,
            )
            authority_values = {
                authority: read_live_codebase_parameter_authority(
                    authority,
                    project,
                    region,
                    expected_candidates,
                )
                for authority in manifest.parameter_authority_functions
            }
            validate_live_parameter_authority(
                candidate_values=candidate,
                authority_values_by_function=authority_values,
                authority_functions=manifest.parameter_authority_functions,
                parameters=parameters,
                source_plain_env_keys=source_contract.custom_plain_env_keys,
            )
        except ParameterContractError as error:
            raise BootstrapContractError(str(error)) from error

    print("NO_SERVING_ENV_AUTHORITY")
    print(f"bootstrap function: {function}")
    print(f"bootstrap source tree sha: {manifest.source_tree_sha}")
    print(f"bootstrap modules: {len(source_contract.modules)}")
    print(f"bootstrap custom plain env keys: {len(manifest.expected_plain_env_keys)}")
    print(f"bootstrap secret bindings: {len(manifest.expected_secret_bindings)}")
    print(f"bootstrap dotenv sha256: {_sha256_file(candidate_path)}")
    print("BOOTSTRAP_DEPLOY_CONTRACT_PASS")
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--function", required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--firebase-cli-version", required=True)
    parser.add_argument("--discovered-build-params", type=Path)
    parser.add_argument("--prebuild-source-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        discovered_build_params = None
        if args.discovered_build_params is not None:
            try:
                discovered_build_params = json.loads(
                    args.discovered_build_params.resolve().read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as error:
                raise BootstrapContractError(
                    f"cannot read discovered Build parameters: {error}"
                ) from error
        validate_bootstrap_contract(
            repo_root=args.repo_root,
            manifest_path=args.manifest,
            project=args.project,
            region=args.region,
            function=args.function,
            env_file=args.env_file,
            source_dir=args.source_dir,
            firebase_cli_version=args.firebase_cli_version,
            discovered_build_params=discovered_build_params,
            prebuild_source_only=args.prebuild_source_only,
        )
        return 0
    except (BootstrapContractError, GuardError, ParameterContractError) as error:
        print(f"BOOTSTRAP ENV CONTRACT: FAIL\n  {error}")
        return 1
    except OSError as error:
        print(f"BOOTSTRAP ENV CONTRACT: FAIL\n  {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
