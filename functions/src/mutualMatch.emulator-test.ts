/**
 * P1-1 — mutual match duplication, block bypass and like-notification spam,
 * pinned on the real handlers (`onInteractionCreated.run`,
 * `onRecEventCreated.run`) against the Firestore emulator.
 *
 * Before the fix (`874cb3aa`) the interactions trigger ran a non-transactional
 * "existing matches" query and then created a random-id match, so two
 * simultaneous mutual likes created two matches and two welcome messages; a
 * block was never consulted; the like notification id was derived from the
 * interaction document id, so every extra interaction document notified again.
 *
 * Run (repo root, JDK 21):
 *   npx tsc -p functions --outDir functions/.p1-lib
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore --project demo-p11-match \
 *     "node --test functions/.p1-lib/mutualMatch.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

// index.ts performs initializeApp(); only import here.
import { onInteractionCreated, onRecEventCreated } from "./index";
import { buildDeterministicMatchId, buildDirectRoomId } from "./matchIdentity";

const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

type Runner = { run: (event: unknown) => Promise<unknown> };

async function seedUser(uid: string, extra: Record<string, unknown> = {}) {
  await db.collection("users").doc(uid).set({
    kakaoUserId: uid, nickname: `nick_${uid.slice(-4)}`, isActive: true, status: "active",
    adultVerified: true, realNameVerified: true, ...extra,
  });
}

/** Writes the interaction document the way the client does and returns the trigger event. */
async function writeLike(from: string, to: string, action = "like") {
  const ref = db.collection("interactions").doc();
  await ref.set({ fromUserId: from, toUserId: to, action, source: "test", createdAt: Timestamp.now() });
  const snap = await ref.get();
  return { data: snap, params: { interactionId: ref.id }, id: `evt_${ref.id}`, time: new Date().toISOString() };
}

async function runInteraction(event: unknown) {
  await (onInteractionCreated as unknown as Runner).run(event);
}

async function like(from: string, to: string, action = "like") {
  const event = await writeLike(from, to, action);
  await runInteraction(event);
  return event;
}

async function writeRecLike(from: string, to: string) {
  const ref = db.collection("recEvents").doc(from).collection("events").doc();
  await ref.set({ userId: from, targetUserId: to, eventType: "like", type: "like", createdAt: Timestamp.now() });
  const snap = await ref.get();
  return { data: snap, params: { userId: from, eventId: ref.id }, id: `rev_${ref.id}`, time: new Date().toISOString() };
}

async function runRecEvent(event: unknown) {
  await (onRecEventCreated as unknown as Runner).run(event);
}

async function block(blocker: string, target: string) {
  await db.collection("blocks").doc(blocker).collection("targets").doc(target).set({ createdAt: Timestamp.now() });
}

async function matchesBetween(a: string, b: string) {
  const snap = await db.collection("matches").where("userIds", "array-contains", a).get();
  return snap.docs.filter((d) => ((d.data().userIds ?? []) as string[]).includes(b));
}

async function likeNotificationsOf(uid: string) {
  const snap = await db.collection("users").doc(uid).collection("notifications").where("type", "==", "profile_like").get();
  return snap.docs;
}

async function systemMessagesOf(roomId: string) {
  const snap = await db.collection("chat_rooms").doc(roomId).collection("messages").get();
  return snap.docs.filter((d) => d.data().type === "system");
}

async function pair() {
  const a = fresh("ma"), b = fresh("mb");
  await seedUser(a); await seedUser(b);
  return { a, b, matchId: buildDeterministicMatchId(a, b), roomId: buildDirectRoomId(a, b) };
}

test("A: two simultaneous mutual likes create exactly one match, one room and one welcome message", async () => {
  const { a, b, matchId, roomId } = await pair();
  const [ab, ba] = await Promise.all([writeLike(a, b), writeLike(b, a)]);
  await Promise.all([runInteraction(ab), runInteraction(ba)]);

  const matches = await matchesBetween(a, b);
  assert.equal(matches.length, 1, "one logical match");
  assert.equal(matches[0].id, matchId, "deterministic pair identity");
  const match = matches[0].data();
  assert.equal(match.status, "active");
  assert.equal(match.chatRoomId, roomId);
  assert.equal(match.dataPartition, "production");

  const room = await db.collection("chat_rooms").doc(roomId).get();
  assert.equal(room.exists, true);
  assert.equal(room.data()?.matchId, matchId);
  assert.deepEqual(new Set(room.data()?.participantIds), new Set([a, b]));
  assert.equal((await systemMessagesOf(roomId)).length, 1, "exactly one welcome message");
  assert.equal((await likeNotificationsOf(a)).length, 1);
  assert.equal((await likeNotificationsOf(b)).length, 1);
});

