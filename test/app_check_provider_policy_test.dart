import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/utils/app_check_provider_policy.dart';

void main() {
  group('App Check provider policy', () {
    test('release builds never use debug providers', () {
      expect(
        shouldUseDebugAppCheckProvider(isWeb: false, isReleaseMode: true),
        isFalse,
      );
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

    test('web reCAPTCHA site key is required and trimmed', () {
      expect(webAppCheckRecaptchaSiteKey(), isNull);
      expect(webAppCheckRecaptchaSiteKey(fromEnvironment: ''), isNull);
      expect(webAppCheckRecaptchaSiteKey(fromEnvironment: '   '), isNull);
      expect(
        webAppCheckRecaptchaSiteKey(fromEnvironment: '  site-key  '),
        'site-key',
      );
    });
  });
}
