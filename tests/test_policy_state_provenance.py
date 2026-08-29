"""Regression tests for recommendation policy-state provenance and audits."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AI_MODEL_DIR = ROOT / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from seolleyeon_policy_state import (  # noqa: E402
    account_active_provenance,
    activity_provenance,
    profile_completion_provenance,
)
from recsys.jobs.policy_audit import audit_policy_pairs  # noqa: E402


def _meta(
    uid: str,
    *,
    complete: bool = True,
    last_active_at=None,
    campus_life_zones=("sinchon",),
) -> dict:
    """정상 사용자를 표현한다.

    생활권도 hard eligibility 라서 값이 없으면 그 자체로 실패 사유가 된다.
    이 테스트가 보려는 것은 활동성·프로필 완성도 provenance 이므로,
    기본 fixture 는 생활권이 정상적으로 있는 사용자로 둔다.
    """
    return {
        uid: {
            "campusLifeZones": list(campus_life_zones),
            "universityId": "yonsei",
            "isVerified": True,
            "isActive": True,
            "isProfileComplete": complete,
            "gender": "female" if uid != "actor" else "male",
            "birthYear": 2002,
            "prefGender": [],
            "prefAgeMin": None,
            "prefAgeMax": None,
            "mannerScore": 36.5,
            "lastActiveAt": last_active_at,
        }
    }


def test_profile_completion_uses_app_canonical_writer_and_exposes_reason():
    assert profile_completion_provenance({"initialSetupComplete": True}) == {
        "value": True,
        "source": "users.initialSetupComplete",
        "reason": "canonical_true",
    }
    assert profile_completion_provenance({"initialSetupComplete": False}) == {
        "value": False,
        "source": "users.initialSetupComplete",
        "reason": "canonical_false",
    }
    assert profile_completion_provenance({}) == {
        "value": None,
        "source": "none",
        "reason": "missing_completion_fields",
    }


def test_explicit_profile_flag_wins_and_non_boolean_values_stay_unknown():
    assert profile_completion_provenance(
        {"isProfileComplete": False, "initialSetupComplete": True}
    )["reason"] == "explicit_false"
    assert profile_completion_provenance(
        {"initialSetupComplete": "false"}
    )["value"] is None


def test_account_active_is_separate_from_recent_activity():
    state = account_active_provenance({"lastLoginAt": datetime.now(timezone.utc)})
    assert state["value"] is True
    assert state["source"] == "users.account_status"
    assert state["reason"] == "no_blocking_status"

    assert account_active_provenance({"status": "deleted"}) == {
        "value": False,
        "source": "users.status",
        "reason": "blocked_status",
    }

    recent = datetime(2026, 8, 24, 0, 0, tzinfo=timezone.utc)
    assert activity_provenance(
        {
            "lastLoginAt": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "lastActivePlatformUpdatedAt": recent,
            "onboardingUpdatedAt": datetime(2025, 1, 1, tzinfo=timezone.utc),
        }
    ) == {
        "value": recent,
        "source": "users.lastActivePlatformUpdatedAt",
        "reason": "login_activity",
    }


def test_pair_audit_reports_first_and_all_failing_constraints():
    stale = pd.Timestamp("2026-07-01", tz="UTC")
    meta = {}
    meta.update(_meta("actor", last_active_at=None))
    meta.update(_meta("incomplete", complete=False, last_active_at=stale))
    meta.update(_meta("stale", complete=True, last_active_at=stale))

    result = audit_policy_pairs(
        ["actor"],
        ["incomplete", "stale"],
        meta,
        now=pd.Timestamp("2026-08-24", tz="UTC"),
        active_within_days=14,
    )

    assert result["pairChecks"] == 2
    assert result["compatiblePairs"] == 0
    assert result["firstFailureHistogram"] == {
        "inactive": 1,
        "profile_incomplete": 1,
    }
    assert result["uniqueCandidatesByFirstFailure"] == {
        "inactive": 1,
        "profile_incomplete": 1,
    }
    assert result["allFailureHistogram"]["inactive|profile_incomplete"] == 1
    assert result["allFailureHistogram"]["inactive"] == 1


def test_pair_audit_keeps_safety_and_policy_failures_in_full_audit():
    stale = pd.Timestamp("2026-07-01", tz="UTC")
    meta = {}
    meta.update(_meta("actor", last_active_at=None))
    meta.update(_meta("candidate", complete=False, last_active_at=stale))

    result = audit_policy_pairs(
        ["actor"],
        ["candidate"],
        meta,
        now=pd.Timestamp("2026-08-24", tz="UTC"),
        blocked_by_actor={"actor": {"candidate"}},
    )

    assert result["firstFailureHistogram"] == {"blocked": 1}
    assert result["allFailureHistogram"]["blocked|inactive|profile_incomplete"] == 1


def test_pair_audit_reports_missing_campus_life_zone_as_its_own_constraint():
    """생활권 미설정은 다른 정책 실패와 구분되어 집계된다."""
    meta = {}
    meta.update(_meta("actor"))
    meta.update(_meta("candidate", campus_life_zones=()))

    result = audit_policy_pairs(
        ["actor"],
        ["candidate"],
        meta,
        now=pd.Timestamp("2026-08-24", tz="UTC"),
    )

    assert result["compatiblePairs"] == 0
    assert result["allFailureHistogram"]["missing_campus_life_zones"] == 1


def test_pair_audit_passes_when_campus_life_zones_intersect():
    meta = {}
    meta.update(_meta("actor", campus_life_zones=("songdo",)))
    meta.update(_meta("candidate", campus_life_zones=("sinchon", "songdo")))

    result = audit_policy_pairs(
        ["actor"],
        ["candidate"],
        meta,
        now=pd.Timestamp("2026-08-24", tz="UTC"),
    )

    assert result["compatiblePairs"] == 1
