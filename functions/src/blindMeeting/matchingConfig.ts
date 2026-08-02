/**
 * 3:3 블라인드 취향 미팅 — 버전 관리되는 매칭 설정 (서버)
 * 경로: functions/src/blindMeeting/matchingConfig.ts
 *
 * 원본 명세: lib/features/blind_meeting/domain/matching/blind_meeting_matching_config.dart
 * 두 사본의 숫자 일치는 양쪽 테스트에서 검증한다.
 */

export type TeamWeights = {
  initiativeBalance: number;
  atmosphereBalance: number;
  interestConnection: number;
  purposeConsistency: number;
  alcohol: number;
  smoking: number;
  mbti: number;
};

export type CrossWeights = {
  purpose: number;
  interest: number;
  alcohol: number;
  atmosphere: number;
  initiative: number;
  smoking: number;
  mbti: number;
};

export type MatchingConfig = {
  algorithmVersion: string;
  teamWeights: TeamWeights;
  crossWeights: CrossWeights;
  alcoholFreeTeamWeights: TeamWeights;
  alcoholFreeCrossWeights: CrossWeights;
  crossTeamMeanWeight: number;
  crossTeamMinWeight: number;
  finalInternalWeight: number;
  finalCrossWeight: number;
  maxWaitingBonus: number;
  waitingBonusSaturationMinutes: number;
  replacementNormalRatio: number;
  replacementUrgentRatio: number;
  allPassiveTeamMultiplier: number;
  allDominantTeamMultiplier: number;
  noInitiatorTeamMultiplier: number;
  tieEpsilon: number;
  /** 3명 조합을 전부 열거하는 후보 수 상한 */
  exhaustiveTeamPoolLimit: number;
  /** 2단계로 넘길 상위 팀 후보 개수 */
  teamShortlistSize: number;
  /** bounded greedy에서 seed가 검사할 이웃 수 */
  neighborhoodSize: number;
};

export const BLIND_TASTE_V1: MatchingConfig = {
  algorithmVersion: "blind_taste_v1",
  teamWeights: {
    initiativeBalance: 0.3,
    atmosphereBalance: 0.25,
    interestConnection: 0.2,
    purposeConsistency: 0.15,
    alcohol: 0.05,
    smoking: 0.03,
    mbti: 0.02,
  },
  crossWeights: {
    purpose: 0.3,
    interest: 0.25,
    alcohol: 0.15,
    atmosphere: 0.1,
    initiative: 0.1,
    smoking: 0.05,
    mbti: 0.05,
  },
  alcoholFreeTeamWeights: {
    initiativeBalance: 0.32,
    atmosphereBalance: 0.28,
    interestConnection: 0.23,
    purposeConsistency: 0.15,
    alcohol: 0,
    smoking: 0,
    mbti: 0.02,
  },
  alcoholFreeCrossWeights: {
    purpose: 0.35,
    interest: 0.3,
    alcohol: 0,
    atmosphere: 0.15,
    initiative: 0.13,
    smoking: 0,
    mbti: 0.07,
  },
  crossTeamMeanWeight: 0.7,
  crossTeamMinWeight: 0.3,
  finalInternalWeight: 0.4,
  finalCrossWeight: 0.6,
  maxWaitingBonus: 0.03,
  waitingBonusSaturationMinutes: 2880,
  replacementNormalRatio: 0.85,
  replacementUrgentRatio: 0.75,
  allPassiveTeamMultiplier: 0.65,
  allDominantTeamMultiplier: 0.88,
  noInitiatorTeamMultiplier: 0.9,
  tieEpsilon: 1e-9,
  exhaustiveTeamPoolLimit: 14,
  teamShortlistSize: 40,
  neighborhoodSize: 12,
};

export const CURRENT_MATCHING_CONFIG: MatchingConfig = BLIND_TASTE_V1;

export function teamWeightsTotal(w: TeamWeights): number {
  return (
    w.initiativeBalance +
    w.atmosphereBalance +
    w.interestConnection +
    w.purposeConsistency +
    w.alcohol +
    w.smoking +
    w.mbti
  );
}

export function crossWeightsTotal(w: CrossWeights): number {
  return (
    w.purpose +
    w.interest +
    w.alcohol +
    w.atmosphere +
    w.initiative +
    w.smoking +
    w.mbti
  );
}

export function teamWeightsFor(
  config: MatchingConfig,
  alcoholFree: boolean
): TeamWeights {
  return alcoholFree ? config.alcoholFreeTeamWeights : config.teamWeights;
}

export function crossWeightsFor(
  config: MatchingConfig,
  alcoholFree: boolean
): CrossWeights {
  return alcoholFree ? config.alcoholFreeCrossWeights : config.crossWeights;
}
