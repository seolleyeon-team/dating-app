import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_candidate.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_hard_constraints.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_matcher.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_scoring.dart';

import 'blind_meeting_test_fixtures.dart';

void main() {
  const matcher = BlindMeetingMatcher();

  List<BlindMeetingCandidate> pool({int size = 6, String prefix = 'u'}) {
    const roles = [
      ConversationInitiative.initiator,
      ConversationInitiative.adaptive,
      ConversationInitiative.listener,
    ];
    return List.generate(
      size,
      (i) => candidate('$prefix$i', initiative: roles[i % 3]),
    );
  }

  group('hard constraint', () {
    test('학교 인증이 없으면 후보에서 제외된다', () {
      final violations = BlindMeetingHardConstraints.checkCandidate(
        candidate('a', schoolVerified: false),
        slotId: kSlot,
        alcoholFreeGroup: false,
      );
      expect(
        violations,
        contains(BlindMeetingConstraintViolation.notSchoolVerified),
      );
    });

    test('제재 상태면 후보에서 제외된다', () {
      final violations = BlindMeetingHardConstraints.checkCandidate(
        candidate('a', eligible: false),
        slotId: kSlot,
        alcoholFreeGroup: false,
      );
      expect(violations, contains(BlindMeetingConstraintViolation.notEligible));
    });

    test('같은 시간에 참여 불가하면 제외된다', () {
      final violations = BlindMeetingHardConstraints.checkCandidate(
        candidate('a', slots: {'2026-09-09#lunch'}),
        slotId: kSlot,
        alcoholFreeGroup: false,
      );
      expect(
        violations,
        contains(BlindMeetingConstraintViolation.slotUnavailable),
      );
    });

    test('차단 관계는 같은 미팅에 들어갈 수 없다', () {
      final a = candidate('a', blocked: {'b'});
      final b = candidate('b');
      expect(
        BlindMeetingHardConstraints.checkPair(a, b),
        contains(BlindMeetingConstraintViolation.blockedContact),
      );
    });

    test('최근에 만난 사용자는 제외된다', () {
      final a = candidate('a', recentlyMet: {'b'});
      expect(
        BlindMeetingHardConstraints.checkPair(a, candidate('b')),
        contains(BlindMeetingConstraintViolation.recentlyMet),
      );
    });

    test('비흡연자 전용 조건은 hard constraint', () {
      final strict = candidate(
        'a',
        smokingPreference: SmokingCompanionPreference.nonSmokersOnly,
      );
      final smoker = candidate('b', smokingStatus: SmokingStatus.smoker);
      expect(
        BlindMeetingHardConstraints.checkPair(strict, smoker),
        contains(BlindMeetingConstraintViolation.smokingRejected),
      );
    });

    test('연애만 × 친구만 은 hard constraint로 분리된다', () {
      expect(
        BlindMeetingHardConstraints.checkPair(
          candidate('a', purpose: MeetingPurpose.romance),
          candidate('b', purpose: MeetingPurpose.friendship),
        ),
        contains(BlindMeetingConstraintViolation.purposeConflict),
      );
    });

    test('동일 사용자 중복 참가를 막는다', () {
      final duplicated = [candidate('a'), candidate('a'), candidate('b')];
      expect(
        BlindMeetingHardConstraints.checkGroup(
          duplicated,
          slotId: kSlot,
          alcoholFreeGroup: false,
          expectedSize: 3,
        ),
        contains(BlindMeetingConstraintViolation.duplicateParticipant),
      );
    });
  });

  group('무알코올 후보군 분리', () {
    test('전원 비음주를 원하는 사용자는 일반 미팅 후보군에서 빠진다', () {
      final soberStrict = candidate(
        'sober',
        alcoholPreference: AlcoholCompanionPreference.allSober,
        drinkingLevel: DrinkingLevel.none,
      );
      final drinker = candidate('drinker');
      final standard = BlindMeetingHardConstraints.standardPool([
        soberStrict,
        drinker,
      ]);
      expect(standard.map((c) => c.userId), ['drinker']);
    });

    test('무알코올 후보군에는 비음주 사용자만 남는다', () {
      final soberStrict = candidate(
        'sober',
        alcoholPreference: AlcoholCompanionPreference.allSober,
        drinkingLevel: DrinkingLevel.none,
      );
      final soberFlexible = candidate(
        'sober2',
        alcoholPreference: AlcoholCompanionPreference.lightOkay,
        drinkingLevel: DrinkingLevel.none,
      );
      final drinker = candidate('drinker', drinkingLevel: DrinkingLevel.often);
      final alcoholFree = BlindMeetingHardConstraints.alcoholFreePool([
        soberStrict,
        soberFlexible,
        drinker,
      ]);
      expect(alcoholFree.map((c) => c.userId).toList(), ['sober', 'sober2']);
    });

    test('후보가 부족해도 음주 사용자로 자동 대체하지 않는다', () {
      final candidates = <BlindMeetingCandidate>[
        for (var i = 0; i < 5; i++)
          candidate(
            'sober$i',
            alcoholPreference: AlcoholCompanionPreference.allSober,
            drinkingLevel: DrinkingLevel.none,
          ),
        for (var i = 0; i < 5; i++)
          candidate('drinker$i', drinkingLevel: DrinkingLevel.often),
      ];
      final group = matcher.bestGroup(
        pool: BlindMeetingHardConstraints.alcoholFreePool(candidates),
        slotId: kSlot,
        alcoholFree: true,
      );
      // 비음주 후보 5명뿐이므로 6인 구성이 만들어지지 않아야 한다.
      expect(group, isNull);
    });

    test('비음주 6명이면 무알코올 미팅이 구성된다', () {
      final candidates = <BlindMeetingCandidate>[
        for (var i = 0; i < 6; i++)
          candidate(
            'sober$i',
            alcoholPreference: AlcoholCompanionPreference.allSober,
            drinkingLevel: DrinkingLevel.none,
            initiative: ConversationInitiative.values[i % 3],
          ),
      ];
      final group = matcher.bestGroup(
        pool: candidates,
        slotId: kSlot,
        alcoholFree: true,
      );
      expect(group, isNotNull);
      expect(group!.participantIds.length, 6);
      expect(group.alcoholFree, isTrue);
    });
  });

  group('팀 구성', () {
    test('6명 pool에서 3:3 구성이 만들어진다', () {
      final group = matcher.bestGroup(
        pool: pool(),
        slotId: kSlot,
        alcoholFree: false,
      );
      expect(group, isNotNull);
      expect(group!.teamAUserIds.length, 3);
      expect(group.teamBUserIds.length, 3);
      expect(group.participantIds.toSet().length, 6);
    });

    test('5명이면 구성되지 않는다', () {
      expect(
        matcher.bestGroup(
          pool: pool(size: 5),
          slotId: kSlot,
          alcoholFree: false,
        ),
        isNull,
      );
    });

    test('algorithmVersion이 결과에 기록된다', () {
      final group = matcher.bestGroup(
        pool: pool(),
        slotId: kSlot,
        alcoholFree: false,
      )!;
      expect(group.algorithmVersion, 'blind_taste_v1');
      expect(group.toMatchingResultMap()['algorithmVersion'], 'blind_taste_v1');
    });

    test('동일 입력은 항상 동일 결과 (deterministic)', () {
      final first = matcher.bestGroup(
        pool: pool(size: 9),
        slotId: kSlot,
        alcoholFree: false,
      )!;
      final second = matcher.bestGroup(
        pool: pool(size: 9).reversed.toList(),
        slotId: kSlot,
        alcoholFree: false,
      )!;
      expect(first.key, second.key);
      expect(
        first.score.finalGroupScore,
        closeTo(second.score.finalGroupScore, 1e-12),
      );
    });

    test('동점일 때 정렬된 참가자 id로 tie-break 한다', () {
      // 완전히 동일한 속성의 후보 6명 → 모든 조합 점수가 같다.
      final identical = List.generate(6, (i) => candidate('u$i'));
      final group = matcher.bestGroup(
        pool: identical,
        slotId: kSlot,
        alcoholFree: false,
      )!;
      expect(group.key, 'u0|u1|u2|u3|u4|u5');
    });

    test('연애만/친구만 사용자는 같은 미팅에 배정되지 않는다', () {
      final candidates = <BlindMeetingCandidate>[
        for (var i = 0; i < 3; i++)
          candidate(
            'r$i',
            purpose: MeetingPurpose.romance,
            initiative: ConversationInitiative.values[i % 3],
          ),
        for (var i = 0; i < 3; i++)
          candidate(
            'f$i',
            purpose: MeetingPurpose.friendship,
            initiative: ConversationInitiative.values[i % 3],
          ),
      ];
      expect(
        matcher.bestGroup(pool: candidates, slotId: kSlot, alcoholFree: false),
        isNull,
      );
    });

    test('큰 pool에서도 겹치지 않는 여러 구성을 만들 수 있다', () {
      final groups = matcher.proposeGroups(
        pool: pool(size: 18),
        slotId: kSlot,
        alcoholFree: false,
        maxGroups: 3,
      );
      expect(groups.length, 3);
      final all = groups.expand((g) => g.participantIds).toList();
      expect(all.toSet().length, all.length);
    });

    test('대기 시간이 긴 후보가 동점 상황에서 우선된다', () {
      final candidates = <BlindMeetingCandidate>[
        for (var i = 0; i < 6; i++) candidate('a$i'),
        candidate('z0', waitedMinutes: 5000),
      ];
      final group = matcher.bestGroup(
        pool: candidates,
        slotId: kSlot,
        alcoholFree: false,
      )!;
      expect(group.participantIds, contains('z0'));
    });
  });

  group('대체 후보 평가', () {
    List<BlindMeetingCandidate> teamA() => balancedTeam('a');
    List<BlindMeetingCandidate> teamB() => balancedTeam('b');

    double baseline() => groupScore(
      teamA: teamA(),
      teamB: teamB(),
      config: matcher.config,
      alcoholFree: false,
    ).finalGroupScore;

    test('전체 6인 구성 점수를 기준으로 판정한다', () {
      final evaluation = matcher.evaluateReplacement(
        teamA: teamA(),
        teamB: teamB(),
        vacantUserId: 'b3',
        candidate: candidate(
          'new',
          initiative: ConversationInitiative.listener,
        ),
        baselineFinalGroupScore: baseline(),
        slotId: kSlot,
        alcoholFree: false,
      );
      expect(evaluation.violations, isEmpty);
      expect(evaluation.scoreAfterReplacement, isNotNull);
      expect(evaluation.qualityRatio, closeTo(1.0, 0.02));
      expect(evaluation.accepted, isTrue);
    });

    test('hard constraint 위반 후보는 긴급 상황에서도 거부된다', () {
      final evaluation = matcher.evaluateReplacement(
        teamA: teamA(),
        teamB: teamB(),
        vacantUserId: 'b3',
        candidate: candidate(
          'smoker',
          smokingStatus: SmokingStatus.smoker,
        ).copyWith(eligible: false),
        baselineFinalGroupScore: baseline(),
        slotId: kSlot,
        alcoholFree: false,
        urgent: true,
      );
      expect(evaluation.accepted, isFalse);
      expect(
        evaluation.violations,
        contains(BlindMeetingConstraintViolation.notEligible),
      );
    });

    test('품질이 크게 떨어지는 후보는 일반 기준에서 거부된다', () {
      final poorCandidate = candidate(
        'poor',
        purpose: MeetingPurpose.friendship,
        atmosphere: ConversationAtmosphere.lively,
        initiative: ConversationInitiative.listener,
        interests: const {'헤비메탈'},
        mbti: 'ISTJ',
        drinkingLevel: DrinkingLevel.often,
      );
      final normal = matcher.evaluateReplacement(
        teamA: teamA(),
        teamB: teamB(),
        vacantUserId: 'b3',
        candidate: poorCandidate,
        baselineFinalGroupScore: baseline(),
        slotId: kSlot,
        alcoholFree: false,
      );
      final urgent = matcher.evaluateReplacement(
        teamA: teamA(),
        teamB: teamB(),
        vacantUserId: 'b3',
        candidate: poorCandidate,
        baselineFinalGroupScore: baseline(),
        slotId: kSlot,
        alcoholFree: false,
        urgent: true,
      );
      expect(normal.qualityRatio, lessThan(1.0));
      // 긴급 기준은 일반 기준보다 관대하다.
      expect(
        matcher.config.replacementUrgentRatio,
        lessThan(matcher.config.replacementNormalRatio),
      );
      expect(urgent.qualityRatio, closeTo(normal.qualityRatio, 1e-12));
    });

    test('기존 참가자는 대체 후보로 순위에 오르지 않는다', () {
      final ranked = matcher.rankReplacements(
        teamA: teamA(),
        teamB: teamB(),
        vacantUserId: 'b3',
        candidates: [
          candidate('a1'),
          candidate('c1', initiative: ConversationInitiative.listener),
        ],
        baselineFinalGroupScore: baseline(),
        slotId: kSlot,
        alcoholFree: false,
      );
      expect(ranked.map((e) => e.candidate.userId), isNot(contains('a1')));
    });

    test('상위 후보를 제한 개수만큼 순위대로 돌려준다', () {
      final ranked = matcher.rankReplacements(
        teamA: teamA(),
        teamB: teamB(),
        vacantUserId: 'b3',
        candidates: List.generate(
          6,
          (i) => candidate(
            'cand$i',
            initiative: ConversationInitiative.listener,
            waitedMinutes: i * 100,
          ),
        ),
        baselineFinalGroupScore: baseline(),
        slotId: kSlot,
        alcoholFree: false,
        limit: 3,
      );
      expect(ranked.length, 3);
      for (var i = 1; i < ranked.length; i++) {
        expect(
          ranked[i - 1].adjustedScore,
          greaterThanOrEqualTo(ranked[i].adjustedScore),
        );
      }
    });
  });
}
