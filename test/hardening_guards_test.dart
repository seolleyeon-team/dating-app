import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/shared/utils/in_app_purchase_policy.dart';
import 'package:seolleyeon/shared/utils/safe_catch.dart';

enum _Sample { alpha, beta }

void main() {
  group('InAppPurchasePolicy', () {
    test('Google Play is enabled while unverified iOS remains gated', () {
      expect(InAppPurchasePolicy.enabled, isFalse);
      expect(
        InAppPurchasePolicy.allowPurchaseUiFor(
          isWeb: false,
          platform: TargetPlatform.android,
        ),
        isTrue,
      );
      expect(
        InAppPurchasePolicy.allowPurchaseUiFor(
          isWeb: false,
          platform: TargetPlatform.iOS,
        ),
        isFalse,
      );
      expect(
        InAppPurchasePolicy.allowPurchaseUiFor(
          isWeb: true,
          platform: TargetPlatform.android,
        ),
        isFalse,
      );
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

    test('Google Play unfinished purchases are explicitly recovered', () {
      final service = File(
        'lib/features/shop/services/iap_service.dart',
      ).readAsStringSync();
      final charge = File(
        'lib/features/profile/screens/heart_charge_screen.dart',
      ).readAsStringSync();
      expect(service.contains('_inAppPurchase.restorePurchases()'), isTrue);
      expect(service.contains('restorePendingPurchases()'), isTrue);
      expect(charge.contains('_iapService.restorePendingPurchases()'), isTrue);
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
