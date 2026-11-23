/**
 * AUD-09 — "the task was enqueued" must not overwrite the worker.
 *
 * Firestore emulator (real transaction semantics).
 *
 *   npx firebase-tools@15.30.2 emulators:exec --only firestore --project demo-aud09-enqueue \
 *     "node --test functions/.ci-emulator-lib/avatarEnqueueOutcome.emulator-test.js"
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { getFirestore } from "firebase-admin/firestore";

if (!process.env.FIRESTORE_EMULATOR_HOST) {
  throw new Error("FIRESTORE_EMULATOR_HOST is not set. Run via `firebase emulators:exec`.");
}

// index.ts performs initializeApp(); only import here.
import "./index";
import {
  isDispatchOwnedAvatarJobState,
  recordAvatarEnqueueSuccess,
} from "./avatarEnqueueOutcome";

const db = getFirestore();
let seq = 0;
const freshJob = () => db.collection("avatarJobs").doc(`aud09_${Date.now().toString(36)}_${++seq}`);
const QUEUE = { queueMode: "cloud_tasks", queueStatus: "enqueued" };

test("AUD-09: a job still waiting for dispatch is marked queued and its dispatch failure is cleared", async () => {
  for (const before of [
    { status: "queued" },
    { status: "pending" },
    { status: "retryable_failed", errorCode: "avatar_queue_dispatch_failed", retryable: true },
    { status: "retryable_failed", errorCode: "avatar_queue_enqueue_failed" },
  ]) {
    const ref = freshJob();
    await ref.set({ uid: "u1", ...before });
    assert.equal(await recordAvatarEnqueueSuccess(db, ref, QUEUE, { stampQueuedAt: true }), "queued");
    const after = (await ref.get()).data() ?? {};
    assert.equal(after.status, "queued");
    assert.equal("errorCode" in after, false);
    assert.equal("retryable" in after, false);
    assert.equal(after.queueMode, "cloud_tasks");
    assert.equal(after.queueStatus, "enqueued");
    assert.ok(after.queuedAt);
    assert.equal(after.uid, "u1");
  }
});

test("AUD-09: a state the worker already wrote is never put back to queued", async () => {
  const workerStates: Array<Record<string, unknown>> = [
    { status: "running" },
    { status: "provider_inflight" },
    { status: "qa_pending" },
    { status: "preview_ready" },
    { status: "needs_review" },
    // The case that used to strand a job: a fast terminal refusal by a warm
    // worker, overwritten with `queued` and its error code erased.
    { status: "failed", errorCode: "avatar_generation_candidate_cap_reached", retryable: false },
    { status: "retryable_failed", errorCode: "avatar_provider_timeout", retryable: true },
    { status: "superseded" },
  ];
  for (const state of workerStates) {
    const ref = freshJob();
    await ref.set({ uid: "u1", workerMarker: "kept", ...state });
    assert.equal(await recordAvatarEnqueueSuccess(db, ref, QUEUE, { stampQueuedAt: true }), "worker_owned");
    const after = (await ref.get()).data() ?? {};
    assert.equal(after.status, state.status, String(state.status));
    assert.equal(after.errorCode, state.errorCode);
    assert.equal(after.retryable, state.retryable);
    assert.equal(after.workerMarker, "kept");
    // Bookkeeping only.
    assert.equal(after.queueStatus, "enqueued");
    assert.equal("queuedAt" in after, false);
    assert.equal("updatedAt" in after, false);
  }
});

test("AUD-09: a worker write that lands while the bookkeeping transaction runs wins", async () => {
  for (let round = 0; round < 12; round += 1) {
    const ref = freshJob();
    await ref.set({ uid: "u1", status: "queued" });
    await Promise.all([
      recordAvatarEnqueueSuccess(db, ref, QUEUE),
      // The worker's own transition (it reads, then writes its state).
      db.runTransaction(async (tx) => {
        await tx.get(ref);
        tx.set(ref, { status: "failed", errorCode: "avatar_generation_candidate_cap_reached" }, { merge: true });
      }),
    ]);
    const after = (await ref.get()).data() ?? {};
    // Whichever committed first, the terminal state is what remains.
    assert.equal(after.status, "failed", `round ${round}`);
    assert.equal(after.errorCode, "avatar_generation_candidate_cap_reached", `round ${round}`);
    assert.equal(after.queueStatus, "enqueued");
  }
});

test("AUD-09: a missing job document is not created", async () => {
  const ref = freshJob();
  assert.equal(await recordAvatarEnqueueSuccess(db, ref, QUEUE), "missing");
  assert.equal((await ref.get()).exists, false);
});

test("AUD-09: dispatch-owned state classification", () => {
  assert.equal(isDispatchOwnedAvatarJobState({ status: "queued" }), true);
  assert.equal(isDispatchOwnedAvatarJobState({ status: "pending" }), true);
  assert.equal(
    isDispatchOwnedAvatarJobState({ status: "retryable_failed", errorCode: "avatar_queue_dispatch_failed" }),
    true,
  );
  assert.equal(isDispatchOwnedAvatarJobState({ status: "retryable_failed", errorCode: "avatar_provider_timeout" }), false);
  assert.equal(isDispatchOwnedAvatarJobState({ status: "retryable_failed" }), false);
  assert.equal(isDispatchOwnedAvatarJobState({ status: "running" }), false);
  assert.equal(isDispatchOwnedAvatarJobState({}), false);
  assert.equal(isDispatchOwnedAvatarJobState(null), false);
});
