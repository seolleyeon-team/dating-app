# Final Release Verification Report

**Project:** Seolleyeon (설레연)  
**Branch:** `release/grok45-production-readiness-final`  
**Date:** 2026-07-31  
**Engineer role:** Release Verification / Security / QA  

## Final Decision

```
NOT_PRODUCTION_READY
```

Reason: multiple required gates remain `BLOCKED` / `NOT_VERIFIED` (remote CI green, staging full E2E, live orphan audit, production publicProfiles backfill, release keystore signing). Local code/security gates that could be executed were fixed and re-run to PASS.

---

## Verification Evidence

| 검증 항목 | 실행 명령 | 결과 | Exit code | 증거 |
|-----------|-----------|------|-----------|------|
| Java 환경 | `java -version` via Android Studio JBR | PASS | 0 | OpenJDK 21.0.9 (`C:\Program Files\Android\Android Studio1\jbr`) |
| Firebase CLI | `firebase --version` | PASS | 0 | 15.18.0 |
| Firestore Rules Emulator (IDOR / protected / publicProfiles) | `firebase emulators:exec --only firestore --project seolleyeon-rules-test "npm --prefix rules_tests test"` | PASS | 0 | 58/58 tests |
| Storage Rules Emulator | `firebase emulators:exec --only storage --project seolleyeon-storage-rules-test "npm --prefix rules_tests run test:storage"` | PASS | 0 | 8/8 tests |
| Functions lint/build/test | `cd functions && npm test` | PASS | 0 | 211/211 tests |
| Flutter analyze | `flutter analyze` | PASS | 0 | No issues found |
| Flutter test | `flutter test` | PASS | 0 | 135/135 tests |
| `flutter build apk --debug` | same | PASS | 0 | `build\app\outputs\flutter-apk\app-debug.apk` |
| `flutter build appbundle --release` | same | PASS* | 0 | `build\app\outputs\bundle\release\app-release.aab` (75.3MB). *No `android/key.properties` — not Play-upload signed |
| `flutter build web` | `flutter build web --release` | PASS | 0 | `build\web` |
| publicProfiles migration (emulator dry-run) | `APPLY` unset + emulator script | PASS | 0 | `{"dryRun":true,"scanned":4,"upserts":2,"deletes":2,"privateLeaks":0,"ok":true}` |
| publicProfiles migration (emulator apply) | `APPLY=true` + emulator script | PASS | 0 | integrity checks for active/withdrawn/hidden |
| Season concurrency (10 replacement / 20 invites) | functions unit tests + local stress | PASS | 0 | wins=1 fails=9; capacity never exceeded |
| Payment fail-closed (server) | `seasonDepositFailClosed.test.ts` + rules deny | PASS | 0 | `SEASON_DEPOSIT_PROVIDER_READY` gate; client cannot write `seasonDepositIntents` |
| Payment fail-closed (client UI) | `kSeasonDepositEnabled=false` | PASS | 0 | deposit CTA/modal copy gated |
| Account deletion unit orchestration | included in `npm test` (avatarCleanup / social cleanup) | PASS | 0 | unit-level cleanup/idempotency covered |
| Account deletion Full E2E (live Auth/Storage/orphan=0) | staging test accounts | BLOCKED | — | no staging credentials / isolated project access in this session |
| Orphan audit (live) | production/staging search | BLOCKED | — | not run against live data |
| Remote CI green on release branch | `gh run list` / GitHub Actions | BLOCKED | — | `gh` install cancelled (admin UAC 1602); cannot confirm remote jobs |
| Staging user journey E2E | manual/staging app | BLOCKED | — | no staging environment attached |
| Production publicProfiles backfill | Admin SDK against prod | NOT_RUN | — | correctly refused; emulator-only verification performed |
| `dart format --set-exit-if-changed` | same | FAIL / WIP | 1 | pre-existing dirty format in WIP files (`friend_service.dart`, `flutter_lifecycle_guards_test.dart`) left untouched to protect user WIP |

---

## Fixed Issues

### 1. Protected field forge via `changedKeys()` allowlist bypass (P0)

