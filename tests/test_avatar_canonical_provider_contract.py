"""Canonical generation provider contract.

Locks the reconciled production provider decision:
- Azure GPT-Image-2 is the only canonical production generation backend.
- Legacy FLUX is local-only and can never run in a production environment.
- dry_run can never run in a production environment.
- The canonical prompt is the approved single-line contract.

These replace the retired "gpt-image must never appear" policy test that
encoded the superseded FLUX-only architecture.
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.avatar_prompt_contract import (  # noqa: E402
    AVATAR_GENERAL_PROMPT_V0_TEMP,
    AVATAR_GENERAL_PROMPT_VERSION,
)
from avatar_generation.model_adapters.azure_contracts import (  # noqa: E402
    AZURE_GPT_IMAGE_2_MODEL_ID,
)
from avatar_generation.worker import (  # noqa: E402
    AvatarGenerationError,
    CANONICAL_AZURE_WORKER_MODE,
    resolve_worker_mode,
)


@pytest.fixture
def production_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("AVATAR_WORKER_MODE", raising=False)
    monkeypatch.delenv("AVATAR_WORKER_DRY_RUN", raising=False)


def test_production_defaults_to_canonical_azure_mode(production_env):
    assert resolve_worker_mode() == CANONICAL_AZURE_WORKER_MODE
    assert CANONICAL_AZURE_WORKER_MODE == AZURE_GPT_IMAGE_2_MODEL_ID


def test_production_refuses_dry_run(production_env):
    with pytest.raises(AvatarGenerationError):
        resolve_worker_mode("dry_run")


def test_canonical_prompt_is_the_approved_contract():
    # The one-line v0_temp prompt was superseded in the 4865 G004 lineage by
    # the detailed Live2D-style contract, versioned avatar_general_prompt_v1.
    # Lock the version tag and the identity/no-beautification invariants
    # instead of the retired sentence.
    assert AVATAR_GENERAL_PROMPT_VERSION == "avatar_general_prompt_v1"
    prompt = AVATAR_GENERAL_PROMPT_V0_TEMP
    assert "동일하게 유지" in prompt
    assert "과도한 미화" in prompt
    assert "텍스트" in prompt  # 텍스트/장식 금지 invariant
    assert "1명만" in prompt


def test_client_side_code_has_no_azure_credentials_or_endpoints():
    # The Flutter client must never talk to Azure directly. Azure transport is
    # server-only (Cloud Run worker); the client only calls Firebase callables.
    forbidden = ["openai.azure.com", "AZURE_OPENAI", "AZURE_API_KEY", "api-key"]
    dart_root = REPO_ROOT / "lib"
    offenders = []
    for path in dart_root.rglob("*.dart"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path}:{token}")
    assert offenders == []


@pytest.mark.parametrize("environment", ["production", "staging", "local"])
def test_flux_worker_mode_is_retired_in_every_environment(monkeypatch, environment):
    # Not just "not in production": the local-model backend no longer exists,
    # so the stale value is a configuration error everywhere.
    monkeypatch.delenv("AVATAR_WORKER_MODE", raising=False)
    monkeypatch.setenv("ENVIRONMENT", environment)
    with pytest.raises(AvatarGenerationError, match="avatar_worker_mode_retired"):
        resolve_worker_mode("flux")
    monkeypatch.setenv("AVATAR_WORKER_MODE", "flux")
    with pytest.raises(AvatarGenerationError, match="avatar_worker_mode_retired"):
        resolve_worker_mode()


def test_flux_runtime_modules_do_not_exist():
    import importlib

    for module in (
        "avatar_generation.flux_config",
        "avatar_generation.model_adapters.flux2_klein",
        "avatar_generation.seolleyeon_avatar_prompt_builder_v4",
    ):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(module)
