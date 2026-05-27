from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from avatar_generation import FLUX2_KLEIN_MODEL_ID, FLUX2_KLEIN_VERSION
from avatar_generation.model_adapters.base import (
    AvatarGenerationRequest,
    GeneratedCandidate,
)
from avatar_generation.seolleyeon_avatar_prompt_builder_v4 import build_avatar_prompt
from avatar_generation.storage import build_temp_candidate_ref
from avatar_generation.worker import (
    AvatarGenerationError,
    Flux2KleinImageGenerator,
    _default_storage_client,
    deterministic_seed,
    image_to_png_bytes,
    load_source_image_from_gcs,
    parse_gcs_uri,
    prepare_privacy_reference_image,
)


class Flux2KleinAdapter:
    """Interface wrapper for the local GPU worker running FLUX.2-klein-4B."""

    model_id = FLUX2_KLEIN_MODEL_ID
    version = FLUX2_KLEIN_VERSION

    def __init__(
        self,
        *,
        storage_client: Any = None,
        image_generator: Optional[Flux2KleinImageGenerator] = None,
        fixture_output_dir: Optional[Path] = None,
        gcp_project: Optional[str] = None,
    ) -> None:
        self._storage_client = storage_client
        self._image_generator = image_generator
        self._fixture_output_dir = fixture_output_dir
        self._gcp_project = gcp_project

    def _storage(self) -> Any:
        if self._storage_client is None:
            self._storage_client = _default_storage_client(self._gcp_project)
        return self._storage_client

    def _generator(self) -> Flux2KleinImageGenerator:
        if self._image_generator is None:
            self._image_generator = Flux2KleinImageGenerator(self.model_id)
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

        image_ref = parse_gcs_uri(candidate.image_ref)
        blob = self._storage().bucket(image_ref.bucket).blob(image_ref.path)
        blob.upload_from_string(
            image_bytes,
            content_type="image/png",
            predefined_acl=None,
        )
        if hasattr(blob, "patch"):
            blob.cache_control = "private, max-age=0, no-store"
            blob.patch()

    def generate_candidates(self, request: AvatarGenerationRequest) -> List[GeneratedCandidate]:
        if not request.source_photo_refs:
            raise AvatarGenerationError("At least one source photo ref is required for FLUX generation.")

        source_ref = parse_gcs_uri(request.source_photo_refs[0])
        source_image = load_source_image_from_gcs(self._storage(), source_ref)
        privacy_reference_image = prepare_privacy_reference_image(source_image)
        candidates = self.plan_candidate_refs(request)
        generator = self._generator()

        for index, candidate in enumerate(candidates):
            seed = deterministic_seed(request.job_id, index)
            prompt = build_avatar_prompt(
                candidate_index=index,
                candidate_count=int(request.candidate_count),
                seed=seed,
            )
            image = generator.generate(
                source_image=privacy_reference_image,
                prompt=prompt.positive,
                avoid_prompt=prompt.provider_negative or prompt.negative,
                seed=seed,
            )
            self._persist_candidate(candidate, image_to_png_bytes(image))
        return candidates
