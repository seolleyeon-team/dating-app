/**
 * 3:3 블라인드 취향 미팅 — 매칭 엔진 (서버 권위 구현)
 * 경로: functions/src/blindMeeting/matching.ts
 *
 * 이 계산은 다른 참가자의 비공개 DNA를 읽어야 하므로 반드시 서버에서만 수행한다.
 * 명세 기준 구현: lib/features/blind_meeting/domain/matching/*.dart
 * 두 구현의 일치는 양쪽 단위 테스트로 검증한다.
 *
 * 1단계: 같은 편인 우리 팀 3명 구성
 * 2단계: 완성된 두 팀 사이의 호환성 계산
 * 결과는 deterministic 하다 (동점 시 정렬된 참가자 id로 tie-break).
 */

import { normalizeCampusLifeZones } from "../campusLifeZones";
import {
  BLIND_MEETING_GENDERS,
  BLIND_MEETING_GROUP_SIZE,
  BLIND_MEETING_TEAM_SIZE,
  BlindMeetingGender,
  classifyGenderShortage,
  GenderSelectionFailure,
} from "./genderBalance";
import { interestCategoryIdOf } from "./interestTaxonomy";
import {
  CURRENT_MATCHING_CONFIG,
  CrossWeights,
  MatchingConfig,
  crossWeightsFor,
  crossWeightsTotal,
  teamWeightsFor,
  teamWeightsTotal,
} from "./matchingConfig";
import {
  AlcoholCompanionPreference,
  ConversationAtmosphere,
  ConversationInitiative,
  DrinkingLevel,
  MeetingPurpose,
  SmokingCompanionPreference,
  SmokingStatus,
  commonDateKeys,
} from "./types";

export type Candidate = {
  userId: string;
  /**
   * canonical 성별 (`male` / `female`).
   *
   * 3:3 은 3남 + 3녀가 상품 정의 자체이므로 성별은 optional 이 아니다.
   * canonical 값을 확인할 수 없는 사용자는 후보 hydration 단계
   * (store.ts loadCandidate) 에서 제외되므로 여기까지 오지 않는다.
   */
  gender: BlindMeetingGender;
  atmosphere: ConversationAtmosphere;
  initiative: ConversationInitiative;
  purpose: MeetingPurpose;
  alcoholPreference: AlcoholCompanionPreference;
  smokingPreference: SmokingCompanionPreference;
  drinkingLevel: DrinkingLevel;
  smokingStatus: SmokingStatus;
  interestIds: string[];
  mbti: string | null;
  /**
   * 생활권 (users/{uid}.onboarding.campusLifeZones 에 저장된 값).
   * 분류는 클라이언트 CampusLifeZoneResolver 가 담당하며 여기서 재계산하지
   * 않는다. 복수 생활권이 가능하므로 집합 교집합으로만 비교한다.
   */
  campusLifeZones: string[];
  /** 참여 가능한 날짜 (KST `yyyy-MM-dd`). 세부 시간은 매칭 조건이 아니다. */
  availableDateKeys: string[];
  schoolVerified: boolean;
  eligible: boolean;
  blockedUserIds: string[];
  recentlyMetUserIds: string[];
  waitedMinutes: number;
};

export type ConstraintViolation =
  | "notSchoolVerified"
  | "notEligible"
  | "dateUnavailable"
  | "noCommonDate"
  | "blockedContact"
  | "recentlyMet"
  | "alcoholFreeGroupRequired"
  | "alcoholFreeGroupViolated"
  | "smokingRejected"
  | "purposeConflict"
  | "duplicateParticipant"
  | "invalidGroupSize"
  /** 한 팀(같은 편) 안에 서로 다른 성별이 섞였다 */
  | "mixedGenderTeam"
  /** 여섯 명이 3남 + 3녀가 아니다 */
  | "genderImbalance"
  /** 여섯 명이 함께 만날 수 있는 공통 생활권이 없다 */
  | "campusLifeZoneMismatch"
  /** 생활권 정보가 없어 판정할 수 없다 (fail-closed) */
  | "campusLifeZoneMissing";

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
}

function isSober(level: DrinkingLevel): boolean {
  return level === "none";
}

function isSmoker(status: SmokingStatus): boolean {
  return status === "smoker";
}

export function requiresAlcoholFreeGroup(
  candidate: Pick<Candidate, "alcoholPreference" | "drinkingLevel">
): boolean {
  return (
    candidate.alcoholPreference === "allSober" &&
    isSober(candidate.drinkingLevel)
  );
}

export function requiresNonSmokersOnly(
  candidate: Pick<Candidate, "smokingPreference">
): boolean {
  return candidate.smokingPreference === "nonSmokersOnly";
}

// -----------------------------------------------------------------------------
// 개별 요소 점수
// -----------------------------------------------------------------------------

export type PurposeCompatibility = {
  score: number;
  isDirectConflict: boolean;
};

