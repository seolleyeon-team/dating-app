"""생활권(campus life zone) hard eligibility — 1:1 추천 정책 테스트.

생활권은 랭킹 점수가 아니라 eligibility다. 신촌 전용 사용자와 송도 전용
사용자는 CLIP/SVD/KNN 점수가 아무리 높아도 서로 추천되지 않아야 하고,
복수 생활권(신촌+송도) 사용자는 양쪽 모두와 추천 가능해야 한다.

분류 로직 자체(lib/constants/campus_life_zones.dart)는 이 테스트의 대상이
아니다. 여기서는 이미 저장된 campusLifeZones 값만 사용한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

AI_MODEL_DIR = Path(__file__).resolve().parents[2] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

# 생활권 정책 본체는 의존성 없는 순수 모듈이다.
from campus_life_zone_policy import (  # noqa: E402
    campus_life_zone_rejection,
    has_compatible_campus_life_zone,
    normalize_campus_life_zones,
    read_campus_life_zones_from_user_doc,
    shared_campus_life_zones,
)


def _require_rec_common():
    """seolleyeon_rec_common_v3 는 scipy/PIL 의존이라 없으면 skip 한다."""
    return pytest.importorskip(
        "seolleyeon_rec_common_v3",
        reason="1:1 pipeline requires numpy/pandas/scipy/PIL",
    )


def _require_daily_selector():
    """daily selector 모듈이 없는 환경에서는 skip 한다."""
    return pytest.importorskip(
        "recsys.jobs.daily_recommender",
        reason="daily selector module is unavailable",
    )

SINCHON = "sinchon"
SONGDO = "songdo"


# -----------------------------------------------------------------------------
# 1. 사용자 ↔ 사용자 호환성 (§41)
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ([SINCHON], [SINCHON], True),
        ([SONGDO], [SONGDO], True),
        ([SINCHON], [SONGDO], False),
        ([SONGDO], [SINCHON], False),
        ([SINCHON, SONGDO], [SINCHON], True),
        ([SINCHON, SONGDO], [SONGDO], True),
        ([SINCHON, SONGDO], [SINCHON, SONGDO], True),
        ([], [SINCHON], False),
        ([SINCHON], [], False),
        (None, [SONGDO], False),
        ([SONGDO], None, False),
        ("not-a-list", [SINCHON], False),
        ([SINCHON], {"unexpected": "shape"}, False),
    ],
)
def test_pairwise_compatibility_is_set_intersection(left, right, expected):
    assert has_compatible_campus_life_zone(left, right) is expected


def test_compatibility_is_symmetric():
    for left in ([SINCHON], [SONGDO], [SINCHON, SONGDO], []):
        for right in ([SINCHON], [SONGDO], [SINCHON, SONGDO], []):
            assert has_compatible_campus_life_zone(
                left, right
            ) == has_compatible_campus_life_zone(right, left)


def test_normalization_drops_blanks_and_keeps_canonical_values():
    assert normalize_campus_life_zones([SINCHON, " ", None, SINCHON]) == {SINCHON}
    assert normalize_campus_life_zones([" songdo "]) == {SONGDO}
    assert normalize_campus_life_zones(None) == set()
    assert normalize_campus_life_zones(42) == set()


def test_zone_rejection_distinguishes_missing_from_mismatch():
    """§55 — skip 사유가 구분 가능해야 한다."""
    missing = campus_life_zone_rejection({"campusLifeZones": []}, {"campusLifeZones": [SINCHON]})
    assert missing == "missing_campus_life_zones"

    mismatch = campus_life_zone_rejection(
        {"campusLifeZones": [SINCHON]}, {"campusLifeZones": [SONGDO]}
    )
    assert mismatch == "campus_life_zone_mismatch"

    assert (
        campus_life_zone_rejection(
            {"campusLifeZones": [SINCHON, SONGDO]}, {"campusLifeZones": [SONGDO]}
        )
        is None
    )


# -----------------------------------------------------------------------------
# 2. 저장 경로 파싱 — users/{uid}.onboarding.campusLifeZones
# -----------------------------------------------------------------------------


def test_reads_zones_from_canonical_onboarding_path():
    doc = {"onboarding": {"campusLifeZones": [SINCHON, SONGDO]}}
    assert read_campus_life_zones_from_user_doc(doc) == {SINCHON, SONGDO}


def test_reads_flattened_top_level_as_index_compatibility():
    assert read_campus_life_zones_from_user_doc({"campusLifeZones": [SONGDO]}) == {SONGDO}


def test_missing_zone_field_yields_empty_not_a_guess():
    """grade/department 로 재계산하지 않는다 — 없으면 없는 것이다."""
    doc = {"onboarding": {"grade": "1학년", "department": "첨단융합공학부"}}
    assert read_campus_life_zones_from_user_doc(doc) == set()


# -----------------------------------------------------------------------------
# 3. 그룹 공통 생활권 (§44) — 3:3 에서 재사용하는 semantics
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        ([[SINCHON], [SINCHON], [SINCHON]], {SINCHON}),
        ([[SONGDO], [SONGDO], [SINCHON, SONGDO]], {SONGDO}),
        ([[SINCHON], [SINCHON], [SINCHON, SONGDO]], {SINCHON}),
        ([[SINCHON], [SONGDO], [SINCHON, SONGDO]], set()),
        ([[SINCHON, SONGDO]] * 3, {SINCHON, SONGDO}),
        ([[SINCHON], [SINCHON], []], set()),
        ([[SINCHON], [SINCHON], None], set()),
        ([], set()),
    ],
)
def test_group_shared_zone_is_intersection_never_majority(members, expected):
    assert shared_campus_life_zones(members) == expected


def test_two_of_three_majority_does_not_win():
    """§34 — 3명 중 2명이 신촌이어도 신촌 그룹이 되지 않는다."""
    assert shared_campus_life_zones([[SINCHON], [SINCHON], [SONGDO]]) == set()


def test_six_person_intersection_matches_two_group_intersection():
    """§24 — 6인 전체 교집합 == 두 팀 공통 생활권의 교집합."""
    team_a = [[SINCHON], [SINCHON, SONGDO], [SINCHON]]
    team_b = [[SINCHON, SONGDO], [SINCHON], [SINCHON]]
    six = shared_campus_life_zones(team_a + team_b)
    by_group = shared_campus_life_zones(team_a) & shared_campus_life_zones(team_b)
    assert six == by_group == {SINCHON}

    mixed_b = [[SONGDO], [SONGDO], [SONGDO]]
    assert shared_campus_life_zones(team_a + mixed_b) == set()
    assert (shared_campus_life_zones(team_a) & shared_campus_life_zones(mixed_b)) == set()


# -----------------------------------------------------------------------------
# 4. passes_policy 통합 — SVD/KNN/CLIP/daily 공통 진입점
# -----------------------------------------------------------------------------


def _meta(uid: str, zones, *, gender: str = "female") -> dict:
    return {
        uid: {
            "universityId": "yonsei",
            "isVerified": True,
            "isActive": True,
            "isProfileComplete": True,
            "gender": gender,
            "birthYear": 2002,
            "prefGender": [],
            "prefAgeMin": None,
            "prefAgeMax": None,
            "mannerScore": 36.5,
            "lastActiveAt": None,
            "campusLifeZones": zones,
        }
    }


def _policy(actor_zones, candidate_zones, **kwargs) -> bool:
    passes_policy = _require_rec_common().passes_policy
    meta = {**_meta("actor", actor_zones, gender="male"), **_meta("cand", candidate_zones)}
    return passes_policy(
        "actor",
        "cand",
        meta,
        manner_min=33.0,
        active_within_days=14,
        require_same_university=True,
        reciprocal=True,
        **kwargs,
    )


def test_passes_policy_blocks_cross_zone_pairs():
    assert _policy([SINCHON], [SINCHON]) is True
    assert _policy([SONGDO], [SONGDO]) is True
    assert _policy([SINCHON], [SONGDO]) is False
    assert _policy([SONGDO], [SINCHON]) is False


def test_passes_policy_allows_dual_zone_bridge_users():
    assert _policy([SINCHON, SONGDO], [SINCHON]) is True
    assert _policy([SINCHON, SONGDO], [SONGDO]) is True
    assert _policy([SINCHON], [SINCHON, SONGDO]) is True


def test_passes_policy_is_fail_closed_on_missing_zones():
    """§74 — 생활권이 없으면 cross-zone fallback 없이 제외한다."""
    assert _policy([], [SINCHON]) is False
    assert _policy([SINCHON], []) is False
    assert _policy(None, [SINCHON]) is False


def test_zone_gate_can_be_disabled_only_by_explicit_opt_out():
    """운영 토글은 존재하되 기본값은 강제(fail-closed)다."""
    assert _policy([SINCHON], [SONGDO]) is False
    assert _policy([SINCHON], [SONGDO], require_same_campus_life_zone=False) is True


def test_zone_gate_does_not_replace_other_eligibility():
    """§12 — 생활권은 기존 조건을 대체하지 않고 추가된다."""
    passes_policy = _require_rec_common().passes_policy
    meta = {**_meta("actor", [SINCHON], gender="male"), **_meta("cand", [SINCHON])}
    meta["cand"]["isVerified"] = False
    assert (
        passes_policy(
            "actor",
            "cand",
            meta,
            manner_min=33.0,
            active_within_days=14,
            require_same_university=True,
            reciprocal=True,
        )
        is False
    )


# -----------------------------------------------------------------------------
# 5. 최종 serving 선택 (daily) — 부족해도 cross-zone 으로 채우지 않는다 (§20, §43)
# -----------------------------------------------------------------------------


def _rrf(*uids: str) -> list[dict]:
    return [
        {"uid": uid, "rank": rank, "score": 10.0 - rank}
        for rank, uid in enumerate(uids, start=1)
    ]


def test_daily_feed_never_backfills_with_other_zone_candidates():
    """신촌 후보 2명 + 송도 후보 100명 → 정확히 2명만 추천된다."""
    meta: dict = {}
    meta.update(_meta("actor", [SINCHON], gender="male"))
    same_zone = ["same1", "same2"]
    for uid in same_zone:
        meta.update(_meta(uid, [SINCHON]))
    other_zone = [f"other{i}" for i in range(100)]
    for uid in other_zone:
        meta.update(_meta(uid, [SONGDO]))

    # cross-zone 후보를 더 높은 점수로 먼저 배치해도 밀려나면 안 된다.
    daily = _require_daily_selector()
    result = daily.select_daily_items(
        "actor",
        _rrf(*other_zone, *same_zone),
        meta,
        date_key="20260825",
        config=daily.DailySelectionConfig(topn=10),
    )

    assert result["status"] == "ready"
    assert {item["uid"] for item in result["items"]} == set(same_zone)
    assert result["selection"]["rejected"]["campus_life_zone_mismatch"] == 100


def test_daily_feed_reports_missing_zone_separately():
    meta: dict = {}
    meta.update(_meta("actor", [SINCHON], gender="male"))
    meta.update(_meta("nozone", []))
    meta.update(_meta("ok", [SINCHON]))

    daily = _require_daily_selector()
    result = daily.select_daily_items(
        "actor",
        _rrf("nozone", "ok"),
        meta,
        date_key="20260825",
        config=daily.DailySelectionConfig(topn=10),
    )

    assert [item["uid"] for item in result["items"]] == ["ok"]
    assert result["selection"]["rejected"]["missing_campus_life_zones"] == 1
    assert "campus_life_zone_mismatch" not in result["selection"]["rejected"]


def test_daily_feed_is_empty_rather_than_cross_zone():
    meta: dict = {}
    meta.update(_meta("actor", [SONGDO], gender="male"))
    for uid in ("a", "b", "c"):
        meta.update(_meta(uid, [SINCHON]))

    daily = _require_daily_selector()
    result = daily.select_daily_items(
        "actor",
        _rrf("a", "b", "c"),
        meta,
        date_key="20260825",
        config=daily.DailySelectionConfig(topn=3),
    )

    assert result["status"] == "empty"
    assert result["items"] == []


def test_dual_zone_actor_sees_both_populations():
    meta: dict = {}
    meta.update(_meta("actor", [SINCHON, SONGDO], gender="male"))
    meta.update(_meta("sin", [SINCHON]))
    meta.update(_meta("song", [SONGDO]))

    daily = _require_daily_selector()
    result = daily.select_daily_items(
        "actor",
        _rrf("sin", "song"),
        meta,
        date_key="20260825",
        config=daily.DailySelectionConfig(topn=3),
    )

    assert {item["uid"] for item in result["items"]} == {"sin", "song"}
