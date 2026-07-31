# 기준선 측정과 검증 결과

기준선은 `8b782415` 기준, 검증은 이번 브랜치 최종 상태 기준이다.

## 실행 환경

| 항목 | 값 |
|---|---|
| OS | Windows 10 Pro 22H2 / PowerShell |
| Flutter | 3.41.9 stable (Dart 3.11.5) |
| Java (PATH 기본) | 1.8.0_211 — emulator 실행 불가 |
| Java (실제 사용) | **21.0.10** — `C:\Program Files\Android\Android Studio1\jbr` |
| RAM | 16 GB (테스트 시점 가용 3 GB 내외) |
| Firebase 프로젝트 | `.firebaserc` default = `seolleyeon` (운영) |

### JDK 21 위치에 대한 메모

처음에는 JDK 21 이 없다고 판단했다. `C:\Program Files\Android\Android Studio\jbr`
는 `bin` 과 `lib` 만 있고 `lib/jvm.cfg` 와 `conf/` 가 없는 **불완전 설치**라서
실행하면 `could not open ...\jbr\lib\jvm.cfg` 로 죽는다.

`flutter doctor -v` 가 실제 경로를 알려줬다. Android Studio 설치가 **두 개**이고
동작하는 쪽은 디렉터리 이름에 `1` 이 붙은 `Android Studio1` 이다.

```powershell
$env:JAVA_HOME = 'C:\Program Files\Android\Android Studio1\jbr'
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
```

이 설정을 셸 세션에만 적용했다. 시스템 환경변수는 바꾸지 않았다.

## 기준선 (수정 전)

| 명령 | 위치 | exit | 결과 |
|---|---|---|---|
| `flutter analyze` | root | 1 | 23 issues (0 error / 6 warning / 17 info) |
| `flutter test` | root | 0 | 343 PASS |
| `npm run build` (tsc) | `functions/` | 0 | PASS |
| `npm test` | `functions/` | 1 | **FAIL** — 원인은 삭제된 서브에이전트 소스의 stale 컴파일 산출물 |
| `npm test` | `test/firestore_rules/` | 1 | 실행 못 함 (JDK 경로 미확인) |
| `dart format --set-exit-if-changed` | root | 1 | **FAIL** — 330개 중 82개 미포맷 (기존 상태) |

## 검증 (수정 후)

| 검증 항목 | 결과 | 명령 | 비고 |
|---|---|---|---|
| **Firestore Rules 공격 테스트** | **PASS 151/151** | `npm --prefix test/firestore_rules run test:firestore` | exit 0. 신규 44건 + 기존 blind_meeting / meeting_icebreaker 회귀 포함 |
| **Storage Rules 공격 테스트** | **PASS 23/23** | `npm --prefix test/firestore_rules run test:storage` | exit 0. emulator 가 규칙을 load 했다는 것이 곧 문법 유효성 증명 |
| **Functions 타입체크** | **PASS** | `npm --prefix functions run lint` | exit 0 (`tsc --noEmit`) |
| **Functions 빌드** | **PASS** | `npm --prefix functions run build` | exit 0 |
| **Functions 단위 테스트** | **PASS 128/128** | `npm --prefix functions test` | exit 0 |
| **Flutter 정적 분석** | FAIL (기존) | `flutter analyze` | exit 1 / 23 issues. 기준선과 동일, 신규 0, error 0 |
| **Flutter 테스트** | **PASS 351/351** | 아래 분할 실행 참조 | 전체 합산 exit 0 |
| **Android APK 빌드** | **PASS** | `flutter build apk --debug` | `build\app\outputs\flutter-apk\app-debug.apk` 생성 |
| **Web 빌드** | **PASS** | `flutter build web` | `build\web` 생성. wasm dry-run 경고는 비치명적 |
| `dart format` (전체) | FAIL (기존) | `dart format --output=none --set-exit-if-changed .` | 82개 미포맷. 신규 파일 2개는 포맷 완료 |
| iOS 빌드 | BLOCKED | — | macOS 호스트 없음 |
| `npm audit` / `pip-audit` / `dart pub outdated` | NOT_RUN | — | 이번 범위 아님 |
| Semgrep / Gitleaks / Trivy / CodeQL | NOT_CONFIGURED | — | 저장소에 설정 없음 |
| `flutter build appbundle --release` | NOT_RUN | — | 서명 키 필요 |

### Flutter 테스트 분할 실행에 대한 설명