export function purposeCompatibility(
  a: MeetingPurpose,
  b: MeetingPurpose
): PurposeCompatibility {
  const conflict =
    (a === "romance" && b === "friendship") ||
    (a === "friendship" && b === "romance");
  if (conflict) return { score: 0, isDirectConflict: true };
  if (a === b) return { score: 1, isDirectConflict: false };
  return { score: 0.8, isDirectConflict: false };
}

export function interestSimilarity(a: string[], b: string[]): number {
  if (a.length === 0 || b.length === 0) return 0;

  const setA = new Set(a);
  const setB = new Set(b);
  let exactOverlap = 0;
  for (const item of setA) if (setB.has(item)) exactOverlap++;
  const exactScore = exactOverlap / Math.min(setA.size, setB.size);

  const catA = new Set([...setA].map(interestCategoryIdOf));
  const catB = new Set([...setB].map(interestCategoryIdOf));
  const union = new Set([...catA, ...catB]);
  let catOverlap = 0;
  for (const c of catA) if (catB.has(c)) catOverlap++;
  const categoryScore = union.size === 0 ? 0 : catOverlap / union.size;

  return clamp01(0.65 * exactScore + 0.35 * categoryScore);
}

export function sharesAnyInterest(a: string[], b: string[]): boolean {
  const setB = new Set(b);
  return a.some((item) => setB.has(item));
}

export function atmosphereCompatibility(
  a: ConversationAtmosphere,
  b: ConversationAtmosphere
): number {
  if (a === "either" || b === "either") {
    return a === b ? 0.9 : 0.85;
  }
  return a === b ? 1 : 0.35;
}

const INITIATIVE_SCORES: Record<string, number> = {
  "initiator|listener": 1,
  "initiator|adaptive": 0.9,
  "adaptive|listener": 0.85,
  "adaptive|adaptive": 0.8,
  "initiator|initiator": 0.6,
  "listener|listener": 0.25,
};

export function initiativeCompatibility(
  a: ConversationInitiative,
  b: ConversationInitiative
): number {
  return (
    INITIATIVE_SCORES[`${a}|${b}`] ?? INITIATIVE_SCORES[`${b}|${a}`] ?? 0.5
  );
}

export function alcoholToleranceScore(
  preference: AlcoholCompanionPreference,
  otherLevel: DrinkingLevel
): number {
  switch (preference) {
    case "allSober":
      return isSober(otherLevel) ? 1 : 0;
    case "lightOkay":
      switch (otherLevel) {
        case "none":
          return 1;
        case "sometimes":
          return 0.8;
        case "weekly1_2":
          return 0.5;
        case "often":
          return 0.2;
      }
      return 0;
    case "noPreference":
      return 1;
  }
}

export function alcoholCompatibility(a: Candidate, b: Candidate): number {
  return Math.min(
    alcoholToleranceScore(a.alcoholPreference, b.drinkingLevel),
    alcoholToleranceScore(b.alcoholPreference, a.drinkingLevel)
  );
}

export function smokingToleranceScore(
  preference: SmokingCompanionPreference,
  otherStatus: SmokingStatus
): number {
  if (!isSmoker(otherStatus)) return 1;
  switch (preference) {
    case "nonSmokersOnly":
      return 0;
    case "noIndoorSmoking":
      return 0.7;
    case "noPreference":
      return 1;
  }
}

export function smokingCompatibility(a: Candidate, b: Candidate): number {
  return Math.min(
    smokingToleranceScore(a.smokingPreference, b.smokingStatus),
    smokingToleranceScore(b.smokingPreference, a.smokingStatus)
  );
}

const MBTI_AXES = [
  ["E", "I"],
  ["N", "S"],
  ["T", "F"],
  ["J", "P"],
];

function normalizeMbti(raw: string | null): string | null {
  const text = (raw ?? "").trim().toUpperCase();
  if (text.length !== 4) return null;
  for (let i = 0; i < 4; i++) {
    if (!MBTI_AXES[i].includes(text[i])) return null;
  }
  return text;
}

export function mbtiCompatibility(
  a: string | null,
  b: string | null
): number {
  const left = normalizeMbti(a);
  const right = normalizeMbti(b);
  if (left == null || right == null) return 0.5;

  const ei = left[0] === right[0] ? 0.7 : 1;
  const ns = left[1] === right[1] ? 1 : 0.5;
  const tf = left[2] === right[2] ? 0.9 : 0.8;
  const jp = left[3] === right[3] ? 0.9 : 0.8;
  return clamp01((ei + ns + tf + jp) / 4);
}

