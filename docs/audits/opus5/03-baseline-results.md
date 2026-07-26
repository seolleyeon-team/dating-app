# 03 — 기준선 측정 결과 (Opus 5 감사)

측정 시각: 2026-07-27
측정 위치: `C:/Users/samsung/StudioProjects/semisemifinal`
브랜치: `audit/opus5-production-hardening` (기준선 측정은 `9eb76d3` 워킹트리 상태)

이 문서는 **코드를 수정하기 전** 상태를 기록한다. 이후 회귀 검증은
10-verification-results.md에서 이 값과 비교한다.

## 실행 환경

| 항목 | 값 |
|------|-----|
| OS | Windows 10.0.26200, PowerShell |
| Flutter | 3.41.2 (stable), Dart 3.11.0 |
| Node | v24.14.0, npm 11.10.1 |
| Python | 3.13.3 |
| Firebase CLI | 15.18.0 |
| JRE | 시스템 PATH에 **없음**. Android Studio 번들 JBR(OpenJDK 21.0.9)을 사용해야 에뮬레이터가 뜬다: `C:\Program Files\Android\Android Studio1\jbr` |

## 기준선 측정 결과

| 항목 | 명령 | 실행 위치 | exit | 상태 | 비고 |
|------|------|-----------|------|------|------|
| Git 상태 | `git status --short` | repo root | 0 | **PASS** | 추적 파일 120개 수정 + 미추적 60개+. 대규모 미커밋 작업 존재 |
| Git 브랜치 | `git branch --show-current` | repo root | 0 | **PASS** | `semisemifinal` |
| Flutter 버전 | `flutter --version` | repo root | 0 | **PASS** | |
| 정적 분석 | `flutter analyze` | repo root | 0 | **PASS** | `No issues found!` (56.6s) |
| Flutter 테스트 | `flutter test` | repo root | 0 | **PASS** | **122개 전부 통과** (2분 16초) |
| Functions lint | `npm run lint` (`tsc --noEmit`) | `functions/` | 0 | **PASS** | |
| Functions 빌드 | `npm run build` (`tsc`) | `functions/` | 0 | **PASS** | |
| Functions 테스트 | `npm test` | `functions/` | 0 | **PASS** | **143개 전부 통과** |
| npm audit | `npm audit` | `functions/` | 1 | **FAIL(기존)** | 취약점 보고됨. 상세는 06/의존성 절 참조 |
| Firestore Rules 테스트 | 에뮬레이터 | — | — | **NOT_CONFIGURED → 본 감사에서 구축** | 아래 참조 |
| Storage Rules 테스트 | — | — | — | **NOT_CONFIGURED** | 미구축. 잔여 위험 |
| Android 빌드 | `flutter build apk --debug` | — | — | **NOT_ASSESSED** | 본 세션 미실행 |
| Web 빌드 | `flutter build web` | — | — | **NOT_ASSESSED** | 본 세션 미실행 |
| iOS 빌드 | — | — | — | **NOT_APPLICABLE** | Windows 환경 |
| Python 테스트 | `pytest` | — | — | **NOT_CONFIGURED** | `pyproject.toml`/`pytest.ini`/`setup.cfg`/`tox.ini` 없음 |
| ruff / mypy / bandit / pip-audit | — | — | — | **NOT_CONFIGURED** | 설정 파일 없음 |
| Semgrep / Gitleaks / Trivy / OSV | — | — | — | **NOT_CONFIGURED** | 저장소에 설정 없음 |
| CodeQL / Dependabot / CI | `.github/workflows` | — | — | **NOT_CONFIGURED** | `.github/` 워크플로 없음. **CI 게이트가 전혀 없다** |

### 기준선 해석

기존 실패는 `npm audit` 하나뿐이다. 나머지 자동 검증은 모두 초록이었다.
따라서 이후 발생하는 실패는 **본 감사의 수정 때문**이라고 판단할 수 있다.

동시에, 초록인 것이 안전을 뜻하지는 않는다. 이 프로젝트의 자동 검증에는
**보안 규칙을 실제로 평가하는 테스트가 하나도 없었다.** 유일하게 규칙을
다루던 `functions/src/firestoreRules.test.ts`는 규칙 파일을 문자열로 grep할 뿐,
"누가 무엇에 접근할 수 있는가"를 검증하지 않는다. 규칙이 완전히 개방돼 있어도
문자열만 맞으면 통과한다. P0 4건이 테스트를 모두 통과한 채로 존재했던 이유다.

## 본 감사에서 새로 구축한 검증

| 항목 | 명령 | 결과 |
|------|------|------|
| Firestore Rules 에뮬레이터 테스트 | `firebase emulators:exec --only firestore --project seolleyeon-rules-test "npm --prefix rules_tests test"` | 수정 전 **9 pass / 11 fail** → 수정 후 **20 pass / 0 fail** |

11건의 실패는 전부 보안 단언(SEC-P0-01~04)이었고, 9건의 통과는 로그인·학생
인증·프로필 수정 정상 플로우의 특성화 테스트였다. 즉 **취약점은 실증됐고,
정상 동작은 수정 전후로 보존됐다.**

실행 방법은 `rules_tests/README.md`에 있다. `--project seolleyeon-rules-test`는
운영 프로젝트에 절대 붙지 않게 하려는 것이므로 실제 프로젝트 ID로 바꾸면 안 된다.

## 운영 프로젝트 연결 상태

사용자 승인 하에 **읽기 전용** 조회만 수행했다. 쓰기·배포·데이터 변경은 없었다.

| 항목 | 값 | 평가 |
|------|-----|------|
| Active Project | `seolleyeon-final` | **운영 프로젝트** |
| Billing | Enabled | 실 과금 중 |
| 인증 계정 | `seolleyeon.official@gmail.com` | 운영 소유자 계정 |
| `.firebaserc` default / staging | 둘 다 `seolleyeon-final` | **staging이 곧 production.** 스테이징 검증이 운영 접촉이다 |
| Firestore location | `asia-northeast3` | |
| `functions/.env.seolleyeon-final`, `.env.seolleyeon-festival` | 워킹트리에 존재 | `.gitignore:53,64`로 제외 확인. 추적되지 않음. **내용을 열람하지 않았다** |

### 배포된 규칙과 저장소 규칙의 괴리 (최우선 발견)

`firebase_get_security_rules`로 조회한 **운영 배포본**은 저장소의
`firestore.rules`와 전혀 다른, 훨씬 개방된 버전이다. 상세는
04-security-findings.md의 SEC-P0-05를 볼 것. 요약하면 운영에는
채팅·신고·차단·무물·추천 로그가 **비인증 전체 읽기/쓰기**로 열려 있다.

즉 저장소를 아무리 고쳐도 **배포하지 않으면 운영은 그대로다.** 본 감사의
결론이 "코드 수정 완료"가 아니라 "배포가 최우선 조치"인 이유다.
