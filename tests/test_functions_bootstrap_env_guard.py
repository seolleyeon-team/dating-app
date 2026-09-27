"""Tests for the narrow no-serving-revision bootstrap contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import functions_bootstrap_env_guard as bootstrap  # noqa: E402
import deploy_functions_guarded_contract as deploy_contract  # noqa: E402
import functions_env_regression_guard as normal_guard  # noqa: E402


PROJECT = "seolleyeon-final"
REGION = "asia-northeast3"
FUNCTION = "syncMeetingIcebreakerFromPromise"
MAIN_SHA = "634b149bdf581addf2be741823b494986dbb965c"
NEXT_MAIN_SHA = "1111111111111111111111111111111111111111"
SOURCE_TREE_SHA = "3e6e2519b55015d3c499c1c3563ada335cf6d7eb"
RECREATE_MANIFEST = SCRIPTS_DIR / "functions_bootstrap_recreate_manifest.json"
CODEBASE_PARAMETER_KEYS = [
    "APPLE_IAP_APPLE_ID",
    "APPLE_IAP_BUNDLE_ID",
    "RESEND_FROM_EMAIL",
    "RESEND_REPLY_TO",
]
CODEBASE_PARAMETER_VALUES = {
    "APPLE_IAP_APPLE_ID": "94727223",
    "APPLE_IAP_BUNDLE_ID": "com.seolleyeon.app",
    "RESEND_FROM_EMAIL": "synthetic-sender@example.invalid",
    "RESEND_REPLY_TO": "synthetic-reply@example.invalid",
}
CODEBASE_SECRET_NAMES = [
    "PLAY_REVIEW_LOGIN_ID",
    "PLAY_REVIEW_PASSWORD_SCRYPT",
    "PLAY_REVIEW_FIREBASE_UID",
    "PLAY_REVIEW_ENABLED",
    "PORTONE_API_SECRET",
    "RESEND_API_KEY",
]
PARAMETER_AUTHORITIES = [
    "sendStudentVerificationEmail",
    "appStoreServerNotifications",
    "cleanupAvatarMedia",
]


def _fixture(
    tmp_path: Path,
    *,
    source: str = "export const syncMeetingIcebreakerFromPromise = 1;\n",
    plain_keys: list[str] | None = None,
    secret_keys: list[str] | None = None,
    candidate: str = "",
    function: str = FUNCTION,
    project: str = PROJECT,
    region: str = REGION,
    source_tree_sha: str = SOURCE_TREE_SHA,
    codebase_keys: list[str] | None = None,
    codebase_types: dict[str, str] | None = None,
    codebase_secret_names: list[str] | None = None,
    parameter_authority_functions: list[str] | None = None,
    allowed_function_states: list[str] | None = None,
    allow_absent_function: bool = False,
):
    root = tmp_path / "repo"
    source_dir = root / "functions" / "src"
    source_dir.mkdir(parents=True)
    (source_dir / "entry.ts").write_text(source, encoding="utf-8")
    env_file = root / "functions" / f".env.{PROJECT}"
    env_file.write_text(candidate, encoding="utf-8")
    manifest = root / "manifest.json"
    manifest_data = {
        "contract_version": 2,
        "reason": "no_serving_revision_recovery",
        "function": function,
        "project": project,
        "region": region,
        "source_tree_sha": source_tree_sha,
        "expected_plain_env_keys": plain_keys or [],
        "expected_secret_bindings": secret_keys or [],
        "source_entry": "entry.ts",
        "source_export": FUNCTION,
        "allowed_function_states": allowed_function_states or ["FAILED"],
        "allow_absent_function": allow_absent_function,
    }
    if codebase_keys is not None:
        manifest_data["expected_codebase_parameter_keys"] = codebase_keys
        manifest_data["expected_codebase_parameter_types"] = codebase_types or {
            name: "string" for name in codebase_keys
        }
        manifest_data["expected_codebase_secret_parameter_names"] = (
            codebase_secret_names or []
        )
    if parameter_authority_functions is not None:
        manifest_data["parameter_authority_functions"] = parameter_authority_functions
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    return root, manifest, env_file, source_dir


def _codebase_discovery(*, secret_names: list[str] | None = None):
    secrets = secret_names or CODEBASE_SECRET_NAMES
    return {
        "contractVersion": 1,
        "firebaseToolsVersion": "15.30.2",
        "parameterCount": len(CODEBASE_PARAMETER_KEYS) + len(secrets),
        "secretParameterCount": len(secrets),
        "parameters": [
            {
                "name": "APPLE_IAP_APPLE_ID",
                "type": "string",
                "default": CODEBASE_PARAMETER_VALUES["APPLE_IAP_APPLE_ID"],
            },
            {
                "name": "APPLE_IAP_BUNDLE_ID",
                "type": "string",
                "default": CODEBASE_PARAMETER_VALUES["APPLE_IAP_BUNDLE_ID"],
            },
            {"name": "RESEND_FROM_EMAIL", "type": "string", "default": ""},
            {"name": "RESEND_REPLY_TO", "type": "string", "default": ""},
            *({"name": name, "type": "secret"} for name in secrets),
        ],
    }


def _recreate_fixture(tmp_path: Path, **overrides):
    candidate = "".join(
        f"{key}={value}\n" for key, value in CODEBASE_PARAMETER_VALUES.items()
    )
    options = {
        "candidate": candidate,
        "codebase_keys": CODEBASE_PARAMETER_KEYS,
        "codebase_secret_names": CODEBASE_SECRET_NAMES,
        "parameter_authority_functions": PARAMETER_AUTHORITIES,
        "allowed_function_states": ["ABSENT"],
        "allow_absent_function": True,
    }
    options.update(overrides)
    return _fixture(tmp_path, **options)


def _stub_recreate_live_authority(
    monkeypatch, *, function_state: str = "ABSENT", serving_service_exists: bool = False
):
    _stub_live_authority(monkeypatch)
    monkeypatch.setattr(
        bootstrap, "describe_function_state", lambda *args: function_state
    )
    if serving_service_exists:
        monkeypatch.setattr(
            bootstrap,
            "assert_no_serving_service",
            lambda *args: (_ for _ in ()).throw(
                bootstrap.BootstrapContractError("SERVING_ENV_AUTHORITY_EXISTS")
            ),
        )
    else:
        monkeypatch.setattr(bootstrap, "assert_no_serving_service", lambda *args: None)
    monkeypatch.setattr(
        bootstrap,
        "read_live_codebase_parameter_authority",
        lambda function, project, region, expected: CODEBASE_PARAMETER_VALUES,
    )


def _validate_recreate(monkeypatch, fixture, *, discovered_build_params=None, **live):
    root, manifest, env_file, source_dir = fixture
    _stub_recreate_live_authority(monkeypatch, **live)
    return bootstrap.validate_bootstrap_contract(
        repo_root=root,
        manifest_path=manifest,
        project=PROJECT,
        region=REGION,
        function=FUNCTION,
        env_file=env_file,
        source_dir=source_dir,
        firebase_cli_version="15.30.2",
        discovered_build_params=discovered_build_params or _codebase_discovery(),
    )


def _manifest_seen_in_recent_history(path: Path) -> bool:
    relative = path.relative_to(REPO_ROOT).as_posix()
    commits = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-list", "--max-count=20", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if commits.returncode != 0:
        return False
    for commit in commits.stdout.splitlines()[1:]:
        exists = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{commit}:{relative}"],
            check=False,
            capture_output=True,
            text=True,
        )
        if exists.returncode == 0:
            return True
    return False


def _stub_live_authority(monkeypatch):
    monkeypatch.setattr(
        bootstrap, "_require_clean_source", lambda root, **kwargs: None
    )
    monkeypatch.setattr(bootstrap, "_fresh_git_sha", lambda root, ref: MAIN_SHA)
    monkeypatch.setattr(
        bootstrap, "_git_tree_sha", lambda root, ref, path: SOURCE_TREE_SHA
    )
    monkeypatch.setattr(
        bootstrap,
        "_require_deploy_source_matches_ref",
        lambda root, ref, **kwargs: None,
    )
    monkeypatch.setattr(bootstrap, "describe_function_state", lambda *args: "FAILED")
    monkeypatch.setattr(bootstrap, "assert_no_serving_service", lambda *args: None)


def _validate(monkeypatch, fixture, *, discovered_build_params=None):
    root, manifest, env_file, source_dir = fixture
    _stub_live_authority(monkeypatch)
    return bootstrap.validate_bootstrap_contract(
        repo_root=root,
        manifest_path=manifest,
        project=PROJECT,
        region=REGION,
        function=FUNCTION,
        env_file=env_file,
        source_dir=source_dir,
        firebase_cli_version="15.30.2",
        discovered_build_params=discovered_build_params,
    )


def test_no_service_normal_mode_remains_fail_closed(monkeypatch):
    def no_service(*args, **kwargs):
        raise normal_guard.GuardError("cannot describe target: service not found")

    monkeypatch.setattr(normal_guard, "run_gcloud_json", no_service)
    with pytest.raises(normal_guard.GuardError, match="service not found"):
        normal_guard.deployed_env_for(FUNCTION, PROJECT, REGION)


def test_standard_manifest_remains_failed_only():
    manifest = bootstrap.load_manifest(SCRIPTS_DIR / "functions_bootstrap_env_manifest.json")

    assert manifest.allowed_function_states == {"FAILED"}
    assert manifest.allow_absent_function is False


def test_committed_recreate_manifest_is_absent_only_when_present():
    if not RECREATE_MANIFEST.exists() and _manifest_seen_in_recent_history(
        RECREATE_MANIFEST
    ):
        pytest.skip("recreate manifest was intentionally removed after cleanup")

    manifest = bootstrap.load_manifest(RECREATE_MANIFEST)

    assert manifest.allowed_function_states == {"ABSENT"}
    assert manifest.allow_absent_function is True
    assert manifest.function == FUNCTION
    assert manifest.project == PROJECT
    assert manifest.region == REGION
    assert manifest.source_tree_sha == SOURCE_TREE_SHA
    assert "FAILED" not in manifest.allowed_function_states


def test_no_service_valid_bootstrap_manifest_passes(monkeypatch, tmp_path):
    fixture = _fixture(tmp_path)

    result = _validate(monkeypatch, fixture)

    assert result.function == FUNCTION
    assert result.expected_plain_env_keys == frozenset()
    assert result.expected_secret_bindings == frozenset()


def test_recreate_manifest_accepts_absent_function_after_cloud_run_is_absent(
    monkeypatch, tmp_path
):
    fixture = _recreate_fixture(tmp_path)

    result = _validate_recreate(monkeypatch, fixture)

    assert result.allowed_function_states == {"ABSENT"}
    assert result.allow_absent_function is True
    assert result.expected_codebase_parameter_keys == frozenset(CODEBASE_PARAMETER_KEYS)
    assert result.expected_secret_bindings == frozenset()


def test_recreate_manifest_refuses_failed_function_state(monkeypatch, tmp_path):
    fixture = _recreate_fixture(tmp_path)

    with pytest.raises(bootstrap.BootstrapContractError, match="FUNCTION_STATE_REFUSED"):
        _validate_recreate(monkeypatch, fixture, function_state="FAILED")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("function", "otherFunction", "FUNCTION_MISMATCH"),
        ("project", "other-project", "PROJECT_MISMATCH"),
        ("region", "us-central1", "REGION_MISMATCH"),
        (
            "source_tree_sha",
            "2222222222222222222222222222222222222222",
            "SOURCE_TREE_SHA_MISMATCH",
        ),
    ],
)
def test_recreate_manifest_identity_must_match_target_and_tree(
    monkeypatch, tmp_path, field, value, message
):
    root, manifest, env_file, source_dir = _recreate_fixture(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data[field] = value
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(bootstrap.BootstrapContractError, match=message):
        _validate_recreate(monkeypatch, (root, manifest, env_file, source_dir))


def test_recreate_manifest_refuses_existing_cloud_run_service(monkeypatch, tmp_path):
    fixture = _recreate_fixture(tmp_path)

    with pytest.raises(bootstrap.BootstrapContractError, match="SERVING_ENV_AUTHORITY_EXISTS"):
        _validate_recreate(monkeypatch, fixture, serving_service_exists=True)


def test_recreate_manifest_refuses_unexpected_dotenv_key(monkeypatch, tmp_path):
    candidate = "".join(
        f"{key}={value}\n" for key, value in CODEBASE_PARAMETER_VALUES.items()
    )
    fixture = _recreate_fixture(tmp_path, candidate=candidate + "UNEXPECTED=value\n")

    with pytest.raises(bootstrap.BootstrapContractError, match="CANDIDATE_ENV_MISMATCH"):
        _validate_recreate(monkeypatch, fixture)


def test_recreate_manifest_refuses_live_parameter_authority_mismatch(
    monkeypatch, tmp_path
):
    fixture = _recreate_fixture(tmp_path)
    root, manifest, env_file, source_dir = fixture
    _stub_recreate_live_authority(monkeypatch)
    mismatched_values = {
        **CODEBASE_PARAMETER_VALUES,
        "RESEND_FROM_EMAIL": "other-sender@example.invalid",
    }
    monkeypatch.setattr(
        bootstrap,
        "read_live_codebase_parameter_authority",
        lambda function, project, region, expected: mismatched_values,
    )

    with pytest.raises(bootstrap.BootstrapContractError, match="LIVE_PARAMETER_VALUE_MISMATCH"):
        bootstrap.validate_bootstrap_contract(
            repo_root=root,
            manifest_path=manifest,
            project=PROJECT,
            region=REGION,
            function=FUNCTION,
            env_file=env_file,
            source_dir=source_dir,
            firebase_cli_version="15.30.2",
            discovered_build_params=_codebase_discovery(),
        )


def test_recreate_manifest_refuses_secret_leakage_into_dotenv_contract(
    monkeypatch, tmp_path
):
    leaked_secret = "RESEND_API_KEY"
    candidate = "".join(
        f"{key}={value}\n" for key, value in CODEBASE_PARAMETER_VALUES.items()
    )
    fixture = _recreate_fixture(
        tmp_path,
        candidate=candidate + f"{leaked_secret}=leaked\n",
        codebase_keys=[*CODEBASE_PARAMETER_KEYS, leaked_secret],
        codebase_secret_names=CODEBASE_SECRET_NAMES,
    )

    with pytest.raises(
        bootstrap.BootstrapContractError,
        match="secret parameter names cannot be codebase dotenv keys",
    ):
        _validate_recreate(monkeypatch, fixture)


def test_recreate_manifest_refuses_dirty_deploy_source(monkeypatch, tmp_path):
    fixture = _recreate_fixture(tmp_path)
    root, manifest, env_file, source_dir = fixture
    _stub_recreate_live_authority(monkeypatch)
    monkeypatch.setattr(
        bootstrap,
        "_require_clean_source",
        lambda repo, **kwargs: (_ for _ in ()).throw(
            bootstrap.BootstrapContractError("SOURCE_WORKTREE_NOT_CLEAN")
        ),
    )

    with pytest.raises(bootstrap.BootstrapContractError, match="SOURCE_WORKTREE_NOT_CLEAN"):
        bootstrap.validate_bootstrap_contract(
            repo_root=root,
            manifest_path=manifest,
            project=PROJECT,
            region=REGION,
            function=FUNCTION,
            env_file=env_file,
            source_dir=source_dir,
            firebase_cli_version="15.30.2",
            discovered_build_params=_codebase_discovery(),
        )


def test_codebase_parameter_bootstrap_requires_actual_runtime_discovery(
    monkeypatch, tmp_path
):
    codebase_keys = [
        "APPLE_IAP_APPLE_ID",
        "APPLE_IAP_BUNDLE_ID",
        "RESEND_FROM_EMAIL",
        "RESEND_REPLY_TO",
    ]
    candidate = "".join(f"{key}=synthetic-value\n" for key in codebase_keys)
    authorities = [
        "sendStudentVerificationEmail",
        "appStoreServerNotifications",
        "cleanupAvatarMedia",
    ]
    secret_names = [
        "PLAY_REVIEW_LOGIN_ID",
        "PLAY_REVIEW_PASSWORD_SCRYPT",
        "PLAY_REVIEW_FIREBASE_UID",
        "PLAY_REVIEW_ENABLED",
        "PORTONE_API_SECRET",
        "RESEND_API_KEY",
    ]
    fixture = _fixture(
        tmp_path,
        candidate=candidate,
        codebase_keys=codebase_keys,
        codebase_secret_names=secret_names,
        parameter_authority_functions=authorities,
    )

    with pytest.raises(
        bootstrap.BootstrapContractError,
        match="PARAMETER_DISCOVERY_REQUIRED",
    ):
        _validate(monkeypatch, fixture)


def test_parameter_authorities_are_bound_to_the_approved_three_functions(
    monkeypatch, tmp_path
):
    fixture = _fixture(
        tmp_path,
        codebase_keys=[
            "APPLE_IAP_APPLE_ID",
            "APPLE_IAP_BUNDLE_ID",
            "RESEND_FROM_EMAIL",
            "RESEND_REPLY_TO",
        ],
        parameter_authority_functions=[
            "sendStudentVerificationEmail",
            "appStoreServerNotifications",
            "otherActiveFunction",
        ],
    )

    with pytest.raises(
        bootstrap.BootstrapContractError,
        match="approved live authorities",
    ):
        _validate(monkeypatch, fixture)


def test_discovered_parameters_and_live_authorities_pass_bootstrap(monkeypatch, tmp_path):
    codebase_keys = [
        "APPLE_IAP_APPLE_ID",
        "APPLE_IAP_BUNDLE_ID",
        "RESEND_FROM_EMAIL",
        "RESEND_REPLY_TO",
    ]
    candidate_values = {
        "APPLE_IAP_APPLE_ID": "94727223",
        "APPLE_IAP_BUNDLE_ID": "com.seolleyeon.app",
        "RESEND_FROM_EMAIL": "synthetic-sender@example.invalid",
        "RESEND_REPLY_TO": "synthetic-reply@example.invalid",
    }
    candidate = "".join(f"{key}={value}\n" for key, value in candidate_values.items())
    authorities = [
        "sendStudentVerificationEmail",
        "appStoreServerNotifications",
        "cleanupAvatarMedia",
    ]
    secret_names = [
        "PLAY_REVIEW_LOGIN_ID",
        "PLAY_REVIEW_PASSWORD_SCRYPT",
        "PLAY_REVIEW_FIREBASE_UID",
        "PLAY_REVIEW_ENABLED",
        "PORTONE_API_SECRET",
        "RESEND_API_KEY",
    ]
    fixture = _fixture(
        tmp_path,
        candidate=candidate,
        codebase_keys=codebase_keys,
        codebase_secret_names=secret_names,
        parameter_authority_functions=authorities,
    )
    parameters = [
        {"name": "APPLE_IAP_APPLE_ID", "type": "string", "default": "94727223"},
        {
            "name": "APPLE_IAP_BUNDLE_ID",
            "type": "string",
            "default": "com.seolleyeon.app",
        },
        {"name": "RESEND_FROM_EMAIL", "type": "string", "default": ""},
        {"name": "RESEND_REPLY_TO", "type": "string", "default": ""},
        *({"name": name, "type": "secret"} for name in secret_names),
    ]
    discovered = {
        "contractVersion": 1,
        "firebaseToolsVersion": "15.30.2",
        "parameterCount": 10,
        "secretParameterCount": 6,
        "parameters": parameters,
    }
    monkeypatch.setattr(
        bootstrap,
        "read_live_codebase_parameter_authority",
        lambda function, project, region, expected: candidate_values,
    )

    result = _validate(monkeypatch, fixture, discovered_build_params=discovered)

    assert result.expected_codebase_parameter_keys == frozenset(codebase_keys)
    assert result.parameter_authority_functions == tuple(authorities)


def test_live_parameter_authority_reads_only_selected_non_secret_environment(monkeypatch):
    expected = {
        "APPLE_IAP_APPLE_ID",
        "APPLE_IAP_BUNDLE_ID",
        "RESEND_FROM_EMAIL",
        "RESEND_REPLY_TO",
    }
    values = {
        "APPLE_IAP_APPLE_ID": "synthetic-apple-id",
        "APPLE_IAP_BUNDLE_ID": "synthetic-bundle-id",
        "RESEND_FROM_EMAIL": "synthetic-sender@example.invalid",
        "RESEND_REPLY_TO": "synthetic-reply@example.invalid",
        "UNRELATED_ENV": "synthetic-unrelated",
    }
    monkeypatch.setattr(
        bootstrap,
        "_run_gcloud_json",
        lambda *args, **kwargs: (
            {
                "state": "ACTIVE",
                "serviceConfig": {
                    "environmentVariables": values,
                    "secretEnvironmentVariables": [
                        {"key": "SYNTHETIC_SECRET_NAME", "secret": "not-read"}
                    ],
                },
            },
            "",
        ),
    )

    selected = bootstrap.read_live_codebase_parameter_authority(
        "syntheticAuthority", PROJECT, REGION, frozenset(expected)
    )

    assert set(selected) == expected
    assert "UNRELATED_ENV" not in selected
    assert "SYNTHETIC_SECRET_NAME" not in selected


def test_serving_service_makes_bootstrap_refuse(monkeypatch, tmp_path):
    root, manifest, env_file, source_dir = _fixture(tmp_path)
    _stub_live_authority(monkeypatch)
    monkeypatch.setattr(
        bootstrap,
        "assert_no_serving_service",
        lambda *args: (_ for _ in ()).throw(
            bootstrap.BootstrapContractError("SERVING_ENV_AUTHORITY_EXISTS")
        ),
    )

    with pytest.raises(bootstrap.BootstrapContractError, match="SERVING_ENV_AUTHORITY_EXISTS"):
        bootstrap.validate_bootstrap_contract(
            repo_root=root,
            manifest_path=manifest,
            project=PROJECT,
            region=REGION,
            function=FUNCTION,
            env_file=env_file,
            source_dir=source_dir,
            firebase_cli_version="15.30.2",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("function", "otherFunction", "FUNCTION_MISMATCH"),
        ("project", "other-project", "PROJECT_MISMATCH"),
        ("region", "us-central1", "REGION_MISMATCH"),
        (
            "source_tree_sha",
            "2222222222222222222222222222222222222222",
            "SOURCE_TREE_SHA_MISMATCH",
        ),
    ],
)
def test_manifest_identity_must_bind_to_fresh_target(
    monkeypatch, tmp_path, field, value, message
):
    root, manifest, env_file, source_dir = _fixture(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data[field] = value
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(bootstrap.BootstrapContractError, match=message):
        _validate(monkeypatch, (root, manifest, env_file, source_dir))


def test_manifest_tree_binding_survives_tooling_only_main_commit(monkeypatch, tmp_path):
    fixture = _fixture(tmp_path)
    root, manifest, env_file, source_dir = fixture
    _stub_live_authority(monkeypatch)
    monkeypatch.setattr(bootstrap, "_fresh_git_sha", lambda repo, ref: NEXT_MAIN_SHA)

    result = bootstrap.validate_bootstrap_contract(
        repo_root=root,
        manifest_path=manifest,
        project=PROJECT,
        region=REGION,
        function=FUNCTION,
        env_file=env_file,
        source_dir=source_dir,
        firebase_cli_version="15.30.2",
    )

    assert result.source_tree_sha == SOURCE_TREE_SHA


def test_checkout_functions_tree_must_match_manifest_and_fresh_main(monkeypatch, tmp_path):
    fixture = _fixture(tmp_path)
    root, manifest, env_file, source_dir = fixture
    _stub_live_authority(monkeypatch)

    def changed_head_tree(repo, ref, tree_path):
        if ref == "HEAD":
            return "2222222222222222222222222222222222222222"
        return SOURCE_TREE_SHA

    monkeypatch.setattr(bootstrap, "_git_tree_sha", changed_head_tree)

    with pytest.raises(bootstrap.BootstrapContractError, match="SOURCE_TREE_SHA_MISMATCH"):
        bootstrap.validate_bootstrap_contract(
            repo_root=root,
            manifest_path=manifest,
            project=PROJECT,
            region=REGION,
            function=FUNCTION,
            env_file=env_file,
            source_dir=source_dir,
            firebase_cli_version="15.30.2",
        )


def test_untracked_functions_source_invalidates_tree_authority(tmp_path):
    repo_root = tmp_path / "repo"
    functions = repo_root / "functions"
    functions.mkdir(parents=True)
    tracked_source = functions / "index.ts"
    tracked_source.write_text("export {}\n", encoding="utf-8")
    subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "add", "functions/index.ts"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "-c",
            "user.name=Bootstrap Test",
            "-c",
            "user.email=bootstrap-test@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        check=True,
        capture_output=True,
    )
    (functions / "untracked-runtime.ts").write_text("export {}\n", encoding="utf-8")

    with pytest.raises(
        bootstrap.BootstrapContractError,
        match="untracked deployable Functions",
    ):
        bootstrap._require_deploy_source_matches_ref(repo_root, "HEAD")


def test_only_verified_generated_json_is_ignored_for_deploy_source_authority(tmp_path):
    repo_root = tmp_path / "repo"
    functions = repo_root / "functions"
    source = functions / "src" / "avatarQaHardRejectContract.json"
    generated = functions / "lib" / "avatarQaHardRejectContract.json"
    source.parent.mkdir(parents=True)
    generated.parent.mkdir(parents=True)
    source.write_text('{"approved":true}\n', encoding="utf-8")
    generated.write_text('{"approved":true}\n', encoding="utf-8")
    (functions / "index.ts").write_text("export {}\n", encoding="utf-8")
    subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "add", "functions/src", "functions/index.ts"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "-c",
            "user.name=Bootstrap Test",
            "-c",
            "user.email=bootstrap-test@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        check=True,
        capture_output=True,
    )

    bootstrap._require_deploy_source_matches_ref(
        repo_root, "HEAD", allow_exact_generated_artifact=True
    )
    (functions / "lib" / "unrelated.js").write_text("module.exports = {}\n", encoding="utf-8")
    with pytest.raises(
        bootstrap.BootstrapContractError,
        match="untracked deployable Functions",
    ):
        bootstrap._require_deploy_source_matches_ref(
            repo_root, "HEAD", allow_exact_generated_artifact=True
        )


def test_exact_verified_generated_json_is_allowed_in_clean_source_check(tmp_path):
    repo_root = tmp_path / "repo"
    source = repo_root / "functions" / "src" / "avatarQaHardRejectContract.json"
    generated = repo_root / "functions" / "lib" / "avatarQaHardRejectContract.json"
    source.parent.mkdir(parents=True)
    generated.parent.mkdir(parents=True)
    source.write_text('{"approved":true}\n', encoding="utf-8")
    generated.write_text('{"approved":true}\n', encoding="utf-8")
    (repo_root / "functions" / "index.ts").write_text("export {}\n", encoding="utf-8")
    subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "add", "functions/src", "functions/index.ts"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "-c",
            "user.name=Bootstrap Test",
            "-c",
            "user.email=bootstrap-test@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        check=True,
        capture_output=True,
    )

    bootstrap._require_clean_source(repo_root, allow_exact_generated_artifact=True)
    unexpected = repo_root / "functions" / "lib" / "unrelated.txt"
    unexpected.write_text("unexpected\n", encoding="utf-8")
    with pytest.raises(
        bootstrap.BootstrapContractError,
        match="SOURCE_WORKTREE_NOT_CLEAN",
    ):
        bootstrap._require_clean_source(repo_root, allow_exact_generated_artifact=True)


def test_dirty_source_worktree_is_refused(tmp_path):
    repo_root = tmp_path / "repo"
    functions = repo_root / "functions"
    functions.mkdir(parents=True)
    tracked_source = functions / "index.ts"
    tracked_source.write_text("export const baseline = true;\n", encoding="utf-8")
    subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo_root), "add", "functions/index.ts"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "-c",
            "user.name=Bootstrap Test",
            "-c",
            "user.email=bootstrap-test@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        check=True,
        capture_output=True,
    )
    tracked_source.write_text("export const changed = true;\n", encoding="utf-8")

    with pytest.raises(
        bootstrap.BootstrapContractError,
        match="SOURCE_WORKTREE_NOT_CLEAN",
    ):
        bootstrap._require_clean_source(repo_root)


def test_extra_candidate_env_key_is_refused(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, candidate="UNRELATED=value\n")

    with pytest.raises(bootstrap.BootstrapContractError, match="CANDIDATE_ENV_MISMATCH"):
        _validate(monkeypatch, fixture)


def test_missing_required_env_key_is_refused(tmp_path, monkeypatch):
    fixture = _fixture(
        tmp_path,
        source="const required = process.env.REQUIRED_KEY;\n"
        "export const syncMeetingIcebreakerFromPromise = required;\n",
        plain_keys=["REQUIRED_KEY"],
    )

    with pytest.raises(bootstrap.BootstrapContractError, match="CANDIDATE_ENV_MISMATCH"):
        _validate(monkeypatch, fixture)


def test_unexpected_secret_binding_is_refused(tmp_path, monkeypatch):
    fixture = _fixture(
        tmp_path,
        source="const secret = defineSecret(\"RECOVERY_SECRET\");\n"
        "export const syncMeetingIcebreakerFromPromise = secret;\n",
    )

    with pytest.raises(
        bootstrap.BootstrapContractError,
        match="SECRET_CONTRACT_MISMATCH",
    ):
        _validate(monkeypatch, fixture)


def test_manifest_secret_binding_must_match_source_closure(tmp_path, monkeypatch):
    root, manifest, env_file, source_dir = _fixture(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["expected_secret_bindings"] = ["RECOVERY_SECRET"]
    manifest.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(bootstrap.BootstrapContractError, match="SECRET_CONTRACT_MISMATCH"):
        _validate(monkeypatch, (root, manifest, env_file, source_dir))


def test_absent_function_is_refused(monkeypatch, tmp_path):
    fixture = _fixture(tmp_path)
    root, manifest, env_file, source_dir = fixture
    _stub_live_authority(monkeypatch)
    monkeypatch.setattr(bootstrap, "describe_function_state", lambda *args: "ABSENT")

    with pytest.raises(bootstrap.BootstrapContractError, match="FUNCTION_STATE_REFUSED"):
        bootstrap.validate_bootstrap_contract(
            repo_root=root,
            manifest_path=manifest,
            project=PROJECT,
            region=REGION,
            function=FUNCTION,
            env_file=env_file,
            source_dir=source_dir,
            firebase_cli_version="15.30.2",
        )


def test_unknown_dynamic_env_read_is_refused(tmp_path, monkeypatch):
    fixture = _fixture(
        tmp_path,
        source="const name = \"REQUIRED_KEY\";\n"
        "const value = process.env[name];\n"
        "export const syncMeetingIcebreakerFromPromise = value;\n",
    )

    with pytest.raises(bootstrap.BootstrapContractError, match="UNKNOWN_ENV_READ"):
        _validate(monkeypatch, fixture)


def test_transitive_module_load_closure_is_inventoried(tmp_path, monkeypatch):
    root, manifest, env_file, source_dir = _fixture(
        tmp_path,
        source="import { helper } from \"./helper\";\n"
        "export const syncMeetingIcebreakerFromPromise = helper;\n",
        plain_keys=["CLOSURE_KEY"],
        candidate="CLOSURE_KEY=value\n",
    )
    (source_dir / "helper.ts").write_text(
        "export const helper = process.env.CLOSURE_KEY;\n", encoding="utf-8"
    )

    result = _validate(monkeypatch, (root, manifest, env_file, source_dir))

    assert result.expected_plain_env_keys == {"CLOSURE_KEY"}


def test_bootstrap_invocation_rejects_allow_flags_and_multiple_targets():
    with pytest.raises(bootstrap.BootstrapContractError, match="ALLOW_FLAG_REFUSED"):
        bootstrap.validate_bootstrap_invocation(
            functions=[FUNCTION], allow_authorizations=["--allow-add-key"]
        )
    with pytest.raises(bootstrap.BootstrapContractError, match="MULTI_FUNCTION_REFUSED"):
        bootstrap.validate_bootstrap_invocation(
            functions=[FUNCTION], allow_multiple_functions=True
        )
    with pytest.raises(bootstrap.BootstrapContractError, match="EXACT_TARGET_REQUIRED"):
        bootstrap.validate_bootstrap_invocation(functions=[FUNCTION, "otherFunction"])


def test_firebase_cli_version_must_be_exact():
    with pytest.raises(bootstrap.BootstrapContractError, match="VERSION_MISMATCH"):
        bootstrap.validate_firebase_cli_version("15.30.1")
    bootstrap.validate_firebase_cli_version("15.30.2\n")


def test_dotenv_mutation_after_guard_is_refused(tmp_path):
    env_file = tmp_path / ".env.seolleyeon-final"
    env_file.write_text("CLOSURE_KEY=value\n", encoding="utf-8")
    expected = deploy_contract.sha256_file(env_file)
    env_file.write_text("CLOSURE_KEY=changed\n", encoding="utf-8")

    with pytest.raises(deploy_contract.DeployContractError, match="CHANGED_AFTER_GUARD"):
        deploy_contract.require_unchanged(env_file, expected)


def test_platform_managed_candidate_key_is_refused(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path, candidate="FUNCTION_TARGET=wrong\n")

    with pytest.raises(bootstrap.BootstrapContractError, match="PLATFORM_ENV_REFUSED"):
        _validate(monkeypatch, fixture)