export function pairCompatibility(
  a: Candidate,
  b: Candidate,
  weights: CrossWeights
): number {
  const total = crossWeightsTotal(weights);
  if (total <= 0) return 0;
  const purpose = purposeCompatibility(a.purpose, b.purpose);

  const raw =
    weights.purpose * purpose.score +
    weights.interest * interestSimilarity(a.interestIds, b.interestIds) +
    weights.alcohol * alcoholCompatibility(a, b) +
    weights.atmosphere * atmosphereCompatibility(a.atmosphere, b.atmosphere) +
    weights.initiative * initiativeCompatibility(a.initiative, b.initiative) +
    weights.smoking * smokingCompatibility(a, b) +
    weights.mbti * mbtiCompatibility(a.mbti, b.mbti);

  return clamp01(raw / total);
}

// -----------------------------------------------------------------------------
// 팀 내부 품질
// -----------------------------------------------------------------------------

function meanPairwise(
  members: Candidate[],
  metric: (a: Candidate, b: Candidate) => number
): number {
  if (members.length < 2) return 0;
  let sum = 0;
  let count = 0;
  for (let i = 0; i < members.length; i++) {
    for (let j = i + 1; j < members.length; j++) {
      sum += metric(members[i], members[j]);
      count++;
    }
  }
  return count === 0 ? 0 : clamp01(sum / count);
}

export function initiativeBalanceScore(
  initiatives: ConversationInitiative[],
  config: MatchingConfig
): number {
  if (initiatives.length === 0) return 0;
  const size = initiatives.length;
  let initiators = 0;
  let adaptives = 0;
  let listeners = 0;
  for (const initiative of initiatives) {
    if (initiative === "initiator") initiators++;
    else if (initiative === "adaptive") adaptives++;
    else listeners++;
  }

  const ideal = 1 / 3;
  const l1 =
    Math.abs(initiators / size - ideal) +
    Math.abs(adaptives / size - ideal) +
    Math.abs(listeners / size - ideal);
  let score = clamp01(1 - 0.5 * l1);

  if (listeners === size) {
    score *= config.allPassiveTeamMultiplier;
  } else if (initiators === size) {
    score *= config.allDominantTeamMultiplier;
  } else if (initiators === 0) {
    score *= config.noInitiatorTeamMultiplier;
  }

  return clamp01(score);
}

export function teamInterestConnectionScore(team: Candidate[]): number {
  if (team.length < 2) return 0;
  let connected = 0;
  for (let i = 0; i < team.length; i++) {
    for (let j = 0; j < team.length; j++) {
      if (i === j) continue;
      if (sharesAnyInterest(team[i].interestIds, team[j].interestIds)) {
        connected++;
        break;
      }
    }
  }
  const coverage = connected / team.length;
  const mean = meanPairwise(team, (a, b) =>
    interestSimilarity(a.interestIds, b.interestIds)
  );
  return clamp01(0.6 * coverage + 0.4 * mean);
}

export function teamPurposeConsistencyScore(team: Candidate[]): number {
  if (team.length < 2) return 0;
  let sum = 0;
  let count = 0;
  for (let i = 0; i < team.length; i++) {
    for (let j = i + 1; j < team.length; j++) {
      const compatibility = purposeCompatibility(
        team[i].purpose,
        team[j].purpose
      );
      if (compatibility.isDirectConflict) return 0;
      sum += compatibility.score;
      count++;
    }
  }
  return count === 0 ? 0 : clamp01(sum / count);
}

export type InternalTeamScore = {
  initiativeBalance: number;
  atmosphereBalance: number;
  interestConnection: number;
  purposeConsistency: number;
  alcohol: number;
  smoking: number;
  mbti: number;
  total: number;
};

export function internalTeamScore(
  team: Candidate[],
  config: MatchingConfig,
  alcoholFree: boolean
): InternalTeamScore {
  const weights = teamWeightsFor(config, alcoholFree);
  const initiativeBalance = initiativeBalanceScore(
    team.map((c) => c.initiative),
    config
  );
  const atmosphereBalance = meanPairwise(team, (a, b) =>
    atmosphereCompatibility(a.atmosphere, b.atmosphere)
  );
  const interestConnection = teamInterestConnectionScore(team);
  const purposeConsistency = teamPurposeConsistencyScore(team);
  const alcohol = meanPairwise(team, alcoholCompatibility);
  const smoking = meanPairwise(team, smokingCompatibility);
  const mbti = meanPairwise(team, (a, b) => mbtiCompatibility(a.mbti, b.mbti));

  const total = teamWeightsTotal(weights);
  const weighted =
    total <= 0
      ? 0
      : (weights.initiativeBalance * initiativeBalance +
          weights.atmosphereBalance * atmosphereBalance +
          weights.interestConnection * interestConnection +
          weights.purposeConsistency * purposeConsistency +
          weights.alcohol * alcohol +
          weights.smoking * smoking +
          weights.mbti * mbti) /
        total;

  return {
    initiativeBalance,
    atmosphereBalance,
    interestConnection,
    purposeConsistency,
    alcohol,
    smoking,
    mbti,
    total: clamp01(weighted),
  };
}

