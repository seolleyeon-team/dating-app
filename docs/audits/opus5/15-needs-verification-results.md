> **HISTORICAL / RETIRED — NOT A CURRENT DEPLOYMENT AUTHORITY.** The current Azure-only, source-set architecture is defined in [avatar-production/CURRENT_ARCHITECTURE.md](../avatar-production/CURRENT_ARCHITECTURE.md).
>

# 15 — NEEDS-VERIFICATION 조사 결과

작성 시각: 2026-07-29  
조사 대상: [04-security-findings.md](04-security-findings.md) §「검증되지 않은 영역」5건  
방법: 저장소 정적 분석 + `seolleyeon-final` 운영 READ-ONLY 조회 (Firestore REST, Firebase App Check API, Firebase Rules API)  
**커밋·배포 없음**

---

## 요약 표

| # | 항목 | 판정 | 한 줄 결론 |
|---|------|------|-----------|
| 1 | 위조 `recEvents` like → match/chat 생성 | **PARTIALLY VERIFIED** | 상호 like가 이미 있으면 `matches` 문서는 생성되나 **채팅방은 생성되지 않음**. 타인 `recEvents` 위조·소급 변조는 현행 규칙·배포본에서 차단. |
| 2 | Flutter 채팅 앱 `messages` update 필드 | **VERIFIED** | `readBy`/`updatedAt` 읽음 처리 + `promise_*` 약속 카드 생애주기 필드만 갱신. |
| 3 | 운영 `emailLinkTokens` 악성 문서 존재 | **RESOLVED** | 레거시 28건 전부 만료·미검증 → **2026-07-29 일괄 삭제 완료** (REMAINING=0). |
| 4 | App Check 콘솔 enforcement (callable/Storage) | **PARTIALLY → Storage RESOLVED** | **Storage = ENFORCED** (2026-07-29). Firestore/Auth는 여전히 UNENFORCED. Callable은 코드 `enforceAppCheck`. |
| 5 | Storage rules deny vs Flutter 직접 업로드 | **VERIFIED** | `lib/`에 `putFile`/`putData`/직접 업로드 없음. 아바타는 callable 경유. Storage는 read-only(`getDownloadURL`)만. |

---

## 1. 위조 `recEvents` like → `onRecEventCreated` / `checkAndCreateRecMatch` 매치 생성

**판정: PARTIALLY VERIFIED**

### 트리거 동작

`onRecEventCreated`는 Admin SDK 트리거로 **클라이언트 auth를 재검증하지 않는다**. 문서 필드만 읽는다.

```2694:2721:functions/src/index.ts
export const onRecEventCreated = onDocumentCreated(
  "recEvents/{userId}/events/{eventId}",
  async (event) => {
    // ...
    const userId = asString(data.userId ?? event.params.userId ?? "");
    const targetUserId = asString(data.targetUserId ?? "");
    const eventType = asString(data.eventType ?? "");
    // ...
    if (eventType === "like" || eventType === "swipe_right") {
      await checkAndCreateRecMatch(userId, targetUserId, eventType);
    }
  }
);
```

`checkAndCreateRecMatch`는 **상대방의 기존 like/swipe_right**를 `collectionGroup("events")`로 조회한 뒤, 있을 때만 `ensureMutualMatch`를 호출한다.

```4063:4102:functions/src/index.ts
async function checkAndCreateRecMatch(
  userA: string,
  userB: string,
  matchType: string
): Promise<string | null> {
  const reverseQuery = await db
    .collectionGroup("events")
    .where("userId", "==", userB)
    .where("targetUserId", "==", userA)
    .where("eventType", "in", ["like", "swipe_right"])
    .limit(1)
    .get();

  if (reverseQuery.empty) {
    return null;
  }

  const { matchId, created } = await ensureMutualMatch(db, {
    userA,
    userB,
    matchType,
  });
  // ...
}
```

**채팅방 생성 여부:** `checkAndCreateRecMatch`는 `chatRoom` 인자를 넘기지 않는다. `ensureMutualMatch`는 `chatRoom`이 없으면 `matches/{matchId}`만 만들고 **chat_rooms/messages는 만들지 않는다**.

```32:39:functions/src/mutualMatchCreation.ts
export async function ensureMutualMatch(
  db: Firestore,
  params: EnsureMutualMatchParams
): Promise<EnsureMutualMatchResult> {
  const matchId = buildDeterministicMatchId(params.userA, params.userB);
  const roomId = params.chatRoom
    ? buildDirectRoomId(params.userA, params.userB)
    : null;
```

