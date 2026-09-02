import 'package:flutter/foundation.dart';

/// Digital hearts are sold through the platform's native purchase system.
///
/// iOS uses StoreKit and Android uses Google Play Billing. Both paths verify
/// the transaction with the server before the app grants any hearts.
class InAppPurchasePolicy {
  const InAppPurchasePolicy._();

  /// Kept as a named policy value for UI callers and test coverage.
  static const bool enabled = true;

  static bool allowPurchaseUiFor({
    required bool isWeb,
    required TargetPlatform platform,
  }) {
    if (isWeb) return false;
    return platform == TargetPlatform.android || platform == TargetPlatform.iOS;
  }

  /// Native iOS and Android builds support StoreKit or Play Billing.
  static bool get allowPurchaseUi =>
      allowPurchaseUiFor(isWeb: kIsWeb, platform: defaultTargetPlatform);

  static String get unavailableMessage => '현재 사용 중인 플랫폼에서는 하트 결제를 이용할 수 없어요.';
}
