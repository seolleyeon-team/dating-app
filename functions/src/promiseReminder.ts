export const PROMISE_REMINDER_QUEUE = "dispatchPromiseReminder";
export const PROMISE_REMINDER_QUEUE_PATH =
  "locations/asia-northeast3/functions/dispatchPromiseReminder";

export type PromiseReminderTaskPayload = {
  roomId: string;
  promiseId: string;
  taskToken: string;
  scheduledForMs: number;
};

export function shouldSchedulePromiseReminderTransition(params: {
  beforeData: Record<string, unknown> | null | undefined;
  afterData: Record<string, unknown> | null | undefined;
  scheduledForMs: number;
}): boolean {
  const after = params.afterData;
  if (!after || String(after.status ?? "").trim().toLowerCase() !== "confirmed") {
    return false;
  }

  const existingScheduledForMs =
    typeof after.exactReminderScheduledForMs === "number"
      ? after.exactReminderScheduledForMs
      : null;
  const existingTaskToken =
    typeof after.exactReminderTaskToken === "string"
      ? after.exactReminderTaskToken.trim()
      : "";
  if (
    existingScheduledForMs === params.scheduledForMs &&
    existingTaskToken.length > 0
  ) {
    return false;
  }

  const before = params.beforeData;
  if (!before) return true;
  if (String(before.status ?? "").trim().toLowerCase() !== "confirmed") {
    return true;
  }
  return existingScheduledForMs !== params.scheduledForMs;
}

export function buildUpcomingPromiseReminderTitle(place: string | null): string {
  const trimmedPlace = place?.trim() ?? "";
  return trimmedPlace.length > 0
    ? `1시간 뒤 ${trimmedPlace}에서 약속이 있어요!`
    : "1시간 뒤 약속이 있어요!";
}

export function buildReminderScheduledForMs(dateTimeMs: number): number {
  return dateTimeMs - 60 * 60 * 1000;
}
