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

/**
 * 허용된 참가자 상태 전환.
 *
 * lib/features/blind_meeting/domain/blind_meeting_session.dart 의
 * allowedParticipantTransitions 와 1:1 동일해야 한다 (Dart 쪽 주석대로
 * "여기 정의된 전환 표는 서버 로직과 UI 판단의 단일 기준"). 파리티는
 * __tests__/stateMachines.test.ts 의 fingerprint 테스트가 지킨다.
 */
export const ALLOWED_PARTICIPANT_TRANSITIONS: Record<
  ParticipantStatus,
  ParticipantStatus[]
> = {
  applied: ["waitlisted", "invited", "cancelled", "restricted"],
  waitlisted: ["invited", "cancelled", "restricted"],
  invited: ["accepted", "cancelled", "waitlisted"],
  accepted: ["deposit_pending", "confirmed", "cancel_requested", "cancelled"],
  deposit_pending: ["confirmed", "cancel_requested", "cancelled"],
  confirmed: [
    "cancel_requested",
    "replacement_pending",
    "attended",
    "no_show",
    "cancelled",
  ],
  cancel_requested: ["replacement_pending", "cancelled", "confirmed"],
  replacement_pending: ["replaced", "confirmed", "cancelled"],
  replaced: [],
  cancelled: [],
  no_show: ["restricted", "attended"],
  attended: ["completed", "no_show"],
  completed: [],
  restricted: [],
};

export function canTransitionParticipant(
  from: ParticipantStatus,
  to: ParticipantStatus
): boolean {
  if (from === to) return false;
  return (ALLOWED_PARTICIPANT_TRANSITIONS[from] ?? []).includes(to);
}

/**
 * 허용된 신청서 상태 전환.
 *
 * 신청서(blindMeetingApplications/{uid})는 사용자당 하나의 문서를 미팅을
 * 넘나들며 재사용하므로 participant 와 lifecycle이 다르다:
 * - `applied` 로의 재진입 edge(재신청, 미팅 취소 후 재오픈, 거절 후 재오픈)
 * - `applied → confirmed` 는 대체 참가자 직접 합류 전용
 * cancel_requested / replacement_pending / replaced / attended 는
 * participant 전용 상태로, 신청서에는 쓰지 않는다.
 */
export const ALLOWED_APPLICATION_TRANSITIONS: Record<
  ParticipantStatus,
  ParticipantStatus[]
> = {
  applied: ["waitlisted", "invited", "confirmed", "cancelled", "restricted"],
  waitlisted: ["invited", "applied", "cancelled", "restricted"],
  invited: ["accepted", "applied", "cancelled", "no_show"],
  accepted: ["confirmed", "applied", "cancelled", "no_show"],
  deposit_pending: ["confirmed", "applied", "cancelled", "no_show"],
  confirmed: ["completed", "applied", "cancelled", "no_show"],
  cancel_requested: [],
  replacement_pending: [],
  replaced: [],
  attended: [],
  completed: ["applied"],
  cancelled: ["applied"],
  no_show: ["applied"],
  restricted: ["applied"],
};

