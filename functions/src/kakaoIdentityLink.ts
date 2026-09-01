import { createHash } from "crypto";
import { FieldValue, type Firestore } from "firebase-admin/firestore";
import { HttpsError, onCall } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import { withAppCheck } from "./appCheckPolicy";

/**
 * Kakao identity linking (identity contract §4.3/§5).
 *
 * Kakao is authorization-only in the primary-email architecture: a verified
 * Kakao OAuth session may be bound to exactly one appUserId, and that binding
 * exists solely so friend-exclusion sync can resolve Kakao ids to member
 * accounts. Kakao is never an authentication credential on this path.
 */

const SAFE_PATH_SEGMENT_RE = /^[A-Za-z0-9_-]+$/;

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** `kakaoIdentities/{docId}`: lowercase hex sha256("kakao_identity:" + id). */
export function kakaoIdentityHash(kakaoUserId: string): string {
  return createHash("sha256")
    .update(`kakao_identity:${kakaoUserId}`, "utf8")
    .digest("hex");
}

// =============================================================================
// Pure decision logic (unit-testable without Firestore)
// =============================================================================

export type KakaoIdentityLinkRejection =
  | "identity_conflict"
  | "relink_required"
  | "primary_email_auth_required";

export type KakaoIdentityLinkDecision =
  | { ok: true; alreadyLinked: boolean }
  | { ok: false; reason: KakaoIdentityLinkRejection };

/**
 * Link-conflict resolution (contract §4.3). Fail closed: any ambiguity about
 * which appUserId a Kakao identity belongs to is manual remediation, never an
 * automatic re-bind.
 */
export function decideKakaoIdentityLink(params: {
  authUid: string;
  verifiedKakaoUserId: string;
  identityHash: string;
  existingMappingData: Record<string, unknown> | null;
  legacyUserDocExists: boolean;
  userDocData: Record<string, unknown> | null;
}): KakaoIdentityLinkDecision {
  const authUid = asNonEmptyString(params.authUid);
  const kakaoUserId = asNonEmptyString(params.verifiedKakaoUserId);
  if (!authUid || !kakaoUserId) {
    return { ok: false, reason: "primary_email_auth_required" };
  }

  // Precondition: the caller must already be a primary-email-authenticated,
  // student-verified account.
  if (!params.userDocData || params.userDocData.isStudentVerified !== true) {
    return { ok: false, reason: "primary_email_auth_required" };
  }

  if (params.existingMappingData) {
    const mappedAppUserId = asNonEmptyString(
      params.existingMappingData.appUserId
    );
    if (mappedAppUserId === authUid) {
      return { ok: true, alreadyLinked: true };
    }
    // ONE Kakao identity <-> ONE appUserId. Never silently re-bind.
    return { ok: false, reason: "identity_conflict" };
  }

  // LEGACY COLLISION: users/{kakaoUserId} existing under a different account
  // means this Kakao identity IS another legacy account.
  if (params.legacyUserDocExists && kakaoUserId !== authUid) {
    return { ok: false, reason: "identity_conflict" };
  }

  const connection = isRecord(params.userDocData.kakaoFriendConnection)
    ? params.userDocData.kakaoFriendConnection
    : {};
  const linkedHash = asNonEmptyString(connection.kakaoIdentityHash);
  if (linkedHash && linkedHash !== params.identityHash) {
    // The account already points at a different Kakao identity: no silent swap.
    return { ok: false, reason: "relink_required" };
  }

  return { ok: true, alreadyLinked: false };
}

export type KakaoCallerIdentityDecision =
  | { ok: true; appUserId: string }
  | { ok: false };

/**
 * Rollout-compatible caller identity OR-chain (contract §5): a verified Kakao
 * user id is accepted iff the caller's Firebase uid IS the Kakao id (legacy
 * invariant), the session claim names it (legacy claim), or the
 * kakaoIdentities mapping binds it to the caller's appUserId.
 */
export function decideKakaoCallerIdentity(params: {
  authUid: string | null;
  claimedKakaoUserId: string | null;
  verifiedKakaoUserId: string;
  mappingAppUserId: string | null;
}): KakaoCallerIdentityDecision {
  const verified = asNonEmptyString(params.verifiedKakaoUserId);
  if (!verified) return { ok: false };
  const authUid = asNonEmptyString(params.authUid);
  if (authUid && authUid === verified) {
    return { ok: true, appUserId: authUid };
  }
  const claimed = asNonEmptyString(params.claimedKakaoUserId);
  if (authUid && claimed && claimed === verified) {
    return { ok: true, appUserId: verified };
  }
  const mapped = asNonEmptyString(params.mappingAppUserId);
  if (authUid && mapped && mapped === authUid) {
    return { ok: true, appUserId: authUid };
  }
  return { ok: false };
}

export type FriendResolutionCandidate = {
  kakaoUserId: string;
  legacyUserDocExists: boolean;
  mappingAppUserId: string | null;
};

export type FriendResolution = {
  targetAppUserIds: string[];
  matchedUserCount: number;
  skippedSelfCount: number;
};

/**
 * Friend -> member resolution (contract §5). A friend Kakao id matches a
 * member iff users/{kakaoId} exists (legacy invariant) OR the kakaoIdentities
 * mapping resolves it; the RESOLVED appUserId is used for the exclusion pair.
 * This closes the fail-open where friends of new (email-primary) members
 * silently never matched.
 */
