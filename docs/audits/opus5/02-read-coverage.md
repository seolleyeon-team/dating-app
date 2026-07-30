# 02 — 조사 범위 및 읽기 커버리지 (Opus 5 감사)

작성 시각: 2026-07-27
방법: 읽기 전용 (Glob / Grep / Read). 셸 불가로 인해 파일 수 집계는
도구 검색 결과 기반이며 `find`/`wc` 등으로 교차 검증하지 못했다.

## 감사 대상 저장소 구조 (확인된 최상위 영역)

| 영역 | 경로 | 성격 |
|------|------|------|
| Flutter 앱 | `lib/` (ai_recommend_model 제외 273개 `.dart`) | 클라이언트 |
| 추천/AI 모델 | `lib/ai_recommend_model/` (약 26개 `.py` + avatar_generation) | Python |
| 추천 파이프라인 | `recsys/` (6개 `.py` + Dockerfile) | Cloud Run Job |
| Cloud Functions | `functions/src/` (TypeScript, 35개 export) | 서버 |
| 인프라 | `infra/deploy.sh`, `infra/workflows/recs_pipeline.yaml`, `cloudbuild.yaml` | 배포 |
| 보안 규칙 | `firestore.rules` (1011줄), `storage.rules` (69줄) | 규칙 |
| 인덱스 | `firestore.indexes.json` | 규칙 |
| Flutter 테스트 | `test/` (19개 파일) | 테스트 |
| Python 테스트 | `tests/` (아바타 위주 다수) | 테스트 |
| 운영 스크립트 | `scripts/` (49개 `.py` + `.ps1`/`.sh`) | 도구 |
| 웹 | `seolleyeon-initial/`, `seolleyeon-iniitial/`, `public/` | 웹/호스팅 |

## 정독한 파일 (메인 에이전트 직접 확인)

| 파일 | 범위 |
|------|------|
| `firestore.rules` | **전체 1011줄** |
| `storage.rules` | **전체 69줄** |
| `firebase.json` | 전체 |
| `.firebaserc` | 전체 |
| `.gitignore` | 전체 |
| `pubspec.yaml` | 전체 |
| `README.md` | 전체 (Flutter 기본 템플릿) |
| `functions/src/index.ts` | 1440–1620행 (custom token 발급 경로) |
| `lib/features/auth/screens/student_verification_screen.dart` | 230–369행 (이메일 링크 흐름) |
| `lib/features/onboarding/screens/terms_screen.dart` | 80–119행 (테스트 계정 우회) |

## 서브에이전트가 조사한 영역 (읽기 전용)

메인 에이전트는 서브에이전트 결과를 그대로 신뢰하지 않고,
**P0로 승격한 항목은 모두 직접 원문을 재확인했다** (위 정독 목록 참조).
P1 이하 항목은 서브에이전트 근거(파일:줄)를 채택하되 미재확인 상태임을 명시한다.

| 서브에이전트 | 담당 | 결과 문서 |
|---|---|---|
| Flutter/Dart | `lib/` 273개 `.dart`, `test/` 19개 | 04-security-findings.md에 반영 |
| Cloud Functions | `functions/src/**` 35개 export + 9개 테스트 | 04-security-findings.md에 반영 |
| 추천 시스템 | `recsys/` 6개, `lib/ai_recommend_model/` 14개 정독 + 6개 부분 | 04-security-findings.md에 반영 |

## 조사에서 제외한 항목

| 제외 대상 | 이유 |
|---|---|
| `functions/node_modules/**` | 외부 의존성. 단 `functions/package-lock.json`은 검사 대상이었으나 **미검사** (아래 참조) |
| `functions/lib/**` | `functions/src/**`의 TypeScript 컴파일 산출물 |
| `.dart_tool/`, `build/`, `.pytest_cache/` | 생성물 |
| `ios/Pods/`, `.gradle/` | 외부 의존성 |
| `.tmp/**`, `.g002narrow/**`, `.g003_pytest_tmp/**` | 이전 작업의 임시 산출물 (미커밋 사용자 파일 — 건드리지 않음) |
| `functions/.env.seolleyeon-final` | 실제 환경 변수 파일. **의도적으로 열지 않음.** `.example` 파일로 키 종류만 파악 |
| `assets/fonts/*.ttf`, 모델 가중치 | 바이너리 |

## 조사하지 못한 영역 (읽기 커버리지 공백)

§3.2가 필수 검사 대상으로 지정했으나 본 세션에서 **확인하지 못한** 항목:

| 미조사 영역 | 영향 |
|---|---|
| `android/app/src/main/AndroidManifest.xml` | 권한 선언, exported 컴포넌트, 딥링크 intent-filter 검증 안 됨 |
| `ios/Runner/Info.plist` | 권한 설명, URL scheme, ATS 설정 검증 안 됨 |
| `android/app/build.gradle` | minify/shrink, signing, debuggable 플래그 미확인 |
| `firestore.indexes.json` | 쿼리-인덱스 정합성 미검토 |
| `pubspec.lock`, `functions/package-lock.json` | 의존성 CVE·supply chain 미검토 |
| `requirements*.txt` 4종 | Python 의존성 고정/CVE 미검토 |
| `.github/workflows/**` | 발견되지 않음 (CI 부재로 추정, 미확정) |
| `seolleyeon-initial/`, `seolleyeon-iniitial/` (축제 웹) | **전혀 조사하지 않음.** 참가권/결제 관련 코드가 있을 수 있음 |
| `public/` (Hosting) | 이메일 링크 랜딩 페이지 포함 추정 — SEC-P0-01 관련성 있으나 미조사 |
| `scripts/` 49개 중 47개 | 운영 도구. 위험한 fallback·자격증명 취급 미검토 |
| `tests/` Python 테스트 대부분 | 아바타 관련 다수 미정독 |
| `lib/` 273개 중 대부분 | 서브에이전트의 grep 기반 스캔은 받았으나 메인 에이전트 정독은 소수 파일에 한정 |
| `lib/ai_recommend_model/avatar_generation/**` | 아바타 생성 파이프라인 Python 측 미조사 (Functions 측만 조사) |

## 정직한 커버리지 평가

**"전체 코드를 읽었다"고 주장할 수 없다.**

- 보안 규칙(`firestore.rules`, `storage.rules`)은 전체를 정독했고, 이것이 최대 성과다.
- Cloud Functions는 인벤토리와 보안 매트릭스를 확보했으나 원문 정독은 부분적이다.
- Flutter 클라이언트는 구조·패턴 스캔 수준이며 화면별 로직 검증은 하지 않았다.
- 네이티브 설정, 의존성, 축제 웹, 운영 스크립트는 **공백**이다.
- 셸 불가로 인해 어떤 동적 검증도 없었다.

따라서 §26 완료 기준 중 "production 코드 전체 인벤토리 작성"은 **미충족**이다.
