/**
 * AUD-22 — the one KST calendar-day rule.
 *
 * Korea Standard Time is UTC+9 with no daylight saving, so the calendar day
 * of an instant is that of `instant + 9 h` read in UTC. Four modules carried
 * their own copy of this arithmetic (index.ts, playReviewAccess.ts,
 * profileVisibility.ts, recommendationRefresh.ts); they now delegate here.
 * The client derives the same key with `toUtc().add(Duration(hours: 9))`
 * (ai_recommendation_service.dart, rec_event_service.dart), never from the
 * device time zone.
 *
 * Never use `getFullYear()` / `getDate()` or `toLocale*` for a day key: the
 * result would depend on the process time zone.
 */
export const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

/** `YYYY-MM-DD` of the KST calendar day containing `instant`. */
export function kstDateKeyDashed(instant: Date = new Date()): string {
  return new Date(instant.getTime() + KST_OFFSET_MS).toISOString().slice(0, 10);
}

/** `YYYYMMDD` of the KST calendar day containing `instant`. */
export function kstDateKeyCompact(instant: Date = new Date()): string {
  return kstDateKeyDashed(instant).replace(/-/g, "");
}
