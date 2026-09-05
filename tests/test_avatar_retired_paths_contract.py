import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.model_adapters.azure_contracts import AZURE_GPT_IMAGE_2_MODEL_ID  # noqa: E402
from avatar_generation.worker import AvatarGenerationError, parse_avatar_generation_payload  # noqa: E402


def _payload(model_id: str) -> dict:
    return {
        "schemaVersion": "avatar_job_v1",
        "jobType": "avatar_generation",
        "jobId": "avatar_job_contract_123456",
        "uid": "user_contract_123456",
        "sourcePhotoIds": ["photo_contract_123456"],
        "sourcePhotoRefs": [
            "gs://seolleyeon-final-private-source-photos/users/user_contract_123456/source/photo_contract_123456.jpg"
        ],
        "candidateCount": 2,
        "modelId": model_id,
    }


def test_only_canonical_azure_model_is_accepted():
    parsed = parse_avatar_generation_payload(_payload(AZURE_GPT_IMAGE_2_MODEL_ID))
    assert parsed.model_id == AZURE_GPT_IMAGE_2_MODEL_ID
    with pytest.raises(AvatarGenerationError, match="canonical_azure_model_required"):
        parse_avatar_generation_payload(_payload("black-forest-labs/FLUX.2-klein-4B"))


def test_retired_model_adapter_is_not_importable():
    assert importlib.util.find_spec("avatar_generation.model_adapters.flux2_klein") is None


def test_current_worker_requirements_do_not_install_generation_model_runtime():
    requirements = (REPO_ROOT / "requirements_avatar_worker.txt").read_text(encoding="utf-8").lower()
    assert "diffusers" not in requirements


def test_current_deployment_sources_have_no_retired_generation_route():
    roots = [REPO_ROOT / "lib" / "ai_recommend_model" / "avatar_generation", REPO_ROOT / "scripts"]
    forbidden = (
        "black-forest-labs/flux",
        "flux.2-klein",
        "avatar_worker_mode=flux",
        'mode == "flux"',
        "local_cloud_run_flux",
    )
    offenders = []
    for root in roots:
        for path in root.rglob("*"):
            if path.suffix.lower() not in {".py", ".ps1", ".json", ".yaml", ".yml", ".toml", ".txt"}:
                continue
            source = path.read_text(encoding="utf-8", errors="ignore").lower()
            offenders.extend(
                f"{path.relative_to(REPO_ROOT)}:{token}" for token in forbidden if token in source
            )
    assert offenders == []


def test_preflight_rejects_stale_worker_mode_without_cloud_calls(monkeypatch):
    script = REPO_ROOT / "scripts" / "staging_avatar_live_preflight.py"
    spec = importlib.util.spec_from_file_location("avatar_live_preflight", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("AVATAR_WORKER_MODE", "flux")
    with pytest.raises(ValueError, match="canonical Azure"):
        module.validate_local_avatar_worker_mode(os.environ)
