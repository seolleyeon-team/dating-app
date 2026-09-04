/**
 * 3:3 블라인드 취향 미팅 — legacy 결제 대기 문서 복구 (LEGACY_STATE_NORMALIZATION)
 * 경로: functions/src/blindMeeting/legacyDepositNormalizer.ts
 *
 * 블라인드 미팅에는 보증금도, 매칭 후 수락/거절 단계도 없다 (2026-09-03).
 * 매칭이 commit 되면 미팅은 곧바로 confirmed 이고 6인 채팅방이 함께 생긴다.
 *
 * 이 모듈은 그 이전에 만들어져 Firestore 에 `awaiting_deposits` 로 남아 있는
 * 미팅 문서를 새 계약으로 옮기는 **유일한** 경로다.
 *  - 결제를 요구하거나 결제 화면으로 보내지 않는다.
 *  - 폐기된 수락 대기 상태(awaiting_acceptance)나 수락 창을 다시 만들지 않는다.
 *  - 과거 참가자 상태(invited/accepted/deposit_pending)의 "수락 수"를 세지 않는다.
 *    사용자에게 수락을 다시 요구하지 않으므로 판단 기준은 오직 canonical match
 *    의 온전함이다.
 *
 * 판정:
 *  - canonical match 온전 (좌석 6, uid 6 unique, 3남+3녀, 좌석마다 참가자 문서가
 *    있고 좌석을 쥔 상태, 신청서 6개가 이 미팅에 귀속)
 *      → legacyAcceptance 의 FSM 경로로 confirmed → 채팅방 → chat_open
 *  - 그 외 (좌석 부족/중복, 성비 오류, 참가자 문서 누락, 빈 좌석, 신청서 이탈,
 *    확정 전 미팅에 있을 수 없는 참가자 상태)
 *      → 상태는 그대로 두고 legacyRepairRequired + 운영 검토 문서 1건 (fail-closed).
 *        이후 tick 은 표시된 문서를 다시 건드리지 않는다.
 */

import { FieldValue } from "firebase-admin/firestore";
import * as logger from "firebase-functions/logger";

import {
  LEGACY_MEETING_STATUS_AWAITING_DEPOSITS,
  isLegacyAwaitingDepositsStatus,
} from "./legacyDepositStatus";
import {
  confirmLegacyAwaitingAcceptanceMeeting,
  inspectLegacyMatch,
  isReplacementInProgress,
  markLegacyRepairRequired as markRepairRequired,
} from "./legacyAcceptance";
import { db, readMeetingDoc } from "./store";
import { BLIND_MEETING_COLLECTIONS, asStr } from "./types";

export type LegacyNormalizationOutcome =
  | "not_legacy"
  | "confirmed"
  /** 대체 충원 진행 중 — 취소·표시 없이 replacement FSM 에 맡긴다 */
  | "replacement_in_progress"
  | "repair_required"
  /** 이미 repair 표시가 된 문서. 운영자가 손보기 전까지 다시 건드리지 않는다. */
  | "repair_pending";

/**
 * legacy `awaiting_deposits` 미팅 하나를 새 계약으로 옮긴다.
 *
 * idempotent: 이미 canonical 상태면 `not_legacy`, 이미 repair 표시면
 * `repair_pending` 을 돌려주고 아무것도 쓰지 않는다.
 */
export async function repairLegacyMeetingStatus(
  meetingId: string
): Promise<LegacyNormalizationOutcome> {
  const ref = db().collection(BLIND_MEETING_COLLECTIONS.meetings).doc(meetingId);
  const snap = await ref.get();
  const raw = snap.data();
  if (!snap.exists || raw == null) return "not_legacy";

  const rawStatus = asStr(raw.serverStatus ?? raw.status, "");
  if (!isLegacyAwaitingDepositsStatus(rawStatus)) return "not_legacy";

  // 이미 repair 표시된 문서는 운영자가 플래그를 지우기 전까지 매 tick 마다
  // 다시 로그·검토 문서를 쓰지 않는다 (상태는 여전히 legacy 그대로 둔다).
  if (raw.legacyRepairRequired === true) return "repair_pending";

  const meeting = readMeetingDoc(meetingId, raw);
  if (meeting == null) {
    await markRepairRequired(meetingId, ["meeting_unreadable"]);
    return "repair_required";
  }

  const reasons = await inspectLegacyMatch(meeting);
  if (reasons.length > 0) {
    // 대체 충원이 진행 중이면 손상이 아니라 진행 중인 상태다. legacyAcceptance
    // 와 같은 판단을 해서 두 legacy 경로가 서로 다른 결론을 내지 않게 한다.
    if (await isReplacementInProgress(meetingId)) {
      logger.info("blindMeeting legacy deposit doc left to the replacement FSM", {
        meetingId,
      });
      return "replacement_in_progress";
    }
    await markRepairRequired(meetingId, reasons);
    return "repair_required";
  }

  try {
    // canonical match 가 온전하다. 새 계약(매칭 = 확정)대로 legacy 확정 경로를
    // 탄다: FSM 전이 → 좌석 6개 confirmed → 채팅방(3남+3녀 재검증) → chat_open.
    const confirmed = await confirmLegacyAwaitingAcceptanceMeeting(meetingId);
    if (confirmed) {
      await ref.set(
        {
          legacyStatusNormalizedAt: FieldValue.serverTimestamp(),
          legacyStatusNormalizedFrom: LEGACY_MEETING_STATUS_AWAITING_DEPOSITS,
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true }
      );
      logger.info("blindMeeting legacy status normalized to confirmed", {
        meetingId,
      });
      return "confirmed";
    }
  } catch (error) {
    await markRepairRequired(meetingId, [
      `confirm_failed:${error instanceof Error ? error.message : String(error)}`,
    ]);
    return "repair_required";
  }

  // 확정 경로가 false 를 돌려줬다 = 동시 실행이 먼저 옮겼거나 좌석이 그 사이
  // 바뀌었다. 최신 상태가 canonical 이면 no-op, 여전히 legacy 면 repair.
  const latest = await ref.get();
  const latestStatus = asStr(
    latest.data()?.serverStatus ?? latest.data()?.status,
    ""
  );
  if (!isLegacyAwaitingDepositsStatus(latestStatus)) return "not_legacy";
  if (latest.data()?.legacyRepairRequired === true) return "repair_pending";
  await markRepairRequired(meetingId, ["confirm_declined_by_fsm"]);
  return "repair_required";
}

/** 스케줄러용: legacy 상태로 남은 미팅을 모두 복구한다. */
export async function repairLegacyMeetingStatuses(): Promise<
  { meetingId: string; outcome: LegacyNormalizationOutcome }[]
> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .where("serverStatus", "==", LEGACY_MEETING_STATUS_AWAITING_DEPOSITS)
    .get();
  const results: { meetingId: string; outcome: LegacyNormalizationOutcome }[] =
    [];
  for (const doc of snap.docs) {
    try {
      const outcome = await repairLegacyMeetingStatus(doc.id);
      results.push({ meetingId: doc.id, outcome });
    } catch (error) {
      // 한 문서가 실패해도 나머지 복구는 계속한다.
      logger.error("blindMeeting legacy normalization failed", {
        meetingId: doc.id,
        error,
      });
    }
  }
  return results;
}
