import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/utils/app_check_provider_policy.dart';

void main() {
  group('App Check provider policy', () {
    test('release builds never use debug providers by default', () {
      expect(
        shouldUseDebugAppCheckProvider(isWeb: false, isReleaseMode: true),
        isFalse,
      );
    });

    test(
      'force debug overrides release default for local release APK tests',
      () {
        expect(
          shouldUseDebugAppCheckProvider(
            isWeb: false,
            isReleaseMode: true,
            forceDebugProvider: true,
          ),
          isTrue,
        );
      },
    );

    test('debug-signed Android release still uses production providers', () {
      expect(
        shouldUseDebugAppCheckProvider(
          isWeb: false,
          isReleaseMode: true,
          isDebugSignedAndroid: true,
        ),
        isFalse,
      );
    });

    test('Android debug token is trimmed and absent when unset', () {
      expect(
        androidAppCheckDebugToken(fromEnvironment: '  local-token  '),
        'local-token',
      );
      expect(androidAppCheckDebugToken(fromEnvironment: '   '), isNull);
      expect(androidAppCheckDebugToken(), isNull);
    });

    test('non-release app builds use debug providers', () {
      expect(
        shouldUseDebugAppCheckProvider(isWeb: false, isReleaseMode: false),
        isTrue,
      );
    });

    test('web builds do not activate native debug providers', () {
      expect(
        shouldUseDebugAppCheckProvider(isWeb: true, isReleaseMode: false),
        isFalse,
      );
    });

    test('localhost web debug builds use the web debug provider', () {
      expect(
        shouldUseWebDebugAppCheckProvider(isDebugMode: true, host: 'localhost'),
        isTrue,
      );
      expect(
        shouldUseWebDebugAppCheckProvider(isDebugMode: true, host: '127.0.0.1'),
        isTrue,
      );
    });

    test('non-local or non-debug web builds keep the deployed provider', () {
      expect(
        shouldUseWebDebugAppCheckProvider(
          isDebugMode: true,
          host: 'seolleyeon-final.web.app',
        ),
        isFalse,
      );
      expect(
        shouldUseWebDebugAppCheckProvider(
          isDebugMode: false,
          host: 'localhost',
        ),
        isFalse,
      );
    });

    test('web reCAPTCHA site key is required and trimmed', () {
      expect(webAppCheckRecaptchaSiteKey(), isNull);
      expect(webAppCheckRecaptchaSiteKey(fromEnvironment: ''), isNull);
      expect(webAppCheckRecaptchaSiteKey(fromEnvironment: '   '), isNull);
      expect(
        webAppCheckRecaptchaSiteKey(fromEnvironment: '  site-key  '),
        'site-key',
      );
    });

    test('missing web site key is an explicit skipped state', () {
      final result = evaluateWebAppCheckActivation(siteKey: null);
      expect(result.status, AppCheckInitStatus.skippedWebMissingKey);
      expect(result.callablesLikelyBlocked, isTrue);
      expect(result.isReady, isFalse);
    });

    test('native activation failure is not silent success', () {
      final result = evaluateNativeAppCheckActivation(
        usedDebugProvider: false,
        platform: 'android',
        activateErrorSummary: 'provider_unavailable',
      );
      expect(result.status, AppCheckInitStatus.failed);
      expect(result.callablesLikelyBlocked, isTrue);
      expect(result.errorSummary, 'provider_unavailable');
    });

    test(
      'main wires stable token only to explicit debug provider branches',
      () {
        final source = File('lib/main.dart').readAsStringSync();

        expect(source, contains('APP_CHECK_ANDROID_DEBUG_TOKEN'));
        expect(source, contains('AndroidDebugProvider(debugToken:'));
        expect(source, contains('AndroidPlayIntegrityProvider()'));
        expect(source, contains('AppleAppAttestProvider()'));
        expect(source, contains('recordAppCheckInitResult'));
        expect(source, isNot(contains('isDebugSignedAndroid')));
      },
    );
  });
}
