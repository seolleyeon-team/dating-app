/**
 * AUD-12 / AUD-25 unit pins (no Firestore).
 *
 *  - runWithConcurrency: the bound holds, order of starts is the input order,
 *    a stop request ends scheduling without dropping what already started.
 *  - grantPurchasedHearts replay answers with the committed balance, not the
 *    balance recorded when the purchase was first granted.
 *  - the Bamboo like notification id is derived from the delivery's event id,
 *    never from the like document id (which is the liker's uid, P0-3).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { runWithConcurrency } from "./shared/boundedConcurrency";

const indexSource = readFileSync(
  join(__dirname, "..", "src", "index.ts"),
  "utf8"
).replace(/\r\n/g, "\n");

function sourceBetween(startMarker: string, endMarker: string): string {
  const start = indexSource.indexOf(startMarker);
  assert.notEqual(start, -1, `${startMarker} must exist`);
  const end = indexSource.indexOf(endMarker, start + startMarker.length);
  assert.notEqual(end, -1, `could not delimit ${startMarker}`);
  return indexSource.slice(start, end);
}

test("runWithConcurrency never exceeds the bound and handles every item once", async () => {
  const items = Array.from({ length: 57 }, (_, i) => i);
  let inFlight = 0;
  let peak = 0;
  const seen: number[] = [];
  const started = await runWithConcurrency(items, 8, async (item) => {
    inFlight += 1;
    peak = Math.max(peak, inFlight);
    await new Promise((resolve) => setTimeout(resolve, 2));
    seen.push(item);
    inFlight -= 1;
  });
  assert.equal(started, items.length);
  assert.equal(peak, 8);
  assert.deepEqual([...seen].sort((a, b) => a - b), items);
});

test("runWithConcurrency starts items in input order and stops scheduling on request", async () => {
  const startedOrder: number[] = [];
  let finished = 0;
  const started = await runWithConcurrency(
    Array.from({ length: 40 }, (_, i) => i),
    4,
    async (item) => {
      startedOrder.push(item);
      await new Promise((resolve) => setTimeout(resolve, 1));
      finished += 1;
    },
    () => startedOrder.length >= 10
  );
  // Everything that started also finished; nothing after the stop started.
  assert.equal(started, finished);
  assert.ok(started >= 10 && started <= 13, `started ${started}`);
  assert.deepEqual(startedOrder, Array.from({ length: started }, (_, i) => i));
});

test("runWithConcurrency: a bound larger than the list, and an empty list", async () => {
  let calls = 0;
  assert.equal(await runWithConcurrency([1, 2], 50, async () => { calls += 1; }), 2);
  assert.equal(calls, 2);
  assert.equal(await runWithConcurrency([], 5, async () => { calls += 1; }), 0);
  assert.equal(calls, 2);
});

test("a replayed heart grant reports the committed balance, not the balance stored at first grant", () => {
  const grant = sourceBetween(
    "export const grantPurchasedHearts =",
    "\n/**\n * Store refund accounting"
  );
  const replay = grant.slice(grant.indexOf("alreadyGranted: true"));
  const branch = replay.slice(0, replay.indexOf("};"));
  assert.match(branch, /heartBalance: userSnap\.exists\s*\?\s*heartBalanceFromSnapshot\(userSnap\)/);
  // The stored after-balance is only the fallback for a missing user document.
  assert.equal(
    (grant.match(/existingData\.heartBalanceAfter/g) ?? []).length,
    1,
    "heartBalanceAfter of the first grant must not be the replay answer"
  );
});

test("the Bamboo like notification is idempotent on the event id and never keyed by the liker", () => {
  const trigger = sourceBetween(
    "export const onBambooPostLikeCreated =",
    "\nexport const onAskCreated ="
  );
  assert.match(trigger, /sha256Hex\(`bamboo_post_like:\$\{event\.id\}`\)/);
  assert.match(trigger, /await sendPushOnce\(/);
  assert.doesNotMatch(trigger, /await sendPushToUsers\(/, "push must go through the idempotent sender");
  // likerUserId is used for the self-like check and nothing else.
  const uses = trigger.match(/likerUserId/g) ?? [];
  assert.equal(uses.length, 3, "declaration, null check, self-like check");
  assert.doesNotMatch(trigger, /buildNotificationIdempotencyKey\(\[[^\]]*likerUserId/);
});

test("scheduled jobs touched by AUD-12 declare an explicit timeout", () => {
  const goodbye = sourceBetween(
    "export const autoCompleteExpiredGoodbyeSafetyStamps = onSchedule(",
    "async () => {"
  );
  assert.match(goodbye, /timeoutSeconds: 300/);
  const digest = sourceBetween(
    "export const sendDailyUnreadChatDigests = onSchedule(",
    "async () => {"
  );
  assert.match(digest, /timeoutSeconds: 540/);
  // The unpaginated collection-group read is gone from the schedule body.
  const body = sourceBetween(
    "export const autoCompleteExpiredGoodbyeSafetyStamps = onSchedule(",
    "\nexport const schedulePromiseReminderTask"
  );
  assert.doesNotMatch(body, /collectionGroup\("promises"\)/);
  assert.match(body, /sweepExpiredGoodbyePromises\(/);
});
