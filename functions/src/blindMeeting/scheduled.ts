/**
 * 3:3 블라인드 취향 미팅 — 예약 작업
 * 경로: functions/src/blindMeeting/scheduled.ts
 *
 * 클라이언트 local timer가 아니라 서버 예약 작업으로 처리한다.
 *  - 매칭 재시도
 *  - 24시간 / 3시간 전 참석 재확인
 *  - 미응답자 위험 표시 + 대체 후보 탐색
 *  - 미팅 시작/종료 안전도장 안내
 *  - 종료 후 약 15분 뒤 후속 대화 푸시
 *  - 후속 선택 마감 전 1회 리마인더
 *  - 단체 채팅 lifecycle (48시간 읽기 전용, 7일 보관)
 */

import { Timestamp } from "firebase-admin/firestore";
import { onSchedule } from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";

import { notifyBlindMeeting } from "./notifications";
import {
  applyChatLifecycle,
  handleVacancy,
  openFollowUp,
  runMatchingForAllSlots,
  settleCancellation,
} from "./orchestrator";
import {
  MeetingDoc,
  db,
  loadMeeting,
  loadParticipants,
  loadPolicy,
  readMeetingDoc,
  updateParticipant,
} from "./store";
import { BLIND_MEETING_SCHEDULE_OPTIONS } from "./runtime";
import { BLIND_MEETING_COLLECTIONS } from "./types";

/** 한 단계가 실패해도 나머지 단계는 계속 진행한다. */
async function runStep(name: string, step: () => Promise<void>): Promise<void> {
  try {
    await step();
  } catch (error) {
    logger.error("blindMeeting scheduled step failed", { step: name, error });
  }
}

async function loadMeetingsByStatuses(
  statuses: string[]
): Promise<MeetingDoc[]> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .where("serverStatus", "in", statuses)
    .get();
  const result: MeetingDoc[] = [];
  for (const doc of snap.docs) {
    const meeting = readMeetingDoc(doc.id, doc.data());
    if (meeting) result.push(meeting);
  }
  return result;
}

/** 10분마다 대기 중인 슬롯에 대해 팀 구성을 재시도한다. */
async function runBlindMeetingMatchingStep(): Promise<void> {
    const created = await runMatchingForAllSlots();
    logger.info("blindMeeting scheduled matching", {
      createdMeetings: created.length,
    });
}

/** 15분마다 참석 재확인 알림과 미응답 위험 처리를 수행한다. */
async function dispatchBlindMeetingAttendanceChecksStep(): Promise<void> {
    const policy = await loadPolicy();
    const meetings = await loadMeetingsByStatuses([
      "chat_open",
      "schedule_confirmed",
    ]);
    const now = Date.now();

    for (const meeting of meetings) {
      const startAt = meeting.scheduledStartAtMs;
      if (startAt == null) continue;
      const untilStart = startAt - now;
      const participants = await loadParticipants(meeting.meetingId);

      const runPhase = async (
        phase: "24h" | "3h",
        windowMs: number,
        field: "attendance24h" | "attendance3h"
      ) => {
        if (untilStart > windowMs || untilStart <= 0) return;
        const pending = participants
          .filter((p) => p.status === "confirmed")
          .filter((p) => p[field] === "pending")
          .map((p) => p.userId);
        if (pending.length === 0) return;

        await notifyBlindMeeting({
          userIds: pending,
          meetingId: meeting.meetingId,
          kind: phase === "24h" ? "attendance_24h" : "attendance_3h",
        });

        // 응답 마감을 넘긴 미응답자는 위험 상태로 표시하고 대체 후보를 찾는다.
        const overdue =
          untilStart <= windowMs - policy.attendanceResponseWindowMs;
        if (!overdue) return;
        for (const userId of pending) {
          await updateParticipant(meeting.meetingId, userId, {
            extra: { attendanceRisk: phase },
          });
          await handleVacancy({
            meetingId: meeting.meetingId,
            vacantUserId: userId,
            urgent: phase === "3h",
          });
        }
      };

      await runPhase("24h", policy.firstAttendanceCheckBeforeMs, "attendance24h");
      await runPhase("3h", policy.secondAttendanceCheckBeforeMs, "attendance3h");
    }
}

/** 미팅 시작 시각 전후로 도착 안전도장을 안내한다. */
async function dispatchBlindMeetingCheckinRemindersStep(): Promise<void> {
    const meetings = await loadMeetingsByStatuses([
      "schedule_confirmed",
      "checkin_open",
      "in_progress",
    ]);
    const now = Date.now();

    for (const meeting of meetings) {
      const startAt = meeting.scheduledStartAtMs;
      if (startAt == null) continue;
      const delta = now - startAt;
      if (delta < -15 * 60 * 1000 || delta > 60 * 60 * 1000) continue;

      const participants = await loadParticipants(meeting.meetingId);
      const pending = participants
        .filter((p) => p.status === "confirmed" && !p.checkedIn)
        .map((p) => p.userId);
      if (pending.length === 0) continue;

      await notifyBlindMeeting({
        userIds: pending,
        meetingId: meeting.meetingId,
        kind: "checkin",
      });
    }
}

/**
 * 당일 노쇼 처리.
 *
 * 긴급 대체 탐색 기간이 지나도 도착 안전도장이 없으면 노쇼로 확정한다.
 */
