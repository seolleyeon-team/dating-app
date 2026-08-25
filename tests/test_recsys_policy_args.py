"""Cloud Run entrypoint must forward the candidate policy and RRF quality gates.

The Cloud Workflow only passes --step/--date-key/--project/--bucket, so any
policy that is not defaulted here never runs in production.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from recsys.main import (  # noqa: E402
    build_model_script_args,
    build_rrf_script_args,
    build_parser,
)


def parse(*argv):
    """Parse exactly what the Cloud Workflow sends, plus any overrides."""
    args = build_parser().parse_args(list(argv))
    if not args.date_key:
        args.date_key = "20260727"
    return args


def arg_value(script_args, flag):
    return script_args[script_args.index(flag) + 1]


@pytest.mark.parametrize("step", ["clip", "svd", "knn"])
def test_workflow_invocation_enables_policy_filters(step):
    args = parse("--step", step, "--date-key", "20260727", "--project", "seolleyeon-final")

    script_args = build_model_script_args(args)

    assert "--apply_policy_filters" in script_args
    assert arg_value(script_args, "--policy_min_meta_coverage") == "0.9"
    assert "--no_require_same_university" not in script_args


def test_events_csv_is_passed_through_for_collaborative_steps():
    args = parse("--step", "svd", "--project", "seolleyeon-final")

    script_args = build_model_script_args(args, events_csv="/tmp/events.csv")

    assert arg_value(script_args, "--events_csv") == "/tmp/events.csv"


def test_policy_filters_can_be_disabled_explicitly():
    args = parse("--step", "clip", "--project", "p", "--no-apply-policy-filters")

    script_args = build_model_script_args(args)

    assert "--apply_policy_filters" not in script_args
    assert "--policy_min_meta_coverage" not in script_args


def test_workflow_invocation_keeps_firestore_blocks_enabled_by_default():
    # SVD/KNN train from events CSV; contact/report blocks live in Firestore only.
    args = parse("--step", "svd", "--project", "seolleyeon-final")

    script_args = build_model_script_args(args, events_csv="/tmp/events.csv")

    assert "--no_firestore_blocks" not in script_args


def test_firestore_blocks_can_be_disabled_explicitly():
    args = parse("--step", "knn", "--project", "p", "--no-firestore-blocks")

    script_args = build_model_script_args(args, events_csv="/tmp/events.csv")

    assert "--no_firestore_blocks" in script_args


def test_same_university_requirement_can_be_relaxed():
    args = parse("--step", "clip", "--project", "p", "--no-require-same-university")

    script_args = build_model_script_args(args)

    assert "--no_require_same_university" in script_args


def test_workflow_invocation_enforces_rrf_quality_gates():
    args = parse("--step", "rrf", "--date-key", "20260727", "--project", "seolleyeon-final")

    script_args = build_rrf_script_args(args)

    # A user with only SVD signal must not be exported as a fused feed.
    assert arg_value(script_args, "--required_sources") == "clip"
    assert arg_value(script_args, "--min_sources_per_user") == "1"
    assert arg_value(script_args, "--sources") == "clip,svd,knn"
    assert arg_value(script_args, "--topn") == "400"
    assert arg_value(script_args, "--max_items_per_source") == "400"
    assert "clip" in arg_value(script_args, "--source_weights_json")


def test_rrf_required_sources_omitted_when_blank():
    args = parse("--step", "rrf", "--project", "p", "--rrf-required-sources", "")

    script_args = build_rrf_script_args(args)

    assert "--required_sources" not in script_args


def test_firestore_database_is_forwarded_when_set():
    args = parse("--step", "rrf", "--project", "p", "--database", "recs-db")

    assert arg_value(build_rrf_script_args(args), "--firestore_database") == "recs-db"
    assert arg_value(build_model_script_args(args), "--firestore_database") == "recs-db"
