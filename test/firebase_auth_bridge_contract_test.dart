import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  final root = Directory.current.path;

  String read(String relativePath) =>
      File('$root/$relativePath').readAsStringSync();

  String sectionBetween(String source, String startMarker, String endMarker) {
    final start = source.indexOf(startMarker);
    expect(start, isNonNegative, reason: startMarker);
    final end = source.indexOf(endMarker, start + startMarker.length);
    return source.substring(start, end == -1 ? source.length : end);
  }

  test('session inspection failure is distinct from mismatch and sign-out', () {
    final source = read('lib/services/auth_service.dart');
    final signOutSection = sectionBetween(
      source,
      'Future<void> _signOutFirebaseIfMismatched',
      'Future<Map<String, dynamic>> loginWithKakao',
    );

    expect(signOutSection, contains('FirebaseSessionIdentityState.mismatched'));
    expect(signOutSection, isNot(contains('_hasMatchingFirebaseSession')));

    final ensureSection = sectionBetween(
      source,
      'Future<bool> ensureFirebaseSessionForKakao',
      'Future<bool> ensureFirebaseSessionForVerifiedUser',
    );
    expect(
      ensureSection,
      contains('FirebaseSessionIdentityState.inspectionFailed'),
    );
    expect(
      ensureSection,
      contains('FirebaseSessionFailureReason.sessionInspectionFailed'),
    );
    expect(
      ensureSection,
      contains('FirebaseSessionFailureReason.identityMismatch'),
    );
  });

  test('App Check preflight completes before the custom-token callable', () {
    final source = read('lib/services/auth_service.dart');
    final ensureSection = sectionBetween(
      source,
      'Future<bool> ensureFirebaseSessionForKakao',
      'Future<bool> ensureFirebaseSessionForVerifiedUser',
    );
    final preflight = ensureSection.indexOf('appCheckReadiness.preflight');
    final preflightGuard = ensureSection.indexOf(
      'if (!appCheckPreflight.isReady)',
    );
    final callable = ensureSection.indexOf(
      "httpsCallable('createFirebaseCustomToken')",
    );

    expect(preflight, isNonNegative);
    expect(preflightGuard, isNonNegative);
    expect(callable, isNonNegative);
    expect(preflight, lessThan(preflightGuard));
    expect(preflightGuard, lessThan(callable));
    expect(
      ensureSection,
      contains('FirebaseSessionFailureReason.appCheckRejected'),
    );
    expect(
      ensureSection,
      contains('FirebaseSessionFailureReason.customTokenEmpty'),
    );
  });

  test(
    'successful custom-token sign-in validates identity without forced refresh',
    () {
      final source = read('lib/services/auth_service.dart');
      final ensureSection = sectionBetween(
        source,
        'Future<bool> ensureFirebaseSessionForKakao',
        'Future<bool> ensureFirebaseSessionForVerifiedUser',
      );

      expect(ensureSection, contains('_inspectFirebaseSession'));
      expect(ensureSection, contains('firebase_custom_token_signin_success'));
      expect(ensureSection, isNot(contains('getIdToken(true)')));
    },
  );

  test('login boundaries propagate typed bridge failures', () {
    final bootstrap = read(
      'lib/features/auth/services/kakao_login_firestore_bootstrap.dart',
    );
    final authProvider = read('lib/providers/auth_provider.dart');

    expect(bootstrap, contains('FirebaseSessionFailure'));
    expect(authProvider, contains('FirebaseSessionFailure'));
    expect(bootstrap, isNot(contains('Firebase 濡쒓렇???몄뀡??以鍮꾪븯吏')));
  });

  test('transient failures do not clear the cached Kakao identity', () {
    final authProvider = read('lib/providers/auth_provider.dart');
    final splash = read('lib/features/splash/splash_screen.dart');

    expect(authProvider, contains('lastFirebaseSessionFailure'));
    expect(authProvider, contains('isTransient'));
    expect(splash, contains('lastFirebaseSessionFailure'));
    expect(splash, contains('isTransient'));
  });
}
