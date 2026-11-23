/**
 * AUD-11 — adult verification on the real callable and the real Firestore
 * engine (PortOne mocked at the network boundary): one identity ↔ one
 * account under concurrency, idempotent retries, no downgrade by an
 * incomplete verification, nothing written on a failure, Play-review
 * isolation, and no trust in anything the client asserts.
 *
 * Run (repo root, JDK 21):
 *   firebase emulators:exec --only firestore --project demo-auth \
 *     "node --test functions/<outDir>/adultIdentityOwnership.emulator-test.js"
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { after, before, test } from "node:test";

import { getFirestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

// index.ts performs initializeApp(); only import here.
import { unlockDirectChat, verifyAdultIdentityAfterLogin } from "./index";
import {
  ADULT_IDENTITY_OWNERS_COLLECTION,
  PRIVATE_VERIFICATIONS_COLLECTION,
  adultIdentityKeysOf,
  adultIdentityOwnerDocId,
  auditAdultIdentityOwnership,
  backfillAdultIdentityOwnership,
  releaseAdultIdentityOwnership,
} from "./adultIdentityOwnership";

type Runnable = { run: (request: unknown) => Promise<unknown> };
const db = getFirestore();
let seq = 0;
// File tag: accountStateGate.emulator-test.ts runs in the same emulator session
// in a parallel process with the same generator.
const fresh = (p: string) => `${p}_aio_${Date.now().toString(36)}_${++seq}`;
const sha = (value: string) => createHash("sha256").update(value, "utf8").digest("hex");

type Person = { name: string; phoneNumber: string; birthDate: string; ci: string; di?: string; id: string };
function person(birthDate = "1999-03-02"): Person {
  const n = ++seq;
  return {
    name: `person ${n}`,
    phoneNumber: `010${String(10_000_000 + ((Date.now() + n * 7919) % 89_999_999)).slice(0, 8)}`,
    birthDate,
    ci: `ci-${Date.now().toString(36)}-${n}`.padEnd(88, "x"),
    id: `portone-customer-${Date.now().toString(36)}-${n}`,
  };
}

/** PortOne answers by verification id; anything else is an unexpected request. */
const provider = new Map<string, { httpStatus?: number; body: unknown }>();
function verified(id: string, who: Person, extra: Record<string, unknown> = {}) {
  provider.set(id, { body: { status: "VERIFIED", id, verifiedCustomer: who, ...extra } });
}
const realFetch = globalThis.fetch;
before(() => {
  process.env.PORTONE_API_SECRET = "test-secret";
  delete process.env.FUNCTIONS_EMULATOR; // the real provider path, not the mock- shortcut
  globalThis.fetch = (async (input: unknown) => {
    const url = String(input);
    const prefix = "https://api.portone.io/identity-verifications/";
    if (!url.startsWith(prefix)) throw new Error("unexpected outbound request");
    const answer = provider.get(decodeURIComponent(url.slice(prefix.length)));
    const status = answer?.httpStatus ?? (answer ? 200 : 404);
    return {
      ok: status >= 200 && status < 300,
      status,
      text: async () => JSON.stringify(answer?.body ?? { type: "IDENTITY_VERIFICATION_NOT_FOUND" }),
    };
  }) as unknown as typeof fetch;
});
after(() => {
  globalThis.fetch = realFetch;
});

async function seedUser(uid: string, extra: Record<string, unknown> = {}) {
  await db.collection("users").doc(uid).set({
    isStudentVerified: true,
    studentEmail: `${uid}@yonsei.ac.kr`,
    nickname: uid,
    ...extra,
  });
}

function verify(uid: string, identityVerificationId: string, extraData: Record<string, unknown> = {}, claims: Record<string, unknown> = {}) {
  return (verifyAdultIdentityAfterLogin as unknown as Runnable).run({
    data: { identityVerificationId, ...extraData },
    auth: { uid, token: claims },
    rawRequest: {},
  }) as Promise<Record<string, unknown>>;
}

