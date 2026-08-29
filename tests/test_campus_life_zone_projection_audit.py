"""publicProfiles 투영 감사 집계 로직.

production 접근 없이 순수 함수만 검증한다. 이 감사는 최종 활성화 게이트에
쓰이므로, "원본에는 있는데 투영에는 없는" 사용자를 놓치면 안 된다.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "scripts", ROOT / "lib" / "ai_recommend_model"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from campus_life_zone_projection_audit import (  # noqa: E402
    recommendation_eligible,
    summarize,
    zone_state,
)


def _user(zones, **overrides):
    doc = {
        "isStudentVerified": True,
        "onboarding": {"campusLifeZones": zones} if zones is not None else {},
    }
    doc.update(overrides)
    return doc


def _public(zones):
    return {"onboarding": {"campusLifeZones": zones} if zones is not None else {}}


def test_full_coverage_has_no_mismatch():
    users = {"u1": _user(["sinchon"]), "u2": _user(["songdo"])}
    public = {"u1": _public(["sinchon"]), "u2": _public(["songdo"])}

    report = summarize(users, public)

    assert report["eligibleUsers"] == 2
    assert report["eligibleUsersWithZone"] == 2
    assert report["eligibleUsersWithPublicProfileZone"] == 2
    assert report["sourceProjectionMismatch"] == 0
    assert report["sourceCoverageRatio"] == 1.0
    assert report["projectionCoverageRatio"] == 1.0


def test_source_present_but_projection_missing_is_mismatch():
    """serving 이 실제로 깨지는 조합. 이걸 놓치면 활성화 후 후보가 사라진다."""
    users = {"u1": _user(["sinchon"])}
    public = {"u1": _public(None)}

    report = summarize(users, public)

    assert report["eligibleUsersWithZone"] == 1
    assert report["eligibleUsersWithPublicProfileZone"] == 0
    assert report["eligibleUsersMissingPublicProfileZone"] == 1
    assert report["sourceProjectionMismatch"] == 1


def test_missing_public_profile_document_counts_as_mismatch():
    users = {"u1": _user(["sinchon"])}
    report = summarize(users, {})

    assert report["sourceProjectionMismatch"] == 1
    assert report["projectionZoneStates"]["no_public_profile"] == 1
    assert report["eligibleUsersWithPublicProfile"] == 0


def test_missing_source_zone_is_not_a_projection_mismatch():
    """원본이 비어 있으면 보충 대상이지 투영 결함이 아니다."""
    users = {"u1": _user(None)}
    public = {"u1": _public(None)}

    report = summarize(users, public)

    assert report["eligibleUsersMissingZone"] == 1
    assert report["sourceProjectionMismatch"] == 0


def test_dual_zone_truncation_is_reported_separately():
    users = {"u1": _user(["sinchon", "songdo"])}
    public = {"u1": _public(["sinchon"])}

    report = summarize(users, public)

    assert report["dualZoneUsers"] == 1
    assert report["dualZoneProjected"] == 0
    assert report["sourceProjectionMismatch"] == 0
    assert report["projectionZoneValueMismatch"] == 1


def test_dual_zone_preserved_is_clean():
    users = {"u1": _user(["sinchon", "songdo"])}
    public = {"u1": _public(["songdo", "sinchon"])}

    report = summarize(users, public)

    assert report["dualZoneUsers"] == 1
    assert report["dualZoneProjected"] == 1
    assert report["projectionZoneValueMismatch"] == 0


def test_ineligible_users_are_excluded():
    users = {
        "ok": _user(["sinchon"]),
        "withdrawn": _user(["sinchon"], isWithdrawn=True),
        "unverified": _user(["sinchon"], isStudentVerified=False),
        "hidden": _user(["sinchon"], profileVisible=False),
    }
    report = summarize(users, {})

    assert report["totalUsers"] == 4
    assert report["eligibleUsers"] == 1
    assert recommendation_eligible(users["withdrawn"]) is False
    assert recommendation_eligible(users["ok"]) is True


def test_malformed_values_are_classified():
    assert zone_state(None) == "missing_field"
    assert zone_state("sinchon") == "invalid_type"
    assert zone_state(123) == "invalid_type"
    assert zone_state([]) == "empty"
    assert zone_state([1]) == "invalid_item_type"
    assert zone_state(["garbage"]) == "unknown_token"
    assert zone_state(["sinchon", "garbage"]) == "mixed_unknown_token"
    assert zone_state(["sinchon"]) == "valid"
    assert zone_state([" songdo "]) == "valid"


def test_malformed_counts_roll_up():
    users = {
        "a": _user(["garbage"]),
        "b": _user("sinchon"),
        "c": _user(["sinchon", "garbage"]),
        "d": _user(["sinchon"]),
    }
    public = {
        "a": _public(["garbage"]),
        "b": _public(["sinchon"]),
        "c": _public(["sinchon"]),
        "d": _public(["sinchon"]),
    }

    report = summarize(users, public)

    assert report["malformedSourceZones"] == 3
    assert report["malformedProjectionZones"] == 1
    # 손상된 원본은 생활권이 없는 것으로 센다 (fail-closed 와 동일한 기준).
    assert report["eligibleUsersWithZone"] == 1
    assert report["eligibleUsersMissingZone"] == 3


def test_report_contains_no_user_identifiers():
    users = {"kakao-1234567": _user(["sinchon"])}
    public = {"kakao-1234567": _public(["sinchon"])}

    report = summarize(users, public)

    serialized = str(report)
    assert "kakao-1234567" not in serialized
