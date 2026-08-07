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

  it("10 concurrent replacement claims from same snapshot yield exactly one winner", () => {
    let seat: ReplacementSeatClaim = {
      seatId: "seat-race",
      claimedByUid: null,
      status: "open",
      version: 7,
    };
    let wins = 0;
    let fails = 0;
    for (let i = 0; i < 10; i += 1) {
      const result = claimReplacementSeat({
        seat,
        claimantUid: `claimant_${i}`,
        expectedVersion: 7,
      });
      if (result.ok) {
        wins += 1;
        seat = result.seat;
      } else {
        fails += 1;
      }
    }
    assert.equal(wins, 1);
    assert.equal(fails, 9);
    assert.equal(seat.claimedByUid, "claimant_0");
    assert.equal(seat.status, "claimed");
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
