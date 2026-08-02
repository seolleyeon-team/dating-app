# 3:3 블라인드 취향 미팅 운영 가이드

이 문서는 블라인드 취향 미팅의 수동 운영 절차를 정리한다.
전용 관리자 UI는 아직 없고, 운영 기능은 관리자 claim으로 보호된
Cloud Functions callable과 `BlindMeetingOpsRepository`로만 접근한다.

## 1. 운영 권한 부여

권한 판정은 클라이언트 필드가 아니라 Firebase Auth custom claim으로만 한다.

```bash
# 운영 담당자 UID에 claim 부여 (Firebase Admin SDK 환경에서 실행)
node -e "require('firebase-admin').initializeApp();require('firebase-admin').auth().setCustomUserClaims('<UID>',{admin:true}).then(()=>console.log('ok'))"
```

claim이 없으면 모든 운영 callable이 `permission-denied`로 거부된다.
`blindMeetingOps: true` claim도 동일하게 허용된다.

## 2. 운영 callable 목록

| callable | 용도 |
|---|---|
| `listBlindMeetingsForOps` | 상태별 미팅 목록 |
| `getBlindMeetingOpsDetail` | 참가자·대기자·대체 제안·환급·안전 flag·점수 요약·피드백 수 |
| `forceBlindMeetingRematch` | 수동 재매칭 (기존 미팅 취소 + 전액 환급 + 재매칭) |
| `overrideBlindMeetingRefund` | 운영자 예외 환급 (basis point 지정) |
| `setBlindMeetingRestriction` | 참여 제한 부여/해제 (days=0이면 해제) |
| `triggerBlindMeetingReplacement` | 대체 후보 탐색 수동 재시작 |
| `resolveBlindMeetingOpsReview` | 운영 검토 종료 처리 |
| `listBlindMeetingNotificationDispatches` | 알림 발송 상태 확인 |

## 3. 상태별 확인 포인트

| 상태 | 확인할 것 |
|---|---|
| `forming` | 슬롯별 신청자 수, 무알코올 후보군 충분 여부 |
| `awaiting_acceptance` | 수락 지연 참가자, 수락 마감 시간 |
| `awaiting_deposits` | 결제 실패 참가자, provider 응답 메시지 |
| `chat_open` | 일정 투표 진행률 |
| `schedule_confirmed` | 24시간·3시간 참석 확인 응답률 |
| `checkin_open` | 도착 안전도장 미완료자, 긴급 대체 진행 |
| `in_progress` | 5인 예외 진행 승인 여부 |
| `completed` | 종료 안전도장, 환급 상태 |
| `followup_open` | 후속 선택 제출률, 상호 선택 수 |
| `read_only` / `archived` | 채팅 lifecycle 정상 전환 |

## 4. 자주 하는 운영 작업

### 4.1 노쇼 수동 확정

스케줄러(`finalizeBlindMeetingNoShows`)가 미팅 시작 후
`urgentReplacementSearchWindowMs`(기본 45분)가 지나면 자동 처리한다.
수동으로 앞당겨야 하면 `triggerBlindMeetingReplacement`로 대체 탐색을 먼저 돌리고,
대체가 실패하면 자동으로 5인 진행 투표가 열린다.

### 4.2 사고·응급 상황 환급

참가자가 `emergency: true`로 취소하면 환급을 실행하지 않고
`blindMeetingOpsReviews`에 검토 문서가 생성된다.
검토 후 `overrideBlindMeetingRefund`로 비율을 지정해 환급하고
`resolveBlindMeetingOpsReview`로 종료한다.

### 4.3 종료 안전도장 누락 복구

사용자가 종료 도장을 놓치면 보증금 환급 조건이 채워지지 않는다.
참석 증거(도착 도장, 단체 채팅 기록)를 확인한 뒤
`overrideBlindMeetingRefund`(10000 basis point)로 전액 환급한다.

### 4.4 심각한 신고 처리

만족도 제출 시 `safetyConcernReported: true`가 오면
`blindMeetingSafetyFlags/{meetingId}`에 대상자와 pair가 기록되고
해당 참가자 간 후속 선택과 1:1 채팅 생성이 차단된다.
필요하면 `setBlindMeetingRestriction`으로 참여 제한을 추가한다.

## 5. 운영 설정 변경

정책 숫자는 `blindMeetingConfig/current` 문서로 덮어쓸 수 있다.
문서에 없는 키는 `functions/src/blindMeeting/policy.ts`의 기본값을 사용한다.

변경 가능한 주요 키:

```
depositAmount                     보증금 (원)
acceptanceWindowMs                수락 제한 시간
depositWindowMs                   결제 제한 시간
firstAttendanceCheckBeforeMs      1차 참석 확인 시점
secondAttendanceCheckBeforeMs     2차 참석 확인 시점
attendanceResponseWindowMs        참석 확인 응답 제한
fullRefundBeforeMs                전액 환급 경계
lateCancellationBeforeMs          부분 환급 경계
followUpPushDelayMs               후속 대화 푸시 지연
followUpWindowMs                  후속 선택 기간
groupChatWritableAfterMeetingMs   단체 채팅 쓰기 가능 기간
groupChatArchiveAfterMeetingMs    단체 채팅 보관 시점
firstNoShowRestrictionDays        첫 노쇼 제한 일수
secondNoShowRestrictionDays       재노쇼 제한 일수
replacementOfferWaveSize          대체 제안 1차 인원
replacementOfferExpiryMs          대체 제안 만료
recentlyMetLookbackMs             재매칭 제외 기간
```

매칭 가중치는 정책 문서가 아니라 코드의 versioned config
(`blind_taste_v1`)로 관리한다. 가중치를 바꾸면 새 버전을 만들고
`algorithmVersion`을 올려 성과를 버전별로 비교한다.

## 6. 결제 provider 설정 (외부 blocker)

운영 결제는 아래 환경 변수(Secret Manager)가 모두 있어야 동작한다.

```
BLIND_MEETING_PAYMENT_PROVIDER
BLIND_MEETING_PAYMENT_API_KEY
BLIND_MEETING_PAYMENT_BASE_URL
```

- 세 값이 모두 있으면 `ExternalPaymentProvider`가 선택된다.
- 값이 없고 emulator 환경이면 `SandboxPaymentProvider`(sandbox 플래그 true).
- 값이 없고 운영 환경이면 `UnconfiguredPaymentProvider`가 선택되어
  결제가 `failed`로 남는다. 성공을 가짜로 반환하지 않는다.

## 7. 배포 전 확인 순서

1. `blindMeetingConfig/current` 정책 값 검토
2. 결제 provider secret 주입 및 sandbox 결제 1건 검증
3. `firestore.rules` 배포 후 `test/firestore_rules` 통과 확인
4. `firestore.indexes.json` 배포 (신청 조회·대체 제안 쿼리에 필요)
5. Functions 배포 (`npm --prefix functions run build` 후 배포)
6. 알림 채널(`seolleyeon_high_importance`) 및 푸시 권한 확인
7. 내부 테스트 계정으로 전체 흐름 1회 리허설
