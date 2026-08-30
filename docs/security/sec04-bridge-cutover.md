# SEC-04 — bridge 릴리스와 cutover 게이트

## 지금 상태

| | |
|---|---|
| Phase A (비공개 소유권 매핑) | main 병합됨 |
| public `bamboo_posts.authorId` | **아직 raw UID 그대로** |
| `SEC04_FIXED` | **NO** |
| `SEC04_CUTOVER_READY` | **NO** |

Phase A 는 소유권을 옮겨 둘 자리를 만들었을 뿐이다. public 문서에 여전히 raw
UID 가 있고 `publicProfiles/{uid}` 는 로그인만 하면 읽히므로, join 한 번으로
익명 글의 작성자를 특정할 수 있다는 사실은 그대로다.

## 이 문서가 다루는 것

public `authorId` 를 지우려면(Phase C) 그 필드에 의존하는 클라이언트가 먼저
사라져야 한다. 그 사전 작업이 bridge 릴리스다.

## 반드시 구분해야 하는 두 가지

| | 무엇 | 어디 |
|---|---|---|
| **클라이언트 업데이트 게이트** | 사용자에게 업데이트를 요구하는 UX | 앱 |
| **서버 capability 강제** | legacy write 를 실제로 거부하는 경계 | Firestore Rules |

cutover 의 보안 authority 는 **Firestore Rules** 다. 정책 문서도, 업데이트
화면도 아니다. 수정된 클라이언트는 업데이트 화면을 지울 수 있고, 그래도
Phase D 불변식은 깨지지 않아야 한다.

`CLIENT_VERSION_GATE_IS_UX_ONLY = YES`

## 게이트가 못 하는 일 — 반드시 읽을 것

**bridge 이전 빌드에는 이 게이트 코드가 없다.**

bridge 릴리스를 스토어에 올려도 build 14 이하 사용자는 아무 영향을 받지
않는다. 그들에게는 정책을 읽는 코드도, 업데이트 화면도 존재하지 않는다.

```
PRE_BRIDGE_CLIENTS_DO_NOT_KNOW_THIS_GATE
ALL_OLD_CLIENTS_BLOCKED = NO
OLD_CLIENTS_FORCED_TO_UPDATE = NO
```

"minimum-version gate 를 구현했으므로 구버전이 차단된다" 는 **틀린 문장이다.**
게이트는 bridge 릴리스 **이후** 빌드부터 동작한다.

## Phase C 이후 구버전이 겪는 일

pre-bridge 클라이언트의 "내가 쓴 글" 은 public 문서를 직접 조회한다.

```dart
_posts.where('authorId', isEqualTo: uid)
```

Phase C 가 `authorId` 를 지우면 이 쿼리는 **빈 목록**을 돌려준다. 앱은 죽지
않지만 사용자는 자기 글을 잃은 것처럼 본다.

```
OLD_CLIENT_READ_COMPATIBILITY_AFTER_PHASE_C = BROKEN
PRE_BRIDGE_ZERO_BREAK_CUTOVER = IMPOSSIBLE_WITH_CURRENT_SCHEMA
```

클라이언트가 Firestore 를 직접 조회하는 현재 구조에서 "public authorId 제거"
와 "pre-bridge 완전 호환" 을 동시에 만족시킬 방법은 없다. 서버 API 를 경유하는
구조로 바꾸면 가능하지만 그것은 이 작업의 범위가 아니다. **이 한계를 숨기지
않고 cutover 승인 시점에 명시적으로 수용해야 한다.**

## 클라이언트 게이트 구조

| | |
|---|---|
| 삽입 지점 | `MaterialApp.builder` (`lib/app.dart`) |
| 정책 소스 | `appCompatibilityConfig/{flavor}` (공개 읽기 전용 Firestore 문서) |
| 버전 소스 | `package_info_plus` → build number (Android `versionCode` / iOS `CFBundleVersion`) |
| flavor 판별 | Flutter 내장 `appFlavor` (플러그인 없음) |

### 왜 Remote Config 가 아닌가

