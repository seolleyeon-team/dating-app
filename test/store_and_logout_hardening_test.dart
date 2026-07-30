import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('release Android build must not fall back to debug signing', () {
    final gradle = File('android/app/build.gradle.kts').readAsStringSync();
    expect(gradle, contains('hasReleaseKeystore'));
    expect(gradle, contains('Fail closed'));
    expect(
      gradle,
      isNot(contains('signingConfig = signingConfigs.getByName("debug")')),
    );
    expect(File('android/key.properties.example').existsSync(), isTrue);
  });

  test('iOS PrivacyInfo.xcprivacy exists for App Store privacy manifest', () {
    final privacy = File('ios/Runner/PrivacyInfo.xcprivacy');
    expect(privacy.existsSync(), isTrue);
    final body = privacy.readAsStringSync();
    expect(body, contains('NSPrivacyTracking'));
    expect(body, contains('NSPrivacyAccessedAPITypes'));
  });

  test('logout clears user-scoped local session helpers', () {
    final storage = File(
      'lib/services/storage_service.dart',
    ).readAsStringSync();
    final auth = File('lib/providers/auth_provider.dart').readAsStringSync();
    expect(storage, contains('clearUserScopedSession'));
    expect(auth, contains('clearUserScopedSession'));
  });
}
