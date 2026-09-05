import assert from "node:assert/strict";
import test from "node:test";

import {
  classifyAvatarJobForReconciliation,
  PROVIDER_OUTCOME_UNKNOWN_ERROR_CODES,
} from "./avatarJobReconciliation";

const QUEUED_JOB = {
  status: "queued",
  queueStatus: "enqueued",
};

test("queued job with zero dispatches provably made no provider call", () => {
  const result = classifyAvatarJobForReconciliation({
    jobData: QUEUED_JOB,
    queuePaused: true,
    taskDispatchCount: 0,
    taskExists: true,
  });

  assert.equal(result.classification, "queued_not_dispatched");
  assert.equal(result.providerCallPossible, false);
  // 큐가 멈춰 있는 것은 사용자 실패가 아니다.
  assert.equal(result.publicStatus, "queued");
  assert.equal(result.reasonCode, "avatar_generation_paused");
  assert.equal(result.safeToRequeue, false, "paused queue must not be requeued");
});

test("queued job with a running queue and no dispatch is safe to requeue", () => {
  const result = classifyAvatarJobForReconciliation({
    jobData: QUEUED_JOB,
    queuePaused: false,
    taskDispatchCount: 0,
    taskExists: false,
  });

  assert.equal(result.classification, "queued_not_dispatched");
  assert.equal(result.providerCallPossible, false);
  assert.equal(result.safeToRequeue, true);
});

test("post-send unknown outcome is never confused with QA review", () => {
  for (const errorCode of PROVIDER_OUTCOME_UNKNOWN_ERROR_CODES) {
    const result = classifyAvatarJobForReconciliation({
      jobData: {
        status: "needs_review",
        errorCode,
        generationClaim: { state: "active" },
      },
      queuePaused: false,
      taskDispatchCount: 1,
      taskExists: true,
    });

    assert.equal(result.classification, "provider_outcome_unknown");
    // 유료 생성이 이미 일어났을 수 있다.
    assert.equal(result.providerCallPossible, true);
    assert.equal(result.safeToRequeue, false);
    assert.equal(result.publicStatus, "reconciliation_required");
    assert.equal(result.reasonCode, "avatar_provider_outcome_unknown");
    assert.notEqual(result.publicStatus, "needs_review");
  }
});

test("a genuine QA needs_review is not a reconciliation state", () => {
  const result = classifyAvatarJobForReconciliation({
    jobData: { status: "needs_review", errorCode: "qa_requires_review" },
    queuePaused: false,
    taskDispatchCount: 1,
    taskExists: false,
  });

  assert.equal(result.classification, "terminal");
  assert.equal(result.publicStatus, "needs_review");
  assert.equal(result.providerCallPossible, true);
  assert.equal(result.safeToRequeue, false);
});

test("an active generation claim alone blocks requeue even without an error code", () => {
  const result = classifyAvatarJobForReconciliation({
    jobData: {
      status: "provider_inflight",
      generationClaim: { state: "active" },
    },
    queuePaused: false,
    taskDispatchCount: 1,
    taskExists: true,
  });

  assert.equal(result.classification, "active");
  assert.equal(result.safeToRequeue, false);
});

test("providerUsage evidence forbids the queued-not-dispatched conclusion", () => {
  const result = classifyAvatarJobForReconciliation({
    jobData: { status: "queued", providerUsage: { attempts: 1 } },
    queuePaused: true,
    taskDispatchCount: 0,
    taskExists: true,
  });

  assert.notEqual(result.classification, "queued_not_dispatched");
  assert.equal(result.providerCallPossible, true);
  assert.equal(result.safeToRequeue, false);
});

test("unknown dispatch evidence is never treated as proof of no provider call", () => {
  const result = classifyAvatarJobForReconciliation({
    jobData: QUEUED_JOB,
    queuePaused: false,
    taskDispatchCount: null,
    taskExists: null,
  });

  assert.equal(result.classification, "insufficient_evidence");
  assert.equal(result.providerCallPossible, true);
  assert.equal(result.safeToRequeue, false);
});
