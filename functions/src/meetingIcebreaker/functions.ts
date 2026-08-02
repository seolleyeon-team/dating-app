/**
 * 3:3 미팅 아이스브레이킹 룰렛 — Cloud Functions
 * 경로: functions/src/meetingIcebreaker/functions.ts
 *
 *  1) syncMeetingIcebreakerFromPromise — 3:3 시즌 미팅 안전도장 → 알림 활성/중단
 *  2) dispatchMeetingIcebreakerPrompt  — 예약된 조용한 알림 1건 발송 + 다음 주기 예약
 *  3) meetingIcebreakerReconcileTick   — 유실된 예약 복구 + 최대 지속 시간 종료
 *  4) meetingIcebreakerAction          — 진입 검증 / 이번 미팅 알림 끄기 (callable)
 *
 * 모든 경로가 idempotent 하다. 같은 (세션, 참가자, 순번)으로는 한 번만 발송된다.
 */

import { FieldValue, Timestamp } from "firebase-admin/firestore";
import { onDocumentWritten } from "firebase-functions/v2/firestore";
import { HttpsError, onCall } from "firebase-functions/v2/https";
import { onSchedule } from "firebase-functions/v2/scheduler";
import { onTaskDispatched } from "firebase-functions/v2/tasks";
import * as logger from "firebase-functions/logger";
import { randomBytes } from "crypto";

import {
  classifySeasonMeetingRoom,
  isSeasonMeetingPromiseActive,
  isSeasonMeetingPromiseTerminal,
  readPromiseSafetyStampUserIds,
  readPromiseStatus,
} from "./eligibility";
import { sendMeetingIcebreakerPrompt } from "./notifications";
import {
  areIcebreakerNotificationsEnabled,
  computeExpiresAtMs,
  decidePromptDispatch,
  promptIntervalMs,
  promptSequenceBucket,
} from "./policy";
import {
  MEETING_ICEBREAKER_CALLABLE_OPTIONS,
  MEETING_ICEBREAKER_FIRESTORE_OPTIONS,
  MEETING_ICEBREAKER_SCHEDULE_OPTIONS,
  MEETING_ICEBREAKER_TASK_OPTIONS,
} from "./runtime";
import {
  activateMeetingIcebreakerPrompts,
  enqueueMeetingIcebreakerPromptTask,
  loadOverduePromptParticipants,
  reschedulePrompt,
  setMeetingIcebreakerOptOut,
  stopMeetingIcebreakerPrompts,
  stopMeetingIcebreakerSession,
} from "./session";
import {
  db,
  loadActivePromptParticipants,
  loadMeetingIcebreakerPolicy,
  loadPromptParticipant,
  promptParticipantRef,
  readPromptParticipantDoc,
} from "./store";
import {
  isMeetingIcebreakerPromptTaskPayload,
  type MeetingIcebreakerPromptTaskPayload,
} from "./tasks";
import {
  SEASON_MEETING_TYPE,
  asStr,
  buildMeetingIcebreakerSessionId,
  isRecord,
} from "./types";
import { verifyMeetingIcebreakerEntry } from "./verify";

