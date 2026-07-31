# 기준선 측정과 검증 결과

기준선은 `8b782415` 기준, 검증은 이번 브랜치 최종 상태 기준이다.

## 실행 환경

| 항목 | 값 |
|---|---|
| OS | Windows / PowerShell |
| Flutter | 3.41.9 stable (Dart 3.11.5) |
| Node | `functions/` 에 `node_modules` 설치됨 |
| Java | **1.8.0_211 만 존재** |
| Firebase 프로젝트 | `.firebaserc` default = `seolleyeon` (운영) |

## 기준선 (수정 전)

| 명령 | 위치 | exit | 결과 |
|---|---|---|---|
| `flutter analyze` | repo root | 1 | 23 issues (0 error / 6 warning / 17 info) — analyze 는 issue 가 있으면 exit 1 |
| `flutter test` | repo root | 0 | **343 tests PASS** |
| `npm run build` (tsc) | `functions/` | 0 | PASS |
| `npm test` | `test/firestore_rules/` | 1 | **BLOCKED** — JDK 21+ 필요 |

## 검증 (수정 후)

| 검증 항목 | 결과 | 명령 | 비고 |
|---|---|---|---|
| Dart 정적 분석 | PASS (회귀 없음) | `flutter analyze` | 23 issues — 기준선과 동일. 새 이슈 0 |
| Flutter 단위·위젯 테스트 | PASS | `flutter test` | 기준선 343 + 신규 9 = 352 |
| 신규 MIME 정규화 테스트 | PASS (9/9) | `flutter test test/utils/image_content_type_test.dart` | |
| Functions 타입 체크·빌드 | PASS | `npm --prefix functions run build` | 제거한 callable 참조 잔존 없음 |
| Functions 단위 테스트 | NOT_RUN | `npm --prefix functions test` | 이번 세션에서 실행하지 않음 |
| Firestore Rules 공격 테스트 | **BLOCKED_NOT_EXECUTED** | `cd test/firestore_rules && npm test` | B-JDK21 |
| Storage Rules 공격 테스트 | **NOT_WRITTEN** | — | B-JDK21 로 실행 불가라 작성하지 않음 |
| `storage.rules` 문법 검증 | **NOT_VERIFIED** | — | B-JDK21 |
| `firestore.rules` 문법 검증 | **NOT_VERIFIED** | — | B-JDK21 |
| Android APK 빌드 | NOT_RUN | `flutter build apk --debug` | |
| Web 빌드 | NOT_RUN | `flutter build web` | |
| iOS 빌드 | BLOCKED | — | macOS 호스트 없음 |
| `npm audit` / `pip-audit` / `dart pub outdated` | NOT_RUN | — | |
| Semgrep / Gitleaks / Trivy / CodeQL | NOT_CONFIGURED | — | 저장소에 설정 없음 |

`flutter analyze` 잔존 23건은 전부 기존 이슈이고 error 는 없다. 내용은
미사용 지역변수·미사용 필드·불필요 import·`deprecated_member_use`·
`use_build_context_synchronously`·`control_flow_in_finally` 다. 이번 작업 범위가
아니라서 손대지 않았다 (기능 변경과 스타일 변경을 섞지 않는다는 원칙).

## 블로커

### B-JDK21 — Firestore/Storage emulator 실행 불가 (심각)

```
Error: firebase-tools no longer supports Java version before 21.
Please install a JDK at version 21 or above to get a compatible runtime.
```

- 이 머신의 Java: `1.8.0_211`
- Android Studio 번들 JBR(`C:\Program Files\Android\Android Studio\jbr`)은
  `bin` 과 `lib` 만 있고 `lib\jvm.cfg` 가 없는 **불완전 설치**다.
  실행하면 `Error: could not open ...\jbr\lib\jvm.cfg` 로 죽는다.
- `C:\Users\Mickey\.jdks`, `C:\Program Files\Microsoft`,
  `C:\Program Files\Eclipse Adoptium` 에 다른 JDK 없음.

**영향**: 이번에 변경한 `firestore.rules` 와 `storage.rules` 는
문법 검증도, 공격 테스트 통과 확인도 되지 않았다.
`test/firestore_rules/authz_hardening_rules.test.js` 는 작성했지만 실행하지
못했다. 기존 3개 규칙 테스트(`blind_meeting_rules`, `kakao_login_rules`,
`meeting_icebreaker_rules`)도 같은 이유로 회귀 확인을 못 했다.

**해소 방법**: JDK 21+ 설치 후

```powershell
cd test/firestore_rules
npm install
npm test
```

규칙 배포는 이 명령이 exit 0 이 된 다음에만 한다.

### B-SEARCH — 저장소 전문 검색 도구 부재

`grep_search` / `file_search` 는 권한 엔진이 거부하고, shell `Select-String` /
`Get-Content` 는 shell-gate 훅이 차단한다. `git grep ... | Out-File <파일>` 후
`read_file` 로 우회했다. 이 때문에 "전 저장소 fallback 패턴 전수 조사"와
"PII 로그 전수 조사"는 수행하지 못했다.

### B-IOS — iOS 빌드 불가

macOS 호스트가 없다. `flutter build ios` / `ipa` 는 검증 불가.
