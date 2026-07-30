/**
 * 3:3 미팅 아이스브레이킹 룰렛 — 진입 권한 서버 검증
 * 경로: functions/src/meetingIcebreaker/verify.ts
 *
 * 알림 payload의 meetingId만 믿고 룰렛을 열지 않는다.
 * 매번 원본 문서(blindMeetings / chat_rooms 약속)를 다시 읽어
 *   - 현재 사용자가 그 미팅의 참가자인지
 *   - 시작 안전도장이 완료됐는지
 *   - 종료 안전도장이 아직 아닌지
 *   - 미팅이 진행 중인지
 * 를 확인한다.
 */

import { BLIND_MEETING_COLLECTIONS } from "../blindMeeting/types";
import {
  classifySeasonMeetingRoom,
  isBlindMeetingParticipantBlocked,
  isBlindMeetingStatusActive,
  isBlindMeetingStatusTerminal,
  isSeasonMeetingPromiseActive,
  isSeasonMeetingPromiseTerminal,
  readPromiseSafetyStampUserIds,
} from "./eligibility";
import {
  isAlcoholFreeCopyForced,
  isBombPassEnabled,
  isRouletteEnabled,
} from "./policy";
import {
  db,
  loadMeetingIcebreakerPolicy,
  loadPromptParticipant,
  loadSession,
  resolveSeasonMeetingRefs,
  type MeetingIcebreakerSessionDoc,
} from "./store";
import {
  BLIND_TASTE_MEETING_TYPE,
  SEASON_MEETING_TYPE,
  asStr,
  asStrArray,
  buildMeetingIcebreakerSessionId,
  isMeetingIcebreakerMeetingType,
  type MeetingIcebreakerEntryDecision,
  type MeetingIcebreakerMeetingType,
} from "./types";

export type MeetingIcebreakerEntry = {
  decision: MeetingIcebreakerEntryDecision;
  allowed: boolean;
  sessionId: string | null;
  meetingId: string | null;
  meetingType: MeetingIcebreakerMeetingType | null;
  /** 음주 벌칙 칸을 비음주 문구로 대체해야 하는지 */
  alcoholFreeCopy: boolean;
  optedOut: boolean;
  bombPassEnabled: boolean;
};

function denied(
  decision: MeetingIcebreakerEntryDecision,
  base?: Partial<MeetingIcebreakerEntry>
): MeetingIcebreakerEntry {
  return {
    decision,
    allowed: false,
    sessionId: base?.sessionId ?? null,
    meetingId: base?.meetingId ?? null,
    meetingType: base?.meetingType ?? null,
    alcoholFreeCopy: base?.alcoholFreeCopy ?? false,
    optedOut: base?.optedOut ?? false,
    bombPassEnabled: base?.bombPassEnabled ?? false,
  };
}

/** sessionId를 못 받았을 때 meetingId + meetingType으로 복원한다. */
export function resolveSessionId(params: {
  sessionId?: string | null;
  meetingId?: string | null;
  meetingType?: string | null;
}): string | null {
  const sessionId = asStr(params.sessionId, "").trim();
  if (sessionId.length > 0) return sessionId;

  const meetingId = asStr(params.meetingId, "").trim();
  if (meetingId.length === 0) return null;
  const meetingType = params.meetingType;
  if (!isMeetingIcebreakerMeetingType(meetingType)) return null;
  return buildMeetingIcebreakerSessionId(meetingType, meetingId);
}

