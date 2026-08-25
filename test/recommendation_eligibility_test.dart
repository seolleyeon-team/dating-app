import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/utils/recommendation_eligibility.dart';

Map<String, dynamic> candidate({
  String gender = 'female',
  Map<String, dynamic> overrides = const {},
}) {
  return {
    'isStudentVerified': true,
    'initialSetupComplete': true,
    'avatar': {
      'status': 'approved',
      'approvedAvatarUrl': 'https://cdn.example.com/avatars/ok.png',
    },
    'onboarding': {'gender': gender, 'nickname': '테스터'},
    ...overrides,
  };
}

bool recommendable(Map<String, dynamic>? cand, {Map<String, dynamic>? viewer}) {
  return RecommendationEligibility.isRecommendableTo(
    viewerUid: 'viewer',
    viewer: viewer ?? candidate(gender: 'male'),
    candidateUid: 'cand',
    candidate: cand,
  );
}

void main() {
  group('후보 노출 가능 여부', () {
    test('인증·완성·승인 아바타를 갖춘 이성 후보는 노출된다', () {
      expect(recommendable(candidate()), isTrue);
    });

    test('학생 인증이 없으면 제외된다', () {
      expect(
        recommendable(candidate(overrides: {'isStudentVerified': false})),
        isFalse,
      );
    });

    test('정지·삭제된 계정은 제외된다', () {
      expect(
        recommendable(candidate(overrides: {'isSuspended': true})),
        isFalse,
      );
      expect(recommendable(candidate(overrides: {'isDeleted': true})), isFalse);
      expect(
        recommendable(candidate(overrides: {'status': 'blocked'})),
        isFalse,
      );
      expect(recommendable(candidate(overrides: {'isActive': false})), isFalse);
    });

    test('프로필이 미완성이면 제외된다', () {
      expect(
        recommendable(candidate(overrides: {'initialSetupComplete': false})),
        isFalse,
      );
    });

    test('승인된 아바타가 없으면 제외된다', () {
      expect(
        recommendable(
          candidate(
            overrides: {
              'avatar': {'status': 'pending'},
            },
          ),
        ),
        isFalse,
      );
      expect(recommendable(candidate(overrides: {'avatar': null})), isFalse);
    });

    test('민감한 원본 사진 URL은 노출 이미지로 인정하지 않는다', () {
      expect(
        recommendable(
          candidate(
            overrides: {
              'avatar': {
                'status': 'approved',
                'approvedAvatarUrl':
                    'https://storage.googleapis.com/seolleyeon-private-source-photos/a.png',
              },
            },
          ),
        ),
        isFalse,
      );
    });
  });

  group('동성 제외', () {
    test('같은 성별은 제외된다', () {
      expect(
        recommendable(
          candidate(gender: 'male'),
          viewer: candidate(gender: 'male'),
        ),
        isFalse,
      );
    });

    test('성별 표기가 달라도 정규화해서 비교한다', () {
      expect(
        recommendable(
          candidate(gender: 'MALE'),
          viewer: candidate(gender: ' male '),
        ),
        isFalse,
      );
    });

    test('한쪽 성별을 모르면 제외하지 않는다', () {
      final unknown = candidate()..remove('onboarding');
      expect(recommendable(unknown), isTrue);
    });

    test('최상위 gender 필드도 읽는다', () {
      final viewer = candidate()
        ..remove('onboarding')
        ..['gender'] = 'female';
      expect(
        recommendable(candidate(gender: 'female'), viewer: viewer),
        isFalse,
      );
    });
  });

  group('조회자 기준 제외', () {
    test('자기 자신은 제외된다', () {
      expect(
        RecommendationEligibility.isRecommendableTo(
          viewerUid: 'me',
          viewer: candidate(gender: 'male'),
          candidateUid: 'me',
          candidate: candidate(),
        ),
        isFalse,
      );
    });

    test('차단한 상대는 제외된다', () {
      expect(
        RecommendationEligibility.isRecommendableTo(
          viewerUid: 'viewer',
          viewer: candidate(gender: 'male'),
          candidateUid: 'cand',
          candidate: candidate(),
          blockedUids: const {'cand'},
        ),
        isFalse,
      );
    });

    test('null 후보는 제외된다', () {
      expect(recommendable(null), isFalse);
    });
  });

  group('생활권 (campus life zone) 최종 serving guard', () {
    Map<String, dynamic> withZones(List<String>? zones) => {
      if (zones != null) 'onboarding': {'campusLifeZones': zones},
    };

    test('저장 경로 users/{uid}.onboarding.campusLifeZones 를 읽는다', () {
      expect(
        RecommendationEligibility.campusLifeZonesOf(
          withZones(['sinchon', 'songdo']),
        ),
        {'sinchon', 'songdo'},
      );
    });

    test('값이 없으면 학년·학과로 추측하지 않고 빈 집합이다', () {
      expect(
        RecommendationEligibility.campusLifeZonesOf({
          'onboarding': {'grade': '1학년', 'department': '첨단융합공학부'},
        }),
        isEmpty,
      );
      expect(RecommendationEligibility.campusLifeZonesOf(null), isEmpty);
    });

    test('공백·빈 문자열은 무시한다', () {
      expect(
        RecommendationEligibility.campusLifeZonesOf(
          withZones([' sinchon ', '', '  ']),
        ),
        {'sinchon'},
      );
    });

    test('같은 생활권끼리만 추천된다', () {
      expect(
        RecommendationEligibility.isCampusLifeZoneCompatible(
          withZones(['sinchon']),
          withZones(['sinchon']),
        ),
        isTrue,
      );
      expect(
        RecommendationEligibility.isCampusLifeZoneCompatible(
          withZones(['songdo']),
          withZones(['songdo']),
        ),
        isTrue,
      );
      expect(
        RecommendationEligibility.isCampusLifeZoneCompatible(
          withZones(['sinchon']),
          withZones(['songdo']),
        ),
        isFalse,
      );
    });

    test('복수 생활권 사용자는 양쪽 모두와 추천 가능하다', () {
      for (final other in ['sinchon', 'songdo']) {
        expect(
          RecommendationEligibility.isCampusLifeZoneCompatible(
            withZones(['sinchon', 'songdo']),
            withZones([other]),
          ),
          isTrue,
          reason: 'dual-zone ↔ $other 는 추천 가능해야 한다',
        );
        expect(
          RecommendationEligibility.isCampusLifeZoneCompatible(
            withZones([other]),
            withZones(['sinchon', 'songdo']),
          ),
          isTrue,
        );
      }
      expect(
        RecommendationEligibility.isCampusLifeZoneCompatible(
          withZones(['sinchon', 'songdo']),
          withZones(['sinchon', 'songdo']),
        ),
        isTrue,
      );
    });

    test('생활권이 없으면 fail-closed (아무 생활권이나 추천하지 않는다)', () {
      expect(
        RecommendationEligibility.isCampusLifeZoneCompatible(
          withZones(['sinchon']),
          withZones(const []),
        ),
        isFalse,
      );
      expect(
        RecommendationEligibility.isCampusLifeZoneCompatible(
          withZones(['sinchon']),
          withZones(null),
        ),
        isFalse,
      );
      expect(
        RecommendationEligibility.isCampusLifeZoneCompatible(
          withZones(null),
          withZones(['songdo']),
        ),
        isFalse,
      );
    });

    test('판정은 대칭이다', () {
      const zoneSets = [
        ['sinchon'],
        ['songdo'],
        ['sinchon', 'songdo'],
        <String>[],
      ];
      for (final left in zoneSets) {
        for (final right in zoneSets) {
          expect(
            RecommendationEligibility.isCampusLifeZoneCompatible(
              withZones(left),
              withZones(right),
            ),
            RecommendationEligibility.isCampusLifeZoneCompatible(
              withZones(right),
              withZones(left),
            ),
          );
        }
      }
    });
  });
}
