# 06 — Account Deletion / Data Lifecycle

작성: 2026-07-31

## Orchestration modules

- `accountDeletionSocialCleanup.ts`
- `accountDeletionChatLifecycle.ts`
- `accountDeletionEventTeamCleanup.ts`
- `accountDeletionRetentionPurge.ts`
- `accountDeletionConstants.ts`

## Prior audit

`docs/audits/opus5/18-account-deletion-data-lifecycle.md`

## This session

- Journey contract asserts modules exist
- Stale `account_deletion_running` included in repair planner (dry-run)

## External

- Production purge scheduler deploy
- Legal retention day confirmation
- Historical backfill migration (approval required)
