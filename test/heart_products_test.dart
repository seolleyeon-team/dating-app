import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/shop/services/heart_products.dart';

void main() {
  test('iOS and Android expose the same five heart products', () {
    expect(
      HeartProducts.productIdsFor(HeartPurchasePlatform.android),
      HeartProducts.productIdsFor(HeartPurchasePlatform.ios),
    );
    expect(HeartProducts.all.map((product) => product.hearts), <int>[
      50,
      20,
      40,
      100,
      220,
    ]);
  });

  test('first purchase product is marked as an account-limited offer', () {
    expect(HeartProducts.firstHeart50.isFirstPurchaseOffer, isTrue);
    expect(HeartProducts.firstHeart50.hearts, 50);
    expect(
      HeartProducts.all.where((product) => product.isFirstPurchaseOffer),
      hasLength(1),
    );
  });

  test(
    '50-heart offer visibility depends only on whether that offer was used',
    () {
      final screenSource = File(
        'lib/features/profile/screens/heart_charge_screen.dart',
      ).readAsStringSync();

      expect(screenSource, contains("data?['firstPurchaseOfferUsed'] != true"));
      expect(screenSource, isNot(contains("data?['iapPurchaseCount']")));
    },
  );

  test('Korean UI prices match the configured StoreKit catalog', () {
    expect(HeartProducts.all.map((product) => product.priceWon), <int>[
      6900,
      3900,
      6900,
      14900,
      29900,
    ]);
  });

  test('rejects empty or zero-priced store product details', () {
    expect(
      HeartProducts.hasValidPaidStorePrice(
        rawPrice: 3900,
        formattedPrice: '₩3,900',
      ),
      isTrue,
    );
    expect(
      HeartProducts.hasValidPaidStorePrice(rawPrice: 0, formattedPrice: '₩0'),
      isFalse,
    );
    expect(
      HeartProducts.hasValidPaidStorePrice(rawPrice: 3900, formattedPrice: ''),
      isFalse,
    );
  });

  test(
    'local Korean StoreKit catalog matches the five paid heart products',
    () {
      final raw =
          jsonDecode(
                File('ios/Runner/Configuration.storekit').readAsStringSync(),
              )
              as Map<String, dynamic>;
      final products = (raw['products'] as List<dynamic>)
          .cast<Map<String, dynamic>>();
      final productById = <String, Map<String, dynamic>>{
        for (final product in products) product['productID'] as String: product,
      };

      expect(
        productById.keys.toSet(),
        HeartProducts.productIdsFor(HeartPurchasePlatform.ios),
      );
      for (final product in productById.values) {
        expect(product['currency'], 'KRW');
        expect(
          product['price'],
          isA<num>().having((price) => price, 'price', greaterThan(0)),
        );
        expect((product['displayPrice'] as String).trim(), isNotEmpty);
      }
    },
  );
}
