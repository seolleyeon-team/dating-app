import 'dart:convert';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../firebase_options.dart';
import '../router/route_names.dart';
import '../features/event/models/event_team_route_args.dart';
import '../features/event/meeting_icebreaker/domain/meeting_icebreaker_prompt.dart';
import '../features/event/meeting_icebreaker/services/meeting_icebreaker_deep_link_handler.dart';
import '../features/chat/models/safety_stamp_follow_up_args.dart';
import '../shared/layouts/main_scaffold_args.dart';
import '../shared/utils/privacy_log_utils.dart';
import 'navigation_service.dart';
import 'storage_service.dart';

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
}

class PushNotificationService {
  PushNotificationService._();
  static final PushNotificationService instance = PushNotificationService._();

  static const Map<String, bool> defaultNotificationSettings = {
    'all': true,
    'chat': true,
    'matching': true,
    'community': true,
    'asks': true,
    'events': true,
    'safety': true,
  };

  FirebaseMessaging? _messagingInstance;
  FirebaseFirestore? _firestoreInstance;
  final FlutterLocalNotificationsPlugin _local =
      FlutterLocalNotificationsPlugin();
  final StorageService _storage = StorageService();

  FirebaseMessaging get _messaging =>
      _messagingInstance ??= FirebaseMessaging.instance;
  FirebaseFirestore get _firestore =>
      _firestoreInstance ??= FirebaseFirestore.instance;

  String? _openedChatRoomId;
  bool _isChatRoomVisible = false;

  static const AndroidNotificationChannel _chatChannel =
      AndroidNotificationChannel(
        'seolleyeon_high_importance',
        'Seolleyeon Notifications',
        description: '채팅 및 커뮤니티 알림',
        importance: Importance.max,
      );

  /// 3:3 미팅 아이스브레이킹 룰렛 전용 조용한 채널.
  ///
  /// 알림 센터에는 문구가 남지만 소리·진동·강한 heads-up이 없다.
  /// 중요 채팅·안전 알림 채널(`seolleyeon_high_importance`)과 분리되어 있어
  /// 사용자가 이 안내만 따로 끌 수 있다.
  static const AndroidNotificationChannel _meetingIcebreakerQuietChannel =
      AndroidNotificationChannel(
        kMeetingIcebreakerQuietChannelId,
        kMeetingIcebreakerQuietChannelName,
        description: kMeetingIcebreakerQuietChannelDescription,
        importance: Importance.low,
        playSound: false,
        enableVibration: false,
        enableLights: false,
      );

  /// foreground에서 이미 표시한 알림 id (같은 알림 중복 표시 방지).
  final Set<String> _shownForegroundNotificationIds = <String>{};

  Future<void> initialize() async {
    try {
      Firebase.app();
    } catch (_) {
      debugPrint('[PUSH] Firebase is not initialized; skipping setup.');
      return;
    }

    if (kIsWeb) {
      debugPrint(
        '[PUSH] Web push service worker is not configured, skipping FCM init.',
      );
      return;
    }

    final notificationSettings = await loadUserNotificationSettings();
    if (notificationSettings['all'] != false) {
      await _requestPermission();
    }
    await _initLocalNotifications();
    await syncFcmToken(notificationSettings: notificationSettings);

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
    debugPrint('[PUSH] opened ${PrivacyLogUtils.idFingerprint(roomId)}');
  }

  void clearOpenedChatRoom(String roomId) {
    if (_openedChatRoomId == roomId) {
      debugPrint('[PUSH] cleared ${PrivacyLogUtils.idFingerprint(roomId)}');
      _openedChatRoomId = null;
      _isChatRoomVisible = false;
    }
  }

