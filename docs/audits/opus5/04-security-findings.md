# 04 — 보안 발견 사항 (Opus 5 감사)

작성 시각: 2026-07-27 (2차 갱신: 에뮬레이터 검증 및 운영 배포본 대조 반영)
감사 방식: 정적 코드 분석 + Firestore 에뮬레이터 동적 검증 + 운영 배포 규칙 읽기 전용 대조

1차 작성 시점에는 셸이 동작하지 않아 정적 분석만 가능했다. 2차에서 셸이
복구되어 P0 항목을 **실제 규칙 엔진으로 재현**하고 수정했다. `상태` 열은
검증 수준과 수정 여부를 함께 나타낸다.

---

## 요약

| ID | 등급 | 영역 | 제목 | 상태 |
|----|------|------|------|------|
| **SEC-P0-05** | **P0** | **배포** | **운영에 배포된 규칙이 저장소본보다 훨씬 개방적 — 채팅 전체 공개** | **Firestore 규칙 배포 완료 (2026-07-27). Functions 일부 CPU 쿼터로 재시도 필요** |
| SEC-P0-01 | P0 | 인증 | 비인증 임의 계정 탈취 (emailLinkTokens → custom token) | 에뮬레이터 재현 → **수정 완료** (`b1ab01b`) |
| SEC-P0-02 | P0 | Firestore Rules | 비인증 사용자 문서 생성 + 학교 인증 위조 | 에뮬레이터 재현 → **수정 완료** (`b1ab01b`) |
| SEC-P0-03 | P0 | Firestore Rules | 연세 이메일 보유자가 타인 문서의 studentEmail 탈취 | 에뮬레이터 재현 → **수정 완료** (`b1ab01b`) |
| SEC-P0-04 | P0 | 개인정보 | users 컬렉션 전체 비인증 read/list | 에뮬레이터 재현 → **수정 완료** (`b1ab01b`) |
| SEC-P1-01 | P1 | 클라이언트 | 프로덕션 UI의 테스트 계정 로그인 우회 (`fake_user_1`) | **수정 완료** (약관 버튼 + 가짜 채팅방 debug 전용) |
| SEC-P1-02 | P1 | 채팅 | 참여자가 상대방 메시지를 임의 수정 가능 | **수정 완료** (읽음 표시·약속 생애주기만 허용) |
| SEC-P1-03 | P1 | 채팅 | 참여자가 participantIds 임의 변경 가능 | **수정 완료** (participantIds immutable) |
| SEC-P1-04 | P1 | 추천 | recEvents 클라이언트 무검증 쓰기 (추천 조작) | **수정 완료** (append-only + 타입 화이트리스트, 운영 규칙 배포) |
| SEC-P1-05 | P1 | Functions | 인증/부트스트랩 callable App Check 미적용 | **수정·운영 배포 완료** (`809fa537`, 13 callables) |
| **REC-P0-01~04** | **P0** | **추천** | **정책 필터·RRF 게이트 미적용 + 차단 단방향 (→ [14번 문서](14-recommendation-policy-findings.md))** | **수정 완료** |
| **REC-P1-01~02** | **P1** | **추천** | **신고 양방향 차단 callable + 폴백 정책 적용 (→ [14번 문서](14-recommendation-policy-findings.md))** | **수정 완료** |
| SEC-P1-06 | P1 | 추천 | 배치 파이프라인이 blocks/contactBlocked 미제외 | 부분 완화 (recEvents block/report 대칭 제외는 REC-P0-04; Firestore blocks·연락처 해시는 미로드) |
| SEC-P1-07 | P1 | FCM | 차단·탈퇴 사용자 푸시 미필터 | 코드상 확정, 미수정 |
| SEC-P1-08 | P1 | 개인정보 | account_deletion 시 대량 orphan 데이터 잔존 | 코드상 확정, 미수정 |
| SEC-P2-01 | P2 | 커뮤니티 | bamboo_posts likeCount 임의 조작 | 코드상 확정, 미수정 |
| SEC-P2-02 | P2 | 데이터 일관성 | 상호 like 시 match/chat_room 중복 생성 race | 코드상 확정, 미수정 |
| SEC-P3-01 | P3 | Rules | place_catalog 규칙 블록 중복 정의 | 코드상 확정, 미수정 |

---

## SEC-P0-05 — 운영에 배포된 Firestore 규칙이 저장소본보다 훨씬 개방적

**등급:** P0 (Critical)
**영역:** 배포 / Firestore Rules / 개인정보
**악용 가능성:** 매우 높음. 인증 불필요. Firebase 프로젝트 ID만 알면 REST API로 직접 접근 가능.
**검증:** 2026-07-27, `firebase_get_security_rules(type=firestore)`로 **운영 프로젝트
`seolleyeon-final`의 실제 배포본을 읽기 전용 조회**하여 확인. 쓰기·배포는 하지 않았다.

