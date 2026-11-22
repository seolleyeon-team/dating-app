/**
 * 안전도장 서버 권위 write — 순수 로직 테스트
 * 실행: npm --prefix functions test
 *
 * 트랜잭션 본체는 Firestore 가 필요하므로 emulator 테스트에서 다룬다.
 * 여기서는 입력 정규화와 도장 목록 계산처럼 순수한 부분만 고정한다.
 */

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  promiseDateTimeMs,
  stampsMatchCurrentPromise,
  SAFETY_STAMP_FOLLOW_UP_REASONS,
  SAFETY_STAMP_PHASES,
  SAFETY_STAMP_TERMINAL_PROMISE_STATUSES,
  effectiveMeetupStamps,
  normalizeFollowUpReason,
  normalizeSafetyStampPhase,
} from "./safetyStamp";

describe("안전도장 단계 정규화", () => {
  it("canonical 단계만 인정한다", () => {
    assert.equal(normalizeSafetyStampPhase("meetup"), "meetup");
    assert.equal(normalizeSafetyStampPhase("goodbye"), "goodbye");
    assert.equal(normalizeSafetyStampPhase(" MEETUP "), "meetup");
  });

  it("알 수 없는 값은 meetup 으로 떨어지지 않는다", () => {
    // 예전 클라이언트는 phase 가 'goodbye' 가 아니면 전부 meetup 으로 처리했다.
    // 오타 하나로 종료 도장이 도착 도장이 되면 안 된다.
    for (const raw of [null, undefined, "", "meetups", "goodby", "checkin", 0, {}]) {
      assert.equal(
        normalizeSafetyStampPhase(raw),
        null,
        `${JSON.stringify(raw)} 는 단계로 인정하지 않는다`
      );
    }
  });

  it("지원 단계는 두 개뿐이다", () => {
    assert.deepEqual(SAFETY_STAMP_PHASES, ["meetup", "goodbye"]);
  });
});

describe("도장 목록 계산", () => {
  it("meetupStampedUserIds 가 있으면 그대로 쓴다", () => {
    assert.deepEqual(
      [...effectiveMeetupStamps({ meetupStampedUserIds: ["a", "b"] })].sort(),
      ["a", "b"]
    );
  });

  it("비어 있으면 legacy stampedUserIds 로 되돌아간다", () => {
    assert.deepEqual(
      [
        ...effectiveMeetupStamps({
          meetupStampedUserIds: [],
          stampedUserIds: ["a"],
        }),
      ],
      ["a"]
    );
  });

  it("meetup 이 있으면 legacy 를 섞지 않는다", () => {
    assert.deepEqual(
      [
        ...effectiveMeetupStamps({
          meetupStampedUserIds: ["a"],
          stampedUserIds: ["b", "c"],
        }),
      ],
      ["a"]
    );
  });

  it("손상된 값은 무시한다", () => {
    assert.equal(effectiveMeetupStamps({}).size, 0);
    assert.equal(effectiveMeetupStamps({ meetupStampedUserIds: "a" }).size, 0);
    assert.deepEqual(
      [...effectiveMeetupStamps({ meetupStampedUserIds: ["a", "", null, 1] })],
      ["a"]
    );
  });

  it("중복 uid 를 두 명으로 세지 않는다", () => {
    assert.equal(
      effectiveMeetupStamps({ meetupStampedUserIds: ["a", "a", "a"] }).size,
      1
    );
  });
});

describe("종료된 약속", () => {
  it("도장을 받을 수 없는 상태 목록", () => {
    for (const status of ["cancelled", "canceled", "rejected", "completed", "expired"]) {
      assert.ok(
        SAFETY_STAMP_TERMINAL_PROMISE_STATUSES.includes(status),
        `${status} 는 종료 상태여야 한다`
      );
    }
    assert.equal(
      SAFETY_STAMP_TERMINAL_PROMISE_STATUSES.includes("confirmed"),
      false
    );
    assert.equal(
      SAFETY_STAMP_TERMINAL_PROMISE_STATUSES.includes("in_progress"),
      false
    );
  });
});

describe("헤어짐 사유 정규화", () => {
  it("클라이언트 enum 과 같은 값만 받는다", () => {
    for (const code of ["phone_off", "forgot_to_stamp", "other"]) {
      assert.equal(normalizeFollowUpReason(code), code);
    }
    assert.deepEqual(SAFETY_STAMP_FOLLOW_UP_REASONS, [
      "phone_off",
      "forgot_to_stamp",
      "other",
    ]);
  });

  it("임의 문자열은 거부한다", () => {
    for (const raw of [null, undefined, "", "hacked", "OTHER", 1, {}]) {
      assert.equal(normalizeFollowUpReason(raw), null);
    }
  });
});

