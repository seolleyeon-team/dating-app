# 17 — Admin / Operator Tools

작성: 2026-07-31

## Status

PARTIAL — server callables + repair dry-run plans exist; dedicated admin console UI not duplicated.

## Operator actions available via repair planner intent

- Review stale deposit/refund/season meeting
- Dead-letter exhausted retries
- Resume account deletion (existing modules)

## Security requirements

- custom claims / server-only
- audit logs
- PII masking
- idempotent actions
