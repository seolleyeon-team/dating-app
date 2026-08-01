import assert from "node:assert/strict";
import test from "node:test";

import { evaluateEmailLinkTokenExchange } from "./index";

/** Stand-in for the Admin SDK Timestamp, which is not available in unit tests. */
class FakeTimestamp {
  constructor(private readonly date: Date) {}
  toDate(): Date {
    return this.date;
  }
}

const NOW = new Date("2026-07-27T00:00:00.000Z");
const FUTURE = new FakeTimestamp(new Date("2026-07-27T00:30:00.000Z"));
const PAST = new FakeTimestamp(new Date("2026-07-26T23:30:00.000Z"));

function evaluate(tokenData: Record<string, unknown> | null, requested?: {
  kakaoUserId?: string | null;
  studentEmail?: string | null;
}) {
  return evaluateEmailLinkTokenExchange({
    tokenData,
    requestedKakaoUserId: requested?.kakaoUserId ?? null,
    requestedStudentEmail: requested?.studentEmail ?? null,
    now: NOW,
    isTimestamp: (value) => value instanceof FakeTimestamp,
    toDate: (value) =>
      value instanceof FakeTimestamp
        ? value.toDate()
        : value instanceof Date
          ? value
          : null,
  });
}

/** A token that already carries mailbox-ownership proof. */
function provenToken(overrides: Record<string, unknown> = {}) {
  return {
    email: "Victim@yonsei.ac.kr",
    kakaoUserId: "kakao_victim_1000",
    expiresAt: FUTURE,
    emailVerifiedUid: "emaillink_victim",
    emailVerifiedAt: new FakeTimestamp(NOW),
    ...overrides,
  };
}

test("a token carrying mailbox proof is exchangeable and normalizes the email", () => {
  const decision = evaluate(provenToken());
  assert.deepEqual(decision, {
    ok: true,
    kakaoUserId: "kakao_victim_1000",
    email: "victim@yonsei.ac.kr",
  });
});

test("a forged token without mailbox proof cannot be exchanged", () => {
  // The account takeover primitive: a planted document naming a victim.
  const decision = evaluate({
    email: "victim@yonsei.ac.kr",
    kakaoUserId: "kakao_victim_1000",
    expiresAt: FUTURE,
  });
  assert.deepEqual(decision, { ok: false, reason: "mailbox-unproven" });
});

test("a half-written proof marker is not accepted", () => {
  assert.deepEqual(evaluate(provenToken({ emailVerifiedUid: "" })), {
    ok: false,
    reason: "mailbox-unproven",
  });
  assert.deepEqual(evaluate(provenToken({ emailVerifiedAt: "2026-07-27" })), {
    ok: false,
    reason: "mailbox-unproven",
  });
});

test("a missing or malformed expiry is treated as expired, not as no expiry", () => {
  assert.deepEqual(evaluate(provenToken({ expiresAt: undefined })), {
    ok: false,
    reason: "expired",
  });
  assert.deepEqual(evaluate(provenToken({ expiresAt: "never" })), {
    ok: false,
    reason: "expired",
  });
  assert.deepEqual(evaluate(provenToken({ expiresAt: PAST })), {
    ok: false,
    reason: "expired",
  });
});

test("a token is single use", () => {
  assert.deepEqual(
    evaluate(provenToken({ exchangedAt: new FakeTimestamp(NOW) })),
    { ok: false, reason: "already-exchanged" }
  );
});

test("the caller cannot redirect the exchange to a different account", () => {
  assert.deepEqual(
    evaluate(provenToken(), { kakaoUserId: "kakao_attacker_2000" }),
    { ok: false, reason: "kakao-mismatch" }
  );
  assert.deepEqual(
    evaluate(provenToken(), { studentEmail: "attacker@yonsei.ac.kr" }),
    { ok: false, reason: "email-mismatch" }
  );
});

test("a caller-supplied email matching the token in a different case still passes", () => {
  const decision = evaluate(provenToken(), {
    studentEmail: "VICTIM@yonsei.ac.kr",
  });
  assert.equal(decision.ok, true);
});

test("missing and structurally broken documents are rejected", () => {
  assert.deepEqual(evaluate(null), { ok: false, reason: "missing" });
  assert.deepEqual(evaluate({ email: "victim@yonsei.ac.kr" }), {
    ok: false,
    reason: "malformed",
  });
  assert.deepEqual(evaluate({ kakaoUserId: "kakao_victim_1000" }), {
    ok: false,
    reason: "malformed",
  });
});