async function code(promise: Promise<unknown>): Promise<string> {
  try {
    await promise;
  } catch (error) {
    return String((error as { code?: string }).code);
  }
  return "ok";
}

const userDoc = async (uid: string) => (await db.collection("users").doc(uid).get()).data() ?? {};
const record = async (uid: string) => (await db.collection(PRIVATE_VERIFICATIONS_COLLECTION).doc(uid).get()).data();
const ownersOf = async (uid: string) =>
  (await db.collection(ADULT_IDENTITY_OWNERS_COLLECTION).where("userId", "==", uid).get()).docs.map((d) => d.id).sort();
const ownerOfKey = async (kind: string, hash: string) =>
  (await db.collection(ADULT_IDENTITY_OWNERS_COLLECTION).doc(`${kind}_${hash}`).get()).get("userId");
const expectedOwnerIds = (who: Person, sessionId: string) =>
  [`ci_${sha(who.ci)}`, `uniqueKey_${sha(who.id)}`, `session_${sha(sessionId)}`, ...(who.di ? [`di_${sha(who.di)}`] : [])].sort();

test("A1 a completed verification records the identity and its ownership in one commit", async () => {
  const uid = fresh("a1"), who = person(), id = fresh("iv");
  await seedUser(uid);
  verified(id, who);
  const result = await verify(uid, id);
  assert.equal(result.adultVerified, true);
  const user = await userDoc(uid);
  assert.deepEqual([user.adultVerified, user.realNameVerified, user.registrationStatus], [true, true, "adult_verified"]);
  const stored = await record(uid);
  assert.deepEqual([stored?.ciHash, stored?.uniqueKeyHash, stored?.diHash, stored?.identityVerificationId], [sha(who.ci), sha(who.id), null, id]);
  assert.deepEqual(await ownersOf(uid), expectedOwnerIds(who, id));
  // The ownership documents carry no identity value beyond the hash in their id.
  const owner = (await db.collection(ADULT_IDENTITY_OWNERS_COLLECTION).doc(`ci_${sha(who.ci)}`).get()).data() ?? {};
  assert.deepEqual(Object.keys(owner).sort(), ["claimedAt", "kind", "updatedAt", "userId"]);
});

test("A2 [race] the same identity verified concurrently by different accounts: exactly one wins", async () => {
  for (const contenders of [2, 2, 2, 6]) {
    const who = person();
    const uids = Array.from({ length: contenders }, () => fresh("race"));
    const sessions = uids.map(() => fresh("iv"));
    await Promise.all(uids.map((uid) => seedUser(uid)));
    sessions.forEach((id) => verified(id, who)); // each account ran its own PASS session as the same person
    const results = await Promise.allSettled(uids.map((uid, i) => verify(uid, sessions[i])));
    const winners = uids.filter((_, i) => results[i].status === "fulfilled");
    assert.equal(winners.length, 1, `${contenders} contenders`);
    for (let i = 0; i < uids.length; i += 1) {
      if (results[i].status === "fulfilled") continue;
      assert.equal((results[i] as PromiseRejectedResult).reason.code, "already-exists");
      assert.notEqual((await userDoc(uids[i])).adultVerified, true);
      assert.equal(await record(uids[i]), undefined);
      assert.deepEqual(await ownersOf(uids[i]), []);
    }
    assert.equal(await ownerOfKey("ci", sha(who.ci)), winners[0]);
    assert.equal(await ownerOfKey("uniqueKey", sha(who.id)), winners[0]);
    const holders = await db.collection(PRIVATE_VERIFICATIONS_COLLECTION).where("ciHash", "==", sha(who.ci)).get();
    assert.deepEqual(holders.docs.map((d) => d.id), winners);
  }
});

