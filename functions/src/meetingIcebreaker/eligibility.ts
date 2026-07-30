/**
 * 3:3 미팅 아이스브레이킹 룰렛 — 적용 대상 판정
 * 경로: functions/src/meetingIcebreaker/eligibility.ts
 *
 * 이 파일의 함수는 모두 순수 함수다. Firestore를 읽지 않으므로
 * "어떤 미팅에 알림을 켜도 되는가"를 테스트로 고정할 수 있다.
 *
 * 기본값은 항상 "적용하지 않음"이다.
 * 일반 이벤트, 1:1 추천, 일반 채팅, 커뮤니티는 어떤 경우에도 통과하지 못한다.
 */

import {
  MEETING_ICEBREAKER_PARTICIPANT_COUNT,
  asStr,
  asStrArray,
  isRecord,
} from "./types";

/**
 * 3:3 시즌 미팅 단체 채팅방으로 인정하는 roomType.
 *
 * 시즌 미팅 단체 채팅방 생성은 아직 저장소에 없다. 값이 생기면 여기에만 추가한다.
 */
export const SEASON_MEETING_ROOM_TYPES = [
  "season_meeting_group",
  "event_season_meeting_group",
  "three_vs_three_group",
];

/** eventTeamMatches / eventTeamMeetingGroups 문서가 쓰는 eventType */
export const SEASON_MEETING_EVENT_TYPES = ["season_meeting"];

/** 단체(3:3) 형태로 인정하는 legacy 채팅방 종류 (`type` 필드) */
export const SEASON_MEETING_GROUP_ROOM_KINDS = [
  "group",
  "three_vs_three",
  "event_team_group",
];

/** 3:3 시즌 미팅 매칭 문서와의 연결을 나타내는 필드 후보 */
export const SEASON_MEETING_MATCH_ID_FIELDS = [
  "threeVsThreeMatchId",
  "seasonMeetingMatchId",
  "eventThreeVsThreeMatchId",
];

/** 블라인드 취향 미팅 채팅방 접두어 (여기서는 처리하지 않는다) */
export const BLIND_MEETING_ROOM_TYPE_PREFIX = "blind_meeting_";

export type SeasonMeetingRoomRejectReason =
  | "missing_room"
  | "blind_meeting_room"
  | "direct_room"
  | "not_season_meeting"
  | "participant_count_mismatch";

export type SeasonMeetingRoomClassification =
  | { eligible: true; participantIds: string[] }
  | { eligible: false; reason: SeasonMeetingRoomRejectReason };

function readRoomType(roomData: Record<string, unknown>): string {
  return asStr(roomData.roomType, "").trim();
}

function readRoomKind(roomData: Record<string, unknown>): string {
  // legacy 방은 `type`, 신규 방은 `roomType`을 쓴다.
  const kind = asStr(roomData.type, "").trim();
  if (kind.length > 0) return kind;
  return readRoomType(roomData);
}

function hasSeasonMeetingMatchLink(roomData: Record<string, unknown>): boolean {
  return SEASON_MEETING_MATCH_ID_FIELDS.some(
    (field) => asStr(roomData[field], "").trim().length > 0
  );
}

/**
 * 채팅방이 3:3 시즌 미팅 단체 채팅방인지 판정한다.
 *
 * 통과 조건 (하나라도 만족 + 인원 6명):
 *   1. roomType이 시즌 미팅 전용 값
 *   2. eventType이 season_meeting이고 단체 방 형태
 *   3. 단체 방 형태이고 3:3 매칭 문서 id가 연결되어 있음
 */
export function classifySeasonMeetingRoom(
  roomDataRaw: unknown
): SeasonMeetingRoomClassification {
  if (!isRecord(roomDataRaw)) {
    return { eligible: false, reason: "missing_room" };
  }
  const roomData = roomDataRaw;

  const roomType = readRoomType(roomData);
  if (roomType.startsWith(BLIND_MEETING_ROOM_TYPE_PREFIX)) {
    // 블라인드 미팅은 blindMeetings 체크인/체크아웃 경로에서 직접 처리한다.
    return { eligible: false, reason: "blind_meeting_room" };
  }

  const roomKind = readRoomKind(roomData);
  if (roomKind === "one_to_one" || roomKind === "direct") {
    return { eligible: false, reason: "direct_room" };
  }

  const isGroupShaped = SEASON_MEETING_GROUP_ROOM_KINDS.includes(roomKind);
  const eventType = asStr(roomData.eventType, "").trim();

  const isSeasonMeetingRoom =
    SEASON_MEETING_ROOM_TYPES.includes(roomType) ||
    (SEASON_MEETING_EVENT_TYPES.includes(eventType) && isGroupShaped) ||
    (isGroupShaped && hasSeasonMeetingMatchLink(roomData));

  if (!isSeasonMeetingRoom) {
    return { eligible: false, reason: "not_season_meeting" };
  }

  const participantIds = asStrArray(roomData.participantIds);
  if (participantIds.length !== MEETING_ICEBREAKER_PARTICIPANT_COUNT) {
    return { eligible: false, reason: "participant_count_mismatch" };
  }

  return { eligible: true, participantIds };
}

