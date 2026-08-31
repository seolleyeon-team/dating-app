import type { Auth } from "firebase-admin/auth";
import {
  FieldValue,
  Timestamp,
  type Firestore,
} from "firebase-admin/firestore";
import {
  HttpsError,
  onCall,
  type CallableOptions,
} from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";
import { createHash, randomUUID } from "crypto";

import { withAppCheck } from "./appCheckPolicy";
import {
  decideStudentVerificationRateLimit,
  normalizeYonseiEmail,
} from "./studentVerificationEmail";

/**
 * Yonsei-email-primary authentication (identity contract §4.1/§4.2).
 *
 * The verified Yonsei mailbox is the PRIMARY credential. Kakao is never an
 * authentication credential on this path: token documents written here carry
 * `purpose: "primary_auth"` and NO kakaoUserId, and the completion callable
 * mints the canonical `{ appSession: true, primaryAuth: "yonsei_email" }`
 * session claims.
 */

export const PRIMARY_AUTH_TOKEN_PURPOSE = "primary_auth";
const TOKEN_ID_RE = /^[A-Za-z0-9_-]{1,128}$/;
const SAFE_EMAIL_REQUEST_ID = /^[A-Za-z0-9_-]{16,128}$/;
const PRIMARY_AUTH_TOKEN_TTL_MS = 30 * 60 * 1000;
const PRIMARY_AUTH_REQUEST_TTL_MS = 31 * 24 * 60 * 60 * 1000;
// Restricted account states may never re-enter through a fresh email login.
const REJOIN_RESTRICTED_STATUSES = new Set([
  "deleting",
  "banned",
  "blocked",
  "restricted_rejoin",
  "suspended",
  "withdrawn",
]);

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toDate(value: unknown): Date | null {
  if (value && typeof value === "object") {
    const maybeTimestamp = value as { toDate?: unknown };
    if (typeof maybeTimestamp.toDate === "function") {
      const date = maybeTimestamp.toDate();
      return date instanceof Date && !Number.isNaN(date.getTime())
        ? date
        : null;
    }
  }
  return value instanceof Date && !Number.isNaN(value.getTime()) ? value : null;
}

function sha256Hex(value: string): string {
  return createHash("sha256").update(value, "utf8").digest("hex");
}

// =============================================================================
// Pure decision logic (unit-testable without Firestore)
// =============================================================================

export type PrimaryEmailLinkTokenRejection =
  | "missing"
  | "malformed"
  | "email-mismatch"
  | "expired";

export type PrimaryEmailLinkTokenDecision =
  | { ok: true; email: string }
  | { ok: false; reason: PrimaryEmailLinkTokenRejection };

/**
 * Validates an `emailLinkTokens` document for the primary-auth flow. The
 * Firebase email-link session is the mailbox-ownership proof; the token
 * document only routes the completion back to the request that created it.
 */
export function evaluatePrimaryEmailLinkToken(params: {
  tokenData: Record<string, unknown> | null | undefined;
  authenticatedEmail: unknown;
  now: Date;
}): PrimaryEmailLinkTokenDecision {
  const tokenData = params.tokenData;
  // Tokens are deleted in the completion transaction, so a missing document
  // means "consumed or never existed" — both map to the same rejection.
  if (!tokenData) return { ok: false, reason: "missing" };

  const email = normalizeYonseiEmail(tokenData.email);
  const authenticatedEmail = normalizeYonseiEmail(params.authenticatedEmail);
  // A legacy token (kakaoUserId, no purpose) must never complete through the
  // primary flow, and vice versa.
  if (
    tokenData.purpose !== PRIMARY_AUTH_TOKEN_PURPOSE ||
    tokenData.kakaoUserId != null ||
    !email ||
    !authenticatedEmail
  ) {
    return { ok: false, reason: "malformed" };
  }

  if (email !== authenticatedEmail) {
    return { ok: false, reason: "email-mismatch" };
  }

  const createdAt = toDate(tokenData.createdAt);
  const expiresAt = toDate(tokenData.expiresAt);
  const nowMs = params.now.getTime();
  // Same expiry + clock-skew policy as the legacy completion: a missing or
  // malformed timestamp is expired, and a createdAt more than 5 minutes in
  // the future is a planted/clock-skewed document.
  if (
    !createdAt ||
    !expiresAt ||
    createdAt.getTime() > nowMs + 5 * 60 * 1000 ||
    expiresAt.getTime() <= nowMs
  ) {
    return { ok: false, reason: "expired" };
  }

  return { ok: true, email };
}

