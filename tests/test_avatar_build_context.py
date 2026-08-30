"""Static build-context regression for the canonical avatar worker image.

Guards against the historical failure class where source tests pass but a
runtime module is missing from the container image (ModuleNotFoundError after
deploy). No image is built here; this only checks the build recipe and the
presence of every canonical runtime module inside the copied context.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AG = REPO_ROOT / "lib" / "ai_recommend_model" / "avatar_generation"
DOCKERFILE = AG / "Dockerfile"

REQUIRED_RUNTIME_FILES = [
    "worker.py",
    "worker_service.py",
    "qa.py",
    "qa_signals.py",
    "qa_runtime.py",
    "qa_contract.py",
    "qa_preflight.py",
    "qa_diagnostics.py",
    "preview_policy.py",
    "trait_policy.py",
    "unique_mark_policy.py",
    "avatar_prompt_contract.py",
    "analysis/watermark.py",
    "analysis/visual_risk.py",
    "model_adapters/azure_contracts.py",
    "model_adapters/azure_gpt_image_2.py",
    "model_adapters/azure_rate_limit.py",
    "model_adapters/azure_transport.py",
    "artifacts/avatar_qa_calibration_v1.json",
]


def test_dockerfile_copies_the_whole_model_tree():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY lib/ai_recommend_model /app" in text


def test_dockerfile_defaults_to_canonical_azure_mode():
    text = DOCKERFILE.read_text(encoding="utf-8")
    assert "AVATAR_WORKER_MODE=azure_gpt_image_2" in text


def test_every_canonical_runtime_module_exists_in_build_context():
    missing = [rel for rel in REQUIRED_RUNTIME_FILES if not (AG / rel).is_file()]
    assert missing == []
