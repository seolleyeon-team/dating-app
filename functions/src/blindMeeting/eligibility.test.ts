import assert from "node:assert/strict";
import test from "node:test";

import {
  hasRequiredInterests,
  hasRequiredLifestyle,
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

test("blind meeting lifestyle eligibility requires both drinking and smoking", () => {
  assert.equal(
    hasRequiredLifestyle({
      lifestyle: { drinking: "sometimes", smoking: "nonSmoker" },
    }),
    true
  );
  assert.equal(
    hasRequiredLifestyle({ lifestyle: { drinking: "sometimes" } }),
    false
  );
  assert.equal(
    hasRequiredLifestyle({ lifestyle: { smoking: "nonSmoker" } }),
    false
  );
  assert.equal(
    hasRequiredLifestyle({
      lifestyle: { drinking: "unknown", smoking: "nonSmoker" },
    }),
    false
  );
  assert.equal(hasRequiredLifestyle(null), false);
});
