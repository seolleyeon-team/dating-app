import 'dart:convert';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../firebase_options.dart';
import '../router/route_names.dart';
import '../shared/layouts/main_scaffold_args.dart';
import 'navigation_service.dart';
import 'storage_service.dart';

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
}

class PushNotificationService {
  PushNotificationService._();
  static final PushNotificationService instance = PushNotificationService._();

  final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  final FlutterLocalNotificationsPlugin _local =
      FlutterLocalNotificationsPlugin();
  final FirebaseFirestore _firestore = FirebaseFirestore.instance;
  final StorageService _storage = StorageService();

  String? _openedChatRoomId;
  bool _isChatRoomVisible = false;

  static const AndroidNotificationChannel _chatChannel =
      AndroidNotificationChannel(
        'seolleyeon_high_importance',
        'Seolleyeon Notifications',
        description: '채팅 및 커뮤니티 알림',
        importance: Importance.max,
      );

  Future<void> initialize() async {
    await _requestPermission();
    await _initLocalNotifications();
    await syncFcmToken();

    FirebaseMessaging.onMessage.listen(_onForegroundMessage);
    FirebaseMessaging.onMessageOpenedApp.listen(_handleMessageTap);

    final initialMessage = await _messaging.getInitialMessage();
    if (initialMessage != null) {
      _handleMessageTap(initialMessage);
    }

    _messaging.onTokenRefresh.listen((_) async {
      await syncFcmToken();
    });
  }

  void setOpenedChatRoom(String roomId) {
    _openedChatRoomId = roomId;
    _isChatRoomVisible = true;
    debugPrint('[PUSH] opened chat room = $roomId');
  }

  void clearOpenedChatRoom(String roomId) {
    if (_openedChatRoomId == roomId) {
      debugPrint('[PUSH] cleared opened chat room = $roomId');
      _openedChatRoomId = null;
      _isChatRoomVisible = false;
    }
  }

  Future<void> _requestPermission() async {
    await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      provisional: false,
    );

    // iOS foreground 시스템 배너는 끄고,
    // 필요한 경우에만 _onForegroundMessage()에서 직접 local notification 표시
    await _messaging.setForegroundNotificationPresentationOptions(
      alert: false,
      badge: false,
      sound: false,
    );
  }

  Future<void> _initLocalNotifications() async {
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const ios = DarwinInitializationSettings();

    await _local.initialize(
      const InitializationSettings(android: android, iOS: ios),
      onDidReceiveNotificationResponse: (details) {
        final payload = details.payload;
        if (payload == null || payload.isEmpty) return;
        final data = jsonDecode(payload) as Map<String, dynamic>;
        _navigateFromData(data.map((k, v) => MapEntry(k, '$v')));
      },
    );

    await _local
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >()
        ?.createNotificationChannel(_chatChannel);
  }

  Future<void> syncFcmToken() async {
    try {
      final userId = await _storage.getKakaoUserId();
      debugPrint('[PUSH] stored kakaoUserId = $userId');

      final settings = await _messaging.getNotificationSettings();
      debugPrint('[PUSH] permission = ${settings.authorizationStatus}');

      final apnsToken = await _messaging.getAPNSToken();
      debugPrint('[PUSH] apnsToken = $apnsToken');

      final token = await _messaging.getToken();
      debugPrint('[PUSH] fcmToken = $token');

      if (userId == null || userId.isEmpty) {
        debugPrint('[PUSH] no userId, skip');
        return;
      }
      if (token == null || token.isEmpty) {
        debugPrint('[PUSH] no fcm token, skip');
        return;
      }

      await _firestore
          .collection('users')
          .doc(userId)
          .collection('deviceTokens')
          .doc(token)
          .set({
            'userId': userId,
            'token': token,
            'platform': defaultTargetPlatform.name,
            'updatedAt': FieldValue.serverTimestamp(),
          }, SetOptions(merge: true));

      debugPrint('[PUSH] token saved to firestore');
    } catch (e, st) {
      debugPrint('[PUSH] syncFcmToken error: $e');
      debugPrint('$st');
    }
  }

  Future<void> _onForegroundMessage(RemoteMessage message) async {
    final notification = message.notification;
    if (notification == null) return;

    final type = message.data['type']?.toString() ?? '';
    final roomId = message.data['roomId']?.toString() ?? '';

    final isSameOpenedChat =
        type == 'chat' &&
        _isChatRoomVisible &&
        _openedChatRoomId != null &&
        _openedChatRoomId == roomId;

    if (isSameOpenedChat) {
      debugPrint(
        '[PUSH] suppress foreground chat notification for room=$roomId',
      );
      return;
    }

    await _local.show(
      notification.hashCode,
      notification.title,
      notification.body,
      NotificationDetails(
        android: AndroidNotificationDetails(
          _chatChannel.id,
          _chatChannel.name,
          channelDescription: _chatChannel.description,
          importance: Importance.max,
          priority: Priority.high,
        ),
        iOS: const DarwinNotificationDetails(),
      ),
      payload: jsonEncode(message.data),
    );
  }

  void _handleMessageTap(RemoteMessage message) {
    final data = message.data.map((k, v) => MapEntry(k, '$v'));
    _navigateFromData(data);
  }

  void _navigateFromData(Map<String, String> data) {
    final nav = NavigationService.navigatorKey.currentState;
    if (nav == null) return;

    final type = data['type'] ?? '';

    if (type == 'chat' || type == 'chat_digest') {
      nav.pushNamedAndRemoveUntil(
        RouteNames.main,
        (route) => false,
        arguments: const MainScaffoldArgs(initialTabIndex: 1),
      );
      return;
    }

    if (type == 'community_comment' || type == 'community_reply') {
      final postId = data['postId'] ?? '';
      nav.pushNamedAndRemoveUntil(
        RouteNames.main,
        (route) => false,
        arguments: MainScaffoldArgs(
          initialTabIndex: 3,
          pendingRouteName: RouteNames.postDetail,
          pendingRouteArgs: postId,
        ),
      );
      return;
    }

    if (type == 'profile_like' || type == 'community_post_like') {
      nav.pushNamedAndRemoveUntil(
        RouteNames.main,
        (route) => false,
        arguments: const MainScaffoldArgs(initialTabIndex: 4),
      );
      Future.delayed(const Duration(milliseconds: 300), () {
        nav.pushNamed(RouteNames.receivedHearts);
      });
      return;
    }

    if (type == 'ask_received') {
      nav.pushNamedAndRemoveUntil(
        RouteNames.main,
        (route) => false,
        arguments: const MainScaffoldArgs(initialTabIndex: 4),
      );
      Future.delayed(const Duration(milliseconds: 300), () {
        nav.pushNamed(RouteNames.asksInbox);
      });
      return;
    }

    nav.pushNamed(RouteNames.notifications);
  }
}
