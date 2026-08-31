import test from "node:test";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import { doc, getDoc, setDoc, updateDoc, deleteDoc } from "firebase/firestore";

const ALICE = "kakao_alice";
const BOB = "kakao_bob";
const DATE_KEY = "20260830";

function completedEntitlement() {
  return {
    product: "one_to_one_daily_refresh",
    dateKey: DATE_KEY,
    algo: "rrf",
    costHearts: 5,
    refreshIndex: 1,
    displayRankStart: 4,
    displayRankEnd: 6,
    status: "completed",
    heartBalanceAfter: 5,
  };
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

test("an owner can read their own refresh entitlement", async () => {
  await withClearedDb(async (db) => {
    await setDoc(
      doc(db, "users", ALICE, "recommendationRefreshes", DATE_KEY),
      completedEntitlement()
    );
  });
  const alice = await kakaoSession(ALICE);

  await assertSucceeds(
    getDoc(doc(alice, "users", ALICE, "recommendationRefreshes", DATE_KEY))
  );
});

test("another user cannot read someone else's refresh entitlement", async () => {
  await withClearedDb(async (db) => {
    await setDoc(
      doc(db, "users", ALICE, "recommendationRefreshes", DATE_KEY),
      completedEntitlement()
    );
  });
  const bob = await kakaoSession(BOB);

  await assertFails(
    getDoc(doc(bob, "users", ALICE, "recommendationRefreshes", DATE_KEY))
  );
});

test("a client cannot forge a refresh entitlement to unlock ranks 4-6 for free", async () => {
  await withClearedDb();
  const alice = await kakaoSession(ALICE);

  await assertFails(
    setDoc(
      doc(alice, "users", ALICE, "recommendationRefreshes", DATE_KEY),
      completedEntitlement()
    )
  );
});

test("a client cannot rewrite or delete an existing refresh receipt", async () => {
  await withClearedDb(async (db) => {
    await setDoc(
      doc(db, "users", ALICE, "recommendationRefreshes", DATE_KEY),
      completedEntitlement()
    );
  });
  const alice = await kakaoSession(ALICE);

  await assertFails(
    updateDoc(doc(alice, "users", ALICE, "recommendationRefreshes", DATE_KEY), {
      displayRankStart: 7,
      displayRankEnd: 9,
    })
  );
  await assertFails(
    deleteDoc(doc(alice, "users", ALICE, "recommendationRefreshes", DATE_KEY))
  );
});

test("a client cannot debit or credit heartBalance directly", async () => {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "users", ALICE), {
      kakaoUserId: ALICE,
      isStudentVerified: true,
      studentEmail: "alice@yonsei.ac.kr",
      heartBalance: 10,
    });
  });
  const alice = await kakaoSession(ALICE);

  await assertFails(updateDoc(doc(alice, "users", ALICE), { heartBalance: 5 }));
  await assertFails(
    updateDoc(doc(alice, "users", ALICE), { heartBalance: 99999 })
  );
});
