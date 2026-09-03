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
| `getBlindMeetingOpsDetail` | 참가자·대기자·대체 제안·안전 flag·점수 요약·피드백 수 |
| `forceBlindMeetingRematch` | 수동 재매칭 (기존 미팅 취소 + 우선 재매칭) |
| `setBlindMeetingRestriction` | 참여 제한 부여/해제 (days=0이면 해제) |
| `triggerBlindMeetingReplacement` | 대체 후보 탐색 수동 재시작 |
| `resolveBlindMeetingOpsReview` | 운영 검토 종료 처리 |
| `listBlindMeetingNotificationDispatches` | 알림 발송 상태 확인 |

## 3. 상태별 확인 포인트

| 상태 | 확인할 것 |
|---|---|
| `forming` | 슬롯별 신청자 수, 무알코올 후보군 충분 여부 |
| `awaiting_acceptance` | **legacy 전용** (2026-09-03 이전 문서). 신규 미팅은 매칭 tx 에서 곧바로 `confirmed` + 채팅방으로 생성된다. 온전한 legacy 미팅은 `legacyAcceptance` tick 이 자동 확정, 대체 충원 진행 중이면 그대로, 빈 좌석·손상은 `legacyRepairRequired` 표시(취소 없음, 수락 타이머 없음) |
| `confirmed` | 채팅방(`groupChatId`)은 매칭 tx 에서 이미 생성됨. `chat_open` 전이가 지연되면 `groupChatRepair` tick 이 확정 시점 성별 스냅샷으로 복구. `groupChatRepairRequired: true` 면 운영자 수동 복구 대상(플래그를 지우면 다음 tick 재시도) |
| `chat_open` | 일정 투표 진행률 |
| `schedule_confirmed` | 24시간·3시간 참석 확인 응답률 |
| `checkin_open` | 도착 안전도장 미완료자, 긴급 대체 진행 |
| `in_progress` | 5인 예외 진행 승인 여부 |
| `completed` | 종료 안전도장 완료 여부 |
| `followup_open` | 후속 선택 제출률, 상호 선택 수 |
| `read_only` / `archived` | 채팅 lifecycle 정상 전환 |

## 4. 자주 하는 운영 작업

### 4.1 노쇼 수동 확정

스케줄러(`finalizeBlindMeetingNoShows`)가 미팅 시작 후
`urgentReplacementSearchWindowMs`(기본 45분)가 지나면 자동 처리한다.
수동으로 앞당겨야 하면 `triggerBlindMeetingReplacement`로 대체 탐색을 먼저 돌리고,
대체가 실패하면 자동으로 5인 진행 투표가 열린다.

### 4.2 사고·응급 상황

블라인드 미팅에는 보증금이 없다. 참가자가 `emergency: true`로 취소하면
좌석 정리(취소 상태·채팅 멤버십 해제·신청서 분리)는 즉시 끝나고, 제재 없이
`blindMeetingOpsReviews`에 `emergency_cancellation` 검토 문서만 남는다.
확인 후 `resolveBlindMeetingOpsReview`로 종료한다.

### 4.3 legacy 결제 대기 문서 복구

보증금 제도가 있던 시절의 미팅 문서는 `serverStatus = awaiting_deposits`로
남아 있을 수 있다. 5분 lifecycle tick 의 `legacyNormalize` 단계가
`functions/src/blindMeeting/legacyDepositNormalizer.ts`로 이를 복구한다.

- canonical match 가 온전하면(좌석 6·uid 6 unique·3남+3녀·좌석마다 참가자
  문서·신청서 6개가 이 미팅에 귀속) 과거 수락 수와 무관하게 새 계약(매칭 =
  확정)대로 legacy 확정 경로(`legacyAcceptance.ts`)로 `confirmed` → 채팅방 →
  `chat_open`. 사용자에게 수락을 다시 묻지 않고 `awaiting_acceptance` 도 새로
  만들지 않는다.
- 그 외(좌석 부족/중복, 성비 오류, 참가자 문서 누락, 빈 좌석, 신청서 이탈,
  확정 전 미팅에 있을 수 없는 참가자 상태) → 상태를 바꾸지 않고
  `legacyRepairRequired: true` + `legacy_status_repair` 운영 검토 문서 1건
  (fail-closed). 이후 tick 은 표시된 문서를 다시 건드리지 않는다. 운영자가
  확인 후 `legacyRepairRequired` 를 지우면 다음 tick 에 재판정한다.
- 만남 이력(`blindMeetingHistory/{uid}/metUsers`, 재매칭 제외용 recentlyMet)은
  매칭·확정·채팅방 시점이 아니라 도착 안전도장 시점에 실제 도착자끼리만
  기록된다. 노쇼·취소·대체로 빠진 사람은 기록되지 않는다.

어느 경우에도 결제를 요구하거나 결제 화면으로 보내지 않는다.
`blindMeetingDeposits` 컬렉션은 더 이상 읽지도 쓰지도 않는다
(운영 데이터 삭제는 별도 승인 사안).

### 4.4 매칭 전 신청 취소와 하트 환불

- 신청 취소는 **매칭 전에만** 있다 (`blindMeetingApplications/{uid}` 가
  applied/waitlisted ∧ meetingId 없음). 성공하면 같은 트랜잭션에서 신청에 쓴
  하트(DNA 시작 시 30H)를 정확히 한 번 돌려주고 신청서에
  `heartRefundedAmount / heartRefundedChargeCount / heartRefundedAt` 를 남긴다.
  환불 ledger: `heartTransactions/{sha256("blind_meeting_heart_refund:{uid}:{chargeCount}")}`
  (`type: heart_refund`, `refundOfTransactionId` = 원 spend id).
- 매칭이 이미 commit 된 신청은 `CANNOT_CANCEL_ALREADY_MATCHED` 로 거부된다
  (환불 없음). 앱은 매칭 결과/채팅으로 복구한다. 매칭 후 참여 불가는
  미팅 화면의 "참가 취소 요청"(대체 충원, 환불 없음)뿐이다.
- 이중 취소/재시도는 `already_cancelled` no-op 이다. 환불이 두 번 생겼다면
  ledger id 충돌이 아니라 데이터 손상이므로 `heartTransactions` 에서
  `type == heart_refund` 를 uid 로 조회해 확인한다.
- 취소해도 재사용 DNA(`blindMeetingDna/{uid}`, 답변 + `availableDateKeys`)와
  신청서의 `requestedDateKeys` 는 삭제되지 않는다. 다음 신청 화면이 이를
  그대로 불러온다.

### 4.5 심각한 신고 처리

만족도 제출 시 `safetyConcernReported: true`가 오면
`blindMeetingSafetyFlags/{meetingId}`에 대상자와 pair가 기록되고
해당 참가자 간 후속 선택과 1:1 채팅 생성이 차단된다.
필요하면 `setBlindMeetingRestriction`으로 참여 제한을 추가한다.

## 5. 운영 설정 변경

정책 숫자는 `blindMeetingConfig/current` 문서로 덮어쓸 수 있다.
문서에 없는 키는 `functions/src/blindMeeting/policy.ts`의 기본값을 사용한다.

변경 가능한 주요 키:

```
acceptanceWindowMs                수락 제한 시간
firstAttendanceCheckBeforeMs      1차 참석 확인 시점
secondAttendanceCheckBeforeMs     2차 참석 확인 시점
attendanceResponseWindowMs        참석 확인 응답 제한
lateCancellationBeforeMs          긴급 취소 경계 (긴급 대체 탐색 판단)
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
