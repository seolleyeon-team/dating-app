/**
 * P0-3 — 대나무숲 익명성 공격 스위트 (실제 Security Rules + 인증된 SDK 클라이언트).
 *
 * 불변식: 일반 로그인 사용자는 앱이 통제하는 공개 데이터로 익명 글·댓글·좋아요의
 * 작성자 실계정을 특정할 수 없다. 공격자가 피해자 UID 를 이미 알고, SDK 를 직접
 * 쓰고, 문서 id 를 알고 있어도 마찬가지다.
 *
 *   USER_A  = 작성자 (피해자)
 *   USER_B  = 공격자
 *   USER_C  = 무관한 사용자
 *   REVIEW  = Play 심사 세션
 *
 * 서버 writer / 알림 / 마이그레이션은 functions 쪽 에뮬레이터 테스트가 맡는다.
 * 여기서는 규칙이 지키는 경계만 본다.
 */
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
  collection,
  collectionGroup,
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  increment,
  query,
  setDoc,
  updateDoc,
  where,
  writeBatch,
} from "firebase/firestore";

const A = "kakao_author_a";
const B = "kakao_attacker_b";
const C = "kakao_unrelated_c";
const REVIEWER = "play-reviewer-v1";

const POST = "postA";
const COMMENT = "commentA";
const REPLY = "replyB";
const REVIEW_POST = "review_post";

/** 서버 writer(createCommunityPost/Comment) 가 실제로 쓰는 public 스키마. */
const PUBLIC_POST_KEYS = new Set([
  "postId", "content", "category", "tags", "createdAt", "updatedAt",
  "likeCount", "commentCount", "score7d", "isDeleted", "dataPartition", "reviewFixture",
]);
const PUBLIC_COMMENT_KEYS = new Set([
  "commentId", "content", "parentCommentId", "createdAt", "updatedAt",
  "likeCount", "isDeleted", "dataPartition", "reviewFixture",
]);

const now = () => new Date();

async function reviewSession(uid = REVIEWER) {
  const env = await getTestEnv();
  return env
    .authenticatedContext(uid, { appSession: true, playReviewer: true, dataPartition: "play_review" })
    .firestore();
}

async function seed() {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "bamboo_posts", POST), {
      postId: POST, content: "A 의 익명 글", category: "고민", tags: [],
      createdAt: now(), updatedAt: now(), likeCount: 1, commentCount: 2, score7d: 3, isDeleted: false,
    });
    await setDoc(doc(db, "bamboo_post_authors", POST), { postId: POST, ownerUid: A, createdAt: now() });
    await setDoc(doc(db, "bamboo_posts", POST, "comments", COMMENT), {
      commentId: COMMENT, content: "A 의 댓글", parentCommentId: null,
      createdAt: now(), updatedAt: now(), likeCount: 0, isDeleted: false,
    });
    await setDoc(doc(db, "bamboo_comment_authors", `${POST}__${COMMENT}`), {
      postId: POST, commentId: COMMENT, ownerUid: A, createdAt: now(),
    });
    await setDoc(doc(db, "bamboo_posts", POST, "comments", REPLY), {
      commentId: REPLY, content: "B 의 답글", parentCommentId: COMMENT,
      createdAt: now(), updatedAt: now(), likeCount: 0, isDeleted: false,
    });
    await setDoc(doc(db, "bamboo_comment_authors", `${POST}__${REPLY}`), {
      postId: POST, commentId: REPLY, ownerUid: B, createdAt: now(),
    });
    // A 가 자기 글이 아닌 글에도 좋아요를 눌렀다고 하자 — 공격자는 그걸 알아내려 한다.
    await setDoc(doc(db, "bamboo_posts", POST, "likes", A), { userId: A, createdAt: now() });
    await setDoc(doc(db, "bamboo_posts", POST, "comments", COMMENT, "likes", A), { userId: A, createdAt: now() });
    // A 의 알림함과 신고 숨김 목록
    await setDoc(doc(db, "users", A, "notifications", "n1"), {
      type: "community_comment", actorId: null, actorName: "익명", postId: POST, commentId: REPLY, isRead: false,
    });
    await setDoc(doc(db, "users", A, "bambooHiddenContent", "otherPost"), {
      contentType: "bamboo_post", postId: "otherPost", commentId: null,
    });
    // Play 심사 파티션
    await setDoc(doc(db, "playReviewBambooPosts", REVIEW_POST), {
      postId: REVIEW_POST, content: "심사 글", category: "일상", tags: [], dataPartition: "play_review",
      createdAt: now(), updatedAt: now(), likeCount: 0, commentCount: 0, score7d: 0, isDeleted: false,
    });
    await setDoc(doc(db, "playReviewBambooPostAuthors", REVIEW_POST), {
      postId: REVIEW_POST, ownerUid: REVIEWER, dataPartition: "play_review", createdAt: now(),
    });
  });
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