### 영향

이 감사에서 가장 중요한 발견이다. 저장소의 `firestore.rules`(1011줄, 상당히
견고함)와 **실제 운영에 배포된 규칙이 서로 다른 버전**이며, 배포본은 핵심
컬렉션 대부분이 `if true`로 열려 있다.

저장소를 아무리 잘 고쳐도 배포되지 않으면 운영은 바뀌지 않는다. 아래는
현재 운영에서 **비인증 상태로 가능한 것들**이다.

| 컬렉션 | 배포된 규칙 | 비인증 상태로 가능한 일 |
|--------|-------------|--------------------------|
| `chat_rooms/{roomId}` | `allow read: if true` | **모든 사용자의 모든 채팅방 조회** |
| `chat_rooms/{roomId}/messages/{id}` | `allow read, create: if true`<br>`allow update: if true` | **모든 채팅 메시지 열람.** 임의 발신자로 메시지 삽입. 남의 메시지 내용 수정 |
| `reports/{reportId}` | `read/update/delete: if true` | **신고 내용·신고자·피신고자 전체 열람.** 신고 임의 삭제(증거 인멸) |
| `blocks/{viewerUid}` | `read/create/update/delete: if true` | 타인의 차단 목록 열람. **타인의 차단 해제** |
| `asks/{askId}` | `allow read: if true` | 모든 무물 질문·답변 열람 |
| `recEvents/{userId}` 및 하위 | `read, write: if true` | 행동 로그 전체 열람 + 임의 이벤트 주입(추천 조작) |
| `interactions/{id}` | `allow read: if true` | 누가 누구를 like/nope 했는지 전체 열람 |
| `matches/{id}` | `read: if true`, `create: if true` | 매치 관계 전체 열람. 임의 매치 생성 |
| `users/{uid}/deviceTokens/{token}` | `get/list/create/update/delete: if true` | **FCM 토큰 수집** 및 타인 토큰 등록·삭제 |
| `users/{uid}/notifications/{id}` | `get/list/create/delete: if true` | 타인 알림 열람, **가짜 알림 주입**, 알림 삭제 |
| `modelRecs/{uid}/...` | `allow read: if true` | 타인의 추천 결과·점수 열람 |
| `bamboo_posts/{id}` | `create`에 `authorId` 무검증 | 커뮤니티 글 **타인 명의 작성** |
| `app_issue_reports`, `app_inquiries` | `read/update/delete: if true` | 문의·제보 내용 전체 열람 및 삭제 |
| `users/{uid}` | `get/list: if true` | 학교 이메일·프로필·취향 벡터 전체 수집 (= SEC-P0-04) |

`chat_rooms`의 노출은 특히 심각하다. 진지한 관계를 전제로 한 서비스에서
전 사용자의 사적 대화가 인증 없이 읽히는 상태이며, 이는 개인정보보호법상
안전조치 의무 위반 소지가 있다.

### 증거

운영 배포본 발췌 (조회 결과 원문):

```
match /recEvents/{userId} {
  allow read, write: if true;
  match /events/{eventId} { allow read, write: if true; }
}

match /chat_rooms/{roomId} {
  allow read: if true;
  match /messages/{messageId} {
    allow read, create: if true;
    allow update: if true;
  }
}

match /reports/{reportId} {
  allow read: if true;
  allow update: if true;
  allow delete: if true;
}
```

같은 위치의 저장소본(`firestore.rules:638-655, 692-727, 833-848`)은
`isChatRoomParticipant()`, `isSelf()` 등으로 참여자·소유자 범위를 강제한다.
즉 **저장소가 운영보다 앞서 있고, 그 격차가 배포되지 않은 상태**다.

### 근본 원인

배포 게이트가 없다. `.github/workflows`가 없어 규칙 변경이 자동 배포되지
않고, 규칙 배포 여부를 확인하는 절차도 없다. `firestore.rules`를 고치는
작업과 `firebase deploy --only firestore:rules`를 실행하는 작업이 완전히
분리되어 있어서, 코드 리뷰를 통과한 강화가 운영에 반영됐는지 아무도 모른다.

`.firebaserc`에서 `staging`과 `default`가 모두 `seolleyeon-final`인 것도
같은 뿌리다. 안전하게 먼저 배포해볼 대상이 없으니 배포를 미루게 된다.

### 수정 방안

코드 수정으로 해결되지 않는다. **배포가 곧 수정**이며, 운영 반영이므로
사용자 승인 없이 수행하지 않았다.

절차는 13-deployment-and-rollback.md에 있다. 요약:

