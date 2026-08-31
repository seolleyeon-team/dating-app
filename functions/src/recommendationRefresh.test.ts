import assert from "node:assert/strict";
import test from "node:test";

import {
  areDisplayCandidatesStillEligible,
  evaluateRefreshPurchase,
  hasDisplayableImage,
  isExclusionActive,
  isRefreshCandidateDisplayable,
  kstDateKeyOf,
  MYSTERY_FEED_ALGO_PRIORITY,
  ONE_TO_ONE_REFRESH_COST_HEARTS,
  ONE_TO_ONE_REFRESH_DISPLAY_RANK_END,
  ONE_TO_ONE_REFRESH_DISPLAY_RANK_START,
  ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE,
  ONE_TO_ONE_WINDOW_SIZE,
  parseRefreshCandidates,
  selectEligibleRefreshCandidates,
  type DisplayCandidateCommitState,
  type RefreshCandidate,
} from "./recommendationRefresh";

const NO_ZONES = { enforceCampusZone: false, viewerZones: new Set<string>() };

function displayableProfile(
  overrides: Record<string, unknown> = {}
): Record<string, unknown> {
  return {
    schemaVersion: 2,
    status: "active",
    isStudentVerified: true,
    isProfileComplete: true,
    onboarding: {
      avatarUrls: ["https://storage.googleapis.com/seolleyeon-final/a.png"],
      campusLifeZones: ["sinchon"],
    },
    ...overrides,
  };
}

function candidatesOfRanks(ranks: number[]): RefreshCandidate[] {
  return ranks.map((rank) => ({ uid: `cand_${rank}`, rank }));
}

function profilesFor(
  candidates: RefreshCandidate[]
): Map<string, Record<string, unknown> | null> {
  return new Map(
    candidates.map((candidate) => [candidate.uid, displayableProfile()])
  );
}

function readyPurchaseInput(overrides: Record<string, unknown> = {}) {
  return {
    entitlementStatus: null as string | null,
    sourceStatus: "ready" as string | null,
    sourceUnchanged: true,
    displayCandidatesStillEligible: true,
    eligibleCandidateCount: ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE,
    heartBalance: 10,
    ...overrides,
  };
}

function commitState(
  uid: string,
  overrides: Partial<DisplayCandidateCommitState> = {}
): DisplayCandidateCommitState {
  return {
    uid,
    profile: displayableProfile(),
    blocked: false,
    exclusionActive: false,
    ...overrides,
  };
}

function commitCheckInput(
  candidates: DisplayCandidateCommitState[],
  overrides: Record<string, unknown> = {}
) {
  return {
    candidates,
    viewerUid: "viewer",
    enforceCampusZone: false,
    viewerZones: new Set<string>(),
    expectedCount: ONE_TO_ONE_WINDOW_SIZE,
    ...overrides,
  };
}

test("kst date key crosses midnight on KST, not UTC", () => {
  // 2026-08-30 14:59 UTC = 2026-08-30 23:59 KST
  assert.equal(kstDateKeyOf(new Date("2026-08-30T14:59:00Z")), "20260830");
  // 2026-08-30 15:00 UTC = 2026-08-31 00:00 KST
  assert.equal(kstDateKeyOf(new Date("2026-08-30T15:00:00Z")), "20260831");
});

test("algo priority mirrors the mystery feed client fallback order", () => {
  // AiRecommendationService.fetchMysteryFeed: rrf -> clip -> svd. If these
  // drift, the charged set and the rendered set can differ.
  assert.deepEqual([...MYSTERY_FEED_ALGO_PRIORITY], ["rrf", "clip", "svd"]);
});

test("candidate parsing keeps raw ranks and rank ordering", () => {
  const parsed = parseRefreshCandidates([
    { uid: "b", rank: 7 },
    { uid: "a", rank: 2 },
    { uid: "  ", rank: 1 },
    "junk",
    null,
    { rank: 3 },
    { uid: "c" }, // missing rank -> 999, sorts last
  ]);
  assert.deepEqual(parsed, [
    { uid: "a", rank: 2 },
    { uid: "b", rank: 7 },
    { uid: "c", rank: 999 },
  ]);
});

