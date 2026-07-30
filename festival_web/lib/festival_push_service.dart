import 'dart:js_interop';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

import 'push_config.dart';
import 'pwa_detect.dart';

@JS('festivalRequestPushToken')
external JSPromise<JSString> _festivalRequestPushToken(
  String vapidKey,
  bool shouldRequestPermission,
);

@JS('festivalGetNotificationPermission')
external JSString _festivalGetNotificationPermission();

@pragma('vm:entry-point')
Future<void> festivalFirebaseMessagingBackgroundHandler(
  RemoteMessage message,
) async {
  debugPrint('[FESTIVAL_PUSH] background message: ${message.messageId}');
}

class FestivalPushService {
  FestivalPushService._();

  static final FestivalPushService instance = FestivalPushService._();

  final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  final FirebaseFirestore _db = FirebaseFirestore.instance;
  final FirebaseAuth _auth = FirebaseAuth.instance;

  String? _openedChatRoomId;
  bool _initialized = false;

  bool get canRequestPush {
    if (!kIsWeb) return false;
    if (isIosWebBrowser && !isInstalledWebApp) return false;
    return true;
  }

  Future<AuthorizationStatus?> currentAuthorizationStatus() async {
    if (!kIsWeb) return null;
    try {
      final permission = _festivalGetNotificationPermission().toDart;
      return switch (permission) {
        'granted' => AuthorizationStatus.authorized,
        'denied' => AuthorizationStatus.denied,
        'default' => AuthorizationStatus.notDetermined,
        _ => AuthorizationStatus.notDetermined,
      };
    } catch (_) {
      return null;
    }
  }

  String? get iosHomeScreenHint {
    if (!kIsWeb) return null;
    if (isIosWebBrowser && !isInstalledWebApp) {
      return 'iPhone에서는 Safari 공유 버튼 → 홈 화면에 추가한 뒤, 추가된 설레연 앱에서 알림을 켜주세요.';
    }
    return null;
  }

  Future<void> initializeSafely() async {
    try {
      await initialize();
    } catch (error, stackTrace) {
      debugPrint('[FESTIVAL_PUSH] initialize failed: $error');
      debugPrint('$stackTrace');
    }
  }

  Future<void> initialize() async {
    if (!kIsWeb || _initialized) return;
    _initialized = true;

    try {
      FirebaseMessaging.onBackgroundMessage(
        festivalFirebaseMessagingBackgroundHandler,
      );
    } catch (error) {
      debugPrint('[FESTIVAL_PUSH] background handler unavailable: $error');
    }

    try {
      FirebaseMessaging.onMessage.listen(_onForegroundMessage);
      FirebaseMessaging.onMessageOpenedApp.listen(_onMessageOpenedApp);
    } catch (error) {
      debugPrint('[FESTIVAL_PUSH] foreground listeners unavailable: $error');
    }

    try {
      final initialMessage = await _messaging.getInitialMessage();
      if (initialMessage != null) {
        _onMessageOpenedApp(initialMessage);
      }
    } catch (error) {
      debugPrint('[FESTIVAL_PUSH] initial message unavailable: $error');
    }

    try {
      _messaging.onTokenRefresh.listen((_) => syncTokenSafely());
    } catch (error) {
      debugPrint('[FESTIVAL_PUSH] token refresh listener unavailable: $error');
    }

    if (FestivalPushAuthBridge.hasActiveSession()) {
      await syncTokenSafely(requestPermissionIfNeeded: false);
    }
  }

  void setOpenedChatRoom(String? roomId) {
    _openedChatRoomId = roomId;
  }

  Future<FestivalPushResult> requestPermissionAndSyncDetailed() async {
    if (!kIsWeb) {
      return const FestivalPushResult.failure(
        code: 'not-web',
        message: '웹 환경이 아니라서 브라우저 푸시를 등록할 수 없어요.',
      );
    }

    final hint = iosHomeScreenHint;
    if (hint != null) {
      debugPrint('[FESTIVAL_PUSH] blocked on iOS browser: $hint');
      return FestivalPushResult.failure(
        code: 'ios-browser-not-installed',
        message: hint,
      );
    }

    return syncTokenDetailed(requestPermissionIfNeeded: true);
  }

  Future<bool> requestPermissionAndSync() async {
    final result = await requestPermissionAndSyncDetailed();
    return result.success;
  }

  Future<bool> syncTokenSafely({bool requestPermissionIfNeeded = false}) async {
    final result = await syncTokenSafelyDetailed(
      requestPermissionIfNeeded: requestPermissionIfNeeded,
    );
    return result.success;
  }

  Future<FestivalPushResult> syncTokenSafelyDetailed({
    bool requestPermissionIfNeeded = false,
  }) async {
    try {
      return syncTokenDetailed(
        requestPermissionIfNeeded: requestPermissionIfNeeded,
      );
    } catch (error, stackTrace) {
      debugPrint('[FESTIVAL_PUSH] syncToken outer failure: $error');
      debugPrint('$stackTrace');
      return FestivalPushResult.failure(
        code: _errorCode(error, fallback: 'sync-token-outer-failed'),
        message: '푸시 토큰 등록 중 예상하지 못한 오류가 났어요.',
        detail: _errorDetail(error),
      );
    }
  }

  Future<bool> syncToken({bool requestPermissionIfNeeded = false}) async {
    final result = await syncTokenDetailed(
      requestPermissionIfNeeded: requestPermissionIfNeeded,
    );
    return result.success;
  }

