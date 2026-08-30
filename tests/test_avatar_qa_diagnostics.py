import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

import avatar_generation.qa_diagnostics as diagnostics  # noqa: E402


class _FakeProcessor:
    tokenizer = object()


class _FakeModel:
    def parameters(self):
        return iter([SimpleNamespace(device="cuda:0")])


class _FakeClipScorer:
    model_id = "/private/model/path"

    def _load_components(self):
        return _FakeProcessor(), _FakeModel()

    def score_prompt_groups(self, image, prompt_groups):
        return {"diagnostic": {"safe": 0.9, "unsafe": 0.1}}


class _FakeEncoder:
    provider = "clip"
    version = "openai/clip-vit-base-patch32@test"

    def _load_components(self):
        return _FakeProcessor(), _FakeModel()

    def encode_image(self, image):
        return (0.1, 0.2, 0.3)


class _FakeSimilarityAdapter:
    encoder = _FakeEncoder()


class _FakeArtifact:
    model_versions = {
        "clipSafety": "openai/clip-vit-large-patch14@large-revision",
        "faceSimilarity": "openai/clip-vit-base-patch32@base-revision",
    }

    def to_clip_policy(self):
        return SimpleNamespace(is_valid=True)

    @property
    def face_similarity(self):
        return {"threshold": 0.8, "reviewMargin": 0.1}


def test_runtime_diagnostics_reports_offline_clip_and_similarity_stages_without_paths(
    monkeypatch,
    tmp_path,
):
    model_root = tmp_path / "clip"
    model_root.mkdir()
    monkeypatch.setenv("AVATAR_CLIP_RISK_MODEL_ID", str(model_root))
    monkeypatch.setenv("AVATAR_QA_SIMILARITY_MODEL_ID", str(model_root))
    monkeypatch.setattr(diagnostics, "load_configured_calibration_artifact", lambda required=True: _FakeArtifact())
    monkeypatch.setattr(diagnostics, "get_default_clip_risk_scorer", lambda: _FakeClipScorer())
    monkeypatch.setattr(diagnostics, "get_default_similarity_adapter", lambda: _FakeSimilarityAdapter())
    monkeypatch.setattr(
        diagnostics,
        "get_qa_runtime_readiness",
        lambda: SimpleNamespace(to_document=lambda: {"ready": True}),
    )

    result = diagnostics.collect_qa_runtime_diagnostics()
    serialized = json.dumps(result, sort_keys=True)

    assert result["clipArtifactPresent"] is True
    assert result["clipTokenizerReady"] is True
    assert result["clipModelLoaded"] is True
    assert result["clipPromptEmbeddingsReady"] is True
    assert result["clipInferenceReady"] is True
    assert result["clipCalibrationLoaded"] is True
    assert result["faceSimilarityModelLoaded"] is True
    assert result["faceSimilarityInferenceReady"] is True
    assert result["faceSimilarityCalibrationLoaded"] is True
    assert result["sanitizedFailureCode"] == ""
    assert str(model_root).lower() not in serialized.lower()
