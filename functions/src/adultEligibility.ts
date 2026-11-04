/**
 * P1-7 — server-authoritative adult-verification eligibility.
 *
 * `users/{uid}.adultVerified` and `realNameVerified` are written only by
 * `verifyAdultIdentityAfterLogin` (Admin SDK) after PortOne / KG Inicis
 * returned a VERIFIED identity whose Korean year age is at least
 * MINIMUM_SERVICE_AGE (20); the Firestore rules keep both fields out of every
 * client-writable allowlist. They are therefore the trusted evidence.
 *
 * Before this module the flags were consulted only by the Flutter route
 * guard: a modified client could skip the verification screen and still like,
 * match, ask and chat. Every dating entry point now re-checks here.
 *
 * The Play-review data plane (dataPartition "play_review") is exempt: its
 * fixtures cannot sign in and never meet production accounts.
 */
import { HttpsError } from "firebase-functions/v2/https";

import { dataPartitionOf } from "./playReviewAccess";

export const ADULT_VERIFICATION_REQUIRED_MESSAGE =
  "본인인증(성인 인증)을 완료한 뒤 이용할 수 있어요.";

/** Trusted server-written evidence only. */
export function isAdultVerifiedUserData(
  data: Record<string, unknown> | null | undefined
): boolean {
  return data?.adultVerified === true && data?.realNameVerified === true;
}

/**
 * Whether a production account may use dating features. Review-partition
 * accounts are eligible by construction (isolated data plane).
 */
export function isEligibleForDatingFeatures(
  data: Record<string, unknown> | null | undefined
): boolean {
  if (dataPartitionOf(data ?? {}) === "play_review") return true;
  return isAdultVerifiedUserData(data);
}

export function assertEligibleForDatingFeatures(
  data: Record<string, unknown> | null | undefined
): void {
  if (!isEligibleForDatingFeatures(data)) {
    throw new HttpsError("failed-precondition", ADULT_VERIFICATION_REQUIRED_MESSAGE);
  }
}
