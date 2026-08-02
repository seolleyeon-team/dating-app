/**
 * 3:3 미팅 아이스브레이킹 룰렛 — 알림 정책과 예약 계산
 * 경로: functions/src/meetingIcebreaker/policy.ts
 *
 * 15분 같은 숫자를 코드 여러 곳에 반복하지 않고 이 파일 한 곳에서 관리한다.
 * 운영 중에는 `meetingIcebreakerConfig/current` 문서로 값을 덮어쓸 수 있다.
 * (blindMeeting/policy.ts와 같은 규칙: 숫자 필드만 override)
 */

import type { MeetingIcebreakerStopReason } from "./types";

const SECOND = 1000;
const MINUTE = 60 * SECOND;
const HOUR = 60 * MINUTE;

export type MeetingIcebreakerPolicy = {
  /** 반복 알림 주기 (분) */
  promptIntervalMinutes: number;
  /** 시작 안전도장 완료 후 첫 알림까지 대기 (분) */
  firstPromptDelayMinutes: number;
  /** 종료 도장을 잊은 경우를 위한 hard stop (시간) */
  maxPromptDurationHours: number;
  /**
   * 같은 참가자에게 연속 발송을 막는 최소 간격 (분).
   *
   * task 중복 실행이나 재시도로 알림이 몰리는 것을 막는 rate limit이다.
   */
  minPromptGapMinutes: number;
  /** 예약 시각보다 이만큼 이르게 실행된 task는 다시 예약한다 (초) */
  earlyDispatchToleranceSeconds: number;
  /** 예약 작업이 유실됐다고 보고 재예약하는 지연 임계값 (분) */
  reconcileGraceMinutes: number;
  /** Cloud Tasks dispatch deadline (초) */
  taskDispatchDeadlineSeconds: number;
  /** 한 번의 reconcile tick에서 처리할 최대 참가자 수 */
  reconcileBatchLimit: number;

  // ── feature flag (0 = 비활성, 1 = 활성) ────────────────────────────────
  /** 룰렛 화면 전체 */
  rouletteEnabled: number;
  /** 15분 반복 알림 */
  notificationsEnabled: number;
  /** 폭탄 돌리기 타이머 게임 */
  bombPassEnabled: number;
  /**
   * 1이면 음주 벌칙 칸을 비음주 문구로 강제 대체한다.
   *
   * 무알코올 미팅이거나 서비스 정책상 음주 표현이 허용되지 않는 경우에 사용한다.
   */
  alcoholFreeCopyForced: number;
};

export const DEFAULT_MEETING_ICEBREAKER_POLICY: MeetingIcebreakerPolicy = {
  promptIntervalMinutes: 15,
  firstPromptDelayMinutes: 15,
  maxPromptDurationHours: 6,
  minPromptGapMinutes: 13,
  earlyDispatchToleranceSeconds: 60,
  reconcileGraceMinutes: 3,
  taskDispatchDeadlineSeconds: 180,
  reconcileBatchLimit: 200,
  rouletteEnabled: 1,
  notificationsEnabled: 1,
  bombPassEnabled: 1,
  alcoholFreeCopyForced: 0,
};

/** 운영 설정 문서로 정책 일부를 덮어쓴다. 숫자 필드만 허용한다. */
export function meetingIcebreakerPolicyFromConfigDoc(
  raw: unknown,
  base: MeetingIcebreakerPolicy = DEFAULT_MEETING_ICEBREAKER_POLICY
): MeetingIcebreakerPolicy {
  if (typeof raw !== "object" || raw === null) return base;
  const data = raw as Record<string, unknown>;
  const merged: MeetingIcebreakerPolicy = { ...base };
  for (const key of Object.keys(base) as (keyof MeetingIcebreakerPolicy)[]) {
    const value = data[key];
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
      merged[key] = value;
    }
  }
  // 주기가 0이면 무한 루프가 되므로 최소 1분을 보장한다.
  if (merged.promptIntervalMinutes < 1) {
    merged.promptIntervalMinutes = 1;
  }
  if (merged.maxPromptDurationHours < 1) {
    merged.maxPromptDurationHours = 1;
  }
  return merged;
}

export function promptIntervalMs(policy: MeetingIcebreakerPolicy): number {
  return policy.promptIntervalMinutes * MINUTE;
}

export function firstPromptDelayMs(policy: MeetingIcebreakerPolicy): number {
  return policy.firstPromptDelayMinutes * MINUTE;
}

export function maxPromptDurationMs(policy: MeetingIcebreakerPolicy): number {
  return policy.maxPromptDurationHours * HOUR;
}

export function minPromptGapMs(policy: MeetingIcebreakerPolicy): number {
  return policy.minPromptGapMinutes * MINUTE;
}

export function reconcileGraceMs(policy: MeetingIcebreakerPolicy): number {
  return policy.reconcileGraceMinutes * MINUTE;
}

