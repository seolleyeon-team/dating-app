/**
 * B-08 — interactions privacy.
 *
 * The author reads everything they wrote. The target reads only like /
 * super_like (the "received hearts" surface). A nope, a profile view and the
 * `message` record are private to their author, for single reads AND for
 * list queries: a target can no longer learn who passed on them or who
 * looked at their profile.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  seedActiveUser,
  withClearedDb,
} from "./helpers.mjs";

import {
  collection,
  doc,
  getDoc,
  getDocs,
  limit,
  orderBy,
  query,
  serverTimestamp,
  setDoc,
  where,
} from "firebase/firestore";

const ALICE = "kakao_alice";
const BOB = "kakao_bob";
const CAROL = "kakao_carol";
const REVIEWER = "play-reviewer-v1";
const FIXTURE = "play-fixture-b-01";

const ACTIONS = ["like", "super_like", "nope", "view", "message"];

function interaction(from, to, action, extra = {}) {
  return { fromUserId: from, toUserId: to, action, source: "profile", createdAt: new Date(), ...extra };
}

async function seed(db) {
  await seedActiveUser(db, ALICE);
  await seedActiveUser(db, BOB);
  await seedActiveUser(db, CAROL);
  await seedActiveUser(db, REVIEWER, { dataPartition: "play_review", accountType: "google_play_review" });
  await seedActiveUser(db, FIXTURE, { dataPartition: "play_review", accountType: "google_play_fixture" });
  // Alice reacted to Bob in every way; Carol liked and noped Bob too.
  for (const action of ACTIONS) {
    await setDoc(doc(db, "interactions", `a_b_${action}`), interaction(ALICE, BOB, action));
  }
  await setDoc(doc(db, "interactions", "c_b_like"), interaction(CAROL, BOB, "like"));
  await setDoc(doc(db, "interactions", "c_b_nope"), interaction(CAROL, BOB, "nope"));
  await setDoc(doc(db, "interactions", "c_b_view"), interaction(CAROL, BOB, "view"));
  // Review partition traffic.
  await setDoc(doc(db, "interactions", "r_f_like"),
    interaction(REVIEWER, FIXTURE, "like", { dataPartition: "play_review" }));
  await setDoc(doc(db, "interactions", "f_r_like"),
    interaction(FIXTURE, REVIEWER, "like", { dataPartition: "play_review" }));
}

async function reviewerSession() {
  const env = await getTestEnv();
  return env
    .authenticatedContext(REVIEWER, {
      appSession: true,
      playReviewer: true,
      dataPartition: "play_review",
    })
    .firestore();
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

test("B-08: the author reads every interaction they wrote, whatever its action", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  for (const action of ACTIONS) {
    const snap = await assertSucceeds(getDoc(doc(alice, "interactions", `a_b_${action}`)));
    assert.equal(snap.data().action, action);
  }
});

test("B-08: the target still reads a like and a super_like sent to them (existing like visibility)", async () => {
  await withClearedDb(seed);
  const bob = await kakaoSession(BOB);
  await assertSucceeds(getDoc(doc(bob, "interactions", "a_b_like")));
  await assertSucceeds(getDoc(doc(bob, "interactions", "a_b_super_like")));
});

test("B-08: the target cannot read who noped them", async () => {
  await withClearedDb(seed);
  const bob = await kakaoSession(BOB);
  await assertFails(getDoc(doc(bob, "interactions", "a_b_nope")));
  await assertFails(getDoc(doc(bob, "interactions", "c_b_nope")));
});

test("B-08: the target cannot read who viewed their profile, nor the sender's message record", async () => {
  await withClearedDb(seed);
  const bob = await kakaoSession(BOB);
  await assertFails(getDoc(doc(bob, "interactions", "a_b_view")));
  await assertFails(getDoc(doc(bob, "interactions", "c_b_view")));
  await assertFails(getDoc(doc(bob, "interactions", "a_b_message")));
});

test("B-08: a third party reads nothing", async () => {
  await withClearedDb(seed);
  const carol = await kakaoSession(CAROL);
  for (const action of ACTIONS) {
    await assertFails(getDoc(doc(carol, "interactions", `a_b_${action}`)));
  }
});

test("B-08: the client's real list queries keep working (received hearts, sent hearts, hasInteracted)", async () => {
  await withClearedDb(seed);
  const bob = await kakaoSession(BOB);
  const alice = await kakaoSession(ALICE);
  // InteractionService.watchLikesReceived / getLikesReceived
  const received = await assertSucceeds(getDocs(query(
    collection(bob, "interactions"),
    where("toUserId", "==", BOB),
    where("action", "in", ["like", "super_like"]),
    orderBy("createdAt", "desc"),
  )));
  assert.deepEqual(received.docs.map((d) => d.id).sort(), ["a_b_like", "a_b_super_like", "c_b_like"]);
  // InteractionService.watchLikesSent / getLikesSent
  const sent = await assertSucceeds(getDocs(query(
    collection(alice, "interactions"),
    where("fromUserId", "==", ALICE),
    where("action", "in", ["like", "super_like"]),
    orderBy("createdAt", "desc"),
  )));
  assert.deepEqual(sent.docs.map((d) => d.id).sort(), ["a_b_like", "a_b_super_like"]);
  // InteractionService.hasInteracted
  const decided = await assertSucceeds(getDocs(query(
    collection(alice, "interactions"),
    where("fromUserId", "==", ALICE),
    where("toUserId", "==", BOB),
    where("action", "in", ["like", "nope", "super_like"]),
    limit(1),
  )));
  assert.equal(decided.size, 1);
  // The author may list everything they wrote.
  const mine = await assertSucceeds(getDocs(query(
    collection(alice, "interactions"),
    where("fromUserId", "==", ALICE),
  )));
  assert.equal(mine.size, ACTIONS.length);
});

test("B-08: the target cannot enumerate reactions with list queries", async () => {
  await withClearedDb(seed);
  const bob = await kakaoSession(BOB);
  const ref = collection(bob, "interactions");
  // No action filter: would return nopes and views.
  await assertFails(getDocs(query(ref, where("toUserId", "==", BOB))));
  await assertFails(getDocs(query(ref, where("toUserId", "==", BOB), limit(1))));
  // Explicitly asking for the private actions.
  await assertFails(getDocs(query(ref, where("toUserId", "==", BOB), where("action", "==", "nope"))));
  await assertFails(getDocs(query(ref, where("toUserId", "==", BOB), where("action", "==", "view"))));
  await assertFails(getDocs(query(ref, where("toUserId", "==", BOB), where("action", "==", "message"))));
  await assertFails(getDocs(query(ref, where("toUserId", "==", BOB), where("action", "in", ["like", "nope"]))));
  await assertFails(getDocs(query(ref, where("toUserId", "==", BOB), where("action", "in", ["like", "super_like", "view"]))));
  // Someone else's outgoing reactions, and the whole collection.
  await assertFails(getDocs(query(ref, where("fromUserId", "==", ALICE))));
  await assertFails(getDocs(query(ref, where("fromUserId", "==", ALICE), where("action", "==", "nope"))));
  await assertFails(getDocs(query(ref, where("action", "==", "nope"))));
  await assertFails(getDocs(ref));
  // A single allowed action is narrower than the policy and stays readable.
  await assertSucceeds(getDocs(query(ref, where("toUserId", "==", BOB), where("action", "==", "like"))));
});

test("B-08: no cross-partition access in either direction", async () => {
  await withClearedDb(seed);
  const alice = await kakaoSession(ALICE);
  const bob = await kakaoSession(BOB);
  const reviewer = await reviewerSession();
  // Production accounts cannot see review-partition interactions.
  await assertFails(getDoc(doc(alice, "interactions", "r_f_like")));
  await assertFails(getDoc(doc(bob, "interactions", "f_r_like")));
  await assertFails(getDocs(query(collection(alice, "interactions"), where("toUserId", "==", FIXTURE), where("action", "in", ["like", "super_like"]))));
  await assertFails(getDocs(query(collection(alice, "interactions"), where("fromUserId", "==", REVIEWER))));
  // The reviewer cannot see production interactions, single or listed.
  for (const action of ACTIONS) {
    await assertFails(getDoc(doc(reviewer, "interactions", `a_b_${action}`)));
  }
  await assertFails(getDocs(query(collection(reviewer, "interactions"), where("toUserId", "==", BOB), where("action", "in", ["like", "super_like"]))));
  await assertFails(getDocs(query(collection(reviewer, "interactions"), where("fromUserId", "==", ALICE))));
  // The reviewer cannot plant an interaction on a production account either.
  await assertFails(setDoc(doc(reviewer, "interactions", "r_b_like"), {
    fromUserId: REVIEWER, toUserId: BOB, action: "like", source: "profile",
    createdAt: serverTimestamp(), dataPartition: "play_review",
  }));
  // Inside its own partition the reviewer keeps the normal policy.
  await assertSucceeds(getDoc(doc(reviewer, "interactions", "r_f_like")));
  await assertSucceeds(getDoc(doc(reviewer, "interactions", "f_r_like")));
});

test("B-08: write-first one-shot decisions still work (create, refused repeat, author re-read) for like and nope", async () => {
  await withClearedDb(seed);
  const carol = await kakaoSession(CAROL);
  for (const action of ["like", "nope", "super_like"]) {
    const ref = doc(carol, "interactions", `${CAROL}_${ALICE}_${action}`);
    const payload = { fromUserId: CAROL, toUserId: ALICE, action, source: "profile", metadata: null, createdAt: serverTimestamp() };
    // A missing document is unreadable (resource.data is null): write first.
    await assertFails(getDoc(ref));
    await assertSucceeds(setDoc(ref, payload));
    await assertFails(setDoc(ref, payload));
    const again = await assertSucceeds(getDoc(ref));
    assert.equal(again.exists(), true);
  }
  // Alice (the target) sees Carol's like but not Carol's nope.
  const alice = await kakaoSession(ALICE);
  await assertSucceeds(getDoc(doc(alice, "interactions", `${CAROL}_${ALICE}_like`)));
  await assertFails(getDoc(doc(alice, "interactions", `${CAROL}_${ALICE}_nope`)));
});
