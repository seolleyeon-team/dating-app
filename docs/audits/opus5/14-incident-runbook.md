# 보안 사고 대응 Runbook — 임의 계정 탈취 (P0-1)

상태: `COMPROMISE_NOT_CONFIRMED` / `EXPOSURE_POSSIBLE`

침해 증거가 없다는 것은 침해가 없었다는 뜻이 아니다. 이 세션에서는 운영 로그와
운영 데이터에 접근하지 않았고, 접근해서도 안 됐다. 아래는 **실행하지 않은**
절차이며, 운영 권한을 가진 사람이 순서대로 수행해야 한다.

## 0. 전제

취약점 요약:

```
익명 users list  →  피해자 kakaoUserId + studentEmail
                 →  emailLinkTokens/{임의ID} 익명 생성
                 →  createFirebaseCustomTokenFromEmailLinkToken(verificationToken 만)
                 →  피해자 UID custom token
```

배포 여부는 저장소만으로 확정할 수 없다. 다만 `.firebaserc` 의 유일한 프로젝트가
운영(`seolleyeon`)이고 `functions/package.json` 에 `deploy` 스크립트가 있으므로
**배포되었다고 가정하고 진행한다.**

## 1. 노출 기간 확정

```
Google Cloud Console → Cloud Functions → createFirebaseCustomTokenFromEmailLinkToken
  → 버전 이력에서 최초 배포 시각 확인
```

없으면 Cloud Build / Cloud Logging 의 `google.cloud.functions.v2.FunctionService.CreateFunction`
감사 로그를 본다. 그 시각부터 이번 수정 배포 시각까지가 노출 구간이다.

Firestore 규칙 쪽도 같이 본다.

```
Firebase Console → Firestore → 규칙 → 버전 이력
  → users 의 `allow list: if true` 가 처음 들어간 시각
```

두 구간의 교집합이 실제 공격 가능 구간이다.

## 2. 공격 시그니처 검색 (가장 중요)

정상 클라이언트는 **항상 3개 필드**를 보낸다
(`auth_service.dart` 의 제거 전 코드 기준):

```
verificationToken
studentEmail
kakaoUserId
```

공격은 `verificationToken` **하나만** 보내야 성립한다. 두 조건부 검사
(`index.ts:1246`, `1253`)를 건너뛰어야 하기 때문이다.

Cloud Logging 쿼리 예:

```
resource.type="cloud_function"
resource.labels.function_name="createFirebaseCustomTokenFromEmailLinkToken"
jsonPayload.message=~"createFirebaseCustomTokenFromEmailLinkToken invoked"
```

이 함수는 `hasVerificationToken` / `hasKakaoUserId` / `hasStudentEmail` 를
로깅했다 (`index.ts:1206-1210`). 따라서:

```
jsonPayload.hasVerificationToken=true
jsonPayload.hasKakaoUserId=false
```

**이 조합이 나오면 공격으로 간주한다.** 값 자체는 로깅되지 않았으므로
어떤 계정이 대상이었는지는 이 로그만으로는 알 수 없다. 같은 요청의
`lastRecoveredKakaoUserId` 쓰기(3단계)로 대상을 특정한다.

## 3. emailLinkTokens 감사

취약 함수는 성공 시 토큰 문서에 다음을 merge 했다 (`index.ts:1287-1291`).

```
lastRecoveredAt
lastRecoveredKakaoUserId
```

따라서 `lastRecoveredKakaoUserId` 가 있는 문서 = 세션이 발급된 적이 있는 토큰이다.
그 중 아래에 해당하면 위조 의심이다.

- `expiresAt` 이 `timestamp` 타입이 아니다 (정상 클라이언트는 항상 Timestamp)
- `createdAt` 이 없거나 serverTimestamp 가 아니다
- `createdAt` 과 `lastRecoveredAt` 의 간격이 30분(정상 만료)을 넘는다
- `email` / `kakaoUserId` 조합이 `users` 문서와 맞지만 그 사용자의 학생 인증
  시각(`studentVerifiedAt`)보다 토큰 `createdAt` 이 늦다
