import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  AVOIDANCE_MUTATION_FIELD,
  buildAvoidanceMutationCompletion,
  buildAvoidanceMutationFailure,
  buildAvoidanceMutationStart,
  buildKakaoFriendPairId,
  buildKakaoFriendPairUpsert,
  buildLegacyKakaoSyncFailureRevert,
  buildPairExclusionDoc,
  buildSnapshotCompletionUpdate,
  buildSnapshotFailureUpdate,
  buildSnapshotLeaseUpdate,
  decideAvoidanceToggle,
  decideLegacySweepDeletion,
  decideSnapshotIdentityPrecondition,
  decideSnapshotLease,
  executeSetKakaoFriendAvoidanceEnabled,
  isCanonicalKakaoFriendPairId,
  isCurrentAvoidanceGeneration,
  isDeletableKakaoPairExclusion,
  isEffectiveAvoidanceEnabled,
  isKakaoOwnedExclusion,
  isKakaoPairIdForMembers,
  isValidKakaoFriendPairMemberUid,
  KAKAO_FRIEND_PAIR_UID_MAX_LENGTH,
  readAvoidanceMutationGeneration,
  reconcileKakaoFriendAvoidanceForUser,
  sanitizeSnapshotErrorCode,
  snapshotRunOwnsLease,
  SNAPSHOT_LEASE_STALE_MS,
  type SetKakaoFriendAvoidanceEnabledDeps,
} from "./kakaoFriendPairs";
import {
  buildRecommendationExclusionPairId,
  hasActiveRecommendationExclusion,
} from "./kakaoFriendRecommendationPrivacy";
import { isExclusionActive } from "./recommendationRefresh";
import { FieldValue, type Firestore } from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";

const NOW = new Date("2026-09-01T12:00:00.000Z");
const CANON_AB = buildKakaoFriendPairId("uid_a", "uid_b");

function minutesBefore(now: Date, minutes: number): Date {
  return new Date(now.getTime() - minutes * 60 * 1000);
}

// ============================================================================
// Snapshot lease decisions (contract §3)
// ============================================================================

test("missing, not_started, failed, or malformed snapshot state acquires the lease", () => {
  assert.deepEqual(decideSnapshotLease({ state: undefined, now: NOW }), {
    action: "acquire",
  });
  assert.deepEqual(
    decideSnapshotLease({ state: { status: "not_started" }, now: NOW }),
    { action: "acquire" },
  );
  assert.deepEqual(
    decideSnapshotLease({
      state: { status: "failed", errorCode: "kakao_friends_http_401" },
      now: NOW,
    }),
    { action: "acquire" },
  );
  assert.deepEqual(decideSnapshotLease({ state: "junk", now: NOW }), {
    action: "acquire",
  });
});

test("completed snapshot is idempotent and immutable — never re-acquired", () => {
  assert.deepEqual(
    decideSnapshotLease({
      state: { status: "completed", pairCount: 7 },
      now: NOW,
    }),
    { action: "alreadyCompleted", pairCount: 7 },
  );
  // Missing/invalid pairCount degrades to 0, still completed.
  assert.deepEqual(
    decideSnapshotLease({ state: { status: "completed" }, now: NOW }),
    { action: "alreadyCompleted", pairCount: 0 },
  );
});

test("a fresh in_progress lease rejects concurrent runs", () => {
  assert.deepEqual(
    decideSnapshotLease({
      state: {
        status: "in_progress",
        snapshotRunId: "run_1",
        startedAt: minutesBefore(NOW, 5),
      },
      now: NOW,
    }),
    { action: "inProgress" },
  );
});

test("a stale in_progress lease (>10 minutes) can be taken over", () => {
  assert.deepEqual(
    decideSnapshotLease({
      state: {
        status: "in_progress",
        snapshotRunId: "run_1",
        startedAt: minutesBefore(NOW, 11),
      },
      now: NOW,
    }),
    { action: "acquire" },
  );
  // Timestamp-like startedAt (Firestore Timestamp exposes toMillis()).
  assert.deepEqual(
    decideSnapshotLease({
      state: {
        status: "in_progress",
        startedAt: { toMillis: () => NOW.getTime() - SNAPSHOT_LEASE_STALE_MS },
      },
      now: NOW,
    }),
    { action: "acquire" },
  );
  // An unreadable startedAt could never expire — treated as stale.
  assert.deepEqual(
    decideSnapshotLease({
      state: { status: "in_progress", snapshotRunId: "run_1" },
      now: NOW,
    }),
    { action: "acquire" },
  );
});

test("lease update always carries run id, startedAt, and schemaVersion", () => {
  assert.deepEqual(
    buildSnapshotLeaseUpdate({ snapshotRunId: "run_9", now: NOW }),
    {
      status: "in_progress",
      snapshotRunId: "run_9",
      startedAt: NOW,
      schemaVersion: 1,
    },
  );
});

// ============================================================================
// snapshotRunId completion guard (contract §4 step 6/7)
// ============================================================================

test("only the run that owns the lease may finalize", () => {
  const owned = { status: "in_progress", snapshotRunId: "run_1" };
  assert.equal(snapshotRunOwnsLease(owned, "run_1"), true);
  assert.equal(snapshotRunOwnsLease(owned, "run_2"), false); // takeover
  assert.equal(
    snapshotRunOwnsLease({ status: "completed", snapshotRunId: "run_1" }, "run_1"),
    false, // completed is terminal — a stale run can never re-finalize
  );
  assert.equal(snapshotRunOwnsLease(null, "run_1"), false);
  assert.equal(snapshotRunOwnsLease(owned, ""), false);
});

test("completion update drops the lease and records pairCount", () => {
  const update = buildSnapshotCompletionUpdate({
    previousState: {
      status: "in_progress",
      snapshotRunId: "run_1",
      startedAt: minutesBefore(NOW, 1),
    },
    pairCount: 12,
    now: NOW,
  });
  assert.equal(update.status, "completed");
  assert.equal(update.pairCount, 12);
  assert.equal(update.completedAt, NOW);
  assert.deepEqual(update.startedAt, minutesBefore(NOW, 1));
  assert.equal("snapshotRunId" in update, false);
});

test("failure update never marks completed and sanitizes the error code", () => {
  const update = buildSnapshotFailureUpdate({
    previousState: { status: "in_progress", snapshotRunId: "run_1" },
    errorCode: "kakao_friends_http_429",
    now: NOW,
  });
  assert.equal(update.status, "failed");
  assert.notEqual(update.status, "completed");
  assert.equal(update.errorCode, "kakao_friends_http_429");
  assert.equal(update.failedAt, NOW);
  assert.equal("snapshotRunId" in update, false);
  assert.equal("pairCount" in update, false);

  const oversized = buildSnapshotFailureUpdate({
    previousState: {},
    errorCode: "x".repeat(200),
    now: NOW,
  });
  assert.equal((oversized.errorCode as string).length, 80);
});

