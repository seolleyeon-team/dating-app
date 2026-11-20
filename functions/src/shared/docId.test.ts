import assert from "node:assert/strict";
import test from "node:test";

import { isSingleDocumentId } from "./docId";

test("ordinary document ids are accepted", () => {
  for (const id of ["4850097844", "play-reviewer-v1", "fake_user_1", "dm_a_b", "a|b", "9f2c0e"]) {
    assert.equal(isSingleDocumentId(id), true, id);
  }
});

test("a value that would resolve to a nested path is refused", () => {
  for (const id of ["A/notifications/like_B_A", "A/friends/B", "/A", "A/", "a//b"]) {
    assert.equal(isSingleDocumentId(id), false, id);
  }
});

test("empty, relative and non-string values are refused", () => {
  for (const id of ["", ".", "..", null, undefined, 42, {}, ["a"]]) {
    assert.equal(isSingleDocumentId(id), false, String(id));
  }
});
