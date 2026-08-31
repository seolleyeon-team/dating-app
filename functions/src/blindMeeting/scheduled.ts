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
  cancelMeeting,
  finalizeExpiredScheduleVotes,
  handleVacancy,
  openFollowUp,
  openGroupChatForConfirmedMeeting,
  runMatchingForAllDates,
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

/** 10분마다 대기 중인 날짜에 대해 팀 구성을 재시도한다. */
async function runBlindMeetingMatchingStep(): Promise<void> {
    const created = await runMatchingForAllDates();
    logger.info("blindMeeting scheduled matching", {
      createdMeetings: created.length,
    });
}

/** 문서에서 밀리초 타임스탬프를 읽는다 (없으면 null). */
function readMillis(raw: unknown): number | null {
  return raw instanceof Timestamp ? raw.toMillis() : null;
}

/**
 * 수락/보증금 마감 창이 지난 미팅을 정리한다.
 *
 * 초대 한 명이 응답하지 않으면 나머지 다섯 명의 신청서가 `open: false`,
 * `meetingId` 로 묶인 채 남아 재신청도 못 하고 보증금도 잡혀 있다.
 * 정책에 창(acceptanceWindowMs / depositWindowMs)이 정의돼 있는데도
 * 이를 적용하는 곳이 없어 사실상 무기한 대기였다.
 *
 * 창이 지나면 미팅을 취소한다. cancelMeeting 이 전원 환급 + 우선 재매칭으로
 * 신청서를 다시 열어준다.
 */
async function expireBlindMeetingResponseWindowsStep(): Promise<void> {
  const policy = await loadPolicy();
  const now = Date.now();
  const meetings = await loadMeetingsByStatuses([
    "awaiting_acceptance",
    "awaiting_deposits",
  ]);

  for (const meeting of meetings) {
    const raw = meeting.raw as Record<string, unknown>;
    const isDepositStage = meeting.status === "awaiting_deposits";
    // 보증금 창은 보증금 단계에 진입한 시점부터 센다.
    // depositsOpenedAt 은 이 변경 이후에 만들어진 미팅에만 있으므로,
    // 없으면 createdAt 으로 대체하지 않고 건너뛴다. 대체하면 이미 수락
    // 단계에서 시간을 다 쓴 기존 미팅이 첫 실행에 한꺼번에 취소된다
    // (보증금까지 낸 살아 있는 미팅을 없애는 쪽이 더 위험하다).
    // 대신 기준 시각을 지금으로 찍어두면 다음 창부터 정상 적용된다.
    const startedAtMs = isDepositStage
      ? readMillis(raw.depositsOpenedAt)
      : readMillis(raw.createdAt);
    if (startedAtMs == null) {
      if (isDepositStage) {
        await db()
          .collection(BLIND_MEETING_COLLECTIONS.meetings)
          .doc(meeting.meetingId)
          .set(
            { depositsOpenedAt: Timestamp.fromMillis(now) },
            { merge: true }
          );
        logger.info("blindMeeting deposit window backfilled", {
          meetingId: meeting.meetingId,
        });
      }
      continue;
    }

    const windowMs = isDepositStage
      ? policy.depositWindowMs
      : policy.acceptanceWindowMs;
    if (windowMs <= 0) continue;
    if (now - startedAtMs < windowMs) continue;

    logger.info("blindMeeting response window expired", {
      meetingId: meeting.meetingId,
      stage: meeting.status,
      waitedMs: now - startedAtMs,
    });
    // 한 미팅이 실패해도 나머지 미팅 정리는 계속한다.
    try {
      // loadMeetingsByStatuses 스냅샷은 이 루프가 도는 동안 낡을 수 있다.
      // 그 사이 마지막 보증금이 들어와 confirmed/chat_open 으로 넘어간
      // 살아 있는 미팅을 취소하지 않도록 확정 직전에 다시 읽는다.
      const fresh = await loadMeeting(meeting.meetingId);
      if (fresh.status !== meeting.status) {
        logger.info("blindMeeting response window skipped: status moved", {
          meetingId: meeting.meetingId,
        });
        continue;
      }
      await cancelMeeting(
        meeting.meetingId,
        isDepositStage ? "deposit_window_expired" : "acceptance_window_expired"
      );
    } catch (error) {
      logger.error("blindMeeting response window cleanup failed", {
        meetingId: meeting.meetingId,
        error,
      });
    }
  }
}

