// =============================================================================
// 3:3 블라인드 취향 미팅 — 점수 계산
// 경로: lib/features/blind_meeting/domain/matching/blind_meeting_scoring.dart
//
// 모든 요소는 [0, 1] 로 정규화된다.
// 1단계: 같은 편인 우리 팀 3명 구성 품질 (internalTeamScore)
// 2단계: 완성된 두 팀 사이의 호환성 (crossTeamScore)
// 최종:  finalGroupScore
//
// 순수 함수만 두고, Firestore/Flutter 의존성은 없다.
// =============================================================================

import '../../../../constants/interest_taxonomy.dart';
import '../blind_meeting_enums.dart';
import 'blind_meeting_candidate.dart';
import 'blind_meeting_matching_config.dart';

/// 미팅 목적 호환 결과.
class MeetingPurposeCompatibility {
  /// [0, 1] 정규화 점수.
  final double score;

  /// `연애만` × `친구만` 처럼 원칙적으로 같은 미팅에 배정하지 않아야 하는 조합.
  final bool isDirectConflict;

  const MeetingPurposeCompatibility(
    this.score, {
    this.isDirectConflict = false,
  });
}

/// 미팅 목적 호환 matrix.
///
/// | A | B | 처리 |
/// |---|---|---|
/// | 연애 | 연애 | 높은 호환 |
/// | 연애 | 둘 다 | 호환 |
/// | 둘 다 | 둘 다 | 높은 호환 |
/// | 친구 | 둘 다 | 호환 |
/// | 친구 | 친구 | 높은 호환 |
/// | 연애만 | 친구만 | 원칙적으로 분리 |
MeetingPurposeCompatibility purposeCompatibility(
  MeetingPurpose a,
  MeetingPurpose b,
) {
  if (a == MeetingPurpose.romance && b == MeetingPurpose.friendship ||
      a == MeetingPurpose.friendship && b == MeetingPurpose.romance) {
    return const MeetingPurposeCompatibility(0.0, isDirectConflict: true);
  }
  if (a == b) return const MeetingPurposeCompatibility(1.0);
  // 한쪽이 `둘 다` 인 경우
  return const MeetingPurposeCompatibility(0.8);
}

/// 관심사 연결성.
///
/// 정확 일치만 쓰지 않고 온보딩 taxonomy의 카테고리 겹침도 함께 반영한다.
double interestSimilarity(Set<String> a, Set<String> b) {
  if (a.isEmpty || b.isEmpty) return 0.0;

  final exactOverlap = a.intersection(b).length;
  final exactScore = exactOverlap / (a.length < b.length ? a.length : b.length);

  final categoriesA = a.map(interestCategoryIdOf).toSet();
  final categoriesB = b.map(interestCategoryIdOf).toSet();
  final unionSize = categoriesA.union(categoriesB).length;
  final categoryScore = unionSize == 0
      ? 0.0
      : categoriesA.intersection(categoriesB).length / unionSize;

  return _clamp01(0.65 * exactScore + 0.35 * categoryScore);
}

/// 두 사람이 관심사를 하나라도 공유하는지.
bool sharesAnyInterest(Set<String> a, Set<String> b) =>
    a.intersection(b).isNotEmpty;

/// 대화 분위기 호환.
double atmosphereCompatibility(
  ConversationAtmosphere a,
  ConversationAtmosphere b,
) {
  if (a == ConversationAtmosphere.either ||
      b == ConversationAtmosphere.either) {
    return a == b ? 0.90 : 0.85;
  }
  return a == b ? 1.0 : 0.35;
}

