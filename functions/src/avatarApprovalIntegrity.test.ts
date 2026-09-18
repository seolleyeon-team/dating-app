/**
 * Can a candidate QA rejected, or one whose own fields contradict each other,
 * become an approved avatar?
 *
 * The approval callable is careful about almost everything else. It asserts
 * candidate ownership, job ownership and the current-avatar-job contract both
 * before and again inside the transaction; it re-reads candidate, user, job and
 * private media in that transaction; it is idempotent through
 * planAvatarApprovalState. The QA gate deliberately distinguishes the
 * canonical soft needs_review exposure policy from hard review and rejects.
 *
 * canPreviewCandidate is the final QA/exposure gate:
 *
 *     preview_ready + normal QA pass, or canonical soft needs_review,
 *     plus hard-reject checks and !expired
 *
 * Hard reject fields remain checked here even when the soft-review policy
 * bypasses qa.previewAllowed for a canonical soft candidate. The approval path
 * is the last server-side authority before a face becomes the user's public
 * profile, so it must fail closed on malformed or contradictory documents.
 *
 * These tests state what must hold regardless of how a contradictory document
 * came to exist -- partial write, admin repair, migration, or a future producer
 * that sets the two fields without the QA gate between them.
 */

import assert from "node:assert/strict";
import test from "node:test";

import * as avatarApprovalModule from "./avatarApproval";

type ApprovalGate = {
  buildAvatarCandidateQaSummary: (
    candidate: Record<string, unknown>,
  ) => Record<string, unknown>;
  canPreviewCandidate: (
    candidate: Record<string, unknown>,
    nowMs?: number,
  ) => boolean;
  canAdmitAvatarApproval: (
    candidate: Record<string, unknown>,
    userData: Record<string, unknown>,
    candidateId: string,
  ) => boolean;
  isAvatarApprovalJobStatusAllowed: (status: string) => boolean;
};

function gate(): ApprovalGate {
  return avatarApprovalModule as unknown as ApprovalGate;
}

const FRESH_USER = { avatar: { status: "preview_ready" } };
const CANDIDATE_ID = "candidate-001";

/** A candidate the worker would actually produce for preview. */
function healthyCandidate(
  qaOverrides: Record<string, unknown> = {},
  candidateOverrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    status: "preview_ready",
    jobId: "job-001",
    ownerUid: "user-001",
    ...candidateOverrides,
    qa: {
      previewAllowed: true,
      selectedForPreview: true,
      requiresHumanReview: false,
      rejectReasons: [],
      reviewReasons: [],
      adultQa: "pass",
      privacyQa: "pass",
      brandQa: "pass",
      cropConsistency: "pass",
      watermarkQaAction: "allow",
      identifiabilityRisk: "low",
      ...qaOverrides,
    },
  };
}

// ---------------------------------------------------------------------------
// A. the normal path must keep working
// ---------------------------------------------------------------------------

test("A healthy preview_ready candidate is approvable", () => {
  assert.equal(gate().canPreviewCandidate(healthyCandidate()), true);
  assert.equal(
    gate().canAdmitAvatarApproval(healthyCandidate(), FRESH_USER, CANDIDATE_ID),
    true,
  );
});

// ---------------------------------------------------------------------------
// B-F. contradictory QA state must fail closed
// ---------------------------------------------------------------------------

const CONTRADICTORY: ReadonlyArray<[string, Record<string, unknown>]> = [
  ["B rejectReasons non-empty", { rejectReasons: ["logo_text_watermark"] }],
  ["B2 rejectReasons secondary person", { rejectReasons: ["secondary_person_generated"] }],
  ["C privacyQa fail", { privacyQa: "fail" }],
  ["C2 brandQa fail", { brandQa: "fail" }],
  ["C3 cropConsistency fail", { cropConsistency: "fail" }],
  ["D adultQa fail", { adultQa: "fail" }],
  ["E watermarkQaAction reject", { watermarkQaAction: "reject" }],
];

