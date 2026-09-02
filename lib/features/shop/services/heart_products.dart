/// StoreKit/App Store Connect와 Google Play에서 공유하는 하트 상품입니다.
/// [priceWon]은 한국 스토어에 설정한 화면 표시용 가격입니다. 실제 결제와
/// 영수증 검증은 계속 플랫폼의 [ProductDetails]와 서버 검증을 사용합니다.
enum HeartPurchasePlatform { ios, android }

class HeartProduct {
  final String iosProductId;
  final String androidProductId;
  final int hearts;
  final int priceWon;
  final String displayName;
  final bool isFirstPurchaseOffer;

  const HeartProduct({
    required this.iosProductId,
    required this.androidProductId,
    required this.hearts,
    required this.priceWon,
    required this.displayName,
    this.isFirstPurchaseOffer = false,
  });

  String productIdFor(HeartPurchasePlatform platform) => switch (platform) {
    HeartPurchasePlatform.ios => iosProductId,
    HeartPurchasePlatform.android => androidProductId,
  };
}

abstract final class HeartProducts {
  static const heart20ProductId = 'seolleyeon.heart.20';
  static const heart40ProductId = 'seolleyeon.heart.40';
  static const heart100ProductId = 'seolleyeon.heart.100';
  static const heart220ProductId = 'seolleyeon.heart.220';
  static const firstHeart50ProductId = 'seolleyeon.heart.first.50';

  // Google Play product ID도 현재는 iOS ID와 동일하다. Play Console 규칙상
  // 달라져야 할 경우 이 mapping만 변경하면 UI/지급 로직은 그대로 유지된다.
  static const heart20 = HeartProduct(
    iosProductId: heart20ProductId,
    androidProductId: heart20ProductId,
    hearts: 20,
    priceWon: 3900,
    displayName: '가볍게',
  );
  static const heart40 = HeartProduct(
    iosProductId: heart40ProductId,
    androidProductId: heart40ProductId,
    hearts: 40,
    priceWon: 6900,
    displayName: '핵심',
  );
  static const heart100 = HeartProduct(
    iosProductId: heart100ProductId,
    androidProductId: heart100ProductId,
    hearts: 100,
    priceWon: 14900,
    displayName: '활동',
  );
  static const heart220 = HeartProduct(
    iosProductId: heart220ProductId,
    androidProductId: heart220ProductId,
    hearts: 220,
    priceWon: 29900,
    displayName: '학기',
  );
  static const firstHeart50 = HeartProduct(
    iosProductId: firstHeart50ProductId,
    androidProductId: firstHeart50ProductId,
    hearts: 50,
    priceWon: 6900,
    displayName: '첫 결제 특별 상품',
    isFirstPurchaseOffer: true,
  );

  static const all = <HeartProduct>[
    firstHeart50,
    heart20,
    heart40,
    heart100,
    heart220,
  ];

  static List<HeartProduct> productsFor(HeartPurchasePlatform platform) => all;

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

  /// StoreKit/Play Billing이 제공한 가격만 화면에 표시한다.
  /// 하트는 유료 소모품이므로 0원·음수·비어 있는 표시 가격은 출시 빌드에서
  /// 판매 가능한 상품으로 취급하지 않는다.
  static bool hasValidPaidStorePrice({
    required double rawPrice,
    required String formattedPrice,
  }) {
    return rawPrice.isFinite &&
        rawPrice > 0 &&
        formattedPrice.trim().isNotEmpty;
  }
}
