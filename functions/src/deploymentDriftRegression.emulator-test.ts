/**
 * Deployment-drift regression (2026-10-25): two functions that had not been
 * redeployed since 2026-08-10 carry, besides the readBy removal, behaviour
 * that was committed in September but never went live. Before redeploying
 * them, pin that behaviour on the real handlers (`.run(event)`):
 *
 *  - onInteractionCreated: operations accounts and cross-partition /
 *    invalid-partition interactions are blocked (no notification, no match);
 *    a normal mutual like still creates match + room + system message, now
 *    carrying `dataPartition` and no `readBy`.
 *  - autoCompleteExpiredGoodbyeSafetyStamps: the client-written
 *    `participantIds` of a promise is narrowed to the room's participants
 *    before follow-up notifications go out; the completion message carries
 *    no `readBy`.
 *
 * Run (repo root, JDK 21):
 *   firebase emulators:exec --only firestore --project demo-p02-chat \
 *     "node --test functions/.p02-lib/deploymentDriftRegression.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

// index.ts performs initializeApp(); only import here.
import { autoCompleteExpiredGoodbyeSafetyStamps, onInteractionCreated } from "./index";

const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

type Runner = { run: (event: unknown) => Promise<unknown> };

async function seedUser(uid: string, extra: Record<string, unknown> = {}) {
  await db.collection("users").doc(uid).set({
    kakaoUserId: uid, nickname: `nick_${uid.slice(-4)}`, isActive: true, status: "active", ...extra,
  });
}

async function like(from: string, to: string, extra: Record<string, unknown> = {}) {
  const ref = db.collection("interactions").doc();
  await ref.set({ fromUserId: from, toUserId: to, action: "like", createdAt: Timestamp.now(), ...extra });
  const snap = await ref.get();
  await (onInteractionCreated as unknown as Runner).run({
    data: snap, params: { interactionId: ref.id }, id: `evt_${ref.id}`, time: new Date().toISOString(),
  });
  return ref.id;
}

async function notificationsOf(uid: string) {
  return (await db.collection("users").doc(uid).collection("notifications").get()).docs.map((d) => d.data());
}

async function matchesOf(uid: string) {
  return (await db.collection("matches").where("userIds", "array-contains", uid).get()).docs;
}

test("onInteractionCreated — production users: like notifies, mutual like creates match + room + readBy-free system message", async () => {
  const a = fresh("ia"), b = fresh("ib");
  await seedUser(a); await seedUser(b);
  const first = await like(a, b);
  const bNotes = await notificationsOf(b);
  assert.equal(bNotes.length, 1);
  assert.equal(bNotes[0].type, "profile_like");
  assert.equal((await matchesOf(a)).length, 0, "one-sided like creates no match");

  await like(b, a);
  const matches = await matchesOf(a);
  assert.equal(matches.length, 1);
  const match = matches[0].data();
  assert.deepEqual(new Set(match.userIds), new Set([a, b]));
  assert.equal(match.dataPartition, "production");
  const room = await db.collection("chat_rooms").doc(match.chatRoomId).get();
  assert.equal(room.exists, true);
  assert.equal(room.data()?.dataPartition, "production");
  const msgs = await room.ref.collection("messages").get();
  assert.equal(msgs.size, 1);
  assert.equal(msgs.docs[0].data().senderId, "system");
  assert.equal("readBy" in msgs.docs[0].data(), false, "no legacy readBy on the system message");
  assert.equal(msgs.docs[0].data().dataPartition, "production");
  // Redelivery of the second like is idempotent for the match.
  const snap = await db.collection("interactions").doc(first).get();
  await (onInteractionCreated as unknown as Runner).run({ data: snap, params: { interactionId: first }, id: "evt_redeliver", time: new Date().toISOString() });
  assert.equal((await matchesOf(a)).length, 1, "existing match is not duplicated");
});

test("onInteractionCreated — an operations account never becomes a counterpart (no notification, no match)", async () => {
  const a = fresh("ia"), ops = fresh("iops");
  await seedUser(a); await seedUser(ops, { accountType: "operations" });
  await like(a, ops);
  await like(ops, a);
  assert.equal((await notificationsOf(ops)).length, 0);
  assert.equal((await notificationsOf(a)).length, 0);
  assert.equal((await matchesOf(a)).length, 0);
});

test("onInteractionCreated — cross-partition and invalid-partition interactions are blocked", async () => {
  const prod = fresh("ia"), review = fresh("irv"), bad = fresh("ibad");
  await seedUser(prod); await seedUser(review, { dataPartition: "play_review" }); await seedUser(bad, { dataPartition: "garbage" });
  await like(prod, review);
  await like(review, prod, { dataPartition: "play_review" });
  await like(prod, bad);
  await like(bad, prod);
  assert.equal((await notificationsOf(review)).length, 0);
  assert.equal((await notificationsOf(prod)).length, 0);
  assert.equal((await notificationsOf(bad)).length, 0);
  assert.equal((await matchesOf(prod)).length, 0);
  // A play_review pair stays inside its partition: no production like-notification is sent.
  const r2 = fresh("irv");
  await seedUser(r2, { dataPartition: "play_review" });
  await like(review, r2, { dataPartition: "play_review" });
  assert.equal((await notificationsOf(r2)).length, 0, "no production like-notification inside the review partition");
});

test("autoCompleteExpiredGoodbyeSafetyStamps — participantIds narrowed to room participants; completion message has no readBy", async () => {
  const a = fresh("sa"), b = fresh("sb"), outsider = fresh("sx"), roomId = fresh("sroom");
  for (const u of [a, b, outsider]) await seedUser(u);
  const twoDaysAgo = Timestamp.fromMillis(Date.now() - 2 * 24 * 60 * 60 * 1000);
  const roomRef = db.collection("chat_rooms").doc(roomId);
  await roomRef.set({ roomId, type: "one_to_one", status: "active", participantIds: [a, b], participantInfo: {}, createdAt: Timestamp.now(), updatedAt: Timestamp.now() });
  const promiseRef = roomRef.collection("promises").doc(fresh("p"));
  await promiseRef.set({
    promiseId: promiseRef.id, status: "in_progress", meetupCompletedAt: twoDaysAgo,
    participantIds: [a, b, outsider], // outsider is client-written and must be ignored
    safetyStamp: { goodbyeStampedUserIds: [a] },
    requestedBy: a, requestedTo: b, place: "신촌", placeCategory: "cafe",
  });
  // Control: a promise whose participantIds hold only one room member must be left alone.
  const lonelyRoom = db.collection("chat_rooms").doc(fresh("sroom"));
  await lonelyRoom.set({ roomId: lonelyRoom.id, type: "one_to_one", status: "active", participantIds: [a, b], participantInfo: {}, createdAt: Timestamp.now(), updatedAt: Timestamp.now() });
  const lonelyPromise = lonelyRoom.collection("promises").doc(fresh("p"));
  await lonelyPromise.set({ promiseId: lonelyPromise.id, status: "in_progress", meetupCompletedAt: twoDaysAgo, participantIds: [a, outsider], safetyStamp: {}, requestedBy: a, requestedTo: b });

  await (autoCompleteExpiredGoodbyeSafetyStamps as unknown as Runner).run({ scheduleTime: new Date().toISOString() });

  const done = (await promiseRef.get()).data() ?? {};
  assert.equal(done.status, "completed");
  assert.equal(done.completionMode, "auto_without_goodbye_stamp");
  const followUps = Object.keys((done.safetyStamp as Record<string, unknown>).goodbyeFollowUpByUserId as Record<string, unknown>);
  assert.deepEqual(followUps, [b], "only the room participant without a goodbye stamp gets a follow-up");
  assert.equal((await notificationsOf(b)).length, 1);
  assert.equal((await notificationsOf(outsider)).length, 0, "client-listed outsider receives nothing");
  const msgs = await roomRef.collection("messages").get();
  assert.equal(msgs.size, 1);
  assert.equal(msgs.docs[0].data().type, "promise_completed");
  assert.equal("readBy" in msgs.docs[0].data(), false);
  assert.equal(((await lonelyPromise.get()).data() ?? {}).status, "in_progress", "fewer than two room participants: untouched");
});
