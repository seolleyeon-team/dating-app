import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The Kakao→Firebase custom-token bridge was REMOVED with the
/// Yonsei-email-primary re-architecture. These tests pin its absence and the
/// integrity checks of the replacement (canonical email custom token).
void main() {
  final root = Directory.current.path;

  String read(String relativePath) =>
      File('$root/$relativePath').readAsStringSync();

  test('the Kakao→custom-token bridge is gone from the client', () {
    final authService = read('lib/services/auth_service.dart');

    expect(authService, isNot(contains('createFirebaseCustomToken')));
    expect(authService, isNot(contains('ensureFirebaseSessionForKakao')));
    expect(
      authService,
      isNot(contains('ensureFirebaseSessionForVerifiedUser')),
    );
    expect(authService, isNot(contains('FirebaseSessionInspector')));
    expect(authService, isNot(contains('FirebaseSessionFailure')));

    // The bridge support machinery was deleted with it.
    expect(
      File('$root/lib/services/firebase_session_inspector.dart').existsSync(),
      isFalse,
    );
    expect(
      File('$root/lib/services/firebase_session_failure.dart').existsSync(),
      isFalse,
    );
  });

  test('no production file bridges a Kakao token into a Firebase session', () {
    final libDir = Directory('$root/lib');
    final offenders = <String>[];
    for (final entity in libDir.listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final source = entity.readAsStringSync();
      if (source.contains('createFirebaseCustomToken') ||
          source.contains('ensureFirebaseSessionForKakao') ||
          source.contains('ensureFirebaseSessionForVerifiedUser')) {
        offenders.add(entity.path);
      }
    }
    expect(
      offenders,
      isEmpty,
      reason:
          'Kakao access tokens must never become Firebase sessions anywhere.',
    );
  });

  test(
    'completePrimaryStudentEmailAuth verifies the minted session identity',
    () {
      final source = read('lib/services/auth_service.dart');
      final start = source.indexOf('completePrimaryStudentEmailAuth');
      expect(start, isNonNegative);
      final end = source.indexOf('bool isSignInWithEmailLink', start);
      final section = source.substring(start, end == -1 ? source.length : end);

      final signIn = section.indexOf('signInWithCustomToken');
      final refresh = section.indexOf('getIdToken(true)');
      final assertUid = section.indexOf('uid != completion.appUserId');
      final signOutOnMismatch = section.indexOf('signOut');

      expect(signIn, isNonNegative);
      expect(refresh, isNonNegative);
      expect(assertUid, isNonNegative);
      expect(signOutOnMismatch, isNonNegative);
      expect(signIn, lessThan(refresh));
      expect(refresh, lessThan(assertUid));
      expect(
        assertUid,
        lessThan(signOutOnMismatch),
        reason: 'A uid-mismatched session must be discarded, never kept.',
      );
    },
  );

  test('ensureCanonicalAppSession is a pure Firebase check', () {
    final source = read('lib/services/auth_service.dart');
    final start = source.indexOf('Future<bool> ensureCanonicalAppSession()');
    expect(start, isNonNegative);
    final end = source.indexOf('Future<void> sendPrimaryStudentEmailLink');
    final section = source.substring(start, end);

    expect(section, contains('_firebaseAuth.currentUser != null'));
    expect(section, isNot(contains('httpsCallable')));
    expect(section, isNot(contains('TokenManagerProvider')));
    expect(section, isNot(contains('accessTokenInfo')));
  });

  test('primary email completion propagates typed callable failures', () {
    final source = read('lib/services/auth_service.dart');
    expect(source, contains('primary_email_completion_failed'));
    expect(source, contains('primary_email_signin_failed'));
    expect(source, contains('rethrow;'));
  });
}
