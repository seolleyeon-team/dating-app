import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/push_notification_service.dart';

void main() {
  test('push initialization is safe before Firebase is available', () async {
    await expectLater(PushNotificationService.instance.initialize(), completes);
  });

  test('push diagnostics do not log raw identifiers or tokens', () {
    final source = File(
      'lib/services/push_notification_service.dart',
    ).readAsStringSync();

    expect(source, contains('PrivacyLogUtils.idFingerprint(roomId)'));
    expect(source, contains('PrivacyLogUtils.idFingerprint(userId)'));
    expect(source, contains('hasApnsToken='));
    expect(source, contains('hasFcmToken='));
    expect(source, isNot(contains(r'room=$roomId')));
    expect(source, isNot(contains(r'kakaoUserId = $userId')));
    expect(source, isNot(contains(r'apnsToken = $apnsToken')));
    expect(source, isNot(contains(r'fcmToken = $token')));
    expect(source, isNot(contains(r"debugPrint('$st')")));
  });
}
