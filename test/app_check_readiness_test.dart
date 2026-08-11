import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/app_check_readiness.dart';

void main() {
  test('non-empty App Check token is ready and uses forced refresh', () async {
    var requestedForceRefresh = false;
    final readiness = AppCheckReadiness(
      tokenProvider: (forceRefresh) async {
        requestedForceRefresh = forceRefresh;
        return 'token-is-not-exposed-by-the-result';
      },
    );

    final result = await readiness.preflight();

    expect(result.status, AppCheckPreflightStatus.ready);
    expect(result.isReady, isTrue);
    expect(requestedForceRefresh, isTrue);
    expect(result.errorSummary, isNull);
  });

  test('null or blank App Check token is an explicit empty state', () async {
    for (final token in <String?>[null, '', '   ']) {
      final result = await AppCheckReadiness(
        tokenProvider: (forceRefresh) async => token,
      ).preflight();

      expect(result.status, AppCheckPreflightStatus.empty);
      expect(result.isReady, isFalse);
    }
  });

  test('403 attestation errors are classified as rejected', () async {
    final result = await AppCheckReadiness(
      tokenProvider: (forceRefresh) async {
        throw FirebaseException(
          plugin: 'firebase_app_check',
          code: '403',
          message: 'App attestation failed.',
        );
      },
    ).preflight();

    expect(result.status, AppCheckPreflightStatus.rejected);
    expect(result.errorCode, '403');
    expect(result.errorSummary, isNot(contains('App attestation failed')));
  });

  test('non-attestation errors are classified as unavailable', () async {
    final result = await AppCheckReadiness(
      tokenProvider: (forceRefresh) async {
        throw StateError('temporary provider error');
      },
    ).preflight();

    expect(result.status, AppCheckPreflightStatus.unavailable);
    expect(result.errorSummary, isNot(contains('temporary provider error')));
  });
}