test.beforeEach(seed);

// ---------------------------------------------------------------------------
// ATTACK 1–3, 19 — 공개 문서 열거와 프로필 join
// ---------------------------------------------------------------------------
test("ATTACK 1: B 가 열람 가능한 글을 모두 받아도 작성자 식별 필드가 없다", async () => {
  const b = await kakaoSession(B);
  const posts = await assertSucceeds(getDocs(collection(b, "bamboo_posts")));
  assert.ok(posts.size > 0);
  for (const p of posts.docs) {
    for (const key of Object.keys(p.data())) assert.ok(PUBLIC_POST_KEYS.has(key), `post field ${key}`);
  }
});

test("ATTACK 2: 댓글·답글 열거에도 작성자 식별 필드가 없다", async () => {
  const b = await kakaoSession(B);
  const comments = await assertSucceeds(getDocs(collection(b, "bamboo_posts", POST, "comments")));
  assert.equal(comments.size, 2);
  for (const c of comments.docs) {
    for (const key of Object.keys(c.data())) assert.ok(PUBLIC_COMMENT_KEYS.has(key), `comment field ${key}`);
  }
});

test("ATTACK 3/19: A 의 UID 를 알아도 public 쿼리로 A 의 글을 고를 수 없다 (publicProfiles join 불가)", async () => {
  const b = await kakaoSession(B);
  for (const field of ["authorId", "ownerUid", "userId", "actorId"]) {
    const res = await assertSucceeds(getDocs(query(collection(b, "bamboo_posts"), where(field, "==", A))));
    assert.equal(res.size, 0, `bamboo_posts where ${field} == A`);
  }
});

test("ATTACK 18: 댓글 collectionGroup 쿼리는 거부된다", async () => {
  const b = await kakaoSession(B);
  await assertFails(getDocs(query(collectionGroup(b, "comments"), where("isDeleted", "==", false))));
});

// ---------------------------------------------------------------------------
// ATTACK 5, 19 — 좋아요 열거
// ---------------------------------------------------------------------------
test("ATTACK 5: B 는 좋아요 목록을 list 할 수 없다 (글·댓글)", async () => {
  const b = await kakaoSession(B);
  await assertFails(getDocs(collection(b, "bamboo_posts", POST, "likes")));
  await assertFails(getDocs(collection(b, "bamboo_posts", POST, "comments", COMMENT, "likes")));
  await assertFails(getDocs(query(collection(b, "bamboo_posts", POST, "likes"), where("userId", "==", A))));
});

test("ATTACK 5: B 는 collectionGroup('likes') 로 A 의 좋아요를 찾을 수 없다", async () => {
  const b = await kakaoSession(B);
  await assertFails(getDocs(query(collectionGroup(b, "likes"), where("userId", "==", A))));
  await assertFails(getDocs(collectionGroup(b, "likes")));
});

test("ATTACK 19: UID 를 알아도 A 가 좋아요를 눌렀는지 시험할 수 없다 — 있는 문서와 없는 문서가 같은 거부", async () => {
  const b = await kakaoSession(B);
  await assertFails(getDoc(doc(b, "bamboo_posts", POST, "likes", A))); // 존재
  await assertFails(getDoc(doc(b, "bamboo_posts", POST, "likes", C))); // 부재
  await assertFails(getDoc(doc(b, "bamboo_posts", POST, "comments", COMMENT, "likes", A)));
});

test("본인은 자기 좋아요 여부를 확인할 수 있다 (hasLiked)", async () => {
  const a = await kakaoSession(A);
  const own = await assertSucceeds(getDoc(doc(a, "bamboo_posts", POST, "likes", A)));
  assert.equal(own.exists(), true);
  const c = await kakaoSession(C);
  const none = await assertSucceeds(getDoc(doc(c, "bamboo_posts", POST, "likes", C)));
  assert.equal(none.exists(), false);
});

