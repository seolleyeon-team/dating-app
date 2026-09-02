import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve as resolvePath } from "node:path";
import test from "node:test";

import {
  CURRENT_TERMS_VERSION,
  REQUIRED_TERMS_DOCUMENT_IDS,
  SUPPORTED_TERMS_VERSIONS,
  buildPrimaryEmailDeliveryRequestId,
  buildCanonicalSessionClaims,
  buildPrimaryAuthNewUserShell,
  buildTermsAcceptanceRecord,
  decidePrimaryEmailAccountResolution,
  evaluatePrimaryEmailLinkTerms,
  evaluatePrimaryEmailLinkToken,
  evaluateTermsAcceptancePayload,
  readStoredTermsVersion,
  shouldRenewPrimaryEmailSend,
} from "./primaryEmailAuth";

const NOW = new Date("2026-08-31T12:00:00.000Z");
const CREATED = new Date("2026-08-31T11:50:00.000Z");
const FUTURE = new Date("2026-08-31T12:20:00.000Z");
const PAST = new Date("2026-08-31T11:55:00.000Z");

const NO_OPTIONAL_CONSENTS = { marketing: false, push: false, email: false };

test("a sent request renews after the legacy resend cooldown or token expiry", () => {
  const nowMs = NOW.getTime();
  assert.equal(
    shouldRenewPrimaryEmailSend({
      status: "sent",
      expiresAtMs: nowMs + 1,
      sentAtMs: nowMs - 59_999,
      nowMs,
    }),
    false
  );
  assert.equal(
    shouldRenewPrimaryEmailSend({
      status: "sent",
      expiresAtMs: nowMs,
      sentAtMs: nowMs - 1,
      nowMs,
    }),
    true
  );
  assert.equal(
    shouldRenewPrimaryEmailSend({
      status: "sent",
      expiresAtMs: null,
      sentAtMs: null,
      nowMs,
    }),
    true
  );
  assert.equal(
    shouldRenewPrimaryEmailSend({
      status: "sending",
      expiresAtMs: nowMs - 1,
      sentAtMs: nowMs - 60_000,
      nowMs,
    }),
    false
  );
  assert.equal(
    shouldRenewPrimaryEmailSend({
      status: "sent",
      expiresAtMs: nowMs + 20 * 60_000,
      sentAtMs: nowMs - 60_000,
      nowMs,
    }),
    true
  );
});

test("renewed sends use a fresh provider idempotency key", () => {
  assert.equal(buildPrimaryEmailDeliveryRequestId("request_12345678", 0),
    "request_12345678");
  assert.equal(buildPrimaryEmailDeliveryRequestId("request_12345678", 1),
    "request_12345678-renewal-1");
  assert.notEqual(
    buildPrimaryEmailDeliveryRequestId("request_12345678", 1),
    buildPrimaryEmailDeliveryRequestId("request_12345678", 2)
  );
});

function primaryToken(overrides: Record<string, unknown> = {}) {
  return {
    email: "Student@yonsei.ac.kr",
    purpose: "primary_auth",
    createdAt: CREATED,
    expiresAt: FUTURE,
    termsVersion: CURRENT_TERMS_VERSION,
    termsOptionalConsents: NO_OPTIONAL_CONSENTS,
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
    terms: {
      ok: true,
      version: CURRENT_TERMS_VERSION,
      optionalConsents: NO_OPTIONAL_CONSENTS,
    },
  });
});

test("pending status is accepted explicitly as well as on legacy primary tokens", () => {
  assert.deepEqual(evaluateToken(primaryToken({ status: "pending" })), {
    ok: true,
    email: "student@yonsei.ac.kr",
    terms: {
      ok: true,
      version: CURRENT_TERMS_VERSION,
      optionalConsents: NO_OPTIONAL_CONSENTS,
    },
  });
});

test("completed token can recover the same account result until expiry", () => {
  assert.deepEqual(
    evaluateToken(
      primaryToken({
        status: "completed",
        completedAppUserId: "app_uid_1",
        completedIsNewUser: true,
      })
    ),
    {
      ok: true,
      email: "student@yonsei.ac.kr",
      terms: {
        ok: true,
        version: CURRENT_TERMS_VERSION,
        optionalConsents: NO_OPTIONAL_CONSENTS,
      },
      completedAppUserId: "app_uid_1",
      completedIsNewUser: true,
    }
  );
});

