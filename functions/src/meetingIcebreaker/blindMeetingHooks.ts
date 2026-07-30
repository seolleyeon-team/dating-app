/**
 * 3:3 미팅 아이스브레이킹 룰렛 — 블라인드 취향 미팅 연결 지점
 * 경로: functions/src/meetingIcebreaker/blindMeetingHooks.ts
 *
 * blindMeeting/orchestrator.ts가 이 파일만 import 하도록 해서
 * 의존 방향을 한 쪽으로 유지한다 (orchestrator → meetingIcebreaker).
 *
 * 아이스브레이킹은 부가 기능이다. 여기서 예외가 나도 안전도장 처리 자체가
 * 실패하면 안 되므로 모든 함수가 예외를 삼키고 로그만 남긴다.
 */

import * as logger from "firebase-functions/logger";

import {
  activateMeetingIcebreakerPrompts,
  stopMeetingIcebreakerPrompts,
  stopMeetingIcebreakerSession,
} from "./session";
import {
  BLIND_TASTE_MEETING_TYPE,
  buildMeetingIcebreakerSessionId,
  type MeetingIcebreakerStopReason,
} from "./types";

function sessionIdFor(meetingId: string): string {
  return buildMeetingIcebreakerSessionId(BLIND_TASTE_MEETING_TYPE, meetingId);
}

/** 도착 안전도장 완료 → 15분 뒤부터 조용한 룰렛 알림 시작 */
export async function onBlindMeetingCheckIn(params: {
  meetingId: string;
  userId: string;
  isAlcoholFree: boolean;
}): Promise<void> {
  try {
    const result = await activateMeetingIcebreakerPrompts({
      meetingType: BLIND_TASTE_MEETING_TYPE,
      meetingId: params.meetingId,
      uid: params.userId,
      isAlcoholFree: params.isAlcoholFree,
    });
    logger.info("meetingIcebreaker blind meeting check-in hook", {
      sessionId: sessionIdFor(params.meetingId),
      result,
    });
  } catch (error) {
    logger.error("meetingIcebreaker activate failed (blind check-in)", {
      sessionId: sessionIdFor(params.meetingId),
      error,
    });
  }
}

/** 종료 안전도장 완료 → 해당 참가자 알림 즉시 종료 */
export async function onBlindMeetingCheckOut(params: {
  meetingId: string;
  userId: string;
}): Promise<void> {
  await stopBlindMeetingParticipantPrompts({
    meetingId: params.meetingId,
    userId: params.userId,
    reason: "goodbye_stamp",
  });
}

export async function stopBlindMeetingParticipantPrompts(params: {
  meetingId: string;
  userId: string;
  reason: MeetingIcebreakerStopReason;
}): Promise<void> {
  try {
    await stopMeetingIcebreakerPrompts({
      sessionId: sessionIdFor(params.meetingId),
      uid: params.userId,
      reason: params.reason,
    });
  } catch (error) {
    logger.error("meetingIcebreaker stop failed (blind participant)", {
      sessionId: sessionIdFor(params.meetingId),
      reason: params.reason,
      error,
    });
  }
}

/** 미팅 전체 종료·취소 → 남은 모든 알림 종료 */
export async function stopBlindMeetingSessionPrompts(params: {
  meetingId: string;
  reason: MeetingIcebreakerStopReason;
}): Promise<void> {
  try {
    const stopped = await stopMeetingIcebreakerSession({
      sessionId: sessionIdFor(params.meetingId),
      reason: params.reason,
    });
    if (stopped > 0) {
      logger.info("meetingIcebreaker session stopped (blind meeting)", {
        sessionId: sessionIdFor(params.meetingId),
        reason: params.reason,
        stopped,
      });
    }
  } catch (error) {
    logger.error("meetingIcebreaker stop failed (blind session)", {
      sessionId: sessionIdFor(params.meetingId),
      reason: params.reason,
      error,
    });
  }
}
