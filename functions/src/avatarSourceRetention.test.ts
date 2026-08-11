import assert from "node:assert/strict";
import test from "node:test";

import {
  avatarSourceRetentionStateId,
  hasAvatarApprovalProtectedState,
  nextSourceDeletionRetryAt,
  planAvatarSourceRetention,
  redactSourcePhotosAfterDeletion,
} from "./avatarSourceRetention";

const uid = "u1";
const jobId = "avatar_u1_photo1";
const privateSourceRef =
  "gs://seolleyeon-final-private-source-photos/users/u1/source/photo1.jpg";

function privateMedia(overrides: Record<string, unknown> = {}) {
  return {
    currentAvatarJobId: jobId,
    currentAvatarSourcePhotoId: "photo1",
    avatarSourceSelectionVersion: 3,
    photoConsent: {
      purposes: {
        avatarGeneration: true,
        clipRecommendation: false,
        sourcePhotoRetention: false,
      },
    },
    clip: { embeddingStatus: "not_requested" },
    sourcePhotos: [
      {
        photoId: "photo1",
        status: "active",
        avatarGenerationState: "current",
        gcsUri: privateSourceRef,
        storageBucket: "seolleyeon-final-private-source-photos",
        storagePath: "users/u1/source/photo1.jpg",
        sha256: "audit-hash",
      },
    ],
    ...overrides,
  };
}

function avatarJob(overrides: Record<string, unknown> = {}) {
  return {
    uid,
    jobId,
    status: "terminal_failed",
    sourcePhotoIds: ["photo1"],
    sourcePhotoRefs: [privateSourceRef],
    avatarSourceSelectionVersion: 3,
    ...overrides,
  };
}

test("plans source deletion only after irreversible terminal outcome when retention is false", () => {
  const decision = planAvatarSourceRetention({
    uid,
    jobId,
    privateData: privateMedia(),
    jobData: avatarJob(),
  });

  assert.equal(decision.action, "claim");
  assert.equal(decision.sourceSelectionVersion, 3);
  assert.deepEqual(decision.refs, [
    {
      bucket: "seolleyeon-final-private-source-photos",
      path: "users/u1/source/photo1.jpg",
    },
  ]);
});

test("non-irreversible avatar statuses are not source deletion terminal", () => {
  for (const status of [
    "preview_ready",
    "needs_review",
    "retryable_failed",
    "no_previewable",
    "no_previewable_candidates",
    "completed",
    "approved",
  ]) {
    const decision = planAvatarSourceRetention({
      uid,
      jobId,
      privateData: privateMedia(),
      jobData: avatarJob({ status }),
    });

    assert.deepEqual(decision, {
      action: "skip",
      reason: "avatar_not_irreversible_terminal",
    });
  }
});

test("completed and approved jobs require an explicit irreversible deletion contract", () => {
  for (const status of ["completed", "approved"]) {
    const decision = planAvatarSourceRetention({
      uid,
      jobId,
      privateData: privateMedia(),
      jobData: avatarJob({ status, sourceDeletionIrreversible: true }),
    });

    assert.equal(decision.action, "claim");
  }
});

test("retryable failed jobs keep source available for retry", () => {
  const retryable = planAvatarSourceRetention({
    uid,
    jobId,
    privateData: privateMedia(),
    jobData: avatarJob({ status: "failed", retryable: true }),
  });
  const finalFailed = planAvatarSourceRetention({
    uid,
    jobId,
    privateData: privateMedia(),
    jobData: avatarJob({ status: "failed", retryable: false }),
  });

  assert.deepEqual(retryable, {
    action: "skip",
    reason: "avatar_not_irreversible_terminal",
  });
  assert.equal(finalFailed.action, "claim");
});

test("approval and approval-in-progress public states protect source deletion unconditionally", () => {
  for (const status of ["approved", "approval_copying", "approval_copy_failed"]) {
    assert.equal(hasAvatarApprovalProtectedState({ avatar: { status } }), true);
  }
  assert.equal(hasAvatarApprovalProtectedState({ avatar: { status: "completed" } }), false);
});

