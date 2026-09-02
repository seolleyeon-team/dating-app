# Final full release gate

검증일: 2026-09-02 (Asia/Seoul)

기준 SHA: `e5b47c84161ea8cc7a4236925eff8971e7d0cc4e` + uncommitted security integration diff.

## Toolchain

| Tool | Version / note |
|---|---|
| Python | CPython 3.11.9 |
| Java | Microsoft OpenJDK 21.0.12 |
| Flutter | 3.47.2 stable, CI pin과 일치 |
| Dart | 3.13.2 |
| Node | local 24.14.0; Functions contract는 22이므로 environment variance 기록 |
| npm | 11.10.1 |
| gitleaks | 8.30.1, official manifest SHA-256 verified |

## Fresh gate results after final code change

| Gate / command | Exit | Result |
|---|---:|---|
| `git diff --check` | 0 | PASS |
| `pytest ... tests recsys/tests` with pinned Flask validation path and pinned offline tokenizer | 0 | `1260 passed in 184.33s` |
| `npm test` in `test/firestore_rules` with JDK 21 | 0 | `199/199`, 36 suites, fail 0, skipped 0 |
| `npm test` in `functions` | 0 | build + `699/699`, 63 suites, fail 0 |
| `npm run lint` in `functions` | 0 | `tsc --noEmit` PASS |
| `npm run build` in `functions` | 0 | `tsc` PASS |
| `flutter pub get` | 0 | dependency resolution PASS |
| `dart format --output=none --set-exit-if-changed lib test` | 0 | 489 files, 0 changed |
| `flutter test --no-pub` | 0 | `905 passed` |
| `flutter analyze --no-pub` | 0 | no issues, 287.7s |
| `flutter build apk --debug --flavor staging --no-pub` | 0 | staging debug APK built, 68.5s |
| `flutter build appbundle --flavor production --release --no-pub` | 1 | expected fail-closed: release keystore config absent; AAB not produced |

## iOS static gate

Windows에서는 Xcode archive를 실행하거나 PASS로 주장하지 않았다. 값 자체를 출력하지 않고 다음 계약을 확인했다.

- Runner bundle identifier가 production identifier와 일치
- Firebase plist 존재 및 bundle identifier 일치
- Info.plist 및 URL schemes 선언 존재
- entitlements 및 Associated Domains 선언 존재
- App Check provider source wiring 존재
- PrivacyInfo.xcprivacy 존재

`IOS_ARCHIVE = NOT_RUN_WINDOWS`.

## Dependency status

`npm audit`는 변경 없이 조회했다. 자동 fix/force fix는 하지 않았다.

| Scope | Total | Low | Moderate | High | Critical |
|---|---:|---:|---:|---:|---:|
| Rules test package | 0 | 0 | 0 | 0 | 0 |
| Functions, including runtime `--omit=dev` | 25 | 1 | 14 | 9 | 1 |

high/critical 10개 중 직접 의존성은 `sharp` 1개이고 나머지는 전이 의존성이다. audit는 모두 fix metadata를 제공하지만 reachability forensic과 호환성 검토 없이 자동 변경하거나 release P0로 재분류하지 않았다. 별도 dependency remediation이 필요하다.

## Secret / PII

- gitleaks 8.30.1 full history: 453 commits, 약 1.15GB, leaks 0
- tracked working diff: leaks 0
- untracked audit/plan docs: leaks 0
- added diff regex: email, access token, service-account key, Korean phone 0
- signed-URL marker는 test fixture 교체 1개 추가/1개 제거로 순증 0; concrete credential은 없음

실제 값은 보고서와 로그에 출력하지 않았다.

## Generated artifacts and Git safety

- `.dart_tool/`, `build/`, Functions/Rules `node_modules/`는 ignore된 validation artifact이며 diff에 포함되지 않는다.
- staging APK는 ignore된 build output이다.
- production AAB와 `android/key.properties`는 생성되지 않았다.
- 원본 `security-main` worktree와 사용자 WIP는 변경하지 않았다.
- commit, push, PR, deploy, production mutation은 수행하지 않았다.

## Release matrix

```text
LATEST_MAIN_INTEGRATED = YES
P1_CLIP_PRIVATE_MEDIA = PASS
INDEPENDENT_SECURITY_REVIEW = PASS
PYTHON_TEST_HYGIENE = PASS
PYTHON_FULL = PASS
RULES_FULL = PASS
FUNCTIONS_TEST = PASS
FUNCTIONS_LINT = PASS
FUNCTIONS_BUILD = PASS
FLUTTER_TEST = PASS
FLUTTER_ANALYZE = PASS
FORMAT = PASS
STAGING_BUILD = PASS
PRODUCTION_AAB = BLOCKED_EXTERNAL_SIGNING
IOS_ARCHIVE = NOT_RUN_WINDOWS
SECRET_PII_SCAN = PASS
NEW_REGRESSION = ZERO
```

## Final verdict

```text
LATEST_MAIN_INTEGRATION = PASS
CLIP_P1 = PASS
INDEPENDENT_SECURITY_REVIEW = PASS
PYTHON_29_HYGIENE = PASS
PYTHON_FULL = PASS
RULES = PASS
FUNCTIONS = PASS
FLUTTER_TEST = PASS
FLUTTER_ANALYZE = PASS
ANDROID_STAGING = PASS
ANDROID_PRODUCTION_AAB = BLOCKED
NEW_SECURITY_REGRESSION = ZERO
SECURITY_SCOPE_READY = YES
FULL_RELEASE_READY = BLOCKED
COMMIT = NOT_RUN
PUSH = NOT_RUN
DEPLOY = NOT_RUN
```

Full release blockers are the external Android release signing secret and the unrun macOS/Xcode iOS archive. The Functions audit findings and local Node 24 versus contract Node 22 variance remain explicit follow-up risks; neither was hidden or auto-fixed.
