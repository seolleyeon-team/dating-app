/**
 * 3:3 블라인드 취향 미팅 — 운영(관리자) callable
 * 경로: functions/src/blindMeeting/ops.ts
 *
 * 권한 판정은 클라이언트 필드가 아니라 Firebase Auth custom claim
 * (`admin: true`) 으로만 수행한다. 일반 앱 route와 완전히 분리되어 있다.
 *
 * 운영자 계정에 claim을 부여하는 절차는
 * docs/blind_meeting_operations.md 를 참고한다.
 */

import { FieldValue, Timestamp } from "firebase-admin/firestore";
import { HttpsError, onCall } from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import { refundDeposit } from "./payments";
import { loadPolicy, refundAmountForOps } from "./opsHelpers";
import { BLIND_MEETING_CALLABLE_OPTIONS } from "./runtime";
import {
  applyRestriction,
  db,
  loadMeeting,
  loadParticipants,
  updateParticipant,
} from "./store";
import { cancelMeeting, handleVacancy, runMatchingForSlot } from "./orchestrator";
import {
  BLIND_MEETING_COLLECTIONS,
  asNum,
  asStr,
  asTrimmedOrNull,
  isRecord,
} from "./types";

type AdminRequest = {
  auth?: { uid?: string; token?: Record<string, unknown> } | null;
  data?: unknown;
};

/** 관리자 custom claim 검증 */
function requireAdmin(request: AdminRequest): string {
  const uid = request.auth?.uid;
  const token = request.auth?.token ?? {};
  if (!uid) {
    throw new HttpsError("unauthenticated", "로그인이 필요해요.");
  }
  if (token.admin !== true && token.blindMeetingOps !== true) {
    logger.warn("blindMeeting ops access denied");
    throw new HttpsError("permission-denied", "운영 권한이 없어요.");
  }
  return uid;
}

function getData(request: AdminRequest): Record<string, unknown> {
  return isRecord(request.data) ? request.data : {};
}

/** 상태별 미팅 목록 */
async function listBlindMeetingsForOpsHandler(request: AdminRequest) {
  requireAdmin(request);
  const data = getData(request);
  const status = asTrimmedOrNull(data.serverStatus);
  const limit = Math.min(100, Math.max(1, Math.floor(asNum(data.limit, 50))));

  let query = db()
    .collection(BLIND_MEETING_COLLECTIONS.meetings)
    .orderBy("createdAt", "desc")
    .limit(limit);
  if (status) {
    query = db()
      .collection(BLIND_MEETING_COLLECTIONS.meetings)
      .where("serverStatus", "==", status)
      .orderBy("createdAt", "desc")
      .limit(limit);
  }

  const snap = await query.get();
  return {
    meetings: snap.docs.map((doc) => {
      const raw = doc.data();
      return {
        meetingId: doc.id,
        serverStatus: asStr(raw.serverStatus, ""),
        slotId: asStr(raw.slotId, ""),
        isAlcoholFree: raw.isAlcoholFree === true,
        algorithmVersion: asStr(raw.algorithmVersion, ""),
        participantCount: Array.isArray(raw.participantIds)
          ? raw.participantIds.length
          : 0,
        groupChatId: asTrimmedOrNull(raw.groupChatId),
        fivePersonExceptionApproved: raw.fivePersonExceptionApproved === true,
      };
    }),
  };
}

