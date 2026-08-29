from __future__ import annotations

from pathlib import Path


WORKFLOW_PATH = Path(__file__).parents[2] / "infra" / "workflows" / "recs_pipeline.yaml"
DEPLOY_PATH = Path(__file__).parents[2] / "infra" / "deploy.sh"


def test_workflow_resolves_one_kst_date_key_and_runs_meeting_steps_in_order():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert 'time.format(sys.now(), "Asia/Seoul")' in workflow
    assert 'text.substring' in workflow
    assert 'text.replace_all' in workflow

    expected = [
        "recs-meeting-group-index",
        "recs-meeting-recommend",
        "recs-meeting-daily",
        "recs-meeting-verify",
    ]
    positions = [workflow.index(f"/jobs/{job}") for job in expected]
    assert positions == sorted(positions)

    for step, job in zip(
        [
            "meeting-group-index",
            "meeting-recommend",
            "meeting-daily",
            "meeting-verify",
        ],
        expected,
    ):
        assert f'"--step={step}"' in workflow
        assert '"--project=" + project_id' in workflow
        assert '"--date-key=" + date_key' in workflow
        assert f"/jobs/{job}" in workflow

    assert '"--write-meeting-verify-doc"' in workflow
    assert "raise_meeting_group_index" in workflow
    assert "raise_meeting_recommend" in workflow
    assert "raise_meeting_daily" in workflow
    assert "raise_meeting_verify" in workflow


def test_one_to_one_verify_failure_propagates_before_meeting_steps():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    start = workflow.index("- run_verify:")
    end = workflow.index("- run_meeting_group_index:")
    verify_block = workflow[start:end]
    assert "Verify failed:" in verify_block
    assert "raise_verify" in verify_block


def test_deploy_script_declares_all_meeting_jobs_and_resources():
    deploy = DEPLOY_PATH.read_text(encoding="utf-8")
    expected = {
        "recs-meeting-group-index": ("--cpu=1", "--memory=2Gi", "--task-timeout=600"),
        "recs-meeting-recommend": ("--cpu=2", "--memory=8Gi", "--task-timeout=3600"),
        "recs-meeting-daily": ("--cpu=2", "--memory=8Gi", "--task-timeout=3600"),
        "recs-meeting-verify": ("--cpu=1", "--memory=1Gi", "--task-timeout=300"),
    }
    for job, resources in expected.items():
        start = deploy.index(f"create_or_update_job {job}")
        end = deploy.find("\n\n", start)
        block = deploy[start:] if end == -1 else deploy[start:end]
        for resource in resources:
            assert resource in block
        assert f"--step={job.removeprefix('recs-')}" in block
