import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_matching_config.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_scoring.dart';

import 'blind_meeting_test_fixtures.dart';

void main() {
  const config = BlindMeetingMatchingConfig.current;

  group('가중치 설정', () {
    test('일반 미팅 가중치 합은 1.0', () {
      expect(config.teamWeights.total, closeTo(1.0, 1e-9));
      expect(config.crossWeights.total, closeTo(1.0, 1e-9));
    });

    test('무알코올 미팅 가중치 합도 1.0이고 음주·흡연 가중치는 0', () {
      expect(config.alcoholFreeTeamWeights.total, closeTo(1.0, 1e-9));
      expect(config.alcoholFreeCrossWeights.total, closeTo(1.0, 1e-9));
      expect(config.alcoholFreeTeamWeights.alcohol, 0);
      expect(config.alcoholFreeTeamWeights.smoking, 0);
      expect(config.alcoholFreeCrossWeights.alcohol, 0);
      expect(config.alcoholFreeCrossWeights.smoking, 0);
    });

    test('MBTI는 목적·관심사·음주·대화 성향보다 비중이 낮다', () {
      expect(config.crossWeights.mbti, lessThan(config.crossWeights.purpose));
      expect(config.crossWeights.mbti, lessThan(config.crossWeights.interest));
      expect(config.crossWeights.mbti, lessThan(config.crossWeights.alcohol));
      expect(
        config.crossWeights.mbti,
        lessThanOrEqualTo(config.crossWeights.atmosphere),
      );
    });
  });

  group('미팅 목적 호환 matrix', () {
    test('연애 × 연애 는 높은 호환', () {
      final result = purposeCompatibility(
        MeetingPurpose.romance,
        MeetingPurpose.romance,
      );
      expect(result.score, 1.0);
      expect(result.isDirectConflict, isFalse);
    });

    test('친구 × 친구 는 높은 호환', () {
      expect(
        purposeCompatibility(
          MeetingPurpose.friendship,
          MeetingPurpose.friendship,
        ).score,
        1.0,
      );
    });

    test('둘 다 × 둘 다 는 높은 호환', () {
      expect(
        purposeCompatibility(MeetingPurpose.both, MeetingPurpose.both).score,
        1.0,
      );
    });

    test('연애 × 둘 다 / 친구 × 둘 다 는 호환', () {
      expect(
        purposeCompatibility(MeetingPurpose.romance, MeetingPurpose.both).score,
        0.8,
      );
      expect(
        purposeCompatibility(
          MeetingPurpose.friendship,
          MeetingPurpose.both,
        ).score,
        0.8,
      );
    });

    test('연애만 × 친구만 은 직접 충돌로 분리', () {
      final forward = purposeCompatibility(
        MeetingPurpose.romance,
        MeetingPurpose.friendship,
      );
      final backward = purposeCompatibility(
        MeetingPurpose.friendship,
        MeetingPurpose.romance,
      );
      expect(forward.isDirectConflict, isTrue);
      expect(forward.score, 0.0);
      expect(backward.isDirectConflict, isTrue);
    });
  });

  group('관심사 연결성', () {
    test('완전히 같은 관심사는 1.0', () {
      expect(interestSimilarity({'커피', '영화'}, {'커피', '영화'}), 1.0);
    });

    test('한쪽이 비면 0.0', () {
      expect(interestSimilarity(<String>{}, {'커피'}), 0.0);
    });

    test('정확히 겹치는 항목이 없어도 같은 카테고리면 0보다 크다', () {
      // '커피'와 '와인'은 모두 음식 카테고리
      final score = interestSimilarity({'커피'}, {'와인'});
      expect(score, greaterThan(0.0));
      expect(score, lessThan(1.0));
    });

    test('겹치는 항목이 많을수록 점수가 높다', () {
      final low = interestSimilarity({'커피', '영화', '농구'}, {'커피', '락/밴드', '수영'});
      final high = interestSimilarity({'커피', '영화', '농구'}, {'커피', '영화', '농구'});
      expect(high, greaterThan(low));
    });

    test('sharesAnyInterest 는 교집합 존재 여부', () {
      expect(sharesAnyInterest({'커피'}, {'커피', '영화'}), isTrue);
      expect(sharesAnyInterest({'커피'}, {'영화'}), isFalse);
    });
  });

  group('대화 분위기 호환', () {
    test('같은 분위기는 1.0, 정반대는 낮다', () {
      expect(
        atmosphereCompatibility(
          ConversationAtmosphere.calm,
          ConversationAtmosphere.calm,
        ),
        1.0,
      );
      expect(
        atmosphereCompatibility(
          ConversationAtmosphere.calm,
          ConversationAtmosphere.lively,
        ),
        lessThan(0.5),
      );
    });

    test('둘 다 괜찮은 사용자는 어느 쪽과도 높게 호환', () {
      expect(
        atmosphereCompatibility(
          ConversationAtmosphere.either,
          ConversationAtmosphere.lively,
        ),
        greaterThan(0.8),
      );
    });
  });

  group('먼저 말하는 성향 호환', () {
    test('주도 ↔ 경청 이 가장 높다', () {
      expect(
        initiativeCompatibility(
          ConversationInitiative.initiator,
          ConversationInitiative.listener,
        ),
        1.0,
      );
    });

    test('경청 ↔ 경청 이 가장 낮다', () {
      final listeners = initiativeCompatibility(
        ConversationInitiative.listener,
        ConversationInitiative.listener,
      );
      final initiators = initiativeCompatibility(
        ConversationInitiative.initiator,
        ConversationInitiative.initiator,
      );
      expect(listeners, lessThan(initiators));
      expect(listeners, 0.25);
    });

    test('대칭이다', () {
      expect(
        initiativeCompatibility(
          ConversationInitiative.initiator,
          ConversationInitiative.adaptive,
        ),
        initiativeCompatibility(
          ConversationInitiative.adaptive,
          ConversationInitiative.initiator,
        ),
      );
    });
  });

  group('음주 호환', () {
    test('전원 비음주 선호는 음주자와 0.0', () {
      expect(
        alcoholToleranceScore(
          AlcoholCompanionPreference.allSober,
          DrinkingLevel.sometimes,
        ),
        0.0,
      );
      expect(
        alcoholToleranceScore(
          AlcoholCompanionPreference.allSober,
          DrinkingLevel.none,
        ),
        1.0,
      );
    });

    test('가벼운 음주 허용은 음주 빈도가 높을수록 점수가 낮다', () {
      final sometimes = alcoholToleranceScore(
        AlcoholCompanionPreference.lightOkay,
        DrinkingLevel.sometimes,
      );
      final often = alcoholToleranceScore(
        AlcoholCompanionPreference.lightOkay,
        DrinkingLevel.often,
      );
      expect(sometimes, greaterThan(often));
    });

    test('양방향 중 더 불편한 쪽을 사용한다', () {
      final strict = candidate(
        'a',
        alcoholPreference: AlcoholCompanionPreference.lightOkay,
        drinkingLevel: DrinkingLevel.none,
      );
      final heavy = candidate(
        'b',
        alcoholPreference: AlcoholCompanionPreference.noPreference,
        drinkingLevel: DrinkingLevel.often,
      );
      expect(alcoholCompatibility(strict, heavy), 0.20);
    });
  });

  group('흡연 호환', () {
    test('비흡연자만 원하면 흡연자와 0.0', () {
      final strict = candidate(
        'a',
        smokingPreference: SmokingCompanionPreference.nonSmokersOnly,
      );
      final smoker = candidate('b', smokingStatus: SmokingStatus.smoker);
      expect(smokingCompatibility(strict, smoker), 0.0);
    });

    test('금연 중은 흡연자로 보지 않는다', () {
      final strict = candidate(
        'a',
        smokingPreference: SmokingCompanionPreference.nonSmokersOnly,
      );
      final quitting = candidate('b', smokingStatus: SmokingStatus.quitting);
      expect(smokingCompatibility(strict, quitting), 1.0);
    });

    test('실내 흡연만 아니면 괜찮은 경우는 부분 점수', () {
      final tolerant = candidate(
        'a',
        smokingPreference: SmokingCompanionPreference.noIndoorSmoking,
      );
      final smoker = candidate('b', smokingStatus: SmokingStatus.smoker);
      expect(smokingCompatibility(tolerant, smoker), 0.70);
    });
  });

  group('MBTI 호환', () {
    test('값이 없으면 중립 0.5', () {
      expect(mbtiCompatibility(null, 'ENFP'), 0.5);
      expect(mbtiCompatibility('XXXX', 'ENFP'), 0.5);
    });

    test('유효한 값이면 0.5보다 크다', () {
      expect(mbtiCompatibility('ENFP', 'INFJ'), greaterThan(0.5));
    });
  });

  group('먼저 말하는 성향 균형', () {
    test('주도/상황/경청 1명씩이 최고 점수', () {
      final balanced = initiativeBalanceScore(const [
        ConversationInitiative.initiator,
        ConversationInitiative.adaptive,
        ConversationInitiative.listener,
      ], config: config);
      expect(balanced, closeTo(1.0, 1e-9));
    });

    test('세 명 모두 소극적이면 강하게 감점된다', () {
      final allListeners = initiativeBalanceScore(const [
        ConversationInitiative.listener,
        ConversationInitiative.listener,
        ConversationInitiative.listener,
      ], config: config);
      final allInitiators = initiativeBalanceScore(const [
        ConversationInitiative.initiator,
        ConversationInitiative.initiator,
        ConversationInitiative.initiator,
      ], config: config);

      expect(allListeners, lessThan(allInitiators));
      expect(allListeners, lessThan(0.3));
    });

    test('세 명 모두 주도는 약하게 감점된다', () {
      final allInitiators = initiativeBalanceScore(const [
        ConversationInitiative.initiator,
        ConversationInitiative.initiator,
        ConversationInitiative.initiator,
      ], config: config);
      expect(allInitiators, greaterThan(0.28));
      expect(allInitiators, lessThan(0.5));
    });
  });

  group('우리 팀 구성 품질', () {
    test('균형 잡힌 팀이 전원 경청 팀보다 높다', () {
      final balanced = internalTeamScore(
        balancedTeam('a'),
        config: config,
        alcoholFree: false,
      );
      final passive = internalTeamScore(
        [
          candidate('p1', initiative: ConversationInitiative.listener),
          candidate('p2', initiative: ConversationInitiative.listener),
          candidate('p3', initiative: ConversationInitiative.listener),
        ],
        config: config,
        alcoholFree: false,
      );

      expect(balanced.total, greaterThan(passive.total));
    });

    test('미팅 목적이 직접 충돌하면 목적 일관성이 0', () {
      final conflicting = internalTeamScore(
        [
          candidate('c1', purpose: MeetingPurpose.romance),
          candidate('c2', purpose: MeetingPurpose.friendship),
          candidate('c3', purpose: MeetingPurpose.both),
        ],
        config: config,
        alcoholFree: false,
      );
      expect(conflicting.purposeConsistency, 0.0);
    });

    test('모든 세부 점수가 [0,1] 범위', () {
      final score = internalTeamScore(
        balancedTeam('a'),
        config: config,
        alcoholFree: false,
      );
      for (final value in score.toMap().values) {
        expect(value as double, inInclusiveRange(0.0, 1.0));
      }
    });
  });

  group('6인 구성 점수', () {
    test('참가자 6명 모두의 상대 팀 평균 점수를 계산한다', () {
      final score = groupScore(
        teamA: balancedTeam('a'),
        teamB: balancedTeam('b'),
        config: config,
        alcoholFree: false,
      );
      expect(score.participantOpponentScores.length, 6);
      expect(score.finalGroupScore, inInclusiveRange(0.0, 1.0));
    });

    test('crossTeamScore = 평균×0.70 + 최저×0.30', () {
      final score = groupScore(
        teamA: balancedTeam('a'),
        teamB: balancedTeam('b'),
        config: config,
        alcoholFree: false,
      );
      final values = score.participantOpponentScores.values.toList();
      final mean = values.reduce((a, b) => a + b) / values.length;
      final min = values.reduce((a, b) => a < b ? a : b);
      expect(score.crossTeamScore, closeTo(mean * 0.70 + min * 0.30, 1e-9));
      expect(score.minimumParticipantScore, closeTo(min, 1e-9));
    });

    test('finalGroupScore = 내부 평균×0.40 + crossTeam×0.60', () {
      final score = groupScore(
        teamA: balancedTeam('a'),
        teamB: balancedTeam('b'),
        config: config,
        alcoholFree: false,
      );
      final internalMean = (score.teamAInternal + score.teamBInternal) / 2;
      expect(
        score.finalGroupScore,
        closeTo(internalMean * 0.40 + score.crossTeamScore * 0.60, 1e-9),
      );
    });

    test('한 명만 심하게 안 맞으면 최저 참가자 점수가 떨어진다', () {
      final teamB = [
        candidate(
          'b1',
          initiative: ConversationInitiative.initiator,
          atmosphere: ConversationAtmosphere.lively,
          purpose: MeetingPurpose.friendship,
          interests: const {'헤비메탈'},
          mbti: 'ISTJ',
        ),
        candidate('b2', initiative: ConversationInitiative.adaptive),
        candidate('b3', initiative: ConversationInitiative.listener),
      ];
      final teamA = [
        candidate(
          'a1',
          purpose: MeetingPurpose.romance,
          initiative: ConversationInitiative.initiator,
        ),
        candidate('a2', initiative: ConversationInitiative.adaptive),
        candidate('a3', initiative: ConversationInitiative.listener),
      ];
      final mixed = groupScore(
        teamA: teamA,
        teamB: teamB,
        config: config,
        alcoholFree: false,
      );
      final uniform = groupScore(
        teamA: balancedTeam('a'),
        teamB: balancedTeam('b'),
        config: config,
        alcoholFree: false,
      );
      expect(
        mixed.minimumParticipantScore,
        lessThan(uniform.minimumParticipantScore),
      );
    });

    test('최저 참가자 보호: 최저값이 낮으면 crossTeamScore가 평균보다 작다', () {
      final score = groupScore(
        teamA: [
          candidate('a1', purpose: MeetingPurpose.romance),
          candidate('a2'),
          candidate('a3'),
        ],
        teamB: [
          candidate(
            'b1',
            purpose: MeetingPurpose.friendship,
            interests: {'축구'},
          ),
          candidate('b2'),
          candidate('b3'),
        ],
        config: config,
        alcoholFree: false,
      );
      final values = score.participantOpponentScores.values.toList();
      final mean = values.reduce((a, b) => a + b) / values.length;
      expect(score.crossTeamScore, lessThanOrEqualTo(mean));
    });
  });

  group('대기 시간 보정', () {
    test('대기 시간이 0이면 보정 없음', () {
      expect(waitingTimeBonus(balancedTeam('a'), config: config), 0.0);
    });

    test('보정치는 설정된 최대값을 넘지 않는다', () {
      final longWaiting = [
        candidate('w1', waitedMinutes: 100000),
        candidate('w2', waitedMinutes: 100000),
      ];
      expect(
        waitingTimeBonus(longWaiting, config: config),
        closeTo(config.maxWaitingBonus, 1e-9),
      );
    });
  });
}
