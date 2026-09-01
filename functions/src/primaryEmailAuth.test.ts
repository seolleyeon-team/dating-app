import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCanonicalSessionClaims,
  buildPrimaryAuthNewUserShell,
  decidePrimaryEmailAccountResolution,
  evaluatePrimaryEmailLinkToken,
} from "./primaryEmailAuth";

const NOW = new Date("2026-08-31T12:00:00.000Z");
const CREATED = new Date("2026-08-31T11:50:00.000Z");
const FUTURE = new Date("2026-08-31T12:20:00.000Z");
const PAST = new Date("2026-08-31T11:55:00.000Z");

function primaryToken(overrides: Record<string, unknown> = {}) {
  return {
    email: "Student@yonsei.ac.kr",
    purpose: "primary_auth",
    createdAt: CREATED,
    expiresAt: FUTURE,
    ...overrides,
  };
}

function evaluateToken(
  tokenData: Record<string, unknown> | null,
  authenticatedEmail: unknown = "student@yonsei.ac.kr"
) {
  return evaluatePrimaryEmailLinkToken({
    tokenData,
    authenticatedEmail,
    now: NOW,
  });
}

// ============================================================================
// evaluatePrimaryEmailLinkToken
// ============================================================================

test("primary token with matching mailbox proof passes and normalizes the email", () => {
  assert.deepEqual(evaluateToken(primaryToken()), {
    ok: true,
    email: "student@yonsei.ac.kr",
  });
});

test("consumed or missing token documents are rejected as missing", () => {
  assert.deepEqual(evaluateToken(null), { ok: false, reason: "missing" });
});

test("a legacy Kakao-shaped token cannot complete through the primary flow", () => {
  // Legacy shape: kakaoUserId, no purpose.
  assert.deepEqual(
    evaluateToken({
      email: "student@yonsei.ac.kr",
      kakaoUserId: "12345",
      createdAt: CREATED,
      expiresAt: FUTURE,
    }),
    { ok: false, reason: "malformed" }
  );
  // Purpose set but a kakaoUserId smuggled in.
  assert.deepEqual(
    evaluateToken(primaryToken({ kakaoUserId: "12345" })),
    { ok: false, reason: "malformed" }
  );
  // Wrong purpose value.
  assert.deepEqual(evaluateToken(primaryToken({ purpose: "verify" })), {
    ok: false,
    reason: "malformed",
  });
});

test("non-Yonsei or missing emails are malformed", () => {
  assert.deepEqual(
    evaluateToken(primaryToken({ email: "student@gmail.com" })),
    { ok: false, reason: "malformed" }
  );
  assert.deepEqual(evaluateToken(primaryToken({ email: null })), {
    ok: false,
    reason: "malformed",
  });
  assert.deepEqual(evaluateToken(primaryToken(), "not-a-yonsei-email"), {
    ok: false,
    reason: "malformed",
  });
});

test("token email must match the authenticated session email", () => {
  assert.deepEqual(evaluateToken(primaryToken(), "other@yonsei.ac.kr"), {
    ok: false,
    reason: "email-mismatch",
  });
});

test("case-only differences between token and session email still pass", () => {
  assert.equal(
    evaluateToken(primaryToken(), "STUDENT@yonsei.ac.kr").ok,
    true
  );
});

test("expired, missing, or malformed timestamps reject as expired", () => {
  assert.deepEqual(evaluateToken(primaryToken({ expiresAt: PAST })), {
    ok: false,
    reason: "expired",
  });
  assert.deepEqual(evaluateToken(primaryToken({ expiresAt: undefined })), {
    ok: false,
    reason: "expired",
  });
  assert.deepEqual(evaluateToken(primaryToken({ createdAt: "never" })), {
    ok: false,
    reason: "expired",
  });
  // expiresAt exactly now is already expired.
  assert.deepEqual(evaluateToken(primaryToken({ expiresAt: NOW })), {
    ok: false,
    reason: "expired",
  });
});

test("a createdAt more than five minutes in the future is rejected (clock skew guard)", () => {
  const farFuture = new Date(NOW.getTime() + 6 * 60 * 1000);
  assert.deepEqual(evaluateToken(primaryToken({ createdAt: farFuture })), {
    ok: false,
    reason: "expired",
  });
  const withinSkew = new Date(NOW.getTime() + 4 * 60 * 1000);
  assert.equal(
    evaluateToken(primaryToken({ createdAt: withinSkew })).ok,
    true
  );
});

