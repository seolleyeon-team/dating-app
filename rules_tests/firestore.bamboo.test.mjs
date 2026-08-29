import test from "node:test";
import assert from "node:assert/strict";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import {
  doc,
  setDoc,
  updateDoc,
  increment,
  writeBatch,
} from "firebase/firestore";

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

test("likes move the counters only with the like document (SEC-P3-01)", async () => {
  await withClearedDb(async (db) => {
    await seedPost(db);
  });
  const alice = await kakaoSession(ALICE);

  // 카운터만 올리는 요청은 like 문서 전이가 없으므로 랭킹 조작이다.
  await assertFails(
    updateDoc(doc(alice, "bamboo_posts", "post1"), {
      likeCount: increment(1),
      score7d: increment(1),
      updatedAt: new Date().toISOString(),
    })
  );

  // 앱의 togglePostLike 는 like 문서와 카운터를 한 커밋으로 쓴다.
  const batch = writeBatch(alice);
  batch.set(doc(alice, "bamboo_posts", "post1", "likes", ALICE), {
    userId: ALICE,
    createdAt: new Date().toISOString(),
  });
  batch.update(doc(alice, "bamboo_posts", "post1"), {
    likeCount: increment(1),
    score7d: increment(1),
    updatedAt: new Date().toISOString(),
  });
  await assertSucceeds(batch.commit());
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
