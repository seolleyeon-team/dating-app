export const PROMISE_REMINDER_QUEUE = "dispatchPromiseReminder";
export const PROMISE_REMINDER_QUEUE_PATH =
  "locations/asia-northeast3/functions/dispatchPromiseReminder";

export type PromiseReminderTaskPayload = {
  roomId: string;
  promiseId: string;
  taskToken: string;
  scheduledForMs: number;
};

export function buildUpcomingPromiseReminderTitle(place: string | null): string {
  const trimmedPlace = place?.trim() ?? "";
  return trimmedPlace.length > 0
    ? `1시간 뒤 ${trimmedPlace}에서 약속이 있어요!`
    : "1시간 뒤 약속이 있어요!";
}

export function buildReminderScheduledForMs(dateTimeMs: number): number {
  return dateTimeMs - 60 * 60 * 1000;
}
