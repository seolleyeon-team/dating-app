/**
 * P1-13 — season meeting callables on the real Firestore engine.
 *
 * The audited defect: reportSeasonMeetingNoShow trusted the caller's
 * meetupStartAtMs / gracePeriodMs / safetyStartCompleted and any accusedUid,
 * cancelSeasonMeeting let any participant cancel the whole 3:3 match with a
 * caller-chosen refund window and deposit state, and the deposit intent used a
 * caller-chosen global document id (another user's intent was returned).
 *
 * Every authoritative value now comes from server-owned records:
 *   participants      eventThreeVsThreeMatches/{id}.participantUids (+ left/right)
 *   schedule          the season room's confirmed promise, as observed by the
 *                     server at eventThreeVsThreeMatches/{id}/serverState/schedule
 *   check-in          promise.safetyStamp (written only by submitSafetyStamp)
 *   cancel authority  meetingGroups/{teamId}.leaderUid
 *   deposit capture   seasonDepositIntents (server-only)
 *
 * The suite only calls the five callable factories, so it runs unchanged
 * against the vulnerable implementation (the attack tests fail there).
 *
 * Run (repo root, JDK 21):
 *   ./functions/node_modules/.bin/tsc -p functions --outDir functions/.p113-lib
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore --project demo-p113-season \
 *     "node --test functions/.p113-lib/seasonMeetingSecurity.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-p113-season" });

import {
  createSeasonMeetingCancelFunction,
  createSeasonMeetingClaimReplacementFunction,
  createSeasonMeetingDepositIntentFunction,
  createSeasonMeetingRefundFunction,
  createSeasonMeetingReportNoShowFunction,
} from "./seasonMeetingOperations";

const db = getFirestore();
type Runner = { run: (request: unknown) => Promise<unknown> };
const resolve = async (auth: { uid: string } | undefined) => ({ userId: auth?.uid ?? "" });
const noShowFn = createSeasonMeetingReportNoShowFunction(db, resolve) as unknown as Runner;
const cancelFn = createSeasonMeetingCancelFunction(db, resolve) as unknown as Runner;
const depositFn = createSeasonMeetingDepositIntentFunction(db, resolve) as unknown as Runner;
const refundFn = createSeasonMeetingRefundFunction(db, resolve) as unknown as Runner;
const claimFn = createSeasonMeetingClaimReplacementFunction(db, resolve) as unknown as Runner;
const call = (fn: Runner, uid: string, data: Record<string, unknown>) =>
  fn.run({ data, auth: { uid, token: {} }, rawRequest: {} });

let seq = 0;
const fresh = (p: string) => `${p}${Date.now().toString(36)}${++seq}`;
const MIN = 60 * 1000;
const HOUR = 60 * MIN;
const DAY = 24 * HOUR;
const KST = 9 * HOUR;

async function expectCode(promise: Promise<unknown>, code: string, label = "") {
  try {
    await promise;
  } catch (error) {
    assert.equal((error as { code?: string }).code, code, `${label}: ${(error as Error).message}`);
    return (error as Error).message;
  }
  assert.fail(`${label}: expected ${code}, the call succeeded`);
}

type Seed = {
  matchId: string;
  roomId: string;
  promiseId: string;
  left: string[];
  right: string[];
  all: string[];
  leftLeader: string;
  rightLeader: string;
};

type SeedOptions = {
  phase?: string;
  /** null: no promise at all. */
  meetupStartAtMs?: number | null;
  promiseStatus?: string;
  /** Server observation time of the schedule; null: never observed. */
  observedAtMs?: number | null;
  meetupStampedUserIds?: string[];
  meetupCompleted?: boolean;
  partitionOf?: Record<string, string>;
  matchOverrides?: Record<string, unknown>;
  dateTimeOverride?: unknown;
  withLeaders?: boolean;
};

