# External ops checklist (do NOT run from agent without approval)

Project: `seolleyeon-final`

## 1. App Check — Firestore / Authentication

Staging first (Monitor → 24h → Enforce), then production canary.
See: `docs/audits/opus5/17-app-check-enforcement-runbook.md`

Rollback: Console → App Check → APIs → Unenforced

## 2. Node 22 + deletion retention scheduler

```bash
cd functions
npm ci
npm test
firebase deploy --only functions --project seolleyeon-final
```

Confirm exports include:
- `purgeExpiredEmailLinkTokens`
- `purgeAccountDeletionRetention`

## 3. Firestore indexes

```bash
firebase deploy --only firestore:indexes --project seolleyeon-final
```

Includes messages collectionGroup (authorDeleted/legalHold/purgeAfter) and eventTeamSetups status/purgeAfter.

## 4. Retention legal confirmation

Default: 90 days (`DEFAULT_DELETED_MESSAGE_RETENTION_DAYS`).
After legal sign-off, change constant and redeploy functions only.
