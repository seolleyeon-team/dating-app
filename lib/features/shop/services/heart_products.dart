/// StoreKit/App Store Connect와 Google Play에서 공유하는 하트 상품입니다.
/// 가격·제목·설명은 각 스토어의 [ProductDetails]만 사용하며 앱에 저장하지 않습니다.
enum HeartPurchasePlatform { ios, android }

class HeartProduct {
  final String iosProductId;
  final String androidProductId;
  final int hearts;

  const HeartProduct({
    required this.iosProductId,
    required this.androidProductId,
    required this.hearts,
  });

  String productIdFor(HeartPurchasePlatform platform) => switch (platform) {
    HeartPurchasePlatform.ios => iosProductId,
    HeartPurchasePlatform.android => androidProductId,
  };
}

abstract final class HeartProducts {
  static const heart10ProductId = 'seolleyeon.heart.10';
  static const heart30ProductId = 'seolleyeon.heart.30';
  static const heart100ProductId = 'seolleyeon.heart.100';

  // Google Play product ID도 현재는 iOS ID와 동일하다. Play Console 규칙상
  // 달라져야 할 경우 이 mapping만 변경하면 UI/지급 로직은 그대로 유지된다.
  static const heart10 = HeartProduct(
    iosProductId: heart10ProductId,
    androidProductId: heart10ProductId,
    hearts: 10,
  );
  static const heart30 = HeartProduct(
    iosProductId: heart30ProductId,
    androidProductId: heart30ProductId,
    hearts: 30,
  );
  static const heart100 = HeartProduct(
    iosProductId: heart100ProductId,
    androidProductId: heart100ProductId,
    hearts: 100,
  );

  static const all = <HeartProduct>[heart10, heart30, heart100];

  // Google Play first launch exposes only the 10-heart consumable. The iOS
  // catalog is kept intact for StoreKit local testing, but production iOS
  // purchases remain gated by InAppPurchasePolicy.
  static const googlePlayLaunchProducts = <HeartProduct>[heart10];

  static List<HeartProduct> productsFor(HeartPurchasePlatform platform) =>
      platform == HeartPurchasePlatform.android
      ? googlePlayLaunchProducts
      : all;

  static Set<String> productIdsFor(HeartPurchasePlatform platform) =>
      productsFor(
        platform,
      ).map((product) => product.productIdFor(platform)).toSet();

  static HeartProduct? fromProductId(
    String productId, {
    required HeartPurchasePlatform platform,
  }) {
    for (final product in productsFor(platform)) {
      if (product.productIdFor(platform) == productId) return product;
    }
    return null;
  }
}
