/**
 * 3:3 블라인드 취향 미팅 — 성비 불변식 (canonical 3M + 3F)
 * 경로: functions/src/blindMeeting/genderBalance.ts
 *
 * 3:3 블라인드 미팅의 최상위 system invariant:
 *
 *   participantCount == 6
 *   maleCount        == 3
 *   femaleCount      == 3
 *   uniqueUidCount   == 6
 *
 * 이 조건을 만족할 수 없으면 어떤 그룹/미팅/채팅방도 만들지 않는다.
 * 점수가 높다는 이유로 4M2F·5M1F·6M 구성을 만드는 것은 결함이다.
 *
 * 성별은 추측하지 않는다. canonical 값(`male` / `female`) 이 아니면
 * 후보에서 제외한다 (fail-closed). 3:3 상품이 현재 이 두 값만 지원하므로
 * `other` / `unknown` / 오타 / null 은 임의로 한쪽에 배정하지 않는다.
 */

/** 3:3 상품이 지원하는 canonical 성별. */
export const BLIND_MEETING_GENDERS = ["male", "female"] as const;

export type BlindMeetingGender = (typeof BLIND_MEETING_GENDERS)[number];

/** 한 팀(같은 편)의 인원. 3:3 이므로 3명. */
export const BLIND_MEETING_TEAM_SIZE = 3;

/** 한 미팅의 총 인원. 3남 + 3녀. */
export const BLIND_MEETING_GROUP_SIZE = 6;

/**
 * 성별 값을 canonical enum 으로 정규화한다.
 *
 * 대소문자와 앞뒤 공백만 허용 오차로 둔다. 그 밖의 값(`other`, `unknown`,
 * 한글 표기, legacy 오타, null, 숫자)은 전부 null 이다. 절대 추측해서
 * male/female 로 끼워 넣지 않는다.
 */
export function normalizeBlindMeetingGender(
  raw: unknown
): BlindMeetingGender | null {
  if (typeof raw !== "string") return null;
  const text = raw.trim().toLowerCase();
  return (BLIND_MEETING_GENDERS as readonly string[]).includes(text)
    ? (text as BlindMeetingGender)
    : null;
}

/**
 * `users/{uid}` 문서에서 성별을 읽는다.
 *
 * source of truth 는 온보딩이 쓰는 `onboarding.gender` 다.
 * 그 키 자체가 없을 때만 legacy 최상위 `gender` 로 내려간다.
 * `onboarding.gender` 가 있는데 canonical 이 아니면 거기서 fail-closed 한다
 * (다른 필드를 뒤져서 male/female 을 찾아내지 않는다).
 */
export function readBlindMeetingGender(
  user: Record<string, unknown> | undefined | null
): BlindMeetingGender | null {
  if (user == null || typeof user !== "object") return null;

  const onboarding = user.onboarding;
  if (onboarding != null && typeof onboarding === "object") {
    const scoped = (onboarding as Record<string, unknown>).gender;
    if (scoped !== undefined && scoped !== null && scoped !== "") {
      return normalizeBlindMeetingGender(scoped);
    }
  }

  const root = user.gender;
  if (root !== undefined && root !== null && root !== "") {
    return normalizeBlindMeetingGender(root);
  }
  return null;
}

/** 3:3 그룹이 canonical 이 아닌 이유. 로그/에러 분류용. */
export type GenderBalanceViolation =
  | "invalidGroupSize"
  | "duplicateParticipant"
  | "unknownGender"
  | "genderImbalance";

/** 성비 선택이 실패한 이유. PII 없는 관측 지표로 그대로 쓴다. */
export type GenderSelectionFailure =
  | "INSUFFICIENT_MALE_CANDIDATES"
  | "INSUFFICIENT_FEMALE_CANDIDATES"
  | "INSUFFICIENT_BALANCED_CANDIDATES";

export type GenderCounts = {
  male: number;
  female: number;
  unknown: number;
};

export type BlindThreeVsThreeValidation = {
  ok: boolean;
  violations: GenderBalanceViolation[];
  counts: GenderCounts;
  uniqueUserCount: number;
};

export type ParticipantGenderInput = {
  userId: string;
  /** 정규화 전 원본 값도 허용한다 (저장된 문서를 그대로 검증하기 위해). */
  gender: unknown;
};

/**
 * 3:3 블라인드 미팅 참가자 구성의 canonical 검증기.
 *
 * 추천 결과, 미팅 확정 직전, 참가자 문서 저장, 채팅방 생성 등
 * 모든 계층에서 같은 함수를 호출한다. 알고리즘을 우회한 legacy/손상/수동
 * 문서도 여기서 걸린다.
 */
export function validateBlindThreeVsThreeParticipants(
  participants: readonly ParticipantGenderInput[]
): BlindThreeVsThreeValidation {
  const violations = new Set<GenderBalanceViolation>();
  const counts: GenderCounts = { male: 0, female: 0, unknown: 0 };
  const seen = new Set<string>();

  for (const participant of participants) {
    const userId = typeof participant.userId === "string" ? participant.userId : "";
    if (userId.length === 0 || seen.has(userId)) {
      violations.add("duplicateParticipant");
    }
    seen.add(userId);

    const gender = normalizeBlindMeetingGender(participant.gender);
    if (gender == null) {
      counts.unknown++;
      violations.add("unknownGender");
      continue;
    }
    counts[gender]++;
  }

  if (participants.length !== BLIND_MEETING_GROUP_SIZE) {
    violations.add("invalidGroupSize");
  }
  if (
    counts.male !== BLIND_MEETING_TEAM_SIZE ||
    counts.female !== BLIND_MEETING_TEAM_SIZE
  ) {
    violations.add("genderImbalance");
  }

  return {
    ok: violations.size === 0,
    violations: [...violations],
    counts,
    uniqueUserCount: seen.size,
  };
}

/**
 * 성별 후보 수만으로 3+3 이 가능한지 판정한다.
 *
 * 부족하면 상위 점수 6명을 뽑는 것이 아니라 그룹을 만들지 않는다.
 */
export function classifyGenderShortage(
  maleCount: number,
  femaleCount: number
): GenderSelectionFailure | null {
  const maleShort = maleCount < BLIND_MEETING_TEAM_SIZE;
  const femaleShort = femaleCount < BLIND_MEETING_TEAM_SIZE;
  if (maleShort && femaleShort) return "INSUFFICIENT_BALANCED_CANDIDATES";
  if (maleShort) return "INSUFFICIENT_MALE_CANDIDATES";
  if (femaleShort) return "INSUFFICIENT_FEMALE_CANDIDATES";
  return null;
}
