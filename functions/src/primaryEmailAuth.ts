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
const PRIMARY_AUTH_LEGACY_RESEND_COOLDOWN_MS = 60 * 1000;
// Terms gate (terms-gate-contract §2/§3). One repo-wide version covers all four
// required documents — there are no per-document versions.
export const CURRENT_TERMS_VERSION = "2026-05-16";
export const SUPPORTED_TERMS_VERSIONS: readonly string[] = ["2026-05-16"];
// `ageOver18` is NOT a UI item and MUST NOT be fabricated in any record.
export const REQUIRED_TERMS_DOCUMENT_IDS: readonly string[] = [
  "termsOfService",
  "privacyPolicy",
  "kakaoNamePhone",
  "ageOver20",
];
// Restricted account states may never re-enter through a fresh email login.
const REJOIN_RESTRICTED_STATUSES = new Set([
  "deleting",
  "banned",
  "blocked",
  "restricted_rejoin",
  "suspended",
  "withdrawn",
]);

export function shouldRenewPrimaryEmailSend(params: {
  status: string;
  expiresAtMs: number | null;
  sentAtMs: number | null;
  nowMs: number;
}): boolean {
  return (
    params.status === "sent" &&
    (params.expiresAtMs === null ||
      params.expiresAtMs <= params.nowMs ||
      (params.sentAtMs !== null &&
        params.sentAtMs <=
          params.nowMs - PRIMARY_AUTH_LEGACY_RESEND_COOLDOWN_MS))
  );
}

export function buildPrimaryEmailDeliveryRequestId(
  clientRequestId: string,
  sendGeneration: number
): string {
  return sendGeneration > 0
    ? `${clientRequestId}-renewal-${sendGeneration}`
    : clientRequestId;
}

function readSendGeneration(value: unknown): number {
  return typeof value === "number" &&
    Number.isSafeInteger(value) &&
    value >= 0
    ? value
    : 0;
}

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

export type TermsOptionalConsents = {
  marketing: boolean;
  push: boolean;
  email: boolean;
};

export type TermsAcceptanceSource =
  | "primary_auth_token"
  | "authenticated_reconsent";

export type TermsAcceptanceRejection =
  | "terms_acceptance_required"
  | "terms_version_outdated";

export type TermsAcceptanceDecision =
  | { ok: true; version: string; optionalConsents: TermsOptionalConsents }
  | { ok: false; reason: TermsAcceptanceRejection };

/**
 * Optional consents are ALWAYS strict booleans defaulting to FALSE. The legacy
 * client receipt used `fallback: true`, so a malformed blob recorded full
 * consent; that is the bug this gate closes.
 */
function normalizeOptionalConsents(raw: unknown): TermsOptionalConsents {
  const record = isRecord(raw) ? raw : {};
  return {
    marketing: record.marketing === true,
    push: record.push === true,
    email: record.email === true,
  };
}

/**
 * Validates a client terms-acceptance payload (contract §4). Fail closed: an
 * absent or non-record payload is `terms_acceptance_required`, never an
 * implicit acceptance.
 *
 * Version handling: a present-but-unsupported version is `terms_version_outdated`
 * (the user accepted *something*, just not the current documents); an absent or
 * blank version is `terms_acceptance_required` (nothing was accepted at all).
 */
export function evaluateTermsAcceptancePayload(
  raw: unknown
): TermsAcceptanceDecision {
  if (!isRecord(raw)) {
    return { ok: false, reason: "terms_acceptance_required" };
  }
  const rawVersion = raw.version;
  const version = asNonEmptyString(rawVersion);
  if (!version) {
    return {
      ok: false,
      reason:
        rawVersion === undefined || rawVersion === null
          ? "terms_acceptance_required"
          : "terms_version_outdated",
    };
  }
  if (!SUPPORTED_TERMS_VERSIONS.includes(version)) {
    return { ok: false, reason: "terms_version_outdated" };
  }

  const rawAccepted = raw.acceptedDocumentIds;
  if (!Array.isArray(rawAccepted)) {
    return { ok: false, reason: "terms_acceptance_required" };
  }
  // Unknown ids are ignored, never persisted: the required set is the only
  // gate and `ageOver18` is never fabricated from an unknown id.
  const acceptedIds = new Set(
    rawAccepted
      .map((value) => asNonEmptyString(value))
      .filter((value): value is string => value !== null)
  );
  for (const requiredId of REQUIRED_TERMS_DOCUMENT_IDS) {
    if (!acceptedIds.has(requiredId)) {
      return { ok: false, reason: "terms_acceptance_required" };
    }
  }

  return {
    ok: true,
    version,
    optionalConsents: normalizeOptionalConsents(raw.optionalConsents),
  };
}

