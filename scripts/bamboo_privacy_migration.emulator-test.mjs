/**
 * P0-3 마이그레이션 — 레거시 데이터를 심고 실제로 돌린다 (Firestore Emulator).
 *
 *   firebase emulators:exec --only firestore,auth --project demo-p03-migration \
 *     "node --test scripts/bamboo_privacy_migration.emulator-test.mjs"
 *
 * 에뮬레이터에는 Rules API 가 없어서 배포 이력은 주입한다 (`deps.loadRulesHistory`).
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

/** 당시 배포된 규칙이 클라이언트 create 에서 authorId == auth.uid 를 강제했다. */
const BOUND_HISTORY = [{
  name: "bound",
  createTimeMs: 0,
  source: `service cloud.firestore { match /databases/{database}/documents {
    match /bamboo_posts/{postId} {
      allow create: if request.resource.data.authorId == request.auth.uid;
      match /comments/{commentId} {
        allow create: if request.resource.data.authorId == request.auth.uid;
      }
    }
  } }`,
}];
const UNBOUND_HISTORY = [{ name: "open", createTimeMs: 0, source: "service cloud.firestore { match /bamboo_posts/{postId} { allow create: if true; } }" }];
const DEPS = { loadRulesHistory: async () => BOUND_HISTORY };
const run = (args, deps = DEPS) => main(["--project", PROJECT, ...args], ENV, deps);

async function clear() {
  const res = await fetch(
    `http://${process.env.FIRESTORE_EMULATOR_HOST}/emulator/v1/projects/${PROJECT}/databases/(default)/documents`,
    { method: "DELETE" }
  );
  assert.ok(res.ok);
}

const ts = (ms) => admin.firestore.Timestamp.fromMillis(ms);
const postBody = (id, authorId) => ({
  postId: id, authorId, content: id, category: "고민", tags: [], likeCount: 0, commentCount: 0,
  score7d: 0, isDeleted: false, createdAt: ts(1_700_000_000_000), updatedAt: ts(1_700_000_000_000),
});

/** 운영 모양의 레거시 데이터. */
async function seedLegacy() {
  await clear();
  // 매핑이 있는 글
  await db.doc("bamboo_posts/mapped").set(postBody("mapped", "alice"));
  await db.doc("bamboo_post_authors/mapped").set({ postId: "mapped", ownerUid: "alice" });
  // 클라이언트가 혼자 쓴 글 (그 시각 규칙이 authorId 를 묶었고 이후 수정 없음)
  await db.doc("bamboo_posts/solo").set(postBody("solo", "bob"));
  // 관리자 일괄 import: 서로 다른 작성자의 글이 한 커밋에 생겼다
  const batch = db.batch();
  batch.set(db.doc("bamboo_posts/importA"), postBody("importA", "carol"));
  batch.set(db.doc("bamboo_posts/importB"), postBody("importB", "dave"));
  await batch.commit();
  // 생성 뒤 수정된 글 — authorId 가 처음 값이라는 보장이 없다
  await db.doc("bamboo_posts/edited").set(postBody("edited", "bob"));
  await db.doc("bamboo_posts/edited").update({ likeCount: 1 });
  // 매핑과 public 이 다른 사람을 가리킨다
  await db.doc("bamboo_posts/conflict").set(postBody("conflict", "alice"));
  await db.doc("bamboo_post_authors/conflict").set({ postId: "conflict", ownerUid: "carol" });
  // 댓글 (혼자 쓴 것)
  await db.doc("bamboo_posts/mapped/comments/c1").set({
    commentId: "c1", authorId: "bob", content: "c", parentCommentId: null, likeCount: 0, isDeleted: false,
  });
  await db.doc("bamboo_posts/mapped/likes/carol").set({ userId: "carol" });
  await db.doc("playReviewBambooPosts/rv").set({
    postId: "rv", authorId: "play-reviewer-v1", content: "r", dataPartition: "play_review", isDeleted: false,
  });
  await db.doc("playReviewBambooPostAuthors/rv").set({ postId: "rv", ownerUid: "play-reviewer-v1", dataPartition: "play_review" });
  await db.doc("users/alice/notifications/n1").set({ type: "community_comment", actorId: "bob", actorName: "bob", postId: "mapped" });
  await db.doc("users/alice/notifications/n2").set({ type: "profile_like", actorId: "carol", actorName: "carol" });
}