// -----------------------------------------------------------------------------
// 그룹 점수
// -----------------------------------------------------------------------------

export type GroupScore = {
  teamAInternal: number;
  teamBInternal: number;
  participantOpponentScores: Record<string, number>;
  crossTeamScore: number;
  minimumParticipantScore: number;
  finalGroupScore: number;
};

export function participantOpponentScore(
  participant: Candidate,
  opponents: Candidate[],
  weights: CrossWeights
): number {
  if (opponents.length === 0) return 0;
  let sum = 0;
  for (const opponent of opponents) {
    sum += pairCompatibility(participant, opponent, weights);
  }
  return clamp01(sum / opponents.length);
}

export function groupScore(
  teamA: Candidate[],
  teamB: Candidate[],
  config: MatchingConfig,
  alcoholFree: boolean
): GroupScore {
  const crossWeights = crossWeightsFor(config, alcoholFree);
  const internalA = internalTeamScore(teamA, config, alcoholFree).total;
  const internalB = internalTeamScore(teamB, config, alcoholFree).total;

  const scores: Record<string, number> = {};
  for (const member of teamA) {
    scores[member.userId] = participantOpponentScore(
      member,
      teamB,
      crossWeights
    );
  }
  for (const member of teamB) {
    scores[member.userId] = participantOpponentScore(
      member,
      teamA,
      crossWeights
    );
  }

  const values = Object.values(scores);
  if (values.length === 0) {
    return {
      teamAInternal: 0,
      teamBInternal: 0,
      participantOpponentScores: {},
      crossTeamScore: 0,
      minimumParticipantScore: 0,
      finalGroupScore: 0,
    };
  }

  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const minimum = values.reduce((a, b) => (a < b ? a : b));
  const cross = clamp01(
    config.crossTeamMeanWeight * mean + config.crossTeamMinWeight * minimum
  );
  const internalMean = (internalA + internalB) / 2;
  const finalScore = clamp01(
    config.finalInternalWeight * internalMean + config.finalCrossWeight * cross
  );

  return {
    teamAInternal: internalA,
    teamBInternal: internalB,
    participantOpponentScores: scores,
    crossTeamScore: cross,
    minimumParticipantScore: minimum,
    finalGroupScore: finalScore,
  };
}

export function waitingTimeBonus(
  members: Candidate[],
  config: MatchingConfig
): number {
  if (members.length === 0) return 0;
  const saturation = config.waitingBonusSaturationMinutes;
  if (saturation <= 0) return 0;
  let sum = 0;
  for (const member of members) {
    const ratio = member.waitedMinutes <= 0 ? 0 : member.waitedMinutes / saturation;
    sum += clamp01(ratio);
  }
  return config.maxWaitingBonus * (sum / members.length);
}

// -----------------------------------------------------------------------------
// hard constraint
// -----------------------------------------------------------------------------

/**
 * 그룹 전원이 함께 만날 수 있는 공통 생활권.
 *
 * 다수결/대표자 기준이 아니라 반드시 교집합이다. 한 명이라도 생활권 정보가
 * 없으면 빈 집합을 돌려준다 (fail-closed).
 */
export function sharedCampusLifeZones(members: Candidate[]): string[] {
  if (members.length === 0) return [];
  let shared: Set<string> | null = null;
  for (const member of members) {
    // canonical 이 아닌 값은 생활권으로 인정하지 않는다 (손상된 문서 방어).
    const zones = new Set(normalizeCampusLifeZones(member.campusLifeZones));
    if (zones.size === 0) return [];
    if (shared == null) {
      shared = zones;
      continue;
    }
    shared = new Set([...shared].filter((zone) => zones.has(zone)));
    if (shared.size === 0) return [];
  }
  return [...(shared ?? new Set<string>())].sort();
}

/** 성별별 인원 수. 관측 지표와 불변식 검사에 함께 쓴다. */
export function candidateGenderCounts(members: readonly Candidate[]): {
  male: number;
  female: number;
} {
  let male = 0;
  let female = 0;
  for (const member of members) {
    if (member.gender === "male") male++;
    else if (member.gender === "female") female++;
  }
  return { male, female };
}

/** 성별로 후보군을 나눈다. 점수 계산 이전 단계다 (filter-before-rank). */
export function splitByGender(pool: readonly Candidate[]): {
  male: Candidate[];
  female: Candidate[];
} {
  const male: Candidate[] = [];
  const female: Candidate[] = [];
  for (const candidate of pool) {
    if (candidate.gender === "male") male.push(candidate);
    else if (candidate.gender === "female") female.push(candidate);
  }
  return { male, female };
}

/** 생활권 정보가 비어 있는 참가자가 하나라도 있는지. */
function hasMissingCampusLifeZone(members: Candidate[]): boolean {
  return members.some(
    (member) => normalizeCampusLifeZones(member.campusLifeZones).length === 0
  );
}

