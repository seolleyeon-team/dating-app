import type { CallableOptions } from "firebase-functions/v2/https";

/**
 * Every public callable that accepts untrusted clients must require App Check.
 * Without it, createFirebaseCustomToken and friends can be scripted from
 * outside the installed app — the same class of abuse SEC-P0-01 relied on.
 */
export function withAppCheck(
  options: Omit<CallableOptions, "enforceAppCheck"> = {}
): CallableOptions {
  return {
    ...options,
    enforceAppCheck: true,
  };
}
