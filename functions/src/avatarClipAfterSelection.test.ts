import assert from "node:assert/strict";
import test from "node:test";

import {
  AVATAR_CLIP_AFTER_SELECTION_TRIGGER_OPTIONS,
  planClipEnqueueAfterSelection,
} from "./avatarClipAfterSelection";

const CONSENT_TRUE = {
  avatarGeneration: true,
  clipRecommendation: true,
  sourcePhotoRetention: false,
};
const CONSENT_FALSE = { ...CONSENT_TRUE, clipRecommendation: false };

function job(selection: string, extra: Record<string, unknown> = {}) {
  return {
    uid: "uid_clip_1",
    jobId: "avatar_job_clip_000000001",
    consentPurposes: CONSENT_TRUE,
    sourceSelection: { status: selection },
    selectedSource:
      selection === "selected"
        ? {
            photoId: "src_clip_selected",
            gcsUri: "gs://seolleyeon-final-private-source-photos/users/uid_clip_1/source/src_clip_selected.jpg",
            objectGeneration: "77",
          }
        : undefined,
    ...extra,
  };
}

test("CLIP consent true enqueues exactly on the pending -> selected transition", () => {
  const plan = planClipEnqueueAfterSelection({
    beforeData: job("pending"),
    afterData: job("selected"),
  });
  assert.equal(plan.action, "enqueue");
  if (plan.action !== "enqueue") return;
  assert.equal(plan.payload.jobType, "clip_embedding");
  assert.deepEqual(plan.payload.sourcePhotoIds, ["src_clip_selected"]);
  // Deterministic key -> deterministic Cloud Task name -> idempotent enqueue.
  assert.equal(plan.payload.idempotencyKey, "uid_clip_1:src_clip_selected:clip_embedding_v1");
});

test("CLIP consent false never enqueues and never blocks the avatar job", () => {
  const plan = planClipEnqueueAfterSelection({
    beforeData: job("pending", { consentPurposes: CONSENT_FALSE }),
    afterData: job("selected", { consentPurposes: CONSENT_FALSE }),
  });
  assert.equal(plan.action, "skip");
  if (plan.action !== "skip") return;
  assert.equal(plan.reason, "clip_not_consented");
});

test("re-writes of an already selected job are a semantic no-op (no duplicate CLIP task)", () => {
  const plan = planClipEnqueueAfterSelection({
    beforeData: job("selected"),
    afterData: job("selected", { status: "preview_ready" }),
  });
  assert.equal(plan.action, "skip");
  if (plan.action !== "skip") return;
  assert.equal(plan.reason, "already_selected");
});

test("CLIP is not enqueued before a source is selected or when the source is incomplete", () => {
  assert.equal(
    planClipEnqueueAfterSelection({ beforeData: null, afterData: job("pending") }).action,
    "skip",
  );
  const incomplete = planClipEnqueueAfterSelection({
    beforeData: job("pending"),
    afterData: job("selected", { selectedSource: { photoId: "src_x" } }),
  });
  assert.equal(incomplete.action, "skip");
  if (incomplete.action !== "skip") return;
  assert.equal(incomplete.reason, "selected_source_incomplete");
});

test("the trigger is redelivered on transient failure and writes nothing it watches", () => {
  assert.equal(AVATAR_CLIP_AFTER_SELECTION_TRIGGER_OPTIONS.retry, true);
  assert.equal(AVATAR_CLIP_AFTER_SELECTION_TRIGGER_OPTIONS.document, "avatarJobs/{jobId}");
});
