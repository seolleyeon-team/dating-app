import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/services/push_notification_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

// AUD-16 (push half): listeners are attached independently of the awaited
// set-up, set-up steps fail on their own and are retried within a budget,
// and nothing is ever subscribed twice.

class _PushHarness {
  final onMessage = StreamController<RemoteMessage>.broadcast(sync: true);
  final onOpened = StreamController<RemoteMessage>.broadcast(sync: true);
  final onTokenRefresh = StreamController<String>.broadcast(sync: true);

  Map<String, bool> settings = Map<String, bool>.from(
    PushNotificationService.defaultNotificationSettings,
  );
  Object? settingsError;
  Object? localNotificationsError;
  Object? permissionError;
  Object? initialMessageError;
  Object? syncError;
  bool tokenSettled = true;
  AuthorizationStatus permission = AuthorizationStatus.authorized;
  RemoteMessage? initialMessage;

  int settingsLoads = 0;
  int localNotificationInits = 0;
  int permissionRequests = 0;
  int syncCalls = 0;
  int initialMessageReads = 0;
  final List<RemoteMessage> opened = [];

  PushPlatformHooks get hooks => PushPlatformHooks(
    onMessage: onMessage.stream,
    onMessageOpenedApp: onOpened.stream,
    onTokenRefresh: onTokenRefresh.stream,
    getInitialMessage: () async {
      initialMessageReads += 1;
      final error = initialMessageError;
      if (error != null) throw error;
      return initialMessage;
    },
    requestPermission: () async {
      permissionRequests += 1;
      final error = permissionError;
      if (error != null) throw error;
      return permission;
    },
    authorizationStatus: () async => permission,
    initLocalNotifications: () async {
      localNotificationInits += 1;
      final error = localNotificationsError;
      if (error != null) throw error;
    },
    loadSettings: () async {
      settingsLoads += 1;
      final error = settingsError;
      if (error != null) throw error;
      return settings;
    },
    syncToken: () async {
      syncCalls += 1;
      final error = syncError;
      if (error != null) throw error;
      return tokenSettled;
    },
    openMessage: opened.add,
  );

  bool get allListenersAttached =>
      onMessage.hasListener &&
      onOpened.hasListener &&
      onTokenRefresh.hasListener;
}

RemoteMessage _tap(String id) => RemoteMessage(
  messageId: id,
  data: {'type': 'chat', 'roomId': 'room-$id', 'messageId': id},
);

Future<void> _settle(WidgetTester tester, [Duration? advance]) async {
  if (advance != null) await tester.pump(advance);
  // `pump()` without a duration does not fire zero-delay timers.
  for (var i = 0; i < 6; i++) {
    await tester.pump(Duration.zero);
  }
}

void _resume(PushNotificationService service) {
  service.didChangeAppLifecycleState(AppLifecycleState.paused);
  service.didChangeAppLifecycleState(AppLifecycleState.resumed);
}

