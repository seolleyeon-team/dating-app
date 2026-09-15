import { createHash } from "node:crypto";

export type GooglePlayProductPurchase = {
  purchaseState?: number;
  consumptionState?: number;
  productId?: string;
  quantity?: number;
  obfuscatedExternalAccountId?: string;
};

export type GooglePlayPurchaseValidation =
  | { ok: true; needsConsumption: boolean }
  | {
      ok: false;
      reason: "not_purchased" | "product_mismatch" | "account_mismatch";
    };

export type GooglePlayRefundPurchaseValidation =
  | { ok: true }
  | { ok: false; reason: "product_mismatch" | "account_mismatch" };

/** Validates only server-returned Google Play purchase fields. */
export function validateGooglePlayProductPurchase(input: {
  purchase: GooglePlayProductPurchase;
  expectedProductId: string;
  expectedAccountId: string;
}): GooglePlayPurchaseValidation {
  if (input.purchase.purchaseState !== 0) {
    return { ok: false, reason: "not_purchased" };
  }
  if (
    input.purchase.productId !== input.expectedProductId ||
    (input.purchase.quantity ?? 1) !== 1
  ) {
    return { ok: false, reason: "product_mismatch" };
  }
  if (
    input.purchase.obfuscatedExternalAccountId !== input.expectedAccountId
  ) {
    return { ok: false, reason: "account_mismatch" };
  }
  return {
    ok: true,
    needsConsumption: input.purchase.consumptionState !== 1,
  };
}

/**
 * RTDN tells us a purchase changed state, not every authoritative purchase
 * field. Re-read the Developer API and bind its immutable product/account
 * identifiers to our original ledger before honoring a voided-purchase event.
 * A refunded purchase may no longer have purchaseState=0, so state is not
 * reused from the initial-grant validator here.
 */
export function validateGooglePlayRefundProductPurchase(input: {
  purchase: GooglePlayProductPurchase;
  expectedProductId: string;
  expectedAccountId: string;
}): GooglePlayRefundPurchaseValidation {
  if (input.purchase.productId !== input.expectedProductId) {
    return { ok: false, reason: "product_mismatch" };
  }
  if (
    input.purchase.obfuscatedExternalAccountId !== input.expectedAccountId
  ) {
    return { ok: false, reason: "account_mismatch" };
  }
  return { ok: true };
}

/** Android clients must echo the purchase token in both legacy request fields. */
export function googlePlayPurchaseIdentifiersMatch(
  transactionId: string,
  purchaseToken: string,
): boolean {
  const normalizedTransactionId = transactionId.trim();
  const normalizedToken = purchaseToken.trim();
  return (
    normalizedTransactionId.length > 0 &&
    normalizedToken.length > 0 &&
    normalizedTransactionId === normalizedToken
  );
}

/**
 * Builds the only Firestore ledger key accepted for a Google Play purchase.
 *
 * The purchase token is verified with Google Play and is stable across
 * redelivery. A client-provided transaction/order id must never participate in
 * the idempotency key: a modified client could vary that value and replay one
 * valid token into multiple entitlement records.
 */
export function googlePlayPurchaseLedgerKey(purchaseToken: string): string {
  const normalizedToken = purchaseToken.trim();
  if (!normalizedToken) {
    throw new Error("google_play_purchase_token_missing");
  }
  return createHash("sha256")
    .update(`google_play:${normalizedToken}`, "utf8")
    .digest("hex");
}

/** Hash persisted for audit/reconciliation without storing the raw token. */
export function googlePlayPurchaseTokenHash(purchaseToken: string): string {
  const normalizedToken = purchaseToken.trim();
  if (!normalizedToken) {
    throw new Error("google_play_purchase_token_missing");
  }
  return createHash("sha256").update(normalizedToken, "utf8").digest("hex");
}
