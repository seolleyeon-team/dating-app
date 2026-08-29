import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/auth/utils/post_student_verification_route.dart';
import 'package:seolleyeon/router/route_names.dart';

void main() {
  test(
    'completed profile opens main immediately after student verification',
    () {
      expect(
        resolvePostStudentVerificationRoute(
          initialSetupComplete: true,
          nextOnboardingRoute: RouteNames.onboardingInterestsSelection,
        ),
        RouteNames.main,
      );
    },
  );

  test('incomplete profile resumes its next onboarding step', () {
    expect(
      resolvePostStudentVerificationRoute(
        initialSetupComplete: false,
        nextOnboardingRoute: RouteNames.onboardingInterestsSelection,
      ),
      RouteNames.onboardingInterestsSelection,
    );
  });

  test('complete legacy profile without marker opens main', () {
    expect(
      resolvePostStudentVerificationRoute(initialSetupComplete: false),
      RouteNames.main,
    );
  });
}
