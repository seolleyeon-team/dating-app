/**
 * NEW-24 — one server-side account-state policy for every callable.
 *
 * The state of an account lives on `users/{uid}` and is written only by the
 * Admin SDK (firestore.rules keeps every field below out of the client
 * allowlists):
 *
 *   suspended  decideCommunityReport("suspend"): status "suspended",
 *              loginDisabled true, isActive false,
 *              moderationActionType "indefinite_suspension"
 *              (restoreCommunityAccount reverses it)
 *   banned     decideCommunityReport("ban"): status "banned", loginDisabled
 *              true, isActive false, moderationActionType "permanent_ban"
 *              (restoreCommunityAccount refuses to lift it)
 *   withdrawn  account deletion lock (avatarCleanup lockAccountForDeletion):
 *              status "deleting", isWithdrawn true, loginDisabled true,
 *              canRejoin false — the document is deleted at the end of the
 *              pipeline
 *   inactive   loginDisabled / isActive:false with no status above (Play
 *              review fixtures, which can never sign in), plus the legacy
 *              flags other modules still read (isDeleted, isSuspended,
 *              isBanned, accountStatus, status "blocked" / "deleted" /
 *              "restricted_rejoin")
 *
 * Firebase Auth is disabled and refresh tokens are revoked on a moderation
 * decision, but an ID token issued before it stays valid for up to an hour.
 * The state is therefore read from Firestore on every call and never taken
 * from the token.
 *
 * Which callable applies the gate, and which one is deliberately exempt, is
 * declared per export in callableAccountStatePolicy.ts and enforced by
 * callableAccountStatePolicy.test.ts.
 */
import type { Firestore } from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";

export type AccountState =
  | "active"
  | "suspended"
  | "banned"
  | "withdrawn"
  | "inactive";

const BANNED_STATUSES = new Set(["banned"]);
const SUSPENDED_STATUSES = new Set(["suspended", "blocked"]);
const WITHDRAWN_STATUSES = new Set(["withdrawn", "deleting", "deleted"]);
const INACTIVE_STATUSES = new Set(["restricted_rejoin", "disabled", "inactive"]);

function normalizedStatus(value: unknown): string {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

/**
 * Classifies the stored account state. A missing document is not a state:
 * callers decide what an absent `users/{uid}` means for them.
 */
export function classifyAccountState(
  data: Record<string, unknown> | null | undefined
): AccountState {
  if (!data) return "active";
  // `accountStatus` has no writer in the current source; it is honoured as an
  // alias because several readers (push, avatar replay, recommendations) do.
  const statuses = [
    normalizedStatus(data.status),
    normalizedStatus(data.accountStatus),
  ];
  const hasStatus = (set: Set<string>) => statuses.some((s) => set.has(s));

  if (hasStatus(BANNED_STATUSES) || data.isBanned === true) return "banned";
  if (hasStatus(SUSPENDED_STATUSES) || data.isSuspended === true) {
    return "suspended";
  }
  if (
    hasStatus(WITHDRAWN_STATUSES) ||
    data.isWithdrawn === true ||
    data.isDeleted === true
  ) {
    return "withdrawn";
  }
  if (
    hasStatus(INACTIVE_STATUSES) ||
    data.loginDisabled === true ||
    data.isActive === false
  ) {
    return "inactive";
  }
  return "active";
}

export function isActiveAccountData(
  data: Record<string, unknown> | null | undefined
): boolean {
  return classifyAccountState(data) === "active";
}

/**
 * AUD-22 — the part of the state every "should OTHER users still see, match
 * with or be notified about this account" predicate must agree on: a
 * moderation sanction (suspended / banned) or a deletion in progress
 * (withdrawn).
 *
 * It deliberately does NOT include "inactive": Play review fixtures carry
 * `loginDisabled: true` so they can never sign in, yet they must stay visible
 * as candidates inside the review partition. A caller-side gate uses
 * assertActiveAccountState; a visibility predicate adds this to its own
 * checks.
 */
export function isRestrictedAccountData(
  data: Record<string, unknown> | null | undefined
): boolean {
  const state = classifyAccountState(data);
  return state === "suspended" || state === "banned" || state === "withdrawn";
}

/**
 * The refusal every gated callable returns. The code stays
 * `permission-denied` (the contract recovered in NEW-20); `details.detail`
 * tells the states apart without exposing moderation reasons.
 */
export function accountStateError(
  state: Exclude<AccountState, "active">
): HttpsError {
  // One message for every state: it is the string the NEW-20 contract pinned
  // (reportAndBlock.emulator-test N9, including a withdrawn status).
  return new HttpsError("permission-denied", "이용이 정지된 계정이에요.", {
    detail: `account_${state}`,
  });
}

export function assertActiveAccountState(
  data: Record<string, unknown> | null | undefined
): void {
  const state = classifyAccountState(data);
  if (state !== "active") throw accountStateError(state);
}

/**
 * Gate for callables that must not require student verification (verification
 * recovery, re-consent) but must still refuse a suspended, banned, withdrawn
 * or inactive account. Reads `users/{uid}` on every call.
 */
export async function requireActiveAccount(
  firestore: Firestore,
  uid: string
): Promise<Record<string, unknown>> {
  const snapshot = await firestore.collection("users").doc(uid).get();
  if (!snapshot.exists) {
    throw new HttpsError("failed-precondition", "가입 정보를 찾을 수 없어요.");
  }
  const data = (snapshot.data() ?? {}) as Record<string, unknown>;
  assertActiveAccountState(data);
  return data;
}
