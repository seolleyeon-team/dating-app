// Dart 기준 구현과 TS 서버 구현의 매칭 결과 일치 검증
//
// 골든 벡터: shared/blind_meeting_matching_vectors.json
//   기대값은 tools/generate_matching_vectors.js 가 서버 구현으로 생성한다.
//   같은 파일을 functions/src/blindMeeting/__tests__/matching.test.ts 도 검증한다.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/constants/interest_taxonomy.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_candidate.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_matching_config.dart';
import 'package:seolleyeon/features/blind_meeting/domain/matching/blind_meeting_scoring.dart';

Map<String, dynamic> loadFixture() {
  final file = File('shared/blind_meeting_matching_vectors.json');
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

BlindMeetingCandidate hydrate(Map<String, dynamic> raw, String slotId) {
  return BlindMeetingCandidate(
    userId: raw['userId'] as String,
    atmosphere: enumFromName(
      ConversationAtmosphere.values,
      raw['atmosphere'],
      fallback: ConversationAtmosphere.calm,
    ),
    initiative: enumFromName(
      ConversationInitiative.values,
      raw['initiative'],
      fallback: ConversationInitiative.adaptive,
    ),
    purpose: enumFromName(
      MeetingPurpose.values,
      raw['purpose'],
      fallback: MeetingPurpose.both,
    ),
    alcoholPreference: enumFromName(
      AlcoholCompanionPreference.values,
      raw['alcoholPreference'],
      fallback: AlcoholCompanionPreference.noPreference,
    ),
    smokingPreference: enumFromName(
      SmokingCompanionPreference.values,
      raw['smokingPreference'],
      fallback: SmokingCompanionPreference.noPreference,
    ),
    drinkingLevel: enumFromName(
      DrinkingLevel.values,
      raw['drinkingLevel'],
      fallback: DrinkingLevel.sometimes,
    ),
    smokingStatus: enumFromName(
      SmokingStatus.values,
      raw['smokingStatus'],
      fallback: SmokingStatus.nonSmoker,
    ),
    interestIds: (raw['interestIds'] as List).map((e) => '$e').toSet(),
    mbti: raw['mbti'] as String?,
    availableSlotIds: {slotId},
  );
}

void main() {
  const config = BlindMeetingMatchingConfig.current;

  group('관심사 taxonomy 사본 일치', () {
    test('카테고리와 라벨 개수 fingerprint가 서버 사본과 같다', () {
      // functions/src/blindMeeting/interestTaxonomy.ts 와 동일해야 한다.
      final perCategory = <String, int>{
        for (final category in interestCategories)
          category.id: category.items.length,
      };
      expect(interestCategories.length, 9);
      expect(
        perCategory,
        {
          'indoor': 19,
          'outdoor': 31,
          'food': 21,
          'sports': 29,
          'screen': 13,
          'music': 11,
          'game': 6,
          'creative': 13,
          'social': 7,
        },
      );
      expect(
        perCategory.values.reduce((a, b) => a + b),
        150,
      );
    });

    test('알 수 없는 관심사는 other 카테고리', () {
      expect(interestCategoryIdOf('커피'), 'food');
      expect(interestCategoryIdOf('존재하지-않는-관심사'), 'other');
      expect(interestCategoryIdOf(''), 'other');
    });
  });

  group('매칭 골든 벡터', () {
    final fixture = loadFixture();
    final slotId = fixture['slotId'] as String;
    final cases = (fixture['cases'] as List).cast<Map<String, dynamic>>();
    final expected = fixture['expected'] as Map<String, dynamic>;

    test('algorithmVersion이 일치한다', () {
      expect(fixture['algorithmVersion'], config.algorithmVersion);
    });

    test('골든 벡터가 비어 있지 않다', () {
      expect(cases, isNotEmpty);
      expect(expected.keys.toSet(), cases.map((c) => c['name']).toSet());
    });

    for (final testCase in cases) {
      final name = testCase['name'] as String;
      test('$name 벡터가 서버 구현과 같다', () {
        final alcoholFree = testCase['alcoholFree'] == true;
        final teamA = (testCase['teamA'] as List)
            .cast<Map<String, dynamic>>()
            .map((raw) => hydrate(raw, slotId))
            .toList();
        final teamB = (testCase['teamB'] as List)
            .cast<Map<String, dynamic>>()
            .map((raw) => hydrate(raw, slotId))
            .toList();

        final want = expected[name] as Map<String, dynamic>;
        final internalA = internalTeamScore(
          teamA,
          config: config,
          alcoholFree: alcoholFree,
        );
        final internalB = internalTeamScore(
          teamB,
          config: config,
          alcoholFree: alcoholFree,
        );
        final group = groupScore(
          teamA: teamA,
          teamB: teamB,
          config: config,
          alcoholFree: alcoholFree,
        );

        expect(
          internalA.total,
          closeTo((want['internalTeamA'] as num).toDouble(), 1e-9),
        );
        expect(
          internalB.total,
          closeTo((want['internalTeamB'] as num).toDouble(), 1e-9),
        );
        expect(
          group.crossTeamScore,
          closeTo((want['crossTeamScore'] as num).toDouble(), 1e-9),
        );
        expect(
          group.minimumParticipantScore,
          closeTo((want['minimumParticipantScore'] as num).toDouble(), 1e-9),
        );
        expect(
          group.finalGroupScore,
          closeTo((want['finalGroupScore'] as num).toDouble(), 1e-9),
        );

        final wantScores =
            want['participantOpponentScores'] as Map<String, dynamic>;
        expect(
          group.participantOpponentScores.keys.toSet(),
          wantScores.keys.toSet(),
        );
        for (final entry in wantScores.entries) {
          expect(
            group.participantOpponentScores[entry.key],
            closeTo((entry.value as num).toDouble(), 1e-9),
            reason: '$name/${entry.key}',
          );
        }
      });
    }
  });
}
