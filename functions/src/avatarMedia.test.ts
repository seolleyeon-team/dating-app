import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAvatarPayload,
  avatarPresentationGenderFromUserData,
  buildChatRealPhotoMetadata,
  buildAvatarSourceRecoveryUserFields,
  buildClipPayload,
  buildCloudTaskHttpRequest,
  buildDeterministicCloudTaskName,
  buildDisabledChatRealPhotoMetadata,
  cloudTaskDispatchDeadlineSeconds,
  buildPrivateMediaPayload,
  hasLockedAvatarSource,
  isCloudTasksAlreadyExistsError,
  planAvatarUploadState,
  queueMode,
  shouldSupersedeAvatarJobStatus,
  summarizeQueueWriteState,
  upsertSourcePhotoEntry,
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

test("duplicate preview_ready current upload returns existing preview state", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "preview_ready",
    userAvatar: { status: "preview_ready" },
    duplicate: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.shouldSetUserAvatarQueued, false);
  assert.equal(plan.responseAvatarStatus, "preview_ready");
  assert.equal(plan.responseMessage, "avatar_generation_preview_ready");
});

test("duplicate completed current upload does not create queued writes", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "completed",
    userAvatar: { status: "queued" },
    duplicate: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.responseAvatarStatus, "completed");
  assert.equal(plan.responseMessage, "avatar_generation_completed");
});

test("duplicate queued dry-run job is re-enqueued after queue config is fixed", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "queued",
    existingQueueMode: "dry_run",
    existingQueueStatus: "enqueued",
    userAvatar: {},
    duplicate: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, true);
  assert.equal(plan.shouldSetUserAvatarQueued, true);
  assert.equal(plan.responseAvatarStatus, "queued");
});

test("duplicate queued current upload is not enqueued again", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "queued",
    existingQueueMode: "cloud_tasks",
    existingQueueStatus: "enqueued",
    userAvatar: { status: "queued" },
    duplicate: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.shouldSetUserAvatarQueued, false);
  assert.equal(plan.responseAvatarStatus, "queued");
  assert.equal(plan.responseMessage, "avatar_generation_queued");
});

test("approved avatar lock rejects duplicate upload without queue regression", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "approved",
    userAvatar: {
      status: "approved",
      approvedAvatarUrl: "https://cdn.example/avatar.png",
    },
    duplicate: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.shouldSetUserAvatarQueued, false);
  assert.equal(plan.responseAvatarStatus, "approved");
  assert.equal(plan.responseMessage, "avatar_already_approved");
  assert.equal(plan.approvedAvatarUrl, "https://cdn.example/avatar.png");
});

test("locked avatar source rejects duplicate upload without queue writes", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "preview_ready",
    userAvatar: { status: "preview_ready" },
    duplicate: true,
    sourceLocked: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.shouldSetUserAvatarQueued, false);
  assert.equal(plan.responseAvatarStatus, "preview_ready");
  assert.equal(plan.responseMessage, "avatar_source_locked");
});

test("failed current avatar source remains locked against new upload bytes", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "failed",
    userAvatar: { status: "failed" },
    duplicate: false,
    sourceLocked: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.shouldSetUserAvatarQueued, false);
  assert.equal(plan.responseAvatarStatus, "failed");
  assert.equal(plan.responseMessage, "avatar_source_locked");
});

test("explicit internal retry plan can requeue failed job only when source is not locked", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "failed",
    userAvatar: { status: "failed" },
    duplicate: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, true);
  assert.equal(plan.shouldEnqueue, true);
  assert.equal(plan.shouldSetUserAvatarQueued, true);
  assert.equal(plan.responseAvatarStatus, "queued");
  assert.equal(plan.responseMessage, "avatar_generation_queued");
});

test("approved user avatar lock prevents upload retry job writes", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "failed",
    userAvatar: {
      status: "approved",
      approvedAvatarUrl: "https://cdn.example/avatar.png",
    },
    duplicate: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.shouldSetUserAvatarQueued, false);
  assert.equal(plan.responseMessage, "avatar_already_approved");
});

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

