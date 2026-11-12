/**
 * P1-13 — server-authoritative facts for the 3:3 season meeting callables.
 *
 * The callables used to take the meeting time, the no-show grace period, the
 * safety-start state, the refund window and the deposit state from the
 * request. Every one of those now comes from a server-owned record; nothing
 * here has a client fallback. When a fact cannot be established the decision
 * fails closed.
 *
 *   value             source (writer)                                    missing / invalid
 *   participants      eventThreeVsThreeMatches/{id}.participantUids,      refuse
 *                     left/rightMemberUids (respondTeamMeetingRequest tx)
 *   chat room         chatRoomId == season_<id>, room.participantIds      refuse
 *   schedule          room.activePromise → promises/{p} (confirmed) AND   refuse (no-show),
 *                     serverState/schedule (onSeasonMeetingPromiseWritten:  "schedule pending"
 *                     the time the SERVER first observed that schedule)    (cancel)
 *   check-in          promise.safetyStamp (submitSafetyStamp only)        treated as "not checked in"
 *   grace period      SEASON_NO_SHOW_GRACE_MS (server constant)           —
 *   cancel authority  meetingGroups/{teamId}.leaderUid (team leader)      refuse
 *   deposit captured  seasonDepositIntents status captured/refund_pending  "not captured"
 *                     (server-only collection)
 *   deposit amount    SEASON_DEPOSIT_AMOUNT_KRW (server constant)         —
 *
 * The confirmed promise's dateTime is written by participants and can be
 * edited by either party, so on its own it is NOT evidence. The server-owned
 * schedule lock records when the server first saw that exact time; a no-show
 * is only eligible when that observation happened before the meeting started,
 * so moving the schedule into the past after the fact never qualifies.
 */
import { createHash } from "node:crypto";

import {
  Timestamp,
  type DocumentReference,
  type DocumentSnapshot,
  type Firestore,
  type Transaction,
} from "firebase-admin/firestore";
import { HttpsError } from "firebase-functions/v2/https";

import { dataPartitionOf } from "./playReviewAccess";
import {
  SEASON_MEETING_EVENT_TYPE,
  seasonMeetingChatRoomId,
} from "./seasonMeetingChat";
import type { SeasonCancelWindow } from "./seasonMeetingLifecycle";
import {
  canTransitionSeasonMeeting,
  type SeasonMeetingPhase,
} from "./seasonMeetingStateMachine";

/** Product policy: a no-show can be reported 15 minutes after the start. */
export const SEASON_NO_SHOW_GRACE_MS = 15 * 60 * 1000;
/** Product policy: the season deposit (seasonMeetingLifecycle contract). */
export const SEASON_DEPOSIT_AMOUNT_KRW = 5000;
export const SEASON_DEPOSIT_CURRENCY = "KRW";
const KST_OFFSET_MS = 9 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

export const SEASON_MATCHES = "eventThreeVsThreeMatches";
export const SEASON_SERVER_STATE = "serverState";
export const SEASON_SCHEDULE_LOCK_DOC = "schedule";
export const SEASON_NO_SHOW_REPORTS = "noShowReports";
export const SEASON_DEPOSIT_INTENTS = "seasonDepositIntents";
export const SEASON_CANCEL_AUDIT = "seasonMeetingCancelAudit";

export const SEASON_PHASES: ReadonlySet<string> = new Set([
  "team_forming", "team_ready", "exploring", "request_pending", "matched",
  "deposit_pending", "deposit_paid", "chat_open", "promise_set", "safety_start",
  "in_meeting", "roulette_done", "safety_end", "refund_pending", "completed",
  "cancelled", "noshow_review", "replacement_open",
]);
const PRE_MATCH_PHASES = new Set(["team_forming", "team_ready", "exploring", "request_pending"]);
const SAFETY_STARTED_PHASES = new Set(["safety_start", "in_meeting", "roulette_done", "safety_end"]);
const SCHEDULED_PROMISE_STATUSES = new Set(["confirmed", "in_progress", "completed"]);
const SAFE_ID = /^[A-Za-z0-9_-]{1,128}$/;
const CLIENT_KEY = /^[A-Za-z0-9_-]{8,64}$/;

export function requireSafeId(value: unknown, field: string): string {
  const text = typeof value === "string" ? value.trim() : "";
  if (!SAFE_ID.test(text)) throw new HttpsError("invalid-argument", `${field}_invalid`);
  return text;
}

/** A client retry key: bounded, path-safe, never used as a document id directly. */
export function requireClientKey(value: unknown, field: string): string {
  const text = typeof value === "string" ? value : "";
  if (!CLIENT_KEY.test(text)) throw new HttpsError("invalid-argument", `${field}_invalid`);
  return text;
}