test("Timestamp-like objects with toDate() are accepted", () => {
  const decision = evaluateToken(
    primaryToken({
      createdAt: { toDate: () => CREATED },
      expiresAt: { toDate: () => FUTURE },
    })
  );
  assert.equal(decision.ok, true);
});

// ============================================================================
// decidePrimaryEmailAccountResolution
// ============================================================================

const EMAIL = "student@yonsei.ac.kr";

function resolve(overrides: Partial<Parameters<
  typeof decidePrimaryEmailAccountResolution
>[0]> = {}) {
  return decidePrimaryEmailAccountResolution({
    authUid: "emaillink_uid_1",
    normalizedEmail: EMAIL,
    bindingData: null,
    bindingUserData: null,
    legacyCandidates: [],
    authUidUserData: null,
    ...overrides,
  });
}

test("binding hit resolves to the bound appUserId without recreating the binding", () => {
  const decision = resolve({
    bindingData: { appUserId: "kakao_legacy_1" },
    bindingUserData: { isStudentVerified: true, studentEmail: EMAIL },
  });
  assert.deepEqual(decision, {
    ok: true,
    appUserId: "kakao_legacy_1",
    isNewUser: false,
    createBinding: false,
    userData: { isStudentVerified: true, studentEmail: EMAIL },
  });
});

test("binding pointing at a missing user doc is an identity conflict", () => {
  assert.deepEqual(
    resolve({
      bindingData: { appUserId: "kakao_legacy_1" },
      bindingUserData: null,
    }),
    { ok: false, reason: "identity_conflict" }
  );
  assert.deepEqual(
    resolve({ bindingData: { appUserId: "" }, bindingUserData: {} }),
    { ok: false, reason: "identity_conflict" }
  );
});

test("legacy single verified candidate resolves and lazily backfills the binding", () => {
  const decision = resolve({
    legacyCandidates: [
      {
        id: "kakao_legacy_9",
        data: { isStudentVerified: true, studentEmail: EMAIL },
      },
    ],
  });
  assert.deepEqual(decision, {
    ok: true,
    appUserId: "kakao_legacy_9",
    isNewUser: false,
    createBinding: true,
    userData: { isStudentVerified: true, studentEmail: EMAIL },
  });
});

test("an unverified legacy candidate never resolves (fail closed)", () => {
  assert.deepEqual(
    resolve({
      legacyCandidates: [
        { id: "kakao_legacy_9", data: { studentEmail: EMAIL } },
      ],
    }),
    { ok: false, reason: "identity_conflict" }
  );
});

test("two or more legacy candidates are an identity conflict, never auto-merged", () => {
  assert.deepEqual(
    resolve({
      legacyCandidates: [
        { id: "a", data: { isStudentVerified: true, studentEmail: EMAIL } },
        { id: "b", data: { isStudentVerified: true, studentEmail: EMAIL } },
      ],
    }),
    { ok: false, reason: "identity_conflict" }
  );
});

test("no binding and no legacy account creates a new user under the auth uid", () => {
  assert.deepEqual(resolve(), {
    ok: true,
    appUserId: "emaillink_uid_1",
    isNewUser: true,
    createBinding: true,
    userData: null,
  });
});

test("an existing doc under the auth uid is merged, not treated as new", () => {
  const decision = resolve({
    authUidUserData: { studentEmail: EMAIL, isStudentVerified: true },
  });
  assert.equal(decision.ok, true);
  assert.equal(decision.ok && decision.isNewUser, false);
  assert.equal(decision.ok && decision.createBinding, true);
});

