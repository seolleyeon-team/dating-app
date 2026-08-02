/**
 * 3:3 블라인드 취향 미팅 — 운영 정책 (서버)
 * 경로: functions/src/blindMeeting/policy.ts
 *
 * 원본 명세: lib/features/blind_meeting/domain/blind_meeting_policy.dart
 * 환급 계산은 basis point로 하고, 실제 실행은 payments 모듈이 idempotent하게 수행한다.
 */

export type RefundOutcome =
  | "full_refund"
  | "partial_refund"
  | "no_refund"
  | "ops_review";

export type CancellationDecision = {
  outcome: RefundOutcome;
  refundBasisPoints: number;
  triggersWaitlistFill: boolean;
  appliesRestriction: boolean;
};

export type NoShowSanction = {
  restrictedDays: number;
  requiresOpsReview: boolean;
};

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export type BlindMeetingPolicy = {
  depositAmount: number;
  acceptanceWindowMs: number;
  depositWindowMs: number;
  firstAttendanceCheckBeforeMs: number;
  secondAttendanceCheckBeforeMs: number;
  attendanceResponseWindowMs: number;
  attendanceReminderRetries: number;
  fullRefundBeforeMs: number;
  lateCancellationBeforeMs: number;
  lateCancellationReplacementFailedBasisPoints: number;
  urgentCancellationReplacementFoundBasisPoints: number;
  followUpPushDelayMs: number;
  followUpWindowMs: number;
  followUpReminderBeforeCloseMs: number;
  groupChatWritableAfterMeetingMs: number;
  groupChatArchiveAfterMeetingMs: number;
  urgentReplacementSearchWindowMs: number;
  firstNoShowRestrictionDays: number;
  secondNoShowRestrictionDays: number;
  noShowLookbackMs: number;
  /** 대체 제안 1차 wave 인원 */
  replacementOfferWaveSize: number;
  /** 대체 제안 응답 제한 시간 */
  replacementOfferExpiryMs: number;
  /** 최근에 만난 사용자 재매칭 제외 기간 */
  recentlyMetLookbackMs: number;
  /** 단체 채팅방 약속잡기 투표 제한 시간 (지나면 서버가 자동 확정한다) */
  scheduleVoteWindowMs: number;
  /**
   * 신청 즉시 인라인으로 매칭을 시도할 최대 날짜 수.
   *
   * 나머지 날짜는 10분 주기 스케줄러가 처리한다. callable 타임아웃과
   * cold start 비용을 제한하기 위한 값이다.
   */
  inlineMatchingDateLimit: number;
  /**
   * legacy 슬롯 필드(`requestedSlotIds`) 호환 조회 사용 여부.
   *
   * 날짜 전용 backfill이 끝나면 0으로 내려 읽기 비용을 절반으로 줄인다.
   * (숫자 정책이라 config 문서로 override 가능: 0 = 비활성)
   */
  legacySlotCompatEnabled: number;
};

/**
 * 현재 운영 정책.
 *
 * depositAmount는 앱 상수(AppConstants.meetingDeposit)와 같은 값이며,
 * 운영 설정 문서(blindMeetingConfig/current)로 override 할 수 있다.
 */
export const DEFAULT_POLICY: BlindMeetingPolicy = {
  depositAmount: 5000,
  acceptanceWindowMs: 12 * HOUR,
  depositWindowMs: 12 * HOUR,
  firstAttendanceCheckBeforeMs: 24 * HOUR,
  secondAttendanceCheckBeforeMs: 3 * HOUR,
  attendanceResponseWindowMs: 2 * HOUR,
  attendanceReminderRetries: 1,
  fullRefundBeforeMs: 24 * HOUR,
  lateCancellationBeforeMs: 6 * HOUR,
  lateCancellationReplacementFailedBasisPoints: 5000,
  urgentCancellationReplacementFoundBasisPoints: 5000,
  followUpPushDelayMs: 15 * MINUTE,
  followUpWindowMs: 24 * HOUR,
  followUpReminderBeforeCloseMs: 4 * HOUR,
  groupChatWritableAfterMeetingMs: 48 * HOUR,
  groupChatArchiveAfterMeetingMs: 7 * DAY,
  urgentReplacementSearchWindowMs: 45 * MINUTE,
  firstNoShowRestrictionDays: 14,
  secondNoShowRestrictionDays: 30,
  noShowLookbackMs: 90 * DAY,
  replacementOfferWaveSize: 3,
  replacementOfferExpiryMs: 30 * MINUTE,
  recentlyMetLookbackMs: 60 * DAY,
  scheduleVoteWindowMs: 24 * HOUR,
  inlineMatchingDateLimit: 3,
  legacySlotCompatEnabled: 1,
};

