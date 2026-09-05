import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = REPO_ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from avatar_generation.admission_policy import (
    DEFAULT_EXTRA_CANDIDATE_COUNT,
    DEFAULT_INITIAL_CANDIDATE_COUNT,
    DEFAULT_MAX_TOTAL_CANDIDATES,
    AdmissionPolicy,
    AdmissionRequest,
    CumulativeUsage,
    evaluate_admission,
)


def test_admission_defaults_follow_canonical_two_two_four_policy():
    policy = AdmissionPolicy()

    assert DEFAULT_INITIAL_CANDIDATE_COUNT == 2
    assert DEFAULT_EXTRA_CANDIDATE_COUNT == 2
    assert DEFAULT_MAX_TOTAL_CANDIDATES == 4
    assert policy.initial_candidate_count == 2
    assert policy.extra_candidate_count == 2
    assert policy.max_total_candidates == 4


def _policy(**overrides):
    values = {
        "initial_candidate_count": 4,
        "extra_candidate_count": 4,
        "max_total_candidates": 8,
        "max_retry_attempts": 3,
        "min_initial_deadline_seconds": 20,
        "min_extra_deadline_seconds": 30,
        "estimated_usd_per_candidate": 1.25,
        "hard_daily_generation_limit": 10,
        "hard_monthly_generation_limit": 100,
        "hard_daily_usd_limit": 10.0,
        "hard_monthly_usd_limit": 50.0,
        "enforce_budget": True,
    }
    values.update(overrides)
    return AdmissionPolicy(**values)


def test_initial_admission_projects_candidate_cost_against_daily_budget():
    decision = evaluate_admission(
        AdmissionRequest(
            phase="initial",
            existing_candidate_count=0,
            retry_attempt=0,
            remaining_deadline_seconds=30,
            usage=CumulativeUsage(daily_count=1, monthly_count=1, daily_usd=6.0, monthly_usd=6.0),
        ),
        policy=_policy(),
    )

    assert decision.allowed is False
    assert decision.reason == "daily_budget_exceeded"
    assert decision.candidate_count == 0
    assert decision.projected_daily_usd == 11.0


def test_extra_admission_uses_remaining_candidates_and_canonical_deadline():
    short_deadline = evaluate_admission(
        AdmissionRequest(
            phase="extra",
            existing_candidate_count=4,
            retry_attempt=1,
            remaining_deadline_seconds=29,
            usage=CumulativeUsage(),
        ),
        policy=_policy(),
    )
    admitted = evaluate_admission(
        AdmissionRequest(
            phase="extra",
            existing_candidate_count=6,
            retry_attempt=1,
            remaining_deadline_seconds=30,
            usage=CumulativeUsage(),
        ),
        policy=_policy(),
    )

    assert short_deadline.allowed is False
    assert short_deadline.reason == "deadline_insufficient"
    assert admitted.allowed is True
    assert admitted.reason == "admitted"
    assert admitted.candidate_count == 2
    assert admitted.projected_monthly_count == 1


def test_extra_admission_projects_current_job_candidates_plus_requested_extra():
    decision = evaluate_admission(
        AdmissionRequest(
            phase="extra",
            existing_candidate_count=4,
            retry_attempt=1,
            remaining_deadline_seconds=30,
            usage=CumulativeUsage(daily_usd=0.0, monthly_usd=0.0),
        ),
        policy=_policy(hard_daily_usd_limit=9.0, hard_monthly_usd_limit=20.0),
    )

    assert decision.allowed is False
    assert decision.reason == "daily_budget_exceeded"
    assert decision.projected_daily_usd == 10.0


def test_admission_blocks_stable_disable_and_retry_reasons_before_budget_projection():
    assert (
        evaluate_admission(
            AdmissionRequest(phase="initial", usage=CumulativeUsage()),
            policy=_policy(kill_switch_enabled=True),
        ).reason
        == "cost_kill_switch_enabled"
    )
    assert (
        evaluate_admission(
            AdmissionRequest(phase="initial", usage=CumulativeUsage()),
            policy=_policy(disable_new_generation=True),
        ).reason
        == "new_generation_disabled"
    )
    assert (
        evaluate_admission(
            AdmissionRequest(phase="initial", retry_attempt=3, usage=CumulativeUsage()),
            policy=_policy(),
        ).reason
        == "retry_limit_exceeded"
    )


@pytest.mark.parametrize(
    ("env_name", "expected_reason"),
    [
        ("AVATAR_DISABLE_NEW_GENERATION", "new_generation_disabled"),
        ("AVATAR_GENERATION_DISABLED", "new_generation_disabled"),
        ("AVATAR_GENERATION_PAUSED", "new_generation_disabled"),
        ("AVATAR_KILL_SWITCH", "cost_kill_switch_enabled"),
        ("AVATAR_COST_KILL_SWITCH_ENABLED", "cost_kill_switch_enabled"),
        ("AVATAR_GENERATION_BUDGET_EXHAUSTED", "cost_kill_switch_enabled"),
    ],
)
def test_operational_switch_aliases_map_to_canonical_admission_reasons(env_name, expected_reason):
    decision = evaluate_admission(
        AdmissionRequest(phase="initial", usage=CumulativeUsage()),
        policy=AdmissionPolicy.from_env({env_name: "true"}),
    )

    assert decision.allowed is False
    assert decision.reason == expected_reason

def test_true_operational_alias_is_not_masked_by_false_primary_name():
    disabled = AdmissionPolicy.from_env(
        {
            "AVATAR_DISABLE_NEW_GENERATION": "false",
            "AVATAR_GENERATION_PAUSED": "true",
        }
    )
    budget = AdmissionPolicy.from_env(
        {
            "AVATAR_COST_KILL_SWITCH_ENABLED": "false",
            "AVATAR_GENERATION_BUDGET_EXHAUSTED": "true",
        }
    )

    assert disabled.disable_new_generation is True
    assert budget.kill_switch_enabled is True

def test_production_like_admission_fails_closed_without_cumulative_usage():
    production_decision = evaluate_admission(
        AdmissionRequest(phase="initial", usage=None),
        policy=_policy(production_like=True),
    )
    local_decision = evaluate_admission(
        AdmissionRequest(phase="initial", usage=None),
        policy=_policy(production_like=False),
    )

    assert production_decision.allowed is False
    assert production_decision.reason == "cumulative_guard_unavailable"
    assert local_decision.allowed is True
    assert local_decision.reason == "admitted"
