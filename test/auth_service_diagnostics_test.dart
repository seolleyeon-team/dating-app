import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/firebase_diagnostics.dart';

void main() {
  test('primary email auth logs phases without printing tokens', () {
    final authService = File('lib/services/auth_service.dart');
    final diagnostics = File('lib/services/firebase_diagnostics.dart');

    expect(authService.existsSync(), isTrue);
    expect(diagnostics.existsSync(), isTrue);

    final authSource = authService.readAsStringSync();
    final diagnosticsSource = diagnostics.readAsStringSync();

    for (final marker in [
      'primary_email_link_send_start',
      'primary_email_link_send_success',
      'primary_email_link_send_failed',
      'primary_email_completion_start',
      'primary_email_completion_success',
      'primary_email_completion_failed',
      'primary_email_signin_start',
      'primary_email_signin_failed',
      'primary_email_uid_mismatch',
    ]) {
      expect(
        authSource,
        contains(marker),
        reason: 'Primary auth should expose debug phase marker $marker.',
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

    // 이어보기 URL 은 서버가 프로젝트 ID 로 만든다. 화면이 origin 을 넘기지
    // 않는 것이 정상이므로 여기서 검사하지 않는다.
    for (final source in [featureScreen, legacyScreen]) {
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
