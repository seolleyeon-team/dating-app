"""시즌 미팅 산출물의 생활권 정책 provenance.

1:1 문서와 같은 계약을 미팅 쪽에도 요구한다. 문서가 어떤 정책 상태에서
만들어졌는지 문서 자체에 남아 있어야, 상위/하위 단계가 서로 다른 정책으로
만들어진 결과를 섞지 않고, 검증이 "활성화했다고 믿는 상태"와 실제 산출물을
대조할 수 있다.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "lib" / "ai_recommend_model"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from seolleyeon_meeting_common_v1 import (  # noqa: E402
    meeting_policy_provenance,
    read_meeting_policy_state,
    upstream_policy_matches,
)
from recsys.jobs.meeting_verify_policy import (  # noqa: E402
    build_meeting_verification_summary,
    campus_life_zone_policy_failures,
)

ENFORCED = "enforced"
OFF = "off"


def _summary(model_state, daily_state, *, expected):
    """provenance 만 다른 최소 산출물로 검증 요약을 만든다."""

    def doc(state, item_field):
        payload = {"status": "ready", item_field: [{"groupId": "g2"}]}
        if state is not None:
            payload["policy"] = {"campusLifeZone": state}
        return payload

    return build_meeting_verification_summary(
        "20260826",
        {"g1": {"index_status": "ready"}},
        {"g1": doc(model_state, "items")},
        {"g1": doc(daily_state, "candidates")},
        expected_campus_life_zone_state=expected,
    )


# ------------------------------------------------------------- provenance 형식


def test_provenance_payload_matches_the_one_to_one_contract():
    assert meeting_policy_provenance(OFF, 0) == {
        "campusLifeZone": "off",
        "campusLifeZonePolicyVersion": 0,
    }
    assert meeting_policy_provenance(ENFORCED, 3) == {
        "campusLifeZone": "enforced",
        "campusLifeZonePolicyVersion": 3,
    }


def test_reading_policy_state_tolerates_legacy_documents():
    assert read_meeting_policy_state({"policy": {"campusLifeZone": ENFORCED}}) == ENFORCED
    assert read_meeting_policy_state({"policy": {}}) is None
    assert read_meeting_policy_state({"policy": "off"}) is None
    assert read_meeting_policy_state({}) is None
    assert read_meeting_policy_state(None) is None


# ------------------------------------------------- upstream/downstream 혼합 방지


def test_enforced_run_refuses_off_or_legacy_upstream():
    """활성화된 뒤에는 생활권을 적용하지 않고 만든 상위 문서를 재사용하지 않는다."""
    assert upstream_policy_matches(ENFORCED, {"policy": {"campusLifeZone": ENFORCED}})
    assert not upstream_policy_matches(ENFORCED, {"policy": {"campusLifeZone": OFF}})
    assert not upstream_policy_matches(ENFORCED, {})  # legacy


def test_preparation_run_accepts_legacy_upstream():
    """준비 단계에서는 생활권으로 거른 것이 없으므로 legacy 문서를 허용한다."""
    assert upstream_policy_matches(OFF, {})
    assert upstream_policy_matches(OFF, {"policy": {"campusLifeZone": OFF}})
    assert not upstream_policy_matches(OFF, {"policy": {"campusLifeZone": ENFORCED}})


# -------------------------------------------------------------------- verify


def test_off_run_with_off_documents_is_healthy():
    summary = _summary(OFF, OFF, expected=OFF)
    assert summary["healthy"] is True
    assert summary["meetingModelRecs"]["policyStates"] == {OFF: 1}
    assert summary["meetingDailyRecs"]["policyStates"] == {OFF: 1}


def test_enforced_run_with_enforced_documents_is_healthy():
    summary = _summary(ENFORCED, ENFORCED, expected=ENFORCED)
    assert summary["healthy"] is True
    assert summary["campusLifeZoneExpectedState"] == ENFORCED


def test_enforced_run_with_off_model_documents_fails():
    """활성화했는데 상위 산출물이 off 면 cross-zone 이 들어 있을 수 있다."""
    summary = _summary(OFF, ENFORCED, expected=ENFORCED)
    assert summary["healthy"] is False
    assert "meetingModelRecs:campusLifeZone_off" in summary["failureReasons"]


def test_enforced_run_with_off_daily_documents_fails():
    summary = _summary(ENFORCED, OFF, expected=ENFORCED)
    assert summary["healthy"] is False
    assert "meetingDailyRecs:campusLifeZone_off" in summary["failureReasons"]


def test_enforced_run_with_missing_provenance_fails():
    """활성화 이후에는 provenance 없는 legacy 문서도 실패로 본다."""
    summary = _summary(None, None, expected=ENFORCED)
    assert summary["healthy"] is False
    assert "meetingModelRecs:campusLifeZone_missing" in summary["failureReasons"]


def test_off_run_with_enforced_documents_fails():
    """정책을 껐는데 산출물이 enforced 면 서로 다른 세대가 섞인 상태다."""
    summary = _summary(ENFORCED, ENFORCED, expected=OFF)
    assert summary["healthy"] is False
    assert "meetingModelRecs:campusLifeZone_enforced" in summary["failureReasons"]


def test_off_run_with_legacy_documents_is_healthy():
    """준비 단계의 legacy 문서는 허용한다 (호환)."""
    summary = _summary(None, None, expected=OFF)
    assert summary["healthy"] is True


def test_unknown_activation_is_not_reported_healthy():
    summary = _summary(OFF, OFF, expected=None)
    assert summary["healthy"] is False
    assert "campusLifeZone:activation_unknown" in summary["failureReasons"]


def test_legacy_callers_without_the_check_keep_working():
    """정책 검사를 요청하지 않은 기존 호출부는 그대로 동작한다."""
    summary = build_meeting_verification_summary(
        "20260826",
        {"g1": {"index_status": "ready"}},
        {"g1": {"status": "ready", "items": [{"groupId": "g2"}]}},
        {"g1": {"status": "ready", "candidates": [{"groupId": "g2"}]}},
    )
    assert summary["healthy"] is True
    assert "campusLifeZoneExpectedState" not in summary


@pytest.mark.parametrize("expected", [OFF, ENFORCED])
def test_no_ready_groups_is_not_a_policy_failure(expected):
    summary = build_meeting_verification_summary(
        "20260826", {}, {}, {}, expected_campus_life_zone_state=expected
    )
    assert summary["healthy"] is True


def test_policy_failures_helper_is_explicit_about_unknown():
    assert campus_life_zone_policy_failures({}, None) == [
        "campusLifeZone:activation_unknown"
    ]
    assert campus_life_zone_policy_failures({}, OFF) == []


# --------------------------------------------------------------- writer 배선


def test_meeting_writers_record_provenance_on_every_output():
    model_dir = ROOT / "lib" / "ai_recommend_model"
    ranker = (model_dir / "seolleyeon_meeting_recommend_export_v1.py").read_text(
        encoding="utf-8"
    )
    daily = (model_dir / "seolleyeon_meeting_daily_recs_export_v1.py").read_text(
        encoding="utf-8"
    )

    # 상위(ranker): skipped + ready/empty 두 경로 모두
    assert ranker.count('"policy": policy_provenance') >= 2
    # 하위(daily): skipped + stale-policy + empty x2 + ready
    assert daily.count('"policy": policy_provenance') >= 5
    # 상위 문서의 정책이 다르면 그대로 내려보내지 않는다
    assert "upstream_policy_matches(campus_zone_state, ranker_doc)" in daily
    assert "stale_campus_life_zone_policy" in daily


def test_meeting_batches_abort_when_activation_is_unknown():
    """1:1 배치와 같은 계약: 상태를 모르면 새로 쓰지 않는다."""
    model_dir = ROOT / "lib" / "ai_recommend_model"
    for name in (
        "seolleyeon_meeting_recommend_export_v1.py",
        "seolleyeon_meeting_daily_recs_export_v1.py",
    ):
        source = (model_dir / name).read_text(encoding="utf-8")
        assert "load_meeting_campus_zone_activation(db)" in source, name
        # on_unknown="off" 로 조용히 넘어가는 경로가 없어야 한다.
        assert 'on_unknown="off"' not in source, name
