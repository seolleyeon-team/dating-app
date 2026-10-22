/**
 * P0-2 — the DEPLOYED trigger wiring: `onChatMessageCreated` from index.ts
 * accounts the message before its push logic, including system messages
 * (which return early for push). Runs the real handler via `.run(event)`.
 *
 * Run (repo root, JDK 21):
 *   firebase emulators:exec --only firestore --project demo-p02-chat \
 *     "node --test functions/.p02-lib/chatUnreadTrigger.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { FieldPath, FieldValue, getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

// index.ts performs initializeApp(); only import here.
import { onChatMessageCreated } from "./index";
import { unreadCountFor } from "./chatUnread";

const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

async function createMessage(roomId: string, senderId: string, text: string) {
  const ref = db.collection("chat_rooms").doc(roomId).collection("messages").doc();
  const now = Timestamp.now();
  await ref.set({ senderId, text, type: senderId === "system" ? "system" : "text", readBy: senderId === "system" ? [] : [senderId], createdAt: now, updatedAt: now });
  return ref;
}

async function runTrigger(roomId: string, messageId: string) {
  const snap = await db.collection("chat_rooms").doc(roomId).collection("messages").doc(messageId).get();
  await (onChatMessageCreated as unknown as { run: (event: unknown) => Promise<unknown> }).run({
    data: snap,
    params: { roomId, messageId },
    id: `evt_${messageId}`,
    time: new Date().toISOString(),
  });
}

test("deployed onChatMessageCreated accounts text and system messages exactly once", async () => {
  const a = fresh("ta"), b = fresh("tb"), roomId = fresh("troom");
  await db.collection("users").doc(a).set({ kakaoUserId: a });
  await db.collection("users").doc(b).set({ kakaoUserId: b });
  await db.collection("chat_rooms").doc(roomId).set({
    roomId, type: "one_to_one", status: "active", participantIds: [a, b],
    participantInfo: { [a]: { nickname: "A" }, [b]: { nickname: "B" } },
    createdAt: Timestamp.now(), updatedAt: Timestamp.now(),
  });
  const m1 = await createMessage(roomId, a, "hello");
  await runTrigger(roomId, m1.id);
  await runTrigger(roomId, m1.id); // redelivery
  const sys = await createMessage(roomId, "system", "매칭이 성사되었어요");
  await runTrigger(roomId, sys.id);

  const room = (await db.collection("chat_rooms").doc(roomId).get()).data() ?? {};
  assert.equal(unreadCountFor(room, b), 2, "b: text + system");
  assert.equal(unreadCountFor(room, a), 1, "a: system only");
  assert.equal(room.unreadModelVersion, 1);
  assert.ok((await m1.get()).data()?.unreadAccountedAt);
  assert.ok((await sys.get()).data()?.unreadAccountedAt);
});

test("deployed trigger declares platform retries: a failed accounting is retried, not dropped", () => {
  const endpoint = (onChatMessageCreated as unknown as { __endpoint?: { eventTrigger?: { retry?: unknown } } }).__endpoint;
  assert.equal(endpoint?.eventTrigger?.retry, true);
});

test("deployed trigger: recipient marked the room read before the delayed delivery → no phantom unread", async () => {
  const a = fresh("ta"), b = fresh("tb"), roomId = fresh("troom");
  await db.collection("chat_rooms").doc(roomId).set({
    roomId, type: "one_to_one", status: "active", participantIds: [a, b],
    participantInfo: { [a]: { nickname: "A" }, [b]: { nickname: "B" } },
    createdAt: Timestamp.now(), updatedAt: Timestamp.now(),
  });
  const m = await createMessage(roomId, a, "seen before the trigger ran");
  await new Promise((r) => setTimeout(r, 5));
  // The client's single mark-read write (chat_service.dart markRoomRead).
  await db.collection("chat_rooms").doc(roomId).update(
    new FieldPath("unreadCounts", b), 0,
    new FieldPath("lastReadAt", b), FieldValue.serverTimestamp()
  );
  await runTrigger(roomId, m.id);
  await runTrigger(roomId, m.id); // and a redelivery
  const room = (await db.collection("chat_rooms").doc(roomId).get()).data() ?? {};
  assert.equal(unreadCountFor(room, b), 0, "phantom unread after a delayed trigger");
  assert.ok((await m.get()).data()?.unreadAccountedAt);
});