// ---------------------------------------------------------------------------
// Eligibility mirror of the Flutter _hydrateProfiles filter
// ---------------------------------------------------------------------------

test("candidates without a public profile, verification, a complete profile, "
  + "or a display image are not eligible", () => {
  assert.equal(isRefreshCandidateDisplayable(null, NO_ZONES), false);
  assert.equal(
    isRefreshCandidateDisplayable(
      displayableProfile({ isStudentVerified: false }),
      NO_ZONES
    ),
    false
  );
  assert.equal(
    isRefreshCandidateDisplayable(
      displayableProfile({ isProfileComplete: false }),
      NO_ZONES
    ),
    false
  );
  assert.equal(
    isRefreshCandidateDisplayable(
      displayableProfile({ onboarding: { campusLifeZones: ["sinchon"] } }),
      NO_ZONES
    ),
    false // 표시할 아바타/이미지 없음
  );
  assert.equal(
    isRefreshCandidateDisplayable(
      displayableProfile({ status: "suspended" }),
      NO_ZONES
    ),
    false
  );
  assert.equal(isRefreshCandidateDisplayable(displayableProfile(), NO_ZONES), true);
});

test("the recommendationPrivacyReady pending gate is GONE; pair-exclusion "
  + "filtering is the only Kakao privacy mechanism", () => {
  // kakao-friend-pairs contract §7: a candidate is displayable regardless of
  // the legacy pending flag in either direction.
  assert.equal(
    isRefreshCandidateDisplayable(
      displayableProfile({ recommendationPrivacyReady: false }),
      NO_ZONES
    ),
    true
  );
  assert.equal(
    isRefreshCandidateDisplayable(
      displayableProfile({ recommendationPrivacyReady: true }),
      NO_ZONES
    ),
    true
  );

  // The pair filter STAYS: an active exclusion doc (new §6 shape) still
  // removes the candidate through blockedUids / isExclusionActive.
  assert.equal(
    isExclusionActive({
      pairId: "a_b",
      userIds: ["a", "b"],
      source: "kakao_friend_pair",
      reason: "kakao_friend_avoidance",
      active: true,
      enabledBy: { a: true, b: false },
    }),
    true
  );
  const candidates = candidatesOfRanks([1, 2, 3]);
  const eligible = selectEligibleRefreshCandidates({
    candidates,
    viewerUid: "viewer",
    blockedUids: new Set(["cand_2"]), // union of blocks + active exclusions
    profileByUid: profilesFor(candidates),
    ...NO_ZONES,
  });
  assert.deepEqual(eligible.map((c) => c.uid), ["cand_1", "cand_3"]);
});

test("display image check accepts an approved avatar and rejects unsafe urls", () => {
  assert.equal(
    hasDisplayableImage({
      avatar: {
        status: "approved",
        approvedAvatarUrl:
          "https://storage.googleapis.com/seolleyeon-final/avatar.png",
      },
    }),
    true
  );
  assert.equal(
    hasDisplayableImage({
      onboarding: { avatarUrls: ["gs://seolleyeon-final/private.png"] },
    }),
    false
  );
  assert.equal(hasDisplayableImage({}), false);
});

test("campus life zone gate fails closed when enforced, like the client", () => {
  const enforcedForSinchon = {
    enforceCampusZone: true,
    viewerZones: new Set(["sinchon"]),
  };
  assert.equal(
    isRefreshCandidateDisplayable(displayableProfile(), enforcedForSinchon),
    true
  );
  assert.equal(
    isRefreshCandidateDisplayable(
      displayableProfile({
        onboarding: {
          avatarUrls: ["https://storage.googleapis.com/seolleyeon-final/a.png"],
          campusLifeZones: ["songdo"],
        },
      }),
      enforcedForSinchon
    ),
    false // 교집합 없음
  );
  assert.equal(
    isRefreshCandidateDisplayable(
      displayableProfile({
        onboarding: {
          avatarUrls: ["https://storage.googleapis.com/seolleyeon-final/a.png"],
        },
      }),
      enforcedForSinchon
    ),
    false // 후보 생활권 없음 -> fail-closed
  );
});

