/**
 * Callable entrypoints for season meeting money/ops flows.
 * Without provider credentials these fail closed — never fake success.
 */

import { onCall, HttpsError } from "firebase-functions/v2/https";
import type { Firestore } from "firebase-admin/firestore";
import { FieldValue } from "firebase-admin/firestore";

import { withAppCheck } from "./appCheckPolicy";
import {
  assertDepositAmount,
  evaluateCancelRefund,
  evaluateNoShowReport,
  applySeasonRefundOnce,
  claimSeasonReplacementSeat,
  type SeasonCancelWindow,
  type SeasonDepositIntent,
} from "./seasonMeetingLifecycle";
import type { ReplacementSeatClaim } from "./seasonMeetingConcurrency";
import {
  canTransitionSeasonMeeting,
  type SeasonMeetingPhase,
} from "./seasonMeetingStateMachine";

const SEASON_PHASES: ReadonlySet<string> = new Set([
  "team_forming",
  "team_ready",
  "exploring",
  "request_pending",
  "matched",
  "deposit_pending",
  "deposit_paid",
  "chat_open",
  "promise_set",
  "safety_start",
  "in_meeting",
  "roulette_done",
  "safety_end",
  "refund_pending",
  "completed",
  "cancelled",
  "noshow_review",
  "replacement_open",
]);

function readSeasonPhaseRaw(data: Record<string, unknown> | undefined): string {
  return String(data?.seasonPhase ?? "matched");
}

/**
 * eventThreeVsThreeMatches/{meetingId}의 seasonPhase를 FSM 검증과 함께
 * 단일 트랜잭션으로 전이한다. 허용되지 않는 전이는 failed-precondition.
 * from === to 재시도는 idempotent 성공으로 처리한다.
 */
async function transitionMatchSeasonPhase(
  firestore: Firestore,
  meetingId: string,
  to: SeasonMeetingPhase,
  extra: Record<string, unknown> = {},
): Promise<{ from: SeasonMeetingPhase; transitioned: boolean }> {
  const matchRef = firestore
    .collection("eventThreeVsThreeMatches")
    .doc(meetingId);
  return firestore.runTransaction(async (tx) => {
    const snap = await tx.get(matchRef);
    if (!snap.exists) {
      throw new HttpsError("not-found", "meeting_missing");
    }
    const rawFrom = readSeasonPhaseRaw(snap.data() as Record<string, unknown>);
    if (!SEASON_PHASES.has(rawFrom)) {
      // 알 수 없는 phase는 자동 복구하지 않고 명시적으로 실패시킨다 (fail-closed).
      throw new HttpsError(
        "failed-precondition",
        `season_phase_unknown:${rawFrom}`,
      );
    }
    const from = rawFrom as SeasonMeetingPhase;
    if (from === to) {
      // idempotent 재시도: phase는 그대로 두되 동반 필드는 갱신한다
      // (예: noshow_review 상태에서 추가 신고 기록).
      if (Object.keys(extra).length > 0) {
        tx.set(
          matchRef,
          { ...extra, updatedAt: FieldValue.serverTimestamp() },
          { merge: true },
        );
      }
      return { from, transitioned: false };
    }
    if (!canTransitionSeasonMeeting(from, to)) {
      throw new HttpsError(
        "failed-precondition",
        `season_phase_transition_rejected:${from}->${to}`,
      );
    }
    tx.set(
      matchRef,
      {
        seasonPhase: to,
        ...extra,
        updatedAt: FieldValue.serverTimestamp(),
      },
      { merge: true },
    );
    return { from, transitioned: true };
  });
}

type ResolveUser = (
  auth: { uid: string; token?: Record<string, unknown> } | undefined,
) => Promise<{ userId: string }>;

const depositProviderReady = (): boolean =>
  process.env.SEASON_DEPOSIT_PROVIDER_READY === "true";

async function requireSeasonMeetingParticipant(
  firestore: Firestore,
  meetingId: string,
  uid: string,
): Promise<Record<string, unknown>> {
  const snap = await firestore
    .collection("eventThreeVsThreeMatches")
    .doc(meetingId)
    .get();
  if (!snap.exists) {
    throw new HttpsError("not-found", "meeting_missing");
  }
  const data = (snap.data() ?? {}) as Record<string, unknown>;
  const participants = Array.isArray(data.participantUids)
    ? data.participantUids.map((value) => String(value))
    : Array.isArray(data.participantIds)
      ? data.participantIds.map((value) => String(value))
      : [];
  if (!participants.includes(uid)) {
    throw new HttpsError("permission-denied", "not_meeting_participant");
  }
  return data;
}

