import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:seolleyeon/features/onboarding/screens/interests_selection_screen.dart';
import 'package:seolleyeon/router/route_names.dart';
import 'package:seolleyeon/services/auth_service.dart';
import 'package:seolleyeon/services/user_service.dart';

class _FakeUserService extends UserService {
  _FakeUserService(this.profile);

  final Map<String, dynamic>? profile;

  @override
  Future<Map<String, dynamic>?> getUserProfile(String kakaoUserId) async {
    return profile;
  }

  @override
  Future<void> saveOnboardingInterests({
    required String kakaoUserId,
    required List<String> interests,
  }) async {
    final onboarding = profile?['onboarding'];
    if (onboarding is Map<String, dynamic>) {
      onboarding['interests'] = List<String>.from(interests);
    }
  }
}

Map<String, dynamic> _profile({
  required List<String> interests,
  Map<String, dynamic>? overrides,
}) {
  return <String, dynamic>{
    'initialSetupComplete': true,
    'onboarding': <String, dynamic>{
      'nickname': 'tester',
      'gender': 'female',
      'interests': interests,
      'lifestyle': <String, dynamic>{'drinking': 'none', 'smoking': 'never'},
      'major': 'humanities',
      'sourcePhotoUploadCount': 1,
      'selfIntroduction': 'hello',
      'profileQa': [
        {'question': 'q', 'answer': 'a'},
      ],
      'keywords': ['calm'],
    },
    ...?overrides,
  };
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    SharedPreferences.setMockInitialValues({});
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp();
    }
  });

  test(
    'AuthService resumes completed onboarding at interest recovery',
    () async {
      final authService = AuthService(
        userService: _FakeUserService(_profile(interests: <String>[])),
      );

      expect(
        await authService.getOnboardingNextRoute('fixture-user'),
        RouteNames.onboardingInterestsSelection,
      );
    },
  );

  test(
    'saved interests advance recovery after the independent write',
    () async {
      final userService = _FakeUserService(_profile(interests: <String>[]));
      final authService = AuthService(userService: userService);

      expect(
        await authService.getOnboardingNextRoute('fixture-user'),
        RouteNames.onboardingInterestsSelection,
      );

      await userService.saveOnboardingInterests(
        kakaoUserId: 'fixture-user',
        interests: const ['movie'],
      );

      expect(
        await authService.getOnboardingNextRoute('fixture-user'),
        RouteNames.onboardingIdealType,
      );
    },
  );

  test('saving interests advances recovery to the next missing step', () async {
    final authService = AuthService(
      userService: _FakeUserService(_profile(interests: ['movie'])),
    );

    expect(
      await authService.getOnboardingNextRoute('fixture-user'),
      RouteNames.onboardingIdealType,
    );
  });

  testWidgets('recovery route resolves to the real interests screen', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () => Navigator.of(
              context,
            ).pushNamed(RouteNames.onboardingInterestsSelection),
            child: const Text('open'),
          ),
        ),
        onGenerateRoute: (settings) => MaterialPageRoute<void>(
          settings: settings,
          builder: (_) => const InterestsSelectionScreen(),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(find.byType(InterestsSelectionScreen), findsOneWidget);
    expect(tester.takeException(), isNull);

    await tester.pumpWidget(const SizedBox());
  });
}
