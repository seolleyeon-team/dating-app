# 20 — Deployment and Rollback

작성: 2026-07-31

## Forbidden without explicit approval

- production firebase deploy
- production data migration
- store submit
- secret rotation
- force push / history rewrite

## Prepared (example — do not run)

### Functions

```bash
cd functions
npm ci
npm run lint
npm test
firebase deploy --only functions --project seolleyeon
```

Rollback: redeploy previous functions revision / git SHA artifact.

### Rules

```bash
cd rules_tests && npm ci
npx firebase-tools@13 emulators:exec --only firestore --project seolleyeon-rules-test "npm --prefix rules_tests test"
# only after green:
firebase deploy --only firestore:rules --project seolleyeon
```

Rollback: redeploy previous `firestore.rules` from last known good git tag.

### Recsys image

Use existing `infra/deploy.sh` / Cloud Build; never auto-promote from offline eval alone.
