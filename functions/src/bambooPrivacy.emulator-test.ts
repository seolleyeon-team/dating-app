/**
 * P0-3 — 대나무숲 익명성: 서버 writer · 소유 판정 · 알림 · 신고 · 계정삭제를 실제
 * 배포 핸들러(`.run`)로 고정한다 (Firestore Emulator).
 *
 *   A = 글 작성자, B = 댓글 작성자/공격자, C = 답글 작성자
 *
 * 실행 (repo root, JDK 21):
 *   ./functions/node_modules/.bin/tsc -p functions --outDir functions/.p03-lib
 *   firebase emulators:exec --only firestore --project demo-p03-bamboo \
 *     "node --test functions/.p03-lib/bambooPrivacy.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getFirestore, Timestamp } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

// index.ts performs initializeApp(); only import here.
import {
  createCommunityComment,
  createCommunityPost,
  deleteCommunityComment,
  deleteCommunityPost,
  onBambooCommentCreated,
  onBambooPostLikeCreated,
  reportAndBlockUser,
  reportBambooContent,
} from "./index";
import { createInAppNotification } from "./shared/notify";
import { executeAccountDeletionSocialCleanup } from "./accountDeletionSocialCleanup";
import { BAMBOO_PUBLIC_IDENTITY_FIELDS } from "./bambooOwnership";

type Runnable = { run: (request: unknown) => Promise<unknown> };
const db = getFirestore();
let seq = 0;
const fresh = (p: string) => `${p}_${Date.now().toString(36)}_${++seq}`;

async function seedUser(uid: string, nickname: string) {
  await db.collection("users").doc(uid).set({
    kakaoUserId: uid,
    isStudentVerified: true,
    studentEmail: `${uid}@yonsei.ac.kr`,
    nickname,
    onboarding: { nickname },
    isActive: true,
  });
}

function call<T = Record<string, unknown>>(fn: unknown, uid: string, data: Record<string, unknown>): Promise<T> {
  return (fn as Runnable).run({ data, auth: { uid, token: {} }, rawRequest: {} }) as Promise<T>;
}

async function expectCode(promise: Promise<unknown>, code: string) {
  await assert.rejects(promise, (err: unknown) => {
    assert.equal((err as { code?: string }).code, code);
    return true;
  });
}

async function runCommentTrigger(postId: string, commentId: string) {
  const snap = await db.collection("bamboo_posts").doc(postId).collection("comments").doc(commentId).get();
  await (onBambooCommentCreated as unknown as Runnable).run({
    data: snap, params: { postId, commentId }, id: `evt_${commentId}`, time: new Date().toISOString(),
  });
}

async function runLikeTrigger(postId: string, userId: string) {
  const ref = db.collection("bamboo_posts").doc(postId).collection("likes").doc(userId);
  await ref.set({ userId, createdAt: Timestamp.now() });
  await (onBambooPostLikeCreated as unknown as Runnable).run({
    data: await ref.get(), params: { postId, userId }, id: `evt_like_${postId}_${userId}`, time: new Date().toISOString(),
  });
}

async function notificationsOf(uid: string) {
  return (await db.collection("users").doc(uid).collection("notifications").get()).docs.map((d) => d.data());
}

function assertNoIdentity(value: Record<string, unknown>, uids: string[], nicknames: string[], label: string) {
  const json = JSON.stringify(value);
  for (const uid of uids) assert.ok(!json.includes(uid), `${label} must not contain uid ${uid}`);
  for (const nick of nicknames) assert.ok(!json.includes(nick), `${label} must not contain nickname ${nick}`);
}

async function scenario() {
  const A = fresh("ua"), B = fresh("ub"), C = fresh("uc");
  const nick = { A: `닉A${seq}`, B: `닉B${seq}`, C: `닉C${seq}` };
  await seedUser(A, nick.A);
  await seedUser(B, nick.B);
  await seedUser(C, nick.C);
  return { A, B, C, nick };
}

test("writers: public 글/댓글에 작성자 필드가 없고, 매핑은 같은 커밋에 생긴다", async () => {
  const { A, B, nick } = await scenario();
  const { postId } = await call<{ postId: string }>(createCommunityPost, A, { content: "익명 글", category: "고민", tags: ["t"] });
  const post = (await db.collection("bamboo_posts").doc(postId).get()).data() ?? {};
  for (const field of BAMBOO_PUBLIC_IDENTITY_FIELDS) assert.ok(!(field in post), `post.${field}`);
  assertNoIdentity(post, [A], [nick.A], "public post");
  assert.equal((await db.collection("bamboo_post_authors").doc(postId).get()).data()?.ownerUid, A);

  const { commentId } = await call<{ commentId: string }>(createCommunityComment, B, { postId, content: "댓글" });
  const comment = (await db.collection("bamboo_posts").doc(postId).collection("comments").doc(commentId).get()).data() ?? {};
  for (const field of BAMBOO_PUBLIC_IDENTITY_FIELDS) assert.ok(!(field in comment), `comment.${field}`);
  assertNoIdentity(comment, [B], [nick.B], "public comment");
  assert.equal((await db.collection("bamboo_comment_authors").doc(`${postId}__${commentId}`).get()).data()?.ownerUid, B);
  assert.equal((await db.collection("bamboo_posts").doc(postId).get()).data()?.commentCount, 1);
});

test("ATTACK 4: 댓글·답글·좋아요 알림은 행위자의 UID 와 닉네임을 담지 않는다", async () => {
  const { A, B, C, nick } = await scenario();
  const { postId } = await call<{ postId: string }>(createCommunityPost, A, { content: "글", category: "일상", tags: [] });
  const { commentId } = await call<{ commentId: string }>(createCommunityComment, B, { postId, content: "B 댓글" });
  await runCommentTrigger(postId, commentId);
  await runCommentTrigger(postId, commentId); // 재전달 — 중복 알림 없음
  const { commentId: replyId } = await call<{ commentId: string }>(createCommunityComment, C, { postId, content: "C 답글", parentCommentId: commentId });
  await runCommentTrigger(postId, replyId);
  await runLikeTrigger(postId, B);

  const forA = await notificationsOf(A);
  assert.deepEqual(forA.map((n) => n.type).sort(), ["community_comment", "community_post_like"]);
  for (const n of forA) {
    assert.equal(n.actorId, null);
    assert.equal(n.actorName, "익명");
    assertNoIdentity(n, [B, C], [nick.B, nick.C], `A notification ${n.type}`);
  }
  const forB = await notificationsOf(B);
  assert.deepEqual(forB.map((n) => n.type), ["community_reply"]);
  assert.equal(forB[0].actorId, null);
  assertNoIdentity(forB[0], [C, A], [nick.C, nick.A], "B reply notification");
  // 운영 dispatch 로그는 받는 사람만 담는다 — 행위자(그 알림을 일으킨 사람)는 없다.
  const logs = (await db.collection("notificationDispatchLog").get()).docs
    .map((d) => d.data())
    .filter((d) => JSON.stringify(d).includes(postId));
  assert.ok(logs.length >= 2);
  for (const log of logs) {
    const recipients = (log.userIds as string[]) ?? [];
    const actors = [B, C].filter((uid) => !recipients.includes(uid));
    assertNoIdentity(log, actors, [nick.B, nick.C], "dispatch log");
  }
});

test("자기 알림 억제: 내 글에 내가 댓글·좋아요 → 알림 없음", async () => {
  const { A } = await scenario();
  const { postId } = await call<{ postId: string }>(createCommunityPost, A, { content: "글", category: "질문", tags: [] });
  const { commentId } = await call<{ commentId: string }>(createCommunityComment, A, { postId, content: "내 댓글" });
  await runCommentTrigger(postId, commentId);
  await runLikeTrigger(postId, A);
  assert.equal((await notificationsOf(A)).length, 0);
});

test("ATTACK 15: 매핑이 없거나 깨진 글은 아무에게도 알리지 않고 아무 권한도 주지 않는다 (fail closed)", async () => {
  const { A, B } = await scenario();
  // 마이그레이션 전 레거시 문서: public authorId 만 있고 매핑이 없다.
  const legacy = fresh("legacy");
  await db.collection("bamboo_posts").doc(legacy).set({
    postId: legacy, authorId: A, content: "legacy", category: "고민", tags: [],
    likeCount: 0, commentCount: 0, score7d: 0, isDeleted: false, createdAt: Timestamp.now(), updatedAt: Timestamp.now(),
  });
  const { commentId } = await call<{ commentId: string }>(createCommunityComment, B, { postId: legacy, content: "댓글" });
  await runCommentTrigger(legacy, commentId);
  await runLikeTrigger(legacy, B);
  assert.equal((await notificationsOf(A)).length, 0, "no fallback to public authorId");
  await expectCode(call(deleteCommunityPost, A, { postId: legacy }), "permission-denied");

  // ownerUid 가 빈 매핑
  const broken = fresh("broken");
  await db.collection("bamboo_posts").doc(broken).set({
    postId: broken, content: "x", category: "고민", tags: [], likeCount: 0, commentCount: 0, score7d: 0, isDeleted: false,
  });
  await db.collection("bamboo_post_authors").doc(broken).set({ postId: broken, ownerUid: "" });
  await expectCode(call(deleteCommunityPost, A, { postId: broken }), "permission-denied");
  // 다른 글을 가리키는 매핑
  await db.collection("bamboo_post_authors").doc(broken).set({ postId: "someOtherPost", ownerUid: A });
  await expectCode(call(deleteCommunityPost, A, { postId: broken }), "permission-denied");
  assert.equal((await db.collection("bamboo_posts").doc(broken).get()).data()?.isDeleted, false);
});

test("ATTACK 8: 남의 글·댓글 삭제는 거부, 본인 삭제는 동작하고 멱등이며 카운터가 한 번만 움직인다", async () => {
  const { A, B } = await scenario();
  const { postId } = await call<{ postId: string }>(createCommunityPost, A, { content: "글", category: "설렘", tags: [] });
  const { commentId } = await call<{ commentId: string }>(createCommunityComment, B, { postId, content: "댓글" });

  await expectCode(call(deleteCommunityComment, A, { postId, commentId }), "permission-denied");
  await expectCode(call(deleteCommunityPost, B, { postId }), "permission-denied");
  // 소유자가 아닌 경우와 매핑 없는 경우의 응답이 같다 (오라클 없음)
  await expectCode(call(deleteCommunityComment, A, { postId, commentId: "doesNotExistButPostDoes" }), "not-found");

  await call(deleteCommunityComment, B, { postId, commentId });
  await call(deleteCommunityComment, B, { postId, commentId });
  const post = (await db.collection("bamboo_posts").doc(postId).get()).data() ?? {};
  assert.equal(post.commentCount, 0, "decremented exactly once");
  assert.equal((await db.collection("bamboo_posts").doc(postId).collection("comments").doc(commentId).get()).data()?.isDeleted, true);

  await call(deleteCommunityPost, A, { postId });
  await call(deleteCommunityPost, A, { postId });
  assert.equal((await db.collection("bamboo_posts").doc(postId).get()).data()?.isDeleted, true);
  // 매핑은 그대로 — 삭제된 글도 여전히 A 의 것으로 남는다
  assert.equal((await db.collection("bamboo_post_authors").doc(postId).get()).data()?.ownerUid, A);
});

test("신고: 작성자는 서버 신고 문서에만 남고, 신고자에게는 콘텐츠 id 만 숨김으로 돌아간다 (실명 차단 문서 없음)", async () => {
  const { A, B, nick } = await scenario();
  const { postId } = await call<{ postId: string }>(createCommunityPost, A, { content: "글", category: "고민", tags: [] });
  const { commentId } = await call<{ commentId: string }>(createCommunityComment, A, { postId, content: "A 의 댓글" });

  const result = await call(reportBambooContent, B, { contentType: "bamboo_post", postId, reason: "스팸·광고" });
  assertNoIdentity(result, [A], [nick.A], "report response");
  await call(reportBambooContent, B, { contentType: "bamboo_post", postId, reason: "스팸·광고" });
  await call(reportBambooContent, B, { contentType: "bamboo_comment", postId, commentId, reason: "기타" });

  const reports = (await db.collection("reports").where("reporterId", "==", B).get()).docs.map((d) => d.data());
  assert.equal(reports.length, 2, "one report per reporter per content");
  for (const r of reports) {
    assert.equal(r.reportedId, A, "moderation still knows the author (server-only collection)");
    assert.equal(r.ownershipStatus, "mapped");
  }
  const hidden = (await db.collection("users").doc(B).collection("bambooHiddenContent").get()).docs;
  assert.deepEqual(hidden.map((d) => d.id).sort(), [postId, `${postId}__${commentId}`].sort());
  for (const h of hidden) assertNoIdentity(h.data(), [A], [nick.A], "hidden entry");
  // 실명 차단 문서가 어느 방향으로도 생기지 않는다
  assert.equal((await db.collection("blocks").doc(B).collection("targets").get()).size, 0);
  assert.equal((await db.collection("blocks").doc(A).collection("targets").get()).size, 0);
  // 자기 글 신고는 거부
  await expectCode(call(reportBambooContent, A, { contentType: "bamboo_post", postId, reason: "기타" }), "failed-precondition");
});

test("ATTACK 19 (신고 경로): reportAndBlockUser 로 대나무숲 작성자 추측을 시험할 수 없다", async () => {
  const { A, B } = await scenario();
  const { postId } = await call<{ postId: string }>(createCommunityPost, A, { content: "글", category: "고민", tags: [] });
  for (const guess of [A, B, "nobody_at_all"]) {
    await expectCode(
      call(reportAndBlockUser, B, { reportedUserId: guess, reason: "spam", source: "bamboo_post", contentType: "bamboo_post", contentId: postId }),
      "failed-precondition"
    );
  }
  assert.equal((await db.collection("blocks").doc(B).collection("targets").get()).size, 0);
});

test("ATTACK 17: 공용 알림 writer 는 대나무숲 알림에 행위자를 되살리지 않는다", async () => {
  const target = fresh("ut");
  await createInAppNotification(target, {
    type: "community_comment", title: "t", body: "b", deeplinkType: "community_post",
    actorId: "leaked_uid", actorName: "실명닉네임",
  }, fresh("n"));
  await createInAppNotification(target, {
    type: "profile_like", title: "t", body: "b", deeplinkType: "received_like",
    actorId: "profile_actor", actorName: "프로필닉네임",
  }, fresh("n"));
  const docs = await notificationsOf(target);
  const bamboo = docs.find((d) => d.type === "community_comment")!;
  assert.equal(bamboo.actorId, null);
  assert.equal(bamboo.actorName, "익명");
  const other = docs.find((d) => d.type === "profile_like")!;
  assert.equal(other.actorId, "profile_actor", "non-bamboo notifications are unchanged");
});

test("계정삭제: 글·댓글 soft delete 가 레거시 authorId 를 지우고 소유권 매핑도 지운다", async () => {
  const { A, B } = await scenario();
  const { postId } = await call<{ postId: string }>(createCommunityPost, A, { content: "글", category: "고민", tags: [] });
  const { commentId } = await call<{ commentId: string }>(createCommunityComment, A, { postId, content: "댓글" });
  // 마이그레이션 전 상태를 흉내 내어 legacy authorId 를 남겨 둔다.
  await db.collection("bamboo_posts").doc(postId).set({ authorId: A }, { merge: true });
  await call(createCommunityComment, B, { postId, content: "B" });

  await executeAccountDeletionSocialCleanup(db, A);
  const post = (await db.collection("bamboo_posts").doc(postId).get()).data() ?? {};
  assert.equal(post.isDeleted, true);
  assert.ok(!("authorId" in post));
  assert.equal((await db.collection("bamboo_posts").doc(postId).collection("comments").doc(commentId).get()).data()?.isDeleted, true);
  assert.equal((await db.collection("bamboo_post_authors").doc(postId).get()).exists, false);
  assert.equal((await db.collection("bamboo_comment_authors").doc(`${postId}__${commentId}`).get()).exists, false);
});
