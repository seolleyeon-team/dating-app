from __future__ import annotations

import inspect
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, List, Mapping, Optional

from avatar_generation import FLUX2_KLEIN_MODEL_ID, FLUX2_KLEIN_VERSION
from avatar_generation.flux_config import (
    Flux2KleinExecutionConfig,
    build_flux2_klein_execution_audit,
    resolve_flux2_klein_execution_config,
)
from avatar_generation.model_adapters.base import (
    AvatarGenerationRequest,
    GeneratedCandidate,
)
from avatar_generation.seolleyeon_avatar_prompt_builder_v4 import build_avatar_prompt
from avatar_generation.storage import build_temp_candidate_ref



class Flux2KleinAdapter:
    """Interface wrapper for the local GPU worker running FLUX.2-klein-4B."""

    model_id = FLUX2_KLEIN_MODEL_ID
    version = FLUX2_KLEIN_VERSION

    def __init__(
        self,
        *,
        storage_client: Any = None,
        image_generator: Optional[Any] = None,
        fixture_output_dir: Optional[Path] = None,
        gcp_project: Optional[str] = None,
        execution_config: Flux2KleinExecutionConfig | None = None,
    ) -> None:
        self._execution_config = execution_config or resolve_flux2_klein_execution_config()
        self.model_id = self._execution_config.logical_model_id
        self.version = self._execution_config.model_version
        self.generation_audits: dict[str, dict[str, int | float | str]] = {}
        self._storage_client = storage_client
        self._image_generator = image_generator
        self._fixture_output_dir = fixture_output_dir
        self._gcp_project = gcp_project

    def _storage(self) -> Any:
        if self._storage_client is None:
            self._storage_client = _worker_attr("_default_storage_client")(self._gcp_project)
        return self._storage_client

    def _generator(self) -> Any:
        if self._image_generator is None:
            self._image_generator = _worker_attr("get_flux2_klein_generator")(
                self._execution_config.logical_model_id,
                config=self._execution_config,
            )
        return self._image_generator

    def plan_candidate_refs(self, request: AvatarGenerationRequest) -> List[GeneratedCandidate]:
        return [
            GeneratedCandidate(
                candidate_id=f"cand_{index + 1:02d}",
                image_ref=build_temp_candidate_ref(
                    uid=request.uid,
                    job_id=request.job_id,
                    candidate_id=f"cand_{index + 1:02d}",
                ),
            )
            for index in range(int(request.candidate_count))
        ]

    def _persist_candidate(self, candidate: GeneratedCandidate, image_bytes: bytes) -> None:
        if self._fixture_output_dir is not None:
            self._fixture_output_dir.mkdir(parents=True, exist_ok=True)
            (self._fixture_output_dir / f"{candidate.candidate_id}.png").write_bytes(image_bytes)
            return

        image_ref = _worker_attr("parse_gcs_uri")(candidate.image_ref)
        blob = self._storage().bucket(image_ref.bucket).blob(image_ref.path)
        blob.upload_from_string(
            image_bytes,
            content_type="image/png",
            predefined_acl=None,
        )
        if hasattr(blob, "patch"):
            blob.cache_control = "private, max-age=0, no-store"
            blob.patch()

    def execution_config(self) -> Flux2KleinExecutionConfig:
        return self._execution_config

    def execution_audit(self, *, seed: int) -> dict[str, int | float | str]:
        return build_flux2_klein_execution_audit(self._execution_config, seed=seed)
    def _generate_with_execution_config(
        self,
        generator: Flux2KleinImageGenerator,
        *,
        source_image: Any,
        prompt: str,
        avoid_prompt: str,
        seed: int,
    ) -> Any:
        base_kwargs: dict[str, Any] = {
            "source_image": source_image,
            "prompt": prompt,
            "avoid_prompt": avoid_prompt,
            "seed": seed,
        }
        execution_kwargs = self._execution_config.generation_kwargs()
        supported_execution_kwargs = _supported_kwargs(generator.generate, execution_kwargs)
        if supported_execution_kwargs:
            return generator.generate(**base_kwargs, **supported_execution_kwargs)
        with _temporary_flux_generation_env(self._execution_config):
            return generator.generate(**base_kwargs)
    def generate_candidates(self, request: AvatarGenerationRequest) -> List[GeneratedCandidate]:
        if not request.source_photo_refs:
            raise _worker_attr("AvatarGenerationError")("At least one source photo ref is required for FLUX generation.")

        source_ref = _worker_attr("parse_gcs_uri")(request.source_photo_refs[0])
        source_image = _worker_attr("load_source_image_from_gcs")(self._storage(), source_ref)
        privacy_reference_image = _worker_attr("prepare_privacy_reference_image")(source_image)
        candidates = self.plan_candidate_refs(request)
        generator = self._generator()

        for index, candidate in enumerate(candidates):
            seed = _worker_attr("deterministic_seed")(request.job_id, index)
            prompt = build_avatar_prompt(
                candidate_index=index,
                candidate_count=int(request.candidate_count),
                seed=seed,
            )
            image = self._generate_with_execution_config(
                generator,
                source_image=privacy_reference_image,
                prompt=prompt.positive,
                avoid_prompt=prompt.provider_negative or prompt.negative,
                seed=seed,
            )
            self.generation_audits[candidate.candidate_id] = self.execution_audit(seed=seed)
            self._persist_candidate(candidate, _worker_attr("image_to_png_bytes")(image))
        return candidates


def _supported_kwargs(callable_obj: Any, kwargs: Mapping[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return {}
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return dict(kwargs)
    return {
        key: value
        for key, value in kwargs.items()
        if key in signature.parameters
    }


@contextmanager
def _temporary_flux_generation_env(config: Flux2KleinExecutionConfig) -> Iterator[None]:
    updates = {
        "AVATAR_GENERATION_WIDTH": str(config.width),
        "AVATAR_GENERATION_HEIGHT": str(config.height),
        "AVATAR_GENERATION_STEPS": str(config.num_inference_steps),
        "AVATAR_GENERATION_GUIDANCE_SCALE": str(config.guidance_scale),
    }
    previous = {key: os.environ.get(key) for key in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

def _worker_attr(name: str) -> Any:
    from avatar_generation import worker

    return getattr(worker, name)