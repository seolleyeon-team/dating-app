import { createHash, randomUUID } from "crypto";
import { FieldValue, type Firestore } from "firebase-admin/firestore";
import { HttpsError, onCall } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import { withAppCheck } from "./appCheckPolicy";
import {
  buildRecommendationExclusionPairId,
  isKakaoFriendAvoidanceEnabled,
} from "./kakaoFriendRecommendationPrivacy";
import {
  decideKakaoCallerIdentity,
  kakaoIdentityHash,
  resolveFriendExclusionAppUserIds,
  type FriendResolutionCandidate,
} from "./kakaoIdentityLink";

/**
 * One-time Kakao friend snapshot (kakao-friend-pairs contract v2).
 *
 * Replaces the repeated `syncKakaoTalkFriendBlocks` reconciliation with a
 * once-per-account snapshot into `kakaoFriendPairs/{pairId}` plus the
 * preference toggle `setKakaoFriendAvoidanceEnabled`. Serving reads only the
 * bilateral `recommendationExclusions` docs; the Kakao API is never called at
 * serving/batch time and never again after a completed snapshot (contract §3).
 */

// =============================================================================
// Pure decision logic (unit-testable without Firestore)
// =============================================================================

export const KAKAO_FRIEND_PAIR_SOURCE = "kakao_friend_snapshot";
export const KAKAO_FRIEND_PAIR_EXCLUSION_SOURCE = "kakao_friend_pair";
export const LEGACY_KAKAO_EXCLUSION_SOURCE = "kakao_talk_friend";

/** Exclusion sources the new code may ever delete (contract §6, spec §57). */
const KAKAO_OWNED_EXCLUSION_SOURCES: ReadonlySet<string> = new Set([
  KAKAO_FRIEND_PAIR_EXCLUSION_SOURCE,
  LEGACY_KAKAO_EXCLUSION_SOURCE,
]);

/** Stale-lease policy (contract §3): in_progress older than 10 minutes. */
export const SNAPSHOT_LEASE_STALE_MS = 10 * 60 * 1000;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function toMillis(value: unknown): number | null {
  if (value instanceof Date) return value.getTime();
  if (
    isRecord(value) &&
    typeof (value as { toMillis?: unknown }).toMillis === "function"
  ) {
    const millis = (value as { toMillis: () => unknown }).toMillis();
    return typeof millis === "number" && Number.isFinite(millis)
      ? millis
      : null;
  }
  return null;
}

function uidHash(uid: string): string {
  return createHash("sha256").update(uid, "utf8").digest("hex").slice(0, 16);
}

/**
 * Deletion safety predicate (contract §6): only exclusion docs produced by the
 * Kakao friend pipeline may ever be deleted by this module. Manual/report
 * blocks and any future producer are untouchable.
 */
export function isKakaoOwnedExclusion(
  data: Record<string, unknown> | null | undefined,
): boolean {
  if (!data) return false;
  const source = data.source;
  return typeof source === "string" && KAKAO_OWNED_EXCLUSION_SOURCES.has(source);
}

// =============================================================================
// Collision-safe canonical pairId (production blocker #2)
// =============================================================================

/**
 * Canonical pairId hash-preimage version. The version is part of the preimage,
 * so bumping it changes every id — never bump without a migration plan.
 */
export const KAKAO_FRIEND_PAIR_ID_VERSION = 1;

/**
 * Pair-member uid contract: Firebase Auth uids (28 chars) and legacy numeric
 * Kakao ids both match the safe-path-segment alphabet already enforced across
 * identity resolution and account deletion (`^[A-Za-z0-9_-]+$` — Unicode is
 * impossible by contract, so anything else is rejected). 200 is a generous
 * bound well above every id the identity contract can produce (Firestore doc
 * ids allow up to 1500 bytes).
 */
export const KAKAO_FRIEND_PAIR_UID_MAX_LENGTH = 200;

const KAKAO_PAIR_MEMBER_UID_RE = /^[A-Za-z0-9_-]+$/;
const CANONICAL_KAKAO_PAIR_ID_RE = /^[0-9a-f]{64}$/;

export function isValidKakaoFriendPairMemberUid(
  value: unknown,
): value is string {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    value.length <= KAKAO_FRIEND_PAIR_UID_MAX_LENGTH &&
    KAKAO_PAIR_MEMBER_UID_RE.test(value)
  );
}

/**
 * Collision-safe canonical pairId (blocker #2): 64-char lowercase sha256 hex
 * over a JSON-array preimage. The JSON array is an injective encoding of the
 * (sorted) uid pair, so no concatenation ambiguity can make two distinct
 * pairs collide — the delimiter-only legacy format
 * (`buildRecommendationExclusionPairId`, `[a,b].sort().join("_")`) collides on
 * e.g. ("a_b","c") vs ("a","b_c") and stays confined to legacy
 * `kakao_talk_friend` writers.
 *
 * MIGRATION NOTE: the kakaoFriendPairs feature has never been deployed to any
 * environment, so no old-schema (joined-format) kakaoFriendPairs docs exist
 * anywhere; the canonical hash is the only doc-id format ever written for
 * `kakaoFriendPairs/{pairId}` and for new `kakao_friend_pair` exclusion
 * metadata. Legacy `kakao_talk_friend` recommendationExclusions docs DO carry
 * the legacy joined pairId — code that must recognize those accepts either
 * format (see isKakaoPairIdForMembers). The predeploy dry-run
 * (scripts/kakao_friend_pairs_migration_dryrun.mjs) counts oldFormatPairDocs
 * to verify emptiness.
 */
export function buildKakaoFriendPairId(uidA: string, uidB: string): string {
  for (const uid of [uidA, uidB]) {
    if (!isValidKakaoFriendPairMemberUid(uid)) {
      throw new Error("kakao_friend_pair_member_uid_invalid");
    }
  }
  if (uidA === uidB) {
    throw new Error("kakao_friend_pair_members_must_differ");
  }
  const [uidLow, uidHigh] = [uidA, uidB].sort();
  return createHash("sha256")
    .update(
      JSON.stringify([
        "kakao_friend_pair",
        KAKAO_FRIEND_PAIR_ID_VERSION,
        uidLow,
        uidHigh,
      ]),
      "utf8",
    )
    .digest("hex");
}

/** 64-hex canonical id predicate (mirrored by the migration dry-run). */
export function isCanonicalKakaoFriendPairId(value: unknown): boolean {
  return (
    typeof value === "string" && CANONICAL_KAKAO_PAIR_ID_RE.test(value)
  );
}

