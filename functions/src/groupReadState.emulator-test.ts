/**
 * P1-12 — group read-state concurrency on the P0-2 room-level model.
 *
 * The audit's original defect was a per-message `readBy` array that two
 * members read-modify-wrote at once (lost update). P0-2 replaced it with
 * `chat_rooms/{roomId}.unreadCounts.{uid}` / `lastReadAt.{uid}`: each member
 * writes exactly its own two keys with FieldPath updates and the server
 * increments the others' counters with FieldValue.increment inside a
 * transaction. This suite pins that six members marking read concurrently,
 * messages arriving during mark-read, delayed and duplicated accounting
 * triggers, and a departed member never corrupt another member's state.
 *
 * Run (repo root, JDK 21):
 *   npx tsc -p functions --outDir functions/.p1-lib
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore --project demo-p112-readstate \
 *     "node --test functions/.p1-lib/groupReadState.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { FieldPath, FieldValue, Timestamp, getFirestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-p112-readstate" });

import { UNREAD_MODEL_VERSION, accountMessageUnread, unreadCountFor } from "./chatUnread";

const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

async function seedGroup(size: number) {
  const members = Array.from({ length: size }, (_, i) => fresh(`m${i}`));
  const roomId = fresh("group");
  await db.collection("chat_rooms").doc(roomId).set({
    roomId, type: "group", roomType: "season_meeting_group", status: "active", writable: true,
    participantIds: members, unreadModelVersion: UNREAD_MODEL_VERSION,
    unreadCounts: Object.fromEntries(members.map((m) => [m, 0])),
    createdAt: Timestamp.now(), updatedAt: Timestamp.now(),
  });
  return { roomId, members };
}

/** Exactly what the client (chat_service.markRoomRead) writes. */
async function markRead(roomId: string, uid: string) {
  await db.collection("chat_rooms").doc(roomId).update(
    new FieldPath("unreadCounts", uid), 0,
    new FieldPath("lastReadAt", uid), FieldValue.serverTimestamp(),
  );
}

async function send(roomId: string, senderId: string, text: string) {
  const ref = await db.collection("chat_rooms").doc(roomId).collection("messages").add({
    senderId, text, type: "text", createdAt: FieldValue.serverTimestamp(),
  });
  return ref.id;
}

async function room(roomId: string) {
  return (await db.collection("chat_rooms").doc(roomId).get()).data() ?? {};
}

test("six members mark the room read at the same instant: every own counter is 0 and every own lastReadAt is set", async () => {
  const { roomId, members } = await seedGroup(6);
  for (let i = 0; i < 5; i += 1) {
    const id = await send(roomId, members[i % 6], `m${i}`);
    await accountMessageUnread(db, { roomId, messageId: id });
  }
  const before = await room(roomId);
  for (const m of members) assert.ok(unreadCountFor(before, m) >= 0);

  await Promise.all(members.map((m) => markRead(roomId, m)));
  const after = await room(roomId);
  const lastReadAt = after.lastReadAt as Record<string, Timestamp>;
  for (const m of members) {
    assert.equal(unreadCountFor(after, m), 0, `${m} counter reset`);
    assert.ok(lastReadAt[m] instanceof Timestamp, `${m} lastReadAt stamped`);
  }
  assert.equal(after.unreadModelVersion, UNREAD_MODEL_VERSION, "server-owned model version untouched");
});

test("two members mark read while a third member's message is being accounted: only the sender and the two readers end at the right values", async () => {
  const { roomId, members } = await seedGroup(6);
  const [a, b, c] = members;
  const id = await send(roomId, c, "racing");
  // Mark-read by a and b races the accounting of c's message.
  await Promise.all([
    accountMessageUnread(db, { roomId, messageId: id }),
    markRead(roomId, a),
    markRead(roomId, b),
  ]);
  const data = await room(roomId);
  // Readers: 0 (message committed before their mark-read) or 1 (their mark-read
  // committed before the message) — never negative, never another member's.
  for (const reader of [a, b]) assert.ok([0, 1].includes(unreadCountFor(data, reader)), reader);
  assert.equal(unreadCountFor(data, c), 0, "the sender never counts its own message");
  for (const other of members.slice(3)) assert.equal(unreadCountFor(data, other), 1, `${other} unaffected by the readers`);
});

test("a delayed and duplicated accounting trigger never resurrects an unread for a member who already read", async () => {
  const { roomId, members } = await seedGroup(3);
  const [a, b, c] = members;
  const id = await send(roomId, a, "late");
  await new Promise((r) => setTimeout(r, 10));
  await markRead(roomId, b); // b read the message on screen before the trigger ran
  const first = await accountMessageUnread(db, { roomId, messageId: id });
  const second = await accountMessageUnread(db, { roomId, messageId: id }); // redelivery
  assert.equal(second.reason, "already_accounted");
  const data = await room(roomId);
  assert.equal(unreadCountFor(data, b), 0, `b read before the late trigger (alreadyRead=${first.alreadyRead.length})`);
  assert.equal(unreadCountFor(data, c), 1, "c did not read: exactly one increment despite redelivery");
  assert.equal(unreadCountFor(data, a), 0);
});

test("a departed member's stale key is inert: it never changes and the remaining members' counters stay correct", async () => {
  const { roomId, members } = await seedGroup(4);
  const [a, b, c, gone] = members;
  await db.collection("chat_rooms").doc(roomId).set({ participantIds: [a, b, c] }, { merge: true });
  const id = await send(roomId, a, "after departure");
  await accountMessageUnread(db, { roomId, messageId: id });
  const data = await room(roomId);
  assert.equal(unreadCountFor(data, gone), 0, "non-participants are not incremented");
  assert.equal(unreadCountFor(data, b), 1);
  assert.equal(unreadCountFor(data, c), 1);
});

test("one read-state write is atomic per member: 25 concurrent mark-reads from six devices of the same six members converge", async () => {
  const { roomId, members } = await seedGroup(6);
  for (let i = 0; i < 3; i += 1) {
    const id = await send(roomId, members[0], `b${i}`);
    await accountMessageUnread(db, { roomId, messageId: id });
  }
  const writes: Promise<void>[] = [];
  for (let i = 0; i < 25; i += 1) writes.push(markRead(roomId, members[i % 6]));
  await Promise.all(writes);
  const data = await room(roomId);
  for (const m of members) assert.equal(unreadCountFor(data, m), 0, m);
  assert.deepEqual((data.participantIds as string[]).length, 6, "membership untouched by read-state writes");
});
