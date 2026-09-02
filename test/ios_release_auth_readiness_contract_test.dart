import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/config/portone_config.dart';

void main() {
  final root = Directory.current.path;

  test('iOS Release signs with the production App Attest entitlement', () {
    final entitlements = File(
      '$root/ios/Runner/RunnerRelease.entitlements',
    ).readAsStringSync();
    final project = File(
      '$root/ios/Runner.xcodeproj/project.pbxproj',
    ).readAsStringSync();

    expect(
      entitlements,
      contains('com.apple.developer.devicecheck.appattest-environment'),
    );
    expect(entitlements, contains('<string>production</string>'));
    expect(
      project,
      contains('CODE_SIGN_ENTITLEMENTS = Runner/RunnerRelease.entitlements;'),
    );
  });

  test('portable iOS archive has a production PortOne channel default', () {
    expect(
      PortOneConfig.kgInicisIdentityChannelKey,
      startsWith('channel-key-'),
    );
    expect(PortOneConfig.kgInicisIdentityChannelKey.trim(), isNotEmpty);
  });

  test('client configuration never contains the PortOne API Secret', () {
    final source = File(
      '$root/lib/config/portone_config.dart',
    ).readAsStringSync();
    expect(source, isNot(contains('PORTONE_API_SECRET')));
  });
}
