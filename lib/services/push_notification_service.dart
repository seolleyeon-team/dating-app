import 'dart:async';
import 'dart:convert';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter/widgets.dart';

import '../firebase_options.dart';
import '../router/route_names.dart';
import '../features/event/models/event_team_route_args.dart';
import '../features/event/meeting_icebreaker/domain/meeting_icebreaker_prompt.dart';
import '../features/event/meeting_icebreaker/services/meeting_icebreaker_deep_link_handler.dart';
import '../features/blind_meeting/presentation/blind_meeting_route_args.dart';
import '../features/chat/models/safety_stamp_follow_up_args.dart';
import '../shared/layouts/main_scaffold_args.dart';
import '../shared/utils/privacy_log_utils.dart';
import 'account_setup_flow.dart';
import 'navigation_service.dart';
import 'storage_service.dart';

@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
}

/// Test seam over the platform side of push set-up (FirebaseMessaging's
/// static streams and instance calls, the local-notification plugin, and the
/// Firestore reads/writes). Production never sets it.
@visibleForTesting
class PushPlatformHooks {
  PushPlatformHooks({
    required this.onMessage,
    required this.onMessageOpenedApp,
    required this.onTokenRefresh,
    required this.getInitialMessage,
    required this.requestPermission,
    required this.authorizationStatus,
    required this.initLocalNotifications,
    required this.loadSettings,
    required this.syncToken,
    required this.openMessage,
  });

  final Stream<RemoteMessage> onMessage;
  final Stream<RemoteMessage> onMessageOpenedApp;
  final Stream<String> onTokenRefresh;
  final Future<RemoteMessage?> Function() getInitialMessage;
  final Future<AuthorizationStatus> Function() requestPermission;
  final Future<AuthorizationStatus> Function() authorizationStatus;
  final Future<void> Function() initLocalNotifications;
  final Future<Map<String, bool>> Function() loadSettings;

  /// Returns whether the token registration is settled (see
  /// [PushNotificationService.syncFcmToken]).
  final Future<bool> Function() syncToken;
  final void Function(RemoteMessage message) openMessage;
}

class PushNotificationService with WidgetsBindingObserver {
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
  bool _isChatListVisible = false;
  bool _isAppForeground = true;
  Timer? _deliveryContextHeartbeat;
  bool _initialized = false;
  bool _initializing = false;
  final Set<String> _handledOpenKeys = <String>{};

  // --- set-up state (AUD-16) -------------------------------------------------
  // Listeners are attached once per process and independently of the awaited
  // set-up below, so a failed step can no longer leave the whole session
  // without message / tap / token-refresh handling.
  bool _listenersAttached = false;
  final List<StreamSubscription<Object?>> _listenerSubscriptions = [];
  bool _localNotificationsReady = false;
  bool _permissionStepDone = false;
  bool _initialMessageChecked = false;
  bool _tokenSyncSettled = false;
  AuthorizationStatus? _lastAuthorizationStatus;
  Timer? _setupRetryTimer;
  int _setupRetryAttempt = 0;
  PushPlatformHooks? _hooks;

  /// Delays between automatic set-up retries. The list length is the budget;
  /// after it is spent only an app resume retries.
  @visibleForTesting
  static const List<Duration> setupRetryDelays = [
    Duration(seconds: 5),
    Duration(seconds: 30),
    Duration(minutes: 2),
  ];

  /// True once every set-up step has succeeded.
  @visibleForTesting
  bool get isSetupComplete => _initialized;

  @visibleForTesting
  bool get listenersAttached => _listenersAttached;

  /// Builds a stable deep-link dedupe key for open/tap handling.
  @visibleForTesting
  static String buildOpenDedupeKey(
    Map<String, String> data, {
    String? messageId,
  }) {
    final type = data['type'] ?? '';
    final roomId = data['roomId'] ?? '';
    final postId = data['postId'] ?? '';
    final inviteId = data['inviteId'] ?? '';
    final promiseId = data['promiseId'] ?? '';
    final mid = (messageId ?? data['messageId'] ?? '').trim();
    return [mid, type, roomId, postId, inviteId, promiseId].join('|');
  }

