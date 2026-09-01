// 3:3 블라인드 취향 미팅 — 성비 불변식 (3남 + 3녀) 회귀 테스트
//
// 최상위 system invariant:
//   participantCount == 6 && male == 3 && female == 3 && unique == 6
//
// 3남 또는 3녀를 확보할 수 없으면 어떤 구성도 만들지 않는다.
// 서버 구현(functions/src/blindMeeting/__tests__/genderBalance.test.ts)과
// 같은 케이스를 검증한다.

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_candidate.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_hard_constraints.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_matcher.dart';

import 'blind_meeting_test_fixtures.dart';

void main() {
  const matcher = BlindMeetingMatcher();

  /// 역할이 균형 잡힌 동성 N명.
  List<BlindMeetingCandidate> pool(
    String prefix,
    BlindMeetingGender gender,
    int count,
  ) {
    const roles = [
      ConversationInitiative.initiator,
      ConversationInitiative.adaptive,
      ConversationInitiative.listener,
    ];
    return List.generate(
      count,
      (i) => candidate(
        '$prefix${i + 1}',
        gender: gender,
        initiative: roles[i % 3],
      ),
    );
  }

  /// 어떤 성공 결과든 항상 만족해야 하는 불변식.
  void expectCanonicalGroup(BlindMeetingGroupProposal? group) {
    expect(group, isNotNull, reason: '그룹이 생성되어야 한다');
    final members = [...group!.teamA.members, ...group.teamB.members];
    expect(members.length, 6, reason: '참가자는 정확히 6명');
    expect(members.map((m) => m.userId).toSet().length, 6, reason: 'UID 6개 유일');
    final counts = BlindMeetingHardConstraints.genderCounts(members);
    expect(counts.male, 3, reason: '남성 3명');
    expect(counts.female, 3, reason: '여성 3명');
  }

  BlindMeetingGroupProposal? best(List<BlindMeetingCandidate> candidates) {
    return matcher.bestGroup(
      pool: candidates,
      dateKey: kDateKey,
      alcoholFree: false,
    );
  }

  group('그룹 제약: 성비', () {
    test('6인 구성이 3남 3녀가 아니면 거부한다', () {
      final members = [
        ...pool('M', BlindMeetingGender.male, 4),
        ...pool('F', BlindMeetingGender.female, 2),
      ];
      expect(
        BlindMeetingHardConstraints.checkGroup(
          members,
          dateKey: kDateKey,
          alcoholFreeGroup: false,
          expectedSize: 6,
        ),
        contains(BlindMeetingConstraintViolation.genderImbalance),
      );
    });

    test('한 팀 안에 성별이 섞이면 거부한다', () {
      final trio = [
        candidate('M1', gender: BlindMeetingGender.male),
        candidate('M2', gender: BlindMeetingGender.male),
        candidate('F1', gender: BlindMeetingGender.female),
      ];
      expect(
        BlindMeetingHardConstraints.checkGroup(
          trio,
          dateKey: kDateKey,
          alcoholFreeGroup: false,
          expectedSize: 3,
        ),
        contains(BlindMeetingConstraintViolation.mixedGenderTeam),
      );
    });

    test('정상 3남 3녀는 성비 위반이 없다', () {
      final members = [
        ...pool('M', BlindMeetingGender.male, 3),
        ...pool('F', BlindMeetingGender.female, 3),
      ];
      final violations = BlindMeetingHardConstraints.checkGroup(
        members,
        dateKey: kDateKey,
        alcoholFreeGroup: false,
        expectedSize: 6,
      );
      expect(
        violations,
        isNot(contains(BlindMeetingConstraintViolation.genderImbalance)),
      );
      expect(
        violations,
        isNot(contains(BlindMeetingConstraintViolation.mixedGenderTeam)),
      );
    });
  });

  group('3남 + 3녀 선택 불변식', () {
    test('Case 1: 남3 여3 → 3남 3녀', () {
      expectCanonicalGroup(
        best([
          ...pool('M', BlindMeetingGender.male, 3),
          ...pool('F', BlindMeetingGender.female, 3),
        ]),
      );
    });

    test('Case 2: 남5 여5 → 3남 3녀', () {
      expectCanonicalGroup(
        best([
          ...pool('M', BlindMeetingGender.male, 5),
          ...pool('F', BlindMeetingGender.female, 5),
        ]),
      );
    });

    test('Case 3: 남5 여1 → 그룹 없음', () {
      expect(
        best([
          ...pool('M', BlindMeetingGender.male, 5),
          ...pool('F', BlindMeetingGender.female, 1),
        ]),
        isNull,
      );
    });

    test('Case 4: 남1 여5 → 그룹 없음', () {
      expect(
        best([
          ...pool('M', BlindMeetingGender.male, 1),
          ...pool('F', BlindMeetingGender.female, 5),
        ]),
        isNull,
      );
    });

    test('남6 여0 → 그룹 없음 (점수가 높아도 6남 팀을 만들지 않는다)', () {
      expect(best(pool('M', BlindMeetingGender.male, 6)), isNull);
    });

    test('남0 여6 → 그룹 없음', () {
      expect(best(pool('F', BlindMeetingGender.female, 6)), isNull);
    });

    test('남2 여4 → 그룹 없음', () {
      expect(
        best([
          ...pool('M', BlindMeetingGender.male, 2),
          ...pool('F', BlindMeetingGender.female, 4),
        ]),
        isNull,
      );
    });

    test('성별 편중이 심해도(남10 여3) 정확히 3남 3녀', () {
      expectCanonicalGroup(
        best([
          ...pool('M', BlindMeetingGender.male, 10),
          ...pool('F', BlindMeetingGender.female, 3),
        ]),
      );
    });

    test('Case 5: 차단된 후보는 빠지고 대체 후보로 3남 3녀를 채운다', () {
      final males = pool('M', BlindMeetingGender.male, 3);
      final females = pool('F', BlindMeetingGender.female, 4);
      females[0] = candidate(
        'F1',
        gender: BlindMeetingGender.female,
        initiative: ConversationInitiative.initiator,
        blocked: males.map((m) => m.userId).toSet(),
      );
      final group = best([...males, ...females]);
      expectCanonicalGroup(group);
      final ids = [
        ...group!.teamA.members,
        ...group.teamB.members,
      ].map((m) => m.userId);
      expect(ids, isNot(contains('F1')));
    });

    test('차단 때문에 3녀를 못 채우면 5인 그룹을 만들지 않는다', () {
      final males = pool('M', BlindMeetingGender.male, 3);
      final females = pool('F', BlindMeetingGender.female, 3);
      females[0] = candidate(
        'F1',
        gender: BlindMeetingGender.female,
        initiative: ConversationInitiative.initiator,
        blocked: {males[0].userId},
      );
      expect(best([...males, ...females]), isNull);
    });

    test('Case 6: 같은 uid 가 남/여 양쪽에 있어도 6인으로 계산하지 않는다', () {
      final males = pool('M', BlindMeetingGender.male, 3);
      final females = [
        candidate(
          'M1',
          gender: BlindMeetingGender.female,
          initiative: ConversationInitiative.initiator,
        ),
        candidate(
          'F2',
          gender: BlindMeetingGender.female,
          initiative: ConversationInitiative.adaptive,
        ),
        candidate(
          'F3',
          gender: BlindMeetingGender.female,
          initiative: ConversationInitiative.listener,
        ),
      ];
      expect(best([...males, ...females]), isNull);
    });

    test('여러 구성을 만들어도 각 그룹이 3남 3녀이고 겹치지 않는다', () {
      final groups = matcher.proposeGroups(
        pool: [
          ...pool('M', BlindMeetingGender.male, 6),
          ...pool('F', BlindMeetingGender.female, 6),
        ],
        dateKey: kDateKey,
        alcoholFree: false,
        maxGroups: 2,
      );
      expect(groups, isNotEmpty);
      for (final group in groups) {
        expectCanonicalGroup(group);
      }
      final all = groups.expand((g) => g.participantIds).toList();
      expect(all.toSet().length, all.length);
    });

    test('teamA 와 teamB 는 각각 단일 성별이고 서로 다르다', () {
      final group = best([
        ...pool('M', BlindMeetingGender.male, 4),
        ...pool('F', BlindMeetingGender.female, 4),
      ]);
      expect(group, isNotNull);
      final teamAGenders = group!.teamA.members.map((m) => m.gender).toSet();
      final teamBGenders = group.teamB.members.map((m) => m.gender).toSet();
      expect(teamAGenders.length, 1);
      expect(teamBGenders.length, 1);
      expect(teamAGenders.single, isNot(teamBGenders.single));
    });

    test('결과는 deterministic 하다', () {
      final input = [
        ...pool('M', BlindMeetingGender.male, 5),
        ...pool('F', BlindMeetingGender.female, 5),
      ];
      final first = best(input);
      final second = best(input.reversed.toList());
      expect(first, isNotNull);
      expect(second, isNotNull);
      expect(first!.key, second!.key);
    });

    test('성비를 맞추느라 점수가 낮은 후보를 넣지 않는다', () {
      // M4 / F4 는 분위기·관심사가 어긋나 점수가 낮다.
      final males = [
        ...pool('M', BlindMeetingGender.male, 3),
        candidate(
          'M4',
          gender: BlindMeetingGender.male,
          atmosphere: ConversationAtmosphere.lively,
          interests: const {'볼링'},
        ),
      ];
      final females = [
        ...pool('F', BlindMeetingGender.female, 3),
        candidate(
          'F4',
          gender: BlindMeetingGender.female,
          atmosphere: ConversationAtmosphere.lively,
          interests: const {'볼링'},
        ),
      ];
      final group = best([...males, ...females]);
      expectCanonicalGroup(group);
      expect(group!.participantIds.toSet(), {
        'M1',
        'M2',
        'M3',
        'F1',
        'F2',
        'F3',
      });
    });
  });

  group('대체 후보와 성비', () {
    test('빈자리와 다른 성별 후보는 성비를 깨므로 거부된다', () {
      final teamA = pool('M', BlindMeetingGender.male, 3);
      final teamB = pool('F', BlindMeetingGender.female, 3);
      final baseline = matcher
          .evaluateReplacement(
            teamA: teamA,
            teamB: teamB,
            vacantUserId: 'F3',
            candidate: candidate(
              'X',
              gender: BlindMeetingGender.female,
              initiative: ConversationInitiative.listener,
            ),
            baselineFinalGroupScore: 0.5,
            dateKey: kDateKey,
            alcoholFree: false,
          )
          .violations;
      expect(baseline, isEmpty, reason: '같은 성별 대체는 허용된다');

      final crossGender = matcher.evaluateReplacement(
        teamA: teamA,
        teamB: teamB,
        vacantUserId: 'F3',
        candidate: candidate(
          'Y',
          gender: BlindMeetingGender.male,
          initiative: ConversationInitiative.listener,
        ),
        baselineFinalGroupScore: 0.5,
        dateKey: kDateKey,
        alcoholFree: false,
      );
      expect(crossGender.accepted, isFalse);
      expect(
        crossGender.violations,
        contains(BlindMeetingConstraintViolation.genderImbalance),
      );
    });
  });
}
