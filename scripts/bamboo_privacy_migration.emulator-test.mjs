/**
 * P0-3 마이그레이션 — 레거시 데이터를 심고 실제로 돌린다 (Firestore Emulator).
 *
 *   firebase emulators:exec --only firestore,auth --project demo-p03-migration \
 *     "node --test scripts/bamboo_privacy_migration.emulator-test.mjs"
 */
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import { main, verify } from "./bamboo_privacy_migration.mjs";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}
const PROJECT = "demo-p03-migration";
const require = createRequire(import.meta.url);
const admin = require("../functions/node_modules/firebase-admin");
if (admin.apps.length === 0) admin.initializeApp({ projectId: PROJECT });
const db = admin.firestore();
const ENV = { FIRESTORE_EMULATOR_HOST: process.env.FIRESTORE_EMULATOR_HOST };

async function clear() {
  const res = await fetch(
    `http://${process.env.FIRESTORE_EMULATOR_HOST}/emulator/v1/projects/${PROJECT}/databases/(default)/documents`,
    { method: "DELETE" }
  );
  assert.ok(res.ok);
}

const ts = (ms) => admin.firestore.Timestamp.fromMillis(ms);

/** 운영 모양의 레거시 데이터: public authorId, 매핑은 일부만. */
async function seedLegacy() {
  await clear();
  for (const uid of ["alice", "bob", "carol"]) await db.collection("users").doc(uid).set({ nickname: uid });
  const post = (id, authorId, extra = {}) => db.collection("bamboo_posts").doc(id).set({
    postId: id, authorId, content: id, category: "고민", tags: [], likeCount: 0, commentCount: 0,
    score7d: 0, isDeleted: false, createdAt: ts(1_700_000_000_000), updatedAt: ts(1_700_000_000_000), ...extra,
  });
  await post("mapped", "alice");
  await db.collection("bamboo_post_authors").doc("mapped").set({ postId: "mapped", ownerUid: "alice" });
  await post("unmapped", "bob");
  await post("conflict", "alice");
  await db.collection("bamboo_post_authors").doc("conflict").set({ postId: "conflict", ownerUid: "carol" });
  await post("ghost", "deleted_account");
  // 초기 Kakao 커스텀 토큰 계정: Auth 계정만 있고 users 문서가 없다.
  await admin.auth().deleteUser("1234567890").catch(() => {});
  await admin.auth().createUser({ uid: "1234567890" });
  await post("authonly", "1234567890");
  await db.collection("bamboo_posts").doc("mapped").collection("comments").doc("c1").set({
    commentId: "c1", authorId: "bob", content: "c", parentCommentId: null, likeCount: 0, isDeleted: false,
  });
  await db.collection("bamboo_posts").doc("mapped").collection("likes").doc("carol").set({ userId: "carol" });
  await db.collection("playReviewBambooPosts").doc("rv").set({
    postId: "rv", authorId: "play-reviewer-v1", content: "r", dataPartition: "play_review", isDeleted: false,
  });
  await db.collection("playReviewBambooPostAuthors").doc("rv").set({ postId: "rv", ownerUid: "play-reviewer-v1", dataPartition: "play_review" });
  await db.collection("users").doc("alice").collection("notifications").doc("n1").set({
    type: "community_comment", actorId: "bob", actorName: "bob", postId: "mapped",
  });
  await db.collection("users").doc("alice").collection("notifications").doc("n2").set({
    type: "profile_like", actorId: "carol", actorName: "carol",
  });
}

const data = async (path) => (await db.doc(path).get()).data();

test("ATTACK 12: dry-run 은 아무것도 쓰지 않는다", async () => {
  await seedLegacy();
  const code = await main(["--project", PROJECT], ENV);
  assert.equal(code, 2, "conflict/unverifiable records are reported");
  assert.equal((await data("bamboo_posts/unmapped")).authorId, "bob");
  assert.equal((await db.doc("bamboo_post_authors/unmapped").get()).exists, false);
  assert.equal((await data("users/alice/notifications/n1")).actorId, "bob");
});

