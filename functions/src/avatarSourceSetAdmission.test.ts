import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import {
  admitAvatarGenerationFromOnboardingPhotos,
  type BucketLike,
  type SourceSetAdmissionDeps,
  type StoredFileLike,
} from "./avatarSourceSetAdmission";
import {
  assertAvatarSourceSetQueuePayload,
  type AvatarSourceSetQueuePayload,
} from "./avatarSourceSetQueue";
import {
  buildCloudTaskHttpRequest,
  buildDeterministicCloudTaskName,
  readCurrentAvatarContract,
  redactQueuePayload,
} from "./avatarMedia";
import { FakeFirestore, type Db } from "./testing/fakeFirestore";

const UID = "uid_admit_00000001";
const REQ = "req-admit-000000001";

type StoredObject = {
  bytes: Buffer;
  generation: string;
  metadata: Record<string, unknown>;
  contentType: string;
};

class FakeBucket implements BucketLike {
  readonly objects = new Map<string, StoredObject>();
  constructor(readonly name: string) {}

  put(path: string, object: StoredObject) {
    this.objects.set(path, object);
  }

  file(path: string, options?: { generation?: string }): StoredFileLike {
    const bucket = this;
    return {
      async getMetadata() {
        const stored = bucket.objects.get(path);
        if (!stored) throw new Error("No such object");
        if (options?.generation && options.generation !== stored.generation) {
          throw new Error("generation mismatch");
        }
        return [
          {
            name: path,
            size: String(stored.bytes.length),
            contentType: stored.contentType,
            generation: stored.generation,
            metadata: stored.metadata,
          },
        ];
      },
      async download() {
        const stored = bucket.objects.get(path);
        if (!stored) throw new Error("No such object");
        if (options?.generation && options.generation !== stored.generation) {
          throw new Error("generation mismatch");
        }
        return [stored.bytes];
      },
      async exists() {
        return [bucket.objects.has(path)];
      },
      async save(data: Buffer, saveOptions: Record<string, unknown>) {
        if (bucket.objects.has(path)) throw new Error("412 precondition failed");
        const meta = (saveOptions.metadata ?? {}) as Record<string, unknown>;
        bucket.put(path, {
          bytes: data,
          generation: String(1000 + bucket.objects.size),
          contentType: String(meta.contentType ?? "application/octet-stream"),
          metadata: (meta.metadata ?? {}) as Record<string, unknown>,
        });
      },
    };
  }
}

function onboardingObject(
  photoId: string,
  slotIndex: number,
  generation: string,
  overrides: Partial<StoredObject> & { metadata?: Record<string, unknown> } = {},
): StoredObject {
  return {
    bytes: Buffer.from(`jpeg-bytes-${photoId}`),
    generation,
    contentType: "image/jpeg",
    ...overrides,
    metadata: {
      ownerUid: UID,
      uploadKind: "onboarding_profile_photo",
      uploadState: "ready",
      normalization: "onboarding_normalized_jpeg_v1",
      slotIndex: String(slotIndex),
      ...(overrides.metadata ?? {}),
    },
  };
}

function ref(photoId: string, slotIndex: number, generation: string) {
  return { photoId, slotIndex, objectGeneration: generation };
}

function metadata(clip = false) {
  return {
    clientRequestId: REQ,
    consentVersion: "photo_consent_v4",
    consentPurposes: {
      avatarGeneration: true,
      clipRecommendation: clip,
      sourcePhotoRetention: false,
    },
  };
}

type Harness = {
  deps: SourceSetAdmissionDeps;
  store: Db;
  onboarding: FakeBucket;
  privateBucket: FakeBucket;
  enqueued: AvatarSourceSetQueuePayload[];
};

