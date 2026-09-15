/** Pure accounting rules for store refunds of already-issued hearts. */

export type OpenRefundDebt = {
  id: string;
  outstandingAmount: number;
  repaidAmount: number;
  createdAtMs: number;
};

function wholeNonNegative(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? Math.floor(value)
    : 0;
}

export function refundHeartsForRevocation(
  originalHeartAmount: number,
  revocationPercentage: number | null
): number {
  const original = wholeNonNegative(originalHeartAmount);
  if (original === 0) return 0;
  // App Store represents partial-refund percentages in milliunits. Missing,
  // zero, and 100%+ values mean a full revocation for a unit consumable.
  if (
    revocationPercentage === null ||
    !Number.isFinite(revocationPercentage) ||
    revocationPercentage <= 0 ||
    revocationPercentage >= 100000
  ) {
    return original;
  }
  return Math.min(original, Math.max(1, Math.ceil((original * revocationPercentage) / 100000)));
}

export function applyRefundToBalance(
  currentBalance: number,
  refundedHearts: number
): { balanceAfter: number; recoveredFromBalance: number; outstandingAmount: number } {
  const balance = wholeNonNegative(currentBalance);
  const refund = wholeNonNegative(refundedHearts);
  const recoveredFromBalance = Math.min(balance, refund);
  return {
    balanceAfter: balance - recoveredFromBalance,
    recoveredFromBalance,
    outstandingAmount: refund - recoveredFromBalance,
  };
}

export function applyPurchasedHeartsToRefundDebts(
  purchasedHearts: number,
  debts: readonly OpenRefundDebt[]
): {
  creditedToBalance: number;
  appliedToDebt: number;
  allocations: Array<{ id: string; amount: number; outstandingAfter: number }>;
} {
  let remaining = wholeNonNegative(purchasedHearts);
  const allocations: Array<{ id: string; amount: number; outstandingAfter: number }> = [];
  const sorted = [...debts].sort((a, b) => a.createdAtMs - b.createdAtMs || a.id.localeCompare(b.id));
  for (const debt of sorted) {
    const outstanding = wholeNonNegative(debt.outstandingAmount);
    if (outstanding === 0 || remaining === 0) continue;
    const amount = Math.min(remaining, outstanding);
    remaining -= amount;
    allocations.push({ id: debt.id, amount, outstandingAfter: outstanding - amount });
  }
  return {
    creditedToBalance: remaining,
    appliedToDebt: wholeNonNegative(purchasedHearts) - remaining,
    allocations,
  };
}

export function refundReversalRestoration(input: {
  currentBalance: number;
  currentOutstandingTotal: number;
  recoveredFromBalance: number;
  repaidAmount: number;
  outstandingAmount: number;
}): { balanceAfter: number; outstandingAfter: number; restoredHearts: number } {
  const recovered = wholeNonNegative(input.recoveredFromBalance);
  const repaid = wholeNonNegative(input.repaidAmount);
  const released = wholeNonNegative(input.outstandingAmount);
  const restoredHearts = recovered + repaid;
  return {
    balanceAfter: wholeNonNegative(input.currentBalance) + restoredHearts,
    outstandingAfter: Math.max(0, wholeNonNegative(input.currentOutstandingTotal) - released),
    restoredHearts,
  };
}
