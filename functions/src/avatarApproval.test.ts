import assert from "node:assert/strict";
import test from "node:test";

import {
  avatarPreviewResponseStatus,
  buildApprovedAvatarPath,
  buildAvatarId,
  checkCurrentAvatarJobContract,
  planAvatarApprovalState,
} from "./avatarApproval";

test("same-candidate repeated approval returns the existing approved avatar", () => {
  const plan = planAvatarApprovalState(
    {
      avatar: {
        status: "approved",
        selectedCandidateId: "cand_1",
        approvedAvatarUrl: "https://cdn.example/avatar.png",
        avatarId: "avatar_1",
      },
    },
    "cand_1"
  );

  assert.equal(plan.action, "return_existing");
  assert.equal(plan.approvedAvatarUrl, "https://cdn.example/avatar.png");
  assert.equal(plan.avatarId, "avatar_1");
});

test("same-candidate approval does not echo unsafe persisted avatar urls", () => {
  const plan = planAvatarApprovalState(
    {
      avatar: {
        status: "approved",
        selectedCandidateId: "cand_1",
        approvedAvatarUrl:
          "gs://seolleyeon-final-private-source-photos/users/u1/source/src.jpg",
        avatarId: "avatar_1",
      },
    },
    "cand_1"
  );

  assert.equal(plan.action, "reserve");
});

test("same-candidate approval rejects Festival private-media URLs", () => {
  for (const approvedAvatarUrl of [
    "https://seolleyeon-festival-private-source-photos.storage.googleapis.com/users/u/source/src.jpg",
    "https://seolleyeon-festival-avatar-temp.storage.googleapis.com/users/u/jobs/j/candidates/c.png",
    "https://seolleyeon-festival-chat-profile-photos.storage.googleapis.com/users/u/chat/photo.jpg?token=secret",
  ]) {
    const plan = planAvatarApprovalState(
      {
        avatar: {
          status: "approved",
          selectedCandidateId: "cand_1",
          approvedAvatarUrl,
          avatarId: "avatar_1",
        },
      },
      "cand_1"
    );

    assert.equal(plan.action, "reserve", approvedAvatarUrl);
  }
});

test("different-candidate approval conflicts before copy when approval is in progress", () => {
  const plan = planAvatarApprovalState(
    {
      avatar: {
        status: "approval_copying",
        selectedCandidateId: "cand_winner",
        avatarId: "avatar_winner",
      },
    },
    "cand_loser"
  );

  assert.equal(plan.action, "conflict");
  assert.equal(plan.errorCode, "avatar_already_approved");
});

test("different-candidate approval conflicts after approval has completed", () => {
  const plan = planAvatarApprovalState(
    {
      avatar: {
        status: "approved",
        selectedCandidateId: "cand_winner",
        approvedAvatarUrl: "https://cdn.example/avatar.png",
      },
    },
    "cand_loser"
  );

  assert.equal(plan.action, "conflict");
  assert.equal(plan.errorCode, "avatar_already_approved");
});

test("same-candidate copy failure can retry with the same deterministic object", () => {
  const plan = planAvatarApprovalState(
    {
      avatar: {
        status: "approval_copy_failed",
        selectedCandidateId: "cand_1",
        avatarId: "avatar_1",
        approvalDownloadToken: "token-1",
      },
    },
    "cand_1"
  );

  assert.equal(plan.action, "reserve");
  assert.equal(plan.avatarId, "avatar_1");
  assert.equal(plan.approvalDownloadToken, "token-1");
});

test("approved avatar id and path are deterministic by candidate id", () => {
  const avatarId = buildAvatarId("cand_avatar_job_1_01");

  assert.equal(avatarId, "avatar_avatar_job_1_01");
  assert.equal(
    buildApprovedAvatarPath("u1", avatarId),
    "users/u1/avatar/avatar_avatar_job_1_01.png"
  );
});

test("current avatar job contract accepts the current active source", () => {
  const result = checkCurrentAvatarJobContract({
    jobId: "job_current",
    jobData: {
      sourcePhotoIds: ["src_current"],
      avatarSourceSelectionVersion: 3,
    },
    privateData: {
      currentAvatarJobId: "job_current",
      currentAvatarSourcePhotoId: "src_current",
      avatarSourceSelectionVersion: 3,
      sourcePhotos: [
        {
          photoId: "src_current",
          status: "active",
          avatarGenerationState: "current",
        },
      ],
    },
  });

  assert.equal(result.ok, true);
});

test("current avatar job contract rejects stale preview-ready jobs", () => {
  const result = checkCurrentAvatarJobContract({
    jobId: "job_old",
    jobData: {
      sourcePhotoIds: ["src_old"],
      avatarSourceSelectionVersion: 1,
    },
    privateData: {
      currentAvatarJobId: "job_new",
      currentAvatarSourcePhotoId: "src_new",
      avatarSourceSelectionVersion: 2,
      sourcePhotos: [
        {
          photoId: "src_old",
          status: "active",
          avatarGenerationState: "superseded",
        },
        {
          photoId: "src_new",
          status: "active",
          avatarGenerationState: "current",
        },
      ],
    },
  });

  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.errorCode, "avatar_job_superseded");
    assert.equal(result.reason, "current_job_mismatch");
  }
});

test("current avatar job contract rejects selection version mismatch", () => {
  const result = checkCurrentAvatarJobContract({
    jobId: "job_current",
    jobData: {
      sourcePhotoIds: ["src_current"],
      avatarSourceSelectionVersion: 1,
    },
    privateData: {
      currentAvatarJobId: "job_current",
      currentAvatarSourcePhotoId: "src_current",
      avatarSourceSelectionVersion: 2,
      sourcePhotos: [
        {
          photoId: "src_current",
          status: "active",
          avatarGenerationState: "current",
        },
      ],
    },
  });

  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.reason, "selection_version_mismatch");
  }
});

test("stale non-current active preview polls terminate as superseded", () => {
  for (const jobStatus of ["queued", "running", "qa_pending", "preview_ready"]) {
    assert.equal(
      avatarPreviewResponseStatus({
        jobStatus,
        currentContractOk: false,
        candidateCount: jobStatus === "preview_ready" ? 1 : 0,
        previewableCandidateCount: 0,
      }),
      "superseded",
      `for status=${jobStatus}`,
    );
  }
});

test("preview ready with only blocked candidates maps to no_previewable", () => {
  assert.equal(
    avatarPreviewResponseStatus({
      jobStatus: "preview_ready",
      currentContractOk: true,
      candidateCount: 2,
      previewableCandidateCount: 0,
    }),
    "no_previewable_candidates",
  );
});
