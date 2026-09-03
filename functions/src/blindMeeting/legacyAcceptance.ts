/**
 * 3:3 블라인드 취향 미팅 — legacy 수락 대기 미팅 정규화 (LEGACY_COMPATIBILITY_ONLY)
 * 경로: functions/src/blindMeeting/legacyAcceptance.ts
 *
 * 2026-09-03 정책 변경으로 매칭 후 참가 수락/거절 단계가 사라졌다. 매칭이
 * commit 되면 미팅은 곧바로 confirmed 이고 같은 트랜잭션에서 6인 채팅방이
 * 생긴다. 이 모듈은 그 변경 이전에 `awaiting_acceptance` 로 남아 있는
 * 미팅 문서를 새 계약(매칭 = 확정)으로 옮기는 **유일한** 자리다.
 *
 * 신규 business flow 는 이 파일을 호출하지 않는다. 호출자는
 *  - scheduled.ts 의 legacyAcceptance 단계
 *  - legacyDepositNormalizer.ts (과거 결제 대기 문서 → 확정)
 *  - orchestrator.respondReplacementOffer (legacy 수락 대기 미팅에 대체
 *    참가자가 합류해 좌석이 모두 찼을 때)
 * 뿐이다.
 *
 * fail-closed / 수락 타임아웃 없음 (FINAL RELEASE CLOSURE ②):
 *  - canonical match 가 온전할 때만 확정한다 (inspectLegacyMatch: 좌석 6,
 *    uid 6 unique, 3남+3녀, 좌석마다 invited/accepted/confirmed 참가자 문서,
 *    신청서 6개가 이 미팅에 귀속). 응답 창이 얼마나 지났는지는 판단 기준이
 *    아니다 — 사용자 수락을 다시 기다리지도, 창 만료로 취소하지도 않는다.
 *  - 대체 충원이 진행 중(replacement_pending/cancel_requested 좌석 또는 열린
 *    대체 제안)이면 replacement FSM 에 맡기고 건드리지 않는다.
 *  - 그 외(빈 좌석·좌석 수/성비 오류·문서 누락·신청서 이탈)는 취소가 아니라
 *    `legacyRepairRequired` 를 한 번만 표시하고 운영 검토 문서 1건을 남긴다.
 *    이후 tick 은 표시된 문서를 다시 건드리지 않는다.
 *  - 성비·좌석 검증은 상태 전이 **이전**에 한다 — confirmed 인데 방이 없는
 *    미팅을 만들지 않는다. 확정 시 성별 스냅샷(participantGenders)을 남겨
 *    이후 채팅방 복구가 mutable 프로필에 의존하지 않게 한다.
 *  - 참가자 write 는 store 의 FSM choke point 를 그대로 탄다
 *    (invited → accepted → confirmed, 신규 FSM edge 추가 없음).
 *  - 수락 기한/수락 창 같은 수락 단계 필드는 새로 만들지 않는다
 *    (참가자 acceptedBy 는 legacy 좌석 자동 승격 감사 표시).
 */

import { FieldValue } from "firebase-admin/firestore";
import * as logger from "firebase-functions/logger";

import {
  readBlindMeetingGender,
  validateBlindThreeVsThreeParticipants,
} from "./genderBalance";
import { openGroupChatForConfirmedMeeting } from "./meetingConfirmation";
import { notifyBlindMeeting } from "./notifications";
import {
  createOpsReview,
  db,
  loadMeeting,
  loadParticipants,
  resolveRosterGenderEvidence,
  setApplication,
  transitionMeetingStatus,
  updateParticipant,
} from "./store";
import { BLIND_MEETING_COLLECTIONS, ParticipantStatus, asStr } from "./types";

/**
 * legacy 미팅을 복구 불가로 표시한다 (fail-closed, 1회).
 * 상태는 바꾸지 않고 `legacyRepairRequired` + 운영 검토 문서만 남긴다.
 * legacyDepositNormalizer 와 공유한다.
 */
