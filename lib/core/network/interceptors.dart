/// HTTP 인터셉터 (로깅, 인증 등)
///
/// 이 파일은 향후 dio 등의 HTTP 클라이언트로 전환 시 사용됩니다.
/// 현재는 기본 HttpClient를 사용하므로 스텁으로 제공됩니다.
library;

abstract class Interceptor {
  /// 요청 전 처리
  Future<void> onRequest(Map<String, dynamic> request);

  /// 응답 후 처리
  Future<void> onResponse(Map<String, dynamic> response);

  /// 에러 처리
  Future<void> onError(Object error);
}

/// 로깅 인터셉터
class LoggingInterceptor implements Interceptor {
  @override
  Future<void> onRequest(Map<String, dynamic> request) async {
    // ignore: avoid_print
    print('[API Request] ${request['method']} ${request['url']}');
  }

  @override
  Future<void> onResponse(Map<String, dynamic> response) async {
    // ignore: avoid_print
    print('[API Response] ${response['statusCode']}');
  }

  @override
  Future<void> onError(Object error) async {
    // ignore: avoid_print
    print('[API Error] $error');
  }
}

/// 인증 토큰 갱신 인터셉터
class AuthInterceptor implements Interceptor {
  @override
  Future<void> onRequest(Map<String, dynamic> request) async {
    // TODO: 토큰 추가 로직
  }

  @override
  Future<void> onResponse(Map<String, dynamic> response) async {
    // TODO: 토큰 갱신 로직
  }

  @override
  Future<void> onError(Object error) async {
    // TODO: 401 에러 시 토큰 갱신 로직
  }
}