void main() {
  final service = PushNotificationService.instance;
  late _PushHarness h;

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    h = _PushHarness();
  });

  tearDown(() {
    service.resetForTest();
  });

  testWidgets('normal cold start: listeners, one prompt, one registration', (
    tester,
  ) async {
    service.resetForTest(hooks: h.hooks);
    await service.initialize();

    expect(h.allListenersAttached, isTrue);
    expect(service.isSetupComplete, isTrue);
    expect(h.permissionRequests, 1);
    expect(h.localNotificationInits, 1);
    expect(h.syncCalls, 1);
    expect(h.initialMessageReads, 1);

    await _settle(tester, const Duration(hours: 1));
    expect(h.syncCalls, 1, reason: 'nothing to retry');
  });

  testWidgets('offline start: a failed settings read no longer costs the '
      'session its listeners', (tester) async {
    h.settingsError = StateError('unavailable');
    service.resetForTest(hooks: h.hooks);
    await service.initialize();

    expect(h.allListenersAttached, isTrue);
    // The rest of the set-up still ran, on the default settings.
    expect(h.localNotificationInits, 1);
    expect(h.permissionRequests, 1);
    expect(h.syncCalls, 1);
    expect(service.isSetupComplete, isTrue);

    h.onOpened.add(_tap('a'));
    expect(h.opened, hasLength(1));
  });

  testWidgets('a failing step is retried and nothing is subscribed twice', (
    tester,
  ) async {
    h.localNotificationsError = StateError('plugin not ready');
    service.resetForTest(hooks: h.hooks);
    await service.initialize();

    expect(h.allListenersAttached, isTrue);
    expect(service.isSetupComplete, isFalse);

    // Listeners work while set-up is still incomplete.
    h.onTokenRefresh.add('token-2');
    await _settle(tester);
    expect(h.syncCalls, 2);

    h.localNotificationsError = null;
    await _settle(tester, PushNotificationService.setupRetryDelays[0]);

    expect(service.isSetupComplete, isTrue);
    expect(h.localNotificationInits, 2);
    expect(h.permissionRequests, 1, reason: 'the prompt is not repeated');
    expect(h.initialMessageReads, 1);

    final syncsBefore = h.syncCalls;
    h.onTokenRefresh.add('token-3');
    await _settle(tester);
    expect(
      h.syncCalls,
      syncsBefore + 1,
      reason: 'one token-refresh subscription, not two',
    );
  });

  testWidgets('transient registration failure: bounded retry, then resume', (
    tester,
  ) async {
    h.syncError = StateError('firestore unavailable');
    service.resetForTest(hooks: h.hooks);
    await service.initialize();
    expect(service.isSetupComplete, isFalse);
    expect(h.syncCalls, 1);

    for (final delay in PushNotificationService.setupRetryDelays) {
      await _settle(tester, delay);
    }
    final budget = 1 + PushNotificationService.setupRetryDelays.length;
    expect(h.syncCalls, budget);

    await _settle(tester, const Duration(hours: 6));
    expect(h.syncCalls, budget, reason: 'the retry is bounded');
    expect(service.isSetupComplete, isFalse);

    // App resume tries again and succeeds.
    h.syncError = null;
    _resume(service);
    await _settle(tester);
    expect(h.syncCalls, budget + 1);
    expect(service.isSetupComplete, isTrue);
    expect(h.permissionRequests, 1);
  });

  testWidgets('no token yet (APNs not ready) is retried, not forgotten', (
    tester,
  ) async {
    h.tokenSettled = false;
    service.resetForTest(hooks: h.hooks);
    await service.initialize();
    expect(service.isSetupComplete, isFalse);

    h.tokenSettled = true;
    await _settle(tester, PushNotificationService.setupRetryDelays[0]);
    expect(service.isSetupComplete, isTrue);
  });

  testWidgets('permission denied: set-up completes and the device is still '
      'registered; re-granting is picked up on resume', (tester) async {
    h.permission = AuthorizationStatus.denied;
    service.resetForTest(hooks: h.hooks);
    await service.initialize();

    expect(service.isSetupComplete, isTrue);
    expect(h.allListenersAttached, isTrue);
    expect(h.syncCalls, 1);

    // Still denied on a resume: nothing to do.
    _resume(service);
    await _settle(tester);
    expect(h.syncCalls, 1);

    // The user grants it in the system settings and comes back.
    h.permission = AuthorizationStatus.authorized;
    _resume(service);
    await _settle(tester);
    expect(h.syncCalls, 2);
    expect(h.permissionRequests, 1);

    // Unchanged afterwards: no further writes.
    _resume(service);
    await _settle(tester);
    expect(h.syncCalls, 2);
  });

  testWidgets('a failing permission request does not block the rest', (
    tester,
  ) async {
    h.permissionError = StateError('platform error');
    service.resetForTest(hooks: h.hooks);
    await service.initialize();

    expect(h.allListenersAttached, isTrue);
    expect(h.syncCalls, 1);
    expect(h.initialMessageReads, 1);
    expect(service.isSetupComplete, isFalse);

    h.permissionError = null;
    await _settle(tester, PushNotificationService.setupRetryDelays[0]);
    expect(service.isSetupComplete, isTrue);
    expect(h.permissionRequests, 2);
  });

  testWidgets('all notifications turned off: no system prompt', (tester) async {
    h.settings = {...h.settings, 'all': false};
    service.resetForTest(hooks: h.hooks);
    await service.initialize();

    expect(h.permissionRequests, 0);
    expect(service.isSetupComplete, isTrue);
    expect(h.allListenersAttached, isTrue);
  });

  testWidgets('re-init, logout then login and account switch never add a '
      'subscription', (tester) async {
    service.resetForTest(hooks: h.hooks);
    await service.initialize();
    await service.initialize();
    await service.initialize();
    // Login / account switch paths call syncFcmToken, never a re-attach.
    await service.syncFcmToken();
    await service.syncFcmToken();
    _resume(service);
    await _settle(tester);

    final syncsBefore = h.syncCalls;
    h.onTokenRefresh.add('rotated');
    await _settle(tester);
    expect(h.syncCalls, syncsBefore + 1);

    h.onOpened.add(_tap('x'));
    h.onOpened.add(_tap('y'));
    expect(h.opened.map((m) => m.messageId), ['x', 'y']);
    expect(h.permissionRequests, 1);
    expect(h.localNotificationInits, 1);
  });

  testWidgets('the launch notification is opened once, even across a retry', (
    tester,
  ) async {
    h.initialMessage = _tap('launch');
    h.syncError = StateError('offline');
    service.resetForTest(hooks: h.hooks);
    await service.initialize();
    expect(h.opened, hasLength(1));

    h.syncError = null;
    await _settle(tester, PushNotificationService.setupRetryDelays[0]);
    expect(service.isSetupComplete, isTrue);
    expect(h.initialMessageReads, 1);
    expect(h.opened, hasLength(1));

    // The same tap delivered again through the stream is deduplicated.
    h.onOpened.add(_tap('launch'));
    expect(h.opened, hasLength(1));
  });

  testWidgets('a failing launch-notification read is retried', (tester) async {
    h.initialMessageError = StateError('platform error');
    service.resetForTest(hooks: h.hooks);
    await service.initialize();
    expect(service.isSetupComplete, isFalse);
    expect(h.allListenersAttached, isTrue);

    h.initialMessageError = null;
    h.initialMessage = _tap('late');
    await _settle(tester, PushNotificationService.setupRetryDelays[0]);
    expect(service.isSetupComplete, isTrue);
    expect(h.opened, hasLength(1));
  });
}
