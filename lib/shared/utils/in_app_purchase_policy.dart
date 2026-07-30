/// In-app purchase / heart recharge is not production-ready until a real
/// billing provider is wired and store review assets exist.
///
/// Enable locally with:
/// `--dart-define=ENABLE_IN_APP_PURCHASE=true`
class InAppPurchasePolicy {
  const InAppPurchasePolicy._();

  static const bool enabled = bool.fromEnvironment(
    'ENABLE_IN_APP_PURCHASE',
    defaultValue: false,
  );

  /// Store/release builds must not complete a fake purchase.
  static bool get allowPurchaseUi => enabled;

  static String get unavailableMessage =>
      '하트 충전 결제는 아직 준비 중입니다.\n스토어 배포 전에 결제 연동이 완료됩니다.';
}
