/**
 * P0-3 Phase 0B — 마이그레이션 동안만 배포하는 과도기 규칙의 계약.
 *
 * firestore.p03-transition.rules 는 최종 firestore.rules 에 "작성자 식별 필드가 있는
 * 대나무숲 문서는 읽을 수 없다" 는 조건만 더한 것이다 (scripts/build_p03_transition_rules.mjs
 * 가 생성). 규칙은 읽기 응답의 필드를 가릴 수 없으므로, 규칙 배포와 데이터 마이그레이션
 * 사이에 레거시 authorId 가 노출되지 않게 하는 유일한 방법이다.
 *
 * 의도된 부작용: 목록 쿼리는 이 조건을 증명할 수 없어 모두 거부된다 (피드 일시 중단).
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import test from "node:test";

import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from "@firebase/rules-unit-testing";
import {
  collection,
  collectionGroup,
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

import { buildTransitionRules } from "../scripts/build_p03_transition_rules.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const finalRules = readFileSync(resolve(here, "../firestore.rules"), "utf8");
const transitionRules = readFileSync(resolve(here, "../firestore.p03-transition.rules"), "utf8");

const A = "kakao_author_a";
const B = "kakao_attacker_b";
const REVIEWER = "play-reviewer-v1";

let env;
async function getEnv() {
  if (!env) {
    env = await initializeTestEnvironment({
      projectId: "seolleyeon-p03-transition",
      firestore: { rules: transitionRules, host: "127.0.0.1", port: 8080 },
    });
  }
  return env;
}
const session = async (uid) => (await getEnv()).authenticatedContext(uid, { kakaoUserId: uid }).firestore();
const review = async () =>
  (await getEnv())
    .authenticatedContext(REVIEWER, { appSession: true, playReviewer: true, dataPartition: "play_review" })
    .firestore();

const now = () => new Date();
const post = (extra = {}) => ({
  postId: "x", content: "c", category: "고민", tags: [], createdAt: now(), updatedAt: now(),
  likeCount: 0, commentCount: 0, score7d: 0, isDeleted: false, ...extra,
});

test.after(async () => {
  if (env) await env.cleanup();
});

test.beforeEach(async () => {
  const e = await getEnv();
  await e.clearFirestore();
  await e.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();
    await setDoc(doc(db, "bamboo_posts", "legacy"), post({ postId: "legacy", authorId: A }));
    await setDoc(doc(db, "bamboo_posts", "clean"), post({ postId: "clean" }));
    await setDoc(doc(db, "bamboo_posts", "nick"), post({ postId: "nick", nickname: "닉" }));
    await setDoc(doc(db, "bamboo_posts", "clean", "comments", "legacyC"), { commentId: "legacyC", authorId: A, content: "c", parentCommentId: null, likeCount: 0, isDeleted: false });
    await setDoc(doc(db, "bamboo_posts", "clean", "comments", "cleanC"), { commentId: "cleanC", content: "c", parentCommentId: null, likeCount: 0, isDeleted: false });
    await setDoc(doc(db, "bamboo_post_authors", "clean"), { postId: "clean", ownerUid: A });
    await setDoc(doc(db, "playReviewBambooPosts", "rvLegacy"), post({ postId: "rvLegacy", authorId: REVIEWER, dataPartition: "play_review" }));
    await setDoc(doc(db, "playReviewBambooPosts", "rvClean"), post({ postId: "rvClean", dataPartition: "play_review" }));
  });
});

test("과도기 규칙은 최종 규칙에서 생성된 그대로다 (드리프트 없음)", () => {
  assert.equal(transitionRules, buildTransitionRules(finalRules));
  // 차이는 대나무숲 읽기 4곳의 조건과 헬퍼 하나뿐이다.
  assert.equal(transitionRules.split("noPublicBambooIdentity()").length - 1, 5);
  // 목록 4곳은 닫혀 있다 (쿼리 평가에서는 문서 필드 조건이 의미가 없다).
  const lists = (src) => src.split("allow list: if false;").length;
  assert.equal(lists(transitionRules) - lists(finalRules), 4);
});

test("레거시 식별 필드가 남은 문서는 아무도 읽을 수 없다 — 작성자 본인도", async () => {
  for (const uid of [A, B]) {
    const db = await session(uid);
    await assertFails(getDoc(doc(db, "bamboo_posts", "legacy")));
    await assertFails(getDoc(doc(db, "bamboo_posts", "nick")));
    await assertFails(getDoc(doc(db, "bamboo_posts", "clean", "comments", "legacyC")));
  }
  await assertFails(getDoc(doc(await review(), "playReviewBambooPosts", "rvLegacy")));
});

test("식별 필드가 없는 문서는 get 으로 읽힌다 (새 서버 writer 의 문서)", async () => {
  const b = await session(B);
  const snap = await assertSucceeds(getDoc(doc(b, "bamboo_posts", "clean")));
  assert.equal(snap.data().authorId, undefined);
  await assertSucceeds(getDoc(doc(b, "bamboo_posts", "clean", "comments", "cleanC")));
  await assertSucceeds(getDoc(doc(await review(), "playReviewBambooPosts", "rvClean")));
});

test("의도된 제한: 과도기 동안 목록 쿼리는 거부된다 (레거시 문서를 섞어 받을 수 없음)", async () => {
  const b = await session(B);
  const probes = {
    all: () => getDocs(collection(b, "bamboo_posts")),
    feed: () => getDocs(query(collection(b, "bamboo_posts"), where("isDeleted", "==", false))),
    byAuthor: () => getDocs(query(collection(b, "bamboo_posts"), where("authorId", "==", A))),
    comments: () => getDocs(collection(b, "bamboo_posts", "clean", "comments")),
    group: () => getDocs(collectionGroup(b, "comments")),
  };
  for (const [name, run] of Object.entries(probes)) {
    let leaked = null;
    try {
      const snap = await run();
      leaked = snap.docs.map((d) => d.data()).filter((d) => "authorId" in d || "nickname" in d).length;
      console.log("TRANSITION_PROBE", name, "succeeded", snap.size, "identity-bearing", leaked);
    } catch (e) {
      console.log("TRANSITION_PROBE", name, "denied", e.code);
    }
    assert.equal(leaked, null, `${name} must be denied during the transition`);
    assert.ok(!leaked, `${name} must never return an identity-bearing document`);
  }
});

test("과도기에도 최종 경계는 그대로: 매핑·좋아요·카운터·파티션", async () => {
  const a = await session(A);
  const b = await session(B);
  await assertSucceeds(getDoc(doc(a, "bamboo_post_authors", "clean")));
  await assertFails(getDoc(doc(b, "bamboo_post_authors", "clean")));
  await assertFails(getDocs(query(collection(b, "bamboo_post_authors"), where("ownerUid", "==", A))));
  await assertFails(getDoc(doc(b, "bamboo_ownership_unresolved", "bamboo_posts__legacy")));
  await assertFails(getDocs(collection(b, "bamboo_posts", "clean", "likes")));
  await assertFails(updateDoc(doc(b, "bamboo_posts", "clean"), { commentCount: increment(1), score7d: increment(1), updatedAt: now() }));
  await assertFails(setDoc(doc(b, "bamboo_post_authors", "legacy"), { postId: "legacy", ownerUid: B }));
  await assertFails(getDoc(doc(b, "playReviewBambooPosts", "rvClean")));
  await assertFails(getDoc(doc(await review(), "bamboo_posts", "clean")));
  // 깨끗한 글의 좋아요 토글은 동작한다
  const like = writeBatch(b);
  like.set(doc(b, "bamboo_posts", "clean", "likes", B), { userId: B, createdAt: now() });
  like.update(doc(b, "bamboo_posts", "clean"), { likeCount: increment(1), score7d: increment(1), updatedAt: now() });
  await assertSucceeds(like.commit());
});