test("A3 the same account retrying is idempotent (same session, and a new session for the same person)", async () => {
  const uid = fresh("a3"), who = person(), first = fresh("iv"), second = fresh("iv");
  await seedUser(uid);
  verified(first, who);
  verified(second, who);
  await verify(uid, first);
  const [again, parallelA, parallelB] = await Promise.all([verify(uid, first), verify(uid, first), verify(uid, first)]);
  assert.deepEqual([again.adultVerified, parallelA.adultVerified, parallelB.adultVerified], [true, true, true]);
  assert.deepEqual(await ownersOf(uid), expectedOwnerIds(who, first));

  await verify(uid, second);
  // The record names the latest session; ownership follows the record exactly.
  assert.equal((await record(uid))?.identityVerificationId, second);
  assert.deepEqual(await ownersOf(uid), expectedOwnerIds(who, second));
  assert.equal((await userDoc(uid)).adultVerified, true);
});

test("A4 a different account is refused for the same identity and for a replayed session; nothing changes", async () => {
  const owner = fresh("a4_owner"), other = fresh("a4_other"), who = person(), id = fresh("iv"), otherSession = fresh("iv");
  await seedUser(owner);
  await seedUser(other);
  verified(id, who);
  verified(otherSession, who);
  await verify(owner, id);
  const before = [await userDoc(other), await ownersOf(owner)];

  assert.equal(await code(verify(other, otherSession)), "already-exists"); // same person, own session
  assert.equal(await code(verify(other, id)), "already-exists"); // the owner's session replayed
  // same customer key with a different CI is still the same PortOne customer
  const sameCustomer = fresh("iv");
  verified(sameCustomer, { ...person(), id: who.id });
  assert.equal(await code(verify(other, sameCustomer)), "already-exists");

  assert.deepEqual([await userDoc(other), await ownersOf(owner)], before);
  assert.equal(await record(other), undefined);
  assert.deepEqual(await ownersOf(other), []);
  assert.equal((await userDoc(owner)).adultVerified, true);
});

test("A5 a record written before ownership documents existed still blocks, and is adopted on its owner's next verification", async () => {
  const legacy = fresh("legacy"), other = fresh("a5_other"), who = person(), oldSession = fresh("iv");
  await seedUser(legacy, { adultVerified: true, realNameVerified: true });
  await seedUser(other);
  await db.collection(PRIVATE_VERIFICATIONS_COLLECTION).doc(legacy).set({
    ciHash: sha(who.ci), diHash: null, uniqueKeyHash: sha(who.id), identityVerificationId: oldSession, verificationStatus: "adult_verified",
  });
  assert.deepEqual(await ownersOf(legacy), []);

  const attempt = fresh("iv");
  verified(attempt, who);
  assert.equal(await code(verify(other, attempt)), "already-exists");
  verified(oldSession, who);
  assert.equal(await code(verify(other, oldSession)), "already-exists");
  assert.deepEqual(await ownersOf(other), []);

  const renewed = fresh("iv");
  verified(renewed, who);
  await verify(legacy, renewed);
  assert.deepEqual(await ownersOf(legacy), expectedOwnerIds(who, renewed));
});

test("A6 an incomplete verification never downgrades a verified account and creates no account", async () => {
  const uid = fresh("a6"), who = person(), id = fresh("iv");
  await seedUser(uid);
  verified(id, who);
  await verify(uid, id);
  const verifiedState = await userDoc(uid);

  for (const status of ["READY", "FAILED", "", "verified"]) {
    const incomplete = fresh("iv");
    provider.set(incomplete, { body: { status, id: incomplete, verifiedCustomer: person() } });
    assert.equal(await code(verify(uid, incomplete)), "failed-precondition", status);
  }
  const afterIncomplete = await userDoc(uid);
  assert.deepEqual(
    [afterIncomplete.adultVerified, afterIncomplete.realNameVerified, afterIncomplete.registrationStatus, afterIncomplete.updatedAt],
    [true, true, "adult_verified", verifiedState.updatedAt],
  );
  assert.deepEqual(await ownersOf(uid), expectedOwnerIds(who, id));

  // A not-yet-verified account is marked as still requiring verification, as before.
  const pending = fresh("a6_pending"), incomplete = fresh("iv");
  await seedUser(pending);
  provider.set(incomplete, { body: { status: "FAILED", id: incomplete } });
  assert.equal(await code(verify(pending, incomplete)), "failed-precondition");
  assert.deepEqual([(await userDoc(pending)).adultVerified, (await userDoc(pending)).registrationStatus], [false, "adult_verification_required"]);

  // A session without an account document gets none.
  const ghost = fresh("ghost");
  assert.equal(await code(verify(ghost, incomplete)), "failed-precondition");
  assert.equal((await db.collection("users").doc(ghost).get()).exists, false);
});