  /// Returns true once per key; subsequent identical opens are suppressed.
  @visibleForTesting
  bool claimOpenHandling(String dedupeKey) {
    if (dedupeKey.isEmpty || dedupeKey == '||||||') {
      return true;
    }
    if (_handledOpenKeys.contains(dedupeKey)) {
      return false;
    }
    _handledOpenKeys.add(dedupeKey);
    return true;
  }

  @visibleForTesting
  void resetForTest({PushPlatformHooks? hooks}) {
    _hooks = hooks;
    for (final subscription in _listenerSubscriptions) {
      subscription.cancel();
    }
    _listenerSubscriptions.clear();
    if (_listenersAttached) {
      WidgetsBinding.instance.removeObserver(this);
    }
    _listenersAttached = false;
    _localNotificationsReady = false;
    _permissionStepDone = false;
    _initialMessageChecked = false;
    _tokenSyncSettled = false;
    _lastAuthorizationStatus = null;
    _setupRetryTimer?.cancel();
    _setupRetryTimer = null;
    _setupRetryAttempt = 0;
    _initialized = false;
    _initializing = false;
    _handledOpenKeys.clear();
    _openedChatRoomId = null;
    _isChatRoomVisible = false;
    _isChatListVisible = false;
    _isAppForeground = true;
    _deliveryContextHeartbeat?.cancel();
    _deliveryContextHeartbeat = null;
  }

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

  bool _isFirebaseReady() {
    if (_hooks != null) return true;
    try {
      Firebase.app();
      return true;
    } catch (_) {
      return false;
    }
  }

  /// Starts push handling. Safe to call any number of times.
  ///
  /// Order matters (AUD-16): the message / tap / token-refresh listeners are
  /// attached FIRST and synchronously. The awaited set-up (settings read,
  /// permission prompt, local-notification channels, token registration,
  /// launch notification) used to run before them, so one failing step - a
  /// Firestore read while offline was enough - left the whole session without
  /// listeners. Each step now fails on its own and is retried.
  Future<void> initialize() async {
    if (_initialized || _initializing) {
      debugPrint('[PUSH] initialize skipped; listeners already attached');
      return;
    }

    if (!_isFirebaseReady()) {
      debugPrint('[PUSH] Firebase is not initialized; skipping setup.');
      return;
    }

    if (kIsWeb && _hooks == null) {
      debugPrint(
        '[PUSH] Web push service worker is not configured, skipping FCM init.',
      );
      return;
    }

    _initializing = true;
    try {
      _attachListeners();
      if (await _runSetup()) {
        _initialized = true;
        _setupRetryAttempt = 0;
      } else {
        _scheduleSetupRetry();
      }
    } finally {
      _initializing = false;
    }
  }

  /// Attached exactly once per process: a retry, a logout / login or an
  /// account switch never adds a second subscription.
  void _attachListeners() {
    if (_listenersAttached) return;
    _listenersAttached = true;

    final hooks = _hooks;
    WidgetsBinding.instance.addObserver(this);
    _listenerSubscriptions.add(
      (hooks?.onMessage ?? FirebaseMessaging.onMessage).listen((message) {
        unawaited(_onForegroundMessageGuarded(message));
      }),
    );
    _listenerSubscriptions.add(
      (hooks?.onMessageOpenedApp ?? FirebaseMessaging.onMessageOpenedApp)
          .listen(_handleMessageTap),
    );
    _listenerSubscriptions.add(
      (hooks?.onTokenRefresh ?? _messaging.onTokenRefresh).listen((_) {
        unawaited(syncFcmToken());
      }),
    );
    if (hooks == null) {
      _startDeliveryContextHeartbeat();
    }
  }

  Future<void> _onForegroundMessageGuarded(RemoteMessage message) async {
    try {
      await _onForegroundMessage(message);
    } catch (e) {
      debugPrint(
        '[PUSH] foreground message ${PrivacyLogUtils.errorSummary(e)}',
      );
    }
  }

