import assert from "node:assert/strict";
import test from "node:test";

import { evaluateEmailLinkCompletion } from "./emailLinkCompletion";

class FakeTimestamp {
  constructor(private readonly date: Date) {}

  toDate(): Date {
    return this.date;
  }
}

const NOW = new Date("2026-08-03T00:00:00.000Z");

function token(overrides: Record<string, unknown> = {}) {
  return {
    email: "student@yonsei.ac.kr",
    kakaoUserId: "kakao_123",
    createdAt: new FakeTimestamp(new Date("2026-08-02T23:40:00.000Z")),
    expiresAt: new FakeTimestamp(new Date("2026-08-03T00:20:00.000Z")),
    ...overrides,
  };
}

test("a verified matching mailbox completes the binding", () => {
  assert.deepEqual(
    evaluateEmailLinkCompletion({
      tokenData: token(),
      authenticatedEmail: "STUDENT@YONSEI.AC.KR",
      expectedKakaoUserId: "kakao_123",
      now: NOW,
    }),
    { ok: true, kakaoUserId: "kakao_123", email: "student@yonsei.ac.kr" }
  );
});

test("a different mailbox cannot complete the binding", () => {
  assert.deepEqual(
    evaluateEmailLinkCompletion({
      tokenData: token(),
      authenticatedEmail: "other@yonsei.ac.kr",
      now: NOW,
    }),
    { ok: false, reason: "email-mismatch" }
  );
});

test("an existing local Kakao identity must match the token", () => {
  assert.deepEqual(
    evaluateEmailLinkCompletion({
      tokenData: token(),
      authenticatedEmail: "student@yonsei.ac.kr",
      expectedKakaoUserId: "kakao_other",
      now: NOW,
    }),
    { ok: false, reason: "kakao-mismatch" }
  );
});

test("missing or expired timestamps cannot be exchanged", () => {
  assert.deepEqual(
    evaluateEmailLinkCompletion({
      tokenData: token({ expiresAt: undefined }),
      authenticatedEmail: "student@yonsei.ac.kr",
      now: NOW,
    }),
    { ok: false, reason: "expired" }
  );
  assert.deepEqual(
    evaluateEmailLinkCompletion({
      tokenData: token({
        expiresAt: new FakeTimestamp(new Date("2026-08-02T23:59:59.000Z")),
      }),
      authenticatedEmail: "student@yonsei.ac.kr",
      now: NOW,
    }),
    { ok: false, reason: "expired" }
  );
});

test("a consumed token cannot be replayed", () => {
  assert.deepEqual(
    evaluateEmailLinkCompletion({
      tokenData: token({ exchangedAt: new FakeTimestamp(NOW) }),
      authenticatedEmail: "student@yonsei.ac.kr",
      now: NOW,
    }),
    { ok: false, reason: "already-exchanged" }
  );
});
