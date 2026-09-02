/**
 * SEC-P3-01 — 대나무숲(bamboo) 카운터/score7d 무결성 규칙 테스트.
 *
 * 배경: bamboo_posts 의 likeCount/commentCount/score7d 는 클라이언트가
 * FieldValue.increment(±1) 로 쓴다. 기존에는 ±1 게이트만 있어서 로그인 사용자
 * 누구나 (a) score7d 를 단독으로 +1, (b) like 문서 없이 likeCount 를 +1,
 * (c) 이미 좋아요한 상태에서 likeCount 를 재증가 시켜 랭킹을 조작할 수 있었다.
 *
 * 수정: likeCount 변경은 요청자 like 문서(likes/{uid})의 생성/삭제 전이와
 * 묶이고(existsAfter), score7d 는 like/comment 카운터가 함께 바뀔 때만 움직인다.
 * 기존 클라 트랜잭션(togglePostLike/addComment/softDeleteComment)은 원자
 * 커밋이므로 회귀가 없다 — 아래에서 batch 로 동일 원자성을 재현해 검증한다.
 *
 * 실행:
 *   cd test/firestore_rules
 *   npx firebase emulators:exec --only firestore \
 *     --project seolleyeon-rules-test "node --test bamboo_counter_rules.test.js"
 */

const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { after, before, beforeEach, describe, it } = require("node:test");

const {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} = require("@firebase/rules-unit-testing");
const {
  doc,
  getDoc,
  setDoc,
  updateDoc,
  writeBatch,
  serverTimestamp,
  increment,
} = require("firebase/firestore");

const POST = "p1";
const AUTHOR = "author-uid-1";
const LIKER = "liker-uid-2";
const ATTACKER = "attacker-uid-3";

let testEnv;

before(async () => {
  testEnv = await initializeTestEnvironment({
    projectId: "seolleyeon-bamboo-rules-test",
    firestore: {
      rules: readFileSync(path.resolve(__dirname, "../../firestore.rules"), "utf8"),
    },
  });
});

after(async () => {
  if (testEnv) await testEnv.cleanup();
});

beforeEach(async () => {
  await testEnv.clearFirestore();
  await testEnv.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();
    await setDoc(doc(db, "bamboo_posts", POST), {
      postId: POST,
      authorId: AUTHOR,
      content: "안녕하세요 익명 글입니다",
      category: "연애",
      tags: [],
      likeCount: 0,
      commentCount: 0,
      score7d: 0,
      isDeleted: false,
      createdAt: new Date(),
      updatedAt: new Date(),
    });
  });
});

// Bamboo writes are an interactive app surface and require the canonical
// app-session claim. Using it here keeps the payload/counter assertions from
// passing early at the session gate.
const authed = (uid) =>
  testEnv
    .authenticatedContext(uid, {
      appSession: true,
      primaryAuth: "yonsei_email",
    })
    .firestore();

const postRef = (db) => doc(db, "bamboo_posts", POST);
const likeRef = (db, uid) => doc(db, "bamboo_posts", POST, "likes", uid);

async function seedLike(uid, count) {
  await testEnv.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();
    await setDoc(likeRef(db, uid), { userId: uid, createdAt: new Date() });
    await setDoc(
      postRef(db),
      { likeCount: count, score7d: count },
      { merge: true }
    );
  });
}

describe("SEC-P3-01 직접 랭킹 조작 차단", () => {
  it("score7d 를 임의 값으로 설정 불가", async () => {
    await assertFails(
      updateDoc(postRef(authed(ATTACKER)), {
        score7d: 999,
        updatedAt: serverTimestamp(),
      })
    );
  });

  it("score7d 단독 +1 (like/comment 없이) 불가", async () => {
    await assertFails(
      updateDoc(postRef(authed(ATTACKER)), {
        score7d: increment(1),
        updatedAt: serverTimestamp(),
      })
    );
  });

  it("like 문서 없이 likeCount +1 불가", async () => {
    await assertFails(
      updateDoc(postRef(authed(ATTACKER)), {
        likeCount: increment(1),
        score7d: increment(1),
        updatedAt: serverTimestamp(),
      })
    );
  });

  it("commentCount 를 임의 값으로 설정 불가 (±1 초과)", async () => {
    await assertFails(
      updateDoc(postRef(authed(ATTACKER)), {
        commentCount: 500,
        score7d: increment(1),
        updatedAt: serverTimestamp(),
      })
    );
  });

  it("게시글 작성자도 score7d 를 임의 조작할 수 없다", async () => {
    await assertFails(
      updateDoc(postRef(authed(AUTHOR)), {
        score7d: 50,
        updatedAt: serverTimestamp(),
      })
    );
  });
});