// =============================================================================
// 1) 3:3 시즌 미팅 안전도장 → 반복 알림 활성 / 중단
//
// 일반 1:1 채팅과 일반 이벤트 채팅방은 classifySeasonMeetingRoom에서 걸러진다.
// (기본값이 "적용하지 않음"이라 새 방 종류가 생겨도 자동으로 켜지지 않는다)
// =============================================================================
export const syncMeetingIcebreakerFromPromise = onDocumentWritten(
  {
    document: "chat_rooms/{roomId}/promises/{promiseId}",
    ...MEETING_ICEBREAKER_FIRESTORE_OPTIONS,
  },
  async (event) => {
    const roomId = event.params.roomId;
    const promiseId = event.params.promiseId;
    const sessionId = buildMeetingIcebreakerSessionId(
      SEASON_MEETING_TYPE,
      promiseId
    );

    const after = event.data?.after.data();

    if (!after) {
      // 약속 문서가 삭제됐다면 남은 알림을 모두 정리한다.
      await stopMeetingIcebreakerSession({
        sessionId,
        reason: "meeting_cancelled",
      });
      return;
    }

    const status = readPromiseStatus(after);
    const meetupIds = readPromiseSafetyStampUserIds(after, "meetup");
    const goodbyeIds = readPromiseSafetyStampUserIds(after, "goodbye");

    // 안전도장 흔적도, 종료 상태도 없는 약속 쓰기는 무시한다 (읽기 비용 절약).
    if (
      meetupIds.length === 0 &&
      goodbyeIds.length === 0 &&
      !isSeasonMeetingPromiseTerminal(after)
    ) {
      return;
    }

    const roomSnap = await db().collection("chat_rooms").doc(roomId).get();
    const classification = classifySeasonMeetingRoom(roomSnap.data());
    if (!classification.eligible) {
      logger.debug("meetingIcebreaker skipped: room not eligible", {
        reason: classification.reason,
        promiseStatus: status,
      });
      return;
    }

    if (isSeasonMeetingPromiseTerminal(after)) {
      const reason =
        readPromiseStatus(after) === "completed"
          ? "meeting_completed"
          : "meeting_cancelled";
      const stopped = await stopMeetingIcebreakerSession({
        sessionId,
        reason,
      });
      logger.info("meetingIcebreaker session stopped by promise status", {
        sessionId,
        reason,
        stopped,
      });
      return;
    }

    if (!isSeasonMeetingPromiseActive(after)) {
      return;
    }

    const roomParticipants = new Set(classification.participantIds);

    // 종료 안전도장을 찍은 참가자는 즉시 중단한다.
    for (const uid of goodbyeIds) {
      await stopMeetingIcebreakerPrompts({
        sessionId,
        uid,
        reason: "goodbye_stamp",
      });
    }

    // 채팅방에서 빠진(교체·퇴장) 참가자에게는 더 보내지 않는다.
    const active = await loadActivePromptParticipants(sessionId);
    for (const participant of active) {
      if (!roomParticipants.has(participant.uid)) {
        await stopMeetingIcebreakerPrompts({
          sessionId,
          uid: participant.uid,
          reason: "participant_left",
        });
      }
    }

    // 시작 안전도장을 찍었고 아직 종료하지 않은 참가자에게 알림을 켠다.
    const goodbyeSet = new Set(goodbyeIds);
    for (const uid of meetupIds) {
      if (goodbyeSet.has(uid)) continue;
      if (!roomParticipants.has(uid)) continue;
      const result = await activateMeetingIcebreakerPrompts({
        meetingType: SEASON_MEETING_TYPE,
        meetingId: promiseId,
        uid,
        roomId,
        promiseId,
      });
      if (result === "activated") {
        logger.info("meetingIcebreaker activated for season meeting", {
          sessionId,
        });
      }
    }
  }
);

