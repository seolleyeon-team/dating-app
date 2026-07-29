from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from PIL import Image


@dataclass(frozen=True)
class AvatarQualityContext:
    """Process-local source/reference artifacts that must not be persisted."""

    generation_image: Image.Image | None = field(default=None, repr=False, compare=False)
    analysis_image: Image.Image | None = field(default=None, repr=False, compare=False)
    foreground_mask: Image.Image | None = field(default=None, repr=False, compare=False)
    face_hints: Sequence[Any] = field(default_factory=tuple, repr=False, compare=False)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def persisted_metadata(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in dict(self.metadata or {}).items()
            if not str(key).startswith("_")
        }