/** 미팅 상세: 참가자, 대기자, 대체 제안, 환급, 안전 flag, 점수 요약 */
async function getBlindMeetingOpsDetailHandler(request: AdminRequest) {
  requireAdmin(request);
  const data = getData(request);
  const meetingId = asTrimmedOrNull(data.meetingId);
  if (!meetingId) {
    throw new HttpsError("invalid-argument", "meetingId가 필요해요.");
  }

  const meeting = await loadMeeting(meetingId);
  const participants = await loadParticipants(meetingId);

  const [offers, deposits, safety, scores, feedback] = await Promise.all([
    db()
      .collection(BLIND_MEETING_COLLECTIONS.replacementOffers)
      .where("meetingId", "==", meetingId)
      .get(),
    db()
      .collection(BLIND_MEETING_COLLECTIONS.deposits)
      .where("meetingId", "==", meetingId)
      .get(),
    db()
      .collection(BLIND_MEETING_COLLECTIONS.safetyFlags)
      .doc(meetingId)
      .get(),
    db()
      .collection(BLIND_MEETING_COLLECTIONS.meetings)
      .doc(meetingId)
      .collection(BLIND_MEETING_COLLECTIONS.matchingResult)
      .doc("summary")
      .get(),
    db()
      .collection(BLIND_MEETING_COLLECTIONS.meetings)
      .doc(meetingId)
      .collection(BLIND_MEETING_COLLECTIONS.feedback)
      .get(),
  ]);

  return {
    meeting: {
      meetingId,
      serverStatus: meeting.status,
      slotId: meeting.slotId,
      isAlcoholFree: meeting.isAlcoholFree,
      algorithmVersion: meeting.algorithmVersion,
      groupChatId: meeting.groupChatId,
      waitlistIds: meeting.waitlistIds,
      fivePersonExceptionApproved: meeting.fivePersonExceptionApproved,
    },
    participants: participants.map((p) => ({
      userId: p.userId,
      team: p.team,
      status: p.status,
      depositStatus: p.depositStatus,
      attendance24h: p.attendance24h,
      attendance3h: p.attendance3h,
      checkedIn: p.checkedIn,
      checkedOut: p.checkedOut,
      isReplacement: p.isReplacement,
    })),
    replacementOffers: offers.docs.map((doc) => ({
      offerId: doc.id,
      candidateUid: asStr(doc.data().candidateUid, ""),
      offerStatus: asStr(doc.data().offerStatus, ""),
      qualityRatio: asNum(doc.data().qualityRatio, 0),
    })),
    deposits: deposits.docs.map((doc) => ({
      userId: asStr(doc.data().userId, ""),
      status: asStr(doc.data().status, ""),
      amount: asNum(doc.data().amount, 0),
      refundedAmount: asNum(doc.data().refundedAmount, 0),
      sandbox: doc.data().sandbox === true,
    })),
    safetyFlags: safety.data() ?? null,
    scoreSummary: scores.data() ?? null,
    feedbackCount: feedback.size,
  };
}

/** 수동 재매칭: 참가자를 다시 후보군으로 돌리고 매칭을 재시도한다. */
async function forceBlindMeetingRematchHandler(request: AdminRequest) {
  const adminUid = requireAdmin(request);
  const data = getData(request);
  const meetingId = asTrimmedOrNull(data.meetingId);
  if (!meetingId) {
    throw new HttpsError("invalid-argument", "meetingId가 필요해요.");
  }
  const meeting = await loadMeeting(meetingId);
  await cancelMeeting(meetingId, `ops_rematch:${adminUid}`);
  const created = await runMatchingForSlot(meeting.slotId);
  logger.info("blindMeeting ops forced rematch", {
    meetingId,
    createdMeetings: created.length,
  });
  return { ok: true, createdMeetings: created.length };
}

/** 운영자 예외 환급 */
async function overrideBlindMeetingRefundHandler(request: AdminRequest) {
  const adminUid = requireAdmin(request);
  const data = getData(request);
  const meetingId = asTrimmedOrNull(data.meetingId);
  const userId = asTrimmedOrNull(data.userId);
  const basisPoints = Math.floor(asNum(data.refundBasisPoints, -1));
  if (!meetingId || !userId) {
    throw new HttpsError("invalid-argument", "meetingId와 userId가 필요해요.");
  }
  if (basisPoints < 0 || basisPoints > 10000) {
    throw new HttpsError(
      "invalid-argument",
      "refundBasisPoints는 0~10000 이어야 해요."
    );
  }

  const policy = await loadPolicy();
  const refundAmount = refundAmountForOps(policy.depositAmount, basisPoints);
  const result = await refundDeposit({
    meetingId,
    userId,
    depositAmount: policy.depositAmount,
    refundAmount,
    reason: `ops_override:${adminUid}`,
  });

  await updateParticipant(meetingId, userId, {
    depositStatus: result.status,
    extra: {
      refundOutcome: "ops_override",
      refundedAmount: result.refundedAmount,
      refundOverriddenBy: adminUid,
    },
  });

  return {
    ok: true,
    status: result.status,
    refundedAmount: result.refundedAmount,
    sandbox: result.sandbox,
    message: result.message ?? null,
  };
}