test("A7 a failure anywhere in the flow leaves every document unchanged", async () => {
  const uid = fresh("a7"), who = person(), id = fresh("iv");
  await seedUser(uid);
  verified(id, who);
  await verify(uid, id);
  const snapshot = async () => [await userDoc(uid), await record(uid), await ownersOf(uid)];
  const baseline = await snapshot();

  const other = person();
  const cases: Array<[string, { httpStatus?: number; body: unknown }, string]> = [
    ["provider 500", { httpStatus: 500, body: { type: "INTERNAL" } }, "failed-precondition"],
    ["unknown verification", { httpStatus: 404, body: { type: "NOT_FOUND" } }, "failed-precondition"],
    ["another store", { body: { status: "VERIFIED", storeId: "store-of-someone-else", verifiedCustomer: other } }, "failed-precondition"],
    ["no identity key", { body: { status: "VERIFIED", verifiedCustomer: { name: "x", phoneNumber: "01011112222", birthDate: "1999-01-01" } } }, "failed-precondition"],
    ["no phone", { body: { status: "VERIFIED", verifiedCustomer: { ...other, phoneNumber: "" } } }, "failed-precondition"],
    ["unreadable phone", { body: { status: "VERIFIED", verifiedCustomer: { ...other, phoneNumber: "12" } } }, "failed-precondition"],
  ];
  for (const [label, answer, expected] of cases) {
    const failing = fresh("iv");
    provider.set(failing, answer);
    assert.equal(await code(verify(uid, failing)), expected, label);
    assert.deepEqual(await snapshot(), baseline, label);
  }
  // Same failures for an account that was never verified: still nothing written.
  const pending = fresh("a7_pending"), failing = fresh("iv");
  await seedUser(pending);
  provider.set(failing, cases[2][1]);
  assert.equal(await code(verify(pending, failing)), "failed-precondition");
  assert.equal(await record(pending), undefined);
  assert.deepEqual(await ownersOf(pending), []);
  assert.equal((await userDoc(pending)).adultVerified, undefined);
});

test("A8 ownership follows the record: stale claims are taken over, deletion releases, a replaced identity is freed", async () => {
  // stale claim: the owner has no verification record any more (deleted account)
  const who = person(), newcomer = fresh("a8_new"), id = fresh("iv");
  await db.collection(ADULT_IDENTITY_OWNERS_COLLECTION).doc(`ci_${sha(who.ci)}`).set({ userId: "deleted-account", kind: "ci" });
  await seedUser(newcomer);
  verified(id, who);
  await verify(newcomer, id);
  assert.equal(await ownerOfKey("ci", sha(who.ci)), newcomer);

  // account deletion helper removes every claim of the account, and is idempotent
  assert.equal(await releaseAdultIdentityOwnership(db, newcomer), 3);
  assert.equal(await releaseAdultIdentityOwnership(db, newcomer), 0);
  assert.deepEqual(await ownersOf(newcomer), []);
  // the record still exists, so the identity is still protected by the record lookup
  const intruder = fresh("a8_intruder"), intruderSession = fresh("iv");
  await seedUser(intruder);
  verified(intruderSession, who);
  assert.equal(await code(verify(intruder, intruderSession)), "already-exists");
  // once the record is deleted too (end of account deletion) the person can verify a new account
  await db.collection(PRIVATE_VERIFICATIONS_COLLECTION).doc(newcomer).delete();
  await verify(intruder, intruderSession);
  assert.equal(await ownerOfKey("ci", sha(who.ci)), intruder);

  // an account that verifies as someone else releases the identity it no longer holds
  const first = person(), second = person(), switcher = fresh("a8_switch"), s1 = fresh("iv"), s2 = fresh("iv");
  await seedUser(switcher);
  verified(s1, first);
  verified(s2, second);
  await verify(switcher, s1);
  await verify(switcher, s2);
  assert.deepEqual(await ownersOf(switcher), expectedOwnerIds(second, s2));
  assert.equal(await ownerOfKey("ci", sha(first.ci)), undefined);
});

