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
  // 30H를 차감했지만 아직 최종 신청하지 않은 DNA 작성 진행 상태.
  // 신청 문서와 분리해 매칭 후보군에 노출되지 않도록 한다.
  dnaDrafts: "blindMeetingDnaDrafts",
  parties: "blindMeetingParties",
  partyInvites: "blindMeetingPartyInvites",
  partyMatching: "blindMeetingPartyMatching",
  partyMemberships: "blindMeetingPartyMemberships",
  participants: "participants",
  publicProfiles: "publicProfiles",
  followUpChoices: "followUpChoices",
  feedback: "feedback",
  matchingResult: "matchingResult",
  replacementOffers: "blindMeetingReplacementOffers",
  restrictions: "blindMeetingRestrictions",
  matchHistory: "blindMeetingHistory",
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

/**
 * 미팅 상태.
 *
 * 신규 canonical 흐름 (2026-09-03, 수락 단계 제거):
 *   (매칭 tx) → confirmed → chat_open → schedule_confirmed → …
 * 매칭이 commit 되는 순간 미팅은 confirmed 로 태어나고 같은 트랜잭션에서
 * 6인 채팅방이 만들어진다. 사용자에게 참가 수락/거절을 묻는 단계는 없다.
 *
 * `application_open` / `forming` / `awaiting_acceptance` 는
 * LEGACY_COMPATIBILITY_ONLY 다: 신규 business flow 는 이 값을 쓰지 않고,
 * 과거 문서를 읽고 legacyAcceptance.ts 가 canonical 상태로 옮길 때만 쓴다.
 */
export type BlindMeetingStatus =
  | "application_open"
  | "forming"
  | "awaiting_acceptance"
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

/**
 * 참가자/신청서 상태.
 *
 * `invited` / `accepted` 는 LEGACY_COMPATIBILITY_ONLY 다. 신규 매칭은
 * 참가자와 신청서를 곧바로 `confirmed` 로 쓴다 (수락 단계 없음).
 */
export type ParticipantStatus =
  | "applied"
  | "waitlisted"
  | "invited"
  | "accepted"
  | "confirmed"
  | "cancel_requested"
  | "cancelled"
  | "replacement_pending"
  | "replaced"
  | "no_show"
  | "attended"
  | "completed"
  | "restricted";

/**
 * 신청서 대기 단계. `awaitingConfirmation` 은 LEGACY_COMPATIBILITY_ONLY
 * (수락 단계가 있던 시절의 값, 신규 write 없음).
 */
export type MatchingStage =
  | "waitingForPartyMembers"
  | "waitingForCommonDates"
  | "searchingCandidates"
  | "formingOwnTeam"
  | "checkingCrossTeam"
  | "awaitingConfirmation"
  | "matched"
  | "insufficientCandidates"
  | "cancelled";

/**
 * 신규 business flow 가 더 이상 쓰지 않는 상태 (LEGACY_COMPATIBILITY_ONLY).
 * 파서/FSM 표에는 남겨 과거 문서를 읽되, 신규 write 는 소스 스캔 테스트
 * (__tests__/noAcceptance.test.ts) 가 0건으로 고정한다.
 */
export const LEGACY_ONLY_MEETING_STATUSES: readonly BlindMeetingStatus[] = [
  "application_open",
  "forming",
  "awaiting_acceptance",
];
export const LEGACY_ONLY_PARTICIPANT_STATUSES: readonly ParticipantStatus[] = [
  "invited",
  "accepted",
];
export const LEGACY_ONLY_MATCHING_STAGES: readonly MatchingStage[] = [
  "awaitingConfirmation",
];

/**
 * 신청 취소가 이미 매칭된 신청에 도착했을 때의 deterministic 코드.
 * HttpsError(failed-precondition) 의 message 와 details.code 양쪽에 실린다.
 * 앱은 이 코드를 보고 현재 매칭 결과/채팅으로 복구한다.
 */
export const CANCEL_ALREADY_MATCHED_CODE = "CANNOT_CANCEL_ALREADY_MATCHED";

/**
 * 사용자가 직접 "신청 취소" 할 수 있는 신청 상태 (매칭 전 open pool).
 * 매칭 이후(confirmed 등)에는 신청 취소가 아니라 미팅 화면의
 * 참가 취소 요청(requestCancellation) 경로만 존재한다.
 */
