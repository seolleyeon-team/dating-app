/**
 * 3:3 블라인드 취향 미팅 — 서버 타입과 컬렉션 이름
 * 경로: functions/src/blindMeeting/types.ts
 *
 * 앱 쪽 정의와 1:1 대응한다.
 *   lib/features/blind_meeting/domain/blind_meeting_enums.dart
 *   lib/features/blind_meeting/data/blind_meeting_repository.dart
 */

export const BLIND_MEETING_COLLECTIONS = {
  meetings: "blindMeetings",
  applications: "blindMeetingApplications",
  dna: "blindMeetingDna",
  participants: "participants",
  publicProfiles: "publicProfiles",
  followUpChoices: "followUpChoices",
  feedback: "feedback",
  matchingResult: "matchingResult",
  replacementOffers: "blindMeetingReplacementOffers",
  restrictions: "blindMeetingRestrictions",
  matchHistory: "blindMeetingHistory",
  deposits: "blindMeetingDeposits",
  opsReviews: "blindMeetingOpsReviews",
  safetyFlags: "blindMeetingSafetyFlags",
  slotLocks: "blindMeetingSlotLocks",
  stats: "blindMeetingStats",
  config: "blindMeetingConfig",
} as const;

export const BLIND_MEETING_TYPE = "blindTasteMeeting";
export const LEGACY_RANDOM_MEETING_TYPE = "randomMeeting";
export const BLIND_MEETING_SCHEMA_VERSION = 2;

export type ConversationAtmosphere = "calm" | "lively" | "either";
export type ConversationInitiative = "initiator" | "adaptive" | "listener";
export type MeetingPurpose = "romance" | "friendship" | "both";
export type AlcoholCompanionPreference =
  | "allSober"
  | "lightOkay"
  | "noPreference";
export type SmokingCompanionPreference =
  | "nonSmokersOnly"
  | "noIndoorSmoking"
  | "noPreference";
export type DrinkingLevel = "none" | "sometimes" | "weekly1_2" | "often";
export type SmokingStatus = "nonSmoker" | "smoker" | "quitting";

export const CONVERSATION_ATMOSPHERES: ConversationAtmosphere[] = [
  "calm",
  "lively",
  "either",
];
export const CONVERSATION_INITIATIVES: ConversationInitiative[] = [
  "initiator",
  "adaptive",
  "listener",
];
export const MEETING_PURPOSES: MeetingPurpose[] = [
  "romance",
  "friendship",
  "both",
];
export const ALCOHOL_PREFERENCES: AlcoholCompanionPreference[] = [
  "allSober",
  "lightOkay",
  "noPreference",
];
export const SMOKING_PREFERENCES: SmokingCompanionPreference[] = [
  "nonSmokersOnly",
  "noIndoorSmoking",
  "noPreference",
];
export const DRINKING_LEVELS: DrinkingLevel[] = [
  "none",
  "sometimes",
  "weekly1_2",
  "often",
];
export const SMOKING_STATUSES: SmokingStatus[] = [
  "nonSmoker",
  "smoker",
  "quitting",
];

export type BlindMeetingStatus =
  | "application_open"
  | "forming"
  | "awaiting_acceptance"
  | "awaiting_deposits"
  | "confirmed"
  | "chat_open"
  | "schedule_confirmed"
  | "checkin_open"
  | "in_progress"
  | "completed"
  | "followup_open"
  | "read_only"
  | "archived"
  | "cancelled";

export type ParticipantStatus =
  | "applied"
  | "waitlisted"
  | "invited"
  | "accepted"
  | "deposit_pending"
  | "confirmed"
  | "cancel_requested"
  | "cancelled"
  | "replacement_pending"
  | "replaced"
  | "no_show"
  | "attended"
  | "completed"
  | "restricted";

export type DepositStatus =
  | "not_required"
  | "pending"
  | "authorized"
  | "paid"
  | "refund_pending"
  | "refunded"
  | "partially_refunded"
  | "forfeited"
  | "failed"
  | "cancelled";

export type MatchingStage =
  | "searchingCandidates"
  | "formingOwnTeam"
  | "checkingCrossTeam"
  | "awaitingConfirmation"
  | "matched"
  | "insufficientCandidates"
  | "cancelled";

/**
 * 앱 enum(camelCase)과 서버 상태(snake_case) 매핑.
 *
 * Firestore에는 앱이 읽는 camelCase 값을 저장하고, 서버 내부 로직은
 * 아래 상수를 사용한다. 두 표기를 오가는 지점을 한 곳으로 모은다.
 */
export const MEETING_STATUS_TO_APP: Record<BlindMeetingStatus, string> = {
  application_open: "applicationOpen",
  forming: "forming",
  awaiting_acceptance: "awaitingAcceptance",
  awaiting_deposits: "awaitingDeposits",
  confirmed: "confirmed",
  chat_open: "chatOpen",
  schedule_confirmed: "scheduleConfirmed",
  checkin_open: "checkinOpen",
  in_progress: "inProgress",
  completed: "completed",
  followup_open: "followupOpen",
  read_only: "readOnly",
  archived: "archived",
  cancelled: "cancelled",
};

