/**
 * P0-3 마이그레이션 — 순수 분류·안전장치 테스트 (에뮬레이터 불필요).
 *   node --test scripts/bamboo_privacy_migration.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  assertRunnable,
  classifyRecord,
  notificationNeedsSanitizing,
  parseArgs,
} from "./bamboo_privacy_migration.mjs";

const P = { postId: "p1" };
const C = { postId: "p1", commentId: "c1" };

test("매핑이 public authorId 와 같으면 redact", () => {
  assert.deepEqual(
    classifyRecord({ publicData: { authorId: "a" }, mapping: { postId: "p1", ownerUid: "a" }, authorAccountExists: true, expected: P }),
    { status: "MAPPING_VERIFIED", action: "redact", ownerUid: "a" }
  );
});

test("매핑이 다른 사람을 가리키면 그 레코드는 멈춘다 (conflict)", () => {
  assert.equal(
    classifyRecord({ publicData: { authorId: "a" }, mapping: { postId: "p1", ownerUid: "b" }, authorAccountExists: true, expected: P }).action,
    "skip"
  );
});

test("깨진 매핑(빈 ownerUid, 다른 글/댓글을 가리킴)은 malformed", () => {
  for (const mapping of [{ postId: "p1", ownerUid: "" }, { postId: "p2", ownerUid: "a" }]) {
    assert.equal(classifyRecord({ publicData: { authorId: "a" }, mapping, authorAccountExists: true, expected: P }).status, "MALFORMED");
  }
  assert.equal(
    classifyRecord({ publicData: { authorId: "a" }, mapping: { postId: "p1", commentId: "c9", ownerUid: "a" }, authorAccountExists: true, expected: C }).status,
    "MALFORMED"
  );
});

test("매핑이 없으면 실존 계정일 때만 매핑을 만들고 redact, 아니면 unverifiable", () => {
  assert.deepEqual(
    classifyRecord({ publicData: { authorId: "a" }, mapping: null, authorAccountExists: true, expected: P }),
    { status: "MAPPING_MISSING", action: "createMappingAndRedact", ownerUid: "a" }
  );
  assert.deepEqual(
    classifyRecord({ publicData: { authorId: "ghost" }, mapping: null, authorAccountExists: false, expected: P }),
    { status: "UNVERIFIABLE", action: "skip" }
  );
});

test("이미 지워진 문서는 아무 것도 하지 않는다 (멱등)", () => {
  assert.equal(
    classifyRecord({ publicData: { content: "x" }, mapping: { postId: "p1", ownerUid: "a" }, authorAccountExists: false, expected: P }).action,
    "none"
  );
  assert.equal(
    classifyRecord({ publicData: { content: "x" }, mapping: null, authorAccountExists: false, expected: P }).status,
    "UNVERIFIABLE_NO_OWNER"
  );
});

test("authorId 외 식별 필드도 redact 대상이고, 소유자 근거가 없으면 멈춘다", () => {
  assert.equal(
    classifyRecord({ publicData: { nickname: "닉" }, mapping: { postId: "p1", ownerUid: "a" }, authorAccountExists: false, expected: P }).action,
    "redact"
  );
  assert.equal(
    classifyRecord({ publicData: { nickname: "닉" }, mapping: null, authorAccountExists: false, expected: P }).action,
    "skip"
  );
});

test("대나무숲 알림만, 행위자가 남아 있을 때만 익명화", () => {
  assert.equal(notificationNeedsSanitizing({ type: "community_comment", actorId: "u", actorName: "닉" }), true);
  assert.equal(notificationNeedsSanitizing({ type: "community_post_like", actorId: null, actorName: "닉" }), true);
  assert.equal(notificationNeedsSanitizing({ type: "community_reply", actorId: null, actorName: "익명" }), false);
  assert.equal(notificationNeedsSanitizing({ type: "profile_like", actorId: "u", actorName: "닉" }), false);
});

test("기본은 dry-run 이고 production 쓰기는 --allow-production 이 필요하다", () => {
  const dry = parseArgs(["--project", "seolleyeon-final"]);
  assert.equal(dry.apply, false);
  assert.doesNotThrow(() => assertRunnable(dry, {}));
  const apply = parseArgs(["--project", "seolleyeon-final", "--apply"]);
  assert.throws(() => assertRunnable(apply, {}), /allow-production/);
  assert.doesNotThrow(() => assertRunnable(parseArgs(["--project", "seolleyeon-final", "--apply", "--allow-production"]), {}));
  assert.throws(() => assertRunnable(parseArgs(["--project", "someone-else"]), {}), /allowlist/);
  assert.throws(() => parseArgs(["--project", "seolleyeon-final", "--apply", "--verify"]), /exclusive/);
  // 테스트 프로젝트는 에뮬레이터로만 쓴다
  assert.throws(() => assertRunnable(parseArgs(["--project", "demo-p03-migration", "--apply"]), {}), /emulator/);
  assert.doesNotThrow(() =>
    assertRunnable(parseArgs(["--project", "demo-p03-migration", "--apply"]), { FIRESTORE_EMULATOR_HOST: "127.0.0.1:8080" })
  );
});
