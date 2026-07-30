import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/utils/in_app_purchase_policy.dart';
import 'package:seolleyeon/shared/utils/safe_catch.dart';

enum _Sample { alpha, beta }

void main() {
  group('InAppPurchasePolicy', () {
    test('purchases are disabled by default', () {
      expect(InAppPurchasePolicy.enabled, isFalse);
      expect(InAppPurchasePolicy.allowPurchaseUi, isFalse);
      expect(InAppPurchasePolicy.unavailableMessage, contains('준비'));
    });

    test('heart recharge screens refuse purchases unless policy enabled', () {
      final recharge = File(
        'lib/features/shop/screens/heart_recharge_screen.dart',
      ).readAsStringSync();
      final charge = File(
        'lib/features/profile/screens/heart_charge_screen.dart',
      ).readAsStringSync();
      expect(recharge.contains('InAppPurchasePolicy.allowPurchaseUi'), isTrue);
      expect(charge.contains('InAppPurchasePolicy.allowPurchaseUi'), isTrue);
      expect(
        recharge.contains('InAppPurchasePolicy.unavailableMessage'),
        isTrue,
      );
      expect(charge.contains('InAppPurchasePolicy.unavailableMessage'), isTrue);
    });
  });

  group('enumByNameOrNull', () {
    test('returns matching enum and null for unknown', () {
      expect(enumByNameOrNull(_Sample.values, 'alpha'), _Sample.alpha);
      expect(enumByNameOrNull(_Sample.values, 'missing'), isNull);
      expect(enumByNameOrNull(_Sample.values, null), isNull);
    });
  });
}