이 저장소에는 이미 `blindMeetingConfig` / `meetingIcebreakerConfig` 같은 공개
읽기 전용 운영 설정 문서 관례가 있고 `cloud_firestore` 는 이미 의존성에 있다.
Remote Config 를 넣으면 네이티브 플러그인이 하나 더 늘고(빌드 리스크), 문서가
공개 읽기이며 클라이언트가 쓸 수 없다는 사실을 CI 에서 증명할 방법이 없다.
Firestore 를 쓰면 `rules_tests/firestore.appcompat.test.mjs` 가 그것을 매 CI 에서
검증한다.

### 왜 semver 가 아니라 build number 인가

`1.0.10 < 1.0.9`. 문자열 비교는 hard gate 근거가 될 수 없다. Android
`versionCode` 와 iOS `CFBundleVersion` 은 둘 다 Flutter build number 에서 나오는
단조 증가 정수다.

### 세 가지 상태

| 상태 | 동작 |
|---|---|
| `SUPPORTED` | 정상 진입 |
| `UPDATE_RECOMMENDED` | 그대로 사용 가능 |
| `UPDATE_REQUIRED` | 본 화면을 덮고 업데이트 화면만 표시 |

### 왜 우회할 수 없는가

게이트는 `MaterialApp.builder` 에 있고, 그 자리는 Navigator **위**다. 딥링크로
push 된 라우트도, 푸시 알림이 `pushNamedAndRemoveUntil` 로 밀어넣은 라우트도
게이트 아래에 깔린다. 라우트마다 가드를 붙이는 방식이라면 새 화면을 추가할
때마다 빠뜨릴 수 있지만, 이 구조에는 빠뜨릴 자리가 없다.

`test/shared/widgets/app_compatibility_gate_test.dart` 가 딥링크·푸시·pop·탭
흡수·resume 재확인을 각각 검증한다.

### 정책을 못 읽었을 때

**실패는 전부 통과 쪽으로 떨어진다.** 오프라인, 타임아웃, 문서 없음, 권한
오류, 값 깨짐 — 어느 것도 `UPDATE_REQUIRED` 를 만들지 않는다. 정책 소스 장애
한 번이 전체 사용자 lockout 이 되면 안 되기 때문이다. 보안은 여기에 걸려
있지 않으므로 fail-open 이 맞다.

내장 기본 정책은 `minimumSupportedBuild: 0`, `requiredCapabilities: []` 다.
앱이 먼저 배포되고 정책 문서를 나중에 만드는 순간이 반드시 있는데, 그때
현재 출시본이 스스로 잠기면 안 된다.

`CURRENT_RELEASE_SELF_LOCKOUT = NO`

### production / staging 분리

두 flavor 는 **같은 Firebase 프로젝트**(`seolleyeon-final`)를 쓴다. 그래서
프로젝트로 나눌 수 없고 문서로 나눈다.

| flavor | 패키지 | 읽는 문서 |
|---|---|---|
| production | `com.seolleyeon.app` | `appCompatibilityConfig/production` |
| staging | `com.yonsei.dating` | `appCompatibilityConfig/staging` |
| 없음 (테스트/웹) | — | 게이트 미적용 |

production 최소 빌드가 개발자 staging 빌드를 잠그는 일이 없다. 웹은 언제나
마지막으로 배포된 코드가 뜨므로 낡은 클라이언트가 남지 않아 게이트 대상이
아니다.

### capability 기반 요구

정책은 build 번호 대신 capability 를 요구할 수 있다.

```json
{ "requiredCapabilities": ["bambooPrivateOwnershipV1"] }
```

이 빌드가 선언하는 capability 는 `kAppCapabilities` 에 있다. SEC-04 하나에
`if version < X` 를 하드코딩하지 않기 위한 것이고, 다음 정책에도 그대로
재사용된다.

### 계정 필수 조작

업데이트 화면에서 **로그아웃은 가능하다**. 공용 기기에서 계정을 두고 나가야
하는 경우가 있고, 앱 내부로 들어가지 않는 조작이라 막을 이유가 없다.