const data = async (path) => (await db.doc(path).get()).data();
const exists = async (path) => (await db.doc(path).get()).exists;

test("ATTACK 12: dry-run 은 아무것도 쓰지 않는다", async () => {
  await seedLegacy();
  assert.equal(await run([]), 2, "the conflict is reported");
  assert.equal((await data("bamboo_posts/solo")).authorId, "bob");
  assert.equal(await exists("bamboo_post_authors/solo"), false);
  assert.equal(await exists("bamboo_ownership_unresolved/bamboo_posts__importA"), false);
  assert.equal((await data("users/alice/notifications/n1")).actorId, "bob");
});

test("Phase 0A: 근거 있는 글만 소유자를 얻고, 근거 없는 글은 소유자 없이 익명화된다", async () => {
  await seedLegacy();
  const dir = mkdtempSync(join(tmpdir(), "p03-"));
  const anomalies = join(dir, "anomalies.txt");
  const checkpoint = join(dir, "checkpoint.json");
  assert.equal(await run(["--apply", "--checkpoint", checkpoint, "--anomaly-ids-out", anomalies]), 2);

  for (const path of ["bamboo_posts/mapped", "bamboo_posts/solo", "bamboo_posts/importA", "bamboo_posts/importB",
    "bamboo_posts/edited", "bamboo_posts/mapped/comments/c1", "playReviewBambooPosts/rv"]) {
    assert.ok(!("authorId" in (await data(path))), `${path} redacted`);
  }
  // 근거 있는 글: 매핑 생성 (글의 작성 시각 유지)
  assert.equal((await data("bamboo_post_authors/solo")).ownerUid, "bob");
  assert.equal((await data("bamboo_post_authors/solo")).createdAt.toMillis(), 1_700_000_000_000);
  assert.equal((await data("bamboo_comment_authors/mapped__c1")).ownerUid, "bob");
  assert.equal((await data("bamboo_post_authors/mapped")).ownerUid, "alice", "existing mapping untouched");
  // 근거 없는 글: 매핑 없음, 서버 전용 미해결 기록에 원래 주장만 보관
  for (const [id, claim] of [["importA", "carol"], ["importB", "dave"], ["edited", "bob"]]) {
    assert.equal(await exists(`bamboo_post_authors/${id}`), false, `${id}: no unverified owner assigned`);
    const record = await data(`bamboo_ownership_unresolved/bamboo_posts__${id}`);
    assert.equal(record.legacyAuthorClaim, claim);
    assert.equal(record.postId, id);
  }
  // 내용·카운터는 그대로
  assert.equal((await data("bamboo_posts/importA")).content, "importA");
  assert.equal((await data("bamboo_posts/edited")).likeCount, 1);
  // 충돌은 그대로 (사람이 판단)
  assert.equal((await data("bamboo_posts/conflict")).authorId, "alice");
  // 알림: 대나무숲만 익명화
  const n1 = await data("users/alice/notifications/n1");
  assert.deepEqual([n1.actorId, n1.actorName], [null, "익명"]);
  assert.equal((await data("users/alice/notifications/n2")).actorId, "carol");
  assert.equal((await data("bamboo_posts/mapped/likes/carol")).userId, "carol");
  // 보고서와 checkpoint 에 UID 없음
  const report = readFileSync(anomalies, "utf8");
  assert.match(report, /MAPPING_CONFLICT bamboo_posts\/conflict/);
  for (const uid of ["alice", "bob", "carol", "dave"]) {
    assert.ok(!report.includes(uid));
    assert.ok(!readFileSync(checkpoint, "utf8").includes(uid));
  }

  const v = await verify(db, admin);
  assert.equal(v.publicPostsWithIdentity, 1, "only the conflict keeps its field until a human decides");
  assert.equal(v.mappingConflicts, 1);
  assert.equal(v.unresolvedOwnership, 3);
  assert.equal(v.recordsWithoutOwnershipRecord, 0);
  assert.equal(v.identifyingBambooNotifications, 0);
});