export function checkCandidateConstraints(
  candidate: Candidate,
  dateKey: string,
  alcoholFreeGroup: boolean
): ConstraintViolation[] {
  const violations: ConstraintViolation[] = [];
  if (!candidate.schoolVerified) violations.push("notSchoolVerified");
  if (!candidate.eligible) violations.push("notEligible");
  if (!candidate.availableDateKeys.includes(dateKey)) {
    violations.push("dateUnavailable");
  }
  if (requiresAlcoholFreeGroup(candidate) && !alcoholFreeGroup) {
    violations.push("alcoholFreeGroupRequired");
  }
  if (alcoholFreeGroup && !isSober(candidate.drinkingLevel)) {
    violations.push("alcoholFreeGroupViolated");
  }
  return violations;
}

export function checkPairConstraints(
  a: Candidate,
  b: Candidate
): ConstraintViolation[] {
  const violations: ConstraintViolation[] = [];
  if (a.userId === b.userId) return ["duplicateParticipant"];
  if (
    a.blockedUserIds.includes(b.userId) ||
    b.blockedUserIds.includes(a.userId)
  ) {
    violations.push("blockedContact");
  }
  if (
    a.recentlyMetUserIds.includes(b.userId) ||
    b.recentlyMetUserIds.includes(a.userId)
  ) {
    violations.push("recentlyMet");
  }
  if (
    (requiresAlcoholFreeGroup(a) && !isSober(b.drinkingLevel)) ||
    (requiresAlcoholFreeGroup(b) && !isSober(a.drinkingLevel))
  ) {
    violations.push("alcoholFreeGroupViolated");
  }
  if (
    (requiresNonSmokersOnly(a) && isSmoker(b.smokingStatus)) ||
    (requiresNonSmokersOnly(b) && isSmoker(a.smokingStatus))
  ) {
    violations.push("smokingRejected");
  }
  if (purposeCompatibility(a.purpose, b.purpose).isDirectConflict) {
    violations.push("purposeConflict");
  }
  return violations;
}

/**
 * 구성원 전원이 공통으로 가능한 날짜 (오름차순).
 *
 * 비어 있으면 같은 미팅으로 확정하지 않는다. 확정된 미팅에서는
 * 단체 채팅방 약속잡기의 날짜 후보로 그대로 쓰인다.
 */
export function groupCommonDateKeys(members: Candidate[]): string[] {
  return commonDateKeys(members.map((m) => m.availableDateKeys));
}

export function checkGroupConstraints(
  members: Candidate[],
  dateKey: string,
  alcoholFreeGroup: boolean,
  expectedSize?: number,
  /**
   * 생활권 hard filter 의 rollout activation.
   * false 면 생활권 조건만 비활성이고 나머지 조건은 전부 유지된다.
   */
  campusLifeZoneEnforced: boolean = true
): ConstraintViolation[] {
  const violations = new Set<ConstraintViolation>();
  if (expectedSize !== undefined && members.length !== expectedSize) {
    violations.add("invalidGroupSize");
  }
  const seen = new Set<string>();
  for (const member of members) {
    if (seen.has(member.userId)) violations.add("duplicateParticipant");
    seen.add(member.userId);
    for (const v of checkCandidateConstraints(
      member,
      dateKey,
      alcoholFreeGroup
    )) {
      violations.add(v);
    }
  }
  for (let i = 0; i < members.length; i++) {
    for (let j = i + 1; j < members.length; j++) {
      for (const v of checkPairConstraints(members[i], members[j])) {
        violations.add(v);
      }
    }
  }
  // 생활권은 날짜와 달리 per-candidate proxy가 없는 진짜 그룹 속성이라
  // (개인은 여러 생활권을 가질 수 있다) 여기서 교집합을 직접 확인한다.
  // 실제로 함께 만나려면 전원이 최소 하나의 공통 생활권을 가져야 한다.
  if (campusLifeZoneEnforced && members.length > 0) {
    if (hasMissingCampusLifeZone(members)) {
      violations.add("campusLifeZoneMissing");
    } else if (sharedCampusLifeZones(members).length === 0) {
      violations.add("campusLifeZoneMismatch");
    }
  }
  // 성비는 3:3 상품 정의 자체다. 팀(3명)은 단일 성별이어야 하고
  // 그룹(6명)은 정확히 3남 + 3녀여야 한다. 점수가 아무리 높아도
  // 4M2F / 5M1F / 6M 구성은 만들지 않는다.
  if (members.length > 0) {
    const counts = candidateGenderCounts(members);
    if (expectedSize === BLIND_MEETING_TEAM_SIZE) {
      if (counts.male > 0 && counts.female > 0) {
        violations.add("mixedGenderTeam");
      }
    } else if (expectedSize === BLIND_MEETING_GROUP_SIZE) {
      if (
        counts.male !== BLIND_MEETING_TEAM_SIZE ||
        counts.female !== BLIND_MEETING_TEAM_SIZE
      ) {
        violations.add("genderImbalance");
      }
    }
  }
  // 공통 가능 날짜 검사는 의도적으로 여기서 하지 않는다.
  // 전원이 dateKey를 갖고 있어야 통과하므로 교집합은 항상 dateKey를 포함한다.
  // 최종 6인 구성 검사는 createMeetingFromProposal 에서 한 번만 수행한다.
  return [...violations];
}

