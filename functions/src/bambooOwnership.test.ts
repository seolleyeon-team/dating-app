import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  BAMBOO_PUBLIC_IDENTITY_FIELDS,
  bambooCommentOwnerDocId,
  ownerUidOrEmpty,
  resolveBambooOwner,
} from "./bambooOwnership";
import {
  ANONYMOUS_COMMUNITY_ACTOR_NAME,
  isAnonymousCommunityNotificationType,
} from "./shared/notify";

test("매핑이 있으면 매핑이 소유자다", () => {
  assert.deepEqual(
    resolveBambooOwner({ postId: "p1", ownerUid: "alice" }, { postId: "p1" }),
    { status: "mapped", ownerUid: "alice" }
  );
});

test("매핑이 없으면 소유자를 모른다 — public authorId 로 되돌아가지 않는다", () => {
  assert.deepEqual(resolveBambooOwner(null, { postId: "p1" }), { status: "missing" });
  assert.deepEqual(resolveBambooOwner(undefined, { postId: "p1" }), { status: "missing" });
  // 시그니처에 legacy authorId 를 넘길 자리가 없다.
  assert.equal(resolveBambooOwner.length, 2);
});

test("ownerUid 가 비었거나 다른 글을 가리키는 매핑은 malformed (fail closed)", () => {
  assert.deepEqual(resolveBambooOwner({ postId: "p1", ownerUid: "  " }, { postId: "p1" }), { status: "malformed" });
  assert.deepEqual(resolveBambooOwner({ postId: "p2", ownerUid: "alice" }, { postId: "p1" }), { status: "malformed" });
  assert.deepEqual(
    resolveBambooOwner({ postId: "p1", commentId: "c2", ownerUid: "alice" }, { postId: "p1", commentId: "c1" }),
    { status: "malformed" }
  );
  assert.deepEqual(
    resolveBambooOwner({ postId: "p1", commentId: "c1", ownerUid: "alice" }, { postId: "p1", commentId: "c1" }),
    { status: "mapped", ownerUid: "alice" }
  );
});

test("확신할 수 없으면 알림 대상은 빈 문자열이다", () => {
  assert.equal(ownerUidOrEmpty({ status: "mapped", ownerUid: "alice" }), "alice");
  assert.equal(ownerUidOrEmpty({ status: "missing" }), "");
  assert.equal(ownerUidOrEmpty({ status: "malformed" }), "");
});

test("댓글 매핑 문서 id 는 postId__commentId", () => {
  assert.equal(bambooCommentOwnerDocId("p1", "c1"), "p1__c1");
});

test("대나무숲 알림 종류는 행위자 익명 처리 대상이다", () => {
  for (const type of ["community_comment", "community_reply", "community_post_like"]) {
    assert.equal(isAnonymousCommunityNotificationType(type), true, type);
  }
  assert.equal(isAnonymousCommunityNotificationType("profile_like"), false);
  assert.equal(ANONYMOUS_COMMUNITY_ACTOR_NAME, "익명");
});

/**
 * 정적 가드: 서버가 public 대나무숲 문서를 쓰는 경로가 작성자 필드를 되살리지
 * 않는다. 대나무숲 public 문서를 쓰는 소스는 communitySafety.ts 와 심사용 시드
 * (playReviewAccess.ts) 뿐이다.
 */
test("public 대나무숲 writer 는 작성자 식별 필드를 쓰지 않는다", () => {
  const src = (name: string) =>
    readFileSync(join(__dirname, "..", "src", name), "utf8")
      .split("\n")
      // comments and type declarations (e.g. `type AppUser = { userId: string }`) are not writes
      .filter((line) => !/^\s*(\/\/|\*|\/\*\*|type\s)/.test(line))
      .join("\n");
  const writer = src("communitySafety.ts");
  for (const field of BAMBOO_PUBLIC_IDENTITY_FIELDS) {
    if (field === "ownerUid") continue; // 비공개 매핑의 필드
    assert.ok(!new RegExp(`\\b${field}\\s*:`).test(writer), `communitySafety.ts must not write ${field}`);
  }
  const seed = src("playReviewAccess.ts");
  assert.ok(!/authorId\s*:/.test(seed), "review Bamboo seed must not write authorId");

  const triggers = src("index.ts");
  const start = triggers.indexOf("export const onBambooCommentCreated");
  const end = triggers.indexOf("export const onAskCreated");
  const bamboo = triggers.slice(start, end);
  assert.ok(start > 0 && end > start);
  assert.ok(!/actorId\s*:/.test(bamboo), "bamboo notifications must not carry actorId");
  assert.ok(!/getUserDisplayInfo/.test(bamboo), "bamboo notifications must not look up the actor's profile");
  assert.ok(!/\.authorId\b/.test(bamboo), "bamboo triggers must not read public authorId");
});