async function seedMeeting(options: SeedOptions = {}): Promise<Seed> {
  const matchId = fresh("m");
  const roomId = `season_${matchId}`;
  const promiseId = fresh("p");
  const left = [fresh("la"), fresh("lb"), fresh("lc")];
  const right = [fresh("ra"), fresh("rb"), fresh("rc")];
  const all = [...left, ...right].sort();
  const leftTeamId = fresh("tl");
  const rightTeamId = fresh("tr");
  for (const uid of all) {
    await db.collection("users").doc(uid).set({
      nickname: uid,
      dataPartition: options.partitionOf?.[uid] ?? "production",
      adultVerified: true,
      realNameVerified: true,
    });
  }
  if (options.withLeaders !== false) {
    await db.collection("meetingGroups").doc(leftTeamId).set({ leaderUid: left[0], captainUid: left[0], memberUids: left });
    await db.collection("meetingGroups").doc(rightTeamId).set({ leaderUid: right[0], captainUid: right[0], memberUids: right });
  }
  await db.collection("eventThreeVsThreeMatches").doc(matchId).set({
    requestId: fresh("req"),
    leftTeamId,
    rightTeamId,
    leftMemberUids: left,
    rightMemberUids: right,
    participantUids: all,
    status: "active",
    eventType: "season_meeting",
    seasonPhase: options.phase ?? "matched",
    chatRoomId: roomId,
    ...(options.matchOverrides ?? {}),
  });
  const start = options.meetupStartAtMs === undefined ? Date.now() - HOUR : options.meetupStartAtMs;
  await db.collection("chat_rooms").doc(roomId).set({
    participantIds: all,
    roomType: "season_meeting",
    ...(start === null ? {} : { activePromise: { promiseId } }),
  });
  if (start !== null) {
    const status = options.promiseStatus ?? (options.meetupCompleted ? "in_progress" : "confirmed");
    await db.collection("chat_rooms").doc(roomId).collection("promises").doc(promiseId).set({
      promiseId,
      requestedBy: left[1],
      requestedTo: right[1],
      status,
      dateTime: options.dateTimeOverride === undefined ? Timestamp.fromMillis(start) : options.dateTimeOverride,
      safetyStamp: {
        meetupStampedUserIds: options.meetupStampedUserIds ?? [],
        stampedForDateTimeMs: start,
        ...(options.meetupCompleted ? { meetupCompletedAt: Timestamp.now() } : {}),
      },
      ...(options.meetupCompleted ? { meetupCompletedAt: Timestamp.now() } : {}),
    });
    const observed = options.observedAtMs === undefined ? start - 2 * DAY : options.observedAtMs;
    if (observed !== null) {
      await db.collection("eventThreeVsThreeMatches").doc(matchId).collection("serverState").doc("schedule").set({
        promiseId,
        meetupStartAtMs: start,
        observedAt: Timestamp.fromMillis(observed),
        version: 1,
      });
    }
  }
  return { matchId, roomId, promiseId, left, right, all, leftLeader: left[0], rightLeader: right[0] };
}

const matchOf = async (id: string) => (await db.collection("eventThreeVsThreeMatches").doc(id).get()).data() ?? {};
const reportsOf = async (id: string) => (await db.collection("eventThreeVsThreeMatches").doc(id).collection("noShowReports").get()).docs;
const auditsOf = async (id: string) => (await db.collection("seasonMeetingCancelAudit").where("meetingId", "==", id).get()).docs;
const intentsOf = async (meetingId: string) => (await db.collection("seasonDepositIntents").where("meetingId", "==", meetingId).get()).docs;

function withProvider<T>(fn: () => Promise<T>): Promise<T> {
  const previous = process.env.SEASON_DEPOSIT_PROVIDER_READY;
  process.env.SEASON_DEPOSIT_PROVIDER_READY = "true";
  return fn().finally(() => {
    if (previous === undefined) delete process.env.SEASON_DEPOSIT_PROVIDER_READY;
    else process.env.SEASON_DEPOSIT_PROVIDER_READY = previous;
  });
}

// ===========================================================================
// No-show reporting
// ===========================================================================

