import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/app_check_readiness.dart';

void main() {
  test('non-empty App Check token is ready and reuses cached token', () async {
    var requestedForceRefresh = true;
    final readiness = AppCheckReadiness(
      tokenProvider: (forceRefresh) async {
        requestedForceRefresh = forceRefresh;
        return 'token-is-not-exposed-by-the-result';
      },
    );

    final result = await readiness.preflight();

    expect(result.status, AppCheckPreflightStatus.ready);
    expect(result.isReady, isTrue);
    expect(requestedForceRefresh, isFalse);
    expect(result.errorSummary, isNull);
    expect(result.supportCode, isNull);
  });

  test('concurrent preflights share one token request', () async {
    var requestCount = 0;
    final completer = Completer<String?>();
    final readiness = AppCheckReadiness(
      tokenProvider: (forceRefresh) {
        requestCount += 1;
        return completer.future;
      },
    );

    final first = readiness.preflight();
    final second = readiness.preflight();
    expect(requestCount, 1);

    completer.complete('cached-token');
    final results = await Future.wait([first, second]);
    expect(results.every((result) => result.isReady), isTrue);
    expect(requestCount, 1);
  });

  test('null or blank App Check token is an explicit empty state', () async {
    for (final token in <String?>[null, '', '   ']) {
      final result = await AppCheckReadiness(
        tokenProvider: (forceRefresh) async => token,
      ).preflight();

      expect(result.status, AppCheckPreflightStatus.empty);
      expect(result.isReady, isFalse);
      expect(result.supportCode, 'AC-E-TOKEN-EMPTY');
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
    expect(result.supportCode, 'AC-R-ATTESTATION');
  });

  test('non-attestation errors are classified as unavailable', () async {
    final result = await AppCheckReadiness(
      tokenProvider: (forceRefresh) async {
        throw StateError('temporary provider error');
      },
    ).preflight();

    expect(result.status, AppCheckPreflightStatus.unavailable);
    expect(result.errorSummary, isNot(contains('temporary provider error')));
    expect(result.supportCode, 'AC-U-APP-CHECK-UNAVAILABLE');
  });

  test(
    'rate limit messages produce a stable non-sensitive support code',
    () async {
      final result = await AppCheckReadiness(
        tokenProvider: (forceRefresh) async {
          throw FirebaseException(
            plugin: 'firebase_app_check',
            code: 'unknown',
            message: 'Too many attempts. Try again later.',
          );
        },
      ).preflight();

      expect(result.status, AppCheckPreflightStatus.unavailable);
      expect(result.supportCode, 'AC-U-RATE-LIMITED');
      expect(result.supportCode, isNot(contains('Try again later')));
    },
  );

  test(
    'rate limits take precedence when the provider also says attestation',
    () async {
      final result = await AppCheckReadiness(
        tokenProvider: (forceRefresh) async {
          throw FirebaseException(
            plugin: 'firebase_app_check',
            code: 'unknown',
            message:
                'Attestation provider: too many attempts. Try again later.',
          );
        },
      ).preflight();

      expect(result.status, AppCheckPreflightStatus.rejected);
      expect(result.supportCode, 'AC-U-RATE-LIMITED');
    },
  );

  test(
    'diagnostic summary retains provider reason but redacts token values',
    () async {
      final result = await AppCheckReadiness(
        tokenProvider: (forceRefresh) async {
          throw FirebaseException(
            plugin: 'firebase_app_check',
            code: 'unknown',
            message: 'Integrity provider rejected authorization=secret-value',
          );
        },
      ).preflight();

      expect(result.diagnosticSummary, contains('firebaseCode=unknown'));
      expect(result.diagnosticSummary, contains('authorization=[redacted]'));
      expect(result.diagnosticSummary, isNot(contains('secret-value')));
    },
  );
}