/// 먼저 말하는 성향 호환.
///
/// 서로 보완되는 조합(주도 ↔ 경청)을 높게, 전원 경청 조합을 가장 낮게 본다.
double initiativeCompatibility(
  ConversationInitiative a,
  ConversationInitiative b,
) {
  const scores = <String, double>{
    'initiator|listener': 1.0,
    'initiator|adaptive': 0.90,
    'adaptive|listener': 0.85,
    'adaptive|adaptive': 0.80,
    'initiator|initiator': 0.60,
    'listener|listener': 0.25,
  };
  final keyDirect = '${a.name}|${b.name}';
  final keyReversed = '${b.name}|${a.name}';
  return scores[keyDirect] ?? scores[keyReversed] ?? 0.5;
}

/// 한 사람의 음주 동석 선호가 상대의 음주 정도를 얼마나 수용하는지 (단방향).
double alcoholToleranceScore(
  AlcoholCompanionPreference preference,
  DrinkingLevel otherLevel,
) {
  switch (preference) {
    case AlcoholCompanionPreference.allSober:
      return otherLevel.isSober ? 1.0 : 0.0;
    case AlcoholCompanionPreference.lightOkay:
      return switch (otherLevel) {
        DrinkingLevel.none => 1.0,
        DrinkingLevel.sometimes => 0.80,
        DrinkingLevel.weekly1_2 => 0.50,
        DrinkingLevel.often => 0.20,
      };
    case AlcoholCompanionPreference.noPreference:
      return 1.0;
  }
}

/// 음주 호환 (양방향 중 더 불편한 쪽 기준).
double alcoholCompatibility(BlindMeetingCandidate a, BlindMeetingCandidate b) {
  final aToB = alcoholToleranceScore(a.alcoholPreference, b.drinkingLevel);
  final bToA = alcoholToleranceScore(b.alcoholPreference, a.drinkingLevel);
  return aToB < bToA ? aToB : bToA;
}

/// 한 사람의 흡연 동석 선호가 상대의 흡연 상태를 얼마나 수용하는지 (단방향).
double smokingToleranceScore(
  SmokingCompanionPreference preference,
  SmokingStatus otherStatus,
) {
  if (!otherStatus.isSmoker) return 1.0;
  return switch (preference) {
    SmokingCompanionPreference.nonSmokersOnly => 0.0,
    SmokingCompanionPreference.noIndoorSmoking => 0.70,
    SmokingCompanionPreference.noPreference => 1.0,
  };
}

/// 흡연 호환 (양방향 중 더 불편한 쪽 기준).
double smokingCompatibility(BlindMeetingCandidate a, BlindMeetingCandidate b) {
  final aToB = smokingToleranceScore(a.smokingPreference, b.smokingStatus);
  final bToA = smokingToleranceScore(b.smokingPreference, a.smokingStatus);
  return aToB < bToA ? aToB : bToA;
}

/// MBTI 보조 신호. 값이 없으면 중립(0.5).
double mbtiCompatibility(String? a, String? b) {
  final left = _normalizeMbti(a);
  final right = _normalizeMbti(b);
  if (left == null || right == null) return 0.5;

  // E/I는 보완될 때, N/S는 같을 때 대화가 잘 이어진다는 가정.
  final ei = left[0] == right[0] ? 0.70 : 1.0;
  final ns = left[1] == right[1] ? 1.0 : 0.50;
  final tf = left[2] == right[2] ? 0.90 : 0.80;
  final jp = left[3] == right[3] ? 0.90 : 0.80;
  return _clamp01((ei + ns + tf + jp) / 4);
}

/// 두 참가자 사이 종합 호환도 (상대 팀 계산에 사용).
double pairCompatibility(
  BlindMeetingCandidate a,
  BlindMeetingCandidate b, {
  required BlindMeetingCrossWeights weights,
}) {
  final purpose = purposeCompatibility(a.purpose, b.purpose);
  final total = weights.total;
  if (total <= 0) return 0.0;

  final raw =
      weights.purpose * purpose.score +
      weights.interest * interestSimilarity(a.interestIds, b.interestIds) +
      weights.alcohol * alcoholCompatibility(a, b) +
      weights.atmosphere * atmosphereCompatibility(a.atmosphere, b.atmosphere) +
      weights.initiative * initiativeCompatibility(a.initiative, b.initiative) +
      weights.smoking * smokingCompatibility(a, b) +
      weights.mbti * mbtiCompatibility(a.mbti, b.mbti);

  return _clamp01(raw / total);
}