test("A9 under-age result: refused, account not verified, identity still bound to that account", async () => {
  const minorYear = new Date(Date.now() + 9 * 3600_000).getUTCFullYear() - 18;
  const uid = fresh("minor"), who = person(`${minorYear}-05-05`), id = fresh("iv");
  await seedUser(uid);
  verified(id, who);
  assert.equal(await code(verify(uid, id)), "permission-denied");
  const user = await userDoc(uid);
  assert.deepEqual([user.adultVerified, user.realNameVerified, user.registrationStatus], [false, false, "adult_verification_under_age"]);
  assert.equal((await record(uid))?.verificationStatus, "under_age");
  const other = fresh("minor_other"), otherSession = fresh("iv");
  await seedUser(other);
  verified(otherSession, who);
  assert.equal(await code(verify(other, otherSession)), "already-exists");
});

test("A10 Play-review and restricted accounts cannot run identity verification; nothing is claimed", async () => {
  const who = person(), id = fresh("iv");
  verified(id, who);
  const reviewer = fresh("review");
  await seedUser(reviewer, { dataPartition: "play_review", accountType: "google_play_review", reviewAccess: true, reviewProfileReady: true });
  assert.equal(await code(verify(reviewer, id, {}, { playReviewer: true, dataPartition: "play_review", appSession: true })), "failed-precondition");
  const invalidPartition = fresh("partition");
  await seedUser(invalidPartition, { dataPartition: "something_else" });
  assert.equal(await code(verify(invalidPartition, id)), "failed-precondition");
  for (const restricted of [
    { status: "suspended", loginDisabled: true, isActive: false },
    { status: "banned", loginDisabled: true, isActive: false },
    { status: "deleting", isWithdrawn: true, loginDisabled: true },
    { isActive: false },
  ]) {
    const uid = fresh("restricted");
    await seedUser(uid, restricted);
    assert.equal(await code(verify(uid, id)), "permission-denied", JSON.stringify(restricted));
    assert.notEqual((await userDoc(uid)).adultVerified, true);
  }
  assert.equal(await ownerOfKey("ci", sha(who.ci)), undefined);
  assert.equal((await db.collection(PRIVATE_VERIFICATIONS_COLLECTION).where("ciHash", "==", sha(who.ci)).get()).size, 0);
  assert.equal(await code((verifyAdultIdentityAfterLogin as unknown as Runnable).run({ data: { identityVerificationId: id }, auth: null, rawRequest: {} })), "unauthenticated");
});

test("A11 [P1-7] nothing the client asserts makes an account verified", async () => {
  const uid = fresh("claim"), partner = fresh("partner"), id = fresh("iv");
  await seedUser(uid);
  await seedUser(partner, { adultVerified: true, realNameVerified: true });
  provider.set(id, { body: { status: "READY", id } });
  const forged = { adultVerified: true, realNameVerified: true, status: "VERIFIED", verifiedCustomer: person(), birthYear: 1990 };
  assert.equal(await code(verify(uid, id, forged, { adultVerified: true, realNameVerified: true })), "failed-precondition");
  assert.notEqual((await userDoc(uid)).adultVerified, true);
  assert.equal(await record(uid), undefined);
  // An unknown verification id (never issued by the provider) is refused as well.
  assert.equal(await code(verify(uid, fresh("never-issued"), forged)), "failed-precondition");
  // A token claim is not evidence for the dating gate either.
  const chat = (unlockDirectChat as unknown as Runnable).run({
    data: { partnerId: partner },
    auth: { uid, token: { adultVerified: true, realNameVerified: true } },
    rawRequest: {},
  });
  assert.equal(await code(chat), "failed-precondition");
  assert.equal((await db.collection("chat_rooms").where("participantIds", "array-contains", uid).get()).size, 0);
});

