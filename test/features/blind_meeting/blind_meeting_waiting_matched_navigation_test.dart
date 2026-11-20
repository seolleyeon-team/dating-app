// 매칭 대기 화면 위에 다른 화면이 떠 있는 동안 매칭이 확정돼도, 결과 화면에서
// 뒤로 갔을 때 빠져나갈 수 없는 대기 화면이 남아 있으면 안 된다.

import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
// ignore: depend_on_referenced_packages
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seolleyeon/features/blind_meeting/data/blind_meeting_repository.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_application.dart';
import 'package:seolleyeon/features/blind_meeting/domain/blind_meeting_enums.dart';
import 'package:seolleyeon/features/blind_meeting/presentation/screens/blind_meeting_waiting_screen.dart';
import 'package:seolleyeon/router/route_names.dart';

class _StreamRepository extends BlindMeetingRepository {
  final StreamController<BlindMeetingApplication?> controller =
      StreamController<BlindMeetingApplication?>.broadcast();

  @override
  Stream<BlindMeetingApplication?> watchMyApplication() => controller.stream;
}

const _overlayRoute = '/test-overlay';

// 대기 화면에는 끝나지 않는 진행 애니메이션이 있어 pumpAndSettle 을 쓸 수 없다.
Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 12; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    setupFirebaseCoreMocks();
    await Firebase.initializeApp();
  });

  testWidgets('대기 화면 위에 다른 화면이 있어도 매칭되면 대기 화면까지 정리하고 결과로 간다', (tester) async {
    final repository = _StreamRepository();
    addTearDown(repository.controller.close);
    final navigatorKey = GlobalKey<NavigatorState>();

    await tester.pumpWidget(
      MaterialApp(
        navigatorKey: navigatorKey,
        initialRoute: RouteNames.blindTasteMeeting,
        onGenerateRoute: (settings) => MaterialPageRoute<void>(
          settings: settings,
          builder: (_) => switch (settings.name) {
            RouteNames.blindTasteMeetingWaiting => BlindMeetingWaitingScreen(
              repository: repository,
            ),
            RouteNames.blindTasteMeetingResult => const Scaffold(
              body: Text('RESULT'),
            ),
            _overlayRoute => const Scaffold(body: Text('OVERLAY')),
            _ => const Scaffold(body: Text('INTRO')),
          },
        ),
      ),
    );
    final navigator = navigatorKey.currentState!;
    unawaited(navigator.pushNamed(RouteNames.blindTasteMeetingWaiting));
    await _settle(tester);
    repository.controller.add(
      BlindMeetingApplication(
        userId: 'u1',
        status: BlindMeetingParticipantStatus.applied,
        stage: BlindMeetingMatchingStage.searchingCandidates,
        requestedDateKeys: const ['2026-08-11'],
      ),
    );
    await _settle(tester);

    // DNA 수정 등 대기 화면 위에 올라간 화면.
    unawaited(navigator.pushNamed(_overlayRoute));
    await _settle(tester);
    expect(find.text('OVERLAY'), findsOneWidget);

    repository.controller.add(
      BlindMeetingApplication(
        userId: 'u1',
        status: BlindMeetingParticipantStatus.confirmed,
        stage: BlindMeetingMatchingStage.searchingCandidates,
        requestedDateKeys: const ['2026-08-11'],
        meetingId: 'm1',
      ),
    );
    await _settle(tester);
    expect(find.text('RESULT'), findsOneWidget);

    navigator.pop();
    await _settle(tester);

    expect(find.text('INTRO'), findsOneWidget);
    expect(find.byType(BlindMeetingWaitingScreen), findsNothing);
    expect(find.text('OVERLAY'), findsNothing);
  });
}