// -----------------------------------------------------------------------------
// 약속 문서(안전도장) 읽기
//
// lib/features/chat/services/chat_service.dart 의 저장 형태를 그대로 따른다.
//   safetyStamp.meetupStampedUserIds   (legacy: safetyStamp.stampedUserIds)
//   safetyStamp.goodbyeStampedUserIds
// -----------------------------------------------------------------------------

export type SafetyStampPhase = "meetup" | "goodbye";

export function readPromiseSafetyStampUserIds(
  promiseDataRaw: unknown,
  phase: SafetyStampPhase
): string[] {
  if (!isRecord(promiseDataRaw)) return [];
  const safetyStamp = isRecord(promiseDataRaw.safetyStamp)
    ? promiseDataRaw.safetyStamp
    : {};

  if (phase === "goodbye") {
    return asStrArray(safetyStamp.goodbyeStampedUserIds);
  }

  const meetup = asStrArray(safetyStamp.meetupStampedUserIds);
  if (meetup.length > 0) return meetup;
  // legacy 필드 호환
  return asStrArray(safetyStamp.stampedUserIds);
}

/**
 * 시작 안전도장 이후 알림을 켜도 되는 약속 상태.
 *
 * `confirmed`는 "약속은 확정됐고 일부가 도착해 도장을 찍은 상태"다.
 * 약속 문서의 status는 여섯 명 전원이 찍은 뒤에야 `in_progress`가 되므로,
 * 참가자 개인 기준으로 알림을 켜려면 두 상태를 모두 허용해야 한다.
 * 무한 알림은 종료 도장과 최대 지속 시간(기본 6시간)이 막는다.
 */
export const SEASON_MEETING_ACTIVE_PROMISE_STATUSES = [
  "confirmed",
  "in_progress",
];

/** 알림을 즉시 멈춰야 하는 약속 상태 */
export const SEASON_MEETING_TERMINAL_PROMISE_STATUSES = [
  "completed",
  "cancelled",
  "canceled",
  "expired",
];

export function readPromiseStatus(promiseDataRaw: unknown): string {
  if (!isRecord(promiseDataRaw)) return "";
  return asStr(promiseDataRaw.status, "").trim().toLowerCase();
}

export function isSeasonMeetingPromiseActive(promiseDataRaw: unknown): boolean {
  return SEASON_MEETING_ACTIVE_PROMISE_STATUSES.includes(
    readPromiseStatus(promiseDataRaw)
  );
}

export function isSeasonMeetingPromiseTerminal(
  promiseDataRaw: unknown
): boolean {
  return SEASON_MEETING_TERMINAL_PROMISE_STATUSES.includes(
    readPromiseStatus(promiseDataRaw)
  );
}

// -----------------------------------------------------------------------------
// 블라인드 취향 미팅
// -----------------------------------------------------------------------------

/**
 * 아이스브레이킹 알림을 켜도 되는 블라인드 미팅 상태 (server snake_case).
 *
 * `checkin_open` = 누군가 도착해 도착 도장을 찍은 상태.
 * `in_progress`  = 전원 도착.
 * 둘 다 "장소에 모여 있는" 구간이라 어색함을 풀 수 있는 시점이다.
 */
export const BLIND_MEETING_ACTIVE_STATUSES = ["checkin_open", "in_progress"];

/** 알림을 즉시 멈춰야 하는 블라인드 미팅 상태 */
export const BLIND_MEETING_TERMINAL_STATUSES = [
  "completed",
  "followup_open",
  "read_only",
  "archived",
  "cancelled",
];

/** 반복 알림을 보내면 안 되는 참가자 상태 (server snake_case) */
export const BLIND_MEETING_BLOCKED_PARTICIPANT_STATUSES = [
  "cancelled",
  "cancel_requested",
  "replacement_pending",
  "replaced",
  "no_show",
  "restricted",
];

export function isBlindMeetingStatusActive(status: unknown): boolean {
  return BLIND_MEETING_ACTIVE_STATUSES.includes(asStr(status, "").trim());
}

export function isBlindMeetingStatusTerminal(status: unknown): boolean {
  return BLIND_MEETING_TERMINAL_STATUSES.includes(asStr(status, "").trim());
}

export function isBlindMeetingParticipantBlocked(status: unknown): boolean {
  return BLIND_MEETING_BLOCKED_PARTICIPANT_STATUSES.includes(
    asStr(status, "").trim()
  );
}

/** 탈퇴·정지 계정에는 발송하지 않는다. */
export function isUserBlockedForPrompts(userDataRaw: unknown): boolean {
  if (!isRecord(userDataRaw)) return true;
  return (
    userDataRaw.isWithdrawn === true ||
    userDataRaw.loginDisabled === true ||
    userDataRaw.isSuspended === true ||
    userDataRaw.isBanned === true
  );
}
