/**
 * 3:3 미팅 아이스브레이킹 룰렛 — Firestore 접근
 * 경로: functions/src/meetingIcebreaker/store.ts
 *
 * 반복 알림 상태는 서버 전용이다. 클라이언트는 자신의 문서를 읽을 수만 있고
 * isActive / nextPromptAt / promptSequence / stopReason 을 직접 바꿀 수 없다.
 * (firestore.rules 의 meetingIcebreakerSessions 규칙 참고)
 */

import {
  getFirestore,
  Timestamp,
  type DocumentReference,
} from "firebase-admin/firestore";
import * as logger from "firebase-functions/logger";

import {
  DEFAULT_MEETING_ICEBREAKER_POLICY,
  meetingIcebreakerPolicyFromConfigDoc,
  type MeetingIcebreakerPolicy,
} from "./policy";
import {
  MEETING_ICEBREAKER_COLLECTIONS,
  SEASON_MEETING_TYPE,
  asInt,
  asStr,
  asTrimmedOrNull,
  isMeetingIcebreakerMeetingType,
  isRecord,
  type MeetingIcebreakerMeetingType,
  type MeetingIcebreakerStopReason,
} from "./types";

export function db() {
  return getFirestore();
}

export function sessionRef(sessionId: string): DocumentReference {
  return db()
    .collection(MEETING_ICEBREAKER_COLLECTIONS.sessions)
    .doc(sessionId);
}

export function promptParticipantRef(
  sessionId: string,
  uid: string
): DocumentReference {
  return sessionRef(sessionId)
    .collection(MEETING_ICEBREAKER_COLLECTIONS.promptParticipants)
    .doc(uid);
}

export async function loadMeetingIcebreakerPolicy(): Promise<MeetingIcebreakerPolicy> {
  try {
    const snap = await db()
      .collection(MEETING_ICEBREAKER_COLLECTIONS.config)
      .doc("current")
      .get();
    return meetingIcebreakerPolicyFromConfigDoc(
      snap.data(),
      DEFAULT_MEETING_ICEBREAKER_POLICY
    );
  } catch (error) {
    logger.warn("meetingIcebreaker policy load failed, using defaults", {
      error,
    });
    return DEFAULT_MEETING_ICEBREAKER_POLICY;
  }
}

// -----------------------------------------------------------------------------
// 세션 문서
// -----------------------------------------------------------------------------

export type MeetingIcebreakerSessionDoc = {
  sessionId: string;
  meetingType: MeetingIcebreakerMeetingType;
  /** 시즌 미팅이면 약속 문서 id, 블라인드 미팅이면 미팅 문서 id */
  meetingId: string;
  /** 시즌 미팅 전용: 단체 채팅방 id */
  roomId: string | null;
  /** 시즌 미팅 전용: 약속 문서 id */
  promiseId: string | null;
  /** 무알코올 미팅이면 음주 벌칙 칸을 비음주 문구로 대체한다 */
  isAlcoholFree: boolean;
  endedAt: number | null;
  stopReason: MeetingIcebreakerStopReason | null;
};

export function readSessionDoc(
  sessionId: string,
  raw: unknown
): MeetingIcebreakerSessionDoc | null {
  if (!isRecord(raw)) return null;
  const meetingType = raw.meetingType;
  if (!isMeetingIcebreakerMeetingType(meetingType)) return null;
  const meetingId = asTrimmedOrNull(raw.meetingId);
  if (meetingId == null) return null;

  return {
    sessionId,
    meetingType,
    meetingId,
    roomId: asTrimmedOrNull(raw.roomId),
    promiseId: asTrimmedOrNull(raw.promiseId),
    isAlcoholFree: raw.isAlcoholFree === true,
    endedAt: readMillis(raw.endedAt),
    stopReason: readStopReason(raw.stopReason),
  };
}

export async function loadSession(
  sessionId: string
): Promise<MeetingIcebreakerSessionDoc | null> {
  const snap = await sessionRef(sessionId).get();
  if (!snap.exists) return null;
  return readSessionDoc(sessionId, snap.data());
}

// -----------------------------------------------------------------------------
// 참가자별 반복 알림 상태
// -----------------------------------------------------------------------------

export type PromptParticipantDoc = {
  uid: string;
  sessionId: string;
  meetingId: string;
  meetingType: MeetingIcebreakerMeetingType;
  isActive: boolean;
  optedOut: boolean;
  startedAtMs: number | null;
  endedAtMs: number | null;
  nextPromptAtMs: number | null;
  lastPromptAtMs: number | null;
  promptSequence: number;
  expiresAtMs: number | null;
  stopReason: MeetingIcebreakerStopReason | null;
  scheduleVersion: number;
  taskToken: string | null;
};

function readMillis(value: unknown): number | null {
  if (value instanceof Timestamp) return value.toMillis();
  if (value instanceof Date) return value.getTime();
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
}

function readStopReason(value: unknown): MeetingIcebreakerStopReason | null {
  const raw = asStr(value, "").trim();
  if (raw.length === 0) return null;
  return raw as MeetingIcebreakerStopReason;
}

export function readPromptParticipantDoc(
  uid: string,
  raw: unknown
): PromptParticipantDoc | null {
  if (!isRecord(raw)) return null;
  const sessionId = asTrimmedOrNull(raw.sessionId);
  const meetingId = asTrimmedOrNull(raw.meetingId);
  const meetingType = raw.meetingType;
  if (
    sessionId == null ||
    meetingId == null ||
    !isMeetingIcebreakerMeetingType(meetingType)
  ) {
    return null;
  }

  return {
    uid,
    sessionId,
    meetingId,
    meetingType,
    isActive: raw.isActive === true,
    optedOut: raw.optedOut === true,
    startedAtMs: readMillis(raw.startedAt),
    endedAtMs: readMillis(raw.endedAt),
    nextPromptAtMs: readMillis(raw.nextPromptAt),
    lastPromptAtMs: readMillis(raw.lastPromptAt),
    promptSequence: asInt(raw.promptSequence, 0),
    expiresAtMs: readMillis(raw.expiresAt),
    stopReason: readStopReason(raw.stopReason),
    scheduleVersion: asInt(raw.scheduleVersion, 0),
    taskToken: asTrimmedOrNull(raw.taskToken),
  };
}

export async function loadPromptParticipant(
  sessionId: string,
  uid: string
): Promise<PromptParticipantDoc | null> {
  const snap = await promptParticipantRef(sessionId, uid).get();
  if (!snap.exists) return null;
  return readPromptParticipantDoc(uid, snap.data());
}

export async function loadActivePromptParticipants(
  sessionId: string
): Promise<PromptParticipantDoc[]> {
  const snap = await sessionRef(sessionId)
    .collection(MEETING_ICEBREAKER_COLLECTIONS.promptParticipants)
    .where("isActive", "==", true)
    .get();
  const out: PromptParticipantDoc[] = [];
  for (const doc of snap.docs) {
    const parsed = readPromptParticipantDoc(doc.id, doc.data());
    if (parsed) out.push(parsed);
  }
  return out;
}

/** 시즌 미팅 세션의 원본 문서 경로 (roomId/promiseId 보정 포함) */
export function resolveSeasonMeetingRefs(session: MeetingIcebreakerSessionDoc): {
  roomId: string | null;
  promiseId: string;
} {
  if (session.meetingType !== SEASON_MEETING_TYPE) {
    return { roomId: null, promiseId: session.meetingId };
  }
  return {
    roomId: session.roomId,
    promiseId: session.promiseId ?? session.meetingId,
  };
}