export const PARTICIPANT_STATUS_TO_APP: Record<ParticipantStatus, string> = {
  applied: "applied",
  waitlisted: "waitlisted",
  invited: "invited",
  accepted: "accepted",
  deposit_pending: "depositPending",
  confirmed: "confirmed",
  cancel_requested: "cancelRequested",
  cancelled: "cancelled",
  replacement_pending: "replacementPending",
  replaced: "replaced",
  no_show: "noShow",
  attended: "attended",
  completed: "completed",
  restricted: "restricted",
};

export const DEPOSIT_STATUS_TO_APP: Record<DepositStatus, string> = {
  not_required: "notRequired",
  pending: "pending",
  authorized: "authorized",
  paid: "paid",
  refund_pending: "refundPending",
  refunded: "refunded",
  partially_refunded: "partiallyRefunded",
  forfeited: "forfeited",
  failed: "failed",
  cancelled: "cancelled",
};

/** 허용된 미팅 상태 전환 (앱 도메인 정의와 동일) */
export const ALLOWED_MEETING_TRANSITIONS: Record<
  BlindMeetingStatus,
  BlindMeetingStatus[]
> = {
  application_open: ["forming"],
  forming: ["awaiting_acceptance", "application_open"],
  awaiting_acceptance: ["awaiting_deposits", "forming"],
  awaiting_deposits: ["confirmed", "forming"],
  confirmed: ["chat_open"],
  chat_open: ["schedule_confirmed"],
  schedule_confirmed: ["checkin_open", "chat_open"],
  checkin_open: ["in_progress"],
  in_progress: ["completed"],
  completed: ["followup_open"],
  followup_open: ["read_only"],
  read_only: ["archived"],
  archived: [],
  cancelled: [],
};

export function canTransitionMeeting(
  from: BlindMeetingStatus,
  to: BlindMeetingStatus
): boolean {
  if (from === to) return false;
  if (from === "archived" || from === "cancelled") return false;
  if (to === "cancelled") return true;
  return (ALLOWED_MEETING_TRANSITIONS[from] ?? []).includes(to);
}

/** 참가자가 단체 채팅 멤버십을 가질 수 있는 상태 */
export const CHAT_MEMBERSHIP_STATUSES: ParticipantStatus[] = [
  "confirmed",
  "attended",
  "completed",
  "no_show",
];

export function holdsChatMembership(status: ParticipantStatus): boolean {
  return CHAT_MEMBERSHIP_STATUSES.includes(status);
}

// -----------------------------------------------------------------------------
// 파싱 헬퍼
// -----------------------------------------------------------------------------

export function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

export function asStr(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return fallback;
}

export function asTrimmedOrNull(v: unknown): string | null {
  const s = asStr(v, "").trim();
  return s.length > 0 ? s : null;
}

export function asStrArray(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of v) {
    const s = asStr(item, "").trim();
    if (s.length === 0 || seen.has(s)) continue;
    seen.add(s);
    out.push(s);
  }
  return out;
}

export function asNum(v: unknown, fallback = 0): number {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  const parsed = Number(v);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function oneOf<T extends string>(
  values: readonly T[],
  raw: unknown,
  fallback: T
): T {
  const s = asStr(raw, "").trim();
  return (values as readonly string[]).includes(s) ? (s as T) : fallback;
}

export function oneOfOrNull<T extends string>(
  values: readonly T[],
  raw: unknown
): T | null {
  const s = asStr(raw, "").trim();
  return (values as readonly string[]).includes(s) ? (s as T) : null;
}

/** 슬롯 id 형식: `2026-08-01#evening` */
export const SLOT_ID_PATTERN = /^\d{4}-\d{2}-\d{2}#(lunch|afternoon|evening|lateEvening)$/;

export function isValidSlotId(slotId: string): boolean {
  return SLOT_ID_PATTERN.test(slotId);
}

export const TIME_BLOCK_START_HOUR: Record<string, number> = {
  lunch: 12,
  afternoon: 15,
  evening: 18,
  lateEvening: 20,
};

/** 슬롯 id를 KST 기준 시작 시각(UTC Date)으로 변환한다. */
export function slotStartAt(slotId: string): Date | null {
  if (!isValidSlotId(slotId)) return null;
  const [dateKey, block] = slotId.split("#");
  const [year, month, day] = dateKey.split("-").map((p) => Number(p));
  const hour = TIME_BLOCK_START_HOUR[block];
  if (hour === undefined) return null;
  // KST(UTC+9) 기준 시각을 UTC로 환산
  return new Date(Date.UTC(year, month - 1, day, hour - 9, 0, 0));
}
