from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Mapping, Optional, Sequence

from avatar_generation.analysis.avatar_source_quality import (
    NO_ELIGIBLE_SOURCE_ERROR,
    SELECTOR_VERSION,
    AvatarSourceQualitySelector,
    AvatarSourceSelectionResult,
    SourceQualitySignals,
)


QUALITY_SELECTOR_MODE = "quality_selector_v1"
LEGACY_FIRST_PHOTO_MODE = "legacy_first_photo"
SOURCE_ANALYSIS_INFRA_ERROR = "avatar_source_analysis_infra_failure"


class SourceSelectionError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True)
class AvatarSourceCandidate:
    photo_id: str
    source_ref: str
    object_generation: str
    stable_order: int


@dataclass(frozen=True)
class SelectedAvatarSource:
    candidate: AvatarSourceCandidate
    selection: AvatarSourceSelectionResult


SelectionEventHook = Callable[[str, Mapping[str, Any]], None]


def candidate_set_from_payload(
    source_photo_ids: Sequence[str],
    source_photo_refs: Sequence[str],
    source_object_generations: Sequence[str],
    *,
    allow_locked_singleton: bool = False,
) -> tuple[AvatarSourceCandidate, ...]:
    minimum = 1 if allow_locked_singleton else 2
    if not (
        minimum <= len(source_photo_ids) <= 6
        and len(source_photo_ids) == len(source_photo_refs)
        and len(source_photo_ids) == len(source_object_generations)
    ):
        raise SourceSelectionError("avatar_source_candidate_contract_invalid")
    if len(set(source_photo_ids)) != len(source_photo_ids):
        raise SourceSelectionError("avatar_source_candidate_contract_invalid")
    candidates = []
    for order, (photo_id, source_ref, generation) in enumerate(
        zip(source_photo_ids, source_photo_refs, source_object_generations)
    ):
        normalized_generation = str(generation or "").strip()
        if not normalized_generation.isdigit():
            raise SourceSelectionError("avatar_source_candidate_generation_invalid")
        candidates.append(
            AvatarSourceCandidate(
                photo_id=str(photo_id or "").strip(),
                source_ref=str(source_ref or "").strip(),
                object_generation=normalized_generation,
                stable_order=order,
            )
        )
    return tuple(candidates)


def analysis_has_infrastructure_failure(analysis: Any) -> bool:
    metadata = getattr(analysis, "detector_metadata", None)
    return isinstance(metadata, Mapping) and (
        metadata.get("modelMissing") is True
        or metadata.get("runtimeFailure") is True
    )


def select_best_source(
    candidates: Sequence[AvatarSourceCandidate],
    *,
    analyze_signals: Callable[[AvatarSourceCandidate], SourceQualitySignals],
    event_hook: Optional[SelectionEventHook] = None,
) -> SelectedAvatarSource:
    started_at = perf_counter()
    _emit(
        event_hook,
        "avatar_source_selection_started",
        {"selectorVersion": SELECTOR_VERSION, "evaluatedCount": len(candidates)},
    )
    signals = []
    for candidate in candidates:
        signal = analyze_signals(candidate)
        signals.append(signal)
        evaluation = AvatarSourceQualitySelector().evaluate(signal)
        _emit(
            event_hook,
            "avatar_source_photo_analyzed",
            {
                "selectorVersion": SELECTOR_VERSION,
                "eligible": evaluation.eligible,
                "reasonCodes": list(evaluation.reason_codes),
            },
        )
    result = AvatarSourceQualitySelector().select(signals)
    latency_ms = round((perf_counter() - started_at) * 1000.0, 3)
    if result.selected_photo_id is None:
        _emit(
            event_hook,
            "avatar_source_selection_failed",
            {
                "selectorVersion": SELECTOR_VERSION,
                "evaluatedCount": result.evaluated_count,
                "eligibleCount": result.eligible_count,
                "reasonHistogram": dict(result.reason_histogram),
                "selectionLatencyMs": latency_ms,
                "errorCode": result.failure_code,
            },
        )
        raise SourceSelectionError(result.failure_code or NO_ELIGIBLE_SOURCE_ERROR)
    selected = next(
        (item for item in candidates if item.photo_id == result.selected_photo_id),
        None,
    )
    if selected is None:
        raise SourceSelectionError("avatar_selected_source_id_mismatch")
    _emit(
        event_hook,
        "avatar_source_selected",
        {
            "selectorVersion": result.selector_version,
            "evaluatedCount": result.evaluated_count,
            "eligibleCount": result.eligible_count,
            "selectedScore": result.top1_score,
            "scoreMargin": result.score_margin,
            "selectionConfidence": result.selection_confidence,
            "selectionLatencyMs": latency_ms,
        },
    )
    return SelectedAvatarSource(candidate=selected, selection=result)


def selected_source_from_job(
    job_doc: Mapping[str, Any],
    candidates: Sequence[AvatarSourceCandidate],
) -> Optional[AvatarSourceCandidate]:
    selection = job_doc.get("sourceSelection")
    if not isinstance(selection, Mapping) or selection.get("status") != "selected":
        return None
    selected = job_doc.get("selectedSource")
    if not isinstance(selected, Mapping):
        raise SourceSelectionError("avatar_selected_source_id_mismatch")
    photo_id = str(selected.get("photoId") or "").strip()
    candidate = next((item for item in candidates if item.photo_id == photo_id), None)
    if candidate is None:
        raise SourceSelectionError("avatar_selected_source_id_mismatch")
    if str(selected.get("gcsUri") or "").strip() != candidate.source_ref:
        raise SourceSelectionError("avatar_selected_source_ref_mismatch")
    if (
        str(selected.get("objectGeneration") or "").strip()
        != candidate.object_generation
    ):
        raise SourceSelectionError("avatar_selected_source_generation_mismatch")
    return candidate


def _emit(
    hook: Optional[SelectionEventHook],
    name: str,
    payload: Mapping[str, Any],
) -> None:
    if hook is not None:
        hook(name, dict(payload))


__all__ = [
    "LEGACY_FIRST_PHOTO_MODE",
    "NO_ELIGIBLE_SOURCE_ERROR",
    "QUALITY_SELECTOR_MODE",
    "SOURCE_ANALYSIS_INFRA_ERROR",
    "AvatarSourceCandidate",
    "SelectedAvatarSource",
    "SourceSelectionError",
    "analysis_has_infrastructure_failure",
    "candidate_set_from_payload",
    "select_best_source",
    "selected_source_from_job",
]