/**
 * Dual-format pairId match (blocker #2): where new code has to recognize docs
 * written by the LEGACY sync (`kakao_talk_friend`, joined-format pairId) it
 * accepts either the canonical hash or the legacy joined format. This helper
 * is never used to WRITE the legacy format.
 */
export function isKakaoPairIdForMembers(
  pairId: unknown,
  uidA: string,
  uidB: string,
): boolean {
  if (typeof pairId !== "string" || uidA === uidB) return false;
  if (
    !isValidKakaoFriendPairMemberUid(uidA) ||
    !isValidKakaoFriendPairMemberUid(uidB)
  ) {
    return false;
  }
  return (
    pairId === buildKakaoFriendPairId(uidA, uidB) ||
    pairId === buildRecommendationExclusionPairId(uidA, uidB)
  );
}

/**
 * Exclusion-deletion predicate for the toggle path (blocker #3 OFF step 3):
 * Kakao-owned source AND a pairId naming exactly this pair (canonical or
 * legacy joined format). Anything else stays in place — the failure direction
 * is always over-exclusion, never a delete of a foreign or mismatched doc.
 */
export function isDeletableKakaoPairExclusion(
  data: Record<string, unknown> | null | undefined,
  uidA: string,
  uidB: string,
): boolean {
  if (!data || !isKakaoOwnedExclusion(data)) return false;
  return isKakaoPairIdForMembers(data.pairId, uidA, uidB);
}

export type SnapshotLeaseDecision =
  | { action: "alreadyCompleted"; pairCount: number }
  | { action: "inProgress" }
  | { action: "acquire" };

/**
 * Lease decision over `users/{uid}.kakaoFriendSnapshot` (contract §3).
 * `completed` is immutable; a fresh `in_progress` lease rejects concurrent
 * runs; a stale lease (>10 minutes, or with an unreadable startedAt that could
 * never expire) may be taken over.
 */
export function decideSnapshotLease(params: {
  state: unknown;
  now: Date;
}): SnapshotLeaseDecision {
  const state = isRecord(params.state) ? params.state : {};
  const status = state.status;
  if (status === "completed") {
    const rawPairCount = state.pairCount;
    const pairCount =
      typeof rawPairCount === "number" && Number.isFinite(rawPairCount)
        ? Math.max(0, Math.trunc(rawPairCount))
        : 0;
    return { action: "alreadyCompleted", pairCount };
  }
  if (status === "in_progress") {
    const startedAtMillis = toMillis(state.startedAt);
    if (
      startedAtMillis !== null &&
      params.now.getTime() - startedAtMillis < SNAPSHOT_LEASE_STALE_MS
    ) {
      return { action: "inProgress" };
    }
    // Stale (or unreadable startedAt, which could otherwise never expire).
    return { action: "acquire" };
  }
  // not_started / failed / missing / malformed -> retryable.
  return { action: "acquire" };
}

/** Lease acquisition payload — replaces the whole snapshot map. */
export function buildSnapshotLeaseUpdate(params: {
  snapshotRunId: string;
  now: Date;
}): Record<string, unknown> {
  return {
    status: "in_progress",
    snapshotRunId: params.snapshotRunId,
    startedAt: params.now,
    schemaVersion: 1,
  };
}

/**
 * Completion/failure transactions may only finalize the run that still owns
 * the lease (contract §4 step 6/7): a mismatching snapshotRunId means another
 * run took over after this one went stale.
 */
export function snapshotRunOwnsLease(
  state: unknown,
  snapshotRunId: string,
): boolean {
  if (!isRecord(state)) return false;
  return (
    snapshotRunId.length > 0 &&
    state.status === "in_progress" &&
    state.snapshotRunId === snapshotRunId
  );
}

/** Terminal success map — snapshotRunId is dropped (lease released). */
export function buildSnapshotCompletionUpdate(params: {
  previousState: unknown;
  pairCount: number;
  now: Date;
}): Record<string, unknown> {
  const previous = isRecord(params.previousState) ? params.previousState : {};
  return {
    status: "completed",
    ...(previous.startedAt !== undefined
      ? { startedAt: previous.startedAt }
      : {}),
    completedAt: params.now,
    pairCount: Math.max(0, Math.trunc(params.pairCount)),
    schemaVersion: 1,
  };
}

/**
 * Terminal failure map — never `completed`, snapshotRunId dropped, errorCode
 * bounded and PII-free (contract §4 step 7). Partial pair docs stay in place
 * for the idempotent retry.
 */
export function buildSnapshotFailureUpdate(params: {
  previousState: unknown;
  errorCode: string;
  now: Date;
}): Record<string, unknown> {
  const previous = isRecord(params.previousState) ? params.previousState : {};
  return {
    status: "failed",
    ...(previous.startedAt !== undefined
      ? { startedAt: previous.startedAt }
      : {}),
    failedAt: params.now,
    errorCode: params.errorCode.slice(0, 80),
    schemaVersion: 1,
  };
}

/**
 * Failure-state error codes must stay machine-readable and PII-free: HttpsError
 * detail/code wins over its user-facing message; raw messages are reduced to a
 * bounded safe alphabet (no emails, no tokens, no Kakao ids with separators).
 */
export function sanitizeSnapshotErrorCode(error: unknown): string {
  let raw: string;
  if (error instanceof HttpsError) {
    const detail = isRecord(error.details) ? error.details.detail : null;
    raw =
      typeof detail === "string" && detail.trim().length > 0
        ? detail
        : `https_${error.code}`;
  } else if (error instanceof Error) {
    raw = error.message;
  } else {
    raw = "unknown";
  }
  const sanitized = raw.replace(/[^A-Za-z0-9_.:-]/g, "_").slice(0, 80);
  return sanitized.length > 0 ? sanitized : "unknown";
}

export type SnapshotIdentityDecision =
  | { ok: true }
  | { ok: false; reason: "kakao_identity_not_linked" | "identity_conflict" };

/**
 * Snapshot identity precondition (contract §4): the server-verified Kakao id
 * must resolve to the CALLER's appUserId — legacy uid==kakaoId, legacy session
 * claim, or the kakaoIdentities mapping. A mapping bound to another account is
 * a conflict, never a silent re-bind.
 */
