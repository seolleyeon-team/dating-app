import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/router/route_names.dart';
import 'package:seolleyeon/services/onboarding_route_resolver.dart';

/// 온보딩 재개(resume) 라우팅의 사진/아바타 게이트 회귀 테스트.
///
/// 사진 단계는 "승인된 아바타"가 있어야만 통과한다. 과거처럼
/// sourcePhotoUploadCount 카운터(클라이언트 위조 가능)만으로는 통과할 수 없다.
Map<String, dynamic> _baseProfile({Map<String, dynamic>? avatar}) {
  return <String, dynamic>{
    if (avatar != null) 'avatar': avatar,
    'onboarding': <String, dynamic>{
      'nickname': 'tester',
      'gender': 'female',
      'interests': ['movie'],
      'lifestyle': <String, dynamic>{'drinking': 'none'},
      'major': 'humanities',
      'sourcePhotoUploadCount': 2,
      'selfIntroduction': 'hello',
      'profileQa': [
        {'question': 'q', 'answer': 'a'},
      ],
      'keywords': ['calm'],
    },
    'idealType': <String, dynamic>{
      'preferredLifestyles': ['calm'],
    },
  };
}

void main() {
  group('resolveOnboardingNextRoute avatar gate', () {
    test('업로드 카운터만으로는 사진 단계를 통과할 수 없다', () {
      final profile = _baseProfile();

      expect(
        resolveOnboardingNextRoute(profile),
        RouteNames.onboardingPhoto,
      );
    });

    test('승인된 아바타 상태가 있으면 사진 단계를 통과한다', () {
      final profile = _baseProfile(
        avatar: <String, dynamic>{'status': 'approved'},
      );

      expect(resolveOnboardingNextRoute(profile), isNull);
    });

    test('onboarding.avatarUrls에 안전한 승인 URL이 있으면 통과한다', () {
      final profile = _baseProfile();
      (profile['onboarding'] as Map<String, dynamic>)['avatarUrls'] = [
        'https://firebasestorage.googleapis.com/v0/b/approved/o/avatar.png',
      ];

      expect(resolveOnboardingNextRoute(profile), isNull);
    });

    test('안전하지 않은 URL만 있으면 사진 단계로 되돌린다', () {
      final profile = _baseProfile();
      (profile['onboarding'] as Map<String, dynamic>)['avatarUrls'] = [
        'gs://seolleyeon-final-avatar-temp/users/u1/jobs/j/candidates/c.png',
      ];

      expect(
        resolveOnboardingNextRoute(profile),
        RouteNames.onboardingPhoto,
      );
    });

    test('진행 중(미승인) 생성 상태는 사진 단계로 되돌린다', () {
      final profile = _baseProfile(
        avatar: <String, dynamic>{'status': 'preview_ready'},
      );

      expect(
        resolveOnboardingNextRoute(profile),
        RouteNames.onboardingPhoto,
      );
    });
  });
}
