# 17 — Canonical Port (semisemifinal-main, 2026-08-31)

릴리스 하드닝 세션(Opus 5)은 원래 `semisemifinal` worktree 의
`release/grok45-production-readiness-final` @ `9ac02bdd` 에서 수행됐다.
사용자 지시로 canonical 을 `semisemifinal-main` worktree 의
`feat/child-safety-standards-page` @ `fa67fa8d` (같은 저장소, **48 ahead / 0
behind** — 직계 후손, 발산 없음) 기준으로 재검증·이식했다.

전체 감사 기록 원본은 구 worktree 의 `docs/audits/production_cleanup/00~16`
(untracked) 에 있다.

## 48개 커밋이 이미 자체 해결한 것 (이식 불필요 — fresh 확인)

| 항목 | canonical 상태 |
|---|---|
| Gradle wrapper | **8.14.3** (동일 결론) |
| AGP / KGP | **8.13.2 / 2.3.0** (감사의 8.11.1/2.2.20 보다 최신, error floor 충족) |
| CI Flutter pin | 3.47.2 ✓ |
| CI flavor 빌드 | production+staging debug APK ✓ |
| `api_client.dart` unawaited ×4 | `return await` ✓ |
| consent widget assertion | Material 내부 배치로 해결 ✓ |

## 이번에 canonical 로 이식한 것

| 변경 | 내용 |
|---|---|
| `ios/Runner/RunnerRelease.entitlements` | aps-environment development → **production** |
| `mini_calibration_uid_photo_map.txt` | **de-track** (git rm --cached, 로컬 1,419B 보존, 내용 미열람) + 정확 ignore rule. HISTORY_EXPOSURE_REQUIRES_SEPARATE_REMEDIATION |
| `.gitignore` | 하드닝 블록 (pytest basetemp 계열, .venv/, __pycache__/, node_modules/, .firebase/, 서명 확장자 5종, 도구 잔여물) |
| dead generated tracked 70 | `.firebase/hosting.*.cache` 1 · `.g003_pytest_tmp` 12 · `pytest_tmp_avatar_qa_escalated` 45(합성 PNG 증명) · `g005_*` 12 — git rm |
| `.github/workflows/ci.yml` | `android-production-release` 잡 신설 (unsigned release AAB compile smoke, JDK17 명시). 기존 잡 무손상, YAML 검증 통과 |
| format | canonical 자체 RED 13파일 포맷 → 게이트 GREEN |

## 이식하지 않은 것 — 중요

- **`assets/fonts/LeeSeoyun.ttf` 제거 금지.** 구 트리에서는 참조 0 이었으나
  canonical 의 `lib/features/matching/screens/mystery_card_screen.dart:1359` 가
  `fontFamily: 'LeeSeoyun'` 을 **실사용**한다 (48개 커밋에서 도입). 구 worktree
  에 적용했던 제거는 **revert 완료** — 두 트리 모두 폰트 유지.
- iOS bundle ID migration: 여전히 BLOCKED_BY_FIREBASE_CONFIG (16-§2 참조).

## 미해결 (사용자 결정)

- 이 브랜치는 `github/main` 대비 **3 ahead / 19 behind** (SEC-04 bamboo 익명성
  매핑, 강제 업데이트 게이트, PR #60–63 포함). main 병합/리베이스는 WIP 52파일과
  얽히므로 사용자/Codex 판단.
- 구 worktree(`semisemifinal`)에 남은 세션 변경(툴체인/CI/문서 등)은 canonical
  이 자체 해결했으므로 대부분 폐기 가능 — 단 감사 문서(00~16)는 보존 가치.

## 검증 (이 worktree, 이식 후)

결과는 아래에 추가 기록한다.

## 검증 결과 (이식 후, 이 worktree 실측)

| 게이트 | 결과 |
|---|---|
| dart format lib test | **GREEN** (자체 RED 13파일 포맷 후 470/0) |
| flutter analyze | **GREEN — No issues found** (271s) |
| flutter test | **733 pass / 1 fail (734)** |
| production AAB (bypass 없음, AGP 8.13.2/KGP 2.3.0) | **√ 93.3MB** (97,852,802 B), `PRODUCTION_IDENTITY_OK` (com.seolleyeon.app), UNSIGNED(fail-closed 정상) |

유일한 fail — `locker_recommendation_preview_test.dart` "locker UI stays visible
while recommendations are empty": **github/main 의 `d527dcb8`
(fix(locker): treat a missing session as not-yet-loaded) 이 정확히 이 문제를
고친다.** 이 브랜치가 main 대비 19 behind 라서 없는 것 — 이식과 무관하며
main 병합으로 해소된다.

테스트 수 734 는 구 트리 658 대비 +76 (48개 커밋 + WIP 의 신규 테스트).
