from __future__ import annotations

import os
from pathlib import Path


def openai_image_api_allowed() -> bool:
    return os.environ.get("ALLOW_OPENAI_IMAGE_API_FOR_AI_PROFILE") == "1"


class OpenAIImageClient:
    """Disabled compatibility shim.

    The Seolleyeon image pipeline now runs in Codex built-in `$imagegen` mode only.
    This class remains solely so legacy imports fail loudly instead of silently
    using an API path.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        if openai_image_api_allowed():
            raise RuntimeError(
                "ALLOW_OPENAI_IMAGE_API_FOR_AI_PROFILE=1 was set, but this compatibility shim still has no production route. "
                "Use a separately reviewed implementation; bounded executor routes do not call this client."
            )
        raise RuntimeError(
            "OpenAI Image API generation is disabled for this workflow. "
            "Use scripts/next_codex_imagegen_prompt_v3.py, built-in $imagegen, "
            "and scripts/recover_pending_imagegen_v3.py instead."
        )

    def generate(self, *, prompt: str) -> bytes:
        raise RuntimeError("OpenAI Image API generation is disabled; use Codex built-in $imagegen.")

    def edit_with_reference(self, *, prompt: str, reference_path: Path) -> bytes:
        raise RuntimeError("OpenAI Image API reference editing is disabled; use Codex built-in $imagegen.")