test("좋아요/취소는 like 문서와 카운터를 한 커밋으로 움직일 때만 된다", async () => {
  const c = await kakaoSession(C);
  const like = writeBatch(c);
  like.set(doc(c, "bamboo_posts", POST, "likes", C), { userId: C, createdAt: now() });
  like.update(doc(c, "bamboo_posts", POST), { likeCount: increment(1), score7d: increment(1), updatedAt: now() });
  await assertSucceeds(like.commit());
  // 같은 사람이 또 +1 할 수 없다
  await assertFails(updateDoc(doc(c, "bamboo_posts", POST), { likeCount: increment(1), score7d: increment(1), updatedAt: now() }));
  const unlike = writeBatch(c);
  unlike.delete(doc(c, "bamboo_posts", POST, "likes", C));
  unlike.update(doc(c, "bamboo_posts", POST), { likeCount: increment(-1), score7d: increment(-1), updatedAt: now() });
  await assertSucceeds(unlike.commit());

  const commentLike = writeBatch(c);
  commentLike.set(doc(c, "bamboo_posts", POST, "comments", COMMENT, "likes", C), { userId: C, createdAt: now() });
  commentLike.update(doc(c, "bamboo_posts", POST, "comments", COMMENT), { likeCount: increment(1), updatedAt: now() });
  await assertSucceeds(commentLike.commit());
  const commentUnlike = writeBatch(c);
  commentUnlike.delete(doc(c, "bamboo_posts", POST, "comments", COMMENT, "likes", C));
  commentUnlike.update(doc(c, "bamboo_posts", POST, "comments", COMMENT), { likeCount: increment(-1), updatedAt: now() });
  await assertSucceeds(commentUnlike.commit());
});

test("남의 좋아요 문서를 만들거나 지울 수 없다", async () => {
  const b = await kakaoSession(B);
  await assertFails(setDoc(doc(b, "bamboo_posts", POST, "likes", C), { userId: C, createdAt: now() }));
  await assertFails(deleteDoc(doc(b, "bamboo_posts", POST, "likes", A)));
  await assertFails(deleteDoc(doc(b, "bamboo_posts", POST, "comments", COMMENT, "likes", A)));
});

// ---------------------------------------------------------------------------
// ATTACK 6, 7, 15 — 비공개 매핑
// ---------------------------------------------------------------------------
test("ATTACK 6: B 는 A 의 매핑을 get / list / 조건 쿼리 할 수 없다", async () => {
  const b = await kakaoSession(B);
  await assertFails(getDoc(doc(b, "bamboo_post_authors", POST)));
  await assertFails(getDoc(doc(b, "bamboo_comment_authors", `${POST}__${COMMENT}`)));
  await assertFails(getDoc(doc(b, "bamboo_post_authors", "no_such_post"))); // 부재도 같은 거부
  await assertFails(getDocs(collection(b, "bamboo_post_authors")));
  await assertFails(getDocs(query(collection(b, "bamboo_post_authors"), where("ownerUid", "==", A))));
  await assertFails(getDocs(query(collection(b, "bamboo_comment_authors"), where("ownerUid", "==", A))));
  await assertFails(getDocs(query(collection(b, "bamboo_post_authors"), where("postId", "==", POST))));
  await assertFails(getDocs(query(collectionGroup(b, "bamboo_post_authors"), where("ownerUid", "==", A))));
});

test("본인은 자기 매핑만 읽는다 (내가 쓴 글 / 내 댓글 표시)", async () => {
  const a = await kakaoSession(A);
  await assertSucceeds(getDoc(doc(a, "bamboo_post_authors", POST)));
  const mine = await assertSucceeds(getDocs(query(collection(a, "bamboo_post_authors"), where("ownerUid", "==", A))));
  assert.equal(mine.size, 1);
  const inPage = await assertSucceeds(getDocs(query(
    collection(a, "bamboo_post_authors"), where("ownerUid", "==", A), where("postId", "in", [POST, "x"]))));
  assert.equal(inPage.size, 1);
  const myComments = await assertSucceeds(getDocs(query(
    collection(a, "bamboo_comment_authors"), where("ownerUid", "==", A), where("postId", "==", POST))));
  assert.deepEqual(myComments.docs.map((d) => d.data().commentId), [COMMENT]);
  // B 의 답글 매핑은 A 에게 보이지 않는다
  await assertFails(getDoc(doc(a, "bamboo_comment_authors", `${POST}__${REPLY}`)));
});