test("sanitized error codes are bounded and free of PII-capable characters", () => {
  assert.equal(
    sanitizeSnapshotErrorCode(new Error("kakao_friends_http_500")),
    "kakao_friends_http_500",
  );
  const withEmail = sanitizeSnapshotErrorCode(
    new Error("failed for student@yonsei.ac.kr <token abc>"),
  );
  assert.equal(withEmail.includes("@"), false);
  assert.equal(withEmail.includes("<"), false);
  assert.equal(withEmail.length <= 80, true);
  assert.equal(sanitizeSnapshotErrorCode(undefined), "unknown");
  assert.equal(
    sanitizeSnapshotErrorCode(new Error("x".repeat(500))).length,
    80,
  );
});

// ============================================================================
// Identity precondition (contract §4)
// ============================================================================

test("identity precondition accepts legacy uid==kakaoId, legacy claim, and mapping", () => {
  assert.deepEqual(
    decideSnapshotIdentityPrecondition({
      authUid: "12345",
      claimedKakaoUserId: null,
      verifiedKakaoUserId: "12345",
      mappingAppUserId: null,
    }),
    { ok: true },
  );
  assert.deepEqual(
    decideSnapshotIdentityPrecondition({
      authUid: "app_user_1",
      claimedKakaoUserId: null,
      verifiedKakaoUserId: "999",
      mappingAppUserId: "app_user_1",
    }),
    { ok: true },
  );
});

test("identity precondition fails closed on unlinked or conflicting identities", () => {
  assert.deepEqual(
    decideSnapshotIdentityPrecondition({
      authUid: "app_user_1",
      claimedKakaoUserId: null,
      verifiedKakaoUserId: "999",
      mappingAppUserId: null,
    }),
    { ok: false, reason: "kakao_identity_not_linked" },
  );
  assert.deepEqual(
    decideSnapshotIdentityPrecondition({
      authUid: "app_user_1",
      claimedKakaoUserId: null,
      verifiedKakaoUserId: "999",
      mappingAppUserId: "app_user_2",
    }),
    { ok: false, reason: "identity_conflict" },
  );
});

// ============================================================================
// Pair upsert build (contract §2, §4 step 4, spec §13/§37)
// ============================================================================

test("pair upsert sorts memberUids and is directionless (same pairId both ways)", () => {
  const fromCaller = buildKakaoFriendPairUpsert({
    callerUid: "uid_b",
    friendUid: "uid_a",
    callerAvoidanceEnabled: false,
    friendAvoidanceEnabled: false,
    existingPairData: null,
  });
  const fromFriend = buildKakaoFriendPairUpsert({
    callerUid: "uid_a",
    friendUid: "uid_b",
    callerAvoidanceEnabled: false,
    friendAvoidanceEnabled: false,
    existingPairData: null,
  });
  assert.equal(fromCaller.pairId, CANON_AB);
  assert.equal(isCanonicalKakaoFriendPairId(fromCaller.pairId), true);
  assert.equal(fromCaller.pairId, fromFriend.pairId);
  assert.deepEqual(fromCaller.memberUids, ["uid_a", "uid_b"]);
  assert.deepEqual(fromFriend.memberUids, ["uid_a", "uid_b"]);
  assert.equal(fromCaller.isNewPair, true);
  assert.equal(fromCaller.avoidanceActive, false);
  assert.deepEqual(fromCaller.avoidanceEnabledBy, []);
});

test("pair upsert unions discoveredByUids with the existing doc", () => {
  const upsert = buildKakaoFriendPairUpsert({
    callerUid: "uid_b",
    friendUid: "uid_a",
    callerAvoidanceEnabled: false,
    friendAvoidanceEnabled: false,
    existingPairData: {
      discoveredByUids: ["uid_a", "stranger_uid"],
      avoidanceEnabledBy: [],
    },
  });
  // Union keeps the counterpart's discovery; non-members never leak in.
  assert.deepEqual(upsert.discoveredByUids, ["uid_a", "uid_b"]);
  assert.equal(upsert.isNewPair, false);
});

test("spec §37: counterpart already ON yields avoidanceEnabledBy=[B] and an active pair", () => {
  const upsert = buildKakaoFriendPairUpsert({
    callerUid: "uid_a",
    friendUid: "uid_b",
    callerAvoidanceEnabled: false,
    friendAvoidanceEnabled: true,
    existingPairData: null,
  });
  assert.deepEqual(upsert.avoidanceEnabledBy, ["uid_b"]);
  assert.equal(upsert.avoidanceActive, true);
});

test("pair upsert derives avoidanceEnabledBy from both current preferences", () => {
  const bothOn = buildKakaoFriendPairUpsert({
    callerUid: "uid_b",
    friendUid: "uid_a",
    callerAvoidanceEnabled: true,
    friendAvoidanceEnabled: true,
    existingPairData: null,
  });
  assert.deepEqual(bothOn.avoidanceEnabledBy, ["uid_a", "uid_b"]);
  assert.equal(bothOn.avoidanceActive, true);

  // A preference that is now OFF does not survive from the existing doc.
  const nowOff = buildKakaoFriendPairUpsert({
    callerUid: "uid_a",
    friendUid: "uid_b",
    callerAvoidanceEnabled: false,
    friendAvoidanceEnabled: false,
    existingPairData: { avoidanceEnabledBy: ["uid_a", "uid_b"] },
  });
  assert.deepEqual(nowOff.avoidanceEnabledBy, []);
  assert.equal(nowOff.avoidanceActive, false);
});

// ============================================================================
// Avoidance toggle decisions (contract §5, spec §54 OR-semantics)
// ============================================================================

function pairDoc(
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    pairId: CANON_AB,
    memberUids: ["uid_a", "uid_b"],
    source: "kakao_friend_snapshot",
    discoveredByUids: ["uid_a"],
    avoidanceEnabledBy: [],
    avoidanceActive: false,
    schemaVersion: 1,
    ...overrides,
  };
}

test("spec §54 OR-semantics: all four enable/disable combinations", () => {
  // OFF/OFF + A enables -> [A], materialize.
  const aOn = decideAvoidanceToggle({
    pairData: pairDoc(),
    uid: "uid_a",
    enabled: true,
  });
  assert.deepEqual(aOn, {
    memberUids: ["uid_a", "uid_b"],
    pairId: CANON_AB,
    avoidanceEnabledBy: ["uid_a"],
    avoidanceActive: true,
    action: "materialize",
  });

  // B already ON + A enables -> both, still materialize.
  const bothOn = decideAvoidanceToggle({
    pairData: pairDoc({ avoidanceEnabledBy: ["uid_b"], avoidanceActive: true }),
    uid: "uid_a",
    enabled: true,
  });
  assert.deepEqual(bothOn?.avoidanceEnabledBy, ["uid_a", "uid_b"]);
  assert.equal(bothOn?.action, "materialize");

  // B still ON + A disables -> exclusions KEPT (OR-semantics).
  const aOffBOn = decideAvoidanceToggle({
    pairData: pairDoc({
      avoidanceEnabledBy: ["uid_a", "uid_b"],
      avoidanceActive: true,
    }),
    uid: "uid_a",
    enabled: false,
  });
  assert.deepEqual(aOffBOn?.avoidanceEnabledBy, ["uid_b"]);
  assert.equal(aOffBOn?.avoidanceActive, true);
  assert.equal(aOffBOn?.action, "materialize");

  // Last member OFF -> remove.
  const lastOff = decideAvoidanceToggle({
    pairData: pairDoc({ avoidanceEnabledBy: ["uid_b"], avoidanceActive: true }),
    uid: "uid_b",
    enabled: false,
  });
  assert.deepEqual(lastOff?.avoidanceEnabledBy, []);
  assert.equal(lastOff?.avoidanceActive, false);
  assert.equal(lastOff?.action, "remove");
});

