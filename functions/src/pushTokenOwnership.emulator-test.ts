/**
 * P1-3 — FCM token ownership on the real Firestore engine: registration
 * events (create / transfer / stale / delete) through the trigger handler,
 * the delivery-time ownership check in fetchUserTokenRecords, and the
 * historical backfill (dry-run writes nothing, apply converges, re-run is a
 * no-op).
 *
 * Before the fix (`874cb3aa`) fetchUserTokenRecords returned every token
 * registered under the recipient, so a token left behind by account A on a
 * shared device kept receiving A's pushes after B signed in.
 *
 * Run (repo root, JDK 21):
 *   npx tsc -p functions --outDir functions/.p1-lib
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore --project demo-p13-tokens \
 *     "node --test functions/.p1-lib/pushTokenOwnership.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-p13-tokens" });

import {
  PUSH_TOKEN_OWNER_COLLECTION,
  createDeviceTokenOwnershipTrigger,
  reconcileTokenRegistration,
  runTokenOwnershipBackfill,
  tokenFingerprint,
  verifyTokenOwnership,
} from "./pushTokenOwnership";
import { fetchUserTokenRecords } from "./shared/notify";

const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;
type Runner = { run: (event: unknown) => Promise<unknown> };
const trigger = createDeviceTokenOwnershipTrigger(db) as unknown as Runner;

const regRef = (uid: string, token: string) => db.collection("users").doc(uid).collection("deviceTokens").doc(token);
const registryRef = (token: string) => db.collection(PUSH_TOKEN_OWNER_COLLECTION).doc(tokenFingerprint(token));

/** Writes the registration the client writes and runs the trigger on it. */
async function register(uid: string, token: string, atMs: number) {
  await db.collection("users").doc(uid).set({ nickname: uid, notificationSettings: { all: true } }, { merge: true });
  await regRef(uid, token).set({
    userId: uid, token, platform: "android", notificationsEnabled: true,
    notificationSettings: { all: true }, updatedAt: Timestamp.fromMillis(atMs),
  });
  const after = await regRef(uid, token).get();
  await trigger.run({ data: { before: { exists: false }, after }, params: { uid, token }, time: new Date(atMs).toISOString() });
}

async function unregister(uid: string, token: string) {
  const before = await regRef(uid, token).get();
  await regRef(uid, token).delete();
  const after = await regRef(uid, token).get();
  await trigger.run({ data: { before, after }, params: { uid, token }, time: new Date().toISOString() });
}

async function tokensDeliverableTo(uid: string) {
  return (await fetchUserTokenRecords(uid, "chat")).map((r) => r.token).sort();
}

test("A: a registration claims the token; the registry stores a fingerprint, not the raw token", async () => {
  const a = fresh("a"), token = fresh("tok");
  await register(a, token, 1000);
  const registry = await registryRef(token).get();
  assert.equal(registry.exists, true);
  assert.equal(registry.get("ownerUid"), a);
  assert.equal(JSON.stringify(registry.data()).includes(token), false, "raw token never stored");
  assert.deepEqual(await tokensDeliverableTo(a), [token]);
});

test("B: A logs out without cleanup, B logs in on the same device — the token moves to B and A can no longer be reached through it", async () => {
  const a = fresh("a"), b = fresh("b"), token = fresh("tok");
  await register(a, token, 1000);
  await register(b, token, 2000);
  assert.equal((await registryRef(token).get()).get("ownerUid"), b);
  assert.equal((await regRef(a, token).get()).exists, false, "A's stale registration is removed");
  assert.deepEqual(await tokensDeliverableTo(a), [], "no push to A's old token");
  assert.deepEqual(await tokensDeliverableTo(b), [token]);
});

test("C: delivery-time check — a stale registration that survived (no trigger yet) is skipped and deleted", async () => {
  const a = fresh("a"), b = fresh("b"), token = fresh("tok");
  await register(b, token, 2000);
  // A's registration is written WITHOUT the trigger running (lost event).
  await db.collection("users").doc(a).set({ nickname: a }, { merge: true });
  await regRef(a, token).set({ userId: a, token, notificationsEnabled: true, updatedAt: Timestamp.fromMillis(1000) });
  assert.deepEqual(await tokensDeliverableTo(a), [], "registry owner differs → not delivered");
  assert.equal((await regRef(a, token).get()).exists, false, "stale registration cleaned on read");
  assert.deepEqual(await tokensDeliverableTo(b), [token]);
});

