from __future__ import annotations

import sys
import unittest
from pathlib import Path


MODEL_DIR = Path(__file__).resolve().parents[2] / "lib" / "ai_recommend_model"
sys.path.insert(0, str(MODEL_DIR))

from seolleyeon_recommendation_privacy import (  # noqa: E402
    build_recommendation_privacy_policy,
    filter_recommendations,
)


def _users(*uids: str):
    return [
        (
            uid,
            {
                "recommendationPrivacyReady": True,
                "isStudentVerified": True,
                "initialSetupComplete": True,
            },
        )
        for uid in uids
    ]


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

    def test_not_ready_users_are_removed_and_ranks_are_compacted(self):
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
            [],
        )

        filtered, stats = filter_recommendations(
            {
                "a": [
                    {"uid": "b", "rank": 1, "score": 0.9},
                    {"uid": "c", "rank": 2, "score": 0.8},
                ],
                "b": [{"uid": "a", "rank": 1}],
            },
            policy,
        )

        self.assertEqual(
            filtered,
            {"a": [{"uid": "c", "rank": 1, "score": 0.8}]},
        )
        self.assertEqual(stats["droppedViewers"], 1)
        self.assertEqual(stats["droppedCandidates"], 2)

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

        self.assertEqual(policy.ready_user_ids, frozenset({"active"}))

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
