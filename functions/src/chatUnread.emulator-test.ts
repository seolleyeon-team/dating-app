/**
 * P0-2 — chat unread/read architecture against the Firestore Emulator.
 *
 * Two kinds of tests live here:
 *
 *  1. COST / BOUNDEDNESS (TEST P0-2-A/B/C/D/L). They run the same assertions
 *     against a "port" — `legacy` replicates the exact query shapes of the
 *     pre-fix client (`chat_service.dart`) and server digest, `new` uses the
 *     room-level model. `CHAT_UNREAD_PORT=legacy` is the before-fix evidence
 *     (expected to FAIL); the default `new` port must pass.
 *  2. BEHAVIOUR (TEST P0-2-E..J): sender exclusion, group recipients,
 *     mark-read/new-message race, at-least-once trigger idempotency,
 *     concurrent increments, multi-device, legacy rooms, backfill.
 *
 * Document "reads" are counted as documents returned by queries/gets (the
 * unit Firestore bills), via a thin wrapper — no production billing is
 * claimed.
 *
 * Run (repo root, JDK 21):
 *   npx tsc -p functions --outDir functions/.p02-lib
 *   firebase emulators:exec --only firestore --project demo-p02-chat \
 *     "node --test functions/.p02-lib/chatUnread.emulator-test.js"
 *   CHAT_UNREAD_PORT=legacy  … (before-fix evidence)
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import {
  FieldPath,
  FieldValue,
  Timestamp,
  getFirestore,
} from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

import {
  accountMessageUnread,
  backfillRoomUnread,
  checkRoomUnreadIntegrity,
  collectDailyUnreadDigest,
  runChatUnreadBackfill,
  timestampAtOrAfter,
  unreadCountFor,
} from "./chatUnread";

initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-p02-chat" });
const db = getFirestore();
const PORT = (process.env.CHAT_UNREAD_PORT ?? "new") as "legacy" | "new";
const PAGE_SIZE = 50;

let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

// ---------------------------------------------------------------------------
// Seeding helpers (Admin SDK, as the server writes)
// ---------------------------------------------------------------------------

async function seedRoom(
  roomId: string,
  participantIds: string[],
  extra: Record<string, unknown> = {}
) {
  await db.collection("chat_rooms").doc(roomId).set({
    roomId,
    type: participantIds.length === 2 ? "one_to_one" : "group",
    status: "active",
    participantIds,
    participantInfo: Object.fromEntries(
      participantIds.map((u) => [u, { nickname: `nick_${u}`, avatarUrl: "" }])
    ),
    createdAt: Timestamp.now(),
    updatedAt: Timestamp.now(),
    ...extra,
  });
}

/** Legacy-shaped message write (what every writer does today). */
async function seedMessage(
  roomId: string,
  senderId: string,
  index: number,
  opts: { readBy?: string[]; accounted?: boolean; type?: string; realTime?: boolean } = {}
) {
  const ref = db.collection("chat_rooms").doc(roomId).collection("messages").doc();
  // Production writers all stamp createdAt with the server time (≈ commit
  // time); the synthetic 2023 timeline keeps the cost tests deterministic.
  // Reconciliation tests need the real clock because its message query is
  // keyed on createdAt (see verifyRoomUnreadCounts).
  const createdAt = opts.realTime
    ? Timestamp.now()
    : Timestamp.fromMillis(1_700_000_000_000 + index * 1000);
  await ref.set({
    senderId,
    text: `m${index}`,
    type: opts.type ?? (senderId === "system" ? "system" : "text"),
    readBy: opts.readBy ?? (senderId === "system" ? [] : [senderId]),
    createdAt,
    updatedAt: createdAt,
    ...(opts.accounted ? { unreadAccountedAt: createdAt } : {}),
  });
  await db.collection("chat_rooms").doc(roomId).set(
    { lastMessage: `m${index}`, lastMessageAt: createdAt, updatedAt: createdAt },
    { merge: true }
  );
  return ref;
}