test("eligible selection preserves raw model ranks without renumbering", () => {
  // CASE C: raw rank 3 이 차단이면 initial 은 raw [1,2,4], refresh 는 [5,6,7].
  const candidates = candidatesOfRanks([1, 2, 3, 4, 5, 6, 7]);
  const eligible = selectEligibleRefreshCandidates({
    candidates,
    viewerUid: "viewer",
    blockedUids: new Set(["cand_3"]),
    profileByUid: profilesFor(candidates),
    ...NO_ZONES,
  });
  assert.deepEqual(
    eligible.map((candidate) => candidate.rank),
    [1, 2, 4, 5, 6, 7]
  );
  const initialWindow = eligible.slice(0, ONE_TO_ONE_WINDOW_SIZE);
  const refreshedWindow = eligible.slice(
    ONE_TO_ONE_WINDOW_SIZE,
    ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE
  );
  assert.deepEqual(initialWindow.map((c) => c.rank), [1, 2, 4]);
  assert.deepEqual(refreshedWindow.map((c) => c.rank), [5, 6, 7]);
});

test("eligible selection drops self and duplicate uids", () => {
  const candidates = [
    { uid: "viewer", rank: 1 },
    { uid: "a", rank: 2 },
    { uid: "a", rank: 3 },
    { uid: "b", rank: 4 },
  ];
  const eligible = selectEligibleRefreshCandidates({
    candidates,
    viewerUid: "viewer",
    blockedUids: new Set(),
    profileByUid: new Map([
      ["a", displayableProfile()],
      ["b", displayableProfile()],
    ]),
    ...NO_ZONES,
  });
  assert.deepEqual(eligible.map((c) => c.uid), ["a", "b"]);
});

// ---------------------------------------------------------------------------
// CASE A: raw 6 / eligible 5 -> purchase rejected, no debit
// ---------------------------------------------------------------------------

test("CASE A: six raw candidates but five eligible must not charge", () => {
  const candidates = candidatesOfRanks([1, 2, 3, 4, 5, 6]);
  const profiles = profilesFor(candidates);
  profiles.set("cand_4", null); // 탈퇴로 public 문서 없음 -> eligible 5명
  const eligible = selectEligibleRefreshCandidates({
    candidates,
    viewerUid: "viewer",
    blockedUids: new Set(),
    profileByUid: profiles,
    ...NO_ZONES,
  });
  assert.equal(eligible.length, 5);

  const decision = evaluateRefreshPurchase(
    readyPurchaseInput({ eligibleCandidateCount: eligible.length })
  );
  assert.deepEqual(decision, {
    kind: "unavailable",
    reason: "not_enough_eligible_candidates",
  });
});

// ---------------------------------------------------------------------------
// CASE B: raw 8, two blocked -> eligible 6, refresh shows eligible 4th..6th
// ---------------------------------------------------------------------------

test("CASE B: eight raw with two blocked charges and reveals eligible 4th-6th", () => {
  const candidates = candidatesOfRanks([1, 2, 3, 4, 5, 6, 7, 8]);
  const eligible = selectEligibleRefreshCandidates({
    candidates,
    viewerUid: "viewer",
    blockedUids: new Set(["cand_2", "cand_5"]),
    profileByUid: profilesFor(candidates),
    ...NO_ZONES,
  });
  assert.equal(eligible.length, 6);
  assert.deepEqual(eligible.map((c) => c.rank), [1, 3, 4, 6, 7, 8]);

  const decision = evaluateRefreshPurchase(
    readyPurchaseInput({ eligibleCandidateCount: eligible.length })
  );
  assert.deepEqual(decision, {
    kind: "charge",
    balanceAfter: 10 - ONE_TO_ONE_REFRESH_COST_HEARTS,
  });

  const paidWindow = eligible.slice(
    ONE_TO_ONE_WINDOW_SIZE,
    ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE
  );
  assert.deepEqual(paidWindow.map((c) => c.uid), ["cand_6", "cand_7", "cand_8"]);
  assert.deepEqual(paidWindow.map((c) => c.rank), [6, 7, 8]);
});