1. 저장소본 + 본 감사의 P0 수정이 반영된 `firestore.rules`를 배포한다.
2. 배포 전에 반드시 `rules_tests`를 통과시킨다 (현재 20/20).
3. 배포 직후 앱 주요 플로우(로그인, 학생 인증, 추천, 채팅, 무물)를 수동 확인한다.
4. 문제 시 이전 릴리스로 롤백한다 (Firebase 콘솔의 규칙 릴리스 히스토리).

**주의:** 이 배포는 개방된 규칙에 의존하던 동작을 끊을 수 있다. 특히
`recEvents` 쓰기와 `deviceTokens` 등록이 비인증으로 이뤄지고 있었다면
Firebase 세션이 없는 경로에서 실패한다. 배포 전 스테이징 프로젝트를
분리해서 검증하는 것이 옳지만, 현재 스테이징이 곧 운영이라 그럴 수 없다.
**별도 스테이징 프로젝트 생성이 배포 전 선행 조건이다.**

### 수정 (적용됨 — 2026-07-27)

사용자 승인 후 `seolleyeon-final`에 배포했다.

- **Firestore 규칙:** 저장소본 릴리스 확인. `chat_rooms`/`messages`가
  `isChatRoomParticipant` / `canUpdateChatMessage`로 잠김.
  `blocks`/`reports` 클라이언트 쓰기 거부. 운영 재조회로 검증.
- **Hosting:** `public/` 업로드·릴리스.
- **Functions:** `reportAndBlockUser`·`createFirebaseCustomTokenFromEmailLinkToken`
  등 다수 성공. 일부는 Cloud Run **CPU 쿼터 초과**로 실패
  (`createFirebaseCustomToken`, `syncContactBlocks`, 친구초대 등).
  기존 revision은 유지되며, 쿼터 회복 후 단건 재배포 필요.

### 함수 재배포 (2026-07-27 후속)

CPU 쿼터 회복 후 실패분을 **1개씩** 재배포했다. 핵심 인증·차단·팀 매칭
callable이 포함된다 (`createFirebaseCustomToken`, `syncContactBlocks`,
친구초대, `respondTeamMeetingRequest` 등).

### 남은 위험

이미 유출됐을 가능성이 있는 데이터의 범위를 코드만으로는 알 수 없다.
운영 감사 로그(Cloud Audit Logs, Firestore 사용량 급증 여부) 확인이 필요하며,
이는 운영 데이터 조회이므로 별도 승인이 필요하다.

실패한 Functions는 구버전이 그대로 서빙 중일 수 있다. 카카오 커스텀 토큰·
연락처 차단 동기화는 단건 재배포로 맞출 것.

---

## SEC-P0-01 — 비인증 임의 계정 탈취

**등급:** P0 (Critical)
**영역:** 인증 / Cloud Functions / Firestore Rules
**악용 가능성:** 높음. 인증 불필요, 특수 도구 불필요, 피해자 상호작용 불필요.

### 영향

공격자가 **아무 인증 없이** 학교 인증을 마친 임의 사용자의 Firebase custom token을 발급받아
해당 계정으로 완전히 로그인할 수 있다. 계정 탈취 후 채팅 내용 열람, 프로필 변경,
추천 데이터 접근, 상대방에게 메시지 전송이 모두 가능하다.

### 증거

1. `firestore.rules:12-27` — `emailLinkTokens/{token}` 문서를 **비인증 상태로 생성 가능**.
   타입 검사만 하고 `request.auth` 검사가 전혀 없다.

```12:21:firestore.rules
    match /emailLinkTokens/{token} {
      allow create: if request.resource.data.email is string &&
          request.resource.data.kakaoUserId is string &&
          isYonseiEmail(request.resource.data.email) &&
          request.resource.data.keys().hasAll([
            'email',
            'kakaoUserId',
            'createdAt',
            'expiresAt'
          ]);
```

   `email`과 `kakaoUserId` 모두 공격자가 임의 지정한다. 문서 ID(`token`)도 공격자가 정한다.

2. `firestore.rules:433-434` — `users` 컬렉션이 **비인증 전체 조회 가능**.
   공격자는 피해자의 문서 ID(= kakaoUserId)와 `studentEmail`, `isStudentVerified`를 그대로 읽는다.

```432:434:firestore.rules
    match /users/{kakaoUserId} {
      allow get: if true;
      allow list: if true;
```

3. `functions/src/index.ts:1498-1607` — `createFirebaseCustomTokenFromEmailLinkToken`은
   `request.auth`도 App Check도 요구하지 않는다. 검증 항목은 전부 공격자가 만족시킬 수 있다.