describe("SEC-P3-01 정상 좋아요 흐름 (원자 batch)", () => {
  it("좋아요: like 문서 생성 + likeCount/score7d +1 은 허용", async () => {
    const db = authed(LIKER);
    const batch = writeBatch(db);
    batch.set(likeRef(db, LIKER), { userId: LIKER, createdAt: serverTimestamp() });
    batch.update(postRef(db), {
      likeCount: increment(1),
      score7d: increment(1),
      updatedAt: serverTimestamp(),
    });
    await assertSucceeds(batch.commit());
  });

  it("이미 좋아요한 사용자가 likeCount 를 재증가(이중 증가)할 수 없다", async () => {
    await seedLike(LIKER, 1);
    // like 문서를 다시 만들지 않고 likeCount 만 +1 시도
    await assertFails(
      updateDoc(postRef(authed(LIKER)), {
        likeCount: increment(1),
        score7d: increment(1),
        updatedAt: serverTimestamp(),
      })
    );
  });

  it("좋아요 취소: like 문서 삭제 + likeCount/score7d -1 은 허용", async () => {
    await seedLike(LIKER, 1);
    const db = authed(LIKER);
    const batch = writeBatch(db);
    batch.delete(likeRef(db, LIKER));
    batch.update(postRef(db), {
      likeCount: increment(-1),
      score7d: increment(-1),
      updatedAt: serverTimestamp(),
    });
    await assertSucceeds(batch.commit());
  });

  it("like 문서를 삭제하지 않고 likeCount -1 만 시도하면 거부", async () => {
    await seedLike(LIKER, 1);
    await assertFails(
      updateDoc(postRef(authed(LIKER)), {
        likeCount: increment(-1),
        score7d: increment(-1),
        updatedAt: serverTimestamp(),
      })
    );
  });
});

describe("SEC-P3-01 댓글 카운터 흐름", () => {
  it("정상 댓글 카운터 증가(commentCount/score7d +1)는 허용", async () => {
    await assertSucceeds(
      updateDoc(postRef(authed(LIKER)), {
        commentCount: increment(1),
        score7d: increment(1),
        updatedAt: serverTimestamp(),
      })
    );
  });

  it("댓글 소프트삭제 카운터 감소(commentCount -1, score7d 불변)는 허용", async () => {
    await testEnv.withSecurityRulesDisabled(async (ctx) => {
      await setDoc(
        postRef(ctx.firestore()),
        { commentCount: 1, score7d: 1 },
        { merge: true }
      );
    });
    await assertSucceeds(
      updateDoc(postRef(authed(LIKER)), {
        commentCount: increment(-1),
        updatedAt: serverTimestamp(),
      })
    );
  });
});

describe("SEC-P3-01 소프트삭제/작성 권한 회귀 확인", () => {
  it("작성자는 자신의 글을 소프트삭제할 수 있다", async () => {
    await assertSucceeds(
      updateDoc(postRef(authed(AUTHOR)), {
        isDeleted: true,
        updatedAt: serverTimestamp(),
      })
    );
  });

  it("타인은 작성자 글을 소프트삭제할 수 없다", async () => {
    await assertFails(
      updateDoc(postRef(authed(ATTACKER)), {
        isDeleted: true,
        updatedAt: serverTimestamp(),
      })
    );
  });

  it("정상 글 작성(authorId==self, 카운터 0)은 허용", async () => {
    await assertSucceeds(
      setDoc(doc(authed(LIKER), "bamboo_posts", "p2"), {
        postId: "p2",
        authorId: LIKER,
        content: "새 글",
        category: "일상",
        tags: [],
        likeCount: 0,
        commentCount: 0,
        score7d: 0,
        isDeleted: false,
        createdAt: serverTimestamp(),
        updatedAt: serverTimestamp(),
      })
    );
  });

  it("authorId 를 위조한 글 작성은 거부", async () => {
    await assertFails(
      setDoc(doc(authed(LIKER), "bamboo_posts", "p3"), {
        postId: "p3",
        authorId: ATTACKER,
        content: "위조",
        category: "일상",
        tags: [],
        likeCount: 0,
        commentCount: 0,
        score7d: 0,
        isDeleted: false,
        createdAt: serverTimestamp(),
        updatedAt: serverTimestamp(),
      })
    );
  });
});
