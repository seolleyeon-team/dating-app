/**
 * 3:3 미팅 아이스브레이킹 룰렛 — 서버 타입과 컬렉션 이름
 * 경로: functions/src/meetingIcebreaker/types.ts
 *
 * 앱 쪽 정의와 1:1 대응한다.
 *   lib/features/event/meeting_icebreaker/domain/meeting_icebreaker_prompt.dart
 *
 * 이 기능은 아래 두 미팅에만 적용된다.
 *   - 3:3 시즌 미팅        (chat_rooms/{roomId}/promises/{promiseId} 안전도장)
 *   - 3:3 블라인드 취향 미팅 (blindMeetings/{meetingId}/participants/{uid} 체크인/체크아웃)
 * 일반 이벤트, 1:1 추천, 일반 채팅, 커뮤니티에는 적용하지 않는다.
 */

export const MEETING_ICEBREAKER_COLLECTIONS = {
  /** 반복 알림 세션 (서버 전용 쓰기) */
  sessions: "meetingIcebreakerSessions",
  /**
   * 세션 하위 참가자 문서.
   *
   * 이름이 `participants`가 아닌 이유: 예약 작업이 collectionGroup 조회를 쓰는데,
   * `blindMeetings/{id}/participants`와 collection group 이름이 겹치면 안 된다.
   */
  promptParticipants: "promptParticipants",
  /** 운영 설정 (주기·최대 지속 시간·feature flag) */
  config: "meetingIcebreakerConfig",
  /** 비식별 analytics */
  analytics: "meetingIcebreakerAnalytics",
} as const;

/** 3:3 시즌 미팅 (chat 약속 안전도장 기반) */
export const SEASON_MEETING_TYPE = "seasonMeeting";
/** 3:3 블라인드 취향 미팅 (blindMeetings 체크인/체크아웃 기반) */
export const BLIND_TASTE_MEETING_TYPE = "blindTasteMeeting";

export type MeetingIcebreakerMeetingType =
  | typeof SEASON_MEETING_TYPE
  | typeof BLIND_TASTE_MEETING_TYPE;

export const MEETING_ICEBREAKER_MEETING_TYPES: MeetingIcebreakerMeetingType[] = [
  SEASON_MEETING_TYPE,
  BLIND_TASTE_MEETING_TYPE,
];

/** 3:3 미팅 인원 (세 명 + 세 명) */
export const MEETING_ICEBREAKER_PARTICIPANT_COUNT = 6;

/** 반복 알림이 멈춘 이유. PII가 아니므로 로깅·analytics에 사용해도 된다. */
export type MeetingIcebreakerStopReason =
  | "goodbye_stamp"
  | "meeting_completed"
  | "meeting_cancelled"
  | "participant_left"
  | "participant_no_show"
  | "max_duration_reached"
  | "opted_out"
  | "feature_disabled"
  | "admin_stop";

export const MEETING_ICEBREAKER_STOP_REASONS: MeetingIcebreakerStopReason[] = [
  "goodbye_stamp",
  "meeting_completed",
  "meeting_cancelled",
  "participant_left",
  "participant_no_show",
  "max_duration_reached",
  "opted_out",
  "feature_disabled",
  "admin_stop",
];

/**
 * 룰렛 진입 판정 결과.
 *
 * 알림 payload만 믿지 않고 서버에서 매번 다시 계산한다.
 */
export type MeetingIcebreakerEntryDecision =
  | "allowed"
  | "unauthenticated"
  | "not_found"
  | "not_participant"
  | "not_started"
  | "meeting_ended"
  | "meeting_cancelled"
  | "feature_disabled";

export function isMeetingIcebreakerMeetingType(
  value: unknown
): value is MeetingIcebreakerMeetingType {
  return (
    typeof value === "string" &&
    (MEETING_ICEBREAKER_MEETING_TYPES as string[]).includes(value)
  );
}

/**
 * 세션 문서 id.
 *
 * 미팅 유형별로 접두어를 붙여 두 종류의 미팅 id가 섞이지 않게 한다.
 *  - 시즌 미팅:   약속 문서 id  → `season_{promiseId}`
 *  - 블라인드 미팅: 미팅 문서 id → `blind_{meetingId}`
 */
export function buildMeetingIcebreakerSessionId(
  meetingType: MeetingIcebreakerMeetingType,
  meetingId: string
): string {
  const prefix = meetingType === SEASON_MEETING_TYPE ? "season" : "blind";
  return `${prefix}_${meetingId}`;
}

// -----------------------------------------------------------------------------
// 파싱 헬퍼 (blindMeeting/types.ts와 같은 규칙)
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

export function asInt(v: unknown, fallback = 0): number {
  if (typeof v === "number" && Number.isFinite(v)) return Math.trunc(v);
  if (typeof v === "string") {
    const parsed = Number(v.trim());
    if (Number.isFinite(parsed)) return Math.trunc(parsed);
  }
  return fallback;
}
