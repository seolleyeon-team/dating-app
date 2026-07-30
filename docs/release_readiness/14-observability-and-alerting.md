# 14 — Observability and Alerting

작성: 2026-07-31

## Existing

Prior runbook: `docs/audits/opus5/20-observability-and-alerting.md`  
Recsys structured JSON logs: `recsys/jobs/common.py`

## Proposed signals (do not create production alerts yet)

| signal | threshold idea | runbook |
|--------|----------------|---------|
| avatar pending stale | > 30m | repair dry-run → operator |
| account deletion stuck | > 60m | deletion resume |
| season deposit pending | > 30m | operator_review |
| App Check failures | spike | app-check runbook 17 |
| push invalid token rate | elevated | token cleanup |

Actual alert creation = EXTERNAL.
