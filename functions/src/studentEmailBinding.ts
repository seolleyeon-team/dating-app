/**
 * P0-1 (2026-10 production audit): one Yonsei mailbox ↔ at most one account.
 *
 * `studentEmailBindings/{sha256(normalized email)}` is the single server-owned
 * ownership record for a mailbox (identity contract §3; clients can neither
 * read nor write it). Every path that can stamp `studentEmail` /
 * `isStudentVerified` onto a users document claims the binding INSIDE the
 * same Firestore transaction through `claimStudentEmailBinding`, so two
 * accounts racing for one mailbox serialize on this document and exactly one
 * commit wins:
 *
 *   - sendStudentVerificationEmail (legacy issuance) reserves it as
 *     `status: "pending"` with the token's expiry. The hosted verification
 *     page (public/auth-email-link.html) writes users/{uid} directly and can
 *     never create this document, so firestore.rules only honours that write
 *     when the reservation names the target account. An unexpired pending
 *     reservation held by another account refuses a second issuance; an
 *     expired one is taken over.
 *   - completeStudentEmailLink (legacy callable) and
 *     completePrimaryStudentEmailAuth confirm it (`status: "confirmed"`).
 *     Bindings written before this field existed carry no status and count
 *     as confirmed.
 *
 * A pending reservation only proves that an account ASKED for a mail; it is
 * never treated as proof of mailbox ownership (the primary flow ignores it),
 * so an attacker reserving a victim's mailbox cannot capture the victim's
 * login into the attacker's account.
 */
import { createHash } from "crypto";
import {
  FieldValue,
  type Firestore,
  type Timestamp,
  type Transaction,
} from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";

export const STUDENT_EMAIL_BINDINGS_COLLECTION = "studentEmailBindings";

export type StudentEmailBindingStatus = "pending" | "confirmed";

export type StudentEmailBindingClaimRejection =
  | "bound_to_other_account"
  | "reserved_by_other_account"
  | "legacy_account_conflict";

export type StudentEmailBindingClaimDecision =
  | { ok: true; alreadyOwned: boolean }
  | { ok: false; reason: StudentEmailBindingClaimRejection };

function asNonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function toMillis(value: unknown): number | null {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value.getTime();
  }
  if (value && typeof value === "object") {
    const maybe = value as { toMillis?: unknown; toDate?: unknown };
    if (typeof maybe.toMillis === "function") {
      const ms = (maybe.toMillis as () => unknown)();
      return typeof ms === "number" && Number.isFinite(ms) ? ms : null;
    }
    if (typeof maybe.toDate === "function") {
      const date = (maybe.toDate as () => unknown)();
      return date instanceof Date && !Number.isNaN(date.getTime())
        ? date.getTime()
        : null;
    }
  }
  return null;
}

/** The ONE normalization every binding reader/writer uses. */
export function normalizeStudentEmailForBinding(email: string): string {
  return email.trim().toLowerCase();
}

/** Binding document id: sha256 hex of the normalized mailbox (never raw PII). */
export function studentEmailBindingId(email: string): string {
  return createHash("sha256")
    .update(normalizeStudentEmailForBinding(email), "utf8")
    .digest("hex");
}

/** Missing `status` = binding written before reservations existed = confirmed. */
export function isConfirmedStudentEmailBinding(
  data: Record<string, unknown> | null | undefined
): boolean {
  return !!data && data.status !== "pending";
}

export function buildStudentEmailBindingDoc(params: {
  appUserId: string;
  emailHash: string;
  status: StudentEmailBindingStatus;
  expiresAt?: Timestamp;
  resetCreatedAt: boolean;
}): Record<string, unknown> {
  if (params.status === "pending" && !params.expiresAt) {
    throw new Error("a pending student email binding requires expiresAt");
  }
  return {
    appUserId: params.appUserId,
    emailHash: params.emailHash,
    status: params.status,
    expiresAt:
      params.status === "pending" ? params.expiresAt : FieldValue.delete(),
    updatedAt: FieldValue.serverTimestamp(),
    ...(params.resetCreatedAt
      ? { createdAt: FieldValue.serverTimestamp() }
      : {}),
  };
}

/**
 * Pure ownership decision for a FIXED target account (unit-tested without
 * Firestore). `boundUserData` is the users doc of the account the binding
 * currently names (only needed when that is a different account);
 * `legacyCandidates` are `users.where("studentEmail","==",email).limit(2)`.
 */
