import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Kakao login attaches Firebase before any users/{id} Firestore access', () {
    final file = File(
      'lib/features/auth/services/kakao_login_firestore_bootstrap.dart',
    );

    expect(
      file.existsSync(),
      isTrue,
      reason:
          'Kakao login Firestore bootstrapping should live in a small service.',
    );

    final source = file.readAsStringSync();
    final existsIndex = source.indexOf('kakaoUserExists');
    final sessionIndex = source.indexOf('ensureFirebaseSessionForKakao');
    final failureGuardIndex = source.indexOf('if (!firebaseAttached)');
    final lastActiveIndex = source.indexOf('setLastActivePlatform');

    expect(existsIndex, isNonNegative);
    expect(sessionIndex, isNonNegative);
    expect(failureGuardIndex, isNonNegative);
    expect(lastActiveIndex, isNonNegative);
    expect(
      source.contains('upsertKakaoUser'),
      isFalse,
      reason:
          'The client must not create users/{kakaoUserId}; the callable does it with Admin privileges.',
    );
    expect(
      sessionIndex,
      lessThan(failureGuardIndex),
      reason: 'failed Firebase session attachment must be handled explicitly.',
    );
    expect(
      failureGuardIndex,
      lessThan(existsIndex),
      reason:
          'users/{id} get requires isSignedIn(); check existence only after the custom-token session is attached.',
    );
    expect(
      existsIndex,
      lessThan(lastActiveIndex),
      reason:
          'lastActivePlatform is an owner update and must not run unauthenticated.',
    );
  });
}