test("NS1 [attack] forged meetupStartAtMs:0 cannot open a review before the real meeting", async () => {
  const s = await seedMeeting({ meetupStartAtMs: Date.now() + 2 * HOUR });
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2], meetupStartAtMs: 0 }), "failed-precondition", "NS1");
  assert.equal((await matchOf(s.matchId)).seasonPhase, "matched");
  assert.equal((await reportsOf(s.matchId)).length, 0);
});

test("NS2 [attack] forged gracePeriodMs:0 does not shorten the server grace period", async () => {
  const s = await seedMeeting({ meetupStartAtMs: Date.now() - 5 * MIN });
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2], meetupStartAtMs: Date.now() - 5 * MIN, gracePeriodMs: 0 }), "failed-precondition", "NS2");
  assert.equal((await matchOf(s.matchId)).seasonPhase, "matched");
});

test("NS3 [attack] forged safetyStartCompleted:false cannot accuse a participant who checked in", async () => {
  const s = await seedMeeting({ meetupStartAtMs: Date.now() - HOUR });
  await db.collection("chat_rooms").doc(s.roomId).collection("promises").doc(s.promiseId)
    .set({ safetyStamp: { meetupStampedUserIds: [s.right[2]], stampedForDateTimeMs: Date.now() - HOUR } }, { merge: true });
  // the seed's stampedForDateTimeMs must equal the promise time
  const p = (await db.collection("chat_rooms").doc(s.roomId).collection("promises").doc(s.promiseId).get()).data() ?? {};
  await db.collection("chat_rooms").doc(s.roomId).collection("promises").doc(s.promiseId)
    .set({ safetyStamp: { meetupStampedUserIds: [s.right[2]], stampedForDateTimeMs: (p.dateTime as Timestamp).toMillis() } }, { merge: true });
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2], meetupStartAtMs: 0, gracePeriodMs: 0, safetyStartCompleted: false }), "failed-precondition", "NS3");
  assert.equal((await reportsOf(s.matchId)).length, 0);
});

test("NS4 a non-participant cannot report", async () => {
  const s = await seedMeeting();
  const outsider = fresh("out");
  await db.collection("users").doc(outsider).set({ nickname: "x", dataPartition: "production" });
  await expectCode(call(noShowFn, outsider, { meetingId: s.matchId, accusedUid: s.right[2] }), "permission-denied", "NS4");
});

test("NS5 [attack] a participant cannot accuse an arbitrary uid", async () => {
  const s = await seedMeeting();
  const outsider = fresh("victim");
  await db.collection("users").doc(outsider).set({ nickname: "x", dataPartition: "production" });
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: outsider, meetupStartAtMs: 0 }), "failed-precondition", "NS5");
  assert.equal((await reportsOf(s.matchId)).length, 0);
  assert.equal((await matchOf(s.matchId)).seasonPhase, "matched");
});

test("NS6 reporter == accused is refused", async () => {
  const s = await seedMeeting();
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.left[1] }), "failed-precondition", "NS6");
});

test("NS7 an unconfirmed schedule (requested promise) is refused", async () => {
  const s = await seedMeeting({ promiseStatus: "requested" });
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] }), "failed-precondition", "NS7");
});

test("NS8 a schedule the server never observed is refused (no fallback to the client)", async () => {
  const s = await seedMeeting({ observedAtMs: null });
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2], meetupStartAtMs: Date.now() - DAY }), "failed-precondition", "NS8");
});

test("NS9 an invalid schedule representation is refused", async () => {
  const s = await seedMeeting({ dateTimeOverride: "2026-01-01T00:00:00Z" });
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] }), "failed-precondition", "NS9");
});

test("NS10 before the 15-minute server grace period: refused", async () => {
  const s = await seedMeeting({ meetupStartAtMs: Date.now() - 10 * MIN });
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] }), "failed-precondition", "NS10");
});