export function isGroupAllowed(
  members: Candidate[],
  dateKey: string,
  alcoholFreeGroup: boolean,
  expectedSize?: number,
  campusLifeZoneEnforced: boolean = true
): boolean {
  return (
    checkGroupConstraints(
      members,
      dateKey,
      alcoholFreeGroup,
      expectedSize,
      campusLifeZoneEnforced
    ).length === 0
  );
}

/** 무알코올 전용 후보군 (비음주만) */
export function alcoholFreePool(pool: Candidate[]): Candidate[] {
  return pool.filter((c) => isSober(c.drinkingLevel));
}

/** 일반 미팅 후보군 (전원 비음주를 요구한 사용자는 제외) */
export function standardPool(pool: Candidate[]): Candidate[] {
  return pool.filter((c) => !requiresAlcoholFreeGroup(c));
}

// -----------------------------------------------------------------------------
// optimizer
// -----------------------------------------------------------------------------

export type TeamProposal = {
  members: Candidate[];
  /** 팀은 단일 성별이다 (3:3 에서 "같은 편"은 동성 3명). */
  gender: BlindMeetingGender;
  score: InternalTeamScore;
  key: string;
  userIds: Set<string>;
};

export type GroupProposal = {
  /** 이 구성을 만든 기준 날짜 (KST `yyyy-MM-dd`) */
  dateKey: string;
  /** 여섯 명이 공통으로 가능한 날짜 전체 (약속잡기 후보) */
  commonDateKeys: string[];
  alcoholFree: boolean;
  algorithmVersion: string;
  teamA: Candidate[];
  teamB: Candidate[];
  score: GroupScore;
  adjustedScore: number;
  key: string;
};

const INITIATIVE_ORDER: Record<ConversationInitiative, number> = {
  initiator: 0,
  adaptive: 1,
  listener: 2,
};

function orderTeamMembers(members: Candidate[]): Candidate[] {
  return [...members].sort((a, b) => {
    const byRole =
      INITIATIVE_ORDER[a.initiative] - INITIATIVE_ORDER[b.initiative];
    if (byRole !== 0) return byRole;
    return a.userId.localeCompare(b.userId);
  });
}

function teamKey(members: Candidate[]): string {
  return members
    .map((m) => m.userId)
    .sort()
    .join("|");
}

function eligiblePool(
  pool: Candidate[],
  dateKey: string,
  alcoholFree: boolean
): Candidate[] {
  const seen = new Set<string>();
  const result: Candidate[] = [];
  for (const candidate of pool) {
    if (seen.has(candidate.userId)) continue;
    seen.add(candidate.userId);
    if (
      checkCandidateConstraints(candidate, dateKey, alcoholFree).length === 0
    ) {
      result.push(candidate);
    }
  }
  result.sort((a, b) => a.userId.localeCompare(b.userId));
  return result;
}

/**
 * 성별 후보 수와 부족 사유. 관측(observability)과 조기 종료에 쓴다.
 *
 * 여기서 세는 것은 hard constraint 를 통과한 후보뿐이다.
 * (자격 미달·날짜 불가·차단 정책 위반은 점수 계산 이전에 이미 빠진다.)
 */
export function describeGenderAvailability(
  pool: Candidate[],
  dateKey: string,
  alcoholFree: boolean
): {
  eligibleMaleCount: number;
  eligibleFemaleCount: number;
  failure: GenderSelectionFailure | null;
} {
  const { male, female } = splitByGender(
    eligiblePool(pool, dateKey, alcoholFree)
  );
  return {
    eligibleMaleCount: male.length,
    eligibleFemaleCount: female.length,
    failure: classifyGenderShortage(male.length, female.length),
  };
}

/**
 * 팀(같은 편) 후보를 만든다.
 *
 * 3:3 에서 한 팀은 동성 3명이므로 성별로 후보군을 먼저 나눈 뒤
 * 각 성별 안에서만 조합을 만든다. 전체 상위 6명을 뽑아놓고 나중에
 * 성비를 맞추는 ad-hoc post-processing 이 아니라, 제약을 탐색 공간
 * 자체에 넣는 constrained selection 이다.
 */