비교: `onInteractionCreated`는 `chatRoom`을 포함해 **매치 + 채팅방 + 시스템 메시지**를 만든다 (`functions/src/index.ts:2809-2826`).

### 누가 `recEvents`를 쓸 수 있는가 (현행 규칙 + 운영 배포본)

저장소·**운영 배포 Firestore rules**(ruleset `a4a65236`, 2026-07-29 배포) 모두 동일:

```843:852:firestore.rules
    match /recEvents/{userId} {
      allow read: if isSelf(userId);
      allow create, update: if isSelf(userId);
      allow delete: if false;

      match /events/{eventId} {
        allow read: if isSelf(userId);
        allow create: if isSelf(userId) && isValidRecEventCreate(userId);
        allow update, delete: if false;
      }
    }
```

필수 필드·화이트리스트 (`firestore.rules:813-840`):

- `userId` == 경로 `{userId}`, `type`/`eventType` 화이트리스트 일치
- `targetUserId` 필수, 자기 자신 금지
- 허용 키 `hasOnly` — 임의 필드 주입 불가
- **update/delete 금지** — 과거 nope → like 소급 변조 불가

에뮬레이터 테스트도 상호 확인 (`rules_tests/firestore.recevents.test.mjs:57-65`, `120-126`).

| 공격 시나리오 | 현행 규칙 하에서 |
|--------------|-----------------|
| A가 자신의 like 이벤트 append (UI 우회/API) | **가능** (설계상 클라이언트 append 허용) |
| A가 B의 `recEvents/{B}`에 like 위조 | **불가** (`isSelf(B)` 실패) |
| A가 자신의 과거 nope를 like로 수정 | **불가** (update 거부) |
| A만 like 위조 → 단독 매치 생성 | **불가** (역방향 like 없음) |
| A·B 상호 like 존재 → A가 like append | **`matches` 문서 생성 가능** |
| recEvents 경로로 채팅방 생성 | **불가** (`chatRoom` 미전달) |

### 권장 조치

- **현행:** recEvents 기반 매치는 `interactions` 경로와 달리 채팅방이 없어 UX 불일치 가능. 의도된 동작인지 제품 확인.
- **강화(선택):** mutual match를 `onRecEventCreated`가 아닌 `interactions` 단일 경로로 통합하거나, recEvents 매치 시에도 `chatRoom` 생성 로직을 `onInteractionCreated`와 동일하게 맞출지 검토.
- recEvents는 학습 로그이므로, 매치 Side-effect를 Functions에서 `interactions` 존재 여부로 한 번 더 검증하는 것도 고려.

---

## 2. Flutter 채팅 앱 `messages` update 필드

**판정: VERIFIED**

### 클라이언트가 갱신하는 필드

| 파일 | 메서드 | 갱신 필드 |
|------|--------|----------|
| `lib/features/chat/services/chat_service.dart:362-386` | `markMessagesAsRead` | `readBy`, `updatedAt` |
| `lib/services/chat_service.dart:164-188` | `markMessagesAsRead` | `readBy` only |
| `lib/features/chat/services/chat_service.dart:603-616` | `updatePromise` | `senderId`, `type`, `text`, `dateTime`, `place`, `placeCategory`, `placeId`, `placeAddress`, `placeLat`, `placeLng`, `status`, `readBy`, `updatedAt`, `isEdited`, `editedAt` |
| `lib/features/chat/services/chat_service.dart:657-662` | `acceptPromise` | `type`, `text`, `status`, `updatedAt` |
| `lib/features/chat/services/chat_service.dart:724-727` | `rejectPromise` | `status`, `updatedAt` |
| `lib/features/chat/services/chat_service.dart:769-772` | `cancelPromise` | `status`, `updatedAt` |

약속 진행/완료 시 **새 메시지 create** (`promise_in_progress`, `promise_completed` 등)는 update가 아니라 `tx.set` (`lib/features/chat/services/chat_service.dart:250-262`, `288-300`).

### Firestore rules와의 정합성

```463:504:firestore.rules
    function onlyMessageReadReceiptUpdate() {
      return request.resource.data.diff(resource.data).affectedKeys()
          .hasOnly(['readBy', 'updatedAt']);
    }
    function onlyPromiseMessageLifecycleUpdate() {
      return isExistingPromiseMessage() &&
          request.resource.data.diff(resource.data).affectedKeys().hasOnly([
            'type', 'text', 'dateTime', 'place', 'placeCategory',
            'placeId', 'placeAddress', 'placeLat', 'placeLng',
            'placeThumbnailUrl', 'status', 'readBy', 'updatedAt',
            'isEdited', 'editedAt'
          ]) &&
          request.resource.data.senderId == resource.data.senderId &&
          request.resource.data.type.matches('promise_.*');
    }
    function canUpdateChatMessage(roomId) {
      return isExistingChatRoomParticipant(roomId) &&
          (onlyMessageReadReceiptUpdate() || onlyPromiseMessageLifecycleUpdate());
    }
```