for (const [label, qaOverrides] of CONTRADICTORY) {
  test(`${label} must not be approvable even with previewAllowed=true`, () => {
    const candidate = healthyCandidate(qaOverrides);
    assert.equal(candidate.status, "preview_ready");
    assert.equal(
      (candidate.qa as Record<string, unknown>).previewAllowed,
      true,
      "premise: the two fields disagree",
    );
    assert.equal(
      gate().canPreviewCandidate(candidate),
      false,
      `${label}: canPreviewCandidate must fail closed`,
    );
    assert.equal(
      gate().canAdmitAvatarApproval(candidate, FRESH_USER, CANDIDATE_ID),
      false,
      `${label}: canAdmitAvatarApproval must fail closed`,
    );
  });
}

// ---------------------------------------------------------------------------
// G-I. status / flag disagreement must fail closed
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// F. requiresHumanReview is NOT a blocking condition -- an explicit product
//    contract says otherwise, and production depends on it
// ---------------------------------------------------------------------------

test("a soft-review candidate the product deliberately offered stays approvable", () => {
  /**
   * Product decision of 2026-09-07 (preview_policy.SOFT_REVIEW_REASONS): a
   * needs_review candidate MAY be offered for preview when its only review
   * reasons are soft calibrated-uncertainty signals and every hard privacy or
   * safety field still passes. Such a candidate carries
   * requiresHumanReview=true, privacyQa="needs_review" and
   * identifiabilityRisk="medium" by design.
   *
   * Production holds two of them right now, one of which is already an
   * approved user avatar. Blocking on requiresHumanReview -- which an earlier
   * draft of this matrix asserted -- would break a live product contract and
   * orphan that avatar. The hardening must distinguish "fail" from
   * "needs_review".
   */
  const softReview = healthyCandidate({
    requiresHumanReview: true,
    reviewTier: "soft_review",
    previewTier: "soft_review",
    privacyQa: "needs_review",
    identifiabilityRisk: "medium",
    reviewReasons: [
      "actual_qa_signal_review",
      "qa_model_signal_review",
      "qa_signal_uncertain",
    ],
  });
  assert.equal(gate().canPreviewCandidate(softReview), true);
  assert.equal(
    gate().canAdmitAvatarApproval(softReview, FRESH_USER, CANDIDATE_ID),
    true,
  );
});

test("needs_review on a status field is not the same as fail", () => {
  for (const field of ["privacyQa", "brandQa", "cropConsistency", "adultQa"]) {
    assert.equal(
      gate().canPreviewCandidate(healthyCandidate({ [field]: "needs_review" })),
      true,
      `${field}=needs_review must stay approvable`,
    );
    assert.equal(
      gate().canPreviewCandidate(healthyCandidate({ [field]: "fail" })),
      false,
      `${field}=fail must fail closed`,
    );
  }
});

test("watermark review is not watermark reject", () => {
  assert.equal(
    gate().canPreviewCandidate(healthyCandidate({ watermarkQaAction: "review" })),
    true,
  );
  assert.equal(
    gate().canPreviewCandidate(healthyCandidate({ watermarkQaAction: "reject" })),
    false,
  );
});

test("G needs_review status is not approvable even with previewAllowed=true", () => {
  const candidate = healthyCandidate({}, { status: "needs_review" });
  assert.equal(gate().canPreviewCandidate(candidate), false);
  assert.equal(
    gate().canAdmitAvatarApproval(candidate, FRESH_USER, CANDIDATE_ID),
    false,
  );
});

