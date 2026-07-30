/**
 * 3:3 Season meeting (event team) state transition guard.
 *
 * Blind taste meeting / SlotMachineScreen is out of scope.
 * This module is pure and side-effect free for unit testing.
 */

export type SeasonMeetingPhase =
  | "team_forming"
  | "team_ready"
  | "exploring"
  | "request_pending"
  | "matched"
  | "deposit_pending"
  | "deposit_paid"
  | "chat_open"
  | "promise_set"
  | "safety_start"
  | "in_meeting"
  | "roulette_done"
  | "safety_end"
  | "refund_pending"
  | "completed"
  | "cancelled"
  | "noshow_review"
  | "replacement_open";

export type SeasonTransitionActor =
  | "member"
  | "leader"
  | "server"
  | "scheduler"
  | "operator";

const ALLOWED: Record<SeasonMeetingPhase, ReadonlySet<SeasonMeetingPhase>> = {
  team_forming: new Set(["team_ready", "cancelled"]),
  team_ready: new Set(["exploring", "cancelled"]),
  exploring: new Set(["request_pending", "team_ready", "cancelled"]),
  request_pending: new Set(["matched", "exploring", "cancelled"]),
  matched: new Set(["deposit_pending", "cancelled", "replacement_open"]),
  deposit_pending: new Set(["deposit_paid", "cancelled", "noshow_review"]),
  deposit_paid: new Set(["chat_open", "refund_pending", "cancelled"]),
  chat_open: new Set(["promise_set", "refund_pending", "cancelled"]),
  promise_set: new Set(["safety_start", "noshow_review", "cancelled"]),
  safety_start: new Set(["in_meeting", "noshow_review"]),
  in_meeting: new Set(["roulette_done", "safety_end", "noshow_review"]),
  roulette_done: new Set(["safety_end"]),
  safety_end: new Set(["refund_pending", "completed"]),
  refund_pending: new Set(["completed", "noshow_review"]),
  completed: new Set(),
  cancelled: new Set(),
  noshow_review: new Set(["replacement_open", "refund_pending", "cancelled"]),
  replacement_open: new Set(["matched", "cancelled", "team_forming"]),
};

export function canTransitionSeasonMeeting(
  from: SeasonMeetingPhase,
  to: SeasonMeetingPhase
): boolean {
  if (from === to) return true;
  return ALLOWED[from]?.has(to) === true;
}

export function assertSeasonMeetingTransition(
  from: SeasonMeetingPhase,
  to: SeasonMeetingPhase,
  actor: SeasonTransitionActor
): void {
  if (!canTransitionSeasonMeeting(from, to)) {
    throw new Error(`illegal_season_transition:${from}->${to}:actor=${actor}`);
  }
}

/** Team meeting request statuses used by teamMeetingRequest.ts */
export type TeamMeetingRequestStatus = "pending" | "accepted" | "declined";

export function canTransitionTeamMeetingRequest(
  from: TeamMeetingRequestStatus,
  to: TeamMeetingRequestStatus
): boolean {
  if (from === to) return true;
  if (from === "pending") return to === "accepted" || to === "declined";
  return false;
}