/** Server-owned `users/{appUserId}.termsAcceptance` record (contract §3). */
export function buildTermsAcceptanceRecord(params: {
  version: string;
  optionalConsents: TermsOptionalConsents;
  source: TermsAcceptanceSource;
}): Record<string, unknown> {
  return {
    schemaVersion: 1,
    version: params.version,
    requiredDocumentIds: [...REQUIRED_TERMS_DOCUMENT_IDS],
    acceptedAt: FieldValue.serverTimestamp(),
    source: params.source,
    optionalConsents: normalizeOptionalConsents(params.optionalConsents),
    optionalUpdatedAt: FieldValue.serverTimestamp(),
  };
}

export type PrimaryEmailLinkTermsRejection = "terms-missing" | "terms-stale";

export type PrimaryEmailLinkTokenRejection =
  | "missing"
  | "malformed"
  | "email-mismatch"
  | "expired"
  | PrimaryEmailLinkTermsRejection;

export type PrimaryEmailLinkTermsDecision =
  | { ok: true; version: string; optionalConsents: TermsOptionalConsents }
  | { ok: false; reason: PrimaryEmailLinkTermsRejection };

export type PrimaryEmailLinkTokenDecision =
  | {
      ok: true;
      email: string;
      terms: PrimaryEmailLinkTermsDecision;
      completedAppUserId?: string;
      completedIsNewUser?: boolean;
    }
  | { ok: false; reason: PrimaryEmailLinkTokenRejection };

/**
 * Reads the non-PII terms proof carried on an `emailLinkTokens` document
 * (contract §4). Returned alongside the token decision rather than folded into
 * it, because only the account-CREATING branch enforces it — an existing user
 * whose token predates this change must still be able to log in (no lockout,
 * no migration).
 */
export function evaluatePrimaryEmailLinkTerms(
  tokenData: Record<string, unknown> | null | undefined
): PrimaryEmailLinkTermsDecision {
  const version = asNonEmptyString(tokenData?.termsVersion);
  if (!version) return { ok: false, reason: "terms-missing" };
  if (!SUPPORTED_TERMS_VERSIONS.includes(version)) {
    return { ok: false, reason: "terms-stale" };
  }
  return {
    ok: true,
    version,
    optionalConsents: normalizeOptionalConsents(
      tokenData?.termsOptionalConsents
    ),
  };
}

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
  // A missing document means "expired/purged or never existed". Completed
  // primary tokens remain until expiry so a lost callable response can be
  // retried by the same verified mailbox without consuming the Firebase
  // action code a second time.
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

  const terms = evaluatePrimaryEmailLinkTerms(tokenData);
  const status = asNonEmptyString(tokenData.status) ?? "pending";
  if (status === "completed") {
    const completedAppUserId = asNonEmptyString(
      tokenData.completedAppUserId
    );
    if (
      !completedAppUserId ||
      typeof tokenData.completedIsNewUser !== "boolean"
    ) {
      return { ok: false, reason: "malformed" };
    }
    return {
      ok: true,
      email,
      terms,
      completedAppUserId,
      completedIsNewUser: tokenData.completedIsNewUser,
    };
  }
  if (status !== "pending") {
    return { ok: false, reason: "malformed" };
  }

  return { ok: true, email, terms };
}

