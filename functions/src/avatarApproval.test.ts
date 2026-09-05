import assert from "node:assert/strict";
import test from "node:test";

import {
  avatarPreviewResponseStatus,
  buildApprovedAvatarPath,
  buildAvatarId,
  checkCurrentAvatarJobContract,
  planAvatarApprovalState,
  resolveAvatarCandidateSource,
  planApprovalFailureRecovery,
} from "./avatarApproval";
import * as avatarApprovalModule from "./avatarApproval";

type ApprovalProvenance = {
  sourceCandidateId: string;
  sourceJobId: string;
  sourceGeneration: number;
};

type FakeApprovalFile = {
  copy: (
    destination: unknown,
    options: Record<string, unknown>,
  ) => Promise<unknown>;
  getMetadata: () => Promise<[
    { metadata?: Record<string, unknown> },
    unknown?,
  ]>;
};

type ApprovalCopyContractModule = {
  buildPhase3SourceFileOptions: (
    sourceGeneration: number,
  ) => { generation: number };
  buildPhase3ApprovalCopyOptions: (
    provenance: ApprovalProvenance,
  ) => Record<string, unknown>;
  copyPhase3ApprovedAvatarObject: (params: {
    sourceFile: FakeApprovalFile;
    destinationFile: FakeApprovalFile;
    provenance: ApprovalProvenance;
  }) => Promise<{ created: boolean; reused: boolean }>;
  shouldCleanupCopiedApprovalObject: (params: {
    copiedApprovedObject: boolean;
    finalTransactionReturnedExisting: boolean;
  }) => boolean;
  canAdmitAvatarApproval: (
    candidate: Record<string, unknown>,
    userData: Record<string, unknown>,
    candidateId: string,
  ) => boolean;
};

function approvalCopyContractModule(): ApprovalCopyContractModule {
  return avatarApprovalModule as unknown as ApprovalCopyContractModule;
}

function storageError(code: number): Error & { code: number } {
  const error = new Error(`storage error ${code}`) as Error & { code: number };
  error.code = code;
  return error;
}

function provenance(): ApprovalProvenance {
  return {
    sourceCandidateId: "candidate-001",
    sourceJobId: "job-synthetic-001",
    sourceGeneration: 41,
  };
}

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

test("Phase 3 candidate approval resolves an opaque scratch ref with generation", () => {
  assert.deepEqual(
    resolveAvatarCandidateSource({
      scratchRef: "phase3/run_1/attempt_1/candidate-001.png",
      scratchObjectGeneration: 7,
    }),
    {
      kind: "phase3",
      bucket: "seolleyeon-final-avatar-phase3-scratch",
      path: "phase3/run_1/attempt_1/candidate-001.png",
      generation: 7,
    },
  );
});

test("Phase 3 approval rejects non-opaque scratch refs and invalid generations", () => {
  assert.throws(
    () =>
      resolveAvatarCandidateSource({
        scratchRef: "gs://private/source.png",
        scratchObjectGeneration: 7,
      }),
    /scratch candidate ref/i,
  );
  assert.throws(
    () =>
      resolveAvatarCandidateSource({
        scratchRef: "phase3/run_1/attempt_1/candidate-001.png",
        scratchObjectGeneration: 0,
      }),
    /generation/i,
  );
});

test("Phase 3 approval pins source generation separately from destination create-only precondition", () => {
  const contract = approvalCopyContractModule();
  const sourceOptions = contract.buildPhase3SourceFileOptions(41);
  const copyOptions = contract.buildPhase3ApprovalCopyOptions(provenance());
  const preconditions = copyOptions.preconditionOpts as {
    ifGenerationMatch: number;
  };
  const metadata = copyOptions.metadata as Record<string, unknown>;

  assert.deepEqual(sourceOptions, { generation: 41 });
  assert.equal(preconditions.ifGenerationMatch, 0);
  assert.equal(metadata.sourceGeneration, "41");
  assert.notEqual(preconditions.ifGenerationMatch, 41);
});