// ---------------------------------------------------------------------------
// CASE D: source doc replaced between eligibility check and the transaction
// ---------------------------------------------------------------------------

test("CASE D: a source change between eligibility check and commit is stale, "
  + "never a charge", () => {
  const decision = evaluateRefreshPurchase(
    readyPurchaseInput({ sourceUnchanged: false, heartBalance: 100 })
  );
  assert.deepEqual(decision, { kind: "stale" });
});

// ---------------------------------------------------------------------------
// TOCTOU: commit-time re-validation of the exact paid trio (CASE 1/2/4/5)
// ---------------------------------------------------------------------------

test("TOCTOU CASE 1: a candidate blocked between precheck and commit rejects "
  + "the purchase without a debit", () => {
  // precheck 시점엔 E/F/G 모두 valid 였다고 가정하고, commit 재읽기에서
  // E 가 blocked 로 드러난 상태.
  const states = [
    commitState("E", { blocked: true }),
    commitState("F"),
    commitState("G"),
  ];
  assert.equal(
    areDisplayCandidatesStillEligible(commitCheckInput(states)),
    false
  );
  const decision = evaluateRefreshPurchase(
    readyPurchaseInput({ displayCandidatesStillEligible: false })
  );
  assert.deepEqual(decision, { kind: "stale_eligibility" });
});

test("TOCTOU CASE 2: a public profile deleted before commit rejects the "
  + "purchase without a debit", () => {
  const states = [
    commitState("E"),
    commitState("F", { profile: null }),
    commitState("G"),
  ];
  assert.equal(
    areDisplayCandidatesStillEligible(commitCheckInput(states)),
    false
  );
  assert.deepEqual(
    evaluateRefreshPurchase(
      readyPurchaseInput({ displayCandidatesStillEligible: false })
    ),
    { kind: "stale_eligibility" }
  );
});

test("TOCTOU: an activated recommendation exclusion at commit also rejects", () => {
  const states = [
    commitState("E", { exclusionActive: true }),
    commitState("F"),
    commitState("G"),
  ];
  assert.equal(
    areDisplayCandidatesStillEligible(commitCheckInput(states)),
    false
  );
});

test("TOCTOU: commit-time campus zone incompatibility rejects when enforced", () => {
  const states = [
    commitState("E"),
    commitState("F", {
      profile: displayableProfile({
        onboarding: {
          avatarUrls: ["https://storage.googleapis.com/seolleyeon-final/a.png"],
          campusLifeZones: ["songdo"],
        },
      }),
    }),
    commitState("G"),
  ];
  assert.equal(
    areDisplayCandidatesStillEligible(
      commitCheckInput(states, {
        enforceCampusZone: true,
        viewerZones: new Set(["sinchon"]),
      })
    ),
    false
  );
});

test("TOCTOU: self, duplicates, and short trios never pass the commit check", () => {
  assert.equal(
    areDisplayCandidatesStillEligible(
      commitCheckInput([
        commitState("viewer"),
        commitState("F"),
        commitState("G"),
      ])
    ),
    false
  );
  assert.equal(
    areDisplayCandidatesStillEligible(
      commitCheckInput([commitState("E"), commitState("E"), commitState("G")])
    ),
    false
  );
  assert.equal(
    areDisplayCandidatesStillEligible(
      commitCheckInput([commitState("E"), commitState("F")])
    ),
    false
  );
});