async function finalizeBlindMeetingNoShowsStep(): Promise<void> {
    const policy = await loadPolicy();
    const meetings = await loadMeetingsByStatuses([
      "checkin_open",
      "in_progress",
    ]);
    const now = Date.now();

    for (const meeting of meetings) {
      const startAt = meeting.scheduledStartAtMs;
      if (startAt == null) continue;
      if (now - startAt < policy.urgentReplacementSearchWindowMs) continue;

      const participants = await loadParticipants(meeting.meetingId);
      for (const participant of participants) {
        if (participant.status !== "confirmed" || participant.checkedIn) {
          continue;
        }
        await settleCancellation({
          meetingId: meeting.meetingId,
          userId: participant.userId,
          replacementFound: false,
          emergency: false,
          isNoShowWithoutContact: true,
        });
        logger.info("blindMeeting no-show finalized", {
          meetingId: meeting.meetingId,
        });
      }
    }
}

/** 종료 안전도장 안내 */
async function dispatchBlindMeetingCheckoutRemindersStep(): Promise<void> {
    const meetings = await loadMeetingsByStatuses(["in_progress"]);
    const now = Date.now();

    for (const meeting of meetings) {
      const startAt = meeting.scheduledStartAtMs;
      if (startAt == null) continue;
      // 미팅 시작 2시간 후부터 종료 도장을 안내한다.
      if (now - startAt < 2 * 60 * 60 * 1000) continue;

      const participants = await loadParticipants(meeting.meetingId);
      const pending = participants
        .filter((p) => p.checkedIn && !p.checkedOut)
        .map((p) => p.userId);
      if (pending.length === 0) continue;

      await notifyBlindMeeting({
        userIds: pending,
        meetingId: meeting.meetingId,
        kind: "checkout",
      });
    }
}

/**
 * 미팅 종료 후 약 15분 뒤 후속 대화 선택 푸시.
 *
 * 조건: 종료 예정 시간 경과 + 종료 안전도장 완료 + 심각한 신고 없음.
 */
async function openBlindMeetingFollowUpsStep(): Promise<void> {
    const policy = await loadPolicy();
    const meetings = await loadMeetingsByStatuses(["completed"]);
    const now = Date.now();

    for (const meeting of meetings) {
      const completedAt = meeting.raw.completedAt;
      if (!(completedAt instanceof Timestamp)) continue;
      if (now - completedAt.toMillis() < policy.followUpPushDelayMs) continue;
      await openFollowUp(meeting.meetingId);
    }
}

/** 후속 선택 마감 전 리마인더 (미응답자에게 최대 1회) */
async function remindBlindMeetingFollowUpsStep(): Promise<void> {
    const policy = await loadPolicy();
    const meetings = await loadMeetingsByStatuses(["followup_open"]);
    const now = Date.now();

    for (const meeting of meetings) {
      const closesAt = meeting.raw.followupClosesAt;
      if (!(closesAt instanceof Timestamp)) continue;
      const remaining = closesAt.toMillis() - now;
      if (remaining <= 0) {
        await db()
          .collection(BLIND_MEETING_COLLECTIONS.meetings)
          .doc(meeting.meetingId)
          .set({ followupClosed: true }, { merge: true });
        continue;
      }
      if (remaining > policy.followUpReminderBeforeCloseMs) continue;

      const choices = await db()
        .collection(BLIND_MEETING_COLLECTIONS.meetings)
        .doc(meeting.meetingId)
        .collection(BLIND_MEETING_COLLECTIONS.followUpChoices)
        .get();
      const submitted = new Set(
        choices.docs
          .filter((doc) => doc.data()?.submittedAt != null)
          .map((doc) => doc.id)
      );

      const participants = await loadParticipants(meeting.meetingId);
      const pending = participants
        .filter((p) => p.checkedIn && !submitted.has(p.userId))
        .map((p) => p.userId);
      if (pending.length === 0) continue;

      // 알림 idempotency key로 최대 1회만 발송된다.
      await notifyBlindMeeting({
        userIds: pending,
        meetingId: meeting.meetingId,
        kind: "follow_up_reminder",
      });
    }
}

/** 단체 채팅 lifecycle: 48시간 후 읽기 전용, 7일 후 보관 */
async function applyBlindMeetingChatLifecycleStep(): Promise<void> {
    const meetings = await loadMeetingsByStatuses([
      "completed",
      "followup_open",
      "read_only",
    ]);
    for (const meeting of meetings) {
      await applyChatLifecycle(await loadMeeting(meeting.meetingId));
    }
}

// -----------------------------------------------------------------------------
// 예약 작업 진입점
//
// 개별 스케줄러 7개를 2개로 모았다 (region당 CPU 할당량 절약).
// 모든 단계는 idempotent 하므로 실행 주기가 잦아도 중복 처리되지 않는다.
// -----------------------------------------------------------------------------

/** 10분마다 팀 구성을 재시도한다. */
export const blindMeetingMatchingTick = onSchedule(
  { schedule: "every 10 minutes", ...BLIND_MEETING_SCHEDULE_OPTIONS },
  async () => {
    await runStep("matching", runBlindMeetingMatchingStep);
  }
);

/**
 * 5분마다 미팅 lifecycle을 진행한다.
 *
 * 참석 재확인 → 도착 도장 안내 → 노쇼 확정 → 종료 도장 안내
 * → 후속 선택 개방(종료 15분 후) → 마감 전 리마인더 → 채팅 lifecycle
 */
export const blindMeetingLifecycleTick = onSchedule(
  { schedule: "every 5 minutes", ...BLIND_MEETING_SCHEDULE_OPTIONS },
  async () => {
    await runStep("attendance", dispatchBlindMeetingAttendanceChecksStep);
    await runStep("checkin", dispatchBlindMeetingCheckinRemindersStep);
    await runStep("noShow", finalizeBlindMeetingNoShowsStep);
    await runStep("checkout", dispatchBlindMeetingCheckoutRemindersStep);
    await runStep("followUpOpen", openBlindMeetingFollowUpsStep);
    await runStep("followUpReminder", remindBlindMeetingFollowUpsStep);
    await runStep("chatLifecycle", applyBlindMeetingChatLifecycleStep);
  }
);
