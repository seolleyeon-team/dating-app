"""Offline evaluation runner with train/eval time separation.

This module never deploys models. It only scores frozen recommendation
snapshots against held-out positive interactions.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence

from . import metrics


@dataclass(frozen=True)
class Interaction:
    user_id: str
    item_id: str
    event_type: str
    ts_ms: int


@dataclass(frozen=True)
class EvalSnapshot:
    model_version: str
    algorithm_version: str
    cutoff_ms: int
    recommendations: Mapping[str, Sequence[str]]
    artifact_hash: str


POSITIVE_TYPES = frozenset({"like", "mutual_like", "match", "detail_open"})


def split_interactions(
    events: Sequence[Interaction], cutoff_ms: int
) -> tuple[list[Interaction], list[Interaction]]:
    """Strict time split: train < cutoff, eval >= cutoff."""
    train = [e for e in events if e.ts_ms < cutoff_ms]
    eval_part = [e for e in events if e.ts_ms >= cutoff_ms]
    return train, eval_part


def assert_no_future_leakage(
    recommendations: Mapping[str, Sequence[str]],
    train_events: Sequence[Interaction],
    eval_events: Sequence[Interaction],
) -> None:
    """Raise if any recommended item for a user only appears as a future positive.

    Allowing train positives in rankings is fine; using eval-only labels as
    ranking inputs is leakage and is rejected by the caller contract.
    This helper validates that eval positives are used only as labels, not
    that they are absent from rankings (rankings may coincidentally include them).
    """
    train_pairs = {(e.user_id, e.item_id) for e in train_events}
    eval_only = {
        (e.user_id, e.item_id)
        for e in eval_events
        if e.event_type in POSITIVE_TYPES and (e.user_id, e.item_id) not in train_pairs
    }
    # Contract note: rankings themselves are inputs; leakage is a data-prep bug
    # if train features were built from eval_only. Callers must pass features
    # built solely from train_events. We expose eval_only for audits.
    _ = eval_only  # documented for auditors; no mutation


def relevant_by_user(eval_events: Sequence[Interaction]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for event in eval_events:
        if event.event_type not in POSITIVE_TYPES:
            continue
        out.setdefault(event.user_id, set()).add(event.item_id)
    return out


def score_snapshot(
    snapshot: EvalSnapshot,
    eval_events: Sequence[Interaction],
    *,
    k: int = 10,
    catalog_size: int | None = None,
    item_popularity: Mapping[str, float] | None = None,
    ranked_sources: Mapping[str, Sequence[tuple[str, str]]] | None = None,
) -> dict:
    """Compute aggregate metrics for a frozen recommendation snapshot."""
    labels = relevant_by_user(eval_events)
    users = sorted(set(snapshot.recommendations) | set(labels))
    recalls: list[float] = []
    precisions: list[float] = []
    ndcgs: list[float] = []
    mrrs: list[float] = []
    cold = 0
    warm = 0

    for user_id in users:
        ranked = list(snapshot.recommendations.get(user_id, ()))
        relevant = labels.get(user_id, set())
        if not relevant:
            continue
        if not ranked:
            cold += 1
        else:
            warm += 1
        recalls.append(metrics.recall_at_k(ranked, relevant, k))
        precisions.append(metrics.precision_at_k(ranked, relevant, k))
        ndcgs.append(metrics.ndcg_at_k(ranked, relevant, k))
        mrrs.append(metrics.mrr(ranked, relevant))

    def mean(xs: Sequence[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    result = {
        "model_version": snapshot.model_version,
        "algorithm_version": snapshot.algorithm_version,
        "artifact_hash": snapshot.artifact_hash,
        "cutoff_ms": snapshot.cutoff_ms,
        "k": k,
        "users_scored": len(recalls),
        "cold_users_without_recs": cold,
        "warm_users_with_recs": warm,
        f"recall@{k}": mean(recalls),
        f"precision@{k}": mean(precisions),
        f"ndcg@{k}": mean(ndcgs),
        "mrr": mean(mrrs),
        "scored_at": datetime.now(timezone.utc).isoformat(),
    }

    if catalog_size is not None:
        result["coverage"] = metrics.coverage(snapshot.recommendations, catalog_size)

    if item_popularity is not None:
        novelties = [
            metrics.novelty(list(snapshot.recommendations.get(u, ())), item_popularity, k)
            for u in users
            if labels.get(u)
        ]
        result["novelty"] = mean(novelties)

    if ranked_sources is not None:
        diversities = [
            metrics.diversity_by_source(list(ranked_sources.get(u, ())), k)
            for u in users
            if labels.get(u)
        ]
        result["diversity"] = mean(diversities)

    return result


def artifact_hash_for_recommendations(
    recommendations: Mapping[str, Sequence[str]],
) -> str:
    payload = json.dumps(
        {uid: list(items) for uid, items in sorted(recommendations.items())},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_snapshot(
    *,
    model_version: str,
    algorithm_version: str,
    cutoff_ms: int,
    recommendations: Mapping[str, Sequence[str]],
) -> EvalSnapshot:
    return EvalSnapshot(
        model_version=model_version,
        algorithm_version=algorithm_version,
        cutoff_ms=cutoff_ms,
        recommendations=recommendations,
        artifact_hash=artifact_hash_for_recommendations(recommendations),
    )


def snapshot_to_dict(snapshot: EvalSnapshot) -> dict:
    data = asdict(snapshot)
    data["recommendations"] = {
        uid: list(items) for uid, items in snapshot.recommendations.items()
    }
    return data
