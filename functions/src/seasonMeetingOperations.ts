/**
 * Callable entrypoints for season meeting money/ops flows.
 * Without provider credentials these fail closed — never fake success.
 *
 * P1-13: every authoritative fact (meeting time, grace period, check-in,
 * membership, cancellation authority and window, deposit state, amount) is
 * read from server-owned records inside the transaction that acts on it
 * (seasonMeetingAuthority.ts). Request fields that used to carry those facts
 * (meetupStartAtMs, gracePeriodMs, safetyStartCompleted, window,
 * depositCaptured, expectedAmount) are ignored.
 */

import { onCall, HttpsError } from "firebase-functions/v2/https";
import type { DocumentReference, Firestore, Transaction } from "firebase-admin/firestore";
import { FieldValue } from "firebase-admin/firestore";

import { withAppCheck } from "./appCheckPolicy";
import {
  SEASON_CANCEL_AUDIT,
  SEASON_DEPOSIT_AMOUNT_KRW,
  SEASON_DEPOSIT_CURRENCY,
  SEASON_DEPOSIT_INTENTS,
  SEASON_MATCHES,
  SEASON_NO_SHOW_REPORTS,
  assertSamePartition,
  decideNoShowReport,
  deriveCancelWindow,
  readCapturedDeposit,
  readSeasonMeetingContext,
  readSeasonPhase,
  requireClientKey,
  requireSafeId,
  requireTeamLeader,
  resolveSeasonParticipants,
  scopedDocId,
} from "./seasonMeetingAuthority";
import {
  claimSeasonReplacementSeat,
  evaluateCancelRefund,
  type SeasonDepositIntent,
  type SeasonRefundDecision,
} from "./seasonMeetingLifecycle";
import type { ReplacementSeatClaim } from "./seasonMeetingConcurrency";
import {
  canTransitionSeasonMeeting,
  type SeasonMeetingPhase,
} from "./seasonMeetingStateMachine";

/**
 * FSM-checked phase transition inside the caller's transaction. A same-phase
 * call writes NOTHING: "same phase" is not "same operation", so per-operation
 * evidence (reports, audits) lives in its own deterministic documents and a
 * retry can never overwrite another event's fields.
 */
function transitionMatchSeasonPhase(
  tx: Transaction,
  matchRef: DocumentReference,
  from: SeasonMeetingPhase,
  to: SeasonMeetingPhase,
  extra: Record<string, unknown> = {},
): boolean {
  if (from === to) return false;
  if (!canTransitionSeasonMeeting(from, to)) {
    throw new HttpsError(
      "failed-precondition",
      `season_phase_transition_rejected:${from}->${to}`,
    );
  }
  tx.set(
    matchRef,
    { seasonPhase: to, ...extra, updatedAt: FieldValue.serverTimestamp() },
    { merge: true },
  );
  return true;
}

type ResolveUser = (
  auth: { uid: string; token?: Record<string, unknown> } | undefined,
) => Promise<{ userId: string }>;

const depositProviderReady = (): boolean =>
  process.env.SEASON_DEPOSIT_PROVIDER_READY === "true";

function requestData(request: { data?: unknown }): Record<string, unknown> {
  const data = request.data;
  return typeof data === "object" && data !== null && !Array.isArray(data)
    ? (data as Record<string, unknown>)
    : {};
}

