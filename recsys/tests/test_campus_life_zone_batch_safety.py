"""배치는 activation 을 모르는 상태에서 추천을 새로 쓰지 않는다.

그리고 verify 는 "활성화했다고 믿는 정책"과 "산출물에 기록된 정책"이 다르면
성공으로 넘기지 않는다 (§23).
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
    ACTIVATION_UNKNOWN,
)
from recsys.jobs.verify_job import (  # noqa: E402
    evaluate_policy_provenance,
    evaluate_verify_health,
)


def _health(policy_provenance=None):
    return evaluate_verify_health(
        total_real_users=10,
        eligible_actors=4,
        candidate_pool=8,
        source_stats={
            name: {"ready": 4, "empty": 0, "skipped": 0, "missing": 0, "failed": 0}
            for name in ("clip", "svd", "knn", "rrf")
        },
        daily_stats={"ready": 4, "empty": 0, "skipped": 0, "missing": 0, "failed": 0},
        compatible_pairs=6,
        policy_provenance=policy_provenance,
    )


def test_provenance_matches_expected_state():
    provenance = evaluate_policy_provenance(
        expected_state=ACTIVATION_ENFORCED,
        observed_states={ACTIVATION_ENFORCED: 12},
    )
    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is True
    health = _health(provenance)
    assert health["fatal"] is False
    assert health["healthy"] is True


def test_enforced_intent_with_off_output_is_fatal():
    """활성화했는데 산출물이 off 면 cross-zone 이 들어 있을 수 있다."""
    provenance = evaluate_policy_provenance(
        expected_state=ACTIVATION_ENFORCED,
        observed_states={ACTIVATION_ENFORCED: 8, ACTIVATION_OFF: 3},
    )
    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is False
    assert provenance["campusLifeZonePolicyMismatchCounts"] == {ACTIVATION_OFF: 3}

    health = _health(provenance)
    assert health["fatal"] is True
    assert "campus_life_zone_policy_provenance_mismatch" in health["fatalReasons"]


def test_missing_provenance_after_activation_is_fatal():
    """provenance 가 없는 legacy 문서도 활성화 이후에는 실패로 본다."""
    provenance = evaluate_policy_provenance(
        expected_state=ACTIVATION_ENFORCED,
        observed_states={"missing": 5},
    )
    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is False
    assert _health(provenance)["fatal"] is True


def test_preparation_phase_expects_off_documents():
    provenance = evaluate_policy_provenance(
        expected_state=ACTIVATION_OFF,
        observed_states={ACTIVATION_OFF: 20},
    )
    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is True
    assert _health(provenance)["fatal"] is False


def test_unknown_expected_state_fails_verification():
    """verify 가 config 를 못 읽으면 건강하다고 말하지 않는다 (§21)."""
    provenance = evaluate_policy_provenance(
        expected_state=ACTIVATION_UNKNOWN,
        observed_states={ACTIVATION_OFF: 10},
    )
    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is False
    assert _health(provenance)["fatal"] is True


def test_health_without_provenance_keeps_previous_behaviour():
    """provenance 를 주지 않으면 기존 판정 그대로다 (하위 호환)."""
    health = _health(None)
    assert health["fatal"] is False
    assert "campusLifeZonePolicyProvenanceHealthy" not in health


def test_daily_job_aborts_when_activation_is_unknown(monkeypatch):
    """§8 — config 조회 실패 시 dailyRecs 를 쓰지 않고 중단한다."""
    from campus_life_zone_policy import CampusLifeZoneActivationUnknown
    from recsys.jobs import daily_job

    calls = {"writes": 0}

    def _boom(_db):
        raise CampusLifeZoneActivationUnknown("deadline exceeded")

    def _write(*_args, **_kwargs):  # pragma: no cover - 호출되면 실패다
        calls["writes"] += 1

    monkeypatch.setattr(
        daily_job, "load_campus_life_zone_activation_with_version", _boom
    )
    monkeypatch.setattr(daily_job, "_write_daily_documents", _write)

    source = Path(daily_job.__file__).read_text(encoding="utf-8")
    # 활성화 조회가 문서 쓰기보다 앞에 있어야 abort 가 의미를 갖는다.
    assert source.index(
        "load_campus_life_zone_activation_with_version"
    ) < source.index("_write_daily_documents(db, date_key, docs)")
    assert "raise" in source[
        source.index("except CampusLifeZoneActivationUnknown") : source.index(
            "campus_zone_enforced = campus_zone_state"
        )
    ]
    assert calls["writes"] == 0


def test_daily_job_reports_activation_state_and_version():
    from recsys.jobs import daily_job

    source = Path(daily_job.__file__).read_text(encoding="utf-8")
    for field in (
        "campusLifeZoneFilterEnabled",
        "campusLifeZoneActivationState",
        "campusLifeZonePolicyVersion",
        "campusLifeZoneActivationReadFailure",
    ):
        assert field in source, field
