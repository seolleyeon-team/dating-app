import assert from "node:assert/strict";
import test from "node:test";

import {
  isProfileVisibleForRecommendationDate,
  kstDateKey,
  nextKstDateKey,
} from "./profileVisibility";

test("profile visibility uses KST calendar dates", () => {
  const utcAfternoon = new Date("2026-09-01T16:00:00.000Z");
  assert.equal(kstDateKey(utcAfternoon), "20260902");
  assert.equal(nextKstDateKey(utcAfternoon), "20260903");
});

test("hiding a profile applies only from the next recommendation day", () => {
  const setting = {
    profileVisible: false,
    profileVisibleBeforeEffectiveDate: true,
    profileVisibleEffectiveDateKey: "20260902",
  };

  assert.equal(isProfileVisibleForRecommendationDate(setting, "20260901"), true);
  assert.equal(isProfileVisibleForRecommendationDate(setting, "20260902"), false);
});

test("showing a hidden profile also waits for the next recommendation day", () => {
  const setting = {
    profileVisible: true,
    profileVisibleBeforeEffectiveDate: false,
    profileVisibleEffectiveDateKey: "20260902",
  };

  assert.equal(isProfileVisibleForRecommendationDate(setting, "20260901"), false);
  assert.equal(isProfileVisibleForRecommendationDate(setting, "20260902"), true);
});
