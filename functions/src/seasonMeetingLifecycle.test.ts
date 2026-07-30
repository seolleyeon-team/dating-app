import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  applySeasonDepositCallback,
  applySeasonRefundOnce,
  assertDepositAmount,
  claimSeasonReplacementSeat,
  evaluateCancelRefund,
  evaluateNoShowReport,
  transitionSeasonPhase,
} from "./seasonMeetingLifecycle";

describe("seasonMeetingLifecycle", () => {
  it("rejects deposit amount mismatch and accepts exact KRW", () => {
    assert.throws(() =>
      assertDepositAmount({ amount: 4000, expectedAmount: 5000, currency: "KRW" }),
    );
    assert.doesNotThrow(() =>
      assertDepositAmount({ amount: 5000, expectedAmount: 5000, currency: "KRW" }),
    );
  });

  it("ignores duplicate deposit callbacks", () => {
    const seen = new Set<string>();
    const first = applySeasonDepositCallback({
      depositStatus: "pending",
      callbackId: "cb1",
      seenCallbackIds: seen,
    });
    const second = applySeasonDepositCallback({
      depositStatus: first.depositStatus,
      callbackId: "cb1",
      seenCallbackIds: seen,
    });
    assert.equal(first.accepted, true);
    assert.equal(second.accepted, false);
    assert.equal(second.reason, "duplicate_callback");
  });

  it("cancel policy never auto-forfeits before review after safety start", () => {
    const decision = evaluateCancelRefund({
      window: "after_safety_start",
      depositCaptured: true,
    });
    assert.equal(decision.action, "forfeit_pending_review");
  });

  it("no-show stays under review and rejects self/early reports", () => {
    const start = 1_000_000;
    assert.equal(
      evaluateNoShowReport({
        meetingId: "m1",
        reporterUid: "a",
        accusedUid: "a",
        reportedAtMs: start + 10_000,
        meetupStartAtMs: start,
        gracePeriodMs: 5_000,
        safetyStartCompleted: false,
      }).status,
      "no_show_rejected",
    );
    assert.equal(
      evaluateNoShowReport({
        meetingId: "m1",
        reporterUid: "a",
        accusedUid: "b",
        reportedAtMs: start + 10_000,
        meetupStartAtMs: start,
        gracePeriodMs: 5_000,
        safetyStartCompleted: false,
      }).status,
      "no_show_reported",
    );
  });

  it("replacement seat claim is single-winner under version race", () => {
    const seat = {
      seatId: "s1",
      claimedByUid: null,
      status: "open" as const,
      version: 1,
    };
    const a = claimSeasonReplacementSeat({
      seat,
      claimantUid: "u1",
      expectedVersion: 1,
    });
    const b = claimSeasonReplacementSeat({
      seat: a.ok ? a.seat : seat,
      claimantUid: "u2",
      expectedVersion: 1,
    });
    assert.equal(a.ok, true);
    assert.equal(b.ok, false);
  });

  it("refund is idempotent and cannot exceed capture", () => {
    const keys = new Set<string>();
    const intent = {
      intentId: "i1",
      meetingId: "m1",
      participantUid: "u1",
      amount: 5000,
      currency: "KRW" as const,
      idempotencyKey: "dep_1",
      status: "captured" as const,
    };
    const first = applySeasonRefundOnce({
      intent,
      refundIdempotencyKey: "ref_1",
      processedRefundKeys: keys,
      amount: 5000,
    });
    const second = applySeasonRefundOnce({
      intent: first,
      refundIdempotencyKey: "ref_1",
      processedRefundKeys: keys,
      amount: 5000,
    });
    assert.equal(first.status, "refunded");
    assert.equal(second.status, "refunded");
    assert.throws(() =>
      applySeasonRefundOnce({
        intent: { ...intent, status: "captured" },
        refundIdempotencyKey: "ref_2",
        processedRefundKeys: new Set(),
        amount: 6000,
      }),
    );
  });

  it("illegal season phase transitions throw", () => {
    assert.throws(() =>
      transitionSeasonPhase({
        from: "completed",
        to: "matched",
        actor: "server",
      }),
    );
    assert.equal(
      transitionSeasonPhase({
        from: "matched",
        to: "deposit_pending",
        actor: "server",
      }),
      "deposit_pending",
    );
  });
});
