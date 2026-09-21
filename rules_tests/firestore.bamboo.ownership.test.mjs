/**
 * SEC-04 — 대나무숲 비공개 소유권 매핑 규칙 (Phase A).
 *
 * public `bamboo_posts/{postId}` 와 그 하위 comments 는 raw authorId(UID)를 담고
 * 있고 로그인 사용자면 누구나 읽을 수 있다. `publicProfiles/{uid}` 도 get 이
 * 열려 있어 authorId → 프로필 join 으로 "익명 보장" 글의 작성자를 특정할 수
 * 있다. 규칙은 read 응답의 개별 필드를 가릴 수 없으므로 최종적으로는 public
 * 문서에서 authorId 를 물리적으로 제거해야 한다.
 *
 * Phase A 는 그 전 단계다. 비공개 매핑을 신설하되 public authorId 는 그대로
 * 둬서 구버전 클라이언트가 계속 동작하게 한다. 이 단계에서 익명성은 아직
 * 확보되지 않는다 — 전환 인프라만 준비된다.
 *
 * 여기서 막아야 하는 핵심 공격은 남의 글에 자기 소유권 매핑을 붙이는 것이다.
 * 매핑 생성은 요청자가 그 public 문서의 작성자일 때만 허용한다.
 */
import test from "node:test";

import {
  assertFails,
  assertSucceeds,
  getTestEnv,
  kakaoSession,
  withClearedDb,
} from "./helpers.mjs";

import {
  collection,
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  increment,
  query,
  runTransaction,
  setDoc,
  updateDoc,
  where,
  writeBatch,
} from "firebase/firestore";

const OWNER = "kakao_owner";
const STRANGER = "kakao_stranger";

const POST = "post1";
const COMMENT = "comment1";

const POST_MAP = "bamboo_post_authors";
const COMMENT_MAP = "bamboo_comment_authors";

const commentMapId = (postId, commentId) => `${postId}__${commentId}`;

function postBody(postId, authorId) {
  return {
    postId,
    authorId,
    content: "익명으로 남기는 글",
    category: "free",
    tags: [],
    likeCount: 0,
    commentCount: 0,
    score7d: 0,
    isDeleted: false,
  };
}

/** Phase A 기준의 레거시 문서: public 에 authorId 가 아직 남아 있다. */
async function seedOwnerContent() {
  await withClearedDb(async (db) => {
    await setDoc(doc(db, "bamboo_posts", POST), postBody(POST, OWNER));
    await setDoc(doc(db, "bamboo_posts", POST, "comments", COMMENT), {
      commentId: COMMENT,
      authorId: OWNER,
      content: "익명 댓글",
      parentCommentId: null,
      likeCount: 0,
      isDeleted: false,
    });
  });
}

async function seedPostMapping(ownerUid) {
  const env = await getTestEnv();
  await env.withSecurityRulesDisabled((ctx) =>
    setDoc(doc(ctx.firestore(), POST_MAP, POST), {
      postId: POST,
      ownerUid,
    })
  );
}

test.after(async () => {
  const env = await getTestEnv();
  await env.cleanup();
});

test("작성자는 자기 글의 매핑을 만들 수 있다", async () => {
  await seedOwnerContent();
  const owner = await kakaoSession(OWNER);
  await assertSucceeds(
    setDoc(doc(owner, POST_MAP, POST), { postId: POST, ownerUid: OWNER })
  );
});

test("남의 글을 자기 소유로 주장할 수 없다", async () => {
  await seedOwnerContent();
  const stranger = await kakaoSession(STRANGER);
  await assertFails(
    setDoc(doc(stranger, POST_MAP, POST), { postId: POST, ownerUid: STRANGER })
  );
});

test("타인 UID 를 ownerUid 로 심을 수 없다", async () => {
  await seedOwnerContent();
  const owner = await kakaoSession(OWNER);
  await assertFails(
    setDoc(doc(owner, POST_MAP, POST), { postId: POST, ownerUid: STRANGER })
  );
});

test("postId 필드가 문서 id 와 다르면 거부", async () => {
  await seedOwnerContent();
  const owner = await kakaoSession(OWNER);
  await assertFails(
    setDoc(doc(owner, POST_MAP, POST), {
      postId: "other-post",
      ownerUid: OWNER,
    })
  );
});

test("클라이언트가 새 글과 매핑을 한 배치로 직접 쓰는 것은 서버 전용 create 때문에 거부된다", async () => {
  await seedOwnerContent();
  const owner = await kakaoSession(OWNER);
  const newPost = "post2";
  const batch = writeBatch(owner);
  batch.set(doc(owner, "bamboo_posts", newPost), postBody(newPost, OWNER));
  batch.set(doc(owner, POST_MAP, newPost), {
    postId: newPost,
    ownerUid: OWNER,
  });
  await assertFails(batch.commit());
});

test("A 소유 글에 B가 소유권 매핑을 붙이는 쓰기는 거부", async () => {
  await seedOwnerContent();
  const env = await getTestEnv();
  await env.withSecurityRulesDisabled((ctx) =>
    setDoc(
      doc(ctx.firestore(), "bamboo_posts", "post3"),
      postBody("post3", OWNER)
    )
  );
  const stranger = await kakaoSession(STRANGER);

  // The post is server-seeded so this assertion reaches the ownership-mapping
  // guard instead of being masked by the server-only post create rule.
  await assertFails(
    setDoc(doc(stranger, POST_MAP, "post3"), {
      postId: "post3",
      ownerUid: STRANGER,
    })
  );
});