/** Reads the server-owned acceptance version already stored on a users doc. */
export function readStoredTermsVersion(
  userData: Record<string, unknown> | null | undefined
): string | null {
  const record = userData?.termsAcceptance;
  return isRecord(record) ? asNonEmptyString(record.version) : null;
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
  termsVersion: string;
  termsOptionalConsents: TermsOptionalConsents;
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
    // One-time snapshot state (kakao-friend-pairs contract §3): new accounts
    // start before their exactly-once Kakao friend snapshot.
    kakaoFriendSnapshot: { status: "not_started", schemaVersion: 1 },
    // Terms gate (contract §3/§5): an account can never be created without an
    // acceptance recorded in the same transaction.
    termsAcceptance: buildTermsAcceptanceRecord({
      version: params.termsVersion,
      optionalConsents: params.termsOptionalConsents,
      source: "primary_auth_token",
    }),
  };
}

/** Terms rejections from a client payload (contract §9 `details.detail`). */
export function termsAcceptanceError(
  reason: TermsAcceptanceRejection
): HttpsError {
  switch (reason) {
    case "terms_version_outdated":
      return new HttpsError(
        "failed-precondition",
        "약관이 업데이트됐어요. 약관에 다시 동의해주세요.",
        { detail: "terms_version_outdated" }
      );
    case "terms_acceptance_required":
      return new HttpsError(
        "failed-precondition",
        "약관 동의가 필요해요. 약관 동의 후 다시 시도해주세요.",
        { detail: "terms_acceptance_required" }
      );
  }
}

