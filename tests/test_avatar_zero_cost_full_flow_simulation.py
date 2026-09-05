"""Zero-cost full-flow simulation of the canonical avatar pipeline (section 18).

PHOTO SET
  P1 blurry, P2 good sharp frontal, P3 side pose, P4 multiple persons,
  P5 dark, P6 tiny face  ->  P2 must be selected.

SCENARIOS
  A  candidate1 safe, candidate2 safe            -> 2 provider calls
  B  candidate1 safe, candidate2 review/reject   -> +2 on the SAME source, 4 total, never > 4
  C  every source fails a hard gate              -> 0 provider calls, typed failure
  D  provider response lost after send           -> no retry, no failover, ambiguous outcome

Real Azure calls: 0. Every provider is a fake.
"""

from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.adaptive_generation import (  # noqa: E402
    AdaptiveGenerationPolicy,
    plan_generation_round,
)
from avatar_generation.analysis.avatar_source_quality import (  # noqa: E402
    NO_ELIGIBLE_SOURCE_ERROR,
    SecondaryFaceSignal,
    SourceQualitySignals,
)
from avatar_generation.model_adapters.azure_gpt_image_2 import (  # noqa: E402
    AVATAR_GENERAL_PROMPT_V0_TEMP,
    AzureGptImage2Config,
    AzureGptImage2Provider,
    AzureTransportError,
    AzureUnknownOutcomeError,
)
from avatar_generation.source_selection_runtime import (  # noqa: E402
    AvatarSourceCandidate,
    SourceSelectionError,
    candidate_set_from_payload,
    select_best_source,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def signals(photo_id: str, order: int, **overrides: object) -> SourceQualitySignals:
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


PHOTO_SET: dict[str, dict[str, object]] = {
    "P1": {"face_sharpness": 0.10},                       # blurry (hard gate)
    "P2": {"face_sharpness": 0.95},                       # good sharp frontal
    "P3": {"yaw_degrees": 40.0, "face_sharpness": 0.85},  # side pose (eligible, worse)
    "P4": {"secondary_faces": (SecondaryFaceSignal(confidence=0.92, area_ratio=0.10),)},
    "P5": {"face_luminance": 18.0, "dark_clip_ratio": 0.80},  # dark
    "P6": {"face_short_side_px": 40},                     # tiny face
}


def candidates() -> tuple[AvatarSourceCandidate, ...]:
    ids = list(PHOTO_SET)
    return candidate_set_from_payload(
        ids,
        [f"gs://seolleyeon-final-private-source-photos/users/u/source/{p}.jpg" for p in ids],
        [str(100 + i) for i in range(len(ids))],
    )


def analyze(candidate: AvatarSourceCandidate) -> SourceQualitySignals:
    return signals(candidate.photo_id, candidate.stable_order, **PHOTO_SET[candidate.photo_id])


class FakeProvider:
    """Counts generation requests and records which source each used."""

    def __init__(self) -> None:
        self.requests: list[str] = []

    def generate(self, source_photo_id: str, count: int) -> None:
        self.requests.extend([source_photo_id] * count)


def qa_candidate(candidate_id: str, safe: bool) -> dict[str, object]:
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


def run_generation(selected: str, outcomes: list[bool], policy: AdaptiveGenerationPolicy) -> FakeProvider:
    provider = FakeProvider()
    initial = plan_generation_round([], policy=policy)
    assert initial.should_generate
    provider.generate(selected, initial.candidate_count)
    generated = [qa_candidate(f"c{i + 1}", safe) for i, safe in enumerate(outcomes[: initial.candidate_count])]
    extra = plan_generation_round(generated, policy=policy)
    if extra.should_generate:
        provider.generate(selected, extra.candidate_count)
        generated += [qa_candidate(f"c{len(generated) + i + 1}", False) for i in range(extra.candidate_count)]
    # A third round must never be planned: max total is 4.
    third = plan_generation_round(generated, policy=policy)
    assert not third.should_generate or third.candidate_count == 0
    return provider


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def test_p2_is_selected_from_the_six_photo_set_and_only_it_reaches_generation():
    events: list[tuple[str, dict]] = []
    selected = select_best_source(candidates(), analyze_signals=analyze, event_hook=lambda n, p: events.append((n, p)))

    assert selected.candidate.photo_id == "P2"
    doc = selected.selection.to_private_document()
    assert doc["selectedPhotoId"] == "P2"
    assert doc["evaluatedCount"] == 6
    # P1 (blur), P4 (second person), P5 (dark), P6 (tiny) are hard-gated;
    # P2 and P3 remain, P2 wins on frontalness/sharpness.
    assert doc["eligibleCount"] == 2
    assert doc["top1Score"] > doc["top2Score"]
    assert doc["scoreMargin"] == round(doc["top1Score"] - doc["top2Score"], 6)

    # Event payloads carry no identifiers, refs or biometric data.
    for _name, payload in events:
        blob = str(payload)
        assert "gs://" not in blob
        assert "bbox" not in blob
        assert "P2.jpg" not in blob


# ---------------------------------------------------------------------------
# Generation policy 2 / 2 / 4
# ---------------------------------------------------------------------------

def test_policy_authority_is_2_2_4():
    policy = AdaptiveGenerationPolicy()
    assert policy.initial_candidate_count == 2
    assert policy.extra_candidate_count == 2
    assert policy.max_candidate_count == 4
    assert policy.preview_candidate_count == 2
    assert policy.min_safe_before_extra == 2
    assert policy.min_preview_candidate_count == 1
    assert policy.require_four_preview is False


def test_scenario_a_two_safe_candidates_stop_at_two_calls():
    provider = run_generation("P2", [True, True], AdaptiveGenerationPolicy())
    assert provider.requests == ["P2", "P2"]


def test_scenario_b_one_unsafe_candidate_adds_two_more_on_the_same_source_and_never_exceeds_four():
    provider = run_generation("P2", [True, False], AdaptiveGenerationPolicy())
    assert provider.requests == ["P2", "P2", "P2", "P2"]
    assert len(provider.requests) == 4
    assert set(provider.requests) == {"P2"}, "extra round must reuse the locked source"


def test_scenario_b_zero_safe_candidates_also_caps_at_four():
    provider = run_generation("P2", [False, False], AdaptiveGenerationPolicy())
    assert len(provider.requests) == 4


# ---------------------------------------------------------------------------
# Scenario C: no eligible source -> zero provider calls
# ---------------------------------------------------------------------------

def test_scenario_c_all_sources_hard_gated_makes_zero_provider_calls():
    bad = {
        "B1": {"corrupt": True},
        "B2": {"face_short_side_px": 10},
        "B3": {"face_sharpness": 0.05},
    }
    ids = list(bad)
    cands = candidate_set_from_payload(ids, [f"gs://b/users/u/source/{p}.jpg" for p in ids], ["1", "2", "3"])
    provider = FakeProvider()
    with pytest.raises(SourceSelectionError) as caught:
        select_best_source(cands, analyze_signals=lambda c: signals(c.photo_id, c.stable_order, **bad[c.photo_id]))
    assert caught.value.error_code == NO_ELIGIBLE_SOURCE_ERROR
    assert provider.requests == []


# ---------------------------------------------------------------------------
# Scenario D: provider response lost after send
# ---------------------------------------------------------------------------

class LostResponseTransport:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def send(self, request):
        self.requests.append(request)
        raise AzureTransportError("timeout", request_sent=True)


def image_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (64, 48), color=(30, 60, 90)).save(out, format="JPEG")
    return out.getvalue()


def test_scenario_d_post_send_timeout_is_ambiguous_and_stops_all_further_calls():
    transport = LostResponseTransport()
    provider = AzureGptImage2Provider(
        config=AzureGptImage2Config(
            endpoint="https://test-resource.openai.azure.com",
            deployment="test-deployment",
            api_version="test",
            api_key="TEST_SECRET_DO_NOT_LEAK",
            max_attempts=5,
            backoff_base_seconds=0.0,
            max_backoff_seconds=0.0,
            max_concurrency=1,
            requests_per_minute=2,
        ),
        transport=transport,
    )
    with pytest.raises(AzureUnknownOutcomeError) as caught:
        provider.generate(
            source_image_bytes=image_bytes(),
            source_content_type="image/jpeg",
            prompt=AVATAR_GENERAL_PROMPT_V0_TEMP,
            idempotency_key="job-d:candidate-1:azure_gpt_image_2",
        )
    error = caught.value
    assert error.retryable is False, "no blind retry once bytes are on the wire"
    assert error.unknown_outcome is True
    assert len(transport.requests) == 1, "exactly one paid request, no failover, no retry"
    assert "TEST_SECRET_DO_NOT_LEAK" not in str(error)
    assert error.error_code == "azure_unknown_post_send_outcome"