describe("약속 수정 후 이전 도장 무효화", () => {
  it("같은 시각이면 기존 도장을 이어 쓴다", () => {
    assert.equal(
      stampsMatchCurrentPromise(
        { stampedForDateTimeMs: 1000 },
        new Date(1000)
      ),
      true
    );
  });

  it("약속 시각이 바뀌면 기존 도장을 인정하지 않는다", () => {
    // 예전 약속에서 찍은 도장이 새 약속의 출석으로 계산되면,
    // 오지 않은 사람이 참석한 것처럼 기록된다.
    assert.equal(
      stampsMatchCurrentPromise(
        { stampedForDateTimeMs: 1000 },
        new Date(2000)
      ),
      false
    );
  });

  it("표식이 없는 legacy 문서는 그대로 인정한다", () => {
    assert.equal(stampsMatchCurrentPromise({}, new Date(1000)), true);
  });

  it("약속 시각을 읽을 수 없으면 막지 않는다", () => {
    assert.equal(
      stampsMatchCurrentPromise({ stampedForDateTimeMs: 1000 }, null),
      true
    );
  });

  it("Timestamp / Date / number 를 모두 밀리초로 읽는다", () => {
    assert.equal(promiseDateTimeMs(new Date(1234)), 1234);
    assert.equal(promiseDateTimeMs(1234), 1234);
    assert.equal(promiseDateTimeMs({ toMillis: () => 1234 }), 1234);
    assert.equal(promiseDateTimeMs(null), null);
    assert.equal(promiseDateTimeMs("2026-01-01"), null);
  });
});

// ---------------------------------------------------------------------------
// B-12 — the stamp window is decided with the server clock
// ---------------------------------------------------------------------------

import {
  SAFETY_STAMP_CLOCK_SKEW_GRACE_MS,
  SAFETY_STAMP_GOODBYE_WINDOW_MS,
  SAFETY_STAMP_MEETUP_CLOSE_AFTER_MS,
  SAFETY_STAMP_MEETUP_OPEN_BEFORE_MS,
  SAFETY_STAMP_OPENABLE_PROMISE_STATUSES,
  evaluateSafetyStampWindow,
} from "./safetyStamp";

