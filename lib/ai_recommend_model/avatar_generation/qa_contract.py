"""Shared required/optional QA signal contract and coarse failure codes."""

from __future__ import annotations

from typing import Any, Mapping


REQUIRED_SIGNAL_ALIASES: dict[str, tuple[str, ...]] = {
    "face_detector": ("faceDetector",),
    "visual_risk": ("visualRisk",),
    "clip_safety": ("clipSafety", "localSafetyRisk", "clip"),
    "face_similarity": ("faceSimilarity",),
}
OPTIONAL_SIGNAL_NAMES = ("dino",)


def required_signal_failure_codes(availability: Mapping[str, Any]) -> tuple[str, ...]:
    """Return stable typed failures without retaining adapter exceptions."""

    normalized = {
        str(key).strip().lower(): str(value or "").strip().lower()
        for key, value in availability.items()
    }
    failures: list[str] = []
    for signal_name, aliases in REQUIRED_SIGNAL_ALIASES.items():
        status = _first_status(normalized, aliases)
        if status == "available":
            continue
        suffix = "uncalibrated" if status == "uncalibrated" else "unavailable"
        failures.append(f"{signal_name}_{suffix}")
    return tuple(failures)


def _first_status(normalized: Mapping[str, str], aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        value = normalized.get(alias.lower())
        if value:
            return value
    return "unavailable"


__all__ = [
    "OPTIONAL_SIGNAL_NAMES",
    "REQUIRED_SIGNAL_ALIASES",
    "required_signal_failure_codes",
]