function harness(options: {
  userAvatar?: Record<string, unknown>;
  privateData?: Record<string, unknown>;
  jobs?: Record<string, Record<string, unknown>>;
  enqueueFails?: boolean;
} = {}): Harness {
  const store: Db = new Map();
  store.set(`users/${UID}`, {
    isStudentVerified: true,
    avatar: options.userAvatar ?? { status: "none" },
    onboarding: {},
  });
  store.set(`userPrivateMedia/${UID}`, options.privateData ?? {});
  for (const [id, job] of Object.entries(options.jobs ?? {})) {
    store.set(`avatarJobs/${id}`, job);
  }
  const onboarding = new FakeBucket("seolleyeon-final.firebasestorage.app");
  const privateBucket = new FakeBucket("seolleyeon-final-private-source-photos");
  const enqueued: AvatarSourceSetQueuePayload[] = [];
  const deps: SourceSetAdmissionDeps = {
    firestore: new FakeFirestore(store) as never,
    onboardingBucket: () => onboarding,
    privateSourceBucket: () => privateBucket,
    enqueueAvatar: async (payload) => {
      if (options.enqueueFails) throw new Error("queue unavailable");
      enqueued.push(payload);
      return { mode: "cloud_tasks", status: "enqueued", taskName: "t" };
    },
    env: {},
  };
  return { deps, store, onboarding, privateBucket, enqueued };
}

function seedPhotos(h: Harness, count: number) {
  const refs = [];
  for (let index = 0; index < count; index += 1) {
    const photoId = `photo_${index}_000000000`;
    const generation = String(100 + index);
    h.onboarding.put(
      `users/${UID}/onboarding/photos/${photoId}.jpg`,
      onboardingObject(photoId, index, generation),
    );
    refs.push(ref(photoId, index, generation));
  }
  return refs;
}

async function admit(h: Harness, sourcePhotos: unknown, clip = false) {
  return admitAvatarGenerationFromOnboardingPhotos(h.deps, {
    uid: UID,
    data: { ...metadata(clip), sourcePhotos },
  });
}

async function expectRejected(promise: Promise<unknown>, fragment: string) {
  await assert.rejects(
    promise,
    (error: unknown) => error instanceof Error && error.message.includes(fragment),
    `expected rejection containing ${fragment}`,
  );
}

// ---------------------------------------------------------------------------
// SOURCE SET SIZE
// ---------------------------------------------------------------------------

test("0 and 1 sources are rejected before any storage or job write", async () => {
  const h = harness();
  await expectRejected(admit(h, []), "avatar_source_set_invalid");
  const refs = seedPhotos(h, 1);
  await expectRejected(admit(h, refs), "avatar_source_set_invalid");
  assert.equal(h.privateBucket.objects.size, 0);
  assert.equal(h.enqueued.length, 0);
  assert.equal(h.store.has(`avatarJobs/${"anything"}`), false);
});

test("2 valid sources are admitted as ONE pending job and ONE task, with no source lock yet", async () => {
  const h = harness();
  const refs = seedPhotos(h, 2);
  const result = await admit(h, refs);

  assert.equal(result.duplicate, false);
  assert.equal(result.avatarStatus, "queued");
  assert.equal(h.enqueued.length, 1, "exactly one task");
  assert.equal(h.enqueued[0].jobId, result.jobId);
  assert.equal(h.enqueued[0].sourcePhotoIds.length, 2);
  assert.equal(h.enqueued[0].candidateCount, 2);
  assert.equal(h.enqueued[0].sourceSelectionMode, "quality_selector_v1");

  const job = h.store.get(`avatarJobs/${result.jobId}`) ?? {};
  assert.equal(job.status, "queued");
  assert.deepEqual(job.sourceSelection, {
    status: "pending",
    selectorVersion: "avatar_source_quality_selector_v1",
    evaluatedCount: 0,
  });
  assert.equal("generationClaim" in job, false);
  assert.equal("providerUsage" in job, false);

  const priv = h.store.get(`userPrivateMedia/${UID}`) ?? {};
  assert.equal(priv.currentAvatarJobId, result.jobId);
  assert.equal("currentAvatarSourcePhotoId" in priv, false, "no source locked by Phase A");
  const contract = readCurrentAvatarContract(priv);
  assert.equal(contract.sourceLocked, true);
  assert.equal(contract.sourceSelecting, true);
  assert.equal(h.privateBucket.objects.size, 2, "both normalized copies persisted");
});

