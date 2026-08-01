import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

/// Legacy placeholder HTTP client. Not wired into production flows.
/// Release construction is blocked so a forgotten import cannot hit
/// `api.example.com` or silently send unauthenticated traffic.
class ApiService {
  late final Dio _dio;
  static const String baseUrl = 'https://api.example.com';

  ApiService() {
    if (kReleaseMode) {
      throw UnsupportedError(
        'ApiService is a legacy placeholder and must not be used in release.',
      );
    }
    _dio = Dio(
      BaseOptions(
        baseUrl: baseUrl,
        connectTimeout: const Duration(seconds: 30),
        receiveTimeout: const Duration(seconds: 30),
        headers: {'Content-Type': 'application/json'},
      ),
    );

    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) {
          return handler.next(options);
        },
        onError: (error, handler) {
          return handler.next(error);
        },
      ),
    );
  }

  Future<Response> get(
    String path, {
    Map<String, dynamic>? queryParameters,
  }) async {
    try {
      return await _dio.get(path, queryParameters: queryParameters);
    } catch (e) {
      throw Exception('GET request failed: $e');
    }
  }

  Future<Response> post(String path, {dynamic data}) async {
    try {
      return await _dio.post(path, data: data);
    } catch (e) {
      throw Exception('POST request failed: $e');
    }
  }

  Future<Response> put(String path, {dynamic data}) async {
    try {
      return await _dio.put(path, data: data);
    } catch (e) {
      throw Exception('PUT request failed: $e');
    }
  }

  Future<Response> delete(String path) async {
    try {
      return await _dio.delete(path);
    } catch (e) {
      throw Exception('DELETE request failed: $e');
    }
  }
}