```1567:1598:functions/src/index.ts
    const userSnap = await db.collection("users").doc(tokenKakaoUserId).get();
    // ...
    if (!isStudentVerified || studentEmail != tokenEmail) {
      throw new HttpsError(
        "failed-precondition",
        "학생 인증이 아직 현재 브라우저와 연결되지 않았어요. 인증 메일 링크를 다시 열어주세요."
      );
    }
    // ...
    const customToken = await getAuth().createCustomToken(tokenKakaoUserId, {
      kakaoUserId: tokenKakaoUserId,
      studentEmail,
    });
```

   - `requestedKakaoUserId` / `requestedStudentEmail`은 **선택적**이므로 공격자는 생략한다
     (`index.ts:1546`, `index.ts:1553` — 값이 있을 때만 비교).
   - `expiresAt`은 토큰 문서에서 읽으므로 공격자가 미래 시각으로 넣는다 (`index.ts:1560`).
   - `isStudentVerified` / `studentEmail` 검사는 **피해자 문서**를 보므로 자동으로 통과한다.

### 재현 조건 (개념)

1. `users` 컬렉션을 비인증 조회하여 `isStudentVerified == true`인 문서 하나를 고른다.
   문서 ID를 `V`, `studentEmail`을 `E`라 한다.
2. 비인증 상태로 `emailLinkTokens/ATTACKER_CHOSEN_ID`를 생성한다.
   `{ email: E, kakaoUserId: V, createdAt: <now>, expiresAt: <now+1h> }`
3. `createFirebaseCustomTokenFromEmailLinkToken({ verificationToken: "ATTACKER_CHOSEN_ID" })` 호출.
4. 응답의 `customToken`으로 `signInWithCustomToken` → 피해자 `V`로 로그인 완료.

> 본 감사에서는 실제 운영 프로젝트를 대상으로 공격을 **실행하지 않았다.**
> 위 재현 절차는 코드 경로 분석 결과이며, 에뮬레이터 검증이 필요하다.

### 근본 원인

이메일 링크 인증의 신뢰 근거가 "Firebase가 실제로 이메일 소유를 검증했는가"가 아니라
"`emailLinkTokens`에 문서가 존재하는가"에 있다. 그런데 그 문서는 누구나 만들 수 있다.
토큰 문서는 **인증의 결과를 전달하는 통로**로 설계됐지만 **인증의 근거**로 사용되고 있다.

`functions/src/index.ts:1580`의 검사(`isStudentVerified && studentEmail == tokenEmail`)는
"이 요청자가 E의 소유자인가"를 전혀 확인하지 않는다. 피해자 문서의 상태만 확인한다.

### 수정 결과 — 완료 (`b1ab01b`)

아래 계획대로 세 겹 모두 적용했고, `rules_tests/firestore.auth.test.mjs`와
`functions/src/emailLinkTokenExchange.test.ts`로 검증했다.

- **Rules**: `emailLinkTokens` create를 `request.auth.uid == kakaoUserId`로 제한.
  `KakaoLoginFirestoreBootstrap`이 세션 부착 실패 시 예외를 던지므로
  이 화면 도달 시점에는 세션이 보장된다 (`kakao_login_firestore_bootstrap.dart:23-28`).
- **Rules**: 메일함 소유 증명용 `emailVerifiedUid`/`emailVerifiedAt` 필드를 신설하고,
  해당 메일함 소유자(`email_verified == true`)만 쓸 수 있게 했다.
- **Web**: `public/index.html`이 토큰을 삭제하는 대신 위 증명 필드를 기록한다.
- **Function**: `evaluateEmailLinkTokenExchange`를 순수 함수로 분리해
  증명 필드가 없으면 발급을 거부한다. 만료값이 없거나 파싱 불가하면
  "만료됨"으로 취급한다(기존에는 만료 검사를 건너뛰어 위조 문서가 영구 자격증명이 됐다).
  교환은 트랜잭션으로 1회용 처리한다.

원래 계획은 다음과 같았다.

1. **Rules**: `emailLinkTokens` create를 인증된 요청으로 제한하고,
   `kakaoUserId`가 호출자 UID와 일치하도록 강제한다.
   현재 클라이언트(`student_verification_screen.dart:327-337`)는 카카오 로그인 직후
   Firebase 세션이 있는지 확인이 필요하다. 세션이 없다면 이 쓰기를 callable로 옮겨야 한다.
2. **Function**: 토큰 문서 존재만으로 custom token을 발급하지 않는다.
   토큰 문서에 서버만 쓸 수 있는 `emailVerifiedAt` 표식을 요구하고,
   그 표식은 Firebase Auth의 실제 email-link 로그인 결과로만 기록한다.
   또한 토큰을 **일회용**으로 만들어 재사용을 차단한다(현재 `lastRecoveredAt`만 merge, 무제한 재사용).
3. **App Check**: 이 callable에 `enforceAppCheck`를 적용한다.

### 남은 위험

`emailLinkTokens` 컬렉션에 이미 공격자가 심어둔 문서가 존재할 가능성이 있다.
수정 배포 시 기존 문서의 감사·정리가 필요하다 (운영 데이터 변경이므로 사용자 승인 필요).