export type PrimaryEmailAccountRejection =
  | "identity_conflict"
  | "rejoin_restricted"
  | "email_mismatch";

export type PrimaryEmailAccountDecision =
  | {
      ok: true;
      appUserId: string;
      isNewUser: boolean;
      createBinding: boolean;
      userData: Record<string, unknown> | null;
    }
  | { ok: false; reason: PrimaryEmailAccountRejection };

function isRejoinRestricted(userData: Record<string, unknown>): boolean {
  const status = asNonEmptyString(userData.status);
  return (
    (status !== null && REJOIN_RESTRICTED_STATUSES.has(status)) ||
    userData.loginDisabled === true ||
    userData.isWithdrawn === true
  );
}

function evaluateExistingUser(
  userData: Record<string, unknown>,
  normalizedEmail: string
): PrimaryEmailAccountRejection | null {
  // Withdrawal/rejoin guard runs before any merge; a restricted account can
  // never be re-entered (or bypassed with a fresh shell) via email login.
  if (isRejoinRestricted(userData)) return "rejoin_restricted";
  const storedEmailValue = userData.studentEmail;
  const storedEmail = normalizeYonseiEmail(storedEmailValue);
  if (
    storedEmailValue != null &&
    asNonEmptyString(storedEmailValue) &&
    storedEmail !== normalizedEmail
  ) {
    return "email_mismatch";
  }
  return null;
}

/**
 * Resolves the appUserId for a verified Yonsei mailbox (contract §4.2 steps
 * 2-4). Pure: the caller supplies the binding document, the legacy
 * `studentEmail` query results (limit 2), and the already-read user documents.
 */
export function decidePrimaryEmailAccountResolution(params: {
  authUid: string;
  normalizedEmail: string;
  bindingData: Record<string, unknown> | null;
  bindingUserData: Record<string, unknown> | null;
  legacyCandidates: Array<{ id: string; data: Record<string, unknown> }>;
  authUidUserData?: Record<string, unknown> | null;
}): PrimaryEmailAccountDecision {
  const authUid = asNonEmptyString(params.authUid);
  if (!authUid) return { ok: false, reason: "identity_conflict" };

  if (params.bindingData) {
    const appUserId = asNonEmptyString(params.bindingData.appUserId);
    // A binding that points at a missing or unreadable account is manual
    // remediation territory — never silently rebound or recreated.
    if (!appUserId || !params.bindingUserData) {
      return { ok: false, reason: "identity_conflict" };
    }
    const rejection = evaluateExistingUser(
      params.bindingUserData,
      params.normalizedEmail
    );
    if (rejection) return { ok: false, reason: rejection };
    return {
      ok: true,
      appUserId,
      isNewUser: false,
      createBinding: false,
      userData: params.bindingUserData,
    };
  }

  const candidates = params.legacyCandidates;
  if (candidates.length >= 2) {
    // Two legacy accounts claim the same mailbox: NO automatic merge.
    return { ok: false, reason: "identity_conflict" };
  }
  if (candidates.length === 1) {
    const candidate = candidates[0];
    const candidateId = asNonEmptyString(candidate.id);
    if (!candidateId || candidate.data.isStudentVerified !== true) {
      return { ok: false, reason: "identity_conflict" };
    }
    const rejection = evaluateExistingUser(
      candidate.data,
      params.normalizedEmail
    );
    if (rejection) return { ok: false, reason: rejection };
    return {
      ok: true,
      appUserId: candidateId,
      isNewUser: false,
      createBinding: true,
      userData: candidate.data,
    };
  }

  // No binding and no legacy account: the Firebase email-link UID becomes the
  // appUserId. If a document already exists under that UID it is merged, and
  // the rejoin guard still applies to it.
  const authUidUserData = params.authUidUserData ?? null;
  if (authUidUserData) {
    const rejection = evaluateExistingUser(
      authUidUserData,
      params.normalizedEmail
    );
    if (rejection) return { ok: false, reason: rejection };
  }
  return {
    ok: true,
    appUserId: authUid,
    isNewUser: authUidUserData === null,
    createBinding: true,
    userData: authUidUserData,
  };
}

