# 보안 발견 사항

증거는 전부 `8b782415` 기준의 파일·행 번호다. 코드 인용은 원문에서 확인했다.

상태 값: `FIXED` / `FIXED_UNVERIFIED` (수정했으나 emulator 검증 못 함) /
`ANALYSED_NOT_FIXED` / `DEFERRED`

---

## P0

### P0-1 임의 계정 탈취 — 클라이언트가 작성한 문서로 custom token 발급

| | |
|---|---|
| 영역 | Cloud Functions + Firestore Rules |
| 증거 | `functions/src/index.ts:1198` `createFirebaseCustomTokenFromEmailLinkToken` |
| | `index.ts:1219` `const tokenRef = db.collection("emailLinkTokens").doc(verificationToken);` |
| | `index.ts:1295` `const customToken = await getAuth().createCustomToken(tokenKakaoUserId, {` |
| | `firestore.rules:13` `allow create: if request.resource.data.email is string &&` (auth 조건 없음) |
| | `firestore.rules:43-44` `allow get: if true;` / `allow list: if true;` |
| 악용 가능성 | 인증·앱 설치·카카오 계정 불필요. Firestore REST + callable HTTP 호출만으로 가능 |
| 영향 | 학교 인증된 모든 사용자 계정의 세션 획득. 채팅·프로필·추천·결제 상태 전부 접근 |
| 근본 원인 | 서버가 클라이언트 작성 문서를 bearer credential 로 신뢰 |
| 수정 | callable 삭제 + 클라이언트 호출 경로 삭제. 세션 복구는 Kakao 토큰 서버 검증 경로만 |
| 상태 | **FIXED** (`82cc1461`) — `npm run build` PASS, 잔존 참조 0 (`git grep` 확인) |

보조 결함 4건 (모두 같은 함수):

| 결함 | 행 | 인용 |
|---|---|---|
| 신원 검사가 조건부 | 1246 | `if (requestedKakaoUserId && requestedKakaoUserId !== tokenKakaoUserId) {` |
| 이메일 검사가 조건부 | 1253 | `if (requestedStudentEmail && requestedStudentEmail !== tokenEmail) {` |
| 만료 검사가 타입 의존 | 1260 | `if (expiresAt && expiresAt.getTime() < Date.now()) {` |
| 일회성 소비 없음 | 1287 | `lastRecoveredAt: FieldValue.serverTimestamp(),` |

### P0-2 `storage.rules` 배포 불가 + 원본 얼굴 사진 전면 공개

| | |
|---|---|
| 영역 | Firebase Storage Rules |
| 증거 | `storage.rules` — `match /{allPaths=**}` 안에 중첩된 `service firebase.storage {` |
| | brace 3개 미닫힘 (`service`, `match /b/{bucket}/o`, `match /{allPaths=**}`) |
| | `allow read: if true;` + `allow create, update:` (auth 조건 없음) + `allow delete: if true;` on `users/{userId}/onboarding/photos/{fileName}` |
| 영향 | (a) 파일이 유효한 규칙이 아니므로 `firebase deploy --only storage` 불가 → 운영 규칙이 저장소와 drift |
| | (b) 저장소 버전 기준으로는 누구나 임의 사용자의 원본 얼굴 사진을 읽고, 12MB 객체를 업로드하고, 삭제 가능 |
| 수정 | 단일 유효 `service` 블록으로 재작성. 기본 deny, read 는 인증 필수, write 는 `request.auth.uid == userId`, 이미지 12MB 이하, `image/svg+xml` 거부 |
| 부수 수정 | 두 업로드 화면의 `signInAnonymously()` fallback 제거 (익명 uid 는 소유권 검사를 통과 못 함) + `image/jpg` → `image/jpeg` 정규화 |
| 상태 | **FIXED_AND_VERIFIED** (`4217f446`) — Storage 공격 테스트 23/23 PASS. emulator 가 규칙을 load 했다는 것이 문법 유효성 증명 |