test("ATTACK 7: 소유권을 주장·이전·삭제할 수 없다 (매핑은 서버만 쓴다)", async () => {
  const b = await kakaoSession(B);
  const a = await kakaoSession(A);
  await assertFails(setDoc(doc(b, "bamboo_post_authors", POST), { postId: POST, ownerUid: B }));
  await assertFails(setDoc(doc(b, "bamboo_post_authors", "brandNew"), { postId: "brandNew", ownerUid: B }));
  await assertFails(setDoc(doc(b, "bamboo_comment_authors", `${POST}__${COMMENT}`), { postId: POST, commentId: COMMENT, ownerUid: B }));
  await assertFails(updateDoc(doc(a, "bamboo_post_authors", POST), { ownerUid: B }));
  await assertFails(deleteDoc(doc(a, "bamboo_post_authors", POST)));
  await assertFails(setDoc(doc(a, "bamboo_post_authors", "unmappedPost"), { postId: "unmappedPost", ownerUid: A }));
});

// ---------------------------------------------------------------------------
// ATTACK 8, 9, 11 — 삭제·카운터·스키마 주입
// ---------------------------------------------------------------------------
test("ATTACK 8: 직접 삭제·soft delete 는 누구도 못 한다 (본인 삭제는 서버 callable)", async () => {
  for (const uid of [A, B]) {
    const db = await kakaoSession(uid);
    await assertFails(updateDoc(doc(db, "bamboo_posts", POST), { isDeleted: true, updatedAt: now() }));
    await assertFails(updateDoc(doc(db, "bamboo_posts", POST, "comments", COMMENT), { isDeleted: true, updatedAt: now() }));
    await assertFails(deleteDoc(doc(db, "bamboo_posts", POST)));
    await assertFails(deleteDoc(doc(db, "bamboo_posts", POST, "comments", COMMENT)));
  }
});

test("ATTACK 9: likeCount / commentCount / score7d 위조는 거부된다", async () => {
  const b = await kakaoSession(B);
  const post = doc(b, "bamboo_posts", POST);
  await assertFails(updateDoc(post, { likeCount: increment(1), score7d: increment(1), updatedAt: now() })); // like 문서 없음
  await assertFails(updateDoc(post, { commentCount: increment(1), score7d: increment(1), updatedAt: now() }));
  await assertFails(updateDoc(post, { commentCount: increment(-1), updatedAt: now() }));
  await assertFails(updateDoc(post, { score7d: increment(1), updatedAt: now() }));
  await assertFails(updateDoc(post, { likeCount: 9999 }));
  await assertFails(updateDoc(doc(b, "bamboo_posts", POST, "comments", COMMENT), { likeCount: increment(1), updatedAt: now() }));
  await assertFails(updateDoc(doc(b, "bamboo_posts", POST, "comments", COMMENT), { parentCommentId: "x" }));
  await assertFails(updateDoc(post, { content: "바꿔치기" }));
});

test("ATTACK 11: 클라이언트는 작성자 식별 필드를 심을 수 없다", async () => {
  const b = await kakaoSession(B);
  await assertFails(setDoc(doc(b, "bamboo_posts", "fresh"), {
    postId: "fresh", authorId: B, content: "x", category: "고민", tags: [],
    likeCount: 0, commentCount: 0, score7d: 0, isDeleted: false,
  }));
  await assertFails(setDoc(doc(b, "bamboo_posts", POST, "comments", "freshC"), {
    commentId: "freshC", authorId: B, content: "x", parentCommentId: null, likeCount: 0, isDeleted: false,
  }));
  for (const field of ["authorId", "ownerUid", "actorId", "actorName", "nickname"]) {
    await assertFails(updateDoc(doc(b, "bamboo_posts", POST), { [field]: B }));
    await assertFails(updateDoc(doc(b, "bamboo_posts", POST, "comments", COMMENT), { [field]: B }));
  }
  // 좋아요 문서에 다른 필드를 끼워 넣을 수 없다
  const batch = writeBatch(b);
  batch.set(doc(b, "bamboo_posts", POST, "likes", B), { userId: B, createdAt: now(), actorName: "B" });
  batch.update(doc(b, "bamboo_posts", POST), { likeCount: increment(1), score7d: increment(1), updatedAt: now() });
  await assertFails(batch.commit());
});

// ---------------------------------------------------------------------------
// ATTACK 4 (rules), 10, 16
// ---------------------------------------------------------------------------
test("ATTACK 4: 알림함은 받는 사람만 읽고, 다른 사람은 읽을 수 없다", async () => {
  const a = await kakaoSession(A);
  const b = await kakaoSession(B);
  const own = await assertSucceeds(getDoc(doc(a, "users", A, "notifications", "n1")));
  assert.equal(own.data().actorId, null);
  await assertFails(getDoc(doc(b, "users", A, "notifications", "n1")));
  await assertFails(getDocs(collectionGroup(b, "notifications")));
  // 받는 사람도 행위자 필드를 고쳐 쓸 수 없다
  await assertFails(updateDoc(doc(a, "users", A, "notifications", "n1"), { actorId: B }));
});

