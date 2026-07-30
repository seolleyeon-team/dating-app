import sys
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.flux_config import (
    FLUX2_KLEIN_ARTIFACT_REVISION,
    Flux2KleinExecutionConfig,
    build_flux2_klein_execution_audit,
    resolve_flux2_klein_execution_config,
)
from avatar_generation.model_adapters.base import AvatarGenerationRequest
from avatar_generation.model_adapters.flux2_klein import Flux2KleinAdapter


class _Blob:
    def __init__(self, image=None):
        self.image = image
        self.uploads = []
        self.cache_control = None

    def download_as_bytes(self):
        import io

        buffer = io.BytesIO()
        self.image.save(buffer, format="PNG")
        return buffer.getvalue()

    def upload_from_string(self, data, **kwargs):
        self.uploads.append((data, kwargs))

    def patch(self):
        pass


class _Bucket:
    def __init__(self, source_blob):
        self.source_blob = source_blob
        self.uploaded = {}

    def blob(self, path):
        if path.endswith("source/src.png"):
            return self.source_blob
        blob = self.uploaded.setdefault(path, _Blob())
        return blob


class _Storage:
    def __init__(self):
        self.bucket_obj = _Bucket(_Blob(Image.new("RGB", (32, 32), (120, 80, 60))))

    def bucket(self, name):
        return self.bucket_obj


class _ConfigAwareGenerator:
    def __init__(self):
        self.calls = []

    def generate(
        self,
        *,
        source_image,
        prompt,
        avoid_prompt,
        seed,
        width,
        height,
        num_inference_steps,
        guidance_scale,
    ):
        self.calls.append(dict(locals()))
        return Image.new("RGB", (16, 16), (seed % 255, 10, 20))


class _LegacySignatureGenerator:
    def __init__(self):
        self.calls = []

    def generate(self, *, source_image, prompt, avoid_prompt, seed):
        import os

        self.calls.append(
            {
                "seed": seed,
                "width_env": os.environ.get("AVATAR_GENERATION_WIDTH"),
                "height_env": os.environ.get("AVATAR_GENERATION_HEIGHT"),
                "steps_env": os.environ.get("AVATAR_GENERATION_STEPS"),
                "guidance_env": os.environ.get("AVATAR_GENERATION_GUIDANCE_SCALE"),
            }
        )
        return Image.new("RGB", (16, 16), (seed % 255, 30, 40))


def _request(count=1):
    return AvatarGenerationRequest(
        job_id="avatar_flux_config_job",
        uid="uid_flux",
        source_photo_refs=["gs://private-source/users/u/source/src.png"],
        candidate_count=count,
    )


def test_flux_config_defaults_are_frozen_and_revision_pinned():
    config = resolve_flux2_klein_execution_config({})

    assert config == Flux2KleinExecutionConfig()
    assert config.model_artifact_revision == FLUX2_KLEIN_ARTIFACT_REVISION
    assert config.num_inference_steps == 4
    assert config.guidance_scale == 1.0
    with pytest.raises(Exception):
        config.width = 512  # type: ignore[misc]


def test_canonical_and_legacy_aliases_match_or_fail_closed():
    config = resolve_flux2_klein_execution_config(
        {
            "AVATAR_FLUX_NUM_INFERENCE_STEPS": "6",
            "AVATAR_GENERATION_STEPS": "6",
            "AVATAR_FLUX_GUIDANCE_SCALE": "1.25",
            "AVATAR_GENERATION_GUIDANCE_SCALE": "1.25",
            "AVATAR_FLUX_WIDTH": "768",
            "AVATAR_GENERATION_WIDTH": "768",
        }
    )

    assert config.num_inference_steps == 6
    assert config.guidance_scale == 1.25
    assert config.width == 768

    with pytest.raises(ValueError, match="Conflicting FLUX"):
        resolve_flux2_klein_execution_config(
            {
                "AVATAR_FLUX_NUM_INFERENCE_STEPS": "4",
                "AVATAR_GENERATION_STEPS": "8",
            }
        )


def test_empty_or_mutable_or_unallowlisted_revision_fails_closed():
    for revision in ("", "main", "latest", "HEAD", "stable"):
        with pytest.raises(ValueError, match="revision"):
            resolve_flux2_klein_execution_config({"AVATAR_FLUX_MODEL_ARTIFACT_REVISION": revision})

    with pytest.raises(ValueError, match="allowlisted"):
        resolve_flux2_klein_execution_config({"AVATAR_FLUX_MODEL_ARTIFACT_REVISION": "0" * 40})


def test_adapter_passes_same_resolved_config_and_seed_to_execution_and_audit():
    generator = _ConfigAwareGenerator()
    config = Flux2KleinExecutionConfig(width=640, height=768, num_inference_steps=5, guidance_scale=1.5)
    adapter = Flux2KleinAdapter(
        image_generator=generator,
        execution_config=config,
    )

    adapter._generate_with_execution_config(
        generator,
        source_image=Image.new("RGB", (32, 32)),
        prompt="safe positive prompt",
        avoid_prompt="avoid folded terms",
        seed=12345,
    )

    call = generator.calls[0]
    audit = adapter.execution_audit(seed=12345)
    assert call["width"] == audit["width"] == 640
    assert call["height"] == audit["height"] == 768
    assert call["num_inference_steps"] == audit["numInferenceSteps"] == 5
    assert call["guidance_scale"] == audit["guidanceScale"] == 1.5
    assert call["seed"] == audit["seed"]
    assert audit["modelArtifactRevision"] == FLUX2_KLEIN_ARTIFACT_REVISION
    assert "negative_prompt" not in call


def test_adapter_bridges_config_to_legacy_generator_env_without_leaking(monkeypatch):
    monkeypatch.setenv("AVATAR_GENERATION_WIDTH", "111")
    generator = _LegacySignatureGenerator()
    config = Flux2KleinExecutionConfig(width=704, height=832, num_inference_steps=7, guidance_scale=1.75)
    adapter = Flux2KleinAdapter(
        image_generator=generator,
        execution_config=config,
    )

    adapter._generate_with_execution_config(
        generator,
        source_image=Image.new("RGB", (32, 32)),
        prompt="safe positive prompt",
        avoid_prompt="avoid folded terms",
        seed=67890,
    )

    assert generator.calls[0]["width_env"] == "704"
    assert generator.calls[0]["height_env"] == "832"
    assert generator.calls[0]["steps_env"] == "7"
    assert generator.calls[0]["guidance_env"] == "1.75"
    import os

    assert os.environ["AVATAR_GENERATION_WIDTH"] == "111"
    assert "AVATAR_GENERATION_HEIGHT" not in os.environ


def test_execution_audit_is_allowlisted_and_contains_no_source_prompt_or_hash_material():
    audit = build_flux2_klein_execution_audit(Flux2KleinExecutionConfig(), seed=123)

    assert set(audit) == {
        "modelId",
        "modelVersion",
        "modelArtifactRevision",
        "width",
        "height",
        "numInferenceSteps",
        "guidanceScale",
        "seed",
    }
    forbidden_fragments = ("prompt", "image", "trait", "source", "reference", "hash")
    for key in audit:
        assert all(fragment.lower() not in key.lower() for fragment in forbidden_fragments)