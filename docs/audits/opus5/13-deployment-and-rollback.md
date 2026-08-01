# 13 — 배포 및 롤백 절차 (Opus 5 감사)

작성 시각: 2026-07-27

**본 감사에서 배포는 수행하지 않았다.** 아래는 사용자가 승인·실행해야 하는 절차다.

---

## 0. 배포 전 반드시 알아야 할 것

### 0.1 지금 운영은 저장소보다 취약하다

`seolleyeon-final`에 배포된 Firestore 규칙은 저장소 `firestore.rules`보다
훨씬 개방적이다 (SEC-P0-05). 채팅·신고·차단·무물·추천 로그가 비인증
전체 읽기/쓰기 상태다.

따라서 **이 배포는 "새 기능 반영"이 아니라 "현재 진행 중인 노출을 멈추는 것"** 이다.
지연시킬수록 노출 시간이 늘어난다.

### 0.2 그런데 곧바로 배포하면 앱이 깨질 수 있다

배포본이 열려 있었다는 것은, 앱의 일부 경로가 **Firebase 세션 없이도 동작하고
있었을 가능성**을 뜻한다. 규칙을 조이면 그 경로가 즉시 실패한다. 특히 위험한 곳:

| 경로 | 배포 후 실패 가능성 | 확인 방법 |
|------|--------------------|-----------|
| `recEvents` 쓰기 (`lib/services/rec_event_service.dart`) | 높음. 배포본은 비인증 쓰기 허용 | 세션 없이 impression/like가 기록되는지 |
| `deviceTokens` 등록 (`lib/services/push_notification_service.dart`) | 높음. 배포본은 비인증 쓰기 허용 | 로그인 직후 FCM 토큰 등록 시점에 세션이 있는지 |
| `chat_rooms` 조회 | 중간. 배포본은 `read: if true` | 채팅 목록·메시지 로딩 |
| `blocks` 쓰기 | 중간 | 차단/차단해제 |
| 커뮤니티(`bamboo_posts`) 작성 | 중간 | 글쓰기·댓글·좋아요 |

**이 확인 없이 배포하면 전 사용자 기능 장애가 날 수 있다.**

### 0.3 선행 조건: 스테이징 프로젝트 분리

`.firebaserc`의 `default`와 `staging`이 둘 다 `seolleyeon-final`이다.
즉 안전하게 먼저 배포해볼 곳이 없다.

배포 전에 별도 Firebase 프로젝트(`seolleyeon-staging` 등)를 만들고
`.firebaserc`의 `staging` 별칭을 그쪽으로 돌리는 것을 **강력히 권장**한다.
이것 없이 진행하려면 트래픽이 가장 적은 시간대에 배포하고 즉시 롤백할
준비를 해야 한다.

---

## 1. 배포 순서

순서를 지켜야 한다. 규칙을 먼저 조이면 아직 배포되지 않은 함수가
필요로 하는 동작이 막힐 수 있다.

### 1단계 — 사전 검증 (운영 무접촉)

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio1\jbr"
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"

flutter analyze
flutter test
npm --prefix functions run lint
npm --prefix functions test
firebase emulators:exec --only firestore --project seolleyeon-rules-test `
  "npm --prefix rules_tests test"
```

전부 통과해야 한다. 하나라도 실패하면 중단한다.

### 2단계 — Cloud Functions 배포

규칙보다 **먼저** 배포한다. 새 규칙은 `emailVerifiedUid` 마커를 요구하는데,
그 마커를 이해하는 함수가 먼저 떠 있어야 인증 플로우가 이어진다.

```powershell
firebase deploy --only functions --project seolleyeon-final
```

배포 후 확인:
- `createFirebaseCustomTokenFromEmailLinkToken`이 정상 기동하는지
- 로그에 `email link token exchange rejected` 가 폭증하지 않는지
  (폭증한다면 웹 페이지가 아직 옛 버전이라는 뜻 → 3단계를 먼저 해야 함)

### 3단계 — Hosting(인증 웹 페이지) 배포

```powershell
firebase deploy --only hosting --project seolleyeon-final
```

`public/index.html`이 토큰 삭제 대신 `emailVerifiedUid`/`emailVerifiedAt`를
기록하도록 바뀌었다. 이게 배포되지 않으면 새 함수가 모든 교환을 거부한다.

**2단계와 3단계는 가급적 연속으로 수행한다.** 사이 구간에서 이메일 링크
인증을 진행 중인 사용자는 세션 복구에 실패하고 카카오 브리지로 폴백한다
(`auth_service.dart:512`). 로그인 자체가 막히지는 않지만 재시도가 필요하다.

