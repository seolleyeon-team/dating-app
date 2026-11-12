/**
 * P1-13 — the server-observed season schedule (onSeasonMeetingPromiseWritten)
 * on the real Firestore engine, and the no-show path end to end through it.
 *
 * Run (repo root, JDK 21):
 *   ./functions/node_modules/.bin/tsc -p functions --outDir functions/.p113-lib
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore --project demo-p113-lock \
 *     "node --test functions/.p113-lib/seasonMeetingScheduleLock.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-p113-lock" });

import { createSeasonMeetingReportNoShowFunction } from "./seasonMeetingOperations";
import { createSeasonScheduleLockTrigger, reconcileSeasonScheduleLock } from "./seasonMeetingScheduleLock";

const db = getFirestore();
type Runner = { run: (request: unknown) => Promise<unknown> };
const noShowFn = createSeasonMeetingReportNoShowFunction(db, async (auth) => ({ userId: auth?.uid ?? "" })) as unknown as Runner;
const trigger = createSeasonScheduleLockTrigger(db) as unknown as Runner;
let seq = 0;
const fresh = (p: string) => `${p}${Date.now().toString(36)}${++seq}`;
const MIN = 60 * 1000;
const HOUR = 60 * MIN;

async function seed() {
  const matchId = fresh("m");
  const roomId = `season_${matchId}`;
  const promiseId = fresh("p");
  const left = [fresh("l"), fresh("l"), fresh("l")];
  const right = [fresh("r"), fresh("r"), fresh("r")];
  const all = [...left, ...right].sort();
  for (const uid of all) await db.collection("users").doc(uid).set({ dataPartition: "production" });
  await db.collection("eventThreeVsThreeMatches").doc(matchId).set({
    leftMemberUids: left, rightMemberUids: right, participantUids: all,
    eventType: "season_meeting", seasonPhase: "matched", chatRoomId: roomId, status: "active",
  });
  await db.collection("chat_rooms").doc(roomId).set({ participantIds: all, activePromise: { promiseId } });
  return { matchId, roomId, promiseId, left, right };
}
const promiseRef = (s: { roomId: string; promiseId: string }) => db.collection("chat_rooms").doc(s.roomId).collection("promises").doc(s.promiseId);
const lockOf = async (matchId: string) => (await db.collection("eventThreeVsThreeMatches").doc(matchId).collection("serverState").doc("schedule").get()).data();
const fire = (roomId: string, promiseId: string) => trigger.run({ params: { roomId, promiseId }, data: {}, time: new Date().toISOString() });

test("L1 only a confirmed time is observed, with the server's clock", async () => {
  const s = await seed();
  await promiseRef(s).set({ status: "requested", dateTime: Timestamp.fromMillis(Date.now() + 3 * HOUR) });
  assert.equal(await reconcileSeasonScheduleLock(db, s.roomId, s.promiseId), "noop");
  assert.equal(await lockOf(s.matchId), undefined);
  const before = Date.now();
  await promiseRef(s).set({ status: "confirmed" }, { merge: true });
  assert.equal(await reconcileSeasonScheduleLock(db, s.roomId, s.promiseId), "observed");
  const lock = await lockOf(s.matchId);
  assert.equal(lock?.promiseId, s.promiseId);
  assert.ok((lock?.observedAt as Timestamp).toMillis() >= before - 5000);
  assert.equal(lock?.version, 1);
});

test("L2 stamps / repeats keep the first observation; a moved time is a new one; cancelling releases it", async () => {
  const s = await seed();
  const start = Date.now() + 3 * HOUR;
  await promiseRef(s).set({ status: "confirmed", dateTime: Timestamp.fromMillis(start) });
  await fire(s.roomId, s.promiseId);
  const first = await lockOf(s.matchId);
  await promiseRef(s).set({ safetyStamp: { meetupStampedUserIds: [s.left[0]], stampedForDateTimeMs: start } }, { merge: true });
  assert.equal(await reconcileSeasonScheduleLock(db, s.roomId, s.promiseId), "unchanged");
  assert.deepEqual(await lockOf(s.matchId), first);
  await promiseRef(s).set({ dateTime: Timestamp.fromMillis(start + HOUR) }, { merge: true });
  assert.equal(await reconcileSeasonScheduleLock(db, s.roomId, s.promiseId), "observed");
  const moved = await lockOf(s.matchId);
  assert.equal(moved?.version, 2);
  assert.equal(moved?.meetupStartAtMs, start + HOUR);
  await promiseRef(s).set({ status: "cancelled" }, { merge: true });
  assert.equal(await reconcileSeasonScheduleLock(db, s.roomId, s.promiseId), "released");
  assert.equal(await lockOf(s.matchId), undefined);
});

test("L3 non-season rooms, unlinked matches and inactive promises are ignored", async () => {
  assert.equal(await reconcileSeasonScheduleLock(db, "dm_a_b", "p1"), "not_season_room");
  const s = await seed();
  await db.collection("eventThreeVsThreeMatches").doc(s.matchId).update({ chatRoomId: "season_elsewhere" });
  await promiseRef(s).set({ status: "confirmed", dateTime: Timestamp.fromMillis(Date.now() + HOUR) });
  assert.equal(await reconcileSeasonScheduleLock(db, s.roomId, s.promiseId), "not_linked");
  const t = await seed();
  const other = fresh("p");
  await db.collection("chat_rooms").doc(t.roomId).collection("promises").doc(other).set({ status: "confirmed", dateTime: Timestamp.fromMillis(Date.now() + HOUR) });
  assert.equal(await reconcileSeasonScheduleLock(db, t.roomId, other), "not_active_promise");
  assert.equal(await lockOf(t.matchId), undefined);
});

test("L4 [attack, end to end] a schedule confirmed or moved into the past cannot support a no-show report", async () => {
  const s = await seed();
  await promiseRef(s).set({ status: "confirmed", dateTime: Timestamp.fromMillis(Date.now() - 2 * HOUR) });
  await fire(s.roomId, s.promiseId);
  await assert.rejects(
    noShowFn.run({ data: { meetingId: s.matchId, accusedUid: s.right[0] }, auth: { uid: s.left[1], token: {} }, rawRequest: {} }),
    (e: { code?: string; message?: string }) => e.code === "failed-precondition" && /schedule_fixed_after_start/.test(e.message ?? ""),
  );
});

test("L5 a schedule observed before the meeting supports a report after the grace period", async () => {
  const s = await seed();
  const start = Date.now() + 2 * MIN;
  await promiseRef(s).set({ status: "confirmed", dateTime: Timestamp.fromMillis(start) });
  await fire(s.roomId, s.promiseId);
  // Time passes: the meeting started 16 minutes ago (lock observed before it).
  const lockRef = db.collection("eventThreeVsThreeMatches").doc(s.matchId).collection("serverState").doc("schedule");
  const shifted = start - 18 * MIN;
  await promiseRef(s).set({ dateTime: Timestamp.fromMillis(shifted) }, { merge: true });
  await lockRef.update({ meetupStartAtMs: shifted, observedAt: Timestamp.fromMillis(shifted - HOUR) });
  const result = (await noShowFn.run({ data: { meetingId: s.matchId, accusedUid: s.right[0] }, auth: { uid: s.left[1], token: {} }, rawRequest: {} })) as Record<string, unknown>;
  assert.equal(result.status, "no_show_reported");
});