  /// Runs every set-up step that has not succeeded yet. A failing step never
  /// stops the following ones. Returns whether set-up is complete.
  Future<bool> _runSetup() async {
    final hooks = _hooks;

    // Unknown settings (offline, signed out) fall back to the defaults for
    // the permission decision only; they are never written anywhere.
    Map<String, bool>? notificationSettings;
    try {
      notificationSettings = hooks != null
          ? await hooks.loadSettings()
          : await loadUserNotificationSettings();
    } catch (e) {
      debugPrint('[PUSH] settings load ${PrivacyLogUtils.errorSummary(e)}');
    }

    if (!_localNotificationsReady) {
      try {
        if (hooks != null) {
          await hooks.initLocalNotifications();
        } else {
          await _initLocalNotifications();
        }
        _localNotificationsReady = true;
      } catch (e) {
        debugPrint(
          '[PUSH] local notifications ${PrivacyLogUtils.errorSummary(e)}',
        );
      }
    }

    if (!_permissionStepDone) {
      if ((notificationSettings ?? defaultNotificationSettings)['all'] ==
          false) {
        // The user turned every notification off: no system prompt.
        _permissionStepDone = true;
      } else {
        try {
          _lastAuthorizationStatus = hooks != null
              ? await hooks.requestPermission()
              : (await requestSystemPermission()).authorizationStatus;
          _permissionStepDone = true;
        } catch (e) {
          debugPrint('[PUSH] permission ${PrivacyLogUtils.errorSummary(e)}');
        }
      }
    }

    // A denied permission does not stop the registration: the token is
    // stored either way, so delivery starts the moment the user grants it.
    final tokenSettled = await syncFcmToken(
      notificationSettings: notificationSettings,
    );

    if (!_initialMessageChecked) {
      try {
        final initialMessage = hooks != null
            ? await hooks.getInitialMessage()
            : await _messaging.getInitialMessage();
        _initialMessageChecked = true;
        if (initialMessage != null) {
          _handleMessageTap(initialMessage);
        }
      } catch (e) {
        debugPrint('[PUSH] initial message ${PrivacyLogUtils.errorSummary(e)}');
      }
    }

    return _localNotificationsReady &&
        _permissionStepDone &&
        tokenSettled &&
        _initialMessageChecked;
  }

  void _scheduleSetupRetry() {
    if (_setupRetryAttempt >= setupRetryDelays.length) {
      debugPrint('[PUSH] setup retry budget exhausted; waiting for resume');
      return;
    }
    final delay = setupRetryDelays[_setupRetryAttempt];
    _setupRetryAttempt += 1;
    _setupRetryTimer?.cancel();
    _setupRetryTimer = Timer(delay, () {
      _setupRetryTimer = null;
      unawaited(initialize());
    });
  }

  /// App resume: finish an incomplete set-up, and pick up a notification
  /// permission the user changed in the system settings meanwhile.
  Future<void> _recoverOnResume() async {
    if (!_listenersAttached) return;
    if (!_initialized) {
      _setupRetryTimer?.cancel();
      _setupRetryTimer = null;
      _setupRetryAttempt = 0;
      await initialize();
      return;
    }
    try {
      final hooks = _hooks;
      final status = hooks != null
          ? await hooks.authorizationStatus()
          : (await _messaging.getNotificationSettings()).authorizationStatus;
      final previous = _lastAuthorizationStatus;
      _lastAuthorizationStatus = status;
      if ((previous != null && previous != status) || !_tokenSyncSettled) {
        debugPrint('[PUSH] permission = $status; refreshing registration');
        await syncFcmToken();
      }
    } catch (e) {
      debugPrint('[PUSH] resume check ${PrivacyLogUtils.errorSummary(e)}');
    }
  }

  void setOpenedChatRoom(String roomId) {
    if (roomId.isEmpty) return;
    _isChatListVisible = false;
    _openedChatRoomId = roomId;
    _isChatRoomVisible = true;
    unawaited(_syncDeliveryContext());
    debugPrint('[PUSH] opened ${PrivacyLogUtils.idFingerprint(roomId)}');
  }

