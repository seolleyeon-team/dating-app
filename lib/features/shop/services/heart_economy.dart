/// 서버와 함께 관리하는 설레연 하트 사용료.
abstract final class HeartFeatureCosts {
  static const int directChat = 10;
  static const int blindMeeting = 30;
  static const int seasonRoulette = 20;
  static const int recommendationRefresh = 5;

  /// The user-facing cost format used at every paid-feature entry point.
  static String label(int amount) => '❤️$amount';
}
