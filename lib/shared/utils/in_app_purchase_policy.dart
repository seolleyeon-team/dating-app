import 'package:flutter/foundation.dart';

/// Android heart purchases use Google Play Billing in production.
///
/// Apple production receipt verification is intentionally still gated behind
/// `--dart-define=ENABLE_IN_APP_PURCHASE=true` until the App Store verifier is
/// implemented. This prevents enabling an unverified iOS purchase path while
/// allowing the production-ready Google Play path without a fragile build flag.
class InAppPurchasePolicy {
  const InAppPurchasePolicy._();

  static const bool enabled = bool.fromEnvironment(
    'ENABLE_IN_APP_PURCHASE',
    defaultValue: false,
  );

  static bool allowPurchaseUiFor({
    required bool isWeb,
    required TargetPlatform platform,
  }) {
    if (isWeb) return false;
    if (platform == TargetPlatform.android) return true;
    return platform == TargetPlatform.iOS && enabled;
  }

  /// Android is enabled by default; iOS remains explicitly gated.
  static bool get allowPurchaseUi =>
      allowPurchaseUiFor(isWeb: kIsWeb, platform: defaultTargetPlatform);

  static String get unavailableMessage => '현재 사용 중인 플랫폼에서는 하트 결제를 이용할 수 없어요.';
}