---

## SEC-P0-02 — 비인증 사용자 문서 생성 + 학교 인증 위조

**등급:** P0
**영역:** Firestore Rules

### 영향

공격자가 인증 없이 임의의 UID에 `users` 문서를 만들 수 있고,
그 문서에 `isStudentVerified: true`와 임의의 `studentEmail`을 직접 넣을 수 있다.
학교 인증 전체가 무력화되며, SEC-P0-01과 결합하면 공격자가
**자신이 통제하는 새 계정**을 학교 인증 상태로 만들어 앱에 진입할 수 있다.

### 증거

`firestore.rules:437-484` — create 규칙의 두 번째 분기에 `request.auth` 검사가 없다.

```456:483:firestore.rules
            (
              usersDocKakaoIdOk(request.resource.data, kakaoUserId) &&
              request.resource.data.keys().hasOnly([
                'kakaoUserId',
                'nickname',
                // ... 중략 ...
                'isStudentVerified',
                'studentEmail',
                'studentVerifiedAt',
                'verifiedAt',
                'preferenceVector'
              ])
            )
```

- 첫 분기(`firestore.rules:440-455`)는 `request.auth != null`을 요구하지만,
  두 번째 분기는 `usersDocKakaoIdOk` + 필드 화이트리스트만 검사한다.
- `usersDocKakaoIdOk`(`firestore.rules:33-35`)는 `data.kakaoUserId == null`이면 통과하므로
  문서 ID와의 일치조차 강제되지 않는다.
- 화이트리스트에 `isStudentVerified`, `studentEmail`이 포함되어 있다 (`firestore.rules:477-480`).

### 근본 원인

카카오 로그인은 Firebase 세션 없이 로컬 저장소의 `kakaoUserId`만으로 진행되는 구간이 있고
(`lib/services/user_service.dart` 부트스트랩), 그 구간의 쓰기를 허용하기 위해
비인증 create 분기가 열려 있는 것으로 보인다. 편의를 위해 인증 경계를 포기한 형태다.

### 수정 방안 (미적용)

`isStudentVerified`, `studentEmail`, `studentVerifiedAt`, `verifiedAt`을
**클라이언트 쓰기 금지 필드**로 전환하고 서버(callable/Admin SDK)에서만 기록한다.
비인증 create 분기는 제거하고, 카카오 부트스트랩은 이미 존재하는
`createFirebaseCustomToken`(`functions/src/index.ts:1463`)이 만드는
`users` shell 문서(`index.ts:1480`)로 대체한다 — 서버가 이미 이 일을 하고 있으므로
클라이언트 create 경로 자체가 불필요할 가능성이 높다. **확인 필요.**

---

## SEC-P0-03 — 연세 이메일 보유자의 타인 문서 탈취

**등급:** P0
**영역:** Firestore Rules

### 영향

`@yonsei.ac.kr` 이메일로 Firebase 세션을 가진 사용자가
**임의의 다른 사용자 문서**의 `studentEmail`을 자신의 이메일로 바꿀 수 있다.
그 결과 `isUserDocOwner`가 공격자에게 true를 반환하게 되어
피해자 프로필(온보딩 정보, 이상형, 프로필 이미지 모드 등)을 계속 수정할 수 있다.

### 증거

`firestore.rules:487-501` — update 규칙 첫 분기가 **대상 문서의 소유권을 확인하지 않는다.**

```489:501:firestore.rules
          (
            request.auth != null &&
            isYonseiEmail(request.auth.token.email) &&
            request.resource.data.studentEmail is string &&
            isYonseiEmail(request.resource.data.studentEmail) &&
            request.resource.data.isStudentVerified == true &&
            request.resource.data.diff(resource.data).changedKeys().hasOnly([
              'kakaoUserId',
              'isStudentVerified',
              'studentEmail',
              'studentVerifiedAt',
              'verifiedAt'
            ])
          )
```

- `request.auth.uid == kakaoUserId` 검사가 없다.
- `request.auth.token.email_verified` 검사도 없다 (`isUserDocOwner`에는 있으나 여기엔 없음).
- 변경 가능 필드에 `studentEmail`이 포함된다.

`isUserDocOwner`(`firestore.rules:49-62`)는 `resource.data.studentEmail == request.auth.token.email`이면
소유자로 인정하므로, 위 분기로 `studentEmail`을 덮어쓴 뒤 소유권을 획득할 수 있다.

### 수정 방안 (미적용)

첫 분기에 `request.auth.uid == kakaoUserId`를 추가하거나,
`studentEmail`/`isStudentVerified`를 서버 전용 필드로 전환한다(SEC-P0-02 수정과 통합 권장).

---

## SEC-P0-04 — users 컬렉션 전체 비인증 read/list