export function buildTeamProposals(
  pool: Candidate[],
  dateKey: string,
  alcoholFree: boolean,
  config: MatchingConfig = CURRENT_MATCHING_CONFIG,
  campusLifeZoneEnforced: boolean = true
): TeamProposal[] {
  const eligible = eligiblePool(pool, dateKey, alcoholFree);
  if (eligible.length < BLIND_MEETING_TEAM_SIZE) return [];

  const byKey = new Map<string, TeamProposal>();

  const tryTeam = (trio: Candidate[], gender: BlindMeetingGender) => {
    if (
      !isGroupAllowed(
        trio,
        dateKey,
        alcoholFree,
        BLIND_MEETING_TEAM_SIZE,
        campusLifeZoneEnforced
      )
    ) {
      return;
    }
    const ordered = orderTeamMembers(trio);
    const proposal: TeamProposal = {
      members: ordered,
      gender,
      score: internalTeamScore(ordered, config, alcoholFree),
      key: teamKey(ordered),
      userIds: new Set(ordered.map((m) => m.userId)),
    };
    byKey.set(proposal.key, proposal);
  };

  const crossWeights = crossWeightsFor(config, alcoholFree);
  const byGender = splitByGender(eligible);

  for (const gender of BLIND_MEETING_GENDERS) {
    const sameGender = byGender[gender];
    if (sameGender.length < BLIND_MEETING_TEAM_SIZE) continue;

    if (sameGender.length <= config.exhaustiveTeamPoolLimit) {
      for (let i = 0; i < sameGender.length; i++) {
        for (let j = i + 1; j < sameGender.length; j++) {
          for (let k = j + 1; k < sameGender.length; k++) {
            tryTeam([sameGender[i], sameGender[j], sameGender[k]], gender);
          }
        }
      }
      continue;
    }

    for (const seed of sameGender) {
      const neighbors = sameGender
        .filter((c) => c.userId !== seed.userId)
        .sort((a, b) => {
          const diff =
            pairCompatibility(seed, b, crossWeights) -
            pairCompatibility(seed, a, crossWeights);
          if (Math.abs(diff) > config.tieEpsilon) return diff > 0 ? 1 : -1;
          return a.userId.localeCompare(b.userId);
        })
        .slice(0, config.neighborhoodSize);
      for (let j = 0; j < neighbors.length; j++) {
        for (let k = j + 1; k < neighbors.length; k++) {
          tryTeam([seed, neighbors[j], neighbors[k]], gender);
        }
      }
    }
  }

  return [...byKey.values()].sort((a, b) => {
    const diff = b.score.total - a.score.total;
    if (Math.abs(diff) > config.tieEpsilon) return diff > 0 ? 1 : -1;
    return a.key.localeCompare(b.key);
  });
}

export function bestGroup(
  pool: Candidate[],
  dateKey: string,
  alcoholFree: boolean,
  config: MatchingConfig = CURRENT_MATCHING_CONFIG,
  campusLifeZoneEnforced: boolean = true
): GroupProposal | null {
  const teams = buildTeamProposals(
    pool,
    dateKey,
    alcoholFree,
    config,
    campusLifeZoneEnforced
  );
  if (teams.length < 2) return null;

  // 두 팀은 반드시 서로 다른 성별이다. 성별별로 상위 팀을 따로 추려서
  // 짝지으므로, 한쪽 성별이 점수 상위권을 독점해도 shortlist 가 한 성별로
  // 채워져 3:3 이 사라지는 일이 없다.
  const maleTeams = teams
    .filter((t) => t.gender === "male")
    .slice(0, config.teamShortlistSize);
  const femaleTeams = teams
    .filter((t) => t.gender === "female")
    .slice(0, config.teamShortlistSize);
  if (maleTeams.length === 0 || femaleTeams.length === 0) return null;

  const groups: GroupProposal[] = [];

  for (const left of maleTeams) {
    for (const right of femaleTeams) {
      let overlaps = false;
      for (const id of left.userIds) {
        if (right.userIds.has(id)) {
          overlaps = true;
          break;
        }
      }
      // 같은 uid 가 남/여 양쪽 문서에 존재하는 손상 데이터 방어.
      if (overlaps) continue;

      const members = [...left.members, ...right.members];
      // 비싼 6인 점수 계산 전에 생활권부터 거른다.
      // (isGroupAllowed 도 같은 조건을 강제하지만 O(36) pair loop보다 싸다)
      if (
        campusLifeZoneEnforced &&
        sharedCampusLifeZones(members).length === 0
      ) {
        continue;
      }
      if (
        !isGroupAllowed(
          members,
          dateKey,
          alcoholFree,
          BLIND_MEETING_GROUP_SIZE,
          campusLifeZoneEnforced
        )
      ) {
        continue;
      }

      const score = groupScore(
        left.members,
        right.members,
        config,
        alcoholFree
      );
      const bonus = waitingTimeBonus(members, config);
      groups.push({
        dateKey,
        commonDateKeys: groupCommonDateKeys(members),
        alcoholFree,
        algorithmVersion: config.algorithmVersion,
        teamA: left.members,
        teamB: right.members,
        score,
        adjustedScore: score.finalGroupScore + bonus,
        key: members
          .map((m) => m.userId)
          .sort()
          .join("|"),
      });
    }
  }

  if (groups.length === 0) return null;

  groups.sort((a, b) => {
    const diff = b.adjustedScore - a.adjustedScore;
    if (Math.abs(diff) > config.tieEpsilon) return diff > 0 ? 1 : -1;
    return a.key.localeCompare(b.key);
  });

  return groups[0];
}

