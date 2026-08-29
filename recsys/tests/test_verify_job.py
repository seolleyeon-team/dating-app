"""Readiness semantics for the production recommendation verification gate."""

from recsys.jobs.verify_job import (
    build_policy_readiness_metrics,
    evaluate_verify_health,
)


def source_stats(**overrides):
    base = {
        "clip": {"ready": 1, "empty": 0, "skipped": 0, "missing": 0, "failed": 0},
        "svd": {"ready": 0, "empty": 0, "skipped": 1, "missing": 0, "failed": 0},
        "knn": {"ready": 0, "empty": 0, "skipped": 1, "missing": 0, "failed": 0},
        "rrf": {"ready": 1, "empty": 0, "skipped": 0, "missing": 0, "failed": 0},
    }
    base.update(overrides)
    return base


def daily(ready=1, empty=0, skipped=0, missing=0, failed=0):
    return {
        "eligible": ready + empty + skipped + missing,
        "ready": ready,
        "empty": empty,
        "skipped": skipped,
        "missing": missing,
        "failed": failed,
    }


def test_zero_users_is_healthy_degraded_success():
    result = evaluate_verify_health(
        total_real_users=0,
        eligible_actors=0,
        candidate_pool=0,
        source_stats=source_stats(),
        daily_stats=daily(ready=0, empty=0, skipped=0),
    )

    assert result["healthy"] is True
    assert result["degraded"] is True
    assert result["fatal"] is False
    assert "no_real_users" in result["reasons"]


def test_one_eligible_actor_is_degraded_but_not_fatal():
    result = evaluate_verify_health(
        total_real_users=1,
        eligible_actors=1,
        candidate_pool=1,
        source_stats=source_stats(),
        daily_stats=daily(ready=0, skipped=1),
    )

    assert result["healthy"] is True
    assert result["degraded"] is True
    assert result["fatal"] is False
    assert "insufficient_candidate_pool" in result["reasons"]


def test_two_or_more_users_without_compatible_pair_is_degraded():
    result = evaluate_verify_health(
        total_real_users=4,
        eligible_actors=2,
        candidate_pool=3,
        compatible_pairs=0,
        source_stats=source_stats(
            clip={"ready": 0, "empty": 2, "skipped": 0, "missing": 0, "failed": 0},
            rrf={"ready": 0, "empty": 2, "skipped": 0, "missing": 0, "failed": 0},
        ),
        daily_stats=daily(ready=0, empty=2),
    )

    assert result["healthy"] is True
    assert result["degraded"] is True
    assert result["fatal"] is False
    assert "no_compatible_pair" in result["reasons"]


def test_missing_current_date_source_is_fatal_when_candidate_data_exists():
    result = evaluate_verify_health(
        total_real_users=4,
        eligible_actors=2,
        candidate_pool=3,
        source_stats=source_stats(
            clip={"ready": 0, "empty": 0, "skipped": 0, "missing": 2, "failed": 0},
        ),
        daily_stats=daily(ready=2),
    )

    assert result["healthy"] is False
    assert result["degraded"] is False
    assert result["fatal"] is True
    assert "missing_clip_source" in result["reasons"]


def test_missing_daily_document_is_fatal_even_when_model_sources_exist():
    result = evaluate_verify_health(
        total_real_users=4,
        eligible_actors=2,
        candidate_pool=3,
        source_stats=source_stats(),
        daily_stats=daily(ready=1, missing=1),
    )

    assert result["healthy"] is False
    assert result["fatal"] is True
    assert "incomplete_daily_coverage" in result["reasons"]


def test_expected_svd_knn_shortage_does_not_fail_clip_only_pipeline():
    result = evaluate_verify_health(
        total_real_users=10,
        eligible_actors=3,
        candidate_pool=5,
        compatible_pairs=3,
        source_stats=source_stats(),
        daily_stats=daily(ready=3),
    )

    assert result["healthy"] is True
    assert result["degraded"] is False
    assert result["fatal"] is False
    assert result["sourceShortageExpected"] is True


def test_policy_readiness_metrics_are_aggregate_and_flag_suspicious_state():
    policy_meta = {
        "complete": {"isActive": True, "isVerified": True, "isProfileComplete": True},
        "incomplete": {"isActive": True, "isVerified": True, "isProfileComplete": False},
        "inactive": {"isActive": False, "isVerified": True, "isProfileComplete": True},
    }
    display_status = {
        "complete": {"displayReady": True},
        "incomplete": {"displayReady": True},
        "inactive": {"displayReady": True},
    }

    result = build_policy_readiness_metrics(
        total_real_users=4,
        policy_meta=policy_meta,
        display_status=display_status,
        compatible_pairs=0,
    )

    assert result == {
        "policyMetadataCoverage": 75.0,
        "activeUserCount": 2,
        "profileCompleteUserCount": 2,
        "policyEligibleCandidateCount": 1,
        "mediaReadyCandidateCount": 3,
        "policyAndMediaReadyCandidateCount": 1,
        "compatiblePairCount": 0,
        "suspiciousPolicyReadiness": False,
        "suspiciousPolicyReadinessReason": "",
    }


def test_policy_readiness_metrics_mark_zero_eligible_candidates_suspicious_not_fatal():
    result = build_policy_readiness_metrics(
        total_real_users=4,
        policy_meta={
            "one": {"isActive": True, "isVerified": True, "isProfileComplete": False},
        },
        display_status={"one": {"displayReady": True}},
        compatible_pairs=0,
    )

    assert result["suspiciousPolicyReadiness"] is True
    assert result["suspiciousPolicyReadinessReason"] == "approved_media_without_policy_eligible_candidate"