export function isRouletteEnabled(policy: MeetingIcebreakerPolicy): boolean {
  return policy.rouletteEnabled > 0;
}

export function areIcebreakerNotificationsEnabled(
  policy: MeetingIcebreakerPolicy
): boolean {
  return policy.notificationsEnabled > 0 && isRouletteEnabled(policy);
}

export function isBombPassEnabled(policy: MeetingIcebreakerPolicy): boolean {
  return policy.bombPassEnabled > 0 && isRouletteEnabled(policy);
}

export function isAlcoholFreeCopyForced(
  policy: MeetingIcebreakerPolicy
): boolean {
  return policy.alcoholFreeCopyForced > 0;
}

/** 시작 안전도장 시각 기준 첫 알림 시각 */
export function computeFirstPromptAtMs(
  startedAtMs: number,
  policy: MeetingIcebreakerPolicy
): number {
  return startedAtMs + firstPromptDelayMs(policy);
}

/** 시작 안전도장 시각 기준 hard stop 시각 */
export function computeExpiresAtMs(
  startedAtMs: number,
  policy: MeetingIcebreakerPolicy
): number {
  return startedAtMs + maxPromptDurationMs(policy);
}

/**
 * 다음 알림 시각.
 *
 * 오프라인이나 서버 지연으로 여러 주기가 지나갔더라도 밀린 알림을
 * 몰아서 보내지 않고, 원래 주기에 맞춰 미래의 다음 시각 하나만 계산한다.
 */
export function computeNextPromptAtMs(params: {
  nowMs: number;
  previousPromptAtMs: number;
  policy: MeetingIcebreakerPolicy;
}): number {
  const interval = promptIntervalMs(params.policy);
  const elapsed = params.nowMs - params.previousPromptAtMs;
  if (elapsed < interval) {
    return params.previousPromptAtMs + interval;
  }
  const passedIntervals = Math.floor(elapsed / interval);
  return params.previousPromptAtMs + (passedIntervals + 1) * interval;
}

export type PromptDispatchDecision =
  | {
      action: "send";
      /** 지연 때문에 건너뛴 알림 수 (몰아 보내지 않았다는 기록) */
      skippedPrompts: number;
      nextPromptAtMs: number;
    }
  | { action: "stop"; reason: MeetingIcebreakerStopReason }
  | {
      action: "reschedule";
      reason: "too_early" | "rate_limited";
      nextPromptAtMs: number;
    };

/**
 * task가 실행됐을 때 실제로 알림을 보낼지 결정한다.
 *
 * 순수 함수라서 시간·정책 조합을 테스트로 고정할 수 있다.
 */
export function decidePromptDispatch(params: {
  nowMs: number;
  scheduledForMs: number;
  expiresAtMs: number;
  lastPromptAtMs: number | null;
  policy: MeetingIcebreakerPolicy;
}): PromptDispatchDecision {
  const { nowMs, scheduledForMs, expiresAtMs, lastPromptAtMs, policy } = params;

  // 최대 지속 시간을 넘었으면 종료 도장이 없어도 더 보내지 않는다.
  if (nowMs >= expiresAtMs) {
    return { action: "stop", reason: "max_duration_reached" };
  }

  const tolerance = policy.earlyDispatchToleranceSeconds * SECOND;
  if (nowMs < scheduledForMs - tolerance) {
    return {
      action: "reschedule",
      reason: "too_early",
      nextPromptAtMs: scheduledForMs,
    };
  }

  if (
    lastPromptAtMs != null &&
    nowMs - lastPromptAtMs < minPromptGapMs(policy)
  ) {
    return {
      action: "reschedule",
      reason: "rate_limited",
      nextPromptAtMs: computeNextPromptAtMs({
        nowMs,
        previousPromptAtMs: lastPromptAtMs,
        policy,
      }),
    };
  }

  const interval = promptIntervalMs(policy);
  const lateBy = Math.max(0, nowMs - scheduledForMs);
  const skippedPrompts = Math.floor(lateBy / interval);

  return {
    action: "send",
    skippedPrompts,
    nextPromptAtMs: computeNextPromptAtMs({
      nowMs,
      previousPromptAtMs: scheduledForMs,
      policy,
    }),
  };
}

/** Cloud Tasks에 넘길 지연 시간 (초). 음수는 0으로 잘라낸다. */
export function scheduleDelaySecondsFor(
  targetMs: number,
  nowMs: number
): number {
  return Math.max(0, Math.floor((targetMs - nowMs) / SECOND));
}

/** 회전 시간 같은 값을 analytics bucket으로 바꾼다 (원시값 노출 방지). */
export function promptSequenceBucket(sequence: number): string {
  if (sequence <= 1) return "1";
  if (sequence <= 4) return "2-4";
  if (sequence <= 8) return "5-8";
  if (sequence <= 16) return "9-16";
  return "17+";
}