  void clearOpenedChatRoom(String roomId) {
    if (_openedChatRoomId == roomId) {
      debugPrint('[PUSH] cleared ${PrivacyLogUtils.idFingerprint(roomId)}');
      _openedChatRoomId = null;
      _isChatRoomVisible = false;
      unawaited(_syncDeliveryContext());
    }
  }

  /// Marks the chat-list screen as visible for this device.
  ///
  /// The server uses this short-lived state to avoid a redundant chat banner
  /// while the user is already looking at the conversation list.
  void setChatListVisible(bool visible) {
    if (_isChatListVisible == visible &&
        !(visible && (_isChatRoomVisible || _openedChatRoomId != null))) {
      return;
    }
    _isChatListVisible = visible;
    if (visible) {
      _openedChatRoomId = null;
      _isChatRoomVisible = false;
    }
    unawaited(_syncDeliveryContext());
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final foreground = state == AppLifecycleState.resumed;
    if (_isAppForeground == foreground) return;
    _isAppForeground = foreground;
    if (foreground) {
      unawaited(_recoverOnResume());
    }
    unawaited(_syncDeliveryContext());
  }

  void _startDeliveryContextHeartbeat() {
    _deliveryContextHeartbeat?.cancel();
    _deliveryContextHeartbeat = Timer.periodic(const Duration(seconds: 45), (
      _,
    ) {
      if (_isAppForeground) {
        unawaited(_syncDeliveryContext());
      }
    });
  }

  Map<String, Object?> _deliveryContext() {
    final screen = !_isAppForeground
        ? 'background'
        : _isChatListVisible
        ? 'chat_list'
        : _isChatRoomVisible && _openedChatRoomId != null
        ? 'chat_room'
        : 'other';
    return {
      'appState': _isAppForeground ? 'foreground' : 'background',
      'screen': screen,
      'chatRoomId': screen == 'chat_room' ? _openedChatRoomId : null,
      'updatedAt': FieldValue.serverTimestamp(),
    };
  }

  Future<void> _syncDeliveryContext() async {
    if (kIsWeb) return;
    try {
      final userId = await _storage.getKakaoUserId();
      if (userId == null || userId.isEmpty) return;
      final token = await _messaging.getToken();
      if (token == null || token.isEmpty) return;
      await _firestore
          .collection('users')
          .doc(userId)
          .collection('deviceTokens')
          .doc(token)
          .set({
            'deliveryContext': _deliveryContext(),
          }, SetOptions(merge: true));
    } catch (e) {
      debugPrint(
        '[PUSH] delivery context sync ${PrivacyLogUtils.errorSummary(e)}',
      );
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

  /// Registers this device's FCM token under the signed-in account.
  ///
  /// Never throws. Returns `true` when there is nothing left to do (saved, or
  /// nobody is signed in, or the account never receives pushes) and `false`
  /// when the registration is still owed (no token yet, or a failure): the
  /// set-up retry and the next app resume try again.
  Future<bool> syncFcmToken({Map<String, bool>? notificationSettings}) async {
    final hooks = _hooks;
    if (hooks != null) {
      try {
        final settled = await hooks.syncToken();
        _tokenSyncSettled = settled;
        return settled;
      } catch (_) {
        _tokenSyncSettled = false;
        return false;
      }
    }
    try {
      if (kIsWeb) {
        debugPrint(
          '[PUSH] Web push service worker is not configured, skip token sync.',
        );
        _tokenSyncSettled = true;
        return true;
      }

      final userId = await _storage.getKakaoUserId();
      debugPrint('[PUSH] ${PrivacyLogUtils.idFingerprint(userId)}');
      if (userId == 'play-reviewer-v1') {
        // Review fixtures never receive device tokens. Synthetic chat and
        // interaction traffic must stay entirely outside FCM delivery.
        debugPrint('[PUSH] Play review session, skip token sync.');
        _tokenSyncSettled = true;
        return true;
      }

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
        _tokenSyncSettled = true;
        return true;
      }
      if (token == null || token.isEmpty) {
        debugPrint('[PUSH] no fcm token, skip');
        _tokenSyncSettled = false;
        return false;
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
            'deliveryContext': _deliveryContext(),
            'updatedAt': FieldValue.serverTimestamp(),
          }, SetOptions(merge: true));

      debugPrint('[PUSH] token saved to firestore');
      _tokenSyncSettled = true;
      return true;
    } catch (e, st) {
      debugPrint('[PUSH] syncFcmToken ${PrivacyLogUtils.errorSummary(e)}');
      debugPrint('[PUSH] stackType=${st.runtimeType}');
      _tokenSyncSettled = false;
      return false;
    }
  }