test("ATTACK 12: apply 는 검증된 레코드만 지우고 매핑을 보존·생성하며, 충돌·미확인은 멈춘다", async () => {
  await seedLegacy();
  const dir = mkdtempSync(join(tmpdir(), "p03-"));
  const anomalies = join(dir, "anomalies.txt");
  const checkpoint = join(dir, "checkpoint.json");
  const code = await main(["--project", PROJECT, "--apply", "--checkpoint", checkpoint, "--anomaly-ids-out", anomalies], ENV);
  assert.equal(code, 2);

  for (const path of ["bamboo_posts/mapped", "bamboo_posts/unmapped", "bamboo_posts/mapped/comments/c1", "playReviewBambooPosts/rv"]) {
    assert.ok(!("authorId" in (await data(path))), `${path} redacted`);
  }
  assert.equal((await data("bamboo_post_authors/unmapped")).ownerUid, "bob");
  assert.equal((await data("bamboo_post_authors/unmapped")).createdAt.toMillis(), 1_700_000_000_000, "mapping keeps the post time");
  assert.equal((await data("bamboo_comment_authors/mapped__c1")).ownerUid, "bob");
  assert.ok(!("authorId" in (await data("bamboo_posts/authonly"))));
  assert.equal((await data("bamboo_post_authors/authonly")).ownerUid, "1234567890", "auth-only legacy account keeps ownership");
  assert.equal((await data("bamboo_post_authors/mapped")).ownerUid, "alice", "existing mapping untouched");
  // 충돌·미확인 레코드는 그대로 (사람이 판단)
  assert.equal((await data("bamboo_posts/conflict")).authorId, "alice");
  assert.equal((await data("bamboo_post_authors/conflict")).ownerUid, "carol");
  assert.equal((await data("bamboo_posts/ghost")).authorId, "deleted_account");
  assert.equal((await db.doc("bamboo_post_authors/ghost").get()).exists, false);
  // 알림: 대나무숲만 익명화
  const n1 = await data("users/alice/notifications/n1");
  assert.deepEqual([n1.actorId, n1.actorName], [null, "익명"]);
  assert.equal((await data("users/alice/notifications/n2")).actorId, "carol");
  // 좋아요 문서는 바꾸지 않는다
  assert.equal((await data("bamboo_posts/mapped/likes/carol")).userId, "carol");
  // 이상 보고는 경로만, UID 없음
  const report = readFileSync(anomalies, "utf8");
  assert.match(report, /MAPPING_CONFLICT bamboo_posts\/conflict/);
  assert.match(report, /UNVERIFIABLE bamboo_posts\/ghost/);
  for (const uid of ["alice", "carol", "deleted_account", "1234567890"]) assert.ok(!report.includes(uid));
  assert.ok(!readFileSync(checkpoint, "utf8").includes("alice"));

  const v = await verify(db, admin);
  assert.equal(v.publicPostsWithIdentity, 2, "conflict + ghost remain until a human decides");
  assert.equal(v.mappingConflicts, 1);
  assert.equal(v.identifyingBambooNotifications, 0);
});

test("멱등: 다시 돌려도 쓰기가 없고, 충돌을 해소하면 마저 끝나며 verify 가 0 이 된다", async () => {
  await seedLegacy();
  await main(["--project", PROJECT, "--apply"], ENV);
  const before = await data("bamboo_posts/mapped");
  await main(["--project", PROJECT, "--apply"], ENV);
  assert.deepEqual(await data("bamboo_posts/mapped"), before);

  // 운영자가 충돌을 판정하고(여기서는 public 쪽이 맞다고 가정) 미확인 글을 정리했다고 하자.
  await db.doc("bamboo_post_authors/conflict").set({ postId: "conflict", ownerUid: "alice" });
  await db.doc("bamboo_posts/ghost").delete();
  assert.equal(await main(["--project", PROJECT, "--apply"], ENV), 0);
  const v = await verify(db, admin);
  assert.equal(v.violations, 0, JSON.stringify(v));
  assert.equal(await main(["--project", PROJECT, "--verify"], ENV), 0);
});

test("--limit 는 canary 로 고칠 레코드 수를 제한한다", async () => {
  await seedLegacy();
  await main(["--project", PROJECT, "--apply", "--limit", "1"], ENV);
  const posts = await db.collection("bamboo_posts").get();
  const comments = await db.collection("bamboo_posts").doc("mapped").collection("comments").get();
  const redacted = [...posts.docs, ...comments.docs].filter((d) => !("authorId" in d.data())).length;
  assert.equal(redacted, 1);
});

test("verify 는 마이그레이션 전 레거시 상태를 위반(exit 3)으로 보고한다", async () => {
  await seedLegacy();
  assert.equal(await main(["--project", PROJECT, "--verify"], ENV), 3);
});
