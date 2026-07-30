/**
 * Season meeting (non-blind) deposit / cancel / no-show / replacement / refund
 * policy contracts. Provider credentials remain EXTERNAL; production fake
 * success paths are forbidden.
 */

import {
  assertSeasonMeetingTransition,
  type SeasonMeetingPhase,
  type SeasonTransitionActor,
} from "./seasonMeetingStateMachine";
import {
  applyDepositCallback,
  claimReplacementSeat,
  type ReplacementSeatClaim,
} from "./seasonMeetingConcurrency";

export type SeasonDepositIntent = {
  intentId: string;
  meetingId: string;
  participantUid: string;
  amount: number;
  currency: "KRW";
  idempotencyKey: string;
  status:
    | "created"
    | "authorized"
    | "captured"
    | "cancelled"
    | "refund_pending"
    | "refunded"
    | "failed";
  providerReference?: string;
};

export type SeasonCancelWindow =
  | "before_match_confirmed"
  | "after_match_before_schedule"
  | "after_schedule_before_meetup"
  | "day_of_meetup"
  | "after_safety_start";

export type SeasonRefundDecision =
  | { action: "none" }
  | { action: "full_refund" }
  | { action: "partial_refund"; ratio: number }
  | { action: "forfeit_pending_review" }
  | { action: "manual_review" };

export function assertDepositAmount(params: {
  amount: number;
  expectedAmount: number;
  currency: string;
}): void {
  if (params.currency !== "KRW") {
    throw new Error("deposit_currency_invalid");
  }
  if (!Number.isInteger(params.amount) || params.amount <= 0) {
    throw new Error("deposit_amount_invalid");
  }
  if (params.amount !== params.expectedAmount) {
    throw new Error("deposit_amount_mismatch");
  }
}

export function applySeasonDepositCallback(params: {
  depositStatus: "pending" | "paid" | "failed";
  callbackId: string;
  seenCallbackIds: Set<string>;
}): ReturnType<typeof applyDepositCallback> {
  return applyDepositCallback(params);
}

export function evaluateCancelRefund(params: {
  window: SeasonCancelWindow;
  depositCaptured: boolean;
}): SeasonRefundDecision {
  if (!params.depositCaptured) return { action: "none" };
  switch (params.window) {
    case "before_match_confirmed":
    case "after_match_before_schedule":
      return { action: "full_refund" };
    case "after_schedule_before_meetup":
      return { action: "partial_refund", ratio: 0.5 };
    case "day_of_meetup":
      return { action: "manual_review" };
    case "after_safety_start":
      return { action: "forfeit_pending_review" };
  }
}

export type NoShowReport = {
  meetingId: string;
  reporterUid: string;
  accusedUid: string;
  reportedAtMs: number;
  meetupStartAtMs: number;
  gracePeriodMs: number;
  safetyStartCompleted: boolean;
};

export function evaluateNoShowReport(report: NoShowReport): {
  status: "no_show_reported" | "no_show_rejected";
  reason?: string;
} {
  if (report.reporterUid === report.accusedUid) {
    return { status: "no_show_rejected", reason: "self_report" };
  }
  if (report.reportedAtMs < report.meetupStartAtMs + report.gracePeriodMs) {
    return { status: "no_show_rejected", reason: "before_grace" };
  }
  // Never auto-confirm forfeit from a single participant claim.
  return { status: "no_show_reported" };
}

export function transitionSeasonPhase(params: {
  from: SeasonMeetingPhase;
  to: SeasonMeetingPhase;
  actor: SeasonTransitionActor;
}): SeasonMeetingPhase {
  assertSeasonMeetingTransition(params.from, params.to, params.actor);
  return params.to;
}

export function claimSeasonReplacementSeat(params: {
  seat: ReplacementSeatClaim;
  claimantUid: string;
  expectedVersion: number;
}): ReturnType<typeof claimReplacementSeat> {
  return claimReplacementSeat(params);
}

export function applySeasonRefundOnce(params: {
  intent: SeasonDepositIntent;
  refundIdempotencyKey: string;
  processedRefundKeys: Set<string>;
  amount: number;
}): SeasonDepositIntent {
  if (params.intent.status === "refunded") {
    return params.intent;
  }
  if (params.processedRefundKeys.has(params.refundIdempotencyKey)) {
    return params.intent;
  }
  if (params.amount > params.intent.amount) {
    throw new Error("refund_exceeds_capture");
  }
  if (
    params.intent.status !== "captured" &&
    params.intent.status !== "refund_pending"
  ) {
    throw new Error("refund_status_invalid");
  }
  params.processedRefundKeys.add(params.refundIdempotencyKey);
  return {
    ...params.intent,
    status: "refunded",
  };
}
