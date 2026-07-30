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
  });

  group('enumByNameOrNull', () {
    test('returns matching enum and null for unknown', () {
      expect(enumByNameOrNull(_Sample.values, 'alpha'), _Sample.alpha);
      expect(enumByNameOrNull(_Sample.values, 'missing'), isNull);
      expect(enumByNameOrNull(_Sample.values, null), isNull);
    });
  });
}
