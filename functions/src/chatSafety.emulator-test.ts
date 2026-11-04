/**
 * P1-2 — sendChatText authorisation and idempotency on the real Firestore
 * engine (transaction semantics), through the transactional core and the
 * callable handler (`.run`) with a stub user resolver.
 *
 * Before the fix (`874cb3aa`) the callable read the room outside the
 * transaction, ignored `status` / `writable`, consulted blocks only when the
 * client-mutable `type` said one_to_one, and every retry created a message.
 *
 * Run (repo root, JDK 21):
 *   npx tsc -p functions --outDir functions/.p1-lib
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore --project demo-p12-chat \
 *     "node --test functions/.p1-lib/chatSafety.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-p12-chat" });

import { createSendChatTextFunction, sendChatTextCore } from "./chatSafety";

const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

type Runner = { run: (req: unknown) => Promise<unknown> };

async function seedRoom(roomId: string, participants: string[], extra: Record<string, unknown> = {}) {
  await db.collection("chat_rooms").doc(roomId).set({
    roomId, type: participants.length === 2 ? "one_to_one" : "group", status: "active",
    participantIds: participants, createdAt: Timestamp.now(), updatedAt: Timestamp.now(), ...extra,
  });
}

async function messagesOf(roomId: string) {
  return (await db.collection("chat_rooms").doc(roomId).collection("messages").get()).docs;
}

async function expectDenied(promise: Promise<unknown>, code: string) {
  await assert.rejects(promise, (error: unknown) => {
    assert.ok(error instanceof HttpsError, `HttpsError expected, got ${String(error)}`);
    assert.equal(error.code, code);
    return true;
  });
}

const send = (uid: string, roomId: string, text: string, clientMessageId: string | null = null, data: Record<string, unknown> = {}) =>
  sendChatTextCore(db, { userId: uid, data }, { roomId, text, clientMessageId });

test("writable active room: a participant sends; the room metadata is updated in the same transaction", async () => {
  const a = fresh("a"), b = fresh("b"), room = fresh("dm");
  await seedRoom(room, [a, b]);
  const result = await send(a, room, "안녕하세요");
  assert.equal(result.deduplicated, false);
  const msgs = await messagesOf(room);
  assert.equal(msgs.length, 1);
  assert.equal(msgs[0].data().type, "text");
  assert.equal(msgs[0].data().senderId, a);
  const roomData = (await db.collection("chat_rooms").doc(room).get()).data() ?? {};
  assert.equal(roomData.lastMessage, "안녕하세요");
  assert.equal(roomData.photoBlurUnlocked, true);
});

test("closed, read_only, archived and writable:false rooms refuse a send; nothing is written", async () => {
  const a = fresh("a"), b = fresh("b");
  for (const extra of [{ status: "closed" }, { status: "read_only" }, { status: "archived", writable: false }, { status: "active", writable: false }]) {
    const room = fresh("dm");
    await seedRoom(room, [a, b], extra);
    await expectDenied(send(a, room, "hello"), "failed-precondition");
    assert.equal((await messagesOf(room)).length, 0, JSON.stringify(extra));
    assert.equal((await db.collection("chat_rooms").doc(room).get()).data()?.lastMessage, undefined);
  }
});

test("a user removed from participantIds (and a stranger) cannot send; a missing room is not-found", async () => {
  const a = fresh("a"), b = fresh("b"), c = fresh("c"), room = fresh("dm");
  await seedRoom(room, [b, c]);
  await expectDenied(send(a, room, "hello"), "permission-denied");
  await expectDenied(send(a, fresh("nope"), "hello"), "not-found");
  assert.equal((await messagesOf(room)).length, 0);
});

test("bilateral blocks: either direction refuses, and a client-spoofed room type does not disable the check", async () => {
  const a = fresh("a"), b = fresh("b");
  const roomForward = fresh("dm"), roomReverse = fresh("dm"), roomSpoofed = fresh("dm");
  await seedRoom(roomForward, [a, b]);
  await seedRoom(roomReverse, [a, b]);
  await seedRoom(roomSpoofed, [a, b], { type: "group", roomType: "season_meeting_group" });
  await db.collection("blocks").doc(a).collection("targets").doc(b).set({ createdAt: Timestamp.now() });
  await expectDenied(send(a, roomForward, "hello"), "permission-denied");
  await expectDenied(send(b, roomReverse, "hello"), "permission-denied");
  await expectDenied(send(b, roomSpoofed, "hello"), "permission-denied");
  for (const room of [roomForward, roomReverse, roomSpoofed]) assert.equal((await messagesOf(room)).length, 0);
});

test("a block committed concurrently with a send is observed: the send after the block never lands", async () => {
  const a = fresh("a"), b = fresh("b"), room = fresh("dm");
  await seedRoom(room, [a, b]);
  const results = await Promise.allSettled([
    db.collection("blocks").doc(b).collection("targets").doc(a).set({ createdAt: Timestamp.now() }),
    send(a, room, "racing"),
  ]);
  assert.equal(results[0].status, "fulfilled");
  // Either the send serialised before the block (one message) or after it
  // (denied, zero messages). It can never be both denied and written, and a
  // follow-up send is always denied.
  const msgs = await messagesOf(room);
  if (results[1].status === "fulfilled") assert.equal(msgs.length, 1); else assert.equal(msgs.length, 0);
  await expectDenied(send(a, room, "after block"), "permission-denied");
  assert.equal((await messagesOf(room)).length, msgs.length);
});

test("partition boundary: a production account cannot write into a review room and vice versa", async () => {
  const a = fresh("a"), b = fresh("b"), reviewRoom = fresh("dm"), prodRoom = fresh("dm");
  await seedRoom(reviewRoom, [a, b], { dataPartition: "play_review" });
  await seedRoom(prodRoom, [a, b]);
  await expectDenied(send(a, reviewRoom, "hello"), "permission-denied");
  await expectDenied(send(a, prodRoom, "hello", null, { dataPartition: "play_review" }), "permission-denied");
  await send(a, reviewRoom, "hello", null, { dataPartition: "play_review" });
  assert.equal((await messagesOf(reviewRoom)).length, 1);
});

test("idempotent send: the same clientMessageId creates one message; distinct ids with identical text create two", async () => {
  const a = fresh("a"), b = fresh("b"), room = fresh("dm");
  await seedRoom(room, [a, b]);
  const key = "11111111-2222-3333-4444-555555555555";
  const first = await send(a, room, "같은 문장", key);
  const retry = await send(a, room, "같은 문장", key);
  assert.equal(first.messageId, retry.messageId);
  assert.equal(retry.deduplicated, true);
  assert.equal((await messagesOf(room)).length, 1, "a timeout + retry is one message");

  await send(a, room, "같은 문장", "66666666-7777-8888-9999-000000000000");
  assert.equal((await messagesOf(room)).length, 2, "a genuinely new message with the same text is kept");

  // The id is sender-scoped: the peer re-using the same key writes their own message.
  await send(b, room, "같은 문장", key);
  assert.equal((await messagesOf(room)).length, 3);
});

test("concurrent duplicate requests (double tap / parallel retry) commit exactly one message", async () => {
  const a = fresh("a"), b = fresh("b"), room = fresh("dm");
  await seedRoom(room, [a, b]);
  const key = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
  const results = await Promise.allSettled([send(a, room, "x", key), send(a, room, "x", key), send(a, room, "x", key)]);
  assert.ok(results.some((r) => r.status === "fulfilled"));
  assert.equal((await messagesOf(room)).length, 1);
});

test("callable handler: validates text, clientMessageId and roomId and enforces the same decisions", async () => {
  const a = fresh("a"), b = fresh("b"), room = fresh("dm");
  await seedRoom(room, [a, b]);
  const fn = createSendChatTextFunction(db, async (request) => {
    const uid = (request as { auth?: { uid?: string } }).auth?.uid ?? "";
    return { userId: uid, data: {} };
  }) as unknown as Runner;
  const call = (uid: string, data: Record<string, unknown>) => fn.run({ data, auth: { uid, token: {} }, rawRequest: {} });

  const ok = (await call(a, { roomId: room, text: "  hi there  ", clientMessageId: "cccccccc-1111-2222-3333-444444444444" })) as { messageId: string };
  assert.ok(ok.messageId);
  await expectDenied(call(a, { roomId: room, text: "x".repeat(1001) }), "invalid-argument");
  await expectDenied(call(a, { roomId: room, text: "hi", clientMessageId: "bad id" }), "invalid-argument");
  await expectDenied(call(a, { roomId: "../etc", text: "hi" }), "invalid-argument");
  await expectDenied(call(a, { roomId: room, text: "call me 010-1234-5678" }), "invalid-argument");
  await db.collection("chat_rooms").doc(room).set({ status: "closed" }, { merge: true });
  await expectDenied(call(a, { roomId: room, text: "hi" }), "failed-precondition");
  assert.equal((await messagesOf(room)).length, 1);
});