test("6 valid sources are admitted; 7 are rejected", async () => {
  const six = harness();
  const refs6 = seedPhotos(six, 6);
  const result = await admit(six, refs6);
  assert.equal(six.enqueued[0].sourcePhotoIds.length, 6);
  assert.equal(result.duplicate, false);

  const seven = harness();
  const refs7 = seedPhotos(seven, 7);
  await expectRejected(admit(seven, refs7), "avatar_source_set_invalid");
  assert.equal(seven.enqueued.length, 0);
});

// ---------------------------------------------------------------------------
// SOURCE OBJECT VERIFICATION (server-owned evidence)
// ---------------------------------------------------------------------------

test("a still-uploading source is rejected", async () => {
  const h = harness();
  const refs = seedPhotos(h, 2);
  h.onboarding.put(
    `users/${UID}/onboarding/photos/${refs[1].photoId}.jpg`,
    onboardingObject(refs[1].photoId, 1, refs[1].objectGeneration, {
      metadata: { uploadState: "uploading" },
    }),
  );
  await expectRejected(admit(h, refs), "avatar_onboarding_source_invalid");
  assert.equal(h.enqueued.length, 0);
});

test("a deleted source is rejected", async () => {
  const h = harness();
  const refs = seedPhotos(h, 2);
  h.onboarding.objects.delete(`users/${UID}/onboarding/photos/${refs[0].photoId}.jpg`);
  await expectRejected(admit(h, refs), "avatar_onboarding_source_invalid");
  assert.equal(h.enqueued.length, 0);
});

test("wrong owner and wrong uploadKind are rejected", async () => {
  const owner = harness();
  const ownerRefs = seedPhotos(owner, 2);
  owner.onboarding.put(
    `users/${UID}/onboarding/photos/${ownerRefs[0].photoId}.jpg`,
    onboardingObject(ownerRefs[0].photoId, 0, ownerRefs[0].objectGeneration, {
      metadata: { ownerUid: "someone_else" },
    }),
  );
  await expectRejected(admit(owner, ownerRefs), "avatar_onboarding_source_invalid");

  const kind = harness();
  const kindRefs = seedPhotos(kind, 2);
  kind.onboarding.put(
    `users/${UID}/onboarding/photos/${kindRefs[0].photoId}.jpg`,
    onboardingObject(kindRefs[0].photoId, 0, kindRefs[0].objectGeneration, {
      metadata: { uploadKind: "chat_real_photo" },
    }),
  );
  await expectRejected(admit(kind, kindRefs), "avatar_onboarding_source_invalid");
});

test("an object generation mismatch is rejected (stale client ref)", async () => {
  const h = harness();
  const refs = seedPhotos(h, 2);
  const stale = [refs[0], { ...refs[1], objectGeneration: "999" }];
  await expectRejected(admit(h, stale), "avatar_onboarding_source_invalid");
  assert.equal(h.enqueued.length, 0);
});

test("duplicate photo ids in one request are rejected", async () => {
  const h = harness();
  const refs = seedPhotos(h, 2);
  await expectRejected(
    admit(h, [refs[0], { ...refs[0], slotIndex: 1 }]),
    "avatar_source_set_invalid",
  );
});

// ---------------------------------------------------------------------------
// IDEMPOTENCY / CONCURRENCY
// ---------------------------------------------------------------------------

test("duplicate Next with the same clientRequestId returns the same job and enqueues once", async () => {
  const h = harness();
  const refs = seedPhotos(h, 2);
  const first = await admit(h, refs);
  const second = await admit(h, refs);
  assert.equal(second.jobId, first.jobId);
  assert.equal(second.duplicate, true);
  assert.equal(h.enqueued.length, 1, "no second task");
});

test("concurrent Next calls converge on one job and one task", async () => {
  const h = harness();
  const refs = seedPhotos(h, 2);
  const results = await Promise.all([admit(h, refs), admit(h, refs)]);
  assert.equal(new Set(results.map((r) => r.jobId)).size, 1);
  // Cloud Tasks dedupes by the deterministic task name derived from the
  // idempotency key, so the invariant is ONE logical task, not one call.
  assert.equal(new Set(h.enqueued.map((p) => p.idempotencyKey)).size, 1);
  assert.equal(results.filter((r) => !r.duplicate).length, 1, "exactly one winner");
});

