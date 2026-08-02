/**
 * 3:3 미팅 아이스브레이킹 룰렛 — 반복 알림 활성화 / 중단 / 재예약
 * 경로: functions/src/meetingIcebreaker/session.ts
 *
 * 알림 상태는 안전도장 이벤트와 신뢰 가능한 서버 코드만 바꿀 수 있다.
 * 클라이언트가 호출할 수 있는 것은 "이번 미팅 알림 끄기/켜기"뿐이다.
 */

import { randomBytes } from "crypto";
import { FieldValue, Timestamp } from "firebase-admin/firestore";
import { getFunctions } from "firebase-admin/functions";
import * as logger from "firebase-functions/logger";

import { isUserBlockedForPrompts } from "./eligibility";
import {
  areIcebreakerNotificationsEnabled,
  computeExpiresAtMs,
  computeFirstPromptAtMs,
  promptIntervalMs,
  scheduleDelaySecondsFor,
  type MeetingIcebreakerPolicy,
} from "./policy";
import {
  db,
  loadActivePromptParticipants,
  loadMeetingIcebreakerPolicy,
  promptParticipantRef,
  readPromptParticipantDoc,
  sessionRef,
} from "./store";
import {
  MEETING_ICEBREAKER_QUEUE_PATH,
  type MeetingIcebreakerPromptTaskPayload,
} from "./tasks";
import {
  MEETING_ICEBREAKER_COLLECTIONS,
  buildMeetingIcebreakerSessionId,
  type MeetingIcebreakerMeetingType,
  type MeetingIcebreakerStopReason,
} from "./types";

/**
 * 다시 켤 수 있는 중단 이유.
 *
 * 종료 안전도장·미팅 종료·노쇼처럼 되돌릴 수 없는 이유로 멈춘 뒤에는
 * 안전도장 이벤트가 다시 들어와도 알림을 되살리지 않는다.
 */
const RESUMABLE_STOP_REASONS: MeetingIcebreakerStopReason[] = [
  "feature_disabled",
];

export type ActivateResult =
  | "activated"
  | "already_active"
  | "already_ended"
  | "opted_out"
  | "notifications_disabled"
  | "user_blocked";

function newTaskToken(): string {
  return randomBytes(16).toString("hex");
}

/**
 * Cloud Tasks에 다음 알림을 예약한다.
 *
 * 실패해도 예외를 올리지 않는다. nextPromptAt이 문서에 남아 있으므로
 * meetingIcebreakerReconcileTick이 다음 tick에서 다시 예약한다.
 */
export async function enqueueMeetingIcebreakerPromptTask(
  payload: MeetingIcebreakerPromptTaskPayload,
  policy: MeetingIcebreakerPolicy,
  nowMs: number
): Promise<void> {
  try {
    await getFunctions()
      .taskQueue(MEETING_ICEBREAKER_QUEUE_PATH)
      .enqueue(payload, {
        scheduleDelaySeconds: scheduleDelaySecondsFor(
          payload.scheduledForMs,
          nowMs
        ),
        dispatchDeadlineSeconds: policy.taskDispatchDeadlineSeconds,
      });
  } catch (error) {
    logger.warn("meetingIcebreaker prompt task enqueue failed", {
      sessionId: payload.sessionId,
      scheduleVersion: payload.scheduleVersion,
      promptSequence: payload.promptSequence,
      error,
    });
  }
}

/**
 * 시작 안전도장 완료 시점에 참가자별 반복 알림을 켠다.
 *
 * 첫 알림은 [MeetingIcebreakerPolicy.firstPromptDelayMinutes] 뒤에 발송된다.
 */