test("D: a late event for an OLDER registration does not steal the token back (concurrent account switch)", async () => {
  const a = fresh("a"), b = fresh("b"), token = fresh("tok");
  await register(b, token, 5000);
  // A's registration was written at t=1000 but its event arrives after B's.
  await db.collection("users").doc(a).set({ nickname: a }, { merge: true });
  await regRef(a, token).set({ userId: a, token, notificationsEnabled: true, updatedAt: Timestamp.fromMillis(1000) });
  const outcome = await reconcileTokenRegistration(db, {
    uid: a, token, registration: (await regRef(a, token).get()).data() ?? {}, eventTimeMs: 6000,
  });
  assert.equal(outcome, "stale_registration_deleted");
  assert.equal((await registryRef(token).get()).get("ownerUid"), b);
  assert.equal((await regRef(a, token).get()).exists, false);
});

test("E: logout / account deletion releases the token only when the registration belonged to the owner", async () => {
  const a = fresh("a"), b = fresh("b"), token = fresh("tok");
  await register(a, token, 1000);
  await unregister(a, token);
  assert.equal((await registryRef(token).get()).exists, false, "released");

  await register(a, token, 2000);
  await register(b, token, 3000);
  // A's client deletes its (already transferred) registration late: B keeps the token.
  await trigger.run({ data: { before: { exists: false }, after: await regRef(a, token).get() }, params: { uid: a, token }, time: new Date().toISOString() });
  assert.equal((await registryRef(token).get()).get("ownerUid"), b);
});

test("F: token refresh — a new token is claimed, the old one is released, both only for the same account", async () => {
  const a = fresh("a"), oldToken = fresh("tok"), newToken = fresh("tok");
  await register(a, oldToken, 1000);
  await register(a, newToken, 2000);
  await unregister(a, oldToken);
  assert.deepEqual(await tokensDeliverableTo(a), [newToken]);
  const verdict = await verifyTokenOwnership(db, a, [oldToken, newToken]);
  assert.deepEqual(verdict, { owned: [newToken], stale: [], unregistered: [oldToken] });
});

test("G: legacy registrations with no registry record are still delivered (transitional) until the backfill runs", async () => {
  const a = fresh("a"), token = fresh("tok");
  await db.collection("users").doc(a).set({ nickname: a }, { merge: true });
  await regRef(a, token).set({ userId: a, token, notificationsEnabled: true, updatedAt: Timestamp.fromMillis(1000) });
  assert.deepEqual(await tokensDeliverableTo(a), [token]);
});

test("H: backfill — dry-run writes nothing; apply assigns the newest registration and deletes the others; re-run is a no-op", async () => {
  const a = fresh("a"), b = fresh("b"), c = fresh("c");
  const shared = fresh("tok"), only = fresh("tok");
  for (const [uid, token, ms] of [[a, shared, 1000], [b, shared, 3000], [c, shared, 2000], [a, only, 100]] as Array<[string, string, number]>) {
    await db.collection("users").doc(uid).set({ nickname: uid }, { merge: true });
    await regRef(uid, token).set({ userId: uid, token, notificationsEnabled: true, updatedAt: Timestamp.fromMillis(ms) });
  }
  const before = await db.collectionGroup("deviceTokens").get();
  const dry = await runTokenOwnershipBackfill(db, { apply: false, pageSize: 2 });
  assert.ok(dry.registrationsScanned >= 4);
  assert.ok(dry.registryWrites >= 2);
  assert.ok(dry.staleDeletes >= 2);
  assert.equal((await db.collectionGroup("deviceTokens").get()).size, before.size, "dry-run deletes nothing");
  assert.equal((await registryRef(shared).get()).exists, false, "dry-run writes nothing");

  await runTokenOwnershipBackfill(db, { apply: true, pageSize: 2 });
  assert.equal((await registryRef(shared).get()).get("ownerUid"), b);
  assert.equal((await registryRef(only).get()).get("ownerUid"), a);
  assert.equal((await regRef(a, shared).get()).exists, false);
  assert.equal((await regRef(c, shared).get()).exists, false);
  assert.equal((await regRef(b, shared).get()).exists, true);
  assert.deepEqual(await tokensDeliverableTo(b), [shared]);
  assert.deepEqual(await tokensDeliverableTo(a), [only]);

  const again = await runTokenOwnershipBackfill(db, { apply: true, pageSize: 2 });
  assert.equal(again.staleDeletes, 0, "idempotent re-run");
  // Only the tokens of THIS test are guaranteed converged; earlier tests may
  // have left legacy registrations by design (test G).
  assert.equal((await registryRef(shared).get()).get("ownerUid"), b);
});
