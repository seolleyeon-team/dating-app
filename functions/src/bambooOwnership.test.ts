import assert from "node:assert/strict";
import test from "node:test";

import {
  bambooCommentOwnerDocId,
  ownerUidForNotification,
  resolveBambooOwner,
} from "./bambooOwnership";

test("매핑이 있으면 매핑이 소유자다", () => {
  const resolution = resolveBambooOwner("uid-a", "uid-a");
  assert.deepEqual(resolution, { status: "mapped", ownerUid: "uid-a" });
  assert.equal(ownerUidForNotification(resolution), "uid-a");
});

test("아직 이관되지 않은 문서는 legacy authorId 를 임시로 인정한다", () => {
  const resolution = resolveBambooOwner(undefined, "uid-a");
  assert.deepEqual(resolution, { status: "legacy", ownerUid: "uid-a" });
  assert.equal(ownerUidForNotification(resolution), "uid-a");
});

test("public authorId 가 사라져도 매핑만으로 소유자를 안다", () => {
  // Phase C 이후의 모습. 이 단계에서 알림이 끊기면 안 된다.
  const resolution = resolveBambooOwner("uid-a", undefined);
  assert.deepEqual(resolution, { status: "mapped", ownerUid: "uid-a" });
});

test("매핑과 legacy 가 다르면 아무도 고르지 않는다", () => {
  // 한쪽을 고르면 남의 글 알림이 엉뚱한 사람에게 간다.
  const resolution = resolveBambooOwner("uid-a", "uid-b");
  assert.deepEqual(resolution, { status: "conflict" });
  assert.equal(ownerUidForNotification(resolution), "");
});

test("둘 다 없으면 소유자를 모른다 — 추측하지 않는다", () => {
  const resolution = resolveBambooOwner(undefined, undefined);
  assert.deepEqual(resolution, { status: "missing" });
  assert.equal(ownerUidForNotification(resolution), "");
});

test("문자열이 아니거나 공백뿐인 값은 없는 것으로 본다", () => {
  assert.deepEqual(resolveBambooOwner(123, "  "), { status: "missing" });
  assert.deepEqual(resolveBambooOwner("  uid-a  ", null), {
    status: "mapped",
    ownerUid: "uid-a",
  });
  // 공백 차이는 충돌이 아니다.
  assert.deepEqual(resolveBambooOwner(" uid-a", "uid-a "), {
    status: "mapped",
    ownerUid: "uid-a",
  });
});

test("댓글 매핑 문서 id 는 글 id 를 포함한다", () => {
  // commentId 는 글 안에서만 유일하다.
  assert.equal(bambooCommentOwnerDocId("post-1", "c-1"), "post-1__c-1");
  assert.notEqual(
    bambooCommentOwnerDocId("post-1", "c-1"),
    bambooCommentOwnerDocId("post-2", "c-1")
  );
});