export function createSeasonMeetingDepositIntentFunction(
  firestore: Firestore,
  resolveUser: ResolveUser,
) {
  return onCall(
    withAppCheck({ region: "asia-northeast3", timeoutSeconds: 30 }),
    async (request) => {
      const user = await resolveUser(request.auth);
      if (!depositProviderReady()) {
        throw new HttpsError(
          "failed-precondition",
          "deposit_provider_not_configured",
        );
      }
      const data = (request.data ?? {}) as Record<string, unknown>;
      const meetingId = String(data.meetingId ?? "").trim();
      const amount = Number(data.amount);
      const currency = String(data.currency ?? "KRW");
      const expectedAmount = Number(data.expectedAmount ?? 5000);
      const idempotencyKey = String(data.idempotencyKey ?? "").trim();
      if (!meetingId || !idempotencyKey) {
        throw new HttpsError("invalid-argument", "deposit_args_invalid");
      }
      await requireSeasonMeetingParticipant(firestore, meetingId, user.userId);
      assertDepositAmount({ amount, expectedAmount, currency });

      const intentRef = firestore
        .collection("seasonDepositIntents")
        .doc(idempotencyKey);
      const existing = await intentRef.get();
      if (existing.exists) {
        return existing.data();
      }

      const intent: SeasonDepositIntent = {
        intentId: idempotencyKey,
        meetingId,
        participantUid: user.userId,
        amount,
        currency: "KRW",
        idempotencyKey,
        status: "created",
      };
      await intentRef.set({
        ...intent,
        createdAt: FieldValue.serverTimestamp(),
      });

      // 입금 intent 생성은 성공시키되, phase 전이는 FSM이 허용할 때만
      // 트랜잭션으로 수행한다 (전이 불가는 intent 흐름을 막지 않는다).
      try {
        await transitionMatchSeasonPhase(firestore, meetingId, "deposit_pending");
      } catch (error) {
        if (
          !(error instanceof HttpsError) ||
          error.code !== "failed-precondition"
        ) {
          throw error;
        }
      }
      return intent;
    },
  );
}

export function createSeasonMeetingCancelFunction(
  firestore: Firestore,
  resolveUser: ResolveUser,
) {
  return onCall(
    withAppCheck({ region: "asia-northeast3", timeoutSeconds: 30 }),
    async (request) => {
      const user = await resolveUser(request.auth);
      const data = (request.data ?? {}) as Record<string, unknown>;
      const meetingId = String(data.meetingId ?? "").trim();
      const window = String(data.window ?? "") as SeasonCancelWindow;
      const depositCaptured = data.depositCaptured === true;
      if (!meetingId) {
        throw new HttpsError("invalid-argument", "cancel_args_invalid");
      }
      await requireSeasonMeetingParticipant(firestore, meetingId, user.userId);
      const refund = evaluateCancelRefund({ window, depositCaptured });
      // FSM 검증이 먼저다: 전이가 거부되면 audit도 남기지 않고 실패한다.
      await transitionMatchSeasonPhase(firestore, meetingId, "cancelled", {
        cancelledByUserId: user.userId,
      });
      await firestore.collection("seasonMeetingCancelAudit").add({
        meetingId,
        actorUid: user.userId,
        window,
        refund,
        createdAt: FieldValue.serverTimestamp(),
      });
      return { ok: true, refund };
    },
  );
}

