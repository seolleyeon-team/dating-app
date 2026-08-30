/**
 * SEC-04 마이그레이션 도구의 안전장치와 분류 로직 테스트.
 *
 * 여기서 지키려는 것은 두 가지다. 하나, 실수로 production 에 쓰지 않는 것.
 * 둘, 이미 있는 매핑을 절대 덮어쓰지 않는 것 — 덮어쓰면 남의 글이 내 글이
 * 된다. 에뮬레이터를 띄우지 않고 돌 수 있게 순수 함수만 검증한다.
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  ALLOWED_PROJECTS,
  DEFAULT_BATCH_SIZE,
  assertRunnable,
  chunk,
  classifyDoc,
  commentMappingId,
  parseArgs,
  parseCommentPath,
} from "./bamboo_anonymize_migration.mjs";

const NO_EMULATOR = {};
const EMULATOR = { FIRESTORE_EMULATOR_HOST: "127.0.0.1:8080" };

test("기본은 dry-run 이다", () => {
  const options = parseArgs(["--project", "seolleyeon-final"], NO_EMULATOR);
  assert.equal(options.apply, false);
  assert.equal(options.allowProduction, false);
  assert.equal(options.batchSize, DEFAULT_BATCH_SIZE);
});

test("--project 는 필수다", () => {
  assert.throws(() => assertRunnable(parseArgs([], NO_EMULATOR), NO_EMULATOR), {
    message: /--project is required/,
  });
});

test("allowlist 밖 프로젝트는 dry-run 도 거부한다", () => {
  // 오타 하나로 남의 프로젝트를 읽는 것도 막는다.
  const options = parseArgs(["--project", "seolleyeon-fnial"], NO_EMULATOR);
  assert.throws(() => assertRunnable(options, NO_EMULATOR), {
    message: /not in the allowlist/,
  });
  assert.ok(ALLOWED_PROJECTS.has("seolleyeon-final"));
});

test("production 쓰기는 --apply 만으로는 안 된다", () => {
  const options = parseArgs(
    ["--project", "seolleyeon-final", "--apply"],
    NO_EMULATOR
  );
  assert.throws(() => assertRunnable(options, NO_EMULATOR), {
    message: /--allow-production/,
  });
});

test("production 쓰기는 자격증명을 명시해야 한다", () => {
  // 주변 환경에 남아 있던 기본 자격증명으로 조용히 붙는 일을 막는다.
  const options = parseArgs(
    ["--project", "seolleyeon-final", "--apply", "--allow-production"],
    NO_EMULATOR
  );
  assert.throws(() => assertRunnable(options, NO_EMULATOR), {
    message: /--credentials/,
  });
});

test("두 옵션과 자격증명이 다 있어야 production 쓰기가 열린다", () => {
  const options = parseArgs(
    [
      "--project",
      "seolleyeon-final",
      "--apply",
      "--allow-production",
      "--credentials",
      "C:/keys/sa.json",
    ],
    NO_EMULATOR
  );
  assert.doesNotThrow(() => assertRunnable(options, NO_EMULATOR));
});

test("production dry-run 은 추가 옵션 없이 가능하다", () => {
  const options = parseArgs(["--project", "seolleyeon-final"], NO_EMULATOR);
  assert.doesNotThrow(() => assertRunnable(options, NO_EMULATOR));
});

test("에뮬레이터로 가는 쓰기는 production 게이트를 타지 않는다", () => {
  const options = parseArgs(
    ["--project", "seolleyeon-final", "--apply"],
    EMULATOR
  );
  assert.doesNotThrow(() => assertRunnable(options, EMULATOR));
});

test("배치 크기는 Firestore 상한을 넘을 수 없다", () => {
  assert.throws(
    () => parseArgs(["--project", "seolleyeon-final", "--batch-size", "501"]),
    { message: /500/ }
  );
  assert.throws(
    () => parseArgs(["--project", "seolleyeon-final", "--batch-size", "0"]),
    { message: /integer >= 1/ }
  );
});

test("값이 필요한 옵션에 값이 없으면 조용히 넘어가지 않는다", () => {
  assert.throws(() => parseArgs(["--project", "--apply"]), {
    message: /--project requires a value/,
  });
});

test("모르는 인자는 무시하지 않고 멈춘다", () => {
  assert.throws(() => parseArgs(["--force"]), { message: /Unknown argument/ });
});

test("매핑이 없고 authorId 가 멀쩡하면 이관 대상", () => {
  assert.equal(classifyDoc({ authorId: "uid-a", mapping: undefined }), "pending");
});

test("같은 소유자로 이미 매핑이 있으면 건너뛴다 — 재실행 안전", () => {
  assert.equal(
    classifyDoc({ authorId: "uid-a", mapping: { ownerUid: "uid-a" } }),
    "alreadyMigrated"
  );
});

test("public authorId 가 이미 지워진 문서도 이관 완료로 본다", () => {
  // Phase C 이후의 모습. 다시 만들 것이 없다.
  assert.equal(
    classifyDoc({ authorId: undefined, mapping: { ownerUid: "uid-a" } }),
    "alreadyMigrated"
  );
});

test("매핑과 authorId 가 다르면 덮어쓰지 않고 conflict 로 남긴다", () => {
  assert.equal(
    classifyDoc({ authorId: "uid-a", mapping: { ownerUid: "uid-b" } }),
    "conflict"
  );
});

test("매핑이 깨져 있으면 고치려 들지 않는다", () => {
  // 소유자를 알 수 없는 매핑을 추측해서 다시 쓰면 틀릴 수 있다.
  assert.equal(classifyDoc({ authorId: "uid-a", mapping: {} }), "conflict");
  assert.equal(
    classifyDoc({ authorId: "uid-a", mapping: { ownerUid: 42 } }),
    "conflict"
  );
});

test("authorId 를 읽을 수 없으면 소유자를 정하지 않는다", () => {
  assert.equal(classifyDoc({ authorId: "  ", mapping: undefined }), "malformed");
  assert.equal(classifyDoc({ authorId: 42, mapping: undefined }), "malformed");
  assert.equal(
    classifyDoc({ authorId: undefined, mapping: undefined }),
    "malformed"
  );
});

test("공백 차이는 충돌이 아니다", () => {
  assert.equal(
    classifyDoc({ authorId: " uid-a ", mapping: { ownerUid: "uid-a" } }),
    "alreadyMigrated"
  );
});

test("배치는 경계에서 정확히 쪼개진다", () => {
  assert.deepEqual(chunk([1, 2, 3, 4, 5], 2), [[1, 2], [3, 4], [5]]);
  assert.deepEqual(chunk([1, 2], 2), [[1, 2]]);
  assert.deepEqual(chunk([], 400), []);
  assert.throws(() => chunk([1], 0), { message: /integer >= 1/ });
});

test("대나무숲 댓글 경로만 대상으로 삼는다", () => {
  assert.deepEqual(parseCommentPath("bamboo_posts/p1/comments/c1"), {
    postId: "p1",
    commentId: "c1",
  });
  // collectionGroup 은 이름이 같은 다른 하위 컬렉션도 끌어온다.
  assert.equal(parseCommentPath("chat_rooms/r1/comments/c1"), null);
  assert.equal(parseCommentPath("bamboo_posts/p1/comments/c1/likes/u1"), null);
  assert.equal(parseCommentPath("bamboo_posts/p1"), null);
});

test("댓글 매핑 id 는 글 id 를 포함한다", () => {
  // commentId 는 글 안에서만 유일하다.
  assert.equal(commentMappingId("p1", "c1"), "p1__c1");
  assert.notEqual(commentMappingId("p1", "c1"), commentMappingId("p2", "c1"));
});
