# Test/build comparison

## Pre-cleanup baseline

| Area | Result | Notes |
|---|---|---|
| Flutter doctor | PASS | Flutter 3.41.2 / Dart 3.11.0; Android JBR and Chrome available |
| Dependencies | PASS | `flutter pub get` completed |
| Dart analysis | PASS | `flutter analyze --no-pub`: no issues |
| Flutter tests | PASS | 505 tests passed |
| Web debug | PASS | `flutter build web --debug --no-pub -v` |
| Web release | PASS | `flutter build web --release --no-pub -v`; informational warnings only |
| Android debug APK | PASS | Gradle build successful; debug APK produced |
| Functions lint | PASS | TypeScript no-emit check |
| Functions build | PASS | TypeScript build |
| Functions tests | PASS | 351 passed, 0 failed |
| Firestore/Storage rules | PASS | 174 passed, 0 failed under emulator |

## Post-cleanup comparison

Not applicable: no deletion batch has run. The same table must be repeated after every approved batch. A green build alone is insufficient; targeted dynamic/native/Firebase/asset/route checks must also be repeated.

## External validation remaining

Physical Android/iOS, deployed Functions, production/staging data, push delivery, email-link in a real browser tab, App Check, and manual blind/season meeting journeys were not executed in this repository-only baseline. They are not treated as passing merely because local builds passed.


## Batch 001 post-removal verification — 2026-08-04

The checks below ran in the isolated cleanup worktree after deleting exactly ten pointer files. Dependency setup generated only local ignored build/dependency state; no user WIP source was copied into the cleanup commit.

| Gate | Post result | Evidence / qualification |
|---|---|---|
| Dart analysis | PASS | flutter analyze --no-pub; no issues |
| Flutter tests | PASS | 484 passed, 0 failed on the clean cleanup branch |
| Web debug | PASS | flutter build web --debug --no-pub -v |
| Web release | PASS | flutter build web --release --no-pub -v |
| Android debug APK | PASS | flutter build apk --debug --no-pub -v |
| Functions lint | PASS | npm --prefix functions run lint |
| Functions build | PASS | npm --prefix functions run build |
| Functions tests | PASS | 335 passed, 0 failed on the clean cleanup branch |
| Firestore/Storage rules | BASELINE MISMATCH, NOT A BATCH REGRESSION | Clean HEAD has 173 tests: 171 pass and 2 old cross-user users/{id} read expectations fail against the current publicProfiles rule. The original dirty WIP was independently rerun at 174/174 PASS, including the updated publicProfiles expectations. |

## Golden Baseline reconciliation

The recorded Golden Baseline belongs to the user's dirty WIP, while the cleanup worktree was intentionally created from clean HEAD 270124f2e930efcf575c5af87d75f967f4c8a7e3 so unrelated WIP could not enter the deletion commit.

| Gate | Recorded WIP baseline | Clean cleanup branch post result | Explanation |
|---|---:|---:|---|
| Flutter tests | 505 passed | 484 passed | 21 WIP-only tests are absent from clean HEAD; the clean branch suite itself is fully green |
| Functions tests | 351 passed | 335 passed | 16 WIP-only tests are absent from clean HEAD; the WIP 351-test suite was rerun and fully green |
| Rules tests | 174 passed | 171/173; 2 stale expectations | The WIP rules suite was rerun at 174/174; the two clean-HEAD failures are pre-existing test/rule drift and do not reference the deleted files |

All deletion-relevant application builds and analysis gates passed. No failed gate is attributable to Batch 001. The first targeted avatar QA probe was not promoted to a green gate because Windows denied its temporary basetemp setup after 13 tests had passed; the full Flutter suite and the exact static/ownership checks remained green.