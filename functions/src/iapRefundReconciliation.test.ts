import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  applyPurchasedHeartsToRefundDebts,
  applyRefundToBalance,
  refundHeartsForRevocation,
  refundReversalRestoration,
} from "./iapRefundReconciliation";

describe("IAP refund reconciliation", () => {
  it("recovers usable hearts first and tracks only the shortfall as debt", () => {
    assert.deepEqual(applyRefundToBalance(12, 20), {
      balanceAfter: 0,
      recoveredFromBalance: 12,
      outstandingAmount: 8,
    });
  });

  it("uses later purchases to settle refund debt before crediting the balance", () => {
    assert.deepEqual(
      applyPurchasedHeartsToRefundDebts(15, [
        { id: "later", outstandingAmount: 7, repaidAmount: 0, createdAtMs: 20 },
        { id: "first", outstandingAmount: 10, repaidAmount: 0, createdAtMs: 10 },
      ]),
      {
        creditedToBalance: 0,
        appliedToDebt: 15,
        allocations: [
          { id: "first", amount: 10, outstandingAfter: 0 },
          { id: "later", amount: 5, outstandingAfter: 2 },
        ],
      }
    );
  });

  it("restores recovered and later-repaid hearts if a refund is reversed", () => {
    assert.deepEqual(
      refundReversalRestoration({
        currentBalance: 4,
        currentOutstandingTotal: 6,
        recoveredFromBalance: 12,
        repaidAmount: 2,
        outstandingAmount: 6,
      }),
      { balanceAfter: 18, outstandingAfter: 0, restoredHearts: 14 }
    );
  });

  it("maps a partial Apple revocation percentage to whole hearts", () => {
    assert.equal(refundHeartsForRevocation(20, 25000), 5);
    assert.equal(refundHeartsForRevocation(20, null), 20);
  });
});
