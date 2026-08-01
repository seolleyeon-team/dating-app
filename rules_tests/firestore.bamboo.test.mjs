import test from "node:test";
import assert from "node:assert/strict";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import { doc, setDoc, updateDoc, increment } from "firebase/firestore";

const ALICE = "kakao_alice";
const BOB = "kakao_bob";

function seedPost(db, overrides = {}) {
  return setDoc(doc(db, "bamboo_posts", "post1"), {
    postId: "post1",
    authorId: BOB,
    content: "hello",
    category: "free",
    tags: [],
    likeCount: 3,
    commentCount: 1,
    score7d: 4,
    isDeleted: false,
    ...overrides,
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

test("signed-in users may increment bamboo counters by one", async () => {
  await withClearedDb(async (db) => {
    await seedPost(db);
  });
  const alice = await kakaoSession(ALICE);

  await assertSucceeds(
    updateDoc(doc(alice, "bamboo_posts", "post1"), {
      likeCount: increment(1),
      score7d: increment(1),
      updatedAt: new Date().toISOString(),
    })
  );
});

test("clients cannot set an arbitrary likeCount or score7d", async () => {
  await withClearedDb(async (db) => {
    await seedPost(db);
  });
  const alice = await kakaoSession(ALICE);

  // Without ±1 gates, ranking (score7d) is fully attacker-controlled.
  await assertFails(
    updateDoc(doc(alice, "bamboo_posts", "post1"), {
      likeCount: 9999,
      updatedAt: new Date().toISOString(),
    })
  );
  await assertFails(
    updateDoc(doc(alice, "bamboo_posts", "post1"), {
      score7d: 9999,
      updatedAt: new Date().toISOString(),
    })
  );
  await assertFails(
    updateDoc(doc(alice, "bamboo_posts", "post1"), {
      likeCount: increment(5),
      updatedAt: new Date().toISOString(),
    })
  );
});

test("comment likeCount also requires a ±1 delta", async () => {
  await withClearedDb(async (db) => {
    await seedPost(db);
    await setDoc(doc(db, "bamboo_posts", "post1", "comments", "c1"), {
      commentId: "c1",
      authorId: BOB,
      content: "hi",
      likeCount: 2,
      isDeleted: false,
      parentCommentId: null,
    });
  });
  const alice = await kakaoSession(ALICE);

  await assertSucceeds(
    updateDoc(doc(alice, "bamboo_posts", "post1", "comments", "c1"), {
      likeCount: increment(1),
      updatedAt: new Date().toISOString(),
    })
  );
  await assertFails(
    updateDoc(doc(alice, "bamboo_posts", "post1", "comments", "c1"), {
      likeCount: 500,
      updatedAt: new Date().toISOString(),
    })
  );
});