test("queue payload builders include idempotency keys", () => {
  const avatar = buildAvatarPayload(
    "u1",
    "src_abc",
    "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg",
    "avatar_job_1",
  );
  const clip = buildClipPayload(
    "u1",
    "src_abc",
    "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg",
    {
      avatarGeneration: true,
      clipRecommendation: true,
      sourcePhotoRetention: false,
    },
  );

  assert.equal(avatar.idempotencyKey, "u1:src_abc:avatar_generation_v1");
  assert.ok(clip);
  assert.equal(clip.idempotencyKey, "u1:src_abc:clip_embedding_v1");
});

test("avatar payload normalizes onboarding gender for private worker guidance", () => {
  const avatar = buildAvatarPayload(
    "u1",
    "src_abc",
    "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg",
    "avatar_job_1",
    "여성",
  );

  assert.equal(avatar.avatarPresentationGender, "female");
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

test("approved avatar status locks upload even when approved url needs repair", () => {
  const plan = planAvatarUploadState({
    existingJobExists: false,
    existingJobStatus: "",
    existingQueueMode: "",
    existingQueueStatus: "",
    userAvatar: {
      status: "approved",
      approvedAvatarUrl:
        "gs://seolleyeon-final-private-source-photos/users/u/source/src.jpg",
    },
    duplicate: false,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.responseAvatarStatus, "approved");
  assert.equal(plan.responseMessage, "avatar_already_approved");
  assert.equal(plan.approvedAvatarUrl, undefined);
});

test("approved avatar lock response suppresses private or signed url variants", () => {
  const unsafeUrls = [
    "https://storage.googleapis.com/seolleyeon-final-private-source-photos/users/u/source/src.jpg",
    "https://seolleyeon-final-private-source-photos.storage.googleapis.com/users/u/source/src.jpg",
    "https://storage.googleapis.com/seolleyeon-final-avatar-temp/jobs/job/candidates/c.jpg",
    "https://seolleyeon-final-avatar-temp.storage.googleapis.com/jobs/job/candidates/c.jpg",
    "https://storage.googleapis.com/seolleyeon-final-chat-profile-photos/users/u/chat/profile.jpg",
    "https://cdn.example/avatar.png?x-goog-signature=abc",
    "https://cdn.example/avatar.png?GoogleAccessId=abc",
    "https://cdn.example/%2Fjobs%2Fjob%2Fcandidates%2Fc.jpg",
    "https://cdn.example/users/u/source/src.jpg",
    "not-a-url-but-signedUrl=true",
  ];

  for (const approvedAvatarUrl of unsafeUrls) {
    const plan = planAvatarUploadState({
      existingJobExists: false,
      existingJobStatus: "",
      existingQueueMode: "",
      existingQueueStatus: "",
      userAvatar: {
        status: "approved",
        approvedAvatarUrl,
      },
      duplicate: false,
    });

    assert.equal(plan.shouldWriteQueuedJob, false, approvedAvatarUrl);
    assert.equal(plan.shouldEnqueue, false, approvedAvatarUrl);
    assert.equal(plan.responseAvatarStatus, "approved", approvedAvatarUrl);
    assert.equal(
      plan.responseMessage,
      "avatar_already_approved",
      approvedAvatarUrl,
    );
    assert.equal(plan.approvedAvatarUrl, undefined, approvedAvatarUrl);
  }
});

test("approved avatar url alone locks upload retries", () => {
  const plan = planAvatarUploadState({
    existingJobExists: false,
    existingJobStatus: "",
    userAvatar: {
      approvedAvatarUrl: "https://cdn.example/avatar.png",
    },
    duplicate: false,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.responseAvatarStatus, "approved");
  assert.equal(plan.responseMessage, "avatar_already_approved");
});

test("avatar source recovery user fields expose only safe job metadata", () => {
  const fields = buildAvatarSourceRecoveryUserFields(
    "avatar_job_abc123DEF_456",
    3,
  );

  assert.deepEqual(fields, {
    "onboarding.avatarGenerationJobId": "avatar_job_abc123DEF_456",
    "onboarding.avatarSourceSelectionVersion": 3,
  });
  assert.equal(
    Object.keys(fields).some((key) => key.includes("gcsUri")),
    false,
  );
  assert.equal(
    Object.keys(fields).some((key) => key.includes("sourcePhotoRefs")),
    false,
  );
});

test("avatar source recovery user fields reject unsafe job ids", () => {
  assert.throws(
    () => buildAvatarSourceRecoveryUserFields("avatar_job_bad/path", 3),
    /jobId is not a safe path segment/,
  );
});

test("new avatar source selection supersedes previous current source only", () => {
  const updated = upsertSourcePhotoEntry(
    [
      {
        photoId: "src_old",
        status: "active",
        avatarGenerationState: "current",
        sha256: "old",
      },
      {
        photoId: "src_clip_only",
        status: "active",
        avatarGenerationState: "superseded",
        sha256: "clip",
      },
    ],
    {
      photoId: "src_new",
      status: "active",
      avatarGenerationState: "current",
      sha256: "new",
    },
    "src_old",
  );

  assert.equal(
    updated.find((entry) => entry.photoId === "src_old")?.avatarGenerationState,
    "superseded",
  );
  assert.equal(
    updated.find((entry) => entry.photoId === "src_new")?.avatarGenerationState,
    "current",
  );
  assert.equal(
    updated.filter((entry) => entry.avatarGenerationState === "current").length,
    1,
  );
  assert.equal(
    updated.find((entry) => entry.photoId === "src_clip_only")?.status,
    "active",
  );
});

test("same current source upload keeps current source current", () => {
  const updated = upsertSourcePhotoEntry(
    [
      {
        photoId: "src_same",
        status: "active",
        avatarGenerationState: "current",
        uploadedAt: "original",
      },
    ],
    {
      photoId: "src_same",
      status: "active",
      avatarGenerationState: "current",
      uploadedAt: "new",
    },
    "src_same",
  );

  assert.equal(updated.length, 1);
  assert.equal(updated[0].avatarGenerationState, "current");
  assert.equal(updated[0].uploadedAt, "original");
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

test("avatar source lock requires both current source and current job ids", () => {
  assert.equal(
    hasLockedAvatarSource({
      currentAvatarSourcePhotoId: "src_abc",
      currentAvatarJobId: "avatar_job_abc",
      sourcePhotos: [
        {
          photoId: "src_abc",
          status: "active",
          avatarGenerationState: "current",
        },
      ],
    }),
    true,
  );
  assert.throws(
    () => hasLockedAvatarSource({ currentAvatarSourcePhotoId: "src_abc" }),
    /avatar_state_inconsistent/,
  );
  assert.throws(
    () => hasLockedAvatarSource({ currentAvatarJobId: "job_abc" }),
    /avatar_state_inconsistent/,
  );
  assert.equal(hasLockedAvatarSource(null), false);
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

test("production Cloud Tasks requires TASK_INVOKER_SERVICE_ACCOUNT", () => {
  const payload = buildAvatarPayload(
    "u1",
    "src_abc",
    "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg",
    "avatar_job_1",
  );

  withEnv(
    {
      ENVIRONMENT: "production",
      TASK_INVOKER_SERVICE_ACCOUNT: undefined,
      ALLOW_INSECURE_WORKER_LOCAL: undefined,
    },
    () => {
      assert.throws(
        () =>
          buildCloudTaskHttpRequest(
            "https://worker.example/tasks/avatar-generation",
            payload,
          ),
        /TASK_INVOKER_SERVICE_ACCOUNT/,
      );
    },
  );
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

test("local insecure Cloud Tasks bypass requires explicit local flag", () => {
  const payload = buildAvatarPayload(
    "u1",
    "src_abc",
    "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg",
    "avatar_job_1",
  );

  withEnv(
    {
      ENVIRONMENT: "local",
      TASK_INVOKER_SERVICE_ACCOUNT: undefined,
      ALLOW_INSECURE_WORKER_LOCAL: undefined,
    },
    () => {
      assert.throws(
        () =>
          buildCloudTaskHttpRequest(
            "http://127.0.0.1:8080/tasks/avatar-generation",
            payload,
          ),
        /ALLOW_INSECURE_WORKER_LOCAL/,
      );
    },
  );

  withEnv(
    {
      ENVIRONMENT: "local",
      TASK_INVOKER_SERVICE_ACCOUNT: undefined,
      ALLOW_INSECURE_WORKER_LOCAL: "true",
    },
    () => {
      const request = buildCloudTaskHttpRequest(
        "http://127.0.0.1:8080/tasks/avatar-generation",
        payload,
      );

      assert.equal(request.oidcToken, undefined);
    },
  );
});
