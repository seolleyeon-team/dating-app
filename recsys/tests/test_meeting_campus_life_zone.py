"""3:3 시즌 미팅 — 그룹 생활권 hard eligibility 테스트.

두 팀이 추천되려면 여섯 명 전체가 최소 하나의 공통 생활권을 가져야 한다.
그룹의 생활권은 다수결이 아니라 세 멤버의 교집합이다.

regionId 정책은 이 테스트의 대상이 아니며, 생활권과 완전히 독립적으로
동작해야 한다 (§30-31, §54).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

AI_MODEL_DIR = Path(__file__).resolve().parents[2] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from campus_life_zone_policy import (  # noqa: E402
    campus_zone_compatibility,
    shared_campus_life_zones,
)

SINCHON = "sinchon"
SONGDO = "songdo"


def _zone_gate(left, right, *, allow_missing: bool = False):
    return campus_zone_compatibility(
        left, right, allow_missing_campus_zone=allow_missing
    )


def _require_meeting_common():
    """seolleyeon_meeting_common_v1 은 CLIP/torch 의존이라 없으면 skip 한다."""
    return pytest.importorskip(
        "seolleyeon_meeting_common_v1",
        reason="meeting pipeline requires numpy/pandas/CLIP dependencies",
    )


# -----------------------------------------------------------------------------
# 그룹 공통 생활권 (§44)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        ([[SINCHON], [SINCHON], [SINCHON]], {SINCHON}),
        ([[SONGDO], [SONGDO], [SINCHON, SONGDO]], {SONGDO}),
        ([[SINCHON], [SINCHON], [SINCHON, SONGDO]], {SINCHON}),
        ([[SINCHON], [SONGDO], [SINCHON, SONGDO]], set()),
        ([[SINCHON, SONGDO]] * 3, {SINCHON, SONGDO}),
    ],
)
def test_group_zone_is_member_intersection(members, expected):
    assert shared_campus_life_zones(members) == expected


def test_group_with_a_zoneless_member_is_ineligible():
    assert shared_campus_life_zones([[SINCHON], [SINCHON], []]) == set()


# -----------------------------------------------------------------------------
# 그룹 ↔ 그룹 호환성 (§45)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right", "ok"),
    [
        ([SINCHON], [SINCHON], True),
        ([SONGDO], [SONGDO], True),
        ([SINCHON], [SONGDO], False),
        ([SINCHON, SONGDO], [SONGDO], True),
        ([SINCHON, SONGDO], [SINCHON], True),
        ([], [SINCHON], False),
        ([SINCHON], [], False),
    ],
)
def test_group_pair_gate(left, right, ok):
    passed, reason = _zone_gate(left, right)
    assert passed is ok
    if ok:
        assert reason is None
    else:
        assert reason in {"missing_campus_life_zones", "campus_life_zone_mismatch"}


def test_gate_distinguishes_missing_from_mismatch():
    assert _zone_gate([], [SINCHON])[1] == "missing_campus_life_zones"
    assert _zone_gate([SINCHON], [SONGDO])[1] == "campus_life_zone_mismatch"


def test_missing_zone_is_fail_closed_by_default_and_opt_out_is_explicit():
    assert _zone_gate([], [SINCHON])[0] is False
    assert _zone_gate([], [SINCHON], allow_missing=True)[0] is True
    # 값이 있는데 어긋난 경우는 토글과 무관하게 항상 거부된다.
    assert _zone_gate([SINCHON], [SONGDO], allow_missing=True)[0] is False


# -----------------------------------------------------------------------------
# 6인 end-to-end 동치성 (§24, §46)
# -----------------------------------------------------------------------------


def _six_person_ok(team_a, team_b) -> bool:
    return bool(shared_campus_life_zones(team_a + team_b))


@pytest.mark.parametrize(
    ("team_a", "team_b", "ok"),
    [
        ([[SINCHON]] * 3, [[SINCHON]] * 3, True),
        ([[SONGDO]] * 3, [[SONGDO]] * 3, True),
        # 5명 신촌 가능 + 1명 송도 전용 → 신촌 미팅 불가
        ([[SINCHON]] * 3, [[SINCHON], [SINCHON], [SONGDO]], False),
        ([[SINCHON]] * 3, [[SONGDO]] * 3, False),
        # dual-zone 이 bridge 역할을 해도 전체 공통이 없으면 불가
        ([[SINCHON], [SINCHON], [SINCHON, SONGDO]], [[SONGDO]] * 3, False),
        # dual-zone 이 실제로 공통을 만들면 가능
        ([[SINCHON, SONGDO]] * 3, [[SONGDO]] * 3, True),
    ],
)
def test_six_person_end_to_end(team_a, team_b, ok):
    assert _six_person_ok(team_a, team_b) is ok
    # 그룹 단위 게이트와 6인 교집합 판정이 동치여야 한다 (§24)
    gate_ok, _reason = _zone_gate(
        sorted(shared_campus_life_zones(team_a)),
        sorted(shared_campus_life_zones(team_b)),
    )
    assert gate_ok is ok


# -----------------------------------------------------------------------------
# regionId 독립성 (§54)
# -----------------------------------------------------------------------------


def test_region_and_campus_zone_are_independent_policies():
    region_compatibility = _require_meeting_common().region_compatibility

    # region 은 같지만 생활권이 다르면 → 생활권 게이트가 거부한다
    region_ok, _score = region_compatibility(
        "yonsei", "yonsei", allow_missing_region=True
    )
    assert region_ok is True
    assert _zone_gate([SINCHON], [SONGDO])[0] is False

    # 생활권은 같지만 region 이 다르면 → region 게이트가 여전히 거부한다
    assert _zone_gate([SINCHON], [SINCHON])[0] is True
    region_ok2, _score2 = region_compatibility(
        "yonsei", "korea", allow_missing_region=True
    )
    assert region_ok2 is False


def test_group_index_record_carries_shared_zone_and_skip_reason():
    meeting_common = _require_meeting_common()
    MemberProfileView = meeting_common.MemberProfileView
    build_group_index_record = meeting_common.build_group_index_record

    def member(uid: str, zones: list[str]) -> MemberProfileView:
        return MemberProfileView(
            uid=uid,
            university_id="yonsei",
            is_verified=True,
            is_active=True,
            is_profile_complete=True,
            gender="female",
            birth_year=2002,
            pref_gender=[],
            pref_age_min=None,
            pref_age_max=None,
            manner_score=36.5,
            last_active_at=None,
            interest_tag_ids=["coffee"],
            lifestyle_tag_ids=[],
            photo_urls=[],
            campus_life_zones=zones,
        )

    raw_group = {"memberUids": ["u1", "u2", "u3"], "status": "open"}

    ok = build_group_index_record(
        "g-ok",
        raw_group,
        {
            "u1": member("u1", [SINCHON]),
            "u2": member("u2", [SINCHON, SONGDO]),
            "u3": member("u3", [SINCHON]),
        },
        manner_min_threshold=33.0,
    )
    assert ok.shared_campus_life_zones == [SINCHON]
    assert ok.index_status == "ready"
    assert ok.to_document()["sharedCampusLifeZones"] == [SINCHON]

    mixed = build_group_index_record(
        "g-mixed",
        raw_group,
        {
            "u1": member("u1", [SINCHON]),
            "u2": member("u2", [SONGDO]),
            "u3": member("u3", [SINCHON, SONGDO]),
        },
        manner_min_threshold=33.0,
    )
    assert mixed.shared_campus_life_zones == []
    assert "no_shared_campus_life_zone" in mixed.skip_reasons
    assert mixed.index_status == "skipped"

    zoneless = build_group_index_record(
        "g-zoneless",
        raw_group,
        {
            "u1": member("u1", [SINCHON]),
            "u2": member("u2", []),
            "u3": member("u3", [SINCHON]),
        },
        manner_min_threshold=33.0,
    )
    assert zoneless.shared_campus_life_zones == []
    assert "missing_campus_life_zones" in zoneless.skip_reasons


def test_member_profile_view_reads_canonical_onboarding_path():
    build_member_profile_view = _require_meeting_common().build_member_profile_view

    view = build_member_profile_view(
        "u1",
        {"universityId": "yonsei"},
        {"onboarding": {"campusLifeZones": [SONGDO, SINCHON]}},
    )
    assert view.campus_life_zones == [SINCHON, SONGDO]

    # 값이 없으면 grade/department 로 추측하지 않는다.
    missing = build_member_profile_view(
        "u2",
        {"universityId": "yonsei"},
        {"onboarding": {"grade": "1학년", "department": "첨단융합공학부"}},
    )
    assert missing.campus_life_zones == []
