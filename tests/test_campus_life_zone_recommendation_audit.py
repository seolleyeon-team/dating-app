"""생성된 추천의 생활권 위반 감사 로직.

production 접근 없이 fixture 로 검증한다. 이 감사는 최종 활성화 직후의
release gate 이므로, cross-zone 을 하나라도 놓치면 안 되고 준비 단계(OFF)에서는
그것을 실패로 만들면 안 된다.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "scripts", ROOT / "lib" / "ai_recommend_model"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from campus_life_zone_recommendation_audit import (  # noqa: E402
    audit_group_index_consistency,
    audit_group_pairs,
    audit_pairs,
    document_policy_state,
    evaluate,
    zone_value_state,
)

SINCHON = ["sinchon"]
SONGDO = ["songdo"]
DUAL = ["sinchon", "songdo"]


# ------------------------------------------------------------------- 1:1 pair


def test_same_zone_pair_is_compatible():
    counts = audit_pairs([(SINCHON, SINCHON)])
    assert counts["compatible"] == 1
    assert counts.get("crossZoneMismatch", 0) == 0


def test_cross_zone_pair_is_counted():
    counts = audit_pairs([(SINCHON, SONGDO)])
    assert counts["crossZoneMismatch"] == 1
    assert counts.get("compatible", 0) == 0


def test_dual_zone_bridges_both_sides():
    assert audit_pairs([(DUAL, SONGDO)])["compatible"] == 1
    assert audit_pairs([(DUAL, SINCHON)])["compatible"] == 1
    assert audit_pairs([(SINCHON, DUAL)])["compatible"] == 1


def test_missing_zones_are_attributed_to_the_right_side():
    assert audit_pairs([(None, SINCHON)])["actorMissingZone"] == 1
    assert audit_pairs([(SINCHON, None)])["candidateMissingZone"] == 1
    assert audit_pairs([([], SINCHON)])["actorMissingZone"] == 1


def test_malformed_zones_are_counted_and_treated_as_missing():
    counts = audit_pairs([(["garbage"], SINCHON)])
    assert counts["actorMalformedZone"] == 1
    assert counts["actorMissingZone"] == 1

    counts = audit_pairs([(SINCHON, "sinchon")])
    assert counts["candidateMalformedZone"] == 1
    assert counts["candidateMissingZone"] == 1

    counts = audit_pairs([(SINCHON, ["sinchon", "garbage"])])
    assert counts["candidateMalformedZone"] == 1
    assert counts["candidateMissingZone"] == 1


def test_zone_value_state_classification():
    assert zone_value_state(None) == "missing"
    assert zone_value_state([]) == "missing"
    assert zone_value_state("sinchon") == "invalid_type"
    assert zone_value_state([1]) == "invalid_item_type"
    assert zone_value_state(["garbage"]) == "unknown_token"
    assert zone_value_state(["sinchon", "garbage"]) == "mixed_unknown_token"
    assert zone_value_state(["sinchon"]) == "valid"


# ----------------------------------------------------------------- group pair


def test_same_zone_groups_are_compatible():
    assert audit_group_pairs([(SINCHON, SINCHON)])["compatibleGroupPairs"] == 1


def test_cross_zone_group_recommendation_is_counted():
    assert (
        audit_group_pairs([(SINCHON, SONGDO)])["crossZoneGroupRecommendation"] == 1
    )


def test_dual_zone_groups_bridge():
    assert audit_group_pairs([(DUAL, SONGDO)])["compatibleGroupPairs"] == 1


def test_group_missing_shared_zone_is_counted():
    assert audit_group_pairs([(None, SINCHON)])["actorGroupMissingSharedZone"] == 1
    assert audit_group_pairs([(SINCHON, [])])["candidateGroupMissingSharedZone"] == 1


# ------------------------------------------------------- group index 정합성


def test_group_index_consistency_detects_stale_derived_field():
    # 저장된 파생 값이 멤버 교집합과 같다
    assert (
        audit_group_index_consistency(SINCHON, [SINCHON, SINCHON, SINCHON])
        == "consistent"
    )
    # 멤버는 교집합이 없는데 파생 값이 남아 있다 (가장 위험한 경우)
    assert (
        audit_group_index_consistency(SINCHON, [SINCHON, SONGDO, SINCHON])
        == "stored_stale"
    )
    # 파생 값이 비었는데 멤버는 교집합이 있다
    assert audit_group_index_consistency(None, [SINCHON, SINCHON, SINCHON]) == (
        "stored_missing"
    )
    # 서로 다른 값
    assert (
        audit_group_index_consistency(SONGDO, [SINCHON, SINCHON, SINCHON])
        == "mismatch"
    )


# ------------------------------------------------------------------ provenance


def test_document_policy_state_reading():
    assert document_policy_state({"policy": {"campusLifeZone": "off"}}) == "off"
    assert (
        document_policy_state({"policy": {"campusLifeZone": "enforced"}}) == "enforced"
    )
    assert document_policy_state({"policy": {}}) == "missing"
    assert document_policy_state({}) == "missing"
    assert document_policy_state(None) == "missing"


# -------------------------------------------------------------- release gate


def _report(**overrides):
    report = {
        "expectedPolicy": "off",
        "oneToOne": {},
        "season": {},
        "blind": {},
        "policyProvenance": {},
    }
    report.update(overrides)
    return report


def test_off_audit_does_not_fail_on_observed_cross_zone():
    """준비 단계에서는 cross-zone 이 정상이다 (아직 거르지 않으므로)."""
    report = _report(
        oneToOne={"crossZoneMismatch": 120, "actorMissingZone": 400},
        season={"crossZoneGroupRecommendation": 5},
        blind={"crossZoneMeetings": 2},
        policyProvenance={"modelRecs": {"off": 74}},
    )
    assert evaluate(report, "off") == []


def test_off_audit_fails_when_documents_claim_enforced():
    report = _report(policyProvenance={"modelRecs": {"enforced": 3}})
    assert "modelRecs:policy_enforced" in evaluate(report, "off")


def test_off_audit_allows_legacy_documents_without_provenance():
    report = _report(policyProvenance={"modelRecs": {"missing": 74}})
    assert evaluate(report, "off") == []


def test_enforced_audit_fails_on_any_cross_zone():
    report = _report(oneToOne={"crossZoneMismatch": 1})
    assert "oneToOne:crossZoneMismatch" in evaluate(report, "enforced")


def test_enforced_audit_fails_on_missing_or_malformed():
    assert "oneToOne:actorMissingZone" in evaluate(
        _report(oneToOne={"actorMissingZone": 1}), "enforced"
    )
    assert "oneToOne:candidateMalformedZone" in evaluate(
        _report(oneToOne={"candidateMalformedZone": 1}), "enforced"
    )


def test_enforced_audit_fails_on_cross_zone_groups_and_meetings():
    assert "season:crossZoneGroupRecommendation" in evaluate(
        _report(season={"crossZoneGroupRecommendation": 1}), "enforced"
    )
    assert "blind:crossZoneMeetings" in evaluate(
        _report(blind={"crossZoneMeetings": 1}), "enforced"
    )


def test_enforced_audit_requires_enforced_provenance():
    report = _report(policyProvenance={"meetingDailyRecs": {"missing": 4}})
    assert "meetingDailyRecs:policy_missing" in evaluate(report, "enforced")


def test_enforced_audit_passes_on_clean_result():
    report = _report(
        oneToOne={"compatible": 500, "pairs": 500},
        season={"compatibleGroupPairs": 10, "groupPairs": 10},
        blind={"compatibleMeetings": 3, "meetings": 3},
        policyProvenance={
            "modelRecs": {"enforced": 74},
            "dailyRecs": {"enforced": 74},
            "meetingModelRecs": {"enforced": 10},
            "meetingDailyRecs": {"enforced": 10},
        },
    )
    assert evaluate(report, "enforced") == []


# ------------------------------------------------------------------ 안전 계약


def test_audit_script_never_writes_to_firestore():
    """감사 도구가 write 를 하지 않는지 소스 수준에서 확인한다."""
    source = (ROOT / "scripts" / "campus_life_zone_recommendation_audit.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    forbidden = {"set", "update", "delete", "create", "commit", "add"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden, (
                "감사 도구는 읽기 전용이어야 한다: .%s(" % node.func.attr
            )
    # HTTP 메서드도 GET 만 쓴다 (urllib 기본값).
    assert "method=" not in source
    assert '"POST"' not in source and "'POST'" not in source


def test_audit_report_contains_no_user_identifiers():
    counts = audit_pairs([(SINCHON, SONGDO)])
    assert all(isinstance(value, int) for value in counts.values())