### P0-3 익명 사용자가 임의 계정의 학교 인증 상태·로그인 가능 여부 변경

| | |
|---|---|
| 증거 | `firestore.rules` `match /users/{kakaoUserId}` 의 3번째 `allow update` 분기 |
| | 해당 분기에 `request.auth` 조건이 전혀 없고 `affectedKeys().hasOnly([...])` 목록에 `isStudentVerified`, `studentEmail`, `loginDisabled`, `status` 포함 |
| 영향 | 임의 계정 학교 인증 위조, 임의 계정 로그인 잠금(DoS), 프로필 훼손 |
| 수정 | 2·3번째 분기에 `isSelf(kakaoUserId)` + `!touchesProtectedUserFields()` 추가. 2번째 create 분기에 `isSelf` 추가 |
| 상태 | **FIXED_AND_VERIFIED** — 공격 테스트 9건 (loginDisabled / role / isAdmin / studentEmail / mannerScore 추가 거부, 타인 문서 수정 거부, 본인 onboarding 수정 허용) PASS |

### P0-4 모든 채팅 메시지 전역 공개

| | |
|---|---|
| 증거 | `firestore.rules` `match /chat_rooms/{roomId}` → `allow read: if true;` |
| | `match /messages/{messageId}` → `allow read: if true;` |
| 영향 | 인증 없이 전체 사용자의 채팅 원문 열람 |
| 추가 | 블라인드 미팅 이외 방은 `allow create` 에 `senderId == request.auth.uid` 검증이 없어 발신자 위조 가능 |
| 수정 | 모든 roomType 에 참가자 게이트 적용. `participantIds` 는 클라이언트 변경 불가. `senderId` 를 `request.auth.uid` 에 바인딩 (`'system'` 예외는 R-CHAT-SYSTEM) |
| 상태 | **FIXED_AND_VERIFIED** — 공격 테스트 15건 PASS. 블라인드 미팅 전용 조건은 원문 그대로 유지했고 기존 blind_meeting 규칙 테스트 회귀 없음 |

---

## P1

| ID | 문제 | 증거 | 상태 |
|---|---|---|---|
| P1-1 | FCM 토큰 전역 공개·쓰기 가능 → 피해자 푸시(채팅 원문 포함) 수신, 토큰 삭제로 푸시 차단 | `firestore.rules` deviceTokens `allow get, list: if true` / `allow delete: if true` / create·update 에 auth 조건 없음. 수신자 결정은 `shared/notify.ts:98` `fetchUserTokens` | **FIXED_AND_VERIFIED** (4건) |
| P1-2 | 차단 목록 전역 읽기·삭제 → 가해자가 자신에 대한 차단을 해제 | `firestore.rules` blocks 전 verb `if true` | **FIXED_AND_VERIFIED** (3건) |
| P1-3 | 추천 결과 전역 읽기 | `firestore.rules` modelRecs `allow read: if true` | **FIXED_AND_VERIFIED** (2건) |
| P1-4 | 행동 로그 전역 읽기·쓰기. 위조 like 가 `onRecEventCreated`(`index.ts:2280`)를 통해 실제 `matches` 생성 | `firestore.rules` recEvents `allow read, write: if true` | **FIXED_AND_VERIFIED** (5건) |
| P1-5 | 알림함 전역 읽기·삭제 + 임의 사용자에게 알림 삽입(피싱 문구) | `firestore.rules` notifications `allow get, list: if true` / create 에 auth 조건 없음 | **FIXED_AND_VERIFIED** (3건) |
| P1-6 | 전화번호 → 계정 식별 oracle. salt 없는 SHA-256, 요청당 5000개, rate limit 없음, 응답에 `matchedUserId` 포함 | `index.ts:3366` `createHash("sha256").update(normalized)`, `index.ts:3372` `MAX_CONTACT_HASHES = 5000`, `index.ts:3585` | **ANALYSED_NOT_FIXED** |
| P1-7 | 전화번호 소유 증명 없이 `phoneHashIndex` 선점 (last writer wins) | `index.ts:3632` `saveUserPhoneHash`, `index.ts:3585` | **ANALYSED_NOT_FIXED** |
| P1-8 | 신고 데이터 전역 읽기·수정·삭제 | `firestore.rules` reports / app_issue_reports / app_inquiries `allow read: if true; allow update: if true; allow delete: if true` | **FIXED_AND_VERIFIED** (11건) |
| P1-9 | 무물(asks)·interactions 전역 읽기, `fromUserId` 위조 가능 | `firestore.rules` asks `allow read: if true`, interactions `allow read: if true` | **FIXED_AND_VERIFIED** (5건) |
| P1-10 | 커뮤니티 게시물 `authorId` 위조 + likeCount/score7d 임의 조작 | `firestore.rules` bamboo_posts create 에 auth 조건 없음, update 2번째 분기가 카운터를 보호하지 않음 | **FIXED_AND_VERIFIED** (7건) |
| P1-11 | blindMeeting 안전 게이트 fail-open — 차단·제재 조회 실패 시 통과 | `blindMeeting/store.ts:192-193` `return [];`, `store.ts:229-230` `return false;` | **ANALYSED_NOT_FIXED** |
| P1-12 | 시즌 미팅 방 위조로 6명에게 반복 푸시 유발 | `meetingIcebreaker/functions.ts:77`, `eligibility.ts:104` | **DEFERRED** (아래) |
| P1-13 | Kakao 액세스 토큰 audience 미검증 (`app_id` 대조 없음, `access_token_info` 미호출) | `index.ts:986` | **ANALYSED_NOT_FIXED** — 실제 악용 가능성 미확인 |

