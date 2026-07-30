import assert from "node:assert/strict";
import test from "node:test";

import { planAvatarGenerationStateSync } from "./avatarGenerationStateSync";

const uid = "u1";
const jobId = "avatar_job_1";

function privateMedia(overrides: Record<string, unknown> = {}) {
  return {
    currentAvatarJobId: jobId,
    currentAvatarSourcePhotoId: "photo1",
    avatarSourceSelectionVersion: 7,
    sourcePhotos: [
      {
        photoId: "photo1",
        status: "active",
        avatarGenerationState: "current",
      },
    ],
    ...overrides,
  };
}

function avatarJob(overrides: Record<string, unknown> = {}) {
  return {
    uid,
    jobId,
    status: "completed",
    sourcePhotoIds: ["photo1"],
    avatarSourceSelectionVersion: 7,
    ...overrides,
  };
}

function queuedAvatar(overrides: Record<string, unknown> = {}) {
  return {
    avatar: {
      status: "queued",
      sourceJobId: jobId,
      jobId,
      sourcePhotoId: "photo1",
      sourceSelectionVersion: 7,
      errorCode: "stale_error",
      reasonCode: "stale_reason",
      ...overrides,
    },
  };
}

test("terminal current completed job updates public avatar out of queued and clears stale errors", () => {
  const plan = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "completed", errorCode: "unsafe_worker_detail" }),
    privateData: privateMedia(),
    userData: queuedAvatar(),
  });

  assert.equal(plan.action, "update_user_avatar");
  assert.equal(plan.uid, uid);
  assert.equal(plan.jobId, jobId);
  assert.equal(plan.sourcePhotoId, "photo1");
  assert.equal(plan.avatarStatus, "completed");
  assert.equal(plan.onboardingStatus, "avatar_generation_completed");
  assert.equal(plan.sourceSelectionVersion, 7);
  assert.equal(plan.avatarErrorCode, null);
  assert.equal(plan.clearAvatarError, true);
});

test("no previewable candidates maps to safe terminal public reason instead of queued", () => {
  const plan = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({
      status: "no_previewable_candidates",
      errorCode: "raw_worker_message_with_path_users/u1/source/photo1.jpg",
    }),
    privateData: privateMedia(),
    userData: queuedAvatar(),
  });

  assert.equal(plan.action, "update_user_avatar");
  assert.equal(plan.avatarStatus, "no_previewable_candidates");
  assert.equal(plan.onboardingStatus, "no_previewable_candidates");
  assert.equal(plan.avatarErrorCode, "no_previewable_candidates");
  assert.equal(plan.clearAvatarError, false);
});

test("retryable and terminal failures use deterministic safe reason codes", () => {
  const retryable = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "retryable_failed", errorCode: "signed-url-secret" }),
    privateData: privateMedia(),
    userData: queuedAvatar(),
  });
  const terminal = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "terminal_failed", message: "raw stack trace" }),
    privateData: privateMedia(),
    userData: queuedAvatar(),
  });

  assert.equal(retryable.action, "update_user_avatar");
  assert.equal(retryable.avatarErrorCode, "avatar_generation_retryable_failed");
  assert.equal(terminal.action, "update_user_avatar");
  assert.equal(terminal.avatarErrorCode, "avatar_generation_terminal_failed");
});

test("preview ready maps to preview public state and clears stale errors", () => {
  const plan = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "preview_ready" }),
    privateData: privateMedia(),
    userData: queuedAvatar(),
  });

  assert.equal(plan.action, "update_user_avatar");
  assert.equal(plan.avatarStatus, "preview_ready");
  assert.equal(plan.onboardingStatus, "avatar_generation_preview_ready");
  assert.equal(plan.avatarErrorCode, null);
  assert.equal(plan.clearAvatarError, true);
});

test("stale private job is blocked by current job compare-and-set contract", () => {
  const plan = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "completed" }),
    privateData: privateMedia({ currentAvatarJobId: "newer_job" }),
    userData: queuedAvatar(),
  });

  assert.deepEqual(plan, { action: "skip", reason: "stale_or_superseded_job" });
});

test("selection version mismatch blocks superseded terminal job", () => {
  const plan = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "failed", avatarSourceSelectionVersion: 6 }),
    privateData: privateMedia({ avatarSourceSelectionVersion: 7 }),
    userData: queuedAvatar(),
  });

  assert.deepEqual(plan, { action: "skip", reason: "stale_or_superseded_job" });
});

test("public avatar source job mismatch blocks terminal state overwrite", () => {
  const plan = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "failed" }),
    privateData: privateMedia(),
    userData: queuedAvatar({ sourceJobId: "other_job" }),
  });

  assert.deepEqual(plan, {
    action: "skip",
    reason: "public_avatar_contract_mismatch",
  });
});

test("public avatar jobId mismatch blocks terminal state overwrite", () => {
  const plan = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "failed" }),
    privateData: privateMedia(),
    userData: queuedAvatar({ jobId: "other_job" }),
  });

  assert.deepEqual(plan, {
    action: "skip",
    reason: "public_avatar_contract_mismatch",
  });
});

test("public avatar source photo mismatch blocks terminal state overwrite", () => {
  const plan = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "failed" }),
    privateData: privateMedia(),
    userData: queuedAvatar({ sourcePhotoId: "other_photo" }),
  });

  assert.deepEqual(plan, {
    action: "skip",
    reason: "public_avatar_contract_mismatch",
  });
});

test("public avatar source selection version mismatch blocks terminal state overwrite", () => {
  const plan = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "failed" }),
    privateData: privateMedia(),
    userData: queuedAvatar({ sourceSelectionVersion: 6 }),
  });

  assert.deepEqual(plan, {
    action: "skip",
    reason: "public_avatar_contract_mismatch",
  });
});

test("approved and approval-in-progress avatar state is preserved", () => {
  for (const status of ["approved", "approval_copying", "approval_copy_failed"]) {
    const plan = planAvatarGenerationStateSync({
      jobId,
      jobData: avatarJob({ status: "failed" }),
      privateData: privateMedia(),
      userData: queuedAvatar({ status }),
    });

    assert.deepEqual(plan, {
      action: "skip",
      reason: "avatar_approval_preserved",
    });
  }
});

test("superseded job terminal state never overwrites user avatar", () => {
  const plan = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "superseded" }),
    privateData: privateMedia(),
    userData: queuedAvatar(),
  });

  assert.deepEqual(plan, { action: "skip", reason: "job_superseded" });
});