export function decideSnapshotIdentityPrecondition(params: {
  authUid: string;
  claimedKakaoUserId: string | null;
  verifiedKakaoUserId: string;
  mappingAppUserId: string | null;
}): SnapshotIdentityDecision {
  const direct = decideKakaoCallerIdentity(params);
  if (direct.ok && direct.appUserId === params.authUid) {
    return { ok: true };
  }
  const mapped = asNonEmptyString(params.mappingAppUserId);
  if (mapped && mapped !== params.authUid) {
    return { ok: false, reason: "identity_conflict" };
  }
  return { ok: false, reason: "kakao_identity_not_linked" };
}

// =============================================================================
// Avoidance toggle mutation state (production blocker #3)
// =============================================================================

export const AVOIDANCE_MUTATION_FIELD = "kakaoFriendAvoidanceMutation";

/**
 * Freshness window for conflicting mutations (blocker #3). With the
 * CAS-supersede policy below the age never blocks a new request — the window
 * exists as documentation of the contract's "fresh conflicting mutation"
 * notion and for operators reading stuck mutation docs.
 */
export const AVOIDANCE_MUTATION_STALE_MS = 10 * 60 * 1000;

export type AvoidanceMutationState = {
  desired: boolean;
  status: "enabling" | "disabling" | "completed" | "failed";
  generation: number;
  startedAt: Date;
};

export function readAvoidanceMutationGeneration(state: unknown): number {
  if (!isRecord(state)) return 0;
  const generation = state.generation;
  return typeof generation === "number" &&
    Number.isFinite(generation) &&
    generation > 0
    ? Math.trunc(generation)
    : 0;
}

/**
 * CAS-supersede lock acquisition (blocker #3): every new request bumps the
 * generation and proceeds — including over a fresh conflicting mutation with a
 * different desired value (higher generation wins; no retryable-rejection
 * path). The superseded operation is not cancelled in place: it fails its next
 * generation check instead (every pair-write transaction and the final commit
 * re-verify), so a stale generation can never overwrite a newer intent.
 */
export function buildAvoidanceMutationStart(params: {
  currentMutation: unknown;
  desired: boolean;
  now: Date;
}): { generation: number; mutation: AvoidanceMutationState } {
  const generation =
    readAvoidanceMutationGeneration(params.currentMutation) + 1;
  return {
    generation,
    mutation: {
      desired: params.desired,
      status: params.desired ? "enabling" : "disabling",
      generation,
      startedAt: params.now,
    },
  };
}

/** True iff the user's CURRENT mutation generation is exactly `generation`. */
export function isCurrentAvoidanceGeneration(
  userData: Record<string, unknown> | null | undefined,
  generation: number,
): boolean {
  if (!userData || generation <= 0) return false;
  return (
    readAvoidanceMutationGeneration(userData[AVOIDANCE_MUTATION_FIELD]) ===
    generation
  );
}

export function buildAvoidanceMutationCompletion(params: {
  mutation: AvoidanceMutationState;
  now: Date;
}): Record<string, unknown> {
  return {
    desired: params.mutation.desired,
    status: "completed",
    generation: params.mutation.generation,
    startedAt: params.mutation.startedAt,
    completedAt: params.now,
  };
}

export function buildAvoidanceMutationFailure(params: {
  mutation: AvoidanceMutationState;
  now: Date;
}): Record<string, unknown> {
  return {
    desired: params.mutation.desired,
    status: "failed",
    generation: params.mutation.generation,
    startedAt: params.mutation.startedAt,
    failedAt: params.now,
  };
}

/**
 * Effective avoidance preference for PAIR-LEVEL writes (snapshot §4 step 4 /
 * concurrent-toggle rule): a user counts as avoidance-enabled when the
 * committed preference is true OR an ON mutation is still in flight (status
 * "enabling", desired true). The bias is deliberate — while an ON toggle is
 * materializing (the preference stays false until its final commit), a
 * concurrent snapshot reading only the committed preference could delete the
 * exclusions the toggle just wrote and leave preference=true with missing
 * exclusions. Counting the in-flight ON intent keeps every interleaving in
 * the over-exclusion direction. A mutation that ended in "failed"/"completed"
 * no longer contributes — the committed preference is then the truth.
 */
export function isEffectiveAvoidanceEnabled(
  userData: Record<string, unknown> | null | undefined,
): boolean {
  if (!userData) return false;
  if (isKakaoFriendAvoidanceEnabled(userData)) return true;
  const mutation = userData[AVOIDANCE_MUTATION_FIELD];
  return (
    isRecord(mutation) &&
    mutation.desired === true &&
    mutation.status === "enabling"
  );
}

/**
 * GATE E (mixed old/new client under-exclusion fix): the legacy
 * `syncKakaoTalkFriendBlocks` callable persists kakaoFriendAvoidanceEnabled
 * BEFORE pair reconciliation. The old failure path relied on
 * recommendationPrivacyReady=false hiding the user, but the new pipeline
 * ignores that gate — so a failed legacy ENABLING sync would leave
 * preference=true with missing exclusions (under-exclusion). On failure of an
 * enabling request the preference is reverted to its pre-request value, inside
 * the existing reconcileId-guarded failure transaction (a stale failure can
 * never clobber a newer sync). OFF-mode failure keeps preference=false plus
 * stale exclusions (over-exclusion) and is deliberately unchanged, as is the
 * ON-mode "never sweep pairs absent from today's API" behavior.
 */
export function buildLegacyKakaoSyncFailureRevert(params: {
  requestedEnabled: boolean;
  preRequestAvoidanceEnabled: boolean;
}): Record<string, unknown> {
  if (!params.requestedEnabled) return {};
  return {
    kakaoFriendAvoidanceEnabled: params.preRequestAvoidanceEnabled,
  };
}

export type KakaoFriendPairUpsert = {
  pairId: string;
  memberUids: [string, string];
  discoveredByUids: string[];
  avoidanceEnabledBy: string[];
  avoidanceActive: boolean;
  isNewPair: boolean;
};

function memberUidsOf(uidA: string, uidB: string): [string, string] {
  const sorted = [uidA, uidB].sort();
  return [sorted[0], sorted[1]];
}

function readStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((entry): entry is string => typeof entry === "string");
}

/**
 * Directionless pair upsert (contract §2, §4 step 4, spec §13/§37): identical
 * from either member's snapshot, `avoidanceEnabledBy` derived from BOTH
 * members' current preference so a counterpart who enabled avoidance before
 * this caller's snapshot immediately yields an active pair.
 */
