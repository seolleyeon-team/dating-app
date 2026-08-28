import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/shop/services/heart_products.dart';

void main() {
  test('Google Play launch catalog exposes only the 10-heart product', () {
    expect(HeartProducts.productIdsFor(HeartPurchasePlatform.android), <String>{
      'seolleyeon.heart.10',
    });
    expect(
      HeartProducts.fromProductId(
        'seolleyeon.heart.30',
        platform: HeartPurchasePlatform.android,
      ),
      isNull,
    );
  });

  test('StoreKit local catalog remains available for existing iOS testing', () {
    expect(HeartProducts.all.map((product) => product.hearts), <int>[
      10,
      30,
      100,
    ]);
  });
}
