import 'dart:async';
import 'dart:math' as math;

import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/notifications/models/app_notification.dart';
import 'package:seolleyeon/features/notifications/screens/notification_list_screen.dart';
import 'package:seolleyeon/features/notifications/services/notification_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeNotificationService extends NotificationService {
  _FakeNotificationService({required this.stored});

  /// How many notifications the account has on the server.
  final int stored;

  final calls = <(String, int)>[];
  int activeListeners = 0;
  int documentsDelivered = 0;

  @override
  Stream<List<AppNotification>> notificationsStream(
    String userId, {
    int limit = NotificationService.pageSize,
  }) {
    calls.add((userId, limit));
    late final StreamController<List<AppNotification>> controller;
    controller = StreamController<List<AppNotification>>(
      onListen: () {
        activeListeners += 1;
        final count = math.min(limit, stored);
        documentsDelivered += count;
        controller.add([
          for (var i = 0; i < count; i++)
            AppNotification(
              id: 'n$i',
              type: 'chat_digest',
              title: 'title $i',
              body: 'body $i',
              isRead: i.isOdd,
              createdAt: DateTime(2026, 11, 21).subtract(Duration(hours: i)),
            ),
        ]);
      },
      onCancel: () => activeListeners -= 1,
    );
    return controller.stream;
  }
}

class _Parent extends StatefulWidget {
  const _Parent({required this.service});

  final _FakeNotificationService service;

  @override
  State<_Parent> createState() => _ParentState();
}

class _ParentState extends State<_Parent> {
  void rebuild() => setState(() {});

  @override
  Widget build(BuildContext context) {
    return CupertinoApp(
      home: NotificationListScreen(notificationService: widget.service),
    );
  }
}

Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.pump(const Duration(milliseconds: 50));
  }
}

/// Jumps to the end of what is loaded. The screen scrolls with bouncing
/// physics, so a long drag would overscroll far past the list instead.
Future<void> _scrollToEnd(WidgetTester tester) async {
  final position = tester
      .state<ScrollableState>(find.byType(Scrollable).first)
      .position;
  position.jumpTo(position.maxScrollExtent);
  await _settle(tester);
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    if (Firebase.apps.isEmpty) await Firebase.initializeApp();
  });

  setUp(() {
    SharedPreferences.setMockInitialValues({'kakao_user_id': 'user-a'});
  });

  testWidgets('rebuilds do not reopen the notification listener', (
    tester,
  ) async {
    final service = _FakeNotificationService(stored: 12);
    await tester.pumpWidget(_Parent(service: service));
    await _settle(tester);
    expect(find.text('title 0'), findsOneWidget);

    final parent = tester.state<_ParentState>(find.byType(_Parent));
    for (var i = 0; i < 6; i++) {
      parent.rebuild();
      await tester.pump();
    }

    expect(service.calls, [('user-a', NotificationService.pageSize)]);
    expect(service.activeListeners, 1);
    expect(service.documentsDelivered, 12);
  });

  testWidgets('listens to one page and widens the window at the end of the '
      'list', (tester) async {
    final service = _FakeNotificationService(stored: 80);
    await tester.pumpWidget(_Parent(service: service));
    await _settle(tester);

    // 80 stored, one page delivered.
    expect(service.calls, [('user-a', 50)]);
    expect(service.documentsDelivered, 50);
    expect(find.textContaining('개 이상 있어요'), findsOneWidget);

    await _scrollToEnd(tester);

    expect(service.calls, [('user-a', 50), ('user-a', 100)]);
    expect(service.activeListeners, 1, reason: 'the old window is cancelled');
    // The list stayed on screen while the wider window loaded.
    expect(find.byType(CupertinoActivityIndicator), findsNothing);

    // All 80 are loaded now: the end of the list asks for nothing more.
    await _scrollToEnd(tester);
    await _scrollToEnd(tester);

    expect(service.calls, hasLength(2));
    expect(find.text('title 79'), findsOneWidget);
    expect(find.textContaining('개 이상 있어요'), findsNothing);
  });
}
