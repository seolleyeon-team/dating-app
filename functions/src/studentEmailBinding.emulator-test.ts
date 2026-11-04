/**
 * P0-1 (2026-10 production audit) — one Yonsei mailbox ↔ at most one account.
 *
 * Firestore Emulator E2E for the LEGACY completion callable
 * (completeStudentEmailLink). The real transaction runs against the emulator,
 * so sequential AND concurrent double-claims are exercised for real (no
 * in-memory Firestore double).
 *
 * Run (repo root, JDK 21 required by firebase-tools):
 *   npx tsc -p functions --outDir functions/.p01-verify-lib
 *   firebase emulators:exec --only firestore --project demo-p01-binding \
 *     "node --test functions/.p01-verify-lib/studentEmailBinding.emulator-test.js"
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";
import type { Auth } from "firebase-admin/auth";
import { HttpsError } from "firebase-functions/v2/https";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error(
    "FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`."
  );
}

import { createCompleteStudentEmailLinkFunction } from "./emailLinkCompletion";

initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-p01-binding" });
const db = getFirestore();

/** The binding id contract used by completePrimaryStudentEmailAuth. */
function bindingIdFor(email: string): string {
  return createHash("sha256")
    .update(email.trim().toLowerCase(), "utf8")
    .digest("hex");
}

/** Fake Auth: every uid is a verified mailbox owner of the email we hand it. */
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

type Runnable = { run: (req: never) => Promise<unknown> };

function runAs(
  fn: Runnable,
  session: { uid: string; email: string },
  data: Record<string, unknown>
) {
  return fn.run({
    data,
    auth: {
      uid: session.uid,
      token: { email: session.email, email_verified: true },
    },
    rawRequest: {},
  } as never);
}

let seq = 0;
function fresh(prefix: string): string {
  seq += 1;
  return `${prefix}_${Date.now().toString(36)}_${seq}`;
}

async function seedKakaoShell(uid: string): Promise<void> {
  await db.collection("users").doc(uid).set({ kakaoUserId: uid, nickname: uid });
}

/** Exactly what sendStudentVerificationEmail writes (Admin SDK). */
async function seedLegacyToken(
  tokenId: string,
  params: { email: string; kakaoUserId: string; expiresInMs?: number }
): Promise<void> {
  const now = Date.now();
  await db.collection("emailLinkTokens").doc(tokenId).set({
    email: params.email,
    kakaoUserId: params.kakaoUserId,
    createdAt: Timestamp.fromMillis(now),
    expiresAt: Timestamp.fromMillis(now + (params.expiresInMs ?? 30 * 60 * 1000)),
  });
}

async function userDoc(uid: string): Promise<Record<string, unknown>> {
  return ((await db.collection("users").doc(uid).get()).data() ?? {}) as Record<
    string,
    unknown
  >;
}

async function bindingFor(email: string): Promise<Record<string, unknown> | null> {
  const snap = await db
    .collection("studentEmailBindings")
    .doc(bindingIdFor(email))
    .get();
  return snap.exists ? ((snap.data() ?? {}) as Record<string, unknown>) : null;
}

function assertNotVerifiedWith(data: Record<string, unknown>, email: string) {
  assert.notEqual(data.isStudentVerified, true, "loser must not be verified");
  assert.notEqual(
    String(data.studentEmail ?? "").toLowerCase(),
    email.toLowerCase(),
    "loser must not carry the contested email"
  );
}

async function isRejected(p: Promise<unknown>): Promise<boolean> {
  try {
    await p;
    return false;
  } catch (error) {
    assert.ok(error instanceof HttpsError, `expected HttpsError, got ${String(error)}`);
    return true;
  }
}

test("TEST A: sequential — second account cannot complete with an email another account already owns", async () => {
  const a = fresh("kakao_a");
  const b = fresh("kakao_b");
  const email = `${fresh("student")}@yonsei.ac.kr`;
  await Promise.all([seedKakaoShell(a), seedKakaoShell(b)]);
  await seedLegacyToken("tok-a", { email, kakaoUserId: a });
  await seedLegacyToken("tok-b", { email, kakaoUserId: b });

  const fn = createCompleteStudentEmailLinkFunction(
    db,
    fakeAuth({ link_a: email, link_b: email })
  );

  await runAs(fn, { uid: "link_a", email }, { token: "tok-a" });
  assert.equal((await userDoc(a)).isStudentVerified, true);

  assert.equal(
    await isRejected(runAs(fn, { uid: "link_b", email }, { token: "tok-b" })),
    true,
    "B must be rejected"
  );
  assertNotVerifiedWith(await userDoc(b), email);
  assert.equal((await bindingFor(email))?.appUserId, a, "binding must name A");
});

test("TEST B: concurrent — exactly one of two accounts wins the same email (5 rounds)", async () => {
  for (let round = 0; round < 5; round += 1) {
    const a = fresh("kakao_ca");
    const b = fresh("kakao_cb");
    const email = `${fresh("race")}@yonsei.ac.kr`;
    await Promise.all([seedKakaoShell(a), seedKakaoShell(b)]);
    await seedLegacyToken(`ctok-a-${round}`, { email, kakaoUserId: a });
    await seedLegacyToken(`ctok-b-${round}`, { email, kakaoUserId: b });
    const fn = createCompleteStudentEmailLinkFunction(
      db,
      fakeAuth({ link_ca: email, link_cb: email })
    );

    const results = await Promise.allSettled([
      runAs(fn, { uid: "link_ca", email }, { token: `ctok-a-${round}` }),
      runAs(fn, { uid: "link_cb", email }, { token: `ctok-b-${round}` }),
    ]);
    const successes = results.filter((r) => r.status === "fulfilled").length;
    const failures = results.filter((r) => r.status === "rejected").length;
    assert.equal(successes, 1, `round ${round}: expected exactly one success`);
    assert.equal(failures, 1, `round ${round}: expected exactly one rejection`);

    const [docA, docB, binding] = await Promise.all([
      userDoc(a),
      userDoc(b),
      bindingFor(email),
    ]);
    const verified = [
      [a, docA],
      [b, docB],
    ].filter(([, d]) => (d as Record<string, unknown>).isStudentVerified === true);
    assert.equal(verified.length, 1, `round ${round}: exactly one verified user`);
    const winner = verified[0][0] as string;
    assert.ok(binding, `round ${round}: binding must exist`);
    assert.equal(binding?.appUserId, winner, `round ${round}: binding owner == winner`);
    assertNotVerifiedWith(winner === a ? docB : docA, email);
  }
});