/**
 * 확정됐지만 단체 채팅방이 열리지 않은 미팅을 되살린다.
 *
 * 확정과 채팅방 개설은 별개 단계라, 사이에서 실패하면 미팅이 `confirmed`
 * 에서 멈춘다. 이 상태를 집어가는 스케줄이 하나도 없어서 보증금이 잡힌 채
 * 영구히 방치됐다. openGroupChatForConfirmedMeeting 은 idempotent 다.
 */
async function repairBlindMeetingGroupChatsStep(): Promise<void> {
  const meetings = await loadMeetingsByStatuses(["confirmed"]);
  for (const meeting of meetings) {
    // groupChatId 유무로 거르지 않는다. 방 id 를 쓴 뒤 chat_open 전이
    // 직전에 죽으면 confirmed + groupChatId 인 채로 멈추는데, 그 문서를
    // 건너뛰면 영영 복구되지 않는다.
    // openGroupChatForConfirmedMeeting 은 idempotent 하고 status 로 self-gate 한다.
    logger.warn("blindMeeting confirmed without open chat, repairing", {
      meetingId: meeting.meetingId,
    });
    // 구성이 손상된 미팅(3남+3녀가 아닌 경우 등)은 채팅방 생성이 거부된다.
    // 그런 미팅 하나 때문에 나머지 복구가 막히면 안 되므로 개별로 격리한다.
    try {
      await openGroupChatForConfirmedMeeting(meeting.meetingId);
    } catch (error) {
      logger.error("blindMeeting group chat repair failed", {
        meetingId: meeting.meetingId,
        error,
      });
    }
  }
}

/**
 * 약속잡기 기한이 지난 미팅을 확정한다.
 *
 * 이 단계가 lifecycle의 나머지 단계보다 먼저 돌아야 한다.
 * scheduledStartAt이 없으면 이후 단계가 모두 건너뛰어지기 때문이다.
 */
async function finalizeBlindMeetingScheduleVotesStep(): Promise<void> {
  const finalized = await finalizeExpiredScheduleVotes();
  if (finalized > 0) {
    logger.info("blindMeeting schedule auto-confirmed", { finalized });
  }
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
        // 한 참가자의 정산이 실패해도 나머지 참가자·나머지 미팅의 노쇼
        // 처리를 막으면 안 된다. 여기서 멈추면 그 사람들은 confirmed 로
        // 남아 다음 tick 에서도 계속 재시도되거나, 이미 no_show 로 바뀐
        // 사람이 채팅방에서 빠지지 못한 채 방치된다.
        try {
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
        } catch (error) {
          logger.error("blindMeeting no-show finalize failed", {
            meetingId: meeting.meetingId,
            error,
          });
        }
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
 * 약속잡기 기한 확정 → 참석 재확인 → 도착 도장 안내 → 노쇼 확정
 * → 종료 도장 안내 → 후속 선택 개방(종료 15분 후) → 마감 전 리마인더
 * → 채팅 lifecycle
 */
export const blindMeetingLifecycleTick = onSchedule(
  { schedule: "every 5 minutes", ...BLIND_MEETING_SCHEDULE_OPTIONS },
  async () => {
    await runStep("responseWindows", expireBlindMeetingResponseWindowsStep);
    await runStep("groupChatRepair", repairBlindMeetingGroupChatsStep);
    await runStep("scheduleVotes", finalizeBlindMeetingScheduleVotesStep);
    await runStep("attendance", dispatchBlindMeetingAttendanceChecksStep);
    await runStep("checkin", dispatchBlindMeetingCheckinRemindersStep);
    await runStep("noShow", finalizeBlindMeetingNoShowsStep);
    await runStep("checkout", dispatchBlindMeetingCheckoutRemindersStep);
    await runStep("followUpOpen", openBlindMeetingFollowUpsStep);
    await runStep("followUpReminder", remindBlindMeetingFollowUpsStep);
    await runStep("chatLifecycle", applyBlindMeetingChatLifecycleStep);
  }
);