**등급:** P0 (개인정보)
**영역:** Firestore Rules / 개인정보

### 영향

인증 없이 전체 사용자 목록과 각 문서의 모든 필드를 덤프할 수 있다.
노출되는 항목에는 최소한 다음이 포함된다 (create/update 화이트리스트 기준):
`nickname`, `email`, `studentEmail`, `isStudentVerified`, `onboarding`(프로필 상세),
`idealType`, `profileImageUrl`, `preferenceVector`, `lastLoginAt`, `lastActivePlatform`.

대학 이메일과 프로필 정보의 대량 수집이 가능하며, SEC-P0-01의 선행 조건을 제공한다.

### 증거

```432:434:firestore.rules
    match /users/{kakaoUserId} {
      allow get: if true;
      allow list: if true;
```

`firestore.rules:906`의 주석("Reads may be allowed when Kakao login leaves request.auth null")으로 보아
카카오 로그인 시 `request.auth`가 null인 구간을 지원하려는 의도로 보인다.

### 수정 방안 (미적용)

1. 최소한 `allow list`를 제거하고 `allow get: if isSignedIn()`으로 좁힌다.
2. 공개가 필요한 프로필 필드는 별도의 `publicProfiles/{uid}` 문서로 분리하고
   `studentEmail`, `email`, `preferenceVector`는 절대 포함하지 않는다.
3. 카카오 로그인 구간의 비인증 읽기 요구는 `createFirebaseCustomToken` 호출을
   먼저 수행하도록 클라이언트 순서를 바꿔 제거한다.

**주의:** 이 변경은 앱의 다수 화면에 영향을 준다. characterization test 없이 적용하면 회귀 위험이 크다.

---

## SEC-P1-01 — 프로덕션 UI의 테스트 계정 로그인 우회

**등급:** P1
**영역:** Flutter 클라이언트 / 인증

### 영향

약관 화면에서 「테스트 계정으로 둘러보기」를 누르면 카카오 로그인과 학교 인증을 모두 건너뛰고
`fake_user_1` 신원으로 메인 화면에 진입한다. 실제 사용자 배포본에 포함되어 있다.

### 증거

```88:105:lib/features/onboarding/screens/terms_screen.dart
  Future<void> _enterWithTestAccount() async {
    final storage = StorageService();
    final userService = UserService();
    await storage.saveKakaoUserId("fake_user_1");
    // ...
    Navigator.of(
      context,
    ).pushNamedAndRemoveUntil(RouteNames.main, (route) => false);
  }
```

관련: `lib/features/chat/screens/premium_chat_list_screen.dart:202-217` —
채팅 목록에 `fake_user_1` 가짜 채팅방을 항상 주입한다.

### 수정 방안 (미적용)

프로덕션 빌드에서 완전히 제거한다. 개발 편의가 필요하면
`kDebugMode` 또는 `--dart-define` 플래그로 감싸고, release 빌드에 없음을 검증하는
정적 테스트를 추가한다 (`test/app_check_provider_policy_test.dart`와 동일한 패턴 사용 가능).

### 수정 (적용됨)

- `DevEntryPolicy.allowTestAccountEntry` — release에서 false (`kDebugMode`만).
- 약관 화면 버튼·핸들러 모두 게이트. `test/terms_screen_test_account_gate_test.dart`로 검증.
- 채팅 목록의 `fake_user_1` 가짜방 주입도 동일 정책으로 감쌈.

---

## SEC-P1-02 — 참여자가 상대방 메시지를 임의 수정 가능

**등급:** P1
**영역:** 채팅 / Firestore Rules

### 증거

```646:651:firestore.rules
      match /messages/{messageId} {
        allow read: if isExistingChatRoomParticipant(roomId);
        allow create: if isParticipantMessageAuthor(roomId);
        allow update: if isExistingChatRoomParticipant(roomId);
        allow delete: if false;
      }
```

create는 `senderId == request.auth.uid`를 강제하지만(`firestore.rules:340-344`),
**update는 작성자 확인이 없다.** 채팅방 참여자면 상대방 메시지의 본문과 `senderId`까지 바꿀 수 있다.

### 영향

신고 시 증거가 되는 메시지를 가해자가 사후 조작할 수 있다.
안전·신고 기능의 신뢰성을 직접 훼손한다.

### 수정 방안 (미적용)

update를 읽음 표시 등 필요한 필드로만 좁힌다. 예:
작성자 본인은 제한된 필드만, 상대방은 `readAt`/`readBy` 계열만 변경 가능하도록 분리.
**실제 앱이 어떤 필드를 update하는지 먼저 조사해야 한다** (미조사).

### 수정 (적용됨)

앱이 실제로 하는 쓰기를 조사한 뒤 규칙을 두 경로로 좁혔다.

