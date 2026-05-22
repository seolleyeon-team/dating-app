import assert from "node:assert/strict";
import test from "node:test";

import {
  buildApprovedAvatarPath,
  buildAvatarId,
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
