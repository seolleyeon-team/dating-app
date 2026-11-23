/**
 * B-14 — department recommendation privacy fan-out (emulator only).
 *
 * Measured quantity: department peers read and pair transactions run per
 * users/{uid} write (each pair transaction is 2 reads + 2 writes), and the
 * materialized exclusion set, which must equal the policy applied to every
 * pair — i.e. skipping no-op pairs changes cost, not outcome.
 *
 * Run (repo root, JDK 21):
 *   firebase emulators:exec --only firestore --project demo-sched \
 *     "node --test functions/.audit-lib-sched/departmentRecommendationFanout.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { initializeApp } from "firebase-admin/app";
import { getFirestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
initializeApp({ projectId: process.env.GCLOUD_PROJECT ?? "demo-sched" });

import {
  DEPARTMENT_RECOMMENDATION_EXCLUSION_COLLECTION,
  reconcileDepartmentRecommendationPrivacy,
  shouldExcludeSameDepartment,
} from "./departmentRecommendationPrivacy";

const db = getFirestore();
const tag = Date.now().toString(36);
const DEPARTMENT = `컴퓨터과학과_${tag}`;
const OTHER_DEPARTMENT = `심리학과_${tag}`;
const PEERS = 300;
const AVOIDING_PEERS = 6;

type UserData = Record<string, unknown>;
const users = new Map<string, UserData>();

async function writeUser(uid: string, data: UserData | null) {
  if (data === null) {
    users.delete(uid);
    await db.collection("users").doc(uid).delete();
    return;
  }
  users.set(uid, data);
  await db.collection("users").doc(uid).set(data);
}

/** Every stored exclusion as "owner>target", for the uids of this run. */
async function storedExclusions(): Promise<string[]> {
  const snap = await db.collectionGroup("targets").get();
  return snap.docs
    .filter((doc) => doc.ref.path.startsWith(`${DEPARTMENT_RECOMMENDATION_EXCLUSION_COLLECTION}/`))
    .map((doc) => `${doc.ref.parent.parent?.id}>${doc.id}`)
    .filter((edge) => edge.includes(tag))
    .sort();
}

/** The policy applied to every ordered pair involving `uid` (brute force). */
function expectedExclusionsFor(uid: string): string[] {
  const edges: string[] = [];
  const mine = users.get(uid) ?? null;
  for (const [other, data] of users) {
    if (other === uid) continue;
    if (shouldExcludeSameDepartment(mine, data)) {
      edges.push(`${uid}>${other}`, `${other}>${uid}`);
    }
  }
  return edges.sort();
}

test("B-14: cost per users/{uid} write, before vs after, with an unchanged outcome", async () => {
  // A department of 300 where 6 members avoid same-department matches. The
  // peers' own pairs are out of scope here: only pairs with `newcomer` are
  // materialized by the calls below.
  let batch = db.batch();
  for (let i = 0; i < PEERS; i += 1) {
    const uid = `peer_${tag}_${String(i).padStart(3, "0")}`;
    const data: UserData = {
      nickname: `n${i}`,
      onboarding: { department: DEPARTMENT, bio: "x".repeat(200) },
      privacySettings: { avoidSameDepartment: i < AVOIDING_PEERS },
      heartBalance: 10,
    };
    users.set(uid, data);
    batch.set(db.collection("users").doc(uid), data);
    if (i % 400 === 399) { await batch.commit(); batch = db.batch(); }
  }
  await batch.commit();
  const newcomer = `newcomer_${tag}`;
  const log: string[] = [];
  const record = (label: string, s: { relevant: boolean; peersRead: number; pairsReconciled: number; pairsSkipped: number }, ms: number) => {
    // OLD SHAPE: one transaction per department peer on every relevant write.
    const oldTx = s.relevant ? s.peersRead : 0;
    log.push(
      `${label}: old ${oldTx} tx (${oldTx * 2} reads + ${oldTx * 2} writes) -> ` +
        `new ${s.pairsReconciled} tx (${s.pairsReconciled * 2} reads + ${s.pairsReconciled * 2} writes), ` +
        `${s.pairsSkipped} skipped, ${s.peersRead} peers read, ${ms}ms`
    );
  };
  const step = async (label: string, before: UserData | null, after: UserData | null) => {
    await writeUser(newcomer, after);
    const started = Date.now();
    const summary = await reconcileDepartmentRecommendationPrivacy(db, newcomer, before, after);
    record(label, summary, Date.now() - started);
    assert.deepEqual(await storedExclusions(), expectedExclusionsFor(newcomer), `${label}: outcome equals the policy on every pair`);
    return summary;
  };

  // 1. Account created without a department yet, then an unrelated write.
  const created: UserData = { nickname: "new", heartBalance: 0 };
  let s = await step("account created (no department)", null, created);
  assert.deepEqual(s, { relevant: false, peersRead: 0, pairsReconciled: 0, pairsSkipped: 0 });

  // 2. Onboarding sets the department: the sign-up fan-out.
  const onboarded: UserData = { ...created, onboarding: { department: DEPARTMENT } };
  s = await step("sign-up joins a 300-member department", created, onboarded);
  assert.equal(s.peersRead, PEERS);
  assert.equal(s.pairsReconciled, AVOIDING_PEERS, "only the pairs where avoidance is in play are written");
  assert.equal(s.pairsSkipped, PEERS - AVOIDING_PEERS);

  // 3. Writes that do not touch department or preference: no read at all.
  const spent: UserData = { ...onboarded, heartBalance: 25, lastActiveAt: Date.now() };
  s = await step("heart balance / lastActive update", onboarded, spent);
  assert.deepEqual(s, { relevant: false, peersRead: 0, pairsReconciled: 0, pairsSkipped: 0 });

  // 4. Redelivery of the sign-up event: only the stored pairs are re-checked.
  s = await step("redelivered sign-up event", created, onboarded);
  assert.equal(s.pairsReconciled, AVOIDING_PEERS);
  await writeUser(newcomer, spent);

  // 5. The user turns avoidance on: every pair must be materialized.
  const avoiding: UserData = { ...spent, privacySettings: { avoidSameDepartment: true } };
  s = await step("preference turned on", spent, avoiding);
  assert.equal(s.pairsReconciled, PEERS);
  assert.equal((await storedExclusions()).length, PEERS * 2);

  // 6. ...and off again: every pair is revisited, 6 remain (the peers' wish).
  const relaxed: UserData = { ...avoiding, privacySettings: { avoidSameDepartment: false } };
  s = await step("preference turned off", avoiding, relaxed);
  assert.equal(s.pairsReconciled, PEERS);
  assert.equal((await storedExclusions()).length, AVOIDING_PEERS * 2);

  // 7. Moving to another department removes the remaining pairs.
  const moved: UserData = { ...relaxed, onboarding: { department: OTHER_DEPARTMENT } };
  s = await step("department changed", relaxed, moved);
  assert.equal(s.pairsReconciled, AVOIDING_PEERS);
  assert.deepEqual(await storedExclusions(), []);

  // 8. Back, then the account is deleted: both directions are cleaned.
  await step("department changed back", moved, relaxed);
  assert.equal((await storedExclusions()).length, AVOIDING_PEERS * 2);
  s = await step("account deleted", relaxed, null);
  assert.equal(s.pairsReconciled, AVOIDING_PEERS);
  assert.deepEqual(await storedExclusions(), [], "no exclusion residue in either direction");

  console.log(`[B-14 fan-out]\n  ${log.join("\n  ")}`);
});