describe("B-12 evaluateSafetyStampWindow", () => {
  const MINUTE = 60_000;
  const HOUR = 60 * MINUTE;
  // 2026-11-22 19:00 KST
  const START = Date.UTC(2026, 10, 22, 10, 0, 0);
  const ts = (ms: number) => ({ toMillis: () => ms });
  const meetup = (nowMs: number, promiseDateTime: unknown = ts(START)) =>
    evaluateSafetyStampWindow({ phase: "meetup", nowMs, promiseDateTime, meetupCompletedAt: null });
  const goodbye = (nowMs: number, meetupCompletedAt: unknown) =>
    evaluateSafetyStampWindow({ phase: "goodbye", nowMs, promiseDateTime: ts(START), meetupCompletedAt });

  it("keeps the product window: 10 minutes before to 1 hour after, plus a short skew grace", () => {
    assert.equal(SAFETY_STAMP_MEETUP_OPEN_BEFORE_MS, 10 * MINUTE);
    assert.equal(SAFETY_STAMP_MEETUP_CLOSE_AFTER_MS, HOUR);
    assert.equal(SAFETY_STAMP_GOODBYE_WINDOW_MS, 24 * HOUR);
    assert.ok(SAFETY_STAMP_CLOCK_SKEW_GRACE_MS > 0 && SAFETY_STAMP_CLOCK_SKEW_GRACE_MS <= 5 * MINUTE);
    assert.deepEqual(SAFETY_STAMP_OPENABLE_PROMISE_STATUSES, ["confirmed", "in_progress"]);
  });

  it("accepts an arrival stamp inside the window", () => {
    for (const offset of [-10 * MINUTE, -MINUTE, 0, 30 * MINUTE, HOUR]) {
      assert.deepEqual(meetup(START + offset), { ok: true });
    }
  });

  it("device clock in the future: a stamp sent days or hours before the meeting is refused", () => {
    // The server time is what it is, whatever the phone displays.
    for (const offset of [-3 * 24 * HOUR, -2 * HOUR, -16 * MINUTE]) {
      assert.deepEqual(meetup(START + offset), { ok: false, reason: "too_early" });
    }
    assert.deepEqual(meetup(START - 10 * MINUTE - SAFETY_STAMP_CLOCK_SKEW_GRACE_MS), { ok: true });
    assert.deepEqual(meetup(START - 10 * MINUTE - SAFETY_STAMP_CLOCK_SKEW_GRACE_MS - 1), { ok: false, reason: "too_early" });
  });

  it("device clock in the past / safety stamp expiry: a stamp after the deadline is refused", () => {
    for (const offset of [HOUR + 6 * MINUTE, 5 * HOUR, 30 * 24 * HOUR]) {
      assert.deepEqual(meetup(START + offset), { ok: false, reason: "too_late" });
    }
    assert.deepEqual(meetup(START + HOUR + SAFETY_STAMP_CLOCK_SKEW_GRACE_MS), { ok: true });
    assert.deepEqual(meetup(START + HOUR + SAFETY_STAMP_CLOCK_SKEW_GRACE_MS + 1), { ok: false, reason: "too_late" });
  });

  it("timezone change: the decision depends only on the instant, not on how the time was written", () => {
    const sameInstant = [
      ts(START),
      new Date("2026-11-22T19:00:00+09:00"),
      new Date("2026-11-22T02:00:00-08:00"),
      new Date("2026-11-22T10:00:00Z"),
      START,
    ];
    for (const value of sameInstant) {
      assert.deepEqual(meetup(START - 5 * MINUTE, value), { ok: true });
      assert.deepEqual(meetup(START - 9 * HOUR, value), { ok: false, reason: "too_early" });
      assert.deepEqual(meetup(START + 9 * HOUR, value), { ok: false, reason: "too_late" });
    }
  });

  it("KST midnight boundary: a 00:05 KST meeting opens at 23:55 KST of the previous day", () => {
    const midnightMeeting = Date.UTC(2026, 10, 22, 15, 5, 0); // 2026-11-23 00:05 KST
    const previousDay2355 = Date.UTC(2026, 10, 22, 14, 55, 0); // 2026-11-22 23:55 KST
    assert.deepEqual(meetup(previousDay2355, ts(midnightMeeting)), { ok: true });
    assert.deepEqual(meetup(previousDay2355 - 6 * MINUTE, ts(midnightMeeting)), { ok: false, reason: "too_early" });
    // 23:30 KST meeting stays open across midnight until 00:30 KST.
    const lateMeeting = Date.UTC(2026, 10, 22, 14, 30, 0); // 23:30 KST
    assert.deepEqual(meetup(Date.UTC(2026, 10, 22, 15, 20, 0), ts(lateMeeting)), { ok: true }); // 00:20 KST
    assert.deepEqual(meetup(Date.UTC(2026, 10, 22, 15, 36, 0), ts(lateMeeting)), { ok: false, reason: "too_late" });
  });

  it("promise time change: the window follows the CURRENT promise time", () => {
    const moved = START + 3 * 24 * HOUR;
    const now = START + 5 * MINUTE;
    assert.deepEqual(meetup(now, ts(START)), { ok: true });
    assert.deepEqual(meetup(now, ts(moved)), { ok: false, reason: "too_early" });
    assert.deepEqual(meetup(moved, ts(moved)), { ok: true });
    assert.deepEqual(meetup(moved, ts(START)), { ok: false, reason: "too_late" });
  });

  it("fails closed when the promise has no usable time", () => {
    for (const value of [null, undefined, "2026-11-22T10:00:00Z", {}, Number.NaN]) {
      assert.deepEqual(
        evaluateSafetyStampWindow({ phase: "meetup", nowMs: START, promiseDateTime: value, meetupCompletedAt: null }),
        { ok: false, reason: "promise_time_missing" },
      );
    }
  });

  it("goodbye stamp: 24 hours from the SERVER-recorded meetup completion", () => {
    const completed = START + 20 * MINUTE;
    assert.deepEqual(goodbye(completed + MINUTE, ts(completed)), { ok: true });
    assert.deepEqual(goodbye(completed + 24 * HOUR, ts(completed)), { ok: true });
    assert.deepEqual(goodbye(completed + 24 * HOUR + SAFETY_STAMP_CLOCK_SKEW_GRACE_MS + 1, ts(completed)), { ok: false, reason: "too_late" });
    assert.deepEqual(goodbye(completed + 3 * 24 * HOUR, ts(completed)), { ok: false, reason: "too_late" });
    assert.deepEqual(goodbye(completed, null), { ok: false, reason: "meetup_not_completed" });
  });
});

describe("B-12 submitSafetyStamp reads no client-supplied time", () => {
  it("the callable source takes time only from the server clock and stored documents", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const source = readFileSync(resolve(__dirname, "..", "src", "safetyStamp.ts"), "utf8");
    const body = source.slice(source.indexOf("export const submitSafetyStamp"), source.indexOf("export const SAFETY_STAMP_FOLLOW_UP_REASONS"));
    assert.ok(body.includes("evaluateSafetyStampWindow("));
    assert.ok(body.includes("nowMs: Date.now()"));
    // Request fields the handler reads: ids, the phase and the opaque blob.
    const requestFields = [...body.matchAll(/\bdata\.([A-Za-z]+)/g)].map((m) => m[1]).sort();
    assert.deepEqual([...new Set(requestFields)], ["phase", "promiseId", "roomId", "verification"]);
  });
});
