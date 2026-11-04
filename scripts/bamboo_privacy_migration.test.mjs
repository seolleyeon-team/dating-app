/**
 * P0-3 마이그레이션 — 순수 분류·출처 근거·안전장치 테스트 (에뮬레이터 불필요).
 *   node --test scripts/bamboo_privacy_migration.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  assertRunnable,
  classifyRecord,
  createRuleBindsAuthor,
  notificationNeedsSanitizing,
  parseArgs,
  provenanceFor,
  rulesetAt,
} from "./bamboo_privacy_migration.mjs";

const P = { postId: "p1" };
const C = { postId: "p1", commentId: "c1" };

test("기존 매핑이 public authorId 와 같으면 redact (TRUSTED_EXISTING_MAPPING)", () => {
  assert.deepEqual(
    classifyRecord({ publicData: { authorId: "a" }, mapping: { postId: "p1", ownerUid: "a" }, provenance: "none", expected: P }),
    { status: "TRUSTED_EXISTING_MAPPING", action: "redact", ownerUid: "a" }
  );
});

test("매핑이 다른 사람을 가리키면 그 레코드는 멈춘다 (conflict)", () => {
  assert.equal(
    classifyRecord({ publicData: { authorId: "a" }, mapping: { postId: "p1", ownerUid: "b" }, provenance: "historical", expected: P }).action,
    "skip"
  );
});

test("깨진 매핑(빈 ownerUid, 다른 글/댓글을 가리킴)은 malformed", () => {
  for (const mapping of [{ postId: "p1", ownerUid: "" }, { postId: "p2", ownerUid: "a" }]) {
    assert.equal(classifyRecord({ publicData: { authorId: "a" }, mapping, provenance: "none", expected: P }).status, "MALFORMED");
  }
  assert.equal(
    classifyRecord({ publicData: { authorId: "a" }, mapping: { postId: "p1", commentId: "c9", ownerUid: "a" }, provenance: "none", expected: C }).status,
    "MALFORMED"
  );
});

test("Phase 0A: 매핑이 없으면 출처 근거가 있을 때만 매핑을 만든다", () => {
  assert.deepEqual(
    classifyRecord({ publicData: { authorId: "a" }, mapping: null, provenance: "historical", expected: P }),
    { status: "TRUSTED_HISTORICAL_PROVENANCE", action: "createMappingAndRedact", ownerUid: "a" }
  );
  // 계정이 존재한다는 것만으로는 근거가 아니다 — 소유자 없이 지우고 미해결로 기록
  assert.deepEqual(
    classifyRecord({ publicData: { authorId: "a" }, mapping: null, provenance: "none", expected: P }),
    { status: "LEGACY_AUTHOR_ONLY", action: "redactUnresolved" }
  );
});

test("소유자가 불확실해도 public 식별 정보는 남기지 않는다", () => {
  assert.equal(
    classifyRecord({ publicData: { nickname: "닉" }, mapping: null, provenance: "none", expected: P }).action,
    "redactUnresolved"
  );
  assert.equal(
    classifyRecord({ publicData: { nickname: "닉" }, mapping: { postId: "p1", ownerUid: "a" }, provenance: "none", expected: P }).action,
    "redact"
  );
});

test("멱등: 이미 정리된 문서는 아무 것도 하지 않는다", () => {
  assert.equal(
    classifyRecord({ publicData: { content: "x" }, mapping: { postId: "p1", ownerUid: "a" }, provenance: "none", expected: P }).action,
    "none"
  );
  assert.equal(
    classifyRecord({ publicData: { content: "x" }, mapping: null, provenance: "none", unresolvedRecorded: true, expected: P }).status,
    "UNRESOLVED_RECORDED"
  );
  // 식별 필드도 매핑도 없는 살아 있는 글은 writer 버그 — 미해결로 덮지 않고 이상으로 보고
  assert.deepEqual(
    classifyRecord({ publicData: { content: "x" }, mapping: null, provenance: "none", unresolvedRecorded: false, expected: P }),
    { status: "OWNERLESS_WITHOUT_EVIDENCE", action: "skip" }
  );
  // 탈퇴 정리로 soft delete 된 글은 정상 종착
  assert.equal(
    classifyRecord({ publicData: { content: "x", isDeleted: true }, mapping: null, provenance: "none", expected: P }).status,
    "DELETED_WITHOUT_OWNER"
  );
});

const BOUND_RULES = `service cloud.firestore {
  match /bamboo_posts/{postId} {
    allow create: if isSignedIn() && request.resource.data.authorId == request.auth.uid && request.resource.data.content is string;
    match /comments/{commentId} {
      allow create: if isSignedIn() &&
        request.resource.data.authorId == request.auth.uid;
    }
  }
}`;

test("규칙 근거: create 가 authorId 를 요청자에게 묶을 때만 인정, OR 분기나 서버 전용은 불인정", () => {
  assert.equal(createRuleBindsAuthor(BOUND_RULES, "bamboo_posts", "post"), true);
  assert.equal(createRuleBindsAuthor(BOUND_RULES, "bamboo_posts", "comment"), true);
  assert.equal(createRuleBindsAuthor(BOUND_RULES, "playReviewBambooPosts", "post"), false);
  assert.equal(
    createRuleBindsAuthor(BOUND_RULES.replace("request.resource.data.content is string", "true || false"), "bamboo_posts", "post"),
    false
  );
  assert.equal(
    createRuleBindsAuthor("match /bamboo_posts/{postId} { allow create: if true; }", "bamboo_posts", "post"),
    false
  );
  assert.equal(
    createRuleBindsAuthor("match /bamboo_posts/{postId} { allow create: if false; }", "bamboo_posts", "post"),
    false
  );
});

function fakeSnap({ authorId, created, updated }) {
  const ts = (ms) => ({ seconds: Math.floor(ms / 1000), nanoseconds: (ms % 1000) * 1e6, toMillis: () => ms });
  return { data: () => ({ authorId }), createTime: ts(created), updateTime: ts(updated ?? created) };
}

test("출처 근거: 그 시각의 규칙, 무수정, 단독 커밋이 모두 있어야 historical", () => {
  const history = [
    { name: "open", createTimeMs: 0, source: "match /bamboo_posts/{postId} { allow create: if true; }" },
    { name: "bound", createTimeMs: 1000, source: BOUND_RULES },
  ];
  const noShare = new Map();
  const at = (snap) => provenanceFor({ snap, rootName: "bamboo_posts", kind: "post", history, sharedCommit: noShare });
  assert.equal(rulesetAt(history, 1500).name, "bound");
  assert.equal(at(fakeSnap({ authorId: "a", created: 2000 })), "historical");
  assert.equal(at(fakeSnap({ authorId: "a", created: 500 })), "none", "rule did not bind authorId then");
  assert.equal(at(fakeSnap({ authorId: "a", created: 2000, updated: 3000 })), "none", "updated after creation");
  assert.equal(at(fakeSnap({ authorId: "", created: 2000 })), "none");
  const shared = new Map([["2.000000000", new Set(["a", "b"])]]);
  assert.equal(
    provenanceFor({ snap: fakeSnap({ authorId: "a", created: 2000 }), rootName: "bamboo_posts", kind: "post", history, sharedCommit: shared }),
    "none",
    "same commit as another author's document = bulk import"
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
  assert.throws(() => parseArgs(["--project", "seolleyeon-final", "--only-post", "../x"]), /document id/);
  assert.throws(() => assertRunnable(parseArgs(["--project", "demo-p03-migration", "--apply"]), {}), /emulator/);
  assert.doesNotThrow(() =>
    assertRunnable(parseArgs(["--project", "demo-p03-migration", "--apply"]), { FIRESTORE_EMULATOR_HOST: "127.0.0.1:8080" })
  );
});
