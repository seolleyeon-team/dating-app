/**
 * 3:3 블라인드 취향 미팅 — 알림
 * 경로: functions/src/blindMeeting/notifications.ts
 *
 * 모든 알림은 idempotency key를 사용해 중복 발송되지 않는다.
 * 실사용자 대상 테스트 푸시는 발송하지 않는다.
 */

import {
  buildNotificationIdempotencyKey,
  createInAppNotification,
  sendPushOnce,
  type InAppNotificationType,
} from "../shared/notify";

export type BlindMeetingNotificationKind =
  | "party_invite"
  | "party_joined"
  | "party_locked"
  | "party_member_completed"
  | "party_ready"
  | "matched"
  | "acceptance_request"
  | "deposit_request"
  | "confirmed"
  | "chat_created"
  | "schedule_vote"
  | "schedule_confirmed"
  | "attendance_24h"
  | "attendance_3h"
  | "replacement_offer"
  | "replacement_confirmed"
  | "checkin"
  | "checkout"
  | "follow_up"
  | "follow_up_reminder"
  | "mutual_match"
  | "cancelled"
  | "refunded";

type NotificationTemplate = {
  type: InAppNotificationType;
  title: string;
  body: string;
  deeplinkType:
    | "blind_meeting_party"
    | "blind_meeting"
    | "blind_meeting_follow_up"
    | "chat";
};

const TEMPLATES: Record<BlindMeetingNotificationKind, NotificationTemplate> = {
  party_invite: {
    type: "blind_meeting_party_invite",
    title: "친구가 취향 미팅에 초대했어요",
    body: "친구와 같은 편으로 블라인드 취향 미팅에 참가해보세요.",
    deeplinkType: "blind_meeting_party",
  },
  party_joined: {
    type: "blind_meeting_party_joined",
    title: "친구가 팀에 합류했어요",
    body: "팀 구성 화면에서 함께 참가할 멤버를 확인해보세요.",
    deeplinkType: "blind_meeting_party",
  },
  party_locked: {
    type: "blind_meeting_party_locked",
    title: "취향 미팅 팀이 확정됐어요",
    body: "이제 각자 미팅 DNA와 가능한 날짜를 작성해주세요.",
    deeplinkType: "blind_meeting_party",
  },
  party_member_completed: {
    type: "blind_meeting_party_member_completed",
    title: "친구가 날짜 신청을 완료했어요",
    body: "팀 전원이 완료하면 같은 미팅으로 함께 매칭을 시작해요.",
    deeplinkType: "blind_meeting_party",
  },
  party_ready: {
    type: "blind_meeting_party_ready",
    title: "우리 팀의 신청이 모두 완료됐어요",
    body: "함께 가능한 날짜로 같은 편 매칭을 시작했어요.",
    deeplinkType: "blind_meeting_party",
  },
  matched: {
    type: "blind_meeting_matched",
    title: "블라인드 취향 미팅 구성 완료",
    body: "취향이 잘 맞을 가능성이 높은 여섯 명을 구성했어요.",
    deeplinkType: "blind_meeting",
  },
  acceptance_request: {
    type: "blind_meeting_acceptance_request",
    title: "참가를 수락해주세요",
    body: "시간과 장소를 확인하고 참가 여부를 알려주세요.",
    deeplinkType: "blind_meeting",
  },
  deposit_request: {
    type: "blind_meeting_deposit_request",
    title: "보증금 결제를 완료해주세요",
    body: "정상 참석 후 종료 안전도장까지 완료하면 전액 환급돼요.",
    deeplinkType: "blind_meeting",
  },
  confirmed: {
    type: "blind_meeting_confirmed",
    title: "미팅이 확정됐어요",
    body: "여섯 명 모두 참가가 확정됐어요.",
    deeplinkType: "blind_meeting",
  },
  chat_created: {
    type: "blind_meeting_chat_created",
    title: "단체 채팅방이 열렸어요",
    body: "시간과 장소를 함께 정해보세요.",
    deeplinkType: "chat",
  },
  schedule_vote: {
    type: "blind_meeting_schedule_vote",
    title: "약속 시간을 정해주세요",
    body: "가능한 시간과 장소에 투표해주세요.",
    deeplinkType: "chat",
  },
  schedule_confirmed: {
    type: "blind_meeting_schedule_confirmed",
    title: "약속이 확정됐어요",
    body: "확정된 시간과 장소를 확인해주세요.",
    deeplinkType: "blind_meeting",
  },
  attendance_24h: {
    type: "blind_meeting_attendance_check",
    title: "내일 미팅 참석 확인",
    body: "내일 블라인드 취향 미팅에 참석할 수 있나요?",
    deeplinkType: "blind_meeting",
  },
  attendance_3h: {
    type: "blind_meeting_attendance_check",
    title: "오늘 미팅 참석 확인",
    body: "오늘 미팅 참석 준비는 괜찮으신가요?",
    deeplinkType: "blind_meeting",
  },
  replacement_offer: {
    type: "blind_meeting_replacement_offer",
    title: "대체 참가 제안",
    body: "조건에 맞는 미팅에 빈자리가 생겼어요. 참가하시겠어요?",
    deeplinkType: "blind_meeting",
  },
  replacement_confirmed: {
    type: "blind_meeting_replacement_confirmed",
    title: "대체 참가가 확정됐어요",
    body: "미팅 시간과 장소를 확인해주세요.",
    deeplinkType: "blind_meeting",
  },
  checkin: {
    type: "blind_meeting_checkin",
    title: "도착 안전도장을 찍어주세요",
    body: "장소에 도착하면 안전도장으로 확인해주세요.",
    deeplinkType: "blind_meeting",
  },
  checkout: {
    type: "blind_meeting_checkout",
    title: "종료 안전도장을 찍어주세요",
    body: "미팅이 끝나면 종료 안전도장을 찍어주세요. 보증금 환급 조건이에요.",
    deeplinkType: "blind_meeting",
  },
  follow_up: {
    type: "blind_meeting_follow_up",
    title: "미팅은 즐거우셨나요?",
    body: "다시 대화해보고 싶은 사람이 있다면 조용히 선택해보세요. 서로 선택한 경우에만 1:1 채팅이 열려요.",
    deeplinkType: "blind_meeting_follow_up",
  },
  follow_up_reminder: {
    type: "blind_meeting_follow_up_reminder",
    title: "선택 기간이 곧 끝나요",
    body: "다시 이야기하고 싶은 사람이 있다면 지금 선택해보세요.",
    deeplinkType: "blind_meeting_follow_up",
  },
  mutual_match: {
    type: "blind_meeting_mutual_match",
    title: "서로 다시 대화해보고 싶어 했어요",
    body: "부담 없이 첫 대화를 시작해보세요.",
    deeplinkType: "chat",
  },
  cancelled: {
    type: "blind_meeting_cancelled",
    title: "미팅이 취소됐어요",
    body: "정상 참석 예정이던 분께는 보증금을 환급하고 우선 재매칭을 드려요.",
    deeplinkType: "blind_meeting",
  },
  refunded: {
    type: "blind_meeting_refunded",
    title: "보증금 환급이 완료됐어요",
    body: "환급 내역을 확인해주세요.",
    deeplinkType: "blind_meeting",
  },
};