async function verifyBlindMeeting(
  uid: string,
  session: MeetingIcebreakerSessionDoc
): Promise<MeetingIcebreakerEntryDecision> {
  const meetingSnap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(session.meetingId)
    .get();
  if (!meetingSnap.exists) return "not_found";

  const meeting = meetingSnap.data() ?? {};
  if (!asStrArray(meeting.participantIds).includes(uid)) {
    return "not_participant";
  }

  const serverStatus = asStr(meeting.serverStatus, "");
  if (serverStatus === "cancelled") return "meeting_cancelled";
  if (isBlindMeetingStatusTerminal(serverStatus)) return "meeting_ended";
  if (!isBlindMeetingStatusActive(serverStatus)) return "not_started";

  const participantSnap = await meetingSnap.ref
    .collection(BLIND_MEETING_COLLECTIONS.participants)
    .doc(uid)
    .get();
  if (!participantSnap.exists) return "not_participant";

  const participant = participantSnap.data() ?? {};
  if (isBlindMeetingParticipantBlocked(participant.serverStatus)) {
    return "not_participant";
  }
  if (participant.checkOutStatus === "completed") return "meeting_ended";
  if (participant.checkInStatus !== "completed") return "not_started";

  return "allowed";
}

async function verifySeasonMeeting(
  uid: string,
  session: MeetingIcebreakerSessionDoc
): Promise<MeetingIcebreakerEntryDecision> {
  const { roomId, promiseId } = resolveSeasonMeetingRefs(session);
  if (roomId == null || roomId.length === 0) return "not_found";

  const roomRef = db().collection("chat_rooms").doc(roomId);
  const roomSnap = await roomRef.get();
  if (!roomSnap.exists) return "not_found";

  const classification = classifySeasonMeetingRoom(roomSnap.data());
  if (!classification.eligible) return "not_participant";
  if (!classification.participantIds.includes(uid)) return "not_participant";

  const promiseSnap = await roomRef.collection("promises").doc(promiseId).get();
  if (!promiseSnap.exists) return "not_found";

  const promise = promiseSnap.data() ?? {};
  if (isSeasonMeetingPromiseTerminal(promise)) return "meeting_ended";
  if (!isSeasonMeetingPromiseActive(promise)) return "not_started";

  if (readPromiseSafetyStampUserIds(promise, "goodbye").includes(uid)) {
    return "meeting_ended";
  }
  if (!readPromiseSafetyStampUserIds(promise, "meetup").includes(uid)) {
    return "not_started";
  }

  return "allowed";
}

/**
 * 룰렛을 열어도 되는지 판정한다.
 *
 * PII를 반환하지 않는다. 실패 이유는 UI 문구를 고르는 데만 쓰인다.
 */
export async function verifyMeetingIcebreakerEntry(params: {
  uid: string;
  sessionId?: string | null;
  meetingId?: string | null;
  meetingType?: string | null;
}): Promise<MeetingIcebreakerEntry> {
  if (params.uid.length === 0) return denied("unauthenticated");

  const sessionId = resolveSessionId(params);
  if (sessionId == null) return denied("not_found");

  const policy = await loadMeetingIcebreakerPolicy();
  const session = await loadSession(sessionId);
  if (session == null) {
    return denied("not_found", { sessionId });
  }

  const base: Partial<MeetingIcebreakerEntry> = {
    sessionId,
    meetingId: session.meetingId,
    meetingType: session.meetingType,
    alcoholFreeCopy: session.isAlcoholFree || isAlcoholFreeCopyForced(policy),
    bombPassEnabled: isBombPassEnabled(policy),
  };

  if (!isRouletteEnabled(policy)) {
    return denied("feature_disabled", base);
  }

  const participant = await loadPromptParticipant(sessionId, params.uid);
  base.optedOut = participant?.optedOut === true;

  const decision =
    session.meetingType === BLIND_TASTE_MEETING_TYPE
      ? await verifyBlindMeeting(params.uid, session)
      : session.meetingType === SEASON_MEETING_TYPE
        ? await verifySeasonMeeting(params.uid, session)
        : "not_found";

  if (decision !== "allowed") {
    return denied(decision, base);
  }

  return {
    decision: "allowed",
    allowed: true,
    sessionId,
    meetingId: session.meetingId,
    meetingType: session.meetingType,
    alcoholFreeCopy: base.alcoholFreeCopy === true,
    optedOut: base.optedOut === true,
    bombPassEnabled: base.bombPassEnabled === true,
  };
}


