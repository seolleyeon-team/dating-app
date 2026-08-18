import assert from "node:assert/strict";
import test from "node:test";

import {
  buildStudentVerificationEmail,
  decideStudentVerificationRateLimit,
  normalizeYonseiEmail,
  STUDENT_VERIFICATION_DAY_WINDOW_MS,
  STUDENT_VERIFICATION_MAX_PER_DAY,
  STUDENT_VERIFICATION_MAX_PER_MINUTE,
  STUDENT_VERIFICATION_MINUTE_WINDOW_MS,
} from "./studentVerificationEmail";

test("student verification accepts only normalized Yonsei email addresses", () => {
  assert.equal(normalizeYonseiEmail(" Student@Yonsei.Ac.Kr "), "student@yonsei.ac.kr");
  assert.equal(normalizeYonseiEmail("student@cs.yonsei.ac.kr"), null);
  assert.equal(normalizeYonseiEmail("student@example.com"), null);
  assert.equal(normalizeYonseiEmail("student @yonsei.ac.kr"), null);
});

test("student verification allows at most two emails per minute per address", () => {
  const now = 1_000_000;
  assert.deepEqual(
    decideStudentVerificationRateLimit(
      {
        minuteWindowStartedAtMs: now - 1,
        minuteRequestCount: STUDENT_VERIFICATION_MAX_PER_MINUTE,
      },
      now
    ),
    { allowed: false, retryAfterMs: STUDENT_VERIFICATION_MINUTE_WINDOW_MS - 1 }
  );
});

test("student verification allows at most ten emails per rolling day per address", () => {
  const now = 1_000_000;
  assert.deepEqual(
    decideStudentVerificationRateLimit(
      {
        dayWindowStartedAtMs: now - 1,
        dayRequestCount: STUDENT_VERIFICATION_MAX_PER_DAY,
      },
      now
    ),
    { allowed: false, retryAfterMs: STUDENT_VERIFICATION_DAY_WINDOW_MS - 1 }
  );
});

test("student verification email escapes the opaque Firebase action link", () => {
  const email = buildStudentVerificationEmail('https://example.test/?q="<unsafe>');
  assert.equal(email.subject, "설레연에서 온 인증 메일");
  assert.match(email.html, /q=&quot;&lt;unsafe&gt;/);
  assert.match(email.text, /https:\/\/example\.test/);
});
