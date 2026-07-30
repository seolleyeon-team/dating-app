# 09 — Recommendation Offline Evaluation

작성: 2026-07-31

## Harness

```text
recsys/eval/metrics.py
recsys/eval/offline_eval.py
recsys/tests/test_offline_metrics.py
```

## Metrics implemented

- Recall@K, Precision@K, NDCG@K, MRR
- Coverage, Diversity (by source), Novelty
- MAP@K helper
- Train/eval time split (`split_interactions`)
- Artifact hash for snapshot reproducibility

## Policy

- No automatic production deploy from this harness
- Leakage contract: features must be built from train-only events
- CI: `pytest -q recsys/tests` with `PYTHONPATH=.`

## Existing production pipeline

Cloud Run Jobs via `recsys/main.py` (clip/svd/knn/rrf/verify) remain unchanged.
