from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from avatar_generation import FLUX2_KLEIN_MODEL_ID, FLUX2_KLEIN_VERSION

FLUX2_KLEIN_ARTIFACT_REVISION = "e7b7dc27f91deacad38e78976d1f2b499d76a294"
DEFAULT_FLUX_WIDTH = 1024
DEFAULT_FLUX_HEIGHT = 1024
DEFAULT_FLUX_NUM_INFERENCE_STEPS = 4
DEFAULT_FLUX_GUIDANCE_SCALE = 1.0

_MUTABLE_REVISION_MARKERS = {
    "",
    "head",
    "latest",
    "main",
    "master",
    "dev",
    "develop",
    "stable",
    "current",
    "mutable",
}


@dataclass(frozen=True)
class Flux2KleinExecutionConfig:
    logical_model_id: str = FLUX2_KLEIN_MODEL_ID
    model_version: str = FLUX2_KLEIN_VERSION
    model_artifact_revision: str = FLUX2_KLEIN_ARTIFACT_REVISION
    width: int = DEFAULT_FLUX_WIDTH
    height: int = DEFAULT_FLUX_HEIGHT
    num_inference_steps: int = DEFAULT_FLUX_NUM_INFERENCE_STEPS
    guidance_scale: float = DEFAULT_FLUX_GUIDANCE_SCALE

    def generation_kwargs(self) -> dict[str, int | float]:
        return {
            "width": int(self.width),
            "height": int(self.height),
            "num_inference_steps": int(self.num_inference_steps),
            "guidance_scale": float(self.guidance_scale),
        }

    def audit(self, *, seed: int) -> dict[str, int | float | str]:
        return {
            "modelId": self.logical_model_id,
            "modelVersion": self.model_version,
            "modelArtifactRevision": self.model_artifact_revision,
            "width": int(self.width),
            "height": int(self.height),
            "numInferenceSteps": int(self.num_inference_steps),
            "guidanceScale": float(self.guidance_scale),
            "seed": int(seed),
        }


_ENV_SPECS: Mapping[str, tuple[str, tuple[str, ...], Any]] = {
    "logical_model_id": ("AVATAR_FLUX_MODEL_ID", ("MODEL_ID",), str),
    "model_version": ("AVATAR_FLUX_MODEL_VERSION", ("AVATAR_GENERATION_MODEL_VERSION",), str),
    "model_artifact_revision": (
        "AVATAR_FLUX_MODEL_ARTIFACT_REVISION",
        ("AVATAR_MODEL_ARTIFACT_REVISION", "MODEL_REVISION"),
        str,
    ),
    "width": ("AVATAR_FLUX_WIDTH", ("AVATAR_GENERATION_WIDTH",), int),
    "height": ("AVATAR_FLUX_HEIGHT", ("AVATAR_GENERATION_HEIGHT",), int),
    "num_inference_steps": (
        "AVATAR_FLUX_NUM_INFERENCE_STEPS",
        ("AVATAR_GENERATION_STEPS",),
        int,
    ),
    "guidance_scale": (
        "AVATAR_FLUX_GUIDANCE_SCALE",
        ("AVATAR_GENERATION_GUIDANCE_SCALE",),
        float,
    ),
}


def resolve_flux2_klein_execution_config(
    env: Mapping[str, str] | None = None,
) -> Flux2KleinExecutionConfig:
    values = Flux2KleinExecutionConfig().__dict__.copy()
    environment = env if env is not None else __import__("os").environ
    for field_name, (canonical_name, aliases, parser) in _ENV_SPECS.items():
        resolved = _resolve_env_value(
            environment,
            canonical_name=canonical_name,
            aliases=aliases,
            parser=parser,
        )
        if resolved is not None:
            values[field_name] = resolved
    config = Flux2KleinExecutionConfig(**values)
    _validate_flux2_klein_execution_config(config)
    return config


def build_flux2_klein_execution_audit(
    config: Flux2KleinExecutionConfig,
    *,
    seed: int,
) -> dict[str, int | float | str]:
    return config.audit(seed=seed)


def _resolve_env_value(
    env: Mapping[str, str],
    *,
    canonical_name: str,
    aliases: tuple[str, ...],
    parser: Any,
) -> Any | None:
    present = [name for name in (canonical_name, *aliases) if name in env]
    if not present:
        return None
    parsed: dict[str, Any] = {}
    for name in present:
        raw = env[name]
        if raw is None or str(raw).strip() == "":
            raise ValueError(f"{name} revision must not be empty" if "REVISION" in name else f"{name} must not be empty")
        parsed[name] = _parse_env_value(name, raw, parser)
    first_name = present[0]
    first_value = parsed[first_name]
    conflicts = [name for name in present[1:] if parsed[name] != first_value]
    if conflicts:
        joined = ", ".join((first_name, *conflicts))
        raise ValueError(f"Conflicting FLUX execution config values: {joined}")
    return first_value


def _parse_env_value(name: str, raw: str, parser: Any) -> Any:
    try:
        value = parser(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid FLUX execution config value for {name}") from exc
    if parser is int and int(value) <= 0:
        raise ValueError(f"{name} must be positive")
    if parser is float and float(value) <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _validate_flux2_klein_execution_config(config: Flux2KleinExecutionConfig) -> None:
    revision = str(config.model_artifact_revision or "").strip()
    if revision.lower() in _MUTABLE_REVISION_MARKERS:
        raise ValueError("FLUX model artifact revision must be immutable")
    if revision != FLUX2_KLEIN_ARTIFACT_REVISION:
        raise ValueError("FLUX model artifact revision is not allowlisted")
    if config.logical_model_id != FLUX2_KLEIN_MODEL_ID:
        raise ValueError("FLUX logical model id is not allowlisted")
    if config.model_version != FLUX2_KLEIN_VERSION:
        raise ValueError("FLUX model version is not allowlisted")