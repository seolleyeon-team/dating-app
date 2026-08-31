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