/**
 * Canonical session claims (contract §2). The legacy `kakaoUserId` claim is
 * carried ONLY for legacy-invariant accounts whose users doc stores
 * `kakaoUserId === appUserId`.
 */
export function buildCanonicalSessionClaims(
  appUserId: string,
  userData: Record<string, unknown> | null
): Record<string, unknown> {
  const claims: Record<string, unknown> = {
    appSession: true,
    primaryAuth: "yonsei_email",
  };
  if (userData && asNonEmptyString(userData.kakaoUserId) === appUserId) {
    claims.kakaoUserId = appUserId;
  }
  return claims;
}

/** New-user shell (contract §4.2 step 2) — fail-closed recommendation defaults. */
export function buildPrimaryAuthNewUserShell(params: {
  appUserId: string;
  studentEmail: string;
}): Record<string, unknown> {
  return {
    appUserId: params.appUserId,
    studentEmail: params.studentEmail,
    isStudentVerified: true,
    studentVerifiedAt: FieldValue.serverTimestamp(),
    createdAt: FieldValue.serverTimestamp(),
    lastLoginAt: FieldValue.serverTimestamp(),
    profileImageUrl: "",
    profileImageMode: "avatar",
    kakaoFriendAvoidanceEnabled: false,
    recommendationPrivacyReady: false,
    kakaoFriendReconcileStatus: "pending",
  };
}

function tokenError(reason: PrimaryEmailLinkTokenRejection): HttpsError {
  switch (reason) {
    case "email-mismatch":
      return new HttpsError(
        "permission-denied",
        "인증한 이메일과 요청한 이메일이 일치하지 않아요."
      );
    case "expired":
      return new HttpsError(
        "deadline-exceeded",
        "인증 링크가 만료됐어요. 새 인증 링크를 요청해주세요."
      );
    case "missing":
    case "malformed":
      return new HttpsError(
        "failed-precondition",
        "인증 링크 정보를 확인할 수 없어요. 새 인증 링크를 요청해주세요."
      );
  }
}

function accountError(reason: PrimaryEmailAccountRejection): HttpsError {
  switch (reason) {
    case "identity_conflict":
      return new HttpsError(
        "failed-precondition",
        "계정 정보를 확인할 수 없어요. 고객센터로 문의해주세요.",
        { detail: "identity_conflict" }
      );
    case "rejoin_restricted":
      return new HttpsError(
        "failed-precondition",
        "이 계정으로는 다시 가입할 수 없어요.",
        { detail: "rejoin_restricted" }
      );
    case "email_mismatch":
      return new HttpsError(
        "permission-denied",
        "이미 다른 연세 이메일로 인증된 계정이에요."
      );
  }
}

// =============================================================================
// sendPrimaryStudentEmailLink (contract §4.1)
// =============================================================================

export type PrimaryEmailLinkSendDeps = {
  db: Firestore;
  secrets: CallableOptions["secrets"];
  requireSender: () => { from: string; replyTo?: string };
  readApiKey: () => string;
  generateActionLink: (email: string, token: string) => Promise<string>;
  deliverEmail: (params: {
    apiKey: string;
    from: string;
    replyTo?: string;
    to: string;
    requestId: string;
    actionLink: string;
  }) => Promise<string>;
};