test("B: a redelivered trigger event notifies once and dispatches one push", async () => {
  const { a, b } = await pair();
  const event = await writeLike(a, b);
  await runInteraction(event);
  await runInteraction(event);
  assert.equal((await likeNotificationsOf(b)).length, 1);
  const dispatch = await db.collection("notificationDispatchLog").where("userIds", "array-contains", b).get();
  assert.equal(dispatch.docs.filter((d) => d.data().type === "profile_like").length, 1);
});

test("C: repeated same-direction likes (many interaction documents, like then super_like) notify the recipient once", async () => {
  const { a, b } = await pair();
  await like(a, b);
  await like(a, b);
  await like(a, b, "super_like");
  const notes = await likeNotificationsOf(b);
  assert.equal(notes.length, 1, "pair-based idempotency, not per interaction document");
  assert.equal(notes[0].id, `like_${a}_${b}`);
  assert.equal((await matchesBetween(a, b)).length, 0, "one-sided likes never match");
});

test("D: a block placed before the reverse like prevents the match and the notification", async () => {
  const { a, b, roomId } = await pair();
  await like(a, b);
  await block(b, a); // B blocks A (server-written, either direction counts)
  await like(b, a);
  assert.equal((await matchesBetween(a, b)).length, 0, "no match between blocked users");
  assert.equal((await db.collection("chat_rooms").doc(roomId).get()).exists, false);
  assert.equal((await likeNotificationsOf(a)).length, 0, "the blocked side is not notified");
});

test("D2: a block from the liker's own side is enforced as well", async () => {
  const { a, b } = await pair();
  await like(b, a);
  await block(a, b);
  await like(a, b);
  assert.equal((await matchesBetween(a, b)).length, 0);
  assert.equal((await likeNotificationsOf(b)).length, 0);
});

test("E: an existing legacy random-id active match is respected — no canonical duplicate, no second welcome message", async () => {
  const { a, b, roomId } = await pair();
  const legacy = db.collection("matches").doc();
  await legacy.set({ userIds: [a, b], matchType: "mutual_like", status: "active", chatRoomId: roomId, matchedAt: Timestamp.now() });
  await db.collection("chat_rooms").doc(roomId).set({
    roomId, type: "one_to_one", status: "active", participantIds: [a, b], matchId: legacy.id,
    participantInfo: { [a]: { nickname: "A", avatarUrl: null }, [b]: { nickname: "B", avatarUrl: null } },
    createdAt: Timestamp.now(), updatedAt: Timestamp.now(),
  });
  await db.collection("chat_rooms").doc(roomId).collection("messages").add({ senderId: "system", type: "system", text: "old", content: "old", createdAt: Timestamp.now() });

  await like(a, b);
  await like(b, a);

  const matches = await matchesBetween(a, b);
  assert.equal(matches.length, 1);
  assert.equal(matches[0].id, legacy.id, "the legacy match stays the one match");
  assert.equal((await systemMessagesOf(roomId)).length, 1, "no duplicate welcome message");
  const room = await db.collection("chat_rooms").doc(roomId).get();
  assert.equal(room.data()?.matchId, legacy.id);
  assert.equal(room.data()?.participantInfo[a].nickname, "A", "participant metadata untouched");
});

test("F: an unmatched legacy match with a closed room is never resurrected by a later mutual like", async () => {
  const { a, b, roomId, matchId } = await pair();
  const legacy = db.collection("matches").doc();
  await legacy.set({ userIds: [a, b], matchType: "mutual_like", status: "unmatched", chatRoomId: roomId, matchedAt: Timestamp.now(), unmatchedAt: Timestamp.now() });
  await db.collection("chat_rooms").doc(roomId).set({
    roomId, type: "one_to_one", status: "closed", participantIds: [a, b], matchId: legacy.id, closedAt: Timestamp.now(),
    participantInfo: { [a]: { nickname: "A", avatarUrl: null }, [b]: { nickname: "B", avatarUrl: null } },
  });

  await like(a, b);
  await like(b, a);

  const matches = await matchesBetween(a, b);
  assert.equal(matches.length, 1);
  assert.equal(matches[0].id, legacy.id);
  assert.equal(matches[0].data().status, "unmatched");
  assert.equal((await db.collection("matches").doc(matchId).get()).exists, false, "no canonical match beside the unmatched legacy one");
  const room = await db.collection("chat_rooms").doc(roomId).get();
  assert.equal(room.data()?.status, "closed", "closed room stays closed");
  assert.equal((await systemMessagesOf(roomId)).length, 0, "no welcome message into a closed room");
});