test("ATTACK 10: 일반 사용자 ↔ 심사 파티션 교차 접근은 거부된다", async () => {
  const b = await kakaoSession(B);
  const review = await reviewSession();
  await assertFails(getDoc(doc(b, "playReviewBambooPosts", REVIEW_POST)));
  await assertFails(getDocs(collection(b, "playReviewBambooPosts")));
  await assertFails(getDoc(doc(b, "playReviewBambooPostAuthors", REVIEW_POST)));
  await assertFails(getDoc(doc(review, "bamboo_posts", POST)));
  await assertFails(getDocs(collection(review, "bamboo_posts")));
  await assertFails(getDocs(query(collection(review, "bamboo_post_authors"), where("ownerUid", "==", REVIEWER))));
  // 심사 세션 안에서는 자기 매핑만, 좋아요는 자기 것만
  await assertSucceeds(getDoc(doc(review, "playReviewBambooPostAuthors", REVIEW_POST)));
  await assertSucceeds(getDocs(collection(review, "playReviewBambooPosts")));
  await assertFails(getDocs(collection(review, "playReviewBambooPosts", REVIEW_POST, "likes")));
  await assertFails(updateDoc(doc(review, "playReviewBambooPosts", REVIEW_POST), { isDeleted: true, updatedAt: now() }));
  await assertFails(setDoc(doc(review, "playReviewBambooPostAuthors", "x"), {
    postId: "x", ownerUid: REVIEWER, dataPartition: "play_review", createdAt: now(),
  }));
  const like = writeBatch(review);
  like.set(doc(review, "playReviewBambooPosts", REVIEW_POST, "likes", REVIEWER), {
    userId: REVIEWER, createdAt: now(), dataPartition: "play_review",
  });
  like.update(doc(review, "playReviewBambooPosts", REVIEW_POST), { likeCount: increment(1), score7d: increment(1), updatedAt: now() });
  await assertSucceeds(like.commit());
});

test("신고 숨김 목록은 본인만 읽고 아무도 직접 쓰지 못한다", async () => {
  const a = await kakaoSession(A);
  const b = await kakaoSession(B);
  await assertSucceeds(getDocs(collection(a, "users", A, "bambooHiddenContent")));
  await assertFails(getDocs(collection(b, "users", A, "bambooHiddenContent")));
  await assertFails(setDoc(doc(a, "users", A, "bambooHiddenContent", POST), { postId: POST }));
});

test("ATTACK 16: 로그아웃(미인증) 세션은 대나무숲과 매핑을 읽을 수 없다", async () => {
  const env = await getTestEnv();
  const anon = env.unauthenticatedContext().firestore();
  await assertFails(getDocs(collection(anon, "bamboo_posts")));
  await assertFails(getDoc(doc(anon, "bamboo_post_authors", POST)));
  await assertFails(getDoc(doc(anon, "bamboo_posts", POST, "likes", A)));
});

test("ATTACK 9 (전환기 레거시 문서): authorId 가 남아 있던 글에서도 commentCount/score7d 위조는 거부된다", async () => {
  // 운영의 마이그레이션 전 문서 모양. 이전 규칙은 이 문서에서 누구나 commentCount 와
  // score7d 를 함께 +1 / -1 해 인기 순위를 움직일 수 있었다.
  const env = await getTestEnv();
  await env.withSecurityRulesDisabled((ctx) =>
    setDoc(doc(ctx.firestore(), "bamboo_posts", "legacyPost"), {
      postId: "legacyPost", authorId: A, content: "legacy", category: "고민", tags: [],
      likeCount: 0, commentCount: 3, score7d: 3, isDeleted: false,
    })
  );
  const b = await kakaoSession(B);
  const post = doc(b, "bamboo_posts", "legacyPost");
  await assertFails(updateDoc(post, { commentCount: increment(1), score7d: increment(1), updatedAt: now() }));
  await assertFails(updateDoc(post, { commentCount: increment(-1), score7d: increment(-1), updatedAt: now() }));
  await assertFails(updateDoc(post, { commentCount: increment(-1), updatedAt: now() }));
});
