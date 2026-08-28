import 'dart:convert';

import 'package:cloud_functions/cloud_functions.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';

import '../../../services/auth_service.dart';
import '../../../services/firebase_runtime.dart';
import '../../../services/storage_service.dart';
import 'heart_products.dart';

class HeartGrantResult {
  final bool granted;
  final bool alreadyGranted;
  final int heartBalance;

  const HeartGrantResult({
    required this.granted,
    required this.alreadyGranted,
    required this.heartBalance,
  });
}

/// 서버의 신뢰 경로로 StoreKit transaction을 전송합니다.
/// heartAmount·가격·성공 여부는 절대로 클라이언트에서 전송하지 않습니다.
class HeartPurchaseGateway {
  HeartPurchaseGateway({
    FirebaseFunctions? functions,
    AuthService? authService,
    StorageService? storageService,
  }) : _functions =
           functions ??
           FirebaseFunctions.instanceFor(region: firebaseFunctionsRegion),
       _authService = authService ?? AuthService(),
       _storageService = storageService ?? StorageService();

  final FirebaseFunctions _functions;
  final AuthService _authService;
  final StorageService _storageService;

  /// Prepares the authenticated app account before opening Google Play's
  /// purchase sheet and returns a non-reversible account identifier.
  Future<String> prepareGooglePlayAccountId() async {
    final kakaoUserId = await _prepareAuthenticatedUserId();
    return sha256.convert(utf8.encode(kakaoUserId)).toString();
  }

  Future<HeartGrantResult> grantPurchasedHearts({
    required String productId,
    required HeartPurchasePlatform platform,
    required String transactionId,
    required String verificationData,
    required String verificationSource,
    required String? purchaseDate,
  }) async {
    _debugLog(
      '[${platform.name.toUpperCase()}] preparing authenticated heart grant '
      'product=$productId',
    );
    await _prepareAuthenticatedUserId();
    _debugLog(
      '[${platform.name.toUpperCase()}] authenticated; requesting server grant',
    );
    final dynamic response;
    try {
      response = await _functions
          .httpsCallable('grantPurchasedHearts')
          .call(<String, dynamic>{
            'productId': productId,
            'platform': platform.name,
            'transactionId': transactionId,
            'verificationData': verificationData,
            'verificationSource': verificationSource,
            if (purchaseDate != null) 'purchaseDate': purchaseDate,
          });
    } on FirebaseFunctionsException catch (error) {
      _debugLog(
        '[${platform.name.toUpperCase()}] server grant failed '
        'code=${error.code} message=${error.message ?? ''}',
      );
      rethrow;
    }

    final raw = response.data;
    if (raw is! Map) {
      throw StateError('하트 지급 서버의 응답 형식이 올바르지 않아요.');
    }
    final data = Map<String, dynamic>.from(raw);
    final balance = (data['heartBalance'] as num?)?.toInt();
    if (balance == null) {
      throw StateError('하트 잔액을 확인하지 못했어요.');
    }

    final result = HeartGrantResult(
      granted: data['granted'] == true,
      alreadyGranted: data['alreadyGranted'] == true,
      heartBalance: balance,
    );
    _debugLog(
      '[${platform.name.toUpperCase()}] server grant confirmed '
      'granted=${result.granted} alreadyGranted=${result.alreadyGranted} '
      'balance=${result.heartBalance}',
    );
    return result;
  }

  Future<String> _prepareAuthenticatedUserId() async {
    final kakaoUserId = await _storageService.getKakaoUserId();
    if (kakaoUserId == null || kakaoUserId.isEmpty) {
      throw StateError('로그인 정보를 찾을 수 없어요. 다시 로그인해주세요.');
    }

    // Callable은 request.auth를 기준으로 사용자 문서를 결정한다. SharedPreferences
    // user id를 서버에 보내거나 권한 판단에 사용하지 않는다.
    final isSessionReady = await _authService.ensureFirebaseSessionForKakao(
      kakaoUserId,
    );
    if (!isSessionReady) {
      throw StateError('구매 정보를 저장할 로그인 세션을 준비하지 못했어요.');
    }
    return kakaoUserId;
  }

  void _debugLog(String message) {
    if (kDebugMode) debugPrint('[IAP] $message');
  }
}
