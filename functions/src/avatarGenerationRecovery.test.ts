import assert from "node:assert/strict";
import test from "node:test";

import {
  MAX_USER_GENERATION_ATTEMPTS,
  planNewGenerationRecovery,
} from "./avatarGenerationRecovery";

function decide(status: string, extra: Record<string, unknown> = {}, attempts = 1) {
  return planNewGenerationRecovery({
    currentJobData: { status, ...extra },
    userAvatar: { status },
    generationAttemptCount: attempts,
  });
}

test("QA needs_review lets the user start a new generation with new photos", () => {
  const decision = decide("needs_review", { errorCode: "qa_requires_review" });
  assert.equal(decision.allowed, true);
  if (!decision.allowed) return;
  // 같은 generation 재시도가 아니라 현재 generation 을 끝내고 lock 을 푼다.
  assert.equal(decision.jobUpdate.status, "cancelled");
  assert.equal(decision.jobUpdate.errorCode, "avatar_generation_replaced_by_user");
  assert.equal(decision.releasesSourceLock, true);
});

test("terminal failure and no previewable candidates also allow a new generation", () => {
  for (const status of ["terminal_failed", "no_previewable_candidates", "failed"]) {
    assert.equal(decide(status).allowed, true, `${status} should allow restart`);
  }
});

test("provider outcome unknown blocks a new generation until reconciled", () => {
  // 이미 과금된 생성이 존재할 수 있다. 재조정 전에는 새 generation 도 막는다.
  const decision = decide("needs_review", {
    errorCode: "azure_unknown_post_send_outcome",
  });
  assert.equal(decision.allowed, false);
  if (decision.allowed) return;
  assert.equal(decision.reasonCode, "avatar_provider_outcome_unknown");
});

test("an active generation cannot be replaced", () => {
  for (const status of [
    "queued",
    "running",
    "provider_inflight",
    "qa_pending",
    "preview_ready",
    "approval_copying",
  ]) {
    const decision = decide(status);
    assert.equal(decision.allowed, false, `${status} must not be replaceable`);
    if (decision.allowed) continue;
    assert.equal(decision.reasonCode, "avatar_generation_in_progress");
  }
});

test("an approved avatar is never replaced by this path", () => {
  const decision = decide("approved");
  assert.equal(decision.allowed, false);
  if (decision.allowed) return;
  assert.equal(decision.reasonCode, "avatar_already_approved");
});

test("the generation attempt limit is enforced", () => {
  const decision = decide("terminal_failed", {}, MAX_USER_GENERATION_ATTEMPTS);
  assert.equal(decision.allowed, false);
  if (decision.allowed) return;
  assert.equal(decision.reasonCode, "avatar_generation_limit_reached");
});

test("an active generation claim blocks replacement even on a terminal status", () => {
  const decision = decide("terminal_failed", {
    generationClaim: { state: "active" },
  });
  assert.equal(decision.allowed, false);
  if (decision.allowed) return;
  assert.equal(decision.reasonCode, "avatar_provider_outcome_unknown");
});