  Future<FestivalPushResult> syncTokenDetailed({
    bool requestPermissionIfNeeded = false,
  }) async {
    if (!kIsWeb) {
      return const FestivalPushResult.failure(
        code: 'not-web',
        message: '웹 환경이 아니라서 브라우저 푸시를 등록할 수 없어요.',
      );
    }

    final user = _auth.currentUser;
    if (user == null || user.uid.isEmpty) {
      return const FestivalPushResult.failure(
        code: 'no-auth-user',
        message: 'Firebase 로그인 세션이 아직 준비되지 않았어요.',
      );
    }

    if (!FestivalPushAuthBridge.hasActiveSession()) {
      return const FestivalPushResult.failure(
        code: 'no-active-entry-session',
        message: '입장 코드 세션이 없어서 푸시 토큰을 저장하지 않았어요.',
      );
    }

    if (isIosWebBrowser && !isInstalledWebApp) {
      return FestivalPushResult.failure(
        code: 'ios-browser-not-installed',
        message: iosHomeScreenHint ?? 'iPhone에서는 홈 화면 웹앱에서만 알림을 켤 수 있어요.',
      );
    }

    String? token;
    try {
      token = (await _festivalRequestPushToken(
        kFestivalWebVapidKey,
        requestPermissionIfNeeded,
      ).toDart).toDart;
    } catch (error, stackTrace) {
      debugPrint('[FESTIVAL_PUSH] getToken failed: $error');
      debugPrint('$stackTrace');
      return FestivalPushResult.failure(
        code: _errorCode(error, fallback: 'get-token-failed'),
        message: 'FCM 토큰을 브라우저에서 발급받지 못했어요.',
        detail: _errorDetail(error),
      );
    }

    if (token.isEmpty) {
      debugPrint('[FESTIVAL_PUSH] empty token');
      return const FestivalPushResult.failure(
        code: 'empty-token',
        message: 'FCM이 빈 토큰을 반환했어요.',
      );
    }

    try {
      await _db
          .collection('festivalPushTokens')
          .doc(user.uid)
          .collection('tokens')
          .doc(token)
          .set({
            'uid': user.uid,
            'token': token,
            'platform': 'web',
            'isPwa': isInstalledWebApp,
            'userAgent': defaultTargetPlatform.name,
            'notificationsEnabled': true,
            'updatedAt': FieldValue.serverTimestamp(),
          }, SetOptions(merge: true));

      debugPrint('[FESTIVAL_PUSH] token saved for uid=${user.uid}');
      return FestivalPushResult.success(token: token);
    } catch (error, stackTrace) {
      debugPrint('[FESTIVAL_PUSH] save token failed: $error');
      debugPrint('$stackTrace');
      return FestivalPushResult.failure(
        code: _errorCode(error, fallback: 'save-token-failed'),
        message: 'FCM 토큰은 발급됐지만 Firestore 저장에 실패했어요.',
        detail: _errorDetail(error),
      );
    }
  }

  String _errorCode(Object error, {required String fallback}) {
    if (error is FirebaseException) {
      return '${error.plugin}/${error.code}';
    }
    return fallback;
  }

  String _errorDetail(Object error) {
    if (error is FirebaseException) {
      final message = error.message;
      if (message == null || message.isEmpty) {
        return error.toString();
      }
      return message;
    }
    return error.toString();
  }

  Future<void> disableCurrentToken() async {
    if (!kIsWeb) return;
    final user = _auth.currentUser;
    if (user == null) return;

    try {
      final token = await _messaging.getToken(vapidKey: kFestivalWebVapidKey);
      if (token != null && token.isNotEmpty) {
        await _db
            .collection('festivalPushTokens')
            .doc(user.uid)
            .collection('tokens')
            .doc(token)
            .set({
              'notificationsEnabled': false,
              'updatedAt': FieldValue.serverTimestamp(),
            }, SetOptions(merge: true));
      }
      await _messaging.deleteToken();
    } catch (error) {
      debugPrint('[FESTIVAL_PUSH] disableCurrentToken failed: $error');
    }
  }

  void _onForegroundMessage(RemoteMessage message) {
    final type = message.data['type']?.toString() ?? '';
    final roomId = message.data['roomId']?.toString() ?? '';
    if (type == 'festival_chat' &&
        _openedChatRoomId != null &&
        _openedChatRoomId == roomId) {
      debugPrint('[FESTIVAL_PUSH] suppress foreground chat push for open room');
    }
  }

  void _onMessageOpenedApp(RemoteMessage message) {
    final roomId = message.data['roomId']?.toString();
    if (roomId == null || roomId.isEmpty) return;
    FestivalPushNavigationBridge.openChatRoom?.call(roomId);
  }
}

/// main.dart에서 세션 상태를 주입하기 위한 브리지 (순환 import 방지).
class FestivalPushAuthBridge {
  static bool Function() hasActiveSession = () => false;
}

class FestivalPushNavigationBridge {
  static void Function(String roomId)? openChatRoom;
}

class FestivalPushResult {
  const FestivalPushResult._({
    required this.success,
    required this.code,
    required this.message,
    this.detail,
    this.token,
  });

  const FestivalPushResult.success({required String token})
    : this._(
        success: true,
        code: 'ok',
        message: '새 채팅 알림을 받을 준비가 됐어요.',
        token: token,
      );

  const FestivalPushResult.failure({
    required String code,
    required String message,
    String? detail,
  }) : this._(success: false, code: code, message: message, detail: detail);

  final bool success;
  final String code;
  final String message;
  final String? detail;
  final String? token;

  String get debugMessage {
    if (success) return message;
    final parts = <String>[message, '원인: $code'];
    if (detail != null && detail!.isNotEmpty) {
      parts.add(detail!);
    }
    return parts.join('\n');
  }
}