export function canTransitionApplication(
  from: ParticipantStatus,
  to: ParticipantStatus
): boolean {
  if (from === to) return false;
  return (ALLOWED_APPLICATION_TRANSITIONS[from] ?? []).includes(to);
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

// -----------------------------------------------------------------------------
// 참여 가능 날짜 (date-only availability)
//
// 참가 신청 단계에서는 날짜만 받는다. 세부 시간은 팀 구성 후 단체 채팅방의
// 약속잡기에서 정한다. 앱 쪽 정의와 반드시 동일해야 한다.
//   lib/features/blind_meeting/domain/blind_meeting_availability.dart
// -----------------------------------------------------------------------------

/** 참여 가능 날짜를 고를 수 있는 기간 (내일 포함 총 일수) */
export const BLIND_MEETING_AVAILABILITY_WINDOW_DAYS = 21;

/** 신청 문서에 기록하는 availability 방식 */
export const BLIND_MEETING_AVAILABILITY_MODE_DATE_ONLY = "date_only";

/** 날짜 전용 선택으로 전환된 스키마 버전 */
export const BLIND_MEETING_SCHEDULE_SELECTION_VERSION = 2;

/** KST 오프셋 (ms) */
const KST_OFFSET_MS = 9 * 60 * 60 * 1000;

const MS_PER_DAY = 24 * 60 * 60 * 1000;

/** 날짜 key 형식: `2026-08-01` (KST 기준) */
export const DATE_KEY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function pad(value: number, width: number): string {
  return String(value).padStart(width, "0");
}

/** UTC anchor(Date)를 `yyyy-MM-dd`로 만든다. */
export function formatDateKey(date: Date): string {
  return `${pad(date.getUTCFullYear(), 4)}-${pad(
    date.getUTCMonth() + 1,
    2
  )}-${pad(date.getUTCDate(), 2)}`;
}

/**
 * `yyyy-MM-dd`를 UTC anchor로 변환한다.
 *
 * 형식이 틀리거나 `2026-02-30`처럼 달력에 없는 날짜면 null.
 */
export function parseDateKey(raw: unknown): Date | null {
  const text = asStr(raw, "").trim();
  if (!DATE_KEY_PATTERN.test(text)) return null;
  const [year, month, day] = text.split("-").map((p) => Number(p));
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  const date = new Date(Date.UTC(year, month - 1, day));
  if (formatDateKey(date) !== text) return null;
  return date;
}

export function isValidDateKey(raw: unknown): boolean {
  return parseDateKey(raw) != null;
}

/** [instant]가 KST에서 속하는 날짜의 UTC anchor */
export function kstDayOf(instant: Date | number): Date {
  const ms = typeof instant === "number" ? instant : instant.getTime();
  const shifted = new Date(ms + KST_OFFSET_MS);
  return new Date(
    Date.UTC(
      shifted.getUTCFullYear(),
      shifted.getUTCMonth(),
      shifted.getUTCDate()
    )
  );
}

/** 선택 가능한 첫 날짜 (KST 기준 내일) */
export function firstSelectableDate(nowMs: number): Date {
  return new Date(kstDayOf(nowMs).getTime() + MS_PER_DAY);
}

/** 선택 가능한 마지막 날짜 */
export function lastSelectableDate(nowMs: number): Date {
  return new Date(
    firstSelectableDate(nowMs).getTime() +
      (BLIND_MEETING_AVAILABILITY_WINDOW_DAYS - 1) * MS_PER_DAY
  );
}

/** 선택 가능한 날짜 key 전체 (오름차순) */
export function selectableDateKeys(nowMs: number): string[] {
  const first = firstSelectableDate(nowMs).getTime();
  const keys: string[] = [];
  for (let i = 0; i < BLIND_MEETING_AVAILABILITY_WINDOW_DAYS; i++) {
    keys.push(formatDateKey(new Date(first + i * MS_PER_DAY)));
  }
  return keys;
}

/** 서버 기준으로 선택 가능 범위 안의 날짜인지. 오늘·과거·범위 밖은 false. */
export function isDateKeyWithinWindow(raw: unknown, nowMs: number): boolean {
  const date = parseDateKey(raw);
  if (date == null) return false;
  const ms = date.getTime();
  return (
    ms >= firstSelectableDate(nowMs).getTime() &&
    ms <= lastSelectableDate(nowMs).getTime()
  );
}

/** 유효한 날짜만 남기고 중복을 제거해 오름차순 정렬한다. */
export function normalizeDateKeys(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const unique = new Set<string>();
  for (const item of raw) {
    const date = parseDateKey(item);
    if (date != null) unique.add(formatDateKey(date));
  }
  return [...unique].sort();
}

/** legacy 슬롯 id(`2026-08-01#evening`)에서 날짜 부분만 추출한다. */
export function dateKeysFromLegacySlots(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  const unique = new Set<string>();
  for (const item of raw) {
    if (isRecord(item)) {
      const date = parseDateKey(item.dateKey);
      if (date != null) unique.add(formatDateKey(date));
      continue;
    }
    const text = asStr(item, "").trim();
    if (text.length === 0) continue;
    const date = parseDateKey(text.split("#")[0].trim());
    if (date != null) unique.add(formatDateKey(date));
  }
  return [...unique].sort();
}

/** 날짜 전용 필드를 우선 읽고, 없으면 legacy 슬롯에서 날짜를 복원한다. */
export function readDateKeys(
  dateKeys: unknown,
  legacySlots: unknown
): string[] {
  const direct = normalizeDateKeys(dateKeys);
  if (direct.length > 0) return direct;
  return dateKeysFromLegacySlots(legacySlots);
}

/** 여러 참가자의 가능 날짜 교집합 (오름차순). 하나라도 비면 결과도 빈 배열. */
export function commonDateKeys(perParticipant: string[][]): string[] {
  if (perParticipant.length === 0) return [];
  const groups = perParticipant.map((group) => normalizeDateKeys(group));
  if (groups.some((group) => group.length === 0)) return [];

  let intersection: string[] = groups[0];
  for (let i = 1; i < groups.length; i++) {
    const current = new Set<string>(groups[i]);
    intersection = intersection.filter((key) => current.has(key));
    if (intersection.length === 0) return [];
  }
  return [...intersection].sort();
}

/** 슬롯 id 형식: `2026-08-01#evening` (최종 확정 시간에만 쓴다) */
export const SLOT_ID_PATTERN = /^\d{4}-\d{2}-\d{2}#(lunch|afternoon|evening|lateEvening)$/;

export function isValidSlotId(slotId: string): boolean {
  return SLOT_ID_PATTERN.test(slotId);
}

/** 슬롯 id에서 날짜 부분만 뽑는다. */
export function dateKeyOfSlotId(slotId: string): string | null {
  if (!isValidSlotId(slotId)) return null;
  return slotId.split("#")[0];
}

/**
 * 투표 기한이 지났을 때 서버가 자동 확정에 쓰는 슬롯.
 *
 * 대학생 미팅 특성상 저녁 시간대가 기본값이다.
 */
export const BLIND_MEETING_FALLBACK_TIME_BLOCK = "evening";

export function fallbackSlotIdFor(dateKey: string): string {
  return `${dateKey}#${BLIND_MEETING_FALLBACK_TIME_BLOCK}`;
}

export const TIME_BLOCKS = [
  "lunch",
  "afternoon",
  "evening",
  "lateEvening",
] as const;

/**
 * 특정 날짜에 대응하는 legacy 슬롯 id 전체.
 *
 * `requestedDateKeys`가 없는 기존 신청 문서를 날짜로 조회하기 위한 호환 쿼리에 쓴다.
 */
export function legacySlotIdsForDate(dateKey: string): string[] {
  if (!isValidDateKey(dateKey)) return [];
  return TIME_BLOCKS.map((block) => `${dateKey}#${block}`);
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