test("NS11 [attack] a schedule set or moved to the past after the fact is refused", async () => {
  // The client backdates the promise; the server observes it only now.
  const s = await seedMeeting({ meetupStartAtMs: Date.now() - 2 * HOUR, observedAtMs: Date.now() - MIN });
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] }), "failed-precondition", "NS11");
});

test("NS12 a legitimate report after the grace period opens a review — an allegation, no financial effect", async () => {
  const s = await seedMeeting({ meetupStartAtMs: Date.now() - 16 * MIN });
  const result = (await call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] })) as Record<string, unknown>;
  assert.equal(result.status, "no_show_reported");
  const m = await matchOf(s.matchId);
  assert.equal(m.seasonPhase, "noshow_review");
  const reports = await reportsOf(s.matchId);
  assert.equal(reports.length, 1);
  assert.equal(reports[0].get("reporterUid"), s.left[1]);
  assert.equal(reports[0].get("accusedUid"), s.right[2]);
  assert.equal(reports[0].get("status"), "pending_review");
  assert.equal((await auditsOf(s.matchId)).length, 0, "no cancellation / financial record");
  assert.equal((await intentsOf(s.matchId)).length, 0);
});

test("NS13 terminal phases accept no report", async () => {
  for (const phase of ["cancelled", "completed"]) {
    const s = await seedMeeting({ phase });
    await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] }), "failed-precondition", `NS13 ${phase}`);
  }
});

test("NS14 duplicate / concurrent invocations by the same reporter create one report", async () => {
  const s = await seedMeeting();
  const runs = await Promise.allSettled(Array.from({ length: 6 }, () => call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] })));
  assert.ok(runs.some((r) => r.status === "fulfilled"));
  for (const r of runs) if (r.status === "rejected") assert.ok(["aborted"].includes((r.reason as { code?: string }).code ?? ""), String(r.reason));
  assert.equal((await reportsOf(s.matchId)).length, 1);
  assert.equal((await matchOf(s.matchId)).noShowReportCount, 1);
});

test("NS15 a second reporter adds a report and never overwrites the first (same-phase retry)", async () => {
  const s = await seedMeeting();
  await call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] });
  await call(noShowFn, s.left[2], { meetingId: s.matchId, accusedUid: s.right[2] });
  await call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[1] });
  const reports = await reportsOf(s.matchId);
  assert.equal(reports.length, 3);
  const pairs = reports.map((r) => `${r.get("reporterUid")}>${r.get("accusedUid")}`).sort();
  assert.deepEqual(pairs, [`${s.left[1]}>${s.right[1]}`, `${s.left[1]}>${s.right[2]}`, `${s.left[2]}>${s.right[2]}`].sort());
  const m = await matchOf(s.matchId);
  assert.equal(m.noShowReportCount, 3);
  assert.equal(m.noShowReport, undefined, "no single overwritable report field on the match");
});

test("NS16 cross-partition accused is refused", async () => {
  const s = await seedMeeting();
  await db.collection("users").doc(s.right[2]).set({ dataPartition: "play_review" }, { merge: true });
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] }), "failed-precondition", "NS16");
  assert.equal((await reportsOf(s.matchId)).length, 0);
});

test("NS17 malformed participant data fails closed", async () => {
  const s = await seedMeeting();
  await db.collection("eventThreeVsThreeMatches").doc(s.matchId).update({ participantUids: s.all.slice(0, 5) });
  await expectCode(call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] }), "failed-precondition", "NS17");
});

test("NS18 legacy match documents (no eventType / no chat link) fail closed", async () => {
  const a = await seedMeeting();
  await db.collection("eventThreeVsThreeMatches").doc(a.matchId).update({ eventType: null });
  await expectCode(call(noShowFn, a.left[1], { meetingId: a.matchId, accusedUid: a.right[2] }), "failed-precondition", "NS18 eventType");
  const b = await seedMeeting();
  await db.collection("eventThreeVsThreeMatches").doc(b.matchId).update({ chatRoomId: "season_other" });
  await expectCode(call(noShowFn, b.left[1], { meetingId: b.matchId, accusedUid: b.right[2] }), "failed-precondition", "NS18 chat link");
});

