import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  planStaleRepair,
  planStaleRepairs,
  STALE_MAX_AGE_MS,
  type StaleJobSnapshot,
} from "./staleJobRepair";

describe("staleJobRepair dry-run planner", () => {
  const now = 1_700_000_000_000;

  it("noops when still within SLA", () => {
    const job: StaleJobSnapshot = {
      domain: "avatar_pending",
      id: "job-1",
      status: "pending",
      updatedAtMs: now - 60_000,
      retryCount: 0,
    };
    const plan = planStaleRepair(job, now);
    assert.equal(plan.action, "noop");
    assert.equal(plan.stale, false);
    assert.equal(plan.dryRun, true);
  });

  it("retries stale avatar jobs under retry budget", () => {
    const job: StaleJobSnapshot = {
      domain: "avatar_pending",
      id: "job-2",
      status: "generating",
      updatedAtMs: now - STALE_MAX_AGE_MS.avatar_pending - 1,
      retryCount: 1,
    };
    const plan = planStaleRepair(job, now);
    assert.equal(plan.action, "retry");
    assert.equal(plan.reason, "stale_active");
  });

  it("dead-letters after retry budget", () => {
    const job: StaleJobSnapshot = {
      domain: "avatar_pending",
      id: "job-3",
      status: "queued",
      updatedAtMs: now - STALE_MAX_AGE_MS.avatar_pending - 1,
      retryCount: 99,
    };
    const plan = planStaleRepair(job, now);
    assert.equal(plan.action, "dead_letter");
  });

  it("escalates high-risk season/deposit/refund to operator_review", () => {
    for (const domain of [
      "season_meeting_pending",
      "deposit_pending",
      "refund_pending",
    ] as const) {
      const plan = planStaleRepair(
        {
          domain,
          id: `${domain}-1`,
          status: "pending",
          updatedAtMs: now - STALE_MAX_AGE_MS[domain] - 1,
          retryCount: 0,
        },
        now
      );
      assert.equal(plan.action, "operator_review");
    }
  });

  it("never plans blind-meeting domains (unsupported by type system)", () => {
    const plans = planStaleRepairs(
      [
        {
          domain: "account_deletion_running",
          id: "del-1",
          status: "running",
          updatedAtMs: now - STALE_MAX_AGE_MS.account_deletion_running - 1,
          retryCount: 0,
        },
      ],
      now
    );
    assert.equal(plans.length, 1);
    assert.equal(plans[0]?.action, "retry");
    assert.equal(plans[0]?.dryRun, true);
  });
});
