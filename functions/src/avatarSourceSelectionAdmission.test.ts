import assert from "node:assert/strict";
import test from "node:test";

import {
  QUALITY_SELECTOR_MODE,
  buildPendingAvatarSourceJob,
  resolveServerSourceSelectionMode,
  shouldDispatchPendingSourceSetJob,
} from "./avatarSourceSelectionAdmission";

const candidates = [
  {
    photoId: "src_quality_a",
    gcsUri: "gs://private/users/u1/source/src_quality_a.jpg",
    objectGeneration: "201",
    stableOrder: 0,
  },
  {
    photoId: "src_quality_b",
    gcsUri: "gs://private/users/u1/source/src_quality_b.jpg",
    objectGeneration: "202",
    stableOrder: 1,
  },
];

test("new jobs use server-controlled quality selector mode and 2 candidate initial cap", () => {
  const job = buildPendingAvatarSourceJob({
    uid: "u1",
    jobId: "avatar_job_quality_1",
    clientRequestId: "request_quality_1",
    selectionVersion: 3,
    candidates,
    avatarPresentationGender: "female",
  });

  assert.equal(job.sourceSelectionMode, QUALITY_SELECTOR_MODE);
  assert.equal(job.candidateCount, 2);
  assert.deepEqual(job.sourcePhotoIds, ["src_quality_a", "src_quality_b"]);
  assert.deepEqual(job.sourcePhotoRefs, candidates.map((item) => item.gcsUri));
  assert.deepEqual(job.sourcePhotoObjectGenerations, ["201", "202"]);
  assert.deepEqual(job.sourceSelection, {
    status: "pending",
    selectorVersion: "avatar_source_quality_selector_v1",
    evaluatedCount: 0,
  });
  assert.equal(job.selectedSource, undefined);
});

test("stale source-selection modes fail closed", () => {
  assert.equal(resolveServerSourceSelectionMode({}), QUALITY_SELECTOR_MODE);
  assert.throws(
    () => resolveServerSourceSelectionMode({ AVATAR_SOURCE_SELECTION_MODE: "legacy_first_photo" }),
    /must be quality_selector_v1/,
  );
  assert.throws(
    () => resolveServerSourceSelectionMode({ AVATAR_SOURCE_SELECTION_MODE: "client_choice" }),
    /AVATAR_SOURCE_SELECTION_MODE/,
  );
});

test("duplicate admission only re-dispatches a job whose queue write never completed", () => {
  assert.equal(
    shouldDispatchPendingSourceSetJob({ status: "queued", queueStatus: "" }),
    true,
  );
  assert.equal(
    shouldDispatchPendingSourceSetJob({
      status: "retryable_failed",
      queueStatus: "dispatch_failed",
      errorCode: "avatar_queue_dispatch_failed",
    }),
    true,
  );
  assert.equal(
    shouldDispatchPendingSourceSetJob({
      status: "queued",
      queueStatus: "enqueued",
    }),
    false,
  );
  assert.equal(
    shouldDispatchPendingSourceSetJob({
      status: "running",
      queueStatus: "enqueued",
    }),
    false,
  );
});
