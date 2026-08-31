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
    // 남/여를 번갈아 채운다. 3:3 은 3남 + 3녀가 성립해야 구성된다.
    return List.generate(
      size,
      (i) => candidate(
        '$prefix$i',
        gender: i.isEven ? BlindMeetingGender.male : BlindMeetingGender.female,
        initiative: roles[i % 3],
      ),
    );
  }

  group('hard constraint', () {
    test('학교 인증이 없으면 후보에서 제외된다', () {
      final violations = BlindMeetingHardConstraints.checkCandidate(
        candidate('a', schoolVerified: false),
        dateKey: kDateKey,
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
        dateKey: kDateKey,
        alcoholFreeGroup: false,
      );
      expect(violations, contains(BlindMeetingConstraintViolation.notEligible));
    });

    test('같은 날짜에 참여 불가하면 제외된다', () {
      final violations = BlindMeetingHardConstraints.checkCandidate(
        candidate('a', dateKeys: {'2026-09-09'}),
        dateKey: kDateKey,
        alcoholFreeGroup: false,
      );
      expect(
        violations,
        contains(BlindMeetingConstraintViolation.dateUnavailable),
      );
    });

    test('세부 시간은 매칭 조건이 아니다 (같은 날짜면 통과)', () {
      final violations = BlindMeetingHardConstraints.checkCandidate(
        candidate('a', dateKeys: {kDateKey}),
        dateKey: kDateKey,
        alcoholFreeGroup: false,
      );
      expect(violations, isEmpty);
    });

    test('기준 날짜를 못 쓰는 참가자가 있으면 dateUnavailable로 걸러진다', () {
      final members = [
        ...balancedTeam('a'),
        ...balancedTeam('b', gender: BlindMeetingGender.female),
      ].map((c) => c.copyWith(availableDateKeys: {kDateKey})).toList();
      // 한 명만 다른 날짜만 가능하게 바꾼다.
      members[5] = members[5].copyWith(availableDateKeys: {'2026-08-09'});

      final violations = BlindMeetingHardConstraints.checkGroup(
        members,
        dateKey: kDateKey,
        alcoholFreeGroup: false,
        expectedSize: 6,
      );
      expect(
        violations,
        contains(BlindMeetingConstraintViolation.dateUnavailable),
      );
    });

    test('전원이 기준 날짜를 쓸 수 있으면 공통 날짜가 항상 존재한다', () {
      // hot path에서 교집합을 다시 계산하지 않아도 되는 근거.
      final members =
          [
                ...balancedTeam('a'),
                ...balancedTeam('b', gender: BlindMeetingGender.female),
              ]
              .map(
                (c) => c.copyWith(availableDateKeys: {kDateKey, '2026-08-09'}),
              )
              .toList();
      expect(
        BlindMeetingHardConstraints.checkGroup(
          members,
          dateKey: kDateKey,
          alcoholFreeGroup: false,
          expectedSize: 6,
        ),
        isEmpty,
      );
      expect(BlindMeetingHardConstraints.commonDateKeys(members), [
        kDateKey,
        '2026-08-09',
      ]);
    });

    test('공통 가능 날짜를 오름차순으로 계산한다', () {
      final members = [
        candidate('a', dateKeys: {'2026-08-03', '2026-08-01', '2026-08-02'}),
        candidate('b', dateKeys: {'2026-08-02', '2026-08-03'}),
        candidate('c', dateKeys: {'2026-08-02', '2026-08-03', '2026-08-09'}),
      ];
      expect(BlindMeetingHardConstraints.commonDateKeys(members), [
        '2026-08-02',
        '2026-08-03',
      ]);
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
          dateKey: kDateKey,
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
        dateKey: kDateKey,
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
            gender: i.isEven
                ? BlindMeetingGender.male
                : BlindMeetingGender.female,
            alcoholPreference: AlcoholCompanionPreference.allSober,
            drinkingLevel: DrinkingLevel.none,
            initiative: ConversationInitiative.values[i % 3],
          ),
      ];
      final group = matcher.bestGroup(
        pool: candidates,
        dateKey: kDateKey,
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
        dateKey: kDateKey,
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
          dateKey: kDateKey,
          alcoholFree: false,
        ),
        isNull,
      );
    });

    test('algorithmVersion이 결과에 기록된다', () {
      final group = matcher.bestGroup(
        pool: pool(),
        dateKey: kDateKey,
        alcoholFree: false,
      )!;
      expect(group.algorithmVersion, 'blind_taste_v1');
      expect(group.toMatchingResultMap()['algorithmVersion'], 'blind_taste_v1');
    });

    test('동일 입력은 항상 동일 결과 (deterministic)', () {
      final first = matcher.bestGroup(
        pool: pool(size: 9),
        dateKey: kDateKey,
        alcoholFree: false,
      )!;
      final second = matcher.bestGroup(
        pool: pool(size: 9).reversed.toList(),
        dateKey: kDateKey,
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
      final identical = List.generate(
        6,
        (i) => candidate(
          'u$i',
          gender: i.isEven
              ? BlindMeetingGender.male
              : BlindMeetingGender.female,
        ),
      );
      final group = matcher.bestGroup(
        pool: identical,
        dateKey: kDateKey,
        alcoholFree: false,
      )!;
      expect(group.key, 'u0|u1|u2|u3|u4|u5');
    });

    test('연애만/친구만 사용자는 같은 미팅에 배정되지 않는다', () {
      final candidates = <BlindMeetingCandidate>[
        for (var i = 0; i < 3; i++)
          candidate(
            'r$i',
            gender: BlindMeetingGender.male,
            purpose: MeetingPurpose.romance,
            initiative: ConversationInitiative.values[i % 3],
          ),
        for (var i = 0; i < 3; i++)
          candidate(
            'f$i',
            gender: BlindMeetingGender.female,
            purpose: MeetingPurpose.friendship,
            initiative: ConversationInitiative.values[i % 3],
          ),
      ];
      expect(
        matcher.bestGroup(
          pool: candidates,
          dateKey: kDateKey,
          alcoholFree: false,
        ),
        isNull,
      );
    });

    test('큰 pool에서도 겹치지 않는 여러 구성을 만들 수 있다', () {
      final groups = matcher.proposeGroups(
        pool: pool(size: 18),
        dateKey: kDateKey,
        alcoholFree: false,
        maxGroups: 3,
      );
      expect(groups.length, 3);
      final all = groups.expand((g) => g.participantIds).toList();
      expect(all.toSet().length, all.length);
    });

    test('대기 시간이 긴 후보가 동점 상황에서 우선된다', () {
      final candidates = <BlindMeetingCandidate>[
        for (var i = 0; i < 6; i++)
          candidate(
            'a$i',
            gender: i.isEven
                ? BlindMeetingGender.male
                : BlindMeetingGender.female,
          ),
        candidate('z0', gender: BlindMeetingGender.female, waitedMinutes: 5000),
      ];
      final group = matcher.bestGroup(
        pool: candidates,
        dateKey: kDateKey,
        alcoholFree: false,
      )!;
      expect(group.participantIds, contains('z0'));
    });
  });

  group('대체 후보 평가', () {
    List<BlindMeetingCandidate> teamA() => balancedTeam('a');
    List<BlindMeetingCandidate> teamB() =>
        balancedTeam('b', gender: BlindMeetingGender.female);

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
          gender: BlindMeetingGender.female,
          initiative: ConversationInitiative.listener,
        ),
        baselineFinalGroupScore: baseline(),
        dateKey: kDateKey,
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
          gender: BlindMeetingGender.female,
          smokingStatus: SmokingStatus.smoker,
        ).copyWith(eligible: false),
        baselineFinalGroupScore: baseline(),
        dateKey: kDateKey,
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
        gender: BlindMeetingGender.female,
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
        dateKey: kDateKey,
        alcoholFree: false,
      );
      final urgent = matcher.evaluateReplacement(
        teamA: teamA(),
        teamB: teamB(),
        vacantUserId: 'b3',
        candidate: poorCandidate,
        baselineFinalGroupScore: baseline(),
        dateKey: kDateKey,
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
          candidate(
            'c1',
            gender: BlindMeetingGender.female,
            initiative: ConversationInitiative.listener,
          ),
        ],
        baselineFinalGroupScore: baseline(),
        dateKey: kDateKey,
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
            gender: BlindMeetingGender.female,
            initiative: ConversationInitiative.listener,
            waitedMinutes: i * 100,
          ),
        ),
        baselineFinalGroupScore: baseline(),
        dateKey: kDateKey,
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

  group('생활권 hard constraint', () {
    List<BlindMeetingCandidate> zonedTeam(
      String prefix,
      Set<String> zones, {
      BlindMeetingGender gender = BlindMeetingGender.male,
    }) => balancedTeam(
      prefix,
      gender: gender,
    ).map((member) => member.copyWith(campusLifeZones: zones)).toList();

    test('그룹 공통 생활권은 교집합이며 다수결이 아니다', () {
      expect(
        BlindMeetingHardConstraints.sharedCampusLifeZones([
          candidate('a', campusLifeZones: const {'sinchon'}),
          candidate('b', campusLifeZones: const {'sinchon'}),
          candidate('c', campusLifeZones: const {'sinchon'}),
        ]),
        {'sinchon'},
      );
      expect(
        BlindMeetingHardConstraints.sharedCampusLifeZones([
          candidate('a', campusLifeZones: const {'songdo'}),
          candidate('b', campusLifeZones: const {'songdo'}),
          candidate('c', campusLifeZones: const {'sinchon', 'songdo'}),
        ]),
        {'songdo'},
      );
      // 2명이 신촌이어도 신촌 그룹이 되지 않는다
      expect(
        BlindMeetingHardConstraints.sharedCampusLifeZones([
          candidate('a', campusLifeZones: const {'sinchon'}),
          candidate('b', campusLifeZones: const {'sinchon'}),
          candidate('c', campusLifeZones: const {'songdo'}),
        ]),
        isEmpty,
      );
      // dual-zone 이 bridge 역할을 해도 전체 공통이 없으면 실패
      expect(
        BlindMeetingHardConstraints.sharedCampusLifeZones([
          candidate('a', campusLifeZones: const {'sinchon'}),
          candidate('b', campusLifeZones: const {'songdo'}),
          candidate('c', campusLifeZones: const {'sinchon', 'songdo'}),
        ]),
        isEmpty,
      );
    });

    test('생활권이 비면 fail-closed 로 판정한다', () {
      final violations = BlindMeetingHardConstraints.checkGroup(
        [
          candidate('a', campusLifeZones: const {'sinchon'}),
          candidate('b', campusLifeZones: const <String>{}),
        ],
        dateKey: kDateKey,
        alcoholFreeGroup: false,
      );
      expect(
        violations,
        contains(BlindMeetingConstraintViolation.campusLifeZoneMissing),
      );
    });

    test('공통 생활권이 없는 6인은 hard constraint 위반이다', () {
      final members = [
        ...zonedTeam('a', const {'sinchon'}),
        ...zonedTeam('b', const {'songdo'}, gender: BlindMeetingGender.female),
      ];
      expect(
        BlindMeetingHardConstraints.checkGroup(
          members,
          dateKey: kDateKey,
          alcoholFreeGroup: false,
          expectedSize: 6,
        ),
        contains(BlindMeetingConstraintViolation.campusLifeZoneMismatch),
      );
    });

    test('신촌 3명 + 송도 3명은 점수와 무관하게 매칭되지 않는다', () {
      final zonedPool = [
        ...zonedTeam('sin', const {'sinchon'}),
        ...zonedTeam('song', const {
          'songdo',
        }, gender: BlindMeetingGender.female),
      ];
      expect(
        matcher.bestGroup(
          pool: zonedPool,
          dateKey: kDateKey,
          alcoholFree: false,
        ),
        isNull,
      );
    });

    test('같은 생활권 6명은 정상 매칭된다', () {
      final zonedPool = [
        ...zonedTeam('a', const {'sinchon'}),
        ...zonedTeam('b', const {'sinchon'}, gender: BlindMeetingGender.female),
      ];
      final group = matcher.bestGroup(
        pool: zonedPool,
        dateKey: kDateKey,
        alcoholFree: false,
      );
      expect(group, isNotNull);
      final resolved = group!;
      expect(
        BlindMeetingHardConstraints.sharedCampusLifeZones([
          ...resolved.teamA.members,
          ...resolved.teamB.members,
        ]),
        {'sinchon'},
      );
    });

    test('dual-zone 사용자는 양쪽 생활권 그룹에 참여할 수 있다', () {
      for (final zone in ['sinchon', 'songdo']) {
        final zonedPool = [
          ...zonedTeam('a', {zone}),
          ...zonedTeam('b', const {
            'sinchon',
            'songdo',
          }, gender: BlindMeetingGender.female),
        ];
        final group = matcher.bestGroup(
          pool: zonedPool,
          dateKey: kDateKey,
          alcoholFree: false,
        );
        expect(group, isNotNull, reason: '$zone 그룹이 구성되어야 한다');
        final resolved = group!;
        expect(
          BlindMeetingHardConstraints.sharedCampusLifeZones([
            ...resolved.teamA.members,
            ...resolved.teamB.members,
          ]),
          {zone},
        );
      }
    });

    test('생활권은 기존 hard constraint 를 대체하지 않는다', () {
      final violations = BlindMeetingHardConstraints.checkGroup(
        [
          candidate(
            'a',
            campusLifeZones: const {'sinchon'},
            blocked: const {'b'},
          ),
          candidate('b', campusLifeZones: const {'sinchon'}),
        ],
        dateKey: kDateKey,
        alcoholFreeGroup: false,
      );
      expect(
        violations,
        contains(BlindMeetingConstraintViolation.blockedContact),
      );
      expect(
        violations,
        isNot(contains(BlindMeetingConstraintViolation.campusLifeZoneMismatch)),
      );
    });
  });
}
