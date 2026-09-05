#!/usr/bin/env python3
"""Read-only staging preflight for the Seolleyeon avatar live pipeline.

The check intentionally reports only resource names and presence/absence. It
does not read secret values, object paths, signed URLs, tokens, or user data.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


DEFAULT_PROJECT = "seolleyeon-final"
DEFAULT_LOCATION = "asia-northeast3"
DEFAULT_WORKER_LOCATION = "asia-southeast1"
DEFAULT_REPOSITORY = "seolleyeon-repo"
DEFAULT_ACCOUNT = "seolleyeon.official@gmail.com"
DEFAULT_HF_TOKEN_ENV_VAR = "AVATAR_WORKER_HF_TOKEN"
DEFAULT_UPLOAD_FUNCTION = "uploadAvatarSourcePhoto"

REQUIRED_SERVICES = {
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudtasks.googleapis.com",
    "compute.googleapis.com",
    "iamcredentials.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
}

BASE_SERVICE_ACCOUNTS = {
    "avatar-worker": "avatar-worker@{project}.iam.gserviceaccount.com",
    "task-invoker": "task-invoker@{project}.iam.gserviceaccount.com",
}

CLIP_SERVICE_ACCOUNTS = {
    "clip-worker": "clip-worker@{project}.iam.gserviceaccount.com",
}

BASE_QUEUES = {"avatar-generation"}
CLIP_QUEUES = {"clip-embedding"}
REQUIRED_WORKER_SERVICES = {"seolleyeon-avatar-worker"}
OPTIONAL_WORKER_SERVICES = {"seolleyeon-clip-worker"}
REQUIRED_SECRETS: set[str] = {
    # Azure 자격증명은 Secret Manager 에만 존재해야 한다. 이 시크릿이 없으면
    # 워커는 첫 생성에서 azure_provider_configuration_missing_ 로 실패한다.
    # 값은 여기에도, 배포 스크립트에도 남기지 않는다(참조 이름만).
    "seolleyeon-avatar-azure-openai-api-key",
}
REQUIRED_BUCKETS = {
    "seolleyeon-final-private-source-photos",
    "seolleyeon-final-avatar-temp",
    "seolleyeon-final-approved-avatars",
}
BASE_ENV_KEYS = {
    "JOB_QUEUE_MODE",
    "CLOUD_TASKS_PROJECT",
    "GCP_LOCATION",
    "AVATAR_GENERATION_QUEUE_NAME",
    "AVATAR_GENERATION_TASK_URL",
    "TASK_INVOKER_SERVICE_ACCOUNT",
}
CLIP_ENV_KEYS = {
    "CLIP_EMBEDDING_QUEUE_NAME",
    "CLIP_EMBEDDING_TASK_URL",
}
AVATAR_ONLY_ENV_KEYS = {"CLIP_EMBEDDING_QUEUE_ENABLED"}
REQUIRED_AVATAR_WORKER_ENV_KEYS = {
    "ENVIRONMENT",
    "AVATAR_WORKER_MODE",
    "AVATAR_WORKER_AUTH_MODE",
    "AVATAR_WORKER_CLOUD_RUN_IAM_ENFORCED",
    "AVATAR_GPU_WORKER_ENABLED",
    "AVATAR_BATCHING_ENABLED",
    "AVATAR_BATCH_MODE",
    "AVATAR_BATCH_CONCURRENCY_PER_GPU",
    "AVATAR_WORKER_DEADLINE_SECONDS",
    "AVATAR_BATCH_MAX_SECONDS",
    "SOURCE_PHOTO_BUCKET",
    "AVATAR_TEMP_BUCKET",
    "MAX_CANDIDATES",
    "CLOUD_RUN_VCPU",
    "CLOUD_RUN_MEMORY_GIB",
    "AVATAR_COST_ALERT_DAILY_USD",
    "AVATAR_COST_ALERT_MONTHLY_USD",
    "AVATAR_COST_HARD_DAILY_GENERATION_LIMIT",
    "AVATAR_COST_HARD_MONTHLY_GENERATION_LIMIT",
    "AVATAR_COST_ENFORCE_BUDGET",
    "AVATAR_COST_KILL_SWITCH_ENABLED",
    "AVATAR_FACE_DETECTOR_ENABLED",
    "AVATAR_FACE_DETECTOR_PROVIDER",
    "AVATAR_FACE_DETECTOR_MIN_CONFIDENCE",
    "AVATAR_FACE_MIN_RELATIVE_SIZE",
    "AVATAR_TRAIT_EXTRACTION_ENABLED",
    "AVATAR_TRAIT_MODEL_ID",
    "AVATAR_TRAIT_MAX_IMAGE_EDGE",
    "AVATAR_TRAIT_LOCAL_FILES_ONLY",
    "AVATAR_TRAIT_ATTENTION_IMPLEMENTATION",
    "AVATAR_TRAIT_FLORENCE_TASK_PROMPT",
    "AVATAR_TRAIT_REQUIRE_VALIDATED",
    "AVATAR_TRAIT_QWEN_FALLBACK_ENABLED",
    "AVATAR_TRAIT_USE_PRIVACY_REFERENCE",
    "AVATAR_CANDIDATE_TRAIT_QA_ENABLED",
    "AVATAR_REFERENCE_PRIVACY_PREPROCESS",
    "AVATAR_REFERENCE_FACE_EQUIVALENT_SIZE",
    "AVATAR_REFERENCE_FACE_BLUR_RADIUS",
    "AVATAR_REFERENCE_NONFACE_EQUIVALENT_SIZE",
    "AVATAR_REFERENCE_NONFACE_BLUR_RADIUS",
    "AVATAR_SAM_ENABLED",
    "AVATAR_SAM_LOAD_ON_DEMAND",
    "AVATAR_FLUX_NUM_INFERENCE_STEPS",
    "AVATAR_FLUX_GUIDANCE_SCALE",
    "AVATAR_INITIAL_CANDIDATE_COUNT",
    "AVATAR_EXTRA_CANDIDATE_COUNT",
    "AVATAR_MIN_SAFE_CANDIDATES_BEFORE_EXTRA",
    "AVATAR_MAX_TOTAL_CANDIDATES",
    "AVATAR_PREVIEW_COUNT",
    "AVATAR_MIN_PREVIEW_CANDIDATES",
    "AVATAR_PREVIEW_REQUIRE_FOUR",
    "AVATAR_PREVIEW_FILL_WITH_SOFT_PASS",
    "AVATAR_PREVIEW_FILL_HARD_REJECT",
    "AVATAR_RERANK_PROVIDER",
    "AVATAR_CLIP_MODEL_ID",
    "AVATAR_DINO_MODEL_ID",
    "AVATAR_QA_ALLOW_STAGING_HEURISTIC_PREVIEW",
    "AVATAR_QA_ALLOW_PHASH_HARD_REJECT_ONLY_NEAR_DUPLICATE",
    "AVATAR_QA_REQUIRE_RELIABLE_FACE_SIM_FOR_TOO_IDENTIFIABLE",
    "AVATAR_QA_PHASH_NEAR_DUPLICATE_REJECT_THRESHOLD",
    "AVATAR_QA_PHASH_REVIEW_THRESHOLD",
    "AVATAR_QA_FACE_SIMILARITY_REVIEW_THRESHOLD",
    "AVATAR_QA_FACE_SIMILARITY_REJECT_THRESHOLD",
}
STAGES = {"prepare", "deploy", "live"}


def _gcloud_executable() -> str:
    return shutil.which("gcloud") or shutil.which("gcloud.cmd") or "gcloud"


def _run(command: Sequence[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _gcloud_values(args: Sequence[str]) -> list[str]:
    code, stdout, _ = _run([_gcloud_executable(), *args])
    if code != 0 or not stdout:
        return []
    return [line.strip() for line in stdout.splitlines() if line.strip()]


def _gcloud_json(args: Sequence[str]) -> Mapping[str, Any]:
    code, stdout, _ = _run([_gcloud_executable(), *args])
    if code != 0 or not stdout:
        return {}
    try:
        decoded = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, Mapping) else {}


def _read_env_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        keys.add(line.split("=", 1)[0].strip())
    return keys


def _missing(expected: Iterable[str], actual: Iterable[str]) -> list[str]:
    actual_set = set(actual)
    return sorted(item for item in expected if item not in actual_set)


def _deployed_function_env_keys(
    *, project: str, location: str, function_name: str
) -> set[str]:
    payload = _gcloud_json(
        [
            "functions",
            "describe",
            function_name,
            "--gen2",
            f"--region={location}",
            f"--project={project}",
            "--format=json",
        ]
    )
    service_config = payload.get("serviceConfig")
    if not isinstance(service_config, Mapping):
        return set()
    env = service_config.get("environmentVariables")
    if not isinstance(env, Mapping):
        return set()
    return {str(key) for key in env.keys()}


def _deployed_run_service_env_keys(
    *, project: str, location: str, service_name: str
) -> set[str]:
    payload = _gcloud_json(
        [
            "run",
            "services",
            "describe",
            service_name,
            f"--region={location}",
            f"--project={project}",
            "--format=json",
        ]
    )
    spec = payload.get("spec")
    if not isinstance(spec, Mapping):
        return set()
    template = spec.get("template")
    if not isinstance(template, Mapping):
        return set()
    template_spec = template.get("spec")
    if not isinstance(template_spec, Mapping):
        return set()
    containers = template_spec.get("containers")
    if not isinstance(containers, list) or not containers:
        return set()
    first = containers[0]
    if not isinstance(first, Mapping):
        return set()
    env = first.get("env")
    if not isinstance(env, list):
        return set()
    keys: set[str] = set()
    for entry in env:
        if isinstance(entry, Mapping) and entry.get("name"):
            keys.add(str(entry["name"]))
    return keys


def _prefixed_issue(kind: str, value: str, severity: str = "blocker") -> dict[str, str]:
    return {"severity": severity, "kind": kind, "value": value}


def build_report(
    *,
    project: str,
    location: str,
    worker_location: str,
    repository: str,
    env_file: Path,
    avatar_only: bool,
    expected_account: str,
    hf_token_env_var: str,
    upload_function_name: str,
    stage: str,
) -> dict[str, Any]:
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {sorted(STAGES)}")

    gcloud = _gcloud_executable()
    code, account, _ = _run([gcloud, "config", "get-value", "account"])
    if code != 0:
        account = ""
    code, active_project, _ = _run([gcloud, "config", "get-value", "project"])
    if code != 0:
        active_project = ""

    services = set(
        _gcloud_values(
            [
                "services",
                "list",
                "--enabled",
                f"--project={project}",
                '--format=value(config.name)',
            ]
        )
    )
    secrets = set(
        _gcloud_values(
            ["secrets", "list", f"--project={project}", "--format=value(name)"]
        )
    )
    service_accounts = set(
        _gcloud_values(
            [
                "iam",
                "service-accounts",
                "list",
                f"--project={project}",
                "--format=value(email)",
            ]
        )
    )
    queues = set(
        _gcloud_values(
            [
                "tasks",
                "queues",
                "list",
                f"--location={location}",
                f"--project={project}",
                "--format=value(name)",
            ]
        )
    )
    run_services = set(
        _gcloud_values(
            [
                "run",
                "services",
                "list",
                f"--region={worker_location}",
                f"--project={project}",
                "--format=value(metadata.name)",
            ]
        )
    )
    repositories = set(
        _gcloud_values(
            [
                "artifacts",
                "repositories",
                "list",
                f"--location={location}",
                f"--project={project}",
                "--format=value(name)",
            ]
        )
    )
    buckets = set(
        _gcloud_values(
            [
                "storage",
                "buckets",
                "list",
                f"--project={project}",
                "--format=value(name)",
            ]
        )
    )
    images = set(
        _gcloud_values(
            [
                "artifacts",
                "docker",
                "images",
                "list",
                f"{location}-docker.pkg.dev/{project}/{repository}",
                f"--project={project}",
                "--include-tags",
                "--format=value(IMAGE)",
            ]
        )
    )
    env_keys = _read_env_keys(env_file)
    deployed_env_keys = _deployed_function_env_keys(
        project=project,
        location=location,
        function_name=upload_function_name,
    )
    deployed_avatar_worker_env_keys = (
        _deployed_run_service_env_keys(
            project=project,
            location=worker_location,
            service_name="seolleyeon-avatar-worker",
        )
        if "seolleyeon-avatar-worker" in run_services
        else set()
    )
    hf_token_env_present = bool(os.environ.get(hf_token_env_var, "").strip())

    required_accounts = dict(BASE_SERVICE_ACCOUNTS)
    required_queues = set(BASE_QUEUES)
    required_env_keys = set(BASE_ENV_KEYS)
    if not avatar_only:
        required_accounts.update(CLIP_SERVICE_ACCOUNTS)
        required_queues.update(CLIP_QUEUES)
        required_env_keys.update(CLIP_ENV_KEYS)
    else:
        required_env_keys.update(AVATAR_ONLY_ENV_KEYS)

    expected_accounts = {
        label: template.format(project=project)
        for label, template in required_accounts.items()
    }

    require_secret = stage in {"deploy", "live"}
    require_worker_service = stage == "live"
    require_deployed_env_keys = stage == "live"

    issues: list[dict[str, str]] = []
    if expected_account and account != expected_account:
        issues.append(_prefixed_issue("account_mismatch", account or "<unset>"))
    if active_project != project:
        issues.append(_prefixed_issue("project_mismatch", active_project or "<unset>"))
    for service in _missing(REQUIRED_SERVICES, services):
        issues.append(_prefixed_issue("service_disabled", service))
    for secret in _missing(REQUIRED_SECRETS, secrets):
        issues.append(
            _prefixed_issue(
                "secret_missing",
                secret,
                severity="blocker" if require_secret else "warning",
            )
        )
    if repository not in repositories:
        issues.append(_prefixed_issue("artifact_repository_missing", repository))
    for bucket in _missing(REQUIRED_BUCKETS, buckets):
        issues.append(_prefixed_issue("bucket_missing", bucket))
    for label, email in expected_accounts.items():
        if email not in service_accounts:
            issues.append(_prefixed_issue("service_account_missing", label))
    for queue in _missing(required_queues, queues):
        issues.append(_prefixed_issue("queue_missing", queue))
    for service in _missing(REQUIRED_WORKER_SERVICES, run_services):
        issues.append(
            _prefixed_issue(
                "run_service_missing",
                service,
                severity="blocker" if require_worker_service else "warning",
            )
        )
    optional_worker_services = set(OPTIONAL_WORKER_SERVICES)
    if avatar_only:
        for label, template in CLIP_SERVICE_ACCOUNTS.items():
            if template.format(project=project) not in service_accounts:
                issues.append(_prefixed_issue("service_account_missing", label, severity="warning"))
        for queue in _missing(CLIP_QUEUES, queues):
            issues.append(_prefixed_issue("queue_missing", queue, severity="warning"))
    for service in _missing(optional_worker_services, run_services):
        issues.append(_prefixed_issue("run_service_missing", service, severity="warning"))
    if not any(image.endswith("/seolleyeon-avatar-worker") for image in images):
        issues.append(_prefixed_issue("artifact_image_missing", "seolleyeon-avatar-worker"))
    for key in _missing(required_env_keys, env_keys):
        issues.append(
            _prefixed_issue(
                "env_key_missing",
                key,
                severity="warning",
            )
        )
    for key in _missing(required_env_keys, deployed_env_keys):
        issues.append(
            _prefixed_issue(
                "function_env_key_missing",
                key,
                severity="blocker" if require_deployed_env_keys else "warning",
            )
        )
    if "seolleyeon-avatar-worker" in run_services:
        for key in _missing(REQUIRED_AVATAR_WORKER_ENV_KEYS, deployed_avatar_worker_env_keys):
            issues.append(
                _prefixed_issue(
                    "worker_env_key_missing",
                    key,
                    severity="blocker" if stage == "live" else "warning",
                )
            )

    return {
        "project": project,
        "location": location,
        "workerLocation": worker_location,
        "stage": stage,
        "activeAccount": account,
        "activeProject": active_project,
        "ok": not any(issue["severity"] == "blocker" for issue in issues),
        "issues": issues,
        "checks": {
            "enabledServices": sorted(services & REQUIRED_SERVICES),
            "secretsPresent": sorted(secrets & REQUIRED_SECRETS),
            "serviceAccountsPresent": sorted(
                label for label, email in expected_accounts.items() if email in service_accounts
            ),
            "queuesPresent": sorted(queues & (BASE_QUEUES | CLIP_QUEUES)),
            "avatarOnly": avatar_only,
            "stage": stage,
            "runServicesPresent": sorted(
                run_services & (REQUIRED_WORKER_SERVICES | OPTIONAL_WORKER_SERVICES)
            ),
            "bucketsPresent": sorted(buckets & REQUIRED_BUCKETS),
            "artifactRepositoriesPresent": sorted(repositories & {repository}),
            "avatarWorkerImagePresent": any(
                image.endswith("/seolleyeon-avatar-worker") for image in images
            ),
            "hfTokenEnvVar": hf_token_env_var,
            "hfTokenEnvVarPresent": hf_token_env_present,
            "envKeysPresent": sorted(env_keys & (BASE_ENV_KEYS | CLIP_ENV_KEYS | AVATAR_ONLY_ENV_KEYS)),
            "uploadFunctionName": upload_function_name,
            "deployedFunctionEnvKeysPresent": sorted(
                deployed_env_keys
                & (BASE_ENV_KEYS | CLIP_ENV_KEYS | AVATAR_ONLY_ENV_KEYS)
            ),
            "deployedAvatarWorkerEnvKeysPresent": sorted(
                deployed_avatar_worker_env_keys & REQUIRED_AVATAR_WORKER_ENV_KEYS
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only preflight for the seolleyeon-final avatar live pipeline."
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--location", default=DEFAULT_LOCATION)
    parser.add_argument("--worker_location", default=DEFAULT_WORKER_LOCATION)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--expected_account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--hf_token_env_var", default=DEFAULT_HF_TOKEN_ENV_VAR)
    parser.add_argument("--upload_function_name", default=DEFAULT_UPLOAD_FUNCTION)
    parser.add_argument(
        "--stage",
        choices=sorted(STAGES),
        default="live",
        help=(
            "prepare: APIs/SAs/queue/image readiness, secret/worker/env as warnings; "
            "deploy: includes HF secret readiness; live: requires deployed worker and Functions env."
        ),
    )
    parser.add_argument(
        "--env_file",
        default="functions/.env.seolleyeon-final",
        help="Local functions env file to check for required key names.",
    )
    parser.add_argument(
        "--avatar_only",
        action="store_true",
        help="Treat CLIP queue/worker resources as warnings for avatar-flow staging smoke.",
    )
    args = parser.parse_args()

    report = build_report(
        project=args.project,
        location=args.location,
        worker_location=args.worker_location,
        repository=args.repository,
        env_file=Path(args.env_file),
        avatar_only=args.avatar_only,
        expected_account=args.expected_account,
        hf_token_env_var=args.hf_token_env_var,
        upload_function_name=args.upload_function_name,
        stage=args.stage,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
