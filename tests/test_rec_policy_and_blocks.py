"""Block/report exclusion and policy metadata sourcing for the 1:1 pipeline."""
import sys
from pathlib import Path

import pandas as pd
import pytest

AI_MODEL_DIR = Path(__file__).resolve().parents[1] / "lib" / "ai_recommend_model"
if str(AI_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(AI_MODEL_DIR))

from seolleyeon_rec_common_v3 import (  # noqa: E402
    assert_policy_meta_coverage,
    block_edges_from_owner_targets,
    build_mutual_block_index,
    build_policy_meta_from_user_docs,
    extend_mutual_block_index,
    same_department_avoidance_rejection,
    passes_policy,
    resolve_mutual_block_index,
    university_id_from_student_email,
)


def events(*rows):
    return pd.DataFrame(list(rows), columns=["user_id", "item_id", "event", "ts"])


# ---------------------------------------------------------------------------
# Mutual block/report exclusion
# ---------------------------------------------------------------------------

def test_block_hides_each_user_from_the_other():
    index = build_mutual_block_index(events(("alice", "bob", "block", None)))

    assert index["alice"] == {"bob"}
    # Without the reverse edge, the blocked user keeps receiving the blocker.
    assert index["bob"] == {"alice"}


def test_report_is_treated_as_a_mutual_block():
    index = build_mutual_block_index(events(("carol", "dave", "report", None)))

    assert index["carol"] == {"dave"}
    assert index["dave"] == {"carol"}


def test_nope_stays_one_directional():
    index = build_mutual_block_index(events(("alice", "bob", "nope", None)))

    assert index == {}


def test_positive_events_never_create_exclusions():
    index = build_mutual_block_index(
        events(
            ("alice", "bob", "like", None),
            ("alice", "bob", "match_created", None),
            ("alice", "bob", "chat_first_message", None),
        )
    )

    assert index == {}


def test_multiple_blocks_accumulate_per_user():
    index = build_mutual_block_index(
        events(
            ("alice", "bob", "block", None),
            ("carol", "alice", "report", None),
        )
    )

    assert index["alice"] == {"bob", "carol"}
    assert index["bob"] == {"alice"}
    assert index["carol"] == {"alice"}


def test_self_blocks_and_empty_input_are_ignored():
    assert build_mutual_block_index(events(("alice", "alice", "block", None))) == {}
    assert build_mutual_block_index(events()) == {}


# ---------------------------------------------------------------------------
# Firestore blocks / contact blocks (SEC-P1-06)
# ---------------------------------------------------------------------------

def test_firestore_block_edges_are_parsed_from_owner_target_map():
    # blocks/{owner}/targets/{target} — contact sync and reportAndBlock both land here.
    edges = block_edges_from_owner_targets(
        {
            "alice": ["bob", "carol", "alice", ""],
            "": ["dave"],
            "erin": [],
        }
    )

    assert set(edges) == {("alice", "bob"), ("alice", "carol")}


def test_firestore_blocks_merge_into_event_based_index():
    # Contact blocks never write recEvents; without Firestore edges they are invisible.
    index = resolve_mutual_block_index(
        events(("alice", "bob", "like", None)),
        firestore_block_edges=[("alice", "carol")],
    )

    assert index["alice"] == {"carol"}
    assert index["carol"] == {"alice"}
    assert "bob" not in index.get("alice", set())


def test_firestore_blocks_cover_pairs_outside_rec_events_lookback():
    # Active blocks collection is the source of truth; old recEvents may age out.
    index = resolve_mutual_block_index(
        events(),
        firestore_block_edges=[("alice", "bob"), ("bob", "alice")],
    )

    assert index["alice"] == {"bob"}
    assert index["bob"] == {"alice"}