test("A12 backfill: read-only audit, dry run writes nothing, apply is create-only and idempotent, duplicates are left for review", async () => {
  await db.recursiveDelete(db.collection(ADULT_IDENTITY_OWNERS_COLLECTION));
  await db.recursiveDelete(db.collection(PRIVATE_VERIFICATIONS_COLLECTION));
  const records = db.collection(PRIVATE_VERIFICATIONS_COLLECTION);
  const one = { ciHash: sha("ci-one"), diHash: null, uniqueKeyHash: sha("key-one"), identityVerificationId: "session-one" };
  const two = { ciHash: sha("ci-two"), diHash: sha("di-two"), uniqueKeyHash: sha("key-two"), identityVerificationId: "session-two" };
  // a pre-existing duplicate: two accounts verified as the same person
  const dupA = { ciHash: sha("ci-dup"), diHash: null, uniqueKeyHash: sha("key-dup-a"), identityVerificationId: "session-dup-a" };
  const dupB = { ciHash: sha("ci-dup"), diHash: null, uniqueKeyHash: sha("key-dup-b"), identityVerificationId: "session-dup-b" };
  await Promise.all([records.doc("u-one").set(one), records.doc("u-two").set(two), records.doc("u-dup-a").set(dupA), records.doc("u-dup-b").set(dupB)]);
  // u-one's CI is already claimed by itself; a leftover claim nobody backs
  await db.collection(ADULT_IDENTITY_OWNERS_COLLECTION).doc(adultIdentityOwnerDocId(adultIdentityKeysOf(one)[0])).set({ userId: "u-one", kind: "ci" });
  await db.collection(ADULT_IDENTITY_OWNERS_COLLECTION).doc(`ci_${sha("ci-gone")}`).set({ userId: "u-gone", kind: "ci" });

  const audit = await auditAdultIdentityOwnership(db);
  assert.deepEqual(audit, {
    privateRecords: 4,
    expectedOwnerDocs: 3 + 4 + 5, // u-one 3, u-two 4, duplicates: 1 shared CI + 2 keys + 2 sessions
    ownerDocs: 2,
    missing: 2 + 4 + 4,
    ownedByAnotherAccount: 0,
    stale: 1,
    sharedIdentityKeys: 1,
    accountsSharingAnIdentity: 2,
    ok: false,
  });

  const count = async () => (await db.collection(ADULT_IDENTITY_OWNERS_COLLECTION).get()).size;
  const dryRun = await backfillAdultIdentityOwnership(db, { apply: false });
  assert.deepEqual(dryRun, { applied: false, recordsScanned: 4, created: 10, alreadyOwned: 1, skippedShared: 2, skippedOwnedByAnotherAccount: 0 });
  assert.equal(await count(), 2, "a dry run writes nothing");

  const applied = await backfillAdultIdentityOwnership(db, { apply: true });
  assert.deepEqual({ ...applied, applied: false }, dryRun);
  assert.equal(await count(), 12);
  assert.equal(await ownerOfKey("ci", sha("ci-dup")), undefined, "a shared identity is never assigned by the backfill");
  const rerun = await backfillAdultIdentityOwnership(db, { apply: true });
  assert.deepEqual([rerun.created, rerun.alreadyOwned, rerun.skippedShared], [0, 11, 2]);
  assert.equal(await count(), 12);
  // the verification records themselves are untouched
  assert.deepEqual((await records.doc("u-two").get()).data(), two);
  const afterApply = await auditAdultIdentityOwnership(db);
  assert.deepEqual([afterApply.missing, afterApply.sharedIdentityKeys, afterApply.stale, afterApply.ok], [0, 1, 1, false]);
});
