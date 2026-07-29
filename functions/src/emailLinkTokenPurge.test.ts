import assert from "node:assert/strict";
import test from "node:test";

import { shouldPurgeEmailLinkToken } from "./emailLinkTokenPurge";

test("expired unverified emailLinkTokens are purgeable", () => {
  assert.equal(
    shouldPurgeEmailLinkToken({
      expiresAt: new Date("2020-01-01T00:00:00.000Z"),
      now: new Date("2026-07-29T00:00:00.000Z"),
    }),
    true
  );
});

test("unexpired or verified tokens must not be purged", () => {
  assert.equal(
    shouldPurgeEmailLinkToken({
      expiresAt: new Date("2099-01-01T00:00:00.000Z"),
      now: new Date("2026-07-29T00:00:00.000Z"),
    }),
    false
  );
  assert.equal(
    shouldPurgeEmailLinkToken({
      expiresAt: new Date("2020-01-01T00:00:00.000Z"),
      emailVerifiedUid: "someone",
      now: new Date("2026-07-29T00:00:00.000Z"),
    }),
    false
  );
});
