import 'dart:convert';
import 'dart:io';
import 'api_endpoints.dart';
import '../error/exceptions.dart';

/// API 클라이언트 (기본 HttpClient 사용)
class ApiClient {
  final HttpClient _client;
  String? _authToken;

  ApiClient({HttpClient? client}) : _client = client ?? HttpClient();

  /// 인증 토큰 설정
  void setAuthToken(String token) {
    _authToken = token;
  }

  /// 인증 토큰 제거
  void clearAuthToken() {
    _authToken = null;
  }

  /// 기본 헤더
  Map<String, String> get _headers {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
    if (_authToken != null) {
      headers['Authorization'] = 'Bearer $_authToken';
    }
    return headers;
  }

  /// GET 요청
  Future<Map<String, dynamic>> get(String endpoint) async {
    try {
      final request = await _client.getUrl(
        Uri.parse('${ApiEndpoints.baseUrl}$endpoint'),
      );
      _headers.forEach((key, value) => request.headers.set(key, value));
      final response = await request.close();
      return await _handleResponse(response);
    } on SocketException {
      throw NetworkException('네트워크 연결을 확인해주세요.');
    }
  }

  /// POST 요청
  Future<Map<String, dynamic>> post(
    String endpoint, {
    Map<String, dynamic>? body,
  }) async {
    try {
      final request = await _client.postUrl(
        Uri.parse('${ApiEndpoints.baseUrl}$endpoint'),
      );
      _headers.forEach((key, value) => request.headers.set(key, value));
      if (body != null) {
        request.write(jsonEncode(body));
      }
      final response = await request.close();
      return await _handleResponse(response);
    } on SocketException {
      throw NetworkException('네트워크 연결을 확인해주세요.');
    }
  }

  /// PUT 요청
  Future<Map<String, dynamic>> put(
    String endpoint, {
    Map<String, dynamic>? body,
  }) async {
    try {
      final request = await _client.putUrl(
        Uri.parse('${ApiEndpoints.baseUrl}$endpoint'),
      );
      _headers.forEach((key, value) => request.headers.set(key, value));
      if (body != null) {
        request.write(jsonEncode(body));
      }
      final response = await request.close();
      return await _handleResponse(response);
    } on SocketException {
      throw NetworkException('네트워크 연결을 확인해주세요.');
    }
  }

  /// DELETE 요청
  Future<Map<String, dynamic>> delete(String endpoint) async {
    try {
      final request = await _client.deleteUrl(
        Uri.parse('${ApiEndpoints.baseUrl}$endpoint'),
      );
      _headers.forEach((key, value) => request.headers.set(key, value));
      final response = await request.close();
      return await _handleResponse(response);
    } on SocketException {
      throw NetworkException('네트워크 연결을 확인해주세요.');
    }
  }

  /// 응답 처리
  Future<Map<String, dynamic>> _handleResponse(
    HttpClientResponse response,
  ) async {
    final bodyBytes = await response.fold<List<int>>(
      [],
      (previous, element) => previous..addAll(element),
    );
    final bodyString = utf8.decode(bodyBytes);
    final body = jsonDecode(bodyString) as Map<String, dynamic>;

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return body;
    } else if (response.statusCode == 401) {
      throw UnauthorizedException('인증이 필요합니다.');
    } else if (response.statusCode == 403) {
      throw ForbiddenException('접근 권한이 없습니다.');
    } else if (response.statusCode == 404) {
      throw NotFoundException('리소스를 찾을 수 없습니다.');
    } else if (response.statusCode >= 500) {
      throw ServerException('서버 오류가 발생했습니다.');
    } else {
      throw ApiException(body['message'] as String? ?? '알 수 없는 오류가 발생했습니다.');
    }
  }

  /// 리소스 해제
  void dispose() {
    _client.close();
  }
}
