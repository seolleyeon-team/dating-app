/**
 * AUD-12 / AUD-25 — the real exported handlers (`.run(event)`) on the
 * emulator, never production.
 *
 *  - autoCompleteExpiredGoodbyeSafetyStamps: a second run and two overlapping
 *    runs neither repeat the completion message nor the follow-up notification.
 *  - sendDailyUnreadChatDigests: bounded-parallel delivery reaches every
 *    recipient once; a re-run delivers nothing twice.
 *  - onBambooPostLikeCreated: a redelivered event creates no second
 *    notification and no second push record, and nothing names the liker.
 *  - notificationDispatchLog records carry `expireAt`.
 *  - icebreaker: a decline recorded before activation is honoured.
 *
 * Run (repo root, JDK 21):
 *   firebase emulators:exec --only firestore --project demo-sched \
 *     "node --test functions/.audit-lib-sched/schedulerResidual.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

// index.ts performs initializeApp(); only import here.
import {
  autoCompleteExpiredGoodbyeSafetyStamps,
  onBambooPostLikeCreated,
  sendDailyUnreadChatDigests,
} from "./index";
import {
  activateMeetingIcebreakerPrompts,
  setMeetingIcebreakerOptOut,
} from "./meetingIcebreaker/session";
import {
  BLIND_TASTE_MEETING_TYPE,
  buildMeetingIcebreakerSessionId,
} from "./meetingIcebreaker/types";
import { verifyMeetingIcebreakerEntry } from "./meetingIcebreaker/verify";
import {
  buildNotificationIdempotencyKey,
  createInAppNotification,
  NOTIFICATION_DISPATCH_LOG_RETENTION_MS,
  sendPushOnce,
} from "./shared/notify";

const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;
const DAY = 24 * 60 * 60 * 1000;

type Runner = { run: (event: unknown) => Promise<unknown> };
const run = (fn: unknown, event: unknown = { scheduleTime: new Date().toISOString() }) =>
  (fn as Runner).run(event);

async function seedUser(uid: string, extra: Record<string, unknown> = {}) {
  await db.collection("users").doc(uid).set({
    kakaoUserId: uid, nickname: `nick_${uid.slice(-4)}`, isActive: true, status: "active",
    adultVerified: true, realNameVerified: true, ...extra,
  });
}

async function notificationsOf(uid: string) {
  return (await db.collection("users").doc(uid).collection("notifications").get()).docs;
}

const goodbyeCheckpoint = () =>
  db.collection("schedulerCheckpoints").doc("autoCompleteExpiredGoodbyeSafetyStamps");

test("goodbye auto-complete: a second run and two overlapping runs do not repeat the completion", async () => {
  // The watermark is global state: another suite sharing this emulator may
  // have advanced it past the fixture below. Start, and leave, without one.
  await goodbyeCheckpoint().delete();
  const a = fresh("ga"), b = fresh("gb"), roomId = fresh("groom");
  await seedUser(a); await seedUser(b);
  const roomRef = db.collection("chat_rooms").doc(roomId);
  await roomRef.set({ roomId, type: "one_to_one", status: "active", participantIds: [a, b], participantInfo: {}, createdAt: Timestamp.now(), updatedAt: Timestamp.now() });
  const promiseRef = roomRef.collection("promises").doc(fresh("p"));
  await promiseRef.set({
    promiseId: promiseRef.id, status: "in_progress",
    meetupCompletedAt: Timestamp.fromMillis(Date.now() - 2 * DAY),
    participantIds: [a, b], safetyStamp: { goodbyeStampedUserIds: [a] },
    requestedBy: a, requestedTo: b, place: "신촌", placeCategory: "cafe",
  });
  // Not due yet: stamped an hour ago.
  const recentRef = roomRef.collection("promises").doc(fresh("p"));
  await recentRef.set({
    promiseId: recentRef.id, status: "in_progress",
    meetupCompletedAt: Timestamp.fromMillis(Date.now() - 60 * 60 * 1000),
    participantIds: [a, b], safetyStamp: {}, requestedBy: a, requestedTo: b,
  });

  await run(autoCompleteExpiredGoodbyeSafetyStamps);
  assert.equal((await promiseRef.get()).get("status"), "completed");
  assert.equal((await recentRef.get()).get("status"), "in_progress", "a promise inside its 24 h window is untouched");
  assert.equal((await notificationsOf(b)).length, 1);
  const checkpoint = await goodbyeCheckpoint().get();
  assert.ok(checkpoint.get("watermark") instanceof Timestamp, "the run stores its watermark");

  await run(autoCompleteExpiredGoodbyeSafetyStamps);
  await Promise.all([run(autoCompleteExpiredGoodbyeSafetyStamps), run(autoCompleteExpiredGoodbyeSafetyStamps)]);
  const messages = await roomRef.collection("messages").get();
  assert.equal(messages.size, 1, "one completion message, however many runs");
  assert.equal((await notificationsOf(b)).length, 1, "one follow-up notification");
  assert.equal((await notificationsOf(a)).length, 0, "the participant who stamped gets nothing");
  assert.equal((await recentRef.get()).get("status"), "in_progress");
  await goodbyeCheckpoint().delete();
});

test("daily digest: every recipient is delivered once in bounded parallel; a re-run delivers nothing twice", async () => {
  const tag = fresh("dg");
  const RECIPIENTS = 240;
  let batch = db.batch();
  let ops = 0;
  const recipients: string[] = [];
  for (let i = 0; i < RECIPIENTS; i += 1) {
    const reader = `${tag}_r${i}`, sender = `${tag}_s${i}`;
    recipients.push(reader);
    batch.set(db.collection("users").doc(reader), { kakaoUserId: reader, nickname: "r", isActive: true, status: "active" });
    batch.set(db.collection("chat_rooms").doc(`${tag}_room${i}`), {
      roomId: `${tag}_room${i}`, type: "one_to_one", status: "active", participantIds: [reader, sender],
      participantInfo: { [sender]: { nickname: "보낸이", avatarUrl: "" }, [reader]: { nickname: "r", avatarUrl: "" } },
      unreadCounts: { [reader]: 2, [sender]: 0 }, unreadModelVersion: 2,
      lastMessageAt: Timestamp.now(), lastSenderId: sender, lastMessage: "hi",
    });
    ops += 2;
    if (ops >= 400) { await batch.commit(); batch = db.batch(); ops = 0; }
  }
  if (ops > 0) await batch.commit();

  // BEFORE shape: the same two delivery calls, one recipient at a time.
  const seqStarted = Date.now();
  for (const uid of recipients) {
    await sendPushOnce([uid], { title: "t", body: "b", data: { type: "chat_digest" } },
      buildNotificationIdempotencyKey(["chat_digest", `${tag}_seq`, uid]));
    await createInAppNotification(uid, { type: "chat_digest", title: "t", body: "b", deeplinkType: "chat", digestDate: `${tag}_seq` }, `chat_digest_${tag}_seq`);
  }
  const sequentialMs = Date.now() - seqStarted;

  const started = Date.now();
  await run(sendDailyUnreadChatDigests);
  const parallelMs = Date.now() - started;

  let delivered = 0;
  for (const uid of recipients) {
    const digests = (await notificationsOf(uid)).filter((doc) => doc.get("type") === "chat_digest" && !String(doc.id).includes("_seq"));
    assert.equal(digests.length, 1, `${uid} has exactly one digest`);
    delivered += 1;
  }
  assert.equal(delivered, RECIPIENTS);

  await run(sendDailyUnreadChatDigests);
  for (const uid of recipients.slice(0, 40)) {
    const digests = (await notificationsOf(uid)).filter((doc) => doc.get("type") === "chat_digest" && !String(doc.id).includes("_seq"));
    assert.equal(digests.length, 1, "a re-run creates no second digest");
  }
  const pushLogs = await db.collection("notificationDispatchLog").where("type", "==", "chat_digest").get();
  const mine = pushLogs.docs.filter((doc) => doc.id.includes(tag) && !doc.id.includes("_seq"));
  assert.equal(mine.length, RECIPIENTS, "one push record per recipient after two runs");

  console.log(
    `[AUD-12 digest] ${RECIPIENTS} recipients — one at a time: ${sequentialMs}ms ` +
      `(${(sequentialMs / RECIPIENTS).toFixed(1)}ms each) | scheduled function (10 in flight, incl. room scan): ${parallelMs}ms`
  );
  assert.ok(parallelMs < sequentialMs, "bounded-parallel delivery is faster than one at a time");
});

test("notificationDispatchLog records carry an expireAt about 90 days out", async () => {
  const uid = fresh("ttl");
  const key = buildNotificationIdempotencyKey(["ttl_probe", uid]);
  const before = Date.now();
  assert.equal(await sendPushOnce([uid], { title: "t", body: "b", data: { type: "ttl_probe" } }, key), true);
  const log = await db.collection("notificationDispatchLog").doc(key).get();
  const expireAt = log.get("expireAt");
  assert.ok(expireAt instanceof Timestamp);
  const delta = expireAt.toMillis() - before;
  assert.ok(Math.abs(delta - NOTIFICATION_DISPATCH_LOG_RETENTION_MS) < 60_000, `expireAt delta ${delta}`);
  // Dedupe is unchanged: the same key does not dispatch again.
  assert.equal(await sendPushOnce([uid], { title: "t", body: "b", data: { type: "ttl_probe" } }, key), false);
});

test("Bamboo like: a redelivered event creates no second notification or push record, and nothing names the liker", async () => {
  const owner = fresh("lo"), liker = fresh("lk"), other = fresh("l2"), postId = fresh("post");
  for (const uid of [owner, liker, other]) await seedUser(uid);
  await db.collection("bamboo_posts").doc(postId).set({ content: "글", category: "일상", isDeleted: false, createdAt: Timestamp.now(), likeCount: 0 });
  await db.collection("bamboo_post_authors").doc(postId).set({ ownerUid: owner, createdAt: Timestamp.now() });

  const deliver = async (uid: string, eventId: string) => {
    const ref = db.collection("bamboo_posts").doc(postId).collection("likes").doc(uid);
    if (!(await ref.get()).exists) await ref.set({ userId: uid, createdAt: Timestamp.now() });
    await run(onBambooPostLikeCreated, { data: await ref.get(), params: { postId, userId: uid }, id: eventId, time: new Date().toISOString() });
  };
  const likeNotes = async () => (await notificationsOf(owner)).filter((doc) => doc.get("type") === "community_post_like");
  const likeLogs = async () =>
    (await db.collection("notificationDispatchLog").where("type", "==", "community_post_like").get()).docs
      .filter((doc) => (doc.get("userIds") as string[]).includes(owner));

  const eventId = `evt-${fresh("uuid")}`;
  await deliver(liker, eventId);
  assert.equal((await likeNotes()).length, 1);
  assert.equal((await likeLogs()).length, 1);

  // At-least-once delivery: the same event arrives again (and concurrently).
  await deliver(liker, eventId);
  await Promise.all([deliver(liker, eventId), deliver(liker, eventId)]);
  assert.equal((await likeNotes()).length, 1, "redelivery must not create a second notification");
  assert.equal((await likeLogs()).length, 1, "redelivery must not push again");

  // A different like is a different event and still notifies.
  await deliver(other, `evt-${fresh("uuid")}`);
  assert.equal((await likeNotes()).length, 2);

  // P0-3: neither the documents nor their ids identify who liked.
  for (const doc of [...(await likeNotes()), ...(await likeLogs())]) {
    const haystack = `${doc.id} ${JSON.stringify(doc.data())}`;
    for (const actor of [liker, other]) assert.ok(!haystack.includes(actor), "no liker uid in id or data");
    assert.ok(!haystack.includes(eventId), "the raw event id is not stored");
  }
  for (const doc of await likeNotes()) {
    assert.equal(doc.get("actorId"), null);
    assert.equal(doc.get("actorName"), "익명");
  }
});

test("icebreaker: a decline recorded before activation is honoured, reported, and can be withdrawn", async () => {
  const uid = fresh("ib"), meetingId = fresh("meeting");
  await seedUser(uid);
  const sessionId = buildMeetingIcebreakerSessionId(BLIND_TASTE_MEETING_TYPE, meetingId);
  const participantRef = db.collection("meetingIcebreakerSessions").doc(sessionId).collection("promptParticipants").doc(uid);

  // The user declines before the session exists.
  assert.equal(await setMeetingIcebreakerOptOut({ sessionId, uid, optedOut: true }), true);
  assert.equal((await participantRef.get()).get("optedOut"), true);

  const activation = await activateMeetingIcebreakerPrompts({ meetingType: BLIND_TASTE_MEETING_TYPE, meetingId, uid });
  assert.equal(activation, "opted_out", "activation must not override the earlier decline");
  const afterActivation = await participantRef.get();
  assert.equal(afterActivation.get("optedOut"), true);
  assert.notEqual(afterActivation.get("isActive"), true);
  assert.equal(afterActivation.get("nextPromptAt") ?? null, null, "no prompt was scheduled");

  // Withdrawing the decline clears it; a later activation proceeds.
  assert.equal(await setMeetingIcebreakerOptOut({ sessionId, uid, optedOut: false }), false);
  assert.equal((await participantRef.get()).get("optedOut"), false);
  const second = await activateMeetingIcebreakerPrompts({ meetingType: BLIND_TASTE_MEETING_TYPE, meetingId, uid });
  assert.equal(second, "activated");
  assert.equal((await participantRef.get()).get("isActive"), true);

  // Declined while the session is already live for others: withdrawing the
  // decline activates this participant.
  const late = fresh("ib2");
  await seedUser(late);
  const lateRef = db.collection("meetingIcebreakerSessions").doc(sessionId).collection("promptParticipants").doc(late);
  await setMeetingIcebreakerOptOut({ sessionId, uid: late, optedOut: true });
  assert.equal(await activateMeetingIcebreakerPrompts({ meetingType: BLIND_TASTE_MEETING_TYPE, meetingId, uid: late }), "opted_out");
  await setMeetingIcebreakerOptOut({ sessionId, uid: late, optedOut: false });
  const lateDoc = await lateRef.get();
  assert.equal(lateDoc.get("optedOut"), false);
  assert.equal(lateDoc.get("isActive"), true, "the live session picks the participant up");
});

test("icebreaker: the entry check reports a pre-activation decline", async () => {
  const uid = fresh("ib3"), meetingId = fresh("meeting");
  await seedUser(uid);
  const sessionId = buildMeetingIcebreakerSessionId(BLIND_TASTE_MEETING_TYPE, meetingId);
  await db.collection("blindMeetings").doc(meetingId).set({ meetingId, serverStatus: "in_progress", participantIds: [uid] });
  await db.collection("meetingIcebreakerSessions").doc(sessionId).set({ sessionId, meetingType: BLIND_TASTE_MEETING_TYPE, meetingId, endedAt: null, stopReason: null });
  await setMeetingIcebreakerOptOut({ sessionId, uid, optedOut: true });
  const entry = await verifyMeetingIcebreakerEntry({ uid, sessionId, meetingId, meetingType: BLIND_TASTE_MEETING_TYPE });
  // Whatever the participation decision is for this bare fixture, the entry
  // reports the stored decline (it used to report "not declined").
  assert.equal(entry.sessionId, sessionId);
  assert.equal(entry.optedOut, true, `decision ${entry.decision}`);
});
