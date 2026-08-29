"""준비 단계(OFF)의 검증 semantics.

production 준비 배포에서 실제로 드러난 두 가지를 고정한다.

1. 정책을 켜기 전에는 provenance 가 없는 legacy 산출물이 정상이다. 그 시점에는
   생활권으로 거른 것이 없어 서로 다른 세대가 섞일 위험이 없다. 이것을 실패로
   보면 배포 직후 첫 배치가 무조건 unhealthy 로 끝난다.
2. 진단용 pair 감사도 activation 을 따라야 한다. OFF 인데 "생활권 때문에 호환
   pair 0" 이라고 보고하면 지표가 실제 서빙과 어긋난다.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "lib" / "ai_recommend_model"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from recsys.jobs.policy_audit import audit_policy_pairs  # noqa: E402
from recsys.jobs.verify_job import (  # noqa: E402
    evaluate_policy_provenance,
    evaluate_verify_health,
)

ENFORCED = "enforced"
OFF = "off"


def _health(provenance):
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
        policy_provenance=provenance,
    )


# ------------------------------------------------------- legacy provenance


def test_preparation_accepts_documents_written_before_the_release():
    """배포 직후: 아직 다시 만들지 않은 문서에는 provenance 가 없다."""
    provenance = evaluate_policy_provenance(
        expected_state=OFF,
        observed_states={"missing": 273, OFF: 11},
    )
    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is True
    assert _health(provenance)["fatal"] is False


def test_activation_still_rejects_legacy_documents():
    """활성화 이후에는 provenance 없는 문서를 신뢰하지 않는다."""
    provenance = evaluate_policy_provenance(
        expected_state=ENFORCED,
        observed_states={"missing": 5},
    )
    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is False
    assert _health(provenance)["fatal"] is True


def test_preparation_still_rejects_enforced_documents():
    """정책을 껐는데 산출물이 enforced 면 세대가 섞인 상태다."""
    provenance = evaluate_policy_provenance(
        expected_state=OFF,
        observed_states={ENFORCED: 3},
    )
    assert provenance["campusLifeZonePolicyProvenanceHealthy"] is False
    assert _health(provenance)["fatal"] is True


def test_meeting_and_one_to_one_verify_agree_on_legacy_handling():
    """두 verify 구현이 같은 규칙을 쓴다 (한쪽만 엄격하면 배포가 막힌다)."""
    from recsys.jobs.meeting_verify_policy import campus_life_zone_policy_failures

    one_to_one = evaluate_policy_provenance(
        expected_state=OFF, observed_states={"missing": 4}
    )["campusLifeZonePolicyProvenanceHealthy"]
    meeting = not campus_life_zone_policy_failures(
        {"meetingModelRecs": {"policyStates": {"missing": 4}}}, OFF
    )
    assert one_to_one is True and meeting is True

    one_to_one_on = evaluate_policy_provenance(
        expected_state=ENFORCED, observed_states={"missing": 4}
    )["campusLifeZonePolicyProvenanceHealthy"]
    meeting_on = not campus_life_zone_policy_failures(
        {"meetingModelRecs": {"policyStates": {"missing": 4}}}, ENFORCED
    )
    assert one_to_one_on is False and meeting_on is False


# --------------------------------------------------------- pair 감사 지표


def _meta(uid, zones, gender):
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


@pytest.mark.parametrize(
    "actor_zones,candidate_zones",
    [([], []), (["sinchon"], ["songdo"]), ([], ["sinchon"])],
)
def test_off_audit_does_not_reject_pairs_for_zones(actor_zones, candidate_zones):
    meta = {}
    meta.update(_meta("actor", actor_zones, "male"))
    meta.update(_meta("cand", candidate_zones, "female"))

    result = audit_policy_pairs(
        ["actor"],
        ["cand"],
        meta,
        now=pd.Timestamp("2026-08-26", tz="UTC"),
        require_same_campus_life_zone=False,
    )

    assert result["compatiblePairs"] == 1, result["firstFailureHistogram"]


def test_enforced_audit_still_rejects_cross_zone_pairs():
    meta = {}
    meta.update(_meta("actor", ["sinchon"], "male"))
    meta.update(_meta("cand", ["songdo"], "female"))

    result = audit_policy_pairs(
        ["actor"],
        ["cand"],
        meta,
        now=pd.Timestamp("2026-08-26", tz="UTC"),
        require_same_campus_life_zone=True,
    )

    assert result["compatiblePairs"] == 0
    assert "campus_life_zone_mismatch" in result["firstFailureHistogram"]


def test_audit_default_stays_fail_closed():
    """기본값은 계속 hard filter 다. 호출부가 명시적으로 완화해야 한다."""
    meta = {}
    meta.update(_meta("actor", ["sinchon"], "male"))
    meta.update(_meta("cand", ["songdo"], "female"))

    result = audit_policy_pairs(
        ["actor"], ["cand"], meta, now=pd.Timestamp("2026-08-26", tz="UTC")
    )

    assert result["compatiblePairs"] == 0