/// 우리 팀 3명 구성 품질 세부 점수.
class InternalTeamScoreBreakdown {
  final double initiativeBalance;
  final double atmosphereBalance;
  final double interestConnection;
  final double purposeConsistency;
  final double alcohol;
  final double smoking;
  final double mbti;
  final double total;

  const InternalTeamScoreBreakdown({
    required this.initiativeBalance,
    required this.atmosphereBalance,
    required this.interestConnection,
    required this.purposeConsistency,
    required this.alcohol,
    required this.smoking,
    required this.mbti,
    required this.total,
  });

  Map<String, dynamic> toMap() => {
    'initiativeBalance': initiativeBalance,
    'atmosphereBalance': atmosphereBalance,
    'interestConnection': interestConnection,
    'purposeConsistency': purposeConsistency,
    'alcohol': alcohol,
    'smoking': smoking,
    'mbti': mbti,
    'total': total,
  };
}

/// 먼저 말하는 성향 균형.
///
/// 이상적인 구성은 `주도 1명 / 상황에 맞춰 1명 / 경청 1명`이다.
/// 세 명 모두 소극적인 구성은 강하게 감점, 세 명 모두 주도는 약하게 감점한다.
double initiativeBalanceScore(
  List<ConversationInitiative> initiatives, {
  required BlindMeetingMatchingConfig config,
}) {
  if (initiatives.isEmpty) return 0.0;
  final size = initiatives.length;

  var initiators = 0;
  var adaptives = 0;
  var listeners = 0;
  for (final initiative in initiatives) {
    switch (initiative) {
      case ConversationInitiative.initiator:
        initiators++;
      case ConversationInitiative.adaptive:
        adaptives++;
      case ConversationInitiative.listener:
        listeners++;
    }
  }

  // 이상 분포 (1/3, 1/3, 1/3) 와의 L1 거리 → 균형 점수
  const ideal = 1 / 3;
  final l1 =
      (initiators / size - ideal).abs() +
      (adaptives / size - ideal).abs() +
      (listeners / size - ideal).abs();
  var score = _clamp01(1.0 - 0.5 * l1);

  if (listeners == size) {
    score *= config.allPassiveTeamMultiplier;
  } else if (initiators == size) {
    score *= config.allDominantTeamMultiplier;
  } else if (initiators == 0) {
    score *= config.noInitiatorTeamMultiplier;
  }

  return _clamp01(score);
}

/// 팀 내부 관심사 연결성.
///
/// "각 참가자는 같은 팀원 중 최소 한 명과 관심사가 겹치도록" 을 주 신호로 쓰고,
/// 평균 유사도를 보조 신호로 섞는다.
double teamInterestConnectionScore(List<BlindMeetingCandidate> team) {
  if (team.length < 2) return 0.0;

  var connected = 0;
  for (var i = 0; i < team.length; i++) {
    for (var j = 0; j < team.length; j++) {
      if (i == j) continue;
      if (sharesAnyInterest(team[i].interestIds, team[j].interestIds)) {
        connected++;
        break;
      }
    }
  }
  final coverage = connected / team.length;
  final mean = _meanPairwise(
    team,
    (a, b) => interestSimilarity(a.interestIds, b.interestIds),
  );
  return _clamp01(0.6 * coverage + 0.4 * mean);
}

