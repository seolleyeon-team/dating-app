from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence


FIDELITY_BANDS = frozenset({"low", "medium", "high", "unavailable"})
MODEL_AVAILABILITY_STATES = frozenset(
    {"available", "unavailable", "uncalibrated", "conflict"}
)
FIDELITY_COMPONENT_KEYS = (
    "broadVisual",
    "geometry",
    "traitConsistency",
    "composition",
    "adultNaturalness",
)
_FIDELITY_SCORE_FIELDS = (
    ("fidelity", "fidelity_score"),
    ("broadVisual", "broad_visual_score"),
    ("geometry", "geometry_score"),
    ("traitConsistency", "trait_consistency_score"),
    ("composition", "composition_score"),
    ("adultNaturalness", "adult_naturalness_score"),
)
FIDELITY_SCORE_KEYS = tuple(key for key, _ in _FIDELITY_SCORE_FIELDS)
FIDELITY_BAND_KEYS = (
    "fidelity",
    "traitConsistency",
    "composition",
)
FIDELITY_TIMING_KEYS = (*FIDELITY_COMPONENT_KEYS, "total")
FIDELITY_REASON_CODES = frozenset(
    {
        "candidate_not_resembling_source",
        "candidate_trait_mismatch",
        "candidate_generation_generic",
        "fidelity_signal_unavailable",
        "conflicting_fidelity_signals",
    }
)
LOWER_BOUND_DECISIONS = frozenset({"pass", "review", "reject"})
TRAIT_COVERAGE_STATES = frozenset({"sufficient", "mismatch", "unavailable"})

_SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:+-]{0,127}$")


@dataclass(frozen=True, repr=False)
class FidelitySignalBundle:
    """Process-local broad-fidelity observations.

    Numeric component scores are deliberately process-local ranking inputs.
    ``to_document`` persists only rounded broad scores, coarse bands,
    availability, model versions, and timings. Identity/face similarity is
    absent so it cannot become a positive fidelity or ranking feature.
    """

    fidelity_score: Optional[float] = field(default=None, repr=False)
    broad_visual_score: Optional[float] = field(default=None, repr=False)
    geometry_score: Optional[float] = field(default=None, repr=False)
    trait_consistency_score: Optional[float] = field(default=None, repr=False)
    composition_score: Optional[float] = field(default=None, repr=False)
    adult_naturalness_score: Optional[float] = field(default=None, repr=False)
    bands: Mapping[str, str] = field(default_factory=dict)
    model_availability: Mapping[str, str] = field(default_factory=dict)
    model_versions: Mapping[str, str] = field(default_factory=dict)
    timing_ms: Mapping[str, float] = field(default_factory=dict)
    trait_coverage_status: str = "unavailable"
    lower_bound_decision: str = "review"
    reason_codes: Sequence[str] = field(default_factory=tuple)
    conflicting: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "bands", MappingProxyType(dict(self.bands)))
        object.__setattr__(
            self,
            "model_availability",
            MappingProxyType(dict(self.model_availability)),
        )
        object.__setattr__(
            self,
            "model_versions",
            MappingProxyType(dict(self.model_versions)),
        )
        object.__setattr__(self, "timing_ms", MappingProxyType(dict(self.timing_ms)))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        decision = str(self.lower_bound_decision or "").strip().lower()
        object.__setattr__(
            self,
            "lower_bound_decision",
            decision if decision in LOWER_BOUND_DECISIONS else "review",
        )
        trait_coverage = str(self.trait_coverage_status or "").strip().lower()
        object.__setattr__(
            self,
            "trait_coverage_status",
            trait_coverage
            if trait_coverage in TRAIT_COVERAGE_STATES
            else "unavailable",
        )

    @classmethod
    def unavailable(
        cls,
        *,
        model_versions: Optional[Mapping[str, str]] = None,
        timing_ms: Optional[Mapping[str, float]] = None,
    ) -> "FidelitySignalBundle":
        return cls(
            bands={key: "unavailable" for key in FIDELITY_BAND_KEYS},
            model_availability={
                key: "unavailable" for key in FIDELITY_COMPONENT_KEYS
            },
            model_versions=model_versions or {},
            timing_ms=timing_ms or {},
            lower_bound_decision="review",
            reason_codes=("fidelity_signal_unavailable",),
        )

    @property
    def critical_signals_available(self) -> bool:
        return bool(
            self.trait_coverage_status == "sufficient"
            and all(
                _availability(self.model_availability.get(key)) == "available"
                for key in FIDELITY_COMPONENT_KEYS
            )
            and all(
                _band(self.bands.get(key)) != "unavailable"
                for key in FIDELITY_BAND_KEYS
            )
        )

    def ranking_vector(self) -> tuple[float, float, float, float, float, float]:
        """Return broad-only descending rank inputs.

        The vector has no identity input by construction. Missing/non-finite
        observations sort last without being converted into a pass signal.
        """

        return (
            _ranking_number(self.fidelity_score),
            _ranking_number(self.broad_visual_score),
            _ranking_number(self.geometry_score),
            _ranking_number(self.trait_consistency_score),
            _ranking_number(self.composition_score),
            _ranking_number(self.adult_naturalness_score),
        )

    def to_document(self) -> dict[str, object]:
        return {
            "scores": {
                key: round(number, 4)
                for key, attribute in _FIDELITY_SCORE_FIELDS
                if (number := _finite_number(getattr(self, attribute)))
                is not None
            },
            "bands": {
                key: _band(self.bands.get(key))
                for key in FIDELITY_BAND_KEYS
            },
            "modelAvailability": {
                key: _availability(self.model_availability.get(key))
                for key in FIDELITY_COMPONENT_KEYS
            },
            "modelVersions": {
                key: _safe_version(self.model_versions.get(key))
                for key in FIDELITY_COMPONENT_KEYS
                if self.model_versions.get(key) is not None
            },
            "timingMs": {
                key: _rounded_milliseconds(self.timing_ms.get(key))
                for key in FIDELITY_TIMING_KEYS
                if _finite_number(self.timing_ms.get(key)) is not None
            },
        }

    def __repr__(self) -> str:
        return f"FidelitySignalBundle({self.to_document()!r})"


def _band(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in FIDELITY_BANDS else "unavailable"


def _availability(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return (
        normalized
        if normalized in MODEL_AVAILABILITY_STATES
        else "unavailable"
    )


def _safe_version(value: Any) -> str:
    text = str(value or "").strip()
    if (
        not text
        or len(text) > 128
        or "\\" in text
        or ".." in text
        or "://" in text
        or not _SAFE_VERSION.fullmatch(text)
    ):
        return "unknown"
    return text


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _ranking_number(value: Any) -> float:
    number = _finite_number(value)
    return number if number is not None else float("-inf")


def _rounded_milliseconds(value: Any) -> float:
    number = _finite_number(value)
    if number is None:
        return 0.0
    return round(max(0.0, number), 3)


__all__ = [
    "FIDELITY_BANDS",
    "FIDELITY_BAND_KEYS",
    "FIDELITY_COMPONENT_KEYS",
    "FIDELITY_REASON_CODES",
    "FIDELITY_SCORE_KEYS",
    "FIDELITY_TIMING_KEYS",
    "FidelitySignalBundle",
    "LOWER_BOUND_DECISIONS",
    "MODEL_AVAILABILITY_STATES",
    "TRAIT_COVERAGE_STATES",
]
