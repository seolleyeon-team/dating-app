import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";

import { Timestamp } from "firebase-admin/firestore";

import {
  SEASON_NO_SHOW_GRACE_MS,
  decideNoShowReport,
  deriveCancelWindow,
  evaluateSchedule,
  kstDayStartMs,
  scopedDocId,
  type ScheduleEvidence,
} from "./seasonMeetingAuthority";

const P = new Set(["a", "b", "c", "d", "e", "f"]);
const observed = (startMs: number, extra: Partial<Extract<ScheduleEvidence, { state: "observed" }>> = {}): ScheduleEvidence =>
  ({ state: "observed", startMs, fixedBeforeStart: true, meetupCompleted: false, checkedIn: new Set(), ...extra });

describe("P1-13 season meeting authority (pure)", () => {
  it("grace boundary: before refused, exactly at start+grace allowed", () => {
    const start = 1_800_000_000_000;
    const base = { phase: "matched" as const, participants: P, reporterUid: "a", accusedUid: "d", schedule: observed(start) };
    assert.deepEqual(decideNoShowReport({ ...base, nowMs: start + SEASON_NO_SHOW_GRACE_MS - 1 }), { ok: false, code: "failed-precondition", reason: "before_grace" });
    assert.deepEqual(decideNoShowReport({ ...base, nowMs: start + SEASON_NO_SHOW_GRACE_MS }), { ok: true, meetupStartAtMs: start });
    assert.equal(SEASON_NO_SHOW_GRACE_MS, 15 * 60 * 1000);
  });

  it("no-show refusals are ordered so membership is never probed through other errors", () => {
    const now = 2_000_000_000_000;
    const s = observed(now - 3600_000);
    assert.equal((decideNoShowReport({ nowMs: now, phase: "matched", participants: P, reporterUid: "x", accusedUid: "zzz", schedule: s }) as { reason: string }).reason, "not_meeting_participant");
    assert.equal((decideNoShowReport({ nowMs: now, phase: "matched", participants: P, reporterUid: "a", accusedUid: "a", schedule: s }) as { reason: string }).reason, "self_report");
    assert.equal((decideNoShowReport({ nowMs: now, phase: "matched", participants: P, reporterUid: "a", accusedUid: "zzz", schedule: s }) as { reason: string }).reason, "accused_not_participant");
    assert.equal((decideNoShowReport({ nowMs: now, phase: "completed", participants: P, reporterUid: "a", accusedUid: "d", schedule: s }) as { reason: string }).reason, "phase_not_reportable:completed");
    assert.equal((decideNoShowReport({ nowMs: now, phase: "matched", participants: P, reporterUid: "a", accusedUid: "d", schedule: observed(now - 3600_000, { fixedBeforeStart: false }) }) as { reason: string }).reason, "schedule_fixed_after_start");
    assert.equal((decideNoShowReport({ nowMs: now, phase: "matched", participants: P, reporterUid: "a", accusedUid: "d", schedule: observed(now - 3600_000, { checkedIn: new Set(["d"]) }) }) as { reason: string }).reason, "accused_checked_in");
    assert.equal((decideNoShowReport({ nowMs: now, phase: "matched", participants: P, reporterUid: "a", accusedUid: "d", schedule: observed(now - 3600_000, { meetupCompleted: true }) }) as { reason: string }).reason, "everyone_checked_in");
    assert.equal(decideNoShowReport({ nowMs: now, phase: "noshow_review", participants: P, reporterUid: "b", accusedUid: "d", schedule: s }).ok, true, "a further report in review");
  });

  it("schedule evidence: only a Timestamp, only the observed time, stamps only for that time", () => {
    const start = 1_800_000_000_000;
    const lock = { promiseId: "p", meetupStartAtMs: start, observedAtMs: start - 1 };
    const promise = { status: "confirmed", dateTime: Timestamp.fromMillis(start), safetyStamp: { meetupStampedUserIds: ["d"], stampedForDateTimeMs: start - 60_000 } };
    const e = evaluateSchedule({ promiseId: "p", promise, lock }) as Extract<ScheduleEvidence, { state: "observed" }>;
    assert.equal(e.state, "observed");
    assert.equal(e.checkedIn.size, 0, "stamps for another time do not count");
    assert.equal(evaluateSchedule({ promiseId: "p", promise: { ...promise, dateTime: start }, lock }).state, "invalid");
    assert.equal(evaluateSchedule({ promiseId: "p", promise: { ...promise, dateTime: "2026-01-01" }, lock }).state, "invalid");
    assert.equal(evaluateSchedule({ promiseId: "p", promise: { ...promise, status: "requested" }, lock }).state, "unscheduled");
    assert.equal(evaluateSchedule({ promiseId: "p", promise, lock: { ...lock, meetupStartAtMs: start + 1 } }).state, "unobserved");
    assert.equal(evaluateSchedule({ promiseId: "p", promise, lock: null }).state, "unobserved");
    assert.equal(evaluateSchedule({ promiseId: null, promise: null, lock }).state, "unscheduled");
  });

  it("cancel window from server facts; unknown evidence fails closed", () => {
    const start = Date.UTC(2026, 10, 20, 10, 0); // 19:00 KST
    const dayStart = kstDayStartMs(start);
    assert.equal(new Date(dayStart + 9 * 3600_000).toISOString().slice(11, 16), "00:00");
    assert.equal(deriveCancelWindow({ phase: "matched", schedule: { state: "unscheduled" }, nowMs: start }), "after_match_before_schedule");
    assert.equal(deriveCancelWindow({ phase: "matched", schedule: observed(start), nowMs: dayStart - 1 }), "after_schedule_before_meetup");
    assert.equal(deriveCancelWindow({ phase: "matched", schedule: observed(start), nowMs: dayStart }), "day_of_meetup");
    assert.equal(deriveCancelWindow({ phase: "matched", schedule: observed(start, { meetupCompleted: true }), nowMs: dayStart }), "after_safety_start");
    assert.equal(deriveCancelWindow({ phase: "in_meeting", schedule: { state: "unscheduled" }, nowMs: start }), "after_safety_start");
    assert.equal(deriveCancelWindow({ phase: "request_pending", schedule: { state: "unscheduled" }, nowMs: start }), "before_match_confirmed");
    assert.equal(deriveCancelWindow({ phase: "matched", schedule: { state: "unobserved", startMs: start }, nowMs: start }), null);
    assert.equal(deriveCancelWindow({ phase: "matched", schedule: { state: "invalid" }, nowMs: start }), null);
  });

  it("scoped ids: NUL-separated digest, no delimiter collision", () => {
    assert.notEqual(scopedDocId("x_", ["u_1", "m"]), scopedDocId("x_", ["u", "1_m"]));
    assert.match(scopedDocId("sdi_", ["a", "b", "c"]), /^sdi_[0-9a-f]{48}$/);
  });

  it("source contract: no request field is authoritative in the season callables", () => {
    const src = readFileSync(resolve(__dirname, "../src/seasonMeetingOperations.ts"), "utf8");
    for (const field of ["meetupStartAtMs", "gracePeriodMs", "safetyStartCompleted", "depositCaptured", "expectedAmount"]) {
      assert.equal(new RegExp(`data\\.${field}`).test(src), false, `request field ${field} must not be read`);
    }
    assert.equal(/data\.window/.test(src), false, "request field window must not be read");
    assert.equal(/\.doc\(idempotencyKey\)/.test(src), false, "client keys never become document ids");
  });
});