/**
 * 블라인드 미팅 알림 발송 (인앱 + 푸시, 둘 다 idempotent).
 *
 * [dedupeSuffix]는 같은 종류의 알림을 여러 번 보내야 하는 경우
 * (예: 재알림) 구분자로 사용한다.
 */
export async function notifyBlindMeeting(params: {
  userIds: string[];
  meetingId: string;
  kind: BlindMeetingNotificationKind;
  bodyOverride?: string;
  deeplinkId?: string;
  dedupeSuffix?: string;
  data?: Record<string, string>;
}): Promise<void> {
  const template = TEMPLATES[params.kind];
  const body = params.bodyOverride ?? template.body;
  const deeplinkId = params.deeplinkId ?? params.meetingId;

  for (const userId of params.userIds) {
    if (!userId) continue;
    const notificationId = buildNotificationIdempotencyKey([
      "blind_meeting",
      params.kind,
      params.meetingId,
      userId,
      params.dedupeSuffix,
    ]);
    await createInAppNotification(
      userId,
      {
        type: template.type,
        title: template.title,
        body,
        deeplinkType: template.deeplinkType,
        deeplinkId,
        meetingId: params.meetingId,
      },
      notificationId
    );
  }

  const pushKey = buildNotificationIdempotencyKey([
    "blind_meeting_push",
    params.kind,
    params.meetingId,
    params.userIds.slice().sort().join("-"),
    params.dedupeSuffix,
  ]);

  await sendPushOnce(
    params.userIds,
    {
      title: template.title,
      body,
      data: {
        type: template.type,
        meetingId: params.meetingId,
        deeplinkType: template.deeplinkType,
        deeplinkId,
        ...(params.data ?? {}),
      },
    },
    pushKey
  );
}

/** 친구 파티 단계 알림. 미팅이 만들어지기 전이라 partyId를 링크로 쓴다. */
export async function notifyBlindMeetingParty(params: {
  userIds: string[];
  partyId: string;
  kind:
    | "party_invite"
    | "party_joined"
    | "party_locked"
    | "party_member_completed"
    | "party_ready";
  dedupeSuffix?: string;
}): Promise<void> {
  const template = TEMPLATES[params.kind];
  for (const userId of params.userIds) {
    if (!userId) continue;
    const notificationId = buildNotificationIdempotencyKey([
      "blind_meeting_party",
      params.kind,
      params.partyId,
      userId,
      params.dedupeSuffix,
    ]);
    await createInAppNotification(
      userId,
      {
        type: template.type,
        title: template.title,
        body: template.body,
        deeplinkType: "blind_meeting_party",
        deeplinkId: params.partyId,
        partyId: params.partyId,
      },
      notificationId
    );
  }
  await sendPushOnce(
    params.userIds,
    {
      title: template.title,
      body: template.body,
      data: {
        type: template.type,
        partyId: params.partyId,
        deeplinkType: "blind_meeting_party",
        deeplinkId: params.partyId,
      },
    },
    buildNotificationIdempotencyKey([
      "blind_meeting_party_push",
      params.kind,
      params.partyId,
      params.userIds.slice().sort().join("-"),
      params.dedupeSuffix,
    ])
  );
}
