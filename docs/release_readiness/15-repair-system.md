# 15 — Automatic Repair System (dry-run)

작성: 2026-07-31

## Module

```text
functions/src/staleJobRepair.ts
functions/src/staleJobRepair.test.ts
```

## Domains

avatar_pending, recommendation_running, notification_scheduled, account_deletion_running, season_meeting_pending, deposit_pending, refund_pending, replacement_pending, safety_stamp_incomplete

Blind-meeting domains are **not** represented.

## Behavior

- Plans only (`dryRun: true`)
- High-risk money/season domains → `operator_review`
- Retry budget → `dead_letter`
- Safety incomplete → `expire`

## Next ops step (external)

Wire a scheduled callable that queries stale docs and applies plans after manual approval / feature flag. Production mutation is blocked until approved.