test("G: an existing active direct room without a match (paid direct chat) is linked, not overwritten", async () => {
  const { a, b, roomId, matchId } = await pair();
  await db.collection("chat_rooms").doc(roomId).set({
    roomId, type: "one_to_one", status: "active", participantIds: [a, b],
    participantInfo: { [a]: { nickname: "PaidA", avatarUrl: "https://x/a.png" }, [b]: { nickname: "PaidB", avatarUrl: null } },
    lastMessage: "hello", createdAt: Timestamp.now(), updatedAt: Timestamp.now(), writable: true,
  });

  await like(a, b);
  await like(b, a);

  const match = await db.collection("matches").doc(matchId).get();
  assert.equal(match.exists, true);
  assert.equal(match.data()?.chatRoomId, roomId);
  const room = (await db.collection("chat_rooms").doc(roomId).get()).data() ?? {};
  assert.equal(room.matchId, matchId, "room linked to the match");
  assert.equal(room.participantInfo[a].nickname, "PaidA", "participant metadata preserved");
  assert.equal(room.lastMessage, "hello", "room metadata preserved");
  assert.equal((await systemMessagesOf(roomId)).length, 0, "no welcome message posted into an existing room");
});

test("H: recEvents and interactions paths share one match — the room-less rec match gets the room attached, never a second match", async () => {
  const { a, b, matchId, roomId } = await pair();
  await runRecEvent(await writeRecLike(a, b));
  await runRecEvent(await writeRecLike(b, a));
  let match = await db.collection("matches").doc(matchId).get();
  assert.equal(match.exists, true, "rec path creates the canonical match");
  assert.equal(match.data()?.chatRoomId, null, "rec path creates no room (unchanged behaviour)");
  assert.equal(match.data()?.matchType, "like");

  await like(a, b);
  await like(b, a);
  assert.equal((await matchesBetween(a, b)).length, 1, "still one match");
  match = await db.collection("matches").doc(matchId).get();
  assert.equal(match.data()?.chatRoomId, roomId, "room attached to the existing active match");
  assert.equal((await db.collection("chat_rooms").doc(roomId).get()).data()?.matchId, matchId);
  assert.equal((await systemMessagesOf(roomId)).length, 1);
});

test("I: rec and interaction triggers racing for the same mutual pair commit exactly one match", async () => {
  const { a, b } = await pair();
  const [recAB, recBA, intAB, intBA] = await Promise.all([
    writeRecLike(a, b), writeRecLike(b, a), writeLike(a, b), writeLike(b, a),
  ]);
  await Promise.all([runRecEvent(recAB), runRecEvent(recBA), runInteraction(intAB), runInteraction(intBA)]);
  const matches = await matchesBetween(a, b);
  assert.equal(matches.length, 1);
  const roomId = buildDirectRoomId(a, b);
  const systemMessages = await systemMessagesOf(roomId);
  assert.ok(systemMessages.length <= 1, "at most one welcome message");
});

test("K (P1-7): an account without server-side adult verification is never notified or matched, whichever side it is", async () => {
  const a = fresh("na"), b = fresh("nb"), c = fresh("nc");
  await seedUser(a); await seedUser(b, { adultVerified: false, realNameVerified: false }); await seedUser(c, { adultVerified: true, realNameVerified: false });
  await like(a, b); await like(b, a);
  assert.equal((await likeNotificationsOf(b)).length, 0);
  assert.equal((await likeNotificationsOf(a)).length, 0);
  assert.equal((await matchesBetween(a, b)).length, 0);
  // realNameVerified missing: the pair of flags is the evidence, not one of them.
  await like(a, c); await like(c, a);
  assert.equal((await matchesBetween(a, c)).length, 0);
  assert.equal((await likeNotificationsOf(c)).length, 0);
});

test("J: an operations account or a cross-partition pair is never matched or notified", async () => {
  const a = fresh("op"), b = fresh("ob"), c = fresh("oc");
  await seedUser(a, { accountType: "operations" }); await seedUser(b); await seedUser(c, { dataPartition: "play_review" });
  await like(b, a); await like(a, b);
  assert.equal((await matchesBetween(a, b)).length, 0);
  assert.equal((await likeNotificationsOf(a)).length, 0);
  await like(b, c); await like(c, b);
  assert.equal((await matchesBetween(b, c)).length, 0);
  assert.equal((await likeNotificationsOf(c)).length, 0);
});