export const CANCELLABLE_APPLICATION_STATUSES: readonly ParticipantStatus[] = [
  "applied",
  "waitlisted",
];

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

/** 허용된 미팅 상태 전환 (앱 도메인 정의와 동일) */
export const ALLOWED_MEETING_TRANSITIONS: Record<
  BlindMeetingStatus,
  BlindMeetingStatus[]
> = {
  // application_open / forming / awaiting_acceptance 는 legacy 문서 전용
  // edge 다. 신규 미팅은 매칭 tx 안에서 confirmed 로 생성된다.
  application_open: ["forming"],
  forming: ["awaiting_acceptance", "application_open"],
  // legacy 수락 대기 미팅은 legacyAcceptance.ts 가 곧바로 확정한다
  // (수락 단계 없음). 과거 결제 대기 상태는 legacyDepositStatus.ts 가
  // 읽기 시점에 정규화한다.
  awaiting_acceptance: ["confirmed", "forming"],
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
  accepted: ["confirmed", "cancel_requested", "cancelled"],
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
  // 노쇼는 본인이 되돌릴 수 없다. 예전에는 attended 로 가는 edge 가 있어서
  // 노쇼 처리된 참가자가 도착 안전도장을 눌러 스스로 attended 로 복귀하고
  // (공개 신뢰 카운터까지 올린 채) 룰렛 알림도 되살릴 수 있었다.
  no_show: ["restricted"],
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

/**
 * 미팅 lifecycle 에 아직 살아 있는(active) 신청 상태.
 *
 * FSM 전이표에는 초대 거절/미팅 취소 재오픈용으로 invited→applied 같은
 * 역전이가 합법으로 남아 있지만, 신규 신청 submit 이 이 상태의 신청을
 * applied 로 덮어쓰면 invitation/meeting 과 신청 lifecycle 이 분리된다.
 * submit 경로의 business guard 가 이 집합을 기준으로 거부한다.
 */
export const ACTIVE_APPLICATION_STATUSES: ParticipantStatus[] = [
  "applied",
  "waitlisted",
  "invited",
  "accepted",
  "confirmed",
  "cancel_requested",
  "replacement_pending",
];

/** active 신청 중에서도 특정 미팅에 귀속되어야만 정상인 상태 */
export const MEETING_BOUND_APPLICATION_STATUSES: ParticipantStatus[] = [
  "invited",
  "accepted",
  "confirmed",
  "cancel_requested",
  "replacement_pending",
];

/**
 * 신청서 기준으로 '끝난' 미팅 상태.
 *
 * completed 이후/취소 미팅은 orchestrator 정리 루프가 신청서를 terminal
 * (completed/cancelled/no_show)로 옮긴다. active 신청이 이런 미팅에 아직
 * 묶여 있다면 정리 실패(corrupt link)이므로 submit 이 조용히 덮어쓰지 않고
 * fail-closed 로 거부해야 한다.
 */
export const SETTLED_MEETING_STATUSES: BlindMeetingStatus[] = [
  "completed",
  "followup_open",
  "read_only",
  "archived",
  "cancelled",
];

export function isApplicationActive(status: ParticipantStatus): boolean {
  return ACTIVE_APPLICATION_STATUSES.includes(status);
}

export function isMeetingSettled(status: BlindMeetingStatus): boolean {
  return SETTLED_MEETING_STATUSES.includes(status);
}

/**
 * 참가자가 단체 채팅 멤버십을 가질 수 있는 상태.
 *
 * `no_show` 는 여기 없다. 이 상태는 검토 중이 아니라 최종 판정이다
 * (스케줄러가 미체크인 상태로 창을 넘긴 참가자에게 한 번 쓰고, 그 즉시
 * 제재·노쇼 카운트가 함께 적용된다). 나타나지 않은 사람이 나머지 다섯 명의
 * 대화를 계속 읽고 쓸 수 있으면 안 되므로 확정과 동시에 방에서 제외한다.
 */
export const CHAT_MEMBERSHIP_STATUSES: ParticipantStatus[] = [
  "confirmed",
  "attended",
  "completed",
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