/** Simulates the deployed trigger (at-least-once) for one message. */
async function fireTrigger(roomId: string, messageId: string) {
  return accountMessageUnread(db, { roomId, messageId });
}

async function room(roomId: string) {
  return ((await db.collection("chat_rooms").doc(roomId).get()).data() ?? {}) as Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Ports: identical contract, legacy vs new implementation
// ---------------------------------------------------------------------------

type Port = {
  /** Global badge: does uid have any unread room? returns docs read. */
  hasAnyUnread(uid: string): Promise<{ value: boolean; reads: number }>;
  /** Room-list unread flag for one room. */
  roomUnread(roomId: string, uid: string): Promise<{ value: number; reads: number }>;
  /** Open a room: initial message load. returns messages loaded + reads. */
  openRoom(roomId: string): Promise<{ loaded: number; reads: number }>;
  /** Mark the room read for uid. returns writes issued. */
  markRead(roomId: string, uid: string): Promise<{ writes: number }>;
  /** Daily digest for all users. returns per-uid unread + message docs read. */
  digest(): Promise<{ counts: Map<string, number>; messageReads: number; roomReads: number }>;
};

const legacyPort: Port = {
  async hasAnyUnread(uid) {
    const rooms = await db.collection("chat_rooms").where("participantIds", "array-contains", uid).get();
    let reads = rooms.size;
    for (const r of rooms.docs) {
      const msgs = await r.ref.collection("messages").get();
      reads += msgs.size;
      for (const m of msgs.docs) {
        const d = m.data();
        if (d.senderId !== uid && !(d.readBy ?? []).includes(uid)) return { value: true, reads };
      }
    }
    return { value: false, reads };
  },
  async roomUnread(roomId, uid) {
    const msgs = await db.collection("chat_rooms").doc(roomId).collection("messages").get();
    let n = 0;
    for (const m of msgs.docs) {
      const d = m.data();
      if (d.senderId !== uid && !(d.readBy ?? []).includes(uid)) n++;
    }
    return { value: n, reads: msgs.size };
  },
  async openRoom(roomId) {
    const msgs = await db.collection("chat_rooms").doc(roomId).collection("messages").orderBy("createdAt").get();
    return { loaded: msgs.size, reads: msgs.size };
  },
  async markRead(roomId, uid) {
    const msgs = await db.collection("chat_rooms").doc(roomId).collection("messages").get();
    const batch = db.batch();
    let writes = 0;
    for (const m of msgs.docs) {
      const d = m.data();
      if (d.senderId === uid || (d.readBy ?? []).includes(uid)) continue;
      batch.update(m.ref, { readBy: [...(d.readBy ?? []), uid], updatedAt: FieldValue.serverTimestamp() });
      writes++;
    }
    if (writes > 0) await batch.commit(); // >500 → the real limit throws
    return { writes };
  },
  async digest() {
    const users = await db.collection("users").get();
    const counts = new Map<string, number>();
    let messageReads = 0;
    let roomReads = users.size;
    for (const u of users.docs) {
      const rooms = await db.collection("chat_rooms").where("participantIds", "array-contains", u.id).where("status", "==", "active").get();
      roomReads += rooms.size;
      let n = 0;
      for (const r of rooms.docs) {
        const msgs = await r.ref.collection("messages").get();
        messageReads += msgs.size;
        for (const m of msgs.docs) {
          const d = m.data();
          if (d.senderId && d.senderId !== "system" && d.senderId !== u.id && !(d.readBy ?? []).includes(u.id)) n++;
        }
      }
      if (n > 0) counts.set(u.id, n);
    }
    return { counts, messageReads, roomReads };
  },
};

const newPort: Port = {
  async hasAnyUnread(uid) {
    const rooms = await db.collection("chat_rooms").where("participantIds", "array-contains", uid).get();
    return { value: rooms.docs.some((r) => unreadCountFor(r.data(), uid) > 0), reads: rooms.size };
  },
  async roomUnread(roomId, uid) {
    const snap = await db.collection("chat_rooms").doc(roomId).get();
    return { value: unreadCountFor(snap.data(), uid), reads: 1 };
  },
  async openRoom(roomId) {
    const page = await db.collection("chat_rooms").doc(roomId).collection("messages").orderBy("createdAt", "desc").limit(PAGE_SIZE).get();
    return { loaded: page.size, reads: page.size };
  },
  async markRead(roomId, uid) {
    // The client's one room-level write (own keys only).
    await db.collection("chat_rooms").doc(roomId).update(
      new FieldPath("unreadCounts", uid), 0,
      new FieldPath("lastReadAt", uid), FieldValue.serverTimestamp()
    );
    return { writes: 1 };
  },
  async digest() {
    const { targets, roomsScanned } = await collectDailyUnreadDigest(db, { pageSize: 25 });
    const counts = new Map<string, number>();
    for (const [uid, t] of targets) counts.set(uid, t.unreadCount);
    return { counts, messageReads: 0, roomReads: roomsScanned };
  },
};

const port: Port = PORT === "legacy" ? legacyPort : newPort;

/** Seeds N rooms × M messages for `me` (peer sends everything, all unread). */
async function seedWorld(me: string, rooms: number, messagesPerRoom: number) {
  const roomIds: string[] = [];
  for (let r = 0; r < rooms; r++) {
    const peer = fresh("peer");
    const roomId = fresh("room");
    await seedRoom(roomId, [me, peer]);
    for (let i = 0; i < messagesPerRoom; i++) {
      const ref = await seedMessage(roomId, peer, i);
      await fireTrigger(roomId, ref.id);
    }
    roomIds.push(roomId);
  }
  return roomIds;
}

// ---------------------------------------------------------------------------
// TEST P0-2-A — unread badge must not scan message history
// ---------------------------------------------------------------------------

test(`[${PORT}] P0-2-A: badge reads grow with rooms, not with message history`, async () => {
  const me = fresh("me");
  const small = await seedWorld(me, 3, 5);
  for (const r of small) await port.markRead(r, me);
  const readAll = await port.hasAnyUnread(me);
  assert.equal(readAll.value, false);
  const baseline = readAll.reads;

  // Grow history 10x in the same rooms (still all read).
  for (const r of small) {
    for (let i = 100; i < 150; i++) {
      const peerId = (await room(r)).participantIds as string[];
      const ref = await seedMessage(r, peerId.find((p) => p !== me)!, i, { readBy: [peerId.find((p) => p !== me)!, me] });
      await fireTrigger(r, ref.id);
    }
    // The trigger counted the 50 new messages for me; re-mark read to make
    // "all read" true again under the new model as well.
    await port.markRead(r, me);
  }
  const grown = await port.hasAnyUnread(me);
  assert.equal(grown.value, false);
  assert.ok(
    grown.reads <= baseline + 1,
    `badge reads must not grow with history: baseline=${baseline} after 10x history=${grown.reads}`
  );
});

// ---------------------------------------------------------------------------
// TEST P0-2-B — mark read must be bounded (600 unread)
// ---------------------------------------------------------------------------

test(`[${PORT}] P0-2-B: marking a room with 600 unread messages read is a bounded operation`, async () => {
  const me = fresh("me");
  const peer = fresh("peer");
  const roomId = fresh("room600");
  await seedRoom(roomId, [me, peer]);
  const writes = db.bulkWriter();
  const createdBase = 1_700_000_000_000;
  for (let i = 0; i < 600; i++) {
    const ref = db.collection("chat_rooms").doc(roomId).collection("messages").doc();
    const createdAt = Timestamp.fromMillis(createdBase + i * 1000);
    void writes.set(ref, { senderId: peer, text: `m${i}`, type: "text", readBy: [peer], createdAt, updatedAt: createdAt });
  }
  await writes.close();
  // New model: the backfill (or trigger) establishes the counter.
  if (PORT === "new") {
    const r = await backfillRoomUnread(db, roomId, { dryRun: false });
    assert.equal(r.counts[me], 600);
  }
  let result: { writes: number } | null = null;
  let error: unknown = null;
  try {
    result = await port.markRead(roomId, me);
  } catch (e) {
    error = e;
  }
  assert.equal(error, null, `markRead must not fail: ${String(error)}`);
  assert.ok(result && result.writes <= 2, `markRead must be bounded, got ${result?.writes} writes`);
  const after = await port.roomUnread(roomId, me);
  assert.equal(after.value, 0);
});

// ---------------------------------------------------------------------------
// TEST P0-2-C / D — initial room load is paginated, pages are gap-free
// ---------------------------------------------------------------------------

test(`[${PORT}] P0-2-C: opening a room loads at most one page`, async () => {
  const me = fresh("me");
  const [roomId] = await seedWorld(me, 1, 120);
  const opened = await port.openRoom(roomId);
  assert.ok(opened.loaded <= PAGE_SIZE, `initial load must be ≤ ${PAGE_SIZE}, got ${opened.loaded}`);
});

test("P0-2-D: cursor pagination returns every message exactly once in order", async () => {
  const me = fresh("me");
  const [roomId] = await seedWorld(me, 1, 125);
  const col = db.collection("chat_rooms").doc(roomId).collection("messages");
  const seen: string[] = [];
  let cursor: FirebaseFirestore.QueryDocumentSnapshot | null = null;
  for (let page = 0; page < 10; page++) {
    let q = col.orderBy("createdAt", "desc").orderBy(FieldPath.documentId(), "desc").limit(PAGE_SIZE);
    if (cursor) q = q.startAfter(cursor);
    const snap = await q.get();
    if (snap.empty) break;
    for (const d of snap.docs) seen.push(d.id);
    cursor = snap.docs[snap.docs.length - 1];
    if (snap.size < PAGE_SIZE) break;
  }
  assert.equal(seen.length, 125, "no gaps");
  assert.equal(new Set(seen).size, 125, "no duplicates");
  const all = await col.orderBy("createdAt", "desc").orderBy(FieldPath.documentId(), "desc").get();
  assert.deepEqual(seen, all.docs.map((d) => d.id), "deterministic ordering across pages");
});

// ---------------------------------------------------------------------------
// TEST P0-2-E / F — recipient accounting
// ---------------------------------------------------------------------------

test("P0-2-E: 1:1 — a message increments the recipient only", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("room");
  await seedRoom(roomId, [a, b]);
  const ref = await seedMessage(roomId, a, 0);
  const res = await fireTrigger(roomId, ref.id);
  assert.deepEqual(res, { applied: true, reason: "applied", recipients: [b], alreadyRead: [] });
  const r = await room(roomId);
  assert.equal(unreadCountFor(r, a), 0);
  assert.equal(unreadCountFor(r, b), 1);
  assert.equal(r.unreadModelVersion, 1);
});

