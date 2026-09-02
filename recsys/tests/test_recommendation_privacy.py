from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from pathlib import Path


MODEL_DIR = Path(__file__).resolve().parents[2] / "lib" / "ai_recommend_model"
sys.path.insert(0, str(MODEL_DIR))

from seolleyeon_recommendation_privacy import (  # noqa: E402
    _is_active_exclusion,
    build_recommendation_privacy_policy,
    filter_recommendations,
    load_recommendation_privacy_policy,
)


def _users(*uids: str):
    # Deliberately does NOT set recommendationPrivacyReady: eligibility is
    # account-state only (kakao friend pairs are handled per-pair).
    return [
        (
            uid,
            {
                "isStudentVerified": True,
                "initialSetupComplete": True,
            },
        )
        for uid in uids
    ]


class _FakeDoc:
    def __init__(self, doc_id: str, data: dict, path: str):
        self.id = doc_id
        self._data = data
        self.reference = SimpleNamespace(path=path)

    def to_dict(self):
        return self._data


class _FakeDb:
    def __init__(self, users, exclusions):
        self._users = users
        self._exclusions = exclusions

    def collection(self, name):
        assert name == "users"
        return SimpleNamespace(stream=lambda: iter(self._users))

    def collection_group(self, name):
        assert name == "targets"
        return SimpleNamespace(stream=lambda: iter(self._exclusions))