export function buildKakaoFriendPairUpsert(params: {
  callerUid: string;
  friendUid: string;
  callerAvoidanceEnabled: boolean;
  friendAvoidanceEnabled: boolean;
  existingPairData: Record<string, unknown> | null;
}): KakaoFriendPairUpsert {
  const memberUids = memberUidsOf(params.callerUid, params.friendUid);
  // Canonical collision-safe id (blocker #2) — doc id and pairId field agree.
  const pairId = buildKakaoFriendPairId(params.callerUid, params.friendUid);
  const discovered = new Set<string>(
    readStringArray(params.existingPairData?.discoveredByUids).filter((uid) =>
      memberUids.includes(uid),
    ),
  );
  discovered.add(params.callerUid);
  const enabledBy = new Set<string>();
  if (params.callerAvoidanceEnabled) enabledBy.add(params.callerUid);
  if (params.friendAvoidanceEnabled) enabledBy.add(params.friendUid);
  const avoidanceEnabledBy = [...enabledBy].sort();
  return {
    pairId,
    memberUids,
    discoveredByUids: [...discovered].sort(),
    avoidanceEnabledBy,
    avoidanceActive: avoidanceEnabledBy.length > 0,
    isNewPair: params.existingPairData === null,
  };
}

export type AvoidanceToggleDecision = {
  memberUids: [string, string];
  pairId: string;
  avoidanceEnabledBy: string[];
  avoidanceActive: boolean;
  action: "materialize" | "remove";
};

/**
 * Preference toggle over one pair (contract §5, spec §54 OR-semantics): the
 * OTHER member's contribution comes from the pair doc itself; exclusions exist
 * while ANY member keeps avoidance on. Pair docs are never deleted here.
 */
export function decideAvoidanceToggle(params: {
  pairData: Record<string, unknown>;
  uid: string;
  enabled: boolean;
}): AvoidanceToggleDecision | null {
  const members = readStringArray(params.pairData.memberUids);
  if (members.length !== 2 || !members.includes(params.uid)) {
    return null; // malformed pair doc — skip, never guess
  }
  if (
    members[0] === members[1] ||
    !isValidKakaoFriendPairMemberUid(members[0]) ||
    !isValidKakaoFriendPairMemberUid(members[1])
  ) {
    return null; // impossible-by-contract members — skip, never guess
  }
  const memberUids = memberUidsOf(members[0], members[1]);
  const enabledBy = new Set<string>(
    readStringArray(params.pairData.avoidanceEnabledBy).filter((uid) =>
      memberUids.includes(uid),
    ),
  );
  if (params.enabled) {
    enabledBy.add(params.uid);
  } else {
    enabledBy.delete(params.uid);
  }
  const avoidanceEnabledBy = [...enabledBy].sort();
  const avoidanceActive = avoidanceEnabledBy.length > 0;
  return {
    memberUids,
    pairId: buildKakaoFriendPairId(memberUids[0], memberUids[1]),
    avoidanceEnabledBy,
    avoidanceActive,
    action: avoidanceActive ? "materialize" : "remove",
  };
}

/**
 * Bilateral exclusion doc shape (contract §6). Compatible with every existing
 * active-predicate: `active: true` plus an `enabledBy` map with at least one
 * true entry while the doc exists.
 */
export function buildPairExclusionDoc(params: {
  pairId: string;
  memberUids: readonly string[];
  avoidanceEnabledBy: readonly string[];
}): Record<string, unknown> {
  const userIds = [...params.memberUids].sort();
  const enabledBy: Record<string, boolean> = {};
  for (const uid of userIds) {
    enabledBy[uid] = params.avoidanceEnabledBy.includes(uid);
  }
  return {
    pairId: params.pairId,
    userIds,
    source: KAKAO_FRIEND_PAIR_EXCLUSION_SOURCE,
    reason: "kakao_friend_avoidance",
    active: true,
    enabledBy,
  };
}

/**
 * Legacy sweep (contract §4 step 5): a `kakao_talk_friend` doc whose target
 * was NOT re-materialized as an active pair this run is deleted, together with
 * its reverse doc iff that reverse doc is Kakao-owned AND carries a pairId
 * naming this pair — legacy docs carry the joined format, new docs carry the
 * canonical hash, so the reverse match accepts EITHER (blocker #2). General
 * blocks live in `blocks` and are untouched by construction.
 */
export function decideLegacySweepDeletion(params: {
  callerUid: string;
  targetUid: string;
  rematerializedActiveTargetUids: ReadonlySet<string>;
  reverseDocData: Record<string, unknown> | null;
}): { deleteForward: boolean; deleteReverse: boolean } {
  if (params.rematerializedActiveTargetUids.has(params.targetUid)) {
    return { deleteForward: false, deleteReverse: false };
  }
  const deleteReverse = isDeletableKakaoPairExclusion(
    params.reverseDocData,
    params.callerUid,
    params.targetUid,
  );
  return { deleteForward: true, deleteReverse };
}

// =============================================================================
// createKakaoFriendPairsOnce (contract §4)
// =============================================================================

const SAFE_PATH_SEGMENT_RE = /^[A-Za-z0-9_-]+$/;
/** Member-resolution lookups: 2 refs per candidate -> 200 refs per getAll. */
const RESOLUTION_LOOKUP_CHUNK = 100;
/** Pair processing: 4 reads per friend (<=200) and 3 writes (<=400/batch). */
const PAIR_PROCESSING_CHUNK = 50;
/** Legacy sweep: 1 reverse read per target, <=2 deletes per target. */
const LEGACY_SWEEP_CHUNK = 200;

export type CreateKakaoFriendPairsOnceDeps = {
  db: Firestore;
  verifyKakaoAccessToken: (accessToken: string) => Promise<{ userId: string }>;
  fetchFriends: (accessToken: string) => Promise<string[]>;
  /** Test-injectable clock; defaults to the real clock. */
  now?: () => Date;
  /** Test-injectable lease id source; defaults to randomUUID. */
  newSnapshotRunId?: () => string;
};

function exclusionRef(db: Firestore, ownerUid: string, targetUid: string) {
  return db
    .collection("recommendationExclusions")
    .doc(ownerUid)
    .collection("targets")
    .doc(targetUid);
}

