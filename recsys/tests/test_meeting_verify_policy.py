from __future__ import annotations

from recsys.jobs.meeting_verify_policy import build_meeting_verification_summary


def test_no_ready_groups_is_a_successful_no_input_run():
    summary = build_meeting_verification_summary("20260802", {}, {}, {})
    assert summary["status"] == "no_input"
    assert summary["healthy"] is True
    assert summary["readyGroups"] == 0


def test_complete_ready_group_is_healthy():
    groups = {
        "g-ready": {"index_status": "ready"},
        "g-skipped": {"index_status": "skipped", "skip_reason": "not_open"},
    }
    model_docs = {
        "g-ready": {
            "status": "ready",
            "algorithmVersion": "meeting_group_ranker_v1_20260802",
            "items": [{"groupId": "g-other"}],
        }
    }
    daily_docs = {
        "g-ready": {
            "status": "ready",
            "algorithmVersion": "meeting_daily_v1_20260802",
            "candidates": [{"groupId": "g-other"}],
        }
    }

    summary = build_meeting_verification_summary(
        "20260802", groups, model_docs, daily_docs
    )
    assert summary["status"] == "healthy"
    assert summary["healthy"] is True
    assert summary["readyGroups"] == 1
    assert summary["skippedGroups"] == 1
    assert summary["meetingModelRecs"]["missing"] == 0
    assert summary["meetingDailyRecs"]["missing"] == 0
    assert summary["modelReady"] == 1
    assert summary["dailyReady"] == 1
    assert summary["skipReasonHistogram"]["not_open"] == 1


def test_ready_group_missing_outputs_is_a_hard_failure():
    groups = {"g-ready": {"index_status": "ready"}}
    summary = build_meeting_verification_summary(
        "20260802", groups, {}, {}
    )
    assert summary["status"] == "failed"
    assert summary["healthy"] is False
    assert summary["meetingModelRecs"]["missing"] == 1
    assert summary["meetingDailyRecs"]["missing"] == 1
    assert "meetingModelRecs:missing" in summary["failureReasons"]
    assert "meetingDailyRecs:missing" in summary["failureReasons"]


def test_empty_domain_outputs_are_valid_when_documents_exist():
    groups = {"g-ready": {"index_status": "ready"}}
    model_docs = {"g-ready": {"status": "empty", "items": []}}
    daily_docs = {"g-ready": {"status": "empty", "candidates": []}}
    summary = build_meeting_verification_summary(
        "20260802", groups, model_docs, daily_docs
    )
    assert summary["status"] == "healthy"
    assert summary["meetingModelRecs"]["empty"] == 1
    assert summary["meetingDailyRecs"]["empty"] == 1


def test_invalid_status_or_shape_is_malformed_and_fails():
    groups = {"g-ready": {"index_status": "ready"}}
    model_docs = {"g-ready": {"status": "ready", "items": []}}
    daily_docs = {"g-ready": {"status": "unexpected", "candidates": []}}
    summary = build_meeting_verification_summary(
        "20260802", groups, model_docs, daily_docs
    )
    assert summary["status"] == "failed"
    assert summary["meetingModelRecs"]["malformed"] == 1
    assert summary["meetingDailyRecs"]["malformed"] == 1