test("Phase 3 approval copies a fresh destination with the pinned source contract", async () => {
  const contract = approvalCopyContractModule();
  let copyOptions: Record<string, unknown> | undefined;
  let destinationMetadataReads = 0;
  const sourceFile: FakeApprovalFile = {
    async copy(_destination, options) {
      copyOptions = options;
      return undefined;
    },
    async getMetadata() {
      throw new Error("source metadata must not be read after a successful copy");
    },
  };
  const destinationFile: FakeApprovalFile = {
    async copy() {
      throw new Error("destination must not initiate the copy");
    },
    async getMetadata() {
      destinationMetadataReads += 1;
      throw new Error("destination metadata must not be read after a successful copy");
    },
  };

  const result = await contract.copyPhase3ApprovedAvatarObject({
    sourceFile,
    destinationFile,
    provenance: provenance(),
  });

  assert.deepEqual(result, { created: true, reused: false });
  assert.equal(destinationMetadataReads, 0);
  assert.equal(
    (copyOptions?.preconditionOpts as { ifGenerationMatch: number })
      .ifGenerationMatch,
    0,
  );
});

test("Phase 3 approval fails closed when the pinned source generation is stale", async () => {
  const contract = approvalCopyContractModule();
  let destinationMetadataReads = 0;
  const sourceFile: FakeApprovalFile = {
    async copy() {
      throw storageError(412);
    },
    async getMetadata() {
      throw new Error("source metadata is not an idempotency proof");
    },
  };
  const destinationFile: FakeApprovalFile = {
    async copy() {
      throw new Error("destination must not initiate the copy");
    },
    async getMetadata() {
      destinationMetadataReads += 1;
      throw storageError(404);
    },
  };

  await assert.rejects(
    contract.copyPhase3ApprovedAvatarObject({
      sourceFile,
      destinationFile,
      provenance: provenance(),
    }),
    (error: unknown) =>
      (error as { code?: number }).code === 412 && destinationMetadataReads === 1,
  );
});

test("Phase 3 approval rejects a 412 from an unrelated canonical destination", async () => {
  const contract = approvalCopyContractModule();
  let destinationWrites = 0;
  const sourceFile: FakeApprovalFile = {
    async copy() {
      throw storageError(412);
    },
    async getMetadata() {
      throw new Error("source metadata is not an idempotency proof");
    },
  };
  const destinationFile: FakeApprovalFile = {
    async copy() {
      destinationWrites += 1;
      throw new Error("destination must not initiate the copy");
    },
    async getMetadata() {
      return [
        {
          metadata: {
            purpose: "approved_avatar_display",
            sourceCandidateId: "different-candidate",
            sourceJobId: "different-job",
            sourceGeneration: "999",
          },
        },
      ];
    },
  };

  await assert.rejects(
    contract.copyPhase3ApprovedAvatarObject({
      sourceFile,
      destinationFile,
      provenance: provenance(),
    }),
    (error: unknown) =>
      (error as { code?: string; message?: string }).code ===
        "failed-precondition" &&
      (error as { message?: string }).message ===
        "avatar_canonical_destination_conflict" &&
      destinationWrites === 0,
  );
});

test("Phase 3 approval converges on a same-provenance 412 without overwriting the canonical object", async () => {
  const contract = approvalCopyContractModule();
  let destinationWrites = 0;
  const expected = provenance();
  const sourceFile: FakeApprovalFile = {
    async copy() {
      throw storageError(412);
    },
    async getMetadata() {
      throw new Error("source metadata is not an idempotency proof");
    },
  };
  const destinationFile: FakeApprovalFile = {
    async copy() {
      destinationWrites += 1;
      throw new Error("destination must not initiate the copy");
    },
    async getMetadata() {
      return [
        {
          metadata: {
            purpose: "approved_avatar_display",
            sourceCandidateId: expected.sourceCandidateId,
            sourceJobId: expected.sourceJobId,
            sourceGeneration: String(expected.sourceGeneration),
          },
        },
      ];
    },
  };

  const result = await contract.copyPhase3ApprovedAvatarObject({
    sourceFile,
    destinationFile,
    provenance: expected,
  });

  assert.deepEqual(result, { created: false, reused: true });
  assert.equal(destinationWrites, 0);
});