/** NUL-separated digest: no delimiter collision between the parts. */
export function scopedDocId(prefix: string, parts: string[]): string {
  return prefix + createHash("sha256").update(parts.join("\u0000")).digest("hex").slice(0, 48);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string" && v.length > 0) : [];
}

/** Firestore Timestamp only — numbers / strings are ambiguous and refused. */
export function timestampMs(value: unknown): number | null {
  if (value instanceof Timestamp) return value.toMillis();
  if (isRecord(value) && typeof (value as { toMillis?: unknown }).toMillis === "function") {
    const ms = (value as { toMillis: () => number }).toMillis();
    return Number.isFinite(ms) ? ms : null;
  }
  return null;
}

export function kstDayStartMs(ms: number): number {
  return Math.floor((ms + KST_OFFSET_MS) / DAY_MS) * DAY_MS - KST_OFFSET_MS;
}

// ---------------------------------------------------------------------------
// Schedule evidence (pure)
// ---------------------------------------------------------------------------

export type ScheduleLock = { promiseId: string; meetupStartAtMs: number; observedAtMs: number };

export type ScheduleEvidence =
  | { state: "unscheduled" }
  | { state: "invalid" }
  /** A confirmed time exists but the server has not observed it yet. */
  | { state: "unobserved"; startMs: number }
  | {
    state: "observed";
    startMs: number;
    /** The server observed this exact time before the meeting started. */
    fixedBeforeStart: boolean;
    /** Every participant checked in (meetup safety stamp phase complete). */
    meetupCompleted: boolean;
    /** Participants with a server-recorded meetup stamp for THIS time. */
    checkedIn: ReadonlySet<string>;
  };

export function readScheduleLock(data: Record<string, unknown> | undefined): ScheduleLock | null {
  if (!data) return null;
  const promiseId = typeof data.promiseId === "string" ? data.promiseId : "";
  const meetupStartAtMs = typeof data.meetupStartAtMs === "number" && Number.isFinite(data.meetupStartAtMs)
    ? data.meetupStartAtMs : null;
  const observedAtMs = timestampMs(data.observedAt);
  if (!promiseId || meetupStartAtMs == null || observedAtMs == null) return null;
  return { promiseId, meetupStartAtMs, observedAtMs };
}

export function evaluateSchedule(params: {
  promiseId: string | null;
  promise: Record<string, unknown> | null;
  lock: ScheduleLock | null;
}): ScheduleEvidence {
  const { promiseId, promise, lock } = params;
  if (!promiseId || !promise) return { state: "unscheduled" };
  const status = typeof promise.status === "string" ? promise.status.toLowerCase() : "";
  if (!SCHEDULED_PROMISE_STATUSES.has(status)) return { state: "unscheduled" };
  const startMs = timestampMs(promise.dateTime);
  if (startMs == null) return { state: "invalid" };
  if (!lock || lock.promiseId !== promiseId || lock.meetupStartAtMs !== startMs) {
    return { state: "unobserved", startMs };
  }
  const stamp = isRecord(promise.safetyStamp) ? promise.safetyStamp : {};
  const stampFor = typeof stamp.stampedForDateTimeMs === "number" ? stamp.stampedForDateTimeMs : null;
  const checkedIn = new Set(stampFor === startMs ? stringList(stamp.meetupStampedUserIds) : []);
  const meetupCompleted = status === "in_progress" || status === "completed" ||
    promise.meetupCompletedAt != null || stamp.meetupCompletedAt != null;
  return { state: "observed", startMs, fixedBeforeStart: lock.observedAtMs < startMs, meetupCompleted, checkedIn };
}

// ---------------------------------------------------------------------------
// Decisions (pure)
// ---------------------------------------------------------------------------

export type NoShowDecision =
  | { ok: true; meetupStartAtMs: number }
  | { ok: false; code: "permission-denied" | "failed-precondition"; reason: string };

