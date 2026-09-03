/**
 * 3:3 블라인드 취향 미팅 — 운영 정책 (서버)
 * 경로: functions/src/blindMeeting/policy.ts
 *
 * 원본 명세: lib/features/blind_meeting/domain/blind_meeting_policy.dart
 *
 * 블라인드 미팅에는 금전 개념이 없다. 취소·노쇼 정책은 좌석 해제, 대체 충원,
 * 참여 제한(신뢰/안전)만 결정한다.
 */

/** 취소·노쇼 처리 결과 */
export type CancellationOutcome =
  /** 좌석을 놓고 나간다. 대체 충원 대상. */
  | "released"
  /** 연락 없는 노쇼. 참여 제한 대상. */
  | "no_show"
  /** 사고·응급 상황. 운영자 검토 기록을 남긴다. */
  | "ops_review";

export type CancellationDecision = {
  outcome: CancellationOutcome;
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
  firstAttendanceCheckBeforeMs: number;
  secondAttendanceCheckBeforeMs: number;
  attendanceResponseWindowMs: number;
  attendanceReminderRetries: number;
  /**
   * 긴급 취소 경계. 미팅 시작까지 이 시간보다 적게 남았을 때의 취소는
   * 긴급 대체 탐색(더 큰 wave, 짧은 만료)으로 처리한다.
   */
  lateCancellationBeforeMs: number;
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
 * 운영 설정 문서(blindMeetingConfig/current)로 override 할 수 있다.
 */
export const DEFAULT_POLICY: BlindMeetingPolicy = {
  firstAttendanceCheckBeforeMs: 24 * HOUR,
  secondAttendanceCheckBeforeMs: 3 * HOUR,
  attendanceResponseWindowMs: 2 * HOUR,
  attendanceReminderRetries: 1,
  lateCancellationBeforeMs: 6 * HOUR,
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

/**
 * 운영 설정 문서로 정책 일부를 덮어쓴다.
 *
 * 정책에 없는 키(과거 결제 관련 키 포함)는 무시한다.
 */
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

/**
 * 취소·노쇼 처리 결정.
 *
 * 금전 결과가 없으므로 시점(untilMeetingMs)과 대체 성공 여부는 결정을
 * 바꾸지 않는다. 두 인자는 호출부의 운영 로그·긴급 대체 판단용으로만 쓰인다.
 */
export function resolveCancellation(params: {
  policy: BlindMeetingPolicy;
  /** 미팅 시작까지 남은 시간. null 이면 아직 시간이 확정되지 않았다. */
  untilMeetingMs: number | null;
  replacementFound: boolean;
  isNoShowWithoutContact?: boolean;
  emergencyReviewRequested?: boolean;
}): CancellationDecision {
  if (params.emergencyReviewRequested) {
    return {
      outcome: "ops_review",
      triggersWaitlistFill: true,
      appliesRestriction: false,
    };
  }

  if (params.isNoShowWithoutContact) {
    return {
      outcome: "no_show",
      triggersWaitlistFill: false,
      appliesRestriction: true,
    };
  }

  return {
    outcome: "released",
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