test("TEST C: same owner re-completing with a fresh token is idempotent", async () => {
  const a = fresh("kakao_retry");
  const email = `${fresh("retry")}@yonsei.ac.kr`;
  await seedKakaoShell(a);
  await seedLegacyToken("rtok-1", { email, kakaoUserId: a });
  await seedLegacyToken("rtok-2", { email, kakaoUserId: a });
  const fn = createCompleteStudentEmailLinkFunction(db, fakeAuth({ link_r: email }));

  await runAs(fn, { uid: "link_r", email }, { token: "rtok-1" });
  await runAs(fn, { uid: "link_r", email }, { token: "rtok-2" });
  assert.equal((await userDoc(a)).isStudentVerified, true);
  assert.equal((await bindingFor(email))?.appUserId, a);
});

test("TEST D: different emails bind different accounts without interference", async () => {
  const a = fresh("kakao_d1");
  const b = fresh("kakao_d2");
  const e1 = `${fresh("d1")}@yonsei.ac.kr`;
  const e2 = `${fresh("d2")}@yonsei.ac.kr`;
  await Promise.all([seedKakaoShell(a), seedKakaoShell(b)]);
  await seedLegacyToken("dtok-a", { email: e1, kakaoUserId: a });
  await seedLegacyToken("dtok-b", { email: e2, kakaoUserId: b });
  const fn = createCompleteStudentEmailLinkFunction(
    db,
    fakeAuth({ link_d1: e1, link_d2: e2 })
  );

  const results = await Promise.allSettled([
    runAs(fn, { uid: "link_d1", email: e1 }, { token: "dtok-a" }),
    runAs(fn, { uid: "link_d2", email: e2 }, { token: "dtok-b" }),
  ]);
  assert.deepEqual(
    results.map((r) => r.status),
    ["fulfilled", "fulfilled"]
  );
  assert.equal((await bindingFor(e1))?.appUserId, a);
  assert.equal((await bindingFor(e2))?.appUserId, b);
});

test("TEST F: a case-variant of an owned email resolves to the same binding and is rejected", async () => {
  const a = fresh("kakao_f1");
  const b = fresh("kakao_f2");
  const local = fresh("Case");
  const lower = `${local.toLowerCase()}@yonsei.ac.kr`;
  const mixed = `${local}@YONSEI.ac.kr`;
  await Promise.all([seedKakaoShell(a), seedKakaoShell(b)]);
  // The server stores the normalized (lowercased) email on both tokens.
  await seedLegacyToken("ftok-a", { email: lower, kakaoUserId: a });
  await seedLegacyToken("ftok-b", { email: lower, kakaoUserId: b });
  const fn = createCompleteStudentEmailLinkFunction(
    db,
    fakeAuth({ link_f1: mixed, link_f2: lower })
  );

  await runAs(fn, { uid: "link_f1", email: mixed }, { token: "ftok-a" });
  assert.equal(
    await isRejected(runAs(fn, { uid: "link_f2", email: lower }, { token: "ftok-b" })),
    true
  );
  assert.equal(bindingIdFor(mixed), bindingIdFor(lower));
  assert.equal((await bindingFor(lower))?.appUserId, a);
  assertNotVerifiedWith(await userDoc(b), lower);
});

test("TEST G: an expired token neither verifies nor reserves the email", async () => {
  const a = fresh("kakao_g");
  const email = `${fresh("g")}@yonsei.ac.kr`;
  await seedKakaoShell(a);
  await seedLegacyToken("gtok", { email, kakaoUserId: a, expiresInMs: -1000 });
  const fn = createCompleteStudentEmailLinkFunction(db, fakeAuth({ link_g: email }));

  assert.equal(await isRejected(runAs(fn, { uid: "link_g", email }, { token: "gtok" })), true);
  assertNotVerifiedWith(await userDoc(a), email);
  assert.equal(await bindingFor(email), null);
});

test("TEST H (legacy data): a verified user doc WITHOUT a binding still blocks a second account", async () => {
  const legacy = fresh("kakao_legacy");
  const b = fresh("kakao_h");
  const email = `${fresh("h")}@yonsei.ac.kr`;
  await db.collection("users").doc(legacy).set({
    kakaoUserId: legacy,
    isStudentVerified: true,
    studentEmail: email,
  });
  await seedKakaoShell(b);
  await seedLegacyToken("htok", { email, kakaoUserId: b });
  const fn = createCompleteStudentEmailLinkFunction(db, fakeAuth({ link_h: email }));

  assert.equal(await isRejected(runAs(fn, { uid: "link_h", email }, { token: "htok" })), true);
  assertNotVerifiedWith(await userDoc(b), email);
  // The transaction aborted before any write: the still-valid token survives
  // untouched and no binding was created for the loser.
  assert.equal((await db.collection("emailLinkTokens").doc("htok").get()).exists, true);
  assert.notEqual((await bindingFor(email))?.appUserId, b);
});