test("P0-2-F: six-person room — sender excluded, the other five increment exactly once", async () => {
  const uids = Array.from({ length: 6 }, () => fresh("g"));
  const roomId = fresh("group");
  await seedRoom(roomId, uids);
  const ref = await seedMessage(roomId, uids[2], 0);
  await fireTrigger(roomId, ref.id);
  const r = await room(roomId);
  for (const u of uids) assert.equal(unreadCountFor(r, u), u === uids[2] ? 0 : 1, u);
  // A system message counts for all six.
  const sys = await seedMessage(roomId, "system", 1);
  await fireTrigger(roomId, sys.id);
  const r2 = await room(roomId);
  for (const u of uids) assert.equal(unreadCountFor(r2, u), u === uids[2] ? 1 : 2, u);
});

// ---------------------------------------------------------------------------
// TEST P0-2-G — mark-read / new-message race (both interleavings)
// ---------------------------------------------------------------------------

test("P0-2-G: message before markRead → 0; message after markRead → 1", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("room");
  await seedRoom(roomId, [a, b]);
  const m1 = await seedMessage(roomId, a, 0);
  await fireTrigger(roomId, m1.id);
  await newPort.markRead(roomId, b);
  assert.equal(unreadCountFor(await room(roomId), b), 0);
  const m2 = await seedMessage(roomId, a, 1);
  await fireTrigger(roomId, m2.id);
  assert.equal(unreadCountFor(await room(roomId), b), 1);
  // Concurrent: markRead and an increment racing on the room doc never lose
  // the increment (increment is atomic; the reset only zeroes what existed).
  const m3 = await seedMessage(roomId, a, 2);
  await Promise.all([newPort.markRead(roomId, b), fireTrigger(roomId, m3.id)]);
  const final = unreadCountFor(await room(roomId), b);
  assert.ok(final === 0 || final === 1, `race must end at 0 or 1, got ${final}`);
  // The message is accounted exactly once regardless of ordering.
  const marked = (await m3.get()).data()?.unreadAccountedAt;
  assert.ok(marked, "message carries the accounting marker");
});