export function resolveFriendExclusionAppUserIds(params: {
  callerAppUserId: string;
  callerKakaoUserId: string;
  candidates: FriendResolutionCandidate[];
}): FriendResolution {
  const targets = new Set<string>();
  let matchedUserCount = 0;
  let skippedSelfCount = 0;
  for (const candidate of params.candidates) {
    const kakaoUserId = asNonEmptyString(candidate.kakaoUserId);
    if (!kakaoUserId) continue;
    if (kakaoUserId === params.callerKakaoUserId) {
      skippedSelfCount++;
      continue;
    }
    let resolved: string | null = null;
    if (candidate.legacyUserDocExists) {
      resolved = kakaoUserId;
    } else {
      const mapped = asNonEmptyString(candidate.mappingAppUserId);
      resolved =
        mapped && SAFE_PATH_SEGMENT_RE.test(mapped) ? mapped : null;
    }
    if (!resolved) continue;
    if (resolved === params.callerAppUserId) {
      skippedSelfCount++;
      continue;
    }
    matchedUserCount++;
    targets.add(resolved);
  }
  return {
    targetAppUserIds: [...targets],
    matchedUserCount,
    skippedSelfCount,
  };
}

function linkError(reason: KakaoIdentityLinkRejection): HttpsError {
  switch (reason) {
    case "primary_email_auth_required":
      return new HttpsError(
        "failed-precondition",
        "연세 이메일 인증을 먼저 완료해주세요.",
        { detail: "primary_email_auth_required" }
      );
    case "identity_conflict":
      return new HttpsError(
        "failed-precondition",
        "이 카카오 계정은 이미 다른 계정과 연결돼 있어요. 고객센터로 문의해주세요.",
        { detail: "identity_conflict" }
      );
    case "relink_required":
      return new HttpsError(
        "failed-precondition",
        "이미 다른 카카오 계정이 연결돼 있어요. 기존 연결을 해제한 뒤 다시 시도해주세요.",
        { detail: "relink_required" }
      );
  }
}

// =============================================================================
// linkKakaoFriendIdentity (contract §4.3)
// =============================================================================

export function createLinkKakaoFriendIdentityFunction(deps: {
  db: Firestore;
  verifyKakaoAccessToken: (accessToken: string) => Promise<{ userId: string }>;
}) {
  return onCall(withAppCheck(), async (request) => {
    const authUid = asNonEmptyString(request.auth?.uid);
    if (!authUid) {
      throw new HttpsError("unauthenticated", "로그인이 필요해요.");
    }

    const data = isRecord(request.data) ? request.data : {};
    const accessToken = asNonEmptyString(data.kakaoAccessToken);
    if (!accessToken) {
      throw new HttpsError(
        "invalid-argument",
        "카카오 액세스 토큰이 필요해요."
      );
    }

    // Server-resolved Kakao identity; the access token is never logged.
    const { userId: kakaoUserId } = await deps.verifyKakaoAccessToken(
      accessToken
    );
    const identityHash = kakaoIdentityHash(kakaoUserId);

    const db = deps.db;
    const userRef = db.collection("users").doc(authUid);
    const mappingRef = db.collection("kakaoIdentities").doc(identityHash);

    const result = await db.runTransaction(async (transaction) => {
      const refs = [userRef, mappingRef];
      const checkLegacyDoc = kakaoUserId !== authUid;
      if (checkLegacyDoc) {
        refs.push(db.collection("users").doc(kakaoUserId));
      }
      const snapshots = await transaction.getAll(...refs);
      const userSnapshot = snapshots[0];
      const mappingSnapshot = snapshots[1];
      const legacySnapshot = checkLegacyDoc ? snapshots[2] : null;

      const decision = decideKakaoIdentityLink({
        authUid,
        verifiedKakaoUserId: kakaoUserId,
        identityHash,
        existingMappingData: mappingSnapshot.exists
          ? ((mappingSnapshot.data() ?? {}) as Record<string, unknown>)
          : null,
        legacyUserDocExists: legacySnapshot?.exists === true,
        userDocData: userSnapshot.exists
          ? ((userSnapshot.data() ?? {}) as Record<string, unknown>)
          : null,
      });
      if (!decision.ok) {
        throw linkError(decision.reason);
      }

      const now = FieldValue.serverTimestamp();
      if (!decision.alreadyLinked) {
        transaction.set(mappingRef, {
          appUserId: authUid,
          kakaoUserId,
          linkedAt: now,
          status: "active",
        });
        transaction.set(
          userRef,
          {
            kakaoFriendConnection: {
              connected: true,
              kakaoIdentityHash: identityHash,
              linkedAt: now,
              lastVerifiedAt: now,
            },
          },
          { merge: true }
        );
      } else {
        transaction.set(
          userRef,
          {
            kakaoFriendConnection: {
              connected: true,
              kakaoIdentityHash: identityHash,
              lastVerifiedAt: now,
            },
          },
          { merge: true }
        );
      }
      return { alreadyLinked: decision.alreadyLinked };
    });

    logger.info("linkKakaoFriendIdentity completed", {
      appUserIdHash: createHash("sha256")
        .update(authUid, "utf8")
        .digest("hex")
        .slice(0, 12),
      alreadyLinked: result.alreadyLinked,
    });

    return { linked: true, alreadyLinked: result.alreadyLinked };
  });
}
