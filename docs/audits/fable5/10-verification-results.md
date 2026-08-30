# 10 — 검증 결과 (Fable 5, 2026-08-28)

3개 코드 수정(SEC-11/05/18) 적용 후.

| 검증 | 명령 | 수정 전 | 수정 후 | 상태 |
|---|---|---|---|---|
| functions 테스트 | `npm test` (node --test) | 431 pass | **436 pass / 0 fail** | PASS (신규 5) |
| functions lint | `npm run lint` (tsc --noEmit) | pass | pass | PASS |
| functions build | `npm run build` | pass | pass | PASS |
| flutter analyze | `flutter analyze` | 0 issues | 변경파일 0 issues | PASS |
| flutter 테스트 | `flutter test` | 656 pass | **658 pass** | PASS (신규 2) |
| rules emulator | `firebase emulators:exec` | 72 pass | 72 pass (rules 미변경) | PASS |
| recsys 테스트 | `pytest recsys/tests` | 181 pass | 181 (미변경) | PASS |
| **tests/ pytest** | `pytest tests` | 921/16 fail | 921/16 fail (WIP, 미변경) | FAIL(기존, WIP) |

## 신규 테스트 4개
- `functions/src/blindMeeting/runtime.test.ts` (App Check 강제)
- `functions/src/meetingIcebreaker/runtime.test.ts` (App Check 강제)
- `functions/src/blindMeeting/store.failClosed.test.ts` (차단/제재 fail-closed, 3 케이스)
- `test/services/legal_consent_resolver_test.dart` (동의 fail-closed, 2 케이스)

각 항목 RED(수정 전 실패)→GREEN 확인. 기대값을 낮춰 통과시킨 것 없음.

## 미검증/BLOCKED (Tier 1 시점)
- iOS 빌드: Windows BLOCKED.
- flutter build apk/web: 미실행(코드 변경이 functions/rules-무관·1개 dart 서비스에 국한, analyze+test 통과로 갈음). 배포 전 최종 검증 권장.
- festival rules emulator: 미구성(테스트 0). → **Tier 2 에서 신설**.
- 16 RED pytest: 사용자 미커밋 WIP 영역 — 본 세션 미개입.

---

## Tier 2 검증 (festival + 커뮤니티, 후속 세션)

JDK: `C:\Program Files\Microsoft\jdk-21.0.12.8-hotspot`(21.0.12) 사용. firebase
emulator 는 JDK 21+ 요구(PATH 기본 JDK17 로는 실행 불가).

| 검증 | 명령 | 결과 | 상태 |
|---|---|---|---|
| festival functions lint | `npm run lint`(tsc --noEmit) | pass | PASS |
| festival functions test (SEC-09) | `npm test`(node --test) | **9 pass / 0 fail** | PASS (신규) |
| festival firestore rules (SEC-03) | emulators:exec firestore | **19 pass / 0 fail** | PASS (신규 인프라) |
| festival storage rules (SEC-08) | emulators:exec storage | **13 pass / 0 fail** | PASS (신규 인프라) |
| **메인 rules 전체** | emulators:exec firestore,storage | **197 pass / 0 fail** | PASS (bamboo 15 신규+authz 1 정정) |
| 메인 functions | `npm test` | 436 pass / 0 fail | PASS (미변경, 회귀 재확인) |
| bamboo 마이그레이션 dry-run/apply/멱등 | emulator harness | OK | VERIFIED (프로덕션 미실행) |

RED→GREEN 증거:
- SEC-08: storage read 를 이전 broad rule 로 되돌리면 "무관 사용자 read"·"경로
  추측" 2건 FAIL → 소유자 게이트 복원 시 GREEN.
- SEC-P3-01: 신규 가드 2개 제거 시 정확히 4개(score7d 단독+1, like문서 없이
  likeCount+1, 이중증가, like삭제 없이 -1)만 FAIL → 가드 복원 시 GREEN. 정상
  like/unlike/comment 흐름은 두 상태 모두 PASS(오탐 없음).

## Tier 2 신규 테스트
- `festival_web/functions/src/admin_http_guard.test.ts` (SEC-09, 9)
- `festival_web/test_rules/festival_ticket_rules.test.js` (SEC-03, 19)
- `festival_web/test_rules/festival_storage_rules.test.js` (SEC-08, 13)
- `test/firestore_rules/bamboo_counter_rules.test.js` (SEC-P3-01, 15)
- `test/firestore_rules/authz_hardening_rules.test.js` 내 좋아요 테스트 1건 정정
  (취약 동작 → 안전 원자 batch)

기대값을 낮춰 통과시킨 것 없음. authz 테스트 1건은 취약 동작을 인코딩하고 있어
안전 동작으로 정정한 것(하향 아님).

## Tier 2 미검증/미수행
- 실제 배포(invoker IAM 반영, rules 배포): 미수행(원격).
- SEC-04 규칙/클라/서버 breaking 변경: 미적용(사용자 결정 대기, DATA_MIGRATION_REQUIRED).
- bamboo 마이그레이션 production 실행: 미수행.
- flutter analyze/test: 메인 Dart 미변경으로 재실행 불필요(658 유효). festival lib
  Dart 미변경(SEC-08 은 rules 만).
- 16 RED pytest(avatar WIP): 본 세션 미개입, 상태 그대로.
