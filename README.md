# 설레연 (seolleyeon)

학교 인증 기반 소개·미팅 앱. Flutter 클라이언트와 Firebase 백엔드(Cloud Functions,
Firestore/Storage Rules, Hosting), Python 추천·아바타 파이프라인으로 이루어져 있다.

이 문서는 저장소를 처음 여는 사람이 **무엇이 어디에 있고, 무엇을 돌려야 변경을
검증한 것인지** 알 수 있게 하는 지도다. 세부 운영 절차는 `docs/` 를 따른다.

## 구성

| 경로 | 내용 |
|---|---|
| `lib/` | Flutter 앱. 진입점 `lib/main.dart`, 라우팅 `lib/router/`, 기능별 코드 `lib/features/` |
| `lib/ai_recommend_model/` | Python 아바타 생성 워커·추천 모델 코드 (Flutter 코드가 아니다) |
| `functions/` | Cloud Functions (TypeScript, Node 22). 진입점 `functions/src/index.ts` |
| `firestore.rules`, `storage.rules`, `firestore.indexes.json` | 보안 규칙과 인덱스 정본 |
| `rules_tests/` | 규칙 테스트 (에뮬레이터, CI 의 `rules` / `storage-rules` job) |
| `test/` | Flutter 테스트. `test/firestore_rules/` 는 별도의 규칙 공격 테스트 스위트 (Node) |
| `tests/`, `recsys/tests/` | Python 테스트 (아바타 파이프라인·배포 가드·추천) |
| `recsys/` | 추천 파이프라인 |
| `scripts/` | 운영·마이그레이션·배포 가드 스크립트 |
| `public/` | Firebase Hosting 정적 페이지 (랜딩, 초대·이메일 인증 링크 페이지) |
| `docs/` | 감사 기록, 런북, 릴리스 문서 |

3:3 블라인드 취향 미팅(`lib/features/blind_meeting`, `functions/src/blindMeeting/`)과
3:3 시즌 미팅(`lib/features/event`, `functions/src/seasonMeeting*.ts`,
`teamMeetingRequest.ts`)은 서로 다른 기능이다.

## 도구 버전

CI(`.github/workflows/ci.yml`)가 기준이다.

- Flutter `3.47.2` (stable)
- Node `22` (Functions), firebase-tools `15.30.2`
- JDK `21` (Firebase 에뮬레이터. firebase-tools 15 는 21 미만을 지원하지 않는다)
- Python `3.12` + `pytest`

## 검증

변경을 끝냈다고 말하기 전에 해당 영역의 명령을 실제로 실행한다. 모두 저장소
루트 기준이다.

### Flutter

```bash
flutter pub get --enforce-lockfile
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
```

### Cloud Functions

```bash
cd functions
npm ci
npm run lint   # tsc --noEmit (타입 검사)
npm test       # tsc 빌드 후 lib/**/*.test.js
```

`npm test` 는 `*.test.ts` 만 돌린다. Firestore 트랜잭션·트리거를 실제 엔진에서
검증하는 `*.emulator-test.ts` 는 에뮬레이터가 필요하고, 실행 목록과 프로젝트 id 는
CI 의 `security-emulators` job 에 있다. 형태는 다음과 같다.

```bash
firebase emulators:exec --only firestore --project demo-blind-fsm \
  "node --test functions/lib/blindMeeting/blindMeetingFsm.emulator-test.js"
```

### 보안 규칙

```bash
# rules_tests (CI: rules, storage-rules)
firebase emulators:exec --only firestore,storage --project seolleyeon-rules-test \
  "npm --prefix rules_tests run test:all"

# test/firestore_rules (CI: rules-attack-suite)
cd test/firestore_rules && npm ci && npm test
```

### Python

```bash
PYTHONPATH=. python -m pytest -q tests recsys/tests
```

CI 는 이 중 명시된 파일만 실행한다(`python-recsys`, `functions-bootstrap` job).

## 빌드

Android `applicationId` 는 flavor 가 정하므로 flavor 없는 빌드는 성립하지 않는다.

```bash
flutter build apk --debug --flavor production
flutter build apk --debug --flavor staging
flutter build appbundle --flavor production --release   # android/key.properties 필요
```

release 빌드는 `android/key.properties` 가 없으면 실패하도록 되어 있다. 서명
자료(`*.jks`, `key.properties`)는 커밋하지 않는다.

## 배포

- Functions 는 `scripts/deploy_functions_guarded.sh` 로 **이름을 지정한 함수만**
  배포한다. 이 스크립트가 배포 전후로 실행 중인 리비전의 환경 변수를 대조한다.
  `firebase deploy --only functions` 를 직접 실행하지 않는다
  (`npm run deploy` 는 거부하도록 되어 있다).
- Hosting 배포는 사이트 전체를 교체한다. 배포 전에 라이브와 `public/` 을 대조한다.
- 규칙·인덱스 배포와 운영 데이터 변경은 소유자 승인 후에만 한다.

## 현재 상태와 미해결 항목

미해결 항목의 단일 원장은
`docs/audits/production_readiness_2026-10/00-backlog.md` 다. 상태는 문서가 아니라
증거(테스트·배포 리비전·실측)로만 바뀐다.
