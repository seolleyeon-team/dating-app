from __future__ import annotations

import math

from recsys.eval.metrics import (
    coverage,
    diversity_by_source,
    mrr,
    ndcg_at_k,
    novelty,
    precision_at_k,
    recall_at_k,
)
from recsys.eval.offline_eval import (
    Interaction,
    build_snapshot,
    score_snapshot,
    split_interactions,
)


def test_recall_precision_mrr_basic():
    ranked = ["a", "b", "c", "d"]
    relevant = {"b", "z"}
    assert recall_at_k(ranked, relevant, 3) == 0.5
    assert precision_at_k(ranked, relevant, 3) == 1 / 3
    assert mrr(ranked, relevant) == 0.5


def test_ndcg_perfect_and_empty():
    ranked = ["a", "b", "c"]
    relevant = {"a", "b"}
    assert math.isclose(ndcg_at_k(ranked, relevant, 2), 1.0)
    assert ndcg_at_k([], relevant, 5) == 0.0
    assert ndcg_at_k(ranked, set(), 5) == 0.0


def test_coverage_diversity_novelty():
    recs = {"u1": ["a", "b"], "u2": ["b", "c"]}
    assert math.isclose(coverage(recs, 4), 0.75)
    div = diversity_by_source([("a", "clip"), ("b", "svd"), ("c", "clip")], 3)
    assert 0.0 < div < 1.0
    nov = novelty(["rare", "common"], {"common": 0.5, "rare": 0.01}, 2)
    assert nov > 0.0


def test_time_split_and_snapshot_scoring_is_deterministic():
    events = [
        Interaction("u1", "i1", "like", 100),
        Interaction("u1", "i2", "impression", 150),
        Interaction("u1", "i3", "like", 300),
        Interaction("u2", "i9", "like", 400),
    ]
    train, eval_part = split_interactions(events, cutoff_ms=250)
    assert [e.item_id for e in train] == ["i1", "i2"]
    assert [e.item_id for e in eval_part] == ["i3", "i9"]

    snap = build_snapshot(
        model_version="v3",
        algorithm_version="rrf-1",
        cutoff_ms=250,
        recommendations={"u1": ["i3", "i1", "x"], "u2": ["y", "i9"]},
    )
    first = score_snapshot(snap, eval_part, k=2, catalog_size=10)
    second = score_snapshot(snap, eval_part, k=2, catalog_size=10)
    assert first["artifact_hash"] == second["artifact_hash"]
    assert first["recall@2"] == second["recall@2"]
    assert first["users_scored"] == 2
    assert first["model_version"] == "v3"