// =============================================================================
// 2) 예약된 조용한 알림 발송
// =============================================================================
export const dispatchMeetingIcebreakerPrompt = onTaskDispatched(
  MEETING_ICEBREAKER_TASK_OPTIONS,
  async (request) => {
    const payload = (request.data ?? {}) as Partial<
      MeetingIcebreakerPromptTaskPayload
    >;
    if (!isMeetingIcebreakerPromptTaskPayload(payload)) {
      logger.warn("meetingIcebreaker prompt task payload invalid");
      return;
    }

    const policy = await loadMeetingIcebreakerPolicy();
    if (!areIcebreakerNotificationsEnabled(policy)) {
      // feature flag가 꺼져 있으면 이미 예약된 task는 아무 것도 하지 않는다.
      logger.info("meetingIcebreaker prompt task no-op: feature disabled", {
        sessionId: payload.sessionId,
      });
      return;
    }

    const nowMs = Date.now();
    const existing = await loadPromptParticipant(
      payload.sessionId,
      payload.uid
    );
    if (existing == null) {
      logger.info("meetingIcebreaker prompt task no-op: session missing", {
        sessionId: payload.sessionId,
      });
      return;
    }
    if (!existing.isActive || existing.optedOut) {
      logger.info("meetingIcebreaker prompt task no-op: stopped", {
        sessionId: payload.sessionId,
        stopReason: existing.stopReason,
      });
      return;
    }
    if (
      existing.scheduleVersion !== payload.scheduleVersion ||
      existing.taskToken !== payload.taskToken ||
      existing.promptSequence + 1 !== payload.promptSequence
    ) {
      // 오래된 task (중단 후 재예약, 재시도 중복 등)
      logger.info("meetingIcebreaker prompt task no-op: stale schedule", {
        sessionId: payload.sessionId,
      });
      return;
    }

    // 원본 문서를 다시 읽어 종료된 미팅에는 절대 보내지 않는다.
    const entry = await verifyMeetingIcebreakerEntry({
      uid: payload.uid,
      sessionId: payload.sessionId,
    });
    if (!entry.allowed) {
      switch (entry.decision) {
        case "meeting_ended":
          await stopMeetingIcebreakerPrompts({
            sessionId: payload.sessionId,
            uid: payload.uid,
            reason: "meeting_completed",
          });
          return;
        case "meeting_cancelled":
          await stopMeetingIcebreakerPrompts({
            sessionId: payload.sessionId,
            uid: payload.uid,
            reason: "meeting_cancelled",
          });
          return;
        case "not_participant":
          await stopMeetingIcebreakerPrompts({
            sessionId: payload.sessionId,
            uid: payload.uid,
            reason: "participant_left",
          });
          return;
        case "not_started":
          await reschedulePrompt({
            sessionId: payload.sessionId,
            uid: payload.uid,
            nextPromptAtMs: nowMs + promptIntervalMs(policy),
            policy,
            nowMs,
          });
          return;
        default:
          logger.info("meetingIcebreaker prompt task no-op: entry denied", {
            sessionId: payload.sessionId,
            decision: entry.decision,
          });
          return;
      }
    }

    const expiresAtMs =
      existing.expiresAtMs ??
      computeExpiresAtMs(existing.startedAtMs ?? nowMs, policy);

    const decision = decidePromptDispatch({
      nowMs,
      scheduledForMs: payload.scheduledForMs,
      expiresAtMs,
      lastPromptAtMs: existing.lastPromptAtMs,
      policy,
    });

    if (decision.action === "stop") {
      await stopMeetingIcebreakerPrompts({
        sessionId: payload.sessionId,
        uid: payload.uid,
        reason: decision.reason,
      });
      return;
    }

    if (decision.action === "reschedule") {
      logger.info("meetingIcebreaker prompt rescheduled", {
        sessionId: payload.sessionId,
        reason: decision.reason,
      });
      await reschedulePrompt({
        sessionId: payload.sessionId,
        uid: payload.uid,
        nextPromptAtMs: decision.nextPromptAtMs,
        policy,
        nowMs,
      });
      return;
    }

    // 발송 예약 확정(claim). 재시도가 같은 순번을 두 번 보내지 못하게 한다.
    const participantRef = promptParticipantRef(
      payload.sessionId,
      payload.uid
    );
    const nextTaskToken = randomBytes(16).toString("hex");
    const claimed = await db().runTransaction<boolean>(async (tx) => {
      const snap = await tx.get(participantRef);
      if (!snap.exists) return false;
      const current = readPromptParticipantDoc(payload.uid, snap.data());
      if (current == null || !current.isActive || current.optedOut) return false;
      if (
        current.scheduleVersion !== payload.scheduleVersion ||
        current.taskToken !== payload.taskToken ||
        current.promptSequence + 1 !== payload.promptSequence
      ) {
        return false;
      }

      tx.set(
        participantRef,
        {
          promptSequence: payload.promptSequence,
          lastPromptAt: Timestamp.fromMillis(nowMs),
          nextPromptAt: Timestamp.fromMillis(decision.nextPromptAtMs),
          scheduleVersion: payload.scheduleVersion + 1,
          taskToken: nextTaskToken,
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      return true;
    });

    if (!claimed) {
      logger.info("meetingIcebreaker prompt claim lost", {
        sessionId: payload.sessionId,
      });
      return;
    }

    const result = await sendMeetingIcebreakerPrompt({
      sessionId: payload.sessionId,
      uid: payload.uid,
      meetingId: existing.meetingId,
      meetingType: existing.meetingType,
      sequence: payload.promptSequence,
    });

    logger.info("meetingIcebreaker prompt sent", {
      sessionId: payload.sessionId,
      meetingType: existing.meetingType,
      notificationSequenceBucket: promptSequenceBucket(payload.promptSequence),
      skippedPrompts: decision.skippedPrompts,
      pushDispatched: result.pushDispatched,
    });

    const nextTask: MeetingIcebreakerPromptTaskPayload = {
      sessionId: payload.sessionId,
      uid: payload.uid,
      scheduleVersion: payload.scheduleVersion + 1,
      promptSequence: payload.promptSequence + 1,
      scheduledForMs: decision.nextPromptAtMs,
      taskToken: nextTaskToken,
    };

    if (decision.nextPromptAtMs >= expiresAtMs) {
      await stopMeetingIcebreakerPrompts({
        sessionId: payload.sessionId,
        uid: payload.uid,
        reason: "max_duration_reached",
      });
      return;
    }

    await enqueueMeetingIcebreakerPromptTask(nextTask, policy, nowMs);
  }
);

// =============================================================================
// 3) 유실된 예약 복구 + 최대 지속 시간 종료
// =============================================================================
export const meetingIcebreakerReconcileTick = onSchedule(
  { schedule: "every 5 minutes", ...MEETING_ICEBREAKER_SCHEDULE_OPTIONS },
  async () => {
    const policy = await loadMeetingIcebreakerPolicy();
    if (!areIcebreakerNotificationsEnabled(policy)) {
      logger.info("meetingIcebreaker reconcile skipped: feature disabled");
      return;
    }

    const nowMs = Date.now();
    let overdue: { sessionId: string; uid: string; nextPromptAtMs: number }[];
    try {
      overdue = await loadOverduePromptParticipants({ nowMs, policy });
    } catch (error) {
      logger.error("meetingIcebreaker reconcile query failed", { error });
      return;
    }

    let expired = 0;
    let rescheduled = 0;
    for (const item of overdue) {
      try {
        const participant = await loadPromptParticipant(
          item.sessionId,
          item.uid
        );
        if (participant == null || !participant.isActive) continue;

        const expiresAtMs =
          participant.expiresAtMs ??
          computeExpiresAtMs(participant.startedAtMs ?? nowMs, policy);
        if (nowMs >= expiresAtMs) {
          await stopMeetingIcebreakerPrompts({
            sessionId: item.sessionId,
            uid: item.uid,
            reason: "max_duration_reached",
          });
          expired += 1;
          continue;
        }

        // 예약이 유실됐으므로 지금 기준으로 즉시 실행되는 task를 다시 만든다.
        // 밀린 알림을 몰아 보내지 않도록 dispatch 쪽에서 1건만 발송한다.
        const ok = await reschedulePrompt({
          sessionId: item.sessionId,
          uid: item.uid,
          nextPromptAtMs: nowMs,
          policy,
          nowMs,
        });
        if (ok) rescheduled += 1;
      } catch (error) {
        logger.error("meetingIcebreaker reconcile item failed", {
          sessionId: item.sessionId,
          error,
        });
      }
    }

    if (overdue.length > 0) {
      logger.info("meetingIcebreaker reconcile finished", {
        candidates: overdue.length,
        rescheduled,
        expired,
      });
    }
  }
);

// =============================================================================
// 4) 진입 검증 / 이번 미팅 알림 끄기 (callable)
// =============================================================================
function requireUid(request: { auth?: { uid?: string } | null }): string {
  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  }
  return uid;
}

function getCallableData(request: { data?: unknown }): Record<string, unknown> {
  return isRecord(request.data) ? request.data : {};
}

export const meetingIcebreakerAction = onCall(
  MEETING_ICEBREAKER_CALLABLE_OPTIONS,
  async (request) => {
    const uid = requireUid(request);
    const data = getCallableData(request);
    const action = asStr(data.action, "");

    if (action === "getMeetingIcebreakerEntry") {
      const entry = await verifyMeetingIcebreakerEntry({
        uid,
        sessionId: asStr(data.sessionId, "") || null,
        meetingId: asStr(data.meetingId, "") || null,
        meetingType: asStr(data.meetingType, "") || null,
      });
      logger.info("meetingIcebreakerAction entry", {
        action,
        decision: entry.decision,
        meetingType: entry.meetingType,
      });
      return {
        allowed: entry.allowed,
        decision: entry.decision,
        sessionId: entry.sessionId,
        meetingId: entry.meetingId,
        meetingType: entry.meetingType,
        alcoholFreeCopy: entry.alcoholFreeCopy,
        optedOut: entry.optedOut,
        bombPassEnabled: entry.bombPassEnabled,
      };
    }

    if (action === "setMeetingIcebreakerOptOut") {
      const optedOut = data.optedOut === true;
      const entry = await verifyMeetingIcebreakerEntry({
        uid,
        sessionId: asStr(data.sessionId, "") || null,
        meetingId: asStr(data.meetingId, "") || null,
        meetingType: asStr(data.meetingType, "") || null,
      });
      if (
        entry.sessionId == null ||
        entry.decision === "not_participant" ||
        entry.decision === "not_found" ||
        entry.decision === "unauthenticated"
      ) {
        throw new HttpsError(
          "permission-denied",
          "이 미팅의 알림 설정을 바꿀 수 없어요."
        );
      }
      await setMeetingIcebreakerOptOut({
        sessionId: entry.sessionId,
        uid,
        optedOut,
      });
      logger.info("meetingIcebreakerAction optOut", { action, optedOut });
      return { optedOut };
    }

    throw new HttpsError("invalid-argument", "지원하지 않는 요청이에요.");
  }
);
