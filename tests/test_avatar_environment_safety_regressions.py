import sys
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

import avatar_generation.qa as qa_module  # noqa: E402
import avatar_generation.worker as worker_module  # noqa: E402
from avatar_generation.preprocessing.reference import (  # noqa: E402
    validate_reference_preprocess_enabled_for_environment,
)

ENVIRONMENT_ALIASES = ("AVATAR_ENVIRONMENT", "ENVIRONMENT", "APP_ENV")


def _clear_environment_aliases(monkeypatch) -> None:
    for name in ENVIRONMENT_ALIASES:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("alias", ENVIRONMENT_ALIASES)
def test_each_production_alias_closes_privacy_and_qa_bypasses(
    monkeypatch,
    alias,
):
    _clear_environment_aliases(monkeypatch)
    monkeypatch.setenv(alias, "production")
    monkeypatch.setenv("AVATAR_REFERENCE_PRIVACY_PREPROCESS", "false")
    monkeypatch.setenv("AVATAR_QA_ALLOW_DEV_BYPASS", "true")
    monkeypatch.setenv("AVATAR_QA_ALLOW_STAGING_HEURISTIC_PREVIEW", "true")

    with pytest.raises(ValueError, match="production"):
        validate_reference_preprocess_enabled_for_environment()
    # No remaining worker mode builds a model-conditioning reference image, so
    # the worker never hands a generation reference to a local model at all.
    context = worker_module._prepare_reference_preprocess_for_generation(
        Image.new("RGB", (64, 64), "white"),
        run_mode="dry_run",
    )
    assert context.generation_image is None

    assert qa_module._is_production_environment() is True
    assert qa_module._dev_bypass_allowed() is False
    assert qa_module._staging_heuristic_preview_allowed() is False


def test_conflicting_environment_aliases_fail_closed_for_privacy_and_qa(
    monkeypatch,
):
    _clear_environment_aliases(monkeypatch)
    monkeypatch.setenv("AVATAR_ENVIRONMENT", "development")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("AVATAR_REFERENCE_PRIVACY_PREPROCESS", "false")
    monkeypatch.setenv("AVATAR_QA_ALLOW_DEV_BYPASS", "true")
    monkeypatch.setenv("AVATAR_QA_ALLOW_STAGING_HEURISTIC_PREVIEW", "true")

    with pytest.raises(ValueError, match="production"):
        validate_reference_preprocess_enabled_for_environment()
    # No remaining worker mode builds a model-conditioning reference image, so
    # the worker never hands a generation reference to a local model at all.
    context = worker_module._prepare_reference_preprocess_for_generation(
        Image.new("RGB", (64, 64), "white"),
        run_mode="dry_run",
    )
    assert context.generation_image is None

    assert qa_module._is_production_environment() is True
    assert qa_module._dev_bypass_allowed() is False
    assert qa_module._staging_heuristic_preview_allowed() is False


def test_reference_validation_explicit_environment_remains_testable(
    monkeypatch,
):
    _clear_environment_aliases(monkeypatch)
    monkeypatch.setenv("AVATAR_ENVIRONMENT", "production")

    validate_reference_preprocess_enabled_for_environment(
        environment="development",
        preprocess_enabled=False,
    )
    with pytest.raises(ValueError, match="production"):
        validate_reference_preprocess_enabled_for_environment(
            environment="production",
            preprocess_enabled=False,
        )
