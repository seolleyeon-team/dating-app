import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import { FieldValue, Timestamp } from "firebase-admin/firestore";

import {
  buildStudentEmailBindingDoc,
  decideStudentEmailBindingClaim,
  isConfirmedStudentEmailBinding,
  normalizeStudentEmailForBinding,
  studentEmailBindingClaimError,
  studentEmailBindingId,
} from "./studentEmailBinding";

const NOW = Date.parse("2026-10-12T09:00:00.000Z");
const EMAIL = "student@yonsei.ac.kr";
const ME = "kakao_me";
const OTHER = "kakao_other";

function decide(
  overrides: Partial<Parameters<typeof decideStudentEmailBindingClaim>[0]>
) {
  return decideStudentEmailBindingClaim({
    appUserId: ME,
    normalizedEmail: EMAIL,
    nowMs: NOW,
    bindingData: null,
    boundUserData: null,
    legacyCandidates: [],
    ...overrides,
  });
}

function pendingBinding(owner: string, expiresInMs: number) {
  return {
    appUserId: owner,
    status: "pending",
    expiresAt: Timestamp.fromMillis(NOW + expiresInMs),
  };
}

// ---------------------------------------------------------------------------
// Binding id / normalization contract
// ---------------------------------------------------------------------------

test("binding id is sha256 hex of the trimmed, lowercased mailbox — the completePrimaryStudentEmailAuth contract", () => {
  const expected = createHash("sha256").update(EMAIL, "utf8").digest("hex");
  assert.equal(studentEmailBindingId(EMAIL), expected);
  assert.equal(studentEmailBindingId("  Student@YONSEI.ac.kr "), expected);
  assert.equal(normalizeStudentEmailForBinding(" Student@Yonsei.AC.KR "), EMAIL);
  assert.match(expected, /^[0-9a-f]{64}$/);
});

test("a binding without a status (written before reservations existed) counts as confirmed", () => {
  assert.equal(isConfirmedStudentEmailBinding(null), false);
  assert.equal(isConfirmedStudentEmailBinding(undefined), false);
  assert.equal(isConfirmedStudentEmailBinding({ appUserId: ME }), true);
  assert.equal(isConfirmedStudentEmailBinding({ status: "confirmed" }), true);
  assert.equal(isConfirmedStudentEmailBinding({ status: "pending" }), false);
});

// ---------------------------------------------------------------------------
// Ownership decision
// ---------------------------------------------------------------------------

test("a free mailbox can be claimed", () => {
  assert.deepEqual(decide({}), { ok: true, alreadyOwned: false });
});

test("a confirmed binding for the same account is an idempotent success", () => {
  assert.deepEqual(
    decide({ bindingData: { appUserId: ME, status: "confirmed" } }),
    { ok: true, alreadyOwned: true }
  );
  assert.deepEqual(decide({ bindingData: { appUserId: ME } }), {
    ok: true,
    alreadyOwned: true,
  });
});

test("a confirmed binding for another account is a hard conflict", () => {
  assert.deepEqual(decide({ bindingData: { appUserId: OTHER } }), {
    ok: false,
    reason: "bound_to_other_account",
  });
  assert.deepEqual(
    decide({ bindingData: { appUserId: OTHER, status: "confirmed" } }),
    { ok: false, reason: "bound_to_other_account" }
  );
});

test("an unexpired pending reservation held by another account refuses the claim", () => {
  assert.deepEqual(decide({ bindingData: pendingBinding(OTHER, 60_000) }), {
    ok: false,
    reason: "reserved_by_other_account",
  });
});

test("an expired pending reservation that was never completed is free", () => {
  assert.deepEqual(decide({ bindingData: pendingBinding(OTHER, -1) }), {
    ok: true,
    alreadyOwned: false,
  });
  // Malformed expiry is treated as expired rather than as a permanent lock.
  assert.deepEqual(
    decide({
      bindingData: { appUserId: OTHER, status: "pending", expiresAt: "junk" },
    }),
    { ok: true, alreadyOwned: false }
  );
});

test("a pending reservation whose holder already completed on its users doc is owned, expired or not", () => {
  for (const expiresInMs of [60_000, -1]) {
    assert.deepEqual(
      decide({
        bindingData: pendingBinding(OTHER, expiresInMs),
        boundUserData: { studentEmail: "Student@Yonsei.ac.kr" },
      }),
      { ok: false, reason: "bound_to_other_account" }
    );
  }
  // A different mailbox on the holder's doc does not count.
  assert.deepEqual(
    decide({
      bindingData: pendingBinding(OTHER, -1),
      boundUserData: { studentEmail: "else@yonsei.ac.kr" },
    }),
    { ok: true, alreadyOwned: false }
  );
});

test("a pending reservation for the same account can be refreshed", () => {
  assert.deepEqual(decide({ bindingData: pendingBinding(ME, 60_000) }), {
    ok: true,
    alreadyOwned: true,
  });
  assert.deepEqual(decide({ bindingData: pendingBinding(ME, -1) }), {
    ok: true,
    alreadyOwned: true,
  });
});

test("a verified account without a binding (legacy data) blocks everyone but itself", () => {
  const legacy = { id: OTHER, data: { studentEmail: EMAIL, isStudentVerified: true } };
  assert.deepEqual(decide({ legacyCandidates: [legacy] }), {
    ok: false,
    reason: "legacy_account_conflict",
  });
  assert.deepEqual(
    decide({ legacyCandidates: [{ id: ME, data: { studentEmail: EMAIL } }] }),
    { ok: true, alreadyOwned: false }
  );
  // Legacy data is checked even when a stale reservation is being taken over.
  assert.deepEqual(
    decide({ bindingData: pendingBinding(OTHER, -1), legacyCandidates: [legacy] }),
    { ok: false, reason: "legacy_account_conflict" }
  );
});

test("a binding without an owner id is treated as free", () => {
  assert.deepEqual(decide({ bindingData: { status: "confirmed" } }), {
    ok: true,
    alreadyOwned: false,
  });
});

// ---------------------------------------------------------------------------
// Document shape / errors
// ---------------------------------------------------------------------------

test("binding documents never carry the raw mailbox and clear expiry when confirmed", () => {
  const expiresAt = Timestamp.fromMillis(NOW + 1);
  const pending = buildStudentEmailBindingDoc({
    appUserId: ME,
    emailHash: "hash",
    status: "pending",
    expiresAt,
    resetCreatedAt: true,
  });
  assert.equal(pending.appUserId, ME);
  assert.equal(pending.status, "pending");
  assert.equal(pending.expiresAt, expiresAt);
  assert.ok(pending.createdAt instanceof FieldValue);
  assert.equal(JSON.stringify(pending).includes(EMAIL), false);

  const confirmed = buildStudentEmailBindingDoc({
    appUserId: ME,
    emailHash: "hash",
    status: "confirmed",
    resetCreatedAt: false,
  });
  assert.equal(confirmed.status, "confirmed");
  assert.ok((confirmed.expiresAt as FieldValue).isEqual(FieldValue.delete()));
  assert.equal("createdAt" in confirmed, false);

  assert.throws(() =>
    buildStudentEmailBindingDoc({
      appUserId: ME,
      emailHash: "hash",
      status: "pending",
      resetCreatedAt: true,
    })
  );
});

test("claim rejections map to a stable already-exists error with a detail code", () => {
  for (const reason of [
    "bound_to_other_account",
    "reserved_by_other_account",
    "legacy_account_conflict",
  ] as const) {
    const error = studentEmailBindingClaimError(reason);
    assert.equal(error.code, "already-exists");
    assert.deepEqual(error.details, { detail: reason });
  }
});
