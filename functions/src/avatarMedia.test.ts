import assert from "node:assert/strict";
import test from "node:test";

import {
  buildCurrentAvatarGenerationStatusResponse,
  buildSourceSetRetryPlan,
  readCurrentAvatarContract,
  previewCandidateAvailableFromCandidate,
  avatarPresentationGenderFromUserData,
  buildChatRealPhotoMetadata,
  buildClipPayload,
  buildCloudTaskHttpRequest,
  buildDeterministicCloudTaskName,
  buildDisabledChatRealPhotoMetadata,
  cloudTaskDispatchDeadlineSeconds,
  buildPrivateMediaPayload,
  isCloudTasksAlreadyExistsError,
  queueMode,
  shouldSupersedeAvatarJobStatus,
  summarizeQueueWriteState,
  queueMode as queueModeExport,
} from "./avatarMedia";

function withEnv(env: Record<string, string | undefined>, run: () => void) {
  const previous: Record<string, string | undefined> = {};
  for (const key of Object.keys(env)) {
    previous[key] = process.env[key];
    const value = env[key];
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
  try {
    run();
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  }
}

test("cloud task names are deterministic per idempotency key", () => {
  const queueName =
    "projects/p/locations/asia-northeast3/queues/avatar-generation";
  const first = buildDeterministicCloudTaskName(
    queueName,
    "avatar_generation",
    "u1:src_abc:avatar_generation_v1",
  );
  const second = buildDeterministicCloudTaskName(
    queueName,
    "avatar_generation",
    "u1:src_abc:avatar_generation_v1",
  );

  assert.equal(first, second);
  assert.match(first, /\/tasks\/avatar-generation-[a-f0-9]{32}$/);
});

test("cloud task already-exists error is idempotent success", () => {
  assert.equal(isCloudTasksAlreadyExistsError({ code: 6 }), true);
  assert.equal(isCloudTasksAlreadyExistsError({ code: 5 }), false);
});

test("dry-run queue results are not recorded as enqueued", () => {
  const state = summarizeQueueWriteState({
    avatar: { mode: "dry_run", status: "dry_run" },
    clip: { mode: "dry_run", status: "dry_run" },
  });

  assert.equal(state.queueMode, "dry_run");
  assert.equal(state.queueStatus, "dry_run");
});

test("real queue dispatch results are recorded as enqueued", () => {
  const state = summarizeQueueWriteState({
    avatar: { mode: "cloud_tasks", status: "enqueued" },
    clip: { mode: "cloud_tasks", status: "already_exists" },
  });

  assert.equal(state.queueMode, "cloud_tasks");
  assert.equal(state.queueStatus, "enqueued");
});

test("avatar dispatch can be recorded as enqueued when optional clip enqueue is disabled", () => {
  const state = summarizeQueueWriteState({
    avatar: { mode: "cloud_tasks", status: "enqueued" },
    clip: { status: "skipped_disabled" },
  });

  assert.equal(state.queueMode, "cloud_tasks");
  assert.equal(state.queueStatus, "enqueued");
});

test("avatar presentation gender ignores non-onboarding profile gender", () => {
  assert.equal(
    avatarPresentationGenderFromUserData({
      gender: "female",
      onboarding: {},
    }),
    "unknown",
  );
  assert.equal(
    avatarPresentationGenderFromUserData({
      gender: "female",
      onboarding: { gender: "male" },
    }),
    "male",
  );
});

test("only non-terminal avatar jobs are superseded by a new current selection", () => {
  assert.equal(shouldSupersedeAvatarJobStatus("queued"), true);
  assert.equal(shouldSupersedeAvatarJobStatus("running"), true);
  assert.equal(shouldSupersedeAvatarJobStatus("preview_ready"), true);
  assert.equal(shouldSupersedeAvatarJobStatus("approved"), false);
  assert.equal(shouldSupersedeAvatarJobStatus("failed"), false);
  assert.equal(shouldSupersedeAvatarJobStatus("cancelled"), false);
  assert.equal(shouldSupersedeAvatarJobStatus("superseded"), false);
});

test("private media payload stores current avatar source contract", () => {
  const payload = buildPrivateMediaPayload(
    [
      {
        photoId: "src_abc",
        gcsUri:
          "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg",
        status: "active",
        avatarGenerationState: "current",
      },
    ],
    {
      currentAvatarSourcePhotoId: "src_abc",
      currentAvatarJobId: "avatar_job_abc",
      avatarSourceSelectionVersion: 2,
    },
  );

  assert.equal(payload.currentAvatarSourcePhotoId, "src_abc");
  assert.equal(payload.currentAvatarJobId, "avatar_job_abc");
  assert.equal(payload.avatarSourceSelectionVersion, 2);
});

test("private media payload records chat real-photo consent explicitly", () => {
  const chatRealPhoto = buildChatRealPhotoMetadata({
    uid: "u1",
    photoId: "src_abc",
    sizeBytes: 1234,
    updatedAt: "now",
  });
  const payload = buildPrivateMediaPayload(
    [
      {
        photoId: "src_abc",
        gcsUri:
          "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg",
        status: "active",
      },
    ],
    {
      chatPartnerRealPhotoDisclosure: true,
      chatRealPhoto,
    },
  );

  assert.equal(payload.photoConsent.chatPartnerRealPhotoDisclosure, true);
  assert.equal(payload.photoConsent.profileDisplayOriginalPhoto, false);
  assert.equal(payload.photoConsent.version, "photo_consent_v4");
  assert.equal(payload.chatRealPhoto.enabled, true);
  assert.equal(
    payload.chatRealPhoto.storageBucket,
    "seolleyeon-final-chat-profile-photos",
  );
  assert.equal(
    payload.chatRealPhoto.gcsUri?.startsWith(
      "gs://seolleyeon-final-chat-profile-photos/",
    ),
    true,
  );
});

test("disabled chat real-photo metadata contains no storage refs", () => {
  const payload = buildPrivateMediaPayload([], {
    chatPartnerRealPhotoDisclosure: false,
    chatRealPhoto: buildDisabledChatRealPhotoMetadata("now"),
  });

  assert.equal(payload.photoConsent.chatPartnerRealPhotoDisclosure, false);
  assert.equal(payload.chatRealPhoto.enabled, false);
  assert.equal(payload.chatRealPhoto.storageBucket, undefined);
  assert.equal(payload.chatRealPhoto.gcsUri, undefined);
});

test("production queue mode must be explicitly configured and cannot dry-run", () => {
  withEnv(
    {
      ENVIRONMENT: "production",
      JOB_QUEUE_MODE: undefined,
    },
    () => {
      assert.throws(() => queueMode(), /explicitly configured/);
    },
  );

  withEnv(
    {
      ENVIRONMENT: "production",
      JOB_QUEUE_MODE: "dry_run",
    },
    () => {
      assert.throws(() => queueMode(), /not allowed/);
    },
  );

  withEnv(
    {
      ENVIRONMENT: "production",
      JOB_QUEUE_MODE: "cloud_tasks",
    },
    () => {
      assert.equal(queueMode(), "cloud_tasks");
    },
  );
});

test("production Cloud Tasks HTTP target includes OIDC token", () => {
  const payload = buildClipPayload(
    "u1",
    "src_abc",
    "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg",
  );

  withEnv(
    {
      ENVIRONMENT: "production",
      TASK_INVOKER_SERVICE_ACCOUNT:
        "task-invoker@example.iam.gserviceaccount.com",
      TASK_OIDC_AUDIENCE: "https://worker.example",
      ALLOW_INSECURE_WORKER_LOCAL: undefined,
    },
    () => {
      const request = buildCloudTaskHttpRequest(
        "https://worker.example/tasks/clip-embedding",
        payload,
      );

      assert.equal(
        request.oidcToken?.serviceAccountEmail,
        "task-invoker@example.iam.gserviceaccount.com",
      );
      assert.equal(request.oidcToken?.audience, "https://worker.example");
    },
  );
});

test("cloud task dispatch deadline is configurable and bounded", () => {
  withEnv({ AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS: undefined }, () => {
    assert.equal(cloudTaskDispatchDeadlineSeconds(), 900);
  });
  withEnv({ AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS: "900" }, () => {
    assert.equal(cloudTaskDispatchDeadlineSeconds(), 900);
  });
  withEnv({ AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS: "5" }, () => {
    assert.equal(cloudTaskDispatchDeadlineSeconds(), 60);
  });
  withEnv({ AVATAR_QUEUE_DISPATCH_DEADLINE_SECONDS: "3600" }, () => {
    assert.equal(cloudTaskDispatchDeadlineSeconds(), 1800);
  });
});


const RESUME_UID = "uid_resume_1";
const RESUME_PHOTO_ID = "src_resume_abc";
const RESUME_JOB_ID = "avatar_job_resume_abc";

function currentStatusFixture(
  jobStatus: string,
  extra: Record<string, unknown> = {},
) {
  return {
    privateData: {
      currentAvatarSourcePhotoId: RESUME_PHOTO_ID,
      currentAvatarJobId: RESUME_JOB_ID,
      avatarSourceSelectionVersion: 3,
      sourcePhotos: [
        {
          photoId: RESUME_PHOTO_ID,
          status: "active",
          avatarGenerationState: "current",
        },
      ],
    },
    userData: { avatar: { status: jobStatus } },
    jobData: {
      uid: RESUME_UID,
      jobId: RESUME_JOB_ID,
      sourcePhotoIds: [RESUME_PHOTO_ID],
      avatarSourceSelectionVersion: 3,
      status: jobStatus,
      ...extra,
    },
    candidatesAvailable: false,
    uid: RESUME_UID,
  };
}

test("in-flight worker states are not reported as terminal failure", () => {
  // 워커는 provider_inflight / generated / persisted 를 실제로 기록한다.
  // 이 값들이 terminal_failed 로 접히면, 유료 Azure 생성이 진행 중인 사용자에게
  // 거짓 최종 실패가 표시된다.
  for (const status of ["provider_inflight", "generated", "persisted"]) {
    const response = buildCurrentAvatarGenerationStatusResponse(
      currentStatusFixture(status),
    );
    assert.notEqual(
      response.status,
      "terminal_failed",
      `${status} must not collapse to terminal_failed`,
    );
    assert.equal(response.retryAllowed, false, `${status} is not retryable`);
  }
});

test("approval_copying is not reported as terminal failure", () => {
  const response = buildCurrentAvatarGenerationStatusResponse(
    currentStatusFixture("approval_copying"),
  );
  assert.notEqual(response.status, "terminal_failed");
  assert.equal(response.retryAllowed, false);
});

test("provider post-send unknown is separated from QA needs_review", () => {
  // 두 상태는 의미가 다르다. 하나는 유료 생성이 이미 일어났을 수 있고,
  // 다른 하나는 생성/후보가 확정된 채 QA 만 자동 통과하지 못한 것이다.
  const unknown = buildCurrentAvatarGenerationStatusResponse(
    currentStatusFixture("needs_review", {
      errorCode: "azure_unknown_post_send_outcome",
      generationClaim: { state: "active" },
    }),
  );
  assert.equal(unknown.status, "reconciliation_required");
  assert.equal(unknown.retryAllowed, false);
  assert.equal(unknown.safeReasonCode, "avatar_provider_outcome_unknown");

  const qaReview = buildCurrentAvatarGenerationStatusResponse(
    currentStatusFixture("needs_review", { errorCode: "qa_requires_review" }),
  );
  assert.equal(qaReview.status, "needs_review");
  assert.equal(qaReview.retryAllowed, false);
});

test("soft needs_review candidate counts as available without becoming QA pass", () => {
  const softReviewCandidate = {
    status: "needs_review",
    qa: {
      previewAllowed: false,
      selectedForPreview: false,
      requiresHumanReview: true,
      reviewTier: "soft_review",
      reviewReasons: ["logo_review"],
    },
  };

  assert.equal(previewCandidateAvailableFromCandidate(softReviewCandidate), true);
  const response = buildCurrentAvatarGenerationStatusResponse({
    ...currentStatusFixture("needs_review", { errorCode: "qa_requires_review" }),
    candidatesAvailable: true,
  });
  assert.equal(response.status, "needs_review");
  assert.equal(response.candidateAvailability, "preview_safe");
});

test("hard-review candidate is not available for preview", () => {
  assert.equal(
    previewCandidateAvailableFromCandidate({
      status: "needs_review",
      qa: {
        previewAllowed: false,
        selectedForPreview: false,
        requiresHumanReview: true,
        reviewTier: "hard_review",
        reviewReasons: ["watermark_artifact_review"],
      },
    }),
    false,
  );
});

test("the source-set dispatch failure code reaches the client", () => {
  // 새 source-set 경로가 쓰는 코드가 허용 목록에 없으면 null 로 잘려
  // 사용자와 운영자 모두 이유를 잃는다.
  const response = buildCurrentAvatarGenerationStatusResponse(
    currentStatusFixture("retryable_failed", {
      errorCode: "avatar_queue_dispatch_failed",
    }),
  );
  assert.equal(response.safeReasonCode, "avatar_queue_dispatch_failed");
});

// ---------------------------------------------------------------------------
// CANONICAL ADMISSION (2026-09-05 product decision)
//   photo upload -> no generation lock; generation submit -> selection -> lock
// ---------------------------------------------------------------------------

test("a pending source selection is a legal intermediate contract, not an inconsistency", () => {
  // Phase A (Functions) writes the job pointer; Phase B (worker) chooses the
  // source and writes the source pointer. In between the XOR is legal.
  const contract = readCurrentAvatarContract({
    currentAvatarJobId: RESUME_JOB_ID,
    avatarSourceSelectionVersion: 3,
    avatarSourceSelection: { status: "pending" },
    sourcePhotos: [
      { photoId: "src_a", status: "active", avatarGenerationState: "selection_candidate" },
      { photoId: "src_b", status: "active", avatarGenerationState: "selection_candidate" },
    ],
  });
  assert.equal(contract.sourceLocked, true);
  assert.equal(contract.sourceSelecting, true);
  assert.equal(contract.jobId, RESUME_JOB_ID);
  assert.equal(contract.sourceId, null);

  // Without an explicit selection state the XOR is still an inconsistency.
  assert.throws(
    () => readCurrentAvatarContract({ currentAvatarJobId: RESUME_JOB_ID }),
    (error: unknown) => error instanceof Error && error.message.includes("avatar_state_inconsistent"),
  );
});

function sourceSetStatusFixture(
  jobStatus: string,
  selectionStatus: "pending" | "failed" | "selected",
  extra: Record<string, unknown> = {},
) {
  const privateData: Record<string, unknown> = {
    currentAvatarJobId: RESUME_JOB_ID,
    avatarSourceSelectionVersion: 2,
    avatarSourceSelection: { status: selectionStatus },
    sourcePhotos: [
      { photoId: "src_a", status: "active", avatarGenerationState: "selection_candidate" },
      { photoId: "src_b", status: "active", avatarGenerationState: "selection_candidate" },
    ],
  };
  if (selectionStatus === "selected") {
    privateData.currentAvatarSourcePhotoId = "src_b";
    (privateData.sourcePhotos as Record<string, unknown>[])[1].avatarGenerationState = "current";
  }
  return {
    privateData,
    userData: { avatar: { status: jobStatus } },
    jobData: {
      uid: RESUME_UID,
      jobId: RESUME_JOB_ID,
      sourcePhotoIds: selectionStatus === "selected" ? ["src_b"] : ["src_a", "src_b"],
      sourcePhotoRefs:
        selectionStatus === "selected"
          ? ["gs://b/users/u/source/src_b.jpg"]
          : ["gs://b/users/u/source/src_a.jpg", "gs://b/users/u/source/src_b.jpg"],
      sourcePhotoObjectGenerations: selectionStatus === "selected" ? ["22"] : ["11", "22"],
      sourceSelectionCandidates: [
        { photoId: "src_a", gcsUri: "gs://b/users/u/source/src_a.jpg", objectGeneration: "11", stableOrder: 0 },
        { photoId: "src_b", gcsUri: "gs://b/users/u/source/src_b.jpg", objectGeneration: "22", stableOrder: 1 },
      ],
      sourceSelectionMode: "quality_selector_v1",
      sourceSelection: { status: selectionStatus },
      avatarSourceSelectionVersion: 2,
      consentPurposes: { avatarGeneration: true, clipRecommendation: false, sourcePhotoRetention: false },
      avatarPresentationGender: "female",
      status: jobStatus,
      ...extra,
    },
    candidatesAvailable: false,
    uid: RESUME_UID,
  };
}

test("source selection in progress is reported as source_selecting, never terminal", () => {
  for (const jobStatus of ["queued", "running"]) {
    const response = buildCurrentAvatarGenerationStatusResponse(
      sourceSetStatusFixture(jobStatus, "pending"),
    );
    assert.equal(response.status, "source_selecting", `${jobStatus} while selecting`);
    assert.equal(response.sourceLocked, true);
    assert.equal(response.retryAllowed, false);
    assert.equal(response.jobId, RESUME_JOB_ID);
  }
});

test("a failed source selection keeps the retryability recorded on the job", () => {
  const infra = buildCurrentAvatarGenerationStatusResponse(
    sourceSetStatusFixture("retryable_failed", "failed", {
      errorCode: "avatar_source_analysis_infra_failure",
      retryable: true,
    }),
  );
  assert.equal(infra.status, "retryable_failed");
  assert.equal(infra.retryAllowed, true);
});

test("a selected source-set job reports like any locked job", () => {
  const response = buildCurrentAvatarGenerationStatusResponse(
    sourceSetStatusFixture("running", "selected"),
  );
  assert.equal(response.status, "running");
  assert.equal(response.sourceLocked, true);
});

test("source-set retry re-dispatches the same job without a new job id or selector rerun", () => {
  const failed = sourceSetStatusFixture("retryable_failed", "failed", {
    errorCode: "avatar_source_analysis_infra_failure",
    retryable: true,
    retryCount: 0,
  }).jobData;
  const plan = buildSourceSetRetryPlan({
    uid: RESUME_UID,
    jobId: RESUME_JOB_ID,
    currentJobData: failed,
    clientRequestId: "retry-ss-0001",
  });
  assert.equal(plan.allowed, true);
  if (!plan.allowed) return;
  assert.equal(plan.replay, false);
  // Selection failed before any source was locked: the selector must run
  // again over the full candidate set.
  assert.deepEqual(plan.payload.sourcePhotoIds, ["src_a", "src_b"]);
  assert.equal(plan.payload.jobId, RESUME_JOB_ID);
  assert.equal(plan.payload.sourceSelectionMode, "quality_selector_v1");
  assert.equal(plan.payload.candidateCount, 2);
  assert.equal(plan.payload.idempotencyKey, `${RESUME_UID}:${RESUME_JOB_ID}:avatar_generation_source_set_retry_v1`);
  assert.equal(plan.jobUpdate.status, "queued");
  assert.equal(plan.jobUpdate.retryCount, 1);

  // Once a source is locked, retry pins that single source: no selector rerun.
  const lockedFailed = sourceSetStatusFixture("retryable_failed", "selected", {
    errorCode: "azure_rate_limit_timeout",
    retryable: true,
    retryCount: 1,
    selectedSource: { photoId: "src_b", gcsUri: "gs://b/users/u/source/src_b.jpg", objectGeneration: "22" },
  }).jobData;
  const locked = buildSourceSetRetryPlan({
    uid: RESUME_UID,
    jobId: RESUME_JOB_ID,
    currentJobData: lockedFailed,
    clientRequestId: "retry-ss-0002",
  });
  assert.equal(locked.allowed, true);
  if (!locked.allowed) return;
  assert.deepEqual(locked.payload.sourcePhotoIds, ["src_b"]);
  assert.equal(locked.payload.idempotencyKey, `${RESUME_UID}:${RESUME_JOB_ID}:avatar_generation_source_set_retry_v2`);
});

test("source-set retry refuses terminal, ambiguous, and in-flight jobs and honours the limit", () => {
  for (const [status, extra] of [
    // 사진 자체가 부적합해서 끝난 실패만 재시도 불가다.
    ["terminal_failed", { failureClass: "content_terminal" }],
    ["needs_review", { errorCode: "azure_unknown_post_send_outcome", generationClaim: { state: "active" } }],
    ["needs_review", { errorCode: "qa_requires_review" }],
    ["queued", {}],
    ["provider_inflight", {}],
    ["approved", {}],
  ] as const) {
    const plan = buildSourceSetRetryPlan({
      uid: RESUME_UID,
      jobId: RESUME_JOB_ID,
      currentJobData: sourceSetStatusFixture(status, "pending", extra).jobData,
      clientRequestId: "retry-ss-0003",
    });
    assert.equal(plan.allowed, false, `${status} must not be retryable`);
  }
  // 인프라 실패는 같은 사진으로 다시 시도할 수 있어야 한다. 사진을 바꾸라고
  // 안내하면 사용자는 고쳐지지 않는 문제를 자기 탓으로 되풀이한다.
  for (const extra of [
    { failureClass: "infrastructure_recoverable" },
    {}, // 분류가 없는 레거시 실패도 사진 탓으로 단정하지 않는다.
  ]) {
    const infrastructure = buildSourceSetRetryPlan({
      uid: RESUME_UID,
      jobId: RESUME_JOB_ID,
      currentJobData: sourceSetStatusFixture("failed", "failed", extra).jobData,
      clientRequestId: "retry-ss-0005",
    });
    assert.equal(infrastructure.allowed, true);
  }

  const exhausted = buildSourceSetRetryPlan({
    uid: RESUME_UID,
    jobId: RESUME_JOB_ID,
    currentJobData: sourceSetStatusFixture("retryable_failed", "failed", { retryable: true, retryCount: 2 }).jobData,
    clientRequestId: "retry-ss-0004",
  });
  assert.equal(exhausted.allowed, false);
  if (exhausted.allowed) return;
  assert.equal(exhausted.reasonCode, "avatar_retry_limit_reached");
});

test("source-set retry with the same clientRequestId is a replay, not a second dispatch", () => {
  const plan = buildSourceSetRetryPlan({
    uid: RESUME_UID,
    jobId: RESUME_JOB_ID,
    currentJobData: sourceSetStatusFixture("queued", "pending", {
      retryClientRequestId: "retry-ss-0005",
      retryCount: 1,
      queueStatus: "enqueued",
    }).jobData,
    clientRequestId: "retry-ss-0005",
  });
  assert.equal(plan.allowed, true);
  if (!plan.allowed) return;
  assert.equal(plan.replay, true);
  assert.equal(plan.shouldEnqueue, false);
});

test("local insecure Cloud Tasks bypass requires the explicit local flag (shared dispatch contract)", () => {
  const payload = {
    jobId: "avatar_job_local_bypass",
    uid: "uid_local",
    sourcePhotoIds: ["src_a", "src_b"],
    sourcePhotoRefs: ["gs://b/users/u/source/src_a.jpg", "gs://b/users/u/source/src_b.jpg"],
    jobType: "avatar_generation",
    schemaVersion: "avatar_job_v1",
    idempotencyKey: "uid_local:avatar_job_local_bypass:avatar_generation_source_set_v1",
  };
  withEnv({ ENVIRONMENT: "local", TASK_INVOKER_SERVICE_ACCOUNT: undefined, ALLOW_INSECURE_WORKER_LOCAL: undefined, AVATAR_WORKER_ALLOW_INSECURE_LOCAL: undefined }, () => {
    assert.throws(() => buildCloudTaskHttpRequest("http://localhost:8080/tasks/avatar-generation", payload));
  });
  withEnv({ ENVIRONMENT: "local", TASK_INVOKER_SERVICE_ACCOUNT: undefined, ALLOW_INSECURE_WORKER_LOCAL: "true" }, () => {
    const request = buildCloudTaskHttpRequest("http://localhost:8080/tasks/avatar-generation", payload);
    assert.equal(request.oidcToken, undefined);
  });
});

/**
 * 프로덕션 인시던트 회귀. Storage 403 은 사진 문제가 아니라 서버 문제였는데
 * 클라이언트에는 "이 사진으로는 아바타를 만들 수 없어요" 로 표시됐다.
 */
test("infrastructure failures are reported as retryable, not as a photo problem", () => {
  const response = buildCurrentAvatarGenerationStatusResponse(
    sourceSetStatusFixture("failed", "selected", {
      failureClass: "infrastructure_recoverable",
      errorCode: "avatar_generation_worker_error",
    }),
  );

  assert.equal(response.status, "retryable_failed");
  assert.equal(response.safeReasonCode, "avatar_generation_infrastructure_failed");
  assert.equal(response.retryAllowed, true);
  assert.equal(response.sourceAvailable, true);
});

test("unclassified legacy failures do not blame the photo either", () => {
  const response = buildCurrentAvatarGenerationStatusResponse(
    sourceSetStatusFixture("failed", "selected", {
      errorCode: "avatar_generation_worker_error",
    }),
  );

  assert.equal(response.status, "retryable_failed");
  assert.equal(response.safeReasonCode, "avatar_generation_infrastructure_failed");
});

test("content-terminal failures stay terminal and are not retryable", () => {
  const response = buildCurrentAvatarGenerationStatusResponse(
    sourceSetStatusFixture("failed", "selected", {
      failureClass: "content_terminal",
      errorCode: "avatar_source_face_too_small",
    }),
  );

  assert.equal(response.status, "terminal_failed");
  assert.equal(response.retryAllowed, false);
  assert.equal(response.safeReasonCode, "avatar_source_face_too_small");
});

test("provider-ambiguous failures reconcile instead of retrying", () => {
  const response = buildCurrentAvatarGenerationStatusResponse(
    sourceSetStatusFixture("failed", "selected", {
      failureClass: "provider_ambiguous",
    }),
  );

  assert.equal(response.status, "reconciliation_required");
  assert.equal(response.retryAllowed, false);
});

/**
 * 원본이 이미 삭제된 과거 인시던트 작업. 재시도 버튼을 띄우면 사용자는 반드시
 * 실패하는 버튼을 누르게 된다.
 */
test("a job whose source was already deleted never offers a same-photo retry", () => {
  const fixture = sourceSetStatusFixture("failed", "selected", {
    failureClass: "infrastructure_recoverable",
  });
  const photos = (fixture.privateData as Record<string, unknown>)
    .sourcePhotos as Record<string, unknown>[];
  photos[1].status = "source_deleted";

  const response = buildCurrentAvatarGenerationStatusResponse(fixture);

  assert.equal(response.retryAllowed, false);
  assert.equal(response.sourceAvailable, false);
  assert.equal(response.safeReasonCode, "avatar_state_inconsistent");
});

/**
 * 배포된 런타임에서 JOB_QUEUE_MODE 가 빠지면 큰 소리로 실패해야 한다.
 *
 * 예전 계약은 `ENVIRONMENT` 문자열에만 의존했다. 프로덕션 Functions 는
 * `ENVIRONMENT=staging` 으로 떠 있어서, 큐 설정이 사라지면 예외 대신 조용히
 * dry_run 으로 떨어질 수 있었다. 실제로 2026-09-08 배포에서 env 파일이
 * 불완전해 JOB_QUEUE_MODE 가 통째로 사라진 적이 있다. 조용한 fallback 은
 * "작업을 큐에 넣었다"고 보고하면서 아무것도 넣지 않는다.
 */
function cloudRuntime(extra: Record<string, string | undefined> = {}) {
  return {
    K_SERVICE: "retrycurrentavatargeneration",
    K_REVISION: "retrycurrentavatargeneration-00008-cip",
    FUNCTION_TARGET: "retryCurrentAvatarGeneration",
    FUNCTIONS_EMULATOR: undefined,
    NODE_ENV: undefined,
    ...extra,
  };
}

function localRuntime(extra: Record<string, string | undefined> = {}) {
  return {
    K_SERVICE: undefined,
    K_REVISION: undefined,
    FUNCTION_TARGET: undefined,
    FUNCTIONS_EMULATOR: undefined,
    NODE_ENV: undefined,
    ...extra,
  };
}

test("a deployed runtime never silently falls back to dry_run", () => {
  for (const environment of ["staging", "production", undefined, "", "anything"]) {
    withEnv(
      cloudRuntime({ JOB_QUEUE_MODE: undefined, ENVIRONMENT: environment }),
      () => {
        assert.throws(
          () => queueModeExport(),
          /JOB_QUEUE_MODE/,
          `ENVIRONMENT=${String(environment)} must still fail closed`,
        );
      },
    );
  }
});

test("a deployed runtime with an explicit queue mode keeps working", () => {
  withEnv(
    cloudRuntime({ JOB_QUEUE_MODE: "cloud_tasks", ENVIRONMENT: "staging" }),
    () => {
      assert.equal(queueModeExport(), "cloud_tasks");
    },
  );
});

test("the emulator keeps its local dry_run default", () => {
  withEnv(
    cloudRuntime({
      JOB_QUEUE_MODE: undefined,
      FUNCTIONS_EMULATOR: "true",
      ENVIRONMENT: "local",
    }),
    () => {
      assert.equal(queueModeExport(), "dry_run");
    },
  );
  withEnv(
    localRuntime({ JOB_QUEUE_MODE: undefined, ENVIRONMENT: "local" }),
    () => {
      assert.equal(queueModeExport(), "dry_run");
    },
  );
});

test("an explicit local dry_run stays allowed", () => {
  withEnv(
    localRuntime({ JOB_QUEUE_MODE: "dry_run", ENVIRONMENT: "local" }),
    () => {
      assert.equal(queueModeExport(), "dry_run");
    },
  );
});

test("an explicit dry_run is still refused in a production environment", () => {
  withEnv(
    cloudRuntime({ JOB_QUEUE_MODE: "dry_run", ENVIRONMENT: "production" }),
    () => {
      assert.throws(() => queueModeExport(), /dry_run/);
    },
  );
});
