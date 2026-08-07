import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { STALE_MAX_AGE_MS } from "./staleJobRepair";
import {
  NEVER_AUTO_APPLY,
  runStaleJobRepairDryRun,
  summarizeRepairPlans,
} from "./staleJobRepairRunner";

describe("staleJobRepairRunner", () => {
  const now = 2_000_000_000_000;

  it("always blocks apply and marks dryRun", () => {
    const result = runStaleJobRepairDryRun({
      nowMs: now,
      allowApply: true,
      jobs: [
        {
          domain: "avatar_pending",
          id: "a1",
          status: "pending",
          updatedAtMs: now - STALE_MAX_AGE_MS.avatar_pending - 1,
          retryCount: 0,
        },
        {
          domain: "deposit_pending",
          id: "d1",
          status: "pending",
          updatedAtMs: now - STALE_MAX_AGE_MS.deposit_pending - 1,
          retryCount: 0,
        },
      ],
    });
    assert.equal(result.dryRun, true);
    assert.equal(result.applyBlocked, true);
    assert.equal(result.scanned, 2);
    assert.equal(result.stale, 2);
    assert.ok(NEVER_AUTO_APPLY.has("deposit_pending"));
    const summary = summarizeRepairPlans(result.plans);
    assert.equal(summary["avatar_pending:retry"], 1);
    assert.equal(summary["deposit_pending:operator_review"], 1);
  });
});