export function decideNoShowReport(params: {
  nowMs: number;
  phase: SeasonMeetingPhase;
  participants: ReadonlySet<string>;
  reporterUid: string;
  accusedUid: string;
  schedule: ScheduleEvidence;
}): NoShowDecision {
  const { nowMs, phase, participants, reporterUid, accusedUid, schedule } = params;
  if (!participants.has(reporterUid)) return { ok: false, code: "permission-denied", reason: "not_meeting_participant" };
  if (reporterUid === accusedUid) return { ok: false, code: "failed-precondition", reason: "self_report" };
  if (!participants.has(accusedUid)) return { ok: false, code: "failed-precondition", reason: "accused_not_participant" };
  if (phase !== "noshow_review" && !canTransitionSeasonMeeting(phase, "noshow_review")) {
    return { ok: false, code: "failed-precondition", reason: `phase_not_reportable:${phase}` };
  }
  if (schedule.state === "unscheduled") return { ok: false, code: "failed-precondition", reason: "schedule_unconfirmed" };
  if (schedule.state === "invalid") return { ok: false, code: "failed-precondition", reason: "schedule_invalid" };
  if (schedule.state === "unobserved") return { ok: false, code: "failed-precondition", reason: "schedule_not_server_observed" };
  if (!schedule.fixedBeforeStart) return { ok: false, code: "failed-precondition", reason: "schedule_fixed_after_start" };
  if (nowMs < schedule.startMs + SEASON_NO_SHOW_GRACE_MS) return { ok: false, code: "failed-precondition", reason: "before_grace" };
  if (schedule.meetupCompleted) return { ok: false, code: "failed-precondition", reason: "everyone_checked_in" };
  if (schedule.checkedIn.has(accusedUid)) return { ok: false, code: "failed-precondition", reason: "accused_checked_in" };
  return { ok: true, meetupStartAtMs: schedule.startMs };
}

export function deriveCancelWindow(params: {
  phase: SeasonMeetingPhase;
  schedule: ScheduleEvidence;
  nowMs: number;
}): SeasonCancelWindow | null {
  const { phase, schedule, nowMs } = params;
  if (PRE_MATCH_PHASES.has(phase)) return "before_match_confirmed";
  if (SAFETY_STARTED_PHASES.has(phase)) return "after_safety_start";
  if (schedule.state === "unscheduled") return "after_match_before_schedule";
  if (schedule.state !== "observed") return null; // invalid or not yet observed: fail closed
  if (schedule.meetupCompleted) return "after_safety_start";
  if (nowMs >= kstDayStartMs(schedule.startMs)) return "day_of_meetup";
  return "after_schedule_before_meetup";
}

// ---------------------------------------------------------------------------
// Transactional reads
// ---------------------------------------------------------------------------

export type SeasonMeetingContext = {
  matchRef: DocumentReference;
  match: Record<string, unknown>;
  phase: SeasonMeetingPhase;
  participants: ReadonlySet<string>;
  left: string[];
  right: string[];
  schedule: ScheduleEvidence;
};

/**
 * The server-written membership contract (same rules as the season chat
 * plan): two sides of exactly three, six distinct accounts, identical to
 * participantUids.
 */
export function resolveSeasonParticipants(match: Record<string, unknown>): {
  participantIds: string[];
  leftMemberIds: string[];
  rightMemberIds: string[];
} {
  const left = stringList(match.leftMemberUids);
  const right = stringList(match.rightMemberUids);
  const all = [...new Set(stringList(match.participantUids))].sort();
  const sides = [...new Set([...left, ...right])].sort();
  if (left.length !== 3 || right.length !== 3 || sides.length !== 6 || all.join("|") !== sides.join("|")) {
    throw new HttpsError("failed-precondition", "season_meeting_participants_invalid");
  }
  return { participantIds: all, leftMemberIds: left, rightMemberIds: right };
}

export function readSeasonPhase(match: Record<string, unknown>): SeasonMeetingPhase {
  const raw = typeof match.seasonPhase === "string" ? match.seasonPhase : "";
  if (!SEASON_PHASES.has(raw)) throw new HttpsError("failed-precondition", `season_phase_unknown:${raw || "absent"}`);
  return raw as SeasonMeetingPhase;
}

/**
 * Reads the match, its season room, the active promise and the server
 * schedule lock inside `tx`. Every read happens before the caller writes.
 */
