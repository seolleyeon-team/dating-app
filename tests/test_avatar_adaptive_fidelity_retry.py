import copy
import sys
from pathlib import Path

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.adaptive_generation import (  # noqa: E402
    AdaptiveGenerationPolicy,
    GenerationBudget,
    plan_generation_round,
)


def _candidate(candidate_id, *, reasons=(), corridor_reasons=(), status="rejected", scores=None):
    qa = {
        "previewAllowed": False,
        "requiresHumanReview": True,
        "rejectReasons": list(reasons),
    }
    if corridor_reasons:
        qa["fidelityCorridor"] = {"reasonCodes": list(corridor_reasons)}
    return {
        "candidateId": candidate_id,
        "status": status,
        "qa": qa,
        "scores": dict(scores or {}),
    }


def _systemic_candidate(candidate_id):
    return {
        "candidateId": candidate_id,
        "status": "needs_review",
        "qa": {
            "previewAllowed": False,
            "requiresHumanReview": True,
            "rejectReasons": [],
            "qaVersion": "avatar_qa_v1_model_unavailable",
            "reviewReasons": ["model_unavailable"],
        },
    }


def test_first_round_systemic_unavailable_keeps_existing_suppression():
    candidates = [_systemic_candidate(f"unavailable_{idx}") for idx in range(4)]

    plan = plan_generation_round(candidates, policy=AdaptiveGenerationPolicy())

    assert plan.should_generate is False
    assert plan.candidate_count == 0
    assert plan.reason == "extra_suppressed_systemic_unavailable"
    assert plan.blocked_reasons == ("qa_critical_model_unavailable",)


def test_all_fidelity_corridor_failures_plan_one_time_fidelity_retry_without_mutation():
    candidates = [
        _candidate(
            "generic",
            corridor_reasons=["candidate_generation_generic"],
            scores={"identitySimilarityScore": 0.99},
        ),
        _candidate("trait", corridor_reasons=["candidate_trait_mismatch"]),
        _candidate("resemblance", corridor_reasons=["candidate_not_resembling_source"]),
    ]
    before = copy.deepcopy(candidates)
    policy = AdaptiveGenerationPolicy(extra_candidate_count=4, max_candidate_count=8)

    default_plan = plan_generation_round(candidates, policy=policy)
    assert default_plan.should_generate is True
    assert default_plan.candidate_count == 4
    assert default_plan.reason == "extra_insufficient_safe"

    plan = plan_generation_round(
        candidates,
        policy=policy,
        adaptive_retry_enabled=True,
    )

    assert plan.should_generate is True
    assert plan.candidate_count == 4
    assert plan.reason == "fidelity_adjusted_retry"
    assert plan.total_after_generation == 7
    assert candidates == before


def test_all_privacy_failures_plan_privacy_strengthened_retry_with_capacity_cap():
    candidates = [
        _candidate(f"private_{idx}", reasons=["candidate_too_identifiable"])
        for idx in range(6)
    ]

    plan = plan_generation_round(
        candidates,
        policy=AdaptiveGenerationPolicy(extra_candidate_count=4, max_candidate_count=8),
        adaptive_retry_enabled=True,
    )

    assert plan.should_generate is True
    assert plan.candidate_count == 2
    assert plan.reason == "privacy_strengthened_retry"
    assert plan.total_after_generation == 8


def test_mixed_candidate_specific_failures_use_existing_bounded_extra():
    candidates = [
        _candidate("fidelity", corridor_reasons=["candidate_trait_mismatch"]),
        _candidate("privacy", reasons=["candidate_too_identifiable"]),
    ]

    plan = plan_generation_round(
        candidates,
        policy=AdaptiveGenerationPolicy(extra_candidate_count=4, max_candidate_count=5),
    )

    assert plan.should_generate is True
    assert plan.candidate_count == 3
    assert plan.reason == "extra_insufficient_safe"


def test_target_retry_reasons_mixed_with_other_failures_fall_back_to_bounded_extra():
    candidates = [
        _candidate(
            "leak",
            reasons=["candidate_trait_mismatch", "candidate_privacy_leak"],
        ),
        _candidate("generic", corridor_reasons=["candidate_generation_generic"]),
    ]

    plan = plan_generation_round(
        candidates,
        policy=AdaptiveGenerationPolicy(extra_candidate_count=4, max_candidate_count=8),
        adaptive_retry_enabled=True,
    )

    assert plan.should_generate is True
    assert plan.candidate_count == 4
    assert plan.reason == "extra_insufficient_safe"


def test_retry_attempt_one_blocks_additional_adaptive_retry():
    candidates = [
        _candidate("generic", corridor_reasons=["candidate_generation_generic"]),
        _candidate("trait", corridor_reasons=["candidate_trait_mismatch"]),
    ]

    plan = plan_generation_round(
        candidates,
        policy=AdaptiveGenerationPolicy(),
        retry_attempt=1,
        adaptive_retry_enabled=True,
    )

    assert plan.should_generate is False
    assert plan.candidate_count == 0
    assert plan.reason == "retry_limit_reached"
    assert plan.blocked_reasons == ("retry_limit_reached",)


def test_retry_plan_uses_existing_candidate_budget_deadline_and_usd_caps():
    candidates = [
        _candidate("generic", corridor_reasons=["candidate_generation_generic"]),
        _candidate("trait", corridor_reasons=["candidate_trait_mismatch"]),
    ]
    policy = AdaptiveGenerationPolicy(extra_candidate_count=4, max_candidate_count=8)

    candidate_capped = plan_generation_round(
        candidates,
        policy=policy,
        budget=GenerationBudget(remaining_candidate_budget=1),
        adaptive_retry_enabled=True,
    )
    assert candidate_capped.reason == "fidelity_adjusted_retry"
    assert candidate_capped.candidate_count == 1

    deadline_blocked = plan_generation_round(
        candidates,
        policy=policy,
        budget=GenerationBudget(remaining_deadline_seconds=4, min_extra_round_seconds=5),
        adaptive_retry_enabled=True,
    )
    assert deadline_blocked.should_generate is False
    assert deadline_blocked.reason == "budget_blocked"
    assert deadline_blocked.blocked_reasons == ("deadline_insufficient",)

    usd_blocked = plan_generation_round(
        candidates,
        policy=policy,
        budget=GenerationBudget(remaining_usd=0.49, estimated_usd_per_candidate=0.5),
        adaptive_retry_enabled=True,
    )
    assert usd_blocked.should_generate is False
    assert usd_blocked.reason == "budget_blocked"
    assert usd_blocked.blocked_reasons == ("cost_budget_insufficient",)