/// 팀 내부 미팅 목적 일관성. 직접 충돌이 하나라도 있으면 0.
double teamPurposeConsistencyScore(List<BlindMeetingCandidate> team) {
  if (team.length < 2) return 0.0;
  var sum = 0.0;
  var count = 0;
  for (var i = 0; i < team.length; i++) {
    for (var j = i + 1; j < team.length; j++) {
      final compatibility = purposeCompatibility(
        team[i].purpose,
        team[j].purpose,
      );
      if (compatibility.isDirectConflict) return 0.0;
      sum += compatibility.score;
      count++;
    }
  }
  return count == 0 ? 0.0 : _clamp01(sum / count);
}

/// 우리 팀 3명 구성 품질.
InternalTeamScoreBreakdown internalTeamScore(
  List<BlindMeetingCandidate> team, {
  required BlindMeetingMatchingConfig config,
  required bool alcoholFree,
}) {
  final weights = config.teamWeightsFor(alcoholFree: alcoholFree);
  final initiativeBalance = initiativeBalanceScore(
    team.map((c) => c.initiative).toList(),
    config: config,
  );
  final atmosphereBalance = _meanPairwise(
    team,
    (a, b) => atmosphereCompatibility(a.atmosphere, b.atmosphere),
  );
  final interestConnection = teamInterestConnectionScore(team);
  final purposeConsistency = teamPurposeConsistencyScore(team);
  final alcohol = _meanPairwise(team, alcoholCompatibility);
  final smoking = _meanPairwise(team, smokingCompatibility);
  final mbti = _meanPairwise(team, (a, b) => mbtiCompatibility(a.mbti, b.mbti));

  final total = weights.total;
  final weighted = total <= 0
      ? 0.0
      : (weights.initiativeBalance * initiativeBalance +
                weights.atmosphereBalance * atmosphereBalance +
                weights.interestConnection * interestConnection +
                weights.purposeConsistency * purposeConsistency +
                weights.alcohol * alcohol +
                weights.smoking * smoking +
                weights.mbti * mbti) /
            total;

  return InternalTeamScoreBreakdown(
    initiativeBalance: initiativeBalance,
    atmosphereBalance: atmosphereBalance,
    interestConnection: interestConnection,
    purposeConsistency: purposeConsistency,
    alcohol: alcohol,
    smoking: smoking,
    mbti: mbti,
    total: _clamp01(weighted),
  );
}

/// 6인 구성 결과 점수.
class BlindMeetingGroupScore {
  final double teamAInternal;
  final double teamBInternal;

  /// 참가자별 `상대 팀 3명과의 평균 호환도`.
  final Map<String, double> participantOpponentScores;

  final double crossTeamScore;

  /// 참가자별 상대 팀 평균 중 최저값 (최저 참가자 만족도 보호).
  final double minimumParticipantScore;

  final double finalGroupScore;

  const BlindMeetingGroupScore({
    required this.teamAInternal,
    required this.teamBInternal,
    required this.participantOpponentScores,
    required this.crossTeamScore,
    required this.minimumParticipantScore,
    required this.finalGroupScore,
  });

  Map<String, dynamic> toMap() => {
    'internalTeamScores': {'teamA': teamAInternal, 'teamB': teamBInternal},
    'participantOpponentScores': participantOpponentScores,
    'crossTeamScore': crossTeamScore,
    'minimumParticipantScore': minimumParticipantScore,
    'finalGroupScore': finalGroupScore,
  };
}

/// 한 참가자가 상대 팀 3명에게 갖는 평균 호환도.
double participantOpponentScore(
  BlindMeetingCandidate participant,
  List<BlindMeetingCandidate> opponents, {
  required BlindMeetingCrossWeights weights,
}) {
  if (opponents.isEmpty) return 0.0;
  var sum = 0.0;
  for (final opponent in opponents) {
    sum += pairCompatibility(participant, opponent, weights: weights);
  }
  return _clamp01(sum / opponents.length);
}

