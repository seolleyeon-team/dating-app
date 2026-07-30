/**
 * Pure concurrency helpers for season meeting races (NOT blind meeting).
 */

export type ReplacementSeatClaim = {
  seatId: string;
  claimedByUid: string | null;
  status: "open" | "claimed" | "closed";
  version: number;
};

export type ClaimResult =
  | { ok: true; seat: ReplacementSeatClaim }
  | { ok: false; reason: "not_open" | "version_conflict" | "already_claimed" };

/**
 * Transactional claim simulation: only one caller with matching version wins.
 */
export function claimReplacementSeat(params: {
  seat: ReplacementSeatClaim;
  claimantUid: string;
  expectedVersion: number;
}): ClaimResult {
  const { seat, claimantUid, expectedVersion } = params;
  // Version is checked first so concurrent claimants observe optimistic-lock failure.
  if (seat.version !== expectedVersion) {
    return { ok: false, reason: "version_conflict" };
  }
  if (seat.status !== "open") {
    return { ok: false, reason: seat.claimedByUid ? "already_claimed" : "not_open" };
  }
  return {
    ok: true,
    seat: {
      ...seat,
      status: "claimed",
      claimedByUid: claimantUid,
      version: seat.version + 1,
    },
  };
}

/**
 * Duplicate payment callback: only the first success transitions deposit.
 */
export function applyDepositCallback(params: {
  depositStatus: "pending" | "paid" | "failed";
  callbackId: string;
  seenCallbackIds: Set<string>;
}): {
  depositStatus: "pending" | "paid" | "failed";
  accepted: boolean;
  reason: string;
} {
  if (params.seenCallbackIds.has(params.callbackId)) {
    return {
      depositStatus: params.depositStatus,
      accepted: false,
      reason: "duplicate_callback",
    };
  }
  params.seenCallbackIds.add(params.callbackId);
  if (params.depositStatus === "paid") {
    return {
      depositStatus: "paid",
      accepted: false,
      reason: "already_paid",
    };
  }
  return {
    depositStatus: "paid",
    accepted: true,
    reason: "paid",
  };
}
