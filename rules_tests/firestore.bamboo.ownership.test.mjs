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
  query,
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

test("새 글과 매핑을 한 배치로 쓰는 것은 허용", async () => {
  await seedOwnerContent();
  const owner = await kakaoSession(OWNER);
  const newPost = "post2";
  const batch = writeBatch(owner);
  batch.set(doc(owner, "bamboo_posts", newPost), postBody(newPost, OWNER));
  batch.set(doc(owner, POST_MAP, newPost), {
    postId: newPost,
    ownerUid: OWNER,
  });
  await assertSucceeds(batch.commit());
});

test("글은 A 로, 매핑은 B 로 쓰는 배치는 거부", async () => {
  await seedOwnerContent();
  const stranger = await kakaoSession(STRANGER);

  // 게시글 규칙만 놓고 보면 이 쓰기는 통과한다. 아래 배치가 막히는 이유가
  // "STRANGER 는 글을 못 쓴다" 가 아니라 매핑 가드임을 여기서 못박는다.
  await assertSucceeds(
    setDoc(
      doc(stranger, "bamboo_posts", "post3-control"),
      postBody("post3-control", STRANGER)
    )
  );

  const newPost = "post3";
  const batch = writeBatch(stranger);
  batch.set(
    doc(stranger, "bamboo_posts", newPost),
    postBody(newPost, STRANGER)
  );
  batch.set(doc(stranger, POST_MAP, newPost), {
    postId: newPost,
    ownerUid: OWNER,
  });
  await assertFails(batch.commit());
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

test("Phase A: 구버전 클라처럼 매핑 없이 글만 써도 아직 허용된다", async () => {
  await seedOwnerContent();
  const owner = await kakaoSession(OWNER);
  await assertSucceeds(
    setDoc(
      doc(owner, "bamboo_posts", "legacy-post"),
      postBody("legacy-post", OWNER)
    )
  );
});