export function createSendPrimaryStudentEmailLinkFunction(
  deps: PrimaryEmailLinkSendDeps
) {
  return onCall(
    withAppCheck({
      timeoutSeconds: 30,
      memory: "256MiB",
      maxInstances: 3,
      concurrency: 10,
      secrets: deps.secrets,
    }),
    async (request) => {
      // Pre-login by design: App Check is enforced, auth is not required.
      const data = isRecord(request.data) ? request.data : {};
      const email = normalizeYonseiEmail(data.email);
      const clientRequestId = asNonEmptyString(data.requestId);
      if (
        !email ||
        !clientRequestId ||
        !SAFE_EMAIL_REQUEST_ID.test(clientRequestId)
      ) {
        throw new HttpsError(
          "invalid-argument",
          "연세 이메일 인증 요청이 올바르지 않아요."
        );
      }

      const sender = deps.requireSender();
      const apiKey = deps.readApiKey();
      if (!apiKey) {
        throw new HttpsError(
          "failed-precondition",
          "인증 메일 발송 설정이 완료되지 않았어요."
        );
      }

      const db = deps.db;
      const nowMs = Date.now();
      const emailHash = sha256Hex(email);
      const requestRef = db
        .collection("studentVerificationEmailRequests")
        .doc(sha256Hex(`primary:${emailHash}:${clientRequestId}`));
      const emailRateRef = db
        .collection("studentVerificationEmailRateLimits")
        .doc(sha256Hex(`email:${email}`));

      const reservation = await db.runTransaction(async (tx) => {
        const existingRequest = await tx.get(requestRef);
        if (existingRequest.exists) {
          const existing = (existingRequest.data() ?? {}) as Record<
            string,
            unknown
          >;
          if (
            existing.kind !== PRIMARY_AUTH_TOKEN_PURPOSE ||
            existing.emailHash !== emailHash ||
            existing.clientRequestId !== clientRequestId
          ) {
            throw new HttpsError(
              "permission-denied",
              "인증 요청을 확인할 수 없어요."
            );
          }
          return {
            existing: true,
            status: asNonEmptyString(existing.status) ?? "preparing",
            actionLink: asNonEmptyString(existing.actionLink),
            token: asNonEmptyString(existing.token),
          };
        }

        const emailRateSnap = await tx.get(emailRateRef);
        const emailRate = (emailRateSnap.data() ?? {}) as Record<
          string,
          unknown
        >;
        const emailDecision = decideStudentVerificationRateLimit(
          {
            minuteWindowStartedAtMs:
              toDate(emailRate.minuteWindowStartedAt)?.getTime() ?? null,
            minuteRequestCount:
              typeof emailRate.minuteRequestCount === "number"
                ? emailRate.minuteRequestCount
                : null,
            dayWindowStartedAtMs:
              toDate(emailRate.dayWindowStartedAt)?.getTime() ?? null,
            dayRequestCount:
              typeof emailRate.dayRequestCount === "number"
                ? emailRate.dayRequestCount
                : null,
          },
          nowMs
        );
        if (!emailDecision.allowed) {
          throw new HttpsError(
            "resource-exhausted",
            "인증 메일은 잠시 후 다시 보낼 수 있어요."
          );
        }

        const token = randomUUID();
        const expiresAt = Timestamp.fromMillis(
          nowMs + PRIMARY_AUTH_TOKEN_TTL_MS
        );
        // Primary-flow token shape (contract §3): purpose only, NO kakaoUserId.
        tx.set(emailRateRef, {
          minuteWindowStartedAt: Timestamp.fromMillis(
            emailDecision.minuteWindowStartedAtMs
          ),
          minuteRequestCount: emailDecision.minuteRequestCount,
          dayWindowStartedAt: Timestamp.fromMillis(
            emailDecision.dayWindowStartedAtMs
          ),
          dayRequestCount: emailDecision.dayRequestCount,
          updatedAt: Timestamp.fromMillis(nowMs),
        }, { merge: true });
        tx.set(db.collection("emailLinkTokens").doc(token), {
          email,
          purpose: PRIMARY_AUTH_TOKEN_PURPOSE,
          createdAt: Timestamp.fromMillis(nowMs),
          expiresAt,
        });
        tx.set(requestRef, {
          kind: PRIMARY_AUTH_TOKEN_PURPOSE,
          emailHash,
          clientRequestId,
          token,
          status: "preparing",
          createdAt: Timestamp.fromMillis(nowMs),
          expiresAt,
          purgeAt: Timestamp.fromMillis(nowMs + PRIMARY_AUTH_REQUEST_TTL_MS),
        });
        return { existing: false, status: "preparing", actionLink: null, token };
      });

      if (reservation.status === "sent") {
        return { accepted: true, duplicate: true };
      }
      if (!reservation.token) {
        throw new HttpsError(
          "failed-precondition",
          "인증 요청이 만료됐어요. 다시 시도해주세요."
        );
      }

      let actionLink = reservation.actionLink;
      if (!actionLink) {
        if (reservation.existing) {
          // Another call with the same request id is generating the link. Do
          // not create a second link under the same Resend idempotency key.
          throw new HttpsError(
            "aborted",
            "인증 메일을 준비 중이에요. 잠시 후 다시 시도해주세요."
          );
        }
        try {
          actionLink = await deps.generateActionLink(email, reservation.token);
          await requestRef.update({
            actionLink,
            status: "sending",
            updatedAt: Timestamp.fromMillis(Date.now()),
          });
        } catch (error) {
          await requestRef.set(
            {
              status: "generation_failed",
              updatedAt: Timestamp.fromMillis(Date.now()),
            },
            { merge: true }
          );
          logger.error(
            "primary auth Firebase action-link generation failed",
            { error: error instanceof Error ? error.name : "unknown" }
          );
          throw new HttpsError(
            "internal",
            "인증 링크를 만들지 못했어요. 잠시 후 다시 시도해주세요."
          );
        }
      }

      try {
        const providerMessageId = await deps.deliverEmail({
          apiKey,
          from: sender.from,
          replyTo: sender.replyTo,
          to: email,
          requestId: clientRequestId,
          actionLink,
        });
        // The bearer link is not needed on our server once the provider has
        // accepted it. Never log it.
        await requestRef.set(
          {
            status: "sent",
            providerMessageId,
            sentAt: Timestamp.fromMillis(Date.now()),
            updatedAt: Timestamp.fromMillis(Date.now()),
            actionLink: FieldValue.delete(),
          },
          { merge: true }
        );
        logger.info("primary auth email accepted by provider", {
          requestIdHash: sha256Hex(clientRequestId).slice(0, 12),
          emailHashPrefix: emailHash.slice(0, 12),
        });
        return { accepted: true, duplicate: false };
      } catch (error) {
        await requestRef.set(
          {
            status: "sending_unknown",
            updatedAt: Timestamp.fromMillis(Date.now()),
          },
          { merge: true }
        );
        if (error instanceof HttpsError) throw error;
        logger.error("primary auth email provider call failed", {
          error: error instanceof Error ? error.name : "unknown",
        });
        throw new HttpsError(
          "internal",
          "인증 메일을 보내지 못했어요. 잠시 후 다시 시도해주세요."
        );
      }
    }
  );
}