test("a second Next with a DIFFERENT clientRequestId cannot steal the lock", async () => {
  const h = harness();
  const refs = seedPhotos(h, 2);
  const first = await admit(h, refs);
  await expectRejected(
    admitAvatarGenerationFromOnboardingPhotos(h.deps, {
      uid: UID,
      data: { ...metadata(), clientRequestId: "req-other-000000002", sourcePhotos: refs },
    }),
    "avatar_source_locked",
  );
  assert.equal((h.store.get(`userPrivateMedia/${UID}`) ?? {}).currentAvatarJobId, first.jobId);
  assert.equal(h.enqueued.length, 1);
});

test("an already approved avatar and an active generation both refuse admission", async () => {
  const approved = harness({ userAvatar: { status: "approved", approvedAvatarUrl: "https://cdn/x.png" } });
  await expectRejected(admit(approved, seedPhotos(approved, 2)), "avatar_already_approved");

  const active = harness({
    userAvatar: { status: "running" },
    privateData: {
      currentAvatarJobId: "avatar_job_active_00000001",
      currentAvatarSourcePhotoId: "src_active",
      sourcePhotos: [{ photoId: "src_active", status: "active", avatarGenerationState: "current" }],
    },
    jobs: { avatar_job_active_00000001: { uid: UID, status: "running", uploadClientRequestId: "other" } },
  });
  await expectRejected(admit(active, seedPhotos(active, 2)), "avatar_source_locked");
});

test("after a completed new-generation recovery the next source set is admitted", async () => {
  // Recovery leaves users.avatar.status = none and clears the private pointers.
  const h = harness({
    userAvatar: { status: "none", generationReplacementCount: 1 },
    privateData: {
      sourcePhotos: [{ photoId: "src_old", status: "active", avatarGenerationState: "replaced" }],
    },
  });
  const result = await admit(h, seedPhotos(h, 2));
  assert.equal(result.duplicate, false);
  assert.equal(h.enqueued.length, 1);
});

// ---------------------------------------------------------------------------
// CLIP CONSENT IS INDEPENDENT OF AVATAR ADMISSION
// ---------------------------------------------------------------------------

test("clipRecommendation=false admits the avatar and requests no CLIP flow", async () => {
  const h = harness();
  const result = await admit(h, seedPhotos(h, 2), false);
  assert.equal(result.clipRecommendation, "not_requested");
  assert.equal(h.enqueued.length, 1);
  assert.equal(h.enqueued[0].consentPurposes.clipRecommendation, false);
});

test("clipRecommendation=true admits the avatar and defers CLIP until the source is selected", async () => {
  const h = harness();
  const result = await admit(h, seedPhotos(h, 2), true);
  assert.equal(result.clipRecommendation, "deferred_until_source_selected");
  // Avatar generation is unaffected: one avatar task, no CLIP task at admission
  // (the selected source is not known yet).
  assert.equal(h.enqueued.length, 1);
  assert.equal(h.enqueued[0].jobType, "avatar_generation");
  assert.equal(h.enqueued[0].consentPurposes.clipRecommendation, true);
  const priv = h.store.get(`userPrivateMedia/${UID}`) ?? {};
  assert.equal((priv.clip as Record<string, unknown>).embeddingStatus, "pending");
});

// ---------------------------------------------------------------------------
// ENQUEUE FAILURE
// ---------------------------------------------------------------------------

test("an enqueue failure records a typed retryable reason and touches no provider state", async () => {
  const h = harness({ enqueueFails: true });
  const refs = seedPhotos(h, 2);
  await expectRejected(admit(h, refs), "avatar_queue_dispatch_failed");
  const jobs = Array.from(h.store.entries()).filter(([k]) => k.startsWith("avatarJobs/"));
  assert.equal(jobs.length, 1);
  const job = jobs[0][1];
  assert.equal(job.status, "retryable_failed");
  assert.equal(job.errorCode, "avatar_queue_dispatch_failed");
  assert.equal(job.retryable, true);
  assert.equal("generationClaim" in job, false);
  assert.equal("providerUsage" in job, false);
});

// ---------------------------------------------------------------------------
// QUEUE CONTRACT (shared with the legacy path by construction)
// ---------------------------------------------------------------------------