def test_extend_mutual_block_index_is_symmetric_and_idempotent():
    base = build_mutual_block_index(events(("alice", "bob", "block", None)))
    once = extend_mutual_block_index(base, [("carol", "alice")])
    twice = extend_mutual_block_index(once, [("carol", "alice"), ("alice", "carol")])

    assert once["alice"] == {"bob", "carol"}
    assert once["carol"] == {"alice"}
    assert twice == once


# ---------------------------------------------------------------------------
# Policy metadata derived from `users`
# ---------------------------------------------------------------------------

def verified_user_doc(**overrides):
    # 생활권은 hard eligibility다. 정상 사용자 fixture는 같은 생활권을 갖고,
    # 생활권 자체를 검증하는 테스트만 onboarding 을 덮어쓴다.
    doc = {
        "isStudentVerified": True,
        "initialSetupComplete": True,
        "studentEmail": "someone@yonsei.ac.kr",
        "onboarding": {
            "gender": "female",
            "birthYear": 2002,
            "campusLifeZones": ["sinchon"],
        },
        "idealType": {"idealAge": {"min": 20, "max": 28}},
    }
    doc.update(overrides)
    return doc


def test_policy_meta_is_derived_from_users_when_profile_index_is_absent():
    meta = build_policy_meta_from_user_docs(
        {
            "u1": verified_user_doc(
                onboarding={
                    "gender": "female",
                    "birthYear": 2002,
                    "department": " 컴퓨터과학과 ",
                    "campusLifeZones": ["sinchon"],
                },
                privacySettings={"avoidSameDepartment": True},
            )
        }
    )

    assert meta["u1"]["isVerified"] is True
    assert meta["u1"]["isActive"] is True
    assert meta["u1"]["isProfileComplete"] is True
    assert meta["u1"]["gender"] == "female"
    assert meta["u1"]["birthYear"] == 2002
    assert meta["u1"]["universityId"] == "yonsei"
    assert meta["u1"]["prefAgeMin"] == 20
    assert meta["u1"]["prefAgeMax"] == 28
    assert meta["u1"]["department"] == "컴퓨터과학과"
    assert meta["u1"]["avoidSameDepartment"] is True


def test_same_department_avoidance_is_bilateral_and_missing_department_is_safe():
    meta = build_policy_meta_from_user_docs(
        {
            "viewer": verified_user_doc(
                onboarding={
                    "gender": "male",
                    "birthYear": 2001,
                    "department": "컴퓨터과학과",
                    "campusLifeZones": ["sinchon"],
                }
            ),
            "candidate": verified_user_doc(
                onboarding={
                    "gender": "female",
                    "birthYear": 2002,
                    "department": "컴퓨터과학과",
                    "campusLifeZones": ["sinchon"],
                },
                privacySettings={"avoidSameDepartment": True},
            ),
            "unknown": verified_user_doc(
                onboarding={
                    "gender": "female",
                    "birthYear": 2002,
                    "campusLifeZones": ["sinchon"],
                },
                privacySettings={"avoidSameDepartment": True},
            ),
        }
    )

    assert same_department_avoidance_rejection(meta["viewer"], meta["candidate"])
    assert same_department_avoidance_rejection(meta["candidate"], meta["viewer"])
    assert not same_department_avoidance_rejection(meta["viewer"], meta["unknown"])
    policy = dict(
        manner_min=33.0,
        active_within_days=14,
        require_same_university=True,
        reciprocal=False,
    )
    assert passes_policy("viewer", "candidate", meta, **policy) is False
    assert passes_policy("candidate", "viewer", meta, **policy) is False


