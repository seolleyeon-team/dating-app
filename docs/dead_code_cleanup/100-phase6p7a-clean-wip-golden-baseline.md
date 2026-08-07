# Phase 6P-7A clean WIP Golden Baseline

All gates were run in the isolated clean WIP checkout at
`C:/tmp/seolleyeon-phase6p7a-20260806-172208/clean-wip/checkout`.

| Gate | Command/result |
|---|---|
| Flutter dependencies | `flutter pub get` — PASS |
| Flutter analyzer | `flutter analyze --no-pub` — PASS, no issues |
| Flutter tests | `flutter test --no-pub --concurrency=1 --reporter compact` — PASS, 505/505 |
| Web debug | `flutter build web --debug --no-pub` — PASS |
| Web release | `flutter build web --release --no-pub` — PASS |
| Android debug | `flutter build apk --debug --no-pub` — PASS |
| Functions dependencies | `npm ci --prefix functions` — PASS; audit warnings retained, no fix run |
| Functions lint | `npm --prefix functions run lint` — PASS |
| Functions build | `npm --prefix functions run build` — PASS |
| Functions tests | `npm --prefix functions test` — PASS, 351/351 |
| Rules dependencies | `npm ci --prefix test/firestore_rules` — PASS |
| Firestore/Storage Rules | `npm --prefix test/firestore_rules test` — PASS, 174/174 |
| Onboarding audit unit tests | `node --test scripts/audit_onboarding_interests.test.mjs` — PASS, 5/5 |
| Onboarding emulator fixture | Firestore emulator synthetic fixture — 6 documents, 0 errors |

The first Rules invocation only exposed missing clean-checkout dependencies;
it was not a source failure. After lockfile installation, all 174 tests passed.
`functions` install warnings (Node engine notice and npm vulnerability report)
were recorded but no dependency repair or audit-fix mutation was run.

This baseline is consistent with the historic Phase 6P baseline in
`00-baseline.md`; all latest executable gates passed on the replacement.