test("ownerUid 는 바꿀 수 없다", async () => {
  await seedOwnerContent();
  await seedPostMapping(OWNER);
  const owner = await kakaoSession(OWNER);
  await assertFails(
    updateDoc(doc(owner, POST_MAP, POST), { ownerUid: STRANGER })
  );
});

test("소유자도 매핑을 지울 수 없다 (계정삭제는 서버 경로)", async () => {
  await seedOwnerContent();
  await seedPostMapping(OWNER);
  const owner = await kakaoSession(OWNER);
  await assertFails(deleteDoc(doc(owner, POST_MAP, POST)));
});

test("소유자는 자기 매핑을 읽을 수 있다", async () => {
  await seedOwnerContent();
  await seedPostMapping(OWNER);
  const owner = await kakaoSession(OWNER);
  await assertSucceeds(getDoc(doc(owner, POST_MAP, POST)));
});

test("타인은 매핑을 읽을 수 없다 — 익명성의 핵심", async () => {
  await seedOwnerContent();
  await seedPostMapping(OWNER);
  const stranger = await kakaoSession(STRANGER);
  await assertFails(getDoc(doc(stranger, POST_MAP, POST)));
});

test("본인 조건 쿼리는 허용 (내가 쓴 글)", async () => {
  await seedOwnerContent();
  await seedPostMapping(OWNER);
  const owner = await kakaoSession(OWNER);
  await assertSucceeds(
    getDocs(query(collection(owner, POST_MAP), where("ownerUid", "==", OWNER)))
  );
});

test("전체 목록 조회는 거부", async () => {
  await seedOwnerContent();
  await seedPostMapping(OWNER);
  const stranger = await kakaoSession(STRANGER);
  await assertFails(getDocs(collection(stranger, POST_MAP)));
});

test("타인 UID 로 거는 쿼리는 거부", async () => {
  await seedOwnerContent();
  await seedPostMapping(OWNER);
  const stranger = await kakaoSession(STRANGER);
  await assertFails(
    getDocs(
      query(collection(stranger, POST_MAP), where("ownerUid", "==", OWNER))
    )
  );
});

test("작성자는 자기 댓글의 매핑을 만들 수 있다", async () => {
  await seedOwnerContent();
  const owner = await kakaoSession(OWNER);
  await assertSucceeds(
    setDoc(doc(owner, COMMENT_MAP, commentMapId(POST, COMMENT)), {
      postId: POST,
      commentId: COMMENT,
      ownerUid: OWNER,
    })
  );
});

test("남의 댓글을 자기 소유로 주장할 수 없다", async () => {
  await seedOwnerContent();
  const stranger = await kakaoSession(STRANGER);
  await assertFails(
    setDoc(doc(stranger, COMMENT_MAP, commentMapId(POST, COMMENT)), {
      postId: POST,
      commentId: COMMENT,
      ownerUid: STRANGER,
    })
  );
});

test("문서 id 가 postId__commentId 와 다르면 거부", async () => {
  await seedOwnerContent();
  const owner = await kakaoSession(OWNER);
  await assertFails(
    setDoc(doc(owner, COMMENT_MAP, "mismatched-id"), {
      postId: POST,
      commentId: COMMENT,
      ownerUid: OWNER,
    })
  );
});

test("타인은 댓글 매핑을 읽을 수 없다", async () => {
  await seedOwnerContent();
  const env = await getTestEnv();
  await env.withSecurityRulesDisabled((ctx) =>
    setDoc(doc(ctx.firestore(), COMMENT_MAP, commentMapId(POST, COMMENT)), {
      postId: POST,
      commentId: COMMENT,
      ownerUid: OWNER,
    })
  );
  const stranger = await kakaoSession(STRANGER);
  await assertFails(
    getDoc(doc(stranger, COMMENT_MAP, commentMapId(POST, COMMENT)))
  );
});

test("구버전 클라이언트의 매핑 없는 직접 글 쓰기는 현재 서버 전용 경로로 거부된다", async () => {
  await seedOwnerContent();
  const owner = await kakaoSession(OWNER);
  await assertFails(
    setDoc(
      doc(owner, "bamboo_posts", "legacy-post"),
      postBody("legacy-post", OWNER)
    )
  );
});

test("댓글과 매핑을 직접 쓰는 클라이언트 트랜잭션은 서버 전용 create 때문에 거부된다", async () => {
  // The production client uses createCommunityComment. A direct Firestore
  // transaction must not bypass that moderated server path.
  await seedOwnerContent();
  const owner = await kakaoSession(OWNER);
  const newComment = "comment2";

  await assertFails(
    runTransaction(owner, async (tx) => {
      const postRef = doc(owner, "bamboo_posts", POST);
      await tx.get(postRef);
      tx.set(doc(postRef, "comments", newComment), {
        commentId: newComment,
        authorId: OWNER,
        content: "익명 댓글",
        parentCommentId: null,
        likeCount: 0,
        isDeleted: false,
      });
      tx.set(doc(owner, COMMENT_MAP, commentMapId(POST, newComment)), {
        postId: POST,
        commentId: newComment,
        ownerUid: OWNER,
      });
      tx.update(postRef, {
        commentCount: increment(1),
        score7d: increment(1),
      });
    })
  );
});