function samplePayload(): AvatarSourceSetQueuePayload {
  return {
    jobId: "avatar_job_q_000000000001",
    uid: UID,
    sourcePhotoIds: ["src_a", "src_b"],
    sourcePhotoRefs: ["gs://b/users/u/source/src_a.jpg", "gs://b/users/u/source/src_b.jpg"],
    sourcePhotoObjectGenerations: ["11", "22"],
    sourceSelectionMode: "quality_selector_v1",
    consentPurposes: { avatarGeneration: true, clipRecommendation: false, sourcePhotoRetention: false },
    avatarPresentationGender: "female",
    candidateCount: 2,
    modelId: "azure_gpt_image_2",
    jobType: "avatar_generation",
    schemaVersion: "avatar_job_v1",
    idempotencyKey: `${UID}:avatar_job_q_000000000001:avatar_generation_source_set_v1`,
  };
}

test("task name is deterministic from the idempotency key (duplicate enqueue is idempotent)", () => {
  const queue = "projects/p/locations/asia-northeast3/queues/avatar-generation";
  const a = buildDeterministicCloudTaskName(queue, "avatar_generation", samplePayload().idempotencyKey);
  const b = buildDeterministicCloudTaskName(queue, "avatar_generation", samplePayload().idempotencyKey);
  assert.equal(a, b);
  const expectedHash = createHash("sha256").update(samplePayload().idempotencyKey).digest("hex").slice(0, 32);
  assert.ok(a.endsWith(`avatar-generation-${expectedHash}`));
});

test("source-set payload contract fails closed on malformed sets", () => {
  assert.doesNotThrow(() => assertAvatarSourceSetQueuePayload(samplePayload()));
  assert.throws(() =>
    assertAvatarSourceSetQueuePayload({
      ...samplePayload(),
      sourcePhotoIds: ["src_a"],
      sourcePhotoRefs: ["gs://b/users/u/source/src_a.jpg"],
      sourcePhotoObjectGenerations: ["11"],
    }),
  );
  assert.throws(() =>
    assertAvatarSourceSetQueuePayload({ ...samplePayload(), sourcePhotoObjectGenerations: ["11"] }),
  );
  assert.throws(() =>
    assertAvatarSourceSetQueuePayload({ ...samplePayload(), sourcePhotoIds: ["src_a", "src_a"], sourcePhotoRefs: ["x", "y"] }),
  );
  assert.throws(() => assertAvatarSourceSetQueuePayload({ ...samplePayload(), idempotencyKey: " " }));
});

test("task request carries the OIDC service-account contract and the raw payload body", () => {
  const previous = { ...process.env };
  try {
    process.env.TASK_INVOKER_SERVICE_ACCOUNT = "task-invoker@example.iam.gserviceaccount.com";
    delete process.env.TASK_OIDC_AUDIENCE;
    const request = buildCloudTaskHttpRequest("https://worker.example/tasks/avatar-generation", samplePayload());
    assert.equal(request.oidcToken?.serviceAccountEmail, "task-invoker@example.iam.gserviceaccount.com");
    assert.equal(request.oidcToken?.audience, "https://worker.example/tasks/avatar-generation");
    const body = JSON.parse(Buffer.from(request.body as Buffer).toString("utf8"));
    assert.equal(body.schemaVersion, "avatar_job_v1");
    assert.deepEqual(body.sourcePhotoObjectGenerations, ["11", "22"]);
  } finally {
    process.env = previous;
  }
});

test("task body redaction hides identifiers, refs, generations, and candidates in logs", () => {
  const redacted = redactQueuePayload({
    ...samplePayload(),
    sourceSelectionCandidates: [{ photoId: "src_a" }],
  });
  assert.equal(redacted.uid, "<redacted>");
  assert.equal(redacted.jobId, "<redacted>");
  assert.equal(redacted.idempotencyKey, "<redacted>");
  assert.deepEqual(redacted.sourcePhotoRefs, ["gs://<private-source-photo-redacted>", "gs://<private-source-photo-redacted>"]);
  assert.equal(redacted.sourcePhotoObjectGenerations, "<redacted>");
  assert.equal(redacted.sourceSelectionCandidates, "<redacted>");
  assert.equal(JSON.stringify(redacted).includes(UID), false);
});