// ---------------------------------------------------------------------------
// TEST P0-2-H — at-least-once trigger delivery / idempotency
// ---------------------------------------------------------------------------

test("P0-2-H: duplicate trigger delivery (sequential and concurrent) counts once", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("room");
  await seedRoom(roomId, [a, b]);
  const m = await seedMessage(roomId, a, 0);
  const first = await fireTrigger(roomId, m.id);
  const second = await fireTrigger(roomId, m.id);
  assert.equal(first.applied, true);
  assert.deepEqual(second, { applied: false, reason: "already_accounted", recipients: [], alreadyRead: [] });
  assert.equal(unreadCountFor(await room(roomId), b), 1);

  const m2 = await seedMessage(roomId, a, 1);
  const results = await Promise.all([fireTrigger(roomId, m2.id), fireTrigger(roomId, m2.id), fireTrigger(roomId, m2.id)]);
  assert.equal(results.filter((r) => r.applied).length, 1, "exactly one concurrent delivery applies");
  assert.equal(unreadCountFor(await room(roomId), b), 2);
});

test("P0-2-H2: 20 concurrent messages lose no increments", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("room");
  await seedRoom(roomId, [a, b]);
  const refs = await Promise.all(Array.from({ length: 20 }, (_, i) => seedMessage(roomId, a, i)));
  await Promise.all(refs.map((r) => fireTrigger(roomId, r.id)));
  assert.equal(unreadCountFor(await room(roomId), b), 20);
  assert.equal(unreadCountFor(await room(roomId), a), 0);
});