export function proposeGroups(
  pool: Candidate[],
  dateKey: string,
  alcoholFree: boolean,
  maxGroups = 1,
  config: MatchingConfig = CURRENT_MATCHING_CONFIG
): GroupProposal[] {
  const selected: GroupProposal[] = [];
  let remaining = pool;
  for (let round = 0; round < maxGroups; round++) {
    const group = bestGroup(remaining, dateKey, alcoholFree, config);
    if (group == null) break;
    selected.push(group);
    const used = new Set([
      ...group.teamA.map((m) => m.userId),
      ...group.teamB.map((m) => m.userId),
    ]);
    remaining = remaining.filter((c) => !used.has(c.userId));
  }
  return selected;
}

export type ReplacementEvaluation = {
  candidate: Candidate;
  violations: ConstraintViolation[];
  scoreAfterReplacement: GroupScore | null;
  qualityRatio: number;
  adjustedScore: number;
  accepted: boolean;
};

export function evaluateReplacement(params: {
  /** 생활권 rollout activation (기본 ON). */
  campusLifeZoneEnforced?: boolean;
  teamA: Candidate[];
  teamB: Candidate[];
  vacantUserId: string;
  candidate: Candidate;
  baselineFinalGroupScore: number;
  dateKey: string;
  alcoholFree: boolean;
  urgent?: boolean;
  config?: MatchingConfig;
}): ReplacementEvaluation {
  const config = params.config ?? CURRENT_MATCHING_CONFIG;
  const threshold = params.urgent
    ? config.replacementUrgentRatio
    : config.replacementNormalRatio;

  const substitute = (team: Candidate[]) =>
    team.map((m) => (m.userId === params.vacantUserId ? params.candidate : m));

  const nextA = substitute(params.teamA);
  const nextB = substitute(params.teamB);
  const members = [...nextA, ...nextB];

  const violations = new Set<ConstraintViolation>();
  if (
    !members.some((m) => m.userId === params.candidate.userId) ||
    members.some((m) => m.userId === params.vacantUserId)
  ) {
    violations.add("invalidGroupSize");
  }
  for (const v of checkGroupConstraints(
    members,
    params.dateKey,
    params.alcoholFree,
    6,
    params.campusLifeZoneEnforced !== false
  )) {
    violations.add(v);
  }

  if (violations.size > 0) {
    return {
      candidate: params.candidate,
      violations: [...violations],
      scoreAfterReplacement: null,
      qualityRatio: 0,
      adjustedScore: 0,
      accepted: false,
    };
  }

  const score = groupScore(nextA, nextB, config, params.alcoholFree);
  const ratio =
    params.baselineFinalGroupScore <= 0
      ? 1
      : score.finalGroupScore / params.baselineFinalGroupScore;
  const bonus = waitingTimeBonus([params.candidate], config);

  return {
    candidate: params.candidate,
    violations: [],
    scoreAfterReplacement: score,
    qualityRatio: ratio,
    adjustedScore: score.finalGroupScore + bonus,
    accepted: ratio + config.tieEpsilon >= threshold,
  };
}

export function rankReplacements(params: {
  /** 생활권 rollout activation (기본 ON). evaluateReplacement 로 그대로 전달된다. */
  campusLifeZoneEnforced?: boolean;
  teamA: Candidate[];
  teamB: Candidate[];
  vacantUserId: string;
  candidates: Candidate[];
  baselineFinalGroupScore: number;
  dateKey: string;
  alcoholFree: boolean;
  urgent?: boolean;
  limit?: number;
  config?: MatchingConfig;
}): ReplacementEvaluation[] {
  const config = params.config ?? CURRENT_MATCHING_CONFIG;
  const seatUserIds = new Set([
    ...params.teamA.map((m) => m.userId),
    ...params.teamB.map((m) => m.userId),
  ]);

  const evaluations: ReplacementEvaluation[] = [];
  for (const candidate of params.candidates) {
    if (seatUserIds.has(candidate.userId)) continue;
    const evaluation = evaluateReplacement({ ...params, candidate, config });
    if (evaluation.accepted) evaluations.push(evaluation);
  }

  evaluations.sort((a, b) => {
    const diff = b.adjustedScore - a.adjustedScore;
    if (Math.abs(diff) > config.tieEpsilon) return diff > 0 ? 1 : -1;
    return a.candidate.userId.localeCompare(b.candidate.userId);
  });

  return evaluations.slice(0, params.limit ?? 3);
}