export async function readSeasonMeetingContext(
  tx: Transaction,
  firestore: Firestore,
  meetingId: string,
): Promise<SeasonMeetingContext> {
  const matchRef = firestore.collection(SEASON_MATCHES).doc(meetingId);
  const lockRef = matchRef.collection(SEASON_SERVER_STATE).doc(SEASON_SCHEDULE_LOCK_DOC);
  const roomId = seasonMeetingChatRoomId(meetingId);
  const roomRef = firestore.collection("chat_rooms").doc(roomId);
  const [matchSnap, roomSnap, lockSnap] = await Promise.all([tx.get(matchRef), tx.get(roomRef), tx.get(lockRef)]);
  if (!matchSnap.exists) throw new HttpsError("not-found", "meeting_missing");
  const match = (matchSnap.data() ?? {}) as Record<string, unknown>;
  if (match.eventType !== SEASON_MEETING_EVENT_TYPE) {
    throw new HttpsError("failed-precondition", "season_meeting_contract_invalid");
  }
  if (match.chatRoomId !== roomId) throw new HttpsError("failed-precondition", "season_meeting_room_link_invalid");
  const resolved = resolveSeasonParticipants(match);
  const phase = readSeasonPhase(match);
  const participants = new Set(resolved.participantIds);
  if (!roomSnap.exists) throw new HttpsError("failed-precondition", "season_meeting_room_missing");
  const room = (roomSnap.data() ?? {}) as Record<string, unknown>;
  const roomParticipants = [...new Set(stringList(room.participantIds))].sort();
  if (roomParticipants.join("|") !== [...participants].sort().join("|")) {
    throw new HttpsError("failed-precondition", "season_meeting_room_participants_mismatch");
  }
  const active = isRecord(room.activePromise) ? room.activePromise : null;
  const rawPromiseId = typeof active?.promiseId === "string" ? active.promiseId : "";
  const promiseId = SAFE_ID.test(rawPromiseId) ? rawPromiseId : null;
  let promise: Record<string, unknown> | null = null;
  if (promiseId) {
    const promiseSnap: DocumentSnapshot = await tx.get(roomRef.collection("promises").doc(promiseId));
    promise = promiseSnap.exists ? ((promiseSnap.data() ?? {}) as Record<string, unknown>) : null;
  }
  const lock = readScheduleLock(lockSnap.exists ? (lockSnap.data() as Record<string, unknown>) : undefined);
  return {
    matchRef,
    match,
    phase,
    participants,
    left: resolved.leftMemberIds,
    right: resolved.rightMemberIds,
    schedule: evaluateSchedule({ promiseId, promise, lock }),
  };
}

/** Both accounts exist and share one data partition (production or review). */
export async function assertSamePartition(
  tx: Transaction,
  firestore: Firestore,
  uids: string[],
): Promise<string> {
  const snaps = await Promise.all(uids.map((uid) => tx.get(firestore.collection("users").doc(uid))));
  const partitions = new Set<string>();
  for (const snap of snaps) {
    if (!snap.exists) throw new HttpsError("failed-precondition", "season_meeting_account_missing");
    partitions.add(dataPartitionOf((snap.data() ?? {}) as Record<string, unknown>));
  }
  if (partitions.size !== 1) throw new HttpsError("failed-precondition", "season_meeting_partition_mismatch");
  const [partition] = [...partitions];
  if (partition !== "production" && partition !== "play_review") {
    throw new HttpsError("failed-precondition", "season_meeting_partition_mismatch");
  }
  return partition;
}

/**
 * Whole-meeting cancellation authority: the caller leads one of the two teams
 * (meetingGroups/{teamId}.leaderUid, else captainUid) and belongs to that side.
 * There is no individual-withdrawal lifecycle for season meetings, so an
 * ordinary member is refused rather than given one.
 */
export async function requireTeamLeader(
  tx: Transaction,
  firestore: Firestore,
  ctx: SeasonMeetingContext,
  uid: string,
): Promise<"left" | "right"> {
  const leftTeamId = typeof ctx.match.leftTeamId === "string" ? ctx.match.leftTeamId : "";
  const rightTeamId = typeof ctx.match.rightTeamId === "string" ? ctx.match.rightTeamId : "";
  if (!SAFE_ID.test(leftTeamId) || !SAFE_ID.test(rightTeamId)) {
    throw new HttpsError("permission-denied", "season_cancel_requires_team_leader");
  }
  const [leftTeam, rightTeam] = await Promise.all([
    tx.get(firestore.collection("meetingGroups").doc(leftTeamId)),
    tx.get(firestore.collection("meetingGroups").doc(rightTeamId)),
  ]);
  const leaderOf = (snap: DocumentSnapshot) => {
    const data = (snap.data() ?? {}) as Record<string, unknown>;
    const leader = typeof data.leaderUid === "string" && data.leaderUid ? data.leaderUid
      : typeof data.captainUid === "string" ? data.captainUid : "";
    return snap.exists ? leader : "";
  };
  if (leaderOf(leftTeam) === uid && ctx.left.includes(uid)) return "left";
  if (leaderOf(rightTeam) === uid && ctx.right.includes(uid)) return "right";
  throw new HttpsError("permission-denied", "season_cancel_requires_team_leader");
}

/** Captured deposits of this meeting, from the server-only intent ledger. */
export async function readCapturedDeposit(
  tx: Transaction,
  firestore: Firestore,
  meetingId: string,
): Promise<boolean> {
  const intents = await tx.get(
    firestore.collection(SEASON_DEPOSIT_INTENTS).where("meetingId", "==", meetingId).limit(50),
  );
  return intents.docs.some((doc) => ["captured", "refund_pending"].includes(String(doc.get("status") ?? "")));
}