export function decideStudentEmailBindingClaim(params: {
  appUserId: string;
  normalizedEmail: string;
  nowMs: number;
  bindingData: Record<string, unknown> | null;
  boundUserData: Record<string, unknown> | null;
  legacyCandidates: Array<{ id: string; data: Record<string, unknown> }>;
}): StudentEmailBindingClaimDecision {
  const { appUserId, normalizedEmail, bindingData } = params;
  const owner = bindingData ? asNonEmptyString(bindingData.appUserId) : null;

  if (bindingData && owner === appUserId) {
    if (isConfirmedStudentEmailBinding(bindingData)) {
      return { ok: true, alreadyOwned: true };
    }
  } else if (bindingData && owner !== null) {
    if (isConfirmedStudentEmailBinding(bindingData)) {
      return { ok: false, reason: "bound_to_other_account" };
    }
    // Pending reservation held by another account. The hosted page completes
    // without flipping the status, so the users doc is the completion proof.
    const boundEmail = params.boundUserData
      ? asNonEmptyString(params.boundUserData.studentEmail)
      : null;
    if (
      boundEmail &&
      normalizeStudentEmailForBinding(boundEmail) === normalizedEmail
    ) {
      return { ok: false, reason: "bound_to_other_account" };
    }
    const expiresAtMs = toMillis(bindingData.expiresAt);
    if (expiresAtMs !== null && expiresAtMs > params.nowMs) {
      return { ok: false, reason: "reserved_by_other_account" };
    }
    // Expired (or malformed) reservation that was never completed: free.
  }

  // Accounts verified before bindings existed never got a document; the
  // mailbox they hold is still theirs.
  for (const candidate of params.legacyCandidates) {
    if (candidate.id !== appUserId) {
      return { ok: false, reason: "legacy_account_conflict" };
    }
  }
  return { ok: true, alreadyOwned: owner === appUserId };
}

/**
 * Atomically claims the mailbox for `appUserId` inside the caller's
 * transaction (all reads happen before the single binding write, as the
 * Admin SDK requires). Returns the decision instead of throwing so callers map
 * it to their own error contract; nothing is written on rejection.
 *
 *   mode "pending"   — issuance reservation, `expiresAt` required
 *   mode "confirmed" — completion with a Firebase-verified mailbox session
 *
 * A confirmed binding is never downgraded to pending, and an account that
 * already holds the mailbox on its users doc (legacy data) is confirmed —
 * never merely reserved — so its ownership cannot lapse.
 */
export async function claimStudentEmailBinding(
  db: Firestore,
  transaction: Transaction,
  params: {
    appUserId: string;
    email: string;
    mode: StudentEmailBindingStatus;
    expiresAt?: Timestamp;
    nowMs?: number;
  }
): Promise<StudentEmailBindingClaimDecision> {
  const normalizedEmail = normalizeStudentEmailForBinding(params.email);
  const emailHash = studentEmailBindingId(normalizedEmail);
  const bindingRef = db
    .collection(STUDENT_EMAIL_BINDINGS_COLLECTION)
    .doc(emailHash);
  const nowMs = params.nowMs ?? Date.now();

  const bindingSnapshot = await transaction.get(bindingRef);
  const bindingData = bindingSnapshot.exists
    ? ((bindingSnapshot.data() ?? {}) as Record<string, unknown>)
    : null;
  const owner = bindingData ? asNonEmptyString(bindingData.appUserId) : null;
  const confirmedForSelf =
    !!bindingData &&
    owner === params.appUserId &&
    isConfirmedStudentEmailBinding(bindingData);

  let boundUserData: Record<string, unknown> | null = null;
  let legacyCandidates: Array<{ id: string; data: Record<string, unknown> }> =
    [];
  if (!confirmedForSelf) {
    if (owner && owner !== params.appUserId) {
      const boundUserSnapshot = await transaction.get(
        db.collection("users").doc(owner)
      );
      boundUserData = boundUserSnapshot.exists
        ? ((boundUserSnapshot.data() ?? {}) as Record<string, unknown>)
        : null;
    }
    const legacySnapshot = await transaction.get(
      db
        .collection("users")
        .where("studentEmail", "==", normalizedEmail)
        .limit(2)
    );
    legacyCandidates = legacySnapshot.docs.map((doc) => ({
      id: doc.id,
      data: (doc.data() ?? {}) as Record<string, unknown>,
    }));
  }

  const decision = decideStudentEmailBindingClaim({
    appUserId: params.appUserId,
    normalizedEmail,
    nowMs,
    bindingData,
    boundUserData,
    legacyCandidates,
  });
  if (!decision.ok) return decision;
  if (confirmedForSelf) return decision;

  const selfAlreadyHoldsEmail = legacyCandidates.some(
    (candidate) => candidate.id === params.appUserId
  );
  const status: StudentEmailBindingStatus =
    params.mode === "confirmed" || selfAlreadyHoldsEmail
      ? "confirmed"
      : "pending";
  transaction.set(
    bindingRef,
    buildStudentEmailBindingDoc({
      appUserId: params.appUserId,
      emailHash,
      status,
      expiresAt: params.expiresAt,
      resetCreatedAt: owner !== params.appUserId,
    }),
    { merge: true }
  );
  return decision;
}

export function studentEmailBindingClaimError(
  reason: StudentEmailBindingClaimRejection
): HttpsError {
  switch (reason) {
    case "reserved_by_other_account":
      return new HttpsError(
        "already-exists",
        "다른 계정에서 이 연세 이메일로 인증을 진행 중이에요. 잠시 후 다시 시도해주세요.",
        { detail: reason }
      );
    case "bound_to_other_account":
    case "legacy_account_conflict":
      return new HttpsError(
        "already-exists",
        "이미 다른 계정에 인증된 연세 이메일이에요.",
        { detail: reason }
      );
  }
}