test("retention consent prevents source deletion", () => {
  const decision = planAvatarSourceRetention({
    uid,
    jobId,
    privateData: privateMedia({
      photoConsent: {
        purposes: {
          avatarGeneration: true,
          clipRecommendation: false,
          sourcePhotoRetention: true,
        },
      },
    }),
    jobData: avatarJob(),
  });

  assert.deepEqual(decision, { action: "skip", reason: "retained_by_consent" });
});

test("running avatar status is never eligible", () => {
  const decision = planAvatarSourceRetention({
    uid,
    jobId,
    privateData: privateMedia(),
    jobData: avatarJob({ status: "running" }),
  });

  assert.deepEqual(decision, {
    action: "skip",
    reason: "avatar_not_irreversible_terminal",
  });
});

test("selection version mismatch blocks stale deletion claims", () => {
  const decision = planAvatarSourceRetention({
    uid,
    jobId,
    privateData: privateMedia({ avatarSourceSelectionVersion: 4 }),
    jobData: avatarJob({ avatarSourceSelectionVersion: 3 }),
  });

  assert.deepEqual(decision, {
    action: "skip",
    reason: "selection_version_mismatch",
  });
});

test("clip recommendation consent waits for terminal clip state", () => {
  const decision = planAvatarSourceRetention({
    uid,
    jobId,
    privateData: privateMedia({
      photoConsent: {
        purposes: {
          avatarGeneration: true,
          clipRecommendation: true,
          sourcePhotoRetention: false,
        },
      },
      clip: { embeddingStatus: "pending" },
    }),
    jobData: avatarJob(),
    clipData: { status: "running", sourcePhotoRefs: [privateSourceRef] },
  });

  assert.deepEqual(decision, { action: "skip", reason: "clip_not_terminal" });
});

test("terminal clip document allows deletion after irreversible avatar terminal", () => {
  const decision = planAvatarSourceRetention({
    uid,
    jobId,
    privateData: privateMedia({
      photoConsent: {
        purposes: {
          avatarGeneration: true,
          clipRecommendation: true,
          sourcePhotoRetention: false,
        },
      },
      clip: { embeddingStatus: "pending" },
    }),
    jobData: avatarJob(),
    clipData: { status: "completed", sourcePhotoRefs: [privateSourceRef] },
  });

  assert.equal(decision.action, "claim");
});

test("already deleted state is represented outside sourcePhotos", () => {
  const sourcePhotos = redactSourcePhotosAfterDeletion(
    privateMedia().sourcePhotos,
    "photo1",
  );
  const redacted = sourcePhotos[0];

  assert.equal(redacted.status, "source_deleted");
  assert.equal(redacted.sourceDeleted, true);
  assert.equal("gcsUri" in redacted, false);
  assert.equal("storageBucket" in redacted, false);
  assert.equal("storagePath" in redacted, false);
  assert.equal("sourceDeletion" in redacted, false);
  assert.equal("updatedAt" in redacted, false);
});

test("only UID-bound private source refs are eligible", () => {
  const decision = planAvatarSourceRetention({
    uid,
    jobId,
    privateData: privateMedia({
      sourcePhotos: [
        {
          photoId: "photo1",
          status: "active",
          avatarGenerationState: "current",
          gcsUri: "gs://seolleyeon-final-avatar-temp/users/u1/jobs/job1/source.png",
        },
      ],
    }),
    jobData: avatarJob(),
  });

  assert.deepEqual(decision, {
    action: "skip",
    reason: "missing_uid_bound_source_ref",
  });
});

test("state ids and retry schedule are deterministic and bounded", () => {
  assert.equal(
    avatarSourceRetentionStateId("u1", "photo1"),
    avatarSourceRetentionStateId("u1", "photo1"),
  );
  assert.equal(
    nextSourceDeletionRetryAt({ attempts: 1, nowMs: 1_000 })?.getTime(),
    301_000,
  );
  assert.equal(nextSourceDeletionRetryAt({ attempts: 5, nowMs: 1_000 }), null);
});