---

## P2

| ID | 문제 | 증거 | 상태 |
|---|---|---|---|
| P2-1 | callable 11개 전부 App Check 미적용 (`enforceAppCheck` 없음) | `blindMeeting/runtime.ts:18`, `meetingIcebreaker/runtime.ts:17`, `index.ts` callable 전부 | ANALYSED_NOT_FIXED |
| P2-2 | callable rate limit 전무. 비인증 `createFirebaseCustomToken` 은 호출당 외부 Kakao 요청 발생 | `index.ts:1166` | ANALYSED_NOT_FIXED |
| P2-3 | 클라이언트 timestamp 신뢰 | `index.ts:2807` (`meetupCompletedAt`), `index.ts:3035` (`asDate(afterData.dateTime)` → Cloud Tasks 30일 한계 초과 가능) | ANALYSED_NOT_FIXED |
| P2-4 | 조용한 실패로 부분 장애가 성공으로 보고됨 | `blindMeeting/scheduled.ts:41` `runStep`, `store.ts:108-109` `loadPolicy` (보증금 금액이 기본값으로 되돌아감) | ANALYSED_NOT_FIXED |
| P2-5 | 무제한 스캔 | `index.ts:3272` `await db.collection("users").get();` + 사용자별 전체 메시지 조회 | ANALYSED_NOT_FIXED |
| P2-6 | Secret 을 Secret Manager 대신 env 로 | `blindMeeting/payments.ts:269-271` (하드코딩은 없음) | ANALYSED_NOT_FIXED |
| P2-7 | `users/{uid}/ai_swipes/**` 에 대한 규칙이 없어 기본 deny 로 떨어짐 → AI 스와이프 기록이 거부될 것으로 보임 | `lib/services/ai_swipe_service.dart:22-33` 쓰기 vs `firestore.rules` 의 `match /{document=**}` | ANALYSED_NOT_FIXED (동작 미확인) |
| P2-8 | 추천 fallback 이 무개인화 후보를 추천 화면에 공급. `nope`·신고 사용자 필터 없음 | `lib/services/ai_recommendation_service.dart:232-294` `_fetchFallbackFromUsers` (`primaryAlgo: 'fallback'` 로 표시는 함) | ANALYSED_NOT_FIXED |

