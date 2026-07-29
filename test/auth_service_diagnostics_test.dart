import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/firebase_diagnostics.dart';

void main() {
  test('Kakao Firebase bridge logs phases without printing tokens', () {
    final authService = File('lib/services/auth_service.dart');
    final diagnostics = File('lib/services/firebase_diagnostics.dart');

    expect(authService.existsSync(), isTrue);
    expect(diagnostics.existsSync(), isTrue);

    final authSource = authService.readAsStringSync();
    final diagnosticsSource = diagnostics.readAsStringSync();

    for (final marker in [
      'kakao_login_start',
      'kakao_login_success',
      'firebase_session_prepare_start',
      'firebase_custom_token_request_start',
      'firebase_custom_token_request_success',
      'firebase_custom_token_request_failed',
      'firebase_custom_token_signin_start',
      'firebase_custom_token_signin_success',
      'firebase_custom_token_signin_failed',
    ]) {
      expect(
        authSource,
        contains(marker),
        reason: 'Auth bridge should expose debug phase marker $marker.',
      );
    }

    expect(
      RegExp(r'debugPrint\([^)]*\$accessToken').hasMatch(authSource),
      isFalse,
      reason: 'Kakao access tokens must never be printed.',
    );
    expect(
      RegExp(r'debugPrint\([^)]*\$customToken').hasMatch(authSource),
      isFalse,
      reason: 'Firebase custom tokens must never be printed.',
    );
    expect(
      authSource,
      isNot(contains(r'details=${e.details}')),
      reason:
          'Callable details may contain request data and should be omitted.',
    );
    expect(diagnosticsSource, contains('Bearer <redacted>'));
    expect(diagnosticsSource, contains('accessToken=<redacted>'));
    expect(diagnosticsSource, contains('customToken=<redacted>'));
    expect(diagnosticsSource, contains('hasApiKey='));
    expect(diagnosticsSource, isNot(contains('apiKeyPrefix=')));
    expect(diagnosticsSource, isNot(contains(r'apiKey=${')));
  });

  test('student email link diagnostics do not print email link secrets', () {
    final featureScreen = File(
      'lib/features/auth/screens/student_verification_screen.dart',
    ).readAsStringSync();
    final legacyScreen = File(
      'lib/screens/auth/student_verification_screen.dart',
    ).readAsStringSync();

    for (final source in [featureScreen, legacyScreen]) {
      expect(source, contains("webOrigin: kIsWeb ? Uri.base.origin : ''"));
      expect(source, isNot(contains('token=\$token')));
      expect(source, isNot(contains('email=\$email')));
      expect(source, isNot(contains('debugPrint(e.toString())')));
    }

    final redacted = FirebaseDiagnostics.safeErrorForLog(
      'email=person@yonsei.ac.kr token=93315f58-5695-4599-9710-d78eaa77b525'
      '&apiKey=secret&oobCode=secret-code&t=93315f58-5695-4599-9710-d78eaa77b525',
    );
    expect(redacted, contains('<redacted-email>'));
    expect(redacted, isNot(contains('person@yonsei.ac.kr')));
    expect(redacted, isNot(contains('93315f58-5695-4599-9710-d78eaa77b525')));
    expect(redacted, contains('apiKey=<redacted>'));
    expect(redacted, contains('oobCode=<redacted>'));
    expect(redacted, contains('t=<redacted>'));
  });
}
