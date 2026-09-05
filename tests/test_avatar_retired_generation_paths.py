"""Forbidden-reachability contract for the canonical Azure-only avatar tree.

Production, deploy and config sources must contain no path to:
  - the retired single-photo generation callable (uploadAvatarSourcePhoto)
  - the retired legacy_first_photo rollback selection mode
  - local-model (FLUX) generation: provider, worker mode, fallback,
    checkpoint/tokenizer download, or the diffusers dependency.

Historical markdown is out of scope by design.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AVATAR_PKG = REPO_ROOT / "lib" / "ai_recommend_model" / "avatar_generation"

PRODUCTION_SOURCES = [
    *sorted((REPO_ROOT / "functions" / "src").glob("*.ts")),
    *sorted(AVATAR_PKG.rglob("*.py")),
    *sorted((REPO_ROOT / "lib" / "services").glob("*.dart")),
    *sorted((REPO_ROOT / "lib" / "features" / "onboarding").rglob("*.dart")),
    AVATAR_PKG / "Dockerfile",
    REPO_ROOT / "requirements_avatar_worker.txt",
    REPO_ROOT / "cloudbuild.avatar-worker.yaml",
    REPO_ROOT / "config" / "avatar-ops" / "avatar-release-manifest.json",
    REPO_ROOT / "scripts" / "staging_avatar_live_setup.ps1",
    REPO_ROOT / "scripts" / "staging_avatar_live_preflight.py",
    REPO_ROOT / "scripts" / "staging_deploy_functions.sh",
]


def _text(path: Path) -> str:
    raw = path.read_bytes()
    if raw[:2] == b"\xff\xfe":
        return raw.decode("utf-16")
    return raw.decode("utf-8", errors="replace")


def _non_test_sources():
    for path in PRODUCTION_SOURCES:
        if not path.exists() or path.name.endswith(".test.ts"):
            continue
        yield path, _text(path)


def test_flux_runtime_files_are_gone():
    for relative in (
        "flux_config.py",
        "model_adapters/flux2_klein.py",
        "seolleyeon_avatar_prompt_builder_v4.py",
    ):
        assert not (AVATAR_PKG / relative).exists(), relative
    for script in ("avatar_flux_param_sweep.py", "retry_failed_avatar_jobs.py", "run_canary_from_validated_map.py"):
        assert not (REPO_ROOT / "scripts" / script).exists(), script


def test_no_retired_generation_dependency_is_declared():
    requirements = _text(REPO_ROOT / "requirements_avatar_worker.txt").lower()
    assert "diffusers" not in requirements
    assert "flux" not in requirements
    dockerfile = _text(AVATAR_PKG / "Dockerfile")
    assert "AVATAR_WORKER_MODE=azure_gpt_image_2" in dockerfile
    assert "flux" not in dockerfile.lower()
    assert "diffusers" not in dockerfile.lower()


FORBIDDEN = {
    "flux worker mode": re.compile(r"AVATAR_WORKER_MODE\s*=\s*['\"]?flux", re.I),
    "flux provider": re.compile(r"provider\s*[=:]\s*['\"]flux", re.I),
    "flux model id": re.compile(r"black-forest-labs|FLUX\.2-klein|flux2_klein", re.I),
    "diffusers import": re.compile(r"^\s*(from|import)\s+diffusers", re.M),
    "legacy rollback mode": re.compile(r"legacy_first_photo"),
    "legacy callable": re.compile(r"uploadAvatarSourcePhoto"),
    "legacy factory": re.compile(r"createUploadAvatarSourcePhotoFunction"),
}


def test_production_sources_have_no_forbidden_generation_paths():
    violations = []
    for path, text in _non_test_sources():
        for label, pattern in FORBIDDEN.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(f"{path.relative_to(REPO_ROOT)}:{line} {label}")
    assert not violations, "\n".join(violations)


def test_worker_mode_flux_fails_closed_and_azure_is_the_only_backend():
    import sys

    sys.path.insert(0, str(REPO_ROOT / "lib" / "ai_recommend_model"))
    from avatar_generation.worker import AvatarGenerationError, CANONICAL_AZURE_WORKER_MODE, resolve_worker_mode

    assert CANONICAL_AZURE_WORKER_MODE == "azure_gpt_image_2"
    try:
        resolve_worker_mode("flux")
    except AvatarGenerationError as exc:
        assert "avatar_worker_mode_retired" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("flux mode must be a configuration error")


def test_worker_refuses_retired_source_selection_mode():
    import pytest

    from avatar_generation.worker import (
        AvatarGenerationError,
        parse_avatar_generation_payload,
    )

    payload = {
        "jobId": "avatar_job_retired_mode",
        "uid": "u1",
        "sourcePhotoIds": ["src_001", "src_002"],
        "sourcePhotoRefs": [
            "gs://seolleyeon-final-private-source-photos/users/u1/source/src_001.jpg",
            "gs://seolleyeon-final-private-source-photos/users/u1/source/src_002.jpg",
        ],
        "sourcePhotoObjectGenerations": ["101", "102"],
        "sourceSelectionMode": "legacy_first_photo",
        "candidateCount": 2,
        "modelId": "azure_gpt_image_2",
        "jobType": "avatar_generation",
        "schemaVersion": "avatar_job_v1",
        "idempotencyKey": "avatar_job_retired_mode:v1",
    }
    with pytest.raises(AvatarGenerationError, match="avatar_source_selection_mode_retired"):
        parse_avatar_generation_payload(payload)
