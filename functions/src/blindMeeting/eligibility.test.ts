import assert from "node:assert/strict";
import test from "node:test";

import {
  hasRequiredInterests,
  isStrictStudentVerification,
} from "./eligibility";

test("blind meeting interest eligibility rejects empty or non-list values", () => {
  assert.equal(hasRequiredInterests([]), false);
  assert.equal(hasRequiredInterests(null), false);
  assert.equal(hasRequiredInterests("movie"), false);
  assert.equal(hasRequiredInterests(["movie"]), true);
});

test("student verification eligibility accepts boolean true only", () => {
  assert.equal(isStrictStudentVerification(true), true);
  assert.equal(isStrictStudentVerification(false), false);
  assert.equal(isStrictStudentVerification("true"), false);
  assert.equal(isStrictStudentVerification(1), false);
  assert.equal(isStrictStudentVerification(null), false);
});