class RecommendationPrivacyPolicyTest(unittest.TestCase):
    def test_one_enabled_friend_setting_blocks_both_directions(self):
        policy = build_recommendation_privacy_policy(
            _users("a", "b", "c"),
            [("a", "c", {"enabledBy": {"a": True, "c": False}})],
        )

        self.assertFalse(policy.allows("a", "c"))
        self.assertFalse(policy.allows("c", "a"))
        self.assertTrue(policy.allows("b", "c"))

    def test_missing_reverse_document_is_still_mirrored_fail_closed(self):
        policy = build_recommendation_privacy_policy(
            _users("a", "c"),
            [("c", "a", {"active": True})],
        )

        self.assertEqual(policy.excluded_by_viewer["a"], frozenset({"c"}))
        self.assertEqual(policy.excluded_by_viewer["c"], frozenset({"a"}))

    def test_loader_includes_same_department_exclusion_collection(self):
        policy = load_recommendation_privacy_policy(
            _FakeDb(
                [
                    _FakeDoc(uid, data, f"users/{uid}")
                    for uid, data in _users("a", "b")
                ],
                [
                    _FakeDoc(
                        "b",
                        {"active": True},
                        "departmentRecommendationExclusions/a/targets/b",
                    )
                ],
            )
        )

        self.assertFalse(policy.allows("a", "b"))
        self.assertFalse(policy.allows("b", "a"))

    def test_recommendation_privacy_ready_flag_no_longer_gates_eligibility(self):
        # The legacy Kakao-sync pending gate is gone: users lacking (or even
        # explicitly failing) recommendationPrivacyReady are eligible as long
        # as their account state qualifies.  Pair exclusions still filter
        # bilaterally, and surviving items keep compacted ranks.
        policy = build_recommendation_privacy_policy(
            [
                ("a", dict(_users("a")[0][1])),
                (
                    "b",
                    {
                        **_users("b")[0][1],
                        "recommendationPrivacyReady": False,
                    },
                ),
                ("c", dict(_users("c")[0][1])),
            ],
            [("a", "b", {"active": True, "source": "kakao_friend_pair"})],
        )

        self.assertEqual(policy.ready_user_ids, frozenset({"a", "b", "c"}))
        self.assertFalse(policy.allows("a", "b"))
        self.assertFalse(policy.allows("b", "a"))
        self.assertTrue(policy.allows("b", "c"))

        filtered, stats = filter_recommendations(
            {
                "a": [
                    {"uid": "b", "rank": 1, "score": 0.9},
                    {"uid": "c", "rank": 2, "score": 0.8},
                ],
                "b": [{"uid": "c", "rank": 1, "score": 0.7}],
            },
            policy,
        )

        self.assertEqual(
            filtered,
            {
                "a": [{"uid": "c", "rank": 1, "score": 0.8}],
                "b": [{"uid": "c", "rank": 1, "score": 0.7}],
            },
        )
        self.assertEqual(stats["droppedViewers"], 0)
        self.assertEqual(stats["droppedCandidates"], 1)

    def test_active_exclusion_accepts_new_and_legacy_doc_shapes(self):
        # New writer shape: kakaoFriendPairs materialization.
        self.assertTrue(
            _is_active_exclusion(
                {
                    "active": True,
                    "source": "kakao_friend_pair",
                    "enabledBy": {"a": True, "b": False},
                }
            )
        )
        # New shape without the compat enabledBy mirror still counts.
        self.assertTrue(
            _is_active_exclusion({"active": True, "source": "kakao_friend_pair"})
        )
        # Legacy shape: enabledBy any-true, no ``active`` field.
        self.assertTrue(_is_active_exclusion({"enabledBy": {"a": True}}))
        self.assertTrue(
            _is_active_exclusion({"enabledBy": {"a": False, "b": True}})
        )
        # Inactive / malformed docs stay excluded from the exclusion set.
        self.assertFalse(_is_active_exclusion({}))
        self.assertFalse(_is_active_exclusion({"active": False}))
        self.assertFalse(_is_active_exclusion({"active": "true"}))
        self.assertFalse(_is_active_exclusion({"enabledBy": {"a": False}}))
        self.assertFalse(_is_active_exclusion({"enabledBy": {"a": "true"}}))
        self.assertFalse(_is_active_exclusion({"enabledBy": ["a"]}))

    def test_inactive_accounts_never_enter_the_ready_pool(self):
        policy = build_recommendation_privacy_policy(
            [
                ("active", dict(_users("active")[0][1])),
                (
                    "suspended",
                    {
                        **_users("suspended")[0][1],
                        "status": "suspended",
                    },
                ),
                (
                    "hidden",
                    {
                        **_users("hidden")[0][1],
                        "profileVisible": False,
                    },
                ),
            ],
            [],
        )

        # A hidden profile can still receive recommendations as a viewer.
        self.assertEqual(policy.ready_user_ids, frozenset({"active", "hidden"}))
        self.assertEqual(policy.candidate_user_ids, frozenset({"active"}))

    def test_hidden_profile_keeps_its_own_feed_but_is_not_a_candidate_tomorrow(self):
        hidden = {
            **_users("hidden")[0][1],
            "profileVisible": False,
            "profileVisibleBeforeEffectiveDate": True,
            "profileVisibleEffectiveDateKey": "20260902",
        }
        visible = dict(_users("visible")[0][1])

        today = build_recommendation_privacy_policy(
            [("hidden", hidden), ("visible", visible)],
            [],
            date_key="20260901",
        )
        tomorrow = build_recommendation_privacy_policy(
            [("hidden", hidden), ("visible", visible)],
            [],
            date_key="20260902",
        )

        # Turning off is not retroactive for the already-generated day.
        self.assertTrue(today.allows("visible", "hidden"))
        # The owner remains a viewer after turning off their public profile.
        self.assertTrue(tomorrow.allows("hidden", "visible"))
        self.assertFalse(tomorrow.allows("visible", "hidden"))

    def test_showing_a_hidden_profile_waits_until_its_effective_date(self):
        pending_show = {
            **_users("pending")[0][1],
            "profileVisible": True,
            "profileVisibleBeforeEffectiveDate": False,
            "profileVisibleEffectiveDateKey": "20260902",
        }
        other = dict(_users("other")[0][1])

        today = build_recommendation_privacy_policy(
            [("pending", pending_show), ("other", other)],
            [],
            date_key="20260901",
        )
        tomorrow = build_recommendation_privacy_policy(
            [("pending", pending_show), ("other", other)],
            [],
            date_key="20260902",
        )

        self.assertFalse(today.allows("other", "pending"))
        self.assertTrue(tomorrow.allows("other", "pending"))

    def test_unverified_or_incomplete_accounts_never_enter_the_ready_pool(self):
        policy = build_recommendation_privacy_policy(
            [
                ("active", dict(_users("active")[0][1])),
                (
                    "unverified",
                    {
                        **_users("unverified")[0][1],
                        "isStudentVerified": False,
                    },
                ),
                (
                    "incomplete",
                    {
                        **_users("incomplete")[0][1],
                        "initialSetupComplete": False,
                    },
                ),
            ],
            [],
        )

        self.assertEqual(policy.ready_user_ids, frozenset({"active"}))


if __name__ == "__main__":
    unittest.main()