- 같은 `kakaoUserId` 에 대해 토큰 문서가 비정상적으로 많다

읽기 전용으로 먼저 목록을 뽑고, 확정 후 만료분을 삭제한다.
**삭제 전에 export 를 남긴다.**

## 4. 계정 세션 무효화

공격이 확인되거나 노출 구간이 넓으면:

```
1. 대상 사용자(또는 전체)의 refresh token 폐기
   Admin SDK: revokeRefreshTokens(uid)
2. 클라이언트가 재로그인을 강제하도록 배포
   (getIdToken(true) 실패 시 로그아웃 처리 경로 확인 필요)
```

전수 폐기는 **모든 사용자가 재로그인**해야 한다는 뜻이다. 사용자 공지가 필요하다.
이 결정은 서비스 영향이 크므로 별도 승인 대상이다.

주의: custom token 으로 발급된 세션은 `revokeRefreshTokens` 이후에도
기존 ID 토큰이 만료(최대 1시간)될 때까지 유효하다.

## 5. 2차 피해 감사

취약점으로 세션을 얻었다면 그 세션으로 무엇이든 할 수 있었다. 아래를 함께 본다.

| 대상 | 무엇을 찾는가 |
|---|---|
| `users` | `isStudentVerified` / `loginDisabled` / `status` 가 정상 흐름 밖에서 바뀐 문서 |
| `users/*/deviceTokens` | 소유자 uid 와 등록 시점·기기 정보가 어긋나는 토큰 |
| `blocks/*/targets` | 비정상 삭제 (가해자가 자기 차단을 지운 경우) |
| `reports` | 삭제되거나 `status` 가 임의로 바뀐 신고 |
| `chat_rooms/*/messages` | `senderId` 가 참가자가 아닌 메시지, `senderId: 'system'` 위조 |
| `interactions` / `recEvents` | 위조 like 로 생성된 `matches` |
| `bamboo_posts` | `likeCount` / `score7d` 가 비정상적으로 큰 글 |
| Storage `users/*/onboarding/photos/` | 소유자가 아닌 주체의 업로드·삭제 (Storage 감사 로그 필요) |
| `emailLinkTokens` | 위 3항 |
| `phoneHashIndex` | 같은 hash 가 다른 uid 로 덮어써진 이력 |

Storage 접근 로그는 기본적으로 켜져 있지 않다. 없으면
`EXPOSURE_POSSIBLE / AUDIT_IMPOSSIBLE` 로 기록한다.

## 6. 개인정보 침해 신고 판단

`users` 가 익명 list 가능했다는 것은 다음이 열람 가능했다는 뜻이다.

```
studentEmail (학교 이메일 = 실명 추정 가능)
onboarding (생년·학과·키·관심사·자기소개·사진 URL)
privacySettings / notificationSettings
preferenceVector
```

또 채팅 원문과 FCM 토큰이 전역 공개였다.

대량 열람 흔적이 확인되면 국내 개인정보보호법상 유출 통지·신고 의무가
발생할 수 있다. **이 판단은 법률 검토가 필요하며 엔지니어링 판단 범위를
넘는다.** 이 문서는 사실관계만 제공한다.

## 7. 기록

조사 결과를 아래 형식으로 남긴다.

```
노출 시작:
노출 종료:
공격 시그니처 발견 여부:
영향 계정 수:
2차 피해 발견 여부:
refresh token 폐기 여부:
법률 검토 요청 여부:
최종 판정: COMPROMISE_CONFIRMED | COMPROMISE_NOT_CONFIRMED
```

침해 증거를 찾지 못했다면 `COMPROMISE_NOT_CONFIRMED` 로 남긴다.
`NO_COMPROMISE` 로 결론 내리지 않는다. 로그 보존 기간이 노출 구간보다
짧으면 그 사실도 함께 적는다.
