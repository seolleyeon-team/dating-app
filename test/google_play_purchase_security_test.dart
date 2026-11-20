import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/shop/services/heart_purchase_gateway.dart';
import 'package:seolleyeon/features/shop/services/heart_products.dart';

void main() {
  test('Google Play account id is the server-compatible user id hash', () {
    const userId = 'canonical-app-user-123';
    expect(
      googlePlayAccountIdForUserId(userId),
      sha256.convert(utf8.encode(userId)).toString(),
    );
  });

  test(
    '50H eligibility is independent from purchases of all other products',
    () {
      final ordinaryProducts = HeartProducts.all.where(
        (product) => !product.isFirstPurchaseOffer,
      );

      expect(ordinaryProducts, hasLength(4));
      expect(
        ordinaryProducts.every(
          (product) =>
              product.productIdFor(HeartPurchasePlatform.android) !=
              HeartProducts.firstHeart50ProductId,
        ),
        isTrue,
      );
      expect(HeartProducts.firstHeart50.isFirstPurchaseOffer, isTrue);
    },
  );

  test('Android hides 50H until its dedicated eligibility flag is loaded', () {
    final source = File(
      'lib/features/profile/screens/heart_charge_screen.dart',
    ).readAsStringSync();

    expect(source, contains('_iapService.supportsGooglePlayIap'));
    expect(source, contains('snapshot.hasData'));
    expect(source, contains("data['firstPurchaseOfferUsed'] != true"));
    expect(source, isNot(contains("data['iapPurchaseCount']")));
  });

  test('Android displays the localized Google Play product price', () {
    final source = File(
      'lib/features/profile/screens/heart_charge_screen.dart',
    ).readAsStringSync();

    // 스토어가 준 localized price 를 그대로 쓴다. 클라이언트가 원화 금액을
    // 직접 포맷해 보여 주는 경로가 다시 생기면 안 된다.
    expect(source, contains('displayPrice: details.price'));
    expect(source, isNot(contains('NumberFormat.currency')));
  });
}