/** 운영 설정 문서로 정책 일부를 덮어쓴다. */
export function policyFromConfigDoc(
  raw: unknown,
  base: BlindMeetingPolicy = DEFAULT_POLICY
): BlindMeetingPolicy {
  if (typeof raw !== "object" || raw === null) return base;
  const data = raw as Record<string, unknown>;
  const merged: BlindMeetingPolicy = { ...base };
  for (const key of Object.keys(base) as (keyof BlindMeetingPolicy)[]) {
    const value = data[key];
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
      merged[key] = value;
    }
  }
  return merged;
}

export function resolveCancellation(params: {
  policy: BlindMeetingPolicy;
  /**
   * 미팅 시작까지 남은 시간.
   *
   * null이면 약속잡기가 끝나지 않아 시작 시각이 아직 없다는 뜻이다.
   * 날짜 전용 정책에서는 보증금을 낸 뒤에도 시간이 미확정인 구간이 존재하므로
   * 이 구간의 취소는 항상 전액 환급이어야 한다. (0으로 취급하면 안 된다)
   */
  untilMeetingMs: number | null;
  replacementFound: boolean;
  isNoShowWithoutContact?: boolean;
  emergencyReviewRequested?: boolean;
}): CancellationDecision {
  const { policy, untilMeetingMs, replacementFound } = params;

  if (params.emergencyReviewRequested) {
    return {
      outcome: "ops_review",
      refundBasisPoints: 0,
      triggersWaitlistFill: true,
      appliesRestriction: false,
    };
  }

  if (params.isNoShowWithoutContact) {
    return {
      outcome: "no_refund",
      refundBasisPoints: 0,
      triggersWaitlistFill: false,
      appliesRestriction: true,
    };
  }

  // 시간이 아직 확정되지 않은 구간의 취소는 전액 환급.
  // 사용자가 알 수 없는 일정을 근거로 위약금을 물릴 수 없다.
  if (untilMeetingMs == null) {
    return {
      outcome: "full_refund",
      refundBasisPoints: 10000,
      triggersWaitlistFill: true,
      appliesRestriction: false,
    };
  }

  if (untilMeetingMs >= policy.fullRefundBeforeMs) {
    return {
      outcome: "full_refund",
      refundBasisPoints: 10000,
      triggersWaitlistFill: true,
      appliesRestriction: false,
    };
  }

  if (untilMeetingMs >= policy.lateCancellationBeforeMs) {
    if (replacementFound) {
      return {
        outcome: "full_refund",
        refundBasisPoints: 10000,
        triggersWaitlistFill: true,
        appliesRestriction: false,
      };
    }
    return {
      outcome: "partial_refund",
      refundBasisPoints: policy.lateCancellationReplacementFailedBasisPoints,
      triggersWaitlistFill: true,
      appliesRestriction: false,
    };
  }

  if (replacementFound) {
    return {
      outcome: "partial_refund",
      refundBasisPoints: policy.urgentCancellationReplacementFoundBasisPoints,
      triggersWaitlistFill: true,
      appliesRestriction: false,
    };
  }

  return {
    outcome: "no_refund",
    refundBasisPoints: 0,
    triggersWaitlistFill: true,
    appliesRestriction: false,
  };
}

export function resolveNoShowSanction(
  policy: BlindMeetingPolicy,
  recentNoShowCount: number
): NoShowSanction {
  if (recentNoShowCount <= 1) {
    return {
      restrictedDays: policy.firstNoShowRestrictionDays,
      requiresOpsReview: false,
    };
  }
  if (recentNoShowCount === 2) {
    return {
      restrictedDays: policy.secondNoShowRestrictionDays,
      requiresOpsReview: false,
    };
  }
  return {
    restrictedDays: policy.secondNoShowRestrictionDays * 2,
    requiresOpsReview: true,
  };
}

export function refundAmountFor(
  depositAmount: number,
  refundBasisPoints: number
): number {
  if (depositAmount <= 0 || refundBasisPoints <= 0) return 0;
  return Math.floor((depositAmount * refundBasisPoints) / 10000);
}
