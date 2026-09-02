import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/utils/recommendation_eligibility.dart';

void main() {
  group('RecommendationEligibility profile visibility', () {
    test('a pending hide remains eligible until the next KST date', () {
      const profile = <String, dynamic>{
        'profileVisible': false,
        'profileVisibleBeforeEffectiveDate': true,
        'profileVisibleEffectiveDateKey': '20260902',
      };

      expect(
        RecommendationEligibility.isProfileVisibleForRecommendationToday(
          profile,
          now: DateTime.utc(2026, 9, 1, 14),
        ),
        isTrue,
      );
      expect(
        RecommendationEligibility.isProfileVisibleForRecommendationToday(
          profile,
          now: DateTime.utc(2026, 9, 1, 15),
        ),
        isFalse,
      );
    });

    test('a pending show remains hidden until the next KST date', () {
      const profile = <String, dynamic>{
        'profileVisible': true,
        'profileVisibleBeforeEffectiveDate': false,
        'profileVisibleEffectiveDateKey': '20260902',
      };

      expect(
        RecommendationEligibility.isProfileVisibleForRecommendationToday(
          profile,
          now: DateTime.utc(2026, 9, 1, 14),
        ),
        isFalse,
      );
      expect(
        RecommendationEligibility.isProfileVisibleForRecommendationToday(
          profile,
          now: DateTime.utc(2026, 9, 1, 15),
        ),
        isTrue,
      );
    });
  });
}
