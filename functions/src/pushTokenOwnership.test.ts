import assert from "node:assert/strict";
import test from "node:test";

import { planTokenOwnershipBackfill, tokenFingerprint } from "./pushTokenOwnership";

test("P1-3: the registry key is a non-reversible fingerprint, never the raw token", () => {
  const fp = tokenFingerprint("fcm:ABCDEF:raw-token-value");
  assert.match(fp, /^[0-9a-f]{64}$/);
  assert.equal(fp.includes("raw-token"), false);
  assert.equal(fp, tokenFingerprint("fcm:ABCDEF:raw-token-value"), "stable");
  assert.notEqual(fp, tokenFingerprint("fcm:ABCDEF:raw-token-valuf"));
});

test("P1-3 backfill plan: one owner per token, newest registration wins, losers are deleted", () => {
  const plan = planTokenOwnershipBackfill([
    { uid: "a", token: "T1", updatedAtMs: 1000 },
    { uid: "b", token: "T1", updatedAtMs: 2000 },
    { uid: "c", token: "T1", updatedAtMs: 1500 },
    { uid: "a", token: "T2", updatedAtMs: 500 },
    { uid: "", token: "T3", updatedAtMs: 1 },
    { uid: "d", token: "", updatedAtMs: 1 },
  ]);
  assert.deepEqual(plan.owners, [
    { token: "T1", ownerUid: "b", registeredAtMs: 2000 },
    { token: "T2", ownerUid: "a", registeredAtMs: 500 },
  ]);
  assert.deepEqual(plan.conflicts, [{ token: "T1", uids: ["a", "b", "c"] }]);
  assert.deepEqual(
    plan.staleRegistrations.sort((x, y) => x.uid.localeCompare(y.uid)),
    [{ uid: "a", token: "T1" }, { uid: "c", token: "T1" }]
  );
});

test("P1-3 backfill plan: a tie on updatedAt resolves deterministically and never deletes the winner's own duplicate", () => {
  const plan = planTokenOwnershipBackfill([
    { uid: "zed", token: "T", updatedAtMs: 0 },
    { uid: "amy", token: "T", updatedAtMs: 0 },
  ]);
  assert.equal(plan.owners[0].ownerUid, "amy");
  assert.deepEqual(plan.staleRegistrations, [{ uid: "zed", token: "T" }]);
  const single = planTokenOwnershipBackfill([{ uid: "amy", token: "T", updatedAtMs: 3 }]);
  assert.deepEqual(single.conflicts, []);
  assert.deepEqual(single.staleRegistrations, []);
});
