# 04 — Security Results

작성: 2026-07-31

## Prior verified work (opus5 / grok45 audits)

See `docs/audits/opus5/04-security-findings.md` and continuation ledger.

## This branch additions

| Item | Evidence |
|------|----------|
| recEvents schemaVersion allowlist | firestore.rules + rules_tests |
| Client score rejection | RecEventContract |
| Push open dedupe / init race | push_notification_service |
| Stale repair cannot mutate alone | dryRun plans only |

## External

- Firestore/Auth App Check Enforce: BLOCKED_EXTERNAL
- Production rules/functions deploy: BLOCKED_EXTERNAL
