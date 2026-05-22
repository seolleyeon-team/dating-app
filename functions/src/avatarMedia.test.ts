import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAvatarPayload,
  avatarPresentationGenderFromUserData,
  buildChatRealPhotoMetadata,
  buildClipPayload,
  buildCloudTaskHttpRequest,
  buildDeterministicCloudTaskName,
  buildDisabledChatRealPhotoMetadata,
  cloudTaskDispatchDeadlineSeconds,
  buildPrivateMediaPayload,
  isCloudTasksAlreadyExistsError,
  planAvatarUploadState,
  queueMode,
  summarizeQueueWriteState,
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

test("duplicate upload keeps preview_ready jobs out of queued writes", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "preview_ready",
    userAvatar: { status: "queued" },
    duplicate: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.shouldSetUserAvatarQueued, false);
  assert.equal(plan.responseAvatarStatus, "preview_ready");
});

test("duplicate upload keeps completed jobs out of queued writes", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "completed",
    userAvatar: { status: "queued" },
    duplicate: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.responseAvatarStatus, "completed");
});

test("duplicate queued dry-run job is re-enqueued after queue config is fixed", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "queued",
    existingQueueMode: "dry_run",
    existingQueueStatus: "enqueued",
    userAvatar: { status: "queued" },
    duplicate: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, true);
  assert.equal(plan.shouldSetUserAvatarQueued, true);
  assert.equal(plan.responseAvatarStatus, "queued");
});

test("duplicate queued job with real enqueue is not enqueued again", () => {
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

test("failed duplicate upload can deterministically reuse the stable job", () => {
  const plan = planAvatarUploadState({
    existingJobExists: true,
    existingJobStatus: "failed",
    userAvatar: { status: "queued" },
    duplicate: true,
  });

  assert.equal(plan.shouldWriteQueuedJob, true);
  assert.equal(plan.shouldEnqueue, true);
  assert.equal(plan.shouldSetUserAvatarQueued, true);
  assert.equal(plan.responseAvatarStatus, "queued");
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
  const queueName = "projects/p/locations/asia-northeast3/queues/avatar-generation";
  const first = buildDeterministicCloudTaskName(
    queueName,
    "avatar_generation",
    "u1:src_abc:avatar_generation_v1"
  );
  const second = buildDeterministicCloudTaskName(
    queueName,
    "avatar_generation",
    "u1:src_abc:avatar_generation_v1"
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
    "avatar_job_1"
  );
  const clip = buildClipPayload(
    "u1",
    "src_abc",
    "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg"
  );

  assert.equal(avatar.idempotencyKey, "u1:src_abc:avatar_generation_v1");
  assert.equal(clip.idempotencyKey, "u1:src_abc:clip_embedding_v1");
});

test("avatar payload normalizes onboarding gender for private worker guidance", () => {
  const avatar = buildAvatarPayload(
    "u1",
    "src_abc",
    "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg",
    "avatar_job_1",
    "여성"
  );

  assert.equal(avatar.avatarPresentationGender, "female");
});

test("avatar presentation gender ignores non-onboarding profile gender", () => {
  assert.equal(
    avatarPresentationGenderFromUserData({
      gender: "female",
      onboarding: {},
    }),
    "unknown"
  );
  assert.equal(
    avatarPresentationGenderFromUserData({
      gender: "female",
      onboarding: { gender: "male" },
    }),
    "male"
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
      approvedAvatarUrl: "gs://seolleyeon-final-private-source-photos/users/u/source/src.jpg",
    },
    duplicate: false,
  });

  assert.equal(plan.shouldWriteQueuedJob, false);
  assert.equal(plan.shouldEnqueue, false);
  assert.equal(plan.responseAvatarStatus, "approved");
  assert.equal(plan.responseMessage, "avatar_already_approved");
  assert.equal(plan.approvedAvatarUrl, undefined);
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
        gcsUri: "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg",
        status: "active",
      },
    ],
    {
      chatPartnerRealPhotoDisclosure: true,
      chatRealPhoto,
    }
  );

  assert.equal(payload.photoConsent.chatPartnerRealPhotoDisclosure, true);
  assert.equal(payload.photoConsent.profileDisplayOriginalPhoto, false);
  assert.equal(payload.photoConsent.version, "photo_consent_v3");
  assert.equal(payload.chatRealPhoto.enabled, true);
  assert.equal(payload.chatRealPhoto.storageBucket, "seolleyeon-chat-profile-photos");
  assert.equal(payload.chatRealPhoto.gcsUri?.startsWith("gs://seolleyeon-chat-profile-photos/"), true);
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
    "avatar_job_1"
  );

  withEnv(
    {
      ENVIRONMENT: "production",
      TASK_INVOKER_SERVICE_ACCOUNT: undefined,
      ALLOW_INSECURE_WORKER_LOCAL: undefined,
    },
    () => {
      assert.throws(
        () => buildCloudTaskHttpRequest("https://worker.example/tasks/avatar-generation", payload),
        /TASK_INVOKER_SERVICE_ACCOUNT/
      );
    }
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
    }
  );

  withEnv(
    {
      ENVIRONMENT: "production",
      JOB_QUEUE_MODE: "dry_run",
    },
    () => {
      assert.throws(() => queueMode(), /not allowed/);
    }
  );

  withEnv(
    {
      ENVIRONMENT: "production",
      JOB_QUEUE_MODE: "cloud_tasks",
    },
    () => {
      assert.equal(queueMode(), "cloud_tasks");
    }
  );
});

test("production Cloud Tasks HTTP target includes OIDC token", () => {
  const payload = buildClipPayload(
    "u1",
    "src_abc",
    "gs://seolleyeon-private-source-photos/users/u1/source/src_abc.jpg"
  );

  withEnv(
    {
      ENVIRONMENT: "production",
      TASK_INVOKER_SERVICE_ACCOUNT: "task-invoker@example.iam.gserviceaccount.com",
      TASK_OIDC_AUDIENCE: "https://worker.example",
      ALLOW_INSECURE_WORKER_LOCAL: undefined,
    },
    () => {
      const request = buildCloudTaskHttpRequest(
        "https://worker.example/tasks/clip-embedding",
        payload
      );

      assert.equal(
        request.oidcToken?.serviceAccountEmail,
        "task-invoker@example.iam.gserviceaccount.com"
      );
      assert.equal(request.oidcToken?.audience, "https://worker.example");
    }
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
    "avatar_job_1"
  );

  withEnv(
    {
      ENVIRONMENT: "local",
      TASK_INVOKER_SERVICE_ACCOUNT: undefined,
      ALLOW_INSECURE_WORKER_LOCAL: undefined,
    },
    () => {
      assert.throws(
        () => buildCloudTaskHttpRequest("http://127.0.0.1:8080/tasks/avatar-generation", payload),
        /ALLOW_INSECURE_WORKER_LOCAL/
      );
    }
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
        payload
      );

      assert.equal(request.oidcToken, undefined);
    }
  );
});