test("규칙이 authorId 를 묶지 않았던 시기의 글은 근거가 없다", async () => {
  await seedLegacy();
  await run(["--apply"], { loadRulesHistory: async () => UNBOUND_HISTORY });
  assert.equal(await exists("bamboo_post_authors/solo"), false);
  assert.equal((await data("bamboo_ownership_unresolved/bamboo_posts__solo")).legacyAuthorClaim, "bob");
  assert.ok(!("authorId" in (await data("bamboo_posts/solo"))));
});

test("멱등: 다시 돌려도 쓰기가 없고, 충돌을 해소하면 마저 끝나며 verify 가 0 이 된다", async () => {
  await seedLegacy();
  await run(["--apply"]);
  const before = await data("bamboo_posts/solo");
  const unresolvedBefore = await data("bamboo_ownership_unresolved/bamboo_posts__importA");
  await run(["--apply"]);
  assert.deepEqual(await data("bamboo_posts/solo"), before);
  assert.deepEqual(await data("bamboo_ownership_unresolved/bamboo_posts__importA"), unresolvedBefore);

  await db.doc("bamboo_post_authors/conflict").set({ postId: "conflict", ownerUid: "alice" });
  assert.equal(await run(["--apply"]), 0);
  const v = await verify(db, admin);
  assert.equal(v.violations, 0, JSON.stringify(v));
  assert.equal(v.unresolvedOwnership, 3, "unresolved ownership is reported, not hidden");
  assert.equal(await run(["--verify"]), 0);
});

test("--limit 와 --only-post 는 canary 범위를 제한한다", async () => {
  await seedLegacy();
  await run(["--apply", "--limit", "1"]);
  const all = [...(await db.collection("bamboo_posts").get()).docs, ...(await db.collection("bamboo_posts/mapped/comments").get()).docs];
  assert.equal(all.filter((d) => !("authorId" in d.data())).length, 1);

  await seedLegacy();
  await run(["--apply", "--only-post", "solo"]);
  assert.ok(!("authorId" in (await data("bamboo_posts/solo"))));
  for (const other of ["mapped", "importA", "edited"]) {
    assert.ok("authorId" in (await data(`bamboo_posts/${other}`)), `${other} untouched by the canary`);
  }
});

test("verify 는 마이그레이션 전 레거시 상태를 위반(exit 3)으로 보고한다", async () => {
  await seedLegacy();
  assert.equal(await run(["--verify"]), 3);
});

test("리뷰 M2: dry-run 이나 --limit 실행의 checkpoint 가 처리 안 된 글을 건너뛰게 하지 않는다", async () => {
  await seedLegacy();
  const checkpoint = join(mkdtempSync(join(tmpdir(), "p03-")), "cp.json");
  await run(["--checkpoint", checkpoint]); // dry-run
  await run(["--apply", "--limit", "1", "--checkpoint", checkpoint]);
  await db.doc("bamboo_post_authors/conflict").set({ postId: "conflict", ownerUid: "alice" });
  assert.equal(await run(["--apply", "--checkpoint", checkpoint]), 0);
  const v = await verify(db, admin);
  assert.equal(v.violations, 0, JSON.stringify(v));
});

test("리뷰 L1: 탈퇴 정리로 매핑이 지워진 삭제 글은 위반이 아니다", async () => {
  await clear();
  await db.doc("bamboo_posts/gone").set({ postId: "gone", content: "[삭제된 게시글]", isDeleted: true });
  const v = await verify(db, admin);
  assert.equal(v.violations, 0, JSON.stringify(v));
  assert.equal(v.deletedWithoutOwner, 1);
});