test("soft needs_review candidate is visible and selectable without changing QA evidence", () => {
  const reviewReasons = ["watermark_review", "logo_review"];
  const candidate = healthyCandidate(
    {
      previewAllowed: false,
      requiresHumanReview: true,
      reviewTier: "soft_review",
      reviewReasons,
    },
    { status: "needs_review" },
  );

  assert.equal(gate().canPreviewCandidate(candidate), true);
  assert.equal(
    gate().canAdmitAvatarApproval(candidate, FRESH_USER, CANDIDATE_ID),
    true,
  );
  assert.equal(candidate.status, "needs_review");
  assert.deepEqual((candidate.qa as Record<string, unknown>).reviewReasons, reviewReasons);
  assert.deepEqual(gate().buildAvatarCandidateQaSummary(candidate), {
    status: "needs_review",
    reviewTier: "soft_review",
    reviewReasons,
  });
  assert.deepEqual(
    gate().buildAvatarCandidateQaSummary(healthyCandidate()),
    { status: "pass" },
  );
});

test("hard-review needs_review candidate remains unavailable", () => {
  const candidate = healthyCandidate(
    {
      previewAllowed: false,
      requiresHumanReview: true,
      reviewTier: "hard_review",
      reviewReasons: ["watermark_artifact_review"],
    },
    { status: "needs_review" },
  );

  assert.equal(gate().canPreviewCandidate(candidate), false);
  assert.equal(
    gate().canAdmitAvatarApproval(candidate, FRESH_USER, CANDIDATE_ID),
    false,
  );
});

test("soft review does not bypass a canonical hard reject", () => {
  const candidate = healthyCandidate(
    {
      previewAllowed: false,
      requiresHumanReview: true,
      reviewTier: "soft_review",
      reviewReasons: ["watermark_review"],
      childlikeRisk: "high",
    },
    { status: "needs_review" },
  );

  assert.equal(gate().canPreviewCandidate(candidate), false);
  assert.equal(
    gate().canAdmitAvatarApproval(candidate, FRESH_USER, CANDIDATE_ID),
    false,
  );
});

test("mixed candidate visibility preserves order and excludes hard review", () => {
  const candidates = [
    healthyCandidate({}, { candidateId: "pass" }),
    healthyCandidate(
      {
        previewAllowed: false,
        requiresHumanReview: true,
        reviewTier: "soft_review",
        reviewReasons: ["logo_review"],
      },
      { candidateId: "soft", status: "needs_review" },
    ),
    healthyCandidate(
      {
        previewAllowed: false,
        requiresHumanReview: true,
        reviewTier: "hard_review",
        reviewReasons: ["watermark_artifact_review"],
      },
      { candidateId: "hard", status: "needs_review" },
    ),
  ];

  assert.deepEqual(
    candidates.filter((candidate) => gate().canPreviewCandidate(candidate)).map(
      (candidate) => candidate.candidateId,
    ),
    ["pass", "soft"],
  );
});

test("only preview-ready, soft needs-review, and approval-copying jobs admit approval", () => {
  assert.equal(gate().isAvatarApprovalJobStatusAllowed("preview_ready"), true);
  assert.equal(gate().isAvatarApprovalJobStatusAllowed("needs_review"), true);
  assert.equal(
    gate().isAvatarApprovalJobStatusAllowed("approval_copying"),
    true,
  );
  assert.equal(
    gate().isAvatarApprovalJobStatusAllowed("reconciliation_required"),
    false,
  );
  assert.equal(gate().isAvatarApprovalJobStatusAllowed("unknown"), false);
});

test("H rejected status is not approvable even with previewAllowed=true", () => {
  const candidate = healthyCandidate({}, { status: "rejected" });
  assert.equal(gate().canPreviewCandidate(candidate), false);
  assert.equal(
    gate().canAdmitAvatarApproval(candidate, FRESH_USER, CANDIDATE_ID),
    false,
  );
});

test("I previewAllowed=false is not approvable even when preview_ready", () => {
  const candidate = healthyCandidate({ previewAllowed: false });
  assert.equal(gate().canPreviewCandidate(candidate), false);
  assert.equal(
    gate().canAdmitAvatarApproval(candidate, FRESH_USER, CANDIDATE_ID),
    false,
  );
});