test("Phase 3 approval cleanup only targets an object created by this attempt", () => {
  const contract = approvalCopyContractModule();

  assert.equal(
    contract.shouldCleanupCopiedApprovalObject({
      copiedApprovedObject: true,
      finalTransactionReturnedExisting: false,
    }),
    true,
  );
  assert.equal(
    contract.shouldCleanupCopiedApprovalObject({
      copiedApprovedObject: false,
      finalTransactionReturnedExisting: false,
    }),
    false,
  );
  assert.equal(
    contract.shouldCleanupCopiedApprovalObject({
      copiedApprovedObject: true,
      finalTransactionReturnedExisting: true,
    }),
    false,
  );
});

test("same approved candidate remains admissible for an idempotent approval retry", () => {
  const contract = approvalCopyContractModule();

  assert.equal(
    contract.canAdmitAvatarApproval(
      {
        status: "approved",
        qa: { previewAllowed: true },
      },
      {
        avatar: {
          status: "approved",
          selectedCandidateId: "candidate-001",
          approvedAvatarUrl: "https://cdn.example/avatar.png",
          avatarId: "avatar_candidate-001",
        },
      },
      "candidate-001",
    ),
    true,
  );
});

test("unapproved candidate still requires the preview-ready admission state", () => {
  const contract = approvalCopyContractModule();

  assert.equal(
    contract.canAdmitAvatarApproval(
      {
        status: "approved",
        qa: { previewAllowed: true },
      },
      { avatar: { status: "none" } },
      "candidate-001",
    ),
    false,
  );
});


test("approval failure releases the job and candidate back to preview_ready", () => {
  // 회귀: 승인 복사가 실패하면 avatarJobs/avatarCandidates 가
  // approval_copying 에 영구히 남아 같은 후보 재승인이 불가능해진다.
  const plan = planApprovalFailureRecovery({
    superseded: false,
    canonicalObjectSurvives: false,
  });
  assert.equal(plan.revertCandidateToPreviewReady, true);
  assert.equal(plan.revertJobToPreviewReady, true);
  assert.equal(plan.recordUserFailure, true);
});

test("approval failure that leaves a canonical object does not release the job", () => {
  const plan = planApprovalFailureRecovery({
    superseded: false,
    canonicalObjectSurvives: true,
  });
  assert.equal(plan.revertJobToPreviewReady, false);
  assert.equal(plan.revertCandidateToPreviewReady, false);
  assert.equal(plan.recordUserFailure, true);
});

test("superseded approval failure releases the candidate but not the job", () => {
  const plan = planApprovalFailureRecovery({
    superseded: true,
    canonicalObjectSurvives: false,
  });
  assert.equal(plan.revertCandidateToPreviewReady, true);
  assert.equal(plan.revertJobToPreviewReady, false);
  assert.equal(plan.recordUserFailure, false);
});

test("a failed approval no longer locks the user out of other candidates", () => {
  // approval_copy_failed 는 진행 중 잠금이 아니라 실패 기록이어야 한다.
  const plan = planAvatarApprovalState(
    {
      avatar: {
        status: "approval_copy_failed",
        selectedCandidateId: "cand_first",
      },
    },
    "cand_second",
  );
  assert.equal(plan.action, "reserve");
});

test("an in-progress approval still conflicts for a different candidate", () => {
  const plan = planAvatarApprovalState(
    {
      avatar: {
        status: "approval_copying",
        selectedCandidateId: "cand_first",
      },
    },
    "cand_second",
  );
  assert.equal(plan.action, "conflict");
});