function preconditionError(
  detail:
    | "primary_email_auth_required"
    | "kakao_identity_not_linked"
    | "identity_conflict"
    | "snapshot_in_progress",
): HttpsError {
  switch (detail) {
    case "primary_email_auth_required":
      return new HttpsError(
        "failed-precondition",
        "연세 이메일 인증을 먼저 완료해주세요.",
        { detail },
      );
    case "kakao_identity_not_linked":
      return new HttpsError(
        "failed-precondition",
        "카카오 계정 연결을 먼저 완료해주세요.",
        { detail },
      );
    case "identity_conflict":
      return new HttpsError(
        "failed-precondition",
        "이 카카오 계정은 다른 계정과 연결돼 있어요. 고객센터로 문의해주세요.",
        { detail },
      );
    case "snapshot_in_progress":
      return new HttpsError(
        "failed-precondition",
        "친구 확인이 이미 진행 중이에요. 잠시 후 다시 시도해주세요.",
        { detail },
      );
  }
}

export function createCreateKakaoFriendPairsOnceFunction(
  deps: CreateKakaoFriendPairsOnceDeps,
) {
  const nowProvider = deps.now ?? (() => new Date());
  const newRunId = deps.newSnapshotRunId ?? (() => randomUUID());
  const db = deps.db;

  return onCall(
    withAppCheck({ timeoutSeconds: 180, memory: "512MiB" }),
    async (request) => {
      const authUid = asNonEmptyString(request.auth?.uid);
      if (!authUid) {
        throw new HttpsError("unauthenticated", "로그인이 필요해요.");
      }
      const data = isRecord(request.data) ? request.data : {};
      const accessToken = asNonEmptyString(data.kakaoAccessToken);
      if (!accessToken) {
        throw new HttpsError(
          "invalid-argument",
          "카카오 액세스 토큰이 필요해요.",
        );
      }
      const claimedKakaoUserId = asNonEmptyString(
        (request.auth?.token as Record<string, unknown> | undefined)
          ?.kakaoUserId,
      );

      const userRef = db.collection("users").doc(authUid);
      const snapshotRunId = newRunId();

      // Transaction A (contract §4 step 1): preconditions + lease.
      const leaseResult = await db.runTransaction(async (transaction) => {
        const userSnapshot = await transaction.get(userRef);
        const userData = userSnapshot.exists
          ? ((userSnapshot.data() ?? {}) as Record<string, unknown>)
          : null;
        if (!userData || userData.isStudentVerified !== true) {
          throw preconditionError("primary_email_auth_required");
        }
        const decision = decideSnapshotLease({
          state: userData.kakaoFriendSnapshot,
          now: nowProvider(),
        });
        if (decision.action === "alreadyCompleted") {
          return decision;
        }
        if (decision.action === "inProgress") {
          throw preconditionError("snapshot_in_progress");
        }
        transaction.update(userRef, {
          kakaoFriendSnapshot: buildSnapshotLeaseUpdate({
            snapshotRunId,
            now: nowProvider(),
          }),
        });
        return decision;
      });
      if (leaseResult.action === "alreadyCompleted") {
        // Immutable completed snapshot: NO Kakao API call (contract §3).
        return {
          completed: true,
          pairCount: leaseResult.pairCount,
          alreadyCompleted: true,
        };
      }

      try {
        // Step 2: server-verified token -> identity precondition.
        const { userId: verifiedKakaoUserId } =
          await deps.verifyKakaoAccessToken(accessToken);
        const mappingSnapshot = await db
          .collection("kakaoIdentities")
          .doc(kakaoIdentityHash(verifiedKakaoUserId))
          .get();
        const identity = decideSnapshotIdentityPrecondition({
          authUid,
          claimedKakaoUserId,
          verifiedKakaoUserId,
          mappingAppUserId: mappingSnapshot.exists
            ? asNonEmptyString(mappingSnapshot.data()?.appUserId)
            : null,
        });
        if (!identity.ok) {
          throw preconditionError(identity.reason);
        }

        const friendKakaoIds = await deps.fetchFriends(accessToken);

        // Step 3: friend Kakao id -> member appUserId (reused resolver).
        const resolutionCandidates: FriendResolutionCandidate[] = [];
        for (
          let offset = 0;
          offset < friendKakaoIds.length;
          offset += RESOLUTION_LOOKUP_CHUNK
        ) {
          const candidateIds = friendKakaoIds
            .slice(offset, offset + RESOLUTION_LOOKUP_CHUNK)
            .filter((id) => SAFE_PATH_SEGMENT_RE.test(id));
          if (candidateIds.length === 0) continue;
          const userRefs = candidateIds.map((id) =>
            db.collection("users").doc(id),
          );
          const identityRefs = candidateIds.map((id) =>
            db.collection("kakaoIdentities").doc(kakaoIdentityHash(id)),
          );
          const lookupDocs = await db.getAll(...userRefs, ...identityRefs);
          for (let index = 0; index < candidateIds.length; index++) {
            const friendDoc = lookupDocs[index];
            const identityDoc = lookupDocs[candidateIds.length + index];
            resolutionCandidates.push({
              kakaoUserId: candidateIds[index],
              legacyUserDocExists: friendDoc?.exists === true,
              mappingAppUserId: identityDoc?.exists
                ? asNonEmptyString(identityDoc.data()?.appUserId)
                : null,
            });
          }
        }
        const resolution = resolveFriendExclusionAppUserIds({
          callerAppUserId: authUid,
          callerKakaoUserId: verifiedKakaoUserId,
          candidates: resolutionCandidates,
        });

        // Step 4: chunked pair upserts + bilateral exclusion reconcile.
        //
        // CONCURRENT-TOGGLE RULE (blocker #3): every pair-level write happens
        // inside a transaction that re-reads BOTH members' user docs and
        // recomputes the pair from their CURRENT effective preferences
        // (committed preference OR an in-flight ON mutation — see
        // isEffectiveAvoidanceEnabled). A concurrent setKakaoFriendAvoidance-
        // Enabled call therefore serializes against these transactions on the
        // caller's user doc, and the snapshot can never deactivate exclusions
        // an in-flight ON toggle just materialized. Residual disagreement in
        // any interleaving is over-exclusion only.
        const activeTargetUids = new Set<string>();
        let pairCount = 0;
        // Resolved targets are member appUserIds; anything outside the pair
        // member-uid contract is skipped defensively (never a whole-run abort).
        const targetUids = resolution.targetAppUserIds.filter(
          (targetUid) =>
            targetUid !== authUid &&
            isValidKakaoFriendPairMemberUid(targetUid),
        );
        for (
          let offset = 0;
          offset < targetUids.length;
          offset += PAIR_PROCESSING_CHUNK
        ) {
          const chunk = targetUids.slice(offset, offset + PAIR_PROCESSING_CHUNK);
          const refs = chunk.flatMap((targetUid) => [
            db
              .collection("kakaoFriendPairs")
              .doc(buildKakaoFriendPairId(authUid, targetUid)),
            db.collection("users").doc(targetUid),
            exclusionRef(db, authUid, targetUid),
            exclusionRef(db, targetUid, authUid),
          ]);
          const chunkResult = await db.runTransaction(async (transaction) => {
            const [callerSnap, ...snapshots] = await transaction.getAll(
              userRef,
              ...refs,
            );
            // Caller preference is re-read INSIDE every chunk transaction so
            // pair writes always reflect the current effective preference.
            const callerEnabled = isEffectiveAvoidanceEnabled(
              (callerSnap.data() ?? {}) as Record<string, unknown>,
            );
            let chunkPairCount = 0;
            const chunkActiveTargets: string[] = [];
            for (let index = 0; index < chunk.length; index++) {
              const targetUid = chunk[index];
              const pairSnap = snapshots[index * 4];
              const friendSnap = snapshots[index * 4 + 1];
              const forwardExclusionSnap = snapshots[index * 4 + 2];
              const reverseExclusionSnap = snapshots[index * 4 + 3];
              const forwardRef = exclusionRef(db, authUid, targetUid);
              const reverseRef = exclusionRef(db, targetUid, authUid);

              if (!friendSnap.exists) {
                // Resolved mapping without a member doc: not a Seolleyeon user
                // anymore. No pair; clear only Kakao-owned exclusion leftovers.
                for (const [ref, snap] of [
                  [forwardRef, forwardExclusionSnap] as const,
                  [reverseRef, reverseExclusionSnap] as const,
                ]) {
                  if (
                    snap.exists &&
                    isKakaoOwnedExclusion(
                      (snap.data() ?? {}) as Record<string, unknown>,
                    )
                  ) {
                    transaction.delete(ref);
                  }
                }
                continue;
              }

              const upsert = buildKakaoFriendPairUpsert({
                callerUid: authUid,
                friendUid: targetUid,
                callerAvoidanceEnabled: callerEnabled,
                friendAvoidanceEnabled: isEffectiveAvoidanceEnabled(
                  (friendSnap.data() ?? {}) as Record<string, unknown>,
                ),
                existingPairData: pairSnap.exists
                  ? ((pairSnap.data() ?? {}) as Record<string, unknown>)
                  : null,
              });
              transaction.set(
                pairSnap.ref,
                {
                  pairId: upsert.pairId,
                  memberUids: upsert.memberUids,
                  source: KAKAO_FRIEND_PAIR_SOURCE,
                  discoveredByUids: FieldValue.arrayUnion(authUid),
                  avoidanceEnabledBy: upsert.avoidanceEnabledBy,
                  avoidanceActive: upsert.avoidanceActive,
                  updatedAt: FieldValue.serverTimestamp(),
                  schemaVersion: 1,
                  ...(upsert.isNewPair
                    ? { createdAt: FieldValue.serverTimestamp() }
                    : {}),
                },
                { merge: true },
              );
              chunkPairCount++;

              if (upsert.avoidanceActive) {
                chunkActiveTargets.push(targetUid);
                const exclusionDoc = buildPairExclusionDoc(upsert);
                for (const [ref, snap] of [
                  [forwardRef, forwardExclusionSnap] as const,
                  [reverseRef, reverseExclusionSnap] as const,
                ]) {
                  transaction.set(
                    ref,
                    {
                      ...exclusionDoc,
                      updatedAt: FieldValue.serverTimestamp(),
                      ...(snap.exists
                        ? {}
                        : { createdAt: FieldValue.serverTimestamp() }),
                    },
                    { merge: true },
                  );
                }
              } else {
                // Inactive pair: delete only Kakao-owned docs (legacy
                // reconcile, spec §31 — other sources are never touched).
                for (const [ref, snap] of [
                  [forwardRef, forwardExclusionSnap] as const,
                  [reverseRef, reverseExclusionSnap] as const,
                ]) {
                  if (
                    snap.exists &&
                    isKakaoOwnedExclusion(
                      (snap.data() ?? {}) as Record<string, unknown>,
                    )
                  ) {
                    transaction.delete(ref);
                  }
                }
              }
            }
            return { chunkPairCount, chunkActiveTargets };
          });
          pairCount += chunkResult.chunkPairCount;
          for (const targetUid of chunkResult.chunkActiveTargets) {
            activeTargetUids.add(targetUid);
          }
        }

        // Step 5: legacy `kakao_talk_friend` sweep (idempotent, same run).
        const legacySnapshot = await db
          .collection("recommendationExclusions")
          .doc(authUid)
          .collection("targets")
          .where("source", "==", LEGACY_KAKAO_EXCLUSION_SOURCE)
          .get();
        const legacyTargets = legacySnapshot.docs.filter(
          (doc) =>
            doc.id !== authUid &&
            SAFE_PATH_SEGMENT_RE.test(doc.id) &&
            !activeTargetUids.has(doc.id),
        );
        let legacySweptCount = 0;
        for (
          let offset = 0;
          offset < legacyTargets.length;
          offset += LEGACY_SWEEP_CHUNK
        ) {
          const chunk = legacyTargets.slice(offset, offset + LEGACY_SWEEP_CHUNK);
          const reverseSnaps = await db.getAll(
            ...chunk.map((doc) => exclusionRef(db, doc.id, authUid)),
          );
          const batch = db.batch();
          for (let index = 0; index < chunk.length; index++) {
            const targetDoc = chunk[index];
            const reverseSnap = reverseSnaps[index];
            const decision = decideLegacySweepDeletion({
              callerUid: authUid,
              targetUid: targetDoc.id,
              rematerializedActiveTargetUids: activeTargetUids,
              reverseDocData: reverseSnap.exists
                ? ((reverseSnap.data() ?? {}) as Record<string, unknown>)
                : null,
            });
            if (decision.deleteForward) {
              batch.delete(targetDoc.ref);
              legacySweptCount++;
            }
            if (decision.deleteReverse) {
              batch.delete(reverseSnap.ref);
            }
          }
          await batch.commit();
        }

        // Step 6: completion transaction guarded by snapshotRunId.
        await db.runTransaction(async (transaction) => {
          const latest = await transaction.get(userRef);
          const state = (latest.data() ?? {}).kakaoFriendSnapshot;
          if (!snapshotRunOwnsLease(state, snapshotRunId)) {
            throw new HttpsError(
              "aborted",
              "다른 친구 확인 작업이 진행 중이에요.",
            );
          }
          transaction.update(userRef, {
            kakaoFriendSnapshot: buildSnapshotCompletionUpdate({
              previousState: state,
              pairCount,
              now: nowProvider(),
            }),
          });
        });

        logger.info("createKakaoFriendPairsOnce completed", {
          callerUidHash: uidHash(authUid),
          fetchedFriendCount: friendKakaoIds.length,
          matchedUserCount: resolution.matchedUserCount,
          pairCount,
          activePairCount: activeTargetUids.size,
          legacySweptCount,
        });

        return { completed: true, pairCount };
      } catch (error) {
        // Step 7: guarded failure transaction — never `completed` on partial
        // pages; partial pair docs stay for the idempotent retry.
        const errorCode = sanitizeSnapshotErrorCode(error);
        try {
          await db.runTransaction(async (transaction) => {
            const latest = await transaction.get(userRef);
            const state = (latest.data() ?? {}).kakaoFriendSnapshot;
            if (!snapshotRunOwnsLease(state, snapshotRunId)) return;
            transaction.update(userRef, {
              kakaoFriendSnapshot: buildSnapshotFailureUpdate({
                previousState: state,
                errorCode,
                now: nowProvider(),
              }),
            });
          });
        } catch (failureWriteError) {
          logger.error("kakao friend snapshot failure write failed", {
            callerUidHash: uidHash(authUid),
            code:
              failureWriteError instanceof Error ? "write_failed" : "unknown",
          });
        }
        logger.warn("createKakaoFriendPairsOnce failed", {
          callerUidHash: uidHash(authUid),
          errorCode,
        });
        if (error instanceof HttpsError) throw error;
        throw new HttpsError(
          "failed-precondition",
          "카카오 친구 확인을 완료하지 못했어요. 잠시 후 다시 시도해주세요.",
        );
      }
    },
  );
}

