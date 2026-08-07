/**
 * Unit coverage for season deposit fail-closed gating.
 * Provider credentials are intentionally absent in production until configured.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

// Compiled tests live in lib/; sources stay in src/.
const srcFile = resolve(__dirname, "../src/seasonMeetingOperations.ts");
const rulesFile = resolve(__dirname, "../../firestore.rules");

describe("season deposit fail-closed", () => {
  it("deposit and refund callables refuse when provider flag is unset", () => {
    const src = readFileSync(srcFile, "utf8");
    assert.match(src, /SEASON_DEPOSIT_PROVIDER_READY === "true"/);
    assert.match(src, /deposit_provider_not_configured/);
    // Both money entrypoints must gate on the same helper.
    const readyChecks = src.match(/if \(!depositProviderReady\(\)\)/g) ?? [];
    assert.ok(
      readyChecks.length >= 2,
      `expected >=2 depositProviderReady gates, got ${readyChecks.length}`,
    );
  });

  it("does not fabricate paid/refunded success without provider", () => {
    const src = readFileSync(srcFile, "utf8");
    // Money callables must throw failed-precondition before any provider I/O.
    assert.match(src, /deposit_provider_not_configured/);
    assert.match(src, /status: "created"/);
    // Intent creation must not auto-mark paid; payment callbacks live elsewhere.
    assert.equal(/status:\s*"paid"/.test(src), false);
    assert.equal(/return\s+\{\s*ok:\s*true,\s*paid:\s*true/.test(src), false);
  });

  it("seasonDepositIntents are client-deny in firestore.rules", () => {
    const rules = readFileSync(rulesFile, "utf8");
    assert.match(
      rules,
      /match \/seasonDepositIntents\/\{intentId\} \{\s*allow read, write: if false;/,
    );
  });
});