/** Owner-scoped view of an intent: no other account, no provider internals. */
function intentView(intentId: string, data: Record<string, unknown>) {
  return {
    intentId,
    meetingId: String(data.meetingId ?? ""),
    amount: Number(data.amount ?? 0),
    currency: String(data.currency ?? SEASON_DEPOSIT_CURRENCY),
    status: String(data.status ?? ""),
  };
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
      const data = requestData(request);
      const meetingId = requireSafeId(data.meetingId, "meetingId");
      const idempotencyKey = requireClientKey(data.idempotencyKey, "idempotencyKey");
      // The amount is the server's. A client value may only confirm it.
      if (data.amount !== undefined && data.amount !== SEASON_DEPOSIT_AMOUNT_KRW) {
        throw new HttpsError("invalid-argument", "deposit_amount_mismatch");
      }
      if (data.currency !== undefined && data.currency !== SEASON_DEPOSIT_CURRENCY) {
        throw new HttpsError("invalid-argument", "deposit_currency_invalid");
      }
      const intentId = scopedDocId("sdi_", [
        "season_deposit_intent_v1", user.userId, meetingId, idempotencyKey,
      ]);
      const intentRef = firestore.collection(SEASON_DEPOSIT_INTENTS).doc(intentId);

      return firestore.runTransaction(async (tx) => {
        const ctx = await readSeasonMeetingContext(tx, firestore, meetingId);
        if (!ctx.participants.has(user.userId)) {
          throw new HttpsError("permission-denied", "not_meeting_participant");
        }
        const [existing, open] = await Promise.all([
          tx.get(intentRef),
          tx.get(
            firestore.collection(SEASON_DEPOSIT_INTENTS)
              .where("meetingId", "==", meetingId)
              .where("participantUid", "==", user.userId)
              .limit(20),
          ),
        ]);
        if (existing.exists) {
          const value = (existing.data() ?? {}) as Record<string, unknown>;
          if (
            value.participantUid !== user.userId ||
            value.meetingId !== meetingId ||
            value.idempotencyKey !== idempotencyKey ||
            value.amount !== SEASON_DEPOSIT_AMOUNT_KRW ||
            value.currency !== SEASON_DEPOSIT_CURRENCY
          ) {
            throw new HttpsError("failed-precondition", "deposit_intent_conflict");
          }
          return intentView(intentId, value);
        }
        const otherOpen = open.docs.some((doc) =>
          doc.id !== intentId &&
          ["created", "authorized", "captured", "refund_pending"].includes(String(doc.get("status") ?? "")));
        if (otherOpen) {
          throw new HttpsError("failed-precondition", "deposit_intent_already_open");
        }
        // The intent and the phase move together: no orphan intent in a phase
        // that does not take a deposit.
        if (ctx.phase !== "matched" && ctx.phase !== "deposit_pending") {
          throw new HttpsError(
            "failed-precondition",
            `season_phase_transition_rejected:${ctx.phase}->deposit_pending`,
          );
        }
        const intent: SeasonDepositIntent = {
          intentId,
          meetingId,
          participantUid: user.userId,
          amount: SEASON_DEPOSIT_AMOUNT_KRW,
          currency: "KRW",
          idempotencyKey,
          status: "created",
        };
        tx.create(intentRef, { ...intent, createdAt: FieldValue.serverTimestamp() });
        transitionMatchSeasonPhase(tx, ctx.matchRef, ctx.phase, "deposit_pending");
        return intentView(intentId, intent as unknown as Record<string, unknown>);
      });
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
      const data = requestData(request);
      const meetingId = requireSafeId(data.meetingId, "meetingId");
      const auditRef = firestore.collection(SEASON_CANCEL_AUDIT).doc(meetingId);

      return firestore.runTransaction(async (tx) => {
        const ctx = await readSeasonMeetingContext(tx, firestore, meetingId);
        if (!ctx.participants.has(user.userId)) {
          throw new HttpsError("permission-denied", "not_meeting_participant");
        }
        const audit = await tx.get(auditRef);
        if (ctx.phase === "cancelled") {
          // One decision per meeting. The same actor's retry gets it back;
          // nobody can replace it.
          if (audit.exists && audit.get("actorUid") === user.userId) {
            return { ok: true, refund: audit.get("refund") as SeasonRefundDecision, duplicate: true };
          }
          throw new HttpsError("failed-precondition", "season_meeting_already_cancelled");
        }
        const side = await requireTeamLeader(tx, firestore, ctx, user.userId);
        const nowMs = Date.now();
        const window = deriveCancelWindow({ phase: ctx.phase, schedule: ctx.schedule, nowMs });
        if (window == null) {
          throw new HttpsError("failed-precondition", "season_schedule_pending_server_observation");
        }
        const depositCaptured = await readCapturedDeposit(tx, firestore, meetingId);
        if (audit.exists) {
          throw new HttpsError("failed-precondition", "season_cancel_audit_conflict");
        }
        const refund = evaluateCancelRefund({ window, depositCaptured });
        // FSM first; the transition and its evidence commit together or not at all.
        transitionMatchSeasonPhase(tx, ctx.matchRef, ctx.phase, "cancelled", {
          cancelledByUserId: user.userId,
          cancelledAt: FieldValue.serverTimestamp(),
        });
        tx.create(auditRef, {
          meetingId,
          actorUid: user.userId,
          actorRole: "team_leader",
          actorSide: side,
          fromPhase: ctx.phase,
          window,
          depositCaptured,
          refund,
          // Settlement is a separate, provider-gated step that reads this
          // decision; nothing external happens inside this transaction.
          refundRequired: refund.action !== "none",
          evaluatedAtMs: nowMs,
          createdAt: FieldValue.serverTimestamp(),
        });
        return { ok: true, refund };
      });
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
      const data = requestData(request);
      const meetingId = requireSafeId(data.meetingId, "meetingId");
      const accusedUid = requireSafeId(data.accusedUid, "accusedUid");
      const reportRef = firestore
        .collection(SEASON_MATCHES).doc(meetingId)
        .collection(SEASON_NO_SHOW_REPORTS)
        .doc(scopedDocId("ns_", ["season_noshow_v1", meetingId, user.userId, accusedUid, "no_show"]));

      return firestore.runTransaction(async (tx) => {
        const ctx = await readSeasonMeetingContext(tx, firestore, meetingId);
        const nowMs = Date.now();
        const decision = decideNoShowReport({
          nowMs,
          phase: ctx.phase,
          participants: ctx.participants,
          reporterUid: user.userId,
          accusedUid,
          schedule: ctx.schedule,
        });
        if (!decision.ok) throw new HttpsError(decision.code, decision.reason);
        await assertSamePartition(tx, firestore, [user.userId, accusedUid]);
        const existing = await tx.get(reportRef);
        if (existing.exists) {
          return { status: "no_show_reported" as const, reportId: reportRef.id, duplicate: true };
        }
        // An allegation for human review — no forfeit, refund or sanction here.
        tx.create(reportRef, {
          meetingId,
          reporterUid: user.userId,
          accusedUid,
          category: "no_show",
          status: "pending_review",
          meetupStartAtMs: decision.meetupStartAtMs,
          evaluatedAtMs: nowMs,
          createdAt: FieldValue.serverTimestamp(),
        });
        const opened = transitionMatchSeasonPhase(tx, ctx.matchRef, ctx.phase, "noshow_review", {
          noShowReviewOpenedAt: FieldValue.serverTimestamp(),
          noShowReportCount: FieldValue.increment(1),
        });
        if (!opened) {
          tx.set(ctx.matchRef, {
            noShowReportCount: FieldValue.increment(1),
            updatedAt: FieldValue.serverTimestamp(),
          }, { merge: true });
        }
        return { status: "no_show_reported" as const, reportId: reportRef.id };
      });
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
      const data = requestData(request);
      const meetingId = requireSafeId(data.meetingId, "meetingId");
      const seatId = requireSafeId(data.seatId, "seatId");
      const expectedVersion = Number(data.expectedVersion);
      if (!Number.isInteger(expectedVersion)) {
        throw new HttpsError("invalid-argument", "replacement_args_invalid");
      }
      const matchRef = firestore.collection(SEASON_MATCHES).doc(meetingId);
      const seatRef = matchRef.collection("replacementSeats").doc(seatId);

      return firestore.runTransaction(async (tx) => {
        // Membership is checked in the same transaction as the claim.
        const [matchSnap, snap] = await Promise.all([tx.get(matchRef), tx.get(seatRef)]);
        if (!matchSnap.exists) throw new HttpsError("not-found", "meeting_missing");
        const match = (matchSnap.data() ?? {}) as Record<string, unknown>;
        const { participantIds } = resolveSeasonParticipants(match);
        readSeasonPhase(match);
        if (!participantIds.includes(user.userId)) {
          throw new HttpsError("permission-denied", "not_meeting_participant");
        }
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
      const data = requestData(request);
      const intentId = requireSafeId(data.intentId, "intentId");
      const refundIdempotencyKey = requireClientKey(data.refundIdempotencyKey, "refundIdempotencyKey");
      const intentRef = firestore.collection(SEASON_DEPOSIT_INTENTS).doc(intentId);

      return firestore.runTransaction(async (tx) => {
        const snap = await tx.get(intentRef);
        if (!snap.exists) {
          throw new HttpsError("not-found", "intent_missing");
        }
        const intent = (snap.data() ?? {}) as Record<string, unknown>;
        if (intent.participantUid !== user.userId) {
          throw new HttpsError("permission-denied", "not_intent_owner");
        }
        const meetingId = requireSafeId(intent.meetingId, "meetingId");
        const matchSnap = await tx.get(firestore.collection(SEASON_MATCHES).doc(meetingId));
        if (!matchSnap.exists) throw new HttpsError("not-found", "meeting_missing");
        const { participantIds } = resolveSeasonParticipants((matchSnap.data() ?? {}) as Record<string, unknown>);
        if (!participantIds.includes(user.userId)) {
          throw new HttpsError("permission-denied", "not_meeting_participant");
        }
        const processed = Array.isArray(intent.refundKeys) ? (intent.refundKeys as string[]) : [];
        if (intent.status === "refunded" || processed.includes(refundIdempotencyKey)) {
          return intentView(intentId, intent);
        }
        if (intent.status !== "captured" && intent.status !== "refund_pending") {
          throw new HttpsError("failed-precondition", "refund_status_invalid");
        }
        // The refund amount is the cancellation decision's, not the caller's.
        const audit = await tx.get(firestore.collection(SEASON_CANCEL_AUDIT).doc(meetingId));
        const decision = (audit.exists ? audit.get("refund") : null) as SeasonRefundDecision | null;
        const captured = Number(intent.amount ?? 0);
        const granted = decision?.action === "full_refund"
          ? captured
          : decision?.action === "partial_refund"
            ? Math.floor(captured * decision.ratio)
            : 0;
        if (granted <= 0) {
          throw new HttpsError("failed-precondition", "refund_not_granted_by_policy");
        }
        if (data.amount !== undefined && data.amount !== granted) {
          throw new HttpsError("invalid-argument", "refund_amount_not_granted");
        }
        tx.update(intentRef, {
          status: "refunded",
          refundedAmount: granted,
          refundKeys: [refundIdempotencyKey],
          updatedAt: FieldValue.serverTimestamp(),
        });
        return { ...intentView(intentId, intent), status: "refunded", refundedAmount: granted };
      });
    },
  );
}