// =============================================================================
// completePrimaryStudentEmailAuth (contract §4.2)
// =============================================================================

export function createCompletePrimaryStudentEmailAuthFunction(
  db: Firestore,
  auth: Auth
) {
  return onCall(withAppCheck(), async (request) => {
    const authUid = asNonEmptyString(request.auth?.uid);
    if (!authUid) {
      throw new HttpsError("unauthenticated", "이메일 인증 세션이 필요해요.");
    }

    const authToken = request.auth?.token as
      | Record<string, unknown>
      | undefined;
    const authenticatedEmail = normalizeYonseiEmail(authToken?.email);
    if (!authenticatedEmail || authToken?.email_verified !== true) {
      throw new HttpsError(
        "failed-precondition",
        "연세 이메일 인증이 확인되지 않았어요."
      );
    }

    // Server re-read: the ID token alone is not trusted for the mailbox proof.
    const authUser = await auth.getUser(authUid);
    const authUserEmail = normalizeYonseiEmail(authUser.email);
    if (!authUser.emailVerified || authUserEmail !== authenticatedEmail) {
      throw new HttpsError(
        "failed-precondition",
        "연세 이메일 인증이 확인되지 않았어요."
      );
    }

    const requestData = isRecord(request.data) ? request.data : {};
    const token = asNonEmptyString(requestData.token);
    if (!token || !TOKEN_ID_RE.test(token)) {
      throw new HttpsError("invalid-argument", "인증 링크 토큰이 필요해요.");
    }

    const tokenRef = db.collection("emailLinkTokens").doc(token);
    const completion = await db.runTransaction(async (transaction) => {
      const tokenSnapshot = await transaction.get(tokenRef);
      const tokenDecision = evaluatePrimaryEmailLinkToken({
        tokenData: tokenSnapshot.exists ? tokenSnapshot.data() : null,
        authenticatedEmail,
        now: new Date(),
      });
      if (!tokenDecision.ok) {
        throw tokenError(tokenDecision.reason);
      }
      const email = tokenDecision.email;
      const emailHash = sha256Hex(email);
      const bindingRef = db.collection("studentEmailBindings").doc(emailHash);
      const bindingSnapshot = await transaction.get(bindingRef);
      const bindingData = bindingSnapshot.exists
        ? ((bindingSnapshot.data() ?? {}) as Record<string, unknown>)
        : null;

      let bindingUserData: Record<string, unknown> | null = null;
      let legacyCandidates: Array<{
        id: string;
        data: Record<string, unknown>;
      }> = [];
      let authUidUserData: Record<string, unknown> | null = null;
      if (bindingData) {
        const boundAppUserId = asNonEmptyString(bindingData.appUserId);
        if (boundAppUserId) {
          const userSnapshot = await transaction.get(
            db.collection("users").doc(boundAppUserId)
          );
          bindingUserData = userSnapshot.exists
            ? ((userSnapshot.data() ?? {}) as Record<string, unknown>)
            : null;
        }
      } else {
        const legacySnapshot = await transaction.get(
          db.collection("users").where("studentEmail", "==", email).limit(2)
        );
        legacyCandidates = legacySnapshot.docs.map((doc) => ({
          id: doc.id,
          data: (doc.data() ?? {}) as Record<string, unknown>,
        }));
        if (legacyCandidates.length === 0) {
          const authUidSnapshot = await transaction.get(
            db.collection("users").doc(authUid)
          );
          authUidUserData = authUidSnapshot.exists
            ? ((authUidSnapshot.data() ?? {}) as Record<string, unknown>)
            : null;
        }
      }

      const decision = decidePrimaryEmailAccountResolution({
        authUid,
        normalizedEmail: email,
        bindingData,
        bindingUserData,
        legacyCandidates,
        authUidUserData,
      });
      if (!decision.ok) {
        throw accountError(decision.reason);
      }

      const userRef = db.collection("users").doc(decision.appUserId);
      if (decision.isNewUser) {
        transaction.set(
          userRef,
          buildPrimaryAuthNewUserShell({
            appUserId: decision.appUserId,
            studentEmail: email,
          }),
          { merge: true }
        );
      } else {
        transaction.set(
          userRef,
          {
            studentEmail: email,
            isStudentVerified: true,
            studentVerifiedAt: FieldValue.serverTimestamp(),
            lastLoginAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );
      }
      if (decision.createBinding) {
        // Server-only collection; never stores the raw email.
        transaction.set(
          bindingRef,
          {
            appUserId: decision.appUserId,
            emailHash,
            createdAt: FieldValue.serverTimestamp(),
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );
      }
      // Single-use guarantee: the token is consumed in the same transaction.
      transaction.delete(tokenRef);
      return {
        appUserId: decision.appUserId,
        isNewUser: decision.isNewUser,
        userData: decision.userData,
        email,
      };
    });

    const customToken = await auth.createCustomToken(
      completion.appUserId,
      buildCanonicalSessionClaims(completion.appUserId, completion.userData)
    );

    logger.info("completePrimaryStudentEmailAuth succeeded", {
      appUserIdHash: sha256Hex(completion.appUserId).slice(0, 12),
      isNewUser: completion.isNewUser,
    });

    const userData = completion.userData;
    return {
      customToken,
      appUserId: completion.appUserId,
      email: completion.email,
      isNewUser: completion.isNewUser,
      initialSetupComplete: userData?.initialSetupComplete === true,
      adultVerified: userData?.adultVerified === true,
      recommendationPrivacyReady:
        userData?.recommendationPrivacyReady === true,
    };
  });
}