export async function markLegacyRepairRequired(
  meetingId: string,
  reasons: string[]
): Promise<void> {
  logger.error("blindMeeting legacy status repair required", {
    meetingId,
    reasons,
  });
  await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .doc(meetingId)
    .set(
      {
        legacyRepairRequired: true,
        legacyRepairReasons: reasons,
        legacyRepairFlaggedAt: FieldValue.serverTimestamp(),
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
  await createOpsReview({
    meetingId,
    userId: "meeting",
    kind: "legacy_status_repair",
    detail: { reasons },
  });
}

/** 대체 충원이 실제로 진행 중인지 (좌석 상태 또는 열린 대체 제안). */
export async function isReplacementInProgress(
  meetingId: string
): Promise<boolean> {
  const participants = await loadParticipants(meetingId);
  if (
    participants.some(
      (p) => p.status === "replacement_pending" || p.status === "cancel_requested"
    )
  ) {
    return true;
  }
  const offers = await db()
    .collection(BLIND_MEETING_COLLECTIONS.replacementOffers)
    .where("meetingId", "==", meetingId)
    .where("offerStatus", "==", "offered")
    .limit(1)
    .get();
  return offers.size > 0;
}

/** legacy 수락 대기 미팅에서 좌석을 여전히 쥐고 있는 상태 */
const LEGACY_HELD_SEAT_STATUSES = new Set<ParticipantStatus>([
  "invited",
  "accepted",
  "confirmed",
]);

/**
 * legacy 미팅의 canonical match 무결성 검사. 위반 사유 목록을 돌려준다
 * (비어 있으면 온전). legacyDepositNormalizer 와 공유한다.
 *
 * 과거 참가자 상태의 "수락 수"는 기준이 아니다 — 사용자에게 수락을 다시
 * 요구하지 않으므로 좌석이 유지되고 있는지(invited/accepted/confirmed)만 본다.
 */
export async function inspectLegacyMatch(
  meetingId: string,
  participantIds: string[]
): Promise<string[]> {
  const reasons: string[] = [];

  if (participantIds.length !== 6) {
    reasons.push("seat_count:" + participantIds.length);
  }
  if (new Set(participantIds).size !== participantIds.length) {
    reasons.push("duplicate_seat");
  }

  // 좌석마다 참가자 문서가 있고 좌석을 쥔 상태여야 한다.
  const participants = await loadParticipants(meetingId);
  const byId = new Map(participants.map((p) => [p.userId, p]));
  for (const userId of participantIds) {
    const participant = byId.get(userId);
    if (participant == null) {
      reasons.push("participant_missing");
      continue;
    }
    if (!LEGACY_HELD_SEAT_STATUSES.has(participant.status)) {
      reasons.push("participant_status:" + participant.status);
    }
  }

  // 3남 + 3녀 (authoritative users 문서 기준). 성별을 모르면 실패.
  if (participantIds.length > 0) {
    const userSnaps = await db().getAll(
      ...participantIds.map((userId) => db().collection("users").doc(userId))
    );
    const balance = validateBlindThreeVsThreeParticipants(
      participantIds.map((userId, index) => ({
        userId,
        gender: readBlindMeetingGender(userSnaps[index]?.data()),
      }))
    );
    if (!balance.ok) {
      reasons.push(
        "gender_balance:" +
          balance.violations.join("+") +
          ":m" + balance.counts.male +
          "f" + balance.counts.female +
          "u" + balance.counts.unknown
      );
    }
  }

  // 신청서 6개가 모두 이 미팅에 귀속돼 있어야 한다 (재오픈/재클레임 = 이탈).
  if (participantIds.length > 0) {
    const applicationSnaps = await db().getAll(
      ...participantIds.map((userId) =>
        db().collection(BLIND_MEETING_COLLECTIONS.applications).doc(userId)
      )
    );
    for (const snap of applicationSnaps) {
      const bound =
        snap.exists && asStr(snap.data()?.meetingId, "").trim() === meetingId;
      if (!bound) reasons.push("application_detached:" + snap.id);
    }
  }

  return reasons;
}

/**
 * legacy `awaiting_acceptance` 미팅 하나를 confirmed → chat_open 으로 옮긴다.
 *
 * canonical match 가 온전할 때만 진행한다 (아니면 false, 아무 write 없음).
 * idempotent: confirmed/chat_open 에서 다시 불러도 안전하다.
 */
export async function confirmLegacyAwaitingAcceptanceMeeting(
  meetingId: string
): Promise<boolean> {
  const meeting = await loadMeeting(meetingId);
  if (
    meeting.status !== "awaiting_acceptance" &&
    meeting.status !== "confirmed" &&
    meeting.status !== "chat_open"
  ) {
    return false;
  }
  // 상태 전이 전에 검증한다. 손상된 legacy 문서를 confirmed 로 옮겨 놓고
  // 채팅방 생성에서 막히면 "confirmed 인데 방 없음" 상태가 남는다.
  const integrity = await inspectLegacyMatch(meetingId, meeting.participantIds);
  if (integrity.length > 0) {
    logger.warn("blindMeeting legacy confirm skipped: match not intact", {
      meetingId,
      reasons: integrity,
    });
    return false;
  }
  const participants = await loadParticipants(meetingId);
  const participantsById = new Map(
    participants.map((participant) => [participant.userId, participant])
  );

  const wasAwaiting = meeting.status === "awaiting_acceptance";
  if (wasAwaiting) {
    // FSM 전이를 먼저 통과시킨다. 동시 실행이면 최신 상태를 재확인한다.
    const confirmed = await transitionMeetingStatus(meetingId, "confirmed", {
      confirmedAt: FieldValue.serverTimestamp(),
      legacyAcceptanceNormalizedAt: FieldValue.serverTimestamp(),
    });
    if (!confirmed) {
      const latest = await loadMeeting(meetingId);
      if (latest.status !== "confirmed" && latest.status !== "chat_open") {
        return false;
      }
    }
  }

  // 좌석 명부(participantIds)에 있는 여섯 명만 확정한다. 거절·대체로 빠진
  // 사람의 참가자 문서(cancelled/replaced, terminal)도 같은 subcollection 에
  // 남아 있으므로 전체를 돌면 FSM 이 거부해 확정 전체가 멈춘다.
  for (const userId of meeting.participantIds) {
    const participant = participantsById.get(userId);
    if (participant == null) continue;
    // 신청서는 아직 이 미팅에 귀속된 경우에만 따라간다. 재오픈(meetingId 없음)
    // 되거나 다른 미팅에 재클레임된 신청서에 confirmed 를 찍으면 미팅 link
    // 없는 confirmed 신청이 생긴다 (reopenApplicationIfBoundTo 와 같은 guard).
    const applicationSnap = await db()
      .collection(BLIND_MEETING_COLLECTIONS.applications)
      .doc(userId)
      .get();
    const applicationBound =
      applicationSnap.exists &&
      asStr(applicationSnap.data()?.meetingId, "").trim() === meetingId;
    if (participant.status === "invited") {
      // 수락 단계가 없어졌으므로 legacy invited 좌석은 시스템이 대신 수락한다.
      await updateParticipant(meetingId, userId, {
        status: "accepted",
        extra: { acceptedAt: FieldValue.serverTimestamp(), acceptedBy: "legacy_normalizer" },
      });
      if (applicationBound) await setApplication(userId, { status: "accepted" });
    }
    await updateParticipant(meetingId, userId, {
      status: "confirmed",
      extra: { confirmedAt: FieldValue.serverTimestamp() },
    });
    if (applicationBound) {
      await setApplication(userId, { status: "confirmed", stage: "matched" });
    } else {
      logger.warn("blindMeeting legacy confirm: application not bound, skipped", {
        meetingId,
      });
    }
  }

  if (wasAwaiting) {
    await notifyBlindMeeting({
      userIds: meeting.participantIds,
      meetingId,
      kind: "confirmed",
    });
  }

  // 확정 시점 성별 스냅샷을 고정한다 (inspectLegacyMatch 가 방금 3남+3녀를
  // 검증한 근거). 이후 채팅방 복구는 이 스냅샷을 1순위 근거로 쓴다.
  const evidence = await resolveRosterGenderEvidence(
    meetingId,
    meeting.participantIds
  );
  if (evidence.missing.length === 0) {
    const participantGenders: Record<string, string> = {};
    for (const entry of evidence.genders) {
      if (entry.gender != null) participantGenders[entry.userId] = entry.gender;
    }
    await db()
      .collection(BLIND_MEETING_COLLECTIONS.meetings)
      .doc(meetingId)
      .set(
        { participantGenders, updatedAt: FieldValue.serverTimestamp() },
        { merge: true }
      );
  }

  await openGroupChatForConfirmedMeeting(meetingId);
  return true;
}

export type LegacyAcceptanceOutcome =
  /** canonical match 온전 → confirmed → chat_open */
  | "confirmed"
  /** 대체 충원 진행 중 → replacement FSM 에 맡김 (취소·타이머 없음) */
  | "replacement_in_progress"
  /** 빈 좌석/손상 → legacyRepairRequired 1회 (취소 아님) */
  | "repair_required"
  /** 이미 repair 표시됨 → 건드리지 않음 */
  | "repair_pending"
  /** 다른 실행이 먼저 canonical 로 옮김 */
  | "not_legacy";

/**
 * legacy `awaiting_acceptance` 미팅 하나를 새 계약으로 옮긴다.
 *
 * 응답 창 만료로 취소하는 경로는 존재하지 않는다. 온전하면 확정, 대체 충원이
 * 진행 중이면 그대로 두고, 그 외는 repair 표시 1회.
 */
export async function normalizeLegacyAwaitingAcceptanceMeeting(
  meetingId: string
): Promise<LegacyAcceptanceOutcome> {
  const ref = db().collection(BLIND_MEETING_COLLECTIONS.meetings).doc(meetingId);
  const snap = await ref.get();
  const raw = snap.data();
  if (!snap.exists || raw == null) return "not_legacy";
  if (asStr(raw.serverStatus ?? raw.status, "") !== "awaiting_acceptance") {
    return "not_legacy";
  }
  if (raw.legacyRepairRequired === true) return "repair_pending";

  if (await confirmLegacyAwaitingAcceptanceMeeting(meetingId)) {
    return "confirmed";
  }
  // 확정 경로가 false 를 돌려줬다 = 동시 실행이 먼저 옮겼거나 match 가 온전하지 않다.
  const latest = (await ref.get()).data();
  if (asStr(latest?.serverStatus ?? latest?.status, "") !== "awaiting_acceptance") {
    return "not_legacy";
  }
  if (await isReplacementInProgress(meetingId)) {
    return "replacement_in_progress";
  }
  const meeting = await loadMeeting(meetingId);
  const reasons = await inspectLegacyMatch(meetingId, meeting.participantIds);
  await markLegacyRepairRequired(
    meetingId,
    reasons.length > 0 ? reasons : ["confirm_declined_by_fsm"]
  );
  return "repair_required";
}

/**
 * 스케줄러용: 아직 `awaiting_acceptance` 로 남은 legacy 미팅을 모두 새 계약으로
 * 옮긴다. 한 미팅의 실패가 나머지를 막지 않는다.
 */
export async function repairLegacyAwaitingAcceptanceMeetings(): Promise<
  { meetingId: string; outcome: LegacyAcceptanceOutcome }[]
> {
  const snap = await db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .where("serverStatus", "==", "awaiting_acceptance")
    .get();
  const results: { meetingId: string; outcome: LegacyAcceptanceOutcome }[] = [];
  for (const doc of snap.docs) {
    try {
      const outcome = await normalizeLegacyAwaitingAcceptanceMeeting(doc.id);
      results.push({ meetingId: doc.id, outcome });
    } catch (error) {
      logger.error("blindMeeting legacy acceptance normalization failed", {
        meetingId: doc.id,
        error,
      });
    }
  }
  return results;
}
