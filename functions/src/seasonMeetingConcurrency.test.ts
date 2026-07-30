import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  applyDepositCallback,
  claimReplacementSeat,
  type ReplacementSeatClaim,
} from "./seasonMeetingConcurrency";

describe("seasonMeetingConcurrency", () => {
  it("only one replacement claimant wins under version race", () => {
    const seat: ReplacementSeatClaim = {
      seatId: "seat-1",
      claimedByUid: null,
      status: "open",
      version: 1,
    };
    const first = claimReplacementSeat({
      seat,
      claimantUid: "u1",
      expectedVersion: 1,
    });
    assert.equal(first.ok, true);
    if (!first.ok) return;

    const second = claimReplacementSeat({
      seat: first.seat,
      claimantUid: "u2",
      expectedVersion: 1,
    });
    assert.equal(second.ok, false);
    if (second.ok) return;
    assert.equal(second.reason, "version_conflict");
  });

  it("ignores duplicate deposit callbacks", () => {
    const seen = new Set<string>();
    const first = applyDepositCallback({
      depositStatus: "pending",
      callbackId: "cb-1",
      seenCallbackIds: seen,
    });
    const second = applyDepositCallback({
      depositStatus: first.depositStatus,
      callbackId: "cb-1",
      seenCallbackIds: seen,
    });
    assert.equal(first.accepted, true);
    assert.equal(first.depositStatus, "paid");
    assert.equal(second.accepted, false);
    assert.equal(second.reason, "duplicate_callback");
    assert.equal(second.depositStatus, "paid");
  });
});
