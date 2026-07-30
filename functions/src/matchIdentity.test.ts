import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDeterministicMatchId,
  buildDirectRoomId,
  InvalidMatchUserIdsError,
} from "./matchIdentity";

test("buildDirectRoomId sorts uids deterministically", () => {
  assert.equal(
    buildDirectRoomId("user-b", "user-a"),
    buildDirectRoomId("user-a", "user-b")
  );
  assert.equal(buildDirectRoomId("user-a", "user-b"), "dm_user-a_user-b");
});

test("buildDeterministicMatchId sorts uids deterministically", () => {
  assert.equal(
    buildDeterministicMatchId("user-b", "user-a"),
    buildDeterministicMatchId("user-a", "user-b")
  );
  assert.equal(
    buildDeterministicMatchId("user-a", "user-b"),
    "match_user-a_user-b"
  );
});

test("match identity helpers reject empty uids", () => {
  for (const fn of [buildDirectRoomId, buildDeterministicMatchId]) {
    assert.throws(() => fn("", "user-a"), InvalidMatchUserIdsError);
    assert.throws(() => fn("user-a", ""), InvalidMatchUserIdsError);
    assert.throws(() => fn("  ", "user-a"), InvalidMatchUserIdsError);
  }
});
