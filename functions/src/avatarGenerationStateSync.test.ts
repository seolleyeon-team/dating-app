import assert from "node:assert/strict";
import test from "node:test";

import {
  planAvatarGenerationStateSync,
  shouldSyncAvatarGenerationTransition,
  syncAvatarGenerationStateForJob,
} from "./avatarGenerationStateSync";

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

test("terminal state is applied only when the job enters terminal state", () => {
  assert.equal(
    shouldSyncAvatarGenerationTransition({
      beforeData: { status: "running", updatedAt: "old" },
      afterData: { status: "completed", updatedAt: "new" },
    }),
    true,
  );
  assert.equal(
    shouldSyncAvatarGenerationTransition({
      beforeData: { status: "completed", updatedAt: "old" },
      afterData: { status: "completed", updatedAt: "new" },
    }),
    false,
  );
  assert.equal(
    shouldSyncAvatarGenerationTransition({
      beforeData: { status: "completed" },
      afterData: { status: "retryable_failed" },
    }),
    false,
  );
  assert.equal(
    shouldSyncAvatarGenerationTransition({
      beforeData: { status: "queued" },
      afterData: { status: "running", progress: 0.5 },
    }),
    false,
  );
});

test("a terminal job that already matches user state is a semantic no-op", () => {
  const plan = planAvatarGenerationStateSync({
    jobId,
    jobData: avatarJob({ status: "completed" }),
    privateData: privateMedia(),
    userData: {
      profileImageMode: "avatar",
      avatar: {
        status: "completed",
        sourceJobId: jobId,
        jobId,
        sourcePhotoId: "photo1",
        sourceSelectionVersion: 7,
      },
      onboarding: {
        sourcePhotoUploadStatus: "avatar_generation_completed",
      },
    },
  });

  assert.deepEqual(plan, {
    action: "skip",
    reason: "already_synchronized",
  });
});

test("state sync updates users without writing back to the watched avatar job", async () => {
  const snapshots: Record<string, { exists: boolean; data: () => Record<string, unknown> }> = {
    [`avatarJobs/${jobId}`]: {
      exists: true,
      data: () => avatarJob({ status: "completed" }),
    },
    "userPrivateMedia/u1": {
      exists: true,
      data: () => privateMedia(),
    },
    "users/u1": {
      exists: true,
      data: () => queuedAvatar(),
    },
  };
  const writes: Array<{ type: string; path: string }> = [];
  const firestore = {
    collection(name: string) {
      return {
        doc(id: string) {
          return { path: `${name}/${id}` };
        },
      };
    },
    async runTransaction(callback: (tx: unknown) => Promise<unknown>) {
      const tx = {
        async get(ref: { path: string }) {
          return snapshots[ref.path] ?? { exists: false, data: () => ({}) };
        },
        update(ref: { path: string }) {
          writes.push({ type: "update", path: ref.path });
        },
        set(ref: { path: string }) {
          writes.push({ type: "set", path: ref.path });
        },
      };
      return callback(tx);
    },
  } as never;

  const result = await syncAvatarGenerationStateForJob({
    firestore,
    jobId,
  });

  assert.equal(result, "updated");
  assert.deepEqual(writes, [{ type: "update", path: "users/u1" }]);
});
