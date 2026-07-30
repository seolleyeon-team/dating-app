import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// Legacy Dio wrapper. Production traffic uses Firebase SDKs, not this client.
///
/// Instantiating against `api.example.com` in release is a hard error so a
/// forgotten import cannot ship placeholder networking.
class ApiService {
  late final Dio _dio;

  static const String _placeholderBaseUrl = 'https://api.example.com';

  /// Override only for explicit local experiments.
  static const String baseUrl = String.fromEnvironment(
    'LEGACY_API_BASE_URL',
    defaultValue: _placeholderBaseUrl,
  );

  ApiService() {
    if (kReleaseMode &&
        (baseUrl.contains('api.example.com') || baseUrl.trim().isEmpty)) {
      throw UnsupportedError(
        'ApiService placeholder base URL is blocked in release. '
        'Use Firebase clients or pass --dart-define=LEGACY_API_BASE_URL=...',
      );
    }
    _dio = Dio(
      BaseOptions(
        baseUrl: baseUrl,
        connectTimeout: const Duration(seconds: 30),
        receiveTimeout: const Duration(seconds: 30),
        headers: {
          'Content-Type': 'application/json',
        },
      ),
    );

    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) => handler.next(options),
        onError: (error, handler) => handler.next(error),
      ),
    );
  }

  Dio get dio => _dio;

  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) {
    return _dio.get<T>(path, queryParameters: queryParameters);
  }

  Future<Response<T>> post<T>(String path, {dynamic data}) {
    return _dio.post<T>(path, data: data);
  }
}
