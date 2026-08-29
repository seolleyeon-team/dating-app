"""Pure, deterministic tests for the daily 1:1 selector."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

AI_MODEL_DIR = Path(__file__).resolve().parents[2] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from recsys.jobs.daily_recommender import (  # noqa: E402
    DailySelectionConfig,
    select_daily_items,
)


def policy_meta(
    uid: str,
    *,
    gender: str = "female",
    birth_year: int = 2002,
    university: str = "yonsei",
    pref_gender: list[str] | None = None,
    pref_age_min: int | None = None,
    pref_age_max: int | None = None,
    active: bool = True,
    verified: bool = True,
    complete: bool = True,
    campus_life_zones: list[str] | None = None,
) -> dict:
    return {
        uid: {
            "universityId": university,
            "isVerified": verified,
            "isActive": active,
            "isProfileComplete": complete,
            "gender": gender,
            "birthYear": birth_year,
            "prefGender": pref_gender or [],
            "prefAgeMin": pref_age_min,
            "prefAgeMax": pref_age_max,
            "mannerScore": 36.5,
            "lastActiveAt": None,
            # 생활권은 hard eligibility다. 기본 fixture는 같은 생활권을 쓰고,
            # 생활권 자체를 검증하는 테스트만 명시적으로 덮어쓴다.
            "campusLifeZones": (
                ["sinchon"] if campus_life_zones is None else campus_life_zones
            ),
        }
    }


def merge_meta(*metas: dict) -> dict:
    result: dict = {}
    for meta in metas:
        result.update(meta)
    return result


def rrf(*rows: tuple[str, float]) -> list[dict]:
    return [
        {
            "uid": uid,
            "rank": rank,
            "score": score,
            "sourceRanks": {"clip": rank},
        }
        for rank, (uid, score) in enumerate(rows, start=1)
    ]


def test_ready_top3_contains_two_exploit_items_and_one_explore_item():
    meta = merge_meta(
        policy_meta("actor", gender="male"),
        policy_meta("u1", gender="female"),
        policy_meta("u2", gender="female"),
        policy_meta("u3", gender="female"),
    )
    result = select_daily_items(
        "actor",
        rrf(("u1", 0.99), ("u2", 0.98), ("u3", 0.50)),
        meta,
        date_key="20260824",
        candidate_docs={
            "u1": {"interests": ["music"]},
            "u2": {"interests": ["music"]},
            "u3": {"interests": ["hiking", "travel"]},
        },
    )

    assert result["status"] == "ready"
    assert len(result["items"]) == 3
    assert [item["uid"] for item in result["items"][:2]] == ["u1", "u2"]
    assert sum(item["isExplore"] for item in result["items"]) == 1
    assert result["items"][2]["uid"] == "u3"
    assert result["selection"]["exploitCount"] == 2
    assert result["selection"]["exploreCount"] == 1


def test_empty_when_only_self_or_synthetic_candidates_remain():
    meta = merge_meta(policy_meta("actor", gender="male"))
    result = select_daily_items(
        "actor",
        rrf(("actor", 1.0), ("female_001", 0.9)),
        meta,
        date_key="20260824",
    )

    assert result["status"] == "empty"
    assert result["items"] == []
    assert result["selection"]["rejected"]["self"] == 1
    assert result["selection"]["rejected"]["synthetic"] == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("isActive", False),
        ("isVerified", False),
        ("isProfileComplete", False),
    ],
)
def test_policy_rejects_inactive_unverified_or_incomplete_candidate(field, value):
    actor = policy_meta("actor", gender="male")
    candidate = policy_meta("candidate", gender="female")
    candidate["candidate"][field] = value

    result = select_daily_items(
        "actor",
        rrf(("candidate", 1.0)),
        merge_meta(actor, candidate),
        date_key="20260824",
    )

    assert result["status"] == "empty"
    assert result["selection"]["rejected"]["policy"] == 1


def test_gender_age_university_and_reciprocal_policy_are_applied():
    actor = policy_meta(
        "actor",
        gender="male",
        birth_year=2002,
        pref_age_min=23,
        pref_age_max=24,
    )
    same_gender = policy_meta("same", gender="male", birth_year=2003)
    wrong_age = policy_meta("old", gender="female", birth_year=1998)
    wrong_school = policy_meta("school", gender="female", university="korea")
    wrong_reciprocal = policy_meta(
        "reciprocal",
        gender="female",
        pref_gender=["female"],
        birth_year=2003,
    )
    result = select_daily_items(
        "actor",
        rrf(("same", 1.0), ("old", 0.9), ("school", 0.8), ("reciprocal", 0.7)),
        merge_meta(actor, same_gender, wrong_age, wrong_school, wrong_reciprocal),
        date_key="20260824",
    )

    assert result["status"] == "empty"
    assert result["selection"]["rejected"]["gender"] == 1
    assert result["selection"]["rejected"]["policy"] == 3


def test_mutual_block_report_nope_and_recent_exposure_are_hard_exclusions():
    meta = merge_meta(
        policy_meta("actor", gender="male"),
        policy_meta("blocked", gender="female"),
        policy_meta("reported", gender="female"),
        policy_meta("noped", gender="female"),
        policy_meta("seen", gender="female"),
    )
    result = select_daily_items(
        "actor",
        rrf(("blocked", 1.0), ("reported", 0.9), ("noped", 0.8), ("seen", 0.7)),
        meta,
        date_key="20260824",
        blocked_by_actor={"blocked", "reported"},
        nope_by_actor={"noped"},
        recent_exposure_by_actor={"seen"},
    )

    assert result["status"] == "empty"
    assert result["selection"]["rejected"]["blocked_or_reported"] == 2
    assert result["selection"]["rejected"]["nope"] == 1
    assert result["selection"]["rejected"]["recent_exposure"] == 1


def test_selection_is_deterministic_for_same_actor_and_date():
    meta = merge_meta(
        policy_meta("actor", gender="male"),
        policy_meta("u1", gender="female"),
        policy_meta("u2", gender="female"),
        policy_meta("u3", gender="female"),
        policy_meta("u4", gender="female"),
    )
    candidates = rrf(("u1", 0.7), ("u2", 0.7), ("u3", 0.7), ("u4", 0.7))
    first = select_daily_items("actor", candidates, meta, date_key="20260824")
    second = select_daily_items("actor", candidates, meta, date_key="20260824")

    assert first == second
    assert [item["rank"] for item in first["items"]] == [1, 2, 3]


def test_topn_can_return_a_smaller_ready_feed_without_faking_items():
    meta = merge_meta(
        policy_meta("actor", gender="male"),
        policy_meta("u1", gender="female"),
    )
    result = select_daily_items(
        "actor",
        rrf(("u1", 1.0)),
        meta,
        date_key="20260824",
        config=DailySelectionConfig(topn=3),
    )

    assert result["status"] == "ready"
    assert [item["uid"] for item in result["items"]] == ["u1"]