function tokenError(reason: PrimaryEmailLinkTokenRejection): HttpsError {
  switch (reason) {
    case "terms-missing":
      return termsAcceptanceError("terms_acceptance_required");
    case "terms-stale":
      return termsAcceptanceError("terms_version_outdated");
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

      // Terms gate (contract §4), validated BEFORE any rate-limit or
      // idempotency work so a malformed payload cannot consume send quota.
      //
      // COMPATIBILITY / FAIL-CLOSED: an ABSENT `termsAcceptance` is rejected
      // with `terms_acceptance_required`. The only legitimate caller is the
      // post-terms email screen, so there is no legacy caller to grandfather;
      // this is precisely what closes the F7 deep-link bypass, where a cold
      // start on an email link reached student verification (and account
      // creation) with no terms acceptance at all.
      const termsDecision = evaluateTermsAcceptancePayload(
        data.termsAcceptance
      );
      if (!termsDecision.ok) {
        throw termsAcceptanceError(termsDecision.reason);
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
        let existing: Record<string, unknown> | null = null;
        let sendGeneration = 0;
        if (existingRequest.exists) {
          existing = (existingRequest.data() ?? {}) as Record<
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
          const status = asNonEmptyString(existing.status) ?? "preparing";
          sendGeneration = readSendGeneration(existing.sendGeneration);
          if (
            !shouldRenewPrimaryEmailSend({
              status,
              expiresAtMs: toDate(existing.expiresAt)?.getTime() ?? null,
              sentAtMs: toDate(existing.sentAt)?.getTime() ?? null,
              nowMs,
            })
          ) {
            return {
              existing: true,
              status,
              actionLink: asNonEmptyString(existing.actionLink),
              token: asNonEmptyString(existing.token),
              deliveryRequestId:
                asNonEmptyString(existing.deliveryRequestId) ??
                buildPrimaryEmailDeliveryRequestId(
                  clientRequestId,
                  sendGeneration
                ),
              sendGeneration,
            };
          }

          // Older app builds keep the same client request id after a
          // successful send. Once that send's token has expired, renew the
          // reservation and provider idempotency key instead of returning a
          // permanent duplicate.
          sendGeneration += 1;
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
        const deliveryRequestId = buildPrimaryEmailDeliveryRequestId(
          clientRequestId,
          sendGeneration
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
        // The token doc is world-readable by id, so it carries ONLY the
        // non-PII terms proof (contract §4) — never the raw payload.
        tx.set(db.collection("emailLinkTokens").doc(token), {
          email,
          purpose: PRIMARY_AUTH_TOKEN_PURPOSE,
          createdAt: Timestamp.fromMillis(nowMs),
          expiresAt,
          termsVersion: termsDecision.version,
          termsAcceptedAt: Timestamp.fromMillis(nowMs),
          termsOptionalConsents: termsDecision.optionalConsents,
        });
        const requestReservation = {
          kind: PRIMARY_AUTH_TOKEN_PURPOSE,
          emailHash,
          clientRequestId,
          token,
          status: "preparing",
          sendGeneration,
          deliveryRequestId,
          expiresAt,
          purgeAt: Timestamp.fromMillis(nowMs + PRIMARY_AUTH_REQUEST_TTL_MS),
        };
        if (existing) {
          tx.set(
            requestRef,
            {
              ...requestReservation,
              renewedAt: Timestamp.fromMillis(nowMs),
              updatedAt: Timestamp.fromMillis(nowMs),
              actionLink: FieldValue.delete(),
              providerMessageId: FieldValue.delete(),
              sentAt: FieldValue.delete(),
            },
            { merge: true }
          );
        } else {
          tx.set(requestRef, {
            ...requestReservation,
            createdAt: Timestamp.fromMillis(nowMs),
          });
        }
        return {
          existing: false,
          status: "preparing",
          actionLink: null,
          token,
          deliveryRequestId,
          sendGeneration,
        };
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
          requestId: reservation.deliveryRequestId,
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
          sendGeneration: reservation.sendGeneration,
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

      // The account/binding transaction may have committed even when the
      // callable response carrying the custom token was lost. Re-mint only
      // for the exact same server-verified mailbox and the recorded account.
      if (tokenDecision.completedAppUserId) {
        const completedUserSnapshot = await transaction.get(
          db.collection("users").doc(tokenDecision.completedAppUserId)
        );
        const completedUserData = completedUserSnapshot.exists
          ? ((completedUserSnapshot.data() ?? {}) as Record<string, unknown>)
          : null;
        if (!completedUserData) {
          throw accountError("identity_conflict");
        }
        const completedUserRejection = evaluateExistingUser(
          completedUserData,
          email
        );
        if (completedUserRejection) {
          throw accountError(completedUserRejection);
        }
        return {
          appUserId: tokenDecision.completedAppUserId,
          isNewUser: tokenDecision.completedIsNewUser === true,
          userData: completedUserData,
          email,
        };
      }

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

      const terms = tokenDecision.terms;
      // Terms gate (contract §5): enforced ONLY for the account-creating
      // branch, and thrown before any write so no partial state survives.
      // Existing accounts stay functional without a proof (no lockout, no
      // migration) — their staleness is handled by the client resolver rung.
      if (decision.isNewUser && !terms.ok) {
        throw tokenError(terms.reason);
      }

      const userRef = db.collection("users").doc(decision.appUserId);
      if (decision.isNewUser && terms.ok) {
        transaction.set(
          userRef,
          buildPrimaryAuthNewUserShell({
            appUserId: decision.appUserId,
            studentEmail: email,
            termsVersion: terms.version,
            termsOptionalConsents: terms.optionalConsents,
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
            // A returning user who re-accepted a bumped version at login gets
            // the fresh record; without a proof the stored one is untouched.
            ...(terms.ok
              ? {
                  termsAcceptance: buildTermsAcceptanceRecord({
                    version: terms.version,
                    optionalConsents: terms.optionalConsents,
                    source: "primary_auth_token",
                  }),
                }
              : {}),
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
      // Logical single-use guarantee: the account transition happens once,
      // while an identical verified-mailbox retry can recover a response that
      // was lost after this transaction committed. The purge job removes the
      // marker after the original 30-minute expiry.
      transaction.set(
        tokenRef,
        {
          status: "completed",
          completedAppUserId: decision.appUserId,
          completedIsNewUser: decision.isNewUser,
          completedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      return {
        appUserId: decision.appUserId,
        isNewUser: decision.isNewUser,
        userData: decision.userData,
        email,
        // The version in force after this completion: the one just recorded,
        // otherwise whatever the account already carried.
        termsVersion: terms.ok
          ? terms.version
          : readStoredTermsVersion(decision.userData),
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
      termsVersion: completion.termsVersion,
    };
  });
}
