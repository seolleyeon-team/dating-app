/**
 * P0-1 — legacy issuance callable (sendStudentVerificationEmail) reserves the
 * mailbox atomically with the token. Runs the deployed handler (.run()) from
 * index.ts against the Firestore + Auth emulators; the Resend call is stubbed.
 *
 * Run (repo root, JDK 21):
 *   npx tsc -p functions --outDir functions/.p01-verify-lib
 *   firebase emulators:exec --only firestore,auth --project demo-p01-binding \
 *     "node --test functions/.p01-verify-lib/studentEmailIssuance.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getFirestore } from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";

if (!process.env.FIRESTORE_EMULATOR_HOST || !process.env.FIREBASE_AUTH_EMULATOR_HOST) {
  throw new Error(
    "FIRESTORE_EMULATOR_HOST / FIREBASE_AUTH_EMULATOR_HOST are not set. Run via `firebase emulators:exec --only firestore,auth`."
  );
}

// Mail-provider configuration read at call time by the handler.
process.env.RESEND_API_KEY = "test-resend-key";
process.env.RESEND_FROM_EMAIL = "noreply@example.test";
process.env.RESEND_REPLY_TO = "";

// Never let the handler reach api.resend.com.
const originalFetch = globalThis.fetch;
globalThis.fetch = (async (input: RequestInfo | URL) => {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  if (!url.startsWith("https://api.resend.com/")) return originalFetch(input);
  return new Response(JSON.stringify({ id: "stub-message" }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}) as typeof fetch;

// index.ts performs initializeApp(); only import here.
import { sendStudentVerificationEmail } from "./index";
import { studentEmailBindingId } from "./studentEmailBinding";

const db = getFirestore();

let seq = 0;
function fresh(prefix: string): string {
  seq += 1;
  return `${prefix}_${Date.now().toString(36)}_${seq}`;
}

function requestId(): string {
  return fresh("req").padEnd(16, "0");
}

function send(uid: string, email: string) {
  return sendStudentVerificationEmail.run({
    data: { email, requestId: requestId() },
    auth: { uid, token: {} },
    rawRequest: {},
  } as never) as Promise<{ accepted: boolean; duplicate: boolean }>;
}

async function seedShell(uid: string, extra: Record<string, unknown> = {}) {
  await db.collection("users").doc(uid).set({ kakaoUserId: uid, ...extra });
}

async function bindingFor(email: string): Promise<Record<string, unknown> | null> {
  const snap = await db
    .collection("studentEmailBindings")
    .doc(studentEmailBindingId(email))
    .get();
  return snap.exists ? ((snap.data() ?? {}) as Record<string, unknown>) : null;
}

async function tokensFor(uid: string): Promise<number> {
  const snap = await db
    .collection("emailLinkTokens")
    .where("kakaoUserId", "==", uid)
    .get();
  return snap.size;
}

async function rejection(p: Promise<unknown>): Promise<HttpsError | null> {
  try {
    await p;
    return null;
  } catch (error) {
    assert.ok(error instanceof HttpsError, `expected HttpsError, got ${String(error)}`);
    return error;
  }
}

test("issuance reserves the mailbox for the requesting account together with the token", async () => {
  const a = fresh("iss_a");
  const email = `${fresh("iss")}@yonsei.ac.kr`;
  await seedShell(a);

  const result = await send(a, email);
  assert.equal(result.accepted, true);
  const binding = await bindingFor(email);
  assert.equal(binding?.appUserId, a);
  assert.equal(binding?.status, "pending");
  assert.ok(binding?.expiresAt, "reservation carries the token expiry");
  assert.equal(await tokensFor(a), 1);
});

test("a second account cannot obtain a token for a mailbox another account reserved", async () => {
  const a = fresh("iss2_a");
  const b = fresh("iss2_b");
  const email = `${fresh("iss2")}@yonsei.ac.kr`;
  await Promise.all([seedShell(a), seedShell(b)]);

  await send(a, email);
  const error = await rejection(send(b, email));
  assert.equal(error?.code, "already-exists");
  assert.equal(await tokensFor(b), 0, "no token is issued to the loser");
  assert.equal((await bindingFor(email))?.appUserId, a);
});

test("concurrent issuance for one mailbox yields exactly one token holder (3 rounds)", async () => {
  for (let round = 0; round < 3; round += 1) {
    const a = fresh("ciss_a");
    const b = fresh("ciss_b");
    const email = `${fresh("ciss")}@yonsei.ac.kr`;
    await Promise.all([seedShell(a), seedShell(b)]);

    const results = await Promise.allSettled([send(a, email), send(b, email)]);
    const okCount = results.filter((r) => r.status === "fulfilled").length;
    assert.equal(okCount, 1, `round ${round}: exactly one issuance`);
    const binding = await bindingFor(email);
    const winner = results[0].status === "fulfilled" ? a : b;
    const loser = winner === a ? b : a;
    assert.equal(binding?.appUserId, winner);
    assert.equal(await tokensFor(winner), 1);
    assert.equal(await tokensFor(loser), 0);
  }
});

test("a mailbox confirmed for another account (or held on a legacy users doc) can never be requested", async () => {
  const legacy = fresh("iss_legacy");
  const b = fresh("iss_b3");
  const email = `${fresh("held")}@yonsei.ac.kr`;
  await seedShell(legacy, { isStudentVerified: true, studentEmail: email });
  await seedShell(b);

  const error = await rejection(send(b, email));
  assert.equal(error?.code, "already-exists");
  assert.equal(await tokensFor(b), 0);
  assert.equal(await bindingFor(email), null, "a rejected request writes nothing");
});

test("an account verified with one mailbox cannot request a different one", async () => {
  const a = fresh("iss_switch");
  const e1 = `${fresh("e1")}@yonsei.ac.kr`;
  const e2 = `${fresh("e2")}@yonsei.ac.kr`;
  await seedShell(a, { isStudentVerified: true, studentEmail: e1 });

  const error = await rejection(send(a, e2));
  assert.equal(error?.code, "permission-denied");
  assert.equal(await bindingFor(e2), null, "the other mailbox is not reserved");
  assert.equal(await tokensFor(a), 0);
});

test("the owner re-requesting their own verified mailbox is accepted and lazily confirms the binding", async () => {
  const a = fresh("iss_own");
  const email = `${fresh("own")}@yonsei.ac.kr`;
  await seedShell(a, { isStudentVerified: true, studentEmail: email });

  assert.equal((await send(a, email)).accepted, true);
  const binding = await bindingFor(email);
  assert.equal(binding?.appUserId, a);
  assert.equal(binding?.status, "confirmed");
});