test("NS19 a report racing a cancellation leaves one consistent outcome", async () => {
  const s = await seedMeeting();
  const [rep, can] = await Promise.allSettled([
    call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] }),
    call(cancelFn, s.leftLeader, { meetingId: s.matchId }),
  ]);
  assert.equal(can.status, "fulfilled", String((can as PromiseRejectedResult).reason));
  const m = await matchOf(s.matchId);
  assert.equal(m.seasonPhase, "cancelled");
  assert.equal((await auditsOf(s.matchId)).length, 1);
  const reports = (await reportsOf(s.matchId)).length;
  assert.equal(reports, rep.status === "fulfilled" ? 1 : 0, "a report exists exactly when its call succeeded");
});

test("NS20 a report racing a replacement claim: both stay consistent", async () => {
  const s = await seedMeeting();
  await db.collection("eventThreeVsThreeMatches").doc(s.matchId).collection("replacementSeats").doc("seat1")
    .set({ seatId: "seat1", claimedByUid: null, status: "open", version: 1 });
  const [rep, claim] = await Promise.allSettled([
    call(noShowFn, s.left[1], { meetingId: s.matchId, accusedUid: s.right[2] }),
    call(claimFn, s.left[2], { meetingId: s.matchId, seatId: "seat1", expectedVersion: 1 }),
  ]);
  assert.equal(rep.status, "fulfilled");
  assert.equal(claim.status, "fulfilled");
  assert.equal((await reportsOf(s.matchId)).length, 1);
  const seat = (await db.collection("eventThreeVsThreeMatches").doc(s.matchId).collection("replacementSeats").doc("seat1").get()).data() ?? {};
  assert.equal(seat.claimedByUid, s.left[2]);
  assert.equal(seat.version, 2);
});

// ===========================================================================
// Cancellation
// ===========================================================================

test("C1 [attack] an ordinary participant cannot cancel the whole 3:3 meeting", async () => {
  const s = await seedMeeting();
  await expectCode(call(cancelFn, s.left[1], { meetingId: s.matchId, window: "before_match_confirmed", depositCaptured: true }), "permission-denied", "C1");
  assert.equal((await matchOf(s.matchId)).seasonPhase, "matched");
  assert.equal((await auditsOf(s.matchId)).length, 0);
});

test("C2 [attack] the refund window and deposit state are server-derived, never the caller's", async () => {
  // Same KST day as the meeting, nothing captured → day_of_meetup, no refund.
  const start = Date.now() + 30 * MIN;
  const s = await seedMeeting({ meetupStartAtMs: start });
  const result = (await call(cancelFn, s.leftLeader, { meetingId: s.matchId, window: "before_match_confirmed", depositCaptured: true })) as Record<string, unknown>;
  const kstDay = (ms: number) => Math.floor((ms + KST) / DAY);
  const expectWindow = kstDay(Date.now()) === kstDay(start) ? "day_of_meetup" : "after_schedule_before_meetup";
  const audits = await auditsOf(s.matchId);
  assert.equal(audits.length, 1);
  assert.equal(audits[0].get("window"), expectWindow);
  assert.equal(audits[0].get("depositCaptured"), false);
  assert.deepEqual(audits[0].get("refund"), { action: "none" });
  assert.deepEqual(result.refund, { action: "none" });
  assert.equal((await matchOf(s.matchId)).seasonPhase, "cancelled");
});

test("C3 window derivation: unscheduled / ahead / safety started", async () => {
  const unscheduled = await seedMeeting({ meetupStartAtMs: null });
  await call(cancelFn, unscheduled.rightLeader, { meetingId: unscheduled.matchId });
  assert.equal((await auditsOf(unscheduled.matchId))[0].get("window"), "after_match_before_schedule");

  const ahead = await seedMeeting({ meetupStartAtMs: Date.now() + 3 * DAY });
  await call(cancelFn, ahead.leftLeader, { meetingId: ahead.matchId });
  assert.equal((await auditsOf(ahead.matchId))[0].get("window"), "after_schedule_before_meetup");

  const met = await seedMeeting({ meetupStartAtMs: Date.now() - 30 * MIN, meetupCompleted: true });
  await call(cancelFn, met.leftLeader, { meetingId: met.matchId });
  assert.equal((await auditsOf(met.matchId))[0].get("window"), "after_safety_start");
});