def test_policy_meta_uses_login_activity_writer_and_modern_ideal_age_fields():
    recent = pd.Timestamp("2026-08-24", tz="UTC")
    meta = build_policy_meta_from_user_docs(
        {
            "u1": verified_user_doc(
                lastActivePlatformUpdatedAt=recent,
                idealType={"minAge": 23, "maxAge": 27},
            )
        }
    )

    assert meta["u1"]["lastActiveAt"] == recent
    assert meta["u1"]["activitySource"] == "users.lastActivePlatformUpdatedAt"
    assert meta["u1"]["activityReason"] == "login_activity"
    assert meta["u1"]["profileCompleteSource"] == "users.initialSetupComplete"
    assert meta["u1"]["profileCompleteReason"] == "canonical_true"
    assert meta["u1"]["activeSource"] == "users.account_status"
    assert meta["u1"]["activeReason"] == "no_blocking_status"
    assert meta["u1"]["prefAgeMin"] == 23
    assert meta["u1"]["prefAgeMax"] == 27


def test_unverified_and_suspended_users_are_marked_ineligible():
    meta = build_policy_meta_from_user_docs(
        {
            "unverified": verified_user_doc(isStudentVerified=False),
            "suspended": verified_user_doc(isSuspended=True),
            "deleted": verified_user_doc(status="deleted"),
            "incomplete": verified_user_doc(initialSetupComplete=False),
        }
    )

    assert meta["unverified"]["isVerified"] is False
    assert meta["suspended"]["isActive"] is False
    assert meta["deleted"]["isActive"] is False
    assert meta["incomplete"]["isProfileComplete"] is False


def test_derived_meta_lets_passes_policy_reject_unverified_candidates():
    meta = build_policy_meta_from_user_docs(
        {
            "viewer": verified_user_doc(
                onboarding={
                    "gender": "male",
                    "birthYear": 2001,
                    "campusLifeZones": ["sinchon"],
                }
            ),
            "ok": verified_user_doc(),
            "unverified": verified_user_doc(isStudentVerified=False),
        }
    )
    policy = dict(manner_min=33.0, active_within_days=14, require_same_university=True, reciprocal=False)

    assert passes_policy("viewer", "ok", meta, **policy) is True
    assert passes_policy("viewer", "unverified", meta, **policy) is False


def test_same_university_check_works_off_the_student_email_domain():
    meta = build_policy_meta_from_user_docs(
        {
            "viewer": verified_user_doc(),
            "other_school": verified_user_doc(studentEmail="someone@korea.ac.kr"),
        }
    )
    policy = dict(manner_min=33.0, active_within_days=14, reciprocal=False)

    assert passes_policy("viewer", "other_school", meta, require_same_university=True, **policy) is False
    assert passes_policy("viewer", "other_school", meta, require_same_university=False, **policy) is True


@pytest.mark.parametrize(
    "email,expected",
    [
        ("a@yonsei.ac.kr", "yonsei"),
        ("a@cs.yonsei.ac.kr", "yonsei"),
        ("a@korea.ac.kr", "korea"),
        ("a@mit.edu", "mit"),
        ("not-an-email", None),
        (None, None),
    ],
)
def test_university_id_from_student_email(email, expected):
    assert university_id_from_student_email(email) == expected


# ---------------------------------------------------------------------------
# Fail-loud coverage guard
# ---------------------------------------------------------------------------

def test_sparse_policy_metadata_aborts_the_export():
    meta = build_policy_meta_from_user_docs({"u1": verified_user_doc()})

    with pytest.raises(ValueError, match="covers only 1/4"):
        assert_policy_meta_coverage(
            meta, ["u1", "u2", "u3", "u4"], min_coverage=0.9, source="users"
        )


def test_empty_policy_metadata_aborts_instead_of_exporting_nothing():
    with pytest.raises(ValueError, match="profileIndex"):
        assert_policy_meta_coverage({}, ["u1"], min_coverage=0.9, source="profileIndex")


def test_full_coverage_passes():
    meta = build_policy_meta_from_user_docs(
        {"u1": verified_user_doc(), "u2": verified_user_doc()}
    )

    assert assert_policy_meta_coverage(meta, ["u1", "u2"], min_coverage=0.9, source="users") == 1.0


def test_coverage_check_is_a_noop_without_candidates():
    assert assert_policy_meta_coverage({}, [], min_coverage=1.0, source="users") == 1.0
