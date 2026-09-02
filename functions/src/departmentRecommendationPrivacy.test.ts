import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDepartmentRecommendationExclusionPayload,
  departmentOfUser,
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