- `onlyMessageReadReceiptUpdate` — `readBy`/`updatedAt`만.
- `onlyPromiseMessageLifecycleUpdate` — **기존** `promise_*` 메시지에 한해
  약속 필드만 변경. 일반 text를 promise로 위장해 우회하는 경로도 차단.
- 에뮬레이터 테스트: `rules_tests/firestore.chat.test.mjs`

---

## SEC-P1-03 — 참여자가 participantIds 임의 변경 가능

**등급:** P1
**영역:** 채팅 / Firestore Rules

### 증거

```641:643:firestore.rules
      allow update: if isChatRoomParticipant() &&
        isChatRoomParticipantAfter() &&
        chatRoomDoesNotPersistPrivateMedia(request.resource.data);
```

자신이 변경 전후 모두 참여자이기만 하면 `participantIds`에서 상대방을 제거하거나
제3자를 추가할 수 있다. 제3자 추가 시 그 사람이 과거 메시지 전체를 읽게 된다
(`messages` read가 현재 participantIds 기준이므로).

### 수정 방안 (미적용)

`participantIds`를 immutable로 강제한다:
`request.resource.data.participantIds == resource.data.participantIds`.

### 수정 (적용됨)

`chatRoomParticipantIdsUnchanged()`를 chat_rooms update 조건에 추가.
제3자 추가·상대 제거를 에뮬레이터에서 거부 검증.

---

## SEC-P1-04 — recEvents 클라이언트 무검증 쓰기

**등급:** P1
**영역:** 추천 시스템 / Firestore Rules

### 증거

```626:632:firestore.rules
    match /recEvents/{userId} {
      allow read, write: if isSelf(userId);

      match /events/{eventId} {
        allow read, write: if isSelf(userId);
      }
    }
```

스키마 검증, 이벤트 타입 화이트리스트, `serverTimestamp` 강제, 개수 제한이 모두 없다.
`allow write`에는 **delete와 update가 포함**되므로 과거 이벤트를 소급 조작할 수 있다.

### 영향

- 사용자가 자신의 학습 데이터를 임의로 조작해 추천 결과를 유도할 수 있다.
- `functions/src/index.ts`의 `onRecEventCreated`가 like 이벤트를 보고 mutual match를 검사하므로
  (서브에이전트 보고: `index.ts:4010-4032`), 위조된 like 이벤트로
  **매치를 임의 생성**할 수 있는지 추가 검증이 필요하다. **NEEDS-VERIFICATION.**

### 수정 방안 (미적용)

이벤트 타입 화이트리스트, `createdAt == request.time` 강제,
`update`/`delete` 금지, 필드 화이트리스트를 추가한다.

### 수정 (적용됨)

- `events`는 create만 허용. update/delete 거부 → 과거 nope를 like로
  바꿔 상호 매치를 만드는 경로를 차단.
- `type`/`eventType` 화이트리스트 + 상호 일치 강제.
- `userId`는 경로와 일치, `targetUserId`는 자기 자신 금지.
- 필드 `hasOnly`로 임의 키 주입 차단.
- 에뮬레이터 8건 + 운영 `firestore:rules` 배포 완료 (2026-07-27).

`onRecEventCreated`의 mutual-match는 상대방의 기존 like가 있어야만
성립하므로, 단방향 위조만으로는 매치가 생기지 않는다. 소급 변조는
위 규칙으로 막았다.

---

## SEC-P1-05 — 인증/부트스트랩 callable App Check 미적용

**등급:** P1
**영역:** Cloud Functions / abuse 방지
**상태:** 코드 수정 및 운영 Functions 배포 완료 (2026-07-27, `seolleyeon-final`, commit `809fa537`).

App Check(`enforceAppCheck`)가 avatar/chat/team 모듈에만 적용되어 있고,
`createFirebaseCustomToken`, `createFirebaseCustomTokenFromEmailLinkToken`,
`createFriendInvite`, `acceptFriendInvite`, `syncContactBlocks`, `saveUserPhoneHash`,
이벤트 팀 관련 callable 등이 미적용이었다.

### 수정

- `functions/src/appCheckPolicy.ts` — `withAppCheck()`로 `enforceAppCheck: true` 고정
- `functions/src/index.ts` — 인증·초대·이벤트 팀·연락처 해시 callable 10개에 적용
- `avatarApproval` / `chatRealPhoto` callables에도 `enforceAppCheck: true`
- Flutter web: `--dart-define=APP_CHECK_WEB_RECAPTCHA_SITE_KEY=...`로 reCAPTCHA v3 활성화
  (키 없으면 web App Check 스킵 → 해당 callable은 서버에서 거부)
- 회귀: `functions/src/appCheckPolicy.test.ts`, `test/app_check_provider_policy_test.dart`

웹/로컬 스테이징은 [staging_app_check_setup.md](../../staging_app_check_setup.md) 참고.