test("A-then-B off sequence keeps exclusions until the last member turns off", () => {
  const afterAOff = decideAvoidanceToggle({
    pairData: pairDoc({
      avoidanceEnabledBy: ["uid_a", "uid_b"],
      avoidanceActive: true,
    }),
    uid: "uid_a",
    enabled: false,
  });
  assert.equal(afterAOff?.action, "materialize"); // B still ON -> kept
  const afterBOff = decideAvoidanceToggle({
    pairData: pairDoc({
      avoidanceEnabledBy: afterAOff?.avoidanceEnabledBy,
      avoidanceActive: afterAOff?.avoidanceActive,
    }),
    uid: "uid_b",
    enabled: false,
  });
  assert.equal(afterBOff?.action, "remove"); // now exclusions go away
  assert.deepEqual(afterBOff?.avoidanceEnabledBy, []);
});

test("toggle decisions never delete the pair doc and ignore non-member junk", () => {
  const decision = decideAvoidanceToggle({
    pairData: pairDoc({ avoidanceEnabledBy: ["stranger_uid", "uid_b"] }),
    uid: "uid_b",
    enabled: false,
  });
  // Non-member entries are dropped, and the only possible actions are
  // materialize/remove of EXCLUSION docs — there is no pair-delete action.
  assert.deepEqual(decision?.avoidanceEnabledBy, []);
  assert.equal(decision?.action, "remove");
  assert.equal(Object.keys(decision ?? {}).includes("deletePair"), false);

  // Malformed pair docs (or a uid outside memberUids) are skipped entirely.
  assert.equal(
    decideAvoidanceToggle({
      pairData: { memberUids: ["uid_a"] },
      uid: "uid_a",
      enabled: true,
    }),
    null,
  );
  assert.equal(
    decideAvoidanceToggle({
      pairData: pairDoc(),
      uid: "uid_c",
      enabled: true,
    }),
    null,
  );
});

// ============================================================================
// Exclusion doc shape (contract §6) — predicate compatibility
// ============================================================================

test("pair exclusion doc matches contract §6 and every active-predicate", () => {
  const doc = buildPairExclusionDoc({
    pairId: CANON_AB,
    memberUids: ["uid_b", "uid_a"],
    avoidanceEnabledBy: ["uid_b"],
  });
  assert.deepEqual(doc, {
    pairId: CANON_AB,
    userIds: ["uid_a", "uid_b"],
    source: "kakao_friend_pair",
    reason: "kakao_friend_avoidance",
    active: true,
    enabledBy: { uid_a: false, uid_b: true },
  });
  // Server predicate (recommendationRefresh.isExclusionActive).
  assert.equal(isExclusionActive(doc), true);
  // Legacy enabledBy-map predicate (any-true).
  assert.equal(hasActiveRecommendationExclusion(doc), true);
  // Deletion safety predicate accepts its own docs.
  assert.equal(isKakaoOwnedExclusion(doc), true);
});

// ============================================================================
// Deletion safety predicate (contract §6, spec §57)
// ============================================================================

test("only kakao_friend_pair and kakao_talk_friend exclusions are deletable", () => {
  assert.equal(isKakaoOwnedExclusion({ source: "kakao_friend_pair" }), true);
  assert.equal(isKakaoOwnedExclusion({ source: "kakao_talk_friend" }), true);
  // spec §57: any other producer is protected forever.
  assert.equal(isKakaoOwnedExclusion({ source: "manual" }), false);
  assert.equal(isKakaoOwnedExclusion({ source: "report_block" }), false);
  assert.equal(isKakaoOwnedExclusion({}), false);
  assert.equal(isKakaoOwnedExclusion(null), false);
  assert.equal(isKakaoOwnedExclusion(undefined), false);
  assert.equal(isKakaoOwnedExclusion({ source: 42 }), false);
});

// ============================================================================
// Legacy sweep decisions (contract §4 step 5)
// ============================================================================

test("legacy sweep keeps docs re-materialized as active pairs this run", () => {
  assert.deepEqual(
    decideLegacySweepDeletion({
      callerUid: "uid_a",
      targetUid: "uid_b",
      rematerializedActiveTargetUids: new Set(["uid_b"]),
      reverseDocData: { source: "kakao_talk_friend", pairId: "uid_a_uid_b" },
    }),
    { deleteForward: false, deleteReverse: false },
  );
});

test("legacy sweep deletes stale kakao_talk_friend docs incl. matching reverse", () => {
  assert.deepEqual(
    decideLegacySweepDeletion({
      callerUid: "uid_a",
      targetUid: "uid_b",
      rematerializedActiveTargetUids: new Set(),
      reverseDocData: { source: "kakao_talk_friend", pairId: "uid_a_uid_b" },
    }),
    { deleteForward: true, deleteReverse: true },
  );
  // Reverse under the new source with the same pairId is also Kakao-owned.
  assert.deepEqual(
    decideLegacySweepDeletion({
      callerUid: "uid_b",
      targetUid: "uid_a",
      rematerializedActiveTargetUids: new Set(),
      reverseDocData: { source: "kakao_friend_pair", pairId: "uid_a_uid_b" },
    }),
    { deleteForward: true, deleteReverse: true },
  );
});

test("legacy sweep never deletes reverse docs from other sources or other pairs", () => {
  // Foreign source on the reverse doc -> forward only.
  assert.deepEqual(
    decideLegacySweepDeletion({
      callerUid: "uid_a",
      targetUid: "uid_b",
      rematerializedActiveTargetUids: new Set(),
      reverseDocData: { source: "manual", pairId: "uid_a_uid_b" },
    }),
    { deleteForward: true, deleteReverse: false },
  );
  // pairId mismatch -> forward only.
  assert.deepEqual(
    decideLegacySweepDeletion({
      callerUid: "uid_a",
      targetUid: "uid_b",
      rematerializedActiveTargetUids: new Set(),
      reverseDocData: { source: "kakao_talk_friend", pairId: "uid_a_uid_c" },
    }),
    { deleteForward: true, deleteReverse: false },
  );
  // Missing reverse doc -> forward only.
  assert.deepEqual(
    decideLegacySweepDeletion({
      callerUid: "uid_a",
      targetUid: "uid_b",
      rematerializedActiveTargetUids: new Set(),
      reverseDocData: null,
    }),
    { deleteForward: true, deleteReverse: false },
  );
});

// ============================================================================
// Grep-able invariants (contract §12) — source scans
// ============================================================================

const pairsSrc = readFileSync(
  resolve(__dirname, "../src/kakaoFriendPairs.ts"),
  "utf8",
);
const indexSrc = readFileSync(resolve(__dirname, "../src/index.ts"), "utf8");

