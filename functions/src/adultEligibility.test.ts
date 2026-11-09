import assert from "node:assert/strict";
import test from "node:test";

import { HttpsError } from "firebase-functions/v2/https";

import {
  assertEligibleForDatingFeatures,
  isAdultVerifiedUserData,
  isEligibleForDatingFeatures,
} from "./adultEligibility";

test("P1-7: only the server-written pair adultVerified && realNameVerified counts", () => {
  assert.equal(isAdultVerifiedUserData({ adultVerified: true, realNameVerified: true }), true);
  assert.equal(isAdultVerifiedUserData({ adultVerified: true }), false);
  assert.equal(isAdultVerifiedUserData({ realNameVerified: true }), false);
  assert.equal(isAdultVerifiedUserData({ adultVerified: "true", realNameVerified: true }), false, "strings are not booleans");
  assert.equal(isAdultVerifiedUserData({ adultVerified: 1, realNameVerified: 1 }), false);
  assert.equal(isAdultVerifiedUserData({}), false);
  assert.equal(isAdultVerifiedUserData(null), false);
  assert.equal(isAdultVerifiedUserData(undefined), false);
});

test("P1-7: production accounts need the evidence; the review partition is exempt; invalid partitions are not", () => {
  assert.equal(isEligibleForDatingFeatures({ adultVerified: true, realNameVerified: true }), true);
  assert.equal(isEligibleForDatingFeatures({ isStudentVerified: true }), false, "student verification alone is not adult verification");
  assert.equal(isEligibleForDatingFeatures({ dataPartition: "play_review" }), true);
  assert.equal(isEligibleForDatingFeatures({ dataPartition: "garbage" }), false);
  assert.throws(
    () => assertEligibleForDatingFeatures({ isStudentVerified: true }),
    (error: unknown) => error instanceof HttpsError && error.code === "failed-precondition"
  );
  assert.doesNotThrow(() => assertEligibleForDatingFeatures({ adultVerified: true, realNameVerified: true }));
});
