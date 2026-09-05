import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.analysis.avatar_source_quality import (  # noqa: E402
    SecondaryFaceSignal,
    SourceQualitySignals,
)
from avatar_generation.source_selection_runtime import (  # noqa: E402
    NO_ELIGIBLE_SOURCE_ERROR,
    AvatarSourceCandidate,
    SourceSelectionError,
    candidate_set_from_payload,
    select_best_source,
    selected_source_from_job,
)


def _candidate(photo_id: str, order: int) -> AvatarSourceCandidate:
    return AvatarSourceCandidate(
        photo_id=photo_id,
        source_ref=f"gs://private/users/u1/source/{photo_id}.jpg",
        object_generation=str(100 + order),
        stable_order=order,
    )


def _signals(candidate: AvatarSourceCandidate, **overrides) -> SourceQualitySignals:
    values = dict(
        photo_id=candidate.photo_id,
        stable_order=candidate.stable_order,
        image_width=1200,
        image_height=1600,
        primary_face_confidence=0.96,
        primary_bbox=(0.28, 0.18, 0.44, 0.42),
        face_short_side_px=520,
        face_sharpness=0.90,
        yaw_degrees=4.0,
        pitch_degrees=2.0,
        roll_degrees=1.0,
        illumination_quality=0.90,
        face_luminance=128.0,
        dark_clip_ratio=0.01,
        highlight_clip_ratio=0.01,
        face_visibility=0.95,
        occlusion_score=0.05,
        landmarks_reliable=True,
        corrupt=False,
        secondary_faces=(),
    )
    values.update(overrides)
    return SourceQualitySignals(**values)


def test_candidate_payload_requires_two_to_six_parallel_generation_pins():
    candidates = candidate_set_from_payload(
        ["p1", "p2"],
        ["gs://private/users/u1/source/p1.jpg", "gs://private/users/u1/source/p2.jpg"],
        ["101", "102"],
    )
    assert [item.photo_id for item in candidates] == ["p1", "p2"]

    with pytest.raises(SourceSelectionError, match="candidate_contract_invalid"):
        candidate_set_from_payload(["p1", "p2"], ["one"], ["101", "102"])
    with pytest.raises(SourceSelectionError, match="candidate_generation_invalid"):
        candidate_set_from_payload(["p1", "p2"], ["one", "two"], ["101", "stale"])


def test_six_photo_simulation_selects_p3_then_p2_and_emits_privacy_safe_events():
    candidates = [_candidate(f"p{i}", i - 1) for i in range(1, 7)]
    events = []
    variants = {
        "p1": dict(face_sharpness=0.22),
        "p2": dict(yaw_degrees=34.0, face_sharpness=0.88),
        "p3": {},
        "p4": dict(secondary_faces=(SecondaryFaceSignal(0.9, 0.10),)),
        "p5": dict(face_luminance=20.0, dark_clip_ratio=0.8),
        "p6": dict(face_short_side_px=40),
    }

    selected = select_best_source(
        candidates,
        analyze_signals=lambda candidate: _signals(candidate, **variants[candidate.photo_id]),
        event_hook=lambda name, payload: events.append((name, payload)),
    )

    assert selected.candidate.photo_id == "p3"
    assert selected.selection.runner_up_photo_id == "p2"
    assert selected.selection.score_margin == pytest.approx(
        selected.selection.top1_score - selected.selection.top2_score
    )
    assert [name for name, _ in events] == [
        "avatar_source_selection_started",
        *(["avatar_source_photo_analyzed"] * 6),
        "avatar_source_selected",
    ]
    assert all("photoId" not in payload and "sourceRef" not in payload for _, payload in events)


def test_all_ineligible_is_typed_and_never_calls_generation_provider():
    candidates = [_candidate("p1", 0), _candidate("p2", 1)]
    provider_calls = 0

    with pytest.raises(SourceSelectionError) as caught:
        select_best_source(
            candidates,
            analyze_signals=lambda candidate: _signals(candidate, corrupt=True),
        )

    assert caught.value.error_code == NO_ELIGIBLE_SOURCE_ERROR
    assert provider_calls == 0


def test_persisted_selection_is_reused_without_rerunning_selector():
    candidates = [_candidate("p1", 0), _candidate("p2", 1)]
    calls = 0
    selected = selected_source_from_job(
        {
            "sourceSelection": {"status": "selected"},
            "selectedSource": {
                "photoId": "p2",
                "gcsUri": candidates[1].source_ref,
                "objectGeneration": candidates[1].object_generation,
            },
        },
        candidates,
    )
    assert selected == candidates[1]
    assert calls == 0


def test_persisted_source_id_or_generation_mismatch_fails_closed():
    candidates = [_candidate("p1", 0), _candidate("p2", 1)]
    with pytest.raises(SourceSelectionError, match="selected_source_generation_mismatch"):
        selected_source_from_job(
            {
                "sourceSelection": {"status": "selected"},
                "selectedSource": {
                    "photoId": "p2",
                    "gcsUri": candidates[1].source_ref,
                    "objectGeneration": "999",
                },
            },
            candidates,
        )
    with pytest.raises(SourceSelectionError, match="selected_source_id_mismatch"):
        selected_source_from_job(
            {
                "sourceSelection": {"status": "selected"},
                "selectedSource": {
                    "photoId": "forged",
                    "gcsUri": candidates[1].source_ref,
                    "objectGeneration": candidates[1].object_generation,
                },
            },
            candidates,
        )
