from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from avatar_generation.adaptive_generation import (
    AdaptiveGenerationPolicy,
    plan_generation_round,
)
from avatar_generation.analysis.avatar_source_quality import (
    AvatarSourceQualitySelector,
    SecondaryFaceSignal,
    SourceQualitySignals,
)


@dataclass(frozen=True)
class SimulatedGenerationCase:
    provider_calls: int
    source_photo_ids: tuple[str, ...]


@dataclass(frozen=True)
class ZeroCostSimulationReport:
    selected_photo_id: str
    runner_up_photo_id: str
    top1_score: float
    top2_score: float
    score_margin: float
    selection_confidence: str
    initial_success: SimulatedGenerationCase
    extra_required: SimulatedGenerationCase
    real_azure_calls: int = 0


class _FakeProvider:
    def __init__(self) -> None:
        self.source_photo_ids: list[str] = []

    def generate(self, source_photo_id: str, count: int) -> None:
        self.source_photo_ids.extend([source_photo_id] * count)


def _source(photo_id: str, order: int, **overrides: object) -> SourceQualitySignals:
    values: dict[str, object] = {
        "photo_id": photo_id,
        "stable_order": order,
        "image_width": 1200,
        "image_height": 1600,
        "primary_face_confidence": 0.96,
        "primary_bbox": (0.28, 0.18, 0.44, 0.42),
        "face_short_side_px": 520,
        "face_sharpness": 0.90,
        "yaw_degrees": 4.0,
        "pitch_degrees": 2.0,
        "roll_degrees": 1.0,
        "illumination_quality": 0.90,
        "face_luminance": 128.0,
        "dark_clip_ratio": 0.01,
        "highlight_clip_ratio": 0.01,
        "face_visibility": 0.95,
        "occlusion_score": 0.05,
        "landmarks_reliable": True,
        "corrupt": False,
        "secondary_faces": (),
        "glasses_present": False,
    }
    values.update(overrides)
    return SourceQualitySignals(**values)  # type: ignore[arg-type]


def _qa_candidate(candidate_id: str, safe: bool) -> dict[str, object]:
    return {
        "candidateId": candidate_id,
        "status": "preview_ready" if safe else "rejected",
        "qa": {
            "previewAllowed": safe,
            "requiresHumanReview": False,
            "rejectReasons": [] if safe else ["simulation_rejected"],
            "adultQa": "pass" if safe else "fail",
            "privacyQa": "pass" if safe else "fail",
            "brandQa": "pass" if safe else "fail",
            "cropConsistency": "pass" if safe else "fail",
            "childlikeRisk": "low" if safe else "high",
            "beautificationRisk": "low" if safe else "high",
            "identifiabilityRisk": "low" if safe else "high",
            "uniqueMarkCopyRisk": "low" if safe else "high",
            "logoTextWatermarkRisk": "low" if safe else "high",
        },
    }


def _simulate_generation(
    selected_photo_id: str,
    safe_outcomes: Sequence[bool],
) -> SimulatedGenerationCase:
    policy = AdaptiveGenerationPolicy()
    provider = _FakeProvider()
    initial = plan_generation_round([], policy=policy)
    provider.generate(selected_photo_id, initial.candidate_count)
    candidates = [
        _qa_candidate(f"candidate_{index + 1}", safe)
        for index, safe in enumerate(safe_outcomes[: initial.candidate_count])
    ]
    extra = plan_generation_round(candidates, policy=policy)
    if extra.should_generate:
        provider.generate(selected_photo_id, extra.candidate_count)
    return SimulatedGenerationCase(
        provider_calls=len(provider.source_photo_ids),
        source_photo_ids=tuple(provider.source_photo_ids),
    )


def run_zero_cost_avatar_simulation() -> ZeroCostSimulationReport:
    sources = (
        _source("P1", 0, face_sharpness=0.25),
        _source("P2", 1, face_sharpness=0.92, yaw_degrees=30.0),
        _source("P3", 2, face_sharpness=0.96, illumination_quality=0.96),
        _source(
            "P4",
            3,
            secondary_faces=(SecondaryFaceSignal(confidence=0.92, area_ratio=0.10),),
        ),
        _source("P5", 4, face_luminance=20.0, dark_clip_ratio=0.75),
        _source("P6", 5, face_short_side_px=40),
    )
    selection = AvatarSourceQualitySelector().select(sources)
    if (
        selection.selected_photo_id is None
        or selection.runner_up_photo_id is None
        or selection.top1_score is None
        or selection.top2_score is None
        or selection.score_margin is None
        or selection.selection_confidence is None
    ):
        raise AssertionError("zero-cost source selection fixture is invalid")
    return ZeroCostSimulationReport(
        selected_photo_id=selection.selected_photo_id,
        runner_up_photo_id=selection.runner_up_photo_id,
        top1_score=selection.top1_score,
        top2_score=selection.top2_score,
        score_margin=selection.score_margin,
        selection_confidence=selection.selection_confidence,
        initial_success=_simulate_generation(
            selection.selected_photo_id,
            (True, True),
        ),
        extra_required=_simulate_generation(
            selection.selected_photo_id,
            (True, False),
        ),
    )


__all__ = [
    "SimulatedGenerationCase",
    "ZeroCostSimulationReport",
    "run_zero_cost_avatar_simulation",
]
