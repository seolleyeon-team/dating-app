import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final root = Directory.current.path;

  String read(String relativePath) =>
      File('$root/$relativePath').readAsStringSync();

  test('native and web Kakao login attach Firebase before Firestore work', () {
    final source = read('lib/features/auth/screens/kakao_auth_screen.dart');
    expect(source, contains('KakaoLoginFirestoreBootstrap'));

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
      final bootstrap = section.indexOf('_loginBootstrap.bootstrap');
      final localIdSave = section.indexOf('saveKakaoUserId');

      expect(bootstrap, isNonNegative, reason: methodMarker);
      expect(localIdSave, isNonNegative, reason: methodMarker);
      expect(
        bootstrap,
        lessThan(localIdSave),
        reason:
            'Firebase must be attached before local login state is persisted.',
      );
      expect(section, isNot(contains('_attachFirebaseSession')));
      expect(section, isNot(contains('_ensureUserShellIfMissing')));
      expect(section, isNot(contains('_userService.upsertKakaoUser')));
    }
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

  test('OAuth callback does not write a user document before auth', () {
    final source = read('lib/screens/auth/kakao_callback_screen.dart');
    expect(source, contains('setKakaoLogin'));
    expect(source, isNot(contains("services/user_service.dart")));
    expect(source, isNot(contains('upsertKakaoUser')));
  });
}