/** 참여 제한 부여/해제 */
async function setBlindMeetingRestrictionHandler(request: AdminRequest) {
  const adminUid = requireAdmin(request);
  const data = getData(request);
  const userId = asTrimmedOrNull(data.userId);
  const days = Math.floor(asNum(data.days, -1));
  if (!userId || days < 0) {
    throw new HttpsError("invalid-argument", "userId와 days가 필요해요.");
  }
  await applyRestriction({
    userId,
    days,
    reason: `ops:${adminUid}:${asStr(data.reason, "manual")}`,
    requiresOpsReview: false,
  });
  return { ok: true };
}

/** 노쇼 수동 처리: 대체 후보 탐색을 다시 시작한다. */
async function triggerBlindMeetingReplacementHandler(request: AdminRequest) {
  requireAdmin(request);
  const data = getData(request);
  const meetingId = asTrimmedOrNull(data.meetingId);
  const userId = asTrimmedOrNull(data.userId);
  if (!meetingId || !userId) {
    throw new HttpsError("invalid-argument", "meetingId와 userId가 필요해요.");
  }
  const offered = await handleVacancy({
    meetingId,
    vacantUserId: userId,
    urgent: data.urgent === true,
  });
  return { ok: true, offered };
}

/** 운영 검토 종료 */
async function resolveBlindMeetingOpsReviewHandler(request: AdminRequest) {
  const adminUid = requireAdmin(request);
  const data = getData(request);
  const reviewId = asTrimmedOrNull(data.reviewId);
  if (!reviewId) {
    throw new HttpsError("invalid-argument", "reviewId가 필요해요.");
  }
  await db()
    .collection(BLIND_MEETING_COLLECTIONS.opsReviews)
    .doc(reviewId)
    .set(
      {
        status: "resolved",
        resolvedBy: adminUid,
        resolution: asStr(data.resolution, ""),
        resolvedAt: FieldValue.serverTimestamp(),
      },
      { merge: true }
    );
  return { ok: true };
}

/** 알림 발송 상태 확인 */
async function listBlindMeetingNotificationDispatchesHandler(request: AdminRequest) {
    requireAdmin(request);
    const data = getData(request);
    const meetingId = asTrimmedOrNull(data.meetingId);
    if (!meetingId) {
      throw new HttpsError("invalid-argument", "meetingId가 필요해요.");
    }
    const snap = await db()
      .collection("notificationDispatchLog")
      .orderBy("createdAt", "desc")
      .limit(200)
      .get();
    const dispatches = snap.docs
      .filter((doc) => doc.id.includes(meetingId))
      .map((doc) => {
        const createdAt = doc.data().createdAt;
        return {
          key: doc.id,
          type: asStr(doc.data().type, ""),
          createdAtMs:
            createdAt instanceof Timestamp ? createdAt.toMillis() : null,
        };
      });
    return { dispatches };
}

// -----------------------------------------------------------------------------
// 운영 dispatcher
//
// 운영 callable도 단일 함수로 모은다 (region당 CPU 할당량 절약).
// 권한 판정은 각 handler의 requireAdmin이 claim으로 수행한다.
// -----------------------------------------------------------------------------

type OpsHandler = (request: AdminRequest) => Promise<Record<string, unknown>>;

const OPS_HANDLERS: Record<string, OpsHandler> = {
  listBlindMeetingsForOps: listBlindMeetingsForOpsHandler,
  getBlindMeetingOpsDetail: getBlindMeetingOpsDetailHandler,
  forceBlindMeetingRematch: forceBlindMeetingRematchHandler,
  overrideBlindMeetingRefund: overrideBlindMeetingRefundHandler,
  setBlindMeetingRestriction: setBlindMeetingRestrictionHandler,
  triggerBlindMeetingReplacement: triggerBlindMeetingReplacementHandler,
  resolveBlindMeetingOpsReview: resolveBlindMeetingOpsReviewHandler,
  listBlindMeetingNotificationDispatches:
    listBlindMeetingNotificationDispatchesHandler,
};

export const BLIND_MEETING_OPS_ACTIONS = Object.keys(OPS_HANDLERS);

export const blindMeetingOps = onCall(
  BLIND_MEETING_CALLABLE_OPTIONS,
  async (request) => {
    const data = getData(request);
    const action = asStr(data.action, "");
    const handler = OPS_HANDLERS[action];
    if (!handler) {
      throw new HttpsError("invalid-argument", "지원하지 않는 운영 요청이에요.");
    }
    logger.info("blindMeetingOps", { action });
    return handler(request);
  }
);