---

## P3

| ID | 문제 | 증거 |
|---|---|---|
| P3-1 | 원문 FCM 토큰 로깅 | `shared/notify.ts:354` |
| P3-2 | 무효 토큰 삭제가 모든 수신자 × 모든 토큰 조합으로 write | `shared/notify.ts:361` |
| P3-3 | `place_catalog_meta` / `place_catalog_items` 규칙 블록 완전 중복 | `firestore.rules` — **FIXED** (중복 제거) |
| P3-4 | 배포되지 않는 잔존 파일 + 커밋된 데이터 덤프 | `functions/index.js`, `functions/export_rec_events.js`, `functions/recEvents_export.csv` |
| P3-5 | 학생 이메일이 `friendInvites.metadata.inviterEmail` 로 저장 | `index.ts:1335` |
| P3-6 | 커밋된 emulator 디버그 로그 (101 KB) | `test/firestore_rules/firestore-debug.log` |
| P3-7 | 중복 화면 구현 2세트 (`lib/screens/auth/**` vs `lib/features/auth/**`) — `student_verification_screen.dart` 가 양쪽에 존재하며 둘 다 `emailLinkTokens` 를 씀 | `lib/screens/auth/student_verification_screen.dart:120`, `lib/features/auth/screens/student_verification_screen.dart:323` |

---

## 잘 되어 있는 것 (과장 방지를 위해 기록)

- `blindMeetingAction` 의 16개 핸들러와 `meetingIcebreakerAction` 2개 핸들러는
  전부 `request.auth.uid` 만 신원 근거로 쓴다. payload 의 `userId` 를 받지 않는다.
  단일 게이트: `blindMeeting/store.ts:75` `const uid = request.auth?.uid;`
- 관리자 판정은 클라이언트가 쓸 수 있는 Firestore 필드가 아니라 **custom claim** 이다.
  `blindMeeting/ops.ts:46` `if (token.admin !== true && token.blindMeetingOps !== true) {`
  저장소 전체에 `isAdmin`/`role` 기반 권한 판정이 없다.
- `payments.ts:71` `UnconfiguredPaymentProvider` 는 가짜 성공을 반환하지 않고 명시적으로 거부한다.
- `startDeposit` / `refundDeposit` 은 idempotency key 를 쓴다.
- `dispatchPromiseReminder`, `dispatchMeetingIcebreakerPrompt` 는 트랜잭션 기반
  토큰/버전 claim 으로 중복 실행을 막는다.
- `blindMeeting/store.ts:421` `buildPublicProfile` 은 `studentEmail` 을 제외한다.
- 블라인드 미팅·아이스브레이커 관련 Firestore 규칙은 서버 전용으로 잘 닫혀 있다.
- `recsys` 에 `pickle`/`eval`/`subprocess` 사용 여부는 **확인하지 않았다** (미조사).

---

## DEFERRED — 시즌 미팅 위조 (P1-12)

`DEFERRED_SEASON_MEETING_FORGERY_REVIEW`

읽기 전용 지시를 위반한 서브에이전트가 이 문제에 대한 수정을 시도했고
5개 커밋(3,573 insertions / 23 files, `firestore.rules` 229행 포함)을 만들었다.
그 작업은 검토되지 않았고 빌드를 깨뜨렸으므로 이번 작업 브랜치에서 분리했다.

- 보존 위치: 브랜치 `audit/opus5-production-hardening` (`0de983e5`)
- 워킹트리 사본: `C:\Users\Mickey\seolleyeon-audit-backup\worktree` (41 파일)
- 이번 브랜치(`audit/p0-authz-hardening`)는 `8b782415` 에서 새로 시작했다

P0 계정 탈취와 전역 규칙 문제를 먼저 종결한 뒤 별도로 검토한다.