test("C4 captured deposit evidence comes from the server ledger and drives the refund decision", async () => {
  const s = await seedMeeting({ meetupStartAtMs: Date.now() + 3 * DAY });
  await db.collection("seasonDepositIntents").doc(fresh("sdi_")).set({
    meetingId: s.matchId, participantUid: s.left[1], amount: 5000, currency: "KRW", status: "captured",
  });
  await call(cancelFn, s.rightLeader, { meetingId: s.matchId, depositCaptured: false, window: "after_safety_start" });
  const audit = (await auditsOf(s.matchId))[0];
  assert.equal(audit.get("depositCaptured"), true);
  assert.deepEqual(audit.get("refund"), { action: "partial_refund", ratio: 0.5 });
});

test("C5 a retry by the same leader is idempotent; another leader cannot overwrite the decision", async () => {
  const s = await seedMeeting({ meetupStartAtMs: Date.now() + 3 * DAY });
  const first = (await call(cancelFn, s.leftLeader, { meetingId: s.matchId })) as Record<string, unknown>;
  const again = (await call(cancelFn, s.leftLeader, { meetingId: s.matchId })) as Record<string, unknown>;
  assert.deepEqual(again.refund, first.refund);
  await expectCode(call(cancelFn, s.rightLeader, { meetingId: s.matchId }), "failed-precondition", "C5 other leader");
  const audits = await auditsOf(s.matchId);
  assert.equal(audits.length, 1);
  assert.equal(audits[0].get("actorUid"), s.leftLeader);
  assert.equal((await matchOf(s.matchId)).cancelledByUserId, s.leftLeader);
});

test("C6 concurrent cancellations by both leaders commit exactly one decision", async () => {
  const s = await seedMeeting({ meetupStartAtMs: Date.now() + 3 * DAY });
  const runs = await Promise.allSettled([
    call(cancelFn, s.leftLeader, { meetingId: s.matchId }),
    call(cancelFn, s.rightLeader, { meetingId: s.matchId }),
    call(cancelFn, s.leftLeader, { meetingId: s.matchId }),
  ]);
  assert.ok(runs.some((r) => r.status === "fulfilled"));
  const audits = await auditsOf(s.matchId);
  assert.equal(audits.length, 1);
  assert.equal((await matchOf(s.matchId)).cancelledByUserId, audits[0].get("actorUid"));
});

test("C7 terminal and unknown phases are refused; a never-observed schedule fails closed", async () => {
  const done = await seedMeeting({ phase: "completed" });
  await expectCode(call(cancelFn, done.leftLeader, { meetingId: done.matchId }), "failed-precondition", "C7 completed");
  const weird = await seedMeeting({ phase: "legacy_whatever" });
  await expectCode(call(cancelFn, weird.leftLeader, { meetingId: weird.matchId }), "failed-precondition", "C7 unknown");
  const unobserved = await seedMeeting({ meetupStartAtMs: Date.now() + 3 * DAY, observedAtMs: null });
  await expectCode(call(cancelFn, unobserved.leftLeader, { meetingId: unobserved.matchId }), "failed-precondition", "C7 unobserved");
  for (const s of [done, weird, unobserved]) assert.equal((await auditsOf(s.matchId)).length, 0);
});

test("C8 leadership that cannot be verified from the team records fails closed", async () => {
  const s = await seedMeeting({ withLeaders: false });
  await expectCode(call(cancelFn, s.left[0], { meetingId: s.matchId }), "permission-denied", "C8");
  assert.equal((await matchOf(s.matchId)).seasonPhase, "matched");
});

