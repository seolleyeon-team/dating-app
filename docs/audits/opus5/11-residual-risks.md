# 11 — Residual Risks

작성: 2026-07-30

| ID | Risk | Severity | Mitigation | Status |
|----|------|----------|------------|--------|
| R-01 | Firestore/Auth App Check still UNENFORCED | High | Runbook 17 | BLOCKED_EXTERNAL |
| R-02 | Node 20 deprecated; code set to 22 but not prod-deployed | High | Deploy functions | BLOCKED_EXTERNAL |
| R-03 | New indexes undeployed | Medium | `firebase deploy --only firestore:indexes` | BLOCKED_EXTERNAL |
| R-04 | Chat retention days need legal sign-off | Medium | Default 90d + legalHold | BLOCKED_EXTERNAL |
| R-05 | Historical deleted-user messages not backfilled | Low | Migration dry-run only | BLOCKED_EXTERNAL |
| R-06 | UI jank / APK size unmeasured | Low | Doc 19 follow-up | Accepted residual |
| R-07 | Kakao client keys in source | Low (public SDK keys) | Keep; rotate only if leaked private | Accepted |