export async function activateMeetingIcebreakerPrompts(params: {
  meetingType: MeetingIcebreakerMeetingType;
  meetingId: string;
  uid: string;
  roomId?: string | null;
  promiseId?: string | null;
  isAlcoholFree?: boolean;
  policy?: MeetingIcebreakerPolicy;
}): Promise<ActivateResult> {
  const policy = params.policy ?? (await loadMeetingIcebreakerPolicy());
  const sessionId = buildMeetingIcebreakerSessionId(
    params.meetingType,
    params.meetingId
  );

  if (!areIcebreakerNotificationsEnabled(policy)) {
    logger.info("meetingIcebreaker prompts disabled by feature flag", {
      sessionId,
      meetingType: params.meetingType,
    });
    return "notifications_disabled";
  }

  const userSnap = await db().collection("users").doc(params.uid).get();
  if (isUserBlockedForPrompts(userSnap.data())) {
    return "user_blocked";
  }

  const nowMs = Date.now();
  const participantRef = promptParticipantRef(sessionId, params.uid);

  const outcome = await db().runTransaction<{
    result: ActivateResult;
    task: MeetingIcebreakerPromptTaskPayload | null;
  }>(async (tx) => {
    const snap = await tx.get(participantRef);
    const existing = snap.exists
      ? readPromptParticipantDoc(params.uid, snap.data())
      : null;

    if (existing?.isActive === true) {
      return { result: "already_active", task: null };
    }
    if (existing?.optedOut === true) {
      return { result: "opted_out", task: null };
    }
    if (
      existing != null &&
      existing.stopReason != null &&
      !RESUMABLE_STOP_REASONS.includes(existing.stopReason)
    ) {
      return { result: "already_ended", task: null };
    }

    const scheduleVersion = (existing?.scheduleVersion ?? 0) + 1;
    const startedAtMs = existing?.startedAtMs ?? nowMs;
    const nextPromptAtMs = computeFirstPromptAtMs(nowMs, policy);
    const expiresAtMs = computeExpiresAtMs(startedAtMs, policy);
    const taskToken = newTaskToken();
    const promptSequence = existing?.promptSequence ?? 0;

    tx.set(
      sessionRef(sessionId),
      {
        sessionId,
        meetingType: params.meetingType,
        meetingId: params.meetingId,
        roomId: params.roomId ?? null,
        promiseId: params.promiseId ?? null,
        isAlcoholFree: params.isAlcoholFree === true,
        endedAt: null,
        stopReason: null,
        createdAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

    tx.set(
      participantRef,
      {
        sessionId,
        meetingId: params.meetingId,
        meetingType: params.meetingType,
        uid: params.uid,
        isActive: true,
        optedOut: false,
        startedAt: Timestamp.fromMillis(startedAtMs),
        endedAt: null,
        nextPromptAt: Timestamp.fromMillis(nextPromptAtMs),
        lastPromptAt:
          existing?.lastPromptAtMs != null
            ? Timestamp.fromMillis(existing.lastPromptAtMs)
            : null,
        promptSequence,
        expiresAt: Timestamp.fromMillis(expiresAtMs),
        stopReason: null,
        scheduleVersion,
        taskToken,
        createdAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );

    return {
      result: "activated",
      task: {
        sessionId,
        uid: params.uid,
        scheduleVersion,
        promptSequence: promptSequence + 1,
        scheduledForMs: nextPromptAtMs,
        taskToken,
      },
    };
  });

  if (outcome.task != null) {
    await enqueueMeetingIcebreakerPromptTask(outcome.task, policy, nowMs);
    logger.info("meetingIcebreaker prompts activated", {
      sessionId,
      meetingType: params.meetingType,
      scheduleVersion: outcome.task.scheduleVersion,
      firstPromptInMinutes: policy.firstPromptDelayMinutes,
    });
  }

  return outcome.result;
}

/**
 * 참가자 한 명의 반복 알림을 즉시 중단한다.
 *
 * scheduleVersion을 올리므로 이미 예약된 task가 실행돼도 no-op이 된다.
 */
export async function stopMeetingIcebreakerPrompts(params: {
  sessionId: string;
  uid: string;
  reason: MeetingIcebreakerStopReason;
  markOptedOut?: boolean;
}): Promise<boolean> {
  const participantRef = promptParticipantRef(params.sessionId, params.uid);

  const stopped = await db().runTransaction<boolean>(async (tx) => {
    const snap = await tx.get(participantRef);
    if (!snap.exists) {
      if (params.markOptedOut !== true) return false;
      // 아직 세션이 만들어지지 않았어도 "이번 미팅 알림 끄기"는 기록해 둔다.
      tx.set(
        participantRef,
        {
          uid: params.uid,
          sessionId: params.sessionId,
          isActive: false,
          optedOut: true,
          stopReason: params.reason,
          endedAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      return true;
    }

    const existing = readPromptParticipantDoc(params.uid, snap.data());
    const patch: Record<string, unknown> = {
      isActive: false,
      nextPromptAt: null,
      taskToken: null,
      scheduleVersion: (existing?.scheduleVersion ?? 0) + 1,
      updatedAt: FieldValue.serverTimestamp(),
    };
    if (params.markOptedOut === true) {
      patch.optedOut = true;
    }
    // 이미 끝난 세션의 중단 이유는 최초 값을 유지한다.
    if (existing?.stopReason == null) {
      patch.stopReason = params.reason;
      patch.endedAt = FieldValue.serverTimestamp();
    }

    tx.set(participantRef, patch, { merge: true });
    return existing?.isActive === true || params.markOptedOut === true;
  });

  if (stopped) {
    logger.info("meetingIcebreaker prompts stopped", {
      sessionId: params.sessionId,
      reason: params.reason,
    });
  }
  return stopped;
}

/** 미팅 전체 종료·취소 시 남은 모든 알림을 정리한다. */
export async function stopMeetingIcebreakerSession(params: {
  sessionId: string;
  reason: MeetingIcebreakerStopReason;
}): Promise<number> {
  const active = await loadActivePromptParticipants(params.sessionId);
  let stopped = 0;
  for (const participant of active) {
    const ok = await stopMeetingIcebreakerPrompts({
      sessionId: params.sessionId,
      uid: participant.uid,
      reason: params.reason,
    });
    if (ok) stopped += 1;
  }

  await sessionRef(params.sessionId).set(
    {
      endedAt: FieldValue.serverTimestamp(),
      stopReason: params.reason,
      updatedAt: FieldValue.serverTimestamp(),
    },
    { merge: true }
  );

  return stopped;
}

/**
 * 다음 알림 시각을 다시 예약한다.
 *
 * dispatch 이후, rate limit, task 유실 복구에 모두 같은 경로를 쓴다.
 */
export async function reschedulePrompt(params: {
  sessionId: string;
  uid: string;
  nextPromptAtMs: number;
  policy: MeetingIcebreakerPolicy;
  nowMs?: number;
}): Promise<boolean> {
  const nowMs = params.nowMs ?? Date.now();
  const participantRef = promptParticipantRef(params.sessionId, params.uid);

  const task =
    await db().runTransaction<MeetingIcebreakerPromptTaskPayload | null>(
      async (tx) => {
        const snap = await tx.get(participantRef);
        if (!snap.exists) return null;
        const existing = readPromptParticipantDoc(params.uid, snap.data());
        if (existing == null || !existing.isActive || existing.optedOut) {
          return null;
        }
        if (
          existing.expiresAtMs != null &&
          params.nextPromptAtMs >= existing.expiresAtMs
        ) {
          // 다음 알림이 hard stop 이후라면 예약하지 않고 여기서 끝낸다.
          tx.set(
            participantRef,
            {
              isActive: false,
              nextPromptAt: null,
              taskToken: null,
              stopReason: existing.stopReason ?? "max_duration_reached",
              endedAt: FieldValue.serverTimestamp(),
              scheduleVersion: existing.scheduleVersion + 1,
              updatedAt: FieldValue.serverTimestamp(),
            },
            { merge: true }
          );
          return null;
        }

        const scheduleVersion = existing.scheduleVersion + 1;
        const taskToken = newTaskToken();
        tx.set(
          participantRef,
          {
            nextPromptAt: Timestamp.fromMillis(params.nextPromptAtMs),
            scheduleVersion,
            taskToken,
            updatedAt: FieldValue.serverTimestamp(),
          },
          { merge: true }
        );

        return {
          sessionId: params.sessionId,
          uid: params.uid,
          scheduleVersion,
          promptSequence: existing.promptSequence + 1,
          scheduledForMs: params.nextPromptAtMs,
          taskToken,
        };
      }
    );

  if (task == null) return false;
  await enqueueMeetingIcebreakerPromptTask(task, params.policy, nowMs);
  return true;
}

/**
 * "이번 미팅에서는 룰렛 알림 받지 않기" 토글.
 *
 * 채팅·안전 알림 등 다른 알림에는 영향을 주지 않고, 다른 참가자에게도
 * 노출되지 않는다.
 */
export async function setMeetingIcebreakerOptOut(params: {
  sessionId: string;
  uid: string;
  optedOut: boolean;
}): Promise<boolean> {
  if (params.optedOut) {
    await stopMeetingIcebreakerPrompts({
      sessionId: params.sessionId,
      uid: params.uid,
      reason: "opted_out",
      markOptedOut: true,
    });
    return true;
  }

  const policy = await loadMeetingIcebreakerPolicy();
  const nowMs = Date.now();
  const participantRef = promptParticipantRef(params.sessionId, params.uid);

  const task =
    await db().runTransaction<MeetingIcebreakerPromptTaskPayload | null>(
      async (tx) => {
        const snap = await tx.get(participantRef);
        if (!snap.exists) return null;
        const existing = readPromptParticipantDoc(params.uid, snap.data());
        if (existing == null) return null;

        const patch: Record<string, unknown> = {
          optedOut: false,
          updatedAt: FieldValue.serverTimestamp(),
        };

        const resumable =
          existing.stopReason == null || existing.stopReason === "opted_out";
        const notExpired =
          existing.expiresAtMs == null || existing.expiresAtMs > nowMs;

        if (
          !areIcebreakerNotificationsEnabled(policy) ||
          !resumable ||
          !notExpired
        ) {
          tx.set(participantRef, patch, { merge: true });
          return null;
        }

        const scheduleVersion = existing.scheduleVersion + 1;
        const taskToken = newTaskToken();
        const nextPromptAtMs = nowMs + promptIntervalMs(policy);

        tx.set(
          participantRef,
          {
            ...patch,
            isActive: true,
            stopReason: null,
            endedAt: null,
            nextPromptAt: Timestamp.fromMillis(nextPromptAtMs),
            scheduleVersion,
            taskToken,
          },
          { merge: true }
        );

        return {
          sessionId: params.sessionId,
          uid: params.uid,
          scheduleVersion,
          promptSequence: existing.promptSequence + 1,
          scheduledForMs: nextPromptAtMs,
          taskToken,
        };
      }
    );

  if (task != null) {
    await enqueueMeetingIcebreakerPromptTask(task, policy, nowMs);
  }
  return false;
}

/** 예약 작업이 유실된 참가자 문서를 collection group으로 찾는다. */
export async function loadOverduePromptParticipants(params: {
  nowMs: number;
  policy: MeetingIcebreakerPolicy;
}): Promise<{ sessionId: string; uid: string; nextPromptAtMs: number }[]> {
  const cutoff = Timestamp.fromMillis(
    params.nowMs - params.policy.reconcileGraceMinutes * 60 * 1000
  );
  const snap = await db()
    .collectionGroup(MEETING_ICEBREAKER_COLLECTIONS.promptParticipants)
    .where("isActive", "==", true)
    .where("nextPromptAt", "<=", cutoff)
    .orderBy("nextPromptAt", "asc")
    .limit(params.policy.reconcileBatchLimit)
    .get();

  const out: { sessionId: string; uid: string; nextPromptAtMs: number }[] = [];
  for (const doc of snap.docs) {
    const parsed = readPromptParticipantDoc(doc.id, doc.data());
    if (parsed == null || parsed.nextPromptAtMs == null) continue;
    out.push({
      sessionId: parsed.sessionId,
      uid: parsed.uid,
      nextPromptAtMs: parsed.nextPromptAtMs,
    });
  }
  return out;
}