test("every restricted status blocks resolution with rejoin_restricted", () => {
  for (const status of [
    "deleting",
    "banned",
    "blocked",
    "restricted_rejoin",
    "suspended",
    "withdrawn",
  ]) {
    assert.deepEqual(
      resolve({
        bindingData: { appUserId: "kakao_legacy_1" },
        bindingUserData: { isStudentVerified: true, status },
      }),
      { ok: false, reason: "rejoin_restricted" },
      `status=${status}`
    );
  }
  assert.deepEqual(
    resolve({
      bindingData: { appUserId: "kakao_legacy_1" },
      bindingUserData: { isStudentVerified: true, loginDisabled: true },
    }),
    { ok: false, reason: "rejoin_restricted" }
  );
  assert.deepEqual(
    resolve({
      bindingData: { appUserId: "kakao_legacy_1" },
      bindingUserData: { isStudentVerified: true, isWithdrawn: true },
    }),
    { ok: false, reason: "rejoin_restricted" }
  );
});

test("rejoin guard also applies to legacy candidates and existing auth-uid docs", () => {
  assert.deepEqual(
    resolve({
      legacyCandidates: [
        {
          id: "kakao_legacy_9",
          data: { isStudentVerified: true, status: "withdrawn" },
        },
      ],
    }),
    { ok: false, reason: "rejoin_restricted" }
  );
  assert.deepEqual(
    resolve({ authUidUserData: { status: "banned" } }),
    { ok: false, reason: "rejoin_restricted" }
  );
});

test("an account already bound to a different mailbox is rejected", () => {
  assert.deepEqual(
    resolve({
      bindingData: { appUserId: "kakao_legacy_1" },
      bindingUserData: {
        isStudentVerified: true,
        studentEmail: "other@yonsei.ac.kr",
      },
    }),
    { ok: false, reason: "email_mismatch" }
  );
});

test("an active status like a normal account passes the guard", () => {
  const decision = resolve({
    bindingData: { appUserId: "kakao_legacy_1" },
    bindingUserData: { isStudentVerified: true, status: "active" },
  });
  assert.equal(decision.ok, true);
});

// ============================================================================
// buildCanonicalSessionClaims
// ============================================================================

test("canonical claims always carry appSession and primaryAuth", () => {
  assert.deepEqual(buildCanonicalSessionClaims("uid_1", null), {
    appSession: true,
    primaryAuth: "yonsei_email",
  });
});

test("legacy kakaoUserId claim is minted only when the doc id matches", () => {
  assert.deepEqual(
    buildCanonicalSessionClaims("12345", { kakaoUserId: "12345" }),
    { appSession: true, primaryAuth: "yonsei_email", kakaoUserId: "12345" }
  );
  // kakaoUserId stored but under a different appUserId: no claim.
  assert.deepEqual(
    buildCanonicalSessionClaims("emaillink_uid", { kakaoUserId: "12345" }),
    { appSession: true, primaryAuth: "yonsei_email" }
  );
  assert.deepEqual(buildCanonicalSessionClaims("emaillink_uid", {}), {
    appSession: true,
    primaryAuth: "yonsei_email",
  });
});

// ============================================================================
// buildPrimaryAuthNewUserShell
// ============================================================================

test("new user shell carries exactly the contract fields with fail-closed defaults", () => {
  const shell = buildPrimaryAuthNewUserShell({
    appUserId: "emaillink_uid_1",
    studentEmail: EMAIL,
  });
  assert.deepEqual(Object.keys(shell).sort(), [
    "appUserId",
    "createdAt",
    "isStudentVerified",
    "kakaoFriendAvoidanceEnabled",
    "kakaoFriendReconcileStatus",
    "kakaoFriendSnapshot",
    "lastLoginAt",
    "profileImageMode",
    "profileImageUrl",
    "recommendationPrivacyReady",
    "studentEmail",
    "studentVerifiedAt",
  ]);
  assert.equal(shell.appUserId, "emaillink_uid_1");
  assert.equal(shell.studentEmail, EMAIL);
  assert.equal(shell.isStudentVerified, true);
  assert.equal(shell.profileImageUrl, "");
  assert.equal(shell.profileImageMode, "avatar");
  // Fail-closed recommendation defaults.
  assert.equal(shell.kakaoFriendAvoidanceEnabled, false);
  assert.equal(shell.recommendationPrivacyReady, false);
  assert.equal(shell.kakaoFriendReconcileStatus, "pending");
  // kakao-friend-pairs contract §3/§7: the one-time snapshot starts pending.
  assert.deepEqual(shell.kakaoFriendSnapshot, {
    status: "not_started",
    schemaVersion: 1,
  });
});