// ---------------------------------------------------------------------------
// TEST P0-2-I — same user, two devices
// ---------------------------------------------------------------------------

test("P0-2-I: two devices marking read concurrently never corrupt the peer's counter", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("room");
  await seedRoom(roomId, [a, b]);
  const m1 = await seedMessage(roomId, a, 0);
  await fireTrigger(roomId, m1.id);
  const m2 = await seedMessage(roomId, b, 1);
  await fireTrigger(roomId, m2.id);
  // a has 1 unread (m2), b has 1 unread (m1). b reads on two devices at once.
  await Promise.all([newPort.markRead(roomId, b), newPort.markRead(roomId, b)]);
  const r = await room(roomId);
  assert.equal(unreadCountFor(r, b), 0);
  assert.equal(unreadCountFor(r, a), 1, "the other participant's counter is untouched");
  assert.ok((r.lastReadAt as Record<string, unknown>)[b], "lastReadAt recorded for b");
});

// ---------------------------------------------------------------------------
// TEST P0-2-J / backfill — legacy rooms
// ---------------------------------------------------------------------------

test("P0-2-J: a legacy room (readBy only) reads as 0 unread under the new model until backfilled, then matches the legacy count", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("legacy");
  await seedRoom(roomId, [a, b]);
  // 7 from a (unread for b), 3 from b read by a, 2 system (unread for both)
  for (let i = 0; i < 7; i++) await seedMessage(roomId, a, i);
  for (let i = 7; i < 10; i++) await seedMessage(roomId, b, i, { readBy: [b, a] });
  for (let i = 10; i < 12; i++) await seedMessage(roomId, "system", i);
  const legacyA = await legacyPort.roomUnread(roomId, a);
  const legacyB = await legacyPort.roomUnread(roomId, b);
  assert.equal(legacyA.value, 2);
  assert.equal(legacyB.value, 9);
  const before = await room(roomId);
  assert.equal(before.unreadModelVersion, undefined);
  assert.equal(unreadCountFor(before, b), 0);

  const dry = await backfillRoomUnread(db, roomId, { dryRun: true });
  assert.deepEqual(dry.counts, { [a]: 2, [b]: 9 });
  assert.equal(dry.writes, 0);
  assert.equal((await room(roomId)).unreadModelVersion, undefined, "dry-run writes nothing");

  const applied = await backfillRoomUnread(db, roomId, { dryRun: false });
  assert.deepEqual(applied.counts, { [a]: 2, [b]: 9 });
  const after = await room(roomId);
  assert.equal(unreadCountFor(after, a), 2);
  assert.equal(unreadCountFor(after, b), 9);
  assert.equal(after.unreadModelVersion, 1);
  assert.ok(after.unreadBackfilledAt);
  assert.deepEqual(checkRoomUnreadIntegrity(roomId, after), []);

  // Idempotent: a second run is a no-op.
  const again = await backfillRoomUnread(db, roomId, { dryRun: false });
  assert.equal(again.skipped, "already_backfilled");
  assert.equal(unreadCountFor(await room(roomId), b), 9);
});