  Future<NotificationSettings> requestSystemPermission() async {
    final settings = await _messaging.requestPermission(
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

    return settings;
  }

  Future<NotificationSettings> getSystemNotificationSettings() {
    return _messaging.getNotificationSettings();
  }

  Future<void> _requestPermission() async {
    await requestSystemPermission();
  }

  Map<String, bool> normalizeNotificationSettings(dynamic raw) {
    final normalized = Map<String, bool>.from(defaultNotificationSettings);
    if (raw is Map) {
      for (final key in defaultNotificationSettings.keys) {
        final value = raw[key];
        if (value is bool) {
          normalized[key] = value;
        }
      }
    }
    return normalized;
  }

  Future<Map<String, bool>> loadUserNotificationSettings({
    String? userId,
  }) async {
    final resolvedUserId = userId ?? await _storage.getKakaoUserId();
    if (resolvedUserId == null || resolvedUserId.isEmpty) {
      return Map<String, bool>.from(defaultNotificationSettings);
    }

    final doc = await _firestore.collection('users').doc(resolvedUserId).get();
    return normalizeNotificationSettings(doc.data()?['notificationSettings']);
  }

  Future<void> saveUserNotificationSettings({
    String? userId,
    required Map<String, bool> settings,
  }) async {
    final resolvedUserId = userId ?? await _storage.getKakaoUserId();
    if (resolvedUserId == null || resolvedUserId.isEmpty) {
      throw StateError('사용자 정보를 찾을 수 없습니다.');
    }

    final normalized = normalizeNotificationSettings(settings);
    await _firestore.collection('users').doc(resolvedUserId).set({
      'notificationSettings': normalized,
      'notificationSettingsUpdatedAt': FieldValue.serverTimestamp(),
      'updatedAt': FieldValue.serverTimestamp(),
    }, SetOptions(merge: true));

    await syncFcmToken(notificationSettings: normalized);
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

    final androidPlugin = _local
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();
    await androidPlugin?.createNotificationChannel(_chatChannel);
    await androidPlugin?.createNotificationChannel(
      _meetingIcebreakerQuietChannel,
    );
  }

  Future<void> syncFcmToken({Map<String, bool>? notificationSettings}) async {
    try {
      if (kIsWeb) {
        debugPrint(
          '[PUSH] Web push service worker is not configured, skip token sync.',
        );
        return;
      }

      final userId = await _storage.getKakaoUserId();
      debugPrint('[PUSH] ${PrivacyLogUtils.idFingerprint(userId)}');

      final settings = await _messaging.getNotificationSettings();
      debugPrint('[PUSH] permission = ${settings.authorizationStatus}');
      final userNotificationSettings =
          notificationSettings ??
          await loadUserNotificationSettings(userId: userId);

      final apnsToken = await _messaging.getAPNSToken();
      debugPrint(
        '[PUSH] hasApnsToken=${apnsToken != null && apnsToken.isNotEmpty}',
      );

      final token = await _messaging.getToken();
      debugPrint('[PUSH] hasFcmToken=${token != null && token.isNotEmpty}');

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
            'notificationsEnabled': userNotificationSettings['all'] != false,
            'notificationSettings': userNotificationSettings,
            'updatedAt': FieldValue.serverTimestamp(),
          }, SetOptions(merge: true));

      debugPrint('[PUSH] token saved to firestore');
    } catch (e, st) {
      debugPrint('[PUSH] syncFcmToken ${PrivacyLogUtils.errorSummary(e)}');
      debugPrint('[PUSH] stackType=${st.runtimeType}');
    }
  }

  Future<void> _onForegroundMessage(RemoteMessage message) async {
    final notification = message.notification;
    if (notification == null) return;

    final type = message.data['type']?.toString() ?? '';
    final roomId = message.data['roomId']?.toString() ?? '';

    final notificationSettings = await loadUserNotificationSettings();
    if (!_isNotificationTypeEnabled(notificationSettings, type)) {
      debugPrint('[PUSH] suppress foreground notification by settings: $type');
      return;
    }

    final isSameOpenedChat =
        type == 'chat' &&
        _isChatRoomVisible &&
        _openedChatRoomId != null &&
        _openedChatRoomId == roomId;

    if (isSameOpenedChat) {
      debugPrint(
        '[PUSH] suppress foreground chat notification '
        '${PrivacyLogUtils.idFingerprint(roomId)}',
      );
      return;
    }

    // 같은 알림이 두 listener를 통해 두 번 표시되지 않게 한다.
    final dedupeId = message.data['notificationId']?.toString().trim() ?? '';
    if (dedupeId.isNotEmpty) {
      if (_shownForegroundNotificationIds.contains(dedupeId)) {
        debugPrint('[PUSH] suppress duplicate foreground notification');
        return;
      }
      _shownForegroundNotificationIds.add(dedupeId);
      if (_shownForegroundNotificationIds.length > 100) {
        _shownForegroundNotificationIds.remove(
          _shownForegroundNotificationIds.first,
        );
      }
    }

    final isQuiet = type == kMeetingIcebreakerNotificationType;

    await _local.show(
      notification.hashCode,
      notification.title,
      notification.body,
      NotificationDetails(
        android: isQuiet
            ? AndroidNotificationDetails(
                _meetingIcebreakerQuietChannel.id,
                _meetingIcebreakerQuietChannel.name,
                channelDescription: _meetingIcebreakerQuietChannel.description,
                importance: Importance.low,
                priority: Priority.low,
                playSound: false,
                enableVibration: false,
                enableLights: false,
                onlyAlertOnce: true,
                // 같은 미팅의 안내가 알림 센터에 쌓이지 않게 교체한다.
                tag: message.data['sessionId']?.toString(),
              )
            : AndroidNotificationDetails(
                _chatChannel.id,
                _chatChannel.name,
                channelDescription: _chatChannel.description,
                importance: Importance.max,
                priority: Priority.high,
              ),
        iOS: isQuiet
            ? const DarwinNotificationDetails(
                presentSound: false,
                presentBadge: false,
                interruptionLevel: InterruptionLevel.passive,
              )
            : const DarwinNotificationDetails(),
      ),
      payload: jsonEncode(message.data),
    );
  }

  bool _isNotificationTypeEnabled(Map<String, bool> settings, String type) {
    if (settings['all'] == false) return false;
    final category = _categoryForPushType(type);
    if (category == null) return true;
    return settings[category] != false;
  }

  String? _categoryForPushType(String type) {
    switch (type) {
      case 'chat':
      case 'chat_digest':
        return 'chat';
      case 'profile_like':
        return 'matching';
      case 'community_post_like':
      case 'community_comment':
      case 'community_reply':
        return 'community';
      case 'ask_received':
        return 'asks';
      case 'event_team_invite':
        return 'events';
      case kMeetingIcebreakerNotificationType:
        return 'events';
      case 'safety_stamp_follow_up':
        return 'safety';
      default:
        // 서버(functions/src/shared/notify.ts)와 같은 규칙:
        // 블라인드 취향 미팅 알림은 이벤트 카테고리를 따른다.
        if (type.startsWith('blind_meeting_')) return 'events';
        return null;
    }
  }

  void _handleMessageTap(RemoteMessage message) {
    final data = message.data.map((k, v) => MapEntry(k, '$v'));
    _navigateFromData(data);
  }

  void _navigateFromData(Map<String, String> data) {
    final nav = NavigationService.navigatorKey.currentState;
    if (nav == null) return;

    final type = data['type'] ?? '';

    // 3:3 미팅 아이스브레이킹 룰렛.
    //
    // 화면 이동 대신 단일 coordinator가 처리한다.
    // onMessage / onMessageOpenedApp / getInitialMessage 가 같은 알림을
    // 각각 넘겨도 룰렛이 두 번 열리지 않는다.
    if (type == kMeetingIcebreakerNotificationType) {
      MeetingIcebreakerDeepLinkHandler.instance.handleNotificationData(data);
      return;
    }

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

    if (type == 'event_team_invite') {
      final inviteId = data['inviteId'] ?? '';
      if (inviteId.isEmpty) {
        nav.pushNamed(RouteNames.notifications);
        return;
      }
      nav.pushNamed(
        RouteNames.eventTeamInviteResponse,
        arguments: EventTeamInviteResponseArgs(inviteId: inviteId),
      );
      return;
    }

    if (type == 'safety_stamp_follow_up') {
      final roomId = data['roomId'] ?? '';
      final promiseId = data['promiseId'] ?? '';
      if (roomId.isEmpty || promiseId.isEmpty) {
        nav.pushNamed(RouteNames.notifications);
        return;
      }
      nav.pushNamedAndRemoveUntil(
        RouteNames.main,
        (route) => false,
        arguments: MainScaffoldArgs(
          initialTabIndex: 1,
          pendingRouteName: RouteNames.safetyStampFollowUp,
          pendingRouteArgs: SafetyStampFollowUpArgs(
            roomId: roomId,
            promiseId: promiseId,
          ),
        ),
      );
      return;
    }

    nav.pushNamed(RouteNames.notifications);
  }
}