export function createSeasonMeetingReportNoShowFunction(
  firestore: Firestore,
  resolveUser: ResolveUser,
) {
  return onCall(
    withAppCheck({ region: "asia-northeast3", timeoutSeconds: 30 }),
    async (request) => {
      const user = await resolveUser(request.auth);
      const data = (request.data ?? {}) as Record<string, unknown>;
      const meetingId = String(data.meetingId ?? "").trim();
      const accusedUid = String(data.accusedUid ?? "").trim();
      const meetupStartAtMs = Number(data.meetupStartAtMs);
      const gracePeriodMs = Number(data.gracePeriodMs ?? 15 * 60 * 1000);
      const safetyStartCompleted = data.safetyStartCompleted === true;
      if (!meetingId || !accusedUid || !Number.isFinite(meetupStartAtMs)) {
        throw new HttpsError("invalid-argument", "noshow_args_invalid");
      }
      await requireSeasonMeetingParticipant(firestore, meetingId, user.userId);
      const decision = evaluateNoShowReport({
        meetingId,
        reporterUid: user.userId,
        accusedUid,
        reportedAtMs: Date.now(),
        meetupStartAtMs,
        gracePeriodMs,
        safetyStartCompleted,
      });
      if (decision.status === "no_show_rejected") {
        throw new HttpsError(
          "failed-precondition",
          decision.reason ?? "rejected",
        );
      }
      await transitionMatchSeasonPhase(firestore, meetingId, "noshow_review", {
        noShowReport: {
          reporterUid: user.userId,
          accusedUid,
          status: decision.status,
          at: FieldValue.serverTimestamp(),
        },
      });
      return decision;
    },
  );
}

export function createSeasonMeetingClaimReplacementFunction(
  firestore: Firestore,
  resolveUser: ResolveUser,
) {
  return onCall(
    withAppCheck({ region: "asia-northeast3", timeoutSeconds: 30 }),
    async (request) => {
      const user = await resolveUser(request.auth);
      const data = (request.data ?? {}) as Record<string, unknown>;
      const meetingId = String(data.meetingId ?? "").trim();
      const seatId = String(data.seatId ?? "").trim();
      const expectedVersion = Number(data.expectedVersion);
      if (!meetingId || !seatId || !Number.isInteger(expectedVersion)) {
        throw new HttpsError("invalid-argument", "replacement_args_invalid");
      }
      await requireSeasonMeetingParticipant(firestore, meetingId, user.userId);

      return firestore.runTransaction(async (tx) => {
        const seatRef = firestore
          .collection("eventThreeVsThreeMatches")
          .doc(meetingId)
          .collection("replacementSeats")
          .doc(seatId);
        const snap = await tx.get(seatRef);
        if (!snap.exists) {
          throw new HttpsError("not-found", "seat_missing");
        }
        const seat = snap.data() as ReplacementSeatClaim;
        const result = claimSeasonReplacementSeat({
          seat,
          claimantUid: user.userId,
          expectedVersion,
        });
        if (!result.ok) {
          throw new HttpsError("aborted", result.reason);
        }
        tx.set(seatRef, result.seat, { merge: true });
        return { ok: true, seat: result.seat };
      });
    },
  );
}

export function createSeasonMeetingRefundFunction(
  firestore: Firestore,
  resolveUser: ResolveUser,
) {
  return onCall(
    withAppCheck({ region: "asia-northeast3", timeoutSeconds: 30 }),
    async (request) => {
      const user = await resolveUser(request.auth);
      if (!depositProviderReady()) {
        throw new HttpsError(
          "failed-precondition",
          "deposit_provider_not_configured",
        );
      }
      const data = (request.data ?? {}) as Record<string, unknown>;
      const intentId = String(data.intentId ?? "").trim();
      const refundIdempotencyKey = String(
        data.refundIdempotencyKey ?? "",
      ).trim();
      const amount = Number(data.amount);
      if (!intentId || !refundIdempotencyKey) {
        throw new HttpsError("invalid-argument", "refund_args_invalid");
      }
      const intentRef = firestore.collection("seasonDepositIntents").doc(intentId);
      const snap = await intentRef.get();
      if (!snap.exists) {
        throw new HttpsError("not-found", "intent_missing");
      }
      const intent = snap.data() as SeasonDepositIntent;
      if (intent.participantUid !== user.userId) {
        throw new HttpsError("permission-denied", "not_intent_owner");
      }
      await requireSeasonMeetingParticipant(
        firestore,
        intent.meetingId,
        user.userId,
      );
      const processed = new Set<string>(
        Array.isArray((snap.data() as { refundKeys?: string[] }).refundKeys)
          ? ((snap.data() as { refundKeys?: string[] }).refundKeys as string[])
          : [],
      );
      const next = applySeasonRefundOnce({
        intent,
        refundIdempotencyKey,
        processedRefundKeys: processed,
        amount,
      });
      await intentRef.set(
        {
          ...next,
          refundKeys: [...processed],
          updatedAt: FieldValue.serverTimestamp(),
        },
        { merge: true },
      );
      return next;
    },
  );
}
