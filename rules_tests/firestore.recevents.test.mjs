import test from "node:test";
import assert from "node:assert/strict";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import { doc, setDoc, updateDoc, deleteDoc, collection, addDoc } from "firebase/firestore";

const ALICE = "kakao_alice";
const BOB = "kakao_bob";

function validLike(overrides = {}) {
  return {
    userId: ALICE,
    targetType: "user_profile",
    targetId: BOB,
    targetUserId: BOB,
    candidateUserId: BOB,
    type: "like",
    eventType: "like",
    surface: "profile_card",
    source: "profile_card",
    cardVariant: "real_profile",
    eventTime: "2026-07-27T00:00:00.000Z",
    createdAt: "2026-07-27T00:00:00.000Z",
    exposureId: "exp-1",
    dateKey: "2026-07-27",
    ...overrides,
  };
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

test("an owner can append a well-formed recEvent", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  await assertSucceeds(
    addDoc(collection(alice, "recEvents", ALICE, "events"), validLike())
  );
});

test("a client cannot rewrite or delete a past recEvent", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "recEvents", ALICE, "events", "e1"), validLike());
  });
  const alice = await kakaoSession(ALICE);

  // Without this gate, Alice could change a nope into a like after Bob liked her,
  // and onRecEventCreated's mutual-match path would create a match she never made.
  await assertFails(
    updateDoc(doc(alice, "recEvents", ALICE, "events", "e1"), {
      type: "like",
      eventType: "like",
    })
  );
  await assertFails(deleteDoc(doc(alice, "recEvents", ALICE, "events", "e1")));
});

test("event type must be on the whitelist", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  await assertFails(
    addDoc(
      collection(alice, "recEvents", ALICE, "events"),
      validLike({ type: "admin_boost", eventType: "admin_boost" })
    )
  );
});

test("type and eventType must agree", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  await assertFails(
    addDoc(
      collection(alice, "recEvents", ALICE, "events"),
      validLike({ type: "like", eventType: "nope" })
    )
  );
});

test("path userId must match the payload userId", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  await assertFails(
    addDoc(
      collection(alice, "recEvents", ALICE, "events"),
      validLike({ userId: BOB })
    )
  );
});

test("self-targeting events are rejected", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  await assertFails(
    addDoc(
      collection(alice, "recEvents", ALICE, "events"),
      validLike({
        targetId: ALICE,
        targetUserId: ALICE,
        candidateUserId: ALICE,
      })
    )
  );
});

test("a client cannot write into another user's recEvents", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  await assertFails(
    addDoc(collection(alice, "recEvents", BOB, "events"), validLike({ userId: BOB }))
  );
});

test("parent lastEventAt metadata remains writable by the owner", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  await assertSucceeds(
    setDoc(doc(alice, "recEvents", ALICE), { lastEventAt: "2026-07-27T00:00:00.000Z" }, { merge: true })
  );
});

test("schemaVersion 1 is accepted and invalid schemaVersion is rejected", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  await assertSucceeds(
    addDoc(
      collection(alice, "recEvents", ALICE, "events"),
      validLike({ schemaVersion: 1 })
    )
  );

  await assertFails(
    addDoc(
      collection(alice, "recEvents", ALICE, "events"),
      validLike({ schemaVersion: 99 })
    )
  );
});

test("legacy recEvents without schemaVersion remain creatable", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);
  const legacy = validLike();
  delete legacy.schemaVersion;

  await assertSucceeds(
    addDoc(collection(alice, "recEvents", ALICE, "events"), legacy)
  );
});
