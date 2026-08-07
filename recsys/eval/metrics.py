"""Deterministic ranking metrics for offline recommendation evaluation.

No network I/O. Inputs are plain ranked lists and relevance sets so that
train/eval leakage checks live in the caller (see offline_eval.py).
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Iterable, Mapping, Sequence


def _as_set(items: Iterable[str]) -> set[str]:
    return {str(x) for x in items if str(x)}


def recall_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Fraction of relevant items found in the top-k ranked list."""
    if k <= 0:
        raise ValueError("k must be positive")
    rel = _as_set(relevant)
    if not rel:
        return 0.0
    hit = sum(1 for item in ranked[:k] if item in rel)
    return hit / len(rel)


def precision_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Fraction of the top-k ranked list that is relevant."""
    if k <= 0:
        raise ValueError("k must be positive")
    if not ranked:
        return 0.0
    rel = _as_set(relevant)
    top = ranked[:k]
    if not top:
        return 0.0
    hit = sum(1 for item in top if item in rel)
    return hit / len(top)


def ndcg_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    """Binary-relevance NDCG@K."""
    if k <= 0:
        raise ValueError("k must be positive")
    rel = _as_set(relevant)
    if not rel:
        return 0.0

    def dcg(items: Sequence[str]) -> float:
        score = 0.0
        for idx, item in enumerate(items[:k], start=1):
            if item in rel:
                score += 1.0 / math.log2(idx + 1)
        return score

    ideal_hits = min(len(rel), k)
    ideal = [f"__ideal_{i}" for i in range(ideal_hits)]
    # Ideal DCG for binary relevance of length ideal_hits
    ideal_dcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    if ideal_dcg == 0.0:
        return 0.0
    return dcg(ranked) / ideal_dcg


def mrr(ranked: Sequence[str], relevant: Iterable[str]) -> float:
    """Mean reciprocal rank for a single query (binary relevance)."""
    rel = _as_set(relevant)
    if not rel:
        return 0.0
    for idx, item in enumerate(ranked, start=1):
        if item in rel:
            return 1.0 / idx
    return 0.0


def mean_average_precision_at_k(
    ranked: Sequence[str], relevant: Iterable[str], k: int
) -> float:
    """Average precision @ K for a single query."""
    if k <= 0:
        raise ValueError("k must be positive")
    rel = _as_set(relevant)
    if not rel:
        return 0.0
    hits = 0
    precision_sum = 0.0
    for idx, item in enumerate(ranked[:k], start=1):
        if item in rel:
            hits += 1
            precision_sum += hits / idx
    if hits == 0:
        return 0.0
    return precision_sum / min(len(rel), k)


def coverage(
    recommendations: Mapping[str, Sequence[str]], catalog_size: int
) -> float:
    """Share of catalog items that appear in any recommendation list."""
    if catalog_size <= 0:
        raise ValueError("catalog_size must be positive")
    recommended = {item for ranked in recommendations.values() for item in ranked}
    return len(recommended) / catalog_size


def diversity_by_source(
    ranked_with_source: Sequence[tuple[str, str]], k: int
) -> float:
    """1 - Herfindahl index of source share in top-k (higher = more diverse)."""
    if k <= 0:
        raise ValueError("k must be positive")
    top = ranked_with_source[:k]
    if not top:
        return 0.0
    counts = Counter(source for _, source in top)
    n = len(top)
    hhi = sum((c / n) ** 2 for c in counts.values())
    return 1.0 - hhi


def novelty(
    ranked: Sequence[str],
    item_popularity: Mapping[str, float],
    k: int,
) -> float:
    """Mean -log2(popularity) over top-k; missing popularity treated as rare (1e-6)."""
    if k <= 0:
        raise ValueError("k must be positive")
    top = ranked[:k]
    if not top:
        return 0.0
    total = 0.0
    for item in top:
        p = float(item_popularity.get(item, 1e-6))
        p = min(max(p, 1e-12), 1.0)
        total += -math.log2(p)
    return total / len(top)