**계정 삭제는 업데이트 후에 가능하다.** 삭제 화면은 설정 깊숙이 있어 열어주면
앱 전체를 열어주는 것과 같다. 삭제 경로가 사라지는 것이 아니라 한 단계
늘어나는 것이며, 문의 경로(`RouteNames.inquiry`)도 업데이트 후 접근 가능하다.
이 선택은 운영/법무 검토 대상으로 남긴다.

## Phase D 서버 강제 — 준비만 되어 있음

`rules_tests/fixtures/sec04-phase-d.candidate.rules` 는 **배포되지 않는다.**
`firebase.json` 은 `firestore.rules` 만 배포하고, 이 후보 파일이 그 자리로
옮겨가는 순간이 곧 cutover 다.

`rules_tests/firestore.sec04phased.test.mjs` 가 후보 규칙을 로드해 증명하는 것:

| | |
|---|---|
| 매핑 없는 글/댓글 생성 | DENY |
| public `authorId` 포함 | DENY |
| 매핑을 같은 커밋에 쓴 글/댓글 | ALLOW |
| 남의 글에 소유권 붙이기 | DENY |
| 타인의 매핑 읽기 | DENY |

**규칙은 클라이언트가 신고한 버전을 신뢰하지 않는다.** 후보 규칙에는
`buildNumber` 도 `clientVersion` 도 `schemaVersion` 도 없고, 테스트가 그
부재를 검증한다. 그런 필드는 클라이언트가 마음대로 적을 수 있어 보안 근거가
되지 못한다.

capability 증명은 **실제 쓰기의 모양**이다 — 비공개 매핑을 같은 커밋에 남길 수
있는 클라이언트만 글을 쓸 수 있고, 그 능력 자체가 증명이다. 그래서 public
문서에 `clientVersion` 같은 필드를 새로 추가할 이유가 없다.

## adoption 근거 — 추측하지 않는다

```
ADOPTION_EVIDENCE_SOURCE = EXTERNAL_EVIDENCE_REQUIRED
CUTOVER_ADOPTION_THRESHOLD = PRODUCT_DECISION_REQUIRED
```

필요한 근거는 스토어 콘솔에 있다.

- Google Play — version distribution / active installs
- App Store Connect — version adoption / active devices

클라이언트가 스스로 신고한 build number 는 위조 가능하므로 **cutover 근거로
쓰지 않는다**(`ADOPTION_TELEMETRY_ONLY`). 이번 작업에서는 새 텔레메트리를
추가하지 않았다 — 스토어 콘솔이 이미 더 정확한 숫자를 갖고 있고, 근거로 쓸 수
없는 데이터를 위해 수집 항목을 늘릴 이유가 없다.

임계값(95% / 99% / 99.9%)은 **여기서 정하지 않는다.** 실제 active-version
분포를 보고 운영자가 결정할 사항이다.

## cutover 순서

1. bridge 릴리스 서명 빌드
2. Play / App Store 배포
3. production 호환성 정책 문서 설정
4. adoption 관찰 기간
5. adoption 근거 검토 → **cutover 승인**
6. Phase-D 규칙으로 legacy write 차단
7. production 마이그레이션 dry-run
8. conflict = 0 확인
9. Phase C 마이그레이션 (public `authorId` 제거)
10. Phase D 최종 적용
11. 잔여 pre-bridge 트래픽 모니터링

1~5 는 이 저장소 밖의 외부 단계다. **6 이후는 pre-bridge 사용자가 남아 있을
가능성을 명시적으로 수용한 뒤에만 진행한다.**

## 이번 작업이 하지 않은 것

- production Remote Config / Firestore 설정 값 변경 — **없음**
- production 마이그레이션 — **없음**
- public `authorId` 제거 — **없음**
- Phase-D 규칙 적용 — **없음**
- Firebase / Functions 배포 — **없음**
- 스토어 업로드 — **없음**

```
BRIDGE_SOURCE_READY = YES
BRIDGE_RELEASED_TO_USERS = NO
```