| | |
|--|--|
| **문제** | Owner could add `status` / `isWithdrawn` / `loginDisabled` / `role` / `premium` / verification timestamps that did not previously exist. Rules used `diff().changedKeys().hasOnly([...])`, which **ignores newly added keys**. |
| **원인** | Firestore MapDiff: `changedKeys` = keys present in both maps with different values; adds/removes require `affectedKeys` / `addedKeys`. |
| **수정** | `firestore.rules` users/emailLinkTokens/notifications/status updates: `changedKeys` → `affectedKeys`. |
| **테스트** | Extended `rules_tests/firestore.auth.test.mjs` (role/admin/premium, add-loginDisabled, null/deleteField). Emulator: 58/58 PASS. |
| **Commit** | Not committed (awaiting explicit user request). |

### 2. Storage rules had no emulator suite

| | |
|--|--|
| **문제** | Only static Dart characterization existed; CI did not run Storage emulator attacks. |
| **원인** | Missing `storage*.test.mjs` and CI job. |
| **수정** | Added `rules_tests/storage.security.test.mjs`, `npm run test:storage`, CI job `storage-rules`. |
| **테스트** | Emulator 8/8 PASS (IDOR read/upload, private paths, avatar write deny, path traversal, catch-all). |
| **Commit** | Not committed. |

### 3. Season deposit UI exposed while provider absent

| | |
|--|--|
| **문제** | `Deposit & Enter Chat` / promise-money copy visible despite no payment provider. |
| **원인** | Client mock UI not gated; server already fail-closed via `SEASON_DEPOSIT_PROVIDER_READY`. |
| **수정** | `lib/core/feature_flags.dart` (`kSeasonDepositEnabled` default false); hide locked-chat deposit section; gate promise modal deposit rule. Added fail-closed functions tests + concurrency stress tests. |
| **테스트** | `test/feature_flags_deposit_test.dart`; functions 211/211. |
| **Commit** | Not committed. |

### 4. publicProfiles migration emulator harness

| | |
|--|--|
| **문제** | Backfill documented but not executable in CI/emulator. |
| **수정** | `scripts/backfill_public_profiles_emulator.mjs` (refuses without `FIRESTORE_EMULATOR_HOST`). |
| **테스트** | dry-run + apply PASS on emulator. |
| **Commit** | Not committed. |

---

## Remaining Risks

### 코드 문제
- Users update still evaluates expensive `publicUserMediaOk` first; some denials surface as **expression limit (1000)** fail-closed rather than explicit allowlist messages. Safe for attackers, noisy for debugging. Recommend reordering allowlist/denylist ahead of media checks.
- Release AAB builds without `android/key.properties` — artifact is not Play-store signed.

### 환경 문제
- Machine `java` not on PATH; verification used Android Studio JBR. Document / install JDK 21 for CI-parity local scripts.
- `gh` CLI install blocked by UAC — remote Actions status unverified.
- `dart format` gate fails on pre-existing WIP files (intentionally not rewritten).

### 외부 서비스 필요
- Set `SEASON_DEPOSIT_PROVIDER_READY=true` only after real PSP wiring; keep unset in prod until then.
- Production/staging Admin credentials for live publicProfiles backfill (`scripts/backfill_public_profiles.md`).
- Release keystore (`android/key.properties`) for uploadable AAB.
- Staging Firebase project for full account-deletion E2E + orphan=0 audit.

### 운영 결정 필요
- Deploy order: Functions sync → publicProfiles backfill → tightened rules → client that reads `publicProfiles`.
- Confirm tutorial copy that still *mentions* deposit conceptually is acceptable while payment is disabled (CTA hidden).

---

## WIP Protection Notes

- Did **not** run `git reset --hard` / `git clean` / `git restore` on user WIP.
- Left untracked `.tmp/`, `dating-app/`, merge-restore artifacts untouched.
- Blind-meeting domains remain unsupported in stale-job repair (existing fail-closed).
- Deposit UI gating only hides payment surfaces; slot-machine / matching sections preserved.

---

## Recommended External Actions (to reach PRODUCTION_READY_WITH_EXTERNAL_ACTIONS)

1. Commit verification fixes on this branch and push; confirm all GitHub Actions jobs green.
2. Provide release keystore and rebuild signed AAB.
3. Run publicProfiles backfill dry-run then apply on **staging**, then production per runbook.
4. Create staging test accounts; execute full deletion E2E + orphan audit = 0.
5. Execute staging critical user journey checklist (signup → chat → report/block → season meeting without payment).
6. Install JDK 21 system-wide optional; keep JBR documented as fallback.
