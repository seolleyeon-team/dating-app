"""생활권 정책의 장애/손상 데이터 semantics (Python 런타임).

두 가지를 고정한다.

1. activation read failure 가 fail-open 이 되지 않는다.
   "아직 활성화한 적 없음"(문서 없음)과 "지금 상태를 모름"(조회 실패)은
   다른 상태이고, 배치는 후자에서 추천을 새로 쓰지 않는다.
2. canonical 이 아닌 생활권 값은 생활권으로 인정하지 않는다.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "lib" / "ai_recommend_model"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from campus_life_zone_policy import (  # noqa: E402
    ACTIVATION_ENFORCED,
    ACTIVATION_OFF,
    CampusLifeZoneActivationUnknown,
    campus_life_zone_activation_from_config,
    campus_life_zone_policy_version_from_config,
    has_compatible_campus_life_zone,
    load_campus_life_zone_activation,
    load_campus_life_zone_activation_with_version,
    load_campus_life_zone_enforced,
    normalize_campus_life_zones,
    read_campus_life_zones_from_user_doc,
    read_persisted_campus_life_zones,
    shared_campus_life_zones,
)

SINCHON = "sinchon"
SONGDO = "songdo"


class _Snapshot:
    def __init__(self, data):
        self._data = data

    def to_dict(self):
        return self._data


class _DocRef:
    def __init__(self, data):
        self._data = data

    def get(self):
        return _Snapshot(self._data)


class _Collection:
    def __init__(self, data):
        self._data = data

    def document(self, _doc_id):
        return _DocRef(self._data)


class _Db:
    """조회에 성공하는 Firestore stub."""

    def __init__(self, data):
        self._data = data

    def collection(self, _name):
        return _Collection(self._data)


class _FailingDb:
    """조회 자체가 실패하는 Firestore stub (네트워크/권한 장애)."""

    def __init__(self, error=None):
        self._error = error or RuntimeError("deadline exceeded")

    def collection(self, _name):
        raise self._error


# ---------------------------------------------------------------- activation


def test_missing_document_is_explicit_off_not_unknown():
    """준비 단계: 문서가 없으면 OFF 다. 이것은 장애가 아니다."""
    assert load_campus_life_zone_activation(_Db(None)) == ACTIVATION_OFF
    assert load_campus_life_zone_activation(_Db({})) == ACTIVATION_OFF
    assert load_campus_life_zone_enforced(_Db(None)) is False


def test_explicit_true_is_enforced():
    assert (
        load_campus_life_zone_activation(_Db({"campusLifeZoneEnforced": True}))
        == ACTIVATION_ENFORCED
    )
    assert load_campus_life_zone_enforced(_Db({"campusLifeZoneEnforced": True})) is True


def test_loose_values_do_not_enable_the_policy():
    for loose in ("true", 1, "ON", [True], {"value": True}):
        assert (
            campus_life_zone_activation_from_config({"campusLifeZoneEnforced": loose})
            == ACTIVATION_OFF
        ), loose


def test_read_failure_is_unknown_and_batches_abort():
    """§8 — 조회 실패를 OFF 로 간주하지 않는다.

    활성화된 뒤 config 조회가 실패했는데 OFF 로 진행하면, 그 배치는
    cross-zone 후보가 들어간 추천을 새로 저장한다. 배치가 한 번 실패하는
    편이 안전하다.
    """
    with pytest.raises(CampusLifeZoneActivationUnknown):
        load_campus_life_zone_activation(_FailingDb())
    with pytest.raises(CampusLifeZoneActivationUnknown):
        load_campus_life_zone_enforced(_FailingDb())
    with pytest.raises(CampusLifeZoneActivationUnknown):
        load_campus_life_zone_activation_with_version(_FailingDb())


def test_read_only_tools_may_opt_into_off_on_unknown():
    """결과를 쓰지 않는 진단 도구만 명시적으로 OFF 를 택할 수 있다."""
    assert load_campus_life_zone_enforced(_FailingDb(), on_unknown="off") is False


def test_permission_denied_is_also_unknown():
    class _PermissionDenied(Exception):
        pass

    with pytest.raises(CampusLifeZoneActivationUnknown):
        load_campus_life_zone_activation(_FailingDb(_PermissionDenied("denied")))


def test_policy_version_is_read_with_the_state():
    state, version = load_campus_life_zone_activation_with_version(
        _Db({"campusLifeZoneEnforced": True, "campusLifeZonePolicyVersion": 3})
    )
    assert (state, version) == (ACTIVATION_ENFORCED, 3)
    assert campus_life_zone_policy_version_from_config({}) == 0
    assert campus_life_zone_policy_version_from_config(
        {"campusLifeZonePolicyVersion": "3"}
    ) == 0
    assert campus_life_zone_policy_version_from_config(
        {"campusLifeZonePolicyVersion": True}
    ) == 0


# ------------------------------------------------------------ malformed data


@pytest.mark.parametrize(
    "value",
    [
        ["garbage"],
        [SINCHON, "garbage"],
        ["SINCHON"],
        ["신촌"],
        [""],
        [SINCHON, ""],
        [SINCHON, None],
        [SINCHON, 1],
        [None],
        [123],
        [],
    ],
)
def test_malformed_zone_values_are_rejected(value):
    assert read_persisted_campus_life_zones(value) == set()


@pytest.mark.parametrize("value", ["sinchon", 123, None, True, {"zone": SINCHON}])
def test_invalid_stored_types_are_rejected(value):
    """§12 — canonical 스키마는 List<String> 이다. raw string 도 무효."""
    assert read_persisted_campus_life_zones(value) == set()


def test_canonical_values_are_accepted():
    assert read_persisted_campus_life_zones([SINCHON]) == {SINCHON}
    assert read_persisted_campus_life_zones([SONGDO]) == {SONGDO}
    assert read_persisted_campus_life_zones([SINCHON, SONGDO]) == {SINCHON, SONGDO}


def test_garbage_never_matches_even_against_itself():
    """§10 — 같은 손상 값끼리도 호환으로 보지 않는다."""
    assert has_compatible_campus_life_zone(["garbage"], ["garbage"]) is False
    assert has_compatible_campus_life_zone(["garbage"], [SINCHON]) is False
    assert has_compatible_campus_life_zone([SINCHON, "garbage"], [SINCHON]) is False


def test_dual_zone_still_bridges_both_sides():
    assert has_compatible_campus_life_zone([SINCHON, SONGDO], [SONGDO]) is True
    assert has_compatible_campus_life_zone([SINCHON, SONGDO], [SINCHON]) is True


def test_group_intersection_rejects_malformed_member():
    """그룹 한 명이라도 손상된 값이면 공통 생활권이 없다 (fail-closed)."""
    assert shared_campus_life_zones([[SINCHON], [SINCHON], ["garbage"]]) == set()
    assert shared_campus_life_zones([[SINCHON], [SINCHON], [SINCHON]]) == {SINCHON}


def test_user_document_reader_uses_persisted_schema_validation():
    assert read_campus_life_zones_from_user_doc(
        {"onboarding": {"campusLifeZones": [SINCHON]}}
    ) == {SINCHON}
    # raw string 으로 저장된 손상 문서
    assert (
        read_campus_life_zones_from_user_doc(
            {"onboarding": {"campusLifeZones": SINCHON}}
        )
        == set()
    )
    # canonical 이 아닌 토큰
    assert (
        read_campus_life_zones_from_user_doc(
            {"onboarding": {"campusLifeZones": ["sinchon-campus"]}}
        )
        == set()
    )


def test_in_memory_helper_still_accepts_sets_and_tuples():
    """내부 helper 는 컬렉션 타입을 편하게 받는다 (스키마 검증과 분리)."""
    assert normalize_campus_life_zones({SINCHON}) == {SINCHON}
    assert normalize_campus_life_zones((SINCHON, SONGDO)) == {SINCHON, SONGDO}
    assert normalize_campus_life_zones({"garbage"}) == set()