### 4단계 — Firestore 인덱스 배포

규칙보다 먼저. 인덱스가 없으면 새 쿼리가 실패한다.

```powershell
firebase deploy --only firestore:indexes --project seolleyeon-final
```

### 5단계 — Firestore 규칙 배포 (가장 위험)

```powershell
firebase deploy --only firestore:rules --project seolleyeon-final
```

배포 직후 **10분 내에** 다음을 수동 확인한다. 하나라도 실패하면 즉시 롤백.

- [ ] 신규 카카오 로그인
- [ ] 기존 사용자 앱 재실행 시 세션 복구
- [ ] 연세 이메일 인증 링크 발송 → 웹에서 인증 → 앱 복귀
- [ ] 온보딩 프로필 저장
- [ ] 1:1 추천 카드 로딩
- [ ] 추천 카드 like/nope (→ `recEvents` 쓰기)
- [ ] 채팅방 목록 및 메시지 송수신
- [ ] 무물 발송/수신
- [ ] 차단 및 차단 해제
- [ ] 신고
- [ ] 푸시 알림 수신 (→ `deviceTokens` 등록)
- [ ] 커뮤니티 글 작성

### 6단계 — Storage 규칙 배포

저장소본은 배포본에 축제(`seolleyeon-festival-*`) 버킷 허용이 추가된
정도라 위험이 낮다. 다만 배포본의 `ai_profiles`는 `read: if true`인데
저장소본은 `isApprovedAvatarBucket()`으로 제한한다. AI 더미 프로필
이미지가 다른 버킷에서 서빙되고 있었다면 깨진다.

```powershell
firebase deploy --only storage --project seolleyeon-final
```

---

## 2. 롤백

| 롤백 대상 | 관련 커밋 | 롤백 방법 | 데이터 영향 | 추가 조치 |
|-----------|-----------|-----------|-------------|-----------|
| Firestore 규칙 | `b1ab01b` | Firebase 콘솔 → Firestore → 규칙 → 릴리스 히스토리에서 직전 버전 게시. CLI에는 규칙 롤백 명령이 없다 | 없음 | 롤백하면 SEC-P0-01~05가 전부 다시 열린다. **임시 조치로만 쓰고 즉시 재수정한다** |
| Cloud Functions | `b1ab01b` | `git revert b1ab01b -- functions/src/index.ts` 후 재배포. 또는 콘솔에서 이전 버전 트래픽 전환 | 없음. `exchangedAt`/`emailVerifiedUid` 필드는 남지만 구버전이 무시한다 | 구버전은 위조 토큰을 다시 수락한다 |
| Hosting | `b1ab01b` | `firebase hosting:rollback --project seolleyeon-final` | 없음 | Functions와 짝을 맞춰 롤백해야 한다 |
| Storage 규칙 | 미변경 | 콘솔 릴리스 히스토리 | 없음 | |
| 감사 브랜치 전체 | `eaa910c`, `b1ab01b` | `git checkout semisemifinal` | 없음 | `semisemifinal` 브랜치는 `9eb76d3` 그대로다 |

### 롤백 판단 기준

즉시 롤백:
- 로그인 성공률이 눈에 띄게 떨어짐
- `permission-denied` 오류가 급증
- 채팅 송수신 불가

관찰 후 판단:
- 이메일 링크 인증 실패 일부 (배포 순서 불일치일 가능성. 3단계 완료 여부 먼저 확인)
- `recEvents` 기록 누락 (기능 장애는 아님. 추천 품질에만 영향)

---

## 3. 배포하지 않은 것 / 승인이 필요한 것

| 항목 | 이유 |
|------|------|
| 운영 데이터 정리 | `emailLinkTokens`에 공격자가 이미 심어둔 문서가 있을 수 있다. 조회·삭제는 운영 데이터 변경이라 승인 필요 |
| `emailLinkTokens` TTL 정책 | 토큰이 더 이상 자동 삭제되지 않으므로 `expiresAt` 기준 Firestore TTL 정책 설정이 필요하다. GCP 콘솔 작업 |
| Secret 교체 | 미수행. 운영 노출 범위가 확정되기 전까지는 판단 불가 |
| App Check 강제 활성화 | 콘솔 설정 변경. 강제 시 미대응 클라이언트가 즉시 차단되므로 별도 계획 필요 |
| 유출 범위 조사 | Cloud Audit Logs 조회 필요. 운영 데이터 접근이라 승인 필요 |