test("C9 a non-participant cannot cancel", async () => {
  const s = await seedMeeting();
  const outsider = fresh("out");
  await expectCode(call(cancelFn, outsider, { meetingId: s.matchId }), "permission-denied", "C9");
});

// ===========================================================================
// Deposit intents and refunds (provider stays disabled in production)
// ===========================================================================

test("D1 provider disabled (production default): deposit and refund refuse before anything else", async () => {
  delete process.env.SEASON_DEPOSIT_PROVIDER_READY;
  const s = await seedMeeting();
  await expectCode(call(depositFn, s.left[1], { meetingId: s.matchId, idempotencyKey: "key-aaaa-0001", amount: 5000 }), "failed-precondition", "D1 deposit");
  await expectCode(call(refundFn, s.left[1], { intentId: "x", refundIdempotencyKey: "rk-aaaa-0001", amount: 5000 }), "failed-precondition", "D1 refund");
  assert.equal((await intentsOf(s.matchId)).length, 0);
});

test("D2 [attack] the same idempotency key from another user never returns or overwrites the first user's intent", async () => withProvider(async () => {
  const s = await seedMeeting();
  const key = fresh("shared-key-");
  const a = (await call(depositFn, s.left[1], { meetingId: s.matchId, idempotencyKey: key, amount: 5000 })) as Record<string, unknown>;
  const b = (await call(depositFn, s.right[1], { meetingId: s.matchId, idempotencyKey: key, amount: 5000 })) as Record<string, unknown>;
  assert.notEqual(a.intentId, b.intentId);
  const intents = await intentsOf(s.matchId);
  assert.equal(intents.length, 2);
  assert.deepEqual(intents.map((d) => d.get("participantUid")).sort(), [s.left[1], s.right[1]].sort());
  assert.equal(JSON.stringify(b).includes(s.left[1]), false, "no other user's data in the response");
}));

test("D3 same user + key + meeting is idempotent, including concurrently", async () => withProvider(async () => {
  const s = await seedMeeting();
  const key = fresh("k-");
  const runs = await Promise.allSettled(Array.from({ length: 5 }, () => call(depositFn, s.left[1], { meetingId: s.matchId, idempotencyKey: key, amount: 5000 })));
  const ok = runs.filter((r): r is PromiseFulfilledResult<unknown> => r.status === "fulfilled").map((r) => (r.value as Record<string, unknown>).intentId);
  assert.ok(ok.length >= 1);
  assert.equal(new Set(ok).size, 1);
  assert.equal((await intentsOf(s.matchId)).length, 1);
  assert.equal((await matchOf(s.matchId)).seasonPhase, "deposit_pending");
}));

test("D4 same key in another meeting is a different intent; a second open intent in one meeting is refused", async () => withProvider(async () => {
  const s1 = await seedMeeting();
  const key = fresh("k-");
  await call(depositFn, s1.left[1], { meetingId: s1.matchId, idempotencyKey: key, amount: 5000 });
  await expectCode(call(depositFn, s1.left[1], { meetingId: s1.matchId, idempotencyKey: fresh("other-"), amount: 5000 }), "failed-precondition", "D4 second open");
  assert.equal((await intentsOf(s1.matchId)).length, 1);
}));

test("D5 the amount and currency are the server's; a conflicting retry fails", async () => withProvider(async () => {
  const s = await seedMeeting();
  await expectCode(call(depositFn, s.left[1], { meetingId: s.matchId, idempotencyKey: fresh("k-"), amount: 100, expectedAmount: 100 }), "invalid-argument", "D5 amount");
  await expectCode(call(depositFn, s.left[1], { meetingId: s.matchId, idempotencyKey: fresh("k-"), amount: 5000, currency: "USD" }), "invalid-argument", "D5 currency");
  const key = fresh("k-");
  const first = (await call(depositFn, s.left[1], { meetingId: s.matchId, idempotencyKey: key })) as Record<string, unknown>;
  assert.equal(first.amount, 5000);
  await expectCode(call(depositFn, s.left[1], { meetingId: s.matchId, idempotencyKey: key, amount: 6000 }), "invalid-argument", "D5 retry amount");
}));

