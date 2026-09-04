/**
 * 3:3 블라인드 취향 미팅 — 확정 미팅의 채팅방 개방 (idempotent)
 * 경로: functions/src/blindMeeting/meetingConfirmation.ts
 *
 * 신규 canonical 흐름에서는 createMeetingFromProposal 의 트랜잭션이 미팅
 * (confirmed)과 6인 채팅방을 함께 commit 한다. 이 모듈은 그 뒤에 오는
 * 부수 단계 — chat_open 전이, 알림 — 를 idempotent 하게 수행하며,
 * (만남 이력 recentlyMet 은 매칭이 아니라 실제 도착 안전도장 시점에
 * orchestrator.markSafetyStamp 가 기록한다 — 여기서는 쓰지 않는다.)
 * 트랜잭션 직후 실패했더라도 스케줄러(groupChatRepair)가
 * repairConfirmedMeetingGroupChat 으로 복구한다. legacy 수락 대기 미팅
 * 확정(legacyAcceptance.ts)도 같은 경로로 채팅방을 연다.
 *
 * 복구 정책 (groupChatRepair):
 *  - 3남+3녀 재검증은 확정 시점 스냅샷(미팅 participantGenders → 참가자 gender
 *    → 현재 프로필) 순의 근거로 한다 (store.resolveRosterGenderEvidence).
 *  - 근거가 없거나 불변식이 깨진 미팅은 fail-closed 로 두되, 매 tick 같은
 *    오류를 반복하지 않는다: `groupChatRepairRequired` 를 한 번만 표시하고
 *    운영 검토 문서 1건을 남긴 뒤 다음 tick 부터 건너뛴다 (repair_pending).
 *  - 일시적 오류(네트워크 등)는 표시하지 않고 다음 tick 에 재시도한다.
 */

import { FieldValue, Timestamp } from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import { notifyBlindMeeting } from "./notifications";
import {
  createOpsReview,
  db,
  ensureGroupChat,
  loadMeeting,
  loadPolicy,
  transitionMeetingStatus,
} from "./store";
import { BLIND_MEETING_COLLECTIONS } from "./types";

/**
 * 확정된 미팅에 단체 채팅방을 보장하고 `chat_open` 으로 넘긴다.
 *
 * `ensureGroupChat` 과 `transitionMeetingStatus` 모두 재실행에 안전하고,
 * 알림은 idempotency key 로 중복 발송되지 않는다. confirmed 가 아니면
 * 아무것도 하지 않고 false 를 돌려준다. 불변식 위반은 HttpsError
 * (failed-precondition) 로 던진다 — 분류는 repairConfirmedMeetingGroupChat 이 한다.
 */
export async function openGroupChatForConfirmedMeeting(
  meetingId: string
): Promise<boolean> {
  const meeting = await loadMeeting(meetingId);
  if (meeting.status !== "confirmed") return false;
  const policy = await loadPolicy();

  const roomId = await ensureGroupChat({
    meetingId,
    memberIds: meeting.participantIds,
    isAlcoholFree: meeting.isAlcoholFree,
  });

  await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId)
    .set(
      {
        groupChatId: roomId,
        // 약속잡기 기한. 지나면 서버가 제출된 투표(없으면 기준 날짜)로 확정한다.
        // 매칭 tx 가 이미 썼다면 같은 값을 유지하고, 없을 때만 채운다.
        ...(meeting.raw.scheduleVoteDeadlineAt == null
          ? {
              scheduleVoteDeadlineAt: Timestamp.fromMillis(
                Date.now() + policy.scheduleVoteWindowMs
              ),
            }
          : {}),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
  await transitionMeetingStatus(meetingId, "chat_open");

  await notifyBlindMeeting({
    userIds: meeting.participantIds,
    meetingId,
    kind: "chat_created",
    deeplinkId: roomId,
    data: { roomId },
  });
  await notifyBlindMeeting({
    userIds: meeting.participantIds,
    meetingId,
    kind: "schedule_vote",
    deeplinkId: roomId,
    data: { roomId },
  });
  return true;
}

export type GroupChatRepairOutcome =
  /** confirmed → chat_open 으로 옮겼다 (방 보장 포함) */
  | "opened"
  /** confirmed 가 아니라 할 일이 없다 (이미 chat_open 등) */
  | "not_confirmed"
  /** 근거 부족/불변식 위반 — 이번 tick 에 repair 표시 + 운영 검토 1건 */
  | "repair_required"
  /** 이미 repair 표시됨 — 운영자가 플래그를 지우기 전까지 건드리지 않음 */
  | "repair_pending"
  /** 일시적 오류 — 표시 없이 다음 tick 재시도 */
  | "retryable_error";

/** 재시도해도 결과가 바뀌지 않는 오류인지 (근거 부족·불변식 위반·문서 손상). */
function isNonRetryable(error: unknown): boolean {
  if (error instanceof HttpsError) {
    return (
      error.code === "failed-precondition" ||
      error.code === "not-found" ||
      error.code === "invalid-argument"
    );
  }
  return false;
}

function describeError(error: unknown): string {
  if (error instanceof HttpsError) {
    const details = error.details as { code?: string; violations?: string[] } | undefined;
    const parts = [error.code, error.message];
    if (details?.code) parts.push(details.code);
    if (details?.violations?.length) parts.push(details.violations.join("+"));
    return parts.join(":").slice(0, 500);
  }
  return String(error instanceof Error ? error.message : error).slice(0, 500);
}

/**
 * 스케줄러(groupChatRepair)용 복구 진입점. 위 복구 정책을 적용한다.
 *
 * idempotent: 건강한 미팅은 한 번 opened 뒤 not_confirmed, 손상 미팅은 한 번
 * repair_required 뒤 repair_pending 만 돌려주며 추가 write 를 하지 않는다.
 */
export async function repairConfirmedMeetingGroupChat(
  meetingId: string
): Promise<GroupChatRepairOutcome> {
  const ref = db().collection(BLIND_MEETING_COLLECTIONS.meetings).doc(meetingId);
  const snap = await ref.get();
  const raw = snap.data() ?? {};
  if (!snap.exists) return "not_confirmed";
  if (raw.groupChatRepairRequired === true) return "repair_pending";

  try {
    const opened = await openGroupChatForConfirmedMeeting(meetingId);
    return opened ? "opened" : "not_confirmed";
  } catch (error) {
    if (!isNonRetryable(error)) {
      logger.warn("blindMeeting group chat repair deferred (retryable)", {
        meetingId,
        error: describeError(error),
      });
      await ref.set(
        {
          groupChatRepairLastAttemptAt: FieldValue.serverTimestamp(),
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      return "retryable_error";
    }
    const reason = describeError(error);
    logger.error("blindMeeting group chat repair requires manual repair", {
      meetingId,
      reason,
    });
    await ref.set(
      {
        groupChatRepairRequired: true,
        groupChatRepairReason: reason,
        groupChatRepairFlaggedAt: FieldValue.serverTimestamp(),
        groupChatRepairLastAttemptAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
    await createOpsReview({
      meetingId,
      userId: "meeting",
      kind: "group_chat_repair",
      detail: { reason },
    });
    return "repair_required";
  }
}
