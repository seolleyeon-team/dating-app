import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDepartmentRecommendationExclusionPayload,
  departmentOfUser,
  departmentPairNeedsReconcile,
  departmentRecommendationPrivacyChanged,
  departmentsToReconcile,
  isAvoidSameDepartmentEnabled,
  normalizeDepartment,
  shouldExcludeSameDepartment,
} from "./departmentRecommendationPrivacy";

test("department is read from onboarding with a legacy top-level fallback", () => {
  assert.equal(
    departmentOfUser({ onboarding: { department: " 컴퓨터과학과 " } }),
    "컴퓨터과학과",
  );
  assert.equal(
    departmentOfUser({ onboarding: { department: "" }, department: "심리학과" }),
    "심리학과",
  );
  assert.equal(normalizeDepartment("  "), null);
  assert.equal(normalizeDepartment(42), null);
});

test("same-department avoidance excludes both recommendation directions", () => {
  const viewer = {
    onboarding: { department: "컴퓨터과학과" },
    privacySettings: { avoidSameDepartment: true },
  };
  const candidate = {
    onboarding: { department: "컴퓨터과학과" },
    privacySettings: { avoidSameDepartment: false },
  };

  assert.equal(shouldExcludeSameDepartment(viewer, candidate), true);
  assert.equal(shouldExcludeSameDepartment(candidate, viewer), true);
  assert.equal(
    shouldExcludeSameDepartment(
      { onboarding: { department: "심리학과" }, privacySettings: { avoidSameDepartment: true } },
      candidate,
    ),
    false,
  );
  assert.equal(
    shouldExcludeSameDepartment(
      { onboarding: { department: "컴퓨터과학과" } },
      { onboarding: { department: "컴퓨터과학과" } },
    ),
    false,
  );
});

test("only the strict boolean true enables the preference", () => {
  assert.equal(
    isAvoidSameDepartmentEnabled({ privacySettings: { avoidSameDepartment: "true" } }),
    false,
  );
  assert.equal(
    isAvoidSameDepartmentEnabled({ privacySettings: { avoidSameDepartment: true } }),
    true,
  );
});

test("materialized pair metadata does not expose either preference value", () => {
  const payload = buildDepartmentRecommendationExclusionPayload("a", "b");

  assert.equal(payload.source, "same_department");
  assert.equal(payload.reason, "same_department_avoidance");
  assert.equal(payload.active, true);
  assert.equal(payload.enabledBy, undefined);
});

test("department changes and preference changes trigger reconciliation", () => {
  const before = {
    onboarding: { department: "컴퓨터과학과" },
    privacySettings: { avoidSameDepartment: false },
  };
  const after = {
    onboarding: { department: "컴퓨터과학과" },
    privacySettings: { avoidSameDepartment: true },
  };

  assert.equal(departmentRecommendationPrivacyChanged(before, after), true);
  assert.deepEqual(departmentsToReconcile(before, after), ["컴퓨터과학과"]);
  assert.equal(
    departmentRecommendationPrivacyChanged(before, {
      ...before,
      updatedAt: "new",
    }),
    false,
  );
  assert.deepEqual(
    departmentsToReconcile(before, {
      onboarding: { department: "심리학과" },
      privacySettings: { avoidSameDepartment: true },
    }),
    ["컴퓨터과학과", "심리학과"],
  );
});

test("B-14: a pair is left alone only when avoidance is not, and was not, in play and nothing is stored", () => {
  const plain = { onboarding: { department: "컴퓨터과학과" } };
  const avoiding = {
    onboarding: { department: "컴퓨터과학과" },
    privacySettings: { avoidSameDepartment: true },
  };
  const elsewhere = { onboarding: { department: "심리학과" } };

  // Sign-up into a department where the peer does not avoid: nothing to write.
  assert.equal(
    departmentPairNeedsReconcile({ before: null, after: plain, peer: plain, exclusionExists: false }),
    false,
  );
  // The peer avoids the department: the pair must be materialized.
  assert.equal(
    departmentPairNeedsReconcile({ before: null, after: plain, peer: avoiding, exclusionExists: false }),
    true,
  );
  // The changed user stopped avoiding: an exclusion may exist and must go.
  assert.equal(
    departmentPairNeedsReconcile({ before: avoiding, after: plain, peer: plain, exclusionExists: false }),
    true,
  );
  // Account deletion of a user who avoided: both directions are cleaned.
  assert.equal(
    departmentPairNeedsReconcile({ before: avoiding, after: null, peer: plain, exclusionExists: false }),
    true,
  );
  // Leaving a department where nobody avoided: nothing to clean.
  assert.equal(
    departmentPairNeedsReconcile({ before: plain, after: elsewhere, peer: plain, exclusionExists: false }),
    false,
  );
  // A stored exclusion is always reconciled, whatever the snapshot says.
  assert.equal(
    departmentPairNeedsReconcile({ before: plain, after: elsewhere, peer: null, exclusionExists: true }),
    true,
  );
});
