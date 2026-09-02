# Firebase Rules 5개 실패 포렌식

검증일: 2026-09-02 (Asia/Seoul)

## 범위와 기준선

- worktree: `C:/Users/samsung/StudioProjects/semisemifinal-security`
- branch: `security-main`
- 조사 시작 HEAD: `5ea0d8c1d23d2ca43584c0e262b4e4457985e123`
- canonical command: `npm --prefix test/firestore_rules test`
- JDK: Microsoft OpenJDK `21.0.12`
- 수정 전 fresh result: 197 total, 192 pass, 5 fail

## 정확한 실패 목록

| ID | Test | Path / operation | Expected | Actual | 최초 차단 계약 |
|---|---|---|---|---|---|
| R1 | `authz_hardening_rules.test.js` — `authenticated users read cross-user profiles through publicProfiles` | `publicProfiles/{victim}` get | ALLOW | DENY | `isCanonicalAppSession()`; fixture에는 `request.auth`만 있고 canonical claim이 없었음 |
| R2 | `authz_hardening_rules.test.js` — 기존 `자신이 참가자인 방은 만들 수 있다` | `chat_rooms/new-room-2` create | ALLOW | DENY | `firestore.rules`의 `allow create: if false` |
| R3 | `authz_hardening_rules.test.js` — `본인 이름의 무물은 허용한다` | `asks/a-own` create | ALLOW | DENY | `isCanonicalAppSession()` |
| R4 | `bamboo_counter_rules.test.js` — `정상 글 작성(authorId==self, 카운터 0)은 허용` | `bamboo_posts/p2` create | ALLOW | DENY | `isCanonicalAppSession()` |
| R5 | `kakao_login_rules.test.js` — `other authenticated sessions read publicProfiles, not private users` | `publicProfiles/{kakaoUserId}` get | ALLOW | DENY | `isCanonicalAppSession()` |

R1/R3/R4/R5는 동일한 stale fixture 원인이다. R2는 직접 채팅방 생성 권한이 서버 callable로 이전된 뒤 남아 있던 이전 기대값이다.

## canonical appSession 계약

`appSession`은 Firestore의 클라이언트 작성 세션 문서가 아니다. Firebase Auth custom claim이다.

- creator: `completePrimaryStudentEmailAuth` 흐름의 `functions/src/primaryEmailAuth.ts`
- new claim shape: `{ appSession: true, primaryAuth: "yonsei_email" }`
- legacy compatibility: 서버가 발급한 custom token의 non-null `kakaoUserId` claim
- client activation: `lib/services/auth_service.dart`가 callable 결과의 custom token으로 Firebase Auth에 로그인
- owner: Firebase Auth의 `request.auth.uid`; 각 Rules의 path/field ownership 조건은 별도로 계속 적용
- expiry: 별도 Firestore TTL 문서를 읽지 않는다. Firebase ID token 수명·갱신 계약을 따른다.
- Rules consumer: `firestore.rules`의 canonical session helper와 public/social surfaces
- forgery boundary: 클라이언트는 custom claim을 직접 쓸 수 없고 Admin SDK token 발급 경로만 claim을 설정한다.

채팅방 생성은 별도 계약이다. `chat_rooms/{roomId}`의 client create는 항상 거부되고, 정상 direct-room 생성과 heart charging은 `unlockDirectChat` 서버 transaction이 소유한다. Flutter의 chat service도 이 callable을 사용한다.

## 분류와 영향

| ID | Classification | Severity | Production impact | Action |
|---|---|---|---|---|
| R1 | R-A STALE_TEST_FIXTURE | TEST_ONLY | 없음. 실제 primary/legacy producer는 canonical claim을 발급함 | 정상 fixture에 canonical claims 추가 |
| R2 | R-E INTENTIONAL_SECURITY_CONTRACT_CHANGE | TEST_ONLY | 없음. 기존 ALLOW 기대가 서버 전용 생성 계약과 충돌 | 이름과 기대를 canonical session에서도 DENY로 수정 |
| R3 | R-A STALE_TEST_FIXTURE | TEST_ONLY | 없음 | 정상 fixture에 canonical claims 추가 |
| R4 | R-A STALE_TEST_FIXTURE | TEST_ONLY | 없음 | 정상 fixture에 canonical claims 추가 |
| R5 | R-A STALE_TEST_FIXTURE | TEST_ONLY | 없음 | 정상 fixture에 canonical claims 추가 |

Rules P0: 0. Rules P1: 0. UNKNOWN: 0.

## 변경과 보안 불변식

- `authz_hardening_rules.test.js`: 일반 앱 traffic helper에 canonical claims를 부여하고 직접 채팅방 create를 DENY 계약으로 교정했다.
- `bamboo_counter_rules.test.js`: 정상 bamboo fixture에 canonical claims를 부여해 payload/counter assertions가 session gate에서 조기 종료되지 않게 했다.
- `kakao_login_rules.test.js`: cross-user public projection read용 fixture만 canonical session으로 만들었다. private `users/{uid}` write DENY는 유지된다.
- production `firestore.rules`는 변경하지 않았다.
- 테스트 삭제, skip, xfail, admin privilege 부여는 없었다.

## 검증

- targeted three-file suite: 117 pass, 0 fail
- 별도 canonical-session contract suite: 6 pass, 0 fail
- fresh full emulator suite: 197 pass, 0 fail, 0 skipped
- 유지된 DENY: unauthenticated, cross-user private users access, forged sender/author, direct chat room create, client-only server collections, undefined-path default deny

결론: 5개 실패는 production Rules 완화 대상이 아니었다. fixture와 기대 계약만 현재 서버 발급 세션/서버 전용 채팅방 생성 구조에 맞췄다.