test("snapshot callable reuses the existing fetch/resolve helpers", () => {
  // The pagination/SSRF/5000-cap fetch helper is injected by index.ts.
  assert.match(
    indexSrc,
    /fetchFriends:\s*\(accessToken\)\s*=>\s*\n?\s*fetchKakaoFriendServiceUserIds\(accessToken/,
  );
  assert.match(pairsSrc, /resolveFriendExclusionAppUserIds\(/);
  assert.match(pairsSrc, /buildRecommendationExclusionPairId/);
});

test("every exclusion deletion in the new module is source-checked", () => {
  // Each batch/transaction delete of an exclusion ref sits behind the
  // isKakaoOwnedExclusion predicate or the legacy sweep decision.
  const deleteCalls = pairsSrc.match(/\.(?:delete)\(/g) ?? [];
  assert.equal(deleteCalls.length > 0, true);
  assert.match(pairsSrc, /isKakaoOwnedExclusion\(/);
  assert.match(pairsSrc, /decideLegacySweepDeletion\(/);
});

test("legacy sync endpoints carry the deprecation marker for old clients", () => {
  const markers = indexSrc.match(
    /LEGACY_KAKAO_SYNC_BACKEND_STILL_REQUIRED_FOR_OLD_CLIENTS/g,
  );
  assert.equal((markers ?? []).length, 2);
});

test("recommendationRefresh no longer carries the recommendationPrivacyReady gate", () => {
  const refreshSrc = readFileSync(
    resolve(__dirname, "../src/recommendationRefresh.ts"),
    "utf8",
  );
  assert.doesNotMatch(refreshSrc, /recommendationPrivacyReady/);
});

// ============================================================================
// Blocker #2 — collision-safe canonical pairId
// ============================================================================

test("canonical pairId is 64-char lowercase hex and order-independent", () => {
  const ab = buildKakaoFriendPairId("uid_a", "uid_b");
  const ba = buildKakaoFriendPairId("uid_b", "uid_a");
  assert.equal(ab, ba);
  assert.match(ab, /^[0-9a-f]{64}$/);
  assert.equal(isCanonicalKakaoFriendPairId(ab), true);
  assert.equal(isCanonicalKakaoFriendPairId("uid_a_uid_b"), false);
  assert.equal(isCanonicalKakaoFriendPairId(ab.toUpperCase()), false);
  assert.equal(isCanonicalKakaoFriendPairId(null), false);
});

test("delimiter-ambiguous pairs no longer collide (legacy format does)", () => {
  // The legacy joined format collides on exactly this input pair.
  assert.equal(
    buildRecommendationExclusionPairId("a_b", "c"),
    buildRecommendationExclusionPairId("a", "b_c"),
  );
  assert.notEqual(
    buildKakaoFriendPairId("a_b", "c"),
    buildKakaoFriendPairId("a", "b_c"),
  );
});

test("pairId builder rejects empty, same, unsafe, and oversized uids", () => {
  assert.throws(() => buildKakaoFriendPairId("", "uid_b"));
  assert.throws(() => buildKakaoFriendPairId("uid_a", ""));
  assert.throws(() => buildKakaoFriendPairId("uid_a", "uid_a"));
  // Unicode / separators are impossible by contract -> rejected outright.
  assert.throws(() => buildKakaoFriendPairId("uid/α", "uid_b"));
  assert.throws(() => buildKakaoFriendPairId("uid a", "uid_b"));
  assert.throws(() => buildKakaoFriendPairId("uid.a", "uid_b"));
  const oversized = "x".repeat(KAKAO_FRIEND_PAIR_UID_MAX_LENGTH + 1);
  assert.throws(() => buildKakaoFriendPairId(oversized, "uid_b"));
  // Boundary length is accepted.
  const atLimit = "x".repeat(KAKAO_FRIEND_PAIR_UID_MAX_LENGTH);
  assert.match(buildKakaoFriendPairId(atLimit, "uid_b"), /^[0-9a-f]{64}$/);

  assert.equal(isValidKakaoFriendPairMemberUid("uid_a-B_0"), true);
  assert.equal(isValidKakaoFriendPairMemberUid(""), false);
  assert.equal(isValidKakaoFriendPairMemberUid("한글uid"), false);
  assert.equal(isValidKakaoFriendPairMemberUid(42), false);
});

test("10,000 generated distinct pairs produce zero duplicate pairIds", () => {
  const uids: string[] = [];
  for (let i = 0; i < 150; i++) uids.push(`u${i}`);
  const seen = new Set<string>();
  let generated = 0;
  outer: for (let i = 0; i < uids.length; i++) {
    for (let j = i + 1; j < uids.length; j++) {
      seen.add(buildKakaoFriendPairId(uids[i], uids[j]));
      generated++;
      if (generated >= 10000) break outer;
    }
  }
  assert.equal(generated, 10000);
  assert.equal(seen.size, 10000);
});

test("dual-format pairId match accepts canonical OR legacy, nothing else", () => {
  assert.equal(isKakaoPairIdForMembers(CANON_AB, "uid_a", "uid_b"), true);
  assert.equal(isKakaoPairIdForMembers("uid_a_uid_b", "uid_a", "uid_b"), true);
  assert.equal(isKakaoPairIdForMembers("uid_a_uid_b", "uid_b", "uid_a"), true);
  assert.equal(isKakaoPairIdForMembers("uid_a_uid_c", "uid_a", "uid_b"), false);
  assert.equal(isKakaoPairIdForMembers(CANON_AB, "uid_a", "uid_c"), false);
  assert.equal(isKakaoPairIdForMembers(undefined, "uid_a", "uid_b"), false);
  assert.equal(isKakaoPairIdForMembers(CANON_AB, "uid_a", "uid_a"), false);
});

test("toggle deletion predicate needs Kakao source AND a matching pairId", () => {
  assert.equal(
    isDeletableKakaoPairExclusion(
      { source: "kakao_friend_pair", pairId: CANON_AB },
      "uid_a",
      "uid_b",
    ),
    true,
  );
  assert.equal(
    isDeletableKakaoPairExclusion(
      { source: "kakao_talk_friend", pairId: "uid_a_uid_b" },
      "uid_a",
      "uid_b",
    ),
    true,
  );
  // Foreign source is never deletable, even with a matching pairId.
  assert.equal(
    isDeletableKakaoPairExclusion(
      { source: "manual", pairId: CANON_AB },
      "uid_a",
      "uid_b",
    ),
    false,
  );
  // Kakao source with a mismatched/missing pairId stays (over-exclusion).
  assert.equal(
    isDeletableKakaoPairExclusion(
      { source: "kakao_friend_pair", pairId: "uid_x_uid_y" },
      "uid_a",
      "uid_b",
    ),
    false,
  );
  assert.equal(
    isDeletableKakaoPairExclusion(
      { source: "kakao_friend_pair" },
      "uid_a",
      "uid_b",
    ),
    false,
  );
  assert.equal(isDeletableKakaoPairExclusion(null, "uid_a", "uid_b"), false);
});

test("legacy sweep reverse match accepts the canonical hash too", () => {
  assert.deepEqual(
    decideLegacySweepDeletion({
      callerUid: "uid_a",
      targetUid: "uid_b",
      rematerializedActiveTargetUids: new Set(),
      reverseDocData: { source: "kakao_friend_pair", pairId: CANON_AB },
    }),
    { deleteForward: true, deleteReverse: true },
  );
});

test("snapshot doc ids and dry-run counters use the canonical format", () => {
  // Doc id and pairId field come from the same canonical builder.
  assert.match(
    pairsSrc,
    /\.doc\(buildKakaoFriendPairId\(authUid, targetUid\)\)/,
  );
  assert.doesNotMatch(
    pairsSrc,
    /\.doc\(buildRecommendationExclusionPairId\(/,
    "kakaoFriendPairs doc ids must never use the legacy joined format",
  );
  // READ-ONLY migration dry-run gains old-vs-canonical counters.
  const dryRunSrc = readFileSync(
    resolve(
      __dirname,
      "../../scripts/kakao_friend_pairs_migration_dryrun.mjs",
    ),
    "utf8",
  );
  assert.match(dryRunSrc, /oldFormatPairDocs/);
  assert.match(dryRunSrc, /canonicalPairDocs/);
  assert.match(dryRunSrc, /\^\[0-9a-f\]\{64\}\$/);
  // Still read-only against Firestore: no write API is ever invoked.
  assert.doesNotMatch(dryRunSrc, /\.set\(|\.delete\(|\.update\(|\.batch\(/);
});

// ============================================================================
// Blocker #3 — avoidance mutation state (pure decisions)
// ============================================================================

test("mutation start bumps the generation via CAS-supersede", () => {
  const first = buildAvoidanceMutationStart({
    currentMutation: undefined,
    desired: true,
    now: NOW,
  });
  assert.equal(first.generation, 1);
  assert.deepEqual(first.mutation, {
    desired: true,
    status: "enabling",
    generation: 1,
    startedAt: NOW,
  });
  // A fresh conflicting mutation (different desired) is superseded, never
  // merged: the new request just takes generation+1 and proceeds.
  const superseded = buildAvoidanceMutationStart({
    currentMutation: first.mutation,
    desired: false,
    now: NOW,
  });
  assert.equal(superseded.generation, 2);
  assert.equal(superseded.mutation.status, "disabling");
  // Malformed stored generations restart from 1.
  assert.equal(
    buildAvoidanceMutationStart({
      currentMutation: { generation: "junk" },
      desired: true,
      now: NOW,
    }).generation,
    1,
  );
  assert.equal(readAvoidanceMutationGeneration({ generation: 7.9 }), 7);
  assert.equal(readAvoidanceMutationGeneration(null), 0);
  assert.equal(readAvoidanceMutationGeneration({ generation: -3 }), 0);
});

test("generation currency check is exact — stale and newer both fail", () => {
  const userData = {
    [AVOIDANCE_MUTATION_FIELD]: {
      desired: true,
      status: "enabling",
      generation: 3,
    },
  };
  assert.equal(isCurrentAvoidanceGeneration(userData, 3), true);
  assert.equal(isCurrentAvoidanceGeneration(userData, 2), false);
  assert.equal(isCurrentAvoidanceGeneration(userData, 4), false);
  assert.equal(isCurrentAvoidanceGeneration({}, 1), false);
  assert.equal(isCurrentAvoidanceGeneration(null, 1), false);
  assert.equal(isCurrentAvoidanceGeneration(userData, 0), false);
});

test("mutation completion and failure records keep desired + generation", () => {
  const mutation = {
    desired: true,
    status: "enabling" as const,
    generation: 5,
    startedAt: NOW,
  };
  assert.deepEqual(buildAvoidanceMutationCompletion({ mutation, now: NOW }), {
    desired: true,
    status: "completed",
    generation: 5,
    startedAt: NOW,
    completedAt: NOW,
  });
  const failure = buildAvoidanceMutationFailure({ mutation, now: NOW });
  assert.equal(failure.status, "failed");
  assert.notEqual(failure.status, "completed");
  assert.equal(failure.generation, 5);
});

test("effective avoidance counts committed prefs and in-flight ON mutations", () => {
  assert.equal(
    isEffectiveAvoidanceEnabled({ kakaoFriendAvoidanceEnabled: true }),
    true,
  );
  // In-flight ON: preference still false, but a concurrent snapshot must not
  // deactivate pairs the toggle is materializing (over-exclusion bias).
  assert.equal(
    isEffectiveAvoidanceEnabled({
      kakaoFriendAvoidanceEnabled: false,
      [AVOIDANCE_MUTATION_FIELD]: {
        desired: true,
        status: "enabling",
        generation: 1,
      },
    }),
    true,
  );
  // Disabling / failed / completed mutations defer to the committed pref.
  assert.equal(
    isEffectiveAvoidanceEnabled({
      kakaoFriendAvoidanceEnabled: false,
      [AVOIDANCE_MUTATION_FIELD]: {
        desired: false,
        status: "disabling",
        generation: 1,
      },
    }),
    false,
  );
  assert.equal(
    isEffectiveAvoidanceEnabled({
      kakaoFriendAvoidanceEnabled: false,
      [AVOIDANCE_MUTATION_FIELD]: {
        desired: true,
        status: "failed",
        generation: 1,
      },
    }),
    false,
  );
  assert.equal(
    isEffectiveAvoidanceEnabled({
      kakaoFriendAvoidanceEnabled: false,
      [AVOIDANCE_MUTATION_FIELD]: {
        desired: true,
        status: "completed",
        generation: 1,
      },
    }),
    false,
  );
  assert.equal(isEffectiveAvoidanceEnabled({}), false);
  assert.equal(isEffectiveAvoidanceEnabled(null), false);
});

test("snapshot pair writes run in transactions over both users' current prefs", () => {
  // Contract for the snapshot/toggle interleaving: every pair-level write in
  // the snapshot re-reads the caller doc inside the chunk transaction and
  // derives BOTH members' contributions via isEffectiveAvoidanceEnabled.
  assert.match(
    pairsSrc,
    /const chunkResult = await db\.runTransaction\(async \(transaction\) => \{\s*\n\s*const \[callerSnap, \.\.\.snapshots\] = await transaction\.getAll\(/,
  );
  const effectiveUses = pairsSrc.match(/isEffectiveAvoidanceEnabled\(/g) ?? [];
  assert.equal(
    effectiveUses.length >= 3,
    true,
    "caller + friend snapshot reads must use the effective-preference rule",
  );
});

// ============================================================================
// Blocker #3 — fault-injection harness (spec §13): in-memory fake Firestore
// with an injectable write-failure threshold and atomic transaction commits.
// ============================================================================

type FakeDocData = Record<string, unknown>;

type FakeWrite =
  | { kind: "set"; path: string; data: FakeDocData; merge: boolean }
  | { kind: "update"; path: string; data: FakeDocData }
  | { kind: "delete"; path: string };

function materializeSentinels(data: FakeDocData): FakeDocData {
  const out: FakeDocData = {};
  for (const [key, value] of Object.entries(data)) {
    out[key] = value instanceof FieldValue ? new Date() : value;
  }
  return out;
}

class FakeDocRef {
  constructor(
    readonly fake: FakeFirestore,
    readonly path: string,
  ) {}
  get id(): string {
    const segments = this.path.split("/");
    return segments[segments.length - 1];
  }
  collection(name: string): FakeCollection {
    return new FakeCollection(this.fake, `${this.path}/${name}`);
  }
  async get() {
    return this.fake.snapshotOf(this);
  }
}

class FakeQuery {
  constructor(
    readonly fake: FakeFirestore,
    readonly path: string,
    readonly filters: Array<{ field: string; op: string; value: unknown }>,
  ) {}
  where(field: string, op: string, value: unknown): FakeQuery {
    return new FakeQuery(this.fake, this.path, [
      ...this.filters,
      { field, op, value },
    ]);
  }
  async get() {
    const wantedDepth = this.path.split("/").length + 1;
    const docs = [];
    for (const [path, data] of this.fake.store) {
      if (!path.startsWith(`${this.path}/`)) continue;
      if (path.split("/").length !== wantedDepth) continue;
      const matches = this.filters.every(({ field, op, value }) => {
        const actual = data[field];
        if (op === "==") return actual === value;
        if (op === "array-contains") {
          return Array.isArray(actual) && actual.includes(value);
        }
        throw new Error(`unsupported fake filter op: ${op}`);
      });
      if (!matches) continue;
      docs.push(this.fake.snapshotOf(new FakeDocRef(this.fake, path)));
    }
    return { docs, empty: docs.length === 0, size: docs.length };
  }
}

class FakeCollection extends FakeQuery {
  constructor(fake: FakeFirestore, path: string) {
    super(fake, path, []);
  }
  doc(id: string): FakeDocRef {
    return new FakeDocRef(this.fake, `${this.path}/${id}`);
  }
}

class FakeTransaction {
  readonly writes: FakeWrite[] = [];
  constructor(readonly fake: FakeFirestore) {}
  async get(ref: FakeDocRef) {
    return this.fake.snapshotOf(ref);
  }
  async getAll(...refs: FakeDocRef[]) {
    return refs.map((ref) => this.fake.snapshotOf(ref));
  }
  set(ref: FakeDocRef, data: FakeDocData, opts?: { merge?: boolean }) {
    this.writes.push({
      kind: "set",
      path: ref.path,
      data,
      merge: opts?.merge === true,
    });
    return this;
  }
  update(ref: FakeDocRef, data: FakeDocData) {
    this.writes.push({ kind: "update", path: ref.path, data });
    return this;
  }
  delete(ref: FakeDocRef) {
    this.writes.push({ kind: "delete", path: ref.path });
    return this;
  }
}

class FakeFirestore {
  readonly store = new Map<string, FakeDocData>();
  writeCount = 0;
  /** Injected fault: the transaction whose buffer would cross this commits nothing. */
  failAfterWrites: number | null = null;

  collection(name: string): FakeCollection {
    return new FakeCollection(this, name);
  }

  async runTransaction<T>(fn: (tx: FakeTransaction) => Promise<T>): Promise<T> {
    const tx = new FakeTransaction(this);
    const result = await fn(tx);
    this.applyWrites(tx.writes);
    return result;
  }

  /** Seeding helper — bypasses the write counter and fault injection. */
  seed(path: string, data: FakeDocData): void {
    this.store.set(path, { ...data });
  }

  snapshotOf(ref: FakeDocRef) {
    const data = this.store.get(ref.path);
    return {
      exists: data !== undefined,
      id: ref.id,
      ref,
      data: () => (data === undefined ? undefined : { ...data }),
    };
  }

  applyWrites(writes: FakeWrite[]): void {
    if (
      this.failAfterWrites !== null &&
      this.writeCount + writes.length > this.failAfterWrites
    ) {
      // Transactions are atomic: the whole buffer is rejected.
      throw new Error("injected_write_failure");
    }
    for (const write of writes) {
      this.writeCount++;
      if (write.kind === "delete") {
        this.store.delete(write.path);
        continue;
      }
      const previous = this.store.get(write.path);
      if (write.kind === "update") {
        if (previous === undefined) {
          throw new Error(`update on missing doc: ${write.path}`);
        }
        this.store.set(write.path, {
          ...previous,
          ...materializeSentinels(write.data),
        });
        continue;
      }
      if (write.merge && previous !== undefined) {
        this.store.set(write.path, {
          ...previous,
          ...materializeSentinels(write.data),
        });
      } else {
        this.store.set(write.path, materializeSentinels(write.data));
      }
    }
  }
}

const CALLER = "u_caller";

function toggleDeps(
  fake: FakeFirestore,
  hooks: Partial<
    Pick<
      SetKakaoFriendAvoidanceEnabledDeps,
      "onBeforeReconcile" | "onBeforeFinalize"
    >
  > = {},
): SetKakaoFriendAvoidanceEnabledDeps {
  return {
    db: fake as unknown as Firestore,
    now: () => NOW,
    ...hooks,
  };
}

function friendUidOf(index: number): string {
  return `f_${String(index).padStart(3, "0")}`;
}

function seedPair(
  fake: FakeFirestore,
  friendUid: string,
  avoidanceEnabledBy: string[],
): string {
  const pairId = buildKakaoFriendPairId(CALLER, friendUid);
  const memberUids = [CALLER, friendUid].sort();
  fake.seed(`kakaoFriendPairs/${pairId}`, {
    pairId,
    memberUids,
    source: "kakao_friend_snapshot",
    discoveredByUids: [CALLER],
    avoidanceEnabledBy: [...avoidanceEnabledBy].sort(),
    avoidanceActive: avoidanceEnabledBy.length > 0,
    schemaVersion: 1,
  });
  fake.seed(`users/${friendUid}`, {
    kakaoFriendAvoidanceEnabled: avoidanceEnabledBy.includes(friendUid),
  });
  return pairId;
}

function seedExclusionPair(
  fake: FakeFirestore,
  friendUid: string,
  overrides: FakeDocData = {},
): void {
  const doc = {
    pairId: buildKakaoFriendPairId(CALLER, friendUid),
    userIds: [CALLER, friendUid].sort(),
    source: "kakao_friend_pair",
    reason: "kakao_friend_avoidance",
    active: true,
    enabledBy: { [CALLER]: true, [friendUid]: false },
    ...overrides,
  };
  fake.seed(`recommendationExclusions/${CALLER}/targets/${friendUid}`, doc);
  fake.seed(`recommendationExclusions/${friendUid}/targets/${CALLER}`, doc);
}

function exclusionDocsOf(fake: FakeFirestore): string[] {
  return [...fake.store.keys()].filter((path) =>
    path.startsWith("recommendationExclusions/"),
  );
}

function callerPreference(fake: FakeFirestore): unknown {
  return fake.store.get(`users/${CALLER}`)?.kakaoFriendAvoidanceEnabled;
}

// ============================================================================
// Blocker #3 — fault-injection: ON with 700 pairs, failure mid-materialize
// ============================================================================

test("ON failure mid-materialize keeps preference false; retry converges", async () => {
  const fake = new FakeFirestore();
  fake.seed(`users/${CALLER}`, { kakaoFriendAvoidanceEnabled: false });
  const PAIRS = 700;
  for (let i = 0; i < PAIRS; i++) seedPair(fake, friendUidOf(i), []);

  // Injected failure around write 300 (~pair 100, chunk 5 of 20-pair chunks:
  // 1 lock write + 3 writes per pair transaction).
  fake.failAfterWrites = 300;
  await assert.rejects(
    executeSetKakaoFriendAvoidanceEnabled(toggleDeps(fake), {
      uid: CALLER,
      enabled: true,
    }),
    /injected_write_failure/,
  );

  // API failed -> the preference must NOT be true (over-exclusion only).
  assert.notEqual(callerPreference(fake), true);
  const partial = exclusionDocsOf(fake);
  assert.equal(partial.length > 0, true, "partial exclusions must remain");
  assert.equal(partial.length < PAIRS * 2, true);
  // The mutation record never reads "completed" after a failure.
  const mutation = fake.store.get(`users/${CALLER}`)?.[
    AVOIDANCE_MUTATION_FIELD
  ] as FakeDocData;
  assert.notEqual(mutation?.status, "completed");

  // Retry from scratch is the same code path and converges fully.
  fake.failAfterWrites = null;
  const retry = await executeSetKakaoFriendAvoidanceEnabled(toggleDeps(fake), {
    uid: CALLER,
    enabled: true,
  });
  assert.deepEqual(retry, {
    enabled: true,
    pairCount: PAIRS,
    activePairCount: PAIRS,
  });
  assert.equal(callerPreference(fake), true);
  // All pairs consistent + bilateral complete + zero duplicates.
  const pairIds = new Set<string>();
  for (let i = 0; i < PAIRS; i++) {
    const friendUid = friendUidOf(i);
    const pairId = buildKakaoFriendPairId(CALLER, friendUid);
    pairIds.add(pairId);
    const pairDoc = fake.store.get(`kakaoFriendPairs/${pairId}`);
    assert.equal(pairDoc?.avoidanceActive, true, friendUid);
    assert.deepEqual(pairDoc?.avoidanceEnabledBy, [CALLER]);
    for (const [owner, target] of [
      [CALLER, friendUid],
      [friendUid, CALLER],
    ]) {
      const doc = fake.store.get(
        `recommendationExclusions/${owner}/targets/${target}`,
      );
      assert.equal(doc?.source, "kakao_friend_pair", `${owner}->${target}`);
      assert.equal(doc?.pairId, pairId);
      assert.equal(doc?.active, true);
    }
  }
  assert.equal(pairIds.size, PAIRS, "zero duplicate pair ids");
  assert.equal(exclusionDocsOf(fake).length, PAIRS * 2);
  const finalMutation = fake.store.get(`users/${CALLER}`)?.[
    AVOIDANCE_MUTATION_FIELD
  ] as FakeDocData;
  assert.equal(finalMutation?.status, "completed");
});

// ============================================================================
// Blocker #3 — fault-injection: OFF failure leaves over-exclusion only
// ============================================================================

test("OFF failure keeps preference false + stale exclusions; retry converges", async () => {
  const fake = new FakeFirestore();
  fake.seed(`users/${CALLER}`, { kakaoFriendAvoidanceEnabled: true });
  const PAIRS = 700;
  const COUNTERPART_ON_FROM = 600;
  for (let i = 0; i < PAIRS; i++) {
    const friendUid = friendUidOf(i);
    const enabledBy =
      i >= COUNTERPART_ON_FROM ? [CALLER, friendUid] : [CALLER];
    seedPair(fake, friendUid, enabledBy);
    if (i < 300) {
      // Legacy-sync docs: joined pairId + kakao_talk_friend source.
      seedExclusionPair(fake, friendUid, {
        pairId: buildRecommendationExclusionPairId(CALLER, friendUid),
        source: "kakao_talk_friend",
      });
    } else {
      seedExclusionPair(fake, friendUid, {
        enabledBy: {
          [CALLER]: true,
          [friendUid]: i >= COUNTERPART_ON_FROM,
        },
      });
    }
  }
  // Protected residue: a foreign-source doc and a pairId-mismatched doc.
  const foreignFriend = friendUidOf(0);
  fake.seed(`recommendationExclusions/${CALLER}/targets/${foreignFriend}`, {
    source: "manual",
    pairId: buildKakaoFriendPairId(CALLER, foreignFriend),
  });
  const mismatchedFriend = friendUidOf(1);
  fake.seed(`recommendationExclusions/${CALLER}/targets/${mismatchedFriend}`, {
    source: "kakao_friend_pair",
    pairId: "uid_x_uid_y",
  });

  fake.failAfterWrites = 300;
  await assert.rejects(
    executeSetKakaoFriendAvoidanceEnabled(toggleDeps(fake), {
      uid: CALLER,
      enabled: false,
    }),
    /injected_write_failure/,
  );

  // The preference went false IN the lock transaction, before any removal.
  assert.equal(callerPreference(fake), false);
  // Stale exclusions may remain (over-exclusion) ...
  assert.equal(exclusionDocsOf(fake).length > 0, true);
  // ... and counterpart-ON pairs never lost their exclusions (no new
  // under-exclusion): OFF only materializes those, never deletes them.
  for (let i = COUNTERPART_ON_FROM; i < PAIRS; i++) {
    const friendUid = friendUidOf(i);
    assert.equal(
      fake.store.has(`recommendationExclusions/${CALLER}/targets/${friendUid}`),
      true,
      friendUid,
    );
    assert.equal(
      fake.store.has(`recommendationExclusions/${friendUid}/targets/${CALLER}`),
      true,
      friendUid,
    );
  }

  // Retry converges: both-OFF pairs end with zero Kakao exclusions,
  // counterpart-ON pairs retain theirs.
  fake.failAfterWrites = null;
  const retry = await executeSetKakaoFriendAvoidanceEnabled(toggleDeps(fake), {
    uid: CALLER,
    enabled: false,
  });
  assert.deepEqual(retry, {
    enabled: false,
    pairCount: PAIRS,
    activePairCount: PAIRS - COUNTERPART_ON_FROM,
  });
  assert.equal(callerPreference(fake), false);
  for (let i = 0; i < PAIRS; i++) {
    const friendUid = friendUidOf(i);
    const forward = fake.store.get(
      `recommendationExclusions/${CALLER}/targets/${friendUid}`,
    );
    const reverse = fake.store.get(
      `recommendationExclusions/${friendUid}/targets/${CALLER}`,
    );
    if (i >= COUNTERPART_ON_FROM) {
      // Counterpart still ON -> exclusions retained, caller contribution off.
      assert.deepEqual(forward?.enabledBy, {
        [CALLER]: false,
        [friendUid]: true,
      });
      assert.equal(reverse?.active, true);
    } else if (friendUid === foreignFriend) {
      // Foreign-source doc is never deleted (protection-for-protection).
      assert.equal(forward?.source, "manual");
      assert.equal(reverse, undefined);
    } else if (friendUid === mismatchedFriend) {
      // Kakao source with a mismatched pairId stays (over-exclusion residue).
      assert.equal(forward?.pairId, "uid_x_uid_y");
      assert.equal(reverse, undefined);
    } else {
      assert.equal(forward, undefined, friendUid);
      assert.equal(reverse, undefined, friendUid);
    }
    const pairDoc = fake.store.get(
      `kakaoFriendPairs/${buildKakaoFriendPairId(CALLER, friendUid)}`,
    );
    assert.notEqual(pairDoc, undefined, "pair docs are never deleted");
  }
});

// ============================================================================
// Blocker #3 — concurrent generations (stale operations must lose)
// ============================================================================

test("older ON finishing after a newer OFF cannot flip the preference true", async () => {
  const fake = new FakeFirestore();
  fake.seed(`users/${CALLER}`, { kakaoFriendAvoidanceEnabled: false });
  for (let i = 0; i < 5; i++) seedPair(fake, friendUidOf(i), []);

  const oldOn = executeSetKakaoFriendAvoidanceEnabled(
    toggleDeps(fake, {
      // The older ON has materialized its pairs; before its final commit a
      // newer OFF supersedes it completely.
      onBeforeFinalize: async () => {
        await executeSetKakaoFriendAvoidanceEnabled(toggleDeps(fake), {
          uid: CALLER,
          enabled: false,
        });
      },
    }),
    { uid: CALLER, enabled: true },
  );
  await assert.rejects(oldOn, (error: unknown) => {
    assert.equal(error instanceof HttpsError, true);
    assert.equal((error as HttpsError).code, "aborted");
    return true;
  });

  assert.equal(callerPreference(fake), false);
  assert.deepEqual(exclusionDocsOf(fake), []);
  const mutation = fake.store.get(`users/${CALLER}`)?.[
    AVOIDANCE_MUTATION_FIELD
  ] as FakeDocData;
  assert.equal(mutation?.generation, 2);
  assert.equal(mutation?.desired, false);
  assert.equal(mutation?.status, "completed");
});

test("stale ON reconcile after a newer OFF aborts without re-materializing", async () => {
  const fake = new FakeFirestore();
  fake.seed(`users/${CALLER}`, { kakaoFriendAvoidanceEnabled: false });
  for (let i = 0; i < 5; i++) seedPair(fake, friendUidOf(i), []);

  const oldOn = executeSetKakaoFriendAvoidanceEnabled(
    toggleDeps(fake, {
      // Superseded BEFORE its reconcile even starts: every pair transaction
      // must see the stale generation and write nothing.
      onBeforeReconcile: async () => {
        await executeSetKakaoFriendAvoidanceEnabled(toggleDeps(fake), {
          uid: CALLER,
          enabled: false,
        });
      },
    }),
    { uid: CALLER, enabled: true },
  );
  await assert.rejects(oldOn, (error: unknown) => {
    return error instanceof HttpsError && error.code === "aborted";
  });

  assert.equal(callerPreference(fake), false);
  assert.deepEqual(
    exclusionDocsOf(fake),
    [],
    "stale ON must not materialize anything",
  );

  // Direct assertion of the silent stale abort at the reconcile level.
  const stale = await reconcileKakaoFriendAvoidanceForUser({
    db: fake as unknown as Firestore,
    uid: CALLER,
    enabled: true,
    generation: 1, // current generation is 2
  });
  assert.equal(stale.staleAborted, true);
  assert.equal(stale.pairCount, 0);
  assert.deepEqual(exclusionDocsOf(fake), []);
});

test("older OFF finishing after a newer ON cannot flip the preference false", async () => {
  const fake = new FakeFirestore();
  fake.seed(`users/${CALLER}`, { kakaoFriendAvoidanceEnabled: true });
  for (let i = 0; i < 5; i++) {
    const friendUid = friendUidOf(i);
    seedPair(fake, friendUid, [CALLER]);
    seedExclusionPair(fake, friendUid);
  }

  const oldOff = executeSetKakaoFriendAvoidanceEnabled(
    toggleDeps(fake, {
      onBeforeFinalize: async () => {
        await executeSetKakaoFriendAvoidanceEnabled(toggleDeps(fake), {
          uid: CALLER,
          enabled: true,
        });
      },
    }),
    { uid: CALLER, enabled: false },
  );
  await assert.rejects(oldOff, (error: unknown) => {
    return error instanceof HttpsError && error.code === "aborted";
  });

  // The newer ON owns the final state: preference true, exclusions present.
  assert.equal(callerPreference(fake), true);
  assert.equal(exclusionDocsOf(fake).length, 10);
  const mutation = fake.store.get(`users/${CALLER}`)?.[
    AVOIDANCE_MUTATION_FIELD
  ] as FakeDocData;
  assert.equal(mutation?.generation, 2);
  assert.equal(mutation?.desired, true);
  assert.equal(mutation?.status, "completed");
});

test("same-desired retry converges idempotently through the same path", async () => {
  const fake = new FakeFirestore();
  fake.seed(`users/${CALLER}`, { kakaoFriendAvoidanceEnabled: false });
  for (let i = 0; i < 3; i++) seedPair(fake, friendUidOf(i), []);

  const first = await executeSetKakaoFriendAvoidanceEnabled(toggleDeps(fake), {
    uid: CALLER,
    enabled: true,
  });
  const second = await executeSetKakaoFriendAvoidanceEnabled(toggleDeps(fake), {
    uid: CALLER,
    enabled: true,
  });
  assert.deepEqual(first, second);
  assert.equal(callerPreference(fake), true);
  assert.equal(exclusionDocsOf(fake).length, 6);
});

// ============================================================================
// GATE E — legacy syncKakaoTalkFriendBlocks under-exclusion fix
// ============================================================================

test("legacy failure revert flips the preference back only for enabling requests", () => {
  assert.deepEqual(
    buildLegacyKakaoSyncFailureRevert({
      requestedEnabled: true,
      preRequestAvoidanceEnabled: false,
    }),
    { kakaoFriendAvoidanceEnabled: false },
  );
  // Already-ON before the request: revert is a no-op value.
  assert.deepEqual(
    buildLegacyKakaoSyncFailureRevert({
      requestedEnabled: true,
      preRequestAvoidanceEnabled: true,
    }),
    { kakaoFriendAvoidanceEnabled: true },
  );
  // OFF-mode failure stays preference=false + stale exclusions: no revert.
  assert.deepEqual(
    buildLegacyKakaoSyncFailureRevert({
      requestedEnabled: false,
      preRequestAvoidanceEnabled: true,
    }),
    {},
  );
});

test("legacy callable captures the pre-request preference before writing", () => {
  assert.match(
    indexSrc,
    /const preRequestAvoidanceEnabled =\s*\n?\s*isKakaoFriendAvoidanceEnabled\(currentCallerData\);/,
  );
});

test("legacy ON failure reverts the preference inside the generation guard", () => {
  // The revert sits INSIDE the reconcileId-guarded failure transaction, after
  // the stale-request early return and before the terminal "failed" status —
  // a stale failing request can never clobber a newer sync's preference.
  assert.match(
    indexSrc,
    /if \(latestData\.kakaoFriendReconcileId !== reconcileId\) return;[\s\S]{0,900}buildLegacyKakaoSyncFailureRevert\(\{\s*\n\s*requestedEnabled: callerEnabled,\s*\n\s*preRequestAvoidanceEnabled,\s*\n\s*\}\),[\s\S]{0,300}kakaoFriendReconcileStatus: "failed"/,
  );
});

test("legacy ON-mode never sweeps pairs absent from today's API", () => {
  // The existing-target sweep only runs for OFF requests; an ON sync must
  // never clear pairs just because the Kakao API omitted them today.
  assert.match(
    indexSrc,
    /const existingTargetSnapshot = callerEnabled\s*\n?\s*\?\s*null\s*\n?\s*:/,
  );
});