test("D6 malformed / oversized keys, missing meeting, non-participant", async () => withProvider(async () => {
  const s = await seedMeeting();
  for (const key of ["", "short", "has space ok", "x".repeat(65), "../etc/passwd", "a/b/c/d/e/f/g"]) {
    await expectCode(call(depositFn, s.left[1], { meetingId: s.matchId, idempotencyKey: key, amount: 5000 }), "invalid-argument", `D6 key ${key.slice(0, 10)}`);
  }
  await expectCode(call(depositFn, s.left[1], { meetingId: fresh("missing"), idempotencyKey: fresh("k-"), amount: 5000 }), "not-found", "D6 missing meeting");
  await expectCode(call(depositFn, fresh("out"), { meetingId: s.matchId, idempotencyKey: fresh("k-"), amount: 5000 }), "permission-denied", "D6 outsider");
}));

test("D7 [attack] no intent is created in a phase that does not allow a deposit", async () => withProvider(async () => {
  for (const phase of ["cancelled", "noshow_review", "chat_open"]) {
    const s = await seedMeeting({ phase });
    await expectCode(call(depositFn, s.left[1], { meetingId: s.matchId, idempotencyKey: fresh("k-"), amount: 5000 }), "failed-precondition", `D7 ${phase}`);
    assert.equal((await intentsOf(s.matchId)).length, 0, `no orphan intent in ${phase}`);
  }
}));

test("R1 refunds: only the owner, only after capture, only what the cancellation policy grants, exactly once", async () => withProvider(async () => {
  const s = await seedMeeting({ meetupStartAtMs: Date.now() + 3 * DAY });
  const intent = (await call(depositFn, s.left[1], { meetingId: s.matchId, idempotencyKey: fresh("k-"), amount: 5000 })) as Record<string, unknown>;
  const intentId = String(intent.intentId);
  // Not captured yet.
  await expectCode(call(refundFn, s.left[1], { intentId, refundIdempotencyKey: fresh("rk-") }), "failed-precondition", "R1 before capture");
  // Simulate the (future) provider callback: server-only capture.
  await db.collection("seasonDepositIntents").doc(intentId).update({ status: "captured" });
  // No cancellation decision yet → nothing is refundable.
  await expectCode(call(refundFn, s.left[1], { intentId, refundIdempotencyKey: fresh("rk-") }), "failed-precondition", "R1 no decision");
  await call(cancelFn, s.leftLeader, { meetingId: s.matchId });
  // Another participant cannot refund it.
  await expectCode(call(refundFn, s.right[1], { intentId, refundIdempotencyKey: fresh("rk-") }), "permission-denied", "R1 not owner");
  // Partial (50 %) policy: more than granted is refused.
  await expectCode(call(refundFn, s.left[1], { intentId, refundIdempotencyKey: fresh("rk-"), amount: 5000 }), "invalid-argument", "R1 exceeds policy");
  const k1 = fresh("rk-"), k2 = fresh("rk-");
  const runs = await Promise.allSettled([
    call(refundFn, s.left[1], { intentId, refundIdempotencyKey: k1 }),
    call(refundFn, s.left[1], { intentId, refundIdempotencyKey: k2 }),
  ]);
  assert.ok(runs.some((r) => r.status === "fulfilled"));
  const after = (await db.collection("seasonDepositIntents").doc(intentId).get()).data() ?? {};
  assert.equal(after.status, "refunded");
  assert.equal(after.refundedAmount, 2500);
  assert.equal((after.refundKeys as string[]).length, 1, "exactly one refund applied");
  const dup = (await call(refundFn, s.left[1], { intentId, refundIdempotencyKey: (after.refundKeys as string[])[0] })) as Record<string, unknown>;
  assert.equal(dup.status, "refunded");
  assert.equal(((await db.collection("seasonDepositIntents").doc(intentId).get()).get("refundKeys") as string[]).length, 1);
}));
