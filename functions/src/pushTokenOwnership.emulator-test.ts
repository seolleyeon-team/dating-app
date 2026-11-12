/**
 * P1-3 — FCM token ownership on the real Firestore engine: registration
 * events (create / transfer / stale / delete) through the trigger handler,
 * the delivery-time ownership check in fetchUserTokenRecords (fail closed
 * without a record), and the historical backfill (dry-run writes nothing,
 * apply converges, re-run is a no-op, canary bound, read-only verify, safe
 * while the trigger is live).
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
  verifyTokenOwnershipRegistry,
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

test("G: a registration with no registry record is NOT delivered (fail closed); the backfill makes it deliverable", async () => {
  const a = fresh("a"), token = fresh("tok");
  await db.collection("users").doc(a).set({ nickname: a }, { merge: true });
  await regRef(a, token).set({ userId: a, token, notificationsEnabled: true, updatedAt: Timestamp.fromMillis(1000) });
  assert.deepEqual(await tokensDeliverableTo(a), [], "no record → nothing proves the token is still A's");
  assert.equal((await regRef(a, token).get()).exists, true, "the registration itself is kept (not stale, just unrecorded)");
  await runTokenOwnershipBackfill(db, { apply: true });
  assert.equal((await registryRef(token).get()).get("ownerUid"), a);
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
  assert.ok(dry.created >= 2, "dry-run reports the records it would create");
  assert.equal(dry.registryWrites, 0, "dry-run writes no record");
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
  assert.equal(again.staleDeletes, 0, "idempotent re-run: nothing stale");
  assert.equal(again.created, 0, "idempotent re-run: nothing to create");
  assert.equal(again.alreadyRecorded, again.tokens);
  assert.equal((await registryRef(shared).get()).get("ownerUid"), b);
});

test("I: verify — read-only; consistent after the backfill, and names each kind of inconsistency", async () => {
  await runTokenOwnershipBackfill(db, { apply: true });
  const clean = await verifyTokenOwnershipRegistry(db, { pageSize: 3 });
  assert.equal(clean.ok, true, JSON.stringify(clean));
  assert.equal(clean.tokensWithoutRecord, 0);
  assert.equal(clean.distinctTokens, clean.tokensWithRecord);

  const a = fresh("a"), b = fresh("b"), unrecorded = fresh("tok"), shared = fresh("tok");
  await db.collection("users").doc(a).set({ nickname: a }, { merge: true });
  await regRef(a, unrecorded).set({ userId: a, token: unrecorded, notificationsEnabled: true, updatedAt: Timestamp.fromMillis(1000) });
  await register(b, shared, 2000);
  await regRef(a, shared).set({ userId: a, token: shared, notificationsEnabled: true, updatedAt: Timestamp.fromMillis(1000) });
  const registryBefore = (await db.collection(PUSH_TOKEN_OWNER_COLLECTION).get()).size;
  const dirty = await verifyTokenOwnershipRegistry(db);
  assert.equal(dirty.ok, false);
  assert.equal(dirty.tokensWithoutRecord, 1);
  assert.equal(dirty.tokensUnderMultipleAccounts, 1);
  assert.equal(dirty.registrationsNotOwned, 1);
  assert.equal((await db.collection(PUSH_TOKEN_OWNER_COLLECTION).get()).size, registryBefore, "verify writes nothing");
  assert.equal((await regRef(a, shared).get()).exists, true, "verify deletes nothing");

  await runTokenOwnershipBackfill(db, { apply: true });
  const repaired = await verifyTokenOwnershipRegistry(db);
  assert.equal(repaired.ok, true, JSON.stringify(repaired));
  assert.equal((await registryRef(shared).get()).get("ownerUid"), b, "the trigger-written record stays");
  assert.equal((await regRef(a, shared).get()).exists, false, "the older other-account registration is stale");
});

test("J: safe while the trigger is live — an existing record is never overwritten; a newer other-account registration is left to its pending event", async () => {
  const a = fresh("a"), b = fresh("b"), c = fresh("c"), token = fresh("tok");
  await register(b, token, 2000);
  // A's registration is NEWER than B's record but its trigger event has not run.
  await db.collection("users").doc(a).set({ nickname: a }, { merge: true });
  await regRef(a, token).set({ userId: a, token, notificationsEnabled: true, updatedAt: Timestamp.fromMillis(3000) });
  // C's is an older leftover.
  await db.collection("users").doc(c).set({ nickname: c }, { merge: true });
  await regRef(c, token).set({ userId: c, token, notificationsEnabled: true, updatedAt: Timestamp.fromMillis(1000) });
  const recordBefore = (await registryRef(token).get()).data();

  const result = await runTokenOwnershipBackfill(db, { apply: true });
  assert.ok(result.pendingNewer >= 1);
  const record = (await registryRef(token).get()).data();
  assert.equal(record?.ownerUid, b, "the backfill does not overwrite the trigger's record");
  assert.deepEqual(record?.registeredAt, recordBefore?.registeredAt);
  assert.equal((await regRef(a, token).get()).exists, true, "a newer registration waits for its own event");
  assert.equal((await regRef(c, token).get()).exists, false, "an older other-account registration is stale");

  // A's pending event then arrives: the token moves to A, as the trigger decides.
  await trigger.run({ data: { before: { exists: false }, after: await regRef(a, token).get() }, params: { uid: a, token }, time: new Date(3000).toISOString() });
  assert.equal((await registryRef(token).get()).get("ownerUid"), a);
  assert.deepEqual(await tokensDeliverableTo(b), []);
  assert.deepEqual(await tokensDeliverableTo(a), [token]);
});

test("K: a record whose owner's registration is gone is left alone (no guessing, nothing deleted)", async () => {
  const a = fresh("a"), b = fresh("b"), token = fresh("tok");
  await register(a, token, 2000);
  await regRef(a, token).delete(); // deleted without the release event
  await db.collection("users").doc(b).set({ nickname: b }, { merge: true });
  await regRef(b, token).set({ userId: b, token, notificationsEnabled: true, updatedAt: Timestamp.fromMillis(1000) });
  const result = await runTokenOwnershipBackfill(db, { apply: true });
  assert.ok(result.ownerRegistrationMissing >= 1);
  assert.equal((await registryRef(token).get()).get("ownerUid"), a);
  assert.equal((await regRef(b, token).get()).exists, true);
  assert.deepEqual(await tokensDeliverableTo(b), [], "still not B's: the record names A");
  // cleanup for later tests: B's late event decides it (older than A's record → stale)
  await trigger.run({ data: { before: { exists: false }, after: await regRef(b, token).get() }, params: { uid: b, token }, time: new Date(1000).toISOString() });
  assert.equal((await regRef(b, token).get()).exists, false);
  await registryRef(token).delete();
});

test("L: canary — --max-tokens bounds the run in fingerprint order and defers the rest", async () => {
  const uids = [fresh("a"), fresh("b"), fresh("c")];
  const tokens = [fresh("tok"), fresh("tok"), fresh("tok")];
  for (let i = 0; i < 3; i++) {
    await db.collection("users").doc(uids[i]).set({ nickname: uids[i] }, { merge: true });
    await regRef(uids[i], tokens[i]).set({ userId: uids[i], token: tokens[i], notificationsEnabled: true, updatedAt: Timestamp.fromMillis(1000 + i) });
  }
  const dry = await runTokenOwnershipBackfill(db, { apply: false });
  const canary = await runTokenOwnershipBackfill(db, { apply: true, maxTokens: 1 });
  assert.equal(canary.created + canary.alreadyRecorded + canary.noRegistration + canary.ownerRegistrationMissing, 1);
  assert.equal(canary.deferredByLimit, dry.tokens - 1);
  const firstByFingerprint = [...tokens].sort((x, y) => tokenFingerprint(x).localeCompare(tokenFingerprint(y)))[0];
  const created = await Promise.all(tokens.map(async (t) => (await registryRef(t).get()).exists));
  // At most one of the three new tokens got a record, and only if it sorts first globally.
  assert.ok(created.filter(Boolean).length <= 1);
  const full = await runTokenOwnershipBackfill(db, { apply: true });
  assert.equal(full.deferredByLimit, 0);
  for (const t of tokens) assert.equal((await registryRef(t).get()).exists, true);
  assert.ok(firstByFingerprint.length > 0);
  assert.equal((await verifyTokenOwnershipRegistry(db)).ok, true);
});
