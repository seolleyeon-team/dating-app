/**
 * P0-1 — reservation helper atomicity and its interplay with the primary
 * (Yonsei-email-first) completion callable, against the Firestore Emulator.
 *
 * Run (repo root, JDK 21):
 *   npx tsc -p functions --outDir functions/.p01-verify-lib
 *   firebase emulators:exec --only firestore --project demo-p01-binding \
 *     "node --test functions/.p01-verify-lib/studentEmailReservation.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import type { Auth } from "firebase-admin/auth";
import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error(
    "FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`."
  );
}

import { createCompletePrimaryStudentEmailAuthFunction } from "./primaryEmailAuth";
import {
  claimStudentEmailBinding,
  studentEmailBindingId,
} from "./studentEmailBinding";

initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-p01-binding" });
const db = getFirestore();

let seq = 0;
function fresh(prefix: string): string {
  seq += 1;
  return `${prefix}_${Date.now().toString(36)}_${seq}`;
}

function fakeAuth(emailByUid: Record<string, string>): Auth {
  return {
    async getUser(uid: string) {
      return { uid, email: emailByUid[uid], emailVerified: true };
    },
    async createCustomToken(uid: string) {
      return `custom-token-for-${uid}`;
    },
  } as unknown as Auth;
}

async function bindingFor(email: string): Promise<Record<string, unknown> | null> {
  const snap = await db
    .collection("studentEmailBindings")
    .doc(studentEmailBindingId(email))
    .get();
  return snap.exists ? ((snap.data() ?? {}) as Record<string, unknown>) : null;
}

async function userDoc(uid: string): Promise<Record<string, unknown>> {
  return ((await db.collection("users").doc(uid).get()).data() ?? {}) as Record<
    string,
    unknown
  >;
}

const inMs = (ms: number) => Timestamp.fromMillis(Date.now() + ms);

function reserve(uid: string, email: string, expiresAt: Timestamp) {
  return db.runTransaction((tx) =>
    claimStudentEmailBinding(db, tx, {
      appUserId: uid,
      email,
      mode: "pending",
      expiresAt,
    })
  );
}

function confirm(uid: string, email: string) {
  return db.runTransaction((tx) =>
    claimStudentEmailBinding(db, tx, { appUserId: uid, email, mode: "confirmed" })
  );
}

test("concurrent pending reservations for one mailbox yield exactly one holder (5 rounds)", async () => {
  for (let round = 0; round < 5; round += 1) {
    const a = fresh("res_a");
    const b = fresh("res_b");
    const email = `${fresh("res")}@yonsei.ac.kr`;
    const results = await Promise.all([
      reserve(a, email, inMs(60_000)),
      reserve(b, email, inMs(60_000)),
    ]);
    const okCount = results.filter((r) => r.ok).length;
    assert.equal(okCount, 1, `round ${round}: exactly one reservation`);
    const binding = await bindingFor(email);
    assert.equal(binding?.status, "pending");
    assert.ok([a, b].includes(String(binding?.appUserId)));
    const loser = results[0].ok ? b : a;
    assert.notEqual(binding?.appUserId, loser);
  }
});

test("an expired reservation held by another account is taken over; a confirmed one is not", async () => {
  const a = fresh("exp_a");
  const b = fresh("exp_b");
  const email = `${fresh("exp")}@yonsei.ac.kr`;

  assert.equal((await reserve(a, email, inMs(-1000))).ok, true);
  assert.equal((await reserve(b, email, inMs(60_000))).ok, true);
  assert.equal((await bindingFor(email))?.appUserId, b);

  assert.equal((await confirm(b, email)).ok, true);
  const binding = await bindingFor(email);
  assert.equal(binding?.status, "confirmed");
  assert.equal("expiresAt" in (binding ?? {}), false);

  const again = await reserve(a, email, inMs(60_000));
  assert.deepEqual(again, { ok: false, reason: "bound_to_other_account" });
  assert.equal((await bindingFor(email))?.appUserId, b);
});

test("an unexpired reservation held by another account refuses a second reservation and a confirmation", async () => {
  const a = fresh("live_a");
  const b = fresh("live_b");
  const email = `${fresh("live")}@yonsei.ac.kr`;

  assert.equal((await reserve(a, email, inMs(60_000))).ok, true);
  assert.deepEqual(await reserve(b, email, inMs(60_000)), {
    ok: false,
    reason: "reserved_by_other_account",
  });
  assert.deepEqual(await confirm(b, email), {
    ok: false,
    reason: "reserved_by_other_account",
  });
  assert.equal((await bindingFor(email))?.appUserId, a);
});

test("a confirmed binding is never downgraded by the owner's later reservation", async () => {
  const a = fresh("own_a");
  const email = `${fresh("own")}@yonsei.ac.kr`;
  assert.equal((await confirm(a, email)).ok, true);
  assert.deepEqual(await reserve(a, email, inMs(60_000)), {
    ok: true,
    alreadyOwned: true,
  });
  const binding = await bindingFor(email);
  assert.equal(binding?.status, "confirmed");
  assert.equal("expiresAt" in (binding ?? {}), false);
});

test("an account that already holds the mailbox on its users doc (legacy data) gets a confirmed binding, not a lapsing reservation", async () => {
  const legacy = fresh("legacy");
  const email = `${fresh("legacy")}@yonsei.ac.kr`;
  await db.collection("users").doc(legacy).set({
    kakaoUserId: legacy,
    isStudentVerified: true,
    studentEmail: email,
  });
  assert.equal((await reserve(legacy, email, inMs(60_000))).ok, true);
  assert.equal((await bindingFor(email))?.status, "confirmed");

  const other = fresh("other");
  assert.deepEqual(await reserve(other, email, inMs(60_000)), {
    ok: false,
    reason: "bound_to_other_account",
  });
});

test("primary flow: a pending reservation by another account never resolves the mailbox owner into that account", async () => {
  const attacker = fresh("kakao_att");
  const email = `${fresh("victim")}@yonsei.ac.kr`;
  await db.collection("users").doc(attacker).set({ kakaoUserId: attacker });
  assert.equal((await reserve(attacker, email, inMs(30 * 60 * 1000))).ok, true);

  const victimSession = fresh("emaillink_victim");
  const now = Date.now();
  const tokenId = fresh("ptok");
  await db.collection("emailLinkTokens").doc(tokenId).set({
    email,
    purpose: "primary_auth",
    createdAt: Timestamp.fromMillis(now),
    expiresAt: Timestamp.fromMillis(now + 30 * 60 * 1000),
    termsVersion: "2026-05-16",
    termsAcceptedAt: Timestamp.fromMillis(now),
    termsOptionalConsents: { marketing: false, push: false, email: false },
  });
  const fn = createCompletePrimaryStudentEmailAuthFunction(
    db,
    fakeAuth({ [victimSession]: email })
  );

  const result = (await fn.run({
    data: { token: tokenId },
    auth: {
      uid: victimSession,
      token: { email, email_verified: true },
    },
    rawRequest: {},
  } as never)) as { appUserId: string };

  assert.equal(result.appUserId, victimSession, "victim must get their own account");
  assert.notEqual(result.appUserId, attacker);
  const attackerDoc = await userDoc(attacker);
  assert.notEqual(attackerDoc.isStudentVerified, true);
  assert.notEqual(attackerDoc.studentEmail, email);
  const binding = await bindingFor(email);
  assert.equal(binding?.appUserId, victimSession);
  assert.equal(binding?.status, "confirmed");
  assert.equal("expiresAt" in (binding ?? {}), false);

  // The attacker's legacy completion now meets a confirmed binding.
  assert.deepEqual(await confirm(attacker, email), {
    ok: false,
    reason: "bound_to_other_account",
  });
});

test("primary flow: a confirmed binding still resolves the returning owner to the bound account", async () => {
  const owner = fresh("owner");
  const email = `${fresh("ret")}@yonsei.ac.kr`;
  await db.collection("users").doc(owner).set({
    kakaoUserId: owner,
    isStudentVerified: true,
    studentEmail: email,
    status: "active",
  });
  assert.equal((await confirm(owner, email)).ok, true);

  const session = fresh("emaillink_ret");
  const now = Date.now();
  const tokenId = fresh("rtok");
  await db.collection("emailLinkTokens").doc(tokenId).set({
    email,
    purpose: "primary_auth",
    createdAt: Timestamp.fromMillis(now),
    expiresAt: Timestamp.fromMillis(now + 30 * 60 * 1000),
  });
  const fn = createCompletePrimaryStudentEmailAuthFunction(
    db,
    fakeAuth({ [session]: email })
  );
  const result = (await fn.run({
    data: { token: tokenId },
    auth: { uid: session, token: { email, email_verified: true } },
    rawRequest: {},
  } as never)) as { appUserId: string };
  assert.equal(result.appUserId, owner);
  assert.equal((await bindingFor(email))?.appUserId, owner);
});
