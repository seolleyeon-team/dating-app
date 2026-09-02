/**
 * Server-authoritative next-day visibility semantics for 1:1 recommendations.
 *
 * A profile can remain a recommendation viewer while being hidden as a
 * candidate.  KST is fixed at UTC+09:00 (Korea has no daylight saving time).
 */

const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

type UserData = Record<string, unknown> | null | undefined;

function validDateKey(value: unknown): string | null {
  return typeof value === "string" && /^\d{8}$/.test(value) ? value : null;
}

export function kstDateKey(now: Date = new Date()): string {
  return new Date(now.getTime() + KST_OFFSET_MS)
    .toISOString()
    .slice(0, 10)
    .replace(/-/g, "");
}

export function nextKstDateKey(now: Date = new Date()): string {
  const kst = new Date(now.getTime() + KST_OFFSET_MS);
  kst.setUTCDate(kst.getUTCDate() + 1);
  return kst.toISOString().slice(0, 10).replace(/-/g, "");
}

/** Resolves the candidate-side setting for a specific recommendation day. */
export function isProfileVisibleForRecommendationDate(
  data: UserData,
  dateKey: string,
): boolean {
  const requestedVisible = data?.profileVisible !== false;
  const effectiveDateKey = validDateKey(data?.profileVisibleEffectiveDateKey);
  if (effectiveDateKey && validDateKey(dateKey) && dateKey < effectiveDateKey) {
    return data?.profileVisibleBeforeEffectiveDate !== false;
  }
  return requestedVisible;
}