test("backfill: messages the trigger already accounted are not counted twice, and >400 messages chunk safely", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("big");
  await seedRoom(roomId, [a, b]);
  const writer = db.bulkWriter();
  const base = 1_700_000_000_000;
  for (let i = 0; i < 900; i++) {
    const ref = db.collection("chat_rooms").doc(roomId).collection("messages").doc();
    const createdAt = Timestamp.fromMillis(base + i * 1000);
    void writer.set(ref, { senderId: a, text: `m${i}`, type: "text", readBy: [a], createdAt, updatedAt: createdAt });
  }
  await writer.close();
  // 5 post-deploy messages already accounted by the trigger.
  for (let i = 900; i < 905; i++) {
    const ref = await seedMessage(roomId, a, i);
    await fireTrigger(roomId, ref.id);
  }
  assert.equal(unreadCountFor(await room(roomId), b), 5);
  const result = await backfillRoomUnread(db, roomId, { dryRun: false });
  assert.equal(result.messagesInspected, 905);
  assert.equal(result.messagesCounted, 900);
  assert.ok(result.chunks >= 3, `expected chunking, got ${result.chunks}`);
  assert.equal(unreadCountFor(await room(roomId), b), 905);
  assert.equal(unreadCountFor(await room(roomId), a), 0);
});

test("backfill run: paged, resumable by checkpoint, bounded by --limit", async () => {
  // Isolate: this run id only touches rooms created here via startAfter.
  const prefix = fresh("zz_run");
  const ids = [1, 2, 3].map((i) => `${prefix}_${i}`);
  const a = fresh("a"), b = fresh("b");
  for (const id of ids) {
    await seedRoom(id, [a, b]);
    await seedMessage(id, a, 0);
  }
  const cp = fresh("cp");
  const first = await runChatUnreadBackfill(db, {
    dryRun: false, limitRooms: 2, checkpointId: cp, startAfterRoomId: `${prefix}_0`, pageSize: 2,
  });
  assert.equal(first.roomsVisited, 2);
  assert.equal(first.roomsBackfilled, 2);
  assert.equal(first.completed, false);
  const cpDoc = (await db.collection("chatUnreadBackfillRuns").doc(cp).get()).data();
  assert.equal(cpDoc?.lastRoomId, ids[1]);
  const second = await runChatUnreadBackfill(db, { dryRun: false, limitRooms: 10, checkpointId: cp, pageSize: 2 });
  assert.equal(second.roomsVisited >= 1, true);
  assert.ok(ids.every(() => true));
  for (const id of ids) assert.equal(unreadCountFor(await room(id), b), 1, id);
  // Rerunning over the same rooms is a no-op (already_backfilled).
  const third = await runChatUnreadBackfill(db, { dryRun: false, limitRooms: 3, startAfterRoomId: `${prefix}_0`, pageSize: 2 });
  assert.equal(third.roomsSkippedAlready, 3);
});