/// 두 팀이 완성된 뒤의 6인 구성 점수.
BlindMeetingGroupScore groupScore({
  required List<BlindMeetingCandidate> teamA,
  required List<BlindMeetingCandidate> teamB,
  required BlindMeetingMatchingConfig config,
  required bool alcoholFree,
}) {
  final crossWeights = config.crossWeightsFor(alcoholFree: alcoholFree);
  final internalA = internalTeamScore(
    teamA,
    config: config,
    alcoholFree: alcoholFree,
  ).total;
  final internalB = internalTeamScore(
    teamB,
    config: config,
    alcoholFree: alcoholFree,
  ).total;

  final scores = <String, double>{};
  for (final member in teamA) {
    scores[member.userId] = participantOpponentScore(
      member,
      teamB,
      weights: crossWeights,
    );
  }
  for (final member in teamB) {
    scores[member.userId] = participantOpponentScore(
      member,
      teamA,
      weights: crossWeights,
    );
  }

  if (scores.isEmpty) {
    return const BlindMeetingGroupScore(
      teamAInternal: 0,
      teamBInternal: 0,
      participantOpponentScores: <String, double>{},
      crossTeamScore: 0,
      minimumParticipantScore: 0,
      finalGroupScore: 0,
    );
  }

  final values = scores.values.toList();
  final mean = values.reduce((a, b) => a + b) / values.length;
  final minimum = values.reduce((a, b) => a < b ? a : b);
  final cross = _clamp01(
    config.crossTeamMeanWeight * mean + config.crossTeamMinWeight * minimum,
  );
  final internalMean = (internalA + internalB) / 2;
  final finalScore = _clamp01(
    config.finalInternalWeight * internalMean + config.finalCrossWeight * cross,
  );

  return BlindMeetingGroupScore(
    teamAInternal: internalA,
    teamBInternal: internalB,
    participantOpponentScores: Map<String, double>.unmodifiable(scores),
    crossTeamScore: cross,
    minimumParticipantScore: minimum,
    finalGroupScore: finalScore,
  );
}

/// 대기 시간 starvation 방지 보정치.
///
/// 최대 [BlindMeetingMatchingConfig.maxWaitingBonus] 까지만 더해지고,
/// hard constraint 판정에는 전혀 영향을 주지 않는다.
double waitingTimeBonus(
  Iterable<BlindMeetingCandidate> members, {
  required BlindMeetingMatchingConfig config,
}) {
  final list = members.toList();
  if (list.isEmpty) return 0.0;
  final saturation = config.waitingBonusSaturationMinutes;
  if (saturation <= 0) return 0.0;

  var sum = 0.0;
  for (final member in list) {
    final ratio = member.waitedMinutes <= 0
        ? 0.0
        : (member.waitedMinutes / saturation);
    sum += _clamp01(ratio);
  }
  return config.maxWaitingBonus * (sum / list.length);
}

// -----------------------------------------------------------------------------
// 내부 유틸
// -----------------------------------------------------------------------------

double _meanPairwise(
  List<BlindMeetingCandidate> members,
  double Function(BlindMeetingCandidate a, BlindMeetingCandidate b) metric,
) {
  if (members.length < 2) return 0.0;
  var sum = 0.0;
  var count = 0;
  for (var i = 0; i < members.length; i++) {
    for (var j = i + 1; j < members.length; j++) {
      sum += metric(members[i], members[j]);
      count++;
    }
  }
  return count == 0 ? 0.0 : _clamp01(sum / count);
}

String? _normalizeMbti(String? raw) {
  final text = raw?.trim().toUpperCase();
  if (text == null || text.length != 4) return null;
  const axes = [
    ['E', 'I'],
    ['N', 'S'],
    ['T', 'F'],
    ['J', 'P'],
  ];
  for (var i = 0; i < 4; i++) {
    if (!axes[i].contains(text[i])) return null;
  }
  return text;
}

double _clamp01(double value) {
  if (value.isNaN) return 0.0;
  if (value < 0) return 0.0;
  if (value > 1) return 1.0;
  return value;
}