test("completed token without a complete recovery marker is malformed", () => {
  assert.deepEqual(
    evaluateToken(primaryToken({ status: "completed" })),
    { ok: false, reason: "malformed" }
  );
  assert.deepEqual(
    evaluateToken(
      primaryToken({
        status: "completed",
        completedAppUserId: "app_uid_1",
        completedIsNewUser: "yes",
      })
    ),
    { ok: false, reason: "malformed" }
  );
});

test("unknown primary token status is rejected fail-closed", () => {
  assert.deepEqual(evaluateToken(primaryToken({ status: "sending" })), {
    ok: false,
    reason: "malformed",
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
    termsVersion: CURRENT_TERMS_VERSION,
    termsOptionalConsents: NO_OPTIONAL_CONSENTS,
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
    "termsAcceptance",
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
  // terms-gate contract §3/§5: an account is never created without a record.
  const acceptance = shell.termsAcceptance as Record<string, unknown>;
  assert.equal(acceptance.schemaVersion, 1);
  assert.equal(acceptance.version, CURRENT_TERMS_VERSION);
  assert.equal(acceptance.source, "primary_auth_token");
  assert.deepEqual(acceptance.requiredDocumentIds, [
    "termsOfService",
    "privacyPolicy",
    "kakaoNamePhone",
    "ageOver20",
  ]);
  assert.deepEqual(acceptance.optionalConsents, NO_OPTIONAL_CONSENTS);
  assert.ok(acceptance.acceptedAt);
  assert.ok(acceptance.optionalUpdatedAt);
  // ageOver18 is not a UI item and must never be fabricated.
  assert.equal(
    JSON.stringify(shell).includes("ageOver18"),
    false
  );
});

// ============================================================================
// Terms constants (terms-gate contract §2/§3)
// ============================================================================

test("terms constants match the contract exactly", () => {
  assert.equal(CURRENT_TERMS_VERSION, "2026-05-16");
  assert.deepEqual([...SUPPORTED_TERMS_VERSIONS], ["2026-05-16"]);
  assert.deepEqual(
    [...REQUIRED_TERMS_DOCUMENT_IDS],
    ["termsOfService", "privacyPolicy", "kakaoNamePhone", "ageOver20"]
  );
  // ageOver18 is never a required (or accepted) document id.
  assert.equal(REQUIRED_TERMS_DOCUMENT_IDS.includes("ageOver18"), false);
});

// ============================================================================
// evaluateTermsAcceptancePayload (contract §4)
// ============================================================================

function acceptancePayload(overrides: Record<string, unknown> = {}) {
  return {
    version: CURRENT_TERMS_VERSION,
    acceptedDocumentIds: [...REQUIRED_TERMS_DOCUMENT_IDS],
    ...overrides,
  };
}

test("a complete acceptance payload passes with all optional consents false", () => {
  assert.deepEqual(evaluateTermsAcceptancePayload(acceptancePayload()), {
    ok: true,
    version: CURRENT_TERMS_VERSION,
    optionalConsents: NO_OPTIONAL_CONSENTS,
  });
});

test("an absent or non-record payload fails closed as terms_acceptance_required", () => {
  for (const raw of [undefined, null, "", "yes", 1, true, [], [1, 2]]) {
    assert.deepEqual(
      evaluateTermsAcceptancePayload(raw),
      { ok: false, reason: "terms_acceptance_required" },
      `payload=${JSON.stringify(raw)}`
    );
  }
});

test("a missing version is terms_acceptance_required, a wrong one is terms_version_outdated", () => {
  assert.deepEqual(
    evaluateTermsAcceptancePayload(acceptancePayload({ version: undefined })),
    { ok: false, reason: "terms_acceptance_required" }
  );
  assert.deepEqual(
    evaluateTermsAcceptancePayload(acceptancePayload({ version: null })),
    { ok: false, reason: "terms_acceptance_required" }
  );
  for (const version of ["2025-01-01", "2099-12-31", "  ", 20260516, {}]) {
    assert.deepEqual(
      evaluateTermsAcceptancePayload(acceptancePayload({ version })),
      { ok: false, reason: "terms_version_outdated" },
      `version=${JSON.stringify(version)}`
    );
  }
});

test("every single missing required document id blocks acceptance", () => {
  for (const missing of REQUIRED_TERMS_DOCUMENT_IDS) {
    const acceptedDocumentIds = REQUIRED_TERMS_DOCUMENT_IDS.filter(
      (id) => id !== missing
    );
    assert.deepEqual(
      evaluateTermsAcceptancePayload(
        acceptancePayload({ acceptedDocumentIds })
      ),
      { ok: false, reason: "terms_acceptance_required" },
      `missing=${missing}`
    );
  }
});

test("acceptedDocumentIds must be an array of strings", () => {
  for (const acceptedDocumentIds of [
    undefined,
    null,
    "termsOfService",
    { termsOfService: true },
  ]) {
    assert.deepEqual(
      evaluateTermsAcceptancePayload(
        acceptancePayload({ acceptedDocumentIds })
      ),
      { ok: false, reason: "terms_acceptance_required" },
      `ids=${JSON.stringify(acceptedDocumentIds)}`
    );
  }
  // Non-string entries are discarded, so they can never satisfy a required id.
  assert.deepEqual(
    evaluateTermsAcceptancePayload(
      acceptancePayload({
        acceptedDocumentIds: [
          "termsOfService",
          "privacyPolicy",
          "kakaoNamePhone",
          true,
        ],
      })
    ),
    { ok: false, reason: "terms_acceptance_required" }
  );
});

test("unknown accepted ids are ignored safely and never fabricate ageOver18", () => {
  const decision = evaluateTermsAcceptancePayload(
    acceptancePayload({
      acceptedDocumentIds: [
        ...REQUIRED_TERMS_DOCUMENT_IDS,
        "ageOver18",
        "somethingElse",
        "__proto__",
      ],
    })
  );
  assert.equal(decision.ok, true);
  assert.equal(JSON.stringify(decision).includes("ageOver18"), false);
  assert.equal(JSON.stringify(decision).includes("somethingElse"), false);
});

test("optional consents default to false and are coerced to strict booleans", () => {
  // No optionalConsents key at all.
  assert.deepEqual(
    evaluateTermsAcceptancePayload(acceptancePayload()),
    {
      ok: true,
      version: CURRENT_TERMS_VERSION,
      optionalConsents: NO_OPTIONAL_CONSENTS,
    }
  );
  // Malformed blob must NOT record consent (the legacy `fallback: true` bug).
  for (const optionalConsents of [null, "all", 1, []]) {
    const decision = evaluateTermsAcceptancePayload(
      acceptancePayload({ optionalConsents })
    );
    assert.deepEqual(
      decision.ok && decision.optionalConsents,
      NO_OPTIONAL_CONSENTS,
      `optionalConsents=${JSON.stringify(optionalConsents)}`
    );
  }
  // Truthy-but-not-true values are false; only literal true opts in.
  const coerced = evaluateTermsAcceptancePayload(
    acceptancePayload({
      optionalConsents: {
        marketing: true,
        push: "true",
        email: 1,
      },
    })
  );
  assert.deepEqual(coerced.ok && coerced.optionalConsents, {
    marketing: true,
    push: false,
    email: false,
  });
  const allOn = evaluateTermsAcceptancePayload(
    acceptancePayload({
      optionalConsents: { marketing: true, push: true, email: true },
    })
  );
  assert.deepEqual(allOn.ok && allOn.optionalConsents, {
    marketing: true,
    push: true,
    email: true,
  });
});

// ============================================================================
// buildTermsAcceptanceRecord (contract §3)
// ============================================================================

test("acceptance record carries the contract §3 shape for both sources", () => {
  for (const source of ["primary_auth_token", "authenticated_reconsent"] as const) {
    const record = buildTermsAcceptanceRecord({
      version: CURRENT_TERMS_VERSION,
      optionalConsents: { marketing: true, push: false, email: true },
      source,
    });
    assert.deepEqual(Object.keys(record).sort(), [
      "acceptedAt",
      "optionalConsents",
      "optionalUpdatedAt",
      "requiredDocumentIds",
      "schemaVersion",
      "source",
      "version",
    ]);
    assert.equal(record.source, source);
    assert.equal(record.schemaVersion, 1);
    assert.equal(record.version, CURRENT_TERMS_VERSION);
    assert.deepEqual(record.requiredDocumentIds, [
      ...REQUIRED_TERMS_DOCUMENT_IDS,
    ]);
    assert.deepEqual(record.optionalConsents, {
      marketing: true,
      push: false,
      email: true,
    });
  }
});

test("acceptance record copies requiredDocumentIds instead of aliasing the constant", () => {
  const record = buildTermsAcceptanceRecord({
    version: CURRENT_TERMS_VERSION,
    optionalConsents: NO_OPTIONAL_CONSENTS,
    source: "primary_auth_token",
  });
  assert.notEqual(record.requiredDocumentIds, REQUIRED_TERMS_DOCUMENT_IDS);
});

// ============================================================================
// Terms proof on the emailLinkTokens document (contract §4/§5)
// ============================================================================

test("a token carrying the current version yields a valid terms proof", () => {
  assert.deepEqual(
    evaluatePrimaryEmailLinkTerms({
      termsVersion: CURRENT_TERMS_VERSION,
      termsOptionalConsents: { marketing: true, push: false, email: false },
    }),
    {
      ok: true,
      version: CURRENT_TERMS_VERSION,
      optionalConsents: { marketing: true, push: false, email: false },
    }
  );
});

test("a token with no terms proof rejects as terms-missing", () => {
  for (const tokenData of [
    null,
    undefined,
    {},
    { termsVersion: "" },
    { termsVersion: "   " },
    { termsVersion: null },
    { termsVersion: 20260516 },
  ]) {
    assert.deepEqual(
      evaluatePrimaryEmailLinkTerms(tokenData),
      { ok: false, reason: "terms-missing" },
      `tokenData=${JSON.stringify(tokenData)}`
    );
  }
});

test("a token carrying an unsupported version rejects as terms-stale", () => {
  assert.deepEqual(
    evaluatePrimaryEmailLinkTerms({ termsVersion: "2025-01-01" }),
    { ok: false, reason: "terms-stale" }
  );
});

test("token evaluation surfaces terms-missing without failing the token itself", () => {
  // Existing accounts must not be locked out by a token that predates the
  // gate: the token still resolves, only the terms proof is absent.
  const decision = evaluateToken(
    primaryToken({ termsVersion: undefined, termsOptionalConsents: undefined })
  );
  assert.equal(decision.ok, true);
  assert.deepEqual(decision.ok && decision.terms, {
    ok: false,
    reason: "terms-missing",
  });
});

test("token evaluation surfaces terms-stale for an outdated recorded version", () => {
  const decision = evaluateToken(primaryToken({ termsVersion: "2025-01-01" }));
  assert.equal(decision.ok, true);
  assert.deepEqual(decision.ok && decision.terms, {
    ok: false,
    reason: "terms-stale",
  });
});

test("terms proof is never consulted before the pre-existing rejections", () => {
  // All nine pre-existing rejection paths keep their exact reason even when
  // the token carries a perfectly valid terms proof, and vice versa.
  assert.deepEqual(evaluateToken(null), { ok: false, reason: "missing" });
  assert.deepEqual(
    evaluateToken(primaryToken({ purpose: "verify", termsVersion: undefined })),
    { ok: false, reason: "malformed" }
  );
  assert.deepEqual(
    evaluateToken(primaryToken({ kakaoUserId: "1", termsVersion: undefined })),
    { ok: false, reason: "malformed" }
  );
  assert.deepEqual(
    evaluateToken(primaryToken({ termsVersion: undefined }), "other@yonsei.ac.kr"),
    { ok: false, reason: "email-mismatch" }
  );
  assert.deepEqual(
    evaluateToken(primaryToken({ expiresAt: PAST, termsVersion: undefined })),
    { ok: false, reason: "expired" }
  );
});

// ============================================================================
// readStoredTermsVersion
// ============================================================================

test("stored acceptance version is read only from a well-formed record", () => {
  assert.equal(readStoredTermsVersion(null), null);
  assert.equal(readStoredTermsVersion(undefined), null);
  assert.equal(readStoredTermsVersion({}), null);
  assert.equal(readStoredTermsVersion({ termsAcceptance: "yes" }), null);
  assert.equal(readStoredTermsVersion({ termsAcceptance: {} }), null);
  assert.equal(
    readStoredTermsVersion({ termsAcceptance: { version: "  " } }),
    null
  );
  assert.equal(
    readStoredTermsVersion({
      termsAcceptance: { version: CURRENT_TERMS_VERSION },
    }),
    CURRENT_TERMS_VERSION
  );
});

// ============================================================================
// Source contract: ordering and token-document payload
// ============================================================================

// Compiled tests live under lib/; source under src/.
const authSrc = readFileSync(
  resolvePath(__dirname, "../src/primaryEmailAuth.ts"),
  "utf8"
);
const sendFnSrc = authSrc.slice(
  authSrc.indexOf("export function createSendPrimaryStudentEmailLinkFunction")
);

test("sendPrimaryStudentEmailLink validates terms before spending any quota", () => {
  const termsIdx = sendFnSrc.indexOf("evaluateTermsAcceptancePayload(");
  const rateIdx = sendFnSrc.indexOf("decideStudentVerificationRateLimit(");
  const txIdx = sendFnSrc.indexOf("db.runTransaction(");
  const requestRefIdx = sendFnSrc.indexOf("studentVerificationEmailRequests");
  assert.ok(termsIdx > 0, "terms validation must exist in the send callable");
  assert.ok(rateIdx > 0 && txIdx > 0 && requestRefIdx > 0);
  // A malformed payload must not consume rate-limit quota or an idempotency
  // slot, so validation runs before the reservation transaction.
  assert.ok(termsIdx < rateIdx, "terms must be validated before the rate limit");
  assert.ok(termsIdx < txIdx, "terms must be validated before the transaction");
  assert.ok(
    termsIdx < requestRefIdx,
    "terms must be validated before the idempotency doc"
  );
});

test("the emailLinkTokens write carries the terms proof but no raw payload", () => {
  const match = authSrc.match(
    /collection\("emailLinkTokens"\)\.doc\(token\), \{([\s\S]*?)\n {8}\}\);/
  );
  assert.ok(match, "emailLinkTokens write block not found");
  const tokenWrite = match[1];
  for (const field of [
    "termsVersion",
    "termsAcceptedAt",
    "termsOptionalConsents",
  ]) {
    assert.ok(
      tokenWrite.includes(field),
      `token write must persist ${field}`
    );
  }
  // The document is world-readable by id: no raw acceptance payload, no
  // accepted-document list, no extra identity beyond the existing email.
  assert.doesNotMatch(tokenWrite, /acceptedDocumentIds/);
  assert.doesNotMatch(tokenWrite, /termsAcceptance\b/);
  assert.doesNotMatch(tokenWrite, /data\.termsAcceptance/);
});

test("completePrimaryStudentEmailAuth enforces terms only for new accounts", () => {
  const completeSrc = authSrc.slice(
    authSrc.indexOf(
      "export function createCompletePrimaryStudentEmailAuthFunction"
    )
  );
  // The throw is guarded by isNewUser, so existing users are never locked out.
  assert.match(
    completeSrc,
    /if \(decision\.isNewUser && !terms\.ok\) \{\s*\n\s*throw tokenError\(terms\.reason\);/
  );
  // ...and it precedes every transaction write.
  const throwIdx = completeSrc.indexOf("throw tokenError(terms.reason)");
  const firstWriteIdx = completeSrc.indexOf("transaction.set(");
  assert.ok(throwIdx > 0 && firstWriteIdx > throwIdx);
});