// ---------------------------------------------------------------------------
// TEST P0-2-L — daily digest must not scan message documents
// ---------------------------------------------------------------------------

test(`[${PORT}] P0-2-L: digest reads scale with rooms, never with message history`, async () => {
  const u1 = fresh("du1"), u2 = fresh("du2");
  await db.collection("users").doc(u1).set({ kakaoUserId: u1 });
  await db.collection("users").doc(u2).set({ kakaoUserId: u2 });
  const roomId = fresh("droom");
  await seedRoom(roomId, [u1, u2]);
  for (let i = 0; i < 60; i++) {
    const ref = await seedMessage(roomId, u1, i);
    await fireTrigger(roomId, ref.id);
  }
  const d = await port.digest();
  assert.equal(d.counts.get(u2), 60, "u2 has 60 unread from u1");
  assert.equal(d.counts.has(u1), false, "sender has none");
  assert.equal(d.messageReads, 0, `digest must read 0 message documents, read ${d.messageReads}`);
});

// ---------------------------------------------------------------------------
// TEST P0-2-K — delayed trigger after mark-read (read high-water mark)
//
// The trigger runs asynchronously after the message commit. If the recipient
// marks the room read in between (the message was on screen), the late
// increment must NOT resurrect an unread. Strict correctness, per user u:
//   unreadCounts[u] == |{ m : m.senderId != u && m.commitTime > lastReadAt[u] }|
// Interleavings A–G below drive the trigger by hand, so each order is
// deterministic. Commit times are the emulator's; mark-read uses the server
// timestamp, so a 5 ms gap keeps the clock strictly ordered.
// ---------------------------------------------------------------------------

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function expectedUnread(roomId: string, uid: string): Promise<number> {
  const r = await room(roomId);
  const readAt = (r.lastReadAt as Record<string, Timestamp> | undefined)?.[uid];
  const msgs = await db.collection("chat_rooms").doc(roomId).collection("messages").get();
  return msgs.docs.filter((d) => {
    const data = d.data();
    if (data.senderId === uid) return false;
    return !readAt || !timestampAtOrAfter(readAt, d.createTime);
  }).length;
}

test("P0-2-K-A: trigger, then markRead → 0 (reset wins; baseline)", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("k");
  await seedRoom(roomId, [a, b]);
  const m = await seedMessage(roomId, a, 0);
  await fireTrigger(roomId, m.id);
  await newPort.markRead(roomId, b);
  assert.equal(unreadCountFor(await room(roomId), b), 0);
  assert.equal(await expectedUnread(roomId, b), 0);
});

test("P0-2-K-B: message committed, recipient marks read, THEN the delayed trigger runs → 0, no phantom", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("k");
  await seedRoom(roomId, [a, b]);
  const m = await seedMessage(roomId, a, 0);
  await sleep(5);
  await newPort.markRead(roomId, b);
  const result = await fireTrigger(roomId, m.id);
  assert.equal(unreadCountFor(await room(roomId), b), 0, "phantom unread");
  assert.deepEqual({ applied: result.applied, reason: result.reason, alreadyRead: result.alreadyRead }, {
    applied: false,
    reason: "no_recipients",
    alreadyRead: [b],
  });
  assert.ok((await m.get()).data()?.unreadAccountedAt, "still marked accounted (redelivery stays a no-op)");
  assert.equal(await expectedUnread(roomId, b), 0);
});

