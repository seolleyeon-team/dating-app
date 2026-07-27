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
      expect(
        recommendable(candidate(overrides: {'isDeleted': true})),
        isFalse,
      );
      expect(
        recommendable(candidate(overrides: {'status': 'blocked'})),
        isFalse,
      );
      expect(
        recommendable(candidate(overrides: {'isActive': false})),
        isFalse,
      );
    });

    test('프로필이 미완성이면 제외된다', () {
      expect(
        recommendable(candidate(overrides: {'initialSetupComplete': false})),
        isFalse,
      );
    });

    test('승인된 아바타가 없으면 제외된다', () {
      expect(
        recommendable(candidate(overrides: {'avatar': {'status': 'pending'}})),
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
      expect(recommendable(candidate(gender: 'female'), viewer: viewer), isFalse);
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
}