// =============================================================================
// setKakaoFriendAvoidanceEnabled (contract §5, blocker #3 ordering)
// =============================================================================

const TOGGLE_PAIR_CONCURRENCY = 20;

export type SetKakaoFriendAvoidanceEnabledDeps = {
  db: Firestore;
  /** Test-injectable clock; defaults to the real clock. */
  now?: () => Date;
  /**
   * TEST-ONLY interleaving hooks (fault-injection spec §13). Executed between
   * the lock and the pair reconcile / between the reconcile and the final
   * commit. Never set in production wiring.
   */
  onBeforeReconcile?: () => Promise<void>;
  onBeforeFinalize?: () => Promise<void>;
};

export type AvoidanceReconcileResult = {
  pairCount: number;
  activePairCount: number;
  /** True when a newer generation superseded this run mid-reconcile. */
  staleAborted: boolean;
};

/**
 * Reconcile helper (blocker #3): pair docs only, NO Kakao API — the callable
 * and any retry-from-scratch run this exact code path, so a retry with the
 * same desired value converges. Every pair is reconciled in its own
 * transaction that (a) re-reads the caller's mutation generation and aborts
 * silently — writing nothing — when stale, (b) recomputes the pair decision
 * from the pair doc (the counterpart's contribution comes from the doc itself,
 * spec §20), and (c) materializes or removes the bilateral exclusion docs.
 * Removals are double-guarded: Kakao-owned source AND canonical-or-legacy
 * pairId match (isDeletableKakaoPairExclusion).
 */
