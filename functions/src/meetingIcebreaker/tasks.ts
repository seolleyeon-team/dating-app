/**
 * 3:3 미팅 아이스브레이킹 룰렛 — Cloud Tasks 계약
 * 경로: functions/src/meetingIcebreaker/tasks.ts
 *
 * Dart의 Timer.periodic으로는 앱이 종료된 뒤 알림을 보낼 수 없다.
 * 기존 약속 리마인더(functions/src/promiseReminder.ts)와 같은 방식으로
 * Cloud Tasks 체인을 쓰고, 유실된 task는 예약 작업이 다시 채운다.
 */

export const MEETING_ICEBREAKER_QUEUE = "dispatchMeetingIcebreakerPrompt";
export const MEETING_ICEBREAKER_QUEUE_PATH =
  "locations/asia-northeast3/functions/dispatchMeetingIcebreakerPrompt";

export type MeetingIcebreakerPromptTaskPayload = {
  sessionId: string;
  uid: string;
  /**
   * 예약 세대 번호.
   *
   * 알림이 중단되거나 재예약되면 올라간다. 값이 다르면 오래된 task이므로 no-op.
   */
  scheduleVersion: number;
  /** 이 task가 보내려는 알림 순번 (= 직전 promptSequence + 1) */
  promptSequence: number;
  /** 예약된 발송 시각 */
  scheduledForMs: number;
  /** 문서에 저장된 값과 일치해야 실행되는 1회용 토큰 */
  taskToken: string;
};

export function isMeetingIcebreakerPromptTaskPayload(
  value: Partial<MeetingIcebreakerPromptTaskPayload> | undefined
): value is MeetingIcebreakerPromptTaskPayload {
  if (!value) return false;
  return (
    typeof value.sessionId === "string" &&
    value.sessionId.length > 0 &&
    typeof value.uid === "string" &&
    value.uid.length > 0 &&
    typeof value.scheduleVersion === "number" &&
    Number.isFinite(value.scheduleVersion) &&
    typeof value.promptSequence === "number" &&
    Number.isFinite(value.promptSequence) &&
    typeof value.scheduledForMs === "number" &&
    value.scheduledForMs > 0 &&
    typeof value.taskToken === "string" &&
    value.taskToken.length > 0
  );
}
