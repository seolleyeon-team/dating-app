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
}
