from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol, Sequence


@dataclass(frozen=True)
class AvatarGenerationRequest:
    job_id: str
    uid: str
    source_photo_refs: Sequence[str]
    candidate_count: int = 4


@dataclass(frozen=True)
class GeneratedCandidate:
    candidate_id: str
    image_ref: str


class AvatarModelAdapter(Protocol):
    model_id: str
    version: str

    def generate_candidates(self, request: AvatarGenerationRequest) -> List[GeneratedCandidate]:
        ...