클라이언트 update 범위와 rules whitelist가 **일치**한다.

### 권장 조치

- 없음 (설계·구현·규칙 정합 확인됨).
- `lib/services/chat_service.dart`(레거시)는 `updatedAt` 없이 `readBy`만 갱신 — rules상 허용 subset.

---

## 3. 운영 `emailLinkTokens` 악성 문서 존재 여부

**판정: PARTIALLY VERIFIED**

### 조회 방법

- 프로젝트: `seolleyeon-final`
- Firestore REST `runQuery` (READ-ONLY, ADC + `x-goog-user-project`)
- Firebase MCP `firestore_query_collection`은 401로 실패 → REST로 대체

### 결과 (2026-07-29 조회)

| 지표 | 값 |
|------|-----|
| 컬렉션 전체 문서 수 | **28** |
| `emailVerifiedUid` 보유 | **0** |
| `expiresAt > 2026-07-29` (미만료) | **0** |
| 샘플 20건 doc ID 형식 | 전부 UUID v4 |
| 샘플 필드 키 | `email`, `kakaoUserId`, `createdAt`, `expiresAt` (+ 일부 `lastRecoveredAt`, `lastRecoveredKakaoUserId`) |

### 악용 가능성 판단

현행 교환 함수는 `emailVerifiedUid`/`emailVerifiedAt` 없으면 거부한다.

```1336:1341:functions/src/index.ts
  if (
    !asNonEmptyString(tokenData.emailVerifiedUid) ||
    !isTimestamp(tokenData.emailVerifiedAt)
  ) {
    return { ok: false, reason: "mailbox-unproven" };
  }
```

- **28건 모두 만료 + mailbox-unproven → 현 시점 악용 불가**
- SEC-P0-01 이전(비인증 create 가능)에 공격자가 심은 문서인지, 정상 앱이 만든 레거시인지 **Firestore 데이터만으로는 구분 불가** (전부 UUID, 연세 이메일, 정상 필드 형태)
- `lastRecovered*` 필드는 복구 플로우 흔적로 보이며 공격 지표로 단정 불가

### 권장 조치

- **운영:** 만료된 28건 일괄 삭제(정리) — 기능 영향 없음, orphan 감소
- **모니터링:** `emailVerifiedUid` 없이 create된 신규 토큰 알림 (규칙상 create는 auth 필요하나, anomaly detection용)
- **선택:** `expiresAt` 지난 문서 자동 삭제 Cloud Scheduler/Function

### 운영 조치 (2026-07-29)

- 조건: `expiresAt < now` AND `emailVerifiedUid` 없음
- **DELETED=28 / FAILED=0 / REMAINING=0** (`seolleyeon-final`)
- Firestore REST delete (ADC). 활성·검증 완료 토큰은 0건이라 스킵 없음.

---

## 4. App Check enforcement (callable / Storage)

**판정: PARTIALLY VERIFIED**

### Firebase App Check API (`firebaseappcheck.googleapis.com`)

프로젝트 `810450765203` (seolleyeon-final), 2026-07-27 기준:

| 서비스 | enforcementMode |
|--------|-----------------|
| `firebasestorage.googleapis.com` | **ENFORCED** (2026-07-29 전환) |
| `firestore.googleapis.com` | **UNENFORCED** |
| `identitytoolkit.googleapis.com` (Auth) | **UNENFORCED** |

`cloudfunctions.googleapis.com`은 App Check 서비스 목록에 **없음** (Callable은 콘솔 product toggle 대상이 아님).

### Callable (코드 수준)

`functions/src/appCheckPolicy.ts` — 모든 public callable에 `enforceAppCheck: true`.

적용 예:

- `createFirebaseCustomToken` — `index.ts:1563`
- `createFirebaseCustomTokenFromEmailLinkToken` — `index.ts:1598-1599`
- `uploadAvatarSourcePhoto` — `avatarMedia.ts:38`
- `getChatRealProfilePhoto` — `chatRealPhoto.ts:209`
- 기타 auth/bootstrap/team/avatar callables

**콘솔에서 Callable enforcement ON/OFF를 API로 확인하는 방법은 제공되지 않음.** 배포된 Functions 바이너리의 `enforceAppCheck` 플래그는 코드·배포 이력(`809fa537`)으로만 확인.

