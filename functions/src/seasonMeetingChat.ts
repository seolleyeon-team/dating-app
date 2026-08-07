import { HttpsError } from "firebase-functions/v2/https";

export const SEASON_MEETING_ROOM_TYPE = "season_meeting_group";
export const SEASON_MEETING_ROOM_KIND = "group";
export const SEASON_MEETING_EVENT_TYPE = "season_meeting";

const SEASON_MEETING_TEAM_SIZE = 3;
const SEASON_MEETING_PARTICIPANT_COUNT = 6;
const SEASON_MEETING_CHAT_WELCOME_MESSAGE =
  "3:3 시즌 미팅 채팅방이 열렸어요.";

type UnknownRecord = Record<string, unknown>;

export type SeasonMeetingChatParticipants = {
  participantIds: string[];
  participantInfo: UnknownRecord;
};

export type SeasonMeetingChatPlan = SeasonMeetingChatParticipants & {
  roomId: string;
  roomPayload: UnknownRecord;
};

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function readStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(asString).filter((value) => value.length > 0);
}

function dedupeSorted(values: string[]): string[] {
  return [...new Set(values.map((value) => value.trim()).filter(Boolean))].sort();
}

function fail(message: string): never {
  throw new HttpsError("failed-precondition", message);
}

function readSnapshotMembers(snapshot: unknown): UnknownRecord[] {
  if (!isRecord(snapshot) || !Array.isArray(snapshot.membersSnapshot)) {
    return [];
  }
  return snapshot.membersSnapshot.filter(isRecord);
}

function buildParticipantInfo(
  snapshots: UnknownRecord[],
  participantIds: string[],
): UnknownRecord {
  const info: UnknownRecord = {};
  const seen = new Set<string>();

  for (const member of snapshots) {
    const uid = asString(member.uid);
    if (!uid || seen.has(uid)) continue;
    seen.add(uid);
    if (!participantIds.includes(uid)) continue;

    info[uid] = {
      nickname: asString(member.displayName) || uid,
      avatarUrl: asString(member.photoUrl),
      universityId: asString(member.universityId) || null,
      universityName: asString(member.universityName) || null,
    };
  }

  if (Object.keys(info).length !== participantIds.length) {
    fail("season_meeting_participant_profile_missing");
  }
  return info;
}

export function seasonMeetingChatRoomId(matchId: string): string {
  const normalized = asString(matchId);
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(normalized)) {
    throw new HttpsError("invalid-argument", "matchId is invalid.");
  }
  return `season_${normalized}`;
}

/**
 * Resolves the server-written match contract into exactly six participants.
 * The client never supplies this list: it comes from the accepted request/match
 * document created by the callable transaction.
 */
export function resolveSeasonMeetingChatParticipants(
  matchData: UnknownRecord,
): SeasonMeetingChatParticipants {
  const leftMemberIds = readStringList(matchData.leftMemberUids);
  const rightMemberIds = readStringList(matchData.rightMemberUids);
  const participantIds = readStringList(matchData.participantUids);

  if (
    leftMemberIds.length !== SEASON_MEETING_TEAM_SIZE ||
    rightMemberIds.length !== SEASON_MEETING_TEAM_SIZE
  ) {
    fail("season_meeting_team_member_count_invalid");
  }

  const teamMembers = [...leftMemberIds, ...rightMemberIds];
  const uniqueTeamMembers = dedupeSorted(teamMembers);
  if (uniqueTeamMembers.length !== SEASON_MEETING_PARTICIPANT_COUNT) {
    fail("season_meeting_participants_not_unique");
  }

  const uniqueMatchParticipants = dedupeSorted(participantIds);
  if (
    uniqueMatchParticipants.length !== SEASON_MEETING_PARTICIPANT_COUNT ||
    uniqueMatchParticipants.join("|") !== uniqueTeamMembers.join("|")
  ) {
    fail("season_meeting_participant_source_mismatch");
  }

  const snapshots = [
    ...readSnapshotMembers(matchData.leftTeamSnapshot),
    ...readSnapshotMembers(matchData.rightTeamSnapshot),
  ];
  const participantInfo = buildParticipantInfo(
    snapshots,
    uniqueMatchParticipants,
  );

  return {
    participantIds: uniqueMatchParticipants,
    participantInfo,
  };
}

export function buildSeasonMeetingChatPlan(params: {
  matchId: string;
  matchData: UnknownRecord;
}): SeasonMeetingChatPlan {
  const roomId = seasonMeetingChatRoomId(params.matchId);
  const participants = resolveSeasonMeetingChatParticipants(params.matchData);
  const roomPayload: UnknownRecord = {
    roomId,
    type: SEASON_MEETING_ROOM_KIND,
    roomType: SEASON_MEETING_ROOM_TYPE,
    eventType: SEASON_MEETING_EVENT_TYPE,
    eventThreeVsThreeMatchId: params.matchId,
    matchId: params.matchId,
    participantIds: participants.participantIds,
    participantInfo: participants.participantInfo,
    status: "active",
    writable: true,
    lastMessage: SEASON_MEETING_CHAT_WELCOME_MESSAGE,
    lastMessageAt: null,
    createdAt: null,
    updatedAt: null,
  };

  return {
    roomId,
    ...participants,
    roomPayload,
  };
}

export function assertExistingSeasonMeetingChatRoom(params: {
  roomData: UnknownRecord;
  matchId: string;
  participantIds: string[];
}): void {
  const roomData = params.roomData;
  if (asString(roomData.roomType) !== SEASON_MEETING_ROOM_TYPE) {
    fail("season_meeting_chat_room_type_conflict");
  }
  if (asString(roomData.type) !== SEASON_MEETING_ROOM_KIND) {
    fail("season_meeting_chat_room_kind_conflict");
  }
  if (asString(roomData.eventType) !== SEASON_MEETING_EVENT_TYPE) {
    fail("season_meeting_chat_event_type_conflict");
  }
  if (asString(roomData.eventThreeVsThreeMatchId) !== params.matchId) {
    fail("season_meeting_chat_match_link_conflict");
  }
  if (asString(roomData.status) !== "active" || roomData.writable !== true) {
    fail("season_meeting_chat_room_state_conflict");
  }

  const actualParticipantIds = dedupeSorted(
    readStringList(roomData.participantIds),
  );
  const expectedParticipantIds = dedupeSorted(params.participantIds);
  if (actualParticipantIds.join("|") !== expectedParticipantIds.join("|")) {
    fail("season_meeting_chat_participant_conflict");
  }
  const participantInfo = isRecord(roomData.participantInfo)
    ? roomData.participantInfo
    : null;
  if (
    !participantInfo ||
    expectedParticipantIds.some((participantId) => !isRecord(participantInfo[participantId]))
  ) {
    fail("season_meeting_chat_profile_conflict");
  }
}

export function seasonMeetingChatWelcomeMessage(): string {
  return SEASON_MEETING_CHAT_WELCOME_MESSAGE;
}