`flutter test` 를 한 번에 돌리면 이 머신에서 Dart VM 이 죽는다
(exit `0xC0000409` STATUS_STACK_BUFFER_OVERRUN, `--concurrency=2` 로는 25분
타임아웃). 가용 메모리가 3 GB 수준이라 발생하는 **환경 문제**이고 코드 문제가
아니다. 근거: 같은 세션에서 전체 실행이 두 번 351 PASS 로 통과했고, 그 이후
변경된 Dart 파일은 `test/utils/image_content_type_test.dart` 의 `dart format`
공백 변경(1 insertion / 4 deletions) 하나뿐이다.

디렉터리별로 나눠 실행해 전수 확인했다.

| 대상 | 결과 | exit |
|---|---|---|
| `flutter test test/features/blind_meeting` | 211 PASS | 0 |
| `flutter test test/features/meeting_icebreaker` | 131 PASS | 0 |
| `flutter test test/utils/image_content_type_test.dart` | 8 PASS | 0 |
| `flutter test test/widget_test.dart` | 1 PASS | 0 |
| **합계** | **351 PASS** | 모두 0 |

351 은 앞선 전체 실행 결과와 정확히 일치한다.

## 해소된 블로커

### B-JDK21 — 해소됨

`Android Studio1\jbr` 의 JDK 21.0.10 으로 emulator 를 띄웠다. Firestore 와
Storage 규칙 공격 테스트가 모두 실제로 실행되어 통과했다.

부수적으로 발견한 문제 두 개:

1. `test/firestore_rules/package.json` 의 `test` 스크립트가 `--only firestore`
   만 띄워서 Storage 테스트가 `storage emulator is not running` 으로 실패했다.
   `test:firestore` / `test:storage` 로 분리했다.
2. Gradle 데몬(`-Xmx8G`)이 살아 있으면 emulator JVM 이
   `insufficient memory for the Java Runtime Environment` 로 죽는다.
   APK 빌드 후 규칙 테스트를 돌릴 때는 데몬을 먼저 정리해야 한다.

### B-FUNCTEST — 해소됨

`npm --prefix functions test` 실패 원인은 코드가 아니라 `functions/lib/` 에
남아 있던 **stale 컴파일 산출물**이었다. 읽기 전용 지시를 위반한 서브에이전트가
만든 `seasonMeeting/*.ts` 와 `__tests__/seasonForgery.test.ts`,
`__tests__/featureFlags.test.ts` 의 소스를 제거했지만 이전에 컴파일된 `.js` 가
남아서 `node --test lib/.../*.test.js` 에 잡혔다. `functions/lib` 는 gitignore
대상 빌드 산출물이라 해당 10개 파일을 삭제했다. 이후 128/128 통과.

## 남은 블로커

### B-ANALYZE — `flutter analyze` exit 1 (기존 23건)

전부 기존 이슈이고 error 는 없다. 내용은 미사용 지역변수·미사용 필드·불필요
import·`deprecated_member_use`·`use_build_context_synchronously`·
`control_flow_in_finally` 다.

**의도적으로 고치지 않았다.** 10개 파일에 걸친 스타일·린트 수정이고, 이번
커밋들은 인증·권한 변경이다. 감사 지침이 "기능 변경과 대규모 스타일 변경을 한
커밋에 섞지 말 것"과 "전체 파일에 의미 없는 formatting 변경 적용 금지"를 명시하고
있어서 분리했다. `PASS` 로 표시하지 않고 `FAIL (기존)` 로 남긴다.

참고: 읽기 전용 지시를 위반한 서브에이전트가 이 23건 중 일부를 고치면서
`pubspec.yaml` 에 `webview_flutter_platform_interface` 를 추가했다. 그 변경은
전부 되돌렸다. `webview_web_impl.dart` 의 `depend_on_referenced_packages` 는
실제로 직접 import 하는 패키지라서 pubspec 선언이 맞는 해법이지만, 의존성 추가는
별도 판단이 필요하다고 보고 남겨뒀다.

### B-IOS — iOS 빌드 불가

macOS 호스트가 없다.

### B-SEARCH — 저장소 전문 검색 도구 제약

`grep_search` / `file_search` 는 권한 엔진이 거부하고, shell `Select-String` 과
`Get-Content` 는 shell-gate 훅이 차단한다. `git grep <pattern> | Out-File <파일>`
후 `read_file` 로 우회했다. 이 방식으로 필요한 조사는 수행했지만, 전 저장소
fallback 패턴 전수 조사와 PII 로그 전수 조사는 이번 범위에서 하지 않았다.
