import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final root = Directory.current.path;

  String read(String relativePath) =>
      File('$root/$relativePath').readAsStringSync();

  test('native and web Kakao login attach Firebase before Firestore work', () {
    final source = read('lib/features/auth/screens/kakao_auth_screen.dart');
    expect(source, contains('KakaoLoginFirestoreBootstrap'));

    final continueStart = source.indexOf(
      'Future<void> _continueAfterKakaoLogin(',
    );
    expect(continueStart, isNonNegative);
    final continueEnd = source.indexOf('\n  Future<void> ', continueStart + 1);
    final continueSection = source.substring(
      continueStart,
      continueEnd == -1 ? source.length : continueEnd,
    );
    final bootstrap = continueSection.indexOf('_loginBootstrap.bootstrap');
    final adultVerification = continueSection.indexOf(
      '_verifyAdultIdentityAfterKakaoLogin',
    );
    final localIdSave = continueSection.indexOf('saveKakaoUserId');

    expect(bootstrap, isNonNegative);
    expect(localIdSave, isNonNegative);
    expect(adultVerification, isNonNegative);
    expect(
      bootstrap,
      lessThan(adultVerification),
      reason: 'PortOne verification requires an attached Firebase session.',
    );
    expect(
      adultVerification,
      lessThan(localIdSave),
      reason:
          'Identity verification must finish before local login state is persisted.',
    );
    expect(continueSection, isNot(contains('_attachFirebaseSession')));
    expect(continueSection, isNot(contains('_ensureUserShellIfMissing')));
    expect(continueSection, isNot(contains('_userService.upsertKakaoUser')));

    for (final methodMarker in [
      'Future<void> _login()',
      'Future<void> _loginWithWeb()',
    ]) {
      final start = source.indexOf(methodMarker);
      expect(start, isNonNegative, reason: methodMarker);
      final nextMethod = source.indexOf(
        '\n  Future<void> ',
        start + methodMarker.length,
      );
      final section = source.substring(
        start,
        nextMethod == -1 ? source.length : nextMethod,
      );
      expect(section, contains('_pauseForMissingFriendsConsent'));
      expect(section, contains('_continueAfterKakaoLogin'));
      expect(
        section.indexOf('_pauseForMissingFriendsConsent'),
        lessThan(section.indexOf('_continueAfterKakaoLogin')),
        reason: 'Friends consent must be checked before Firebase onboarding.',
      );
      expect(section, isNot(contains('_attachFirebaseSession')));
      expect(section, isNot(contains('_ensureUserShellIfMissing')));
      expect(section, isNot(contains('_userService.upsertKakaoUser')));
    }
  });

  test('terms require identity verification before the Kakao login screen', () {
    final terms = read('lib/features/onboarding/screens/terms_screen.dart');
    final router = read('lib/router/app_router.dart');
    final verification = read('lib/services/adult_verification_service.dart');

    expect(terms, contains('RouteNames.adultVerification'));
    expect(router, contains('AdultVerificationGateScreen'));
    expect(router, contains('case RouteNames.adultVerification'));
    expect(verification, contains("'ADULT_VERIFICATION_BYPASS'"));
    expect(verification, isNot(contains('isTemporarilyDisabled = true')));
  });

  test('splash validates the Firebase session before reading users', () {
    final source = read('lib/features/splash/splash_screen.dart');
    final session = source.indexOf('ensureFirebaseSessionForKakao');
    final usersRead = source.indexOf('kakaoUserExists');

    expect(session, isNonNegative);
    expect(usersRead, isNonNegative);
    expect(
      session,
      lessThan(usersRead),
      reason: 'A cached Kakao ID alone must not authorize a users read.',
    );
    expect(source, contains('clearKakaoUserId'));
    expect(source, contains('RouteNames.terms'));
  });

  test('AuthProvider fails closed when the Firebase bridge cannot attach', () {
    final source = read('lib/providers/auth_provider.dart');
    final statusStart = source.indexOf('Future<void> _checkAuthStatus()');
    final statusEnd = source.indexOf(
      '\n  // ---------------------------------------------------------------------------',
      statusStart + 1,
    );
    final statusSection = source.substring(
      statusStart,
      statusEnd == -1 ? source.length : statusEnd,
    );
    expect(
      statusSection.indexOf('ensureFirebaseSessionForKakao'),
      lessThan(statusSection.indexOf('_isAuthenticated = true;')),
    );

    final setterStart = source.indexOf('Future<void> setKakaoLogin(');
    final setterEnd = source.indexOf(
      '\n  // ---------------------------------------------------------------------------',
      setterStart + 1,
    );
    final setterSection = source.substring(
      setterStart,
      setterEnd == -1 ? source.length : setterEnd,
    );
    expect(setterSection, contains('if (!firebaseAttached)'));
    expect(setterSection, contains('rethrow;'));
    expect(
      setterSection.indexOf('ensureFirebaseSessionForKakao'),
      lessThan(setterSection.indexOf('saveKakaoUserId')),
    );
  });

  test('Kakao OAuth callback is owned by the SDK, not app-side screens', () {
    final kakaoAuthScreen = read(
      'lib/features/auth/screens/kakao_auth_screen.dart',
    );
    final authProvider = read('lib/providers/auth_provider.dart');
    final activeRouter = read('lib/router/app_router.dart');
    final legacyRouter = read('lib/routes/app_router.dart');

    expect(kakaoAuthScreen, isNot(contains('receiveKakaoScheme')));
    expect(kakaoAuthScreen, isNot(contains('KakaoCallbackScreen')));
    expect(authProvider, isNot(contains('receiveKakaoScheme')));
    expect(authProvider, contains('kakaoSchemeStream'));
    expect(activeRouter, isNot(contains('KakaoCallbackScreen')));
    expect(activeRouter, isNot(contains("name.contains('code=')")));
    expect(legacyRouter, isNot(contains('KakaoCallbackScreen')));
    expect(
      File('$root/lib/screens/auth/kakao_callback_screen.dart').existsSync(),
      isFalse,
    );
  });
}
