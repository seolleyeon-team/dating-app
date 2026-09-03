/**
 * 3:3 블라인드 취향 미팅 — legacy 보증금 상태 어댑터 (순수 함수)
 * 경로: functions/src/blindMeeting/legacyDepositStatus.ts
 *
 * 블라인드 미팅에는 더 이상 보증금도, 매칭 후 수락 단계도 없다. 매칭이
 * commit 되면 바로 confirmed 이고 단체 채팅방이 함께 열린다
 * (LIVE FSM: (매칭 tx) → confirmed → chat_open).
 *
 * 다만 이 변경 이전에 만들어진 Firestore 문서에는 아래 값이 남아 있을 수 있다.
 *   - 미팅   status/serverStatus = awaiting_deposits / awaitingDeposits
 *   - 참가자 status/serverStatus = deposit_pending / depositPending
 *   - 참가자·미팅 문서의 deposit* / refund* 필드
 *
 * 이 파일은 그 값을 canonical(비보증금) 상태로 읽어 들이는 **유일한** 자리다.
 * 여기 밖의 business code 는 legacy 상태 문자열을 알지 못하며, 결제 화면이나
 * payment intent 로 이어지는 경로는 존재하지 않는다 (LEGACY_STATE_NORMALIZATION
 * 만 허용). 실제 문서 복구는 legacyDepositNormalizer.ts 가 fail-closed 로 한다.
 */

/** legacy 미팅 상태 (서버 표기 / 앱 표기) */
export const LEGACY_MEETING_STATUS_AWAITING_DEPOSITS = "awaiting_deposits";
export const LEGACY_MEETING_STATUS_AWAITING_DEPOSITS_APP = "awaitingDeposits";

/** legacy 참가자 상태 (서버 표기 / 앱 표기) */
export const LEGACY_PARTICIPANT_STATUS_DEPOSIT_PENDING = "deposit_pending";
export const LEGACY_PARTICIPANT_STATUS_DEPOSIT_PENDING_APP = "depositPending";

/**
 * 과거 결제 원장 컬렉션. 신규 코드는 읽지도 쓰지도 않는다 (DEPRECATED_UNUSED).
 * firestore.rules 는 클라이언트 접근을 계속 거부한다. 운영 데이터 삭제는
 * 별도의 명시적 운영 승인 없이는 수행하지 않는다.
 */
export const LEGACY_DEPOSIT_LEDGER_COLLECTION = "blindMeetingDeposits";

/**
 * 과거 문서에 남아 있을 수 있는 deposit/refund 필드. 신규 코드는 이 필드를
 * 요구하지 않고 그대로 무시한다 (삭제하지 않는다).
 */
export const LEGACY_DEPOSIT_FIELDS: readonly string[] = [
  "depositStatus",
  "serverDepositStatus",
  "depositAmount",
  "depositPaidAt",
  "depositIntentId",
  "depositsOpenedAt",
  "depositDeadline",
  "refundStatus",
  "refundAmount",
  "refundedAmount",
  "refundOutcome",
  "refundIdempotencyKey",
  "paymentProvider",
];

export function isLegacyAwaitingDepositsStatus(raw: unknown): boolean {
  return (
    raw === LEGACY_MEETING_STATUS_AWAITING_DEPOSITS ||
    raw === LEGACY_MEETING_STATUS_AWAITING_DEPOSITS_APP
  );
}

/**
 * legacy `awaiting_deposits` 는 "매칭은 끝났지만 아직 확정되지 않은" 미팅이다.
 * 파서는 이를 LEGACY_COMPATIBILITY_ONLY 상태인 `awaiting_acceptance` 로 읽어
 * FSM(awaiting_acceptance → confirmed)을 통과시킬 수 있게 한다. 이 값은 읽기
 * 전용 표현이며, legacyDepositNormalizer 는 이 값을 문서에 쓰지 않는다
 * (온전한 match → confirmed, 아니면 repair).
 */
export function normalizeLegacyMeetingStatus(raw: string): string {
  return isLegacyAwaitingDepositsStatus(raw) ? "awaiting_acceptance" : raw;
}

export function isLegacyDepositPendingStatus(raw: unknown): boolean {
  return (
    raw === LEGACY_PARTICIPANT_STATUS_DEPOSIT_PENDING ||
    raw === LEGACY_PARTICIPANT_STATUS_DEPOSIT_PENDING_APP
  );
}

/**
 * legacy `deposit_pending` 참가자는 초대를 수락한 사람이다. 결제 단계가
 * 없어졌으므로 canonical 로는 `accepted` 로 읽는다.
 */
export function normalizeLegacyParticipantStatus(raw: string): string {
  return isLegacyDepositPendingStatus(raw) ? "accepted" : raw;
}