test("TOCTOU CASE 4: three healthy candidates at commit charge exactly once "
  + "for exactly the price", () => {
  const states = [commitState("E"), commitState("F"), commitState("G")];
  assert.equal(
    areDisplayCandidatesStillEligible(commitCheckInput(states)),
    true
  );
  const decision = evaluateRefreshPurchase(readyPurchaseInput());
  assert.deepEqual(decision, {
    kind: "charge",
    balanceAfter: 10 - ONE_TO_ONE_REFRESH_COST_HEARTS,
  });
  // 결제로 저장/노출되는 identity 는 정확히 3명이다.
  assert.equal(states.length, ONE_TO_ONE_WINDOW_SIZE);
});

test("TOCTOU CASE 5: a retry after completion wins over a later eligibility "
  + "failure — no second debit", () => {
  const decision = evaluateRefreshPurchase(
    readyPurchaseInput({
      entitlementStatus: "completed",
      displayCandidatesStillEligible: false,
      sourceUnchanged: false,
      heartBalance: 0,
    })
  );
  assert.deepEqual(decision, { kind: "already_purchased" });
});

test("exclusion activity mirrors the client contract (active flag or any "
  + "enabledBy source)", () => {
  assert.equal(isExclusionActive(null), false);
  assert.equal(isExclusionActive({}), false);
  assert.equal(isExclusionActive({ active: true }), true);
  assert.equal(isExclusionActive({ enabledBy: { kakao: true } }), true);
  assert.equal(isExclusionActive({ enabledBy: { kakao: false } }), false);
});

// ---------------------------------------------------------------------------
// Payment decision matrix
// ---------------------------------------------------------------------------

test("a balance of exactly the price is sufficient and ends at zero", () => {
  const decision = evaluateRefreshPurchase(
    readyPurchaseInput({ heartBalance: ONE_TO_ONE_REFRESH_COST_HEARTS })
  );
  assert.deepEqual(decision, { kind: "charge", balanceAfter: 0 });
});

test("one heart short is rejected without touching the balance", () => {
  const decision = evaluateRefreshPurchase(
    readyPurchaseInput({ heartBalance: ONE_TO_ONE_REFRESH_COST_HEARTS - 1 })
  );
  assert.deepEqual(decision, { kind: "insufficient_hearts" });
});

test("corrupted balances are treated as zero, never as spendable", () => {
  for (const balance of [Number.NaN, -3, Number.NEGATIVE_INFINITY]) {
    assert.deepEqual(
      evaluateRefreshPurchase(readyPurchaseInput({ heartBalance: balance })),
      { kind: "insufficient_hearts" }
    );
  }
});

test("a source that is not ready never charges", () => {
  for (const status of [null, "pending", "failed", ""]) {
    assert.deepEqual(
      evaluateRefreshPurchase(readyPurchaseInput({ sourceStatus: status })),
      { kind: "unavailable", reason: "source_not_ready" }
    );
  }
});

test("a completed entitlement is idempotent before every other check", () => {
  // Retry after success must NOT surface stale/insufficient: the first call
  // already charged, so the retry reports success without a second debit.
  const decision = evaluateRefreshPurchase(
    readyPurchaseInput({
      entitlementStatus: "completed",
      sourceUnchanged: false,
      eligibleCandidateCount: 0,
      heartBalance: 0,
    })
  );
  assert.deepEqual(decision, { kind: "already_purchased" });
});

test("an unknown entitlement state fails closed instead of recharging", () => {
  const decision = evaluateRefreshPurchase(
    readyPurchaseInput({ entitlementStatus: "pending", heartBalance: 100 })
  );
  assert.deepEqual(decision, {
    kind: "unavailable",
    reason: "entitlement_state_unknown",
  });
});

test("display rank window is the fixed 4..6 v1 contract", () => {
  assert.equal(ONE_TO_ONE_REFRESH_DISPLAY_RANK_START, 4);
  assert.equal(ONE_TO_ONE_REFRESH_DISPLAY_RANK_END, 6);
  assert.equal(ONE_TO_ONE_REFRESH_REQUIRED_ELIGIBLE, 6);
});
