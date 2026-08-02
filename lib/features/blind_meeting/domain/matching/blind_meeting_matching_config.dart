// =============================================================================
// 3:3 블라인드 취향 미팅 — 버전 관리되는 매칭 설정
// 경로: lib/features/blind_meeting/domain/matching/blind_meeting_matching_config.dart
//
// 가중치를 코드 곳곳에 흩어놓지 않고 이 파일 하나에서만 관리한다.
// 서버 구현(functions/src/blindMeeting/matchingConfig.ts)은 동일한 숫자를
// 사용하며, 두 구현의 일치는 골든 벡터 테스트로 검증한다.
//   - Dart : test/features/blind_meeting/matching_golden_vectors_test.dart
//   - TS   : functions/src/blindMeeting/__tests__/matching.test.ts
// 매칭 결과 문서에는 항상 algorithmVersion을 함께 저장한다.
// =============================================================================

/// 우리 팀(같은 편) 3명 구성 품질 가중치. 합은 1.0.
class BlindMeetingTeamWeights {
  final double initiativeBalance;
  final double atmosphereBalance;
  final double interestConnection;
  final double purposeConsistency;
  final double alcohol;
  final double smoking;
  final double mbti;

  const BlindMeetingTeamWeights({
    required this.initiativeBalance,
    required this.atmosphereBalance,
    required this.interestConnection,
    required this.purposeConsistency,
    required this.alcohol,
    required this.smoking,
    required this.mbti,
  });

  double get total =>
      initiativeBalance +
      atmosphereBalance +
      interestConnection +
      purposeConsistency +
      alcohol +
      smoking +
      mbti;
}

/// 두 팀 사이 호환성 가중치. 합은 1.0.
class BlindMeetingCrossWeights {
  final double purpose;
  final double interest;
  final double alcohol;
  final double atmosphere;
  final double initiative;
  final double smoking;
  final double mbti;

  const BlindMeetingCrossWeights({
    required this.purpose,
    required this.interest,
    required this.alcohol,
    required this.atmosphere,
    required this.initiative,
    required this.smoking,
    required this.mbti,
  });

  double get total =>
      purpose + interest + alcohol + atmosphere + initiative + smoking + mbti;
}

/// 한 버전의 매칭 설정 전체.
class BlindMeetingMatchingConfig {
  /// 매칭 결과 문서에 저장되는 알고리즘 버전 문자열.
  final String algorithmVersion;

  final BlindMeetingTeamWeights teamWeights;
  final BlindMeetingCrossWeights crossWeights;

  /// 무알코올 전용 미팅에서는 음주가 이미 hard constraint이므로 가중치를 재분배한다.
  final BlindMeetingTeamWeights alcoholFreeTeamWeights;
  final BlindMeetingCrossWeights alcoholFreeCrossWeights;

  /// crossTeamScore = 평균 × [crossTeamMeanWeight] + 최저 × [crossTeamMinWeight]
  final double crossTeamMeanWeight;
  final double crossTeamMinWeight;

  /// finalGroupScore = 팀 내부 품질 평균 × [finalInternalWeight]
  ///                 + crossTeamScore × [finalCrossWeight]
  final double finalInternalWeight;
  final double finalCrossWeight;

  /// 대기 시간 보정 최대치. hard constraint를 절대 넘지 못한다.
  final double maxWaitingBonus;

  /// 보정이 최대치에 도달하는 대기 시간(분).
  final int waitingBonusSaturationMinutes;

  /// 일반 대체 후보 최소 품질 비율.
  final double replacementNormalRatio;

  /// 미팅 직전 긴급 대체 후보 최소 품질 비율.
  final double replacementUrgentRatio;

  /// 세 명 모두 소극적일 때 곱하는 감점 계수 (강한 감점).
  final double allPassiveTeamMultiplier;

  /// 세 명 모두 강하게 주도할 때 곱하는 감점 계수 (약한 감점).
  final double allDominantTeamMultiplier;

  /// 팀에 먼저 말하는 사람이 아무도 없을 때 곱하는 계수.
  final double noInitiatorTeamMultiplier;

  /// 점수 동점 판정 허용 오차.
  final double tieEpsilon;

  const BlindMeetingMatchingConfig({
    required this.algorithmVersion,
    required this.teamWeights,
    required this.crossWeights,
    required this.alcoholFreeTeamWeights,
    required this.alcoholFreeCrossWeights,
    this.crossTeamMeanWeight = 0.70,
    this.crossTeamMinWeight = 0.30,
    this.finalInternalWeight = 0.40,
    this.finalCrossWeight = 0.60,
    this.maxWaitingBonus = 0.03,
    this.waitingBonusSaturationMinutes = 2880,
    this.replacementNormalRatio = 0.85,
    this.replacementUrgentRatio = 0.75,
    this.allPassiveTeamMultiplier = 0.65,
    this.allDominantTeamMultiplier = 0.88,
    this.noInitiatorTeamMultiplier = 0.90,
    this.tieEpsilon = 1e-9,
  });

  BlindMeetingTeamWeights teamWeightsFor({required bool alcoholFree}) =>
      alcoholFree ? alcoholFreeTeamWeights : teamWeights;

  BlindMeetingCrossWeights crossWeightsFor({required bool alcoholFree}) =>
      alcoholFree ? alcoholFreeCrossWeights : crossWeights;

  /// 현재 운영 버전.
  static const BlindMeetingMatchingConfig v1 = BlindMeetingMatchingConfig(
    algorithmVersion: 'blind_taste_v1',
    teamWeights: BlindMeetingTeamWeights(
      initiativeBalance: 0.30,
      atmosphereBalance: 0.25,
      interestConnection: 0.20,
      purposeConsistency: 0.15,
      alcohol: 0.05,
      smoking: 0.03,
      mbti: 0.02,
    ),
    crossWeights: BlindMeetingCrossWeights(
      purpose: 0.30,
      interest: 0.25,
      alcohol: 0.15,
      atmosphere: 0.10,
      initiative: 0.10,
      smoking: 0.05,
      mbti: 0.05,
    ),
    alcoholFreeTeamWeights: BlindMeetingTeamWeights(
      initiativeBalance: 0.32,
      atmosphereBalance: 0.28,
      interestConnection: 0.23,
      purposeConsistency: 0.15,
      alcohol: 0.0,
      smoking: 0.0,
      mbti: 0.02,
    ),
    alcoholFreeCrossWeights: BlindMeetingCrossWeights(
      purpose: 0.35,
      interest: 0.30,
      alcohol: 0.0,
      atmosphere: 0.15,
      initiative: 0.13,
      smoking: 0.0,
      mbti: 0.07,
    ),
  );

  /// 현재 기본 설정.
  static const BlindMeetingMatchingConfig current = v1;
}
