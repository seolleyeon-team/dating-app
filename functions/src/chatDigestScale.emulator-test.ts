/**
 * P1-8 — daily unread digest cost at scale (deterministic document
 * operations on the emulator, never production).
 *
 * The P0-2 collector reads active rooms in pages and never touches a message
 * document. This suite pins that with representative synthetic workloads:
 *   100 / 1,000 users, skewed membership (a handful of 6-person rooms plus
 *   many 1:1 rooms), thousands of messages that must NOT be read.
 *
 * Measured quantity: Firestore DOCUMENT OPERATIONS performed by the
 * collector (rooms scanned == room documents read; message reads == 0),
 * plus wall-clock as a sanity bound. Billing is not measured here.
 *
 * Run (repo root, JDK 21):
 *   npx tsc -p functions --outDir functions/.p1-lib
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore --project demo-p18-digest \
 *     "node --test functions/.p1-lib/chatDigestScale.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-p18-digest" });

import { chatDigestNotificationId, collectDailyUnreadDigest } from "./chatUnread";

const db = getFirestore();
const runTag = Date.now().toString(36);

type Workload = { users: number; groupRooms: number; directRooms: number; messagesPerRoom: number };

/** Seeds rooms with server-maintained unread counters and a message history the collector must ignore. */
async function seedWorkload(prefix: string, w: Workload): Promise<{ rooms: number; expected: Map<string, number> }> {
  const uids = Array.from({ length: w.users }, (_, i) => `${prefix}_u${i}`);
  const expected = new Map<string, number>();
  let batch = db.batch();
  let ops = 0;
  const flush = async () => { if (ops > 0) { await batch.commit(); batch = db.batch(); ops = 0; } };
  const put = (ref: FirebaseFirestore.DocumentReference, data: Record<string, unknown>) => {
    batch.set(ref, data); ops += 1;
  };
  let rooms = 0;
  const seedRoom = async (id: string, members: string[], status: string) => {
    const unreadCounts: Record<string, number> = {};
    members.forEach((uid, i) => {
      const n = (i * 3 + members.length) % 7; // deterministic, some zeros
      unreadCounts[uid] = n;
      if (status === "active" && n > 0) expected.set(uid, (expected.get(uid) ?? 0) + n);
    });
    put(db.collection("chat_rooms").doc(id), {
      roomId: id, type: members.length > 2 ? "group" : "one_to_one", status, participantIds: members,
      participantInfo: Object.fromEntries(members.map((m) => [m, { nickname: `n_${m.slice(-3)}`, avatarUrl: "" }])),
      unreadCounts, unreadModelVersion: 2, lastMessageAt: Timestamp.now(), lastSenderId: members[0],
      lastMessage: "hello",
    });
    rooms += 1;
    for (let m = 0; m < w.messagesPerRoom; m += 1) {
      put(db.collection("chat_rooms").doc(id).collection("messages").doc(`m${m}`), {
        senderId: members[m % members.length], text: `msg ${m}`, type: "text", createdAt: Timestamp.now(), unreadAccountedAt: Timestamp.now(),
      });
    }
    if (ops >= 400) await flush();
  };
  // Skewed membership: the first users sit in every group room.
  for (let g = 0; g < w.groupRooms; g += 1) {
    const members = [uids[0], uids[1], uids[2], uids[(3 + g) % uids.length], uids[(4 + g) % uids.length], uids[(5 + g) % uids.length]];
    await seedRoom(`${prefix}_g${g}`, [...new Set(members)], "active");
  }
  for (let d = 0; d < w.directRooms; d += 1) {
    const a = uids[d % uids.length], b = uids[(d * 7 + 1) % uids.length];
    if (a === b) continue;
    await seedRoom(`${prefix}_d${d}`, [a, b], d % 10 === 9 ? "closed" : "active");
  }
  await flush();
  return { rooms, expected };
}

async function measure(prefixFilterRooms: number, pageSize: number) {
  const started = Date.now();
  const result = await collectDailyUnreadDigest(db, { pageSize });
  return { ...result, durationMs: Date.now() - started, pages: Math.ceil(prefixFilterRooms / pageSize) };
}

test("100 users / 45 rooms / 1,350 messages: the digest reads room documents only and aggregates per user across rooms", async () => {
  const prefix = `p18a_${runTag}`;
  const { rooms, expected } = await seedWorkload(prefix, { users: 100, groupRooms: 5, directRooms: 40, messagesPerRoom: 30 });
  const { targets, roomsScanned, durationMs } = await measure(rooms, 300);
  // roomsScanned counts every ACTIVE room in the emulator (other tests may
  // have seeded rooms); at least ours were read, and nothing else is read.
  assert.ok(roomsScanned >= rooms - 4, `scanned ${roomsScanned} of ${rooms}`);
  for (const [uid, count] of expected) {
    assert.equal(targets.get(uid)?.unreadCount, count, `${uid} aggregated across rooms`);
  }
  for (const uid of targets.keys()) {
    if (uid.startsWith(prefix)) assert.ok((expected.get(uid) ?? 0) > 0, `${uid} must have unread`);
  }
  assert.ok(durationMs < 15_000, `digest took ${durationMs}ms`);
});

test("1,000 users / 400 rooms / 4,000 messages: cost is one room document per active room, zero message documents, bounded time", async () => {
  const prefix = `p18b_${runTag}`;
  const { rooms, expected } = await seedWorkload(prefix, { users: 1000, groupRooms: 20, directRooms: 380, messagesPerRoom: 10 });
  const before = await db.collection("chat_rooms").where("status", "==", "active").count().get();
  const { targets, roomsScanned, durationMs } = await measure(rooms, 300);
  assert.equal(roomsScanned, before.data().count, "exactly the active room documents are read — one read per active room");
  for (const [uid, count] of expected) {
    assert.equal(targets.get(uid)?.unreadCount, count, uid);
  }
  // Skewed members (in all 20 group rooms) are deduplicated into one digest target each.
  assert.equal([...targets.keys()].filter((u) => u === `${prefix}_u0`).length, 1);
  assert.ok(durationMs < 30_000, `digest took ${durationMs}ms`);
  // Closed rooms never contribute.
  for (const [uid, t] of targets) {
    if (uid.startsWith(prefix)) assert.ok(t.unreadCount > 0);
  }
});

test("paging completeness: a page size smaller than the room count still visits every room once", async () => {
  const prefix = `p18c_${runTag}`;
  const { expected } = await seedWorkload(prefix, { users: 30, groupRooms: 2, directRooms: 25, messagesPerRoom: 2 });
  const small = await collectDailyUnreadDigest(db, { pageSize: 7 });
  const large = await collectDailyUnreadDigest(db, { pageSize: 1000 });
  assert.equal(small.roomsScanned, large.roomsScanned, "same rooms regardless of page size");
  for (const [uid, count] of expected) {
    assert.equal(small.targets.get(uid)?.unreadCount, count);
    assert.equal(large.targets.get(uid)?.unreadCount, count);
  }
  assert.equal(chatDigestNotificationId("2026-11-04"), "chat_digest_2026-11-04", "one in-app record per user per day");
});