export async function reconcileKakaoFriendAvoidanceForUser(params: {
  db: Firestore;
  uid: string;
  enabled: boolean;
  generation: number;
}): Promise<AvoidanceReconcileResult> {
  const { db, uid, enabled, generation } = params;
  const userRef = db.collection("users").doc(uid);
  const pairsSnapshot = await db
    .collection("kakaoFriendPairs")
    .where("memberUids", "array-contains", uid)
    .get();
  const pairRefs = pairsSnapshot.docs.map((doc) => doc.ref);

  let pairCount = 0;
  let activePairCount = 0;
  let staleAborted = false;
  for (
    let offset = 0;
    offset < pairRefs.length && !staleAborted;
    offset += TOGGLE_PAIR_CONCURRENCY
  ) {
    const chunk = pairRefs.slice(offset, offset + TOGGLE_PAIR_CONCURRENCY);
    const results = await Promise.all(
      chunk.map((pairRef) =>
        db.runTransaction<{ active: boolean } | "stale" | null>(
          async (transaction) => {
            const [userSnap, pairSnap] = await transaction.getAll(
              userRef,
              pairRef,
            );
            // Generation check INSIDE every pair-write transaction: a stale
            // generation aborts silently without writing anything, so an
            // older operation can never overwrite a newer intent.
            if (
              !isCurrentAvoidanceGeneration(
                (userSnap.data() ?? {}) as Record<string, unknown>,
                generation,
              )
            ) {
              return "stale";
            }
            if (!pairSnap.exists) return null;
            const decision = decideAvoidanceToggle({
              pairData: (pairSnap.data() ?? {}) as Record<string, unknown>,
              uid,
              enabled,
            });
            if (!decision) return null;
            const [memberA, memberB] = decision.memberUids;
            const forwardRef = exclusionRef(db, memberA, memberB);
            const reverseRef = exclusionRef(db, memberB, memberA);
            const [forwardSnap, reverseSnap] = await transaction.getAll(
              forwardRef,
              reverseRef,
            );
            // Pair docs are NEVER deleted by toggling (spec §43).
            transaction.set(
              pairRef,
              {
                avoidanceEnabledBy: decision.avoidanceEnabledBy,
                avoidanceActive: decision.avoidanceActive,
                updatedAt: FieldValue.serverTimestamp(),
              },
              { merge: true },
            );
            if (decision.action === "materialize") {
              const exclusionDoc = buildPairExclusionDoc(decision);
              for (const [ref, snap] of [
                [forwardRef, forwardSnap] as const,
                [reverseRef, reverseSnap] as const,
              ]) {
                transaction.set(
                  ref,
                  {
                    ...exclusionDoc,
                    updatedAt: FieldValue.serverTimestamp(),
                    ...(snap.exists
                      ? {}
                      : { createdAt: FieldValue.serverTimestamp() }),
                  },
                  { merge: true },
                );
              }
            } else {
              for (const [ref, snap] of [
                [forwardRef, forwardSnap] as const,
                [reverseRef, reverseSnap] as const,
              ]) {
                if (
                  snap.exists &&
                  isDeletableKakaoPairExclusion(
                    (snap.data() ?? {}) as Record<string, unknown>,
                    memberA,
                    memberB,
                  )
                ) {
                  transaction.delete(ref);
                }
              }
            }
            return { active: decision.avoidanceActive };
          },
        ),
      ),
    );
    for (const result of results) {
      if (result === "stale") {
        staleAborted = true;
        continue;
      }
      if (!result) continue;
      pairCount++;
      if (result.active) activePairCount++;
    }
  }
  return { pairCount, activePairCount, staleAborted };
}

