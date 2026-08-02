/**
 * 3:3 미팅 아이스브레이킹 룰렛 — 조용한 반복 알림
 * 경로: functions/src/meetingIcebreaker/notifications.ts
 *
 * 조용한 알림은 data-only silent push가 아니다.
 * 알림 센터에는 문구가 보이지만 소리·진동·강한 heads-up이 없어야 한다.
 * (functions/src/shared/notify.ts 의 quiet delivery style 참고)
 *
 * payload에는 미팅 장소, 상대방 UID 목록 같은 민감 정보를 넣지 않는다.
 */

import {
  buildNotificationIdempotencyKey,
  createInAppNotification,
  sendPushOnce,
} from "../shared/notify";
import type { MeetingIcebreakerMeetingType } from "./types";

export const MEETING_ICEBREAKER_NOTIFICATION_TYPE =
  "meeting_icebreaker_roulette";
export const MEETING_ICEBREAKER_DEEPLINK_TYPE = "meeting_icebreaker_roulette";

export const MEETING_ICEBREAKER_PROMPT_TITLE = "설레연 미팅 도우미";
export const MEETING_ICEBREAKER_PROMPT_BODY = "미팅에서 어색할 때 눌러보세요!";

/**
 * 알림 idempotency key.
 *
 * 같은 (세션, 참가자, 순번) 조합이면 항상 같은 key가 되므로
 * Cloud Function 재시도나 task 중복 실행에도 한 번만 발송된다.
 */
export function buildPromptNotificationId(
  sessionId: string,
  uid: string,
  sequence: number
): string {
  return buildNotificationIdempotencyKey([
    "meeting_icebreaker",
    sessionId,
    uid,
    sequence,
  ]);
}

export function buildPromptPushIdempotencyKey(
  sessionId: string,
  uid: string,
  sequence: number
): string {
  return buildNotificationIdempotencyKey([
    "meeting_icebreaker_push",
    sessionId,
    uid,
    sequence,
  ]);
}

/**
 * 같은 미팅의 알림이 알림 센터에 쌓이지 않도록 교체 키를 쓴다.
 *
 * Android는 notification tag + collapseKey, iOS는 apns-collapse-id로 동작한다.
 */
export function buildPromptCollapseKey(sessionId: string): string {
  return `meeting_icebreaker_${sessionId}`;
}

export type MeetingIcebreakerPromptResult = {
  pushDispatched: boolean;
  inAppCreated: boolean;
};

/**
 * 조용한 반복 알림 1회 발송.
 *
 * 인앱 알림 목록은 세션당 1회(첫 알림)만 만든다.
 * 15분마다 인앱 알림을 쌓으면 목록이 같은 문구로 도배되기 때문이다.
 * OS 알림 센터에는 매번 표시되지만 collapse key로 항상 1건으로 유지된다.
 */
export async function sendMeetingIcebreakerPrompt(params: {
  sessionId: string;
  uid: string;
  meetingId: string;
  meetingType: MeetingIcebreakerMeetingType;
  sequence: number;
}): Promise<MeetingIcebreakerPromptResult> {
  const notificationId = buildPromptNotificationId(
    params.sessionId,
    params.uid,
    params.sequence
  );

  let inAppCreated = false;
  if (params.sequence <= 1) {
    inAppCreated = await createInAppNotification(
      params.uid,
      {
        type: MEETING_ICEBREAKER_NOTIFICATION_TYPE,
        title: MEETING_ICEBREAKER_PROMPT_TITLE,
        body: MEETING_ICEBREAKER_PROMPT_BODY,
        deeplinkType: MEETING_ICEBREAKER_DEEPLINK_TYPE,
        deeplinkId: params.meetingId,
        meetingId: params.meetingId,
        sessionId: params.sessionId,
      },
      notificationId
    );
  }

  const pushDispatched = await sendPushOnce(
    [params.uid],
    {
      title: MEETING_ICEBREAKER_PROMPT_TITLE,
      body: MEETING_ICEBREAKER_PROMPT_BODY,
      style: "quiet",
      collapseKey: buildPromptCollapseKey(params.sessionId),
      data: {
        type: MEETING_ICEBREAKER_NOTIFICATION_TYPE,
        deeplinkType: MEETING_ICEBREAKER_DEEPLINK_TYPE,
        deeplinkId: params.meetingId,
        meetingId: params.meetingId,
        meetingType: params.meetingType,
        sessionId: params.sessionId,
        notificationSequence: String(params.sequence),
        notificationId,
      },
    },
    buildPromptPushIdempotencyKey(
      params.sessionId,
      params.uid,
      params.sequence
    )
  );

  return { pushDispatched, inAppCreated };
}
