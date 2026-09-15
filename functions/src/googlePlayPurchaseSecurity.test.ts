import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  googlePlayPurchaseIdentifiersMatch,
  googlePlayPurchaseLedgerKey,
  googlePlayPurchaseTokenHash,
  validateGooglePlayRefundProductPurchase,
  validateGooglePlayProductPurchase,
} from "./googlePlayPurchaseSecurity";

describe("Google Play purchase ledger security", () => {
  it("derives idempotency exclusively from the verified purchase token", () => {
    const token = "play-token-123";
    const firstClientTransactionId = "client-transaction-a";
    const replayedClientTransactionId = "client-transaction-b";

    // Client transaction ids are intentionally absent from the API. Replaying
    // the same verified token therefore cannot select a second ledger record.
    assert.notEqual(firstClientTransactionId, replayedClientTransactionId);
    assert.equal(
      googlePlayPurchaseLedgerKey(token),
      googlePlayPurchaseLedgerKey(token),
    );
  });

  it("rejects a client transaction id that does not echo the purchase token", () => {
    assert.equal(
      googlePlayPurchaseIdentifiersMatch("play-token-123", "play-token-123"),
      true,
    );
    assert.equal(
      googlePlayPurchaseIdentifiersMatch(
        "replayed-client-transaction",
        "play-token-123",
      ),
      false,
    );
    assert.equal(googlePlayPurchaseIdentifiersMatch("", "play-token-123"), false);
  });

  it("separates distinct Google Play purchase tokens", () => {
    assert.notEqual(
      googlePlayPurchaseLedgerKey("play-token-123"),
      googlePlayPurchaseLedgerKey("play-token-456"),
    );
  });

  it("keeps raw purchase tokens out of persisted identifiers", () => {
    const token = "sensitive-play-token";
    assert.doesNotMatch(googlePlayPurchaseLedgerKey(token), new RegExp(token));
    assert.doesNotMatch(googlePlayPurchaseTokenHash(token), new RegExp(token));
    assert.match(googlePlayPurchaseLedgerKey(token), /^[a-f0-9]{64}$/);
    assert.match(googlePlayPurchaseTokenHash(token), /^[a-f0-9]{64}$/);
  });

  it("rejects an empty purchase token", () => {
    assert.throws(
      () => googlePlayPurchaseLedgerKey("   "),
      /google_play_purchase_token_missing/,
    );
    assert.throws(
      () => googlePlayPurchaseTokenHash(""),
      /google_play_purchase_token_missing/,
    );
  });

  it("accepts only a completed, unit-quantity purchase for the bound account", () => {
    assert.deepEqual(
      validateGooglePlayProductPurchase({
        purchase: {
          purchaseState: 0,
          consumptionState: 0,
          productId: "seolleyeon.heart.20",
          quantity: 1,
          obfuscatedExternalAccountId: "account-hash",
        },
        expectedProductId: "seolleyeon.heart.20",
        expectedAccountId: "account-hash",
      }),
      { ok: true, needsConsumption: true },
    );
  });

  it("recognizes an already-consumed valid purchase during an idempotent retry", () => {
    assert.deepEqual(
      validateGooglePlayProductPurchase({
        purchase: {
          purchaseState: 0,
          consumptionState: 1,
          productId: "seolleyeon.heart.20",
          quantity: 1,
          obfuscatedExternalAccountId: "account-hash",
        },
        expectedProductId: "seolleyeon.heart.20",
        expectedAccountId: "account-hash",
      }),
      { ok: true, needsConsumption: false },
    );
  });

  it("re-binds a voided RTDN purchase to its original product and account", () => {
    assert.deepEqual(
      validateGooglePlayRefundProductPurchase({
        purchase: {
          purchaseState: 1,
          productId: "seolleyeon.heart.20",
          obfuscatedExternalAccountId: "account-hash",
        },
        expectedProductId: "seolleyeon.heart.20",
        expectedAccountId: "account-hash",
      }),
      { ok: true },
    );
    assert.deepEqual(
      validateGooglePlayRefundProductPurchase({
        purchase: {
          productId: "seolleyeon.heart.40",
          obfuscatedExternalAccountId: "account-hash",
        },
        expectedProductId: "seolleyeon.heart.20",
        expectedAccountId: "account-hash",
      }),
      { ok: false, reason: "product_mismatch" },
    );
  });

  it("rejects pending/cancelled, mismatched product/quantity, and another account", () => {
    const validPurchase = {
      purchaseState: 0,
      consumptionState: 0,
      productId: "seolleyeon.heart.20",
      quantity: 1,
      obfuscatedExternalAccountId: "account-hash",
    };
    const validate = (purchase: typeof validPurchase) =>
      validateGooglePlayProductPurchase({
        purchase,
        expectedProductId: "seolleyeon.heart.20",
        expectedAccountId: "account-hash",
      });

    assert.deepEqual(validate({ ...validPurchase, purchaseState: 1 }), {
      ok: false,
      reason: "not_purchased",
    });
    assert.deepEqual(
      validate({ ...validPurchase, productId: "seolleyeon.heart.220" }),
      { ok: false, reason: "product_mismatch" },
    );
    assert.deepEqual(validate({ ...validPurchase, quantity: 2 }), {
      ok: false,
      reason: "product_mismatch",
    });
    assert.deepEqual(
      validate({
        ...validPurchase,
        obfuscatedExternalAccountId: "another-account-hash",
      }),
      { ok: false, reason: "account_mismatch" },
    );
  });
});
