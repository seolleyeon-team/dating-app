import 'dart:async';

/// Kakao SDK는 Android MethodChannel에 로그인 결과 슬롯을 하나만 유지하므로
/// 앱 전체에서 Kakao OAuth를 한 번에 하나만 실행하도록 조정합니다.
class KakaoLoginCoordinator {
  KakaoLoginCoordinator._();

  static Future<Map<String, dynamic>>? _inFlight;

  /// 이미 로그인 중이면 새 SDK 호출을 만들지 않고 진행 중인 Future를 공유합니다.
  static Future<Map<String, dynamic>> run(
    Future<Map<String, dynamic>> Function() operation,
  ) {
    final active = _inFlight;
    if (active != null) return active;

    final future = Future<Map<String, dynamic>>.sync(operation);
    _inFlight = future;
    future.then<void>(
      (_) => _clearIfCurrent(future),
      onError: (Object _, StackTrace __) => _clearIfCurrent(future),
    );
    return future;
  }

  static void _clearIfCurrent(Future<Map<String, dynamic>> completed) {
    if (identical(_inFlight, completed)) {
      _inFlight = null;
    }
  }
}