  /// Removes this device's push association with the signed-in account.
  ///
  /// Called BEFORE Firebase sign-out (P1-3). A shared device must not keep
  /// delivering the previous account's private notifications to the next
  /// account. Two independent steps, each bounded so an offline logout never
  /// hangs:
  ///   1. delete `users/{uid}/deviceTokens/{token}` (the client-side claim);
  ///   2. `deleteToken()` rotates the FCM token, so even if step 1 failed
  ///      (offline) the registered token becomes undeliverable and the server
  ///      drops it on the next send. The next sign-in registers a fresh token
  ///      under the new account and the server-side ownership registry
  ///      transfers it.
  /// Failures are logged (privacy-safe) and never block the logout.
  Future<void> unregisterCurrentDevice({String? userId}) async {
    if (kIsWeb) return;
    try {
      Firebase.app();
    } catch (_) {
      return;
    }
    const timeout = Duration(seconds: 5);
    final uid = (userId ?? await _storage.getKakaoUserId())?.trim() ?? '';
    String? token;
    try {
      token = await _messaging.getToken().timeout(timeout);
    } catch (e) {
      debugPrint(
        '[PUSH] unregister getToken ${PrivacyLogUtils.errorSummary(e)}',
      );
    }
    if (uid.isNotEmpty && token != null && token.isNotEmpty) {
      try {
        await _firestore
            .collection('users')
            .doc(uid)
            .collection('deviceTokens')
            .doc(token)
            .delete()
            .timeout(timeout);
        debugPrint(
          '[PUSH] device registration removed for '
          '${PrivacyLogUtils.idFingerprint(uid)}',
        );
      } catch (e) {
        debugPrint(
          '[PUSH] unregister delete ${PrivacyLogUtils.errorSummary(e)}',
        );
      }
    }
    try {
      await _messaging.deleteToken().timeout(timeout);
      debugPrint('[PUSH] fcm token rotated on logout');
    } catch (e) {
      debugPrint(
        '[PUSH] unregister deleteToken ${PrivacyLogUtils.errorSummary(e)}',
      );
    }
    _openedChatRoomId = null;
    _isChatRoomVisible = false;
    _isChatListVisible = false;
  }

  Future<void> _onForegroundMessage(RemoteMessage message) async {
    final notification = message.notification;
    if (notification == null) return;

    final type = message.data['type']?.toString() ?? '';
    final roomId = message.data['roomId']?.toString() ?? '';

    Map<String, bool> notificationSettings;
    try {
      notificationSettings = await loadUserNotificationSettings();
    } catch (e) {
      // Unknown settings (offline): show rather than silently drop.
      debugPrint(
        '[PUSH] settings unavailable for foreground message: '
        '${PrivacyLogUtils.errorSummary(e)}',
      );
      notificationSettings = Map<String, bool>.from(
        defaultNotificationSettings,
      );
    }
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
      case 'promise_reminder':
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
    final key = buildOpenDedupeKey(data, messageId: message.messageId);
    if (!claimOpenHandling(key)) {
      debugPrint('[PUSH] suppress duplicate open/tap');
      return;
    }
    final hooks = _hooks;
    if (hooks != null) {
      hooks.openMessage(message);
      return;
    }
    _navigateFromData(data);
  }