/**
 * Toggle executor (blocker #3). The ordering guarantees that EVERY failure
 * path fails in the over-exclusion direction, never under-exclusion:
 *
 *  - ON (desired true): (1) acquire the CAS mutation lock — the preference is
 *    NOT touched; (2) materialize all pairs + bilateral exclusions (chunked,
 *    idempotent, generation-checked per pair transaction); (3) ONLY after
 *    every pair is materialized, a final generation-checked transaction
 *    atomically sets kakaoFriendAvoidanceEnabled=true together with
 *    mutation.status="completed"; (4) success is returned only then.
 *    Mid-failure: preference stays false, partial exclusions remain
 *    (over-exclusion), the API returns failure.
 *  - OFF (desired false): the preference goes false IN the same transaction
 *    as the lock, before any exclusion removal; per-pair removal then runs
 *    generation-checked with the source+pairId deletion guard; the final
 *    transaction only marks the mutation completed. Mid-failure: preference
 *    already false, stale exclusions remain (over-exclusion only).
 *
 * Retries re-enter the same reconcileKakaoFriendAvoidanceForUser path with a
 * fresh generation and converge; a concurrent newer request supersedes via
 * the CAS generation bump and this run aborts without overwriting it.
 */
export async function executeSetKakaoFriendAvoidanceEnabled(
  deps: SetKakaoFriendAvoidanceEnabledDeps,
  params: { uid: string; enabled: boolean },
): Promise<{ enabled: boolean; pairCount: number; activePairCount: number }> {
  const db = deps.db;
  const nowProvider = deps.now ?? (() => new Date());
  const { uid, enabled } = params;
  const userRef = db.collection("users").doc(uid);

  // Phase 1: CAS lock. OFF also flips the preference false HERE so any later
  // failure leaves over-exclusion only (stale exclusions, never a hidden ON).
  const start = await db.runTransaction(async (transaction) => {
    const userSnap = await transaction.get(userRef);
    if (!userSnap.exists) {
      throw new HttpsError(
        "failed-precondition",
        "사용자 프로필이 필요해요.",
      );
    }
    const userData = (userSnap.data() ?? {}) as Record<string, unknown>;
    const started = buildAvoidanceMutationStart({
      currentMutation: userData[AVOIDANCE_MUTATION_FIELD],
      desired: enabled,
      now: nowProvider(),
    });
    transaction.update(userRef, {
      [AVOIDANCE_MUTATION_FIELD]: started.mutation,
      ...(enabled ? {} : { kakaoFriendAvoidanceEnabled: false }),
    });
    return started;
  });

  try {
    if (deps.onBeforeReconcile) await deps.onBeforeReconcile();

    // Phase 2: pair-docs-only reconcile (NO Kakao API), generation-checked.
    const reconcile = await reconcileKakaoFriendAvoidanceForUser({
      db,
      uid,
      enabled,
      generation: start.generation,
    });

    if (deps.onBeforeFinalize) await deps.onBeforeFinalize();

    // Phase 3: final generation-checked commit. ON flips the preference to
    // true ONLY here, atomically with the mutation completion, after every
    // pair verified materialized.
    const committed =
      !reconcile.staleAborted &&
      (await db.runTransaction(async (transaction) => {
        const userSnap = await transaction.get(userRef);
        if (
          !isCurrentAvoidanceGeneration(
            (userSnap.data() ?? {}) as Record<string, unknown>,
            start.generation,
          )
        ) {
          return false;
        }
        transaction.update(userRef, {
          ...(enabled ? { kakaoFriendAvoidanceEnabled: true } : {}),
          [AVOIDANCE_MUTATION_FIELD]: buildAvoidanceMutationCompletion({
            mutation: start.mutation,
            now: nowProvider(),
          }),
        });
        return true;
      }));
    if (!committed) {
      // Superseded by a newer generation — that newer intent owns the state;
      // this run must not flip the preference or re-materialize anything.
      throw new HttpsError(
        "aborted",
        "더 최근의 친구 피하기 설정을 반영하고 있어요.",
      );
    }
    return {
      enabled,
      pairCount: reconcile.pairCount,
      activePairCount: reconcile.activePairCount,
    };
  } catch (error) {
    // Best-effort, generation-guarded failure mark. The preference is false
    // on every path that reaches here (ON never set it; OFF already cleared
    // it in the lock transaction) — the only residue is over-exclusion.
    try {
      await db.runTransaction(async (transaction) => {
        const userSnap = await transaction.get(userRef);
        if (
          !isCurrentAvoidanceGeneration(
            (userSnap.data() ?? {}) as Record<string, unknown>,
            start.generation,
          )
        ) {
          return;
        }
        transaction.update(userRef, {
          [AVOIDANCE_MUTATION_FIELD]: buildAvoidanceMutationFailure({
            mutation: start.mutation,
            now: nowProvider(),
          }),
        });
      });
    } catch {
      // Leaving the mutation in "enabling"/"disabling" is safe: the
      // generation still guards it and a retry supersedes it.
    }
    throw error;
  }
}

export function createSetKakaoFriendAvoidanceEnabledFunction(
  deps: SetKakaoFriendAvoidanceEnabledDeps,
) {
  return onCall(withAppCheck(), async (request) => {
    const authUid = asNonEmptyString(request.auth?.uid);
    if (!authUid) {
      throw new HttpsError("unauthenticated", "로그인이 필요해요.");
    }
    const data = isRecord(request.data) ? request.data : {};
    const enabled = data.enabled;
    if (typeof enabled !== "boolean") {
      throw new HttpsError(
        "invalid-argument",
        "enabled 값이 올바르지 않아요.",
      );
    }

    const result = await executeSetKakaoFriendAvoidanceEnabled(deps, {
      uid: authUid,
      enabled,
    });

    logger.info("setKakaoFriendAvoidanceEnabled completed", {
      callerUidHash: uidHash(authUid),
      enabled: result.enabled,
      pairCount: result.pairCount,
      activePairCount: result.activePairCount,
    });

    return result;
  });
}
