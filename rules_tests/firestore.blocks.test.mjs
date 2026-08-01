import test from "node:test";
import assert from "node:assert/strict";

import {
  assertFails,
  assertSucceeds,
  anon,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import {
  doc,
  deleteDoc,
  getDoc,
  getDocs,
  collection,
  setDoc,
} from "firebase/firestore";

const ALICE = "kakao_alice";
const BOB = "kakao_bob";

// node --test runs each file in its own process, so this file needs its own
// teardown or the run hangs holding an emulator connection.
test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

function blockRef(db, ownerUid, targetUid) {
  return doc(db, "blocks", ownerUid, "targets", targetUid);
}

async function seedMutualBlock(db) {
  await setDoc(blockRef(db, ALICE, BOB), {
    fromUserId: ALICE,
    toUserId: BOB,
    reason: "user_report",
    source: "report",
  });
  await setDoc(blockRef(db, BOB, ALICE), {
    fromUserId: BOB,
    toUserId: ALICE,
    reason: "user_report",
    source: "report_mutual",
  });
}

// ---------------------------------------------------------------------------
// Blocks must be server-written
// ---------------------------------------------------------------------------

test("a client cannot create a one-directional block on itself", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  // Allowing this lets a client block without the mutual reverse edge, which
  // is exactly the asymmetry reportAndBlockUser exists to prevent.
  await assertFails(
    setDoc(blockRef(alice, ALICE, BOB), {
      fromUserId: ALICE,
      toUserId: BOB,
    })
  );
});

test("a client cannot write into another user's block list", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  await assertFails(
    setDoc(blockRef(alice, BOB, ALICE), {
      fromUserId: BOB,
      toUserId: ALICE,
    })
  );
});

test("an unauthenticated client cannot write blocks", async () => {
  await withClearedDb();
  const guest = await anon();

  await assertFails(
    setDoc(blockRef(guest, ALICE, BOB), { fromUserId: ALICE, toUserId: BOB })
  );
});

test("server-written mutual blocks are readable by each owner only", async () => {
  await withClearedDb(seedMutualBlock);

  const alice = await kakaoSession(ALICE);
  const bob = await kakaoSession(BOB);

  const aliceSide = await assertSucceeds(
    getDocs(collection(alice, "blocks", ALICE, "targets"))
  );
  assert.deepEqual(
    aliceSide.docs.map((entry) => entry.id),
    [BOB]
  );

  // The reverse edge exists, so Bob's feed filter also excludes Alice.
  const bobSide = await assertSucceeds(
    getDocs(collection(bob, "blocks", BOB, "targets"))
  );
  assert.deepEqual(
    bobSide.docs.map((entry) => entry.id),
    [ALICE]
  );

  await assertFails(getDoc(blockRef(alice, BOB, ALICE)));

  const guest = await anon();
  await assertFails(getDocs(collection(guest, "blocks", ALICE, "targets")));
});

test("an owner can still unblock their own side", async () => {
  await withClearedDb(seedMutualBlock);
  const alice = await kakaoSession(ALICE);

  await assertSucceeds(deleteDoc(blockRef(alice, ALICE, BOB)));
  await assertFails(deleteDoc(blockRef(alice, BOB, ALICE)));
});

// ---------------------------------------------------------------------------
// Reports must be server-written
// ---------------------------------------------------------------------------

test("a client cannot create a report directly", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  // Direct creation would skip the mutual block written alongside the report.
  await assertFails(
    setDoc(doc(alice, "reports", "r1"), {
      reporterId: ALICE,
      reportedId: BOB,
      reason: "harassment",
      status: "pending",
    })
  );
});

test("reports stay unreadable and immutable for clients", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "reports", "r1"), {
      reporterId: ALICE,
      reportedId: BOB,
      reason: "harassment",
      status: "pending",
    });
  });

  const alice = await kakaoSession(ALICE);
  const bob = await kakaoSession(BOB);

  await assertFails(getDoc(doc(alice, "reports", "r1")));
  await assertFails(getDoc(doc(bob, "reports", "r1")));
  await assertFails(setDoc(doc(bob, "reports", "r1"), { status: "dismissed" }));
  await assertFails(deleteDoc(doc(bob, "reports", "r1")));
});