  /// Notification taps must not jump past the account-setup ladder
  /// (terms-gate contract §8, finding F11): the old code pushed
  /// `RouteNames.main` unconditionally, so a tap on a stale notification put
  /// an un-onboarded — or un-consented — account straight onto the home tab.
  void _navigateFromData(Map<String, String> data) {
    unawaited(_navigateFromDataGuarded(data));
  }

  Future<void> _navigateFromDataGuarded(Map<String, String> data) async {
    if (NavigationService.navigatorKey.currentState == null) return;

    final gateRoute = await _resolveSetupGateRoute();
    final nav = NavigationService.navigatorKey.currentState;
    if (nav == null) return;

    if (gateRoute != null) {
      nav.pushNamedAndRemoveUntil(gateRoute, (route) => false);
      return;
    }

    _routeNotificationTarget(nav, data);
  }

  /// Returns the prerequisite route when the setup ladder is incomplete, and
  /// `null` when the account is `complete` (so in-app deep-link targets keep
  /// working). On an unexpected failure it returns the terms route: the
  /// ladder itself already fails closed internally, so reaching here means
  /// the gate state is unknown and a deep link must not be honoured.
  Future<String?> _resolveSetupGateRoute() async {
    try {
      final route = await AccountSetupFlow().resolveNextRoute();
      return route == RouteNames.main ? null : route;
    } catch (e) {
      debugPrint(
        '[PUSH] setup gate resolve failed: ${PrivacyLogUtils.errorSummary(e)}',
      );
      return RouteNames.terms;
    }
  }

  void _routeNotificationTarget(NavigatorState nav, Map<String, String> data) {
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

    if (type == 'chat' || type == 'chat_digest' || type == 'promise_reminder') {
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

    // 3:3 블라인드 취향 미팅.
    //
    // 알림 종류가 18가지라 type 이 아니라 서버가 함께 보내는 deeplinkType 으로
    // 라우팅한다. 알림에 담긴 단계(예: "수락해주세요")가 이미 지났더라도
    // 결과 화면이 서버 상태를 실시간으로 읽어 현재 단계를 보여준다.
    final deeplinkType = data['deeplinkType'] ?? '';
    if (deeplinkType == 'blind_meeting_party') {
      nav.pushNamed(RouteNames.blindTasteMeetingParty);
      return;
    }
    // 대체 참가 제안은 예외다. 제안을 받은 사람은 아직 그 미팅의 참가자가
    // 아니라서 미팅 문서를 읽을 수 없다 (rules 상 participantIds 기준).
    // 전용 화면이 생기기 전까지는 알림함으로 보낸다.
    final isReplacementOffer = type == 'blind_meeting_replacement_offer';
    if (!isReplacementOffer &&
        (deeplinkType == 'blind_meeting' ||
            deeplinkType == 'blind_meeting_follow_up')) {
      final meetingId = data['meetingId'] ?? '';
      if (meetingId.isEmpty) {
        // 미팅 id 가 없으면 진입 화면이 신청 상태로 알아서 복구한다.
        nav.pushNamed(RouteNames.blindTasteMeeting);
        return;
      }
      nav.pushNamed(
        deeplinkType == 'blind_meeting_follow_up'
            ? RouteNames.blindTasteMeetingFollowUp
            : RouteNames.blindTasteMeetingResult,
        arguments: BlindMeetingMeetingArgs(meetingId: meetingId),
      );
      return;
    }

    // 단체 채팅방으로 보내는 미팅 알림 (약속 투표, 채팅방 개설 등).
    if (deeplinkType == 'chat' && type.startsWith('blind_meeting_')) {
      nav.pushNamedAndRemoveUntil(
        RouteNames.main,
        (route) => false,
        arguments: const MainScaffoldArgs(initialTabIndex: 1),
      );
      return;
    }

    // Older notifications may not include a deeplinkType.  They still lead
    // safely to the blind-meeting entry screen instead of doing nothing.
    if (type.startsWith('blind_meeting_')) {
      nav.pushNamed(
        type.startsWith('blind_meeting_party_')
            ? RouteNames.blindTasteMeetingParty
            : RouteNames.blindTasteMeeting,
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