### 해석

| 계층 | Storage | Callable |
|------|---------|----------|
| Firebase 콘솔 App Check enforcement | **ON (ENFORCED)** (2026-07-29) | N/A (코드 플래그) |
| 코드/규칙 | `storage.rules` 전 경로 `write: if false` | `enforceAppCheck: true` |

Storage는 **rules deny + App Check ENFORCED** 이중 방어. 유효한 App Check 토큰 없는 클라이언트 요청은 Storage API에서 거부된다.

### 권장 조치

- **Storage:** ENFORCED 적용 완료 (2026-07-29).
- **Firestore/Auth:** 제품 요구에 따라 enforcement 검토 (현재 UNENFORCED).
- **Callable:** 코드 `enforceAppCheck` 유지 + Flutter/web App Check 초기화 필수. staging 문서 `docs/staging_app_check_setup.md` 참고.
- App Check 403 blocker(avatar QA 등)는 enforcement 우회가 아닌 **정상 debug token / 등록 device**로 해결.

---

## 5. Storage rules deny vs Flutter 직접 업로드 경로

**판정: VERIFIED**

### `storage.rules`

모든 사용자 경로 `allow read, write: if false`. 유일한 공개 read는 `ai_profiles/**`, `users/{uid}/avatar/**`(approved bucket).

```17:63:storage.rules
    match /users/{userId}/onboarding/photos/{fileName} {
      allow read, write: if false;
    }
    // ... users/, source/, chat-profile/, jobs/, private_source_photos/, chat_profile_photos/ 모두 deny
    match /{allPaths=**} {
      allow read, write: if false;
    }
```

운영 Storage rules 배포: ruleset `a2a15762`, 2026-07-27.

### `lib/` Storage 사용처

| 경로 | 동작 |
|------|------|
| `lib/features/matching/screens/ai_preference_screen.dart:210` | `getDownloadURL()` **read only** (`ai_profiles/`) |
| `lib/services/avatar_source_photo_service.dart:114` | `httpsCallable('uploadAvatarSourcePhoto')` — **직접 Storage 쓰기 없음** |
| `lib/data/repositories/user_repository.dart:22` | `uploadProfilePhoto` **abstract 선언만**, 구현체 없음 |

`lib/` 전체 grep: `putFile`, `putData`, `putString`, `UploadTask`, `uploadTask` **0건**.

채팅 실사진: `getChatRealProfilePhoto` callable (`lib/services/chat_profile_photo_service.dart:98`).

### 권장 조치

- 없음. 클라이언트 직접 업로드 경로 없음, rules와 일치.
- 신규 업로드 기능 추가 시 callable + Admin SDK 패턴 유지.

---

## 조사 한계

1. Firebase MCP Firestore/Rules 도구는 401 — gcloud ADC + REST로 대체.
2. `emailLinkTokens` 공격자 vs 정상 레거시 구분은 **감사 로그 없이 불가**.
3. Callable `enforceAppCheck` **런타임** 검증(실제 403 응답)은 본 조사에서 수행하지 않음.
4. recEvents → match 생성은 **상호 like 선행 조건** 하에서만 재현 가능; 단독 위조 시나리오는 코드·규칙으로 배제 확인.

---

## Follow-up actions taken (2026-07-29)

| 항목 | 조치 |
|------|------|
| 1 recEvents chat gap | `checkAndCreateRecMatch`가 `ensureMutualMatch(..., chatRoom)` 전달 |
| 3 expired tokens | **일괄 삭제 완료** — DELETED=28, REMAINING=0 (2026-07-29) |
| 4 App Check console | **Storage ENFORCED 완료** (2026-07-29). Firestore/Auth는 UNENFORCED 유지 |
| P1-08 phase 2 | `accountDeletionSocialCleanup` — matches/chat/interactions 등 소셜 residual |

---

## 참고 증거 파일

- `functions/src/index.ts` — `onRecEventCreated`, `checkAndCreateRecMatch`, `evaluateEmailLinkTokenExchange`
- `functions/src/mutualMatchCreation.ts` — `ensureMutualMatch`
- `firestore.rules` — `recEvents`, `canUpdateChatMessage`, `emailLinkTokens`
- `storage.rules` — 전면 client write deny
- `lib/features/chat/services/chat_service.dart` — message/promise updates
- `rules_tests/firestore.recevents.test.mjs` — recEvents rules 회귀
- 운영 조회: Firestore REST, `firebaseappcheck.googleapis.com/v1/.../services`, `firebaserules.googleapis.com/v1/.../releases`
