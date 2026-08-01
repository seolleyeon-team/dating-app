import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyPushRecipient,
  filterPushRecipientIds,
} from "./pushRecipientPolicy";

test("deleted or suspended recipients are never notified", () => {
  for (const doc of [
    { isDeleted: true },
    { deleted: true },
    { isSuspended: true },
    { suspended: true },
    { accountStatus: "deleted" },
    { accountStatus: "suspended" },
    { accountStatus: "blocked" },
    { status: "Deleted" },
  ]) {
    const decision = classifyPushRecipient({
      recipientUid: "bob",
      recipientDoc: doc,
    });
    assert.deepEqual(decision, {
      allow: false,
      reason: "deleted_or_suspended",
    });
  }
});

test("missing user docs are skipped so orphan deviceTokens stay quiet", () => {
  assert.deepEqual(
    classifyPushRecipient({ recipientUid: "ghost", recipientDoc: null }),
    { allow: false, reason: "missing_user" }
  );
});

test("active recipients without an actor are allowed", () => {
  assert.deepEqual(
    classifyPushRecipient({
      recipientUid: "bob",
      recipientDoc: { isStudentVerified: true },
    }),
    { allow: true }
  );
});

test("either direction of a block hides the push from the recipient", () => {
  assert.deepEqual(
    classifyPushRecipient({
      recipientUid: "bob",
      recipientDoc: {},
      actorUid: "alice",
      recipientBlockedActor: true,
      actorBlockedRecipient: false,
    }),
    { allow: false, reason: "blocked_with_actor" }
  );
  assert.deepEqual(
    classifyPushRecipient({
      recipientUid: "bob",
      recipientDoc: {},
      actorUid: "alice",
      recipientBlockedActor: false,
      actorBlockedRecipient: true,
    }),
    { allow: false, reason: "blocked_with_actor" }
  );
});

test("self-actor and blank actor never trigger block filtering", () => {
  assert.deepEqual(
    classifyPushRecipient({
      recipientUid: "bob",
      recipientDoc: {},
      actorUid: "bob",
      recipientBlockedActor: true,
      actorBlockedRecipient: true,
    }),
    { allow: true }
  );
  assert.deepEqual(
    classifyPushRecipient({
      recipientUid: "bob",
      recipientDoc: {},
      actorUid: "  ",
      recipientBlockedActor: true,
    }),
    { allow: true }
  );
});

test("filterPushRecipientIds keeps only eligible recipients", async () => {
  const docs: Record<string, Record<string, unknown> | null> = {
    active: { isStudentVerified: true },
    deleted: { isDeleted: true },
    ghost: null,
    blocker: { isStudentVerified: true },
  };
  const blockEdges = new Set(["blocker->alice"]);

  const result = await filterPushRecipientIds(
    ["active", "deleted", "ghost", "blocker", "active", ""],
    {
      actorUserId: "alice",
      loadUserDoc: async (uid) => docs[uid] ?? null,
      hasBlockEdge: async (from, to) => blockEdges.has(`${from}->${to}`),
    }
  );

  assert.deepEqual(result.allowed, ["active"]);
  assert.deepEqual(
    result.skipped.map((s) => `${s.uid}:${s.reason}`).sort(),
    [
      "blocker:blocked_with_actor",
      "deleted:deleted_or_suspended",
      "ghost:missing_user",
    ]
  );
});