---

## SEC-P1-06 — 추천 배치가 blocks / contactBlocked 미제외

**등급:** P1
**영역:** 추천 시스템

Python 배치 파이프라인은 `blocks/{uid}/targets` 컬렉션을 전혀 조회하지 않는다
(서브에이전트 확인: 저장소 전체에서 Python 측 `blocks` 참조 없음).
차단 사용자 제외는 **Flutter 클라이언트 표시 시점에만** 수행된다
(`lib/services/ai_recommendation_service.dart:152`).

`contactBlockedHashes`(연락처 차단)는 **클라이언트·서버 어디에서도 추천에서 제외되지 않는다**
(저장소 전체 `contactBlocked` grep 0건 — 추천 경로 기준).

또한 Cloud Run Job 인자에 `--apply_policy_filters`가 전달되지 않아
`profileIndex` 기반 정책 필터가 비활성 상태다 (`infra/deploy.sh:151-165`).

### 영향

차단·연락처 차단 정책이 추천 파이프라인에 일관되게 반영되지 않는다.
클라이언트 필터를 우회하거나 클라이언트가 구버전이면 차단한 상대가 다시 노출된다.
설레연의 핵심 가치(안전·신뢰)에 직접 배치된다.

---

## SEC-P1-07 — 차단·탈퇴 사용자 FCM 미필터

**등급:** P1
**영역:** 알림

`sendPushToUsers`(`functions/src/index.ts:1043-1113`)는 `deviceTokens` 존재 여부만 확인하고
차단 관계·탈퇴·정지 상태를 확인하지 않는다.
차단한 상대의 활동으로 인한 푸시가 계속 도달할 수 있다.

---

## SEC-P1-08 — account_deletion 시 orphan 데이터 잔존

**등급:** P1
**영역:** 개인정보

`cleanupAvatarMedia(reason: "account_deletion")`은 아바타 미디어, `users/{uid}`,
Firebase Auth 계정을 삭제하지만 다음은 남긴다 (서브에이전트 확인, `functions/src/avatarCleanup.ts`):
`userPrivate/{uid}`(전화번호 해시), `deviceTokens`, `notifications`,
`matches`, `chat_rooms`, `interactions`, `asks`, `friendships`, `blocks`,
`phoneHashIndex`, `contactBlockedHashIndex`, `recEvents`, `bamboo_posts`,
`friendInvites.metadata.inviterEmail`, 이벤트 팀 문서 전반.

전화번호 해시와 이메일이 남는 것은 개인정보 파기 의무와 충돌할 수 있다. **법무 검토 필요.**

---

## SEC-P2-01 — bamboo_posts likeCount 임의 조작

```716:725:firestore.rules
        (
          isSignedIn() &&
          request.resource.data.authorId == resource.data.authorId &&
          // ...
          request.resource.data.diff(resource.data).affectedKeys().hasOnly([
            'likeCount', 'commentCount', 'score7d', 'updatedAt'
          ])
        );
```

증분 검증(`newValue == oldValue + 1`)이 없어 아무 로그인 사용자가
임의 게시물의 `likeCount`/`score7d`를 원하는 값으로 설정할 수 있다.
커뮤니티 랭킹(`score7d`) 조작이 가능하다.

---

## SEC-P2-02 — 상호 like 시 match/chat_room 중복 생성

`functions/src/index.ts:2692-2762` — 기존 match 조회 후 `batch.commit()`.
트랜잭션이 아니므로 두 사용자가 동시에 like하면 match와 chat_room이 중복 생성될 수 있다.
`recEvents` 경로(`index.ts:4010-4032`)도 동일하다.

---

## SEC-P3-01 — place_catalog 규칙 중복 정의

`firestore.rules:662-670`과 `firestore.rules:676-684`에 동일한
`place_catalog_meta` / `place_catalog_items` 블록이 두 번 정의되어 있다.
동작에는 영향이 없으나 (동일 규칙) 규칙 파일의 신뢰성을 떨어뜨리는 편집 사고 흔적이다.

---

## 검증되지 않은 영역 (NEEDS-VERIFICATION)

- 위조 `recEvents` like로 실제 match를 생성할 수 있는지 (`onRecEventCreated` 미정독)
- 채팅 앱 코드가 `messages` update로 어떤 필드를 쓰는지 (수정 범위 설계에 필요)
- `emailLinkTokens`에 이미 악성 문서가 존재하는지 (운영 데이터 조회 필요)
- App Check 강제(enforcement)가 Firebase 콘솔에서 실제로 켜져 있는지
- Storage 규칙이 모든 클라이언트 쓰기를 막고 있는데 앱의 업로드 경로가 전부 callable을 쓰는지
  (`storage.rules:65-67` 기본 deny — 클라이언트 직접 업로드가 남아 있으면 기능 장애)