test("P0-2-K-C: markRead, then a message commits, then its trigger → 1", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("k");
  await seedRoom(roomId, [a, b]);
  await newPort.markRead(roomId, b);
  await sleep(5);
  const m = await seedMessage(roomId, a, 0);
  const result = await fireTrigger(roomId, m.id);
  assert.deepEqual(result.recipients, [b]);
  assert.equal(unreadCountFor(await room(roomId), b), 1);
  assert.equal(await expectedUnread(roomId, b), 1);
});

test("P0-2-K-D: two messages on screen, one mark-read, both triggers late → 0", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("k");
  await seedRoom(roomId, [a, b]);
  const m1 = await seedMessage(roomId, a, 0);
  const m2 = await seedMessage(roomId, a, 1);
  await sleep(5);
  await newPort.markRead(roomId, b);
  await fireTrigger(roomId, m2.id);
  await fireTrigger(roomId, m1.id);
  assert.equal(unreadCountFor(await room(roomId), b), 0);
  assert.equal(await expectedUnread(roomId, b), 0);
});

test("P0-2-K-E: m1 read, m2 after the read; triggers delivered out of order (m2, then m1) → 1", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("k");
  await seedRoom(roomId, [a, b]);
  const m1 = await seedMessage(roomId, a, 0);
  await sleep(5);
  await newPort.markRead(roomId, b);
  await sleep(5);
  const m2 = await seedMessage(roomId, a, 1);
  await fireTrigger(roomId, m2.id);
  await fireTrigger(roomId, m1.id);
  assert.equal(unreadCountFor(await room(roomId), b), 1);
  assert.equal(await expectedUnread(roomId, b), 1);
});

test("P0-2-K-F: trigger, markRead, trigger redelivered → 0 (a redelivery never resurrects)", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("k");
  await seedRoom(roomId, [a, b]);
  const m = await seedMessage(roomId, a, 0);
  await fireTrigger(roomId, m.id);
  await sleep(5);
  await newPort.markRead(roomId, b);
  const again = await fireTrigger(roomId, m.id);
  assert.equal(again.reason, "already_accounted");
  assert.equal(unreadCountFor(await room(roomId), b), 0);
});

test("P0-2-K-G: group room — only the member who read after the commit is skipped", async () => {
  const members = ["g1", "g2", "g3", "g4", "g5", "g6"].map((m) => fresh(m));
  const roomId = fresh("kgroup");
  await seedRoom(roomId, members);
  const m = await seedMessage(roomId, members[0], 0);
  await sleep(5);
  await newPort.markRead(roomId, members[1]);
  await newPort.markRead(roomId, members[2]);
  const result = await fireTrigger(roomId, m.id);
  assert.deepEqual(result.alreadyRead, [members[1], members[2]]);
  assert.deepEqual(result.recipients, [members[3], members[4], members[5]]);
  const r = await room(roomId);
  for (const [i, uid] of members.entries()) {
    const expected = i === 0 || i === 1 || i === 2 ? 0 : 1;
    assert.equal(unreadCountFor(r, uid), expected, `member ${i}`);
    assert.equal(await expectedUnread(roomId, uid), expected, `invariant member ${i}`);
  }
});

test("P0-2-K-H: garbage lastReadAt fails toward counting", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("k");
  await seedRoom(roomId, [a, b], { lastReadAt: { [b]: "2099-01-01" } });
  const m = await seedMessage(roomId, a, 0);
  await fireTrigger(roomId, m.id);
  assert.equal(unreadCountFor(await room(roomId), b), 1);
});

test("P0-2-K-I: mark-read racing the delayed trigger, 10 rounds — always 0 (message committed before the read)", async () => {
  const a = fresh("a"), b = fresh("b"), roomId = fresh("k");
  await seedRoom(roomId, [a, b]);
  for (let i = 0; i < 10; i += 1) {
    const m = await seedMessage(roomId, a, i);
    await sleep(2);
    await Promise.all([newPort.markRead(roomId, b), fireTrigger(roomId, m.id)]);
    assert.equal(unreadCountFor(await room(roomId), b), 0, `round ${i}`);
    assert.equal(await expectedUnread(roomId, b), 0, `invariant round ${i}`);
  }
});