// ---------------------------------------------------------------------------
// offeredToUser is telemetry, never authority
// ---------------------------------------------------------------------------

test("offeredToUser=true does not make a rejected candidate approvable", () => {
  // #105 added offeredToUser to record what the product showed. "We displayed
  // it" is not "the server verified it is safe", and it must never be read as
  // an approval authority.
  const candidate = healthyCandidate({
    offeredToUser: true,
    rejectReasons: ["logo_text_watermark"],
  });
  assert.equal(gate().canPreviewCandidate(candidate), false);
});

test("offeredToUser alone cannot substitute for previewAllowed", () => {
  const candidate = healthyCandidate({ previewAllowed: false, offeredToUser: true });
  assert.equal(gate().canPreviewCandidate(candidate), false);
});

// ---------------------------------------------------------------------------
// the QA verdict recorded by #105 must not be misread either
// ---------------------------------------------------------------------------

test("a soft-review candidate with a hard reject is still blocked", () => {
  // qa.debug.qaDecisionPreviewAllowed=false is normal for a soft-review
  // candidate and must not by itself block approval. A hard reject on the same
  // document must.
  const offered = healthyCandidate({
    requiresHumanReview: true,
    reviewTier: "soft_review",
    previewTier: "soft_review",
    offeredToUser: true,
    privacyQa: "needs_review",
    debug: { qaDecisionPreviewAllowed: false },
  });
  assert.equal(gate().canPreviewCandidate(offered), true);

  const rejected = healthyCandidate({
    ...(offered.qa as Record<string, unknown>),
    rejectReasons: ["secondary_person_generated"],
  });
  assert.equal(gate().canPreviewCandidate(rejected), false);
});

// ---------------------------------------------------------------------------
// expiry is unchanged
// ---------------------------------------------------------------------------

test("an expired candidate stays unapprovable", () => {
  const candidate = healthyCandidate({}, { expiresAt: new Date(1000).toISOString() });
  assert.equal(gate().canPreviewCandidate(candidate, 2000), false);
});

test("a candidate expiring in the future is unaffected", () => {
  const candidate = healthyCandidate({}, {
    expiresAt: new Date(10_000).toISOString(),
  });
  assert.equal(gate().canPreviewCandidate(candidate, 2000), true);
});

// ---------------------------------------------------------------------------
// L. idempotent re-approval is preserved
// ---------------------------------------------------------------------------

test("an already-approved candidate stays admissible for an idempotent retry", () => {
  // This path deliberately bypasses canPreviewCandidate via
  // plan.action === "return_existing"; the hardening must not break it.
  assert.equal(
    gate().canAdmitAvatarApproval(
      { status: "approved", qa: { previewAllowed: true } },
      {
        avatar: {
          status: "approved",
          selectedCandidateId: CANDIDATE_ID,
          approvedAvatarUrl: "https://cdn.example/avatar.png",
          avatarId: `avatar_${CANDIDATE_ID}`,
        },
      },
      CANDIDATE_ID,
    ),
    true,
  );
});

test("an approved-status candidate is not admissible without the matching user state", () => {
  assert.equal(
    gate().canAdmitAvatarApproval(
      { status: "approved", qa: { previewAllowed: true } },
      { avatar: { status: "none" } },
      CANDIDATE_ID,
    ),
    false,
  );
});

// ---------------------------------------------------------------------------
// legacy shape must not fail open
// ---------------------------------------------------------------------------

test("a candidate with no qa map at all is not approvable", () => {
  assert.equal(
    gate().canPreviewCandidate({ status: "preview_ready", jobId: "job-001" }),
    false,
  );
});

test("a candidate with a non-boolean previewAllowed is not approvable", () => {
  for (const value of ["true", 1, {}, null]) {
    assert.equal(
      gate().canPreviewCandidate(
        healthyCandidate({ previewAllowed: value as unknown }),
      ),
      false,
      `previewAllowed=${JSON.stringify(value)}`,
    );
  }
});
