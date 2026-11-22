/**
 * B-12 — submitSafetyStamp decides the stamp window with the SERVER clock, on
 * the real Firestore engine.
 *
 * The window (10 minutes before the promise time to 1 hour after; the goodbye
 * stamp within 24 hours of the server-recorded meetup completion) used to be
 * checked only by the client with the device clock. A caller could stamp
 * "arrived" days before the meeting, and that stamp is what the season
 * meeting no-show decision trusts.
 *
 * Run (repo root, JDK 21):
 *   ./functions/node_modules/.bin/tsc -p functions --outDir functions/.audit-lib
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore --project demo-b12 \
 *     "node --test functions/.audit-lib/safetyStamp.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getApps, initializeApp } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
if (getApps().length === 0) {
  initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-b12" });
}

import { submitSafetyStamp } from "./safetyStamp";

type Runnable = { run: (request: unknown) => Promise<unknown> };
type StampResult = { ok: true; alreadyStamped: boolean; phase: string; phaseCompleted: boolean };

const db = getFirestore();
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

const A = "b12_a";
const B = "b12_b";
const OUTSIDER = "b12_outsider";

function stamp(uid: string, data: Record<string, unknown>) {
  return (submitSafetyStamp as unknown as Runnable).run({
    data,
    auth: { uid, token: {} },
    rawRequest: {},
  }) as Promise<StampResult>;
}

async function failure(promise: Promise<unknown>): Promise<{ code: string; reason: string }> {
  try {
    await promise;
  } catch (error) {
    const e = error as { code?: string; details?: { reason?: string } };
    return { code: String(e.code), reason: String(e.details?.reason ?? "") };
  }
  return { code: "ok", reason: "" };
}

async function seedPromise(params: {
  startOffsetMs: number;
  status?: string;
  safetyStamp?: Record<string, unknown>;
  extra?: Record<string, unknown>;
  active?: boolean;
}) {
  const roomId = fresh("room");
  const promiseId = fresh("promise");
  const dateTime = Timestamp.fromMillis(Date.now() + params.startOffsetMs);
  const status = params.status ?? "confirmed";
  const room = db.collection("chat_rooms").doc(roomId);
  // NEW-24: the callable reads the caller's account state on every call.
  await Promise.all(
    [A, B, OUTSIDER].map((uid) => db.collection("users").doc(uid).set({ status: "active", isActive: true })),
  );
  await room.set({
    roomId,
    participantIds: [A, B],
    ...(params.active === false
      ? {}
      : { activePromise: { promiseId, dateTime, place: "신촌", placeCategory: "cafe", status } }),
  });
  await room.collection("promises").doc(promiseId).set({
    promiseId,
    requestedBy: A,
    requestedTo: B,
    dateTime,
    place: "신촌",
    placeCategory: "cafe",
    status,
    ...(params.safetyStamp ? { safetyStamp: params.safetyStamp } : {}),
    ...(params.extra ?? {}),
  });
  return { roomId, promiseId, dateTime, ref: room.collection("promises").doc(promiseId), room };
}

test("B-12: inside the window both participants stamp and the server records the meetup with its own clock", async () => {
  const p = await seedPromise({ startOffsetMs: 5 * MINUTE });
  const first = await stamp(A, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" });
  assert.deepEqual({ ...first }, { ok: true, alreadyStamped: false, phase: "meetup", phaseCompleted: false });
  const before = Date.now();
  const second = await stamp(B, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" });
  assert.equal(second.phaseCompleted, true);
  const data = (await p.ref.get()).data() ?? {};
  assert.equal(data.status, "in_progress");
  const completedMs = (data.meetupCompletedAt as Timestamp).toMillis();
  assert.ok(Math.abs(completedMs - before) < MINUTE, "meetupCompletedAt is the server time of the write");
  assert.equal(data.safetyStamp.stampedForDateTimeMs, p.dateTime.toMillis());
});

test("B-12: device clock in the future — an arrival stamp days or hours before the meeting is refused and nothing is written", async () => {
  for (const startOffsetMs of [3 * DAY, 2 * HOUR, 20 * MINUTE]) {
    const p = await seedPromise({ startOffsetMs });
    // Whatever the client claims about time is ignored.
    const refused = await failure(stamp(A, {
      roomId: p.roomId,
      promiseId: p.promiseId,
      phase: "meetup",
      clientNowMs: p.dateTime.toMillis(),
      now: new Date(p.dateTime.toMillis()).toISOString(),
      verification: { verifiedAt: new Date(p.dateTime.toMillis()).toISOString(), method: "ble" },
    }));
    assert.deepEqual(refused, { code: "failed-precondition", reason: "too_early" });
    const data = (await p.ref.get()).data() ?? {};
    assert.equal(data.safetyStamp, undefined);
    assert.equal(data.status, "confirmed");
    assert.equal(((await p.room.get()).data() ?? {}).activePromise.safetyStamp, undefined);
  }
});

test("B-12: device clock in the past / safety stamp expiry — an arrival stamp after promise time + 1 hour is refused", async () => {
  for (const startOffsetMs of [-(HOUR + 10 * MINUTE), -5 * HOUR, -3 * DAY]) {
    const p = await seedPromise({ startOffsetMs });
    assert.deepEqual(
      await failure(stamp(A, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" })),
      { code: "failed-precondition", reason: "too_late" },
    );
    assert.equal(((await p.ref.get()).data() ?? {}).safetyStamp, undefined);
  }
  // Still open 50 minutes after the promise time.
  const open = await seedPromise({ startOffsetMs: -50 * MINUTE });
  assert.equal((await stamp(A, { roomId: open.roomId, promiseId: open.promiseId, phase: "meetup" })).ok, true);
});

test("B-12: a retry of a stamp that was already recorded returns the same answer after the window closed", async () => {
  const startMs = Date.now() - 3 * HOUR;
  const p = await seedPromise({
    startOffsetMs: -3 * HOUR,
    safetyStamp: { meetupStampedUserIds: [A], goodbyeStampedUserIds: [], stampedForDateTimeMs: 0 },
  });
  await p.ref.update({ "safetyStamp.stampedForDateTimeMs": (await p.ref.get()).get("dateTime").toMillis() });
  assert.ok(startMs < Date.now());
  const again = await stamp(A, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" });
  assert.equal(again.alreadyStamped, true);
  // The other participant, who never stamped, is too late.
  assert.equal((await failure(stamp(B, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" }))).reason, "too_late");
});

test("B-12: promise time change — stamps for the old time do not carry over and the new time's window applies", async () => {
  const p = await seedPromise({ startOffsetMs: 5 * MINUTE });
  await stamp(A, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" });
  // The promise is re-requested for next week and accepted again (server-side
  // equivalent of chat_service updatePromise + acceptPromise).
  const moved = Timestamp.fromMillis(Date.now() + 7 * DAY);
  await p.ref.update({ dateTime: moved, status: "confirmed" });
  await p.room.update({ "activePromise.dateTime": moved });
  assert.deepEqual(
    await failure(stamp(B, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" })),
    { code: "failed-precondition", reason: "too_early" },
  );
  // A's stamp was for the old time: re-sending it is not "already stamped".
  assert.deepEqual(
    await failure(stamp(A, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" })),
    { code: "failed-precondition", reason: "too_early" },
  );
});

test("B-12: an unconfirmed, cancelled or time-less promise accepts no stamp", async () => {
  const requested = await seedPromise({ startOffsetMs: 5 * MINUTE, status: "requested" });
  assert.equal((await failure(stamp(A, { roomId: requested.roomId, promiseId: requested.promiseId, phase: "meetup" }))).code, "failed-precondition");
  const cancelled = await seedPromise({ startOffsetMs: 5 * MINUTE, status: "cancelled" });
  assert.equal((await failure(stamp(A, { roomId: cancelled.roomId, promiseId: cancelled.promiseId, phase: "meetup" }))).code, "failed-precondition");
  const noTime = await seedPromise({ startOffsetMs: 5 * MINUTE });
  await noTime.ref.update({ dateTime: "2026-11-22T10:00:00Z" });
  assert.deepEqual(
    await failure(stamp(A, { roomId: noTime.roomId, promiseId: noTime.promiseId, phase: "meetup" })),
    { code: "failed-precondition", reason: "promise_time_missing" },
  );
  for (const p of [requested, cancelled, noTime]) {
    assert.equal(((await p.ref.get()).data() ?? {}).safetyStamp, undefined);
  }
});

test("B-12: goodbye stamp — accepted within 24 hours of the server-recorded meetup, refused afterwards", async () => {
  const completedStamp = (completedMs: number, startMs: number) => ({
    meetupStampedUserIds: [A, B],
    goodbyeStampedUserIds: [],
    stampedForDateTimeMs: startMs,
    meetupCompletedAt: Timestamp.fromMillis(completedMs),
  });
  const now = Date.now();
  const recent = await seedPromise({ startOffsetMs: -2 * HOUR, status: "in_progress" });
  await recent.ref.update({
    safetyStamp: completedStamp(now - 2 * HOUR, recent.dateTime.toMillis()),
    meetupCompletedAt: Timestamp.fromMillis(now - 2 * HOUR),
  });
  assert.equal((await stamp(A, { roomId: recent.roomId, promiseId: recent.promiseId, phase: "goodbye" })).ok, true);
  const done = await stamp(B, { roomId: recent.roomId, promiseId: recent.promiseId, phase: "goodbye" });
  assert.equal(done.phaseCompleted, true);
  assert.equal(((await recent.ref.get()).data() ?? {}).status, "completed");

  const expired = await seedPromise({ startOffsetMs: -30 * HOUR, status: "in_progress" });
  await expired.ref.update({
    safetyStamp: completedStamp(now - 25 * HOUR, expired.dateTime.toMillis()),
    meetupCompletedAt: Timestamp.fromMillis(now - 25 * HOUR),
  });
  assert.deepEqual(
    await failure(stamp(A, { roomId: expired.roomId, promiseId: expired.promiseId, phase: "goodbye" })),
    { code: "failed-precondition", reason: "too_late" },
  );
  assert.deepEqual(((await expired.ref.get()).data() ?? {}).safetyStamp.goodbyeStampedUserIds, []);
});

test("B-12: existing guards still hold (non-participant, wrong active promise, goodbye before meetup)", async () => {
  const p = await seedPromise({ startOffsetMs: 5 * MINUTE });
  assert.equal((await failure(stamp(OUTSIDER, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" }))).code, "permission-denied");
  assert.equal((await failure(stamp(A, { roomId: p.roomId, promiseId: p.promiseId, phase: "goodbye" }))).code, "failed-precondition");
  const inactive = await seedPromise({ startOffsetMs: 5 * MINUTE, active: false });
  assert.equal((await failure(stamp(A, { roomId: inactive.roomId, promiseId: inactive.promiseId, phase: "meetup" }))).code, "failed-precondition");
  assert.equal((await failure(stamp("", { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" }))).code, "unauthenticated");
});

test("NEW-24: a suspended, banned or withdrawn participant cannot stamp, even inside the window, and an account without a document is refused", async () => {
  const p = await seedPromise({ startOffsetMs: 5 * MINUTE });
  const restricted: Array<[Record<string, unknown>, string]> = [
    [{ status: "suspended", loginDisabled: true, isActive: false }, "account_suspended"],
    [{ status: "banned", loginDisabled: true, isActive: false }, "account_banned"],
    [{ status: "deleting", isWithdrawn: true, loginDisabled: true }, "account_withdrawn"],
  ];
  for (const [state, detail] of restricted) {
    await db.collection("users").doc(A).set(state);
    try {
      await stamp(A, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" });
      assert.fail(`${detail} was allowed to stamp`);
    } catch (error) {
      const e = error as { code?: string; details?: { detail?: string } };
      assert.equal(e.code, "permission-denied");
      assert.equal(e.details?.detail, detail);
    }
  }
  assert.equal(((await p.ref.get()).data() ?? {}).safetyStamp, undefined, "a refused stamp wrote nothing");

  // The state is read per call: restoring the account restores the callable.
  await db.collection("users").doc(A).set({ status: "active", isActive: true });
  assert.equal((await stamp(A, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" })).ok, true);

  await db.collection("users").doc(B).delete();
  assert.equal(
    (await failure(stamp(B, { roomId: p.roomId, promiseId: p.promiseId, phase: "meetup" }))).code,
    "failed-precondition",
  );
});
